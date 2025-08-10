#!/usr/bin/env python3
"""
Test simulation functionality
"""

import pytest
import json
import subprocess
import time
from pathlib import Path
from simulator.run_simulation import SimulationRunner
from simulator.agent_base import AgentBase
from simulator.market_maker import MarketMaker
from simulator.trader import RandomTrader
from deploy import ContractDeployer

class TestSimulation:
    """Test simulation functionality"""
    
    @pytest.fixture(scope="class")
    def deployed_contracts(self):
        """Deploy contracts for testing"""
        # Start Ganache
        process = subprocess.Popen([
            'ganache-cli',
            '--host', '0.0.0.0',
            '--port', '8546',  # Different port to avoid conflicts
            '--deterministic',
            '--accounts', '10',
            '--defaultBalanceEther', '1000'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        time.sleep(3)  # Wait for Ganache to be ready
        
        try:
            # Deploy contracts
            deployer = ContractDeployer('http://localhost:8546')
            success = deployer.deploy_all()
            assert success
            
            yield 'deployed.json'
            
        finally:
            # Cleanup
            process.terminate()
            process.wait()
    
    @pytest.fixture
    def simulation_config(self):
        """Create test simulation configuration"""
        return {
            'max_steps': 5,
            'step_delay': 0.1,
            'random_seed': 42,
            'agents': [
                {
                    'type': 'market_maker',
                    'initial_balance': {'TEST': 10000, 'USDC': 10000}
                },
                {
                    'type': 'random_trader',
                    'trade_frequency': 0.5,
                    'initial_balance': {'TEST': 5000, 'USDC': 5000}
                }
            ]
        }
    
    def test_simulation_runner_init(self, deployed_contracts, simulation_config):
        """Test simulation runner initialization"""
        runner = SimulationRunner(
            simulation_config, 
            'http://localhost:8546',
            deployed_contracts
        )
        
        assert len(runner.agents) == 2
        assert runner.max_steps == 5
        assert runner.w3.is_connected()
    
    def test_agent_creation(self, deployed_contracts, simulation_config):
        """Test agent creation and initialization"""
        runner = SimulationRunner(
            simulation_config, 
            'http://localhost:8546',
            deployed_contracts
        )
        
        # Check agent types
        agent_types = [type(agent).__name__ for agent in runner.agents]
        assert 'MarketMaker' in agent_types
        assert 'RandomTrader' in agent_types
        
        # Check agent balances (before token distribution)
        for agent in runner.agents:
            eth_balance = agent.get_eth_balance()
            assert eth_balance > 0  # Should have ETH from Ganache
    
    def test_token_distribution(self, deployed_contracts, simulation_config):
        """Test initial token distribution to agents"""
        runner = SimulationRunner(
            simulation_config, 
            'http://localhost:8546',
            deployed_contracts
        )
        
        # Distribute tokens
        runner._distribute_initial_tokens()
        
        # Check that agents received tokens
        for agent in runner.agents:
            balances = agent.get_all_balances()
            
            # Should have received some TEST and USDC tokens
            assert balances.get('ERC20Token', 0) > 0 or balances.get('TEST', 0) > 0
            assert balances.get('USDC', 0) > 0
    
    def test_simulation_step(self, deployed_contracts, simulation_config):
        """Test single simulation step execution"""
        runner = SimulationRunner(
            simulation_config, 
            'http://localhost:8546',
            deployed_contracts
        )
        
        runner._distribute_initial_tokens()
        
        # Execute one step
        step_result = runner.run_step()
        
        # Verify step result structure
        assert 'step' in step_result
        assert 'timestamp' in step_result
        assert 'block_number' in step_result
        assert 'market_data' in step_result
        assert 'agent_actions' in step_result
        assert 'step_metrics' in step_result
        assert 'agent_performance' in step_result
        
        assert step_result['step'] == 0
        assert step_result['execution_time'] > 0
    
    def test_full_simulation(self, deployed_contracts, simulation_config):
        """Test complete simulation run"""
        runner = SimulationRunner(
            simulation_config, 
            'http://localhost:8546',
            deployed_contracts
        )
        
        # Run simulation
        results = runner.run_simulation()
        
        # Verify results structure
        assert 'simulation_config' in results
        assert 'execution_summary' in results
        assert 'overall_metrics' in results
        assert 'final_agent_performance' in results
        
        # Verify execution summary
        execution_summary = results['execution_summary']
        assert execution_summary['total_steps'] == 5
        assert execution_summary['total_time'] > 0
        assert execution_summary['total_transactions'] >= 0
        
        # Verify agent performance tracking
        agent_performance = results['final_agent_performance']
        assert len(agent_performance) == 2
        
        for agent_id, performance in agent_performance.items():
            assert 'pnl' in performance
            assert 'total_gas_used' in performance
            assert 'transaction_count' in performance
            assert 'current_balances' in performance
    
    def test_metrics_calculation(self, deployed_contracts, simulation_config):
        """Test metrics calculation"""
        runner = SimulationRunner(
            simulation_config, 
            'http://localhost:8546',
            deployed_contracts
        )
        
        runner._distribute_initial_tokens()
        
        # Run a few steps
        for _ in range(3):
            runner.run_step()
            runner.current_step += 1
        
        # Test metrics calculation
        overall_metrics = runner.metrics_calculator.calculate_overall_metrics(runner.step_results)
        
        assert 'simulation_steps' in overall_metrics
        assert 'price_statistics' in overall_metrics
        assert 'volume_statistics' in overall_metrics
        assert 'trading_activity' in overall_metrics
        
        assert overall_metrics['simulation_steps'] == 3