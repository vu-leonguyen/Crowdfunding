// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IDiamondPatronNFT
 * @notice Interface for the CrowdOps ERC-721 Diamond Patron NFT ($DIAMOND).
 */
interface IDiamondPatronNFT {
    function mintDiamondBadge(address recipient, string calldata metadataURI) external returns (uint256);
    function balanceOf(address owner) external view returns (uint256);
    function ownerOf(uint256 tokenId) external view returns (address);
}
