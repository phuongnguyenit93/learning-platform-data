# Compromised Key Revocation, Emergency Recovery, and Key Access Auditing

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, signing keys are among the most critical security assets. When a private key used to sign JWTs is leaked or used by an unauthorized actor, an attacker can mint forged tokens bearing arbitrary issuer, subject, audience, scope, and expiration within any Resource Server that trusts the corresponding public key.

This incident differs from a public JWK appearing on the JWKS endpoint. **Publishing the public key is normal behavior**: Resource Servers need it to verify signatures. Risk arises when the private key is exposed, signing permissions are hijacked, or an unauthorized system can ask an HSM/KMS to sign arbitrary data.

Running example: Authorization Server <code>https://auth.example.com</code> signs access tokens with an RSA key having <code>kid=as-signing-k1</code>. The Orders API and Billing API fetch public key K1 from JWKS and verify JWTs offline. An alert indicates an unexpected operational account invoked a signing operation using K1, or a private JWK was discovered in a public artifact. Operations must isolate the key, switch to key K2, update Resource Servers, assess issued tokens, and preserve evidence for investigation.

After this lesson, you will be able to:

1. Distinguish public key disclosure from private key or signing-permission compromise.
2. Recognize indicators of key compromise from KMS/HSM, applications, JWKS, and token issuance.
3. Execute a response workflow: containment, generating a new key, switching the signer, blocking the old key, and restoring service.
4. Understand why removing a JWK from JWKS does not immediately invalidate JWTs when Resource Servers have cached the public key.
5. Design ways to revoke tokens signed by a compromised key, including key denylists, introspection, token-ID denylists, and TTL limits.
6. Ensure database/backup restores never accidentally reactivate a revoked key.
7. Audit private key access, signing permissions, key administration permissions, and rotation actions.
8. Integrate workflows with Spring Authorization Server, Spring Resource Server, KMS/HSM, and monitoring systems.
9. Test emergency rotation, cache invalidation, key revocation, and audit trails.

**Version scope:** Examples use APIs commonly found in Spring Security 6.x and Spring Authorization Server 1.x on the Servlet stack. Newer Spring Security releases integrating Authorization Server may change packages or configuration styles. Interfaces like <code>CompromisedKeyRegistry</code> in this lesson are application-implemented abstractions, not built-in Spring APIs.

## 2. Classifying Key Incidents

Before revoking, determine exactly what was exposed or abused. A "key exposed" alert might just be normal access to a public JWK, or it could be a stolen private key.

| Scenario | Meaning | Response level |
| --- | --- | --- |
| Public JWK appears on JWKS endpoint | Expected behavior; public keys are published to verify signatures. | Not an incident merely because the public key was fetched. |
| Private JWK/PEM/keystore committed to Git or artifact | Anyone with a copy can sign tokens outside the Authorization Server. | Treat as compromise; revoke private key and evaluate tokens. |
| KMS/HSM reports signing operations from an unknown principal or workload | Signing capability may be hijacked even if private material is non-exportable. | Treat as critical incident; lock signing permissions, investigate identity and request scope. |
| Admin account can export or alter key policies without authorization | Key governance boundary is broken. | Revoke permissions, inspect key material, and audit the control plane. |
| One node uses a different key from the published JWKS | Deployment error, split-brain, or sign of key injection. | Stop node from issuing tokens; check deployment and key inventory. |
| KMS/HSM outage without signs of key exposure | Availability issue; insufficient evidence to conclude compromise. | Activate contingency procedure; never downgrade to weak keys. |
| Stale public JWKS cache | Resource Server has not received the new key or revocation status. | Fix cache/distribution; does not necessarily mean private key exposure. |

### 2.1. Private Key Compromise vs. Signing Oracle

Two attack classes must be distinguished:

- **Key material compromise:** the attacker obtains the private key and can sign tokens outside the Authorization Server.
- **Signing capability compromise:** the attacker has not extracted the private key, yet compromised an account/application authorized to call KMS/HSM signing. The attacker can still request arbitrary JWT signatures if the signing API does not constrain payloads or callers are insufficiently bound.

Thus, keeping a non-exportable private key in an HSM is a strong control, yet **insufficient** if any workload can invoke <code>Sign</code> on arbitrary data. You must control key usage permissions, workload identities, signing policies, and operation auditing.

### 2.2. Which Keys Are Affected?

Do not lump all credentials into a single "signing key" bucket. A system may maintain:

- JWT access token signing keys.
- OIDC ID Token signing keys.
- Request object or client assertion signing keys.
- JWE encryption keys.
- HTTPS TLS keys.
- Client authentication keys (e.g., an OAuth client's private key).
- Data encryption / KMS master keys protecting databases or backups.

An incident involving one key type does not automatically mean every other key type is exposed. However, if a shared KMS role, secret store, or host was compromised, assess the broader blast radius rather than rotating just one JWK.

## 3. What Damage Can JWTs Signed with a Compromised Private Key Cause?

Suppose a Resource Server trusts issuer <code>https://auth.example.com</code> and public key K1. If an attacker possesses private K1, they can mint a new JWT:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "administrator",
  "aud": ["https://orders-api.example.com"],
  "iat": 1794800000,
  "exp": 1794803600,
  "scope": "orders.read orders.write orders.admin",
  "client_id": "orders-web"
}
~~~

This is an illustrative payload, not a real token. The forged signature is cryptographically valid because the attacker used the real private key. If the Resource Server checks only signatures and basic claims without additional revocation state, it may accept the forged token.

Consequences may include:

1. Impersonating users or service principals.
2. Self-granting scopes broader than ever consented.
3. Targeting another API via audience if that API trusts the same issuer/key.
4. Minting tokens with lifetimes exceeding real policy.
5. Forging ID Tokens for OIDC clients if the same key signs ID Tokens.
6. Minting forged tokens even after the Authorization Server switches to a new key, as long as Resource Servers still trust the old public key.

**A valid signature does not prove a token was genuinely issued by the Authorization Server.** A signature only proves the data was signed by someone holding the corresponding private key. Once a private key is compromised, trust in that key must be revoked.

### 3.1. Impact Extends Beyond Previously Issued Tokens

In a key compromise, an attacker can keep signing **brand-new tokens** for as long as Resource Servers accept the old key. Therefore, merely querying and revoking legitimate tokens stored in the Authorization Server's database is insufficient: attacker-forged tokens have no record in <code>OAuth2AuthorizationService</code>.

This is why you need a mechanism to **reject all tokens bearing the compromised kid** at Resource Servers, in addition to revoking legitimate issued authorizations/tokens as needed.

## 4. Two Different Workflows: Normal Rotation vs. Emergency Revocation

Scheduled rotation and key-compromise response have different goals:

| Criterion | Normal rotation | Emergency revocation |
| --- | --- | --- |
| Status of old key | Still trusted; only stops signing new tokens. | No longer trusted. |
| Old public key in JWKS | Typically retained until old tokens expire. | Removed from JWKS while deploying kid blocking at Resource Servers. |
| Old tokens | Continue verifying within validity window. | Rejected per incident policy even if unexpired. |
| Goal | Zero-disruption transition. | Stop attackers from minting accepted tokens. |
| User impact | Usually no re-login required. | May force new token issuance or re-authentication. |

Do not apply standard rotation verbatim to a compromised key. Keeping the old public key solely so unexpired JWTs continue working lets attackers keep using the leaked private key to sign new accepted tokens.

## 5. Emergency Response Workflow

### 5.1. Response Phases

~~~mermaid
flowchart TD
    A["Detect suspected key compromise"] --> B["Activate incident and identify kid/key version"]
    B --> C["Containment: block signing permissions and isolate workload/account"]
    C --> D["Generate new key K2 in KMS/HSM"]
    D --> E["Publish public K2 and switch Authorization Server to sign with K2"]
    E --> F["Distribute policy rejecting kid K1 to all Resource Servers"]
    F --> G["Remove public K1 from JWKS and refresh caches"]
    G --> H["Assess affected tokens/authorizations/sessions"]
    H --> I["Restore service, run end-to-end tests, and heighten monitoring"]
    I --> J["Preserve evidence, postmortem, and close incident"]
~~~

During a severe incident, several actions may run in parallel per runbook and infrastructure capabilities. Safe ordering must guarantee two things: **the Authorization Server stops signing with K1** and **Resource Servers stop trusting tokens signed with K1**. Swapping the signer alone without updating verifiers leaves the door open to forged tokens.

### 5.2. Phase 1 — Activate Incident and Scope Impact

As soon as credible indicators appear:

1. Open a security incident and designate an incident commander empowered to make decisions.
2. Identify affected <code>kid</code>, key version, algorithm, KMS/HSM resource, and issuer.
3. Record suspected start time, detection time, and last known normal key usage timestamp.
4. Identify workloads, service accounts, nodes, pipelines, administrators, and backup systems with key access.
5. Preserve audit logs, IAM change logs, signing request metadata, deployment artifacts, and relevant evidence.
6. Classify as suspected or confirmed compromise; whenever unauthorized token signing is plausible, treat the key as **untrusted** during verification.

Do not wipe logs, delete keys, or rebuild all hosts before preserving necessary evidence. However, evidence preservation must not delay containment while attackers can still sign tokens.

### 5.3. Phase 2 — Containment: Stop Signing Capability

Depending on where keys reside:

- **KMS:** disable the key version or revoke <code>Sign</code> permissions for the compromised principal/workload; inspect key policies, IAM bindings, grants, and related credentials.
- **HSM:** disable key usage or compromised sessions/roles; follow HSM operator/dual-control procedures.
- **Keystore/file:** isolate nodes, remove file read permissions, revoke secrets/passwords and workload credentials; do not assume deleting a file on one node suffices if copies exist.
- **Signing service:** shut down the abused signing endpoint, block anomalous callers, and route traffic to verified services.

Do not merely disable the key if the attacker still has permission to create a new key or modify key policies. Revoke compromised credentials/IAM roles, terminate sessions, and audit control-plane permissions.

### 5.4. Phase 3 — Generate a New Signing Key

Generate K2 in a KMS/HSM or protected key management workflow:

- Use a policy-approved algorithm and key size/curve.
- Assign a new, unique <code>kid</code>; never reuse K1's ID.
- Verify the public key matches the exact key version used for signing.
- Ensure the signer can use K2 only under least privilege.
- Record metadata, creation timestamp, owner, key version, algorithm, and approval record.
- Run signing/verification tests in a controlled environment before switching production.

Never copy private K1 into K2 or simply "rename the kid" of the same key material. Changing <code>kid</code> does not make a leaked private key safe again. K2 must be **brand-new key material**.

### 5.5. Phase 4 — Switch Authorization Server to K2

The Authorization Server must select private K2 to sign new tokens. In Spring Authorization Server, the signer is typically wired via <code>JWKSource&lt;SecurityContext&gt;</code>, <code>JwtEncoder</code>, and <code>JwtGenerator</code>. With a KMS/HSM, the signing adapter must point to the new key version, and the published public JWK must match that signing operation.

After switching:

- Verify new JWTs carry <code>kid=K2</code>.
- Verify new token signatures using public K2.
- Verify issuer, audience, scope, and expiration.
- Verify every Authorization Server instance shares the same signer/JWKSource state.
- Monitor logs to confirm no node still issues tokens with K1.

Do not edit a config file on a single node alone. Across a multi-instance cluster, use a controlled rollout/feature flag/config version to prevent split-brain between nodes signing K1 and nodes signing K2.

### 5.6. Phase 5 — Revoke Trust in K1 at Resource Servers

This is the step most commonly missed. Resource Servers may cache public K1 from JWKS. Even after the Authorization Server deletes K1 from JWKS, Resource Servers can still verify newly forged K1 tokens from stale caches.

Execute in parallel:

1. Add <code>kid=K1</code> to a **revoked keys list** checked by Resource Servers before accepting JWTs.
2. Distribute the policy to all API instances, gateways, batch workers, and services verifying JWTs.
3. Force JWKS cache refresh/invalidation per actual decoder/proxy mechanisms.
4. Remove public K1 from the JWKS endpoint so newly polling verifiers no longer receive it.
5. Verify with a test JWT signed by K1: all Resource Servers must reject it; valid K2-signed tokens must succeed.
6. Check that no verifier loads keys from a separate JWKS cache, local file, static config, or secondary unupdated source.

**Removing K1 from JWKS alone is insufficient for immediate revocation.** Removal only takes effect when verifiers refresh JWKS; it does not evict public keys already cached in processes or gateways.

### 5.7. Phase 6 — Assess and Handle Affected Tokens/Authorizations

Categorize:

- JWT access tokens signed with K1.
- OIDC ID Tokens signed with K1.
- Other JWTs (request objects, client assertions, or internal tokens) if sharing K1.
- Refresh tokens and opaque access tokens if tied to affected authorizations.
- Authorizations/consents/sessions linked to compromised clients, principals, or time windows.

When all K1-bearing tokens are rejected via a key denylist, previously issued legitimate K1 tokens are also rejected. This is an intentional effect of emergency revocation. Users/clients may need to obtain fresh K2-signed tokens or re-authorize.

Do not assume refresh tokens were also signed with K1: refresh tokens in Spring Authorization Server are typically opaque credentials persisted in the authorization store. However, if attackers also compromised the database, client secrets, refresh token store, or user sessions, the blast radius is broader and requires revoking those credentials too.

### 5.8. Phase 7 — Recovery, Monitoring, and Closing the Incident

Restore full traffic only when:

- No instance issues tokens with K1.
- Every Resource Server/gateway enforces K1 denial.
- JWKS/discovery returns accurate metadata with zero private material.
- End-to-end K2 signing and verification succeed.
- Clients have a path to obtain fresh tokens; APIs reject forged K1 tokens.
- Compromised IAM/KMS/HSM credentials have been revoked or rotated.
- Audit logs and evidence have been preserved.
- Assigned owners monitor post-incident metrics and heightened alerts.

## 6. Revoking JWTs Signed with a Compromised Key

### 6.1. Why Is Deleting the JWK Insufficient?

Self-contained JWTs can be verified offline. Resource Servers typically:

1. Fetch public keys from JWKS.
2. Cache public keys by <code>kid</code>/JWK Set URI.
3. Verify signatures and claims without querying the Authorization Server on every request.

Once public K1 is removed from JWKS, a Resource Server may still hold K1 in cache until cache expiration or manual refresh. Thus, K1-signed tokens can still be accepted during that window.

Even after caches refresh, a verifier configured with a static public key or pinned key may keep trusting K1. Inventory every single token verification point.

### 6.2. Revocation by kid

A fast-response approach is maintaining a list of compromised <code>(issuer, kid)</code> pairs. Resource Servers reject any JWT matching that pair, even when its cryptographic signature is valid.

Example abstraction:

~~~java
public interface CompromisedKeyRegistry {
    boolean isRevoked(String issuer, String keyId);
}
~~~

A production implementation should read state from a reliably distributed source with clear caching/invalidation and fail-safe behavior aligned with API risk if revocation state cannot be verified. Never use a local map updated only on one instance.

Illustrative validator for Spring Resource Server:

~~~java
OAuth2TokenValidator<Jwt> compromisedSigningKeyValidator(
        CompromisedKeyRegistry registry) {

    return jwt -> {
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String kid = jwt.getHeaders().get("kid");

        if (issuer != null && kid != null
                && registry.isRevoked(issuer, kid)) {
            OAuth2Error error = new OAuth2Error(
                OAuth2ErrorCodes.INVALID_TOKEN,
                "JWT signing key has been revoked",
                null);
            return OAuth2TokenValidatorResult.failure(error);
        }

        return OAuth2TokenValidatorResult.success();
    };
}
~~~

This is an example validator; combine it with default issuer, timestamp, and API audience validators. Register it on <code>JwtDecoder</code> after configuring the decoder from issuer/JWKS. Never replace default validators with a validator that checks only <code>kid</code>.

Example combining validators:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(issuer).build();

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> keyRevocation =
    compromisedSigningKeyValidator(compromisedKeyRegistry);

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(defaults, keyRevocation));
~~~

Builder APIs may vary across Spring Security versions; check your deployed version. If the app needs an API-specific audience validator, add it to the validator list. During an incident, ensure the denylist policy is loaded before opening traffic and propagated to **all** verifiers.

### 6.3. Kid Denylist vs. JTI Denylist

| Mechanism | Scope | When useful |
| --- | --- | --- |
| **Kid denylist** | Rejects all tokens signed by a compromised key. | Private signing key exposed or signing permission hijacked. |
| **JTI/token denylist** | Rejects individual tokens by <code>jti</code>. | Specific tokens leaked or selective revocation needed. |
| **Authorization/session revocation** | Revokes grants/authorizations of a principal or client. | User locked, consent revoked, or client compromised. |
| **Opaque token introspection** | Resource Server checks token status at Authorization Server. | Centralized state, rapid revocation needed, network dependency acceptable. |
| **Short access token TTL** | Bounds how long tokens remain useful. | Shrinks risk window, though not instant revocation. |

For a compromised signing key, a <code>jti</code> denylist alone is insufficient: attackers can forge new tokens with fresh <code>jti</code> values. **Blocking the kid** is much more direct because every token signed by that key is rejected.

### 6.4. Offline JWTs and Limits on Instant Revocation

There is no way to instantly revoke an offline-verified JWT if Resource Servers rely solely on signatures, claims, and cached public keys without checking centralized state. To achieve rapid response, at least one of these designs is required:

- A key revocation registry distributed to all verifiers and checked on every request.
- Opaque access tokens + introspection checking active/inactive status.
- JWTs with <code>jti</code> paired with a centralized/cached denylist updated urgently.
- Checking authorization/session version or account status against a policy service with bounded latency.
- Short access token TTLs to cap remaining exposure windows.

Each approach trades off latency, availability, load, cacheability, and network dependency. Never claim "JWTs are revoked instantly" if the system still permits verifiers to rely on stale key or status caches.

## 7. Integrating the Workflow with Spring Authorization Server

### 7.1. JWKSource and the Active Signing Key

Spring Authorization Server typically uses a <code>JWKSource&lt;SecurityContext&gt;</code> bean as the key source for the JWT encoder and the JWK Set endpoint. Demo apps may use <code>ImmutableJWKSet</code>, whereas production should read state from a controlled key manager/KMS adapter.

During normal rotation, `JWKSource` can provide:

- Active private K2 for signing.
- Public K1 solely for verifying old tokens.
- Public K2 so Resource Servers can fetch and prepare for verification.

During emergency revocation, K1 is no longer trusted. Remove K1 from the `JWKSource`/JWKS public view and ensure the signer can no longer select K1. If a key manager retains K1 for audit/forensics, that archival record must never permit production signing or verification.

### 7.2. Do Not Use the JWKS Endpoint as a Key Management Interface

The JWKS endpoint is an interface for **publishing public keys**. Never expose create, activate, disable, or delete key actions through a public endpoint lacking administrative authorization. Key management must go through a separate control plane with strong authentication, authorization, dual control, and auditing.

### 7.3. Verifying New JWTs Carry the Right kid

After changing the active key, issue a test token through a real grant and verify:

- Header <code>kid</code> is K2.
- <code>alg</code> is within the allowlist.
- The JWT verifies using public K2 fetched from JWKS.
- The JWT fails verification against an unrelated public key.
- Claims <code>iss</code>, <code>aud</code>, <code>exp</code>, and <code>scope</code> remain accurate.
- The Authorization Server logs neither private JWKs nor raw tokens.

Do not check only that a config file lists K2; verify tokens emitted by every deployed node.

### 7.4. Token Types That May Share a Signing Key

One key may sign JWT access tokens, ID Tokens, and other JWTs depending on configuration. On compromise, inventory by <code>kid</code> across the entire ecosystem:

- Access tokens across all Resource Servers.
- ID Tokens issued to OIDC clients.
- JWT assertions or request objects if sharing the key.
- Internal service-to-service JWTs.

Do not assume updating only the Orders API suffices. An OIDC client could still trust forged ID Tokens if its verifier continues accepting public K1.

## 8. Emergency Recovery and Protecting Backups

### 8.1. Recovery Must Not Reactivate Revoked Keys

A dangerous failure occurs when restoring an old database or secret backup: the snapshot may contain JWK K1 and its pre-incident active status. Restoring verbatim can make the Authorization Server resume signing with the compromised key or publish public K1 in JWKS.

Therefore, key revocation state requires storage and restore procedures guaranteed **not to roll back**:

- Store key status/revocation events in an audit/registry system whose versioning and retention are independent of primary database snapshots.
- Maintain the banned-kid list outside backups that could revert to pre-incident timestamps.
- During restore, reconcile key inventory against the incident ledger before enabling the signer or JWKS endpoint.
- Never auto-activate a key solely because a database row says <code>ACTIVE</code>.
- Run post-restore checks: signer uses only K2, JWKS excludes K1, and Resource Servers still reject K1.

### 8.2. Private Key Backups

Key backups may be required for disaster recovery, yet a backup copy has the same sensitivity as the original key. Ensure you:

- Encrypt backups with an independent protection key.
- Restrict create/read/restore permissions and require multi-party approval.
- Audit every export, backup, restore, and backup test.
- Store backups in an isolated administrative boundary and failure domain.
- Run restore drills in an isolated environment.
- After a compromise, mark every backup containing K1 as **compromised material**; never reuse it for signing.

If keys live in an HSM as non-exportable, vendor backup/restore flows differ; still audit clone/replication operations, backup domains, and operator permissions.

### 8.3. Restoring Issuer and Configuration

The issuer is normally a stable identifier for the Authorization Server; **do not change the issuer merely to handle a key compromise** without an extraordinary architectural reason. Changing the issuer breaks discovery, trust configurations, client registrations, and Resource Servers. Typically, keep the issuer, replace the key, revoke the old kid, and update verifiers.

Post-recovery configuration checks:

1. Issuer matches published metadata and the <code>iss</code> claim in new tokens.
2. JWK Set URI is stable, HTTPS, and belongs to the trusted issuer.
3. Active signing key is K2 across every node.
4. K1 remains marked revoked in the registry.
5. Backup/restore and autoscaling do not wipe revocation state.
6. KMS/HSM IAM has been reviewed with zero compromised principals remaining.

## 9. Auditing Key Access and Usage

### 9.1. Events to Record

Auditing must cover both the **data plane** (using keys to sign) and the **control plane** (key administration, IAM, policies, backups):

| Category | Events to audit | Investigation questions |
| --- | --- | --- |
| Key creation | Create/generate key, import, rotate, version creation | Who created the key, when, and in which project/account? |
| Key usage | Sign operations, decrypt if any, key version invoked | Which workload signed, at what frequency, and when? |
| Metadata access | Get public key, describe key, list versions | Who inspected the key and from where? |
| Administration | Enable/disable, schedule deletion, update key policy | Who could disable a key or alter permissions? |
| IAM | Grant/revoke roles, access key/token creation, service account impersonation | Was any new principal unexpectedly granted sign access? |
| Backup/restore | Export, backup, restore, clone/replicate | Were any key copies created or moved? |
| Application | Sign latency, KMS errors, kid used, node/instance | Which node signed tokens with which key? |
| JWKS | Public key set changes, cache refreshes, metadata publish | Which keys were published to Resource Servers? |

### 9.2. Useful Audit Fields

An audit event might contain:

~~~json
{
  "event_type": "SIGN_OPERATION",
  "timestamp": "2026-11-16T09:30:00Z",
  "issuer": "https://auth.example.com",
  "key_id": "as-signing-k2",
  "key_version": "version-17",
  "principal": "service-account/authorization-server",
  "workload": "authorization-server-prod-03",
  "operation": "SIGN",
  "source": "kms",
  "request_id": "audit-correlation-123",
  "result": "SUCCESS"
}
~~~

This is an illustrative schema. Never put raw private keys, secrets, access tokens, refresh tokens, or payloads containing sensitive user data into audit logs. To correlate signing operations with token issuance, use request/correlation IDs and minimal metadata; logging full JWTs is unnecessary.

### 9.3. Protecting Audit Trails from Tampering

Audit logs are valuable for investigation only if attackers cannot easily alter or delete them after compromising an application. You should:

- Ship logs to a centralized system where write permissions are separated from delete permissions.
- Enable appropriate retention/immutability or write-once policies.
- Synchronize clocks across KMS/HSM, Authorization Server, gateways, and Resource Servers.
- Restrict who can query sensitive logs; audit log reads as well.
- Alert if the audit pipeline stops receiving events or shows unexpected gaps.
- Keep copies of control-plane and data-plane events in a separate failure domain.

### 9.4. Separation of Duties and Least Privilege

| Role | Least-privilege permissions |
| --- | --- |
| Runtime signer | Invoke signing with active key; cannot export private key or alter key policy. |
| JWKS publisher | Read public metadata and publish JWKS; zero signing permissions. |
| Key custodian | Manage lifecycle/rotation per approval; cannot arbitrarily grant broad access. |
| Security auditor | Read audit logs and key inventory; cannot sign or modify policies. |
| Resource Server | Read public JWKS; no access to private keys or KMS signing permissions. |
| Incident commander | Coordinate containment/recovery under controlled, audited emergency access. |

In smaller systems, one person may wear multiple hats, yet high-risk operations such as exporting, disabling, rotating, or destroying keys should require independent approval/dual control when criticality demands.

## 10. Detecting Anomalous Access

Do not audit only after an incident; configure proactive alerts. Useful signals include:

- Sudden spikes in signing operations relative to baseline.
- A principal that has never signed before invoking the key.
- Key calls originating from unexpected workloads, subnets, regions, or accounts.
- Signing calls occurring outside operational hours or during unrelated deployments.
- Key policy/IAM changes immediately preceding signing volume spikes.
- Old key versions continuing to sign after active-signer cutover.
- An instance issuing tokens with a <code>kid</code> absent from current inventory.
- JWKS responses changing outside deployment/rotation windows.
- Gaps in KMS/HSM audit logs or disabled log delivery.
- Unusual export/backup/restore actions on key material.

Alerts need defined severity, owners, runbooks, and escalation criteria. A single <code>GetPublicKey</code> call is not necessarily anomalous because public metadata is read frequently; conversely, a <code>Sign</code> call from a new principal requires immediate investigation.

## 11. Example Revoked-kid Enforcement in Spring Resource Server

### 11.1. Shared Registry

Define the contract:

~~~java
public interface CompromisedKeyRegistry {
    boolean isRevoked(String issuer, String kid);
}
~~~

A production implementation can use a distributed database/cache or a policy service supporting push invalidation. Include policy version/epoch, update timestamp, and health signals. If the registry is unreachable during an incident, deciding between fail-open and fail-closed must follow API risk; sensitive APIs usually require **failing closed or entering maintenance mode** until state can be verified.

### 11.2. Supplemental Validator

~~~java
OAuth2TokenValidator<Jwt> rejectCompromisedKid(
        CompromisedKeyRegistry registry) {

    return jwt -> {
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String kid = jwt.getHeaders().get("kid");

        if (issuer == null || kid == null) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(OAuth2ErrorCodes.INVALID_TOKEN));
        }

        if (registry.isRevoked(issuer, kid)) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    OAuth2ErrorCodes.INVALID_TOKEN,
                    "Signing key is revoked",
                    null));
        }

        return OAuth2TokenValidatorResult.success();
    };
}
~~~

This checks the key ID after the decoder parses/verifies the JWT per configuration. Combine this validator with default issuer and timestamp validators, plus the API's audience validator. Rejecting tokens missing <code>kid</code> is appropriate for JWT profiles requiring key identification; if your system has legitimate tokens without kid, define explicit compatibility rules.

**Never use this validator as a substitute for signature verification.** It is strictly an extra revocation-status layer; the decoder must still verify signatures using keys from a trusted issuer.

### 11.3. Distributing Revocation Updates

For the denylist to take effect cluster-wide:

1. Write the <code>issuer + kid + revokedAt + reason + incidentId</code> event to the authoritative registry.
2. Push invalidation events to Resource Servers/gateways.
3. Each instance updates its local cache and reports its active policy version.
4. Track the count/percentage of instances confirming policy adoption.
5. Re-open full traffic only after coverage meets thresholds and K1 test tokens fail across every region.
6. Re-verify during autoscaling or node restarts so policies load before accepting requests.

If a Resource Server cannot receive the updated policy, isolate that node or drain traffic elsewhere. Never equate "event published" with "every instance enforced it."

## 12. Sample Incident Response Runbook

The following runbook is a reference template. KMS/HSM tool names, roles, commands, and SLA timings must be replaced with your organization's actual setup.

| Stage/phase | Action | Completion evidence |
| --- | --- | --- |
| Detection | Open incident; identify suspected issuer, kid, and key version. | Incident ID, owner, timestamp, alert source. |
| Containment | Block compromised principal/workload and halt K1 signing. | KMS/HSM audit confirms sign permission disabled; zero K1 sign successes. |
| Recovery key | Create new K2; verify public key and signer. | Key inventory, approval, test signature. |
| Server rollout | Switch all Authorization Server instances to K2. | Fresh JWTs from every node carry kid K2. |
| Verifier block | Add K1 to revoked-kid registry and invalidate caches. | Resource Server tests reject K1 tokens in every region. |
| JWKS | Remove K1 from public JWKS; verify no private material present. | Inspected HTTP response and metadata version. |
| Token impact | Scope affected authorizations/sessions/clients/users; revoke additionally as needed. | Impact list and revoke/re-auth decisions. |
| Audit | Preserve KMS/HSM/IAM/app logs and evidence. | Immutable logs, correlation timeline, chain of custody. |
| Recovery | Verify K2 tokens, issuer/audience/scope, client flows, and API health. | Integration tests and sign-off from each service owner. |
| Postmortem | Root cause, timeline, control gaps, corrective actions. | Incident report and owner/deadline per action item. |

### 12.1. Decisions That Must Be Documented

- Why was suspected/confirmed compromise concluded?
- From what timestamp could K1 have been exposed?
- Were any forged tokens detected or used?
- Which issuers, audiences, clients, Resource Servers, and OIDC clients were affected?
- Did authorizations, refresh tokens, or sessions have to be revoked?
- Did any services still cache K1 or pin static keys?
- Who approved K2 creation and K1 removal?
- Which backups contain K1 and how were they marked unusable?
- Which temporary mitigations will be lifted, when, and with whose approval?

## 13. Testing and Incident Drills

### 13.1. Test Matrix

| Scenario | Expected result |
| --- | --- |
| JWT signed with K1 before incident, K1 not yet revoked | Verifies under normal policy. |
| JWT signed with K2 after rotation | Verifies cleanly with public K2. |
| JWT signed with K1 after registry marks it revoked | Resource Server rejects despite valid signature. |
| JWKS dropped K1 but Resource Server still caches K1 | Kid denylist still blocks K1 token. |
| Resource Server restarts during incident | Loads revoked-kid policy before accepting traffic. |
| Newly autoscaled node | Rejects K1; policy version is up to date. |
| One Authorization Server node still signs K1 | Monitoring detects; node isolated or rollout halted. |
| Old KMS principal still calls Sign | KMS/HSM denies and emits alert. |
| Key policy modified without authorization | Audit/control-plane alert triggers. |
| Old DB snapshot restored with K1 active | Startup/recovery gate refuses to activate K1. |
| Public JWKS contains private parameters | Security test fails. |
| Attacker-minted K1 JWT with new jti | Kid denylist still rejects; jti denylist alone is insufficient. |
| K2 token with wrong issuer/audience | Resource Server rejects. |
| Revocation registry unavailable | Fail-safe per policy; never auto-trust K1. |
| Opaque token revoked | Introspection returns inactive per server state. |
| OIDC ID Token signed with K1 | Client verifier enforces corresponding compromise policy. |
| One service uses static K1 | Inventory/tests detect and service is updated or isolated. |

### 13.2. Chaos/Incident Drill

At least periodically, rehearse in staging:

1. Create K1 and issue several test JWTs.
2. Simulate K1 compromise without using production private material.
3. Execute the runbook: block K1 signer, create K2, switch servers.
4. Update the revoked-kid registry and JWKS.
5. Measure time until every Resource Server rejects K1.
6. Confirm K2 tokens work and standard grants remain intact.
7. Restore a pre-rotation snapshot and confirm K1 is not reactivated.
8. Verify audit events are complete and free of raw tokens/private keys.
9. Record detection time, containment time, verifier coverage, and recovery time.

Never test by exporting or bringing production private keys into drill environments. Use simulated keys and test data.

## 14. Common Operational Pitfalls

### Error 1: Rotating Only the Private Key Without Updating Resource Servers

**Consequence:** Resource Servers continue trusting cached public K1; attackers keep forging accepted tokens.

**Fix:** Distribute revoked-kid policy, invalidate caches, and verify every verifier.

### Error 2: Removing K1 Only from JWKS

**Consequence:** Verifiers caching the key or pinning static keys still verify K1 tokens.

**Fix:** Pair JWKS removal with a key denylist or centralized revocation mechanism.

### Error 3: Keeping Public K1 to Avoid Breaking Old Tokens

**Consequence:** Attackers keep using private K1 to sign fresh tokens until every verifier stops trusting the key.

**Fix:** For emergency revocation, prioritize containment; legitimate old tokens may also be rejected and users must obtain fresh tokens.

### Error 4: Changing kid While Keeping the Same Key Material

**Consequence:** The leaked private key can still sign tokens; only the key label changed.

**Fix:** Generate a new key pair/version in KMS/HSM; never reuse compromised private material.

### Error 5: Forgetting ID Tokens or Other Services Sharing the Key

**Consequence:** APIs are protected while an OIDC client or another service still trusts forged tokens.

**Fix:** Inventory all token profiles and verifiers by issuer/kid, not just one API's access tokens.

### Error 6: Relying Solely on a jti Denylist for Key Compromise

**Consequence:** Attackers mint forged tokens with brand-new unseen jti values.

**Fix:** Reject by compromised kid; jti denylists only supplement specific-token revocation.

### Error 7: Restoring a Backup Resurrects the Old Key

**Consequence:** Authorization Server resumes signing with K1 or JWKS publishes K1 again.

**Fix:** Maintain a revoked-key ledger independent of snapshots and enforce a recovery gate before enabling signers.

### Error 8: Auditing Only Admin Events While Ignoring Sign Operations

**Consequence:** Impossible to determine which workload used the key, when, and at what volume.

**Fix:** Enable data-plane auditing for signing operations and correlate with request ID/issuer/kid/workload.

### Error 9: Disabling the Key Without Revoking IAM Permissions

**Consequence:** Attackers can create a new key or edit policies to keep signing.

**Fix:** Revoke compromised principals/credentials, review admin permissions, and audit the control plane.

## 15. Production Checklist

| Area | Required condition |
| --- | --- |
| Inventory | Maintain catalog of keys, kids, issuers, key versions, owners, algorithms, and consumers. |
| Key custody | Private keys reside in protected KMS/HSM/keystore; runtime never exports unnecessarily. |
| Least privilege | Runtime signer lacks key admin/export rights; JWKS publisher reads only public metadata. |
| Auditing | Immutable logs cover create/sign/disable/rotate/policy/IAM/backup/restore events. |
| Detection | Alerts cover unusual sign volume, unknown principals, policy changes, and old key versions. |
| Emergency key | Procedure exists to create K2, switch signers, and verify kid. |
| Verifier revocation | Registry blocks compromised kids and distributes to all Resource Servers/gateways. |
| JWKS cache | Invalidation/refresh mechanisms exist and coverage is measured across all instances. |
| JWT impact | Policies cover access tokens, ID Tokens, and any token profiles sharing keys. |
| Opaque tokens | Introspection/revocation available when centralized state is needed. |
| Backup/restore | Snapshots cannot reactivate compromised keys. |
| Recovery drill | Drills, RTO/RPO, and clear approvers are established. |
| Incident evidence | Procedures preserve logs, timelines, and chain of custody. |
| User/client recovery | Runbooks cover acquiring new tokens, re-login, or rotating related credentials. |

## 16. Hands-On Exercise

An Authorization Server runs three instances, signing access tokens and ID Tokens with RSA key K1. JWKS is cached for 30 minutes on several Resource Servers. KMS triggers an alert that a service account outside the operations group invoked a signing operation using K1. Unexpired JWTs issued prior to the incident are in circulation.

Perform the following:

1. Identify the data needed to distinguish private key exposure from KMS signing permission abuse.
2. Write a containment runbook: revoke principal/permissions, block K1 signing, and preserve audit logs.
3. Generate new K2, publish its public key, switch the signer across all three nodes, and verify new JWTs carry kid K2.
4. Design a shared <code>CompromisedKeyRegistry</code> so every Resource Server rejects JWTs with <code>kid=K1</code>.
5. Explain why removing K1 from JWKS is insufficient while caches still have 30 minutes remaining.
6. Write tests proving K1-signed JWTs are rejected while K2-signed JWTs with valid issuer/audience succeed.
7. Assess OIDC clients that may be verifying ID Tokens with K1 and build an update plan.
8. Design a recovery gate preventing old snapshot restores from making K1 active again.
9. Construct audit events for signing and key-management operations without logging raw keys/tokens.
10. Rehearse emergency rotation in staging and measure the time until all verifiers reject K1.

**Completion criteria:** You can demonstrate that **the Authorization Server no longer signs with K1**, **all verifiers no longer trust tokens carrying kid K1**, **K2 operates consistently**, and **audits contain sufficient evidence to identify who used or altered key permissions**.

## 17. References

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set, and public/private key parameters.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS signing and verification.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims and token lifetimes.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile, issuer, audience, and token type.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata and JWK Set URI.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key lifecycle, protection, rotation, and destruction.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): secret management, access control, and auditing.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>JWKSource</code>, <code>JwtEncoder</code>, and token generation.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): JWK Set endpoint and Authorization Server configuration.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer validation, and JWK Set URI.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): cryptographic lifecycle management and protection.
