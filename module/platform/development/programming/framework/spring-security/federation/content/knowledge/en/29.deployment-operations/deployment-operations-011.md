# Responding to Partner Trust Loss, Key Compromise, and Mass Session Revocation

**Federation incidents do not end when a password or certificate is swapped.** If an Identity Provider (IdP), OpenID Provider (OP), SAML signing certificate, OAuth signing key, service keytab, or partner trust relationship is compromised, already-established sessions can remain usable; JWTs may still be accepted by Resource Servers; metadata/JWKS caches can hold old keys; and downstream applications may never receive logout signals. Consequences can include **forged logins, account takeover, cross-tenant access, and persistent access after the organization ceased trusting the partner**.

**Response principle:** first **quarantine the affected trust source at every decision point**, then **revoke HTTP sessions, refresh tokens, access tokens, SAML/OIDC sessions, and dependent credentials per credential type**, while **preserving forensic evidence** and **rotating keys over an independently verified channel**. Never treat rotating a key at the IdP as sufficient, never treat SAML Single Logout/OIDC back-channel logout as an absolute "global kill switch," and never re-enable an issuer merely because new JWKS loaded.

This article belongs to **Spring Security – federation → Deployment and Operations**, focusing on incident response for OIDC/OAuth2, SAML2, Kerberos/SPNEGO, and multi-tenant partner relationships. It includes a trust propagation diagram, compromise classification table, containment–eradication–recovery workflow, Spring Security/Spring Session patterns, a runnable Java 17 demo simulating trust epochs and session revocation, a test matrix, drill checklists, and official standards links.

> **Scope:** This is defensive guidance for systems you are authorized to operate. Changing trust, performing mass revocations, or rotating keys in production must follow operational authority, the incident commander, and organizational change control; this article uses simulated domains, accounts, and keys.

## 1. Learning Objectives

After this lesson, engineers can:

1. Distinguish **partner trust loss** from **signing key compromise**, **SP private key compromise**, **client secret leak**, and **keytab compromise**.
2. Scope blast radius by **issuer/entityID, IdP registration, client ID, key ID, tenant, service, and downstream applications**.
3. Design **quarantine/fail-closed** controls at ingress login, SAML Response consumers, JWT Resource Servers, and session authorization.
4. Explain why **key rotation ≠ token/session revocation**.
5. Distinguish local logout, OIDC back-channel logout, SAML SLO, OAuth token revocation/introspection, and application-enforced invalidation.
6. Mass-revoke Spring HTTP sessions across multiple nodes without relying on a local-only `SessionRegistryImpl`.
7. Design **trust epochs / reauthentication generations** to block sessions missed by an index.
8. Prevent cross-tenant bugs when one issuer serves multiple organizations or one tenant trusts multiple IdPs.
9. Build runbooks, RACI, metrics, re-enablement criteria, and fail-closed tests.
10. Write a standalone Java 17 demo proving quarantine, revocation, stale epochs, and tenant isolation.

## 2. Concepts That Must Stay Distinct

| Concept | What it means | What it does NOT guarantee |
| --- | --- | --- |
| **IdP/OP trust** | RP/app accepts assertions from an issuer/IdP per approved registration | User holds tenant access |
| **Issuer** | Token issuer/AS ID, e.g. `https://id.partner.test` | Signing key is uncompromised |
| **SAML entityID** | Asserting party/service ID in SAML | Cert in metadata has not leaked |
| **JWK / signing certificate** | Public key verifying signatures | Private key has not been stolen |
| **Trust anchor / registration** | Metadata, keys, issuer, audience, binding, and policy for a source | Old sessions have expired |
| **HTTP session** | Local web application session | OAuth API tokens are invalidated |
| **OIDC OP session** | User's session at the OP, optionally linked via `sid` | All RP sessions are terminated |
| **SAML SLO** | Logout protocol across participating SPs/IdPs | Offline or non-participating SPs also logged out |
| **OAuth access token** | Credential for Resource Servers | Immediately revoked if issued as a self-contained JWT |
| **OAuth refresh token** | Allows requesting new access tokens | Revoking it kills already-issued access tokens |
| **Kerberos ticket** | Proof of service access per KDC/service key | Logging out a Spring session destroys OS TGTs |
| **Trust epoch** | App-managed trust policy version | Replaces initial signature verification |

**Never collapse** `sub`, email, `kid`, SAML NameID, or group names into a global key. Identities must retain source namespaces (OIDC `iss+sub`; SAML IdP entityID + stable NameID/attribute per contract; Kerberos verified realm/principal).

## 3. Risk Propagation Diagram

~~~text
                     Partner IdP / OP / SAML
                      private signing key (?)
                               |
                    issuer metadata / JWKS
                               |
      +------------------------+-------------------------+
      |                        |                         |
  Portal RP             Billing API                 HR SAML SP
  Spring session        JWT Resource Server         SAML session
      |                        |                         |
  OAuth refresh         JWT access tokens           Downstream app
      |                        |                         |
      +------------------------+-------------------------+
                               |
                       Tenant A / Tenant B
                               |
                     Domain authorization
~~~

If a Partner's signing key leaks, an attacker can forge valid-looking signatures for any consumer still trusting that key. **Reloading metadata or logging out one portal does not sever every path.** Inventory all **verifiers**, sessions, token consumers, keys, caches, and downstream services.

**Primary control point:** cut off *new and continuing access* at enforcement points your application controls; where third-party downstreams lack central governance, coordinate and document residual risk.

## 4. Classify the Incident Before Picking Countermeasures

| Scenario | Broken boundary | First scope to examine |
| --- | --- | --- |
| **Partner trust loss** (contract ended, IdP takeover, metadata supply chain) | Trust relationship, issuer/IdP registration | All logins/verifications and account links from that partner |
| **OIDC/OAuth private signing key leaked** | ID Token / JWT access token signatures | Every consumer trusting that key; old vs new tokens may be indistinguishable |
| **SAML IdP private signing key leaked** | Response/Assertion/LogoutRequest signatures | All RPs trusting that cert/key, including assertions with forged `IssueInstant` |
| **SAML SP private signing key leaked** | RP identity toward IdP and protocol messages | IdPs trusting that SP signing key |
| **SAML SP decryption key leaked** | Confidentiality of encrypted Assertions | Captured assertions may decrypt; assess historical data exposure |
| **OAuth client secret/private key leaked** | Client authentication with AS | Token issuance/grants, `client_credentials`, refresh token exposure |
| **Spring session store / cookie key leaked** | Local sessions, server-side hijack/forgery depending on design | All users/apps sharing that secret/store |
| **Kerberos HTTP service keytab leaked** | Service credential / SPN | Ticket decryption/service impersonation and SPNs sharing the account |
| **TLS private key or truststore altered** | Channel identity / transport integrity | Endpoints/scopes relying on that TLS key or trust config |

**Exposing a public signing certificate is not a private-key leak**: public keys are published for verifiers. Distinguish *public metadata viewed* from *private key stolen*, *suspected key compromise*, and *IdP issuing wrong tokens*.

## 5. Severity: What Raises Priority?

Assess by business impact and technical reality, not algorithm names alone:

- **Reach:** how many tenants, applications, RPs, APIs, and environments trust the signing key?
- **Trust:** are admin claims or financial/PII privileges signed by this key?
- **Token validity:** do JWTs have long lifetimes, refresh token rotation, and introspection?
- **Session lifetime:** long-lived HTTP sessions, remember-me tokens, downstream sessions?
- **Evidence:** forged tokens/mass logins observed, keys found outside vaults, unauthorized metadata changes?
- **Control:** is there a central kill switch or must each microservice update separately?
- **External exposure:** were keys/metadata shared with third-party verifiers?
- **Service availability:** which workflows stop when disabling the partner; is a separate break-glass path available?
- **Regulatory/customer impact:** personal data, regulated sectors, notification obligations?
- **Cross-tenant:** does the same issuer serve unaffected tenants alongside compromised ones?

**When private-key theft is unconfirmed yet credible indicators exist**, contain according to blast radius and risk appetite—never wait for conclusive forensics before blocking potential forgery.

## 6. War Room Roles

| Role | Primary responsibility |
| --- | --- |
| **Incident Commander (IC)** | Priorities, scope, block/re-enable decisions, timeline log |
| **IAM/IdP owner** | Issuer/SAML metadata, keys, IdP-side user/session revocation |
| **Spring app owner** | Login filters, client registrations, HTTP sessions, local access |
| **API / Resource Server owner** | JWT/opaque access-token rejection, caches, revocation guards |
| **Platform/SRE** | Secret stores, service mesh, Redis/JDBC sessions, rollouts, monitoring |
| **Security/forensics** | IOCs, evidence chain-of-custody, log retention, scope, threat validation |
| **Customer/partner liaison** | Independent verification channel, status updates, transition support |
| **Privacy/legal/compliance** | Notification assessments and legal/contractual reporting obligations |
| **Business continuity owner** | Break-glass workflows and critical business availability |

**Never allow a tenant admin to unilaterally restore trust for an IdP under investigation**, bypassing security owner approval. Identity trust configuration must stay separate from routine business permissions.

## 7. Overall Response Sequence

~~~text
DETECT / VERIFY SIGNAL
         |
         v
DECLARE INCIDENT + preserve evidence
         |
         v
INVENTORY affected trust and consumers
         |
         v
QUARANTINE / fail closed (login + APIs + sessions)
         |
         v
REVOKE local sessions, refresh grants, tokens, delegated credentials
         |
         v
ERADICATE compromise, rotate keys via verified independent channel
         |
         v
ATTEST new issuer/IdP metadata, credentials, trusted mappings
         |
         v
RE-ENABLE selected flows with trust epoch increase
         |
         v
FORCE re-authentication + monitor + post-incident review
~~~

This is the conceptual order; **containment, evidence preservation, and credential revocation can execute in parallel** under IC coordination. What is strictly forbidden is re-enabling trust from new keys/metadata arriving over **the compromised channel itself** without independent verification.

## 8. Signals Identifying "Partner Trust Loss"

Common indicators:
- IdP/OP notifies you of a private signing key compromise.
- JWK Set shows an unapproved new key or anomalous thumbprint.
- SAML metadata points to an unfamiliar signing cert or redirects to an unapproved endpoint.
- Issuer/entityID stays the same while login claims/roles/subjects spike unexpectedly.
- Data shows an account with a verified Partner issuer accessing a tenant without membership.
- JWT has `iat`/`jti` inconsistent with AS telemetry while the signature verifies.
- Partner trust certification expired or a contract requires terminating that identity source.
- Partner suffers a DNS/metadata-server compromise or user-provisioning abuse.

**The source of truth** is incident evidence plus an out-of-band verified communication channel and the approved registration inventory. **Never treat "signature valid" as proof the issuer is uncompromised** when the signing key itself is suspected leaked.

## 9. Initial Containment: Deny Trust, Do Not Merely Delete the Key

At every consumer:
1. Mark the trusted issuer/IdP registration **QUARANTINED** in an authenticated control plane.
2. Reject **new OIDC logins**, OAuth authorization callbacks, and SAML Responses from that profile.
3. Reject API Bearer JWTs belonging to the affected issuer/credential **before or alongside the decoder**, even if validly signed.
4. For opaque access tokens, reject the quarantined profile even if introspection returns `active=true`.
5. Block existing sessions sourced from the quarantined registration/issuer via a **per-request trust guard**—do not rely solely on deleting known sessions.
6. Disable JIT provisioning/automatic account linking and group-role mappings from that source.
7. Remove/quarantine suspected compromised certificates/keys across **all verifiers** or apply immediate deny policies before key-store rollouts finish.
8. Block unauthenticated out-of-band event/log ingestion so the partner cannot self-declare "incident resolved."
9. Preserve audit logs, key version IDs, and config snapshots per forensic procedure.
10. Maintain break-glass admin logins from an **independent source**, bound to MFA and dedicated monitoring.

**Removing one JWK from a JWKS endpoint does not guarantee Resource Servers stop trusting it immediately**: many consumers cache JWKs and some pin keys. Enforce control-plane deny/epochs at consumers and verify every deployment.

## 10. SAML: When the IdP Private Signing Key Leaks

A SAML Assertion signed with a stolen private key can carry **any Issuer, NameID, groups, Conditions, and IssueInstant chosen by the attacker**. RPs still trusting the old certificate will accept it. Never rely on timestamps as proof an assertion predates the compromise.

**SAML Runbook:**
1. Inventory all `RelyingPartyRegistration` entries and SPs trusting that certificate.
2. Disable/quarantine the asserting party registration; block new responses and existing sessions per app policy.
3. Preserve SAML Response identifiers/metadata fingerprints without exposing attributes/PII.
4. Partner generates a **new signing key inside a verified clean environment**; confirm ownership out-of-band.
5. Deliver the new public certificate/thumbprint through the approved metadata change process.
6. Verify expected IdP entityID, signed metadata trust, ACS/Destination, Audience, cert bindings, and algorithms.
7. Separate normal overlap rotation from **compromise**: **never keep a compromised old cert trusted** just to minimize downtime.
8. Reload/roll out `RelyingPartyRegistrationRepository`/validators across all SPs and verify the old cert is rejected.
9. Revoke application sessions created via the compromised asserting party and force re-login once trust is restored.
10. Test SAML login, NameID namespaces, group mappings, tenant isolation, replay/InResponseTo correlation, and SLO behavior.

**Note:** a `LogoutRequest` signed with the compromised IdP key is also untrustworthy. Never treat an unfamiliar `LogoutRequest` as authority to revoke sessions across namespaces when the key is suspect; execute revocation via the independent admin control plane.

## 11. SAML: When a Service Provider Private Key Leaks

Distinguish key roles:

- **SP signing key:** signs AuthnRequest/LogoutRequest, proving SP identity to the IdP when IdP policy requires it.
- **SP decryption key:** decrypts `EncryptedAssertion`; leakage threatens confidentiality of captured assertions.
- **Same key used for both:** widens blast radius—assess both authentication and confidentiality.
- **SAML IdP signing cert:** the partner's public trust key, a different role.

**Actions:** inventory IdPs trusting the SP signing cert or encrypting to the SP encryption cert; request key rotation/disabling over an independent channel; update SP metadata and IdP registrations; stop using the leaked key; test interoperability; and triage historical assertions that might be decrypted. Never swap only a UI-displayed cert while the leaked private key remains active on a node or usable backup.

## 12. OIDC/OAuth: When the OP/Authorization Server Signing Key Leaks

**For ID Tokens:** RPs can accept forged identities while still trusting the signing key, even when `iss` and `aud` look valid. Quarantine the issuer/client registration, invalidate local sessions, and refresh trust metadata.

**For JWT access tokens:** Resource Servers verify signatures locally. When a private signing key leaks, rotating the JWK at the AS **does not automatically make previously issued tokens fail**; Resource Servers may cache the old key and multiple APIs may trust it.

**Priorities:**
1. Block the issuer/key at **all Resource Servers** with a trusted deny policy.
2. Bump the trust epoch/cutoff for sessions and tokens/grants from that source.
3. Rotate signing keys in an independently verified HSM/KMS/AS.
4. Attest the new metadata/JWKS key over a channel independent of compromised infrastructure.
5. Purge/invalidate stale decoder caches or restart/roll out as designed.
6. Verify tokens signed with the old compromised key **fail** at every API.
7. Test new tokens from the restored issuer for audience, `alg`, `iss`, `exp`/`nbf`, and tenant policies.
8. Never use an unverified token's `kid` to fetch arbitrary JWKS dynamically.
9. Revoke refresh grants and sessions; force reauthentication per blast radius.
10. Audit long-lived offline grants and machine clients needing separate rotation.

**Never rely solely on `iat > incidentTime`:** whoever holds the signing key can forge `iat`. Cutoffs work only when keys, clocks, and claim provenance remain trustworthy; on key compromise, enforce server-controlled **key/issuer epochs** or token validation state.

## 13. OAuth Client Secret or Client Private Key Compromise

A compromised client credential differs from an OP token-signing key. Attacks include impersonating the OAuth client, calling `client_credentials`, redeeming grants, or using refresh tokens **if the attacker holds the remaining required factors**.

Runbook:
- Disable/quarantine the client registration or client auth key.
- Revoke the leaked client secret/private key/certificate at the AS.
- Rotate client credentials in the secret manager, across all pods and workload identities; never commit to config/Git.
- Revoke/rotate affected refresh grants; audit access tokens and service-to-service clients.
- Review redirect URIs, consent, DPoP, and mTLS bindings where applicable.
- Inspect anomalous client authentications and API logs.
- Apply least-privilege secrets and isolate blast radius across tenants.
- Maintain break-glass token issuance on a separate client with MFA/admin approval.
- Verify old credentials are rejected, new ones succeed; never post tokens/keys in incident chat.

**Never reuse a client secret across environments, tenants, or multiple partners.** If shared, expand incident scope to every integration sharing that secret.

## 14. Kerberos HTTP Keytab Compromise: Federation-Related Scenarios

**A keytab** stores service principal keys, such as `HTTP/portal.corp.test@CORP.TEST`. Keytab exposure can let attackers decrypt service tickets or impersonate the service under certain conditions. It is not identical to a **user password** leak or an OIDC issuer signing key leak.

Required actions:
1. Identify the service account and **all SPNs** sharing that secret.
2. Disable/block affected services as needed; rotate service account keys/KVNO in coordination with KDC/AD.
3. Roll out the new keytab to every node, handling ticket-lifetime overlap per security policy.
4. Test old/new service tickets by KVNO and allowed enctypes.
5. Prevent reuse of old keytabs in containers/images/CI logs; audit secret exposure.
6. Terminate or isolate app sessions potentially created via the impersonated service.
7. Ensure no privileges are granted from raw `REMOTE_USER`/untrusted proxy headers.
8. Document cross-realm referrals, SPN aliases, and affected services.

**Logging out of a Spring app does not remove OS Kerberos TGTs**, and resetting a service keytab does not automatically revoke Spring sessions. Protect both service trust and local authorization.

## 15. Mass Revocation: Order of Controls Matters

During an incident, separate:

1. **Stop accepting:** halt new and continuing access from the compromised source.
2. **Invalidate HTTP sessions:** portal/RP session cookies lose access.
3. **Revoke refresh tokens/grants:** block minting new access tokens.
4. **Invalidate/deny access tokens:** APIs stop honoring already-issued tokens.
5. **Cut off downstream delegation / service credentials.**
6. **Emit logout signals** where IdP/SP trust remains intact and protocols work.
7. **Apply emergency account and tenant denies** in domain/object authorization.
8. **Force reauthentication** once trust is restored.
9. **Verify propagation** across all services and nodes, not only the UI.
10. **Keep an incident hold** on identities/tenants suspected of abuse even after the issuer recovers.

**Note:** logically, blocking comes first, yet do not wait for a massive session-deletion batch to finish before enforcing denies; per-request quarantine guards close the gap immediately.

## 16. Each Session/Token Type Requires Its Own Action

| Credential / session | Where managed | Available actions | Limitations |
| --- | --- | --- | --- |
| Spring `HttpSession` | App / Spring Session | Invalidate/delete or deny via epoch | Multi-node stores, in-flight requests |
| `SecurityContext` | Spring request/session | Clear current context, deny next requests | Other threads/requests may still be running |
| OIDC RP session | Each RP | Local invalidation or validated back-channel logout | Does not automatically cover all RPs |
| OIDC OP session | OP | OP logout/session revocation | Does not guarantee offline RPs update immediately |
| OAuth refresh token | AS | RFC 7009 revocation, revoke grant | Does not guarantee old access JWTs stop working |
| OAuth opaque access token | AS / introspection | Revoke and return introspection `active=false` | Caches and RS authorization policies |
| OAuth JWT access token | RS / AS | Deny issuer/key/epoch, denylist, short TTL | Offline validation has no central revocation by default |
| SAML SP local session | Each SP | Local invalidation, SLO if supported | SLO may not reach every app |
| SAML IdP session | IdP | IdP-side session revocation | SPs missing SLO keep local sessions |
| Kerberos OS TGT / service ticket | KDC / client / acceptor | KDC/account/key rotation, ticket lifetime | Not in the HTTP session namespace |
| Mobile / offline app token | Client / server | Revoke/deny on next online use, device policy | Offline devices cannot be "remotely wiped instantly" |

**Use the phrase "immediately revoked" only with evidence that Resource Server requests are rejected**, not merely because a revoke call went to the IdP.

## 17. OAuth Token Revocation (RFC 7009): Understanding It Accurately

RFC 7009 defines a **token revocation endpoint**. OAuth clients can ask the AS to revoke a token; the AS invalidates it and may revoke related tokens in the same grant per policy.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: as.example.test
Authorization: Basic <CLIENT_AUTH_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_EXAMPLE&token_type_hint=refresh_token
~~~

This is a **non-runnable pseudo-request** with illustrative placeholders; never store real client credentials in tests or logs.

**Limitations:**
- The revocation endpoint belongs to the AS **if the AS supports it**; an app/RP cannot mock an endpoint and assume every API received it.
- Revoking a refresh token prevents future token issuance, yet **already-issued self-contained access JWTs** may still verify until `exp` unless RSs enforce revocation awareness.
- Access token revocation can suffer propagation delays across AS/RS caches.
- You may need to revoke the **grant family** / rotating refresh-token chain, not a single token string.
- Never write raw tokens into audit logs; log token fingerprints/hashes if policy permits.
- During an issuer compromise, introspection from a compromised AS must not be the **sole trust authority**; emergency denies at RSs remain essential.

**Conclusion:** RFC 7009 is an AS token-management mechanism—**it does not replace centralized emergency authorization denies** across applications.

## 18. Opaque Token Introspection (RFC 7662)

With opaque tokens, Resource Servers normally call the introspection endpoint to check `active=true/false`, scopes, and issuer/client metadata per AS contract.

Example revoked token response:

~~~json
{
  "active": false
}
~~~

What to test:
- Resource Server rejects inactive tokens.
- Access token introspection caches have short TTLs or can be purged so incident disablement is not masked by cache.
- During an **AS/issuer compromise**, an `active=true` response must never override a **local issuer QUARANTINED policy**.
- Introspection client credentials are protected, with verified endpoint TLS and AS identity.
- Never equate introspection success with local tenant authorization.
- During AS outages, fail closed for operations needing that trust—never fall back to accepting tokens freely.

**Limitation:** working introspection does not automatically revoke Spring browser sessions or SAML SP sessions.

## 19. Stateless JWTs Need a Stateful Emergency Deny Layer

JWT access tokens can be verified offline at each Resource Server. **There is no global server-side "delete JWT from browser."** When signed by a leaked key, every JWT trusted by verifiers can be forged.

Protections:
- Denylist **issuer/registration/key version** at Resource Servers.
- Encode policy as integrity-protected trust status + epoch/generation distributed across nodes.
- For tokens issued post-recovery, verify the new signer/key via the updated registration.
- For sessions/tokens lacking epoch claims, deny by source/key/tenant binding or risk tier.
- When keys haven't leaked yet individual JWT revocation is needed, a server-side `jti` denylist with TTL up to `exp` works if token/JTI are trustworthy and fan-out is reliable.
- With a compromised signer, **attacker-signed `jti` and `iat` are not allowlisted trust keys**; treat them only as secondary controls, never as "token acceptance exceptions."
- Prefer short-lived access tokens, sender-constrained tokens (mTLS/DPoP where suitable), and introspection if immediate revocation is mandatory.
- Verify every RS checks issuer, audience, timestamps, token purpose, tenant, and emergency policy.

**Never "fix" an incident by rotating a single key while leaving the old key inside trust stores indefinitely.**

## 20. Spring Security `SessionRegistry`: Useful Yet Not a Cluster Solution Alone

Spring Security supports session management, `SessionRegistry`/`SessionInformation`, and concurrent session control. However:

- `SessionRegistryImpl` stores state in one JVM's memory by default and cannot provide a cluster-wide view across pods.
- `expireNow()` on `SessionInformation` marks a session expired for Spring concurrency tracking; **it does not guarantee immediate deletion across every HTTP session store or abort in-flight HTTP requests**.
- Sessions created through custom filters may bypass the registry unless integrated.
- User-triggered `/logout` invalidates only the current session, not mass revocation.
- `SecurityContextHolder.clearContext()` clears only the current thread's context; it never revokes other users' sessions.
- Stateless API Bearer tokens do not share the HTTP session registry.
- Using Spring Session with a shared store enables lookup/deletion, yet still requires indexes by source/tenant.

**Control decision:** pair a **quarantine guard reading trust policy on every sensitive request** with a **session-revocation job using an indexed inventory**; both reinforce each other.

## 21. Spring Session: Finding and Terminating Sessions Across Nodes

Spring Session defines `SessionRepository<S extends Session>` with `deleteById(sessionId)` and `FindByIndexNameSessionRepository<S>` with `findByPrincipalName(name)` (when supported by the implementation/index).

**Project code fragment, not standalone Java:**

~~~java
import java.util.Map;
import org.springframework.session.Session;
import org.springframework.session.FindByIndexNameSessionRepository;

class PrincipalSessionRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> repository;

    PrincipalSessionRevoker(
        FindByIndexNameSessionRepository<S> repository) {
        this.repository = repository;
    }

    int revokeByPrincipal(String principalName) {
        Map<String, S> sessions =
            repository.findByPrincipalName(principalName);
        sessions.keySet().forEach(repository::deleteById);
        return sessions.size();
    }
}
~~~

**Serious limitations of this example:**
- It performs **best-effort per-principal deletion**. There is no built-in "delete all sessions by issuer" method, nor an atomic cluster-wide snapshot.
- The default principal index may hold only a username, **unable to distinguish two issuers sharing a username**. Store trusted source + subject namespaces via a **dedicated index or trusted session inventory**.
- Repository implementations must populate the index accurately; `findByPrincipalName` returns empty if indexing is unpopulated.
- Delete-by-id does not stop races where another session is created simultaneously; **quarantine/epoch guards** block that.
- In-flight HTTP requests may still be executing; critical operations must re-check policy near commit.
- Session stores may be partitioned/cached; verify deletion propagates to every node.
- Never take a principal name from an unverified attacker token as a batch-revocation target.

**Never run automated production batch deletions triggered solely by a login error or an unverified OIDC Logout Token.** Require IC approval, exact scope, and an audit trail.

## 22. Dedicated Session Inventory for Federation

To revoke by issuer, tenant, or key compromise, maintain a server-side index:

~~~text
federation_session_inventory(
  app_id,
  local_session_id_hash,
  storage_session_id_reference,  // encrypted/protected internal pointer
  source_protocol,              // oidc, saml, kerberos, ldap...
  trusted_registration_id,
  verified_issuer_or_entity_id,
  verified_subject_id,
  tenant_id,
  local_account_id,
  auth_method,
  trust_epoch_at_login,
  created_at,
  last_seen_at,
  expires_at,
  revoked_at,
  policy_version
)
~~~

**Never store raw readable/forgeable session IDs in analytics or logs.** Revocation storage keys require access control; external audits use hashes or opaque correlation IDs. Populate the index **only after successful authentication** from a verified identity context—never from unverified `iss`/`tenant` request inputs.

**Fan-out revocation:** query inventory by approved trusted registration/issuer and tenant scope; delete sessions, set persistent revoked flags, and bump the epoch. Use idempotent batches, pagination, bounded retries, checkpoints, reconciliation, and metrics.

**Compromise of a shared multi-tenant issuer** requires inspecting **all** tenants trusting that issuer/key, not only the tenant reporting the incident.

## 23. Trust Epoch / Generation Guard: Defense Against Missed Sessions

Maintain a **monotonically increasing** version per trust profile. On every quarantine, restore, or key change, increment the epoch; new sessions are issued only after verification under the current epoch. On incoming requests, compare the session's epoch against the **current authoritative epoch**.

~~~text
TrustProfile:
  id = partner-oidc
  status = QUARANTINED / ACTIVE
  epoch = 12

Existing HttpSession:
  source = partner-oidc
  epoch_at_login = 11

Request:
  if status != ACTIVE -> DENY
  else if session_epoch != current_epoch -> DENY_REAUTH_REQUIRED
  else if session revoked -> DENY
  else check local account/tenant/permissions
~~~

Advantages:
- Catches sessions missed by batch deletion due to incomplete indexes.
- Blocks races creating sessions right before quarantine when the epoch increments.
- Applies across cookies/session stores, authenticated API grants, and delegated app sessions when source links exist.

**Limitation:** epoch guards work only when **every enforcement point reads updated policies promptly**. Long-TTL caches or fail-open behavior open windows of exposure. During incidents, fail closed for suspect issuers and measure **maximum propagation delay**.

**A session cookie lacking trusted source registration metadata** is hard to revoke selectively; design the inventory before an incident strikes.

## 24. Spring Request Guard Fragment for Suspended Providers

Project-level design in a Spring Servlet app: inspect the issuer of an **already-provider-verified `Authentication`**, never unverified headers/claims; bind the source identifier inside protected local authentication/session claims.

~~~java
// PSEUDOCODE wired inside a registered OncePerRequestFilter
// ONLY a policy-guard sketch, not a standalone compilable class.
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()
        && !(auth instanceof AnonymousAuthenticationToken)) {
    VerifiedFederationContext ctx =
        trustedContextResolver.resolve(auth); // app-owned; verified
    TrustPolicy policy =
        trustPolicyStore.current(ctx.registrationId());
    if (!policy.active()
            || ctx.loginEpoch() != policy.epoch()) {
        SecurityContextHolder.clearContext();
        response.sendError(401, "Reauthentication required");
        return;
    }
}
filterChain.doFilter(request, response);
~~~

**Additional production requirements:** ensure `VerifiedFederationContext` never comes from HTTP headers, bind source identity to the session, cover API Bearer tokens without bypass, ensure HA/atomic policy store versioning, delete session store entries, and handle CSRF, error responses, and exceptions cleanly. A separate filter does not guard earlier pipeline steps; verify placement in `SecurityFilterChain`. For WebFlux, implement the reactive equivalent.

**Never trust a token signed by a compromised key to extract claims granting an exception to the trust epoch.** While quarantined, policy must block before any privileged acceptance.

## 25. OIDC Back-Channel Logout: Guarantees and Limits

OpenID Connect Back-Channel Logout 1.0 lets the OP send a **Logout Token** to the RP via a server-to-server endpoint. The token must be verified: signature, `iss`, `aud`, `iat`/`exp`, logout `events` claim, presence of `sub` or `sid`, and **absence of `nonce`**. When `sid` is present, target that session; when `sub` appears without `sid`, scope is typically that subject's sessions at the RP for that issuer/client.

**Spring Security Servlet docs** describe configuring:

~~~java
// Fragment inside a Spring Security OAuth2/OIDC Client application.
// Requires oauth2Login; configure logout token validation for your release.
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

In Spring docs, the default endpoint is usually `/logout/connect/back-channel/{registrationId}`; wire the OIDC logout handler/session registry properly. **Spring Session commonly uses the `SESSION` cookie whereas default handlers may expect `JSESSIONID`**, so align cookie names/registries and test end-to-end.

**Incident limitations:**
- Back-channel logout reaches only registered, reachable RPs that process the event.
- The RP must validate the Logout Token before invalidating sessions.
- If the OP signing key leaked, a Logout Token signed with that key is no longer independent trustworthy proof. **Emergency admin revocation must go through a separate control plane**, never waiting for a "valid" Logout Token.
- A token carrying `sid`/`sub` from issuer A **must never delete issuer B's sessions** merely because user strings match.
- OP logout does not guarantee downstream access JWTs and refresh tokens across all APIs are canceled.
- Incidents needing mass revocation must execute **inside RPs and APIs**, incorporating OP signals only after assessing trust.

## 26. SAML Single Logout: Useful Yet Not an Emergency Guarantee

Spring Security SAML2 supports **RP-initiated** and **AP/IdP-initiated SLO** when configured on both sides. Valid SLO helps close local sessions.

**However, SLO cannot be treated as guaranteed global revocation:**
- Both SP and IdP must support it with matching endpoints and trust configs.
- Browser redirects, timeouts, and offline partners cause partial logouts.
- Downstream app sessions using other protocols are not covered automatically by SLO.
- A `LogoutRequest` signed by a **suspected compromised key** cannot be trusted as an authorized remote admin action.
- Key rotation or metadata cache lag can cause `LogoutRequest`/`Response` rejections.
- Logging out an SP session does not expire API access JWTs.
- Users may hold multiple devices, browsers, and local sessions requiring a dedicated inventory.

**During a SAML IdP key compromise, prioritize quarantine and local session revocation via an app-owned control plane** without waiting for SLO completion. Keep SLO as a helper while trust remains intact or after recovery.

## 27. Shared Security Events and Continuous Access Evaluation

Some platforms support **Security Event Tokens (SETs)** and the **Continuous Access Evaluation Profile (CAEP)**—events like `session-revoked`, `token-claims-change`, or `credential-change`. They can reduce propagation latency between identity providers and relying parties where supported.

**Design requirements:**
- Verify event sender/issuer, audience, event type, and event signature per contract.
- Prevent replays/duplicates (event IDs/nonces/timing per spec).
- Bind subject identity to issuer namespace and tenant.
- Combine with local issuer quarantine; never trust a compromised sender.
- Implement retries, idempotency, and audit acknowledgements.
- Account for event-delivery outages.
- Never assume every IdP or Spring app supports CAEP/SET out of the box.

**Never replace** backend revocation logic and policy enforcement with an unauthenticated event bus.

## 28. Minimizing Blast Radius by Tenant Without Missing Shared Keys

In B2B SaaS, multiple tenants may trust one issuer:

~~~text
partner-issuer -> tenants North, South, West
shared-signing-key -> ID Tokens of partner-issuer
North -> partner-issuer + corp-issuer
South -> partner-issuer only
West -> partner-issuer + saml-enterprise
~~~

If `partner-issuer`'s **shared private signing key** leaks, North, South, and West may all be affected even if the incident started at South. Quarantine by **trust/credential blast radius**, not solely by a request-supplied `tenantId`.

If only tenant South's **trust agreement** ends while the OP's signing key remains uncompromised, you can disable the `South → partner-issuer` mapping while keeping North/West active once security owners confirm.

**Local authorization:** even when an issuer remains trusted for a tenant, users must hold **active memberships** and object-level permissions. Never map a user from issuer B to issuer A's account based on matching email or `sub`.

## 29. Metadata, JWKS, and Certificate Caches During Emergencies

Components that may cache trust state:
- OIDC Discovery documents, `jwks_uri`, and signing keys by `kid`.
- Spring/Nimbus `JwtDecoder` key sets and underlying network caches.
- SAML `RelyingPartyRegistrationRepository` and IdP signing certificates.
- Gateway/service-mesh auth policies.
- JWT validation libraries in workers and mobile backends.
- Spring Session and local `SecurityContext`.
- OAuth access token introspection responses.
- Partner metadata endpoints, CDNs, and DNS.

**Check every layer:** is the old key still trusted? How long is cache TTL? Can it be rolled out, restarted, or purged? Is the deny policy enforced before key verification or after? On key compromise, seal every path that could still accept compromised signatures.

**Beware "first key that verifies":** never loop through all issuers and accept whichever signature matches; bind strictly to the source registration, expected issuer/entityID, audience, and tenant.

## 30. Safe Signing Key Replacement and Independent "Proof of Control"

Post-compromise recovery process:

1. IdP/OP owner confirms the intrusion vector is isolated and rotates the signer inside a **clean** vault/HSM.
2. Security owner authenticates the authorized partner contact over a channel **independent** of suspected compromised metadata/DNS/email accounts.
3. Publish the new public key/certificate through an approved trust-change workflow.
4. Record fingerprint, key identifier, algorithm, owner, timestamps, and impacted clients.
5. Reconcile issuer/entityID, service endpoints, keys, metadata, and expected recipient/audience.
6. Reconfigure RPs, Resource Servers, gateways, and downstream services.
7. **Never keep the compromised old key in overlap**; if brief downtime is needed to purge old trust, accept it per IC decision.
8. Verify forged/synthetic tokens signed with the old key **all fail** before restoring service.
9. Verify new-key tokens with trusted provenance pass standard login flows and updated policies.
10. Transition READY→ACTIVE only once verification passes across **all** consumers.
11. Bump the trust epoch; all old sessions must reauthenticate rather than auto-renewing.
12. Monitor changes and ensure rollback procedures never reintroduce the compromised key.

**Without proof the new signing key was generated in a clean environment, trust is not ready to restore.**

## 31. Local Accounts and Authorization After Recovery

A clean new IdP key does not automatically clean up local accounts or roles:

- Verify **(verified issuer, subject)** for OIDC and **(verified IdP entityID, stable identifier)** for SAML.
- If the partner changed issuer/entityID, treat it as a **new namespace**; migrations/linking require authoritative proof, never email auto-linking.
- Keep JIT provisioning disabled during quarantine and audit accounts created inside the incident window.
- Review group→`GrantedAuthority` mappings, privileged grants, tenant memberships, SCIM changes, and admin role assignments.
- Audit resource objects modified by suspect sessions/tokens.
- Revoke OAuth consents/grants that may have been abused.
- Require step-up/MFA/re-enrollment based on severity and tenant policy.
- Never grant `ROLE_ADMIN` merely because a claim was verified by the new signer.
- Check local user disablement and offboarding.
- Rebuild subject-to-local-account maps if identity collisions are found.

**Recovery means not just restoring logins, but ensuring authorization state is clean** after compromise.

## 32. Runnable Java 17: Quarantine, Mass Revocation, and Trust Epoch

The **pure JDK 17** example below models control-plane policies and sessions across two federation sources. It reads no JWTs, verifies no SAML signatures, does not call Redis, and deletes no live Spring sessions. `provider`/`tenant` values represent **post-verification trusted context**, never values from untrusted HTTP requests.

Simulated scenario:
- `partner-oidc` serves South and `corp-saml` serves North.
- Quarantining partner immediately blocks its requests while Corp remains unaffected.
- Batch-revoke known partner sessions.
- Restoring partner bumps the epoch so **old sessions missed by the index become stale**.
- A fresh session after reauthentication is accepted when the tenant matches.
- Unknown providers or missing sessions are denied.

Create **FederationIncidentGateDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class FederationIncidentGateDemo {

    enum TrustState { ACTIVE, QUARANTINED }

    record Policy(TrustState state, long epoch) {}

    record LoginSession(
            String id, String provider, String tenant,
            long loginEpoch, boolean revoked) {}

    private final Map<String, Policy> policies = new HashMap<>();
    private final Map<String, LoginSession> sessions = new HashMap<>();

    FederationIncidentGateDemo() {
        policies.put("partner-oidc", new Policy(TrustState.ACTIVE, 4));
        policies.put("corp-saml", new Policy(TrustState.ACTIVE, 9));
        sessions.put("partner-old", new LoginSession(
                "partner-old", "partner-oidc", "south", 4, false));
        sessions.put("corp-old", new LoginSession(
                "corp-old", "corp-saml", "north", 9, false));
    }

    String check(String sessionId, String requestedTenant) {
        LoginSession session = sessions.get(sessionId);
        if (session == null) {
            return "DENY_NO_SESSION";
        }
        Policy policy = policies.get(session.provider());
        if (policy == null) {
            return "DENY_UNKNOWN_PROVIDER";
        }
        if (policy.state() != TrustState.ACTIVE) {
            return "DENY_PROVIDER_QUARANTINED";
        }
        if (session.revoked()) {
            return "DENY_SESSION_REVOKED";
        }
        if (session.loginEpoch() != policy.epoch()) {
            return "DENY_STALE_TRUST_EPOCH";
        }
        if (!session.tenant().equals(requestedTenant)) {
            return "DENY_TENANT";
        }
        return "ALLOW " + session.id();
    }

    void quarantine(String provider) {
        Policy current = policies.get(provider);
        if (current == null) {
            throw new IllegalArgumentException("Unknown provider");
        }
        policies.put(provider, new Policy(
                TrustState.QUARANTINED, current.epoch() + 1));
    }

    int revokeKnownSessions(String provider) {
        int revoked = 0;
        for (Map.Entry<String, LoginSession> entry : sessions.entrySet()) {
            LoginSession s = entry.getValue();
            if (s.provider().equals(provider) && !s.revoked()) {
                entry.setValue(new LoginSession(
                        s.id(), s.provider(), s.tenant(),
                        s.loginEpoch(), true));
                revoked++;
            }
        }
        return revoked;
    }

    void restoreAfterIndependentAttestation(String provider) {
        Policy current = policies.get(provider);
        if (current == null || current.state() != TrustState.QUARANTINED) {
            throw new IllegalStateException("Not quarantined");
        }
        // In production, security approvals + rotated keys
        // must be verified BEFORE calling this method.
        policies.put(provider, new Policy(
                TrustState.ACTIVE, current.epoch()));
    }

    void addSessionFromVerifiedReauthentication(
            String id, String provider, String tenant) {
        Policy policy = policies.get(provider);
        if (policy == null || policy.state() != TrustState.ACTIVE) {
            throw new IllegalStateException("Provider not active");
        }
        sessions.put(id, new LoginSession(
                id, provider, tenant, policy.epoch(), false));
    }

    public static void main(String[] args) {
        FederationIncidentGateDemo gate = new FederationIncidentGateDemo();

        System.out.println("Partner before: "
                + gate.check("partner-old", "south"));
        System.out.println("Corp before: "
                + gate.check("corp-old", "north"));

        gate.quarantine("partner-oidc");
        System.out.println("Partner quarantined: "
                + gate.check("partner-old", "south"));
        System.out.println("Corp unaffected: "
                + gate.check("corp-old", "north"));

        System.out.println("Revoked known partner sessions: "
                + gate.revokeKnownSessions("partner-oidc"));

        // Simulate an old session missed by the revoked inventory.
        gate.sessions.put("missed-edge", new LoginSession(
                "missed-edge", "partner-oidc", "south", 4, false));
        gate.restoreAfterIndependentAttestation("partner-oidc");

        System.out.println("Known old partner: "
                + gate.check("partner-old", "south"));
        System.out.println("Missed stale session: "
                + gate.check("missed-edge", "south"));

        gate.addSessionFromVerifiedReauthentication(
                "partner-new", "partner-oidc", "south");
        System.out.println("New verified partner: "
                + gate.check("partner-new", "south"));
        System.out.println("Wrong tenant: "
                + gate.check("partner-new", "north"));
        System.out.println("No session: "
                + gate.check("unknown", "south"));

        gate.sessions.put("unknown-provider", new LoginSession(
                "unknown-provider", "rogue-oidc", "south", 1, false));
        System.out.println("Unknown provider: "
                + gate.check("unknown-provider", "south"));
    }
}
~~~

Run:

~~~bash
javac FederationIncidentGateDemo.java
java FederationIncidentGateDemo
~~~

**Exact stdout:**

~~~text
Partner before: ALLOW partner-old
Corp before: ALLOW corp-old
Partner quarantined: DENY_PROVIDER_QUARANTINED
Corp unaffected: ALLOW corp-old
Revoked known partner sessions: 1
Known old partner: DENY_SESSION_REVOKED
Missed stale session: DENY_STALE_TRUST_EPOCH
New verified partner: ALLOW partner-new
Wrong tenant: DENY_TENANT
No session: DENY_NO_SESSION
Unknown provider: DENY_UNKNOWN_PROVIDER
~~~

**Critical limitations:** the demo uses a single-JVM `HashMap` with no cryptography, no trusted distributed policy store, and no live Redis/DB session or JWT deletion; never expose `quarantine`/`restore` as public user-callable endpoints. This demonstrates **authorization safety invariants after credible evidence**; real systems must enforce trust epochs on every request alongside Spring authentication, MFA/privileged authorization, and auditing.

## 33. Why Does the Demo Include Both Session Deletion and Epoch Guards?

Suppose batch inventory revocation misses a session because:
- A user logged out/re-logged in mid-scan.
- The index was unpopulated for a custom SAML/OIDC filter.
- Redis replica lag occurred or a node went offline.
- A session ID rotated.
- Workers/API Gateways held separate caches.
- A session dropped out of the principal index while keeping its `SecurityContext`.

**Session deletion** frees credentials and reduces request volume. **Epoch guards** force any session from an older policy epoch to reauthenticate. **Quarantine** blocks traffic even before batch revocation finishes.

In distributed setups, verify **atomic epoch updates and propagation**, out-of-order events, and fail-closed behavior if the policy store is unreachable. Never let an old node "read an old epoch" and accept tokens from a leaked key.

## 34. Race Conditions and Consistency Controls

| Race | Risk | Protection |
| --- | --- | --- |
| User logs in just as issuer is quarantined | New session stamped with old trust | Epoch CAS / active check right before persist |
| Batch deletion hits right as user re-logs in | Accidentally deletes fresh session | Target by source+epoch+time, idempotency |
| JWT validator key cache unrefreshed | Keeps accepting leaked signer | Emergency deny policy ahead of privileged access |
| Late Logout Token arrives post-restore | Wrongly deletes new session | Validate issuer/client/sid/sub + event semantics |
| Quarantine and restore events arrive out of order | Old ACTIVE overwrites QUARANTINED | Monotonic versions, compare-and-set, signed control plane |
| API request passed check, commits post-quarantine | Side effect still executes | Re-check near transaction/critical commit, idempotency |
| Stale regional policy cache | One region accepts while another denies | Propagation SLO/health, deny-on-staleness |
| IdP rotates key while SP retains old cert | Forged assertions still accepted | Explicit key removal + verification |
| Concurrent admin actions | Re-opened before incident closure | Approval workflow / state machine |
| Session inventory misses custom principals | Incomplete revocation | Independent epoch guard + reconciliation |

**Not every operation completed prior to policy change can be undone.** Incident response also needs fraud review, containment of exported data, and business-transaction rollback tools per policy.

## 35. Forensics: Preserving Evidence Before and After Containment

**Never delay blocking active danger just to gather more logs**, yet preserve cleanly:
- Incident timeline, first-seen timestamps, notices, key versions/serials/thumbprints.
- Versioned issuer/IdP metadata, JWKS fingerprints, `RelyingPartyRegistration`/`ClientRegistration` configs.
- Security config changes, deployments, signer rotations, feature flag changes.
- Auth decisions by issuer/client/tenant, failure codes, pseudonymized IP/device/session fingerprints.
- Redacted/hashed JWT `kid/iss/aud/jti` metadata; keep raw signed tokens strictly inside a forensic vault if legal/security approves.
- SAML Response/Assertion IDs, issuer/audience/Recipient, signing cert fingerprints; protect NameID/PII.
- Spring Session inventory snapshots, revocation counts, failure/retry counts.
- Refresh token grant records and OAuth client activity.
- HSM/KMS audit operations and secret access logs.
- SCIM provisioning, account linking, role changes, and privileged operations.
- Network/CDN/proxy logs for tracing.
- UTC timestamps with clock synchronization.
- Evidence owner, integrity hashes, retention, and chain of custody.

**Never share** private keys, SAML Assertions, access/refresh tokens, session cookies, or HARs carrying credentials in ordinary chat or ticket tools.

## 36. Monitoring Containment Effectiveness

Organization-implemented metrics (not all emitted by Spring Security by default):

| Metric | Purpose |
| --- | --- |
| `federation_trust_quarantined_profiles` | Currently locked profiles |
| `federation_trust_epoch_version` | Epoch/version per region |
| `federation_login_blocked_total` | New logins blocked from quarantined sources |
| `federation_api_token_rejected_total` | JWT/opaque tokens rejected due to incident |
| `federation_sessions_revoked_total` | Batch sessions deleted/marked revoked |
| `federation_session_epoch_denied_total` | Sessions missed by index yet blocked by epoch |
| `federation_logout_event_invalid_total` | Invalid back-channel/SLO/SET events |
| `federation_jwks_stale_instances` | Verifiers still holding old compromised keys |
| `federation_partner_restore_approvals` | Re-enablement approval records |
| `federation_token_introspection_failures` | AS/introspection dependencies |
| `federation_cross_tenant_denials_total` | Lateral-movement risk |
| `federation_reauthentication_success_total` | Fresh sessions post-restore |
| `federation_revocation_propagation_seconds` | Cluster-wide deny propagation time |

**Never place raw subjects, emails, user IDs, or token/JWK values in metric labels**; use allowlisted registration IDs, environment, region, and reason enums. Logs need correlation IDs and audit access controls.

**Measure this:** immediately after quarantine, how many requests still succeed from the affected source? Whenever the answer is non-zero outside approved exceptions, containment is incomplete.

## 37. Communicating with Partners and Customers

Communications must balance accuracy with security:

1. State the confirmed/suspected incident type, UTC timestamps, and expected scope.
2. List temporarily disabled login/access services and the security rationale.
3. Never disclose private signing keys, raw JWTs, logout tokens, or targeted account names.
4. Provide an independent authenticated support channel, not only email from the compromised IdP.
5. Distinguish **restored login availability** from **confirmed compromise eradication**.
6. Communicate required reauthentication, password resets, or MFA re-enrollment per policy.
7. Update timelines and facts realistically without overpromising exact recovery times.
8. Coordinate legal/privacy on mandatory contractual or regulatory notifications.
9. State clearly which party owns revoking downstream tokens/sessions.
10. Offer contingency workflows for customers facing disrupted critical operations while protecting break-glass.

**Never distribute lists of affected users wider than operational need.** Operational incident updates need appropriate access controls.

## 38. Criteria to Re-Enable a Partner / Issuer

Do not restore trust merely because a login page loads. Evidence-backed checklist:

- [ ] Compromise source isolated and root cause sufficiently controlled against recurrence.
- [ ] Security/partner ownership verified out-of-band.
- [ ] New key/signing certificate generated and stored in a trusted HSM/KMS/secret store.
- [ ] Issuer/entityID, endpoints, audience/client IDs, and cert fingerprints independently verified.
- [ ] Old compromised key/cert rejected at every RP, Resource Server, and gateway.
- [ ] Trust policy epoch bumped and propagated across all regions and nodes.
- [ ] Old sessions from the affected source denied, including any missed by session indexes.
- [ ] Refresh grants and API access token policies handled per blast radius.
- [ ] Fresh SAML/OIDC logins pass full protocol verification + anti-replay.
- [ ] Local accounts, group mappings, SCIM JIT/provisioning, and tenant memberships audited.
- [ ] Downstream partners/RPs confirm updated trust.
- [ ] Canary traffic for affected and unaffected tenants passes.
- [ ] Fail-closed verified on policy-store/JWKS/introspection outages.
- [ ] Break-glass, audit logs, metrics, and alerts operational.
- [ ] Incident Commander and security owner sign off on restoration.
- [ ] Immediate re-quarantine path ready if bad signals reappear.

**Proof of restoration is a full suite of tests and approvals**, not "a JWT signature verified with the new key" alone.

## 39. Incident Test Matrix — Trust and Key Compromise

| # | Test case | Expectation |
| --- | --- | --- |
| 01 | Partner OIDC issuer ACTIVE, valid ID Token | Login passes normal policy |
| 02 | Partner quarantined while sending validly signed ID Token | Login blocked |
| 03 | Partner quarantined while sending OAuth callback code | No session created |
| 04 | Partner quarantined, SAML Response validly signed with old key | Not accepted |
| 05 | Forged token signed with compromised key, matching `iss` | Rejected at verifier |
| 06 | Forged token with `iat` predating incident | `iat` cannot bypass |
| 07 | JWKS cache still holds old compromised key | Emergency deny still blocks |
| 08 | Client metadata URI altered without authorization | Not auto-trusted |
| 09 | New signer sent by partner over compromised channel | Pending approval, inactive |
| 10 | Independently verified new signer | Restorable after full QA |
| 11 | Old compromised signing key re-added in overlap | QA fails |
| 12 | SAML Assertion wrong Audience/Recipient despite new key | Rejected |
| 13 | SAML IdP entityID mismatches expected | Rejected |
| 14 | Replayed SAML Response after restore | Rejected |
| 15 | New JWT has wrong Resource Server `aud` | Rejected |
| 16 | JWT `kid` references key outside issuer | Rejected |
| 17 | Resource Server uses `jku` from unverified JWT | Security QA fails |
| 18 | Old client secret after rotation | Rejected by AS |
| 19 | Old refresh token after grant revocation | Cannot mint new access tokens |
| 20 | Old service keytab after rotation | Invalid for ticket acceptance |

## 40. Test Matrix — Sessions, Tokens, and Logout

| # | Test case | Expectation |
| --- | --- | --- |
| 21 | Active Partner Spring session predating quarantine | Next request denied |
| 22 | Corp session outside blast radius | Keeps working per policy |
| 23 | Batch revocation misses Partner session | Epoch guard still denies |
| 24 | User creates session right as quarantine hits | Not persisted as trusted session |
| 25 | App session logged out while JWT access token unexpired | API denies per incident policy |
| 26 | Refresh token revoked while cached JWT unexpired | RS emergency deny still blocks JWT |
| 27 | OAuth opaque token introspection `active=false` | Denied |
| 28 | Compromised issuer returns introspection `active=true` | Local quarantine overrides and denies |
| 29 | Valid OIDC Back-Channel Logout Token in trusted state | Logs out exact issuer/client/sid |
| 30 | OIDC Logout Token wrong issuer/signature/audience | Rejected; other sessions untouched |
| 31 | OIDC Logout Token signed by compromised key during quarantine | Never treated as trusted admin source |
| 32 | IdP-initiated SAML SLO while issuer trusted | Policy and protocol checks apply |
| 33 | SAML SLO misses offline SP | Local emergency deny stays active |
| 34 | `SessionRegistry` holds single-pod sessions only | Distributed test catches gap |
| 35 | Spring Session principal index shares username across two IdPs | No cross-issuer revocation |
| 36 | Two revocation jobs run concurrently | Idempotent; never revives sessions |
| 37 | Revocation events arrive out of order | Higher monotonic version wins |
| 38 | Trust store unavailable during incident | Fails closed per risk policy |
| 39 | JWT AS outage with compromised-signature token | Never falls back to accepting |
| 40 | Browser session revoked while HTTP request is in flight | Critical operations re-check near commit |
| 41 | Same user holds sessions across multiple devices | Revoked per approved scope |
| 42 | Tenant North revoked while South uses unaffected source | No unwarranted deletion if tenant-scoped |
| 43 | Shared issuer signing key across multiple tenants | Blocks every tenant in key blast radius |
| 44 | Reauthentication post-restore with new epoch | New session passes per policy |
| 45 | Old partner session post-restore | Denied; cannot be reused |
| 46 | Local account disabled after IdP compromise | Denied even with new token |
| 47 | Forged `admin` group inside otherwise valid token | Denied by local role mapping/tenant policy |
| 48 | Stale multi-region cache leaves issuer ACTIVE | Test catches propagation SLA breach |
| 49 | Kerberos service account rotated while old keytab remains on pod | Node fails; controlled quarantine/rotation |
| 50 | Security evidence endpoint leaks raw tokens | QA fails; fix incident logging |

## 41. Runbook by Operational Phase

### A. Immediate Activation After Detection

1. Open the incident, assign IC, severity, UTC timeline, and an independent communication channel.
2. Verify initial signals and collect trust profile/credential fingerprints safely.
3. Inventory affected clients, SPs, RPs, Resource Servers, tenants, and session stores.
4. Enforce **QUARANTINED** across all enforcement points; verify new logins and tokens reject.
5. Protect emergency admin access from using the same compromised issuer.
6. Preserve evidence and halt privileged operations if risk requires.

### B. Containment + Revocation

1. Increment the trust epoch and distribute integrity-protected policies.
2. Disable new federation exchanges and JIT provisioning.
3. Scan/index and delete/revoke Spring sessions by trusted source/tenant scope.
4. Revoke refresh grants/client credentials at the AS; contact the AS owner.
5. Enforce emergency denies for JWT/opaque tokens across all RSs.
6. Notify downstream partners to update trust; never assume logout auto-propagates.
7. Block delegated services and rotate service keys per blast radius.
8. Record counts, missed sessions, and propagation times.

### C. Eradication and Recovery

1. Confirm the root cause is addressed enough to stop re-theft of keys.
2. Rotate signing/encryption keys in a clean environment with independent attestation.
3. Update trusted metadata/JWKS/certs, client registrations, and related SPNs/keytabs.
4. Remove old compromised trust everywhere and purge stale caches.
5. Audit accounts, group mappings, privileged grants, and SCIM events.
6. Run full negative tests plus canaries.
7. Re-enable the issuer via staged approval; force reauthentication of old sessions.
8. Monitor 401/403/login anomalies and unknown-key attempts.

### D. Post-Incident

1. Reconcile the incident timeline and forensic evidence.
2. Confirm zero successful access from the compromised source after the quarantine threshold.
3. Close gaps in inventory/indexing and central policy propagation.
4. Tighten token lifetimes, revocation support, and key isolation.
5. Re-drill multi-region, token, and session scenarios.
6. Complete customer/partner notices and legal obligations.
7. Archive decisions/approvals, postmortem, follow-up owners, and deadlines.

## 42. Tabletop Exercises: Questions You Must Be Able to Answer

**Scenario 1 — Partner SAML IdP key leaks; 12 RPs trust it.**  
Who can disable trust centrally? How do self-managed RPs receive emergency notices? Are all old keys purged before restoration? Could an offline SP still accept leaked-key assertions once it comes back online?

**Scenario 2 — OIDC signer leaks; 6 APIs validate JWTs offline.**  
Do APIs have per-API issuer allowlists and kill switches decoupled from JWKS? How long do JWTs live? Which APIs hold stale key caches? How do you prove zero access after quarantine?

**Scenario 3 — Partner serves three tenants; only one reports compromise.**  
Is the signing key shared or are trust relationships separate? Quarantine by key blast radius or tenant mapping? Who approves keeping the remaining tenants live? Could users sharing emails across two issuers get cross-linked?

**Scenario 4 — Redis Spring Session outage during batch mass logout.**  
Does the policy store (separate from Redis) fail closed? If apps defer session deletion until Redis returns, do stateless APIs still accept JWTs? Are reconciliation and retries ready?

**Scenario 5 — OP Logout Token signed with the compromised signer.**  
Should the app accept it to delete all users' sessions? No; an event from a compromised signer is not independent admin proof. A separate control-plane revocation mechanism is mandatory.

**Scenario 6 — Partner rotated its cert and asks for urgent restoration.**  
Do we have independent ownership attestation? Are old signers rejected at every RP? Are old sessions blocked via epoch? Have role-mapping and tenant-isolation tests passed?

**Scenario 7 — OAuth client secret leaked while signer key stays safe.**  
You can narrow scope to client credentials and grants without blocking the entire issuer if evidence supports it—provided that client secret was not shared across integrations.

**Scenario 8 — Operators need break-glass while all partner logins are disabled.**  
Break-glass must use an independent factor/source with heightened auditing, never "temporarily accept any issuer."

## 43. Anti-Patterns Strictly to Avoid

1. **"Rotating JWKS ends the incident":** JWTs and caches can keep trusting the old key.
2. **"Deleting the web portal session revokes API tokens":** separate credential namespaces.
3. **"One OIDC/SAML logout logs out every partner":** protocol/participant coverage is incomplete.
4. **"The `iat` claim proves the token predates the leak":** an attacker holding the signing key can forge `iat`.
5. **"Issuer is valid so the token must be safe":** the issuer's private key itself leaked.
6. **"Try every JWK until one verifies":** enforce strict issuer/key binding.
7. **"Accepting a logout signal from a compromised IdP as admin proof":** requires an independent control plane.
8. **"`SessionRegistryImpl` covers every pod":** local JVM memory by default.
9. **"Deleting by email principal name is precise enough":** causes cross-issuer identity collisions.
10. **"Temporarily skip SAML/ID Token signatures during partner issues":** turns an incident into an authentication bypass.
11. **"Keep the compromised cert another month for overlap":** keeps allowing forgeries.
12. **"Disabling the signing key also closes an SP decryption leak":** confidentiality scope differs.
13. **"Auto-register a new issuer from token claims":** attacker-controlled trust enrollment.
14. **"Session-deletion campaigns without epoch guards":** vulnerable to races and missed indexes.
15. **"All access is safe once the dashboard shows 0 active sessions":** in-flight requests and RS caches may remain open.
16. **"Re-open as soon as one test login succeeds":** skips identity mapping, tenants, revocation, canaries, and approvals.

## 44. Pre-Incident Readiness Checklist

- [ ] Trusted issuer/IdP registry records owners, environments, source protocols, and tenant mappings.
- [ ] All signing/enc/client/TLS/keytab secrets and their consumers are inventoried.
- [ ] Rotation owners, KMS/HSM access, and out-of-band partner contacts are verified.
- [ ] A quarantine switch exists independent of remote issuer metadata/JWKS.
- [ ] Resource Servers enforce deny policies for compromised issuers/keys even when JWT signatures verify.
- [ ] Opaque token introspection cache TTLs and fail-closed behavior are tested.
- [ ] Refresh token/grant revocation APIs have owners and playbooks.
- [ ] Spring Session stores/indexes trace local sessions back to verified sources.
- [ ] Monotonic trust epochs/revocation versions are enforced on critical requests.
- [ ] Sessions can be deleted by exact scope and reconciled across nodes.
- [ ] OIDC back-channel logout validates signatures, issuer, audience, `sid`/`sub`, and replay where used.
- [ ] SAML SLO is treated as best-effort with local revocation fallback.
- [ ] Dynamic issuers/certificates are never trusted from unverified input.
- [ ] JWT access tokens are short-lived or paired with emergency denies matching latency SLAs.
- [ ] Sessions/identities link via issuer+subject or verified SAML namespaces.
- [ ] Roles/tenants/object authorizations are never derived blindly from provider login alone.
- [ ] IdP-initiated SAML and JIT provisioning have separate kill switches.
- [ ] Secret leaks, metadata tampering, and signing key compromises all have test cases.
- [ ] An independent, approved, audited break-glass identity provider exists.
- [ ] Policy propagation monitoring covers all regions, nodes, and partners.
- [ ] Forensic evidence retention, redaction, and custody policies exist.
- [ ] Customer/partner communications and legal escalation paths exist.
- [ ] Re-enablement gates require security approvals plus signed canary passes.
- [ ] Rehearsals have covered at least JWT signer compromise and SAML IdP signing key compromise.

## 45. Conclusion and Memory Formula

Federation incident response is **a problem of revoking *trust* before revoking each *credential* type**. A leaked signing key lets forged tokens/assertions pass verifiers; an HTTP session can outlive IdP disablement; an already-issued JWT does not vanish when its refresh token is revoked. For reliable containment:

**Verified incident → scoped trust quarantine → per-request emergency deny + trust epoch → revoke sessions/grants/tokens → independent key replacement → verify every consumer → forced reauthentication → tenant authorization → staged restore.**

In Spring Security, combine **client/RP registration trust controls**, **JWT Resource Server issuer/key/audience policies**, **indexed Spring Session invalidation**, **OIDC Back-Channel Logout/SAML SLO where appropriate**, and **application-owned domain authorization**. **No single logout API guarantees stopping every OAuth, SAML, Kerberos, and local session.** Verify with negative tests and telemetry from every consumer, not the IdP dashboard alone.

### Official Documentation for Implementation and Review

- NIST SP 800-61 Rev. 3 (April 2025) — Incident Response Recommendations and Considerations for Cybersecurity Risk Management: https://csrc.nist.gov/pubs/sp/800/61/r3/final
- NIST SP 800-57 Part 1 — Key Management Recommendations: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- Spring Security — Session Management and concurrent sessions: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Session — API, `SessionRepository` and `FindByIndexNameSessionRepository`: https://docs.spring.io/spring-session/reference/api.html
- Spring Security — OIDC Logout, RP-initiated and Back-Channel Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- OpenID Connect Back-Channel Logout 1.0: https://openid.net/specs/openid-connect-backchannel-1_0.html
- Spring Security — SAML2 Single Logout: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security — OAuth2 Resource Server JWT validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8417 — Security Event Token: https://www.rfc-editor.org/rfc/rfc8417
- OpenID Continuous Access Evaluation Profile 1.0: https://openid.net/specs/openid-caep-1_0.html
- OpenID Connect Core — ID Token validation/issuer/audience: https://openid.net/specs/openid-connect-core-1_0.html
- OASIS SAML 2.0 Core/Profiles/Metadata: https://www.oasis-open.org/standard/saml/
- RFC 4120 — Kerberos V5: https://www.rfc-editor.org/rfc/rfc4120
