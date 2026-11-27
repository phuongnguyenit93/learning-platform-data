# Secret Versions, Expiration, and Rotation Strategies

A Spring Boot application running on Azure Container Apps needs to call a payment partner's API. The API requires a client secret stored in **Azure Key Vault**. Today the security team creates a new secret and marks the old secret to expire in 60 days. However, some containers still use the old credential due to caching; some jobs hardcode a URL containing the old version ID; and once the partner invalidates the old credential, the application starts getting `401 Unauthorized` errors. The operations team tries updating the secret again, but the outage persists.

This is not just a problem of “swapping a secret string”. **Secret rotation** is a multi-state process involving the **credential issuer**, **secret versions in the vault**, **validity windows**, **how applications fetch and cache values**, **deployment order**, **rollback capability**, and **post-rollout monitoring**.

A reliable architecture must answer:

1. **Which version is the active secret value?** Does the application query by name or by a pinned version ID?
2. **Until when can the secret be used?** Is the `expiresOn` field in Key Vault synchronized with the credential's actual expiration at the target system?
3. **Who generates the new credential?** Key Vault stores the value, but typically lacks permission to change credentials at a partner system on its own.
4. **How do consumers switch to the new value?** Re-fetch, refresh, restart, rolling deployment, or synchronized configuration?
5. **Can two credentials remain valid concurrently for a transition period?** If not, an appropriate downtime or atomic cutover procedure must be chosen.
6. **Can we fall back to the old version on failure?** If the old credential has already been revoked at the source, “rolling back the version in the vault” will not bring it back to life.

Example architecture:

```text
                  CREDENTIAL SOURCE
          API provider / Database / Identity provider
                       |
                Generate new credential
                       |
                       v
                ROTATION WORKFLOW
          policy → validate → publish → rollout
                       |
                       v
               AZURE KEY VAULT
          secret "partner-api-credential"
                 ├── version A (old)
                 └── version B (new)
                       |
            +----------+----------+
            |                     |
            v                     v
       App Service             Container Apps
       Key Vault ref           Java SecretClient
       refresh/restart         refresh/cache TTL
            |                     |
            +----------+----------+
                       |
                       v
            Authenticate with upstream
                       |
               Verify → retire old
```

This lesson belongs to the **Secrets, Keys, and Certificates** chapter in the `CLOUD_PROVIDERS_AZURE` module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, and data to deployment, monitoring, security, and cost control. Therefore, it places the **secret lifecycle** within the full Azure application and operational workflow rather than just showing a single command to create a secret.

> **Scope:** Azure Key Vault **Secrets** are the primary focus. **Keys** and **Certificates** have separate rotation/renewal mechanisms and policies and must not be conflated. APIs, event types, quotas, App Service/AKS refresh cycles, and automation capabilities can vary by product, SDK version, and configuration. Check the documentation and test on a lab vault before applying to Production. All vault/secret names, timestamps, and credentials in examples are illustrative; never use real secrets in terminals, documentation, logs, or Git.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain secrets, secret names, values, version IDs, attributes, tags, and secret identifiers.
2. Distinguish **versionless** retrieval from **version-pinned** retrieval and the impact of caching.
3. Describe `enabled`, `notBefore`, `expiresOn`, and the actual validity of the credential upstream.
4. Explain why **setting an expiration date does not mean automatic rotation or revocation**.
5. Design **rotation intervals, lead times, overlap windows, rollback windows, max secret age, and emergency revocation**.
6. Compare **dual-credential rotation**, **single-credential cutover**, and **dynamic/short-lived credentials**.
7. Design automation with **Event Grid, Azure Functions, schedulers, and Key Vault**.
8. Use **managed identity/Entra RBAC** so consumers and rotation workers hold only least-privilege permissions.
9. Execute the sequence create new version → rollout → verify → disable/revoke old in the proper order.
10. Handle App Service Key Vault references, AKS Secrets Store CSI, Spring Boot/Java SDK, and various consumer caches.
11. Handle compromised secrets, expired versions, access denied errors, and version caching bugs.
12. Read **version metadata** using Azure CLI/Java SDK without exposing secret values.
13. Build alerts, auditing, runbooks, and soft delete/purge protection controls.
14. Complete a rotation lab testing success, failure, and rollback paths.

## 2. What Is a Secret in Azure Key Vault?

A **Key Vault secret** is a confidential value stored under a **name**; each time a new value is set under that name, a **new version** can be created. Example:

```text
Vault:
  kv-orders-prod

Secret name:
  partner-api-credential

Versions:
  7b9... (created first, value A)
  a61... (created later, value B)

Application:
  uses "partner-api-credential"
  → resolves to a suitable version through data-plane API/reference
```

Common types of data stored as secrets:

- API tokens/credentials issued by an external provider.
- Passwords for systems that do not yet support Entra/managed identities.
- Client secrets for legacy systems.
- Shared credentials under integration contracts.
- Sensitive configuration strings that lack a passwordless alternative.

**Key Vault Secrets is not an arbitrary config database.** Non-sensitive data like feature flags should use App Configuration or an appropriate configuration store. Whenever you can **eliminate a secret** using managed identity/workload identity, that is usually a stronger security improvement than repeatedly rotating a long-lived password.

## 3. Distinguishing Secrets, Keys, and Certificates

| Key Vault Object | Value / Capability | Rotation Characteristics |
|---|---|---|
| **Secret** | Confidential value such as a password/token, consumed by apps/SDKs. | Creates a new value version and syncs with the source system; automation is typically implemented by the app/rotation worker. |
| **Key** | Cryptographic key for encrypt/decrypt/sign/verify operations per key type. | Has its own **key rotation policy**/versioning mechanism depending on vault/key type/features. |
| **Certificate** | TLS certificate along with metadata/policy and linked components. | Has its own issuance/renewal/integration policies and CA/certificate lifecycle. |

A certificate managed through Key Vault may have a **backing secret containing certificate contents**, but **changing an arbitrary secret is not equivalent to renewing a certificate from a CA**.

A cryptographic key can allow multiple key versions to decrypt older data. For passwords/API tokens, the old version usually has to be **revoked at the originating authentication system**. Do not copy a rotation policy designed for keys onto secrets without understanding the difference.

## 4. Secret Name, Version, and Identifier

A secret has a stable logical name and distinct versions:

```text
https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential
                                   ↑          ↑
                                /secrets/    secret name

https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential/a61...
                                                                  ↑
                                                             version ID
```

| Component | Meaning |
|---|---|
| **Vault URI** | Key Vault endpoint, tied to environment/tenant and network path. |
| **Secret name** | Stable logical identifier for the credential within the vault. |
| **Version identifier** | Identifier for a snapshot of the secret value at creation time. |
| **Versionless identifier** | URI by name, omitting a specific version ID. |
| **Versioned identifier** | URI containing both name and version ID, targeting an exact version. |
| **Secret value** | Confidential data; never appears in the URI and must never be logged. |
| **Secret properties** | Attributes and metadata such as enabled/notBefore/expiresOn, content type, and tags. |

**A version ID is not a secret value.** However, the full identifier can reveal system/vault/credential names, so do not put it in public logs if organizational policy forbids it. Do not treat a version ID as authorization; the application must still be authenticated and authorized.

## 5. Lifecycle of a Secret Version

Simple scenario:

```text
Provision external credential A
        |
        v
Publish Key Vault version A
        |
        v
Active (consumer uses A)
        |
        v
Rotation preparation
        |
        v
Provision credential B at upstream
        |
        v
Publish Key Vault version B
        |
        v
Consumers migrate and validate B
        |
        +-- Success → disable/revoke A after overlap window
        |
        +-- Failure → pause, fix or rollback while A still valid
        |
        v
Retain metadata/audit under retention policy
```

**Two lifecycles must stay synchronized**:

1. The version stored in **Key Vault**.
2. The credential accepted by the **target system**.

A new version B in Key Vault is not guaranteed to be accepted by the partner API—for example, if the key hasn't been activated yet. Conversely, credential B existing upstream without being published to the right vault prevents the application from using it.

## 6. Does Creating a New Version Overwrite the Old Version?

Typically, setting a **new value for the same secret name** via the `setSecret` API creates a **new secret version**. The old version remains a distinct version according to the vault's lifecycle and retention policy rather than having its value overwritten.

```text
T0: setSecret("partner-api-credential", "A")
    → version v1

T1: setSecret("partner-api-credential", "B")
    → version v2

v1.value = "A"  (old value)
v2.value = "B"  (new value)
```

**A version's secret value is not edited in place** like “changing A to B inside v1”. When the value needs to change, create a new version.

However, **a version's metadata/attributes** can be updated via the appropriate API and permissions, such as changing `enabled` or `expiresOn`. Doing so **does not create a new credential upstream**.

### Audit Implications

Distinguish:

- “**Add secret version**”: a new value was published.
- “**Update secret properties**”: some metadata changed.
- “**Revoke upstream credential**”: the actual secret stopped being accepted by the target system.
- “**Delete/purge secret**”: resource deletion operations in the vault, not a standard rotation step.

## 7. Versionless vs. Version-Pinned Access

**Versionless:**

```text
.../secrets/partner-api-credential
```

**Version-pinned:**

```text
.../secrets/partner-api-credential/<exact-version-id>
```

| Usage | Pros | Risks |
|---|---|---|
| **Versionless / get by name** | Consumers can pick up new versions without changing the secret URI/config. | Must manage caching/refresh and verify behavior if the latest version is disabled/invalid. |
| **Version-pinned / get by name + version** | Reproducible configuration; verifies the exact version per release. | Does not automatically move to new versions; rotation requires updating deployment/config. |
| **Versionless with infinite app cache** | Avoids vault requests after startup. | Effectively keeps using the old value; a versionless URL does not automatically refresh memory. |
| **Version-pinned per release/canary** | Lets you verify v2 on a small subset of consumers. | If v1 is revoked before all deployments update, the remaining ones will fail. |

**Do not assume a versionless secret automatically falls back to an older enabled version** if the newest version has an issue. Version selection and eligibility behavior must be verified against the specific service/API/consumer; the best workflow is **never publishing an untested version**.

## 8. Version Identifiers in Application Code

A Java application using the Key Vault SDK can call:

```java
KeyVaultSecret current = secretClient.getSecret("partner-api-credential");
// Retrieves by name, without specifying a version.

KeyVaultSecret specific = secretClient.getSecret(
    "partner-api-credential", "REPLACE_WITH_VERSION_ID");
// Retrieves a specific version.
```

Both calls **require appropriate data-plane permissions**. Never print `current.getValue()` or `specific.getValue()` to the console.

During a canary deployment, you can pin version B in staging or on a subset of replicas to verify; once Production cutover finishes, switch back to versionless if that is the approved application strategy. Avoid undocumented mixing of pinned and versionless references across service instances.

## 9. Attributes: enabled, notBefore, and expiresOn

Three common attributes:

| Attribute | Practical meaning | What you should not infer |
|---|---|---|
| **`enabled`** | Metadata/toggle controlling whether a version can be used per Key Vault semantics. | Does not mean the credential is revoked upstream. |
| **`notBefore`** | Timestamp when the version becomes valid per policy/vault semantics. | Does not guarantee consumers are ready to use it at that moment. |
| **`expiresOn`** | Expiration timestamp attached to the version, supporting governance/retrieval and service alerting. | Does not auto-generate a new version or change the upstream password. |

Note that SDKs/CLIs may display timestamps in UTC/ISO or epoch formats; applications should standardize on **UTC** rather than comparing dates in arbitrary server timezones.

Do not reduce enabled/disabled/expiry metadata into a simple “boolean table” and treat it as the sole source of truth: the API provider's authentication state and consumer session/connection state matter just as much.

### Content Type and Tags

Secret properties can also include `contentType` and `tags`:

- `contentType` can note the general data format.
- `tags` support owner, system, rotation policy ID, environment, and ticket references.

**Never store passwords/tokens or PII in tags**; metadata is often much easier to list than secret values and follows different logging policies.

## 10. Expiration Metadata Does Not Rotate Credentials Automatically

This is the most critical point.

```text
Secret.version A:
  expiresOn = 2027-01-20T00:00:00Z

Does NOT mean:
  - Azure automatically changes the partner API key at that time
  - Azure automatically creates version B with a valid value
  - Spring Boot automatically reads version B
  - Consumer sessions immediately stop using A
  - The API provider has revoked A
```

**Expiration in Key Vault** is part of the **secret object/version lifecycle**; the **actual credential expiration at the source system** can be completely independent. Whether the vault/API permits or denies reading a version around `notBefore/expiresOn/enabled` follows specific product behavior, but **that metadata must never be treated as the sole method of revoking a credential distributed externally**.

If the partner invalidates credential A, an app holding A in memory cannot “keep reading from cache” and succeed. Conversely, if a version is disabled in the vault, a client that already retrieved the value and still holds a valid upstream credential can continue using its in-memory copy until the real credential is revoked or the session is terminated.

**Revocation must happen where the credential is validated**, paired with controlling active online consumers.

## 11. Two Clocks: Vault Expiry and Upstream Validity

Imagine:

```text
Key Vault version A:
  expiresOn = 2027-01-20T00:00Z

Partner API credential A:
  upstream expiration = 2027-01-10T00:00Z

Application:
  reload interval = 24 hours
```

If you only watch `expiresOn` in the vault, the application can lose access on **January 10**, ahead of the vault timestamp. In the reverse direction, vault metadata can expire before the upstream invalidates the credential.

A governance data model should track:

| Field | Source |
|---|---|
| Secret name/version | Key Vault metadata. |
| Credential provider/account | Integration registry/owner. |
| Upstream validUntil | API provider/issuer contract. |
| Vault expiresOn | Key Vault secret attributes. |
| Rotation window | Internal policy, including lead time. |
| Consumer refresh interval | App Service/AKS/SDK implementation. |
| Revocation date | Audited cutover process. |
| Last validation | Synthetic test/health telemetry. |

**Never use a single expiry field as proof that a credential is still valid or that consumers have switched versions.**

## 12. Expiration, TTL, and Cache Duration Are Three Different Things

Distinguish:

- **Credential lifetime:** how long does upstream accept the value?
- **Key Vault version expiry:** time metadata managing a secret version.
- **Consumer cache TTL/refresh cadence:** how long the app keeps a local copy before re-fetching.
- **Token/session lifetime:** a token derived from the credential can have its own independent lifetime.
- **Secret rotation interval:** how often new credentials are issued.
- **Overlap window:** how long old and new credentials are valid concurrently.

Example:

```text
Rotation every 30 days
Credential expires after 60 days
Consumer reload every 15 minutes
Overlap after publish 48 hours
```

This is an **illustrative policy**, not a Microsoft default or universal recommendation. Actual durations depend on risk, provider behavior, replica count, offline tolerance, and rollback capability.

### Do Not Use TTL as an Authorization Policy

A 15-minute secret cache does not replace upstream credential revocation during a leak. TTL only bounds how quickly new values are picked up when the refresh mechanism works properly.

## 13. Risk-Based Rotation Scheduling

Not every secret needs the same rotation cadence. Build a risk-based table:

| Credential | Impact if leaked | Dual-key capability | Strategy |
|---|---|---|---|
| API key reading public data from provider | Low–medium. | Possible. | Periodic rotation and measure adoption. |
| Token writing to payment system | High. | Depends on provider. | Shorter interval, approvals, anomaly monitoring. |
| Legacy DB password | High if widely shared. | May support dual users or not. | Planned rotation, test connection pools and rollback. |
| Webhook signing secret | Spoofing risk if leaked. | Usually must accept multiple keys/versions temporarily. | Key IDs, dual-signature verification during overlap. |
| Service principal client secret | App impersonation risk. | Supports multiple concurrent credentials per platform. | Prefer managed identity; if still required, scheduled dual credentials. |
| Short-lived lab secret | Low when simulated. | Yes. | Short TTL, auto-cleanup per policy. |

Policy should consider:

- The sensitivity of data and actions the credential authorizes.
- Ability to detect compromise.
- Number of consumers, environments, and locations.
- Whether the provider can issue multiple concurrent credentials.
- SLA/downtime/rollback constraints.
- Regulatory/contractual requirements.
- API and operational cost of rotation.
- Maximum deployment time and longest cache duration.
- Readiness of automation and human approvals.

**Rotating too frequently with unreliable automation can increase downtime.** The goal is reducing overall risk, not merely shrinking the number of days a secret exists on paper.

## 14. Calculating Lead Time and Rotation Deadlines

Suppose the upstream credential expires at `E`, with durations:

- `T_provision`: generating/approving the new credential.
- `T_rollout`: time to deploy across all consumers.
- `T_verify`: testing, reconciliation, and error detection.
- `T_buffer`: contingency for incidents or holidays.

Rotation must start no later than:

```text
Rotation start deadline =
  upstream expiry
  - T_provision
  - T_rollout
  - T_verify
  - T_buffer
```

Internal example:

```text
Credential expiry: T0 + 60 days
Provision/approval: 2 days
Rollout max: 1 day
Verification: 1 day
Buffer: 7 days

Start no later than day 49.
```

**This is a planning formula**, not a Key Vault default. For high-risk systems, cutover may be required even earlier so it never runs right up against expiration.

## 15. Dual-Credential Rotation: Preferred When Upstream Supports It

When the provider allows two credentials to be valid simultaneously:

```text
T0: Credential A valid, app uses A
T1: Create B at provider; A still valid
T2: Store B as new Key Vault version
T3: Canary with B; A still valid
T4: Rollout/reload all consumers to B
T5: Verify traffic uses B, no auth failures
T6: Revoke A at provider
T7: Disable old Key Vault version / retain under policy
```

**Advantages**:

- Little or zero downtime rollout.
- Supports canarying and rollback during the overlap window.
- Applications can transition from A to B replica by replica.
- Leaves time to catch unexpected dependencies.

**Trade-offs**:

- **Two valid credentials** exist temporarily; both must be protected and audited.
- Must track which consumers are still using A.
- Providers may limit the number of active keys.
- Publishing B too early while consumers auto-refresh untested values creates risk.

**Never revoke A simply because version B was created in the vault.** You need evidence that consumers have switched and upstream accepts B.

## 16. Single-Credential Cutover: When No Overlap Exists

Some systems only allow one active password/API token at a time:

```text
Old A valid
   |
   v
Maintenance window / quiesce traffic
   |
   v
Change upstream credential A → B
   |
   v
Publish B to vault + force reload all consumers
   |
   v
Health checks / resume traffic
```

The risk is the **skew window** between upstream changing the password and consumers receiving B. Possible approaches:

1. Use a **two-account/two-user strategy** if the provider can issue parallel accounts.
2. Define a clear maintenance window and degraded mode.
3. Coordinate via a stateful, approval-gated deployment controller.
4. Reduce connection pooling/cache TTL during the cutover phase.
5. Account for background jobs and long-lived connections.
6. Have a recovery procedure if publish/refresh fails.
7. If rollback is infeasible, plan a fast **roll forward** to another fresh credential.
8. Never run multiple rotation workers concurrently.

Do not promise zero-downtime if the source allows only a single credential and no atomic switching mechanism exists.

## 17. Emergency Rotation on Suspected Compromise

**Scheduled rotation** and **emergency rotation** have different priorities.

When a secret leak is suspected:

1. Activate incident response and record timestamps/impact.
2. Scope exposure: vault/version, upstream provider, consumers, and logs.
3. Issue or activate a clean credential in a controlled environment.
4. Migrate consumers to the new credential as quickly as safely possible.
5. **Revoke the exposed credential upstream**, even if a normal overlap window has not ended.
6. Check whether tokens/sessions derived from the old credential must also be invalidated.
7. Rotate related credentials if lateral exposure is possible.
8. Check Git/CI artifacts/logs/backups for leftover copies.
9. Never paste the raw compromised credential into tickets or chat.
10. Monitor for anomalous activity and complete a postmortem.

Emergency rotation may require a **controlled service outage** to stop abuse. Never “keep the old credential active for 48 more hours just in case” if it has been leaked.

## 18. Why Updating Secret Metadata Alone Is Not Enough

Actions like “set `expiresOn` to tomorrow” or “`enabled=false`” change Key Vault state, but:

- They do not create credential B upstream.
- They do not update environment variables read when containers started.
- They do not close already-authenticated database connections.
- They do not invalidate previously issued tokens.
- They do not erase copies in pod/VM memory.
- They do not rotate an external partner's client secret.
- They do not verify the application is using the new version.

Therefore, **reconciliation** across Key Vault, upstream, and consumers is required. For credentials still valid upstream, **disabling in the vault is not a complete revocation control**.

## 19. Rotation Automation Architecture on Azure

A common pattern:

```text
Key Vault secret expiresOn / inventory
                |
        Event Grid events or scheduler
                |
                v
        Azure Function / Logic App
                |
       +--------+-----------+
       |                    |
       v                    v
   Policy & lock       Upstream credential API
   state store              |
       |                    v
       |                New value B
       |                    |
       +---------+----------+
                 |
                 v
            Key Vault
         setSecret(name, B)
                 |
                 v
         Deployment/refresh signal
                 |
                 v
         Consumers validate B
                 |
                 v
        Revoke A + audit + alert
```

**Key Vault does not inherently know how to generate valid credentials for every third party.** The rotation worker must integrate with the provider API and hold its own least-privilege permissions. If upstream is a legacy system requiring manual password changes, automation should open a ticket/approval rather than assuming an API exists.

## 20. Event Grid: Tracking Secret Lifecycle

Key Vault can emit **Event Grid events** related to secret lifecycles as supported, such as:

- `Microsoft.KeyVault.SecretNewVersionCreated`.
- `Microsoft.KeyVault.SecretNearExpiry`.
- `Microsoft.KeyVault.SecretExpired`.

Exact event names, emission timing, metadata conditions, and event types must be verified against the vault's actual **Event Grid schema/capabilities**.

### Do Not Rely on Near-Expiry Events as the Sole Scheduler

A near-expiry event can be missed if:

- The secret lacks expiry metadata meeting event criteria.
- The subscription/endpoint route fails.
- The Function is disabled or misdeployed.
- Retries/DLQ are left unhandled.
- The rotation worker ran but failed.
- The upstream credential expired **before** the `expiresOn` metadata.
- The event arrived during maintenance or lacked an active owner.

Combine **event-driven triggers + periodic inventory reconciliation**. Schedule a daily or risk-appropriate scan to detect missed events.

### Never Blindly Trust Events

Event Grid delivery can retry or duplicate; workers must verify source/event type, never treat the raw event body as a credential, and avoid creating infinite versions from duplicate deliveries of the same event.

## 21. Stateful Workflow Structure

A rotation workflow must maintain explicit state:

```text
PLANNED
   |
   v
PROVISIONING
   |
   v
UPSTREAM_NEW_READY
   |
   v
VAULT_VERSION_PUBLISHED
   |
   v
CANARY_VALIDATED
   |
   v
CONSUMERS_MIGRATING
   |
   v
ADOPTION_CONFIRMED
   |
   v
OLD_REVOKED
   |
   v
COMPLETE
```

Error states:

```text
PROVISIONING_FAILED
VAULT_PUBLISH_FAILED
CANARY_FAILED
ROLLOUT_TIMEOUT
REVOKE_FAILED
RECONCILIATION_REQUIRED
```

Store **operationId**, secret name, provider resource ID, old/new version IDs, policy version, timestamps, attempt count, approvals, and check results in a **controlled state store**. **Never store raw secret values** in workflow records, logs, or Event Grid payloads.

### Why Not Just a Single Stateless Function?

If a Function creates upstream credential B but times out **before publishing B to Key Vault**, a retry must not endlessly generate new credentials. State/idempotency and source reconciliation are mandatory.

## 22. Idempotency and Concurrency in Rotation

Suppose two triggers arrive:

```text
09:00 SecretNearExpiry event
09:01 Daily schedule sees same expiry
09:02 Event Grid retries old event
```

If all three run independently, they could create B, C, and D and publish three new versions, causing consumers to pick up unexpected credentials.

Design approach:

1. A **rotation operation key** such as `vault+secret+policyCycleId`.
2. Locking/leasing or optimistic concurrency in the state store.
3. Each operation records explicit state and created version IDs.
4. Duplicate event → look up the existing operation and resume the remaining step rather than creating a new key.
5. Pass an idempotency token to the upstream API if supported.
6. If unsupported, reconcile previously created credentials before retrying.
7. Never publish a new version while a prior rotation remains unverified, except for an approved emergency.
8. Limit concurrent rotations for the same secret.
9. Record audit/version IDs instead of confidential values.
10. Alert if a workflow remains stuck in a state beyond SLA.

**Event Grid event delivery is not a distributed transaction.** Design the workflow to remain safe if the process crashes between any two steps.

## 23. Timing When to Publish to Key Vault

A dual-key workflow should:

1. Request creation of B upstream.
2. Wait for upstream confirmation that B is active.
3. Test B with a **low-privilege, side-effect-free** probe in an approved environment.
4. Publish B to Key Vault under the **same secret name** to create a new version.
5. Record the new version ID (not the value).
6. Canary rollout to a limited consumer subset.
7. Confirm B works with zero business errors.
8. Roll out to all consumers.
9. Only after sufficient adoption → revoke A.

**Publishing a new version to a versionless path before testing** can cause auto-refreshing consumers to adopt an unready credential. Publish timing and canarying must be designed around each client's refresh semantics.

Another technical option is a **staging secret name** to test B separately, then publishing to the production secret name after approval. However, never leave staging credentials active indefinitely or duplicate values longer than necessary.

## 24. Consumer Adoption: When Is It Safe to Revoke the Old Version?

Do not rely solely on a “deploy succeeded” message. Measure:

- How many instances/pods/VMs have picked up version B?
- Are background workers/cron jobs still starting with A?
- Have connection pools reconnected/authenticated using B?
- Are applications seeing 401/403 or authentication errors post-refresh?
- Does the provider expose metrics by active credential ID/key ID?
- Have weekly or infrequent batch jobs been tested?
- Is there an un-reloaded DR site or standby environment?
- Are there long-lived offline edge clients needing extra transition time?

**Never log raw credentials.** If the provider returns a non-sensitive **credential ID/key ID**, track adoption by that identifier. Otherwise, emit a non-sensitive application-level version marker/telemetry—never log a secret hash that could be abused as a verifier.

### Cutover Gate

```text
Revoke A only if:
  B validated at upstream
  AND all required consumer classes updated
  AND auth failures within SLO
  AND rollback/forward plan approved
  AND overlap deadline not exceeded
```

On a compromise alert, the gate must prioritize containment over maintaining a routine overlap window.

## 25. Caching and Refresh in Applications

How consumers read secrets:

| Approach | Behavior | Action needed on rotation |
|---|---|---|
| **SDK getSecret per use** | Fetches per API and version selection; increases calls/latency. | Handle throttling and ensure values are never printed. |
| **SDK read at startup** | Value stays in memory until restart/reload. | Actively refresh/restart/roll out. |
| **App cache with TTL** | Copy stays alive until next refresh. | Bound max cache age and handle refresh failures. |
| **Environment variable** | Value is typically fixed in the process. | Restart/redeploy or use a supported platform refresh mechanism. |
| **App Service Key Vault reference** | Platform resolves and caches per its own semantics. | Verify refresh cycle/triggers; test empirically. |
| **AKS Secrets Store CSI** | Driver/provider mounts data with optional rotation/sync. | Configure refresh; understand container env vars do not auto-update. |
| **Spring Boot Key Vault property source** | May load at startup/refresh depending on library line. | Verify version and bean rebind behavior. |

**A versionless identifier does not mean instant refresh.** There is always a **data flow from vault to consumer**; if any link retains the value in memory, the new version is not yet in use.

### How Should Cache Refresh Failures Be Handled?

- Never retain old credentials indefinitely without observability.
- On transient errors, cached credentials may be used for an approved grace period **only if still valid and risk is acceptable**.
- When a credential is compromised/revoked, never fall back to cache.
- Implement circuit breakers, bounded retries, backoff, and alerts on refresh failures.
- Define an appropriate max-staleness policy per secret.

## 26. App Service Key Vault References

Azure App Service/Functions can use **Key Vault references** in application settings where supported:

```text
@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential)
```

This is a **versionless reference**, letting the platform fetch the secret by name using App Service's refresh mechanism.

A version-pinned reference:

```text
@Microsoft.KeyVault(SecretUri=https://kv-orders-prod.vault.azure.net/secrets/partner-api-credential/<version-id>)
```

### Risks During Rotation

- Versionless refs may be **cached**; never assume instant switch to B after `setSecret`.
- Version-pinned refs **do not switch** to B until the reference/deployment is updated.
- Verify the platform's settings refresh behavior, including supported ways to force refresh/restart per current docs.
- App Service's managed identity needs read access to the right vault and a valid network path.
- App settings can become process environment variables, so **application code must still protect sensitive data lifecycle**.
- Changing references may trigger restarts/redeploys depending on the operation; evaluate downtime impact.

**Do not apply a single fixed refresh interval to all Azure hosting services.** App Service, Functions, Container Apps, and different versions have different semantics.

## 27. AKS Secrets Store CSI and Secret Rotation

An AKS workload can use the **Secrets Store CSI Driver with the Azure Key Vault provider** to mount secrets/certificates/keys per configuration and supported capabilities.

```text
Azure Key Vault
     |
     v
Azure Key Vault Provider for Secrets Store CSI
     |
     v
Pod mounted file
     |
     v
Application reads credential file / refreshes
```

Key points:

1. Configure identity/workload identity or a supported authentication method.
2. CSI/provider rotation refresh must be enabled and configured per cluster/version.
3. **Updating a mounted file** does not guarantee a Java singleton re-reads the file automatically.
4. If synced into a Kubernetes Secret, Kubernetes and application refresh rules differ from direct mounts.
5. Kubernetes **env vars are injected at container start**; updating a Secret does not change env vars inside a running process.
6. Offline pods or driver errors can leave stale copies behind.
7. Verify per application deployment and namespace.
8. Secret data in Kubernetes Secrets must be protected via RBAC, encryption at rest, and secure operations.

**Never let a Pod keep using version A after A is revoked just because CSI updated the file**; the application must have reload logic or undergo rollout to consume the new data.

## 28. Spring Boot/Java: Reading Secrets via Azure SDK

For Java applications, use `azure-security-keyvault-secrets` with `azure-identity`. Maven projects can manage versions via an approved BOM.

```xml
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-security-keyvault-secrets</artifactId>
        <version>REPLACE_WITH_APPROVED_SDK_VERSION</version>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
        <version>REPLACE_WITH_APPROVED_IDENTITY_VERSION</version>
    </dependency>
</dependencies>
```

**Do not pick two arbitrary versions.** In real projects, use the **Azure SDK BOM** or compatible Spring Cloud Azure BOM per approved policies.

Basic Java client:

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;

public final class SecretReader {
    public static void main(String[] args) {
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (vaultUrl == null || vaultUrl.isBlank()) {
            throw new IllegalArgumentException("KEY_VAULT_URL is required");
        }

        SecretClient client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        KeyVaultSecret current = client.getSecret("partner-api-credential");
        System.out.println("Current version: "
            + current.getProperties().getVersion());

        // NEVER log current.getValue().
        // Keep value lifetime short; do not store in an unbounded static field.
    }
}
```

The `getSecret` call in this example **actually loads the secret value into memory** if executed; run it only against a lab vault with data-plane permissions. The print statement outputs only the **version ID**, not the value.

## 29. Java: Listing Version Metadata

An inventory task does not need to fetch or print secret values:

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.SecretProperties;

public final class VersionInventory {
    public static void main(String[] args) {
        SecretClient client = new SecretClientBuilder()
            .vaultUrl(System.getenv("KEY_VAULT_URL"))
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        for (SecretProperties p :
             client.listPropertiesOfSecretVersions("partner-api-credential")) {

            System.out.printf(
                "version=%s enabled=%s expires=%s%n",
                p.getVersion(),
                p.isEnabled(),
                p.getExpiresOn()
            );
        }
    }
}
```

This is **metadata-only listing** via the SDK interface. Data-plane roles for listing properties can differ from roles for reading values, depending on role definitions and vault permission model. Even without printing values, **metadata should not be made public** if policy restricts exposing resource/credential names.

### Do Not Use getSecret in Inventory Jobs That Do Not Need Values

An inventory job that only checks expiry/versions **should not fetch every secret value**. Minimize privileges and data exposure by listing properties/attributes instead.

## 30. Java: Publishing a New Version in Lab

Simple Java example **for approved lab environments only**:

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;
import com.azure.security.keyvault.secrets.models.KeyVaultSecret;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public final class LabCreateSecretVersion {
    public static void main(String[] args) {
        String value = System.getenv("LAB_NEW_SECRET_VALUE");
        String vaultUrl = System.getenv("KEY_VAULT_URL");
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Lab value must be set");
        }

        SecretClient client = new SecretClientBuilder()
            .vaultUrl(vaultUrl)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        KeyVaultSecret candidate = new KeyVaultSecret(
            "partner-api-credential-lab",
            value
        );
        candidate.getProperties().setExpiresOn(
            OffsetDateTime.now(ZoneOffset.UTC).plusDays(45)
        );

        KeyVaultSecret created = client.setSecret(candidate);

        // Log ONLY version ID and tracking code, NEVER log value.
        System.out.println("New version: "
            + created.getProperties().getVersion());
    }
}
```

**Warnings:**

- This example **only stores value B in the vault**; it does not create a valid credential at the API provider.
- Real environments must not expose secrets in shell history, crash dumps, or long-lived environment variables. Passing via env is solely to illustrate the SDK interface; a Production rotation worker should obtain values securely from an approved source/transport and minimize memory lifetime.
- Scope `set secret` properly and restrict who can publish versions.
- Before running, confirm the vault URL points to a **lab vault**, not Production.
- Running it again creates a **new version**, so real workflows need idempotency/operation state.
- Never call `System.out.println(value)` or serialize `KeyVaultSecret` directly.

## 31. Azure CLI: Safely Inspecting Metadata

The following commands **read metadata only** when using proper `--query` filters and not redirecting raw responses containing values to logs.

```bash
# Replace with VAULT and SECRET from an authorized environment.
VAULT="kv-orders-lab"
SECRET="partner-api-credential-lab"

az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

# List names and attributes; does not request printing values.
az keyvault secret list \
  --vault-name "$VAULT" \
  --query "[].{name:name,enabled:attributes.enabled,expires:attributes.expires}" \
  --output table

# List versions and expiry; restrict output to metadata.
az keyvault secret list-versions \
  --vault-name "$VAULT" \
  --name "$SECRET" \
  --query "[].{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  --output table
```

**Do not use** `az keyvault secret show` with default output when you only want to inspect versions: the command can return the `value` field. If you need it for an attribute, lock down `--query` to metadata fields only and never paste the full response into terminal logs.

### Inspect a Specific Version

```bash
az keyvault secret show \
  --vault-name "$VAULT" \
  --name "$SECRET" \
  --version "REPLACE_WITH_VERSION_ID" \
  --query "{id:id,enabled:attributes.enabled,expires:attributes.expires}" \
  --output json
```

This is a metadata-only query, **but** the `show/get` operation may still require full data-plane read permission. For lower-privilege inventory jobs, prefer property-listing APIs.

## 32. Azure CLI: Creating Versions and Updating Attributes in Lab Only

Conceptual syntax:

```text
az keyvault secret set
  --vault-name <LAB_VAULT>
  --name <LAB_SECRET>
  --value <SENSITIVE_VALUE>
  --expires <UTC_DATE>

az keyvault secret set-attributes
  --vault-name <LAB_VAULT>
  --name <LAB_SECRET>
  --version <VERSION_ID>
  --enabled {true|false}
  --expires <UTC_DATE>
```

This is a **command schema**, not a copy-paste run block. Never type raw credentials after `--value` in a shell with command history or process logging. In labs, use **dummy values** and non-logged secret input/delivery methods; in Production, use automation SDKs and trusted credential transport.

**Remember:**

- `set secret` creates a new version.
- `set-attributes` modifies metadata of the specified version.
- `--enabled false` does not revoke credential copies already distributed outside the vault.
- Updating a version's expiry does not rotate the password upstream.
- Never run test examples against real secrets that could affect production apps.

## 33. Tags and Metadata for Rotation Governance

Example metadata:

```json
{
  "owner": "payments-platform",
  "environment": "production",
  "rotationPolicy": "external-api-dualkey-v2",
  "upstreamSystem": "partner-api",
  "changeTicket": "CHG-EXAMPLE-2026",
  "criticality": "high"
}
```

This metadata can be attached in tags/registries per policy; **do not treat it as a fixed Key Vault schema**.

An internal registry should track:

- System owner and escalation contact.
- Secret name/vault/tenant/environment.
- Upstream credential identifier, never the raw value.
- Last/next rotation windows.
- Actual upstream expiry.
- Required consumer classes and refresh SLAs.
- Revocation confirmation.
- Last success/failure and incident references.

**Do not put all sensitive metadata into tags** if many users can list vault properties. Decide which fields belong in Key Vault vs. a separate access-controlled state store.

## 34. Permissions: Consumer and Rotation Worker Are Two Distinct Roles

| Principal | Need | Should not be granted |
|---|---|---|
| **Application runtime** | `get secret value` for the right vault/scope. | Create/delete/purge secrets or assign roles. |
| **Rotation worker** | Create new versions, read metadata/set expiry, optionally disable old versions per policy. | Subscription-wide admin rights if unneeded. |
| **Security operator** | Audit, review policies, trigger emergency rotation. | Secret values when only metadata monitoring is needed. |
| **Platform engineer** | Manage vault/networking/IaC. | Default access to all secret values if unneeded. |
| **Incident responder** | Revoke, investigate, access under break-glass policy. | Standing unaudited privileges. |

Common Azure RBAC roles:

- **Key Vault Secrets User**: reads secret contents within the authorized scope.
- **Key Vault Secrets Officer**: manages secrets per role definition; verify scope.
- **Key Vault Reader**: reads metadata/control-plane info; not for viewing secret values by default.

**Never infer permissions solely from a role name**: a vault can use **Azure RBAC** or **access policy permission model** depending on configuration and vault type. Verify the exact model, scope, built-in role definitions, and approval workflow.

### Vault-per-Boundary

For large systems, consider separating vaults by **environment/application/tenant/trust boundary**. Avoid dumping every secret into one vault and granting a broad role to all apps just for convenience.

## 35. Managed Identity Before Static Secrets

Prioritize conditionally in this order:

1. **Managed identity/workload identity** to call Azure resources supporting Entra authentication.
2. **Federated identity** instead of client secrets in CI/CD or external workloads where supported.
3. **Short-lived tokens** issued with the right audience/scope instead of long-lived shared secrets.
4. If a partner service mandates a static credential, store it in Key Vault with a rotation workflow.
5. For legacy passwords, plan a migration to modern identity/role models when feasible.

```text
Spring Boot on Azure
    |
    +-- To Blob Storage:
    |      managed identity + Azure RBAC
    |
    +-- To third-party API:
           Key Vault secret + external rotation workflow
```

**Do not create and rotate a secret if you can eliminate the need to hold it at all.** That is a more fundamental risk reduction than rotating keys every week.

## 36. Networking, TLS, and Data Residency

A consumer with the right version still cannot read Key Vault if:

- The vault firewall blocks the outbound IP/subnet.
- The Private Endpoint is misconfigured.
- The Private DNS zone is not linked to the VNet or resolution is wrong.
- App Service/Container Apps/AKS lacks a network route.
- Token audience/tenant/RBAC is wrong.
- TLS certificate validation is misconfigured.
- Outbound proxy blocks the Entra token endpoint.
- The vault is restricted or accessed across a different cloud environment.
- The Event Grid endpoint/Function lacks valid networking/identity.

### Principles

- Use HTTPS/TLS; never disable hostname verification to debug.
- Verify private access and DNS **from the actual runtime**.
- Check network paths for **both the rotation worker and consumers**.
- Keep the vault, automation, and logs within approved data boundaries.
- Never embed secrets in diagnostic events via Event Grid.
- Never open public network access to fix a 403 before identifying the root cause.

**A Private Endpoint does not replace authorization.** An actor with network reachability to the vault still needs identity and data-plane permissions.

## 37. Soft Delete, Purge Protection, and Rotation Implications

**Soft delete** and **purge protection** are Key Vault lifecycle/deletion safeguards per current configuration.

- Soft delete provides recovery of deleted objects within the retention window.
- Purge protection prevents premature purging during the retention period when enabled.
- Conditions and retention durations must be verified per tenant/vault policy.
- Do not treat soft delete as a **historical backup of upstream credentials**.
- Do not treat deleting a secret as a required step of rotation.
- Never purge versions/secrets just to “tidy up” while consumers, forensics, or compliance obligations still exist.

### Why Rotation Must Not Mean Deletion

Deleting a secret name in the vault can break consumers using versionless URIs. Typically, **creating a new version, migrating, and revoking the old upstream credential** is the right path; old versions are retained/disabled or retired according to an approved retention policy.

**Revoking an upstream credential** and **soft-deleting in the vault** serve different goals.

## 38. Auditing, Metrics, and Alerting

Signals to observe:

| Signal | Question | Expected source |
|---|---|---|
| Secret near-expiry inventory | Which credentials are expiring soon? | Key Vault metadata + rotation registry. |
| Rotation overdue | Was a policy cycle missed? | Scheduler/state store. |
| New version created | Which actor/automation published it? | Key Vault events/diagnostic logs. |
| Unexpected version created | Did an actor outside the workflow create a secret? | Audit/change detection. |
| Consumer version adoption | Have all replicas switched to the new version? | Application metrics/version markers. |
| Upstream auth errors | Did 401/403s rise after cutover? | Consumer/provider metrics. |
| Vault get/permission errors | Are consumers failing to retrieve secrets? | Key Vault diagnostics + app logs. |
| Event Grid delivery failures | Is automation missing triggers? | Event Grid/Event handler monitoring. |
| Rotation workflow failures | Which step is stuck and for how long? | Durable state/alerts. |
| Secret access anomalies | Unusual/out-of-scope access? | Azure Monitor/SIEM per configuration. |
| Network errors | DNS/private endpoint/timeouts? | Client traces and network observability. |
| Cost | Calls/version growth/log ingestion. | Cost Management + service meters. |

**Do not assume all of these exist as identically named built-in Azure Monitor metrics**; many must be emitted by the rotation worker or application. Azure Activity Log covers control-plane auditing; data-plane diagnostic logging must be configured appropriately and must never log raw secrets.

## 39. Alert Policy: Do Not Wait for Expiry Events Alone

Example internal alert policy:

```text
30 days before upstream expiry:
  create ticket + schedule rotation (example policy)

14 days before:
  check rotation state and owner acknowledgement

7 days before:
  escalation to operations/security owner

At rotation:
  verify new version published + consumers adopted

After overlap:
  verify upstream old credential revoked

If any gate fails:
  page owner according to severity, do not mark COMPLETE
```

These 30/14/7-day thresholds are **illustrative**, not a Microsoft Key Vault guarantee. Some credentials last only a few hours, making those thresholds nonsensical; choose intervals suited to actual lifetimes.

### Event Plus Polling

```text
Key Vault Event Grid events ─┐
                            ├── Rotation state machine
Daily/periodic inventory ───┘         |
                                     v
                               Alerts + dashboard
```

Include a compensating schedule to catch delayed or dropped events. Store `nextRotationDueUtc` based on upstream validity and policy, not solely inferred from metadata sitting in the vault.

## 40. Cost: Rotation and Secret Reads Have a Price

A secret rotation system can incur:

- Key Vault secret operations (get/list/set/property updates) per meter.
- Azure Functions/Logic Apps and state store.
- Event Grid deliveries.
- Monitoring/Log Analytics ingestion and retention.
- Managed identity/RBAC administration overhead.
- Private Endpoint/egress/networking per billing policy.
- Retry storms when consumers fail credential auth.
- Engineering/on-call time for approvals and integration checks.
- Downtime and business loss if a rotation goes wrong.

**Do not call `getSecret` on every HTTP request** when a safe cache TTL meets requirements: high vault call rates increase latency, quota/throttling risk, and cost. Conversely, **never cache indefinitely** just to save a few requests at the expense of rotation capability.

### Example Call Volume

Suppose 100 pods each read one secret every 10 minutes:

```text
100 pods × 6 reads/hour = 600 reads/hour
600 × 24 = 14,400 reads/day
```

This is a **simplified estimate**, excluding retries, startups, multiple secrets, or SDK caching. Use actual workloads and current pricing to optimize intervals and architecture.

## 41. Runbook: Secret Expired, Application Fails Authentication

**Symptom:** many requests begin returning `401 Unauthorized` when calling the provider API.

### Investigation

1. Confirm whether the error comes from the **upstream provider** or a Key Vault get operation.
2. Capture requestId, UTC timestamp, secret name, and **non-sensitive version ID**.
3. Verify whether the upstream credential is still valid; do not look at Key Vault `expiresOn` alone.
4. Check whether consumers use versionless or pinned references.
5. Check adoption logs/metrics across all pods/VMs/jobs.
6. Check which state the rotation workflow reached.
7. Check whether an upstream credential B was issued but never published.
8. Verify Key Vault get/RBAC/networking are not separately failing.
9. Check app cache/restart/refresh mechanisms.
10. Never print secret values to debug.

### Remediation

- If B is valid upstream: publish/refresh/migrate consumers per runbook.
- If B does not exist yet: rotate at the provider via workflow/owner.
- If A was revoked: **do not try “re-reading version A” as a recovery step**.
- If workflow state is unclear: use operation state/idempotency to reconcile.
- Cap retries, limit blast radius, and verify end-to-end.
- Add tests/alerts against near-expiry and stale consumers.

## 42. Runbook: Key Vault Has a New Version, App Still Uses the Old One

**Symptom:** rotation worker wrote B successfully, but Pods/apps still authenticate with A.

### Checks

- Is a version-pinned URI used in App Service settings or config?
- Does Java/Spring Boot fetch the secret at startup and cache it?
- Has the AKS CSI file mount refreshed, and does the process re-read the file?
- Does a Kubernetes env var require a pod restart?
- Does the App Service Key Vault ref require a refresh/restart per actual behavior?
- Are multiple deployments/regions/DR sites sharing the same secret?
- Does upstream still allow A and B concurrently?
- Is another cache or config server holding a copy of A?
- Are old instances still waiting to drain/roll out?
- Have version metrics/markers updated?

### Remediation

1. Identify consumer classes and their pinning/caching behavior.
2. Trigger refresh/redeployment properly.
3. Canary-test B upstream.
4. Roll out across all consumers and verify adoption.
5. Only once conditions are met, revoke A.
6. Add “refresh verified” to the release checklist.

**Changing the secret value in the vault does not mean rotation is complete.**

## 43. Runbook: New Version Is Bad, Rollback Needed

**Symptom:** B was published, but provider API tests fail while A is still valid.

### Procedure

1. Halt B rollout and pause recurring automation.
2. Verify A **is still valid upstream**.
3. Point consumers back to A config/credentials via a verifiable method.
4. For versionless consumers, some setups may require **re-publishing A's value as a new version** via a trusted workflow; never assume versionless automatically reverts to old version A.
5. Avoid copying secret A into terminals or tickets during rollback.
6. If A was already revoked, **rollback to A is impossible**; roll forward with a corrected B or issue a new C.
7. Decide whether upstream credential B should be revoked after remediation.
8. Record audit logs and incident analysis.
9. Fix validation gates before the next rotation.

**Secret rollback is not simply changing a version ID number.** It depends on upstream validity and how consumers resolve and cache secrets.

## 44. Runbook: Rotation Worker Continuously Creates Versions

**Symptom:** dozens of new versions appear within minutes; worker logs show retries/timeouts.

### Possible Causes

- Event Grid redeliveries treated as independent commands.
- Scheduler and event trigger firing simultaneously.
- Missing distributed lock or idempotency key.
- Workflow timing out after upstream already created a credential.
- Worker failing to persist version ID/operation state.
- “New version created” trigger looping back into rotation logic.
- Secret name looping due to a misconfigured policy.

### Remediation

1. Pause the faulty trigger in a controlled manner.
2. Do not mass-delete versions with an unreviewed script.
3. Identify which version upstream accepts and which versions consumers use.
4. Reconcile created credentials at the provider and audit trail.
5. Add state store, idempotency, locking, and retry budgets.
6. Prevent event feedback loops using origin/correlation filters.
7. Restore active version strategy and consumer adoption.
8. Alert on unexpected new-version creation rates.
9. Run fault injection tests in lab before re-enabling.

## 45. Lab: Secret Rotation with Two Versions

**Context:** a lab vault and a mock API provider allowing two tokens A/B to be valid concurrently. Use **dummy values** or non-privileged test credentials. Never use a Production Key Vault.

### Resources

| Component | Role |
|---|---|
| `kv-orders-lab` | Vault holding secret versions. |
| `partner-api-credential-lab` | Stable logical name. |
| Mock provider | Accepts both A/B tokens during overlap. |
| Lab rotation worker | Stateful execution, never logs values. |
| Consumer A | Reads versionless. |
| Consumer B | Reads pinned version ID. |
| State store | Tracks operationId, old/new version, status. |
| Metrics | Counts requests/auth success and adoption. |

### Tasks

1. Diagram vault–provider–worker–consumers.
2. Identify how secret lifetime, expiry metadata, and cache TTL differ.
3. Define the A→B lifecycle with an overlap window.
4. Verify lab subscription, vault URL, and identity.
5. Create secret A **in lab only** via a trusted method, keeping the value out of Git/logs.
6. Attach a simulated `expiresOn` to version A.
7. List version metadata via CLI or SDK **without printing values**.
8. Have Consumer A query by secret name, and Consumer B pin version A.
9. Create credential B at the mock provider while keeping A valid.
10. Verify B authenticates against the mock provider.
11. Publish B as a new version in the vault.
12. Record the new version ID in the state store without recording the raw value.
13. Verify an un-refreshed Consumer A can still use A.
14. Verify version-pinned Consumer B does not automatically switch to B.
15. Refresh one canary instance to B and measure auth success.
16. Roll out/reload remaining consumers.
17. Confirm all required consumers use B before retiring A.
18. Revoke A in the mock provider.
19. Verify A no longer works even if a consumer retains a cached copy.
20. Test an Event Grid duplicate trigger; no unintended C may be created.
21. Simulate a Function crash after upstream creation and verify recovery/idempotency.
22. Test a vault 403 error and distinguish it from a provider 401.
23. Simulate an invalid version B in the mock environment; roll back while A is still valid.
24. Create an alert when a secret nears expiry with an incomplete workflow.
25. Write an emergency compromise runbook and test early revocation of A.
26. Estimate vault call volume and automation operating cost.
27. Clean up lab resources per procedure without purging shared vaults.

### Acceptance Criteria

- At least two versions exist under the **same secret name**.
- Metadata of each version is clearly distinguished.
- Evidence confirms B works upstream **before** full rollout.
- Versionless and pinned consumer behaviors are documented.
- Duplicate events do not create extra versions.
- Adoption verification, A revocation, and post-checks are completed.
- No raw secrets, access tokens, passwords, or connection strings appear in logs.
- Least-privilege RBAC/network policies are in place.
- Clear rollback or roll-forward plans exist.
- Lab YAML/config contains no production credentials.

## 46. Production Checklist Before Enabling Rotation

**Inventory and Policy**

- [ ] Every secret has an owner, environment, source system, and approver.
- [ ] Upstream expiry/validity is tracked independently of vault metadata.
- [ ] Policies define rotation interval, start deadline, and overlap/rollback windows.
- [ ] Emergency revocation and blast-radius plans exist.
- [ ] Evaluated whether static secrets can be replaced by managed identities.
- [ ] Shared credentials are not reused across multiple apps when separation is possible.

**Versions and Consumers**

- [ ] Versionless vs. pinned URIs are understood.
- [ ] Complete list of consumers, cron jobs, background workers, and DR sites exists.
- [ ] Refresh/restart/rollout procedures exist for each runtime.
- [ ] Upstream B is verified active before publishing/ramping up.
- [ ] Adoption verification gate precedes revoking A.
- [ ] Plans exist for rollback when A is valid and roll-forward when A is revoked.
- [ ] Secrets are not cached or kept in environment variables indefinitely.

**Automation and Safety**

- [ ] Worker has least-privilege managed identity/data-plane role.
- [ ] Event Grid + scheduled inventory together provide compensating alerts.
- [ ] Workflow maintains state, operationId, locking, and idempotency.
- [ ] Retry budgets/backoff/DLQ exist, preventing event feedback loops.
- [ ] Secret values never appear in events/logs/tickets.
- [ ] Rotation worker lacks unnecessary subscription-wide admin rights.
- [ ] Soft delete/purge protection and retention policies are reviewed.
- [ ] Networking/TLS/Private DNS are tested from both worker and consumers.

**Observability and Cost**

- [ ] Alerts exist for near-expiry, overdue rotation, and workflow failures.
- [ ] Provider 401/403s and Key Vault 401/403s are tracked separately.
- [ ] Audits cover new versions, role changes, and unexpected access.
- [ ] Adoption metrics use non-sensitive version markers.
- [ ] Fault injection/partial failure tests have been run in lab.
- [ ] Capacity/Key Vault operation limits and budget alerts are configured.
- [ ] Runbooks exist for expired/stale/compromised secrets with on-call owners.

## 47. Self-Check Questions

**Q1.** How do a secret name and a version ID differ?

**Answer:** The name is the secret's logical identifier; the version ID identifies a specific published value under that name.

**Q2.** Does calling `setSecret` on the same name with a new value overwrite the old version's value in place?

**Answer:** No. It creates a new version per Key Vault Secrets semantics.

**Q3.** Does a versionless URI mean every consumer immediately uses the new version?

**Answer:** No. Consumers/platforms may cache or not re-read automatically, requiring refresh/restart/rollout and adoption verification.

**Q4.** Does a version-pinned URI update automatically when B is published?

**Answer:** No. It specifies an exact version and requires updating references/config during rotation.

**Q5.** Does `expiresOn` metadata automatically change the password at a partner system?

**Answer:** No. A rotation workflow must create the credential upstream and update consumers.

**Q6.** Does `enabled=false` on an old version guarantee credential A is revoked at the provider?

**Answer:** No. It affects vault state; the provider must revoke the actual credential separately.

**Q7.** Does `notBefore` mean applications are ready to cut over at that timestamp?

**Answer:** No. It is a version time attribute; consumer readiness must be measured independently.

**Q8.** Why track both upstream expiry and Key Vault expiry?

**Answer:** The two systems can have different expirations; a credential may stop working before or after the vault metadata timestamp.

**Q9.** What is the benefit of dual-key rotation?

**Answer:** It allows A and B to remain valid concurrently for canarying, rolling out, and rolling back with minimal downtime when the provider supports it.

**Q10.** Should A be revoked immediately after B is published?

**Answer:** Not during routine rotation; verify consumers have adopted B first, except during emergency containment.

**Q11.** If upstream allows only one active password, is zero-downtime guaranteed?

**Answer:** No. You need alternate accounts, controlled cutover, a maintenance window, or specialized synchronization.

**Q12.** Why shouldn't Event Grid near-expiry be the sole trigger?

**Answer:** Metadata, events, or routes can be missing or workers can fail; scheduled inventory reconciliation is needed as a backstop.

**Q13.** What failure can Event Grid duplicate deliveries cause?

**Answer:** Multiple rotation workers creating multiple credentials/versions if idempotency is missing.

**Q14.** Should workflow state store raw secret values?

**Answer:** No. Store only operationId, version IDs, status, timestamps, and audit metadata.

**Q15.** What should a worker that timed out after creating upstream B do on retry?

**Answer:** Reconcile existing state/idempotency instead of unconditionally creating credential C.

**Q16.** Does a versionless App Service Key Vault reference mean instant refresh?

**Answer:** No. You must account for the platform's cache/refresh/restart semantics.

**Q17.** Once AKS CSI updates a mounted file, does the Java process automatically use the new value?

**Answer:** No. The app needs appropriate re-read/reload/rollout logic.

**Q18.** Do Kubernetes env vars populated from an updated Secret automatically change in a running process?

**Answer:** No. Typically a restart/redeploy is required for processes to pick up new values.

**Q19.** Does the Key Vault Reader role grant reading raw secret values by default?

**Answer:** No. An appropriate data-plane role/permission for reading secret values is required.

**Q20.** Why separate consumer and rotation worker identities?

**Answer:** Consumers typically only need read access; workers need publish/update rights, reducing blast radius if an app is compromised.

**Q21.** How can managed identities reduce secret rotation workload?

**Answer:** By eliminating the need to store static credentials for Azure services supporting identity-based access.

**Q22.** Do soft delete and purge protection revoke passwords upstream?

**Answer:** No. They govern deletion/recovery lifecycles inside Key Vault.

**Q23.** If an app receives 401 from the provider, is it necessarily a Key Vault 403?

**Answer:** No. A provider 401 can stem from an expired/revoked credential, while a vault 403 relates to data-plane permissions; separate the failure sources.

**Q24.** When B fails and A has already been revoked, can you roll back by reading version A?

**Answer:** No. You must roll forward to a valid credential or restore A upstream if the provider permits it under policy.

**Q25.** Why shouldn't an entire `KeyVaultSecret` object be logged?

**Answer:** It can contain the secret value and sensitive metadata, leaking them into logs.

**Q26.** Why avoid calling `getSecret` on every HTTP request when unnecessary?

**Answer:** It increases latency, operation quotas, and cost; cache with a risk-appropriate TTL/refresh instead.

**Q27.** Why shouldn't tags contain secret values?

**Answer:** Tags are metadata that can be listed/logged under broader permissions and are not meant for confidential secrets.

**Q28.** How does emergency rotation differ from scheduled rotation?

**Answer:** During a leak, containment/revocation takes priority, accepting shorter overlap or controlled downtime.

**Q29.** What are the completion criteria for a rotation?

**Answer:** The new credential is valid upstream, consumers have switched, the old credential is revoked per policy, metrics/alerts are healthy, and auditing is complete.

**Q30.** What is the single most important principle?

**Answer:** **A new secret version in Key Vault does not mean the credential has been safely rotated**; you must jointly manage upstream validity, versioning, consumer refresh, cutover, revocation, rollback, and observability.

## 48. Glossary and Execution Notes

| Term | Brief explanation |
|---|---|
| **Secret version** | A distinct value published under a secret name. |
| **Versionless URI** | Secret identifier omitting a specific version. |
| **Pinned version** | Consumer explicitly selects a specific version ID. |
| **expiresOn** | Expiration timestamp metadata of a secret version. |
| **notBefore** | Effective-from timestamp metadata. |
| **enabled** | Attribute enabling/disabling a version per Key Vault semantics. |
| **Upstream provider** | The system that actually validates the credential. |
| **Rotation policy** | Rules governing when and how credentials are replaced. |
| **Overlap/grace window** | Period where both A and B are valid for migration. |
| **Adoption** | Evidence that consumers have started using B. |
| **Revocation** | Invalidating a credential where it is authenticated. |
| **Idempotency** | Retrying an operation does not produce duplicate side effects. |
| **Reconciliation** | Comparing vault, provider, and consumers to detect drift. |
| **Emergency rotation** | Rapid rotation responding to suspected compromise. |
| **Soft delete** | Mechanism preserving recoverability after deletion per policy. |
| **Purge protection** | Protection against premature purging before retention expires. |

**In summary:** Managing **secret versions, expiration, and rotation strategies** in Azure Key Vault requires far more than creating a new version or setting `expiresOn`. You must understand **versionless vs. pinned access**, the two independent lifecycles of **vault metadata and upstream credentials**, how consumers **cache/refresh**, and implement **stateful, idempotent rotation with canarying, adoption verification, revocation, and rollback**. With Azure Event Grid/Functions, managed identities, RBAC, Private Endpoints, auditing, and alerts, organizations can mitigate expired or leaked credentials without causing unnecessary outages. **The final step of rotation is not “set secret succeeded”, but “all consumers are using the new valid credential, the old one is retired per policy, and the system continues operating securely”.**
