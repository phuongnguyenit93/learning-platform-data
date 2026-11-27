# Short-Lived Credentials and Access Rotation

Virtual machines, containers, and cloud workloads often need to call APIs to read objects, write logs, access databases, fetch configuration, or manage resources. To perform these operations, workloads must prove their identity and be granted appropriate permissions. If long-lived access keys or passwords are stored directly on the machine, inside an image, or in source code, credentials can be copied and continue to be used even after the machine or application has changed.

**Short-lived credentials** reduce the window during which an exposed credential can be exploited. A workload obtains a time-limited token or credential from a trusted authorization system, uses it within the required scope, and obtains a new one as expiration approaches. **Credential and access rotation** is the process of replacing, refreshing, or revoking issued credentials and permissions to maintain valid access while limiting stale privileges.

In **CLOUD_CORE_SERVICES_COMPUTE**, workload identity is part of the security configuration for VMs, containers, and serverless compute. Identity, token issuance mechanisms, lifetimes, permission scopes, refresh behavior, error handling, and auditing must be designed together. The goal is for workloads to operate continuously without baking long-lived secrets into machine images or configurations.

## 1. Identity, Authentication, and Authorization

Three concepts must be kept distinct:

- **Identity:** represents a person, virtual machine, application, service account, or workload.
- **Authentication:** verifies whether the entity genuinely owns the claimed identity.
- **Authorization:** determines which actions an authenticated identity is allowed to perform on which resources.

For example, a VM can authenticate to the platform using a managed identity. After authenticating, the VM receives a token scoped for the storage service. Permission to read a specific bucket or container is determined by the IAM/RBAC policy attached to that identity.

Do not treat a valid token as synonymous with unrestricted access. A token only proves or carries identity and permission-scope claims according to the system's mechanism. The target service must still verify audience, issuer, expiry, scope/role, and policies.

### 1.1. User identities and workload identities

User identities represent humans signing in with passwords, MFA, security keys, or corresponding authentication methods. Workload identities represent running software and typically require automated authentication without a human typing a password on every API call.

Examples of workload identities:

- Instance role or instance profile attached to a VM.
- Managed identity attached to a virtual machine or application service.
- Service account used by a workload on a cloud platform.
- Kubernetes ServiceAccount attached to a Pod.
- Federated identity via OIDC federation for CI/CD pipelines.

Each workload should have a dedicated identity separated by application, environment, or trust boundary. Sharing a single broadly privileged service account across multiple applications weakens isolation and makes investigating compromised credentials harder.

### 1.2. Distinguishing long-lived secrets from short-lived credentials

| Characteristic | Long-lived secret/credential | Short-lived credential |
| --- | --- | --- |
| Lifetime | May persist for months or until revoked | Has an explicit expiration timestamp |
| Issuance | Created manually or by a secret management system | Dynamically issued by an identity provider or security token service |
| Exposure risk | Can be abused for a long time if undetected and unrevoked | Usage window is bounded by expiry and policy |
| Operations | Requires storage, distribution, and periodic rotation | Requires refresh mechanisms and handling token expiration |
| Examples | Static API key, access key, service account password | STS session, OAuth access token, managed identity token |

Short-lived credentials are still secrets while valid. An attacker can use a stolen token until it expires or is revoked via a supported mechanism. Therefore, tokens must still be protected in memory, logs, temporary files, process environments, and transit.

## 2. Why Prefer Short-Lived Credentials?

Long-lived credentials are hard to manage across many VMs, images, containers, and pipelines. A key baked into an image can appear on every machine launched from that image. If the key is leaked, operations teams must trace distribution scope, replace the key, and update every consumer using the old key.

Short-lived credentials reduce risk in several ways:

- **Time-bounded:** tokens automatically expire after their issued duration.
- **On-demand issuance:** workloads request credentials only when needed and for a specific target service.
- **Reduced secret distribution:** eliminates storing long-lived access keys in images or repositories.
- **Context binding:** tokens can be bound to an audience, scope, role, session tags, or workload identity.
- **Easier auditing:** systems can log the identity, issuance timestamp, and performed actions.
- **Permission revocation:** changing policies or disabling the identity blocks new token issuances; the impact on already-issued tokens depends on the provider's validation and revocation mechanisms.

Short-lived credentials do not replace least privilege, network controls, encryption, or monitoring. They are one layer in an overall security design.

## 3. Mechanisms for Issuing Short-Lived Credentials

### 3.1. Instance role or managed identity

For VMs, the platform can attach an identity to the machine. The workload requests credentials from a metadata service or identity endpoint provided by the platform. The endpoint identifies the VM based on its execution environment and returns temporary tokens or credentials.

General flow:

~~~mermaid
sequenceDiagram
    participant App as App on VM
    participant IMDS as Metadata / Identity endpoint
    participant STS as Identity service
    participant API as Target service
    App->>IMDS: Request token for audience/resource
    IMDS->>STS: Verify VM identity and policy
    STS-->>IMDS: Short-lived token
    IMDS-->>App: Return token and expiry
    App->>API: Call API with token
    API->>API: Validate token and permissions
    API-->>App: Response
    Note over App,API: SDK refreshes token before expiration
~~~

Platform model examples:

- AWS EC2 uses an IAM role attached via an instance profile; applications obtain temporary security credentials through the instance metadata service. Require IMDSv2 and restrict metadata access by policy.
- Azure provides Managed Identity for VMs and certain compute services. Applications obtain access tokens from a platform-managed endpoint, then call services within granted permissions.
- Google Cloud provides service accounts attached to VMs. Workloads can obtain access tokens from the metadata server to call Google APIs per assigned IAM roles.

API names, endpoints, and token lifetimes differ across providers. Use official SDKs or supported identity libraries to handle metadata, caching, and token refresh.

### 3.2. Security Token Service (STS)

STS is a service that issues temporary credentials after verifying an identity or an assume-role request. Instead of distributing long-lived access keys to every workload, the system issues a time-limited credential session, typically containing a temporary access key, temporary secret key, and session token, or an access token depending on the protocol.

An STS session typically includes:

- The identity or role the workload is assuming.
- Start and expiration timestamps.
- Permission scope inherited from the role/policy.
- Session context or additional conditions if supported by the provider.

The session duration should be long enough for the workload to run reliably, yet no longer than necessary. Minimum and maximum durations are defined by the provider. Do not pick an arbitrary number and assume every service supports it.

### 3.3. OAuth 2.0 and OpenID Connect

OAuth 2.0 is commonly used to authorize API access using access tokens. OpenID Connect (OIDC) adds an identity authentication layer on top of OAuth 2.0 using ID tokens.

Key distinctions:

- **ID token:** typically used to prove authentication details of a user or workload to a trusted client; not inherently a token for calling arbitrary APIs.
- **Access token:** used to access a resource server according to the granted audience and scopes/permissions.
- **Refresh token:** can be used to obtain new access tokens without re-authenticating; it usually has a longer lifecycle and higher sensitivity than an access token.
- **Client secret:** a long-lived secret of a confidential client; must be protected and rotated if used.

Workloads should use a flow suited to their execution environment. For server-side applications, authorization code flow with PKCE or client credentials flow may fit depending on the client type and identity provider. For cloud workloads, workload identity federation typically avoids storing long-lived client secrets.

Never send an ID token to an API simply because it is a JWT. The resource server must validate the exact token type, issuer, audience, signature, expiration, and required claims.

### 3.4. Workload identity federation via OIDC

CI/CD runners or workloads outside the cloud can prove their identity using OIDC tokens issued by the CI/CD platform. The cloud identity provider verifies the issuer, signature, and claims such as repository, branch, environment, or subject; if trust conditions are satisfied, the workload receives temporary credentials.

For example, a deployment pipeline is allowed to assume a role only when:

- The token comes from a registered OIDC issuer.
- The subject matches the authorized repository and workflow.
- The branch or deployment environment is on the trusted list.
- The audience matches the credential-issuing service.

Overly broad trust conditions such as accepting any repository or any branch can allow unintended workloads to obtain permissions. Bind the trust policy strictly to the required organization, repository, branch/tag, environment, and audience.

## 4. Metadata Service and Protecting VM Identity

The metadata service provides VM details and is often the path to obtain credentials. Therefore, access to the metadata endpoint must be controlled.

### 4.1. Risks from SSRF

Server-Side Request Forgery (SSRF) occurs when an application is tricked into sending requests to an attacker-controlled address. If the metadata endpoint is reachable from the workload without proper safeguards, an SSRF vulnerability can be exploited to extract VM metadata or tokens.

Mitigation measures:

- Enable provider-recommended metadata protections, such as requiring IMDSv2 session tokens on EC2.
- Restrict hop limits or metadata access paths if supported by the platform.
- Block unnecessary applications from reaching the metadata endpoint.
- Do not allow user-controlled URLs to be fetched by backends without allowlists and destination validation.
- Keep frameworks and HTTP libraries updated and handle redirects safely.
- Restrict instance role permissions so even an exposed token lacks broad privileges.

IMDSv2 mitigates certain SSRF exploit patterns by requiring session tokens and specific request headers, but it does not replace fixing SSRF bugs or enforcing least privilege.

### 4.2. Never put credentials in images

Never bake access keys, client secrets, refresh tokens, private keys, or passwords into:

- Machine images or container images.
- User data, cloud-init, or persistent startup scripts.
- Git repositories, sample configuration files, or build artifacts.
- Shell history, command lines, and pipeline logs.
- Widely shared backups or snapshots.

Images should contain only the application and non-sensitive configuration. At startup, the workload uses the identity attached to the VM or obtains credentials via federation. If a long-lived secret is unavoidable because the target system does not yet support federation, retrieve the secret from a secret manager using a least-privilege bootstrap identity.

## 5. Designing Least-Privilege Permissions for Workloads

Short-lived credentials only limit the exploitation window; overly broad permissions still cause major damage while a token remains valid.

### 5.1. Separating roles by responsibility

For example, an application may need to:

- Read configuration from a specific path.
- Read/write a specific bucket or prefix.
- Write logs and metrics.
- Retrieve a single database's secret.

Instead of granting account-wide administrative permissions, create a role allowing only those operations on specified resources. If an application has multiple components with different responsibilities, assign separate identities to each component.

### 5.2. Scope, audience, and resource restrictions

When supported by the system, tokens should constrain:

- **Audience (aud):** the service or resource server permitted to accept the token.
- **Scope/role:** the set of actions permitted.
- **Resource:** the specific bucket, database, queue, or API.
- **Subject:** the specific workload or user identity.
- **Session duration:** the session lifetime.
- **Network/context conditions:** network, device, or environment conditions if supported by the provider.

Audience does not replace authorization policies. A token with the right audience may still lack permission to read a specific resource. Likewise, broad scopes should not be used when an application only needs a narrow action.

### 5.3. Environment separation

Development, staging, and production should use separate identities, roles, and secrets. Never use production credentials in test environments. If staging is compromised, its permission scope must not allow access to production data or resources.

## 6. Refreshing Credentials Before Expiration

Applications using short-lived credentials must implement a refresh mechanism. Fetching a token only once at startup may work for minutes or hours, then begin failing with unauthorized errors once the token expires.

### 6.1. Using SDKs and credential provider chains

Cloud SDKs typically include a credential provider chain that locates identities in a configured order. In a VM environment, the SDK can use the instance role; in a container, the SDK can use workload identity or the orchestrator's credential provider.

Prefer official SDKs because they normally handle:

- Retrieving tokens from metadata or identity endpoints.
- Caching credentials in memory.
- Refreshing before expiration.
- Bounded retries on transient endpoint errors.
- Selecting the credential provider suited to the environment.

Do not write custom refresh logic when the SDK already supports it. If manual management is unavoidable, account for token lifetime, clock skew, API rate limits, and error handling.

### 6.2. Proactive refresh and avoiding refresh storms

Do not wait until a token expires before requesting a new one. Start refreshing with a safety margin before expiry to tolerate network latency and clock drift.

With many workers running concurrently, if all refresh at the exact same moment, the identity service may experience a traffic spike. Use appropriate shared caching, single-flight deduplication, or jitter to spread out refresh times. Never share tokens across workloads in different trust boundaries.

### 6.3. Handling refresh failures

If the identity endpoint is temporarily unavailable:

1. Continue using the current credential while it remains valid and allowed by policy.
2. Retry with bounded exponential backoff and jitter.
3. Never write tokens or secrets into logs when reporting errors.
4. Emit metrics for refresh failures, remaining lifetime, and retry counts.
5. If the token is nearing expiration and cannot be refreshed, stop accepting new work or transition the workload into a safe degraded state.
6. Once the identity service recovers, refresh and re-verify access permissions.

Do not retry indefinitely with expired or revoked credentials. Distinguish transient network errors, throttling, misconfigured trust policies, wrong audiences, and disabled identities.

## 7. Rotating Long-Lived Credentials When Not Yet Eliminated

Some legacy systems, third-party services, or off-cloud appliances do not yet support workload identity. In those cases, long-lived API keys, passwords, or client secrets may still be required. Manage them in a secret manager with a clear rotation workflow.

### 7.1. Rotation workflow with an overlap window

Replacing an active credential immediately can disrupt applications. The standard workflow is to create a new credential, migrate workloads, verify, and only then revoke the old credential.

~~~mermaid
flowchart TD
    A["Assess credential and consumers"] --> B["Create new credential"]
    B --> C["Store in secret manager"]
    C --> D["Update consumers in batches"]
    D --> E["Verify authentication and business operations"]
    E --> F{"Have all consumers switched to the new credential?"}
    F -- "No" --> D
    F -- "Yes" --> G["Revoke old credential"]
    G --> H["Monitor errors and audit logs"]
    H --> I["Close rotation and update inventory"]
~~~

Recommended steps:

1. Identify the owner, purpose, permissions, expiration, and every consumer using the credential.
2. Check whether the target system supports two concurrent credentials.
3. Create a new credential with equivalent or narrower permissions.
4. Store the new credential in the secret manager; never transmit it over chat or logs.
5. Update a canary group of consumers.
6. Verify connectivity, read/write operations, and error metrics.
7. Roll out updates to remaining consumers in waves.
8. Confirm no requests are still using the old credential.
9. Revoke the old credential and verify it no longer works.
10. Record the rotation outcome, timestamp, and executing person/system.

Keep the overlap window short and bounded. If the old credential is suspected of compromise, consider emergency revocation rather than keeping a long overlap; a controlled outage may be acceptable in that case.

### 7.2. Systems allowing only a single credential

Some services allow only one API key or password at a time. When overlap is impossible:

- Check whether a secondary principal or client can be created for cutover.
- Use a maintenance window and prepare consumers for synchronized updates.
- Update the secret in the centralized store first, then restart/reload consumers on schedule.
- Prepare a credential rollback plan if supported by the target system.
- Verify critical consumers before closing the change window.

Do not delete the old credential before knowing the new credential has been distributed and loaded successfully by consumers.

### 7.3. Rotation is more than changing a secret string

Credentials can be tied to principals, roles, or policies. During rotation, review:

- Are the old permissions still needed?
- Should roles be changed or identities split?
- Does the new credential unintentionally carry broader permissions?
- Does the secret appear in old logs, dumps, or backups?
- Which consumers have not updated or are still using cached values?
- Has the old credential been revoked everywhere relevant?

Creating a new key while leaving the old key active indefinitely does not remove the risk.

## 8. Rotating Access Permissions and Revoking Access

Rotation can involve credentials, while access permissions themselves also need periodic review and adjustment.

### 8.1. Changing policies safely

When tightening permissions:

1. Collect audit logs to identify the actions the workload actually uses.
2. Compare currently granted permissions against current tasks.
3. Create a narrower policy or a new role.
4. Attach the new policy to a test group of workloads.
5. Verify application behavior and infrequently executed flows such as backup, restore, and failover.
6. Migrate all workloads to the new policy.
7. Detach the old policy and verify no excess permissions remain.

Policy changes may affect the next request immediately, though some systems cache authorization decisions or token claims until token expiration. Understand the actual mechanism to determine how long old permissions remain effective.

### 8.2. Emergency revocation

When a credential is compromised or a workload is breached:

- Disable or revoke the credential/principal as supported by the provider.
- Detach sensitive roles or policies and block unnecessary access paths.
- Revoke sessions or tokens if supported by the service; otherwise, limit impact by changing policies and waiting for tokens to expire per mechanism.
- Rotate related secrets, keys, or certificates.
- Inspect audit logs, source IPs, user agents, resources, and anomalous actions.
- Isolate affected VMs/containers and preserve forensic evidence.
- Rebuild workloads from trusted images and issue new identities if needed.

Deleting a credential file from a VM does not revoke copies already exfiltrated. Revocation must happen at the identity provider or target system.

## 9. Storing and Distributing Secrets

A centralized secret manager stores secrets, enforces access controls, logs audits, and automates rotation. Workloads should authenticate to the secret manager using short-lived identities and read only the exact secrets needed.

Principles:

- Each application or workload has its own secret path.
- Grant read access only for required secrets; avoid list or store-wide admin permissions unless needed.
- Minimize how long secrets stay in memory and avoid writing them to disk.
- Avoid passing secrets via environment variables if the runtime or OS offers a safer delivery method; if used, restrict process inspection and memory dump permissions.
- Never pass secrets as command-line arguments because they can appear in process listings or audit logs.
- Mask sensitive values in logs, traces, crash dumps, and error reports.
- Enable auditing for read, write, rotate, and delete secret operations.
- Have a recovery plan when the secret manager or KMS is unavailable.

If a workload caches secrets in memory, enforce a TTL and reload mechanism. Do not keep secrets cached indefinitely simply because the application lacks refresh logic.

## 10. Short-Lived Credentials in VMs, Containers, and Serverless

### 10.1. Virtual machines

VMs typically use instance roles or managed identities. When creating a VM, attach the role matching its task. The SDK retrieves credentials from the metadata/identity endpoint and refreshes them when needed.

Key controls:

- Never share one access key across an entire fleet.
- Restrict metadata endpoint access from applications at risk of SSRF.
- Separate roles by environment and machine role.
- Never place long-lived secrets in user-data.
- Verify role attachments when creating images or changing instance types to avoid losing identity bindings.

### 10.2. Containers and Kubernetes

Containers can receive identities from the orchestrator instead of embedding credentials in images. On Kubernetes, a ServiceAccount bound to a Pod can issue tokens; projected tokens have configurable lifetimes and audiences. On cloud platforms, workload identity integration maps a Kubernetes ServiceAccount to a cloud identity.

Principles:

- Disable automatic mounting of ServiceAccount tokens if the Pod does not need to call the Kubernetes API.
- Grant Role/RoleBindings only in the required namespace and resources.
- Use projected service account tokens with appropriate audiences and lifetimes when supported by the platform.
- For cloud APIs, use workload identity federation or official cloud integration mechanisms.
- Do not store cloud access keys in Kubernetes Secrets when identity federation can be used.
- Restrict node identity permissions; Pods must not inherit broad administrative node permissions.

Default Kubernetes Secrets are not automatically equivalent to a fully encrypted and access-controlled secret manager. Configure encryption at rest, RBAC, auditing, and external secret store integration as required.

### 10.3. Serverless

Functions or serverless containers typically have a platform-assigned execution identity. Attach a role/service account to the function and scope permissions to its task. The runtime retrieves short-lived tokens from the identity service.

Do not store token state on temporary filesystems assuming the instance will persist across invocations. Serverless runtimes may be recycled or scaled to zero. Use the SDK provider chain and store business state in durable services.

### 10.4. CI/CD and off-cloud workloads

Pipelines running on GitHub Actions, GitLab CI, or similar systems can use OIDC federation to exchange identity tokens for temporary credentials. This avoids storing long-lived cloud access keys in CI secrets.

Trust policies should restrict:

- Trusted issuer URL.
- Permitted audience.
- Organization/repository/project.
- Branch, tag, or protected environment.
- Specific workflow or subject if claims are provided by the platform.

Pipelines should receive deployment permissions only for the duration of the job. IAM administration or production resource deletion permissions should be separated from routine deployment roles.

## 11. Task-Based Permission Configuration Example

The conceptual policy example below illustrates allowing a workload only to read one object prefix and write logs. This is not a ready-to-use policy for a specific provider.

~~~yaml
workload_identity:
  name: invoice-worker
  environment: production
  credential:
    source: workload-identity
    max_session_duration: provider-defined
    audience:
      - object-storage-api
  permissions:
    - action:
        - object:Get
      resource:
        - bucket:invoice-archive/pending/*
    - action:
        - logs:Write
      resource:
        - log-group:/services/invoice-worker
  denied_actions:
    - iam:*
    - storage:Delete
~~~

In real deployments, translate this into the provider's IAM/RBAC syntax and specify exact resource ARNs/IDs and action names. Some services require additional permissions to list prefixes or read metadata; add them only after verifying the application truly needs them.

## 12. Token Acquisition and Refresh Flow Example

The following pseudocode illustrates how an application uses an SDK credential provider. Specific functions depend on the SDK and language:

~~~text
credentialProvider = createWorkloadCredentialProvider()
client = createCloudApiClient(credentialProvider)

while applicationIsRunning:
    request = receiveWork()
    try:
        result = client.performAllowedAction(request)
        acknowledge(request)
    catch AuthenticationExpired:
        credentialProvider.refresh()
        retryOnceIfOperationIsIdempotent(request)
    catch AuthorizationDenied:
        recordPermissionFailureWithoutSecrets()
        sendToFailureQueueOrStopSafely(request)
~~~

Distinguish authentication errors from authorization errors:

- **401/Unauthenticated:** missing token, invalid signature, wrong issuer/audience, or expired token.
- **403/Forbidden:** identity is recognized, but policy does not permit the action.

Exact HTTP status codes and error names vary by API. Do not automatically retry 403 errors continuously because refreshing a token usually does not widen granted permissions. For write or payment operations, retry only when an idempotency key or outcome-verification mechanism prevents duplicate execution.

## 13. Monitoring and Auditing Identities

Short-lived credentials must be monitored to detect refresh failures, overly broad permissions, and anomalous behavior.

| Observation group | Metrics or events | Purpose |
| --- | --- | --- |
| Token issuance | Issuance count, errors, latency, issuer, audience | Detect trust or identity service failures |
| Token lifecycle | Remaining lifetime, refresh success/failure | Detect soon-to-expire tokens or unstable refreshes |
| API usage | Principal, action, resource, source, result | Detect anomalous behavior and unnecessary permissions |
| Policy | Role, trust policy, scope, and binding changes | Track access permission modifications |
| Secrets | Read, create, rotate, revoke, delete | Identify consumers and access history |
| Long-lived credentials | Credential age, owner, last used, expiry | Find stale or unused keys |

Never write raw access tokens, refresh tokens, secret keys, or passwords to logs. You may log token IDs, key IDs, principals, expirations, or correlation IDs as long as credentials are not exposed.

Alerts should cover:

- Repeated token refresh failures or throttling at the identity endpoint.
- A workload requesting an unusual audience or scope.
- A long-lived credential exceeding its rotation interval.
- An old API key still being used after a new credential was deployed.
- A principal performing administrative actions outside deployment schedules.
- A workload calling APIs from an unexpected source or region.

## 14. Periodic Rotation Plan

A rotation schedule should reflect the credential type, automation capability, and workload criticality.

| Credential type | Priority approach | Key considerations |
| --- | --- | --- |
| Instance role / managed identity | Use provider-issued short-lived credentials | Review roles and trust policies periodically |
| STS / session credential | SDK auto-refreshes before expiry | Monitor lifetime, caching, and identity endpoint errors |
| OIDC federation | Issue tokens per job/workload | Constrain issuer, audience, subject, and environment |
| Third-party API key | Secret manager and scheduled rotation | Verify overlap and consumers before revoking |
| Database password | Prefer IAM/database auth or integrated secret rotation | Update connection pools and active connections |
| TLS certificate | Automated renewal and deployment of new certificates | Track chain, SANs, expiry, and service reload |
| Administrative SSH key | Prefer short-lived SSH certificates or identity-aware access | Revoke principals and control legacy authorized keys |

No single rotation period fits every secret type. Follow organizational policy, compliance requirements, provider capabilities, and incident response timelines for compromised credentials. Automating rotation reduces human error, though consumers and results still need verification after changes.

### 14.1. Credential inventory

Organizations should maintain a credential inventory recording:

- Credential name and type.
- Owner and consuming application.
- Storage location or identity provider.
- Permitted permissions and accessible resources.
- Creation date, expiration date, or rotation schedule.
- List of consumers and environments.
- Revocation method and recovery plan.
- Final status after the last rotation.

Credentials lacking a clear owner or consumer should be investigated before deletion. Do not bulk-revoke solely by age without checking dependencies.

## 15. Handling Exposed or Expired Credential Incidents

### 15.1. Exposed credential

1. Identify the credential type, principal, permissions, and resource scope.
2. Revoke or disable the credential at the identity provider/target service.
3. Block or narrow policies to constrain still-valid tokens/sessions.
4. Rotate related secrets, keys, certificates, or trust bindings.
5. Inspect audit logs before and after the suspected exposure window.
6. Isolate the workload if compromise is suspected.
7. Rebuild the workload from a trusted image and assign a new identity if needed.
8. Verify the old credential is no longer accepted.
9. Document root cause, scope, and preventive controls.

### 15.2. Token expiration during processing

If a long-running task exceeds the token lifetime, the SDK must refresh credentials before the next request. For tasks lasting hours, avoid holding a single token in startup configuration variables. Use an auto-refreshing provider or break work into checkpointed steps.

If streaming APIs or long-lived connections do not automatically update tokens, check the protocol's reauthentication mechanism. Some already-authenticated connections may continue until closed, while new connections are rejected after expiry. Behavior depends on the service.

### 15.3. Rotation breaks workload permissions

When changing roles or policies, 403 errors can appear if the new permission set omits an auxiliary action. Check audit logs and policy evaluations to identify the denied action/resource. Do not solve this by granting Administrator or broad wildcards. Add only the minimal proven-required permission, retest, and document the justification.

## 16. Common Mistakes

- Baking access keys or client secrets into machine images or container images.
- Sharing one broadly privileged identity across multiple VMs or applications.
- Fetching a token once at startup and never refreshing it.
- Using an ID token to call a resource API without checking audience and token type.
- Trusting every repository/branch in OIDC federation.
- Assuming token expiration means a leaked token is revoked immediately.
- Revoking old credentials before all consumers have switched to the new ones.
- Keeping old credentials active too long after a successful rotation.
- Retrying 403 responses endlessly or retrying non-idempotent write operations.
- Logging raw tokens, secrets, or authorization headers.
- Rotating keys without reviewing the roles and permissions attached to them.
- Deleting secrets without checking backups, caches, or remaining consumers.
- Allowing every container to access metadata or node identities.

## 17. Workflow for Deploying Secure Workload Identity

1. **Classify the workload:** determine whether it is a VM, container, serverless function, or off-cloud pipeline.
2. **Choose native identity:** instance role, managed identity, service account, or OIDC federation.
3. **Design trust:** constrain issuer, audience, subject, environment, and workload source.
4. **Grant least privilege:** restrict actions, resources, lifetimes, and access conditions.
5. **Integrate SDK:** use provider chains, caching, and automatic refresh.
6. **Protect metadata and secrets:** mitigate SSRF, never bake credentials into images, use a secret manager when needed.
7. **Test lifecycle:** verify token issuance, pre-expiry refresh, error handling, and workload reconnection.
8. **Set up auditing:** log principal, action, resource, and outcome without logging credentials.
9. **Maintain inventory and rotation:** track owners, consumers, lifetimes, and revocation workflows.
10. **Practice incident drills:** test revoking identities, rotating secrets, recovering workloads, and verifying old privileges are invalidated.

## 18. Operational Principles

1. **Prefer workload identities:** use instance roles, managed identities, service accounts, or federation instead of static keys.
2. **Limit permissions:** separate identities by application and environment, granting exact actions on exact resources.
3. **Limit lifetimes:** use tokens with appropriate expirations and refresh before expiry.
4. **Constrain tokens:** validate issuer, audience, subject, scope, and policies at the proper layer.
5. **Protect metadata:** mitigate SSRF risks and restrict instance identity permissions.
6. **Rotate with overlap:** distribute new credentials, verify consumers, and only then revoke old credentials when supported.
7. **Revoke at the source:** deleting copies on machines does not replace revoking at the identity provider.
8. **Never log secrets:** log only metadata needed for investigation, never raw tokens or secrets.
9. **Track permissions too:** review roles, trust policies, and policy bindings alongside credential rotation.
10. **Test recovery:** verify refresh, revocation, reconnection, and fallback plans when the identity service is unavailable.

Short-lived credentials allow workloads to access cloud services without carrying long-lived secrets in images or source code. By combining workload identity, least privilege, automatic refresh, controlled rotation, and auditing, engineering teams can shrink the exposure window of compromised credentials while maintaining continuous operations across VMs, containers, and serverless workloads.
