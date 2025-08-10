#!/usr/bin/env python3
"""
Market Maker Agent Implementation
Provides liquidity to AMM pools and manages LP positions
"""

import math
from typing import Dict, Any, Optional
from .agent_base import AgentBase
import logging

logger = logging.getLogger(__name__)

class MarketMaker(AgentBase):
    """
    Market maker agent that provides liquidity to AMM pools
    Implements basic market making strategies:
    - Provide initial liquidity
    - Rebalance positions
    - Collect fees
    - Manage impermanent loss
    """
    
    def __init__(self, 
                 agent_id: str,
                 private_key: str,
                 w3,
                 contracts: Dict[str, Any],
                 amm_address: str,
                 token_a_address: str,
                 token_b_address: str,
                 initial_balance: Dict[str, float] = None,
                 target_ratio: float = 0.5,
                 rebalance_threshold: float = 0.05,
                 random_seed: Optional[int] = None):
        """
        Initialize market maker agent
        
        Args:
            amm_address: AMM contract address
            token_a_address: First token address
            token_b_address: Second token address
            target_ratio: Target ratio of token A to total liquidity value
            rebalance_threshold: Threshold for triggering rebalance
        """
        super().__init__(agent_id, private_key, w3, contracts, initial_balance, random_seed)
        
        self.amm_address = amm_address
        self.token_a_address = token_a_address
        self.token_b_address = token_b_address
        self.target_ratio = target_ratio
        self.rebalance_threshold = rebalance_threshold
        
        # AMM contract instance
        self.amm_contract = self.w3.eth.contract(
            address=amm_address,
            abi=contracts['AMM']['abi']
        )
        
        # Token contracts
        self.token_a_contract = self.w3.eth.contract(
            address=token_a_address,
            abi=contracts[token_a_address]['abi']
        )
        
        self.token_b_contract = self.w3.eth.contract(
            address=token_b_address,
            abi=contracts[token_b_address]['abi']
        )
        
        # LP position tracking
        self.lp_token_balance = 0
        self.initial_reserves = None
        self.fees_collected = 0.0
        self.impermanent_loss = 0.0
        
        # Strategy parameters
        self.min_liquidity_ratio = 0.1  # Minimum 10% of tokens as liquidity
        self.max_liquidity_ratio = 0.9  # Maximum 90% of tokens as liquidity
        self.fee_collection_threshold = 0.01  # Collect fees when > 1% of position
        
        logger.info(f"🏦 Market Maker {agent_id} initialized for AMM {amm_address}")
    
    def get_lp_balance(self) -> int:
        """Get current LP token balance"""
        try:
            balance = self.amm_contract.functions.balanceOf(self.address).call()
            self.lp_token_balance = balance
            return balance
        except Exception as e:
            logger.error(f"Failed to get LP balance: {e}")
            return 0
    
    def get_pool_reserves(self) -> tuple:
        """Get current pool reserves"""
        try:
            reserves = self.amm_contract.functions.getReserves().call()
            return reserves[0], reserves[1]  # (reserve_a, reserve_b)
        except Exception as e:
            logger.error(f"Failed to get pool reserves: {e}")
            return 0, 0
    
    def calculate_optimal_liquidity_amounts(self, 
                                          available_a: int, 
                                          available_b: int) -> tuple:
        """
        Calculate optimal amounts to add as liquidity based on current pool ratio
        
        Args:
            available_a: Available amount of token A
            available_b: Available amount of token B
            
        Returns:
            Tuple of (amount_a, amount_b) to add as liquidity
        """
        reserve_a, reserve_b = self.get_pool_reserves()
        
        if reserve_a == 0 or reserve_b == 0:
            # Initial liquidity provision - use target ratio
            total_value_a = available_a + (available_b * self.target_ratio / (1 - self.target_ratio))
            amount_a = int(total_value_a * self.target_ratio * self.max_liquidity_ratio)
            amount_b = int(amount_a * (1 - self.target_ratio) / self.target_ratio)
            
            # Ensure we don't exceed available amounts
            amount_a = min(amount_a, available_a)
            amount_b = min(amount_b, available_b)
            
            return amount_a, amount_b
        
        # Calculate optimal amounts based on current pool ratio
        pool_ratio = reserve_a / reserve_b if reserve_b > 0 else 1
        
        # Try using all of token A first
        amount_a = int(available_a * self.max_liquidity_ratio)
        required_b = int(amount_a / pool_ratio)
        
        if required_b <= available_b:
            return amount_a, required_b
        
        # Use all of token B and calculate required A
        amount_b = int(available_b * self.max_liquidity_ratio)
        required_a = int(amount_b * pool_ratio)
        
        if required_a <= available_a:
            return required_a, amount_b
        
        # Scale down proportionally
        scale_factor = min(available_a / required_a, available_b / required_b)
        return int(required_a * scale_factor), int(required_b * scale_factor)
    
    def add_liquidity(self, amount_a: int, amount_b: int) -> Optional[str]:
        """Add liquidity to the AMM pool"""
        try:
            # Approve token spending
            self.approve_token_spending(self.token_a_address, self.amm_address, amount_a)
            self.approve_token_spending(self.token_b_address, self.amm_address, amount_b)
            
            # Calculate minimum amounts (5% slippage tolerance)
            amount_a_min = int(amount_a * 0.95)
            amount_b_min = int(amount_b * 0.95)
            
            # Add liquidity
            transaction = self.amm_contract.functions.addLiquidity(
                amount_a,
                amount_b,
                amount_a_min,
                amount_b_min,
                self.address
            ).build_transaction({})
            
            tx_hash = self.send_transaction(transaction)
            
            # Log the trade
            self.log_trade('ADD_LIQUIDITY', {
                'amount_a': amount_a,
                'amount_b': amount_b,
                'tx_hash': tx_hash
            })
            
            # Store initial reserves if this is first liquidity provision
            if self.initial_reserves is None:
                self.initial_reserves = self.get_pool_reserves()
            
            return tx_hash
            
        except Exception as e:
            logger.error(f"Failed to add liquidity: {e}")
            return None
    
    def remove_liquidity(self, lp_amount: int, min_amount_a: int = 0, min_amount_b: int = 0) -> Optional[str]:
        """Remove liquidity from the AMM pool"""
        try:
            transaction = self.amm_contract.functions.removeLiquidity(
                lp_amount,
                min_amount_a,
                min_amount_b,
                self.address
            ).build_transaction({})
            
            tx_hash = self.send_transaction(transaction)
            
            self.log_trade('REMOVE_LIQUIDITY', {
                'lp_amount': lp_amount,
                'tx_hash': tx_hash
            })
            
            return tx_hash
            
        except Exception as e:
            logger.error(f"Failed to remove liquidity: {e}")
            return None
    
    def calculate_impermanent_loss(self) -> float:
        """Calculate current impermanent loss"""
        if self.initial_reserves is None:
            return 0.0
        
        initial_a, initial_b = self.initial_reserves
        current_a, current_b = self.get_pool_reserves()
        
        if initial_a == 0 or initial_b == 0 or current_a == 0 or current_b == 0:
            return 0.0
        
        # Calculate price ratios
        initial_ratio = initial_a / initial_b
        current_ratio = current_a / current_b
        
        if initial_ratio == 0:
            return 0.0
        
        # Simplified impermanent loss calculation
        ratio_change = current_ratio / initial_ratio
        
        # IL = 2 * sqrt(ratio_change) / (1 + ratio_change) - 1
        il = 2 * math.sqrt(ratio_change) / (1 + ratio_change) - 1
        
        self.impermanent_loss = il
        return il
    
    def should_rebalance(self, market_data: Dict[str, Any]) -> bool:
        """Determine if position should be rebalanced"""
        current_a, current_b = self.get_pool_reserves()
        
        if current_a == 0 or current_b == 0:
            return False
        
        # Calculate current ratio
        total_value = current_a + current_b  # Simplified value calculation
        current_ratio = current_a / total_value
        
        # Check if deviation exceeds threshold
        ratio_deviation = abs(current_ratio - self.target_ratio)
        
        return ratio_deviation > self.rebalance_threshold
    
    def should_act(self, market_data: Dict[str, Any]) -> bool:
        """Determine if market maker should act"""
        # Check if we have liquidity to provide
        balance_a = self.get_token_balance(self.token_a_address)
        balance_b = self.get_token_balance(self.token_b_address)
        
        # Act if we have tokens but no LP position
        lp_balance = self.get_lp_balance()
        if lp_balance == 0 and (balance_a > 0 or balance_b > 0):
            return True
        
        # Act if rebalancing is needed
        if self.should_rebalance(market_data):
            return True
        
        # Act randomly with low probability to simulate market making activity
        return self.random.random() < 0.1  # 10% chance per step
    
    def step(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute one step of market making strategy"""
        actions = {
            'agent_id': self.agent_id,
            'agent_type': 'market_maker',
            'actions_taken': []
        }
        
        try:
            balance_a = self.get_token_balance(self.token_a_address)
            balance_b = self.get_token_balance(self.token_b_address)
            lp_balance = self.get_lp_balance()
            
            # If no LP position and we have tokens, add initial liquidity
            if lp_balance == 0 and (balance_a > 0 or balance_b > 0):
                amount_a, amount_b = self.calculate_optimal_liquidity_amounts(balance_a, balance_b)
                
                if amount_a > 0 and amount_b > 0:
                    tx_hash = self.add_liquidity(amount_a, amount_b)
                    if tx_hash:
                        actions['actions_taken'].append({
                            'action': 'add_initial_liquidity',
                            'amount_a': amount_a,
                            'amount_b': amount_b,
                            'tx_hash': tx_hash
                        })
            
            # Check for rebalancing opportunities
            elif self.should_rebalance(market_data):
                # Simple rebalancing: remove some liquidity and re-add in correct ratio
                rebalance_amount = int(lp_balance * 0.1)  # Rebalance 10% of position
                
                if rebalance_amount > 0:
                    # Remove liquidity
                    tx_hash = self.remove_liquidity(rebalance_amount)
                    if tx_hash:
                        actions['actions_taken'].append({
                            'action': 'rebalance_remove',
                            'lp_amount': rebalance_amount,
                            'tx_hash': tx_hash
                        })
                        
                        # Wait a bit and re-add optimally (simplified)
                        # In practice, this would be done in the next step
            
            # Calculate and update performance metrics
            self.calculate_impermanent_loss()
            
            actions['performance'] = {
                'lp_balance': lp_balance,
                'impermanent_loss': self.impermanent_loss,
                'fees_collected': self.fees_collected
            }
            
        except Exception as e:
            logger.error(f"Market maker {self.agent_id} step failed: {e}")
            actions['error'] = str(e)
        
        return actions