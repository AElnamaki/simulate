#!/usr/bin/env python3
"""
Trader Agent Implementations
Various trading strategies for AMM interaction
"""

from typing import Dict, Any, Optional, List
from .agent_base import AgentBase
import logging
import math

logger = logging.getLogger(__name__)

class Trader(AgentBase):
    """
    Base trader class with common trading functionality
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
                 slippage_tolerance: float = 0.05,
                 random_seed: Optional[int] = None):
        """
        Initialize trader agent
        
        Args:
            amm_address: AMM contract address for trading
            token_a_address: First token address
            token_b_address: Second token address
            slippage_tolerance: Maximum acceptable slippage (5% default)
        """
        super().__init__(agent_id, private_key, w3, contracts, initial_balance, random_seed)
        
        self.amm_address = amm_address
        self.token_a_address = token_a_address
        self.token_b_address = token_b_address
        self.slippage_tolerance = slippage_tolerance
        
        # AMM contract instance
        self.amm_contract = self.w3.eth.contract(
            address=amm_address,
            abi=contracts['AMM']['abi']
        )
        
        # Trading parameters
        self.min_trade_size = 1000  # Minimum trade size in wei
        self.max_trade_size_ratio = 0.1  # Max 10% of balance per trade
        
        # Performance tracking
        self.successful_trades = 0
        self.failed_trades = 0
        self.total_volume = 0.0
        self.total_slippage = 0.0
        
        logger.info(f"📈 Trader {agent_id} initialized for AMM {amm_address}")
    
    def get_pool_price(self) -> float:
        """Get current pool price (token A per token B)"""
        try:
            reserves = self.amm_contract.functions.getReserves().call()
            reserve_a, reserve_b = reserves[0], reserves[1]
            
            if reserve_b == 0:
                return 0.0
            
            return reserve_a / reserve_b
        except Exception as e:
            logger.error(f"Failed to get pool price: {e}")
            return 0.0
    
    def calculate_swap_output(self, amount_in: int, token_in: str) -> int:
        """Calculate expected output for a swap"""
        try:
            reserves = self.amm_contract.functions.getReserves().call()
            reserve_a, reserve_b = reserves[0], reserves[1]
            
            if token_in == self.token_a_address:
                return self.amm_contract.functions.getAmountOut(
                    amount_in, reserve_a, reserve_b
                ).call()
            else:
                return self.amm_contract.functions.getAmountOut(
                    amount_in, reserve_b, reserve_a
                ).call()
                
        except Exception as e:
            logger.error(f"Failed to calculate swap output: {e}")
            return 0
    
    def calculate_slippage(self, expected_output: int, actual_output: int) -> float:
        """Calculate slippage percentage"""
        if expected_output == 0:
            return 0.0
        
        return (expected_output - actual_output) / expected_output
    
    def execute_swap(self, 
                    amount_in: int, 
                    token_in: str, 
                    min_amount_out: int = None) -> Optional[str]:
        """
        Execute a token swap
        
        Args:
            amount_in: Amount of input tokens
            token_in: Address of input token
            min_amount_out: Minimum output amount (slippage protection)
            
        Returns:
            Transaction hash if successful
        """
        try:
            # Calculate expected output if min_amount_out not provided
            if min_amount_out is None:
                expected_output = self.calculate_swap_output(amount_in, token_in)
                min_amount_out = int(expected_output * (1 - self.slippage_tolerance))
            
            # Approve token spending
            self.approve_token_spending(token_in, self.amm_address, amount_in)
            
            # Execute swap
            transaction = self.amm_contract.functions.swapExactTokensForTokens(
                amount_in,
                min_amount_out,
                token_in,
                self.address
            ).build_transaction({})
            
            tx_hash = self.send_transaction(transaction)
            
            # Log the trade
            token_out = self.token_b_address if token_in == self.token_a_address else self.token_a_address
            self.log_trade('SWAP', {
                'amount_in': amount_in,
                'token_in': token_in,
                'token_out': token_out,
                'min_amount_out': min_amount_out,
                'tx_hash': tx_hash
            })
            
            self.successful_trades += 1
            self.total_volume += amount_in
            
            return tx_hash
            
        except Exception as e:
            logger.error(f"Swap failed for trader {self.agent_id}: {e}")
            self.failed_trades += 1
            return None
    
    def should_act(self, market_data: Dict[str, Any]) -> bool:
        """Base implementation - to be overridden by specific strategies"""
        return False
    
    def step(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Base implementation - to be overridden by specific strategies"""
        return {
            'agent_id': self.agent_id,
            'agent_type': 'trader',
            'actions_taken': []
        }


class RandomTrader(Trader):
    """
    Random trading strategy - executes random swaps
    Used for testing and generating trading volume
    """
    
    def __init__(self, *args, trade_frequency: float = 0.1, **kwargs):
        """
        Initialize random trader
        
        Args:
            trade_frequency: Probability of trading per step (0.1 = 10% chance)
        """
        super().__init__(*args, **kwargs)
        self.trade_frequency = trade_frequency
        
    def should_act(self, market_data: Dict[str, Any]) -> bool:
        """Act randomly based on trade frequency"""
        return self.random.random() < self.trade_frequency
    
    def step(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute random trading step"""
        actions = {
            'agent_id': self.agent_id,
            'agent_type': 'random_trader',
            'actions_taken': []
        }
        
        try:
            # Get current balances
            balance_a = self.get_token_balance(self.token_a_address)
            balance_b = self.get_token_balance(self.token_b_address)
            
            # Choose a random token to trade (if we have balance)
            tradeable_tokens = []
            if balance_a > self.min_trade_size:
                tradeable_tokens.append((self.token_a_address, balance_a))
            if balance_b > self.min_trade_size:
                tradeable_tokens.append((self.token_b_address, balance_b))
            
            if not tradeable_tokens:
                return actions
            
            # Select random token and amount
            token_in, balance = self.random.choice(tradeable_tokens)
            max_trade_amount = int(balance * self.max_trade_size_ratio)
            trade_amount = self.random.randint(self.min_trade_size, max_trade_amount)
            
            # Execute swap
            tx_hash = self.execute_swap(trade_amount, token_in)
            
            if tx_hash:
                actions['actions_taken'].append({
                    'action': 'random_swap',
                    'token_in': token_in,
                    'amount': trade_amount,
                    'tx_hash': tx_hash
                })
            
        except Exception as e:
            logger.error(f"Random trader {self.agent_id} step failed: {e}")
            actions['error'] = str(e)
        
        return actions


class MomentumTrader(Trader):
    """
    Momentum trading strategy - follows price trends
    Buys when price is rising, sells when price is falling
    """
    
    def __init__(self, *args, 
                 lookback_periods: int = 5,
                 momentum_threshold: float = 0.02,
                 trade_frequency: float = 0.2,
                 **kwargs):
        """
        Initialize momentum trader
        
        Args:
            lookback_periods: Number of periods to look back for momentum
            momentum_threshold: Minimum price change to trigger trade (2% default)
            trade_frequency: Base probability of trading per step
        """
        super().__init__(*args, **kwargs)
        self.lookback_periods = lookback_periods
        self.momentum_threshold = momentum_threshold
        self.trade_frequency = trade_frequency
        
        # Price history for momentum calculation
        self.price_history = []
        
    def calculate_momentum(self) -> float:
        """Calculate price momentum over lookback period"""
        if len(self.price_history) < self.lookback_periods:
            return 0.0
        
        recent_prices = self.price_history[-self.lookback_periods:]
        
        if recent_prices[0] == 0:
            return 0.0
        
        # Simple momentum: (current_price - old_price) / old_price
        momentum = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        return momentum
    
    def should_act(self, market_data: Dict[str, Any]) -> bool:
        """Act based on momentum and random frequency"""
        # Update price history
        current_price = self.get_pool_price()
        self.price_history.append(current_price)
        
        # Keep only required history
        if len(self.price_history) > self.lookback_periods * 2:
            self.price_history = self.price_history[-self.lookback_periods:]
        
        # Check if we have enough history and momentum exceeds threshold
        momentum = self.calculate_momentum()
        has_momentum = abs(momentum) > self.momentum_threshold
        
        # Combine momentum signal with random trading
        return has_momentum or (self.random.random() < self.trade_frequency)
    
    def step(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute momentum trading step"""
        actions = {
            'agent_id': self.agent_id,
            'agent_type': 'momentum_trader',
            'actions_taken': []
        }
        
        try:
            momentum = self.calculate_momentum()
            
            # Get current balances
            balance_a = self.get_token_balance(self.token_a_address)
            balance_b = self.get_token_balance(self.token_b_address)
            
            trade_executed = False
            
            # Positive momentum: buy token A (price of A increasing relative to B)
            if momentum > self.momentum_threshold and balance_b > self.min_trade_size:
                trade_amount = int(balance_b * self.max_trade_size_ratio)
                tx_hash = self.execute_swap(trade_amount, self.token_b_address)
                
                if tx_hash:
                    actions['actions_taken'].append({
                        'action': 'momentum_buy_a',
                        'momentum': momentum,
                        'amount': trade_amount,
                        'tx_hash': tx_hash
                    })
                    trade_executed = True
            
            # Negative momentum: sell token A (price of A decreasing relative to B)
            elif momentum < -self.momentum_threshold and balance_a > self.min_trade_size:
                trade_amount = int(balance_a * self.max_trade_size_ratio)
                tx_hash = self.execute_swap(trade_amount, self.token_a_address)
                
                if tx_hash:
                    actions['actions_taken'].append({
                        'action': 'momentum_sell_a',
                        'momentum': momentum,
                        'amount': trade_amount,
                        'tx_hash': tx_hash
                    })
                    trade_executed = True
            
            # Add momentum info to actions
            actions['momentum'] = momentum
            actions['price_history_length'] = len(self.price_history)
            
        except Exception as e:
            logger.error(f"Momentum trader {self.agent_id} step failed: {e}")
            actions['error'] = str(e)
        
        return actions


class ArbitrageTrader(Trader):
    """
    Arbitrage trading strategy - exploits price differences
    Simple implementation that looks for profitable arbitrage opportunities
    """
    
    def __init__(self, *args, 
                 min_profit_threshold: float = 0.01,
                 **kwargs):
        """
        Initialize arbitrage trader
        
        Args:
            min_profit_threshold: Minimum profit percentage to execute trade
        """
        super().__init__(*args, **kwargs)
        self.min_profit_threshold = min_profit_threshold
        
    def find_arbitrage_opportunity(self) -> Optional[Dict[str, Any]]:
        """
        Find arbitrage opportunities
        In a single AMM, this is limited, but can detect optimal trade sizes
        """
        try:
            current_price = self.get_pool_price()
            
            # Simple check: if we can make a profitable round trip
            # This is more theoretical as single AMM arbitrage is limited
            balance_a = self.get_token_balance(self.token_a_address)
            balance_b = self.get_token_balance(self.token_b_address)
            
            if balance_a > self.min_trade_size:
                # Simulate A->B->A round trip
                test_amount = int(balance_a * 0.1)  # Test with 10% of balance
                
                # A -> B
                b_received = self.calculate_swap_output(test_amount, self.token_a_address)
                
                if b_received > 0:
                    # B -> A
                    a_received = self.calculate_swap_output(b_received, self.token_b_address)
                    
                    profit = a_received - test_amount
                    profit_percentage = profit / test_amount if test_amount > 0 else 0
                    
                    if profit_percentage > self.min_profit_threshold:
                        return {
                            'direction': 'a_to_b_to_a',
                            'amount': test_amount,
                            'expected_profit': profit,
                            'profit_percentage': profit_percentage
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find arbitrage opportunity: {e}")
            return None
    
    def should_act(self, market_data: Dict[str, Any]) -> bool:
        """Act if arbitrage opportunity exists"""
        opportunity = self.find_arbitrage_opportunity()
        return opportunity is not None
    
    def step(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute arbitrage trading step"""
        actions = {
            'agent_id': self.agent_id,
            'agent_type': 'arbitrage_trader',
            'actions_taken': []
        }
        
        try:
            opportunity = self.find_arbitrage_opportunity()
            
            if opportunity:
                # Execute first leg of arbitrage
                if opportunity['direction'] == 'a_to_b_to_a':
                    tx_hash = self.execute_swap(opportunity['amount'], self.token_a_address)
                    
                    if tx_hash:
                        actions['actions_taken'].append({
                            'action': 'arbitrage_leg_1',
                            'expected_profit': opportunity['expected_profit'],
                            'profit_percentage': opportunity['profit_percentage'],
                            'tx_hash': tx_hash
                        })
                        
                        # Note: In practice, the second leg would be executed immediately
                        # or in the next step. Here we simplify by just executing first leg
            
        except Exception as e:
            logger.error(f"Arbitrage trader {self.agent_id} step failed: {e}")
            actions['error'] = str(e)
        
        return actions