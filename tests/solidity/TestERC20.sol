solidity// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "../../contracts/ERC20Token.sol";
import "@openzeppelin/contracts/utils/math/SafeMath.sol";

contract TestERC20 {
    using SafeMath for uint256;
    
    ERC20Token public token;
    address public owner;
    address public user1;
    address public user2;
    
    event TestResult(string test, bool passed);
    
    constructor() {
        owner = msg.sender;
        user1 = address(0x1);
        user2 = address(0x2);
        
        // Deploy test token
        token = new ERC20Token(
            "Test Token",
            "TEST",
            18,
            1000000 * 10**18  // 1M tokens
        );
    }
    
    function testInitialState() external {
        bool passed = true;
        
        // Check initial supply
        if (token.totalSupply() != 1000000 * 10**18) {
            passed = false;
        }
        
        // Check owner balance
        if (token.balanceOf(owner) != 1000000 * 10**18) {
            passed = false;
        }
        
        // Check token details
        if (keccak256(bytes(token.name())) != keccak256(bytes("Test Token"))) {
            passed = false;
        }
        
        if (keccak256(bytes(token.symbol())) != keccak256(bytes("TEST"))) {
            passed = false;
        }
        
        if (token.decimals() != 18) {
            passed = false;
        }
        
        emit TestResult("testInitialState", passed);
    }
    
    function testTransfer() external {
        bool passed = true;
        uint256 transferAmount = 1000 * 10**18;
        
        // Transfer tokens
        try token.transfer(user1, transferAmount) {
            // Check balances
            if (token.balanceOf(user1) != transferAmount) {
                passed = false;
            }
            
            if (token.balanceOf(owner) != (1000000### simulator/metrics.py
```python
#!/usr/bin/env python3
"""
Metrics Calculator - Computes trading and AMM performance metrics
"""

import math
from typing import Dict, Any, List, Optional
from web3 import Web3
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class MetricsCalculator:
    """
    Calculates various DeFi and trading metrics:
    - Slippage
    - Impermanent Loss
    - Volume-Weighted Average Price (VWAP)
    - Fee accrual
    - Gas cost accounting
    - Liquidity utilization
    """
    
    def __init__(self, w3: Web3, contracts: Dict[str, Any]):
        """
        Initialize metrics calculator
        
        Args:
            w3: Web3 instance
            contracts: Dictionary of deployed contracts
        """
        self.w3 = w3
        self.contracts = contracts
        
        # Get AMM contract
        self.amm_address = contracts['AMM']['address']
        self.amm_contract = self.w3.eth.contract(
            address=self.amm_address,
            abi=contracts['AMM']['abi']
        )
        
        # Track historical data
        self.price_history = []
        self.volume_history = []
        self.reserve_history = []
        self.gas_price_history = []
        
        logger.info("📊 Metrics calculator initialized")
    
    def get_current_market_state(self) -> Dict[str, Any]:
        """Get current market state for all contracts"""
        try:
            # Get AMM reserves
            reserves = self.amm_contract.functions.getReserves().call()
            reserve_a, reserve_b = reserves[0], reserves[1]
            
            # Calculate current price (token A per token B)
            price = reserve_a / reserve_b if reserve_b > 0 else 0.0
            
            # Get AMM fee
            fee_bps = self.amm_contract.functions.fee().call()
            
            # Get total LP supply
            total_supply = self.amm_contract.functions.totalSupply().call()
            
            # Get current gas price
            try:
                gas_price = self.w3.eth.gas_price
            except:
                gas_price = self.w3.to_wei('20', 'gwei')  # Default fallback
            
            market_state = {
                'timestamp': int(self.w3.eth.get_block('latest')['timestamp']),
                'block_number': self.w3.eth.block_number,
                'reserve_a': reserve_a,
                'reserve_b': reserve_b,
                'price': price,
                'fee_bps': fee_bps,
                'total_lp_supply': total_supply,
                'gas_price': gas_price,
                'k_invariant': reserve_a * reserve_b
            }
            
            # Store in history
            self.price_history.append({
                'timestamp': market_state['timestamp'],
                'price': price
            })
            
            self.reserve_history.append({
                'timestamp': market_state['timestamp'],
                'reserve_a': reserve_a,
                'reserve_b': reserve_b
            })
            
            self.gas_price_history.append({
                'timestamp': market_state['timestamp'],
                'gas_price': gas_price
            })
            
            return market_state
            
        except Exception as e:
            logger.error(f"Failed to get market state: {e}")
            return {}
    
    def calculate_slippage(self, 
                          amount_in: int, 
                          expected_out: int, 
                          actual_out: int) -> float:
        """
        Calculate sl## 5 — Python Simulation & Tooling
