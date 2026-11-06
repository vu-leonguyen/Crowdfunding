// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IGovernanceToken
 * @notice Interface for the CrowdOps ERC-20 Governance Token ($CROPS).
 */
interface IGovernanceToken {
    function mint(address to, uint256 amount) external;
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
}
