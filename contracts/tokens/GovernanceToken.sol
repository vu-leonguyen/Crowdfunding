// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./IGovernanceToken.sol";

/**
 * @title GovernanceToken
 * @notice ERC-20 Governance Token ($CROPS) for the CrowdOps Decentralized Crowdfunding Platform.
 * @dev Only the authorized CrowdOpsPlatform contract can mint $CROPS when backers contribute ETH.
 */
contract GovernanceToken is ERC20, Ownable, IGovernanceToken {
    address public platformContract;

    error UnauthorizedMinter(address caller);
    error ZeroAddress();
    error ZeroAmount();

    event PlatformContractUpdated(address indexed oldPlatform, address indexed newPlatform);
    event TokensMinted(address indexed to, uint256 amount);

    modifier onlyPlatform() {
        if (msg.sender != platformContract) {
            revert UnauthorizedMinter(msg.sender);
        }
        _;
    }

    constructor() ERC20("CrowdOps Governance Token", "CROPS") Ownable(msg.sender) {}

    /**
     * @notice Sets or updates the authorized CrowdOpsPlatform contract address.
     * @param _platformContract Address of the CrowdOpsPlatform contract.
     */
    function setPlatformContract(address _platformContract) external onlyOwner {
        if (_platformContract == address(0)) revert ZeroAddress();
        address oldPlatform = platformContract;
        platformContract = _platformContract;
        emit PlatformContractUpdated(oldPlatform, _platformContract);
    }

    /**
     * @notice Mints governance tokens to a backer upon ETH contribution.
     * @param to Recipient backer address.
     * @param amount Token amount in 18-decimal wei units.
     */
    function mint(address to, uint256 amount) external override onlyPlatform {
        if (to == address(0)) revert ZeroAddress();
        if (amount == 0) revert ZeroAmount();
        _mint(to, amount);
        emit TokensMinted(to, amount);
    }

    /// @inheritdoc IGovernanceToken
    function balanceOf(address account)
        public
        view
        override(ERC20, IGovernanceToken)
        returns (uint256)
    {
        return super.balanceOf(account);
    }

    /// @inheritdoc IGovernanceToken
    function transfer(address to, uint256 value)
        public
        override(ERC20, IGovernanceToken)
        returns (bool)
    {
        return super.transfer(to, value);
    }
}
