# Ticket Granting Ticket and Service Ticket in Kerberos: From KDC to Spring Security SPNEGO

## 1. Goal and Context

**Kerberos V5** is a network authentication protocol based on **tickets** and cryptographic keys, commonly used with Microsoft Active Directory, MIT Kerberos, enterprise environments, and **SPNEGO**-capable applications. Kerberos allows a user with an existing domain logon session to access other services without sending their password to each application.

In a Spring Boot application using **Spring Security Kerberos**, a user may open an internal web page. The browser exchanges HTTP `Negotiate` with the application using a **service ticket issued specifically for the website's service principal**. The server verifies the token using Kerberos/JGSS and the service's own keytab; the application then maps the Kerberos principal to a local account and business permissions.

The two most important ticket types:

1. **Ticket Granting Ticket (TGT)**: a ticket issued to the client by the **Authentication Service (AS)** inside the **Key Distribution Center (KDC)** to prove to the **Ticket Granting Service (TGS)** that the client is allowed to request other tickets.
2. **Service ticket**: a ticket issued by the **TGS** for **a specific service principal**, such as `HTTP/portal.example.test@EXAMPLE.TEST`. The client uses that ticket along with an **authenticator** to authenticate to the target web server or service.

This lesson belongs to the **Kerberos and SPNEGO** group and aims to help learners:

- Master the three main exchanges: **AS-REQ/AS-REP**, **TGS-REQ/TGS-REP**, and **AP-REQ/AP-REP**.
- Distinguish **TGT and service ticket** by issuer, encryption key, scope of use, TTL, caching, and exposure risk.
- Understand how `krbtgt/REALM@REALM` differs from `HTTP/host@REALM` and the role of the **Service Principal Name (SPN)**.
- Understand why a web app **does not receive a TGT**, receiving instead a **SPNEGO/GSS-API token** containing authentication data with a **service ticket**.
- Understand that **a ticket can be used within its validity window**, whereas each **authenticator** must be fresh and replay-protected; do not confuse this with one-time semantics of another ticket protocol.
- Know how to configure `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, **keytab**, and local authorization.
- Know how to use `kinit`, `klist`, `kvno`, and `klist -k` for diagnostics without leaking keys.
- Recognize errors involving SPN, principal, KVNO, encryption type, DNS/hostname, clock skew, 401/Negotiate, keytab, and business permission failures.
- Work through a **standalone Java 17** example illustrating TGT/service ticket/replay states, plus a negative test matrix and deployment checklist.

**Core point:** a TGT is a credential **presented to the TGS**, whereas a service ticket is a credential **scoped to a specific service**. **A TGT is not a ticket that a Spring web application is allowed to obtain directly from the browser or decrypt with an HTTP keytab.**

## 2. Four Components in a Kerberos Login

~~~text
                +----------------------------------------+
                | Key Distribution Center (KDC)          |
                |                                        |
                | Authentication Service (AS)            |
                | Ticket Granting Service (TGS)           |
                +----------------------------------------+
                   ^                       ^
                   | AS-REQ/AS-REP         | TGS-REQ/TGS-REP
                   |                       |
                   +--------- Client -----+
                              |
                              | AP-REQ (service ticket +
                              |         authenticator)
                              v
                       Service / Acceptor
                         HTTP website
                         CIFS/SMB server
                         database service
~~~

| Component | Responsibility | Primary Secret / Credential |
| --- | --- | --- |
| **Client** | User or process with Kerberos credentials; requests and uses tickets | Credential cache holding TGT, service tickets, and session keys |
| **AS (Authentication Service)** | Authenticates the client initially; issues TGT per KDC policy | KDC-managed keys and client-related keys |
| **TGS (Ticket Granting Service)** | Verifies the TGT and issues a service ticket for the requested service | `krbtgt` principal key and registered service keys |
| **Application Server / Acceptor** | Verifies AP-REQ to identify the client, then checks local authorization | Long-term service key, usually provisioned via **keytab** |
| **DNS / realm configuration** | Helps the client locate the KDC and select the right service principal | Not a source of proof for user identity |
| **Identity/authorization store** | LDAP/AD/local DB mapping the principal to user, groups, roles | Business policies and account status |

**AS and TGS are two logical functions of the KDC**, not necessarily two physical servers. In Active Directory, domain controllers typically provide the Kerberos KDC. A realm can have multiple KDCs for redundancy.

### 2.1. Realm, Principal, and Service Principal

Example realm:

~~~text
EXAMPLE.TEST
~~~

Example user principal:

~~~text
alice@EXAMPLE.TEST
~~~

Example service principals:

~~~text
krbtgt/EXAMPLE.TEST@EXAMPLE.TEST
HTTP/portal.example.test@EXAMPLE.TEST
cifs/files.example.test@EXAMPLE.TEST
~~~

Distinctions:

- `krbtgt/EXAMPLE.TEST@EXAMPLE.TEST` identifies the realm's **ticket-granting** service, whose cryptographic key only the KDC/TGS is permitted to manage. **Never use the krbtgt key as a web app keytab**.
- `HTTP/portal.example.test@EXAMPLE.TEST` is the **SPN of the web service**. When a browser visits this public hostname, the GSS/Kerberos client must obtain a service ticket for this exact SPN.
- `cifs/files.example.test@EXAMPLE.TEST` is a different service principal, not an alternate name for the website.
- Realms are uppercase by convention; hostname/canonicalization depends on KDC and client settings. Never normalize principals with naive rules in business code.

**An SPN is not a full URL**. `https://portal.example.test/reports` is the application URL, while Kerberos usually targets a principal like `HTTP/portal.example.test@EXAMPLE.TEST`. The `/reports` path is not part of an HTTP SPN. Ports, aliases, DNS, and the actual selected name depend on client/JGSS/KDC/AD policies.

## 3. What Is a TGT?

A **Ticket Granting Ticket** is a **Kerberos ticket for the Ticket-Granting Service**, usually represented by the service principal:

~~~text
krbtgt/EXAMPLE.TEST@EXAMPLE.TEST
~~~

A TGT is issued after the **AS exchange**, typically when a user logs into the domain / satisfies initial authentication or when a client runs `kinit`. It lets the client contact the TGS to request service tickets for other services **without repeatedly sending a password or repeating the AS exchange**.

The TGT contains data encrypted by the KDC with the long-term key of the **krbtgt service**, including required fields such as the client principal, timestamps, session key, flags, and authorization data per profile. The client can **store and present the TGT** to the TGS, yet **does not need and normally cannot decrypt the portion of the ticket protected by the krbtgt key**.

The client also receives a **client–TGS session key**, delivered in the AS reply encrypted under the appropriate key from initial authentication. The client needs this key to build an authenticator for **TGS-REQ**.

### 3.1. AS Exchange — Obtaining the Initial TGT

~~~text
Client                            KDC / AS
   |                                |
   | KRB_AS_REQ                     |
   | client = alice@EXAMPLE.TEST    |
   | realm, flags, pre-auth info    |
   |------------------------------->|
   |                                | authenticates principal via
   |                                | password-derived key,
   |                                | PKINIT/smartcard, etc.
   |                                |
   |<-------------------------------|
   | KRB_AS_REP                     |
   |   ticket = TGT for krbtgt      |
   |   encrypted reply = K_c,tgs   |
   |   times, flags ...             |
   |                                |
Client stores TGT + K_c,tgs in credential cache
~~~

**Do not think AS-REP sends the password to the TGS.** The password/long-term key is used during initial authentication under the Kerberos pre-authentication mechanism, never as a plaintext password sent to every application.

### 3.2. What Privileges a TGT Actually Grants

A valid TGT allows the client to **request** a service ticket via the TGS, but does not guarantee:

- That the KDC will issue a ticket for every existing SPN.
- That the client is allowed to access every resource inside each service.
- That the client is allowed to delegate credentials to any intermediary service.
- That the client has administrative privileges simply by holding a TGT.
- That a web app may use the TGT as a bearer token to open a session.

The KDC still enforces realm policy, lifetimes, ticket flags, principal status, and delegation rules. The application server must still enforce **local authorization** after identifying the principal.

### 3.3. A TGT Is Not Sent to a Spring HTTP Service

Wrong mental model:

~~~text
Browser -> Spring: TGT -> web server decrypt TGT -> logged in
~~~

Correct model:

~~~text
Client -> TGS: TGT + authenticator -> request HTTP/portal service ticket
Browser -> Spring: SPNEGO/GSS token containing AP-REQ using HTTP/portal service ticket
Spring/JGSS -> HTTP/portal keytab -> verify ticket + authenticator
~~~

A web app holds a **service keytab**, not the **krbtgt key**. If you encounter an implementation requiring the web app to hold the krbtgt key or extract a TGT from the browser to "verify login", re-evaluate that architecture and its dangerous privilege footprint.

## 4. What Is a Service Ticket?

A **service ticket** is issued by the **TGS** for **a specific service principal**, for example:

~~~text
HTTP/portal.example.test@EXAMPLE.TEST
~~~

It contains a portion encrypted with the **service principal's long-term key** known to the KDC. The receiving service can use its matching key, typically in a **keytab**, to decrypt and verify it. The client is also given a **client–service session key** by the TGS, enabling it to create an **Authenticator** proving possession of the matching session key.

Therefore, a service ticket carries two important bindings:

1. **User binding**: the requester is a Kerberos client principal authenticated/authorized by the TGS for ticket issuance.
2. **Target binding**: the ticket is issued for **one SPN**, not a list of every web app, API, or service port.

### 4.1. TGS Exchange — From TGT to Service Ticket

~~~text
Client                                   KDC / TGS
  |                                         |
  | KRB_TGS_REQ                             |
  |  TGT for krbtgt                         |
  |  authenticator using K_c,tgs            |
  |  sname = HTTP/portal.example.test       |
  |---------------------------------------->|
  |                                         | decrypt TGT with
  |                                         | krbtgt key; check
  |                                         | time, flags, KDC
  |                                         | policy, principal
  |                                         |
  |<----------------------------------------|
  | KRB_TGS_REP                             |
  |  service ticket protected by K_svc      |
  |  encrypted reply grants K_c,svc         |
  |                                         |
Client caches HTTP/portal ticket and K_c,svc
~~~

**K_c,tgs** and **K_c,svc** are two distinct session keys:

- `K_c,tgs` serves the client–TGS relationship, tied to the TGT.
- `K_c,svc` serves the client–service relationship, tied to the service ticket.
- `K_svc` is the **service's long-term key**, stored at the KDC and in the service keytab; **it is not a session key**.
- `K_krbtgt` is the Ticket-Granting Service key; **it does not belong in an HTTP service keytab**.

Do not write application code that derives these keys from an email/user ID or uses a `ticketId` string as a secret. Kerberos/JGSS/JDK/OS libraries handle the protocol and cryptography.

### 4.2. One TGT Can Request Multiple Service Tickets

Suppose Alice already holds a TGT:

~~~text
TGT(alice -> krbtgt/EXAMPLE.TEST)
   |
   +-> TGS request "HTTP/portal.example.test" -> ticket for Portal
   |
   +-> TGS request "cifs/files.example.test" -> ticket for Files
   |
   +-> TGS request "HTTP/wiki.example.test" -> ticket for Wiki
~~~

**The user does not re-enter their password every time a service ticket is requested**. The client OS/credential cache can retain the TGT until it expires or becomes unusable; service tickets are also cached per SPN within their validity window.

However, a service ticket issued for Files cannot be used to log into Portal, even when both share the same realm and client principal.

## 5. Comparing TGT and Service Ticket

| Criterion | Ticket Granting Ticket (TGT) | Service ticket |
| --- | --- | --- |
| Issuer | KDC **AS** in AS exchange, or TGS for inter-realm TGT | KDC **TGS** |
| Recipient / target | `krbtgt/REALM@REALM` or inter-realm `krbtgt/DEST@SRC` | Service principal like `HTTP/portal...@REALM` |
| Purpose | Request additional service tickets via TGS; enables subsequent auth without re-entering password | Authenticate the client to **a single application service** |
| Ticket encryption key | Key of the TGS/krbtgt principal | Long-term key of the service principal |
| Session key given to client | Client–TGS session key | Client–service session key |
| Where client sends it | Inside KRB_TGS_REQ to the TGS, with an authenticator | Inside KRB_AP_REQ/GSS token to the target service |
| Typically seen by Spring web app? | **No** | **Yes, inside GSS/SPNEGO token** |
| Who can decrypt the ticket | TGS/KDC holding the matching key | Target service holding the keytab; certain special profiles differ |
| Lifetime | Governed by KDC policy; may be renewable/forwardable | Governed by TGS policy; has start/end times and flags |
| Reuse | Can request multiple service tickets while valid | Can appear in multiple AP exchanges while valid; **Authenticator must be fresh each time** |
| Exposure risk | An attacker holding both TGT and session key can request multiple tickets within policy limits | An attacker holding both service ticket and session key can attempt impersonation at **the issued service** |
| Invalidation | Expiration, ticket/policy checks, key rotation, and admin controls per deployment | Expiration, service account key rotation, local sessions, and environment policies |
| Relation to local roles | Does not grant ROLE_ADMIN | After service authentication, requires UserDetails/local authorization |

### 5.1. "A TGT Always Lives Longer" Is Not a Law

TGTs are typically configured with a lifetime suited for an SSO session; service tickets have lifetimes per their own policy. Never assert that **a TGT is always longer than a service ticket** or always lasts a fixed number of hours. The KDC enforces **endtime, renew-till, realm policy, principal policy, and service policy**; inspect actual tickets.

### 5.2. "Service Tickets Are One-Time Use" Is Incorrect for Kerberos V5

A very common misconception when learning federation:

- A **Kerberos service ticket** can be reused by the client across multiple AP exchanges while still valid, with a **fresh Authenticator** and appropriate service/GSS security context conditions.
- A **submitted Authenticator** must be protected against **replay**; the service/GSS stack uses timestamps/sequences and a replay cache or compatible mechanisms.
- Do not treat `Authorization: Negotiate <token>` as "one-time use in every sense"; HTTP negotiation and GSS tokens/state have their own lifecycle.
- Some application wrappers/caches enforce shorter policies than the Kerberos ticket lifetime, without changing RFC 4120's ticket definition.

This is why you must separate **TGT**, **service ticket**, **authenticator**, **GSS security context**, and **HttpSession**; they are not the same kind of state.

## 6. AP Exchange — Service Ticket Combined with an Authenticator

After obtaining a service ticket, the client begins the **Application Service exchange**:

~~~text
Client / GSS initiator                    Service / GSS acceptor
       |                                           |
       | KRB_AP_REQ                                |
       |   service ticket for HTTP/portal          |
       |   Authenticator encrypted by K_c,svc      |
       |------------------------------------------>|
       |                                           | keytab K_svc
       |                                           | -> decrypt ticket
       |                                           | -> recover K_c,svc
       |                                           | -> verify Authenticator
       |                                           | -> time/replay/identity
       |                                           |
       |<------------------------------------------|
       | Optional KRB_AP_REP for mutual auth        |
       |                                           |
       v                                           v
Client knows service identity              Server receives client principal
~~~

A **service ticket alone does not prove the sender knows the session key**. RFC 4120 specifies an **Authenticator** encrypted with the session key to prove possession and help prevent an attacker from merely copying a captured ticket and replaying it.

### 6.1. What Does a Service Ticket Carry?

Conceptually:

~~~text
Ticket:
  realm = EXAMPLE.TEST
  sname = HTTP/portal.example.test
  enc-part:
    client = alice@EXAMPLE.TEST
    session-key = K_c,svc
    flags = initial/forwardable/... (per ticket)
    authtime, starttime, endtime, renew-till
    client addresses (if applicable)
    authorization-data (if present)
  kvno = service key version
  enctype = ticket encryption algorithm
~~~

This is a **conceptual illustration**, not a complete ASN.1/DER ticket, nor an editable JSON token. The TGS protects `enc-part` using the **service long-term key**. The client cannot alter `sname`, expiry, username, or flags and expect the web app to trust them.

### 6.2. What Does an Authenticator Carry?

Conceptually:

~~~text
Authenticator:
  client realm/name
  timestamp (ctime, cusec)
  optional subkey / sequence / checksum
  protected by K_c,svc
~~~

Required checks:

1. The service ticket decrypts under the proper service key/kvno/enctype.
2. The service ticket was issued for the exact service principal the server is configured to accept.
3. The ticket is within its validity window, with compatible flags/constraints.
4. The client identity in the authenticator matches the client attested by the ticket.
5. The authenticator demonstrates possession of the right client–service session key.
6. Timestamp, clock skew, and replay cache prevent accepting a replayed authenticator.
7. If mutual authentication is required, the client verifies the corresponding `AP-REP`/GSS context response.
8. If channel binding/extended protection is used, binding data matches both sides' configuration.

**Do not reimplement ASN.1 parsers or Kerberos cryptography in a Spring controller.** Use JAAS/JGSS/Spring Security Kerberos with properly configured KDC/service principals.

### 6.3. Ticket Key Version Number (KVNO)

**KVNO** indicates which key version encrypted the ticket. When a service account changes password or rotates keys:

- The KDC may start issuing tickets encrypted with the **new key**.
- A server still holding the **old keytab** cannot decrypt new tickets.
- Older cached service tickets may still use the old key; if the server removes all old keys, old in-flight requests may fail.
- A keytab can contain multiple entries across different **kvno/enctype** values to support controlled transitions per policy.

Therefore, never work around a post-rotation GSS exception by disabling Kerberos or "trusting a username header". Coordinate **KDC keys, service account, KVNO, and keytab deployment**.

## 7. Kerberos Credential Cache vs. Keytab

| Store | Typical Location | Contents | Role |
| --- | --- | --- | --- |
| **Client credential cache** | OS logon session, MIT credential cache, Windows LSA | Client's TGT, service tickets, and session keys | Lets client/browser acquire and present tickets |
| **Server service keytab** | File/secret volume readable only by the service | Service principal long-term keys, KVNO, enctype | Lets the GSS acceptor verify service tickets |
| **KDC principal database** | KDC/AD directory and key store | Long-term keys and principal policies | KDC issues/validates tickets and administers the realm |
| **Spring HttpSession** | App server/session store | Local Authentication after SPNEGO login per config | Not a raw TGT/ST cache |
| **Replay cache/credential context** | Kerberos/JGSS/OS library | State to reject duplicate authenticators | Distinct from Spring's session |

**Never copy a client credential cache or user TGT onto the web server just to "help login"**. The acceptor side normally needs only the **service keytab**, never user passwords or TGTs. A keytab is a long-term secret: anyone obtaining it can impersonate the service or decrypt matching tickets within the key's scope.

### 7.1. Do Not Confuse a Keytab with a Ticket

A keytab can be inspected with:

~~~bash
klist -k -t -e /run/secrets/kerberos/http.keytab
~~~

This command lists only principal, KVNO, timestamp, and enctype (depending on the MIT Kerberos version), **without printing raw keys**. Avoid `klist -K` in logs/CI because `-K` can reveal **cryptographic key values**.

A valid service keytab for Portal might contain entries like:

~~~text
KVNO Principal
---- ------------------------------------------------
   4 HTTP/portal.example.test@EXAMPLE.TEST (aes256-cts-hmac-sha1-96)
   5 HTTP/portal.example.test@EXAMPLE.TEST (aes256-cts-hmac-sha1-96)
~~~

This is **illustrative output**, not taken from a real keytab. Actual enctypes depend on the environment and allowed algorithms; do not treat one type as universally mandatory.

### 7.2. A Keytab Is a Secret — Never Commit It

Safeguards:

- Provision from KDC/AD via an approved process with a dedicated service account and auditing.
- Mount into containers via read-only secret storage/volumes with tight filesystem and process-identity permissions.
- Never place keytab files in `src/main/resources` or public artifacts; never send them to logs, test reports, or Git.
- Do not share a single service principal/keytab across all apps when trust or rotation boundaries should be separated.
- Rotate keytabs/kvnos on schedule with pre/post testing, avoiding holding stale keys in memory too long.
- Restrict delegation rights on the service account; never enable unconstrained delegation unintentionally.
- Never hand the keytab to an untrusted reverse proxy/plugin solely to read HTTP headers.

## 8. Kerberos Over HTTP: SPNEGO and the Negotiate Header

**SPNEGO (Simple and Protected GSS-API Negotiation Mechanism)** allows client and server to negotiate a GSS-API authentication mechanism. **HTTP Negotiate** per RFC 4559 typically uses SPNEGO to carry Kerberos authentication tokens over HTTP headers.

Illustrative exchange:

~~~http
GET /private HTTP/1.1
Host: portal.example.test

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Then the browser uses OS Kerberos credentials, requesting a service ticket from the TGS if not already cached, and sends:

~~~http
GET /private HTTP/1.1
Host: portal.example.test
Authorization: Negotiate <base64-GSS-token>
~~~

The server may reply:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate <optional-response-GSS-token>
~~~

**This is an illustrative message shape, not a valid HTTP trace to copy and replay verbatim.** `<base64-GSS-token>` is neither a plaintext Kerberos ticket, nor a TGT, nor a username/password. It may contain **SPNEGO NegTokenInit/NegTokenResp**, Kerberos AP-REQ, mechanism OIDs, and security context data per profile.

### 8.1. What the Browser Does Under the Hood

1. The user has an OS/domain Kerberos session or an appropriate credential cache.
2. The browser knows the website is permitted for **Integrated Authentication/Negotiate** via intranet allowlist/enterprise policy.
3. The browser/JGSS selects a service principal based on the URL and Kerberos config, e.g. `HTTP/portal.example.test@EXAMPLE.TEST`.
4. If no service ticket is cached yet, the OS/GSS uses the **TGT** to request a ticket from the TGS.
5. The browser builds a GSS/SPNEGO token for the service.
6. The server receives `Authorization: Negotiate` and verifies it using its service keytab.
7. Browser and server may exchange an extra round if the GSS context requires it.

**Not every HTTP request has to hit the KDC.** If the TGT/service ticket/GSS context is already cached, the client can reuse valid state until expiry. Subsequent requests without a Negotiate header are often recognized via the web app's **local HttpSession**.

### 8.2. SPNEGO Can Negotiate NTLM — Do Not Assume Kerberos

In some Windows environments, HTTP `Negotiate` can negotiate **either Kerberos or NTLM**. If product security policy requires Kerberos:

- Monitor the **actual negotiated mech** and configure client/server to accept only approved mechanisms.
- Never treat the presence of a `Negotiate` header as proof that a Kerberos AP-REQ was verified.
- Define behavior when the browser has no TGT, wrong SPN, or no KDC connectivity.
- If a form/NTLM fallback exists, enforce a dedicated security policy so authentication assurance is not silently downgraded.
- Never turn `WWW-Authenticate: Negotiate` into "Basic Authentication" or read credentials from query strings.

### 8.3. HTTPS Is Still Required

Kerberos/GSS-API provides authentication and offers message protection within GSS when used directly, yet **HTTP Negotiate alone does not encrypt the entire HTTP URL, headers, cookies, or response body**. RFC 4559 explicitly notes that HTTP Negotiate **does not protect the entire HTTP payload**.

Use **HTTPS/TLS**, appropriate Secure/HttpOnly/SameSite cookies, CSRF protection for state-changing requests, and trusted proxies. Never skip TLS simply because "the ticket is already encrypted".

## 9. Spring Security Kerberos: Filter and Provider

When a Spring Boot application acts as an HTTP service behind Negotiate:

~~~text
Browser
  |
  | Authorization: Negotiate <GSS token>
  v
SpnegoAuthenticationProcessingFilter
  |
  | creates KerberosServiceRequestToken
  v
AuthenticationManager / ProviderManager
  |
  v
KerberosServiceAuthenticationProvider
  |
  v
KerberosTicketValidator (e.g., SunJaasKerberosTicketValidator)
  |
  | JAAS/JGSS acceptSecContext
  | servicePrincipal + service keytab
  v
Verified result: alice@EXAMPLE.TEST
  |
  v
UserDetailsService / local identity mapping
  |
  v
Spring Authentication + GrantedAuthorities
  |
  v
SecurityContextRepository / session per config
  |
  v
Authorization to /private or API
~~~

Typical classes documented in Spring Security Kerberos:

| Class | Role | What Not to Confuse It With |
| --- | --- | --- |
| `SpnegoEntryPoint` | Returns `401` and `WWW-Authenticate: Negotiate` when authentication is needed | Not where a TGT is requested from the KDC |
| `SpnegoAuthenticationProcessingFilter` | Reads Negotiate header, builds `KerberosServiceRequestToken`, calls AuthenticationManager | Never trust base64 token before validator |
| `KerberosServiceAuthenticationProvider` | Invokes KerberosTicketValidator and loads UserDetails | Does not automatically enforce all business roles |
| `SunJaasKerberosTicketValidator` | Uses JAAS/JGSS to verify Kerberos/SPNEGO token against service principal/keytab | Keytab must match the service SPN/keys |
| `UserDetailsService` | Maps the verified Kerberos principal to local authorities | Not a KDC or ticket validator |
| `SecurityContextRepository` | Persists local Authentication across HTTP requests when stateful | Not the client's TGT cache |

**Where is the TGT in this diagram?** In the **client OS/credential cache and KDC TGS exchange**, **not inside SpnegoAuthenticationProcessingFilter for the app to process directly**.

### 9.1. Two Easily Confused Providers

- `KerberosServiceAuthenticationProvider`: used when the server **receives a service ticket/SPNEGO token** and must authenticate the client using an acceptor keytab.
- `KerberosAuthenticationProvider`: can be used for **username/password Kerberos login** via KerberosClient in certain designs/fallbacks; not required when only accepting browser SPNEGO service tickets.

Do not configure `KerberosAuthenticationProvider` assuming it validates browser `Authorization: Negotiate`; `KerberosServiceAuthenticationProvider` is normally needed for the service ticket path.

### 9.2. Spring Security Kerberos Is an Extension Module

Spring Security Kerberos has separate documentation and artifacts. According to Spring Security 7.x documentation, the dependency coordinates are:

~~~groovy
// build.gradle: Spring Security 7.x, versions managed by BOM
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.security:spring-security-kerberos-core"
    implementation "org.springframework.security:spring-security-kerberos-web"
}
~~~

**Verify version alignment with your actual Spring Boot and Spring Security release**. In earlier Spring Security Kerberos for 6.x, the artifact group was typically **`org.springframework.security.kerberos`** (for example `spring-security-kerberos-web:2.2.0`). **Starting with Spring Security Kerberos 7**, official documentation states the group changed to **`org.springframework.security`**. Do not mix arbitrary groups/versions to force the classpath to compile, and do not copy the Gradle snippet above as a complete project without SPN/keytab/KDC.

Source: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html .

## 10. Spring Security Servlet Configuration Sample for SPNEGO

This example targets **Spring Security Kerberos 7.x** with JDK 17+ in a Servlet application. It assumes infrastructure has provisioned a service account/keytab and the system provides a `UserDetailsService` bean. The example **does not create a real KDC or keytab**.

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class SpnegoSecurityConfig {
    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
            "HTTP/portal.example.test@EXAMPLE.TEST");
        validator.setKeyTabLocation(new FileSystemResource(
            "/run/secrets/kerberos/http.keytab"));
        // Do not enable verbose credential debug in production.
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService userDetailsService) {
        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {
        ProviderManager manager = new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);
        filter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error")
                .permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationProvider(provider)
            .addFilterBefore(
                filter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**This is a Spring configuration sample**, not standalone runnable Java: it needs a Spring Boot project, matching dependencies/APIs, a `UserDetailsService` bean, KDC/realm config, and a real service principal and keytab. If using Spring Security 6.x, check the corresponding package/import/method names and module version.

Trace the flow:

1. `SpnegoEntryPoint` challenges the browser with HTTP Negotiate.
2. The browser sends a GSS token for the public SPN.
3. `SpnegoAuthenticationProcessingFilter` builds an authentication request from the header and calls `ProviderManager`.
4. `KerberosServiceAuthenticationProvider` delegates to `SunJaasKerberosTicketValidator` to verify the token.
5. The validator uses the **service keytab**, not a password or user TGT.
6. Upon obtaining a valid Kerberos principal, `UserDetailsService` looks up the user and authorities in the application.
7. The filter saves `SecurityContext` in HttpSession per the stateful configuration shown.
8. `authorizeHttpRequests` rules still enforce local authorities and resource permissions.

**Operational note:** do not additionally declare `@Bean SpnegoAuthenticationProcessingFilter`, which causes the Servlet container to register the filter a second time outside the Spring Security chain. If a bean is required for another architecture, control it with `FilterRegistrationBean`. A service ticket/GSS token must never be validated in two duplicate filters as a fallback.

### 10.1. Service Keytab and Principal in the Runtime Environment

Example containerized app deployment:

~~~text
JAVA_OPTS:
  -Djava.security.krb5.conf=/etc/krb5.conf

Keytab file:
  /run/secrets/kerberos/http.keytab  (read-only)

Service principal:
  HTTP/portal.example.test@EXAMPLE.TEST
~~~

These lines are **illustrative deployment parameters**, not a complete Kubernetes YAML manifest. The SPN must be registered in KDC/AD for the right service identity, the keytab must hold the matching key, and the Java runtime must have read permission on the file. Never let Spring infer the SPN from a client-supplied Host header.

### 10.2. Do Not Mix Up Local Sessions and Kerberos Tickets

After SPNEGO succeeds, the application may keep a local `HttpSession`. Subsequent requests can be served via the session cookie **without sending a new GSS token**.

**HttpSession logout** only clears the application session; it **does not clear TGTs/service tickets in the OS credential cache**. On the next visit, the browser may perform Negotiate and **re-authenticate immediately** using valid Kerberos credentials. If the product requires domain/device sign-out or "force interactive reauthentication", design dedicated OS/KDC/browser policies; do not treat Spring's `POST /logout` as wiping all Kerberos tickets.

## 11. Configuring Realm, KDC, and Service Principal

### 11.1. Example krb5.conf

File `/etc/krb5.conf` on Linux or equivalent Kerberos configuration:

~~~ini
[libdefaults]
    default_realm = EXAMPLE.TEST
    dns_lookup_kdc = false
    rdns = false

[realms]
    EXAMPLE.TEST = {
        kdc = kdc.example.test
    }

[domain_realm]
    .example.test = EXAMPLE.TEST
    example.test = EXAMPLE.TEST
~~~

This is a **sample configuration for learning**, not real server data. In Active Directory, DNS SRV records and referral/cross-realm policies may be used instead of hardcoding a KDC; do not overwrite environment configs approved by IT/domain teams. `rdns=false` can reduce unwanted reverse-DNS canonicalization in some topologies, yet must be tested against your real client/JDK/AD ecosystem.

### 11.2. HTTP Service Principal Must Match the Public Hostname

If users visit:

~~~text
https://portal.example.test/private
~~~

The Kerberos client typically needs SPN:

~~~text
HTTP/portal.example.test@EXAMPLE.TEST
~~~

If the app's keytab only contains:

~~~text
HTTP/app-node-1.internal@EXAMPLE.TEST
~~~

then the acceptor may fail to decrypt/verify tickets for the public hostname. Do not strip service keytab checks to accept arbitrary tickets; instead:

- Register the public/alias SPN properly in KDC/AD.
- Map the SPN to the right owning service account.
- Issue the matching keytab and keep KVNOs synchronized.
- Verify DNS CNAMEs and canonicalization from browser/JGSS rather than assuming internal container names.
- Behind a load balancer, ensure every instance holds a valid key/service principal or authenticate at a clearly designed trusted edge.
- With a reverse proxy, ensure the `Authorization: Negotiate` header reaches the actual acceptor; **never trust `X-Remote-User` from the Internet**.

### 11.3. Active Directory and Duplicate SPNs

In AD, an SPN must be registered uniquely for the service identity. Duplicate SPNs, a wrong service account, or a keytab exported from a different account can produce:

~~~text
KRB_AP_ERR_MODIFIED
GSSException: Defective token / Cannot find key of appropriate type
401 Negotiate loop
~~~

These are case-dependent symptoms, not a single error with one universal cause. Domain admins can use official tools such as `setspn -Q` to inspect SPNs and follow approved procedures to register/rotate service accounts. **Never generate a keytab by resetting a production service account's password outside of a coordinated plan**, as other instances may lose the ability to decrypt service tickets.

## 12. Safe Diagnostics with MIT Kerberos Tools

The commands below are **examples for MIT Kerberos on compatible Linux/macOS systems** and do not guarantee identical syntax to Windows `klist`. Do not run them in production without authorization and change procedures, especially operations that modify a credential cache.

### 12.1. kinit — Obtaining a TGT

~~~bash
kinit alice@EXAMPLE.TEST
~~~

Purpose: request a **TGT for alice** from the KDC using the configured authentication mechanism. The command may prompt for a password or another factor; never put passwords in shell commands or history.

To request a policy-compliant lifetime:

~~~bash
kinit -l 8h alice@EXAMPLE.TEST
~~~

**Note:** `-l 8h` is a **requested** lifetime; the KDC may issue a shorter one per policy. You cannot create an unlimited TGT by raising client flags.

When permitted by KDC/IT and the TGT carries the renewable flag:

~~~bash
kinit -R
~~~

This renews only when `renew-till` and current validity rules are satisfied. `kinit -R` cannot bypass a TGT invalidated by KDC/policy.

### 12.2. klist — Viewing the Credential Cache

~~~bash
klist
klist -f
klist -e
~~~

Illustrative output may include:

~~~text
Default principal: alice@EXAMPLE.TEST

Valid starting      Expires             Service principal
...                 ...                 krbtgt/EXAMPLE.TEST@EXAMPLE.TEST
...                 ...                 HTTP/portal.example.test@EXAMPLE.TEST
~~~

This is an **illustrative template**, without fabricated timestamps and not output from a real machine.

- The `krbtgt/EXAMPLE.TEST@EXAMPLE.TEST` entry is the **TGT**.
- The `HTTP/portal.example.test@EXAMPLE.TEST` entry is the **service ticket**.
- `-f` shows client-visible flags such as Forwardable/Renewable.
- `-e` shows ticket/session key enctypes.
- If `klist` shows no TGT, the browser may lack credentials to request a service ticket; also check OS/Windows LSA behavior.

Do not post `klist` screenshots containing real principals or ticket details to public forums during privacy-sensitive investigations.

### 12.3. kvno — Requesting and Inspecting Service Key Version

~~~bash
kvno HTTP/portal.example.test@EXAMPLE.TEST
klist
~~~

`kvno` requires the client to hold a valid ticket cache/TGT and requests a service ticket for the specified SPN from the KDC. In MIT Kerberos it prints the key version number, verifying that the service principal exists and the KDC issues tickets for it.

**Succeeding with kvno does not prove the Spring acceptor has the matching keytab**. A client can obtain a service ticket while the service still fails decryption due to a wrong KVNO/enctype or Java/security misconfiguration.

### 12.4. klist -k — Inspecting the Service Keytab

~~~bash
klist -k -t -e /run/secrets/kerberos/http.keytab
~~~

Check:

- Is `HTTP/portal.example.test@EXAMPLE.TEST` present?
- Do KVNO and encryption types match the ticket/KDC?
- Are file owner/group/permissions secure, and can the JVM read it?
- Is an old keytab still in use after rotation?

**Never run `klist -K` into logs**, as depending on the version it prints actual key material. Never copy a production keytab to a personal workstation for testing.

### 12.5. kdestroy — Clearing Local Cache, Not Global Logout

~~~bash
kdestroy
~~~

This command deletes Kerberos credentials in the client's selected credential cache (per MIT Kerberos semantics). It **does not mean** all local service sessions or tickets issued elsewhere are immediately revoked. Under Windows domain logon, cache/SSO management uses different tools and policies.

## 13. Checking Time, Ticket Flags, and Lifetimes

Kerberos relies on timestamps to bound tickets and prevent replay:

| Field / Flag | General Meaning | Common Implementation Mistake |
| --- | --- | --- |
| `authtime` | Time when the principal was initially authenticated | Confusing with individual HTTP request times |
| `starttime` | Time when the ticket becomes valid | Clock skew making the ticket "not yet valid" |
| `endtime` | Ticket expiration time | Using expired tokens or caching too long |
| `renew-till` | Maximum deadline to renew a ticket if allowed by flag | Assuming a TGT can be renewed forever |
| `forwardable` | Allows forwarding the TGT under specified conditions | Accidentally granting overly broad delegation |
| `renewable` | Allows requesting TGT renewal per policy | App attempts renewal without the flag set |
| `ok-as-delegate` | Hints that the service is considered suitable for delegation under policy | Treating the flag as blanket delegation permission |
| `kvno` | Key version used to encrypt the ticket | Stale keytab after rotation |
| `enctype` | Encryption algorithm for ticket/session key | Client/KDC/service lack a common cipher suite |
| `client addresses` | Address restrictions when enforced by profile/policy | NAT/proxies breaking address assumptions |

Some deployments permit a **clock skew** of a few minutes; around five minutes is a common example, though **that does not mean every realm must use exactly 5 minutes**. Rely on accurate NTP and the environment's skew policy; never widen clock skew excessively just to force login to succeed.

### 13.1. Service Ticket Expired While TGT Is Still Valid

If an SPN service ticket expires while the TGT remains valid, the client can **request a new service ticket from the TGS**. Browser/app does not need to return to an AS exchange if all other conditions remain satisfied.

### 13.2. TGT Expired While a Service Ticket Remains Cached

Do not assume TGT expiration always immediately invalidates an **already-issued service ticket** at the service. Service tickets have their own lifetime and validation rules and can continue working within their validity period under relevant policies; however, the KDC may cap ST lifetimes at issuance and environment-specific policies can alter outcomes.

Key point: **TGT and service ticket do not share the same TTL or cache entry**.

### 13.3. Does Disabling a User or Logging Out Immediately Revoke All Service Tickets?

Not automatically. A Kerberos server can verify an AP-REQ **offline using its keytab** and ticket fields; it does not necessarily contact the KDC to check account status on every call. An issued ticket can remain valid until `endtime` or until other policy/key/validation rules reject it. To achieve rapid access revocation, consider:

- Shortening ticket lifetimes as required.
- Local session invalidation and enabled/locked/resource authorization checks.
- Controlled KDC/service account key rotation/credential invalidation.
- Application session management or supporting AD/KDC policies.
- Avoiding promises that "disabling an AD account instantly kills all HTTP sessions" without verification.

## 14. Forwardable TGTs and Kerberos Delegation: Distinct Risks

**Forwardable** or **proxiable** flags enable specialized Kerberos delegation flows. For example, a web service may need to access an SMB share or database **on the user's behalf** rather than under its own machine identity.

**If delegation is not needed**, avoid enabling:

- Unconstrained delegation: the service can receive/use forwarded credentials broadly, creating a huge blast radius if the host/keytab is compromised.
- Storing a user's TGT on the server as "login state" without strict credential governance.
- Letting any HTTP request header dictate a user and forge KDC tickets on their behalf.

If delegation is genuinely required:

1. Identify the exact permitted target services.
2. Use Kerberos constrained delegation/S4U or a model approved by the domain/security team.
3. Audit client credential-forwarding policies and service principal rights.
4. Scope users/services/realms, credential cache lifetimes, and auditing.
5. Restrict keytab secrets, process/container privileges, and trusted hosts.
6. Test double-hop scenarios and TGS errors specifically without turning them into "read all data" permissions.
7. Never assume every SPNEGO token carries a user TGT for the service to forward.

**A normal service ticket for `HTTP/portal` does not mean the server was granted a user TGT to call every downstream service.** That is the boundary between **authentication** and **delegation**.

## 15. Cross-Realm: A TGT Does Not Unconditionally Span Every Realm

A client in `SALES.EXAMPLE.TEST` might need a service in `CORP.EXAMPLE.TEST`. With **cross-realm Kerberos**, a KDC can issue an **inter-realm TGT** and follow a configured trust path to acquire a service ticket in the target realm.

~~~text
alice@SALES.EXAMPLE.TEST
      |
      v
TGT at SALES KDC
      |
      v
Inter-realm TGT (established trust path)
      |
      v
CORP KDC / TGS
      |
      v
Service ticket HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST
      |
      v
Spring HTTP acceptor at CORP
~~~

Points to verify:

- Realm trust/transited policy: never assume all realms trust one another.
- Target SPN and realm must align; never accept a realm unconditionally from user input.
- Cross-realm identities may share the same username across two realms while being **two distinct principals**.
- Local identity keys should be scoped by **principal + realm/issuer**, with permissions driven by local policy.
- Never enable wildcard realms or map every foreign principal named `alice` into the same admin account.
- MIT/AD referrals and DNS canonicalization can cause the actual realm to differ from operator assumptions.

## 16. Standalone Java 17 Example: Lifecycle of TGT, Service Ticket, and Authenticator

This program **runs on JDK 17+** with no Spring Boot, JGSS, KDC, AD, or network required. It is an **educational simulation**, not a Kerberos implementation. Its goal is to verify key invariants:

- One valid TGT can be used to request **two distinct service tickets**.
- A web acceptor rejects a **TGT** (because a TGT is not for a web service).
- A valid, unexpired service ticket for `HTTP/portal` with the matching principal and **authenticator proof** is accepted.
- Replaying the **same authenticator** is rejected by the replay cache.
- The **same service ticket** with a **fresh authenticator** can be accepted while the ticket remains valid.
- Wrong SPN, wrong principal, missing session-key proof, expired ticket, stale authenticator, expired TGT, and unregistered SPN are all rejected.

**Mandatory security notice:** the booleans `issuedByKdc` and `provesPossessionOfSessionKey` are **simulated outputs from a trusted verifier in a unit test**, not data read from an HTTP request or a self-asserted client "claim". In real Kerberos, **long-term keys, session keys, ticket encryption, authenticator cryptography, replay caches, and time checks** are handled by KDC/JGSS/Kerberos libraries. Never use this code in a web filter, never construct TGTs/service tickets out of Java records, and never grant access from booleans.

File **KerberosTicketsLifecycleDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class KerberosTicketsLifecycleDemo {
    private static final String TGS = "krbtgt/EXAMPLE.TEST@EXAMPLE.TEST";
    private static final String WEB = "HTTP/portal.example.test@EXAMPLE.TEST";
    private static final String FILES = "cifs/files.example.test@EXAMPLE.TEST";

    // All trust booleans are outputs from a MOCK verifier, NOT user input.
    record Tgt(String client, String tgsPrincipal,
               Instant expiresAt, boolean issuedByKdc) {}
    record ServiceTicket(String id, String client, String servicePrincipal,
                         Instant issuedAt, Instant expiresAt,
                         boolean issuedByKdc) {}
    record Authenticator(String client, String nonce, Instant createdAt,
                         boolean provesPossessionOfSessionKey) {}

    static final class FakeTgs {
        private final Set<String> registeredServices = Set.of(WEB, FILES);
        private final AtomicInteger sequence = new AtomicInteger();

        Optional<ServiceTicket> request(Tgt tgt, String spn, Instant now) {
            if (tgt == null || !tgt.issuedByKdc()
                    || !TGS.equals(tgt.tgsPrincipal())
                    || !now.isBefore(tgt.expiresAt())
                    || !registeredServices.contains(spn)) {
                return Optional.empty();
            }
            return Optional.of(new ServiceTicket(
                "ticket-" + sequence.incrementAndGet(),
                tgt.client(), spn, now,
                now.plus(Duration.ofMinutes(15)), true));
        }
    }

    static final class FakeAcceptor {
        private final String expectedSpn;
        private final Set<String> replayCache = ConcurrentHashMap.newKeySet();
        private final Duration allowedSkew = Duration.ofMinutes(5);

        FakeAcceptor(String expectedSpn) {
            this.expectedSpn = expectedSpn;
        }

        boolean accept(Object credential, Authenticator authenticator,
                       Instant now) {
            // A TGT cannot authenticate directly to an application service.
            if (!(credential instanceof ServiceTicket ticket)) return false;
            if (authenticator == null || !ticket.issuedByKdc()) return false;
            if (!expectedSpn.equals(ticket.servicePrincipal())) return false;
            if (now.isBefore(ticket.issuedAt())
                    || !now.isBefore(ticket.expiresAt())) return false;
            if (!ticket.client().equals(authenticator.client())
                    || !authenticator.provesPossessionOfSessionKey()) {
                return false;
            }
            Duration difference = Duration.between(
                authenticator.createdAt(), now).abs();
            if (difference.compareTo(allowedSkew) > 0) return false;
            // Real Kerberos validates cryptographic authenticators
            // and uses a replay cache.
            return replayCache.add(ticket.id() + ":" + authenticator.nonce());
        }
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-01T10:00:00Z");
        FakeTgs kdc = new FakeTgs();
        Tgt tgt = new Tgt(
            "alice@EXAMPLE.TEST", TGS, start.plusSeconds(3600), true);
        Optional<ServiceTicket> web = kdc.request(tgt, WEB, start);
        Optional<ServiceTicket> files = kdc.request(tgt, FILES, start);
        System.out.println("oneTgtGetsTwoServiceTickets=" +
            (web.isPresent() && files.isPresent()));

        FakeAcceptor webServer = new FakeAcceptor(WEB);
        Instant now = start.plusSeconds(30);
        Authenticator one = new Authenticator(
            "alice@EXAMPLE.TEST", "auth-one", now, true);

        System.out.println("tgtRejectedByWeb=" +
            !webServer.accept(tgt, one, now));
        System.out.println("validServiceTicketAccepted=" +
            webServer.accept(web.orElseThrow(), one, now));
        System.out.println("sameAuthenticatorReplayRejected=" +
            !webServer.accept(web.orElseThrow(), one, now));

        Authenticator fresh = new Authenticator(
            "alice@EXAMPLE.TEST", "auth-two", now.plusSeconds(1), true);
        System.out.println("sameServiceTicketFreshAuthenticatorAccepted=" +
            webServer.accept(web.orElseThrow(), fresh, now.plusSeconds(1)));

        System.out.println("wrongServiceRejected=" +
            !webServer.accept(files.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "auth-files", now, true),
                now));
        System.out.println("wrongClientRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("mallory@EXAMPLE.TEST", "other", now, true),
                now));
        System.out.println("noSessionKeyProofRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "unproven", now, false),
                now));
        System.out.println("expiredServiceTicketRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "expired",
                    start.plusSeconds(901), true),
                start.plusSeconds(901)));
        System.out.println("staleAuthenticatorRejected=" +
            !webServer.accept(web.orElseThrow(),
                new Authenticator("alice@EXAMPLE.TEST", "stale",
                    start.minusSeconds(400), true), now));
        System.out.println("expiredTgtCannotIssueNewTicket=" +
            kdc.request(tgt, WEB, start.plusSeconds(3601)).isEmpty());
        System.out.println("unknownServiceDeniedByKdc=" +
            kdc.request(tgt,
                "HTTP/unknown.example.test@EXAMPLE.TEST", now).isEmpty());
        System.out.println("untrustedTgtRejectedByKdc=" +
            kdc.request(new Tgt(
                "alice@EXAMPLE.TEST", TGS, start.plusSeconds(3600), false),
                WEB, now).isEmpty());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 KerberosTicketsLifecycleDemo.java
java KerberosTicketsLifecycleDemo
~~~

**Exact stdout:**

~~~text
oneTgtGetsTwoServiceTickets=true
tgtRejectedByWeb=true
validServiceTicketAccepted=true
sameAuthenticatorReplayRejected=true
sameServiceTicketFreshAuthenticatorAccepted=true
wrongServiceRejected=true
wrongClientRejected=true
noSessionKeyProofRejected=true
expiredServiceTicketRejected=true
staleAuthenticatorRejected=true
expiredTgtCannotIssueNewTicket=true
unknownServiceDeniedByKdc=true
untrustedTgtRejectedByKdc=true
~~~

Explanation:

- **oneTgtGetsTwoServiceTickets=true**: the same TGT acquires tickets for Portal and Files.
- **tgtRejectedByWeb=true**: the web server acceptor does not accept a TGT.
- **validServiceTicketAccepted=true**: a service ticket for the right SPN is accepted with a valid authenticator.
- **sameAuthenticatorReplayRejected=true**: the same authenticator cannot be used twice in the demo replay cache.
- **sameServiceTicketFreshAuthenticatorAccepted=true**: the same unexpired ticket is reused with a **fresh authenticator** — distinguishing the two objects.
- **wrongServiceRejected=true**: a Files ticket cannot be used at Portal.
- **wrongClientRejected=true**: an authenticator impersonating another principal is rejected.
- **noSessionKeyProofRejected=true**: failing to prove possession of the session key is insufficient.
- **expiredServiceTicketRejected=true**: a service ticket past `endtime` is rejected.
- **staleAuthenticatorRejected=true**: an authenticator outside the clock skew policy is rejected.
- **expiredTgtCannotIssueNewTicket=true**: an expired TGT is rejected by the TGS when requesting new tickets.
- **unknownServiceDeniedByKdc=true**: unregistered SPN in the mock KDC.
- **untrustedTgtRejectedByKdc=true**: an untrusted/unverified TGT cannot be used to request tickets.

This is **not Kerberos cryptography**, but a **state and relationship model**. `ConcurrentHashMap.newKeySet` only simulates a replay cache **inside a single JVM**, which is unsafe for multi-node GSS production. **Never implement a custom Kerberos replay cache in an HTTP controller**; use a supported Kerberos/JGSS acceptor and cache/token handling mechanism.

## 17. Handling Identity After Kerberos Verification

Once JGSS verifies the Kerberos token, the application receives a **client principal** such as:

~~~text
alice@EXAMPLE.TEST
~~~

This is an **identity authenticated by the Kerberos service provider**. It does not automatically grant permissions such as:

~~~text
ROLE_ADMIN
ROLE_FINANCE_APPROVER
TENANT_B_RESOURCE_OWNER
~~~

`KerberosServiceAuthenticationProvider` typically uses **UserDetailsService** to load authorities from LDAP/AD/local DB. Depending on the application, you must:

- Map principal + realm to a stable local user.
- Check that the user is enabled and not locked or deprovisioned per policy.
- Grant roles strictly from application-authorized data; never turn browser group strings/headers into `ROLE_ADMIN`.
- Never take only the username before `@` and merge `alice@REALM_A` with `alice@REALM_B`.
- Never treat holding a valid TGT or service ticket as sufficient to read confidential documents.
- Enforce tenant ownership/resource permissions in business APIs rather than relying on an authenticated flag alone.
- If user identity must be passed from a trusted gateway to a backend, use an assessed **trust-propagation model** with header-spoof protection; never blindly treat `X-Forwarded-User` as a verified Kerberos principal.

### 17.1. Protecting Inbound Auth Tokens

An HTTP client can craft and send:

~~~http
Authorization: Negotiate ZmFrZS10b2tlbg==
~~~

The Base64 string above is **fake data**, with no valid GSS context. The application must reject it through the provider/validator. **Never Base64-decode the header to extract a username yourself** or write raw tokens to logs.

### 17.2. Do Not Treat Kerberos Success as Generic MFA Proof

Kerberos proves the client holds a valid credential/session key per the KDC. Whether MFA/PKINIT/smartcard or step-up policy was used during the **AS exchange** depends on infrastructure and recognized authentication signals; not every SPNEGO AP-REQ automatically proves "MFA was just completed" at the time of the HTTP request.

APIs requiring strong authentication need policies combining identity assurance, step-up/freshness, and explicit session boundaries.

## 18. Kerberos Behind Load Balancers, Reverse Proxies, and Containers

### 18.1. Public SPN vs. Private Backend Host

~~~text
Browser -> https://portal.example.test
                  |
                  v
       Load Balancer / Ingress
           /       |        \
        App 1    App 2     App 3
~~~

The browser usually requests a service ticket for `HTTP/portal.example.test@EXAMPLE.TEST`, **not** `HTTP/app-1.internal@EXAMPLE.TEST`. You must align on:

- Which component actually acts as the GSS acceptor: ingress or each app?
- If the apps receive `Authorization: Negotiate` directly, instances must share the appropriate service credentials/keytab.
- If ingress terminates SPNEGO, the backend may trust only a **protected identity assertion** over mTLS/identity-aware proxy, never Internet-supplied headers.
- Session/replay security context must work properly across instances; never arbitrarily disable replay protection.
- If one instance has a newer keytab KVNO while another has an older one, 401 errors may appear intermittently per node.
- If channel binding / Extended Protection is required, both ends must coordinate with TLS termination; **never turn that protection off just to silence errors**.

### 18.2. Never Use a User Keytab as a Web Acceptor

A web service container may need a keytab for `HTTP/public-host`, not `kinit alice` or a user password in an init container. If the app also acts as a client calling another Kerberos service, that is a **separate initiator role**, which may require its own credential acquisition/delegation, distinct from the acceptor role.

## 19. Integration and Security Test Matrix

| Test Case | Condition | Expected Outcome |
| --- | --- | --- |
| Standard domain user | Client holds TGT, accesses Portal via trusted browser | Negotiate → service ticket → authenticated |
| No TGT yet | Empty credential cache and no SSO logon | Cannot auto-Kerberos; presents 401/fallback per policy |
| Valid TGT | Client requests tickets for Portal and Files | Separate service tickets issued per SPN |
| Expired TGT | Requesting a new ticket via TGS no longer valid | Fails/renews/re-runs AS exchange per KDC policy |
| Valid Portal service ticket | HTTP/portal ticket + valid authenticator | GSS accepts and local auth succeeds if user is permitted |
| Files service ticket sent to Portal | Ticket for cifs/files instead of HTTP/portal | Rejected |
| TGT sent to web as service ticket | TGT for krbtgt | Web acceptor does not authenticate |
| Authenticator replay | Replaying exact AP-REQ/authenticator | Rejected by replay protection |
| Same service ticket, fresh authenticator | Ticket unexpired, fresh auth | Can be accepted per Kerberos semantics |
| Expired ticket | `endtime` before now | Rejected |
| Time skew | Client/server drift exceeds limit | Rejected; fix NTP |
| Wrong keytab principal | Keytab contains only HTTP/internal | Rejected for public-host service ticket |
| KVNO mismatch | KDC has new key, app has old keytab | Fails; roll out matching keytab |
| Incompatible enctype | No key matching enctype | Fails; fix key/crypto policy |
| Unregistered SPN | `kvno HTTP/portal...` cannot issue ticket | TGS error; fix KDC/AD |
| Duplicate SPN in AD | One SPN bound to multiple accounts | Investigate/fix with domain admin |
| Browser sends NTLM only | Negotiate falls back to NTLM | Rejected if policy requires Kerberos |
| Fake Base64 header | Not a valid GSS token | 401/failure; no Authentication created |
| HTTP without TLS | Kerberos auth occurs, yet URL/body exposed | Security test FAIL / deployment gate |
| Header spoof | Client sends `X-Remote-User: admin` | Not treated as authenticated |
| Cross-realm user | `alice@REALM_B` via valid trust | Realm-scoped identity; not merged with alice@REALM_A |
| Local user disabled | Valid Kerberos ticket, yet DB locks user | No app access granted |
| User lacks role | GSS succeeds, yet resource requires role | 403, not confused with 401 |
| Local logout | Spring session cleared, OS TGT remains | Browser may re-SPNEGO; UI accurately reflects scope |
| Delegation disabled | Web app attempts downstream call as user | No automatic forwarded credentials |
| Unconstrained delegation | Service granted broad rights beyond use case | Security review FAIL |
| Keytab leak test | Keytab file is world-readable | Security policy FAIL |
| Multiple replicas | One node holds stale keytab after rotation | Per-instance 401 detected |
| Reverse proxy hostname | Public host differs from internal host | Public SPN and forwarded headers properly designed |
| Channel binding | TLS termination mismatches CBT requirement | Fail closed; investigate policy |
| Logging/tracing | Authorization Negotiate token appears in logs | Redact; never store GSS tokens |
| KDC unavailable | Cached TGT/ST exists, yet cannot request new tickets | Behavior distinguishes cache vs. new ticket without bypass |

**Every integration test must distinguish:** **client lacking a TGT** errors, **TGS refusing to issue ST** errors, **GSS acceptor failing to decrypt/verify ST** errors, and **application authorization** errors. Collapsing everything into a single "Invalid password" message makes investigation difficult and can lead to dangerous bypass configurations.

## 20. Troubleshooting by Error Code and Symptom

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| 401 without Negotiate header | SpnegoEntryPoint/filter chain misconfigured | Inspect SecurityFilterChain and response headers |
| 401 with Negotiate, yet browser sends no Authorization | Browser disallows integrated auth, no TGT, site not in intranet allowlist | Browser policy, OS credential cache, klist |
| Browser sends Negotiate, yet 401 repeats | Wrong SPN, keytab/kvno, GSS token/mechanism, policy | Debug auth error in app with token redacted |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | SPN does not exist or wrong realm/name | `kvno HTTP/portal...`, DNS/AD |
| `KRB_AP_ERR_MODIFIED` | Server cannot decrypt ticket: SPN/keys/kvno/account issue | KDC principal, keytab, AD duplicates |
| `KRB_AP_ERR_TKT_EXPIRED` | Service ticket expired | `klist`, time sync, KDC policies |
| `KRB_AP_ERR_SKEW` | Clock skew | NTP on client/KDC/service |
| `KRB_AP_ERR_REPEAT` | Authenticator replay | Check GSS replay cache/context; do not disable |
| `KRB_AP_ERR_NOKEY` | Acceptor lacks suitable key | `klist -k -t -e`, service principal |
| `KRB_AP_ERR_BADKEYVER` | Key version unsupported by server | KVNO rollout, service keytab |
| Encryption type unsupported | Client/KDC/service disagree on enctypes | KDC policy, Java crypto, keytab entries |
| `GSSException: No valid credentials provided` | Unreadable keytab, JAAS login error, missing acceptor credential | File path, permissions, servicePrincipal |
| `GSSException: Defective token` | Corrupted token/wrong mech, proxy altered header, invalid GSS context | Header flow, SPNEGO client/server versions |
| Channel binding mismatch | Incompatible TLS CBT/Extended Protection | TLS termination, Java/browser/AD policy |
| Unexpected NTLM fallback | Browser did not choose Kerberos / SPN failed to resolve | Mech selection, Windows policy |
| Service ticket present, yet app does not auth | Provider/validator/UserDetails error | KerberosServiceAuthenticationProvider, UserDetailsService |
| Login succeeds, yet HTTP 403 | Local role/resource authorization denied | Roles, user status, tenant policy |
| Only one replica fails | Stale keytab or unshared session/config | Per-node logs and deployment version |
| Only production fails | SPN/public host/TLS/trust differs from DEV | DNS, ingress, KDC realm, keytab |
| Logs out, then immediately logs back in automatically | OS TGT/service ticket still valid | Clarify local logout vs. domain sign-out |
| User disabled, yet old session still works | Stale local session/authorization cache | Session invalidation and policy refresh |
| Double-hop fails | Service lacks delegation permission/credentials | Constrained delegation, target SPN |
| Logs contain GSS token | Sensitive access log header captured | Redaction and incident management |

### 20.1. Recommended Step-by-Step Runbook

1. Identify the **public website URL**, realm, and expected service SPN.
2. Client: check the **TGT** in the credential cache using the appropriate OS tool.
3. Client: use `kvno HTTP/portal.example.test@EXAMPLE.TEST` (in an authorized environment) to verify TGS service ticket issuance.
4. Browser: inspect 401 `WWW-Authenticate: Negotiate` then `Authorization: Negotiate`, **without logging/posting raw tokens**.
5. Server: verify the JVM can read the keytab and check principal and KVNO/enctype with `klist -k -t -e`.
6. Check NTP/KDC/AD trust/cross-realm and callback hostname/canonicalization.
7. Check whether `KerberosServiceAuthenticationProvider` receives **KerberosServiceRequestToken** and maps UserDetails successfully.
8. Separate 401 authentication failure from 403 local authorization denial.
9. If login works on one node and fails on another, inspect keytab/version/session and GSS replay/cache topology.
10. Only after investigation, adjust configuration under review. **Never switch to trusting a username HTTP header or disabling crypto/replay to cure a 401.**

### 20.2. Appropriate Logging Scope

Safe to log per policy:

~~~text
event=KERBEROS_SPNEGO_AUTH_FAILED
servicePrincipal=HTTP/portal.example.test@EXAMPLE.TEST
reason=SPN_OR_KEYTAB_MISMATCH
node=portal-2
traceId=trace-7f4e
elapsedMs=121
~~~

Never log **raw `Authorization: Negotiate`**, GSS tokens, ticket caches, keytab bytes, passwords, decrypted ticket/session keys, or principals containing personal data without justification and safeguards.

## 21. Production Deployment Checklist

- [ ] Understood that TGT is for `krbtgt` and service ticket is for the application server's SPN.
- [ ] Reliable AS/TGS/KDC realm with proper trust policy and clock synchronization.
- [ ] Client credential cache holds TGT/keys; server keytab holds **service long-term keys**, not user TGTs.
- [ ] SPN `HTTP/public-fqdn@REALM` properly registered and owned by an approved service account.
- [ ] Browser configured for Integrated Auth on trusted sites only; no blanket "auto logon" on the Internet.
- [ ] HTTP `Negotiate` used over HTTPS; never treat a Negotiate-named header as proof of Kerberos.
- [ ] Per policy, prevent NTLM fallback when Kerberos is required; test actual mech and assurance.
- [ ] Spring Security uses `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, and `SunJaasKerberosTicketValidator` properly.
- [ ] Kerberos dependencies/versions align with Spring Security 6.x or 7.x; note Maven group change in 7.x.
- [ ] Service principal/keytab path/permissions/TLS proxy deployed properly, with no keytab committed.
- [ ] SPNEGO filter is not registered twice outside and inside the Spring Security chain.
- [ ] GSS validation checks service ticket, authenticator, time/replay, and service identity; no raw token parsing in controllers.
- [ ] Keytab KVNO/enctype match KDC/service account, with a rotation/cutover plan.
- [ ] Client TGT and ST lifetimes follow KDC policy; do not hardcode an assumption that all tickets are one-time.
- [ ] Replayed authenticators are rejected; never disable replay cache or skip clock skew checks.
- [ ] App does not accept a TGT as a login credential and does not require the krbtgt key.
- [ ] Local UserDetailsService checks user status and authorities; authentication differs from authorization.
- [ ] Local logout/HttpSession does not promise to clear the OS TGT or other service tickets.
- [ ] Cross-realm identities do not merge users with the same name across different realms.
- [ ] Delegation is enabled only for valid use cases, preferring constrained delegation; never forward user TGTs carelessly.
- [ ] DNS, CNAME, public FQDN, realm mapping, and trusted forward headers are tested.
- [ ] With LB/containers, service keytab and SPN are consistent across instances.
- [ ] HTTP CSRF, cookie/session security, and HTTPS remain enforced even when login uses Kerberos.
- [ ] GSS tokens, tickets, keytabs, passwords, and session keys are never written to logs/traces.
- [ ] Integration tests cover happy path, expired TGT, wrong SPN, wrong keytab/KVNO, NTLM fallback, replay, clock skew, disabled user, and 403.
- [ ] Runbooks exist for KDC outage, rotation, AD SPN ownership, and safe rollback.

## 22. Self-Check Questions

**1. Which component issues the TGT?**

Typically the KDC's **Authentication Service (AS)** during the AS exchange. It is intended for **TGS/krbtgt**, not for a website.

**2. How is a service ticket obtained?**

The client uses its **TGT along with an authenticator built using the client–TGS session key** in a **TGS-REQ** sent to the KDC/TGS to request a ticket for the target SPN.

**3. Does a web app need the `krbtgt` private key to authenticate users?**

No. The web acceptor uses the **service keytab** for `HTTP/public-host@REALM` to verify the **service ticket/AP-REQ**, not the krbtgt key.

**4. Can one TGT be used to obtain multiple service tickets?**

Yes, while valid and permitted by policy. One TGT can obtain tickets for Portal, Files, and other services.

**5. Can a service ticket for Files be used to log into Portal?**

No. Tickets are bound to a service principal. The app must verify the exact SPN.

**6. Can a Kerberos service ticket be reused?**

It can be used across multiple AP exchanges while unexpired and permitted by policy, **but each use requires a fresh authenticator and replay protection**. Never replay an exact previously used AP-REQ/authenticator.

**7. Why is a ticket alone insufficient to authenticate the client?**

Because it could be copied. The **Authenticator**, protected by the session key, proves possession and helps prevent replay.

**8. In Spring Security, which filter processes the TGT?**

A TGT belongs to the **client–KDC TGS exchange**, not a web filter. `SpnegoAuthenticationProcessingFilter` receives the **GSS/SPNEGO service token** from the HTTP header.

**9. Is `Authorization: Negotiate` always a raw service ticket?**

No. It is a **base64 GSS-API/SPNEGO token**, which can contain NegTokenInit/NegTokenResp and a Kerberos AP-REQ; it is not a raw service ticket string or username.

**10. Why might a successful Kerberos login still not let the user open financial reports?**

Kerberos proves identity; **local authorization** still checks user status, roles, tenant, and resource permissions.

**11. How do `kinit`, `klist`, and `kvno` differ?**

`kinit` acquires a TGT; `klist` inspects tickets in the credential cache (or a keytab with `-k`); `kvno` requests/displays a service ticket and key version number.

**12. Why does a keytab break after a domain admin changes the service account password?**

The KDC may issue tickets with a **new KVNO/key**, while the app's keytab still holds the old key. Service credentials must be synchronized and rolled over.

**13. Why does a user immediately re-enter the app without a password after a local Spring logout?**

Because the TGT/service ticket remains in the OS credential cache and the browser can perform SPNEGO again. Local HttpSession logout does not clear the domain credential cache.

**14. Does every HTTP request send the TGT to the KDC?**

No. TGTs/service tickets/GSS contexts and local app sessions can all be cached. The KDC usually does not participate in every HTTP request.

**15. If user Alice signs in from both REALM_A and REALM_B, should the app treat them as the same identity because the username matches?**

Not automatically. Principals must be scoped by **realm**, and business account linking requires separate policy/evidence.

**16. Why does SPNEGO not replace HTTPS?**

HTTP Negotiate authenticates client/service per the chosen mechanism, yet **does not protect the full HTTP URL, headers, cookies, and body**. TLS remains essential.

**17. Should unconstrained delegation be enabled to make downstream calls easier?**

No. Delegation broadens credential usage; scope it by target/role and prefer constrained delegation under KDC/AD governance.

**18. What is the biggest difference between a session key and a keytab?**

A **session key** is a temporary key tied to a ticket/exchange; a **keytab** stores the service principal's long-term key so the acceptor can decrypt/verify tickets for that service.

## 23. Standards and Official References

- IETF **RFC 4120 — The Kerberos Network Authentication Service (V5)**: AS exchange, TGS exchange, AP exchange, ticket, authenticator, service keys, flags, and replay: https://www.rfc-editor.org/rfc/rfc4120
- IETF **RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication**: `WWW-Authenticate: Negotiate`, `Authorization: Negotiate`, SPN `HTTP/hostname`, HTTP security considerations: https://www.rfc-editor.org/rfc/rfc4559
- IETF **RFC 4178 — SPNEGO**: negotiating GSS-API security mechanisms: https://www.rfc-editor.org/rfc/rfc4178
- IETF **RFC 4121 — Kerberos V5 GSS-API Mechanism**: GSS security contexts and tokens: https://www.rfc-editor.org/rfc/rfc4121
- Spring Security, **Introduction to Spring Security Kerberos**: module artifacts, dependency coordinate changes with Spring Security 7: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security, **Spring and Spring Security Kerberos**: `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, keytabs, and JavaConfig: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Spring Security Javadoc, **SpnegoAuthenticationProcessingFilter**: HTTP Negotiate header → KerberosServiceRequestToken/AuthenticationManager: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Spring Security Javadoc, **KerberosServiceAuthenticationProvider**: validating service tickets and loading UserDetails/authorities: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- MIT Kerberos, **kinit**: acquiring/caching TGTs and renew/forwardable options: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kinit.html
- MIT Kerberos, **klist**: inspecting credential caches, keytabs, ticket flags/enctypes: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html
- MIT Kerberos, **kvno**: requesting service tickets and viewing key version numbers: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html
- MIT Kerberos, **keytab**: service long-term keys, principal/KVNO/enctype: https://web.mit.edu/kerberos/krb5-latest/doc/basic/keytab_def.html

**Remember:** a **TGT** is issued by the KDC/AS for **`krbtgt`** so the client can request additional **service tickets** from the TGS; a **service ticket** is issued by the KDC/TGS for **the service's exact SPN**, such as `HTTP/portal.example.test@EXAMPLE.TEST`. For web apps, the browser sends a **GSS/SPNEGO AP-REQ** containing the service ticket and an **authenticator** via HTTP Negotiate; Spring Security Kerberos uses the **service keytab/JGSS** to verify it before mapping the principal to a local user and permissions. **TGTs do not go directly to the web app, service tickets do not replace business permissions, and authenticator replay must be blocked even before the ticket expires.**