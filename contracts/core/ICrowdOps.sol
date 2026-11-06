// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ICrowdOps
 * @notice Interface defining the data types, events, custom errors, and function specifications
 * for the CrowdOps Decentralized Crowdfunding Platform.
 */
interface ICrowdOps {
    // ========================================================
    // ENUMS
    // ========================================================

    enum CampaignState {
        Fundraising, // Actively receiving contributions before deadline
        Successful,  // Reached goal before deadline
        Failed,      // Deadline passed without reaching goal (eligible for refund)
        Operational, // Goal achieved, actively managing milestone spending requests
        Closed       // All milestones completed, all funds disbursed
    }

    enum VoteType {
        None,
        Approve,
        Reject
    }

    // ========================================================
    // STRUCTS
    // ========================================================

    struct SpendingRequestView {
        uint256 id;
        string description;
        uint256 amount;
        address payable recipient;
        string proofCID;
        uint256 approvalWeight;
        uint256 rejectWeight;
        bool completed;
        bool rejected;
    }

    struct CampaignView {
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
    }

    // ========================================================
    // CUSTOM ERRORS
    // ========================================================

    error InvalidGoal();
    error InvalidDeadline();
    error EmptyString();
    error CampaignNotFound(uint256 campaignId);
    error CampaignNotActive(uint256 campaignId, CampaignState state);
    error CampaignDeadlinePassed(uint256 campaignId, uint256 deadline);
    error CampaignStillActive(uint256 campaignId, uint256 deadline);
    error ZeroContribution();
    error RefundNotAvailable(uint256 campaignId);
    error NoContributionToRefund();
    error Unauthorized(address caller);
    error TransferFailed();
    error SpendingRequestNotFound(uint256 requestId);
    error RequestAlreadyCompleted(uint256 requestId);
    error RequestAlreadyClosed(uint256 requestId);
    error AlreadyVoted(address voter);
    error NotABacker(address caller);
    error InsufficientRemainingFunds(uint256 requested, uint256 available);
    error ApprovalThresholdNotMet(uint256 approvalWeight, uint256 totalWeight);
    error InvalidRecipient();

    // ========================================================
    // EVENTS
    // ========================================================

    event CampaignCreated(
        uint256 indexed campaignId,
        address indexed creator,
        string title,
        uint256 goal,
        uint256 deadline,
        string proposalCID
    );

    event FundContributed(
        uint256 indexed campaignId,
        address indexed backer,
        uint256 amount,
        uint256 totalRaised
    );

    event CampaignStateChanged(
        uint256 indexed campaignId,
        CampaignState newState
    );

    event SpendingRequestCreated(
        uint256 indexed campaignId,
        uint256 indexed requestId,
        uint256 amount,
        address indexed recipient,
        string proofCID
    );

    event VoteCast(
        uint256 indexed campaignId,
        uint256 indexed requestId,
        address indexed backer,
        VoteType vote,
        uint256 weight
    );

    event SpendingFinalized(
        uint256 indexed campaignId,
        uint256 indexed requestId,
        uint256 amount,
        address indexed recipient
    );

    event SpendingRejected(
        uint256 indexed campaignId,
        uint256 indexed requestId
    );

    event RefundClaimed(
        uint256 indexed campaignId,
        address indexed backer,
        uint256 amount
    );

    // ========================================================
    // FUNCTIONS
    // ========================================================

    function createCampaign(
        string calldata title,
        string calldata description,
        string calldata proposalCID,
        uint256 goal,
        uint256 durationInSeconds
    ) external returns (uint256 campaignId);

    function contribute(uint256 campaignId) external payable;

    function refund(uint256 campaignId) external;

    function requestSpending(
        uint256 campaignId,
        string calldata description,
        uint256 amount,
        address payable recipient,
        string calldata proofCID
    ) external returns (uint256 requestId);

    function approveRequest(
        uint256 campaignId,
        uint256 requestId,
        VoteType vote
    ) external;

    function finalizeSpending(uint256 campaignId, uint256 requestId) external;

    function getCampaign(uint256 campaignId) external view returns (CampaignView memory);

    function getSpendingRequest(uint256 campaignId, uint256 requestId)
        external
        view
        returns (SpendingRequestView memory);

    function getContribution(uint256 campaignId, address backer) external view returns (uint256);

    function hasVoted(uint256 campaignId, uint256 requestId, address backer)
        external
        view
        returns (bool);
}
