// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./ICrowdOps.sol";
import "../tokens/IGovernanceToken.sol";
import "../tokens/IDiamondPatronNFT.sol";

/**
 * @title CrowdOpsPlatform
 * @notice Core Escrow Vault & Milestone Governance Platform for Decentralized Crowdfunding.
 * @dev Enforces Code-based Trust: Funds are locked on-chain and disbursed only through milestone-based community approvals.
 */
contract CrowdOpsPlatform is ICrowdOps, ReentrancyGuard, Ownable {
    // ========================================================
    // CONSTANTS & IMMUTABLES
    // ========================================================

    uint256 public constant MIN_DURATION = 1 minutes; // Flexible for local testing / production
    uint256 public constant DIAMOND_TIER_THRESHOLD = 1 ether;
    uint256 public constant TOKEN_RATE = 1000; // 1 ETH = 1,000 $CROPS tokens

    // ========================================================
    // STORAGE
    // ========================================================

    uint256 public campaignCounter;
    IGovernanceToken public governanceToken;
    IDiamondPatronNFT public diamondNFT;

    struct SpendingRequestInternal {
        uint256 id;
        string description;
        uint256 amount;
        address payable recipient;
        string proofCID;
        uint256 approvalWeight;
        uint256 rejectWeight;
        bool completed;
        bool rejected;
        mapping(address => VoteType) votes;
    }

    struct CampaignInternal {
        uint256 id;
        address payable creator;
        string title;
        string description;
        string proposalCID;
        uint256 goal;
        uint256 deadline;
        uint256 totalFundsRaised;
        uint256 remainingFunds;
        CampaignState state;
        uint256 requestCount;
        mapping(uint256 => SpendingRequestInternal) requests;
        mapping(address => uint256) contributions;
    }

    mapping(uint256 => CampaignInternal) private _campaigns;

    // ========================================================
    // MODIFIERS
    // ========================================================

    modifier campaignExists(uint256 campaignId) {
        if (campaignId == 0 || campaignId > campaignCounter) {
            revert CampaignNotFound(campaignId);
        }
        _;
    }

    modifier onlyCreator(uint256 campaignId) {
        if (_campaigns[campaignId].creator != msg.sender) {
            revert Unauthorized(msg.sender);
        }
        _;
    }

    // ========================================================
    // CONSTRUCTOR
    // ========================================================

    constructor() Ownable(msg.sender) {}

    // ========================================================
    // CONFIGURATION
    // ========================================================

    /**
     * @notice Link the platform to GovernanceToken (ERC-20) and DiamondPatronNFT (ERC-721).
     * @param _governanceToken Address of the ERC-20 token contract.
     * @param _diamondNFT Address of the ERC-721 NFT contract.
     */
    function setTokenContracts(address _governanceToken, address _diamondNFT) external onlyOwner {
        governanceToken = IGovernanceToken(_governanceToken);
        diamondNFT = IDiamondPatronNFT(_diamondNFT);
    }

    // ========================================================
    // GIAI ĐOẠN 1: NGHIỆP VỤ GỌI VỐN (DAYS 1 - 4)
    // ========================================================

    /**
     * @notice Initializes a new crowdfunding campaign.
     * @param title Title of the campaign.
     * @param description Brief description / executive summary.
     * @param proposalCID IPFS CID pointing to the full Whitepaper / Proposal PDF.
     * @param goal Target funding amount in Wei.
     * @param durationInSeconds Campaign active duration in seconds.
     * @return campaignId Unique identifier of the created campaign.
     */
    function createCampaign(
        string calldata title,
        string calldata description,
        string calldata proposalCID,
        uint256 goal,
        uint256 durationInSeconds
    ) external override returns (uint256 campaignId) {
        if (goal == 0) revert InvalidGoal();
        if (durationInSeconds < MIN_DURATION) revert InvalidDeadline();
        if (bytes(title).length == 0 || bytes(proposalCID).length == 0) revert EmptyString();

        campaignCounter++;
        campaignId = campaignCounter;

        CampaignInternal storage c = _campaigns[campaignId];
        c.id = campaignId;
        c.creator = payable(msg.sender);
        c.title = title;
        c.description = description;
        c.proposalCID = proposalCID;
        c.goal = goal;
        c.deadline = block.timestamp + durationInSeconds;
        c.state = CampaignState.Fundraising;

        emit CampaignCreated(
            campaignId,
            msg.sender,
            title,
            goal,
            c.deadline,
            proposalCID
        );
    }

    /**
     * @notice Backers contribute ETH to support a campaign.
     * @dev Automatically mints Governance Tokens ($CROPS) and Diamond Patron NFT if tier is reached.
     * @param campaignId ID of the campaign to contribute to.
     */
    function contribute(uint256 campaignId)
        external
        payable
        override
        nonReentrant
        campaignExists(campaignId)
    {
        if (msg.value == 0) revert ZeroContribution();

        CampaignInternal storage c = _campaigns[campaignId];

        if (block.timestamp >= c.deadline) {
            revert CampaignDeadlinePassed(campaignId, c.deadline);
        }

        if (c.state != CampaignState.Fundraising) {
            revert CampaignNotActive(campaignId, c.state);
        }

        c.contributions[msg.sender] += msg.value;
        c.totalFundsRaised += msg.value;
        c.remainingFunds += msg.value;

        // Transition state if goal reached
        if (c.totalFundsRaised >= c.goal && c.state == CampaignState.Fundraising) {
            c.state = CampaignState.Successful;
            emit CampaignStateChanged(campaignId, CampaignState.Successful);
        }

        // Mint ERC-20 Governance Token ($CROPS)
        if (address(governanceToken) != address(0)) {
            uint256 tokenAmount = (msg.value * TOKEN_RATE);
            governanceToken.mint(msg.sender, tokenAmount);
        }

        // Mint Diamond Patron NFT if contribution reaches threshold
        if (
            address(diamondNFT) != address(0) &&
            c.contributions[msg.sender] >= DIAMOND_TIER_THRESHOLD &&
            diamondNFT.balanceOf(msg.sender) == 0
        ) {
            diamondNFT.mintDiamondBadge(msg.sender, c.proposalCID);
        }

        emit FundContributed(campaignId, msg.sender, msg.value, c.totalFundsRaised);
    }

    /**
     * @notice Refunds a backer's contribution if the campaign failed to reach its goal by the deadline.
     * @dev Protected with nonReentrant and strictly adheres to Checks-Effects-Interactions pattern.
     * @param campaignId ID of the failed campaign.
     */
    function refund(uint256 campaignId)
        external
        override
        nonReentrant
        campaignExists(campaignId)
    {
        CampaignInternal storage c = _campaigns[campaignId];

        // Evaluate whether campaign has failed
        if (c.state == CampaignState.Fundraising) {
            if (block.timestamp < c.deadline) {
                revert CampaignStillActive(campaignId, c.deadline);
            }
            if (c.totalFundsRaised >= c.goal) {
                c.state = CampaignState.Successful;
                emit CampaignStateChanged(campaignId, CampaignState.Successful);
                revert RefundNotAvailable(campaignId);
            }
            c.state = CampaignState.Failed;
            emit CampaignStateChanged(campaignId, CampaignState.Failed);
        } else if (c.state != CampaignState.Failed) {
            revert RefundNotAvailable(campaignId);
        }

        uint256 backerContribution = c.contributions[msg.sender];
        if (backerContribution == 0) revert NoContributionToRefund();

        // CHECKS-EFFECTS-INTERACTIONS: Zero out state BEFORE transfer
        c.contributions[msg.sender] = 0;
        c.remainingFunds -= backerContribution;

        // Transfer funds back to backer
        (bool success, ) = payable(msg.sender).call{value: backerContribution}("");
        if (!success) revert TransferFailed();

        emit RefundClaimed(campaignId, msg.sender, backerContribution);
    }

    // ========================================================
    // GIAI ĐOẠN 2: CƠ CHẾ MILESTONE SPENDING & BIỂU QUYẾT
    // ========================================================

    /**
     * @notice Campaign Creator submits a milestone spending request with an IPFS proof/invoice CID.
     */
    function requestSpending(
        uint256 campaignId,
        string calldata description,
        uint256 amount,
        address payable recipient,
        string calldata proofCID
    ) external override campaignExists(campaignId) onlyCreator(campaignId) returns (uint256 requestId) {
        CampaignInternal storage c = _campaigns[campaignId];

        if (c.state != CampaignState.Successful && c.state != CampaignState.Operational) {
            revert CampaignNotActive(campaignId, c.state);
        }

        if (amount == 0 || amount > c.remainingFunds) {
            revert InsufficientRemainingFunds(amount, c.remainingFunds);
        }

        if (recipient == address(0)) revert InvalidRecipient();
        if (bytes(description).length == 0 || bytes(proofCID).length == 0) revert EmptyString();

        c.state = CampaignState.Operational;
        c.requestCount++;
        requestId = c.requestCount;

        SpendingRequestInternal storage req = c.requests[requestId];
        req.id = requestId;
        req.description = description;
        req.amount = amount;
        req.recipient = recipient;
        req.proofCID = proofCID;

        emit SpendingRequestCreated(campaignId, requestId, amount, recipient, proofCID);
    }

    /**
     * @notice Backers vote Approve or Reject on a spending request based on its IPFS proof.
     */
    function approveRequest(
        uint256 campaignId,
        uint256 requestId,
        VoteType vote
    ) external override campaignExists(campaignId) {
        CampaignInternal storage c = _campaigns[campaignId];
        uint256 backerWeight = c.contributions[msg.sender];
        if (backerWeight == 0) revert NotABacker(msg.sender);

        if (requestId == 0 || requestId > c.requestCount) {
            revert SpendingRequestNotFound(requestId);
        }

        SpendingRequestInternal storage req = c.requests[requestId];
        if (req.completed) revert RequestAlreadyCompleted(requestId);
        if (req.rejected) revert RequestAlreadyClosed(requestId);
        if (req.votes[msg.sender] != VoteType.None) revert AlreadyVoted(msg.sender);

        req.votes[msg.sender] = vote;

        if (vote == VoteType.Approve) {
            req.approvalWeight += backerWeight;
        } else if (vote == VoteType.Reject) {
            req.rejectWeight += backerWeight;
            // If reject weight reaches 50% or more, lock request permanently
            if (req.rejectWeight * 2 >= c.totalFundsRaised) {
                req.rejected = true;
                emit SpendingRejected(campaignId, requestId);
            }
        }

        emit VoteCast(campaignId, requestId, msg.sender, vote, backerWeight);
    }

    /**
     * @notice Releases milestone funds to the recipient once approval threshold (> 50%) is achieved.
     */
    function finalizeSpending(uint256 campaignId, uint256 requestId)
        external
        override
        nonReentrant
        campaignExists(campaignId)
        onlyCreator(campaignId)
    {
        CampaignInternal storage c = _campaigns[campaignId];

        if (requestId == 0 || requestId > c.requestCount) {
            revert SpendingRequestNotFound(requestId);
        }

        SpendingRequestInternal storage req = c.requests[requestId];
        if (req.completed) revert RequestAlreadyCompleted(requestId);
        if (req.rejected) revert RequestAlreadyClosed(requestId);

        // Code-based Trust: Approval weight must strictly exceed 50% of total funds raised
        if (req.approvalWeight * 2 <= c.totalFundsRaised) {
            revert ApprovalThresholdNotMet(req.approvalWeight, c.totalFundsRaised);
        }

        if (req.amount > c.remainingFunds) {
            revert InsufficientRemainingFunds(req.amount, c.remainingFunds);
        }

        // CHECKS-EFFECTS-INTERACTIONS: Mark completed BEFORE sending funds
        req.completed = true;
        c.remainingFunds -= req.amount;

        if (c.remainingFunds == 0) {
            c.state = CampaignState.Closed;
            emit CampaignStateChanged(campaignId, CampaignState.Closed);
        }

        (bool success, ) = req.recipient.call{value: req.amount}("");
        if (!success) revert TransferFailed();

        emit SpendingFinalized(campaignId, requestId, req.amount, req.recipient);
    }

    // ========================================================
    // VIEW GETTERS
    // ========================================================

    function getCampaign(uint256 campaignId)
        external
        view
        override
        campaignExists(campaignId)
        returns (CampaignView memory)
    {
        CampaignInternal storage c = _campaigns[campaignId];
        return CampaignView({
            id: c.id,
            creator: c.creator,
            title: c.title,
            description: c.description,
            proposalCID: c.proposalCID,
            goal: c.goal,
            deadline: c.deadline,
            totalFundsRaised: c.totalFundsRaised,
            remainingFunds: c.remainingFunds,
            state: c.state,
            requestCount: c.requestCount
        });
    }

    function getSpendingRequest(uint256 campaignId, uint256 requestId)
        external
        view
        override
        campaignExists(campaignId)
        returns (SpendingRequestView memory)
    {
        CampaignInternal storage c = _campaigns[campaignId];
        if (requestId == 0 || requestId > c.requestCount) {
            revert SpendingRequestNotFound(requestId);
        }
        SpendingRequestInternal storage req = c.requests[requestId];
        return SpendingRequestView({
            id: req.id,
            description: req.description,
            amount: req.amount,
            recipient: req.recipient,
            proofCID: req.proofCID,
            approvalWeight: req.approvalWeight,
            rejectWeight: req.rejectWeight,
            completed: req.completed,
            rejected: req.rejected
        });
    }

    function getContribution(uint256 campaignId, address backer)
        external
        view
        override
        campaignExists(campaignId)
        returns (uint256)
    {
        return _campaigns[campaignId].contributions[backer];
    }

    function hasVoted(uint256 campaignId, uint256 requestId, address backer)
        external
        view
        override
        campaignExists(campaignId)
        returns (bool)
    {
        CampaignInternal storage c = _campaigns[campaignId];
        if (requestId == 0 || requestId > c.requestCount) return false;
        return c.requests[requestId].votes[backer] != VoteType.None;
    }
}
