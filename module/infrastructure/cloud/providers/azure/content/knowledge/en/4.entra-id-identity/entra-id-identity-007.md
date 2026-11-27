# Workload identity federation for applications and pipelines

When deploying applications on Microsoft Azure, applications and CI/CD pipelines often need to call Azure Resource Manager, Key Vault, Storage, or data services. To perform these tasks, they need an identity and access permissions. An older approach is creating a client secret for a service principal, storing the secret in the CI/CD system, and using it to sign in. This creates overhead around storing, distributing, rotating, and revoking secrets.

**Workload identity federation (WIF)** lets Microsoft Entra ID trust an external token issuer (identity provider, IdP), accept a valid OIDC token from a workload, and exchange that token for a Microsoft Entra ID access token. As a result, applications or pipelines can access Azure resources without storing long-lived client secrets for an Azure identity.

In the CLOUD_PROVIDERS_AZURE module, this lesson connects Microsoft Entra ID with automated deployments, subscription/resource group administration, Azure RBAC authorization, and secure access to storage, compute, or data services on Azure.

## 1. Objectives and prerequisites

After this lesson, you will be able to:

1. Explain what a workload identity is and how federation based on OpenID Connect (OIDC) works.
2. Distinguish application registration, service principal, managed identity, and federated identity credential.
3. Understand the roles of issuer, subject, and audience, and how Microsoft Entra ID matches these values when receiving a token.
4. Configure a secretless sign-in flow for GitHub Actions and understand the equivalent approach in Azure DevOps and AKS.
5. Grant Azure permissions following least privilege, troubleshoot common errors, and identify security risks.

You should be familiar with basic concepts of Microsoft Entra tenants, Azure subscriptions, resource groups, Azure RBAC, Azure CLI, and CI/CD. The CLI examples assume the operating admin account is permitted to create identities or role assignments. Paid resources are not required to understand the theory.

## 2. Why does a workload need its own identity?

A workload is an application or automated process that needs to call other services: a backend API, a scheduled job, a container on Kubernetes, a pipeline job, or an infrastructure deployment script.

For example, a pipeline deploying the orders application must:

- Read deployment configuration and connect to Azure.
- Create or update an App Service, Storage Account, or resources in a resource group.
- Occasionally retrieve values from Key Vault or push artifacts to an Azure service.
- Record deployment status and end the session.

If the pipeline uses a personal username and password, the account could be locked, change passwords, or leave the company. If it uses a service principal's long-lived client secret, the team must manage that secret across each CI/CD system and handle the risk of secret exposure.

WIF solves the authentication piece by relying on a trust relationship between Microsoft Entra ID and the workload's IdP. The OIDC token issued by the IdP is short-lived and exchanged with Entra ID; the pipeline does not need to receive an Azure password or client secret beforehand. However, WIF **does not grant access permissions on its own**: the federated identity still must be assigned the right Azure RBAC role or permissions on the target service.

## 3. Core concepts

| Concept | Meaning in this lesson |
|---|---|
| Workload identity | Identity of an application, pod, job, or automated process, rather than an interactive human user |
| OpenID Connect (OIDC) | Identity protocol built on OAuth 2.0; an IdP can issue tokens containing claims describing the subject and context |
| Identity provider (IdP) | Party issuing the OIDC token, such as GitHub Actions or a Kubernetes cluster's OIDC issuer |
| Microsoft Entra application | Application registration object in an Entra tenant, having an application (client) ID |
| Service principal | Application identity in a tenant, typically the object assigned Azure RBAC roles |
| User-assigned managed identity | Azure-managed identity with a lifecycle independent of the resources using it; some scenarios support configuring federated credentials on this identity |
| Federated identity credential (FIC) | Trust configuration on an Entra application or user-assigned managed identity specifying accepted issuer, subject, and audience |
| Microsoft Entra access token | Token issued after a successful exchange, used to call Azure Resource Manager or a target API |
| Azure RBAC | Mechanism controlling permissions on Azure resources, independent of federated authentication |

An application registration and a service principal are related but are not the same object. The application (client) ID identifies the app for sign-in; the service principal is the app's representation in the tenant and is typically assigned roles. Do not confuse the client ID with the service principal's object ID when granting permissions.

**Managed identity** is the natural choice for workloads running on supported Azure services. A system-assigned managed identity ties its lifecycle to the resource; a user-assigned managed identity can be reused by design. In environments like AKS Workload Identity, a Kubernetes service account can federate with a user-assigned managed identity. If an application runs on an Azure service that already supports managed identity access directly, you typically do not need to configure external federation manually.

## 4. How workload identity federation works

A typical flow from GitHub Actions or Kubernetes to Azure consists of these steps:

1. **Register trust:** an administrator creates an app registration or user-assigned managed identity, then adds a federated identity credential describing the IdP and the workload allowed to sign in.
2. **Workload starts:** a pipeline runs a job or a pod starts in an environment capable of issuing OIDC tokens.
3. **Receive token from IdP:** the job or pod receives a signed token with claims such as issuer, subject, and audience.
4. **Exchange token:** the workload sends the IdP-issued token to Microsoft Entra ID's token endpoint and specifies the client ID of the target identity.
5. **Entra validates:** Entra verifies the token and matches it against the federated identity credential. When matched, Entra issues an access token for the target resource/API.
6. **Call Azure service:** the workload uses the access token to access the service. Azure RBAC and service data permissions continue to govern which operations are allowed.

Diagram:

~~~mermaid
sequenceDiagram
    participant W as Application / Pipeline
    participant I as OIDC Identity Provider
    participant E as Microsoft Entra ID
    participant A as Azure API or resource
    W->>I: Request OIDC token for workload context
    I-->>W: Signed JWT with iss, sub, aud
    W->>E: Exchange OIDC assertion for access token
    E->>E: Validate token and FIC
    E-->>W: Entra ID access token
    W->>A: Call API with access token
    A->>A: Check granted permissions
    A-->>W: Result or authorization error
~~~

### Issuer, subject, and audience

Three key fields in an FIC configuration are:

- **Issuer (iss):** URL identifying the OIDC token issuer. For example, for GitHub Actions it is https://token.actions.githubusercontent.com.
- **Subject (sub):** identifier of the workload context permitted by Entra. For GitHub Actions, the subject can include organization, repository, and branch or GitHub Environment; for Kubernetes, the subject can specify a service account in a namespace.
- **Audience (aud):** intended token recipient declared by the IdP. For common Azure token exchange configurations, the value used is api://AzureADTokenExchange.

Example for a workflow running from the main branch:

~~~json
{
  "name": "github-orders-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:EXAMPLE_ORG/orders-api:ref:refs/heads/main",
  "audiences": [
    "api://AzureADTokenExchange"
  ]
}
~~~

In standard FIC mode, issuer, subject, and audience values must match the actual token according to Entra's matching rules. Minor differences such as casing, branch name, trailing slash in a URL, or using a GitHub Environment can cause sign-in to fail. Do not guess the subject; obtain it from official IdP documentation and token/property values. Flexible subject-matching features, if supported in a specific environment, must have their trust scope evaluated separately.

**Key distinction:** the initial OIDC token proves the workload's identity to Entra. It is not automatically an access token for calling Azure Resource Manager. The Entra access token is issued after a successful exchange and carries its own audience and permissions.

## 5. Choosing the identity type for each scenario

| Scenario | Typical Azure identity | OIDC token issuer |
|---|---|---|
| GitHub Actions deploying infrastructure | Entra app + service principal + FIC | GitHub Actions OIDC provider |
| Azure DevOps pipeline | Identity of an Azure Resource Manager service connection supporting WIF | Azure DevOps OIDC issuer per service connection |
| Pod in Azure Kubernetes Service | User-assigned managed identity + FIC linked to service account | AKS OIDC issuer |
| App running on App Service/VM supporting managed identity | System-assigned or user-assigned managed identity directly | Azure managed identity endpoint; typically no FIC needed |
| Workload in an external CI system or non-Azure Kubernetes | Entra app or user-assigned managed identity, when the scenario and IdP are supported | Trusted OIDC issuer of the external system |

The difference is not simply "Azure vs. outside Azure"; what matters is whether the IdP issues suitable tokens, whether the target identity supports FIC for that scenario, and whether the SDK or tooling can perform token exchange.

## 6. Hands-on: GitHub Actions using OIDC to sign in to Azure

Suppose repository EXAMPLE_ORG/orders-api deploys to resource group rg-orders-dev in a development subscription. We want only workflows running from the main branch to be able to use the deployment identity.

### 6.1. Prerequisites and information needed

You need:

- Permission to create an app registration or service principal in the tenant (or an existing identity provided by an administrator).
- Permission to create role assignments at the intended deployment scope.
- Permission to manage the GitHub repository and configure workflows.
- Azure CLI signed in to the right tenant and subscription.
- Target resource group already existing, e.g., rg-orders-dev.

Check Azure CLI:

~~~bash
az account show --output table
~~~

To avoid targeting the wrong environment, explicitly select the subscription before configuring:

~~~bash
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

### 6.2. Create the Entra application and service principal

The example below uses Bash in a terminal with Azure CLI installed. Replace all values in braces or `< >` with real values:

~~~bash
APP_ID="$(az ad app create --display-name 'app-orders-deploy-dev' --query appId --output tsv)"
az ad sp create --id "$APP_ID" --output none
SP_OBJECT_ID="$(az ad sp show --id "$APP_ID" --query id --output tsv)"
echo "Application client ID: $APP_ID"
echo "Service principal object ID: $SP_OBJECT_ID"
~~~

APP_ID is the application (client) ID that the workflow will use to sign in. SP_OBJECT_ID is the object ID of the service principal that will be assigned Azure RBAC roles. Do not create a client secret or certificate if deploying solely via this federation method.

If the organization already has an app registration for deployment, you can reuse it per organizational policy rather than creating a new identity. Separate identities between development and production when permission scopes or approval processes differ.

### 6.3. Declare the federated identity credential

Create a JSON configuration file on your admin workstation with the following content:

~~~json
{
  "name": "github-orders-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:EXAMPLE_ORG/orders-api:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "OIDC trust for the main branch deployment workflow"
}
~~~

Assuming it is saved as github-main-fic.json, register the FIC on the app:

~~~bash
az ad app federated-credential create --id "$APP_ID" --parameters @github-main-fic.json
~~~

Read back the configuration:

~~~bash
az ad app federated-credential list --id "$APP_ID" --output json
~~~

In GitHub Actions, the token's subject varies by context type. For example, when a workflow uses a GitHub Environment named production, the subject typically has the form:

~~~text
repo:EXAMPLE_ORG/orders-api:environment:production
~~~

This subject differs from the main branch subject. If a workflow uses an environment, the FIC configuration must match the environment context, and you should enable environment protection rules such as required reviewers, branch restrictions, and appropriate deployment conditions. Only add FICs for genuinely authorized branches, environments, and repositories.

### 6.4. Grant permissions at the smallest scope

For a test pipeline that only reads resources in the target resource group, the Reader role is sufficient to verify sign-in. For example:

~~~bash
SCOPE="/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-orders-dev"
az role assignment create --assignee-object-id "$SP_OBJECT_ID" --assignee-principal-type ServicePrincipal --role Reader --scope "$SCOPE"
~~~

If the pipeline genuinely needs to create or update resources, the admin team should then consider an appropriate role such as Contributor on the specific resource group or a custom role with only needed actions. Avoid using Owner or Contributor across the entire subscription just to test a workflow.

Azure RBAC on the management plane does not equate to permission to read secrets or actual data. For example, if a workload needs to read secrets in Key Vault using the Azure RBAC permission model, you must grant an appropriate data role such as Key Vault Secrets User at the needed scope. For Storage Blobs, an appropriate data role such as Storage Blob Data Reader or Storage Blob Data Contributor is needed depending on the operations.

### 6.5. Configure the GitHub Actions workflow

In the GitHub repository, declare **Actions variables** with the corresponding values:

| Variable | Value |
|---|---|
| AZURE_CLIENT_ID | Application (client) ID of the Entra app |
| AZURE_TENANT_ID | Microsoft Entra tenant ID |
| AZURE_SUBSCRIPTION_ID | Azure subscription ID |

These IDs are configuration identifiers, not client secrets. Even so, do not expose them without control; enforce repository and workflow management permissions according to organizational policy.

Example workflow at .github/workflows/azure-readonly.yml:

~~~yaml
name: Azure OIDC smoke test

on:
  push:
    branches:
      - main

permissions:
  contents: read
  id-token: write

jobs:
  verify-azure:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Sign in with workload identity federation
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Verify identity and resource group access
        run: |
          az account show --query "{subscription:id,tenant:tenantId}" --output table
          az group show --name rg-orders-dev --query "{name:name,location:location}" --output table
~~~

The id-token: write permission allows the job to request an OIDC token from GitHub under GitHub Actions' permission model; it does not grant write access to Azure resources. The azure/login step performs the token exchange per the declared FIC. The final step only reads information for the resource group granted Reader. If replaced with az group list to list every resource group in the subscription, Reader on a single resource group may be insufficient. Never expand permissions to the entire subscription merely to make a smoke test step more convenient.

Repository security controls remain critical. If an attacker can modify a workflow running on a branch or environment trusted by the FIC, they can request an OIDC token in that context and exercise the Azure identity's permissions. Therefore, branch protection, repository write controls, mandatory reviews, and restricting which workflows may deploy remain mandatory.

## 7. Azure DevOps: service connection using workload identity federation

Azure DevOps provides a way to configure an Azure Resource Manager service connection using workload identity federation authentication. The concept is similar to GitHub Actions, except **the issuer and subject are generated by Azure DevOps' service connection mechanism**. Never copy GitHub's issuer/subject into Azure DevOps.

High-level process:

1. In the Azure DevOps project, open Project settings → Service connections.
2. Create or edit an Azure Resource Manager service connection and select the Workload identity federation authentication method if available.
3. Choose automatic identity creation or enter registration details manually, depending on permissions and the Azure DevOps UI.
4. For manual configuration, copy the **issuer and subject provided by the service connection** and register the corresponding FIC in the Entra app or supported identity; never guess the claim strings.
5. Grant an Azure RBAC role to the identity at the target resource group or resource scope.
6. Verify the service connection and restrict which pipelines are permitted to use it.

Example YAML pipeline performing a read-only check:

~~~yaml
trigger:
  - main

pool:
  vmImage: ubuntu-latest

steps:
  - task: AzureCLI@2
    displayName: Verify Azure workload federation
    inputs:
      azureSubscription: 'sc-orders-dev-wif'
      scriptType: bash
      scriptLocation: inlineScript
      inlineScript: |
        az account show --query "{subscription:id,tenant:tenantId}" --output table
        az group show --name rg-orders-dev --query "{name:name,location:location}" --output table
~~~

The name sc-orders-dev-wif is an illustrative service connection name; the pipeline must reference the exact connection created and authorized for use. AzureCLI@2 uses the identity provided by the service connection. The pipeline does not need to store a service principal client secret.

**Operational note:** some organizations have older service connections using secrets or certificates. Migrating to WIF requires checking the connection type, Azure DevOps permissions, extension/task support, and approval workflows. Only after a successful migration and verification that all pipelines use the new configuration should you revoke the old credentials per safe procedure.

## 8. Applications on AKS: Kubernetes service account federated with a managed identity

With Azure Kubernetes Service (AKS), workload identity federation lets a pod use a Kubernetes service account token to obtain an access token from Entra ID. This avoids placing an Azure application's client secret into a Kubernetes Secret.

Example of the orders-api application reading a secret from Azure Key Vault:

~~~text
Pod orders-api
  ↓ attached Kubernetes ServiceAccount orders-api
AKS OIDC issuer
  ↓ issues token with subject system:serviceaccount:orders:orders-api
Microsoft Entra ID
  ↓ matches FIC of user-assigned managed identity
Access token
  ↓
Azure Key Vault (checks data permissions)
~~~

### 8.1. Prerequisites

- The AKS cluster has OIDC issuer and workload identity features enabled.
- The orders namespace and orders-api Kubernetes service account will be created.
- A user-assigned managed identity exists for the application.
- Permissions to operate on the identity and assign Azure RBAC at the target Key Vault scope.
- The application uses the Azure Identity SDK or a token acquisition mechanism compatible with workload identity.

Read the configured AKS cluster's issuer URL:

~~~bash
AKS_ISSUER="$(az aks show --resource-group '<AKS_RESOURCE_GROUP>' --name '<AKS_CLUSTER_NAME>' --query oidcIssuerProfile.issuerUrl --output tsv)"
echo "$AKS_ISSUER"
~~~

If the OIDC issuer is not yet enabled, configure the cluster following AKS guidance before continuing. When entering the issuer URL into the FIC, use the exact string returned by AKS, including any trailing slash if present.

### 8.2. Create the user-assigned managed identity and FIC

Assume the identity is placed in resource group rg-orders-identity:

~~~bash
az identity create --name id-orders-api --resource-group rg-orders-identity
AZURE_CLIENT_ID="$(az identity show --name id-orders-api --resource-group rg-orders-identity --query clientId --output tsv)"
AZURE_PRINCIPAL_ID="$(az identity show --name id-orders-api --resource-group rg-orders-identity --query principalId --output tsv)"
~~~

Create a federated credential trusting the exact service account:

~~~bash
az identity federated-credential create \
  --name fic-aks-orders-api \
  --identity-name id-orders-api \
  --resource-group rg-orders-identity \
  --issuer "$AKS_ISSUER" \
  --subject "system:serviceaccount:orders:orders-api" \
  --audiences "api://AzureADTokenExchange"
~~~

In the Kubernetes subject:

- orders at the front is the namespace.
- orders-api afterward is the Kubernetes service account name.
- Renaming the namespace or service account changes the token's subject and can break the FIC match.

Assign appropriate permissions for the managed identity on the target Key Vault. Example when Key Vault uses the Azure RBAC permission model:

~~~bash
KEY_VAULT_ID="$(az keyvault show --name '<KEY_VAULT_NAME>' --query id --output tsv)"
az role assignment create --assignee-object-id "$AZURE_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope "$KEY_VAULT_ID"
~~~

This role is for reading secrets under that permission model; it does not replace Key Vault networking, firewall, private endpoint, or permission model settings. If Key Vault uses the access policy model, permission assignment differs and must follow the actual configuration.

### 8.3. Declare the service account and pod

Example Kubernetes manifest; replace placeholder client ID and image before deploying:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "<USER_ASSIGNED_IDENTITY_CLIENT_ID>"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: "<REGISTRY>/orders-api:1.0"
~~~

The AKS workload identity webhook uses the pod label and service account annotation to configure the required SDK environment details, including the projected token path in the container and the client ID. The application uses a compatible Azure Identity SDK to acquire tokens without embedding any client secret in source code.

Java example using Azure Identity and Azure Key Vault Secrets SDK (declare appropriate dependencies in the application):

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public class VaultExample {
    public static void main(String[] args) {
        SecretClient client = new SecretClientBuilder()
            .vaultUrl(System.getenv("KEY_VAULT_URL"))
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        // Access illustration only: do not write secret values to logs.
        boolean found = client.getSecret("orders-api-config") != null;
        System.out.println("Secret available: " + found);
    }
}
~~~

You must grant permissions to the managed identity's service principal on the target resource, verify network access, and ensure the application uses an Azure Identity SDK version supporting workload identity. DefaultAzureCredential automatically selects an available credential type based on the environment in the SDK's defined order; with AKS workload identity, the pod must be properly configured so the SDK can use the federated token.

## 9. Defense-in-depth security and authorization

WIF eliminates distributing long-lived client secrets in many scenarios, yet it does not render an Azure identity harmless. A pipeline can still modify production if granted broad roles, regardless of whether authentication uses a secret or OIDC.

This can be analyzed across three control layers:

| Layer | Question to answer | Controls |
|---|---|---|
| Identity provider | Which workloads are issued OIDC tokens? | GitHub branch protection, environment approvals, Azure DevOps pipeline permissions, Kubernetes RBAC |
| Microsoft Entra ID | Which tokens are permitted to exchange for the Azure identity? | FIC restricting issuer/subject/audience; separate identities per environment |
| Azure and target services | What is the Azure identity allowed to do? | Minimal Azure RBAC, data-plane roles, specific scopes, network policies |

Design principles:

1. **Separate dev/prod identities:** dedicated apps or managed identities limit the blast radius if a pipeline is compromised.
2. **Restrict FICs:** trust only approved repositories, branches, environments, or service accounts. Never let unrelated workflows share a highly privileged identity.
3. **Protect the token source:** enforce workflow edit permissions, code reviews, protected branches, and GitHub Environment rules; govern service connections in Azure DevOps.
4. **Grant at the right scope:** prefer specific resources or resource groups, and apply custom roles when needed; never grant Owner at the subscription without clear justification.
5. **Distinguish management plane and data plane:** ARM roles do not automatically grant access to Key Vault, Blob, or database data.
6. **Never log tokens:** both OIDC assertions and access tokens are bearer credentials during their validity period; avoid printing them to stdout, artifacts, or public error messages.
7. **Maintain auditing:** monitor service principal/managed identity sign-in logs where available, Azure Activity Log, and CI/CD deployment logs.
8. **Revoke promptly:** when a repository, branch, service account, or partner is no longer trusted, delete the FIC, reduce or revoke role assignments, and disable related pipelines.

FIC limits and support for certain federation configurations can vary by identity type or service. Design the number of identities and FICs to stay manageable while checking current service quotas.

## 10. Verification and troubleshooting

When a workflow fails to sign in, inspect each stage in sequence: did the IdP issue a token, did Entra accept the token, and did Azure authorize the operation?

| Symptom | Common cause | What to check |
|---|---|---|
| Cannot acquire OIDC token in GitHub Actions | Missing id-token: write permission, mismatched workflow/trigger, repository policy | Check permissions, event, job, and repository settings |
| Entra reports no matching federated credential found | Issuer, subject, or audience mismatch | Compare exact token claims against FIC; check branch and environment |
| Entra reports app does not exist or wrong tenant | Wrong client ID, tenant ID, or registration object | Check app registration, service principal, and selected tenant |
| Sign-in succeeds, but Azure returns 403/AuthorizationFailed | Missing required Azure RBAC role or wrong scope | Check object ID, role assignment, scope, and permission propagation delay |
| Key Vault/Storage read fails despite sign-in | Missing data-plane role, access policy, network config, or endpoint | Check permission model and connectivity to target service |
| AKS pod does not receive credential | Missing pod label, service account annotation, cluster feature not enabled | Check manifest, OIDC issuer, FIC subject, and Azure Identity SDK |
| Pipeline previously used a secret but fails after migration | Service connection or task not using WIF properly | Check connection type, task compatibility, issuer/subject, and pipeline permissions |

Microsoft Entra error codes in the AADSTS70021 or AADSTS700213 family commonly indicate that no FIC matched the assertion. Do not guess and change the audience blindly; inspect the exact issuer, subject, tenant, and registration configuration. Detailed error messages may vary over time and by client type.

Useful verification commands:

~~~bash
# Check app FIC in Entra ID
az ad app federated-credential list --id "<APP_CLIENT_ID>" --output json

# Check FIC of user-assigned managed identity
az identity federated-credential list --identity-name "<IDENTITY_NAME>" --resource-group "<IDENTITY_RG>" --output json

# Check current subscription
az account show --output table

# Check role assignments at the resource group, including inherited permissions
az role assignment list --assignee "<APP_CLIENT_ID>" --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>" --include-inherited --output table
~~~

Verification commands must be run by an account with permission to read the relevant information. Role assignments may take a short time to propagate. When enabling debug logs, restrict log access and avoid sharing raw JWTs or access tokens.

## 11. Comparing workload authentication methods

| Method | Benefits | Limitations and when appropriate |
|---|---|---|
| Service principal + client secret | Broad compatibility, familiar setup | Must store and rotate secrets; use only when better options are not yet viable |
| Service principal + certificate | Not a plaintext password; supports certificate lifecycle management | Still requires managing private keys and certificate expiration |
| Direct managed identity | Azure manages credentials; convenient for supported Azure services | Depends on supported Azure resources and runtime environments |
| Workload identity federation | Eliminates long-lived Azure client secrets; relies on OIDC trust and short-lived tokens | Requires supporting IdP/SDK/service connection, exact FIC, and token-issuance protections |

Example decisions:

- An App Service on Azure needs to read Key Vault: prefer direct managed identity if supported by the service and libraries.
- GitHub Actions needs to deploy Bicep to a resource group: use OIDC and an FIC on an Entra app with appropriate permissions.
- Azure DevOps needs to deploy an application: use an Azure Resource Manager service connection configured with workload identity federation.
- An AKS pod needs to connect to Azure Storage or Key Vault: use AKS Workload Identity linking a Kubernetes service account to a user-assigned managed identity.

## 12. Self-check questions

1. **What does workload identity federation eliminate?** It can eliminate the need to store long-lived Azure client secrets for many workloads by exchanging OIDC tokens with Microsoft Entra ID.
2. **What are the three key claims typically matched in an FIC?** Issuer, subject, and audience.
3. **Does signing in successfully with OIDC equate to Contributor permission?** No. Azure RBAC is granted separately to the identity at a defined scope.
4. **What permission does GitHub Actions need to request an OIDC token?** Typically the job permission id-token: write.
5. **Is the subject for the main branch the same as the subject for the production GitHub Environment?** No; the FIC must be configured to match the exact usage context.
6. **Why create separate identities for development and production?** To isolate permissions, minimize incident blast radius, and enforce different approval controls.
7. **What does an AKS pod need to use workload identity?** A cluster with OIDC issuer/workload identity enabled, a linked Kubernetes service account, a matching FIC, a properly configured pod, and a supported SDK.
8. **If Azure returns 403 after a successful sign-in, what should you check first?** The Azure RBAC role or data-plane permissions at the target scope, rather than hastily changing the FIC.
9. **Is it acceptable to print access tokens to logs for debugging?** No; tokens can be used to access resources while still valid.

## 13. References

- [Microsoft Entra workload identity federation](https://learn.microsoft.com/entra/workload-id/workload-identity-federation) — principles, objects, and WIF support.
- [Federated identity credentials for Microsoft Entra applications](https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust) — configuring trust relationships.
- [GitHub Actions: OpenID Connect with Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure) — creating and using OIDC tokens in GitHub Actions.
- [Azure Login Action](https://github.com/Azure/login) — signing in to Azure from GitHub Actions.
- [Azure DevOps workload identity federation](https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure) — configuring service connections for pipelines.
- [AKS workload identity](https://learn.microsoft.com/azure/aks/workload-identity-overview) — connecting Kubernetes service accounts with Entra and managed identities.
- [Azure RBAC overview](https://learn.microsoft.com/azure/role-based-access-control/overview) — managing access scopes and roles.

Azure Portal interfaces, service connection creation workflows, quotas, and federation capabilities may change by service. In practice, consult the official documentation of the OIDC provider and Microsoft Entra before granting production permissions.
