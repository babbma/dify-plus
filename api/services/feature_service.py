import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
import re # extend: oauth2
from configs import dify_config
from extensions.ext_database import db
from flask import request # extend: oauth2
from extensions.ext_redis import redis_client # extend: oauth2
from services.billing_service import BillingService
from services.enterprise.enterprise_service import EnterpriseService
from models.system_extend import SystemIntegrationExtend, SystemIntegrationClassify # Extend DingTalk third-party login


class SubscriptionModel(BaseModel):
    plan: str = "sandbox"
    interval: str = ""


class BillingModel(BaseModel):
    enabled: bool = False
    subscription: SubscriptionModel = SubscriptionModel()


class EducationModel(BaseModel):
    enabled: bool = False
    activated: bool = False


class LimitationModel(BaseModel):
    size: int = 0
    limit: int = 0


class LicenseStatus(StrEnum):
    NONE = "none"
    INACTIVE = "inactive"
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    LOST = "lost"


class LicenseModel(BaseModel):
    status: LicenseStatus = LicenseStatus.NONE
    expired_at: str = ""


class FeatureModel(BaseModel):
    billing: BillingModel = BillingModel()
    education: EducationModel = EducationModel()
    members: LimitationModel = LimitationModel(size=0, limit=1)
    apps: LimitationModel = LimitationModel(size=0, limit=10)
    vector_space: LimitationModel = LimitationModel(size=0, limit=5)
    knowledge_rate_limit: int = 10
    annotation_quota_limit: LimitationModel = LimitationModel(size=0, limit=10)
    documents_upload_quota: LimitationModel = LimitationModel(size=0, limit=50)
    docs_processing: str = "standard"
    can_replace_logo: bool = False
    model_load_balancing_enabled: bool = False
    dataset_operator_enabled: bool = False

    # pydantic configs
    model_config = ConfigDict(protected_namespaces=())


class KnowledgeRateLimitModel(BaseModel):
    enabled: bool = False
    limit: int = 10
    subscription_plan: str = ""


class SystemFeatureModel(BaseModel):
    sso_enforced_for_signin: bool = False
    sso_enforced_for_signin_protocol: str = ""
    sso_enforced_for_web: bool = False
    sso_enforced_for_web_protocol: str = ""
    enable_web_sso_switch_component: bool = False
    enable_marketplace: bool = False
    max_plugin_package_size: int = dify_config.PLUGIN_MAX_PACKAGE_SIZE
    enable_email_code_login: bool = False
    enable_email_password_login: bool = True
    enable_social_oauth_login: bool = False
    is_allow_register: bool = False
    is_allow_create_workspace: bool = False
    is_email_setup: bool = False
    license: LicenseModel = LicenseModel()
    is_custom_auth2: str = ""  # extend: Customizing AUTH2
    is_custom_auth2_logout: str = ""  # extend: Customizing AUTH2
    ding_talk_client_id: str = "" # extend: DingTalk third-party login
    ding_talk_corp_id: str = "" # extend: DingTalk sidebar login
    ding_talk: bool = "" # extend: DingTalk sidebar login
    auto_join_admin_workspace: bool = False


class FeatureService:
    @classmethod
    def get_features(cls, tenant_id: str) -> FeatureModel:
        features = FeatureModel()

        cls._fulfill_params_from_env(features)

        if dify_config.BILLING_ENABLED and tenant_id:
            cls._fulfill_params_from_billing_api(features, tenant_id)

        return features

    @classmethod
    def get_knowledge_rate_limit(cls, tenant_id: str):
        knowledge_rate_limit = KnowledgeRateLimitModel()
        if dify_config.BILLING_ENABLED and tenant_id:
            knowledge_rate_limit.enabled = True
            limit_info = BillingService.get_knowledge_rate_limit(tenant_id)
            knowledge_rate_limit.limit = limit_info.get("limit", 10)
            knowledge_rate_limit.subscription_plan = limit_info.get("subscription_plan", "sandbox")
        return knowledge_rate_limit

    @classmethod
    def get_system_features(cls) -> SystemFeatureModel:
        system_features = SystemFeatureModel()
        # extend start: oauth2
        api_host = request.host_url
        # 通过nginx代理转发会导致 request.host_url 获取的是内网ip，这个时候使用.env的配置
        if bool(re.search(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}', request.host_url)):
            api_host = dify_config.CONSOLE_WEB_URL
        redis_client.set("api_host", api_host)
        # extend stop: oauth2

        cls._fulfill_system_params_from_env(system_features)

        if dify_config.ENTERPRISE_ENABLED:
            system_features.enable_web_sso_switch_component = True

            cls._fulfill_params_from_enterprise(system_features)

        if dify_config.MARKETPLACE_ENABLED:
            system_features.enable_marketplace = True

        return system_features

    @classmethod
    def _fulfill_system_params_from_env(cls, system_features: SystemFeatureModel):
        system_features.enable_email_code_login = dify_config.ENABLE_EMAIL_CODE_LOGIN
        system_features.auto_join_admin_workspace = dify_config.AUTO_JOIN_ADMIN_WORKSPACE
        system_features.enable_email_password_login = dify_config.ENABLE_EMAIL_PASSWORD_LOGIN
        system_features.enable_social_oauth_login = dify_config.ENABLE_SOCIAL_OAUTH_LOGIN
        system_features.is_allow_register = dify_config.ALLOW_REGISTER
        system_features.is_allow_create_workspace = dify_config.ALLOW_CREATE_WORKSPACE
        system_features.is_email_setup = dify_config.MAIL_TYPE is not None and dify_config.MAIL_TYPE != ""
        # extend start: DingTalk third-party login
        for i in db.session.query(SystemIntegrationExtend).filter(SystemIntegrationExtend.status == True).all():
            if i.classify == SystemIntegrationClassify.SYSTEM_INTEGRATION_DINGTALK:
                system_features.ding_talk_client_id = i.app_key
                system_features.ding_talk_corp_id = i.corp_id
                system_features.ding_talk = i.status
                # Extend: OAuth2 Start
            elif i.classify == SystemIntegrationClassify.SYSTEM_INTEGRATION_OAUTH_TWO:
                config = json.loads(i.config)
                system_features.is_custom_auth2 = i.status
                if "logout_url" in config.keys():
                    system_features.is_custom_auth2_logout = "{}{}".format(
                        config['server_url'], config['logout_url'])
                # Extend: OAuth2 Stop
        # extend stop: DingTalk third-party login

    @classmethod
    def _fulfill_params_from_env(cls, features: FeatureModel):
        features.can_replace_logo = dify_config.CAN_REPLACE_LOGO
        features.model_load_balancing_enabled = dify_config.MODEL_LB_ENABLED
        features.dataset_operator_enabled = dify_config.DATASET_OPERATOR_ENABLED
        features.education.enabled = dify_config.EDUCATION_ENABLED

    @classmethod
    def _fulfill_params_from_billing_api(cls, features: FeatureModel, tenant_id: str):
        billing_info = BillingService.get_info(tenant_id)

        features.billing.enabled = billing_info["enabled"]
        features.billing.subscription.plan = billing_info["subscription"]["plan"]
        features.billing.subscription.interval = billing_info["subscription"]["interval"]
        features.education.activated = billing_info["subscription"].get("education", False)

        if "members" in billing_info:
            features.members.size = billing_info["members"]["size"]
            features.members.limit = billing_info["members"]["limit"]

        if "apps" in billing_info:
            features.apps.size = billing_info["apps"]["size"]
            features.apps.limit = billing_info["apps"]["limit"]

        if "vector_space" in billing_info:
            features.vector_space.size = billing_info["vector_space"]["size"]
            features.vector_space.limit = billing_info["vector_space"]["limit"]

        if "documents_upload_quota" in billing_info:
            features.documents_upload_quota.size = billing_info["documents_upload_quota"]["size"]
            features.documents_upload_quota.limit = billing_info["documents_upload_quota"]["limit"]

        if "annotation_quota_limit" in billing_info:
            features.annotation_quota_limit.size = billing_info["annotation_quota_limit"]["size"]
            features.annotation_quota_limit.limit = billing_info["annotation_quota_limit"]["limit"]

        if "docs_processing" in billing_info:
            features.docs_processing = billing_info["docs_processing"]

        if "can_replace_logo" in billing_info:
            features.can_replace_logo = billing_info["can_replace_logo"]

        if "model_load_balancing_enabled" in billing_info:
            features.model_load_balancing_enabled = billing_info["model_load_balancing_enabled"]

        if "knowledge_rate_limit" in billing_info:
            features.knowledge_rate_limit = billing_info["knowledge_rate_limit"]["limit"]

    @classmethod
    def _fulfill_params_from_enterprise(cls, features):
        enterprise_info = EnterpriseService.get_info()

        if "sso_enforced_for_signin" in enterprise_info:
            features.sso_enforced_for_signin = enterprise_info["sso_enforced_for_signin"]

        if "sso_enforced_for_signin_protocol" in enterprise_info:
            features.sso_enforced_for_signin_protocol = enterprise_info["sso_enforced_for_signin_protocol"]

        if "sso_enforced_for_web" in enterprise_info:
            features.sso_enforced_for_web = enterprise_info["sso_enforced_for_web"]

        if "sso_enforced_for_web_protocol" in enterprise_info:
            features.sso_enforced_for_web_protocol = enterprise_info["sso_enforced_for_web_protocol"]

        if "enable_email_code_login" in enterprise_info:
            features.enable_email_code_login = enterprise_info["enable_email_code_login"]

        if "enable_email_password_login" in enterprise_info:
            features.enable_email_password_login = enterprise_info["enable_email_password_login"]

        if "is_allow_register" in enterprise_info:
            features.is_allow_register = enterprise_info["is_allow_register"]

        if "is_allow_create_workspace" in enterprise_info:
            features.is_allow_create_workspace = enterprise_info["is_allow_create_workspace"]

        if "license" in enterprise_info:
            license_info = enterprise_info["license"]

            if "status" in license_info:
                features.license.status = LicenseStatus(license_info.get("status", LicenseStatus.INACTIVE))

            if "expired_at" in license_info:
                features.license.expired_at = license_info["expired_at"]
