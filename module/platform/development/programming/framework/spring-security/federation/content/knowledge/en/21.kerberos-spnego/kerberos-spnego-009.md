# Identity Delegation Risks and the Need to Restrict Delegation in Kerberos/SPNEGO

## 1. The Practical Problem: Users Enter the Web App Safely, Yet What Can the Web App Do on Their Behalf?

Suppose an employee uses a machine logged into an Active Directory domain to open an internal Spring Boot application:

~~~text
User browser -> https://portal.example.org
                HTTP Negotiate / SPNEGO
                Kerberos service ticket for HTTP/portal.example.org
                -> Spring Security authenticates user@EXAMPLE.ORG
~~~

Next, the application needs to read documents on `CIFS/files.example.org` or query a backend `HTTP/api.example.org` **under the employee's identity** so the target system enforces per-user permissions.

A mistaken assumption is thinking: "Spring has identified the user, so it can call any backend under that exact identity." **Incorrect.** Identifying a principal in `Authentication` covers only **the authentication transaction between client and portal**. Whether an intermediary app can **act on the user's behalf to authenticate to a backend** is a separate privilege, commonly called **delegation** or **impersonation**, governed by the Kerberos KDC, accounts, target services, and runtime policies.

If **unconstrained delegation** is granted to portal just to read one file share, then if the web server/service account is compromised, an attacker can wield user identities across far more services than needed. If **constrained delegation** is used yet the allow-list includes `LDAP/domain-controller` or unnecessary administrative services, the risk remains high. If the backend trusts a client-sent `X-User: administrator` HTTP header, the application has built **identity impersonation** **without Kerberos at all**.

This knowledge lesson belongs to **Spring Security - federation → Kerberos and SPNEGO**, topic **"Identity Delegation Risks and the Need to Restrict Delegation"**. The focus is **designing trust boundaries and scoping privileges**, not exploiting Active Directory.

### Learning Outcomes

After this lesson, you will be able to:

1. Separate **Kerberos authentication**, **local impersonation**, **credential delegation**, **authorization**, and **service-to-service authentication**.
2. Describe the two-hop scenario browser → Spring SPNEGO → backend, explaining why the "double-hop" problem occurs.
3. Distinguish **forwarded TGT/unconstrained delegation**, **classic Kerberos Constrained Delegation (KCD)**, **S4U2Self/S4U2Proxy**, and **Resource-Based Constrained Delegation (RBCD)**.
4. Understand `SPN`, `FORWARDABLE/FORWARDED` ticket flags, `OK-AS-DELEGATE`, GSS-API delegated credentials, and the limits of SPNEGO negotiation.
5. Apply the principle of **no delegation by default**, explicitly specifying **frontend identity, backend service, action, user/tenant, and lifetime**.
6. Never equate `Principal.getName()`, JWT claims, or HTTP headers with **Kerberos credentials**.
7. Know how to configure security at the **Active Directory/KDC policy, service account/gMSA, SPNs, ACL, KCD/RBCD** layers and control privileged accounts.
8. Understand the exact role of Spring Security Kerberos: `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `KerberosTicketValidator`, and `UserDetailsService`.
9. Analyze `GSSContext.requestCredDeleg()`, `getCredDelegState()`, and `getDelegCred()` without encouraging blanket delegation.
10. Test denials, backend authorization, multi-tenancy, credential lifetimes, logging, thread reuse, failure handling, and monitoring.
11. Run a **standalone** Java 17 demo simulating allow/deny delegation policy by service and action without needing a real domain.
12. Build a runbook before taking Kerberos delegation to production.

**Illustrative environment:** Kerberos V5, SPNEGO over HTTP Negotiate, Spring Boot 3.x/Spring Security 6.x+ Servlet/MVC, Windows Active Directory when discussing KCD/RBCD, and Java 17+. RFC 4120 applies to Kerberos generally, whereas **S4U/RBCD are Microsoft Kerberos/AD extensions/behaviors**, not present by default in every MIT/Heimdal KDC or Java integration.

---

## 2. First, Distinguish Five Commonly Conflated Concepts

| Concept | Meaning | Automatically Permits Backend Access as User? |
| --- | --- | --- |
| **Authentication** | Proving a subject to a service, e.g. browser presenting a Kerberos ticket to the HTTP portal | **No** |
| **Authorization** | Deciding which actions a user/service may perform on which resources | **Does not** mint credentials |
| **Local impersonation** | A process uses a user's security context/token for operations within the OS context | **Not by default** valid as credentials for another network hop |
| **Credential delegation** | A subject grants or allows a service to prove its identity on its behalf to another service | **Possibly**, within the granted mechanism and scope |
| **Service identity** | Frontend connects to backend using its own service account identity | Does not impersonate the user; backend may process a separate **verified user context** |

**Right example:** Spring verifies the user logged in via SPNEGO and uses `Authentication.getName()` to display "Hello, Linh". That is **authentication** and reading the principal name.

**Example needing delegation:** Spring uses Linh's identity to obtain a ticket for `CIFS/files.example.org` so the file server checks Linh's ACL. That is a **new Kerberos hop** requiring granted credentials and policy.

**Safe service-identity example where appropriate:** Spring uses a service principal `HTTP/portal.example.org` or its own identity to call an API, passing an **application-issued, signed, audience-bound on-behalf-of context** under a designed contract for the backend to verify. This is not automatic Kerberos KCD; the backend must verify **issuer/audience/signature/scope** and enforce permissions properly. Never take a browser-supplied `X-User` header as delegation proof.

## 3. How Does Kerberos/SPNEGO HTTP Authentication Work?

In a typical Windows/AD environment:

1. The user logs into a workstation and acquires a **Ticket-Granting Ticket (TGT)** from the Key Distribution Center (KDC).
2. The browser visits `https://portal.example.org`.
3. The HTTP app returns `401 WWW-Authenticate: Negotiate` to initiate SPNEGO negotiation.
4. Browser/SSPI/Kerberos stack requests a **service ticket** for SPN `HTTP/portal.example.org`.
5. The browser sends `Authorization: Negotiate [base64 token]`.
6. Spring Security Kerberos filter/provider and the JGSS/JAAS validator verify the service ticket using the corresponding keytab/service credentials.
7. Spring Security creates `Authentication`, mapping principal/authorities via `UserDetailsService` or policy.
8. The browser continues sending requests over the HTTP session; backend authorization remains enforced by the app.

~~~mermaid
sequenceDiagram
    participant B as Browser/user
    participant K as Kerberos KDC
    participant W as Spring SPNEGO portal
    B->>K: Holds TGT, requests service ticket for HTTP/portal
    K-->>B: Service ticket for HTTP/portal
    B->>W: Authorization: Negotiate token
    W->>W: Verify service ticket, create Authentication
    W-->>B: Portal response/session per configuration
    Note over W,K: No user-specific permission for backend yet
~~~

**SPNEGO** is a negotiation mechanism via HTTP `Negotiate` tokens; Kerberos is one security mechanism that may be chosen. In practice, NTLM fallback can also occur in some Windows environments. **Never equate "Negotiate header present" with 100% Kerberos**, and never treat a username string in a header as proof.

**Important:** A service ticket issued **for portal** cannot arbitrarily be forwarded to a database/file server as a valid ticket for that backend. Each backend has its own **SPN/key/audience**. "Passing through" a raw SPNEGO token from the frontend to another backend is a broken trust boundary design without a valid protocol/credential exchange.

## 4. What Is the "Double-Hop Problem"?

Consider three machines:

~~~text
[User workstation] --(Kerberos)--> [Spring web portal]
                                       |
                                       | backend call as user?
                                       v
                                [File server / API / DB]
~~~

**Hop 1:** the browser performs Kerberos authentication with portal.

**Hop 2:** portal wants to connect to the backend **as the user**, so the backend enforces per-user access controls.

If portal receives only a service ticket scoped to portal itself and knows the username, it **does not yet have valid proof** to prove the user's identity to the backend. The system may fail with an access error, fall back to the service identity, or lack delegation credentials.

### Three Distinct Approaches for Different Goals

1. **No delegation:** portal calls the backend using a least-privilege service identity, checking user permissions in the app or via a signed, audience/scope-bound context token if supported by the architecture.
2. **Constrained delegation:** there is a valid business reason for the backend to enforce native Kerberos per-user authorization; KDC policy allows the frontend to act for the user **only toward selected target SPNs**.
3. **Broad credential forwarding:** the frontend receives a broad delegated credential usable to request many service tickets. This is a high-risk option—**never use it just to fix a double-hop error** when narrower options exist.

Decisions must rest on **which resources truly require the user's Kerberos identity**, not on a desire to "just make login work".

## 5. Credential Forwarding and Unconstrained Delegation

Under RFC 4120, a ticket can carry the **FORWARDABLE** flag to enable forwarding authentication; forwarding a TGT to a host allows that host to use the user's identity to request tickets for other services. In AD environments, **unconstrained delegation** is a highly sensitive configuration because an intermediary server can receive and use delegated TGTs from accounts permitted to forward.

### Risks

If a web server trusted for broad delegation is compromised:
- An attacker on that server can attempt to use valid delegated credentials for **many other services** within credential and KDC policy limits.
- Blast radius depends on **which users authenticate to that service**, their privilege levels, credential lifetimes, and credential extractability.
- A high-privilege delegated user can turn the web server into a pivot affecting numerous systems.
- Exfiltration of a keytab/service key has consequences distinct from exfiltration of delegated user credentials; **both** must be protected.
- An unexpired ticket/credential does not become invalid merely because the user clicked browser logout.

**Core point:** Unconstrained delegation grants capabilities **far broader than a specific backend requires**. Reviews should usually **eliminate it**, replacing it with KCD/RBCD or a service identity.

### Do Not Confuse Ticket Flags

| Name | Brief Meaning | What Not to Infer |
| --- | --- | --- |
| `FORWARDABLE` | KDC may allow requesting a forwarded credential under conditions | Does not mean every server received a forwarded TGT |
| `FORWARDED` | Ticket was issued in forwarded form | Does not mean the app may call every backend |
| `OK-AS-DELEGATE` | KDC indicates realm policy deems the service suitable to receive delegated credentials | Does not replace app-level authorization |
| `PROXIABLE/PROXY` | Proxy capabilities per Kerberos RFC | Not identical to Microsoft S4U or every AD UI setting |
| `renewable` | Condition allowing ticket renewal | Not a delegation grant |
| `pre-authenticated` | Indicates Kerberos pre-authentication occurred | Not an MFA or authorization guarantee |

In Java GSS-API, a context is **not automatically delegated** simply because a service ticket has `FORWARDABLE`. The initiator must have matching request/policy/credential capability, the mechanism must support it, and the context must establish cleanly.

## 6. Classic Kerberos Constrained Delegation (KCD)

KCD in Active Directory uses policy to restrict a **frontend service account** to delegate strictly to **specific backend SPNs/services**. Suppose:

~~~text
Frontend service principal: HTTP/portal.example.org
Allowed backend SPNs:
  HTTP/reports-api.example.org
  CIFS/files.example.org

Not allowed:
  LDAP/dc01.example.org
  HOST/domain-controller.example.org
  MSSQLSvc/payments-db.example.org:1433
~~~

This is an **illustrative allow-list**, not a ready-to-apply AD config. You must know which account owns each SPN, who owns each backend, which users may be delegated, and backend authorization.

### 6.1 "Use Kerberos only"

In classic KCD with `Use Kerberos only`, the frontend can use **S4U2Proxy** based on a suitable Kerberos evidence ticket (typically requiring forwardable under KDC conditions). That the client authenticated to the frontend with Kerberos is a key prerequisite, yet **does not guarantee** S4U2Proxy will succeed: account delegation policy, target SPN, ticket flags, KDC trust, and user restrictions must all permit it.

### 6.2 "Use any authentication protocol" / Protocol Transition

If the frontend authenticated the user via another method (e.g., a form or an assured token broker) while the backend requires Kerberos, AD offers **protocol transition** using S4U extensions. This is a **sensitive capability**, because the frontend can ask the KDC to issue a ticket for a user **without directly receiving the user's password or TGT** in that transaction.

**S4U2Self:** a service requests a service ticket to **itself** under the user's identity, subject to KDC policy.

**S4U2Proxy:** the service uses suitable evidence to request a service ticket for a backend service **within delegation policy bounds**.

Protocol transition is not a Spring Boot checkbox; it is a **KDC/Active Directory trust boundary**. The backend must still verify the ticket for its own SPN and enforce user/object permissions.

### 6.3 Visualizing KCD

~~~mermaid
sequenceDiagram
    participant U as User browser
    participant F as Frontend service
    participant K as KDC / AD
    participant B as Backend resource
    U->>F: Authentication to HTTP/portal
    F->>K: S4U2Proxy requests ticket for HTTP/reports-api as user
    K->>K: Check evidence and delegation allow-list/policy
    alt Permitted
        K-->>F: Backend service ticket for user
        F->>B: Kerberos AP-REQ as delegated user
        B->>B: Verify ticket + resource-level permissions
        B-->>F: Response per permissions
    else Not permitted
        K-->>F: Kerberos error, no backend ticket issued
        F-->>U: Deny/fail safely
    end
~~~

**Note:** the flow above is a logical model. Some classic KCD paths require S4U2Self first, while others can use an existing evidence ticket. Never assume every Kerberos KDC supports Microsoft S4U extensions.

### 6.4 KCD Reduces Risk, Yet Does Not Eliminate It

A compromised frontend can still **impersonate KDC-permitted users** to any SPN on its allow-list. If the allow-list is overly broad or includes administrative backends, risk remains high. Therefore:
- Restrict the **set of SPNs** and service classes strictly to what is required;
- Restrict the **user population** eligible for delegation (especially privileged accounts);
- Constrain **business context** on the frontend;
- Enforce **authorization** on the backend per resource and action;
- Monitor **KDC-issued delegated tickets** and delegation configuration changes;
- Never treat "KCD" as synonymous with "lateral movement is impossible".

## 7. Resource-Based Constrained Delegation (RBCD)

**RBCD** is an AD variant in which **control over which service may act on a user's behalf is placed on the resource/backend side**. Typical AD attribute:

`msDS-AllowedToActOnBehalfOfOtherIdentity`

This is a **security descriptor** on the resource service's object letting the KDC evaluate which principals may delegate to that resource. Unlike classic KCD, decisions are governed via **resource ownership/trust boundary**, making it particularly useful for cross-domain scenarios per policy.

| Characteristic | Classic KCD | RBCD |
| --- | --- | --- |
| Where delegation is configured | Frontend service account, listing allowed target SPNs | Backend/resource account decides which callers are allowed |
| Typical AD attribute | `msDS-AllowedToDelegateTo` for target service SPNs | `msDS-AllowedToActOnBehalfOfOtherIdentity` on the resource |
| Scoped by SPN / backend | Yes | Yes, enforced via the resource ACL |
| Protocol transition | Depends on KCD mode/policy | Significant differences in KDC behavior; do not equate directly with classic mode |
| Primary risk | Frontend account with overly broad allow-list or dangerous targets | Who can **write the ACL** on the backend object, and what privileges ACL principals hold |
| Auditing | Changes to delegation list on frontend | Changes to the backend object's security descriptor |

Microsoft notes **RBCD does not use the Trusted-to-Authenticate-for-Delegation bit to gate protocol transition in the same way as classic KCD**; delegation rights live in the resource ACL and KDC extension behavior. This **does not mean any service can impersonate any user to any resource**: KDC/AD must still permit it per the ACL and user/service policies. `Account is sensitive and cannot be delegated`, Protected Users, authentication policies, and forest/domain trusts remain constraints to evaluate per environment. **Do not claim they protect every RBCD path identically without testing your actual AD version.**

### RBCD Design Risks

- Anyone able to modify `msDS-AllowedToActOnBehalfOfOtherIdentity` on the backend object can expand the list of principals allowed to act on behalf of users.
- If the resource ACL allows a shared service account or unhardened principal, an attacker compromising that principal can impersonate users to the resource within policy.
- Changing write permissions on an AD object can create new delegation paths unknown to the frontend admins.
- Cross-domain trusts and complex ACLs complicate reviews.
- RBCD still requires the backend to enforce authorization; a KDC-issued ticket **does not prove every action is permitted**.

**Controls:** RBCD ACL changes must be approved by the resource owner, audit AD object modifications, minimize principals in the allow-list, and protect those principals' credentials.

## 8. Decision Table: When Is Delegation Actually Needed?

| Need | Preferred Solution to Consider First | Is Kerberos Delegation Needed? |
| --- | --- | --- |
| Portal only displays data per its own app permissions | Spring authenticated principal + app authorization | **No** |
| Portal calls an internal org API supporting service auth and scoped on-behalf-of assertions | Service identity + audience-bound signed token/verified context, resource authorization | **Not necessarily** |
| Backend file share must enforce Windows ACLs per user | Scoped Kerberos KCD/RBCD to the exact CIFS SPN | **Possibly** |
| Legacy SQL/SSRS backend requires Windows Integrated user auth | KCD/RBCD if stack supports it; verify SPNs and account restrictions | **Possibly** |
| Background job uses a service account to sync data | Dedicated least-privilege service identity | **Do not use user delegation** |
| Frontend only needs to "know who the user is" for auditing | Verified principal identity + audit log | **No** |
| Domain administration or privileged operations from web UI | Do not open broad delegation; use a dedicated privileged access workflow | **Avoid** |
| App does not support backend Kerberos and holds only a username string | Build a verified boundary or redesign architecture | **Cannot assume KCD happens automatically** |

**Rule:** If the requirement is merely displaying data or enforcing portal policies, **do not enable delegation**. If the backend **must** receive the user's identity via Kerberos, enable **only the exact risk-assessed service paths**.

## 9. Risks When Delegation Is Too Broad

### 9.1 Credential Exposure and Server Compromise

The intermediary frontend holds keytabs/service keys and, depending on the mechanism, may see delegated credentials. An attacker with OS/process access can exploit live credentials or query backends to which the service may delegate. Use service accounts without interactive logon, protected keytabs, secret rotation, process isolation, EDR, and patching. In AD, prefer gMSA where supported to reduce manual password management.

### 9.2 Lateral Movement via Backend SPNs

An allow-list containing backend SPNs unnecessary for the app can turn a portal compromise into access against sensitive backends. Pay special attention to LDAP, CIFS/HOST on domain controllers, administrative SQL services, and shared service SPNs. Never list "SPNs for all internal services" just to avoid 403 errors.

### 9.3 Principal Confusion and Service Identity Spoofing

If a backend blindly trusts `X-Authenticated-User` from a browser request or unprotected proxy, an attacker can spoof any user. If a service-to-service token replaces Kerberos, it must carry a **trusted issuer, signature, audience, expiry, scope, and binding**, and the backend must verify them. Never treat `Authentication.getName()` as a "ticket" you can pass raw to any API.

### 9.4 Cross-Tenant Account Linking

A name like `alex` may exist in both `SALES.EXAMPLE.ORG` and `PARTNER.EXAMPLE.ORG`. Use a scoped identity combining Kerberos realm, principal, domain/tenant mapping, and an immutable account ID if available. Never drop the realm or authorize by the username prefix before `@`.

### 9.5 Stale Authorization Snapshots

Spring may populate `GrantedAuthorities` at SPNEGO login time. If an account is later locked or removed from groups, the app session's `SecurityContext` may retain stale authorities. Kerberos delegation may open a path to the backend, yet **does not replace live authorization policies or revocation**.

### 9.6 Audits Losing the Original Actor

If the backend sees only a service account, logs must still capture the chain:
- Who requested the action (verified end-user principal);
- Which frontend service identity executed it;
- Which backend resource;
- Decision, action, and tenant;
- Correlation ID, timestamp, and policy version.

Never collapse every backend action into "the user did it" when an intermediary service is involved. Audits must separate **initiator**, **delegate**, **resource service**, and **authorization decision**.

### 9.7 Caches, Threads, and Connection Pooling

A sensitive `GSSCredential` or JAAS Subject must never be placed in a global singleton, leaked in a thread-local after a request, serialized into Redis/sessions, or bound to a shared JDBC connection pool where it might accidentally be reused under another user. Connection pools and async jobs require strict context propagation and identity resets. Never stuff a user's delegated credential into a cookie/JWT/session attribute hoping "Spring manages it".

## 10. The KDC Can Issue a Ticket; the Backend Can Still Deny

Never equate **authentication delegation succeeded** with **authorization succeeded**.

Even after the KDC issues a backend service ticket under the user's identity:
1. The backend verifies the ticket matches its own SPN/key;
2. Applies domain/realm trust and local account mapping;
3. Checks account state, tenant, role, and object ACLs;
4. Checks permission for the specific action;
5. Blocks policy-violating requests (typically 403 or business error);
6. Audits the decision.

Example:
- The user has permission to **read** `/finance/reports` but not **modify** it.
- KCD is allowed to `CIFS/files.example.org`.
- Backend Windows ACLs still **block file writes** when the user lacks write permission.

**KCD only limits which targets may receive authentication on the user's behalf; it does not pre-grant backend permissions.** Conversely, a backend granting overly broad user permissions remains risky even if the KCD allow-list is narrow.

## 11. When SPNEGO Succeeds, What Has Spring Security Done?

In a Spring Security Kerberos integration, typical components are:

| Component | Role |
| --- | --- |
| `SpnegoEntryPoint` | Initiates HTTP Negotiate (typically a 401 challenge) |
| `SpnegoAuthenticationProcessingFilter` | Reads `Authorization: Negotiate`, creates authentication request token |
| `KerberosServiceAuthenticationProvider` | Authenticates the service ticket/SPNEGO token via validator |
| `KerberosTicketValidator` | Runtime layer verifying the Kerberos service ticket |
| `SunJaasKerberosTicketValidator` | One implementation using JAAS/JGSS with SPN/keytab |
| `UserDetailsService` | Loads local user/authorities for the verified principal |
| `Authentication / SecurityContext` | Stores principal/authorities for the app per HTTP security policy |

**What it does NOT do automatically:** enable AD delegation, perform S4U2Self/S4U2Proxy, mint backend service tickets for arbitrary APIs, or safely provide a forwarded TGT to business services simply because `Authentication.getName()` is populated.

Spring Kerberos documentation states `KerberosServiceAuthenticationProvider` verifies service tickets/SPNEGO tokens and uses `UserDetailsService` to load authorities. That is **app authentication (authN)**, not an automatic KCD broker.

### Illustrative Spring Boot Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    // Choose a Spring Security Kerberos module compatible with
    // the project's Spring Boot/Spring Security/Jakarta Servlet.
    // Do not pin an independent version outside the BOM without testing.
}
~~~

This is only a **directional `dependencies` snippet**, not a complete `build.gradle`. The Spring Security Kerberos module has its own **release/version compatibility**; if `spring-security-kerberos-web` and `spring-security-kerberos-core` are needed, pick the right artifacts/repositories per project docs rather than copying class names from an old example without compile testing.

## 12. Example Spring Security Authorization Without Delegated Credentials

Suppose portal calls backend APIs using only its service identity and needs to control which users can access business functions. There is no need to enable Kerberos delegation just to enforce authorization in portal.

Example Spring Boot class:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/health", "/public/**").permitAll()
                        .requestMatchers("/reports/**")
                            .hasAuthority("REPORTS_READ")
                        .requestMatchers("/admin/**")
                            .hasAuthority("PORTAL_ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**This illustrates authorization only**, using `httpBasic` as a simple auth placeholder in the snippet, **not a complete SPNEGO/Kerberos configuration**. In a real SPNEGO app, replace `httpBasic` with your version-matched Kerberos entry point/filter/provider. The point is to show **no single line silently turns on delegation**.

**Points to understand:**
- `hasAuthority` checks authorities currently in `Authentication`, which can go stale when groups change.
- Route-level authorization is insufficient for individual documents/files; the service must check **ownership/tenant/ACL** at the domain layer.
- When a backend receives user context over another service-to-service protocol, the backend must verify credentials/context itself rather than trusting client-supplied headers.
- If a backend genuinely requires a **Windows Kerberos user ticket**, authorization at portal **does not eliminate** the need for KCD/RBCD.
- For locked users, enforce an app-local account gate/session revocation; never treat an unexpired Kerberos ticket as proof the user is still active.

## 13. Java GSS-API: Requesting Delegation and Checking Results

Java 17 JDK provides standard `org.ietf.jgss.GSSContext`, `GSSCredential`, and `GSSException` APIs. An application **requesting** delegation is distinct from the KDC/mechanism **permitting and actually granting** delegation.

### 13.1 Initiator Side

~~~java
// Snippet placed before the first initSecContext() call.
// Context must be created with the right target principal and configured
// GSSManager/JAAS credentials. Not a standalone program.
GSSContext context = /* configured initiator context */;
context.requestMutualAuth(true);

// Set true only if business logic genuinely requires it and policy permits.
// For normal SPNEGO login needing no delegation, set false.
context.requestCredDeleg(false);

// Perform initSecContext(...) until the context is established.
~~~

**Key point:** `requestCredDeleg(boolean)` is called **on the initiator before the first initSecContext call**. When a user/browser should not delegate, **do not request it**. Browser/product policies determine whether forwarding to a trusted host is allowed; server-side Java code cannot force enterprise browsers to forward TGTs.

### 13.2 Acceptor Side

~~~java
// Snippet valid only on an established acceptor context.
// Do not call getDelegCred() before acceptSecContext completes.
if (context.isEstablished() && context.getCredDelegState()) {
    GSSCredential delegated = context.getDelegCred();
    if (delegated != null) {
        try {
            // Use only within the authorized request/service.
            // Never cache globally, serialize, or log.
        } finally {
            delegated.dispose();
        }
    }
}
~~~

**Required imports:**

~~~java
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSCredential;
import org.ietf.jgss.GSSException;
~~~

These two snippets are **JGSS illustrations** without `main()`, will not compile standalone since context/credentials are omitted, and must handle checked exceptions. They are not direct Spring Security APIs. In practice:
- `getCredDelegState()` is reliable only once the context is established.
- `getDelegCred()` is called on the acceptor and may return `null` if no credential was delegated.
- A delegated `GSSCredential` is not automatically a KCD S4U ticket; **forwarded credentials and AD S4U delegation are two distinct paths**.
- Never use a `GSSCredential` against an unapproved backend just because Java holds the object.
- If no delegated credential is received, **never bypass** by spoofing a username or sending the service keytab as the user.

### GSS-API Security Status Does Not Replace KDC/AD Policy

`getCredDelegState() == true` shows the context negotiated delegation; it does not prove a specific backend target is authorized under KCD/RBCD. KDC policy, GSS mechanism, ticket flags, credentials, SPNs, and backend authorization must all be verified **at the backend hop itself**.

## 14. Spring Security Kerberos Filter Is Not a Global TGT Store

Some apps inspect `Authentication.getPrincipal()` and try putting the entire Kerberos token into `SecurityContext` or the session to call backends later. That creates problems:
- User credentials can accidentally be serialized to Redis/Spring Session or logs.
- A stolen session ID could enable abuse of delegated credentials.
- Multi-node session replication could carry a credential-bearing security context to other hosts.
- Credentials have a different lifecycle from `HttpSession`; expiry and refresh need separate policies.
- Connection pooling risks mixing principals across requests.
- Disposing credentials and bounding lifetimes becomes error-prone.

**Recommendation:** keep Spring `Authentication` storing **verified identity** and required authorities; keep any sensitive credentials in a short-lived trusted scope bound to the request/operation, never in browser/session stores. If protocol transition/KCD is required for a backend, use a version-verified library/integration with dedicated credential lifecycle management rather than "stuffing the TGT into the Authentication object".

## 15. Active Directory: Principles for Restricting Delegation

In AD environments, a secure baseline includes:

1. **Never grant Unconstrained Delegation** unless an exceptional, approved requirement exists.
2. Give each frontend service a **dedicated service account** (prefer gMSA where appropriate), never Domain Admin or shared admin accounts.
3. Register **exact SPNs**, avoiding duplicated or misregistered SPNs.
4. When KCD is needed, allow-list **only the backend SPNs strictly required**.
5. Do not configure `Use any authentication protocol` unless protocol transition is genuinely needed with a clear threat model.
6. The RBCD ACL on a backend resource object must contain only **authorized delegate principals**, with write access to the ACL tightly restricted.
7. Never grant a frontend service account unnecessary rights to modify AD objects or other KCD/RBCD settings.
8. Enable `Account is sensitive and cannot be delegated` for privileged accounts per policy, and use the **Protected Users** group / authentication policies where supported.
9. Never let a service receive user credentials/cookies/tokens beyond its business scope.
10. Protect keytabs, service passwords, `krb5.conf`, JAAS configs, and runtime secrets via ACLs/secret managers; never commit to Git.
11. Review Kerberos credential lifetimes/renewability and maintain time synchronization.
12. Segment networks among frontend, KDC, and backend, opening only necessary ports.
13. Place delegation change approvals under **security/identity teams and resource owners**.
14. Monitor AD object modifications and KDC service-ticket issuance.
15. Test negative paths for sensitive users, out-of-allow-list backends, and disallowed protocol transitions.

**Note:** RBCD/AD S4U have version and trust prerequisites; a config working in one AD may not work identically in another AD/forest. Never weaken protection on privileged users just to get past KDC errors.

## 16. Protected Users and "Sensitive and Cannot Be Delegated" Accounts

In AD, certain accounts require blocking delegation or enforcing strict authentication policies:
- The user/computer account flag **"Account is sensitive and cannot be delegated"** blocks delegation paths under supported AD/KDC policies.
- The **Protected Users** group applies hardened policies, including restrictions on delegated credentials, NTLM, or Kerberos lifetimes depending on the environment.
- Authentication Policies and Authentication Policy Silos can restrict **where and how a user may authenticate**.
- For privileged identities (Domain Admins, break-glass accounts), never rely on web delegation to run automation; design least-privilege admin workflows.
- When an account is locked or permissions revoked, app sessions may persist; implement live account gating, token/session revocation, and backend protections.

### Common Mistake

Seeing S4U2Proxy fail when a user belongs to Protected Users, operators remove the account from **protection** or turn on unconstrained delegation. That may make the "double hop work" while **expanding risk**. The right approach is deciding whether act-as-user is truly needed, choosing a service identity or KCD/RBCD with proper user/target policies, and seeking formal exception approval if genuinely required.

## 17. RBCD: Who Is Permitted to Modify a Backend Resource Object?

An RBCD design should explicitly document:

~~~text
Resource:    Backend HTTP/reports-api
AD object:   service/computer account owning backend SPN
Owner:       Backend security team
Allowed:     approved gMSA/service principal of portal
Not allowed: shared service accounts, domain users,
             service principals outside this workload
Control:     AD ACL, change review, protected backups, audit
~~~

**Principles:**
- Anyone with write access to `msDS-AllowedToActOnBehalfOfOtherIdentity` or control over the backend object can alter this trust boundary.
- Never grant a developer pipeline permission to edit AD delegation ACLs across an entire OU when it only manages one service.
- Never trust a username in an LDAP `displayName` as a delegate principal; use the exact security principal/SID.
- Verify domain/forest trust relationships, SPN ownership, and backend authentication policies.
- Audit the exact **principals added to or removed from** the ACL, rather than merely logging "RBCD config changed".
- Ensure broad computer/service account creation rights cannot be leveraged to create unintended RBCD paths under AD policy.
- RBCD does not replace backend authorization, nor does it pass full TGTs to the frontend.

## 18. Distinguishing GSS Credential Delegation from S4U-Based KCD

Two mechanisms that are easily confused:

| Characteristic | GSS Credential Forwarding | AD KCD / RBCD with S4U |
| --- | --- | --- |
| Source credential | Initiator/user consents and policy permits forwarding credentials | KDC issues a backend ticket to the service based on S4U evidence/policy |
| Must user send a delegated TGT to frontend? | Potentially in Kerberos forwarding | **Not necessarily**; S4U avoids needing a forwarded TGT in many scenarios |
| Typical Java API | `GSSContext.requestCredDeleg`, `getDelegCred` | Depends on SSPI/AD S4U library and server integration |
| Control point | User/client/browser policy, KDC flags, target service trust | AD KCD list or RBCD resource ACL, user restrictions |
| Risk scope | Can be broad with the forwarded credential | Scoped to target SPNs; still dangerous if list/ACL is misconfigured |
| Handled automatically by Spring SPNEGO filter? | Does not expose or guarantee delegated credentials by default | **Does not implement S4U2Self/S4U2Proxy** |
| Backend requirement | Valid service ticket for its SPN and authorization | Valid service ticket for its SPN and authorization |
| When unnecessary | Keep disabled | Do not configure KCD/RBCD |

**No standard line like `http.saml2Login()`, `oauth2Login()`, or `spnegoFilter.setDelegation(true)` automatically grants AD RBCD.** Those stacks are separate protocol integrations.

## 19. Restricting Delegation Across All Four Dimensions

Configuring a target SPN allow-list alone is necessary but insufficient. A sound policy covers:

### 19.1 Who May Delegate?

- Approved frontend service account/hostname/SPN;
- User principal/realm/tenant within the permitted population;
- Not a privileged/protected account;
- Enabled account status and appropriate authentication assurance;
- Taken strictly from the authenticated request chain, never a query parameter.

### 19.2 Where May Delegation Go?

- Approved backend services/SPNs only;
- Never an arbitrary host from a `Host` header or user-supplied URL;
- Separate prod/staging environments; no cross-realm without explicit assessment;
- The backend service must verify SPN/key and authorization.

### 19.3 What May Be Done?

- `READ_REPORT` differs from `APPROVE_PAYMENT`;
- Separate service delegation rights (getting a backend ticket) from app/business action rights;
- Check resource-level ACL/tenant/ownership;
- You may restrict the app to GET/read-only, yet never treat HTTP methods as sufficient replacement for backend ACLs;
- Never pass credentials to background jobs lacking a valid actor.

### 19.4 For How Long and How Often?

- Credential lifetime governed by KDC policy;
- No global caching; never store in `HttpSession`/logs;
- Dispose promptly after the request;
- Business permission versioning/revocation events;
- Reauthentication/step-up for sensitive actions;
- Audit rate, blast radius, and revocation capability.

**Conceptual policy:**

~~~text
permitDelegation =
    verifiedFrontend
    AND trustedKerberosPrincipal
    AND accountEnabled
    AND notProtectedOrPrivileged
    AND targetSpnInAllowList
    AND businessActionAllowed
    AND backendObjectAuthorizationPasses
    AND delegationMethodApproved
    AND sessionAndCredentialNotExpired
~~~

This is an **architecture-level policy**. Conditions are enforced at different layers: KDC/SPN policy, portal business authorization, and backend resource authorization. You cannot cram all of it into one Spring filter boolean and expect the KDC to obey.

## 20. Standalone Java 17: Simulating a Minimal Delegation Policy

This example **does not obtain real Kerberos tickets**, call a KDC, use JAAS/GSS/AD, or **perform impersonation**. It solely models the decision of **whether to allow an act-on-behalf-of request** once the frontend knows the verified principal, target SPN, and business action.

The goal is practicing **deny-by-default, target allow-lists, protected-account bans, and action/tenant checks**.

File `DelegationBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public final class DelegationBoundaryDemo {

    record User(
            String principal,
            String tenant,
            boolean enabled,
            boolean protectedAccount,
            Set<String> permissions) {
    }

    record Request(
            String targetSpn,
            String action,
            String tenant,
            boolean verifiedCaller) {
    }

    private static final String REPORTS_SPN =
            "HTTP/reports-api.example.org";
    private static final String FILES_SPN =
            "CIFS/files.example.org";

    private static final Map<String, Set<String>> ALLOWED =
            Map.of(
                REPORTS_SPN, Set.of("READ_REPORT"),
                FILES_SPN, Set.of("READ_FILE"));

    static String authorize(User user, Request request) {
        if (user == null || !request.verifiedCaller()) {
            return "DENY_UNVERIFIED";
        }
        if (!user.enabled() || user.protectedAccount()) {
            return "DENY_ACCOUNT";
        }
        if (!user.tenant().equals(request.tenant())) {
            return "DENY_TENANT";
        }
        Set<String> actions = ALLOWED.get(request.targetSpn());
        if (actions == null || !actions.contains(request.action())) {
            return "DENY_TARGET_OR_ACTION";
        }
        if (!user.permissions().contains(request.action())) {
            return "DENY_PERMISSION";
        }
        return "ALLOW_POLICY_ONLY";
    }

    public static void main(String[] args) {
        User reader = new User(
                "reader@EXAMPLE.ORG", "finance",
                true, false, Set.of("READ_REPORT"));
        User admin = new User(
                "admin@EXAMPLE.ORG", "finance",
                true, true, Set.of("READ_REPORT", "READ_FILE"));

        Request readReports = new Request(
                REPORTS_SPN, "READ_REPORT", "finance", true);
        Request unknownTarget = new Request(
                "LDAP/dc01.example.org", "READ_REPORT",
                "finance", true);
        Request elevatedAction = new Request(
                REPORTS_SPN, "APPROVE_PAYMENT", "finance", true);
        Request crossTenant = new Request(
                REPORTS_SPN, "READ_REPORT", "hr", true);
        Request unverified = new Request(
                REPORTS_SPN, "READ_REPORT", "finance", false);

        System.out.println("Normal read: "
                + authorize(reader, readReports));
        System.out.println("Unknown backend: "
                + authorize(reader, unknownTarget));
        System.out.println("Action not permitted: "
                + authorize(reader, elevatedAction));
        System.out.println("Protected admin: "
                + authorize(admin, readReports));
        System.out.println("Cross-tenant: "
                + authorize(reader, crossTenant));
        System.out.println("Unverified caller: "
                + authorize(reader, unverified));
    }
}
~~~

Run:

~~~bash
javac DelegationBoundaryDemo.java
java DelegationBoundaryDemo
~~~

**Exact stdout:**

~~~text
Normal read: ALLOW_POLICY_ONLY
Unknown backend: DENY_TARGET_OR_ACTION
Action not permitted: DENY_TARGET_OR_ACTION
Protected admin: DENY_ACCOUNT
Cross-tenant: DENY_TENANT
Unverified caller: DENY_UNVERIFIED
~~~

### Why Only `ALLOW_POLICY_ONLY`?

The program **does not issue a Kerberos service ticket**. It indicates only that **application policy** does not block that use case. Production still requires:
1. KDC allowing delegation in AD/Kerberos;
2. The target SPN existing uniquely and bound to the right backend account;
3. GSS/SSPI/AD S4U integration actually obtaining the backend ticket;
4. The backend verifying the ticket and resource-level permissions;
5. Preventing credential leaks, auditing, and lifecycle cleanup.

Therefore, the label `ALLOW_POLICY_ONLY` was chosen intentionally so learners **do not mistake a Java policy decision for a KDC grant**.

### Risks of Using the Demo Code as Production

- Accepting a `verifiedCaller` boolean passed by a caller is **unsafe** in a real API. Production must derive status from a **verified authentication context**, never from JSON/query parameters.
- Policy in a `static Map` is illustrative and does not sync AD/tenant permission changes.
- There is no cryptographic binding, credential lifetime, or KDC trust validation.
- `principal` in the record is plain text; it does not prove Kerberos login happened.
- Place policy at a tested backend/service boundary; never treat frontend UI as authoritative.
- There is no database/IO and it does not replace `KerberosTicketValidator`.

## 21. Spring Code Following the Business-Boundary Policy Pattern

An application can enforce policy in a Spring-managed service to check **actions**, not merely `@PreAuthorize("isAuthenticated()")`.

Example:

~~~java
package com.example.portal;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportsService {

    @PreAuthorize("hasAuthority('REPORTS_READ')")
    public String readReport(String reportId) {
        // In production:
        // 1. Validate reportId/tenant ownership
        // 2. Check current account/permission state
        // 3. Use approved backend authentication/delegation
        // 4. Audit subject, target, decision
        return "Report ID: " + reportId;
    }
}
~~~

Enable method security:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

**These are classes inside a Spring project, with no `main()`; do not run `javac` standalone.** The `@PreAuthorize` snippet only checks an authority snapshot. It **does not implement Kerberos KCD** or verify permissions on the actual report ID. Production requires an authorization manager/live account gate, object ACLs, and dedicated backend ticket handling.

### When the Backend Only Supports Windows Integrated Authentication

If the backend strictly requires per-user Windows ACLs:
- Design the KCD/RBCD path with the AD team;
- Select the implementation/service account and target SPNs;
- Never spoof a user via an `X-User` header;
- Verify in real integration testing that the backend sees the right user principal;
- Block unauthorized users/services at both KDC and backend;
- Never "fix" it by running all queries under a Domain Admin service account.

## 22. When the Frontend Uses a Service Identity Instead of User Delegation

One design option is **on-behalf-of application authorization**:
1. The browser logs into portal with SPNEGO.
2. Portal verifies the principal and current permissions.
3. Portal calls the backend using **mTLS/service principal/OAuth2 client credentials** or a suitable mechanism.
4. Portal passes a **signed, short-lived, audience-bound** user context/token if the backend needs user-scoped authorization.
5. The backend verifies signature, issuer, audience, expiry, scope, calling service, and policy—never trusting raw headers.
6. The backend enforces object-level access and audits both actor and service.

**Advantage:** avoids exposing broad user Kerberos credentials to the frontend. **Limitation:** this is an **application contract**, meaning a Windows file share backend will not magically understand OIDC/JWT to enforce ACLs. When a backend supports only Kerberos user auth, KCD or a different file-access architecture may still be needed.

Points that must be right:
- Tokens must never be minted from an arbitrary user-supplied username;
- Token audience is restricted strictly to the required backend;
- Scopes are narrow/action-specific with short lifetimes;
- Prevent confused-deputy attacks when the frontend calls user-selected targets;
- The backend verifies service identity independently of user context;
- Never use a long-lived, unaudited shared "superuser API key".

## 23. Principles for Preventing Confused-Deputy Attacks

**Confused deputy** occurs when a service privileged to access a backend exercises that privilege **on an unauthenticated/unauthorized request from another party**.

For example, portal has permission to read a file share and exposes an API:

~~~text
GET /download?target=\\files.example.org\secret\payroll.xlsx
~~~

If portal simply uses its backend credential to read **any target path the client sends**, a user lacking payroll access can abuse portal's privilege to download the file.

Mitigations:
1. Never accept arbitrary backend hostnames/SPNs/paths from the client.
2. Use a server-side **resource ID** mapped to an approved catalog.
3. Check user tenant, ownership, and permissions for **every resource**.
4. Check the service target allow-list before requesting backend credentials.
5. Connect to the backend over appropriate TLS/mutual auth.
6. Avoid wildcard service account permissions.
7. Audit both user actor and service delegate.
8. For high-risk actions, re-verify permissions right at commit time.

**KCD does not automatically prevent confused-deputy** if the service is permitted to delegate to the backend yet the application itself fails to verify whether the user is allowed to request that specific resource.

## 24. SPNs and Keytabs Are Part of the Trust Boundary

**SPN (Service Principal Name)** lets the KDC select the account/key matching a service. Examples:
- `HTTP/portal.example.org` — frontend service;
- `HTTP/reports-api.example.org` — backend HTTP API;
- `CIFS/files.example.org` — file service;
- `MSSQLSvc/sql.example.org:1433` — SQL Server service in compatible environments.

Ensure:
- Each SPN is registered on the right account/service without duplicates;
- Browsers use the **canonical host** matching the SPN, with proper proxy/DNS;
- Frontend holds the matching keytab/credentials for its SPN to accept tickets;
- Backends accept tickets solely for their own SPN/identity;
- gMSA/service account credentials obey least privilege;
- TLS/channel binding/Extended Protection when supported by the stack—never disable to silence errors without finding root cause;
- Clear cross-realm trust and KDC time synchronization;
- Never let a user dictate `targetSPN` via a URL to delegate outside the allow-list.

### Keytabs Are Not User Credential Forwarding

A keytab for `HTTP/portal` allows the service to verify Kerberos service tickets issued **for portal**. It **does not grant authority to impersonate any user to a backend**. An app knowing a username and holding a keytab cannot mint Kerberos tickets for a backend on its own; the KDC remains responsible for issuing tickets per policy.

## 25. Common Error Table

| Symptom | Likely Cause | Safe Investigation |
| --- | --- | --- |
| Browser SPNEGO login succeeds, yet backend returns 401 | Missing delegation credential/service ticket for target; backend auth config | Check target SPN and KDC policy; never copy Negotiate tokens |
| GSS context gives `getCredDelegState=false` | Initiator did not request / policy disallowed / mechanism unsupported | Check browser/SSPI GSS policy, flags, KDC; **never force user delegation** |
| S4U2Proxy rejected by KDC | Wrong frontend account, evidence ticket, user sensitivity, or target SPN policy | Check AD KCD/RBCD settings, user restrictions, and KDC events |
| KCD works to one backend, fails to another | Different SPN allow-list or target service account | Compare exact target SPN and account ownership |
| RBCD behaves broader than expected | Overly broad ACL on backend resource object | Review `msDS-AllowedToActOnBehalfOfOtherIdentity` and delegate principals |
| Backend sees service account instead of user | No user delegation; using service credential only | Clarify architecture: does service identity need user context? |
| Backend sees wrong user after multiple requests | Thread/Subject/connection pooling leak or faulty mapping | Audit identity scopes; reset contexts/credentials |
| Browser Negotiate falls back to NTLM | KDC/SPN/browser policy/clock/trust issue | Confirm Kerberos mechanism; never assume delegation occurred |
| SPNEGO 401 loop | SPN/keytab mismatch, browser allow-list, channel binding, time skew | Inspect safe configs; never disable channel binding |
| Privileged user cannot delegate | Sensitive account / Protected Users / auth policy | Keep protection; design a separate privileged workflow |
| Valid Kerberos ticket, yet backend returns 403 | Resource-level ACL or business authorization | Check backend permissions; do not expand KCD target list |
| Stale Spring Authentication roles | Authorities loaded at login not refreshed | Implement live account/permission checks and session invalidation |
| Unusual spike in KDC service tickets | Delegation misuse, policy change, or load spike | Triage 4769 events and service/actor/target |
| App crash/restart drops forwarded credential | Credential lifecycle/process memory | Never cache globally; design appropriate auth strategy |
| Service account granted Domain Admin to "fix error" | Broken blast-radius design | Enforce least privilege and separate service identities |

Never expose tickets, keytabs, raw Authorization headers, PACs, or passwords in support logs.

## 26. Safe Pre-Production Test Plan

### Test A — SPNEGO Authentication, Delegation Disabled

1. Using a valid domain test user, browser sends SPNEGO ticket for `HTTP/portal.example.org`.
2. Spring Kerberos provider identifies the right user/realm.
3. Portal routes reading only app-local data work.
4. Verify **no** delegated user credential is present when the flow does not require it.
5. Backend calls must use the defined service identity or be denied; **never silently impersonate the user**.

**Pass:** login succeeds without granting "free" delegation.

### Test B — KCD Scoped to One Backend

1. Portal service account is configured for KCD/RBCD to `HTTP/reports-api.example.org` per AD test policy.
2. Non-sensitive test user holds `READ_REPORT`.
3. Portal calls reports backend with delegated user identity via approved implementation.
4. Backend verifies exact user, target SPN, and resource permission.
5. Same user attempts connection to `LDAP/dc01.example.org`; policy/KDC/app must deny.

**Pass:** required backend succeeds; targets outside allow-list are blocked.

### Test C — Sensitive Flag / Protected Users Account

1. Use a test account flagged against delegation.
2. SPNEGO login may still work per domain policy.
3. Delegation requests must not bypass the corresponding protection mechanism.
4. Never strip the flag/group just to "make the test pass".
5. Backend fallback must fail closed, never substituting a superuser service account.

### Test D — Protocol Transition

1. Run only in an AD test realm with explicit policy.
2. Frontend authenticates user via an approved flow.
3. Exercise S4U2Self/S4U2Proxy via a supported implementation.
4. Permitted backend SPN and user policy: succeeds.
5. Disallowed target or unauthorized user: denies.
6. Never enable "Use any authentication protocol" by default across services.

### Test E — RBCD ACL

1. Resource owner inspects backend object and allowed delegate principals.
2. Service account absent from ACL: cannot delegate.
3. Only the approved test account has target permission.
4. Modify ACL via change control and verify audit logs.
5. Never use real accounts or grant OU-wide AD object write permissions.

### Test F — Thread / Connection Pool Identity Isolation

1. User A has `READ_REPORT`; user B lacks permission.
2. Send two concurrent requests through portal to backend.
3. Backend must never observe A's context while processing B.
4. Per-request credentials are cleaned/disposed and absent from session stores.
5. Background jobs never reuse a user identity after the request ends.

### Test G — Account Revocation

1. User logs in and is allowed to read.
2. IAM locks the account / revokes `READ_REPORT`.
3. Subsequent requests / sensitive actions are denied within SLA policy.
4. Never treat an unexpired Kerberos ticket as proof the account remains enabled.
5. For long-lived backend connections, test separate revocation policies.

### Test H — Wrong SPN, Lost KDC, Time Skew

1. Use a wrong target SPN in lab; must fail safely.
2. Simulate KDC outage or network policy failure; never "fail open".
3. Verify logs never print service tickets or keytabs.
4. Test NTP/time skew causing auth errors; never widen clock validation excessively.
5. Return user-safe errors and fire operational alerts.

## 27. Monitoring: Signals to Observe

On AD/KDC, depending on audit policy:
- **4768**: TGT requested, helpful for observing Kerberos authentication service events.
- **4769**: Kerberos **service ticket** requested; useful for spotting anomalies in target SPNs, users, and issuance times.
- **4771**: Kerberos pre-authentication failed; investigate in context, not automatically delegation abuse.
- **4624**: Logon events on target hosts, providing logon type/context.
- **5136**: AD Directory Service object modified, useful when auditing AD delegation attribute/ACL changes.
- EDR/security tooling and backend logs correlating ticket issuance with actual resource actions.

**Never infer a compromise from a single 4769 event**. Kerberos is chatty in Windows environments; maintain workload baselines, allow-listed expected SPNs, and known service identities.

Application logs should capture:
- Correlation ID, never raw tickets;
- Frontend service alias, backend SPN alias;
- Trusted initiator principal scoped by realm/tenant (minimized personal data);
- Decision `DENY/ALLOW_POLICY_ONLY`;
- Enumerated reason such as `NO_DELEGATION_NEEDED`, `TARGET_NOT_ALLOWED`, `USER_PROTECTED`, `BACKEND_DENIED`;
- Secret-free KDC error category;
- Policy version and timing;
- Alerts when delegation allow-lists/RBCD ACLs change, service principal accounts are modified, or anomalous service ticket requests occur.

**Never log:** raw Kerberos TGTs, AP-REQ/SPNEGO tokens, keytabs, passwords, PAC bytes, `GSSCredential`, or full Windows access tokens.

## 28. Before–After Threat Model for a Reporting Portal

### Before Hardening

- `portal.example.org` uses a broad-privilege shared service account.
- Unconstrained delegation is enabled to "solve double hop".
- Web app reads username from authenticated session and lets users specify a backend path.
- Backend file share grants broad permissions to the service account.
- Service logs record raw `Authorization: Negotiate`.
- A web server compromise spreads blast radius across multiple systems.

### After Hardening

1. Isolate portal's service account/gMSA with least privilege.
2. Disable unconstrained delegation.
3. Decide: if the backend API supports scoped app tokens, use service identity + signed on-behalf-of context; if native Windows ACLs are required, configure KCD/RBCD strictly to **exact backend SPNs**.
4. Flag privileged users as non-delegatable per AD policy.
5. Backend enforces resource ACLs even when delegated user Kerberos login succeeds.
6. Portal resolves resource IDs server-side, rejecting arbitrary target URLs/paths.
7. Never store delegated credentials in Spring sessions, logs, Redis, or shared connection pools.
8. Monitor 4769 service tickets, delegated principals, and AD ACL modifications.
9. Test denied targets, protected users, concurrent requests, and session revocation.
10. Maintain a rollback plan that restores service access without opening wildcard delegation.

**Expected outcome:** portal reads reports strictly per user and business need without gaining power to act for users on unrelated backends.

## 29. Deployment Checklist

- [ ] Clearly documented **why** user-specific backend Kerberos authentication is needed.
- [ ] If app-local authorization or service identity suffices, **keep delegation disabled**.
- [ ] Distinguished authentication, local impersonation, and network credential delegation.
- [ ] Never confused HTTP `Authorization: Negotiate` with permission to forward user TGTs.
- [ ] Confirmed SPNEGO actually selected Kerberos rather than merely checking the Negotiate header.
- [ ] Used matching Kerberos service principal/SPN/keytab on the right account without duplicate SPNs.
- [ ] Unconstrained delegation removed or covered by an approved exception and mitigations.
- [ ] Classic KCD target allow-list contains only required backend SPNs, with no wildcards.
- [ ] If using S4U protocol transition, evaluated user policies and trust scope.
- [ ] RBCD ACL on backend resource objects approved by resource owners and audited.
- [ ] CI/CD and developer roles lack broad AD delegation-editing permissions.
- [ ] Privileged users restricted from delegation via Protected Users / sensitive flags where appropriate.
- [ ] Service account/gMSA hardened; keytabs/passwords excluded from source code.
- [ ] Backends verify Kerberos tickets or service-to-service tokens with right audience/issuer.
- [ ] Backends enforce resource ACLs/business authorization rather than allowing based on username alone.
- [ ] Policies defined across user, tenant, action, target SPN, TTL, and reauthentication.
- [ ] All `target URL/SPN/resource path` inputs allow-listed/resolved server-side.
- [ ] Never trust `X-User`, `isAdmin=true`, or `verifiedCaller=true` from browsers.
- [ ] Never store `GSSCredential`/TGTs/service tickets in `HttpSession`/Redis/logs.
- [ ] Thread/async/connection pools never leak another user's security context.
- [ ] Negative tests run for out-of-allow-list targets, protected accounts, wrong SPNs, KDC outages, cross-tenant, and replay/context leakage.
- [ ] Live account/permission changes remain enforced; unexpired Kerberos tickets are never treated as permanent rights.
- [ ] KDC 4769 / AD 5136 auditing and delegation change control in place.
- [ ] Safe rollback plan exists when a backend does not support delegation.
- [ ] Verified in standard environment with delegation disabled that no unnecessary dependency exists.

## 30. Exercises and Answers

**Q1.** A browser successfully authenticates with Kerberos to a Spring portal. Does portal automatically receive the user's TGT to call a file server?

**Answer:** no. The SPNEGO service ticket authenticates to portal. Forwarded credentials or KCD/RBCD are **separate** mechanisms governed by KDC/client/AD policies.

**Q2.** The backend only needs to know which user called the API, without requiring Windows ACLs. Is unconstrained delegation necessary?

**Answer:** no. Consider service identity + signed scoped on-behalf-of context with backend validation, or app-local authorization.

**Q3.** Why is checking `Authentication.getName()` insufficient to call a backend "as the user"?

**Answer:** a username string is not a Kerberos credential, is not verified by the KDC at the backend, and can collide across realms/tenants.

**Q4.** KCD permits `HTTP/reports-api` but not `LDAP/dc01`. What if a user request tries to reach LDAP?

**Answer:** it must be denied by app policy and/or KDC target SPN restrictions; never open LDAP targets just to avoid errors.

**Q5.** How is unconstrained delegation riskier than KCD?

**Answer:** delegated credential scope can span many services. If the frontend is compromised, the blast radius far exceeds a single selected backend.

**Q6.** What do S4U2Self and S4U2Proxy do?

**Answer:** S4U2Self lets a service request a ticket to **itself** under a user's identity per policy; S4U2Proxy requests a ticket to a **backend service** based on evidence and delegation policy.

**Q7.** Where are RBCD permissions stored?

**Answer:** on the resource/backend account's security descriptor, typically the AD attribute `msDS-AllowedToActOnBehalfOfOtherIdentity`, not merely a frontend list.

**Q8.** Does "RBCD allows protocol transition" mean any service can impersonate any user to a backend?

**Answer:** no. Backend ACLs and KDC policies must permit it, alongside account restrictions and backend authorization. RBCD is not a wildcard.

**Q9.** If `getCredDelegState()` returns `false`, should the app use an admin service account to call the backend as the user?

**Answer:** no. Check policy/capabilities or change the architecture; never bypass with admin privileges or spoofed usernames.

**Q10.** A user is delegated to CIFS yet lacks an ACL to read file X. What happens?

**Answer:** backend Windows file ACLs must deny access to file X. KDC ticket issuance does not grant per-file permissions.

**Q11.** Why should `GSSCredential` never be stored in `HttpSession`?

**Answer:** sensitive credentials can be serialized/leaked or used beyond their lifetime/policy, risking cross-user context leakage and widening blast radius.

**Q12.** A Protected Users account cannot be delegated. Is removing it from the Protected Users group a good fix?

**Answer:** no. Preserve privileged identity protection; consider a service identity or another approved KCD path rather than weakening policy.

**Q13.** A frontend has permission to call a report API and lets the user supply the backend URL. What is the risk?

**Answer:** confused deputy, SSRF, or delegation to unintended targets. Use server-side allow-lists/resource IDs and business authorization.

**Q14.** Does seeing event 4769 for a backend service prove an attacker is exploiting KCD?

**Answer:** no. Establish baselines, user/SPN/host context, and correlate with account/ACL changes and backend actions.

**Q15.** The KDC issues a valid backend ticket, yet the Spring backend API returns 403. Should that SPN be added to the allow-list?

**Answer:** not by default. That likely reflects object/tenant/action authorization in the backend, separate from KDC delegation.

**Q16.** How do classic KCD "Use Kerberos only" and "Use any authentication protocol" differ?

**Answer:** protocol transition mode and the types of evidence the KDC accepts differ. S4U2Self/Proxy carry different requirements and scopes; never enable broad transition when only a Kerberos hop is needed.

**Q17.** Can a successful SAML/OIDC login substitute for a Kerberos forwarded TGT?

**Answer:** no. A SAML Assertion or OIDC ID Token is protocol-specific evidence; if the backend needs Kerberos, KDC-authorized S4U/protocol transition or an equivalent architecture is required.

**Q18.** Why do RBCD ACLs require change control?

**Answer:** any principal able to modify the resource attribute can alter the list of services permitted to act for users, shifting the trust boundary and blast radius.

## 31. Summary

**SPNEGO authentication into Spring Security does not automatically grant delegation rights.** A frontend needing to call a backend "under the user's identity" must use properly governed **credential delegation or KDC-mediated KCD/RBCD**; or adopt **service identity with a verified on-behalf-of contract** if the backend does not genuinely require Kerberos user tickets.

Four principles to keep the system secure:

1. **Do not delegate unless necessary.**
2. **When necessary, restrict by frontend service identity, backend SPNs, user/tenant, action, and lifetime.**
3. **KDC ticket issuance does not replace backend authorization/ACLs.**
4. **Protect service accounts/credentials, audit delegation, and test denial paths.**

An architecture where "SSO login succeeds" while delegation fails can be **the exact intended secure outcome**, not a bug to fix with wildcard SPNs or Domain Admin service accounts.

### Official References

1. IETF RFC 4120 — Kerberos V5, Sections 2.5–2.8 on proxies, forwardable tickets, and OK-AS-DELEGATE: https://www.rfc-editor.org/rfc/rfc4120.html
2. IETF RFC 4178 — SPNEGO mechanism negotiation: https://www.rfc-editor.org/rfc/rfc4178.html
3. Microsoft Learn — Kerberos Constrained Delegation overview (classic KCD/RBCD, S4U, and security implications): https://learn.microsoft.com/en-us/windows-server/security/kerberos/kerberos-constrained-delegation-overview
4. Microsoft Learn — Attribute `msDS-AllowedToActOnBehalfOfOtherIdentity` for RBCD: https://learn.microsoft.com/en-us/windows/win32/adschema/a-msds-allowedtoactonbehalfofotheridentity
5. Microsoft Open Specifications — MS-SFU Service for User and Constrained Delegation Protocol: https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-sfu/
6. Microsoft Learn — Protected Users Security Group: https://learn.microsoft.com/en-us/windows-server/security/credentials-protection-and-management/protected-users-security-group
7. Microsoft Learn — Troubleshooting Kerberos Constrained Delegation: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/troubleshoot-kerberos-constrained-delegation-issues
8. Oracle Java 17 — `GSSContext`, `requestCredDeleg`, `getCredDelegState` and `getDelegCred`: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/org/ietf/jgss/GSSContext.html
9. Spring Security — Spring and Spring Security Kerberos, SPNEGO and providers: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
10. Spring Security Kerberos API — `SpnegoAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
11. Spring Security Kerberos API — `KerberosServiceAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
