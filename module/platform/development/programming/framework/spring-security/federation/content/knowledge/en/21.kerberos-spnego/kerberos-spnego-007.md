# Establishing Cross-Realm Trust and Infrastructure Deployment Boundaries

**Kerberos cross-realm trust** allows a principal authenticated in a source realm to access a service in another realm **without copying the user's password to the target realm**. This is very useful when a Spring Security system using **SPNEGO** must serve users from multiple enterprise domains/forests, partner companies, or post-merger organizations. However, "having trust" **does not mean** "anyone from the partner realm can log in", let alone "that person has permission to read resources".

This lesson belongs to the **Kerberos and SPNEGO** group, focusing on **cross-realm trust relationships**, **referral ticket chains (cross-realm TGT/referral tickets)**, and **infrastructure conditions** that must all hold simultaneously: KDCs, inter-realm keys, trust direction, DNS/SPN, network connectivity, system clocks, encryption policies, service keytabs, account management, AD selective authentication/SID filtering, and permission mapping in Spring. Configurations that merely "change default_realm in Java" or "put two KDCs in one file" **do not create trust**.

End-to-end example:

~~~text
User realm:                   USERS.EXAMPLE
Intermediate realm (if any):  HUB.EXAMPLE
Application realm:            APPS.EXAMPLE

User principal:               lan@USERS.EXAMPLE
Spring public URL:            https://portal.apps.example/
HTTP service principal:       HTTP/portal.apps.example@APPS.EXAMPLE
Service keytab:               /etc/security/keytabs/portal.keytab
Local identity link:          (USERS.EXAMPLE, lan) -> localUser u-702
~~~

All `.example` hosts are illustrative only. **There is no real connection to a KDC/Active Directory** until deployed against an organization-managed domain.

## 1. Trust Layers That Cannot Be Collapsed Into One

| Layer | Question to Answer | Example |
| --- | --- | --- |
| **Source identity** | Which realm does the user belong to, and who authenticates them? | `lan@USERS.EXAMPLE` |
| **KDC trust** | Does the application realm accept the authentication path from the source realm? | A → B or A → HUB → B |
| **Referral routing** | Can the client locate the next realm/KDC to obtain tickets? | Cross-realm TGT `krbtgt/APPS.EXAMPLE@USERS.EXAMPLE` |
| **Service identity** | For which SPN is the ticket issued? | `HTTP/portal.apps.example@APPS.EXAMPLE` |
| **Acceptor key** | Does Spring hold the right keytab/KVNO/enctype to decrypt the ticket? | Keytab for Portal |
| **Infrastructure** | Do DNS, Kerberos ports, clocks, TLS, and proxies work? | DNS 53, KDC 88, HTTPS 443 |
| **Windows trust policy** | Which direction is trust, forest trust, selective authentication, SID filtering? | Resource forest trusts account forest |
| **Principal mapping** | Is there an internal user corresponding to the verified principal? | `(realm, principal) → localUserId` |
| **Authorization** | What is the user allowed to do after login? | `ROLE_REPORT_VIEWER`, tenant allowlist |

A system can **PASS KDC trust yet FAIL Spring authorization** (403), or **PASS network yet FAIL service ticket** due to SPN/keytab mismatch (401). Never fix a 403 by widening a forest trust, and never fix a 401 with `permitAll()`.

## 2. Realm, KDC, Principal, and Cross-Realm Key

A **realm** is a Kerberos administrative domain containing a database of principals/keys and one or more **Key Distribution Centers (KDCs)**. A KDC provides two logical services:

- **AS (Authentication Service):** verifies the client and issues a **Ticket Granting Ticket (TGT)** for the client's realm.
- **TGS (Ticket Granting Service):** validates a TGT and issues a **service ticket** for a service principal.

Example principals:

~~~text
Client principal:
  lan@USERS.EXAMPLE

Home-realm TGS principal:
  krbtgt/USERS.EXAMPLE@USERS.EXAMPLE

Cross-realm TGS principal for source USERS -> target APPS:
  krbtgt/APPS.EXAMPLE@USERS.EXAMPLE

Web service principal:
  HTTP/portal.apps.example@APPS.EXAMPLE
~~~

`krbtgt/DESTINATION@SOURCE` **is not a web server name**, but the principal/key supporting authentication delegation between KDCs. When two MIT Kerberos realms create a **direct cross-realm trust**, the KDCs must share inter-realm trust principals with synchronized key material in the corresponding direction. The reverse direction may require a reverse inter-realm principal. In Microsoft Active Directory, secrets/Trusted Domain Objects are managed by AD through its trust mechanism, not by manually copying MIT Kerberos commands onto domain controllers.

**Important:** Spring's service account/keytab **does not contain inter-realm krbtgt keys**. Spring only needs credentials to accept tickets for the target HTTP SPN, while the **KDCs** issue and verify referral/cross-realm tickets per governed trust. Never copy krbtgt keys or trust passwords into JVM/app pods.

### Terms That Must Not Be Conflated

| Term | Meaning |
| --- | --- |
| **Cross-realm TGT / referral TGT** | Ticket helping the client reach the next KDC/realm |
| **Service Ticket** | Final ticket for `HTTP/portal.apps.example` |
| **Principal** | Identity name of a user/service in a Kerberos namespace |
| **SPN** | Service Principal Name, mapping a service instance to the right account/key |
| **UserPrincipalName (UPN)** | User naming convention in AD; not synonymous with SPN |
| **Realm trust** | Established and governed relationship between KDCs/AD domains/forests |
| **Kerberos delegation** | Capability to forward/act on a principal's behalf to another service; a separate problem |
| **Spring authorities** | Roles/permissions in the app; not automatically granted because the KDC trusts the user |

## 3. Ticket Issuance Flow When User A Reaches Service B

Assume user `lan@USERS.EXAMPLE` accesses Portal in `APPS.EXAMPLE`. The two KDC realms have a trust configured in the direction permitting **USERS → APPS**.

~~~mermaid
sequenceDiagram
    participant B as Browser / user Lan
    participant UA as KDC USERS.EXAMPLE
    participant PA as KDC APPS.EXAMPLE
    participant SP as Spring Portal APPS
    B->>UA: AS-REQ (authenticate lan@USERS.EXAMPLE)
    UA-->>B: TGT in USERS.EXAMPLE
    B->>UA: TGS-REQ for HTTP/portal.apps.example
    UA-->>B: Cross-realm TGT/referral to APPS.EXAMPLE
    B->>PA: TGS-REQ using referral TGT and target SPN
    PA->>PA: Check trust, policy, and identify service key
    PA-->>B: Service Ticket for HTTP/portal.apps.example
    B->>SP: HTTPS Authorization: Negotiate (GSS/SPNEGO token)
    SP->>SP: Keytab/JGSS accepts ticket; identify user principal
    SP->>SP: Look up local account + roles + tenant policy
    SP-->>B: 200 or 403 per local authorization
~~~

If there is an intermediate realm between the two realms:

~~~text
USERS.EXAMPLE ──trust hop──> HUB.EXAMPLE ──trust hop──> APPS.EXAMPLE

Example referral chain:
  krbtgt/HUB.EXAMPLE@USERS.EXAMPLE
  krbtgt/APPS.EXAMPLE@HUB.EXAMPLE
  final service ticket:
  HTTP/portal.apps.example@APPS.EXAMPLE
~~~

**This is a conceptual flow**; the exact number of exchanges and referrals depends on the MIT/AD implementation, trust type, KDC policy, name suffix routing, and client caching. A Windows client may receive referrals through domain/forest hierarchy and Global Catalog; never assume strictly two TGS-REQs or a single static path.

### What Does Each Side Verify?

- The client already holds a TGT from its home realm and never sends the user's password to Portal.
- The source KDC uses the trust relationship to direct the client to the target KDC or next hop.
- The target KDC must accept the trust path, enforce policy, and issue a service ticket for the right SPN.
- The Spring acceptor must hold the **service keytab** matching the **target HTTP SPN** and process a valid GSS context.
- The application must map **user principal + home realm** to an internal account and permissions.

**Trust is configured in the KDC/AD; SPNEGO is handled in Java/web server; authorization is enforced in Spring/app.** One layer does not automatically perform another layer's job.

## 4. One-Way vs. Two-Way Trust: Speaking from the Resource Side

In practice, trust-direction terminology causes confusion because "inbound/outbound" is viewed **from the domain you are looking at**. Write the business statement clearly:

> **Realm APPS trusts realm USERS:** users authenticated by USERS may request tickets to certain services in APPS **if policy permits**.

When expressed in the direction **users moving toward resources**, denote it `USERS → APPS`. That does not imply the reverse `APPS → USERS`.

| Type | Meaning for User Flow | Scope |
| --- | --- | --- |
| **One-way** | Users from A have a trust path to service B, while the reverse is not automatically true | More restricted; typically suitable for serving partner users only |
| **Two-way** | Clients of A and B can access services on the other side per policy | Does not automatically share accounts or roles |
| **Transitive** | A trust path can let client A traverse through B to C when the trust type allows it | Does **not** mean every AD trust is transitive |
| **Non-transitive** | A↔B does not imply A↔C through B | Separate trusts must be configured if needed |
| **Forest trust** | Connects AD forests via forest-root governance | Name suffix routing, selective authentication, SID filtering, permissions |
| **External/domain trust** | Binds specific domains with narrower scope/behavior than forest trust | Does not automatically cover all domains/UPN suffixes |

**Do not treat "A trusts B" and "users of A access B" as the same statement**. In AD terminology, **resource domain/forest B must trust account domain/forest A** so users of A can authenticate to resources in B. Always specify which side holds the accounts and which holds the resources.

### Partner Policy Example

~~~text
Resource owner:  APPS.EXAMPLE (Spring Portal and backend)
Account owner:   PARTNER.EXAMPLE (partner employees)

Business need:
  PARTNER users -> read reports at APPS
  APPS users -> PARTNER resources: NOT NEEDED

Trust design:
  configure only account realm -> resource realm direction
  restrict services / AD selective authentication if used
  local role ROLE_REPORT_VIEWER for allowlisted users
~~~

Two-way trust expands connectivity surface without business benefit, so **never choose two-way "just in case"**. Every domain/forest trust change must be approved by the IAM/AD and security owners.

## 5. What Actually Creates Direct Cross-Realm Trust in MIT Kerberos

According to MIT Kerberos documentation, for a KDC in realm A to authenticate tickets for realm B directly, both sides must share key material for properly structured **cross-realm krbtgt principals**. Operational requirements include:

- Exact principal names matching the source/target realm pair.
- Consistent shared keys/long-term secrets across the linked KDC databases.
- Compatible **Key Version Numbers (KVNO)** and shared encryption types.
- Appropriate ticket lifetimes/renewals, KDC policies, and transited-realm checks.
- KDC discovery, DNS, and network reachability among required entities.
- Clear directional trust, not "trusting every realm" simply by sharing a network diagram.

Example for users in `USERS.EXAMPLE` reaching a service in `APPS.EXAMPLE`:

~~~text
Requested cross-realm service:
  krbtgt/APPS.EXAMPLE@USERS.EXAMPLE

Administrative responsibility:
  KDC admin at USERS + KDC admin at APPS
  share long-term trust key over secure channel, per policy
  ensure compatible key versions and encryption types

Reverse direction if needed:
  krbtgt/USERS.EXAMPLE@APPS.EXAMPLE
  must be designed and configured separately
~~~

**Never write trust keys or passwords into Markdown, CI logs, or application.yml**; application developers should not run `kadmin addprinc krbtgt/...` without an approved change plan and formal authorization. Configuring inter-realm keys is a high-blast-radius KDC admin operation. In AD, use AD trust management rather than manually creating principals in MIT style.

### Rotation Risk

If one side rotates the cross-realm trust key before the other updates, referrals can fail. KDCs may support key history/overlap differently, yet **cannot guarantee** every existing client/ticket survives past rollover. A plan needs both owners, KVNO/enctype checks, testing of both permitted directions, a cutover schedule, and a rollback plan.

**Do not enable RC4 or DES just to rescue an old trust**. Prefer AES per Kerberos/AD interoperability and security baselines; verify actual Windows versions, MIT KDC, Java crypto policies, and service account keys before changing anything.

## 6. [capaths] Is a Path Map, Not a Trust-Creation Command

In MIT Kerberos, `krb5.conf` can contain:

- `[libdefaults]`: default realm, DNS lookup, and Kerberos options.
- `[realms]`: KDC hosts for each realm.
- `[domain_realm]`: maps DNS hostnames/domains to Kerberos realms.
- **`[capaths]`: describes non-hierarchical **cross-realm** paths**, optionally specifying one or more intermediate realms.

Example **direct path** USERS ↔ APPS **only when the KDCs already have trust established**:

~~~ini
[libdefaults]
    default_realm = USERS.EXAMPLE
    dns_lookup_realm = false
    dns_lookup_kdc = true

[realms]
    USERS.EXAMPLE = {
        kdc = users-dc01.users.example
    }
    APPS.EXAMPLE = {
        kdc = apps-dc01.apps.example
    }

[domain_realm]
    .apps.example = APPS.EXAMPLE
    apps.example = APPS.EXAMPLE
    .users.example = USERS.EXAMPLE
    users.example = USERS.EXAMPLE

[capaths]
    USERS.EXAMPLE = {
        APPS.EXAMPLE = .
    }
    APPS.EXAMPLE = {
        USERS.EXAMPLE = .
    }
~~~

**The `.` in `[capaths]`** indicates the two realms share a **direct shared-key relationship** with no intermediate realm on that path. It **is not** a wildcard meaning "trust every realm".

Example **path via HUB** when KDC trusts USERS–HUB and HUB–APPS already exist:

~~~ini
[capaths]
    USERS.EXAMPLE = {
        APPS.EXAMPLE = HUB.EXAMPLE
    }
    APPS.EXAMPLE = {
        USERS.EXAMPLE = HUB.EXAMPLE
    }
    HUB.EXAMPLE = {
        USERS.EXAMPLE = .
        APPS.EXAMPLE = .
    }
~~~

**Scope warning:** `[capaths]` describes paths/transited-field checks **for MIT Kerberos libraries and compatible environments**; Windows AD forest referral behavior relies on domain/forest topology, trusted domain objects, name suffix routing, and KDC referrals. Never treat `capaths` as the sole mechanism or as a command that creates forest trust. In Java 17, support and interpretation of `krb5.conf` options must be verified on the actual JDK.

### Do Not Assume "Adding a Realm Gives SSO"

A common mistake:

~~~ini
[realms]
    USERS.EXAMPLE = { kdc = users-dc01.users.example }
    APPS.EXAMPLE = { kdc = apps-dc01.apps.example }
~~~

Those two entries only tell **where to reach the KDCs**. They **do not** create cross-realm krbtgt keys, make the USERS KDC issue valid referrals, register SPNs, or authorize users. Tests must prove a **real service ticket was issued by the target KDC** and **verified by the Spring acceptor**, not merely that a KDC responds to ping.

## 7. Windows Active Directory: Domain Trusts and Forest Trusts

In AD DS, trusts are managed via **Trusted Domain Objects (TDOs)**, secrets, domain controllers, and AD policies. A forest trust lets KDCs/clients find authentication paths across forests, one-way or two-way depending on business requirements.

In multi-forest AD designs:

- The **account forest** stores user/computer identities.
- The **resource forest** contains web apps, service accounts, file servers, or APIs.
- The resource forest must **trust the account forest** so users from the account forest can reach its resources when authorized.
- Forest trust is established between **forest root domains** per AD architecture.
- AD **name suffix routing** uses UPN/SPN suffixes and forest namespaces to locate the target KDC/forest.
- **Selective authentication** and **SID filtering** are distinct security boundaries beyond the mere existence of trust.
- Services still need registered HTTP SPNs, AD accounts, and matching keytabs.
- The Spring application still needs local user mapping and authorization policies.

~~~mermaid
flowchart LR
    A[Account forest<br/>USERS.EXAMPLE] --> T[Forest trust/referral path]
    T --> B[Resource forest<br/>APPS.EXAMPLE]
    B --> SPN[HTTP/portal.apps.example]
    SPN --> APP[Spring SPNEGO acceptor]
    APP --> AUTH[Local user/tenant authorization]
~~~

This diagram is conceptual and does not depict individual TGT hops. The arrow from account forest to resource forest illustrates **access demand**, not Microsoft's UI "inbound/outbound" labels. When working in the UI, always verify **which domain is trusting** and **which domain is trusted**.

### One-Way Trust in AD

If resource forest **APPS** trusts account forest **USERS**, users in USERS can authenticate to resources in APPS per policy. Users in APPS **do not automatically** gain access to resources in USERS. Symmetric access requires an approved two-way trust.

**Two-way widens the trust surface; it is not a fix for KDC_ERR_S_PRINCIPAL_UNKNOWN.** Check resource-access trust direction and SPNs before altering trust.

## 8. Forest Trust: Name Suffix Routing and Cross-Forest Limits

A KDC often receives a request for a service principal:

~~~text
HTTP/portal.apps.example
~~~

In another forest, it must determine which forest owns that target SPN. An AD forest trust maintains **routed name suffixes** and **Trusted Domain Objects** to forward referrals to the right forest.

Conditions that can cause failures:

1. The forest name suffix for `apps.example` is unrouted or disabled.
2. Two forests have **overlapping/conflicting** suffixes, making routing ambiguous.
3. The user uses a UPN suffix differing from the real Kerberos realm and routing policy does not yet support it.
4. The service SPN is registered on one account while the browser requests an alias hostname lacking an SPN.
5. KDC/DNS/Global Catalog lacks trust visibility, or replication is incomplete.
6. Trust direction does not permit the account forest to authenticate into the resource forest.
7. Selective authentication or another policy intentionally denies access.

Never fix these failures by **rewriting `principal.getName()` in Spring and "allowing login anyway"**. The ticket must be issued and verified from the proper realm/KDC before the app evaluates the principal.

### Forest Trust vs. External Trust

| Aspect | Forest trust | External / domain trust |
| --- | --- | --- |
| Scope | Connects forests with namespace-based routing | Narrower, scoped to specific domains |
| Where created | Forest root domains | Domain level per type/use case |
| Transitivity | Forest trust is transitive across the two-forest relationship | External trust is typically non-transitive |
| SPN/UPN routing | Supports forest name suffix routing | Does not cover all suffixes/hierarchies by default |
| Security | Selective authentication, SID filtering, resource ACLs | Also requires policies suited to the trust type |
| Use case | Enterprise federation across AD forests | Narrowly scoped local domain relationships |

**Never assume an external trust supports every Kerberos referral scenario like a forest trust.** Microsoft documents that mechanisms such as Kerberos Forest Search Order / short-name SPNs do not work over external trusts and require explicit FQDN/SPNs or a proper forest trust. Every decision must verify OS/domain functional levels and documentation for your topology.

## 9. Selective Authentication: Even with Trust, Users Must Be "Allowed to Authenticate"

With Microsoft AD **selective authentication**, the resource forest can require granting **Allowed to Authenticate** to partner-forest users/groups on **specific resource computers/objects**, rather than letting the entire trusted forest authenticate everywhere.

Example:

~~~text
Trust:
  APPS resource forest trusts USERS account forest

Service:
  HTTP/portal.apps.example on app server

Group from USERS:
  USERS\PortalPartners

Allow to Authenticate:
  only service computer/resource objects approved for Portal

App local role:
  only ACTIVE users with partner contract -> ROLE_PARTNER_VIEWER
~~~

These checks **do not replace each other**:

- **Selective authentication** blocks users from a trusted forest from authenticating to unapproved machines/objects per AD policy.
- **Local ACL/RBAC** on the target resource/app governs resource access after authentication.
- **Spring Security `UserDetailsService`/authorities** must still check business entitlement and tenant.
- You cannot replace selective authentication by hiding a UI button, nor replace local roles with the "Allowed to Authenticate" right.

If an organization enforces selective authentication without granting permission on the right resource/host, **KDC/AD can reject** even though the forest trust exists. Support engineers must distinguish "trust broken" from "intentionally denied by policy".

### SID Filtering and SIDHistory

AD uses **Security Identifiers (SIDs)** to authorize Windows resources. Across cross-forest trusts, **SID filtering** prevents an untrusted forest from "carrying over" untrusted SIDs in authorization data. `SIDHistory` aids migrations yet can be abused if trust settings are overly permissive.

**Never disable SID filtering or broadly enable `EnableSIDHistory` just to make a permission-denied app start working.** If `SIDHistory` is genuinely required for a migration, require a threat assessment, time limit, trust-boundary review, and change approval.

For a Spring app that extracts a Kerberos principal and looks up local roles, most SID/PAC enforcement occurs in the AD/Windows layer rather than inside a Java controller. **Never parse a PAC yourself and grant `ROLE_ADMIN` from an unvetted SID**.

## 10. Trust Does Not Equal Access Rights or Delegation

Suppose:

~~~text
User:
  lan@USERS.EXAMPLE

Kerberos cross-realm trust:
  PASS (client obtains service ticket to APPS)

Spring acceptor:
  PASS (valid service principal/keytab)

Local account:
  lan@USERS.EXAMPLE has no approved account in Portal

Expected:
  Spring denies access or runs JIT workflow per policy
  never grant ROLE_ADMIN just because trust PASSED
~~~

For multi-organization apps, a **safe identity key** must preserve the source namespace:

~~~text
(trustedRealm, canonicalPrincipal)
  -> localUserId
  -> tenantMembership
  -> approvedAuthorities
~~~

Do not drop the realm and key solely by `lan`, because `lan@USERS.EXAMPLE` differs from `lan@PARTNER.EXAMPLE`; UPN suffixes and email domains can also differ from the Kerberos realm. If account linking is needed, build a dedicated verification workflow.

### Double Hop and Constrained Delegation

A browser authenticating via Kerberos to Spring Portal **does not automatically** let Portal access another SQL/SMB/HTTP backend on the user's behalf. That is **delegation/double hop**, separate from accepting a user from another realm.

- AD supports Kerberos Constrained Delegation (KCD), Resource-Based Constrained Delegation (RBCD), and S4U under policy constraints.
- A service account should be allowed to delegate strictly to **specific target SPNs** and nothing more.
- Cross-forest delegation has distinct restrictions tied to trust flags and security updates.
- Never enable **unconstrained delegation** to "fix" double-hop errors, as it drastically widens abuse potential.
- If a Java/Spring app does not actually perform delegation, do not enable Kerberos forwardable/proxiable flags unconditionally.
- Downstream services must validate tickets and enforce authorization independently; copying a username into an HTTP header is not safe delegation.

## 11. krb5.conf and Java 17: Easily Overlooked Limits

Oracle Java 17 supports configuring:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
~~~

Or when only a single realm/KDC is needed, **both** may be used:

~~~text
-Djava.security.krb5.realm=USERS.EXAMPLE
-Djava.security.krb5.kdc=users-dc01.users.example
~~~

**Official Oracle warning:** if you use only the two system properties `java.security.krb5.realm` and `java.security.krb5.kdc` **without a `krb5.conf`**, cross-realm authentication **may not work** due to missing realm/path settings. Both properties must be set together if used. For multi-realm SPNEGO, supply a complete `krb5.conf` and test on the target JDK/runtime.

### Example krb5.conf for User A Reaching Service B

~~~ini
[libdefaults]
    default_realm = USERS.EXAMPLE
    dns_lookup_kdc = true
    dns_lookup_realm = false
    rdns = false

[realms]
    USERS.EXAMPLE = {
        kdc = users-dc01.users.example
        kdc = users-dc02.users.example
    }
    APPS.EXAMPLE = {
        kdc = apps-dc01.apps.example
        kdc = apps-dc02.apps.example
    }

[domain_realm]
    users.example = USERS.EXAMPLE
    .users.example = USERS.EXAMPLE
    apps.example = APPS.EXAMPLE
    .apps.example = APPS.EXAMPLE

[capaths]
    USERS.EXAMPLE = {
        APPS.EXAMPLE = .
    }
    APPS.EXAMPLE = {
        USERS.EXAMPLE = .
    }
~~~

This is an **illustrative configuration for an already-existing direct trust**. In an acceptor app running in APPS, `default_realm` may need to be `APPS.EXAMPLE` depending on keytab/JAAS/service principal and client behavior; do not blindly copy a USERS client example onto an APPS SP server. **Changing default_realm alone does not create KDC trust**.

### Java Kerberos Options Are Not Trust Controls

- `java.security.krb5.conf` points to the configuration file.
- `javax.security.auth.login.config` points to a JAAS configuration file when using that login pattern.
- `javax.security.auth.useSubjectCredsOnly` changes where GSS looks for credentials and must be evaluated per flow.
- `sun.security.krb5.debug` is strictly for short-term diagnostics in a safe environment.
- `KRB5_CONFIG` is an environment variable commonly used by MIT libraries; **do not assume** the Java provider handles every environment variable identically to MIT.
- `krb5.conf [capaths]` routes/checks trust paths; **it does not store keytabs**.
- `javax.net.ssl.trustStore` governs TLS CA trust, **not Kerberos cross-realm trust**.

**Do not confuse an HTTPS PKIX truststore with inter-KDC Kerberos key-material trust.** They are two different key systems and threat models.

## 12. DNS, KDC Discovery, and Name Canonicalization

Multi-realm infrastructure relies on accurate DNS. Illustrative DNS SRV records:

~~~dns
_kerberos._tcp.users.example. IN SRV 0 100 88 users-dc01.users.example.
_kerberos._tcp.apps.example.  IN SRV 0 100 88 apps-dc01.apps.example.
_kerberos._udp.users.example. IN SRV 0 100 88 users-dc02.users.example.
~~~

- Clients must find the KDC for both the home realm and target realm (directly or via referrals).
- AD clients also use DC Locator and Global Catalog/NetLogon depending on trust topology.
- `[domain_realm]` affects hostname/realm mapping in MIT/JGSS contexts.
- SPN `HTTP/portal.apps.example` must be registered on **the right service account in the target realm**, and Spring's keytab must hold the matching key.
- DNS aliases/CNAMEs, VIP/load-balancer hostnames, and canonicalization can make clients request an unexpected SPN.
- SNI/TLS certificate SANs for `portal.apps.example` are an **HTTPS** concern and do not make a Kerberos SPN valid.

**Do not register `HTTP/backend-pod-01` when browsers visit `https://portal.apps.example` without a matching SPN design**. Browsers normally request a ticket for the public hostname, so the Spring acceptor must be able to decrypt tickets for the public service.

### Use Explicit FQDNs

For cross-forest Kerberos, prefer **fully qualified domain names (FQDNs)** and explicit SPNs rather than short names that undergo search-suffix or canonicalization differences across Windows, Linux, and proxies. Microsoft notes that certain forest search order / short-name SPN mechanisms do not work over external trusts, so check the actual trust type.

## 13. Firewalls and Limits That Spring Code Cannot Solve

A trust may exist while authentication still fails because KDCs/DCs cannot reach one another or clients cannot reach the right KDC. There is no universal "just open port 88" checklist for every AD forest trust.

| Service | Common Ports | When Needed |
| --- | --- | --- |
| **DNS** | UDP/TCP **53** | Realm/KDC/hostname/DC discovery |
| **Kerberos** | UDP/TCP **88** | AS/TGS, referral/service tickets |
| **Kerberos password change** | TCP/UDP **464** | When password/key workflows require it |
| **LDAP/LDAPS** | **389** / **636** | Directory queries or AD trust operations per topology |
| **Global Catalog** | **3268** / **3269** | AD cross-forest object/name lookups per policy |
| **RPC Endpoint Mapper** | TCP **135** | AD/LSA/NetLogon/RPC functions when required |
| **Dynamic RPC** | Modern Windows typically TCP **49152–65535** | Certain DC-to-DC/LSA/NetLogon flows depending on architecture |
| **SMB** | TCP **445** | Certain trust/domain ops; not every browser SPNEGO request |
| **NTP/time sync** | UDP **123** | Clock synchronization when topology uses NTP |
| **HTTPS to Portal** | TCP **443** | Browser→Spring, or TLS ingress |

**Never expose any of these ports broadly to the Internet.** Microsoft notes not every port is needed in every topology; design a **source → destination → purpose** matrix with least privilege, DNS/DC segmentation, and separate trust-creation vs. steady-state rules. A Spring backend accepting GSS tokens **does not necessarily** need direct connectivity to every KDC of every realm if keytab/identity lookup and flow do not require it; browser/KDC clients and AD/DC traffic have those respective needs.

### Network Boundaries That Commonly Cause Failures

- VPN/site-to-site firewall allows only the source realm's KDC and blocks the target realm's KDC.
- Split-brain DNS causes the browser to pick the wrong target realm or an alias hostname.
- DC Locator selects a domain controller unreachable across the firewall.
- Cross-forest name suffix routing is unsynchronized or conflicting.
- The app pod lacks LDAP/LDAPS reachability to the directory used by `UserDetailsService`, even though the GSS acceptor verified the token.
- Service mesh/proxy strips or alters the `Authorization: Negotiate` header.
- Load balancer rewrites the hostname, causing the browser's requested SPN not to match the keytab.
- UDP fragmentation/dropped Kerberos replies; TCP 88 support per policy is needed.
- KDC/realm clocks drift or Kerberos enctypes are incompatible.

**Diagnose KDC tickets and Spring local lookup as two separate systems**: if a service ticket reaches Spring and verifies cleanly yet the LDAP user lookup fails, the fault lies in **directory connectivity/local identity service**, not in the cross-realm trust key.

## 14. Clock Skew, Ticket Lifetimes, Encryption, and Rotation

Kerberos uses timestamps/authenticators and replay defenses. Client/KDC/service clock drift beyond tolerance triggers `KRB_AP_ERR_SKEW` or equivalent even when trust keys are valid.

**Conditions to monitor:**

1. NTP / Windows Time Service synchronized per domain/forest policy.
2. Ticket lifetimes, renewability, and transited-policy behavior consistent with requirements.
3. **KVNO and encryption types** of cross-realm trust keys stay aligned during rotation.
4. Service account keytab contains the active **service principal, KVNO, and enctype**.
5. KDCs do not require weak DES/RC4 outside the approved baseline.
6. Ticket/PAC/authorization data sizes can grow large when users belong to many AD groups, impacting HTTP header/proxy limits.
7. Kerberos replay cache and GSS security context checks are never disabled arbitrarily.
8. Trust paths may span multiple KDCs, adding latency and dependencies; configure metrics and timeouts accordingly.

**Never "fix" clock skew by setting infinite tolerance**: it weakens replay protection and hides infrastructure faults. **Never "fix" enctype errors by enabling RC4 forest-wide** for an old keytab; coordinate key and runtime updates instead.

### Key Rotation Requires Two Separate Plans

- **Cross-realm trust secrets / krbtgt keys:** managed by both KDC/AD admin teams; test referral tickets after rotation.
- **HTTP service keytab:** managed by the app owner and IAM, distributed to all replicas, verifying KVNO/enctype of `HTTP/portal.apps.example`.

The two key types **serve different purposes**. Never put cross-realm krbtgt keys in an app keytab. When login fails after rotation, determine whether the ticket broke at **referral** or at the **service acceptor**.

## 15. Browser SPNEGO and Spring Security Kerberos

From the HTTP perspective:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

A managed browser can acquire a service ticket from the KDC (traversing trust if needed) and send:

~~~http
GET /reports HTTP/1.1
Host: portal.apps.example
Authorization: Negotiate <base64-GSS-token>
~~~

`Negotiate` is a GSS/SPNEGO negotiation mechanism. **Never assume every Negotiate token is Kerberos**: under certain Windows browser/policy states it can fall back to NTLM. When cross-realm Kerberos is required, verify the actual mechanism used and reject mechanisms disallowed by security policy.

Spring Security Kerberos uses:

| Component | Function |
| --- | --- |
| `SpnegoEntryPoint` | Challenges with HTTP `WWW-Authenticate: Negotiate` and fallback login when configured |
| `SpnegoAuthenticationProcessingFilter` | Extracts GSS/SPNEGO token from header |
| `KerberosServiceAuthenticationProvider` | Verifies service ticket via Kerberos ticket validator |
| `SunJaasKerberosTicketValidator` | Uses JAAS/JGSS with the HTTP service principal and keytab |
| `UserDetailsService` | Maps the verified principal to internal user/authorities |
| `SecurityFilterChain` | Protects routes and enforces dedicated authorization |

**There is no `trustedRealms=["*"]` property in Spring Security that establishes KDC cross-realm trust.** The application merely verifies valid tickets via the GSS acceptor and resolves user identity/roles. Realm trust lives in the KDC/AD, not inside a `requestMatchers` rule or login form.

### Illustrative Spring Bean Fragment

The snippet below requires matching Spring Security Kerberos modules, a compatible JDK, and a real keytab:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class CrossRealmSpnegoBeans {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.apps.example@APPS.EXAMPLE");
        validator.setKeyTabLocation(
                new FileSystemResource(
                    "/etc/security/keytabs/portal.keytab"));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService directoryUsers) {
        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(directoryUsers);
        return provider;
    }
}
~~~

**This is a Spring configuration fragment, not a standalone Java 17 file**; `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, AuthenticationManager, SecurityFilterChain, UserDetailsService, and browser fallback must be configured in the real application. Verify Spring Security Kerberos version/namespace in the dependency tree.

**Never store service keytabs in the source tree or public images.** Mount under a secret volume with minimal permissions and rotate keytabs in sync across pods.

### A Passing Trust Can Still Fail in Spring

After `SunJaasKerberosTicketValidator` verifies the ticket, the provider needs `UserDetailsService` to locate the user. With multi-realm users:

~~~text
Validated Kerberos principal:
  lan@USERS.EXAMPLE

Rejected local lookup:
  app looks up only "lan" in APPS domain without distinguishing realm
  or LDAP queries only the default realm

Correct approach:
  trustedPrincipal = ("USERS.EXAMPLE", "lan")
  lookup approved identity-link registry
  require ACTIVE status and tenant grant
  assign minimal ROLE_REPORT_VIEWER
~~~

**Never strip `@REALM` and merge users automatically**. If the local directory knows only APPS employees, implement an explicit identity mapping/federated lookup for partner users; never open LDAP binds/queries to arbitrary realms supplied by user input.

## 16. Reverse Proxies, Containers, and Keytabs: Ticket Acceptance Conditions

Architecture:

~~~text
Browser USER in USERS.EXAMPLE
     |
     | https://portal.apps.example
     | Authorization: Negotiate <ticket for HTTP/portal.apps.example>
     v
HTTPS ingress/load balancer
     |
     +------ Spring pod A
     |
     +------ Spring pod B

Kerberos service realm: APPS.EXAMPLE
Keytab on both pods:    HTTP/portal.apps.example@APPS.EXAMPLE
~~~

The browser typically requests a ticket for the **URL's public hostname**, not the pod name. Therefore:

- SPN `HTTP/portal.apps.example` must exist in the right target realm/AD account.
- Spring's keytab must match the active service principal and long-term key.
- All replicas must have matching keytabs/KVNOs with protected secret distribution.
- Ingress must **pass through `Authorization: Negotiate`** if Spring is the acceptor.
- If ingress terminates Kerberos itself and forwards a username header, the trust boundary shifts: Spring must authenticate the ingress→backend channel, strip client-sent headers, and enforce explicit proxy-identity policy.
- HTTPS certificate SAN/hostname for Portal differs from the Kerberos SPN; both are required.
- If Windows Extended Protection / Channel Binding Tokens (CBT) are enforced, TLS termination/relay through proxies may require compatible design; **never disable Extended Protection domain-wide for convenience**.
- Session affinity does not replace issuing the proper Kerberos keytab; sticky sessions cannot fix a wrong SPN.

### Container Infrastructure Can Constrain Cross-Realm

Kubernetes pods do not necessarily join a Windows domain. A Java acceptor can use a proper keytab/JAAS to accept GSS tokens, yet **user-detail lookups** and certain KDC/LDAP requirements need dedicated network/DNS/secret management. Pods with drifted clocks, differing DNS policies, read-only mounts, or unsynchronized principal configs can cause hard-to-reproduce errors.

**Never grant privileged container mode or mount full host AD credentials just to run SPNEGO.** Use a minimal service identity/keytab and approved connections.

## 17. Minimal Trust Design Roadmap Before Deployment

**Step 1 — Define the use case:** who from which realm needs which service, for what data, and is mutual access needed?

**Step 2 — Choose the trust type:** direct MIT cross-realm, AD forest trust, external trust, or an identity broker/gateway. Specify account realm, resource realm, trust direction, and transitivity.

**Step 3 — Security analysis:** SID filtering, selective authentication, name suffix routing, risk from partner admin autonomy, token/PAC claims, approved groups, and delegation restrictions.

**Step 4 — Review KDC/keys:** cross-realm principals/secrets or AD TDOs, supported encryption types, KVNO, key rollover, and dual-side admin responsibilities.

**Step 5 — DNS/KDC connectivity:** FQDNs, SRV/DC locator, split DNS, ports 53/88, and required AD ports per matrix.

**Step 6 — Design the HTTP service:** public URL, target SPN, service account, keytab, load balancing, and reverse-proxy Negotiate pass-through.

**Step 7 — Configure Java/OS:** `krb5.conf`, JVM options, JAAS/JGSS, and keytab mounts for Spring; never fabricate trust in YAML.

**Step 8 — Principals and permissions:** realm allowlist, identity linking, local account status, tenant membership, least-privilege RBAC, and denying unknown users.

**Step 9 — E2E testing:** home-realm TGT → referral → service ticket → GSS accept → Spring roles; test failure paths too.

**Step 10 — Operations:** monitoring, key rotation, trust changes, DC health, auditing, break-glass, and clear rollback.

If a partner cannot or will not establish a forest/KDC trust, evaluate **OIDC/SAML federation via an identity broker** instead of demanding deep Kerberos connectivity across networks. That is an **alternative architecture**, not "enabling SPNEGO over the Internet" with a property.

## 18. Standalone Java 17: Simulating Trust Paths and Local Authorization

The pure Java example below illustrates two **separate** requirements: having a referral path from the user realm to the service realm, and having **application-level authorization approval**. It does not contact a KDC, issue tickets, or inspect keytabs or SIDs.

The design assumes a **directed edge** in the graph means only "a path from the account realm to the resource realm is **approved in this learning model**". It is **not** an AD `trustDirection` value or a real `[capaths]` file. The program models a one-way route USERS → HUB → APPS without the reverse path.

Create file **`CrossRealmTrustDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class CrossRealmTrustDemo {

    static final String USERS = "USERS.EXAMPLE";
    static final String HUB = "HUB.EXAMPLE";
    static final String APPS = "APPS.EXAMPLE";

    static final String REQUIRED_SERVICE =
            "HTTP/portal.apps.example@APPS.EXAMPLE";

    static final Map<String, List<String>> ROUTES = Map.of(
            USERS, List.of(HUB),
            HUB, List.of(APPS),
            APPS, List.of());

    static List<String> findPath(String from, String to) {
        ArrayDeque<String> queue = new ArrayDeque<>();
        Map<String, String> parent = new HashMap<>();

        parent.put(from, null);
        queue.add(from);

        while (!queue.isEmpty()) {
            String current = queue.remove();
            if (current.equals(to)) {
                ArrayList<String> reversed = new ArrayList<>();
                for (String step = to;
                        step != null; step = parent.get(step)) {
                    reversed.add(step);
                }
                java.util.Collections.reverse(reversed);
                return reversed;
            }

            for (String next : ROUTES.getOrDefault(current, List.of())) {
                if (!parent.containsKey(next)) {
                    parent.put(next, current);
                    queue.add(next);
                }
            }
        }
        return List.of();
    }

    static String authorize(
            String userRealm,
            String targetService,
            boolean localAccountApproved) {

        if (findPath(userRealm, APPS).isEmpty()) {
            return "DENY: no trust path";
        }
        if (!REQUIRED_SERVICE.equals(targetService)) {
            return "DENY: wrong service principal";
        }
        if (!localAccountApproved) {
            return "DENY: local authorization missing";
        }
        return "ALLOW: route, service and local policy";
    }

    public static void main(String[] args) {
        System.out.println("Referral route: "
                + String.join(" -> ", findPath(USERS, APPS)));

        System.out.println("Reverse route: "
                + !findPath(APPS, USERS).isEmpty());

        System.out.println("Correct service: "
                + REQUIRED_SERVICE.equals(
                    "HTTP/portal.apps.example@APPS.EXAMPLE"));

        System.out.println("Before local grant: "
                + authorize(USERS, REQUIRED_SERVICE, false));

        System.out.println("After local grant: "
                + authorize(USERS, REQUIRED_SERVICE, true));

        System.out.println("Wrong SPN: "
                + authorize(USERS,
                    "HTTP/other.apps.example@APPS.EXAMPLE", true));

        System.out.println("Unknown realm: "
                + authorize("UNTRUSTED.EXAMPLE",
                    REQUIRED_SERVICE, true));
    }
}
~~~

Run on JDK 17 or newer:

~~~bash
javac CrossRealmTrustDemo.java
java CrossRealmTrustDemo
~~~

**Exact stdout:**

~~~text
Referral route: USERS.EXAMPLE -> HUB.EXAMPLE -> APPS.EXAMPLE
Reverse route: false
Correct service: true
Before local grant: DENY: local authorization missing
After local grant: ALLOW: route, service and local policy
Wrong SPN: DENY: wrong service principal
Unknown realm: DENY: no trust path
~~~

**Interpretation:**

1. `Referral route` has two hops per the defined demo graph. This only models an **approved path**, not that KDCs hold cross-realm keys.
2. `Reverse route: false` illustrates one-way trust/use case. A real AD two-way config would behave differently.
3. `Correct service: true` is a **principal-name comparison**, not service ticket verification.
4. `Before local grant` still returns **DENY** despite a valid trust path: Kerberos authentication does not automatically grant business roles.
5. `After local grant` is **ALLOW in the model only**, not proof that the KDC actually authenticated an account.
6. `Wrong SPN` denies when the target service differs from the public service.
7. `Unknown realm` has no route, returning DENY even when the local-grant boolean is true.

**Mandatory limitation:** the Java graph does not verify Kerberos `krbtgt` keys, transited-field validation, AD selective authentication/SID filtering, SAN/TLS, ticket lifetime/replay, DNS, KVNO/enctype, GSS tokens, KDC referral algorithms, or a real `UserDetailsService`. **Never use the `authorize` function from this program in place of Kerberos/Java GSS/API production security checks.**

## 19. Testing Real Kerberos in a Lab Environment

With a managed MIT Kerberos/Linux client:

~~~bash
# 1. Obtain a TGT from the user realm:
kinit lan@USERS.EXAMPLE

# 2. View TGT/referral tickets in the cache:
klist

# 3. Request a service ticket for the app in the target realm:
kvno HTTP/portal.apps.example@APPS.EXAMPLE

# 4. Inspect the acquired tickets again:
klist

# 5. On the Spring acceptor/pod only: inspect keytab metadata:
klist -kte /etc/security/keytabs/portal.keytab
~~~

These commands are illustrative, **with no fixed stdout**. If real trust does not exist, `kvno` must fail or report an appropriate error. A successful `kvno` shows the KDC can issue a service ticket under the client/trust configuration; **it does not prove the Spring backend can decrypt the ticket**.

In AD/Windows with appropriate diagnostic privileges:

~~~powershell
# User machine: inspect ticket cache:
klist

# User machine: request service ticket:
klist get HTTP/portal.apps.example

# Domain admin/RSAT: query SPN:
setspn -Q HTTP/portal.apps.example

# Detect SPN duplicates:
setspn -X

# Check trust status (read-only diagnostics per permissions):
nltest /domain_trusts

# List trust configuration (read-only):
Get-ADTrust -Filter *
~~~

`Get-ADTrust` requires the RSAT ActiveDirectory module and query permissions; for forest trusts, inspect the **exact forest root/domain**. `nltest` displays trust relationships but does not replace a Kerberos service ticket test. Windows tools vary in syntax/capabilities across OS/domain versions; no single command verifies all trust, SID filtering, and app permissions.

### Safely Inspecting `[capaths]`

Read configuration files only, or inspect MIT Kerberos `KRB5_TRACE` on a **test machine** if permitted:

~~~bash
# Run only on a test machine with authorized log access:
KRB5_TRACE=/dev/stderr kvno HTTP/portal.apps.example@APPS.EXAMPLE
~~~

Traces can expose usernames/realms/hostnames and infrastructure info, so store securely and redact sensitive data. Never print ticket bytes or passwords into logs.

Java 17 provides:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
-Dsun.security.krb5.debug=true
~~~

**Enable debugging only briefly on staging** because logs can expose Kerberos metadata, principals, and KDC connections. In production, metrics should aggregate KDC errors, latency, and Spring auth outcomes at a summary level.

## 20. Layered Test Matrix

| Test | Scenario | Expectation |
| --- | --- | --- |
| Direct trust | USERS KDC and APPS KDC have compatible keys/policies | Client gets cross-realm referral/service ticket |
| No trust | APPS does not trust USERS | Valid cross-realm service ticket cannot be issued |
| Trust direction | USERS → APPS approved, APPS → USERS not | Only the approved direction works |
| Trust path via HUB | USERS → HUB → APPS configured and trusted | Valid referral path exists |
| Wrong capaths | Path declared without trust keys | Fail closed |
| Wrong KDC | DNS/SRV points to another realm's KDC | Fails or invalid referral |
| Name suffix conflict | Overlapping AD forest suffixes | Routing rejected/misrouted; admin must fix |
| External vs. forest | Short-name SPN over external trust | Do not assume forest-trust support |
| Selective authentication | Partner user lacks Allowed to Authenticate | Denied despite existing trust |
| SID filtering | Ticket carries SIDs outside trust boundary | AD policy strips/rejects per trust type |
| ST-like service ticket | Service ticket for an unfamiliar SPN | Spring acceptor rejects |
| Valid SPN/keytab | Public HTTP SPN with right KVNO/enctype | GSS/SPNEGO accept succeeds |
| Stale keytab | Service account key rotated | Ticket verification fails |
| Wrong principal | User from another realm mapped to same short username | Accounts are not merged |
| Local account disabled | Valid ticket, yet user disabled | Spring denies access |
| Local role absent | Valid ticket, missing `ROLE_REPORT_VIEWER` | HTTP 403 on protected route |
| Admin spoof | User from partner realm has an "Admins" group | Does not automatically grant `ROLE_ADMIN` |
| DNS split horizon | Client resolves wrong KDC/host | Diagnose DNS; do not bypass |
| KDC firewall | UDP/TCP 88 blocked on required path | Reproducible Kerberos failure |
| AD RPC | DC trust flows missing required ports | Trust verification/maintenance fails |
| Clock skew | User/KDC/SP clocks drifted | Kerberos rejects |
| Enctype mismatch | KDC/trust/service share no cipher | Reject; coordinate key updates |
| PAC size | User in too many groups, oversized token | Check header/proxy limits; do not raise infinitely |
| Proxy strips Negotiate | Authorization header disappears | 401/fallback; fix ingress |
| NTLM fallback | Client does not use Kerberos | Do not count as cross-realm Kerberos PASS |
| Cross-forest double-hop | Portal calls backend on user's behalf | Only when delegation policy is approved |
| Multi-node rollout | Pods have differing keytabs/krb5.conf | Detect drift and fix via change plan |

**End-to-end PASS** happens only with: valid user home TGT → valid KDC referral → target service ticket → Spring GSS accept → proper principal namespace → local permission. Never use ping results, a bare `Authorization: Negotiate` header, or a Java graph demo to claim Kerberos trust is working.

## 21. Symptom-Based Diagnostic Runbook

| Symptom | Where to Investigate First | What Not to Do |
| --- | --- | --- |
| `KDC_ERR_WRONG_REALM` | Realm mapping/DNS/referral hint/name suffix | Do not edit username realms to bypass checks |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | Target SPN unregistered or wrong routing | Do not enable wildcard SPN/AD trust |
| `KDC_ERR_PRINCIPAL_NOT_UNIQUE` | Duplicate servicePrincipalName | Do not delete SPNs without identifying owners |
| `KRB_AP_ERR_MODIFIED` | Keytab wrong KVNO/enctype/account/SPN | Do not disable GSS integrity checks |
| `KDC_ERR_ETYPE_NOSUPP` | Trust key/service key encryption mismatch | Do not enable weak crypto unconditionally |
| `KRB_AP_ERR_SKEW` | NTP/time sync across client, KDC, Spring | Do not widen skew infinitely |
| `Cannot find KDC for realm` | krb5.conf, SRV, DNS, firewall | Do not point KDC to an untrusted host |
| `Server not found in Kerberos database` | SPN/target realm | Do not grant realm-based admin roles |
| `Authentication failed: Service not found` | SPN/alias, user details, filter chain | Do not disable authentication |
| Browser 401 loop | Browser policy, missing ticket, proxy, keytab | Do not enable `permitAll` |
| GSS accepted, yet Spring 403 | Local UserDetailsService/roles/tenant | Do not open two-way trust to fix 403 |
| Works in domain A, fails in domain B | Trust direction, suffix routing, selective auth | Do not disable SID filtering |
| Keytab works on pod A, fails on pod B | Keytab mount/KVNO/JDK config drift | Do not copy keys over insecure channels |
| AD trust verifies, yet SSO fails | SPN, browser DNS, separate app authorization | Do not rush to blame broken trust |
| Referral loops / high latency | capaths/DC locator/forest topology | Do not increase timeouts indefinitely |
| Cross-forest user "not found" | Directory lookup user namespace/UPN mapping | Do not strip realm and auto-link email |
| Double hop denied | KCD/RBCD/trust delegation flags | Do not enable unconstrained delegation |

**Least-invasive debugging order:** (1) actual hostname/SPN; (2) user TGT and target service ticket; (3) trust direction/referral path; (4) network/DNS/clocks; (5) SPN owner/keytab/KVNO; (6) browser/proxy Negotiate; (7) Spring principal mapping; (8) local authorization. Record failures at the exact layer rather than "granting broader permissions" to mask errors.

## 22. Cost and Architectural Limitation Warnings

Cross-realm trust across **real infrastructure** is not just an `application.yml` file; it typically demands:

- Two realm/forest admin teams coordinating and accepting a long-term trust relationship.
- Network/DC-to-DC routing potentially spanning WAN/VPN/peering; firewalls/segmentation must remain protected.
- High-availability and failover capacity for KDC/DNS/Global Catalog/NetLogon.
- Separate HTTPS certificate management for browser/SP alongside Kerberos keytabs/trust keys.
- Synchronizing clocks, crypto policies, and OS security patches across multiple parties.
- Managing **UPN/AD groups/PAC/SIDHistory** and cross-organization user mappings.
- Procedures to rotate trust secrets and service keys affecting multiple services.
- Assessing risk from partners having admin autonomy who can create principals/groups in their namespace.
- Auditing, monitoring, SID/group-spoof detection, and incident response ownership.
- Browser SPNEGO limitations on non-domain-joined, mobile, or unmanaged devices.
- No automatic guarantee of backend delegation just because a user passed SPNEGO at the front end.

**Never establish a broad cross-forest trust just to give a web portal one login screen** when partners only need access to a few apps. Evaluate **OIDC/SAML federation via an identity broker/provider** with narrower network boundaries and better Internet/managed-cloud reachability—keeping in mind those protocols have their own identity/claim/consent semantics and should not be called "Kerberos cross-realm" when no KDC trust actually exists.

## 23. Practice Scenarios and Questions

### Scenario A — Two KDCs Added to krb5.conf Without Referrals

The app team adds `USERS.EXAMPLE` and `APPS.EXAMPLE` under `[realms]`; DNS resolves cleanly, yet `kvno HTTP/portal.apps.example@APPS.EXAMPLE` fails.

**Explanation:** configuring KDC discovery **does not create cross-realm trust keys**. KDC/AD owners must verify trust, referral path, direction, encryption, and policy. Never just add `capaths` assuming trust was created.

### Scenario B — Trust Exists, Yet Partner Cannot Reach the Server

Forest APPS trusts USERS. AD enforces selective authentication, yet `lan@USERS.EXAMPLE` lacks Allowed to Authenticate on the target resource/host.

**Outcome:** authentication can be blocked by AD policy. This is not a Spring role-mapping bug; request minimal access for the target resource via the AD owner. Local application entitlement is still required afterward.

### Scenario C — Same Username in Two Realms

`lan@USERS.EXAMPLE` and `lan@PARTNER.EXAMPLE` share the username `lan`.

**Outcome:** two principals in different namespaces. If the app calls `loadUserByUsername("lan")` for both, an **account collision** can occur. Preserve the trusted realm in the linking key and enforce identity verification.

### Scenario D — Logged Into Portal, Yet Cannot Call Downstream SQL

Spring verified SPNEGO from USERS, yet Portal cannot use Lan's identity on a SQL service in the APPS forest.

**Explanation:** this is **delegation/double-hop**. It requires KCD/RBCD/S4U/trust configuration and SQL permissions per policy; never forward the browser token directly or turn on unconstrained delegation.

### Scenario E — Another Forest Trust Has a Name Suffix Conflict

Users with the same AD account can log in locally, yet cross-forest referrals to SPN `HTTP/portal.apps.example` misroute or fail to route.

**Explanation:** check suffix routing in TDO/forest trust and the SPN hostname rather than changing Spring roles or enabling "trust everyone".

### Scenario F — Kerberos Passes, Yet User Still Gets 403

The KDC issued a service ticket and `SunJaasKerberosTicketValidator` accepted it, yet Spring `UserDetailsService` finds no active local user authorized to view reports.

**Outcome:** 403 may be the correct behavior. Provision the account link/role after approval rather than loosening KDC trust or removing security filters.

## 24. End-of-Lesson Checklist

- [ ] Distinguished realm, KDC, principal, SPN, TGT, and service ticket.
- [ ] Identified account realm, resource realm, and required **user → service direction**.
- [ ] KDC trust keys/TDOs are managed by their owners, never stored in app keytabs.
- [ ] Recognized `krbtgt/DEST@SRC` is an inter-realm principal, not Spring's SPN.
- [ ] Did not conflate direct/transitive/non-transitive forest/external trusts.
- [ ] Understood `[capaths]` only describes paths and does not create keys/trust.
- [ ] `krb5.conf` has proper KDC/realm/domain mappings for Java.
- [ ] Did not rely solely on `java.security.krb5.realm/kdc` omitting required cross-realm data.
- [ ] Verified AD forest trust direction and name suffix routing.
- [ ] SID filtering and selective authentication are approved, never disabled to silence random errors.
- [ ] Assessed DNS/FQDN, DC/KDC reachability, and firewall matrix.
- [ ] KDC/service key enctypes, KVNO, rotation, and time sync are aligned.
- [ ] Browser uses the right HTTP SPN for the public hostname.
- [ ] Spring SPNEGO acceptor holds the right service keytab/principal, never cross-realm trust keys.
- [ ] Reverse proxy pass-through Negotiate or trusted-header architecture is clear.
- [ ] NTLM fallback is not mistaken for cross-realm Kerberos success.
- [ ] Spring principal mapping preserves **realm namespace** and checks local user status and tenant.
- [ ] Never grants admin simply because a realm is trusted or an AD group looks like admin.
- [ ] Double-hop/delegation enabled only with clear KCD/RBCD policy, never unconstrained.
- [ ] Positive/negative E2E tests verify AS/TGS referral + service ticket + GSS + authorization.
- [ ] Operations/monitoring/rollover/runbooks and owners exist for every trust.
- [ ] Considered an OIDC/SAML identity broker when Kerberos trust would be too broad or risky.

## 25. Official References

1. [RFC 4120 — The Kerberos Network Authentication Service V5](https://www.rfc-editor.org/rfc/rfc4120): principals, KDC, AS/TGS, and cross-realm referral/ticket semantics.
2. [MIT Kerberos — Cross-realm authentication](https://web.mit.edu/kerberOS/krb5-1.22/doc/admin/database.html): `krbtgt` cross-realm keys, KVNO/encryption types, and KDC administration.
3. [MIT Kerberos — krb5.conf and capaths](https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/conf_files/krb5_conf.html): `[realms]`, `[domain_realm]`, `[capaths]`, and transited path checks.
4. [Oracle Java 17 — Kerberos Requirements](https://docs.oracle.com/en/java/javase/17/security/kerberos-requirements.html): JVM krb5.conf, realm/kdc properties, and cross-realm limitations.
5. [Oracle Java 17 — Kerberos GSS-API Mechanism](https://docs.oracle.com/en/java/javase/17/security/kerberos-5-gss-api-mechanism.html): `[capaths]` support, realm mapping, and client settings.
6. [Microsoft — How trusts work for AD forests](https://learn.microsoft.com/en-us/entra/identity/domain-services/concepts-forest-trust): trusted domain objects, forest trust, name suffix routing, and KDC referrals.
7. [Microsoft — Netdom trust](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netdom-trust): trust verification, selectiveauth/quarantine/name suffixes, and trust flags.
8. [Microsoft — Selective Authentication](https://learn.microsoft.com/en-us/dotnet/api/system.directoryservices.activedirectory.forest.getselectiveauthenticationstatus): Allowed to Authenticate and cross-forest policy.
9. [Microsoft — Firewall for AD domains and trusts](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/config-firewall-for-ad-domains-and-trusts): DNS/Kerberos/LDAP/GC/RPC ports required per topology.
10. [Microsoft — KFSO across external trusts](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/kfso-not-work-in-external-trust-event-is-17): short-name SPN and forest referral limitations.
11. [Spring Security Kerberos — Spring and Spring Security Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html): `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, keytabs, and user details.
12. [Spring Security — KerberosServiceAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html): ticket validator + UserDetailsService semantics.
13. [Keycloak — Server Admin Guide / Cross-realm trust](https://www.keycloak.org/docs/latest/server_admin/): illustrating `krbtgt/B@A` and cross-realm LDAP user lookups.
14. [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): HTTP `Negotiate` and GSS/SPNEGO mechanics.

**Core takeaway:** **cross-realm trust is a relationship between KDC/AD realms, not a Spring Security switch**. For a user in USERS to reach Spring Portal in APPS, there must be a trusted referral path, valid target SPN/keytab, and working infrastructure conditions (DNS, network, clocks, encryption, AD policies). Even after a Kerberos ticket verifies, **local principal mapping, tenant restrictions, and Spring authorities still decide which resources the user may access**.