# Managing Certificates, Domains, and Time-Bound Dependencies

## 1. Why Are Time-Bound Dependencies an Operational Risk?

Cloud applications often depend on numerous resources with expiration dates or periodic renewal requirements: TLS certificates, domain registrations, DNS zones, API keys, client secrets, signing keys, tokens, licenses, support contracts, code-signing certificates, and partner credentials. A dependency may operate smoothly for months and then cause a sudden outage when it expires, is revoked, or changes without the system updating.

For example, an expired certificate causes clients to reject HTTPS connections; an expired domain registration can suspend the domain or cause loss of control; an expired API key prevents workers from calling a partner; and a rotated signing key whose new public key consumers have not yet fetched can reject valid tokens. These failures frequently strike multiple services simultaneously because they share a single underlying resource.

**Lifecycle management** covers managing the entire dependency lifecycle: creation, registration, distribution, usage, monitoring, renewal/rotation, revocation, and retirement. This work requires inventory, owners, expiration dates, dependency mapping, automation, post-change verification, and audit evidence.

In the **CLOUD_ARCHITECTURE** module, managing time-bound dependencies is an operational capability protecting availability, security, and resilience. The goal is detecting expirations early, renewing under control, and proving every consumer has switched to the valid version.

### Learning Objectives

After this lesson, you will be able to:

1. Inventory certificates, domains, secrets, tokens, keys, and licenses with expirations.
2. Distinguish expiration, rotation, renewal, revocation, and replacement.
3. Design PKI/TLS certificate lifecycles and automated renewals.
4. Manage domain registrations, DNS zones, delegation, and DNSSEC.
5. Rotate API keys, client secrets, and signing keys without disruption.
6. Identify owners, consumers, dependency graphs, and approval workflows.
7. Configure alerts based on remaining lifetime and dependency criticality.
8. Rehearse expiration incidents, accidental revocations, and failed rotations.

## 2. Classifying Time-Bound Dependencies

Not everything with an expiration date is renewed the same way. Classify dependencies by verification method, blast radius, replacement mechanism, and automation feasibility.

| Type | Examples | Action Before Expiration |
|---|---|---|
| **TLS/server certificate** | Certificates for websites, API gateways, ingress, service endpoints | Renew, deploy new certificate, verify chain/SAN, and reload |
| **Client certificate/mTLS** | Certificates between services or partners | Issue new cert, distribute trust chain, shift clients/servers with overlap |
| **Signing certificate/key** | JWT/SAML signing, code signing, artifact signing | Publish new public key, overlap verification, switch signer, retire old key |
| **Domain registration** | `example.com` or product domains | Renew at registrar, verify payment/contacts/locks |
| **DNS delegation/zone** | NS, DS, CNAME, TXT, MX, validation records | Keep zones/records accurate, update delegation and DNSSEC |
| **API key/client secret** | Payment provider, email service, SaaS integrations | Issue new credential, distribute to consumers, cut over, revoke old credential |
| **Access token/refresh token** | OAuth tokens, session tokens | Renew/refresh per protocol, revoke when needed |
| **License/subscription** | Database engine, security agent, monitoring platform | Renew contract/entitlement and verify enforcement |
| **SSH key/host key** | Automation, bastion, host identity | Rotate public/private keys or trust entries with overlap |
| **Support/contract entitlement** | Cloud support plan, partner support | Renew and verify account/resource coverage |
| **Trust anchor/root/intermediate CA** | CA hierarchy and trust stores | Manage key ceremonies, cross-signing/rollovers, trust-store rollouts |

### 2.1. Distinct Time Milestones

- **Not Before / Not After:** start and end of certificate validity.
- **Registration expiry:** date a domain registration must be renewed.
- **Credential expiration:** point at which a secret/token is no longer accepted.
- **Rotation deadline:** internal policy milestone requiring replacement even before expiration.
- **Revocation:** invalidation before expiration due to compromise or trust change.
- **Contract renewal date:** renewal date for a contract or license.

You cannot rely on a single `expires_at` field for every dependency type. Record timezone, time source, expiration semantics, and required actions explicitly.

## 3. Inventory and Ownership

You cannot manage what is neither discovered nor recorded. Inventory must cover cloud-platform-managed resources, SaaS, registrars, partners, and credentials stored in CI/CD.

### 3.1. Minimum Fields

| Field | Meaning |
|---|---|
| Asset ID | Unique identifier in the inventory |
| Type | Certificate, domain, secret, key, license... |
| Identifier | Domain/FQDN, ARN/resource ID, certificate fingerprint, or logical name |
| Environment | Production, staging, development |
| Owner | Technically accountable team/person |
| Business owner | Person confirming business impact |
| Issuer/provider | CA, registrar, SaaS, or issuing party |
| Valid from / expires at | Validity window |
| Renewal/rotation method | ACME, API, manual approval, provider workflow |
| Consumers | Services, workloads, partners, clients using it |
| Dependency criticality | Impact level upon expiration |
| Secret reference | Reference to secret manager; never store plaintext |
| Runbook | Renewal/rotation/recovery procedure |
| Last verified | Most recent live state verification |
| Evidence | Ticket, audit event, certificate fingerprint, or provider receipt |

### 3.2. Owners Must Be Specific

A generic team name like Platform is insufficient without an on-call responder or escalation path. Each asset needs a primary owner, backup owner, and business owner. A brand domain may be owned by marketing/legal at the registrar level while DNS and certificates are operated by platform.

Never put private keys, API secrets, or refresh tokens into the inventory. Store only secret references and non-sensitive metadata; access to secret values stays inside the secret manager.

### 3.3. Automated Inventory Discovery

Combine cloud resource inventories and certificate managers; certificate transparency/hostname discovery within managed domain scope; DNS zone/registrar APIs and domain portfolio reports; secret manager metadata and rotation configurations; permission-scoped CI/CD variable inventories; SaaS admin APIs, license portals, and procurement records; and internal TLS scanners probing live endpoints.

Discovery does not replace owner confirmation. A discovered endpoint might be legacy, partner-managed, or out of scope; establish a workflow to verify and assign owners.

## 4. Dependency Graphs: Knowing What Will Be Impacted

A single certificate or secret often serves multiple consumers. Knowing a certificate expires soon is not enough; you must know which services will break if it is rotated or revoked.

~~~mermaid
flowchart TD
    CA["Certificate authority"] --> Cert["API certificate"]
    Cert --> Gateway["API gateway"]
    Gateway --> Booking["Booking service"]
    Gateway --> Partner["Partner integration"]
    Cert --> Monitor["Synthetic TLS monitor"]
    Secret["Payment client secret"] --> Booking
    Secret --> Worker["Payment reconciliation worker"]
    Domain["Public domain"] --> DNS["DNS zone / delegation"]
    DNS --> Gateway
    DNS --> Web["Web application"]
~~~

Each edge should indicate dependency type:

- **Runtime:** consumer needs the credential to process requests.
- **Trust:** consumer needs the public key/CA to verify peers or tokens.
- **Discovery:** consumer relies on DNS, metadata endpoints, or JWKS.
- **Control plane:** pipeline needs credentials to deploy certificates.
- **Business/contract:** domain or license tied to branding/contracts.

The dependency graph should support bidirectional queries: given an expiring asset, which consumers are affected; given a service outage, which dependencies could cause it.

## 5. PKI and TLS Certificate Lifecycles

TLS certificates bind a public key to an identity verified by a CA under a profile. In TLS server authentication, clients verify the certificate chain, validity window, hostname/SAN, purpose, and other trust conditions.

### 5.1. Certificate Chains

~~~mermaid
flowchart TD
    Root["Trusted root CA"] --> Intermediate["Intermediate CA"]
    Intermediate --> Leaf["Leaf certificate: api.example.com"]
    Leaf --> Endpoint["Load balancer / ingress / service"]
    Client["Client trust store"] -. "validates chain + hostname + time" .-> Endpoint
~~~

The leaf certificate's private key must be protected. Public certificates can be distributed broadly, but private keys must never enter source repositories, public images, logs, or tickets.

### 5.2. SANs and Hostnames

The hostname accessed by clients must match an appropriate Subject Alternative Name (SAN) in the certificate. Common Name should not be relied upon as the sole hostname verification mechanism in modern deployments. Wildcard certificates have bounded scope (typically a single DNS label); verify CA policies and client behavior before use.

Do not share a single wildcard private key across every environment if the blast radius is too large. Issue separate certificates per environment/zone/service and distribute them automatically via a certificate manager.

### 5.3. Certificate Lifecycle Workflow

1. Define hostnames, SANs, environment, issuer, and consumers.
2. Generate the key pair in a protected location; prefer non-exportable HSM/managed key stores where appropriate.
3. Generate a CSR and submit to the CA following validation procedures.
4. Receive the certificate and verify chain, SANs, validity, EKU, and fingerprint.
5. Store certificate/key in an appropriate store; grant access to the runtime identity.
6. Deploy to load balancers, ingress, or services.
7. Reload/restart safely if required by the platform.
8. Verify the TLS handshake from a realistic client perspective.
9. Monitor expiration and auto-renew ahead of threshold.
10. Revoke old certificates once consumers have migrated or an incident occurs.

## 6. Automated Certificate Renewal with ACME

ACME automates domain validation and certificate issuance by ACME-capable CAs. An ACME client proves domain control via challenges such as HTTP-01, DNS-01, or TLS-ALPN-01 depending on CA support and use case.

### 6.1. Common Challenge Types

| Challenge | Verification Method | Best Suited For |
|---|---|---|
| HTTP-01 | CA fetches token over HTTP at a well-known path | Public hosts reachable on the required port |
| DNS-01 | Create a TXT record under the challenge name | Wildcards, private services with DNS automation, or environments not exposing HTTP |
| TLS-ALPN-01 | Challenge over TLS/ALPN on the endpoint | Supported edge/proxy architectures |

DNS-01 requires tightly scoped DNS write permissions. Never give every ACME client a full-admin registrar/DNS account API token when the provider supports zone/record-scoped tokens.

### 6.2. Renewal Does Not Equal Deployment

An ACME client may obtain a new certificate while the load balancer keeps serving the old one. Pipelines must verify whether the new certificate is stored with the right hostnames; whether runtime secret/certificate references updated; whether the load balancer/ingress reloaded; whether the external endpoint serves the new certificate; whether the full intermediate chain is present; and whether legacy consumers pin fingerprints or trust a changed CA.

Alert separately on renewal failures versus deployment/serving failures. Probing the live endpoint provides stronger evidence than merely seeing a renewal job exit 0.

### 6.3. Overlap and Certificate Rollover

For mTLS or client certificates, a dual-trust overlap phase is often required:

1. Issue the new certificate.
2. Distribute the new trusted public certificate/CA to peers.
3. Verify peers accept both old and new certificates.
4. Cut over clients/servers to the new certificate.
5. Monitor handshakes and authentication errors.
6. Revoke/remove the old certificate once all consumers have migrated.

Never remove old trust anchors before confirming every peer has updated. Conversely, do not leave old credentials active indefinitely after rollover finishes.

## 7. Domain Registration, DNS, and Delegation

Domain registration is the right to register and maintain a domain name via a registrar/registry. A DNS zone holds records mapping names to addresses or services. The two layers interact yet remain distinct: renewing a domain does not fix broken DNS records, and working DNS does not prove domain registration has long remaining validity.

### 7.1. Domain Components

- **Registrar:** manages registration, renewals, transfers, and account contacts.
- **Registry:** operates the TLD and registry-level registration records.
- **Registrant:** legal/organizational entity registering the domain.
- **Authoritative DNS:** serves authoritative answers for DNS records.
- **Nameserver delegation:** NS records pointing to authoritative DNS.
- **DNSSEC:** signs DNS data and establishes a validation chain via DS/DNSKEY.

### 7.2. Common Record Types

| Record | Function | Example Use Case |
|---|---|---|
| A | Name to IPv4 | `api.example.com` |
| AAAA | Name to IPv6 | Dual-stack endpoint |
| CNAME | Alias to another name | App pointing to managed endpoint |
| NS | Nameserver delegation | Delegate subdomain |
| SOA | Zone management metadata | Serial/authority parameters |
| MX | Mail exchanger | Email domain |
| TXT | Text/verification/policy | ACME DNS-01, SPF, domain verification |
| CAA | Restricts CAs allowed to issue certificates | Permit only chosen CAs |
| DS/DNSKEY | DNSSEC components | Chain of trust |

### 7.3. Registrar Account Controls

Critical domains need auto-renew enabled with valid payment methods; current registrant/contact info and recovery channels; MFA/phishing-resistant authentication on registrar accounts where supported; appropriate domain/transfer locks; separation of roles across viewing, DNS edits, renewals, and transfers; backed-up registration details, expiry dates, and emergency access; and multi-person/team alerting rather than relying on one personal inbox.

Auto-renew does not guarantee every renewal succeeds: payments can fail, accounts can lock, or registries can enforce special conditions. Always verify registration status after renewal.

## 8. DNSSEC and Trust Chain Changes

DNSSEC provides authenticity and integrity for DNS records via digital signatures; it does not encrypt DNS queries. When enabling or rotating DNSSEC, DS records in the parent zone must match DNSKEY records in the child zone according to rollover procedures. Mismatched DS/DNSKEY records can cause validating resolvers to reject the entire zone.

### DNSSEC Change Procedure

1. Inventory registrar, parent zone, authoritative nameservers, current DNSKEY, and DS records.
2. Plan the key rollover and determine overlap windows from TTL/cache behavior.
3. Publish the new DNSKEY in the authoritative zone.
4. Update DS at the registrar/parent in the exact order required by the rollover method.
5. Verify across multiple validating resolvers and authoritative servers.
6. Monitor SERVFAILs and DNSSEC validation errors.
7. Retire the old key only after the new chain operates stably.

Never edit DS records casually or delete old keys and swap DS simultaneously without understanding your DNS provider's rollover procedure.

## 9. Secrets, API Keys, and Client Secrets

Secrets are typically issued per consumer with specific permissions. Their lifecycle spans issuance, distribution, usage, rotation, revocation, and auditing.

### 9.1. Zero-Downtime Rotation Model

~~~mermaid
flowchart TD
    Old["Old credential active"] --> Create["Create new credential"]
    Create --> Distribute["Store and distribute new secret"]
    Distribute --> Dual["Allow old + new during overlap"]
    Dual --> Switch["Move consumers to new credential"]
    Switch --> Verify["Verify successful use of new credential"]
    Verify --> Revoke["Revoke old credential"]
    Revoke --> Audit["Audit and remove stale references"]
~~~

Not every provider supports two active keys simultaneously. When only one active key is allowed, schedule a maintenance window or use a proxy/credential broker for safe cutover.

### 9.2. Rotation Procedure

1. Identify all consumers and owners.
2. Create the new credential at the provider.
3. Store it in the secret manager under a new version.
4. Roll out updates across consumers per rollout strategy.
5. Verify live requests succeed using the new credential.
6. Monitor error rates, authentication failures, and usage of the old key.
7. Revoke the old key after the defined overlap window.
8. Scan repositories/configs/logs for lingering copies.
9. Record fingerprint/version, timestamp, and operator; never store secret values.

If the provider exposes key IDs or usage logs, use them to prove consumers cut over. Never assume migration finished merely because the secret manager holds a new version.

### 9.3. Tokens and Refresh Tokens

Access tokens are typically short-lived and re-acquired per protocol; refresh tokens can live longer and require strict protection. Never extend tokens in application code by overriding expirations. Use authorization servers, token rotation/reuse detection, and revocation as supported by the protocol/provider.

## 10. Signing Keys and Trust-Store Rollovers

Signing keys sign JWTs, SAML responses, packages, artifacts, or software releases. Swapping a private key without preparing consumers can cause valid tokens or new artifacts to be rejected.

### Key Rollover Strategy

- Generate a new key pair in KMS/HSM or an appropriate key store.
- Publish the new public key via JWKS/metadata/trust store.
- Ensure consumers refresh and accept the new key while still verifying the old key.
- Sign new payloads with the new key, including an explicit key identifier (`kid`).
- Monitor verification failures by `kid`/issuer/audience.
- Wait for old tokens/artifacts to expire or age out per policy.
- Retire/revoke the old key and archive evidence.

If a private key is compromised, do not wait for normal overlap: execute emergency revocation/rotation, assess signed tokens/artifacts, determine re-issuance needs, and notify consumers. Compromise scenarios differ fundamentally from routine expiration.

## 11. Licenses, Subscriptions, and Support Contracts

Some dependencies are not technical credentials yet still cause outages upon expiration:

- Database or commercial software licenses.
- Security/monitoring agent subscriptions.
- Managed service plans or quota entitlements.
- Support contracts and escalation entitlements.
- Partner API subscriptions or quota agreements.

Inventory should capture account/tenant, covered products/resources, renewal terms, procurement owner, technical owner, payment method, provider-stated grace periods if any, and expiration impact.

Never assume a grace period exists or systems will keep running past expiration. Check specific contracts and terms; never store sensitive payment details in operational files.

## 12. Planning Renewals and Rotations by Remaining Time

Do not alert only on expiration day. Establish milestones early enough for execution, approvals, distribution, and rollback.

### Example Certificate Schedule

| Remaining Time | Suggested Action |
|---|---|
| 60 days | Inventory check, confirm owner/consumers, check CA/automation |
| 30 days | Test renewal or staging deploy, verify chain and endpoints |
| 14 days | Escalate if not renewed/deployed; open priority incident/task |
| 7 days | Verify production serving certificates and all consumers |
| 72 hours | Critical alert if not cut over; activate runbook |
| 24 hours | On-call escalation and business owner notification |
| Expired | Incident; restore valid certificate and verify all endpoints |

Milestones are illustrative; certificate lifetimes, CA policies, providers, and automation capabilities may dictate different cadences.

### Risk-Based Prioritization

\[
Risk \approx Impact \times Likelihood \times Exposure
\]

Factor in remaining time, consumer count, and rollback feasibility. A production public API certificate serving millions of clients carries higher risk than a test-environment credential even with the same expiration date.

## 13. Alerting and Dashboards for Time-Bound Dependencies

Dashboards should answer which assets are nearing expiration, who owns them, which consumers are affected, renewal status, and whether verification evidence exists.

### 13.1. Metrics

| Metric | Purpose |
|---|---|
| `dependency_expiry_days` | Days remaining until expiration |
| `certificate_not_after_timestamp` | Exact certificate expiration timestamp |
| `certificate_renewal_success_total` | Count of successful renewals |
| `certificate_deployment_status` | Deployment state of new certificates |
| `tls_handshake_failure_total` | TLS handshake errors |
| `domain_renewal_status` | Domain renewal status |
| `secret_rotation_age_days` | Credential age relative to policy |
| `old_credential_usage_total` | Usage of old keys after cutover |
| `dependency_owner_missing` | Assets missing an owner |
| `expiry_inventory_coverage` | Percentage of assets with expiry and owner metadata |

Never put secret values, private keys, or full tokens into metrics/logs. Restrict labels to asset type, environment, provider, and criticality; keep high-cardinality asset IDs in the inventory system for drill-down rather than exploding metric backend cardinality.

### 13.2. Alert Routing

- Production certificates/domains: platform on-call and asset owner.
- Payment/API keys: integration owner and business operations.
- Signing keys/root CAs: security/key custodian and service owner.
- Licenses/support: procurement/contract owner and technical owner.
- Ownerless assets: governance queue to assign accountability.

Alerts should include `expires-at`, days remaining, owner, criticality, impacted consumers, runbook link, and renewal status. Never send generic “certificate expires soon” emails lacking concrete next actions.

## 14. Safe Automation

Automation cuts manual errors but needs guardrails:

- Idempotent jobs safe to rerun on scheduler retries.
- Renewal/rotation credentials scoped strictly to target assets/zones.
- Approvals for high-blast-radius changes.
- Staging/testing ahead of production whenever possible.
- New secrets written via secret manager APIs, never printed to logs.
- Deployments tracked with versions/fingerprints and rollback references.
- Verification run both externally and from real consumers.
- Old credentials revoked only after verification gates pass.
- Manual recovery paths if the CA, registrar, or secret provider suffers an outage.

### 14.1. Reference State Machine

~~~text
DISCOVERED
  -> INVENTORIED
  -> RENEWAL_DUE
  -> RENEWED
  -> DISTRIBUTED
  -> DEPLOYED
  -> VERIFIED
  -> OLD_VERSION_RETIRED

Exception:
  -> BLOCKED_APPROVAL
  -> RENEWAL_FAILED
  -> DEPLOYMENT_FAILED
  -> ROLLBACK_REQUIRED
  -> INCIDENT
~~~

Never transition to `VERIFIED` merely because a new certificate was issued. Verification must prove consumers actively use the new version and traffic/handshakes succeed.

## 15. Post-Renewal and Post-Rotation Verification

Verify both the control plane and data plane after changes:

### Certificates

- Check certificate serial/fingerprint and NotAfter on live endpoints.
- Verify hostnames/SANs, chain, EKU, key algorithm, and trust.
- Test TLS handshakes from representative clients/runtimes.
- Check all regions, load balancers, ingress controllers, and edge endpoints.
- Confirm the old certificate is no longer served after the transition window.

### Domains/DNS

- Check domain status at registrar/registry.
- Query authoritative nameservers and multiple recursive resolvers.
- Verify NS, A/AAAA/CNAME, MX, TXT, CAA, and DS where relevant.
- Check DNSSEC validation and watch for SERVFAILs.
- Verify certificate/domain bindings after DNS changes.

### Secrets/API Keys

- Test authentication from every consumer.
- Inspect usage logs for both new and old keys.
- Verify no configs/files/images retain the old credential.
- Test rollback if supported by provider and permitted by policy.
- Revoke old credentials after verification and overlap.

### Licenses

- Verify entitlement/activation from runtime.
- Confirm exact licensed instance/node/seat counts.
- Verify support coverage and renewal receipts.

## 16. Incident Response When a Dependency Expires or Is Revoked

When an incident hits, prioritize restoring service while preserving evidence. Procedure:

1. Identify the expired/revoked asset, issuer/provider, and exact timestamp.
2. Determine affected consumers, regions, tenants, and business workflows.
3. Distinguish expiration, revocation, invalid chain, wrong hostname, DNS failure, bad secret, or quota/license denial.
4. Where appropriate, issue/renew a replacement credential per emergency runbook.
5. Distribute securely and roll out across consumers under control.
6. Verify from real clients, business SLIs, and dependency health.
7. If a credential was compromised, revoke immediately per incident policy; do not maintain a false-safety overlap.
8. Inspect every copy/config/cache/session holding the affected credential.
9. Notify owners/partners/customers per impact level and contractual obligations.
10. Record timeline, root cause, detection/recovery times, and corrective actions.

Never recover by disabling TLS verification, bypassing hostname validation, or deploying unverified certificates/secrets. That turns an availability issue into a security vulnerability.

## 17. Case Study: Managing Certificates and Secrets for a Booking Platform

**Context:** A booking platform operates a website, public API, partner API, payment integration, and multiple internal services running mTLS. The website/API use managed certificates; partners connect with client certificates; Payment API uses a client secret; internal tokens are signed with periodically rotated keys. Some dependencies are managed by other teams or external partners.

### 17.1. Initial Inventory

| Asset | Owner | Consumer | Expiry/Rotation | Criticality |
|---|---|---|---|---|
| `www` domain | Business/legal + platform DNS | Website, email | Registrar renewal | Critical |
| `api` TLS certificate | Platform team | Mobile/web clients, partners | Auto-renew + deploy verification | Critical |
| Partner mTLS certificate | Integration team | Partner gateway | Coordinated rollover | High |
| Payment client secret | Payment team | Booking API, reconciliation worker | Provider rotation | Critical |
| JWT signing key | Security/platform | Internal APIs, token consumers | Key rollover | Critical |
| Monitoring license | Operations/procurement | Observability agents | Contract renewal | Medium |

### 17.2. Operational Design

1. Inventory pulls certificate metadata from cloud managers, DNS/registrar reports, and secret metadata from the vault.
2. Every asset has a primary owner, backup owner, business owner, impacted consumers, and runbook.
3. Public API certificates use ACME/managed renewal with separate alerts for renewal and deployment.
4. Partner mTLS uses scheduled overlaps; partners confirm trust bundles before rotating client certificates.
5. Payment secrets create a new version, distribute via vault, roll out Booking API/workers, verify usage, and then revoke the old key.
6. JWT signing keys publish new JWKS keys before the signer switches; consumers refresh keys and verify tokens.
7. Domain auto-renew is enabled, registrar accounts are protected with MFA/locks, and expirations are monitored independently from DNS health.
8. Licenses track both procurement and technical owners; renewals are verified via entitlement checks.

### 17.3. Testing and Acceptance Criteria

- Zero critical production assets lack owners or expiration metadata.
- Public endpoints serve valid certificates with accurate SANs/chains.
- All partners accept the new certificate before the old one retires.
- Payment consumers use the new secret version; old key shows zero usage before revocation.
- JWT consumers verify the new key while honoring old tokens during policy overlap.
- DNS/registrar renewals are confirmed via provider status and live queries.
- Alerts reach the right owners with sufficient lead time; runbooks are rehearsed.
- Zero secrets/private keys appear in repositories, logs, or dashboards.

## 18. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Tracking expirations only in personal calendars | No backup owner, easily missed | Centralized inventory and multi-channel alerts |
| Renewing certificates without deploying | Endpoints keep serving expired certs | Verify fingerprint/NotAfter on live endpoints |
| Tracking expiry without tracking consumers | Consumers break when old keys are revoked | Dependency graphs and consumer verification |
| Rotating secrets and revoking old keys immediately | Unmigrated services suffer outages | Overlap, staged rollout, verify, then revoke |
| Sharing one certificate/private key too broadly | Huge blast radius if compromised | Separate identities/environments and scopes |
| Giving ACME clients full DNS admin tokens | Compromised client can alter entire zones | Scoped tokens and least privilege |
| Assuming auto-renew always succeeds | Payment/account/validation failures go unseen | Check renewal status and probe external endpoints |
| Deleting old keys before consumers refresh JWKS | Valid tokens get rejected | Publish new key, overlap caches, retire under control |
| Changing DNSSEC DS/DNSKEY out of order | Resolvers return SERVFAIL | Rollover plan and validating-resolver checks |
| Ignoring registrar because DNS still resolves | Losing domain control at registration expiry | Monitor registrar status independently |
| Logging secrets to debug auth failures | Credentials leak into telemetry | Redaction and logging metadata/fingerprints |
| Disabling TLS verification as a quick fix | Breaks peer auth, invites MITM | Issue valid certificates and fix trust chains |
| Never rehearsing renewal failures | Runbooks lack permissions or miss steps | Staging rehearsals and emergency drills |

## 19. Lifecycle Review Checklist

### Inventory and Dependencies

- [ ] All critical certificates, domains, DNS, keys, secrets, tokens, licenses, and contracts are inventoried.
- [ ] Assets have technical owners, business owners, backup owners, and runbooks.
- [ ] `expires_at`, renewal methods, issuers/providers, and evidence are documented.
- [ ] Dependency graphs map all consumers and blast radius.
- [ ] Inventory uses automated discovery and periodic reconciliation.

### Renewal and Rotation

- [ ] Certificate renewals validate SANs, chains, validity, and live endpoint serving.
- [ ] ACME/DNS challenges use least-privilege permissions.
- [ ] Registrar auto-renew, payment/contacts, MFA, and domain locks are verified.
- [ ] DNSSEC rollovers follow DS/DNSKEY procedures and validating-resolver checks.
- [ ] Secret/signing-key rotations include overlap, rollout, consumer verification, and revocation.
- [ ] Licenses/contracts have procurement and technical owners.
- [ ] Automation is idempotent, supports approvals/rollbacks, and never logs secrets.

### Monitoring and Incidents

- [ ] Alerts reflect days remaining, criticality, consumers, and owners.
- [ ] Separate alerts exist for renewed, deployed, served, and verified states.
- [ ] Usage of old keys post-rollover is monitored.
- [ ] Runbooks cover expirations, revocations, DNSSEC failures, and provider outages.
- [ ] Renewal/rotation and emergency compromise drills have been rehearsed.
- [ ] Recovery never relies on disabling TLS validation or weakening policies.

## 20. Hands-On Exercise

**Scenario:** A booking platform's primary domain expires in 35 days; the public API certificate expires in 18 days; the payment client secret will be revoked by the provider in 12 days; two partners pin an old client certificate; and a new JWT signing key was created, but some consumers cache JWKS for several hours. The inventory currently lacks an owner for one subdomain.

Build a plan to:

1. Rank risks by impact, likelihood, exposure, remaining time, and consumer count.
2. Assign owners/business owners and complete the inventory/dependency graph.
3. Schedule domain renewal and verify payment/contacts/registrar locks.
4. Renew and deploy the public API certificate; verify endpoints and chains.
5. Coordinate an mTLS rollover with partners including overlap and cutover confirmation.
6. Rotate the payment secret via secret manager, roll out across both consumers, monitor usage, and revoke the old key.
7. Publish the new JWKS key, tune cache/refresh behavior, and verify consumers before retiring the old key.
8. Set alerts at 30/14/7/3-day milestones aligned with criticality and lead times.
9. Write runbooks for failed renewal jobs and compromised credentials.
10. Define acceptance criteria and evidence for each asset.

**Self-check hints:** Domain registration and DNS health are distinct states. A renewed certificate does not mean endpoints serve it yet. Partner pinning and JWKS caches require explicit overlap windows. When secrets are compromised, emergency workflows prioritize immediate revocation and trust restoration rather than preserving old keys to avoid change.

## 21. Key Takeaways

Time-bound dependencies are operational assets requiring owners, inventories, consumer maps, and lifecycle workflows. Certificates, domains, DNS, secrets, signing keys, and licenses have distinct expiration and renewal mechanics—they cannot all be managed with one simple reminder calendar.

Successful renewal must be verified at the point of actual consumption. New certificates must be actively served; DNSSEC requires valid chains; new secrets must be used by every consumer before revoking old keys; new signing keys must be trusted by consumers; and domain registrations must be confirmed at the registrar. Automation, overlaps, staged rollouts, least privilege, lead-time-based alerts, and rehearsed runbooks keep expirations from turning into outages and prevent rotations from becoming security incidents.
