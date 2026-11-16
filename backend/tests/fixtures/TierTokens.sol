// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";

// Integration fixtures only. TV2's production contracts remain a separate task.
contract TierGovernanceFixture is ERC20 {
    constructor(address member) ERC20("Test CROPS", "TCROPS") {
        _mint(member, 1000 * 10 ** decimals());
    }
}

contract TierDiamondFixture is ERC721 {
    constructor(address member) ERC721("Test Diamond", "TDIAMOND") {
        _mint(member, 1);
    }
}
