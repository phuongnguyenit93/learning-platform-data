# Testing Wrong Realm, Clock Skew, and Mismatched Keytabs

**Kerberos SSO can fail even when the user is already signed into Windows and the Spring Boot application is healthy.** Three critical root-cause groups that must be tested independently are **wrong Kerberos realm/trust path**, **clock skew across client–KDC–service**, and **service keytabs not matching the SPN, key version, encryption type, or key material used by the KDC**. These errors share similar browser symptoms: 401/Negotiate loops, password prompts, or `GSSException` in logs. However, their diagnosis and remediation are completely different.

This lesson belongs to **Spring Security – federation → SSO Testing**, focusing on **Kerberos V5 + SPNEGO HTTP Negotiate on the Spring Security Kerberos extension**, with MIT Kerberos and Active Directory (AD) examples. The goal is to build a **repeatable negative test plan**, pinpoint faults across client, KDC, SPN, JVM acceptor, keytab, or app layer, distinguish protocol conditions from business authorization, and avoid security-weakening workarounds.

**Four core principles:**

1. **Realms, SPNs, and principals are strictly scoped**. User `alice@CORP.EXAMPLE.TEST` is not automatically `alice@PARTNER.EXAMPLE.TEST`; a service ticket for `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST` cannot be presented to another service as the same proof.
2. **Clock skew is a freshness/replay bound**, not ticket lifetime. A common default in MIT Kerberos and Sun/Oracle JDK is **300 seconds (5 minutes)**, yet **this is configurable**; never assume every organization or deployment uses the same threshold.
3. **Keytabs hold service secret keys**, not just principal names. SPN, KVNO, enctype, key material, and file path/permissions must match the live ticket; never leak keytabs while debugging.
4. **Passing Kerberos ≠ app user permitted access**. After accepting a ticket, Spring must still map the verified principal to a local user, load authorities, and check tenant/resource policies. Never grant `ROLE_ADMIN` solely because the Kerberos exchange succeeded.

## 1. Learning Objectives and Scope

After this lesson, you will be able to:

- Trace the flow AS-REQ/TGT → TGS-REQ/service ticket → HTTP SPNEGO AP-REQ → Spring authentication.
- Explain how a **realm** differs from an AD domain suffix, DNS hostname, UPN suffix, or Spring tenant.
- Design wrong-realm tests with/without cross-realm trust and distinguish misconfiguration from valid referrals.
- Measure client/KDC/server clock skew in both directions, confirming `KRB_AP_ERR_SKEW` instead of guessing.
- Check SPN ownership, keytab contents, KVNO/encryption types, `KRB_AP_ERR_MODIFIED`, and `KDC_ERR_ETYPE_NOSUPP`.
- Run **read-only** diagnostic commands using MIT `klist`/`kvno`/`kinit` and Windows `setspn`/`klist`/`w32tm` in the proper environment.
- Write classification tests in **runnable Java 17** with deterministic stdout while understanding demo limitations.
- Organize real protocol-level tests with a test realm/AD staging, browsers, and Spring Security filters.
- Build a safe runbook for credential revocation, NTP sync, and keytab rotation.

**Out of scope:** bypassing Kerberos ticket checks, extracting user secrets, cracking tickets, or granting admin privileges. Test only against KDCs, service accounts, service principals, and environments you are authorized to administer.

## 2. How Does Kerberos SSO Work?

~~~text
Browser/OS                   KDC / AD Domain Controller             Spring SPNEGO service
    |                                   |                                 |
    | AS-REQ (login)                    |                                 |
    |---------------------------------->|                                 |
    |<--------------------- AS-REP + TGT                                  |
    |                                   |                                 |
    | TGS-REQ for HTTP/portal...        |                                 |
    |---------------------------------->|                                 |
    |<---------- TGS-REP: service ticket                                   |
    |                                                                     |
    | GET https://portal...                                            |
    |-------------------------------------------------------------------->|
    |<---------------------------------- 401 WWW-Authenticate: Negotiate |
    |                                                                     |
    | GET Authorization: Negotiate <SPNEGO token / AP-REQ>                 |
    |-------------------------------------------------------------------->|
    |                                                  Load service keytab |
    |                                                  GSS accept context |
    |                                                  Check AP authenticator
    |                                                  Verify service ticket |
    |                                                  Resolve user principal|
    |                                                  Load local permissions
    |<----------------------------------------- app response / challenge |
~~~

**Do not confuse:**
- **TGT**: ticket used to request service tickets, not what the browser sends directly to the Spring app.
- **Service ticket**: issued by the KDC for a service principal/realm; the server uses its corresponding secret to decrypt/verify it.
- **SPNEGO**: negotiation mechanism inside HTTP `Negotiate`; in practice it may pick Kerberos or another mechanism depending on environment. Never assume a `Negotiate` header always holds valid Kerberos.
- **Acceptor**: service/JVM receiving Kerberos tokens, typically using JAAS/GSS and a keytab.
- **KDC/realm trust**: governs which principals/services can receive tickets; **separate layer** from Spring `UserDetailsService`.

## 3. Distinguishing Realm, Domain, UPN, SPN, and Tenant

| Term | Example | Where Used? | Typical Mistake |
| --- | --- | --- | --- |
| Kerberos realm | `CORP.EXAMPLE.TEST` | KDC, ticket principal namespace | Thinking realm is always the DNS suffix |
| AD DNS domain | `corp.example.test` | Directory/DNS | Treating every UPN suffix as a realm |
| User principal | `alice@CORP.EXAMPLE.TEST` | Client/KDC | Splitting `alice` and merging across realms |
| HTTP service principal | `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST` | KDC/acceptor | Using backend machine name while browser hits VIP |
| UPN suffix | `alice@example.test` | AD login names | Treating UPN suffix as proof of KDC realm |
| Host/SPN alias | `portal.example.test` | HTTP/Negotiate, KDC lookup | DNS CNAME differs from registered SPN |
| Keytab | `/etc/security/keytabs/portal.keytab` | Server acceptor secret store | Treating keytab as public metadata |
| Tenant | `north` | Application authorization | Inferring tenant from realm and auto-granting admin |

**Realms are uppercase by convention**, yet their exact meaning comes from realm/KDC configuration and trust. Never blindly uppercase/lowercase **a verified identity key** without understanding provider mapping. DNS domains, UPN suffixes, IdP tenants, and Kerberos realms may relate without being identical.

**Multi-realm apps:** the same local username can exist in two realms; map the verified principal **together with its source namespace** (realm/canonical principal) to local accounts, never looking up solely by `getName().split("@")[0]`.

## 4. Three Phases Where Distinct Errors Arise

| Phase | What Happens | Typical Errors |
| --- | --- | --- |
| **AS exchange** | Client proves identity to KDC and gets TGT | Wrong client realm, principal unknown, clock skew, preauth errors |
| **TGS exchange** | Client requests service ticket for exact SPN/realm | Service SPN unknown/duplicate, wrong referral/cross-realm trust, enctype mismatch |
| **AP exchange** | Browser sends AP-REQ to Spring/JVM service | Service cannot decrypt ticket, wrong keytab/KVNO/etype, clock skew, replay |

A `GSSException` on the backend usually points to the **AP exchange** or JAAS acceptor startup. Not every error comes from the service account password; a `401 Negotiate` can be a **normal challenge** at the start of the flow.

**Pinpoint the phase:** did failure occur before TGT, before TGS, when fetching the token from the browser, or during backend verification? That determines the next diagnostic command.

## 5. Preparing a Trustworthy Test Lab

A **staging environment isolated from production** should have:

- Realm A: `CORP.EXAMPLE.TEST` and a test KDC or AD.
- Optional for cross-realm tests: Realm B `PARTNER.EXAMPLE.TEST`, with trust/referrals enabled **only in positive cases**.
- Dedicated service account and SPN `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST`.
- Keytab created by an administrator specifically for the lab service account; managed as a secret.
- Spring Boot/JDK 17+ server with Spring Security Kerberos extension and web endpoint `/secure/whoami`.
- One browser with proper SPNEGO trust policy, one clean browser profile, and one MIT Kerberos client for negative tests.
- NTP/chrony/Windows Time Service and the ability to **simulate clock skew on isolated lab VMs/containers** (never alter production domain controller clocks).
- Known DNS A/CNAME/SRV records to test hostname/SPN behavior.
- Logging with correlation IDs and redaction: never dump `Authorization: Negotiate`, keytabs, tickets, or session secrets.

Lock down a **fixture sheet** beforehand: principal, realm, SPN, keytab path, KVNO, enctype, KDC endpoint, Spring/JDK versions, browser policy, clock-skew threshold, and expected account mapping. Record the lab keytab's checksum/file version, **never** key contents.

## 6. Happy Path Baseline for Comparison

**Given** the client holds a valid TGT, unique SPN, synchronized service keytab, synced clocks, and valid Spring config.

**When** the browser visits `https://portal.corp.example.test/secure/whoami` and completes SPNEGO.

**Then**:
1. A Kerberos service ticket exists for the matching HTTP SPN.
2. The Spring acceptor processes the ticket successfully.
3. The application receives a verified principal with the expected realm.
4. The principal links to the exact active local account.
5. `ROLE_VIEWER` is granted by server-side policy, never from raw HTTP headers.
6. The authorized request receives restricted content per authorization rules.
7. TGT/service ticket validity and replay protection remain intact.
8. No user/password or raw tickets appear in logs.

**A standalone HTTP 200 does not prove Kerberos passed.** The browser might have entered via an anonymous route, an old session, cookies, NTLM fallback, or Basic authentication. Inspect the actual `Authentication` class/provider and security mechanism used.

## 7. Wrong Realm: What Does This Scenario Actually Mean?

**Realm mismatch** can occur when:

1. The client requests a TGT for the wrong realm.
2. The client contacts the wrong realm's KDC due to `krb5.conf`/DNS mappings.
3. The client requests a service ticket for an SPN unknown to that KDC.
4. A service ticket for realm B is sent to an acceptor holding only realm A's keytab without trust/delegation.
5. A realm B user logs in via cross-realm trust, yet app mapping treats them as a realm A user.
6. An AD UPN suffix is mistaken for a Kerberos realm.
7. A reverse proxy/alias makes the client request an SPN on a hostname different from the registered service account.
8. Referrals/canonicalization rewrite the principal into a form the app does not expect.

**Do not expect one single error code for every wrong-realm case.** You may see `KDC_ERR_WRONG_REALM` in referral-related exchanges, `KDC_ERR_S_PRINCIPAL_UNKNOWN` when an SPN is not found, `KRB_AP_ERR_MODIFIED` when the service fails to decrypt the ticket, or client-side principal mapping errors depending on phase and config.

**Valid cross-realm trust is an intentional exception:** a realm B user can obtain a ticket for a realm A service via referral/TGT chains. **Do not reject solely because client realm differs from service realm** when policy permits it; instead, verify trust paths, service targets, and identity namespaces in the app.

## 8. `krb5.conf`: `default_realm` and `domain_realm`

Example config for **MIT Kerberos testing**:

~~~ini
[libdefaults]
  default_realm = CORP.EXAMPLE.TEST
  dns_lookup_realm = false
  dns_lookup_kdc = false
  clockskew = 300

[realms]
  CORP.EXAMPLE.TEST = {
    kdc = kdc1.corp.example.test
  }
  PARTNER.EXAMPLE.TEST = {
    kdc = kdc1.partner.example.test
  }

[domain_realm]
  .corp.example.test = CORP.EXAMPLE.TEST
  corp.example.test = CORP.EXAMPLE.TEST
  .partner.example.test = PARTNER.EXAMPLE.TEST
  partner.example.test = PARTNER.EXAMPLE.TEST
~~~

**This is a lab example, not production configuration**. When using AD with DNS SRV and referrals, discovery and mapping policies can differ. MIT `krb5.conf` supports `[realms]`, `[domain_realm]`, `[capaths]`, and canonicalization/DNS options.

**Never “fix” wrong-realm issues with wildcards for all hosts**. Document exact expected realms, check KDC trust, DNS mappings, SPN registrations, and which principals the app accepts.

## 9. Testing Wrong Realm Layer by Layer

**Test R1 — Wrong user realm:**
- Client tries `alice@PARTNER.EXAMPLE.TEST` when the account belongs only to Corp with no matching Partner identity.
- Expectation: client cannot get a TGT/ticket as `alice@CORP.EXAMPLE.TEST`; **never fall back to the Corp account**.

**Test R2 — Wrong realm when requesting service ticket:**
- With a Corp TGT, request SPN `HTTP/portal.partner.example.test@PARTNER.EXAMPLE.TEST` which is not the intended target.
- Expectation: depending on trust, KDC denies or issues a Partner service ticket; **Corp service must not accept it as Corp**.

**Test R3 — Cross-realm with trust:**
- Partner user is authorized to access the Corp SPN via trust.
- Expectation: AP exchange succeeds **if** service/key and trust path are valid, while the principal retains its Partner namespace; app membership governs access.

**Test R4 — Cross-realm without trust:**
- Partner user has no referral/trust to Corp.
- Expectation: no valid service ticket or failed AP; never bypass via Basic/login fallback.

**Test R5 — Same username across different realms:**
- `alice@CORP...` and `alice@PARTNER...` are two external identities.
- Expectation: never auto-merge local accounts simply due to matching usernames.

## 10. Why DNS and HTTP SPNs Easily Cause Realm Confusion

Given browser URL `https://portal.corp.example.test`, Kerberos HTTP SPNs usually derive from the **hostname selected by client/GSS canonicalization rules**, such as `HTTP/portal.corp.example.test`. If a reverse proxy uses aliases, CNAMEs, or VIPs, the service principal can differ from the backend machine name.

Example:

~~~text
Browser URL: https://portal.corp.example.test
DNS CNAME:   portal.corp.example.test -> ingress-01.internal.test
Backend:     app-07.internal.test

Expected service principal by contract:
  HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST

Wrong candidates:
  HTTP/app-07.internal.test@CORP.EXAMPLE.TEST
  HTTP/portal.partner.example.test@PARTNER.EXAMPLE.TEST
~~~

**Do not assume Kerberos always uses the exact host from the URL**: some clients canonicalize via DNS or apply custom SPN rules. Inspect the actual service ticket principal using `klist`/`kvno` on the client and verify against the KDC/SPN registry.

**In AD**, verify the SPN belongs to the right account with `setspn -Q HTTP/portal.corp.example.test`. If the SPN sits on another account, the KDC may encrypt the service ticket with a secret **absent from the app's keytab**, causing integrity/AP failures.

## 11. Clock Skew: Where Does the 300-Second Limit Come From?

Kerberos uses timestamps inside authenticators and validity windows to prevent **replay**. If clock drift among client/service/KDC exceeds allowed skew, requests are rejected.

In MIT Kerberos, `clockskew` in `krb5.conf` **defaults to 300 seconds**. JDK Kerberos has a corresponding setting; **deployments can configure different values**, or AS/KDC may enforce distinct policies.

**Distinguish:**
- `KRB_AP_ERR_SKEW`: usually appears in the application AP phase when the authenticator timestamp falls outside the acceptor's allowed window.
- `KRB5KRB_AP_ERR_TKT_EXPIRED` / expired ticket: the ticket exceeded its lifetime; do not confuse with clock skew.
- `KRB_AP_ERR_REPEAT`: relates to replay cache/authenticator reuse, not always clock skew.
- `KDC_ERR_SKEW` or KDC pre-auth failures: can occur between client and KDC depending on phase.
- **Client↔KDC** clock skew differs from **client↔server** clock skew; measure all three participants.

**A 299-second offset may still exceed practical limits due to network latency, differing KDC/acceptor policies, or ticket lifetime constraints.** Never measure 300 seconds and declare an absolute boundary pass across every Kerberos stack.

## 12. Designing Bidirectional Clock-Skew Tests

Lab with a 300-second clock skew limit:

| Test | Client vs. Acceptor | Conceptual Expectation |
| --- | ---: | --- |
| T0 | 0s | Pass if other conditions hold |
| T1 | +30s | Typically passes within limit |
| T2 | -30s | Typically passes |
| T3 | +299s | Tight boundary; test may be latency-sensitive |
| T4 | -299s | Tight boundary; test may be latency-sensitive |
| T5 | +301s | Rejected for skew when truly out of bounds |
| T6 | -301s | Rejected for skew |
| T7 | +900s | Definitely rejected under 300s limit unless misconfigured |
| T8 | -900s | Definitely rejected under 300s limit |
| T9 | Client/KDC skewed while client/server synced | May fail at AS/TGS rather than AP |
| T10 | KDC/server skewed while client/KDC synced | Investigate ticket validity/AP behavior per phase |

**Warning:** simulate time changes only inside **isolated test VMs/containers**; never alter NTP/domain controllers or production services. For fresh tickets fetched after shifting clocks, watch ticket lifetimes, cached TGTs, and Kerberos clock correction; purge test credentials before each case as needed.

**Set operational SLAs** keeping actual clock drift well below skew tolerance. Never raise the 5-minute default to 30 minutes just to suppress errors.

## 13. Measuring Clocks and Time-Sync Services

On Linux/staging hosts:

~~~bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
~~~

These are **read-only commands**; `chronyc` requires `chrony` installed and running. On other NTP setups, use the equivalent tool. Measure time on **client, KDC, and SP** nearly simultaneously and inspect offset/root delay, not merely local timezone.

On Windows (PowerShell/CMD):

~~~powershell
w32tm /query /status
w32tm /query /peers
Get-Date -Format o
~~~

**Different displayed timezones do not mean clock skew**: Kerberos timestamps use absolute UTC time. Two hosts showing different local times with accurate UTC can still authenticate.

**Never run** clock-adjustment commands or restart Windows Time Service on a production DC without change approval. Use test VM snapshots/NTP labs and record exact offsets per case.

## 14. What Does a Kerberos Keytab Actually Store?

A **keytab** is a collection of entries shaped as **Kerberos principal + encryption type + key version number (KVNO) + secret key**. It lets the JVM acceptor use the corresponding secret to decrypt/verify service tickets without storing plaintext passwords in application config.

Example:

~~~text
Principal (service):
  HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST

Ticket encrypted with:
  KVNO = 7
  enctype = aes256-cts-hmac-sha1-96
  service key = derived/stored secret for SPN's account

Keytab has:
  HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
  KVNO = 7
  same supported enctype
  matching key material
~~~

**Matching name, KVNO, and enctype is still not enough**: if the account password was reset or the keytab was exported from the wrong account/secret, key bytes mismatch and AP decryption fails.

**Keytabs are highly sensitive credentials.** Never commit them to Git, public container images, Slack/tickets, build logs, or base64-encode them into screenshots. Use secret vaults/volumes, strict file permissions, and owned rotation workflows.

## 15. Three Keytab Mismatches to Distinguish

| Mismatch | How It Arises | How to Check |
| --- | --- | --- |
| **Principal/SPN** | Ticket for `HTTP/portal`, keytab holds only `HTTP/backend` | Inspect ticket service principal and keytab principal |
| **KVNO** | Service account password/key rotation bumps version; pod holds old keytab | `kvno` / `klist -k -e` and target KDC state |
| **Enctype** | KDC issues AES key yet keytab/JAAS has only RC4 or policy blocks it | `klist -k -e`, ticket encryption, JDK allowed etypes |
| **Key material** | Same principal/KVNO/etype yet keytab created from different password/account | Decrypt verification test, controlled regeneration |
| **File/config** | Wrong keytab path, missing read permission, wrong pod/namespace mount | Check permissions/volumes/release config |
| **Service account/SPN owner** | Duplicate SPN, or SPN registered on wrong AD account | `setspn -Q/-X`, AD ownership |
| **KVNO drift across nodes** | Rolling deploy: Pod A has keytab v7, Pod B has v8 | Check every pod/version; staged overlap |

**`KRB_AP_ERR_MODIFIED` does not guarantee the keytab simply lacks a KVNO**. Microsoft documents that it can stem from an SPN on the wrong account, DNS/cluster aliases, mismatched keys/passwords, trust/etypes, or other misconfigurations. Always trace from the ticket principal and actual acceptor key rather than making random edits.

## 16. Inspecting Keytab Contents on MIT Kerberos

On a host holding a **test-environment keytab**, run:

~~~bash
klist -kte /etc/security/keytabs/portal.keytab
~~~

Options:
- `-k`: list entries in a keytab instead of a ticket cache.
- `-t`: display entry timestamps.
- `-e`: display encryption types.
- KVNO appears in output per implementation.

**Never display secret keys via key-dumping flags**. The keytab file itself is a secret, and even its principal/KVNO/etype listing can be sensitive; control log access.

**Limitation:** output only proves **the keytab contains entries**; it does not prove the secret actually matches the KDC. Confirm with a decrypt test of a matching SPN service ticket or SPNEGO E2E.

## 17. Checking Service Tickets and KVNO with `kvno`

On a lab client holding a valid TGT:

~~~bash
klist
kvno HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
~~~

`kvno` requests a service ticket and prints the **KVNO issued by the KDC**. To attempt ticket decryption using a keytab **when supported by your MIT version**, run:

~~~bash
kvno -k /etc/security/keytabs/portal.keytab HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
~~~

**Meaning of `kvno -k`:** tries to decrypt the fetched ticket to verify the keytab holds the matching service key. If it fails, compare SPN, KVNO, enctype, and key material. This is a far stronger check than merely listing keytab entries.

**Note:** `kvno -k` is an MIT utility; Windows `klist` lacks identical syntax, and environments disallowing TGTs for service accounts may require a separate client principal to request the service ticket. Never weaken production service account permissions just to make a `kinit` test pass.

## 18. What Can and Cannot `kinit -k -t` Verify?

Example in a **test realm**:

~~~bash
kinit -k -t /etc/security/keytabs/portal.keytab HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
~~~

Meaning: the client attempts to use the keytab to **acquire initial credentials/TGT for that principal**, which is not the same as accepting a service ticket. Results depend on KDC policy: service principals may be disallowed or unsuitable as AS clients.

**Do not treat `kinit -k` failure as absolute proof the keytab cannot decrypt service tickets.** For a Kerberos HTTP acceptor, it is more accurate to:
1. Acquire a valid TGT as a client user.
2. Request a service ticket for the exact SPN.
3. Run `kvno -k` or actually send `Authorization: Negotiate` to the JVM acceptor.
4. Inspect GSS logs and the authenticated principal.

**There is no need to acquire a service account TGT with a real password** when the test objective is simply the acceptor keytab.

## 19. Windows AD: Verifying SPN Ownership and Ticket Cache

On a domain-joined Windows test workstation/server:

~~~powershell
klist tickets
klist tgt
setspn -Q HTTP/portal.corp.example.test
setspn -X
~~~

- `klist tickets`: lists cached tickets in the current logon session.
- `klist tgt`: inspects the TGT per privilege/session.
- `setspn -Q`: locates the account owning a specific SPN.
- `setspn -X`: searches for duplicate SPNs within the tool/AD scope.

**Interpret output with the right privileges and domain scope**; some forest-wide checks require appropriate permissions/flags. Especially with cross-forest trusts, collisions can exist across trusted forests and remain invisible to a single-domain query.

**Never run `setspn -D/-S` or reset passwords immediately** before verifying the AD owner and rotation plan. SPN edits can impact every service sharing that account.

## 20. Ticket Caches and Negative Testing

A browser/OS may still hold an old TGT or service ticket after you change keytabs/SPNs. Tests must therefore distinguish:

- **Cached old ticket** acquired before account password rotation.
- **New ticket** carrying the new KVNO after KDC updates.
- **Old keytab** still on a subset of pods.
- **New keytab** deployed while JVM/JAAS has not reloaded keys.
- **Browser fallback** to NTLM/Basic making the UI appear to “still log in.”

In **staging**, you can use appropriate ticket-cache purge tools to force fresh ticket issuance—such as MIT `kdestroy` or Windows `klist purge` per test policy. **This mutates active authentication state**: run only on authorized test accounts/VMs, never purge TGTs of live users or production services.

Tests must note **whether the ticket was issued before or after rotation**. An AP request using an old ticket may still succeed during an overlap window if the service retains the old key and policy permits it; that is not necessarily a bug.

## 21. Key Version Rotation: Safe Rollout Sequence

An uncoordinated keytab rotation can cause intermittent service outages:

~~~text
t0 KDC/service account uses KVNO=7, pods keytab v7 -> OK
t1 Password/key rotated in AD/KDC -> new service ticket KVNO=8
t2 Pod A already has v8, Pod B still holds v7
t3 Browser load-balanced to pod B -> AP decrypt fails
t4 Rotation complete -> all pods share matching keys, service OK
~~~

**Safe plan:**
1. Confirm SPN/account owner, keytab output, and supported enctypes.
2. Schedule a maintenance/change window and test in a test realm first.
3. Coordinate key rollover/overlap per KDC/AD behavior and app support; **never assume every keytab automatically preserves multiple KVNOs**.
4. Roll out the keytab via a secret-management system and verify permissions.
5. Run health/acceptor checks on every pod plus actual SPNEGO E2E.
6. Confirm service tickets are issued with the new KVNO and all nodes decrypt them.
7. Monitor ticket lifetimes and old-key expiration; retire old keys per policy.
8. Keep an **organized rollback**—never repeatedly reset passwords or copy keytabs from another environment.

**Never “fix” things by repeatedly re-exporting keytabs from new account passwords**: each reset can increment KVNO and worsen the mismatch.

## 22. Enctype Mismatches, JDK Policy, and AD

**Encryption type (enctype)** determines the cryptographic algorithm used in tickets/service keys. Errors arise when the KDC issues a ticket with an enctype missing from the keytab or disabled by JDK/service account/domain policy.

Examples:
- KDC requires AES256 while the keytab holds only an old RC4 key.
- Service account lacks matching AES keys after a policy/password change.
- Ticket KVNO matches, yet enctype differs from the keytab.
- Java 17 runtime/security policy does not enable/enforce the chosen enctype.
- Cross-realm trust uses incompatible enctypes.

**Never enable DES/RC4 or `allow_weak_crypto=true` as a default fix**. Prefer organization-supported AES; align KDC, account encryption flags, keytab generation, and Java runtime. Legacy policies require an owned, approved migration plan.

**Note:** `KDC_ERR_ETYPE_NOSUPP` typically occurs during KDC ticket issuance; `KRB_AP_ERR_MODIFIED` or GSS accept failures typically occur during AP service decryption. Inspect logs and trace the exact phase.

## 23. Which Spring Components Handle SPNEGO?

**Spring Security Kerberos** is a separate **extension/module**, not included automatically with `spring-boot-starter-security`. In the Servlet stack, common components are:

| Component | Role |
| --- | --- |
| `SpnegoEntryPoint` | Sends HTTP `WWW-Authenticate: Negotiate` challenge |
| `SpnegoAuthenticationProcessingFilter` | Reads `Authorization: Negotiate` and passes the token to `AuthenticationManager` |
| `KerberosServiceAuthenticationProvider` | Invokes the ticket validator and loads user details |
| `SunJaasKerberosTicketValidator` | JAAS/GSS acceptor configured with SPN and keytab |
| `UserDetailsService` | Maps the Kerberos principal to a local account/authorities |
| `SecurityFilterChain` | Protects URLs, filter ordering/entrypoint, and fallback policies |
| `SecurityContext` | Persists authentication per session/repository strategy |

**Which layer checks realm/keytab/clock?** GSS/Kerberos inside the JVM and the KDC enforce protocol checks; the Spring provider turns the outcome into an `Authentication`. **Never compare realm strings or count 300s in a controller and claim the ticket was verified**.

**Which layer checks business permissions?** `UserDetailsService` and the app's authorization layer. A valid ticket does not grant `ROLE_ADMIN`.

## 24. Scoped Spring Security Kerberos Configuration Fragment

Partial configuration example **inside a Spring project with the Kerberos extension**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class KerberosValidatorConfig {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator v =
                new SunJaasKerberosTicketValidator();
        v.setServicePrincipal(
                "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST");
        v.setKeyTabLocation(
                new FileSystemResource(
                    "/run/secrets/kerberos/portal.keytab"));
        v.setDebug(false);
        return v;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            org.springframework.security.core.userdetails.UserDetailsService
                    userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }
}
~~~

**This is a library-dependent configuration class**, not a full application: it requires a Kerberos extension matching the Spring/Security Boot BOM, a real `UserDetailsService`, `SpnegoAuthenticationProcessingFilter`, an entry point, and a properly wired `SecurityFilterChain`. This is **not a standalone Java 17 program**.

**Key testing rule:** `setServicePrincipal` must match the real service name from SPN/KDC; the keytab path must be an authorized secret mount. Never leave `setDebug(true)` on long-term in production because protocol/identity logs can be sensitive.

## 25. JAAS and Java GSS: Controlled Diagnostics

Some systems use `Krb5LoginModule` as an acceptor. Sample JAAS configuration **strictly for test environments with verified JDK/providers**:

~~~text
com.example.KerberosAcceptor {
  com.sun.security.auth.module.Krb5LoginModule required
  useKeyTab=true
  keyTab="/run/secrets/kerberos/portal.keytab"
  principal="HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST"
  storeKey=true
  isInitiator=false
  doNotPrompt=true
  useTicketCache=false
  debug=false;
};
~~~

JVM flags aiding test diagnostics:

~~~bash
java -Djava.security.krb5.conf=/etc/krb5.conf \
     -Dsun.security.krb5.debug=true \
     -jar app.jar
~~~

**This command is illustrative for a Unix shell and a project with `app.jar`**; it does not create keytabs or accounts. Debug output can expose service principals, realms, ticket metadata, and SPN lookups; enable only with authorization, briefly, and under log redaction/retention controls.

**Do not declare success solely from a `"Found key for principal"` log line**. The app must still actually accept AP-REQ, establish a GSS context, resolve the right user principal, and pass authorization.

## 26. Distinguishing Normal HTTP Challenges from Errors

In SPNEGO, the first request without a token may receive:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
Cache-Control: no-store
~~~

The browser can automatically respond with:

~~~http
GET /secure/whoami HTTP/1.1
Host: portal.corp.example.test
Authorization: Negotiate BASE64_SPNEGO_TOKEN
~~~

**A 401 on the first round is not an error**. However, if the server continues returning 401 after receiving a `Negotiate` header, check:
- Did the browser send Kerberos rather than an NTLM fallback?
- Does the ticket carry the right SPN/hostname?
- Is the keytab readable inside the JVM process with the right secret?
- Are realm trust and KDC referrals accurate?
- Is clock skew within policy?
- Are `SecurityFilterChain`/filter ordering configured properly?
- Did a proxy strip or alter the `Authorization` header?

**Never log full Base64 tokens**. They are sensitive security credentials.

## 27. Standalone Java 17: Logic Test Classifying Three Failure Groups

The example below **runs on pure JDK 17**, modeling facts **observed after a trusted inspection**: expected realm/SPN, clock offset, KVNO, enctype, and key-match outcome. It **does not cryptographically verify Kerberos tickets**, replace JAAS/GSS, or read real keytabs, and must never be used in production to decide `Authentication`.

Create **`KerberosFailureMatrixDemo.java`**:

~~~java
import java.util.Set;

public class KerberosFailureMatrixDemo {

    record Evidence(
            String realm,
            String servicePrincipal,
            long clientTimeSeconds,
            long serviceTimeSeconds,
            int ticketKvno,
            int keytabKvno,
            String ticketEtype,
            Set<String> keytabEtypes,
            boolean matchingSecret,
            boolean replayed) {}

    static final String EXPECTED_REALM = "CORP.EXAMPLE.TEST";
    static final String EXPECTED_SPN =
            "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST";
    static final long BASE = 1_700_000_000L;
    static final long MAX_SKEW = 300L;

    static String diagnose(Evidence e) {
        if (!EXPECTED_REALM.equals(e.realm())) {
            return "DENY_REALM";
        }
        if (!EXPECTED_SPN.equals(e.servicePrincipal())) {
            return "DENY_SPN";
        }
        if (Math.abs(e.clientTimeSeconds()
                - e.serviceTimeSeconds()) > MAX_SKEW) {
            return "DENY_CLOCK_SKEW";
        }
        if (!e.keytabEtypes().contains(e.ticketEtype())) {
            return "DENY_ETYPE";
        }
        if (e.ticketKvno() != e.keytabKvno()) {
            return "DENY_KVNO";
        }
        if (!e.matchingSecret()) {
            return "DENY_KEY_MATERIAL";
        }
        if (e.replayed()) {
            return "DENY_REPLAY";
        }
        return "PASS_PRECHECK";
    }

    static Evidence sample(
            String realm, String spn,
            long deltaSeconds, int kvno,
            String etype, boolean secret, boolean replayed) {
        return new Evidence(
                realm, spn, BASE + deltaSeconds, BASE,
                kvno, 7, etype,
                Set.of("aes256-cts-hmac-sha1-96"), secret, replayed);
    }

    public static void main(String[] args) {
        Evidence valid = sample(
                EXPECTED_REALM, EXPECTED_SPN, 0, 7,
                "aes256-cts-hmac-sha1-96", true, false);

        System.out.println("Valid: " + diagnose(valid));
        System.out.println("Wrong realm: " + diagnose(sample(
                "PARTNER.EXAMPLE.TEST", EXPECTED_SPN,
                0, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Wrong SPN: " + diagnose(sample(
                EXPECTED_REALM,
                "HTTP/other.corp.example.test@CORP.EXAMPLE.TEST",
                0, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Clock +301: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                301, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Clock -301: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                -301, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Clock +300: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                300, 7, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Wrong KVNO: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 8, "aes256-cts-hmac-sha1-96", true, false)));
        System.out.println("Wrong enctype: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 7, "arcfour-hmac", true, false)));
        System.out.println("Wrong key material: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 7, "aes256-cts-hmac-sha1-96", false, false)));
        System.out.println("Replayed authenticator: " + diagnose(sample(
                EXPECTED_REALM, EXPECTED_SPN,
                0, 7, "aes256-cts-hmac-sha1-96", true, true)));
        System.out.println("After safe repair: " + diagnose(valid));
    }
}
~~~

Compile and run:

~~~bash
javac KerberosFailureMatrixDemo.java
java KerberosFailureMatrixDemo
~~~

**Exact stdout:**

~~~text
Valid: PASS_PRECHECK
Wrong realm: DENY_REALM
Wrong SPN: DENY_SPN
Clock +301: DENY_CLOCK_SKEW
Clock -301: DENY_CLOCK_SKEW
Clock +300: PASS_PRECHECK
Wrong KVNO: DENY_KVNO
Wrong enctype: DENY_ETYPE
Wrong key material: DENY_KEY_MATERIAL
Replayed authenticator: DENY_REPLAY
After safe repair: PASS_PRECHECK
~~~

**Explanation:** the code enforces precedence: realm first, then SPN, skew, enctype, KVNO, key material, and replay. For the `+300s` test, this is merely a **mathematical threshold check**; real Kerberos also involves network latency, ticket validity, KDC/acceptor policy, and replay caches. Never use demo output to claim Java GSS authenticated anything. Real cross-realm trust **can allow realm B users**; the demo intentionally pins a fixed service realm to illustrate negative cases.

## 28. Why Does the Code Above Not Replace Kerberos Integration Tests?

**Spring Security Kerberos** relies on JAAS/GSS to process cryptographic tokens with a real KDC and keytab. The Java example only classifies pre-assumed facts.

Never:
- Let a browser send `realm=CORP.EXAMPLE.TEST` and `matchingSecret=true` in headers and treat it as authenticated.
- Use `kid`/`kvno` from a request as proof of the keytab.
- Grant local `ROLE_ADMIN` after a passing simulation.
- Test only `Math.abs(clockDelta) <= 300` and claim replay defense is tested.
- Skip actual service ticket decryption using the keytab.

An acceptable integration test must obtain a service ticket **from a controlled test KDC**, send a real SPNEGO AP-REQ, and verify server identity/authorization.

## 29. End-to-End Wrong-Realm Scenarios

**Case RR-A — Wrong realm mapping:**

Given client DNS and `krb5.conf` intentionally map the service hostname to the Partner realm in the lab. When requesting a service ticket for the Corp HTTP service. Then the ticket lacks the intended service realm or TGS fails; the SP never accepts the Partner principal automatically.

**Case RR-B — Missing realm trust:**

Given a Partner client TGT, while the Corp service accepts referrals/trust strictly per allowlist. When attempting to access the Corp service without cross-realm trust. Then the authenticating chain cannot complete; never fall back to weaker authentication mechanisms.

**Case RR-C — Valid cross-realm trust:**

Given configured trust and an app-approved Partner test user. When the KDC issues a service ticket for the Corp SPN via referrals. Then GSS validates the service ticket, the app preserves the verified Partner client realm, and local account policy decides access.

**Case RR-D — Same username collision:**

Given `alex@CORP.EXAMPLE.TEST` and `alex@PARTNER.EXAMPLE.TEST`. When both Kerberos logins are valid. Then the app never merges accounts without an evidenced identity link.

**Case RR-E — SPN alias and CNAME:**

Given the browser visits `portal.corp...` yet the client canonicalizes to another name. When requesting TGS. Then inspect the actual ticket SPN and keytab/SPN ownership; never rewrite SPNs blindly.

## 30. End-to-End Clock-Skew Scenarios

**Case TT-A — Client ahead of server:**
1. On a lab VM, set the client clock offset to +8 minutes relative to SP/KDC.
2. Obtain a fresh TGT/service ticket in a harness-controlled manner.
3. Send the SPNEGO AP-REQ.
4. Expect failure once past policy; record the actual KDC/AP phase and any error code.
5. Restore clock/NTP, retry with a valid ticket, and expect a pass.

**Case TT-B — Client behind server:** -8 minute offset, same steps.

**Case TT-C — Client and KDC skewed while SP matches KDC:** can fail as early as preauthentication/TGS; do not look only in Spring logs.

**Case TT-D — Clocks synced yet ticket expired:** distinguish invalid lifetime from skew.

**Case TT-E — NTP recovery after network partition:** monitor resync while preventing session/token freshness drift.

**Never alter clocks on production DCs or weaken skew policies**. Set clock-drift alerts well below 300 seconds. E2E tests must verify clock offsets and cache states rather than relying on displayed timezones.

## 31. End-to-End Keytab Mismatch Scenarios

**Case KT-A — Different SPN:** ticket for `HTTP/portal` while keytab holds `HTTP/backend`. Expect AP decrypt rejection.

**Case KT-B — Stale keytab:** KDC rotated to KVNO 8 while service pod still holds KVNO 7. Expect new tickets cannot be decrypted once the old key is gone.

**Case KT-C — Incompatible enctype:** AES ticket, RC4-only keytab—never enable legacy crypto to work around it. Expect failure and confirm etype mismatch.

**Case KT-D — Matching KVNO, wrong secret:** test a keytab exported from the wrong account; expect failure. Never fix by hardcoding service account passwords in the app.

**Case KT-E — Unreadable keytab:** missing file, wrong path, or volume mount/permission error. Expect fail-closed and health alerts.

**Case KT-F — Duplicate/wrong-owner SPN:** KDC encrypts ticket under another account; service cannot decrypt with its keytab. Check `setspn -Q/-X` and actual owner.

**Case KT-G — Mixed deployment:** Pod A holds new keytab, Pod B holds old. Test each pod directly and via load balancer to diagnose intermittent post-rotation failures.

**Case KT-H — Old cached ticket:** user holds a KVNO 7 service ticket; if the service keeps only v8, old tickets can fail. Design overlap/retirement per policy.

## 32. Error Matrix and Root-Cause Differentiation

| Symptom / Error Code | Where Observed | Likely Explanation | What Not to Assume |
| --- | --- | --- | --- |
| `KRB_AP_ERR_SKEW` | AP/GSS accept | Client/service clock skew exceeds policy | Do not assume wrong keytab |
| `KDC_ERR_SKEW`/preauth time error | KDC/AS/TGS | Client/KDC time skew | Do not assume Spring filter bug |
| `KRB_AP_ERR_MODIFIED` | Client/Windows Event 4 | Service cannot decrypt/validate ticket | Not only KVNO; could be SPN owner/DNS |
| `KRB_AP_ERR_BAD_INTEGRITY` | GSS/Kerberos | Integrity check failed, secret/account mismatch | Never enable legacy etypes |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | KDC/TGS | Service SPN missing or wrong realm | Not just keytab path |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | AD KDC/TGS | Duplicate SPN/account in search scope | Never delete SPNs before verifying owner |
| `KDC_ERR_ETYPE_NOSUPP` | KDC | No common encryption type | Do not raise clock skew |
| `KRB_AP_ERR_REPEAT` | AP/replay cache | Duplicate authenticator/replay or timestamp/sequence | Never auto-retry the same AP token |
| `GSSException: No valid credentials provided` | JVM | Failed to load credentials/keytab/principal | Not necessarily wrong user password |
| `GSSException: Checksum failed` | JVM GSS | Service secret/key mismatch or token integrity | Not necessarily bad timestamp |
| `Cannot locate KDC` | Client/JVM | DNS SRV, `krb5.conf`, network/realm mapping | Do not assume SSO issuer failure |
| HTTP `401 Negotiate` at start of flow | Browser ↔ Spring | Normal challenge | Not always authentication failure |
| `403 Forbidden` after valid principal | Spring authorization | Local account/role/tenant lacks permission | Never reset keytab to “fix” |

**Error codes are hints, not absolute diagnoses.** The same symptom can originate across layers; correlate ticket/SPN/realm, clocks, keytab entries, and traces for the exact timestamp.

## 33. What Should Spring Integration Tests Assert?

Verify from the HTTP layer down to local authorization:

1. GET protected endpoint without a Negotiate token → **401 challenge** when SPNEGO is required and no other authenticated session exists.
2. Browser sends valid Kerberos AP-REQ → `KerberosServiceAuthenticationProvider` accepts, local user maps, expected authority applies.
3. Wrong realm/no trust → **no `Authentication` created** and no fallback to unapproved form/basic auth.
4. Wrong service principal → token rejected.
5. Clock skew outside policy → authentication fails, metrics record the exact phase.
6. Stale KVNO/wrong key material in keytab → GSS accept fails, no authenticated `SecurityContext` created.
7. Valid ticket yet disabled local account → denied.
8. Valid ticket yet user outside tenant → 403.
9. Same username from two realms → local accounts remain distinct.
10. Replayed token → rejected per GSS/replay policy.
11. Load balancer across two pods with differing keytab versions → test detects drift and request failures.
12. Proxy strips `Authorization` header → classified as network/proxy issue without forging principal.
13. Browser uses NTLM fallback → test detects actual mechanism and never logs a Kerberos pass.
14. Logout/session expiry → reauthenticates per policy without reusing a stale `SecurityContext`.
15. Inaccessible keytab mount → never auto-grants `ROLE_USER` without verification.

**MockMvc does not generate a genuine KDC-signed Kerberos service ticket.** MockMvc can test filter/entrypoint/provider error handling, whereas proving realm/skew/keytab requires real KDC/JAAS/GSS integration.

## 34. Real Browser Testing: SPNEGO or Fallback?

When testing Chrome/Edge/Firefox on a domain-trusted workstation:

- Verify intranet/trusted URI policies and approved SPNEGO settings.
- Confirm the browser URL hostname matches the intended SPN.
- Observe `401 WWW-Authenticate: Negotiate` followed by the `Authorization` request.
- Verify the **service ticket principal in the OS ticket cache** and GSS acceptor logs.
- Never use Basic login, session cookies, or anonymous success as proof of Kerberos.
- Separate clean browser profiles from profiles holding existing cookies/sessions.
- Test first login, refresh, logout, user switching, and multi-tab behavior per policy.
- Inspect proxy TLS termination and HTTP `Authorization` forwarding.
- Test service URL aliases/CNAMEs without arbitrarily altering keytabs on DNS changes.
- Never save raw Negotiate tokens in HAR files or support tickets.
- On failures, determine whether the KDC TGS issued a ticket before Spring returned 401.

**Successful SPNEGO challenge/response ≠ user allowed to invoke business APIs**. Permissions must come from Spring's local authorization.

## 35. Consolidated Negative Test Matrix

| # | Test | Required Result |
| --- | --- | --- |
| 01 | Matching realm, SPN/keytab/clocks valid | Kerberos accepts and resolves exact user |
| 02 | Wrong client realm, nonexistent principal | No valid TGT |
| 03 | Wrong service realm, no trust | No valid service ticket |
| 04 | Valid cross-realm trust and app allows | Valid login; client realm preserved |
| 05 | Valid cross-realm trust yet app denies membership | 403 |
| 06 | Same username in two realms | Local accounts not merged |
| 07 | UPN suffix differs from actual Kerberos realm | Mapping never guesses |
| 08 | Wrong KDC realm DNS mapping | Fails; classified as DNS/realm |
| 09 | Cross-forest referral lacking trust | No bypass |
| 10 | SPN canonicalization switches to CNAME | Actual SPN detected |
| 11 | Duplicate SPN in AD | Alert/deny per KDC behavior |
| 12 | SPN on wrong account | AP decrypt fails; owner identified |
| 13 | Client/acceptor offset +30s | Passes if policy/conditions permit |
| 14 | Offset -30s | Passes if policy/conditions permit |
| 15 | Offset +301s with 300s limit | Rejected when genuinely out of bounds |
| 16 | Offset -301s with 300s limit | Rejected |
| 17 | Client/KDC skewed, SP synced | Classified as AS/TGS failure |
| 18 | Client/SP skewed, KDC synced with client | Classified as AP failure |
| 19 | Expired ticket despite synced clocks | Rejected as expired, distinct from skew |
| 20 | Clocks normal after NTP fix | Kerberos passes again |
| 21 | Keytab missing SPN | Rejected |
| 22 | Keytab holds wrong realm | Rejected |
| 23 | Keytab KVNO 7, ticket KVNO 8 | Decrypt fails if no overlap key |
| 24 | Matching KVNO, wrong secret | Decrypt fails |
| 25 | AES ticket, keytab lacks AES key | Fails without lowering crypto policy |
| 26 | Keytab missing/permission denied | Fails closed |
| 27 | JVM loads wrong keytab path | Fails closed |
| 28 | Valid keytabs yet Pods A/B hold different versions | Detects per-node failures |
| 29 | Browser holds cached old ticket post-rotation | Honors overlap/retirement policy |
| 30 | Fresh ticket + updated keytab across all pods | Passes |
| 31 | Wrong HTTP SPN via load balancer VIP | Fails or proven mapping policy handles |
| 32 | Request missing `Authorization` header | `401 Negotiate` challenge |
| 33 | Request sends NTLM token when Kerberos required | Never counted as Kerberos pass |
| 34 | Valid AP ticket yet account disabled | Denied |
| 35 | Valid AP ticket yet role missing | 403 |
| 36 | Valid AP ticket yet wrong tenant | 403 |
| 37 | Untrusted `X-User` header without Kerberos | Does not impersonate principal |
| 38 | Replayed AP-REQ | Rejected by replay cache |
| 39 | Pre-rotation ticket/service principal | Matches documented behavior |
| 40 | Realm policy changed while JVM caches old config | Detected/restarted/reconfigured under control |
| 41 | KDC outage while local session active | Follows session/freshness policy |
| 42 | Proxy strips `Authorization: Negotiate` | Proxy issue detected |
| 43 | Different timezones, identical UTC | No false-positive skew |
| 44 | MFA/service delegation lacking trust | Never skips Kerberos validation |
| 45 | Keytab baked into public container image | Security policy failure; relocate secret |
| 46 | Read-only least-privilege secret mount | Passes permissions check |
| 47 | JVM debug left true long-term | Privacy/security audit failure |
| 48 | Browser service hostname changes | Tests SPN/DNS/realm mapping |
| 49 | User loses group between two requests | Revocation/role freshness policy enforced |
| 50 | Service account rotated while second pod un-updated | Alert & staged rollback plan |

**A true PASS** requires Kerberos mechanism verification, verified principal + realm, no out-of-policy fallbacks, app membership, authorization, and redacted logs.

## 36. Ordered Diagnostic Runbook

1. **Identify the phase**: AS, TGS, AP, or Spring authorization? Record error codes/hostnames/timestamps.
2. **Confirm actual SPNEGO**: is there a challenge/Negotiate token, or is the browser using Basic/NTLM?
3. **Compare clocks**: client/KDC/acceptor UTC, NTP offsets, and skew policy.
4. **Verify realm**: TGT realm, ticket service realm, `krb5.conf`/AD DNS/UPN referrals.
5. **Check actual SPN** inside the service ticket; compare against URL, DNS alias, and app service principal.
6. **Check AD SPN owner** via read-only `setspn` or KDC config.
7. **List keytab entries** (principal/KVNO/enctype) without dumping secret keys.
8. **Compare ticket vs. keytab KVNO**; review account rotation/change audit.
9. **Test decryption in lab** with `kvno -k` (if MIT) or SPNEGO acceptor E2E.
10. **Check file mounts/permissions and JVM JAAS config** on the exact node/pod.
11. **Verify local account/roles/tenant** once Kerberos authenticates.
12. **Fix at the right layer**: NTP, DNS/realm mapping, SPN owner, keytab rotation, allowed etypes, or app membership.
13. **Run negative regressions** after fixing without dropping signature/replay/skew checks.
14. **Record audit/metrics**, error codes, and time to recovery.

**Never do:** repeatedly reset the service account password by guesswork, set `allow_weak_crypto=true`, disable clock-skew validation, accept any realm, email keytabs, or log raw Kerberos AP tokens.

## 37. Testing Procedure with Safe Rollback

**Lab preparation:**
1. Snapshot test VMs; record NTP sources and clock states.
2. Record SPN owner and KVNO/keytab versions in an ACL-protected test inventory.
3. Create test users for Corp/Partner realms with trust/no-trust variants.
4. Create an SPNEGO-protected endpoint separate from business authorization.
5. Ensure keytab backup/rotation mechanisms exist strictly in staging.

**Execution:**
1. Baseline happy path.
2. Wrong realm/TGT, unknown/duplicate SPN, CNAME alias.
3. Clock skew +8/-8 minutes on **isolated VMs**, never touching production DCs.
4. Enctype/keytab KVNO/secret mismatches using **dedicated staging secrets**.
5. Test fresh tickets and cached tickets before/after rotation.
6. Test every pod, browser, proxy route, and local authorization.
7. Observe error phases rather than HTTP status codes alone.

**Recovery:**
1. Re-enable NTP sync and confirm normal UTC offsets.
2. Roll back test SPN/realm mappings to the recorded baseline.
3. Restore the authorized keytab version and test key rotation matching KDC state.
4. Purge test ticket caches if needed per change approval.
5. Turn off debug logs, scrub sensitive data, and verify secret mounts.
6. Re-run happy path, wrong realm, skew, and keytab negative cases.
7. Archive evidence with error codes, environment, and elapsed time—never raw tickets.

## 38. Proper Observability and Logging

Suggested metrics instrumented by app/infra (**not emitted automatically by Spring Security**):

| Metric | Meaning |
| --- | --- |
| `kerberos_spnego_challenge_total` | Count of `401 Negotiate` challenges |
| `kerberos_ap_accept_success_total` | Successful GSS accepts |
| `kerberos_ap_accept_failure_total` | Failures grouped by Kerberos code |
| `kerberos_wrong_realm_total` | Realm/trust mismatches |
| `kerberos_clock_skew_reject_total` | Time-skew rejections |
| `kerberos_keytab_decrypt_failure_total` | AP decryption failures |
| `kerberos_spn_unknown_total` | Service principal lookup failures |
| `kerberos_kvno_mismatch_total` | Ticket vs. keytab KVNO mismatches |
| `kerberos_etype_unsupported_total` | Incompatible encryption types |
| `kerberos_fallback_mechanism_total` | NTLM/Basic fallbacks when monitored |
| `kerberos_authenticated_user_denied_total` | Kerberos passed, business auth denied |
| `kerberos_keytab_rotation_lag_seconds` | Rollout desync across pods |

**Never log** raw ticket blobs, `Authorization: Negotiate` headers, keytab binaries, service account passwords, session cookies, or user credentials. You may log pseudonymized principal realms, expected SPNs, truncated error codes, pod names, KDC contact times, and correlation IDs under access controls.

**Critical alerts:** clock drift approaching policy limit, keytab KVNO differing from KDC post-rotation, SPN owner changes, AP failures isolated to one pod, sudden spikes in NTLM fallbacks, replay errors, or users from wrong realms gaining privileged roles.

## 39. Self-Assessment Questions

**1. Is a Kerberos realm the same as an AD DNS domain?**  
Not necessarily. They are often related yet distinct; UPN suffixes, DNS aliases, and client realm mappings can differ.

**2. What does `KRB_AP_ERR_SKEW` usually indicate?**  
Time drift between initiator and acceptor in the AP phase exceeding tolerance; measure UTC across client/server/KDC.

**3. Is 300 seconds an immutable constant in every Kerberos setup?**  
No. It is a common MIT/JDK default that can be reconfigured with deployment-specific policies.

**4. Is matching the ticket's KVNO sufficient for a keytab to decrypt?**  
No. Principal/SPN, enctype, key material, and keytab readability must also match.

**5. Are `kinit -k` and `kvno -k` the same?**  
No. `kinit -k` acquires an initial ticket from a keytab; `kvno -k` fetches and decrypts a service ticket using a keytab.

**6. Does `KRB_AP_ERR_MODIFIED` always mean a wrong service account password?**  
No. It can result from wrong SPN ownership, DNS aliases, stale keytabs, wrong encryption keys, and several other causes.

**7. Why shouldn't identical usernames across two realms be merged?**  
Because they represent two distinct identities unless backed by authoritative linking proof.

**8. What if a client presents a cached old-KVNO service ticket after rotation?**  
An overlap policy may be needed; verify when the ticket was issued and which keytabs remain on the acceptor.

**9. Is an HTTP `401 Negotiate` at the start of the flow a Kerberos failure?**  
No, it is normally the expected challenge. Inspect the follow-up request and GSS acceptor.

**10. Does Spring Security core enable Kerberos SPNEGO simply by adding `starter-security`?**  
No. You need the Kerberos extension/JAAS/GSS and properly wired filter/provider configuration.

**11. Can differing displayed timezones cause clock skew?**  
No, provided UTC timestamps are accurate. Always check absolute clock offsets.

**12. Should `clockskew` be raised to one hour to resolve incidents?**  
No; that weakens freshness/replay protection. Fix NTP and time sources instead.

**13. Why is a keytab a secret?**  
It contains service keys that allow impersonating the service within the compromised scope.

**14. If Kerberos succeeds yet the API returns 403, should you reset the keytab?**  
No. That is normally an account/authority/tenant authorization issue.

**15. Why test real KDC/JAAS/GSS instead of only the Java demo?**  
The demo only models conditions; real Kerberos requires cryptographic ticket issuance, decryption, and replay validation.

## 40. Production Checklist

- [ ] Authorized test realms and users exist; production services are never used as fixtures.
- [ ] Realm/UPN/DNS/`domain_realm` mappings are understood and documented.
- [ ] Cross-realm trust/referrals and permissions are covered by positive and negative tests.
- [ ] HTTP hostname/alias SPNs have verified ownership with no duplicate SPNs.
- [ ] SPNs, principals, and keytabs are managed under dedicated service accounts.
- [ ] NTP/chrony/Windows Time synchronize client/KDC/acceptor; drift alerts configured.
- [ ] `clockskew` is never raised arbitrarily to mask authentication errors.
- [ ] Keytabs contain exact principals, KVNOs, enctypes, and matching key material.
- [ ] Keytabs reside in read-only, least-privilege secret stores/volumes.
- [ ] Keytab rotation plans cover all pods, old-ticket overlap, and key retirement.
- [ ] DES/RC4/`allow_weak_crypto` are never enabled to bypass unapproved compatibility failures.
- [ ] Browsers send genuine Kerberos SPNEGO without unintended NTLM/Basic fallbacks.
- [ ] Reverse proxies preserve `Authorization` headers and public hostnames.
- [ ] Spring Security Kerberos extension has proper filter, provider, and GSS acceptor configuration.
- [ ] Kerberos authenticated principals map by source/realm, not local username alone.
- [ ] Local account active status, roles, and tenant/resource authorization are checked independently.
- [ ] Fail closed on KDC, SPN, keytab, or JAAS errors; never auto-create authenticated users.
- [ ] Negative tests cover wrong realm/no trust, bidirectional skew, and KVNO/etype/wrong-key mismatches.
- [ ] Tests cover cached tickets and mixed-keytab pod rollouts.
- [ ] Results signed off from a real staging KDC/AD environment, not MockMvc alone.
- [ ] Error/runbook classification and proper log redaction are in place.
- [ ] Raw keytabs/tickets/passwords are never logged or shared; debugging is time-bounded.
- [ ] Safe canary and rollback exist without modifying production clocks or KDC secrets during tests.

## 41. Conclusion

**Testing wrong realms, clock skew, and mismatched keytabs** must evaluate the **exact Kerberos phase**: realm/trust/SPN at client–KDC, authenticator freshness at client–service/KDC, and keytab decryption at the service acceptor. A `KRB_AP_ERR_MODIFIED` does not by itself prove a wrong KVNO; a `401 Negotiate` is not automatically an error; a valid Kerberos user does not automatically hold application permissions.

A reliable approach is: **real SPNEGO baseline → verify ticket principal/realm and KDC phase → measure UTC offsets → match keytab principal/KVNO/etype/key material → verify Spring GSS acceptor → verify local account/tenant roles → fix the right layer and regression-test**.

The Spring Security Kerberos extension integrates HTTP Negotiate with JAAS/GSS, yet **it does not replace KDC administration, SPN governance, keytab rotation, or clock synchronization**. Production environments require time synchronization, secret management, controlled key rollover, and fail-closed testing—**never drop signature checks, enable legacy crypto, or open wildcard realms** just to make SSO pass.

### Official References

- Spring Security Kerberos — reference for Spring & Kerberos, SPNEGO filter/provider, and `SunJaasKerberosTicketValidator`: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security — Kerberos integration reference: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- MIT Kerberos — `krb5.conf`, realm/`domain_realm`/default 300-second `clockskew`: https://web.mit.edu/kerberos/krb5-current/doc/admin/conf_files/krb5_conf.html
- MIT Kerberos — `kinit`, keytab client credential options: https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/kinit.html
- MIT Kerberos — `kvno`, service ticket KVNO and `-k` keytab decrypt validation: https://www.mit.edu/~kerberos/krb5-latest/doc/user/user_commands/kvno.html
- Microsoft Learn — Kerberos authentication troubleshooting (`KRB_AP_ERR_SKEW`, `MODIFIED`, SPN/etype): https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-authentication-troubleshooting-guidance
- Microsoft Learn — SPN registered to wrong account, `setspn` verification: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-event-4-access-denied
- Microsoft Learn — Windows `klist` tickets/tgt/purge: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/klist
- Oracle Java Security — Kerberos 5 GSS-API mechanism and supported `krb5.conf` settings: https://docs.oracle.com/en/java/javase/24/security/kerberos-5-gss-api-mechanism.html
- IETF RFC 4120 — Kerberos V5 protocol (realms, tickets, authenticators, errors): https://www.rfc-editor.org/rfc/rfc4120
