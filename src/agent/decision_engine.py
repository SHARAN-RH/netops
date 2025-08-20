"""Decision engine for upgrade approvals"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from ..common import logger, load_yaml_file
import os
import json

@dataclass
class UpgradeDecision:
    approve: bool
    reason: str
    target_ver: Optional[str] = None
    confidence: float = 0.0
    metrics_summary: Dict[str, Any] = None
    additional_checks: List[str] = None

class DecisionEngine:
    """Network upgrade decision engine"""
    
    def __init__(self, policy_path: str = None):
        if policy_path is None:
            policy_path = os.path.join(os.path.dirname(__file__), 'policy.yaml')
        
        self.policy = load_yaml_file(policy_path)
        logger.info(f"Loaded policy from {policy_path}")
    
    def evaluate_upgrade_rules(self, 
                             router_info: Dict[str, Any], 
                             policy: Dict[str, Any], 
                             health_summary: Dict[str, Any]) -> UpgradeDecision:
        """Apply rule-based decision logic"""
        
        metrics = health_summary.get('metrics', {})
        
        # Use policy-specific thresholds or fallback to defaults
        max_cpu = policy.get('max_cpu_percent', self.policy['defaults']['max_cpu_percent'])
        min_mem = policy.get('min_free_mem_percent', self.policy['defaults']['min_free_mem_percent'])
        max_errors = self.policy['defaults']['max_critical_errors']
        
        cpu = metrics.get('cpu_avg', 100)
        mem = metrics.get('mem_free_min', 0)
        errors = metrics.get('critical_errors', 0)
        
        # Check maintenance window (simplified - always pass for now)
        within_window = True
        
        # Evaluate conditions
        cpu_ok = cpu <= max_cpu if cpu is not None else False
        mem_ok = mem >= min_mem if mem is not None else False
        errors_ok = errors <= max_errors
        window_ok = within_window or not self.policy['defaults']['require_maintenance_window']
        
        approve = cpu_ok and mem_ok and errors_ok and window_ok
        
        conditions = [
            f"CPU {cpu}% {'✓' if cpu_ok else '✗'} (limit: {max_cpu}%)",
            f"Memory {mem}% {'✓' if mem_ok else '✗'} (min: {min_mem}%)",
            f"Errors {errors} {'✓' if errors_ok else '✗'} (max: {max_errors})",
            f"Window {'✓' if window_ok else '✗'}",
        ]
        
        return UpgradeDecision(
            approve=approve,
            reason=f"All conditions met: {', '.join(conditions)}" if approve else f"Conditions failed: {', '.join(conditions)}",
            target_ver=router_info.get('target_ver') or router_info.get('current_ver'),
            confidence=0.8,
            metrics_summary={'cpu': cpu, 'mem': mem, 'errors': errors, 'conditions': conditions}
        )
    
    def calculate_risk_score(self, router_info: Dict[str, Any], health_summary: Dict[str, Any]) -> float:
        """Calculate risk score (0-100, higher = more risky)"""
        
        metrics = health_summary.get('metrics', {})
        risk_score = 0
        
        cpu = metrics.get('cpu_avg', 0)
        mem = metrics.get('mem_free_min', 100)
        errors = metrics.get('critical_errors', 0)
        
        # CPU risk
        if cpu > 85:
            risk_score += 40
        elif cpu > 75:
            risk_score += 25
        elif cpu > 60:
            risk_score += 10
        
        # Memory risk
        if mem < 20:
            risk_score += 35
        elif mem < 30:
            risk_score += 20
        elif mem < 40:
            risk_score += 10
        
        # Error risk
        if errors > 5:
            risk_score += 25
        elif errors > 2:
            risk_score += 15
        elif errors > 0:
            risk_score += 10
        
        return min(risk_score, 100)
    
    def get_vendor_requirements(self, router_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get vendor-specific upgrade requirements"""
        
        vendor = router_info.get('vendor', '').lower()
        model = router_info.get('model', '').lower()
        
        vendor_policies = self.policy.get('vendor_policies', {})
        
        if vendor in vendor_policies:
            vendor_config = vendor_policies[vendor]
            
            # Find matching model configuration
            for model_key, model_config in vendor_config.items():
                if model_key.lower() in model.lower() or model.lower() in model_key.lower():
                    return model_config
        
        return {}
    
    def check_maintenance_window(self, router_info: Dict[str, Any]) -> bool:
        """Check if current time is within maintenance window"""
        
        # Simplified implementation - always return True for now
        # In real implementation, check router_info['maintenance_window']
        # against current time and policy constraints
        
        constraints = self.policy.get('constraints', {})
        upgrade_window = constraints.get('upgrade_window', {})
        
        if not upgrade_window:
            return True
        
        current_time = datetime.now()
        current_hour = current_time.hour
        current_day = current_time.strftime('%A').lower()
        
        start_hour = upgrade_window.get('start_hour', 0)
        end_hour = upgrade_window.get('end_hour', 24)
        allowed_days = [day.lower() for day in upgrade_window.get('allowed_days', [])]
        
        hour_ok = start_hour <= current_hour <= end_hour
        day_ok = not allowed_days or current_day in allowed_days
        
        return hour_ok and day_ok
    
    def generate_pre_checks(self, router_info: Dict[str, Any]) -> List[str]:
        """Generate list of required pre-upgrade checks"""
        
        base_checks = self.policy.get('constraints', {}).get('pre_checks', [])
        vendor_requirements = self.get_vendor_requirements(router_info)
        
        checks = base_checks.copy()
        
        # Add vendor-specific checks
        if vendor_requirements.get('compatibility_check'):
            checks.append('firmware_compatibility_check')
        
        if vendor_requirements.get('minimum_memory_mb'):
            checks.append('memory_requirements_check')
        
        if vendor_requirements.get('bootflash_requirement_mb'):
            checks.append('bootflash_space_check')
        
        return list(set(checks))  # Remove duplicates