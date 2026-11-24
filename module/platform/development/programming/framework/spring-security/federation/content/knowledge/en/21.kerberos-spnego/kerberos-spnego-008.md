# Distinguishing Kerberos SSO from LDAP Bind and Active Directory Password Login

**Kerberos SSO, LDAP bind, and Active Directory (AD) password login can all use the same enterprise identity system, yet they are not the same authentication mechanism.** In Kerberos SSO via **HTTP SPNEGO**, the browser/OS sends **proof in the form of a Kerberos service ticket** to the application; the application uses its **service principal and keytab** to verify the ticket, typically **without receiving the user's password**. In **LDAP simple bind** for form login authentication, the application **receives the username/password** and forwards those credentials over a **TLS-verified** LDAP connection to the directory to attempt a bind. "Logging in with an AD password" describes only **the credential source and type**, not the protocol: it may verify via LDAP bind, via a Kerberos AS exchange, or via a federated system like OIDC/SAML.

**Important exception to remember:** LDAP also supports **SASL**, where **SASL/GSSAPI uses Kerberos** to authenticate to the LDAP server. Thus saying "LDAP always sends passwords and Kerberos never goes with LDAP" is false. You must determine which mechanism the **browser→app HTTP path** and the **app/client→directory path** each use, who sees the password, who verifies the ticket, and where the application obtains permissions.

This lesson belongs to **Spring Security – federation → Kerberos and SPNEGO**, explaining how to distinguish these at the protocol level, trust boundaries, integration options with Spring Security/Spring LDAP/Active Directory, hybrid models, LDAPS and Kerberos security, a runnable Java 17 example, a test matrix, and an enterprise runbook.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why Kerberos SSO normally does not re-prompt for a password on web applications.
2. Accurately describe the roles of **TGT**, **service ticket**, **KDC**, **SPN**, **keytab**, **SPNEGO**, and **HTTP Negotiate**.
3. Explain **LDAP simple bind** with username/password, as distinct from **LDAP SASL/GSSAPI bind**.
4. Recognize that **logging in with an AD password** does not automatically mean SSO.
5. Distinguish **identity authentication** from **group/department lookup**, **local account provisioning**, and **application authorization**.
6. Choose the right Spring Security provider for each flow without mixing password providers with ticket validators.
7. Protect simple binds with TLS, prevent password leaks, and understand LDAP signing/channel binding by mechanism.
8. Understand Kerberos SSO prerequisites (realm, trust, SPN, clocks, keytab, browser policy).
9. Write integration tests proving **the intended mechanism is actually used**, rather than merely checking HTTP 200.
10. Design a migration path from AD password login to SSO without inadvertently introducing a weaker fallback mechanism.

## 2. Three Terms, Three Layers of Meaning

| Phrase | Nature | Proof Sent to App / Server | Does Web App See Password? |
| --- | --- | --- | --- |
| **Kerberos SSO via SPNEGO/HTTP Negotiate** | Login using a ticket already issued by OS/KDC | SPNEGO token containing/representing Kerberos AP-REQ for the HTTP service | Normally **no** |
| **LDAP simple bind** | Attempts authentication against LDAP directory with bind identity and password | DN/UPN and password sent to directory over LDAP | **Yes** if form login goes to app |
| **AD password login** | Business label: user supplies an AD account password | Depends on implementation: LDAP bind, password-based Kerberos AS, OIDC/SAML redirect... | Depends on implementation; direct form usually **yes** |
| **LDAP SASL/GSSAPI bind** | LDAP authentication using Kerberos via SASL | GSSAPI/Kerberos exchange for the LDAP service | Not necessarily; can use tickets |
| **OIDC/SAML federation with AD as identity source** | App receives token/assertion from IdP/OP | ID Token or SAML Assertion | Often **no** if redirecting to IdP |

**Rule:** "We use AD" is not an answer to a security question. You must know **what the frontend sends**, **how the backend verifies it**, **where the password travels**, and **where sessions and permissions are governed**.

## 3. Side-by-Side Comparison Diagrams

**Kerberos SSO via HTTP SPNEGO:**

~~~text
Windows/Linux user session
         |
         | User already has TGT from KDC after desktop sign-in
         v
Browser -> GET /secure       -> Spring SPNEGO service
Browser <- 401 Negotiate     <- Spring SPNEGO service
         |
         | OS acquires service ticket for HTTP/portal.example.test
         v
Browser -> Authorization: Negotiate ... -> Spring service
                                             |
                                       JAAS/GSS accept context
                                       SPN + service keytab
                                             |
                                       Kerberos principal verified
                                             |
                                       Local account and roles
~~~

**LDAP simple bind from a login form:**

~~~text
Browser -- HTTPS POST username/password --> Spring login endpoint
                                                |
                                         LDAP authentication provider
                                                |
                                  TLS LDAPS/STARTTLS to AD/LDAP server
                                                |
                                  Simple bind as user + password
                                                |
                                        Bind success/failure
                                                |
                                      Local account/roles
~~~

**LDAP SASL/GSSAPI from an LDAP client holding Kerberos credentials:**

~~~text
LDAP client / application with Kerberos credentials
                         |
                 SASL GSSAPI bind to ldap/host SPN
                         |
                    Directory Server
                         |
             Authentication via Kerberos context
                         |
                   LDAP operations as authorized
~~~

**Look at the diagrams:** HTTP SPNEGO authenticates **web requests at the HTTP service**; LDAP SASL/GSSAPI authenticates **an LDAP session at the directory**. Both use Kerberos, yet **they differ in service principal, protocol path, and trust boundary**.

## 4. Kerberos: Roles of KDC, Realm, and Service Principal

Kerberos V5 uses a **Key Distribution Center (KDC)** to issue tickets within a realm. In an AD environment, Domain Controllers typically provide both KDC and LDAP services. Key components:

- **Client principal:** user identity, e.g. `alice@CORP.EXAMPLE.TEST`.
- **Realm:** Kerberos namespace, e.g. `CORP.EXAMPLE.TEST`.
- **TGT (Ticket-Granting Ticket):** used to request service tickets without sending the user's password to every application.
- **TGS (Ticket-Granting Service):** KDC component issuing tickets for target services.
- **Service principal name (SPN):** e.g. `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST`.
- **Service ticket:** proof for a client to access a specific service.
- **Acceptor secret/keytab:** used by the service to decrypt/verify tickets (usually via JAAS/GSS).
- **Authenticator/replay protection:** proves freshness; handles clock skew and replay per Kerberos policy.
- **Cross-realm trust/referral:** required when client and service reside in different realms.

**Do not conflate:** the same `sub`/username across two realms does not automatically identify the same user; a ticket for the HTTP portal is not automatically accepted by the LDAP directory or another HTTP service.

## 5. HTTP SPNEGO: The Exact Sequence

1. The user has signed in to the OS or holds a credential cache with a valid TGT.
2. The browser accesses a protected endpoint.
3. The server demands authentication with `401 WWW-Authenticate: Negotiate`.
4. The browser/OS invokes GSSAPI/SSPI, normally looking up a ticket for `HTTP/hostname`.
5. If no service ticket is cached yet, the OS sends a TGS request to the KDC to obtain one.
6. The browser sends `Authorization: Negotiate <base64-token>`.
7. The service uses its Kerberos acceptor credentials (usually a service keytab) to accept the GSS context.
8. The service verifies the ticket/Authenticator, SPN, lifetime, replay, and protocol conditions.
9. Spring Security creates an `Authentication` for the verified Kerberos principal.
10. The application maps the principal to a local account/groups/roles and checks the requested resource.
11. The browser may receive a session cookie after login; subsequent HTTP requests follow the app's session strategy.

**Note:** `Negotiate` is a negotiation scheme; **NTLM fallback** can occur in some Windows environments. **Seeing a `Negotiate` header or a 200 response alone does not prove Kerberos was used**. Check the negotiated mechanism and service principal ticket in testing.

## 6. Why Is This Called Single Sign-On?

The user **does not re-enter their password in every application** because the OS/Kerberos credential cache holds a TGT; the browser can obtain new service tickets for matching SPNs from the KDC. One desktop authentication can support access to many Kerberos-enabled services within the configured trust scope.

This **does not mean**:
- The user never has to log into the OS.
- TGTs/service tickets never expire.
- Every browser performs SPNEGO automatically; browser policy and device must support it.
- Users outside domain/realm trust always get SSO.
- Kerberos needs only a hostname without proper SPN/keytab/clocks.
- Kerberos authentication automatically grants `ROLE_ADMIN` in Spring.
- Logging out of one app revokes all TGTs and Kerberos credentials across devices.
- Kerberos desktop SSO equals OIDC/SAML SSO for Internet browsers.

**SSO is the experience of not re-entering a password within a trust environment**, not unconditional access.

## 7. What Is LDAP and Why Can It Be Used for Authentication?

**LDAP (Lightweight Directory Access Protocol)** is a protocol for accessing directory services. It supports:
- Binding/authenticating to the directory.
- Searching user objects and attributes.
- Reading memberships and organizational information (within ACLs).
- Other operations such as compare, add, modify, and delete when permitted.

**Active Directory Domain Services** can provide both an LDAP directory and a Kerberos KDC simultaneously. Those two endpoints **do not share the same protocol**.

An application using LDAP may:
1. Search for the user's Distinguished Name (DN) using a least-privilege service bind identity.
2. Attempt to bind as the user using the password the user just entered.
3. If the bind succeeds, treat the password as verified by the directory.
4. Retrieve attributes/groups and map them to app authorities.

**Key insight from Spring Security:** LDAP bind authentication does not read the password back from the directory to compare inside the app; **the directory verifies the password itself during bind**. Therefore, configuring LDAP bind is not simply a `UserDetailsService` fetching a password hash for local comparison.

## 8. LDAP Simple Bind: How Identity and Password Are Sent

LDAP simple bind can use:
- **DN:** `CN=Alice Nguyen,OU=People,DC=corp,DC=example,DC=test`.
- **AD UPN format:** `alice@corp.example.test` when supported by the DC/AD setup.
- Other name forms depending on directory implementation.

The essence of simple bind: **the directory receives the bind identity and password** and replies with success/failure. LDAP simple bind itself **provides no password encryption at the LDAP layer**, so it must be protected by **TLS** to prevent credential exposure on the network.

~~~text
POST https://portal.example.test/login
  username = alice@corp.example.test
  password = ********
       |
       v
Spring AuthenticationManager
       |
       v
LdapAuthenticationProvider / AD-specific provider
       |
       v
LDAPS 636 / STARTTLS 389 with verified TLS certificate
       |
       v
LDAP bind as Alice using provided password
       |
       +--- Success -> verified password, map attributes/roles
       |
       +--- Failure -> bad credentials / account policy / LDAP error
~~~

**Places the password may pass through:** browser form, reverse proxy/WAF (if misconfigured to log bodies), app memory, Authentication request, LDAP client library, and directory. Never log, metric, or trace raw passwords.

## 9. Is Active Directory Password Login Always LDAP Bind?

**Not necessarily.** Saying "the app checks AD passwords" can describe any of several architectures:

| Deployment Type | Who Receives the Password? | Verification Path |
| --- | --- | --- |
| App with form login using LDAP bind | Browser → app → AD LDAP | Directory verifies password via bind |
| App with form login using Kerberos password provider | Browser → app → Kerberos KDC | KDC/AS exchange from credentials; not HTTP SPNEGO SSO |
| App redirects to corporate OIDC/SAML IdP | Browser → IdP (if entered) | App receives token/assertion, usually never sees password |
| OS-integrated Kerberos HTTP SPNEGO | OS/browser does not post password to app | Service verifies Kerberos ticket |
| Legacy custom AD integration | Depends on implementation | Must inspect actual code rather than guessing |

A team might call every method "AD login" because AD manages the accounts. **UX/marketing names do not reveal password exposure or cryptographic trust**. You must inspect the actual request path and `AuthenticationProvider`.

## 10. LDAP Bind Is Not Automatically SSO

If a user must type their password into a form at each Spring application, even if every app verifies against **the same AD**, that is still **re-entering a password**. Individual session cookies keep the user signed in within each app after login, yet **do not constitute cross-app Kerberos SSO**.

**To achieve true web SSO**, you can use:
- HTTP SPNEGO/Kerberos with desktop credential caches and realm trust.
- Redirects to a central IdP using **OIDC or SAML**, where apps never hold passwords.
- A carefully architected SSO gateway passing verified identity across a protocol/trust boundary.

**LDAP is a directory protocol**; it typically serves identity lookups and group attributes **alongside** Kerberos/OIDC/SAML rather than providing browser SSO simply by connecting to the same AD.

## 11. LDAP SASL/GSSAPI: An Important Exception

LDAP supports both **simple bind** and **SASL bind**. With **SASL/GSSAPI**, the LDAP client and server can use Kerberos credentials/tickets to establish an authenticated LDAP session.

~~~text
LDAP client (with Kerberos credentials/TGT)
    |
    | SASL mechanism GSSAPI
    v
LDAP server service principal (ldap/dc.example.test)
    |
    | Validate Kerberos context
    v
Authenticated LDAP session
    |
    +--> Search/group lookup per security context permissions
~~~

In some cases the client is the web app authenticating to the directory under its service identity; in others it uses controlled delegated user credentials. **Never infer that an app using LDAP SASL/GSSAPI means the browser logged into Spring via Kerberos**. Check **who the Kerberos initiator is**, which principal binds to LDAP, and whether delegation occurred.

**NTLM SASL** can also exist in AD, yet must never be equated with Kerberos GSSAPI. Under modern policies, avoid relying on relay-prone NTLM and require appropriate signing/channel binding. <https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing>

## 12. LDAP Bind vs. LDAP Search: Two Distinct Tasks

An LDAP integration may:
- **Bind to authenticate** a user's username/password.
- **Bind with a (read-only) service account** to search user/group attributes.
- **SASL bind** with a Kerberos identity to search LDAP.
- **Bind with user credentials** and read attributes within the user's permissions.

If an app only **finds a user via search** using a service account, that **does not prove the user is authenticated**. Conversely, Kerberos SPNEGO can authenticate the user while still needing a **directory search** to retrieve groups, manager, or business attributes.

~~~text
Kerberos SPNEGO verified principal
             |
             v
Search AD via protected LDAP with service credentials
             |
             v
Resolve directory object and memberOf/group memberships
             |
             v
Map approved groups -> app GrantedAuthority
~~~

Never use `displayName` or email from a bind/search result as the primary identity key. In AD, use `objectGUID` or a stable directory identifier in an IAM-approved link, combined with the source namespace/realm. Account linking needs explicit policy; display names and UPNs can change.

## 13. Deep Comparison Table: Kerberos SPNEGO vs. LDAP Simple Bind

| Criterion | Kerberos HTTP SSO / SPNEGO | LDAP Simple Bind with AD Form |
| --- | --- | --- |
| Sent by browser to app | Negotiate token / service ticket | Username + password |
| App receives user's password | Normally no | Yes |
| Verified by backend | Keytab/GSS acceptor, Kerberos AP exchange | Directory LDAP bind success/failure |
| Identity source | Kerberos realm/KDC, principal | Directory bind identity + attributes |
| Requires SPN for HTTP service | Yes | Not mandatory |
| Requires HTTP service keytab | Usually yes, or equivalent managed credential | No, for LDAP simple bind alone |
| Requires directory connection on every login | Not necessarily for Kerberos AP verification; may need group lookup | Usually yes during bind |
| Requires KDC | Yes to issue tickets (tickets may be cached) | No separate Kerberos needed for simple bind |
| Works on off-domain devices | More complex; depends on trust/client config | Yes if app and LDAPS are reachable |
| Password exposure at app | Lower when SSO is configured properly | Higher since app handles passwords |
| Clock skew / SPN / KVNO | Critical | Not applicable to simple bind itself |
| LDAP TLS / cert | Not required for AP verification; required if app performs LDAP lookup | **Mandatory on the secret-carrying transport** |
| Spring groups/roles | Still must be mapped | Still must be mapped |
| Primary risks | Ticket misuse, SPN/keytab, fallback, relay/delegation, replay | Password exposure, insecure LDAP, brute force, credential stuffing |
| Typical failures | 401 Negotiate loop, GSSException, KRB_AP_ERR_SKEW/MODIFIED | LDAP invalidCredentials (49 AD), TLS/LDAP errors |
| Session logout | Does not auto-purge OS TGT | Does not change password or end other apps' sessions |

**Do not rank "one side as always unconditionally safer"**: Kerberos depends on SPN/keytab governance and browser/OS posture; LDAP password login can be hardened with TLS/MFA/rate limits and clear policy. For seamless corporate login, Kerberos SPNEGO prevents the app from **re-collecting user passwords**, which is a clear security advantage when properly deployed.

## 14. Spring Security: Which Modules Serve Each Branch?

**Kerberos HTTP SPNEGO** in Spring typically uses the **Spring Security Kerberos extension**, which is not auto-enabled by `spring-boot-starter-security` alone:

- `SpnegoAuthenticationProcessingFilter`: reads the `Authorization: Negotiate` header.
- `SpnegoEntryPoint`: issues the `WWW-Authenticate: Negotiate` challenge.
- `KerberosServiceAuthenticationProvider`: validates tokens/service tickets via a ticket validator.
- `SunJaasKerberosTicketValidator`: configures service principal + keytab for JAAS/GSS verification.
- `UserDetailsService` or domain mapping: loads local account and authorities.

**LDAP/AD password login** typically uses:
- `spring-security-ldap` dependency.
- `LdapAuthenticationProvider` + `BindAuthenticator` or AD-specific `ActiveDirectoryLdapAuthenticationProvider`.
- `AuthenticationManager`/form login to read user credentials.
- `LdapAuthoritiesPopulator` or approved mapping to retrieve groups and authorities.

**Shared:** SecurityFilterChain, Authentication, SecurityContext, session management, auditing, and method/resource authorization.

**Different:** **Kerberos ticket validation** is not `BindAuthenticator`; **LDAP bind** is not `SpnegoAuthenticationProcessingFilter`.

## 15. How Does ActiveDirectoryLdapAuthenticationProvider Authenticate?

Spring Security LDAP provides an Active Directory–specific provider: `ActiveDirectoryLdapAuthenticationProvider`. When a user submits a username/password, the provider interacts with LDAP/AD to verify credentials and can then extract attributes/roles per configuration. It **does not perform HTTP SPNEGO** and **does not issue a Kerberos ticket to the browser**.

Example Java fragment for Spring Boot 3 / Spring Security 6.x or compatible release:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider;

@Configuration
class ActiveDirectoryPasswordLoginConfig {

    @Bean
    ActiveDirectoryLdapAuthenticationProvider activeDirectoryProvider() {
        ActiveDirectoryLdapAuthenticationProvider provider =
                new ActiveDirectoryLdapAuthenticationProvider(
                    "corp.example.test",
                    "ldaps://dc1.corp.example.test:636/"
                );
        provider.setConvertSubErrorCodesToExceptions(true);
        return provider;
    }
}
~~~

**This is a project-level fragment**: it requires `spring-security-ldap`, a TLS truststore with the AD DC's CA, network connectivity, SecurityFilterChain/form login, and proper authorities mapping. **It does not run directly with plain javac/JDK**.

**Never use** `ldap://...:389` with simple bind without STARTTLS. If the LDAP server rejects an invalid TLS certificate, fix the truststore/hostname/certificate chain—**never disable hostname verification** or install a trust-all SSL context.

**Note:** AD `data 52e/775/532/533` sub-error codes help classify failures internally, yet never expose all details to the browser so you avoid username enumeration and policy leakage.

## 16. Spring Security LDAP: Bind Authenticator vs. Password Comparison

For general LDAP, two distinct strategies exist:

**Bind authentication:**
- The app reads the user's username/password from the Authentication request.
- Resolves the user DN or uses a directory-accepted name form.
- Attempts to bind using that exact password.
- The directory decides accept/reject.
- No need (and bad practice) to fetch the user's password hash to the app.

**Password comparison authentication:**
- Uses an LDAP compare operation against the password attribute per directory contract.
- Not every AD deployment provides suitable semantics for this approach.
- Never assume you can read AD's `unicodePwd`/password hash for local comparison.

Spring docs confirm `LdapAuthenticationProvider` accepts `LdapAuthenticator` implementations such as `BindAuthenticator` and `PasswordComparisonAuthenticator`. For AD password form login, **use an AD-appropriate provider** or `BindAuthenticator` matching the real schema; never pull password hashes out of LDAP to compare in Java.

## 17. Example Spring BindAuthenticator for a Non-AD-Specific Directory

Illustrative fragment (imports and bean context must match your Spring LDAP version):

~~~java
// Code fragment inside Spring @Configuration, not standalone runnable.
DefaultSpringSecurityContextSource contextSource =
    new DefaultSpringSecurityContextSource(
        "ldaps://directory.example.test:636/dc=example,dc=test");

BindAuthenticator bindAuthenticator =
    new BindAuthenticator(contextSource);

bindAuthenticator.setUserDnPatterns(
    new String[] { "uid={0},ou=people" });

LdapAuthenticationProvider provider =
    new LdapAuthenticationProvider(bindAuthenticator);
~~~

**Limitations:** DN patterns fit only known directory schemas; in AD, UPNs are often more convenient and users can span multiple OUs. If DN search is needed, constrain search base/scope and object classes, escape inputs, use a read-only service bind account, and prevent LDAP filter injection.

**This is not a substitute for Kerberos web SSO**, and still requires TLS and password-handling controls.

## 18. Spring Kerberos Extension: Service Ticket Validator Portion

Typical Java fragment in a Spring application:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
class KerberosSsoConfig {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST");
        validator.setKeyTabLocation(
                new FileSystemResource("/run/secrets/portal.keytab"));
        validator.setDebug(false);
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
}
~~~

**Important:** this fragment requires the Spring Security Kerberos extension plus `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, AuthenticationManager/SecurityFilterChain, and a proper fallback policy. **Creating these beans alone does not automatically assemble a complete SSO application**.

**Configuration values must belong to a real trust environment:** HTTP SPN matching the browser URL, service account, realm, KDC trust, keytab permissions, and supported enctypes. Never store keytabs in Git or public container images.

## 19. Is Password-Based KerberosAuthenticationProvider SSO?

The Kerberos extension includes both APIs for Kerberos authentication from **username/password** (e.g., `KerberosAuthenticationProvider` with `KerberosClient`) and APIs for **service tickets** from SPNEGO (`KerberosServiceAuthenticationProvider`).

Distinguish them:

| Component / Flow | Primary User Input | App Sees Password? | Nature |
| --- | --- | --- | --- |
| KerberosAuthenticationProvider with form credentials | Username/password | **Yes** | App verifies credentials against KDC; not seamless SPNEGO SSO |
| KerberosServiceAuthenticationProvider from HTTP Negotiate | Kerberos service ticket token | Normally **no** | Kerberos HTTP SSO |
| ActiveDirectoryLdapAuthenticationProvider | Username/password | **Yes** | LDAP/AD bind password login |
| LDAP SASL/GSSAPI bind | Kerberos SASL tokens | Depends on credential acquisition, not necessarily | Directory session authentication |
| OIDC/SAML login with AD-backed IdP | Redirect/callback token/assertion | Often no | IdP-driven federation SSO |

**"Authenticating with Kerberos" does not automatically mean "the browser sends no password".** Inspect the exact component and flow.

## 20. Secure LDAP: LDAPS, STARTTLS, and TLS Verification

**Simple bind is safe only when the transport is properly protected**. Two common models:
- **LDAPS:** TLS immediately upon opening the connection, typically port 636.
- **LDAP + STARTTLS:** plain connection on port 389 followed by **upgrading to TLS before binding**.

Practical protections required:
1. Valid CA/truststore and valid certificate chain.
2. Hostname/DC name matches the certificate; never use trust-all.
3. Compliant TLS versions/ciphers per policy.
4. Never downgrade to plaintext LDAP if TLS fails.
5. App–DC connectivity restricted by network/egress controls.
6. Never log passwords in gateways, proxies, app logs, or APM.
7. Timeouts and rate limits to prevent connection exhaustion.
8. Account lockout and brute-force detection aligned with AD policies.
9. Managed DNS/DC failover so the app never connects to the wrong domain.
10. Secret lifecycle management for the search-bind service identity.

**LDAP signing does not replace TLS for simple binds**. Microsoft explains that LDAP signing applies to non-TLS SASL sessions, whereas simple bind must use TLS to protect credentials. See: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing

## 21. LDAP Signing and Channel Binding: Do Not Equate Them

Concepts:

| Control | Protection | Primary Scope |
| --- | --- | --- |
| **TLS (LDAPS/STARTTLS)** | Traffic confidentiality and integrity, PKI server verification | Simple bind and SASL over TLS |
| **LDAP signing** | Integrity/authenticity of LDAP messages (does not encrypt data itself) | Non-TLS SASL binds |
| **SASL sealing** | Confidentiality + integrity at the SASL layer | Non-TLS SASL when mechanism supports it |
| **LDAP Channel Binding Token (CBT)** | Binds SASL authentication to the TLS channel | **TLS + SASL** per AD policy |
| **Kerberos service binding** | Proof bound to service principal and trust/keys | Kerberos authentication/GSS |
| **HTTP TLS** | Protects browser↔app and cookies | Both SPNEGO and form login |

**Never claim "enabling LDAP signing makes password simple bind safe on port 389 without TLS".** Simple bind does not receive SASL-style signing. For LDAP over TLS using SASL/GSSAPI, AD channel-binding policy may require CBT; **CBT does not apply to simple bind** according to Microsoft.

Defaults vary by Windows Server version and policy. **Never guess what an AD DC enforces solely from OS version**; verify actual configuration and audit events. https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding

## 22. When to Use AD Passwords vs. When to Prefer SSO?

| Situation | Appropriate Choice | Key Considerations |
| --- | --- | --- |
| Intranet portal, domain-joined Windows, managed browsers | HTTP SPNEGO/Kerberos | SPN/keytab, realm trust, browser policy, NTLM fallback |
| Multi-device SaaS, mobile, external network | OIDC/SAML with corporate IdP | IdP policy/MFA, issuer/audience, tenant mapping |
| Legacy app supporting only username/password | AD/LDAP bind over TLS, modernization plan | Password handling, phishing, lockout, TLS, MFA |
| Machine process reading directory | LDAP SASL/GSSAPI with service principal or protected service bind | Credential management, least privilege |
| App only needs group/profile data after SPNEGO | LDAP search via protected service credential | Never re-prompt for user password |
| Hybrid app supporting both patterns | SPNEGO for managed clients, IdP redirect or policy-approved password flow | Downgrade/fallback, assurance, session collision |
| Users outside realm trust | IdP federation is the common choice | Never widen Kerberos trust / accept-any-realm arbitrarily |

**Do not treat AD passwords as the end goal** when the app requires phishing resistance/MFA, federation, device posture, or session-scoped internal permissions. Often an OIDC/SAML IdP fronting AD/Kerberos gives a better SSO experience across heterogeneous browsers.

## 23. Designing Hybrid Auth Without Creating Fallback Holes

An app might expose:
- `/login/kerberos` or protected intranet path using HTTP Negotiate.
- `/oauth2/authorization/corp` for OIDC redirect.
- `/login/password` only if business/policy still requires an AD form.
- `/api/**` accepting only OAuth2 access tokens with the right audience.

**Conditions:**
1. Never let a failed Kerberos ticket validation **silently** treat an `X-User` header as authenticated.
2. Never let a user "pick password fallback" to bypass **MFA/assurance/conditional access** required on another route.
3. Define permitted methods per user/tenant/action, not merely via UI choices.
4. Sessions must record authentication method and assurance without auto-elevating privileges.
5. If a principal is already logged in via one method, switching methods must guard against session fixation and identity changes.
6. Keep independent audit categories per provider: Kerberos, AD LDAP, OIDC/SAML.
7. Group mapping/authorization must not depend on whether the credential was a ticket or a password.
8. Maintain account-disable/revocation strategies for local sessions and API tokens.
9. Login errors must not leak user existence or password state details to attackers.
10. Test browser logout followed by automatic Kerberos re-login: that may be **expected SSO behavior**, not a broken session logout.

**A multi-provider system must define precedence and fallback policy explicitly.** Never register a permissive authentication provider that approves requests rejected by a stronger provider.

## 24. AD Account State, Lockout, and Password Changes

**LDAP simple bind** can fail due to:
- Wrong password.
- Nonexistent user or wrong bind DN/UPN.
- Disabled/locked/expired account.
- User must change password or password expired.
- AD DC/LDAP policy or TLS/certificate failure.
- Network/DC outage, or broken anonymous/search service credentials.

**Kerberos SSO** can fail due to:
- Missing TGT/service ticket.
- Wrong client realm/KDC or cross-realm trust.
- HTTP SPN registered on the wrong account.
- Keytab has wrong principal/KVNO/enctype/key material.
- Clock drift among client/KDC/service.
- Expired ticket, replay, or crypto policy mismatch.
- Browser omits Negotiate token due to allowlist/zone/policy.
- Reverse proxy strips Authorization header.

**Never confuse LDAP password bind responses with Kerberos AP-REQ errors**. Disabling an AD account can behave differently when **tickets/sessions were already issued prior to disablement**; applications require session/token revocation and active-account checks per SLA.

## 25. Impact When an AD Password Changes

When a user changes their password:
- A **new LDAP form bind** using the old password will typically be rejected per DC/account replication policy.
- A previously issued **Kerberos TGT** may stay valid until expiry/revocation logic takes effect; existing app sessions may also persist.
- Changing a **service account** password can cause **keytab/KVNO mismatches** and break SPNEGO even when no user password changed.
- Caching a user's password in the app to re-bind automatically is an **anti-pattern**; never store reusable user passwords in databases/sessions.
- If the business requires immediate sign-out upon password reset/disable, implement **explicit session revocation / authorization state checks** rather than expecting a password change to wipe all tickets.

**Three distinct credentials:** user password, user TGT/service tickets, and service keytab. Rotation/revocation of each has its own scope and timing.

## 26. LDAP Filter Injection When Searching Before Bind

Some apps use a service account bind to search for a DN by username and then bind with the user's password. If you concatenate an LDAP filter manually:

~~~java
// Illustrative anti-pattern: never use in production.
String filter = "(uid=" + rawUsernameFromRequest + ")";
~~~

An attacker can inject characters like `*`, `(`, `)`, `\`, or NULL to alter the filter depending on the LDAP API. Use Spring LDAP's escaping/parameterized filter APIs, restrict the base DN/search scope and object classes, and never let clients choose arbitrary LDAP URLs.

**Do not equate LDAP injection with SQL injection**; LDAP filter escaping follows its own rules under RFC 4515.

**Do not let search-first cause user confusion:** if a filter returns multiple accounts, abort instead of binding to the wrong one; verify exact directory identity and source tenant. If no search is needed because AD supports binding by UPN, avoid unnecessary complex queries.

## 27. LDAP Group Retrieval and Granted Authorities

An application needs authorization:

~~~text
AD user verified:
  alice@corp.example.test

Directory groups:
  CN=Finance_Readers,OU=Groups,...
  CN=Shared_Service,OU=Groups,...

App-owned policy:
  (AD source, Finance_Readers, tenant=north)
      -> ROLE_INVOICE_VIEWER

Unknown group:
  CN=Global_Admins,OU=Groups,...
      -> No automatic app admin
~~~

For Kerberos SSO, the app can use an LDAP lookup to retrieve groups **after authenticating the principal**. For LDAP password bind, the provider can use an LDAP authorities populator. **Both still require a controlled mapping policy**.

Notes:
- `memberOf` may not capture all nested or primary group semantics in AD.
- Group `displayName` or opaque IDs do not confer cross-tenant access.
- An authenticated user still needs an active local account, tenant membership, and object-level authorization.
- Authorities cached in Spring's `SecurityContext` can go stale after group removal.
- Never blindly map any group named like `ROLE_ADMIN` to system-wide admin rights.
- Never link directory identities across different domains/realms by email alone.

## 28. Passwords vs. Kerberos Tickets: Risk Boundaries

**If the app receives user passwords from an AD form:**
- Passwords can leak if the app/server/proxy, access logs, APM, heap dumps, or TLS termination are compromised.
- The app becomes a collector of reusable credentials usable across systems if AD passwords are reused.
- You must defend against brute force, credential stuffing, login enumeration, CSRF/session fixation, and enforce MFA policy.
- Never log passwords, send passwords over plaintext HTTP, or retain them after login.

**If the app accepts only Kerberos SPNEGO tickets:**
- The app never needs a plaintext reusable user password.
- The service keytab is a high-value secret: protect, rotate, and restrict its permissions.
- Ticket/AP-REQ replay, SPN substitution, credential delegation/forwarding, clock skew, and NTLM fallback must be controlled.
- Never allow arbitrary service principals or keytab fallbacks; verify the GSS acceptor.
- TLS is still needed to protect HTTP/sessions/responses and prevent multiple attack classes.
- App logout does not clear OS Kerberos credentials by default.

**Never call a mechanism "completely passwordless"** merely because the web application receives no password: the user may have signed into the OS with a password or smart card to get a TGT.

## 29. Standalone Java 17 Demo: Authentication Evidence Model

The program below **does not talk to AD/KDC/LDAP and does not verify real Kerberos tickets or passwords**. It illustrates **decisions based on evidence already verified by trusted providers**, clarifying three kinds of evidence:

- Web SPNEGO requires a **real HTTP service ticket accepted by GSS** matching the right SPN.
- Form LDAP simple bind requires **verified TLS to the directory**, the app receiving user credentials, and **a successful bind**.
- LDAP SASL/GSSAPI authenticates **an LDAP session**; it **does not prove the browser completed HTTP SPNEGO**.

**Booleans in this demo are simulated by a test harness**; never take them from request headers to build Authentication in production.

Create file **KerberosVsLdapLoginDemo.java**:

~~~java
import java.util.Set;

public class KerberosVsLdapLoginDemo {

    enum Mechanism {
        HTTP_SPNEGO, LDAP_PASSWORD_BIND, LDAP_SASL_GSSAPI
    }

    record Evidence(
        Mechanism mechanism,
        String identity,
        boolean serviceTicketVerified,
        boolean httpServicePrincipalMatched,
        boolean appReceivedPassword,
        boolean tlsVerified,
        boolean ldapBindSucceeded,
        boolean accountActive,
        boolean tenantAllowed) {}

    static final String TRUSTED_SPN =
        "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST";

    static final Set<String> APPROVED_IDENTITIES = Set.of(
        "alice@CORP.EXAMPLE.TEST",
        "bob@CORP.EXAMPLE.TEST"
    );

    static String decide(Evidence e) {
        if (!APPROVED_IDENTITIES.contains(e.identity())) {
            return "DENY_UNMAPPED_IDENTITY";
        }

        switch (e.mechanism()) {
            case HTTP_SPNEGO -> {
                if (e.appReceivedPassword()) {
                    return "DENY_UNEXPECTED_PASSWORD";
                }
                if (!e.serviceTicketVerified()) {
                    return "DENY_NO_VALID_HTTP_TICKET";
                }
                if (!e.httpServicePrincipalMatched()) {
                    return "DENY_WRONG_SERVICE_PRINCIPAL";
                }
            }
            case LDAP_PASSWORD_BIND -> {
                if (!e.tlsVerified()) {
                    return "DENY_LDAP_NO_TLS";
                }
                if (!e.appReceivedPassword()) {
                    return "DENY_MISSING_PASSWORD";
                }
                if (!e.ldapBindSucceeded()) {
                    return "DENY_BAD_AD_CREDENTIALS";
                }
            }
            case LDAP_SASL_GSSAPI -> {
                // LDAP bind authentication != HTTP browser SSO.
                if (!e.serviceTicketVerified()
                    || !e.ldapBindSucceeded()) {
                    return "DENY_LDAP_GSSAPI";
                }
                return "LDAP_SESSION_ONLY_NOT_HTTP_SSO";
            }
        }

        if (!e.accountActive()) {
            return "DENY_DISABLED_LOCAL_ACCOUNT";
        }
        if (!e.tenantAllowed()) {
            return "DENY_TENANT";
        }
        return "ALLOW_" + e.mechanism().name();
    }

    static Evidence sample(
        Mechanism mechanism, boolean ticket,
        boolean spn, boolean password, boolean tls,
        boolean bind, boolean active, boolean tenant) {
        return new Evidence(
            mechanism, "alice@CORP.EXAMPLE.TEST",
            ticket, spn, password, tls, bind, active, tenant
        );
    }

    public static void main(String[] args) {
        Evidence kerberos = sample(
            Mechanism.HTTP_SPNEGO,
            true, true, false, true, false, true, true);

        Evidence ldap = sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, true, true, true, true);

        System.out.println("SPNEGO with ticket: " + decide(kerberos));
        System.out.println("LDAP password bind: " + decide(ldap));

        System.out.println("No ticket: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            false, true, false, true, false, true, true)));

        System.out.println("Wrong SPN: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            true, false, false, true, false, true, true)));

        System.out.println("Password sent to SPNEGO: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            true, true, true, true, false, true, true)));

        System.out.println("LDAP without TLS: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, false, true, true, true)));

        System.out.println("LDAP invalid password: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, true, false, true, true)));

        System.out.println("LDAP no password: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, false, true, false, true, true)));

        System.out.println("LDAP SASL GSSAPI: " + decide(sample(
            Mechanism.LDAP_SASL_GSSAPI,
            true, false, false, true, true, true, true)));

        System.out.println("Disabled account: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            true, true, false, true, false, false, true)));

        System.out.println("Wrong tenant: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, true, true, true, false)));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac KerberosVsLdapLoginDemo.java
java KerberosVsLdapLoginDemo
~~~

**Exact stdout:**

~~~text
SPNEGO with ticket: ALLOW_HTTP_SPNEGO
LDAP password bind: ALLOW_LDAP_PASSWORD_BIND
No ticket: DENY_NO_VALID_HTTP_TICKET
Wrong SPN: DENY_WRONG_SERVICE_PRINCIPAL
Password sent to SPNEGO: DENY_UNEXPECTED_PASSWORD
LDAP without TLS: DENY_LDAP_NO_TLS
LDAP invalid password: DENY_BAD_AD_CREDENTIALS
LDAP no password: DENY_MISSING_PASSWORD
LDAP SASL GSSAPI: LDAP_SESSION_ONLY_NOT_HTTP_SSO
Disabled account: DENY_DISABLED_LOCAL_ACCOUNT
Wrong tenant: DENY_TENANT
~~~

**Explanation:**
- SPNEGO allows only when the ticket validator verified a ticket for the right SPN and the app received no password in this flow.
- LDAP form login requires TLS and bind success; it does not use an HTTP service ticket.
- LDAP SASL/GSSAPI can use Kerberos, yet that proof belongs to an **LDAP session**, which should never turn into a Spring browser Authentication.
- After proof, the app still checks local account/tenant (in the demo, LDAP SASL is classified as an LDAP session and disallowed for web login).
- `serviceTicketVerified`, `ldapBindSucceeded`, and `tlsVerified` are **simulations only**, never accepted from a client-supplied request.

**Limitations:** The demo does not handle JAAS/GSS, HTTP Negotiate, LDAP StartTLS, password hashing, directory ACLs, signing/channel binding, session protection, or DC account policies. **Never use it as a production AuthenticationProvider**.

## 30. Organizing Spring SecurityFilterChains to Avoid Mixing Mechanisms

An application with browser login, Kerberos SSO, and resource APIs needs clear trust boundaries:

~~~text
/secure/intranet/**    -> SPNEGO/Kerberos filter + trusted GSS acceptor
/login/password        -> AD LDAP password login (only if policy permits)
/oauth2/**             -> OIDC client/redirect login
/api/**                -> OAuth2 Resource Server access-token validation
/directory/**          -> Protected directory operations (service identity)
~~~

**This layout is conceptual**, not default Spring URLs for each filter. Configure `SecurityFilterChain` matchers and ordering per application. With multiple chains, test which chain handles each route to prevent fall-through into a permissive chain.

**Anti-downgrade rules:**
- If an endpoint requires Kerberos or MFA assurance, LDAP password fallback **is not sufficient on its own** without matching assurance.
- Never allow anonymous Basic/Auth headers to substitute for a Kerberos ticket.
- Never grant authorities from a raw LDAP `displayName` or Kerberos realm string.
- Never pass a raw AD password from backend to multiple microservices to re-authenticate.
- For browsers with a Spring session, the security context must distinguish authentication method, expiry, and principal changes.

## 31. Different Session and Logout Lifecycles

**After Kerberos SSO:**
- The app can create its own HTTP session cookie after GSS authentication.
- App logout destroys the local session/cookie, yet **does not delete the TGT** from the OS credential cache.
- A browser revisiting the endpoint may **auto-log in** via Kerberos per SSO policy.
- If the user is disabled or a group is revoked, old sessions may not reflect it immediately; enforce application policy.

**After LDAP password form login:**
- The app can also create an HTTP session.
- App logout destroys only that session; it does not alter or revoke the AD password.
- Changing the AD password does not automatically terminate all local app sessions unless revocation integration exists.
- Never retain raw passwords in sessions/remember-me tokens; if remember-me is used, enforce proper policy, encryption, and revocation.

**After OIDC/SAML federation:** yet another set of logout/token/session semantics applies. Never assume single logout spans Kerberos, LDAP, OIDC, and SAML simply because the backend shares AD.

## 32. Does SSO with Active Directory Require LDAP?

**Not necessarily.** An HTTP SPNEGO acceptor can verify tickets with a service keytab without needing an LDAP bind during AP verification itself. However, the app may choose to:
- Query AD group memberships via LDAP after login.
- Query a local account/provisioning registry (SCIM or DB).
- Use local policy to decide tenant/resource access.
- Check near-real-time user status if required by security SLA.

**Conclusion:** "Using AD to sign in" can mean **Kerberos authentication + LDAP authorization data lookup**, or **LDAP password authentication + local authorization**. These two forms differ in password handling and trust boundaries, even though both end in a Spring Authentication.

## 33. Diagnostic Error Comparison

| Symptom | Kerberos / SPNEGO Suspect | LDAP / AD Password Suspect |
| --- | --- | --- |
| Browser sends no Negotiate | Browser zone/policy, OS tickets, trusted URLs | Unrelated if using form login |
| Repeated 401 after Negotiate | Wrong SPN/keytab/KVNO/realm/clock, provider wiring | Do not assume LDAP bad password |
| KRB_AP_ERR_SKEW | Client/service/KDC clock skew | Not simple bind |
| KRB_AP_ERR_MODIFIED | Keytab/SPN/key integrity | Not LDAP invalidCredentials |
| LDAP resultCode 49 | Not Kerberos AP success/failure | Bad credentials / account state / AD subcodes |
| LDAP strongAuthRequired (8) | Not a GSS Kerberos password error | LDAP signing/TLS policy mismatch |
| TLS PKIX/cert path error | Only if component uses TLS LDAP/HTTPS | LDAPS truststore/hostname/CA |
| Login succeeds, yet 403 | Local role/tenant policy | Local role/tenant policy |
| User disabled, yet session still accesses | Stale local auth/session, ticket lifecycle | Stale local auth/session |
| NTLM fallback | Mechanism negotiation/policy | SASL NTLM also has its own policy |
| AD DC outage | KDC ticket issuance fails; cached tickets may remain | New LDAP binds usually fail |
| Browser password popup | SPNEGO policy/realm/NTLM negotiation | Password form inherently prompts for password |

**The same HTTP 401/403 does not prove the same root cause**. Isolate the hop first: browser→app, app→KDC, app→directory, or application authorization.

## 34. Technical Testing: Kerberos SPNEGO Happy Path

**Test environment with dedicated domain/KDC and service keytab:**

1. Log a Windows/Linux client into the test realm with a valid TGT.
2. Open a browser permitted to use integrated authentication for the test portal.
3. Hit a protected endpoint and observe `401 WWW-Authenticate: Negotiate` at the challenge step.
4. Verify the browser sends `Authorization: Negotiate` with no password form.
5. Check the OS ticket cache: service ticket for `HTTP/portal.corp.example.test`.
6. Spring Kerberos ticket validator accepts, logging the exact mechanism and pseudonymized principal.
7. User mapping and tenant/roles are accurate.
8. Test disabled local account, wrong tenant, and missing group → deny.
9. Test wrong service principal/keytab, expired ticket, and clock skew → fail closed.
10. Browser logout then revisit: may re-SSO if TGT remains; document expected behavior accurately.

**Never assume Chrome/Edge/Firefox always share identical policies**, nor treat a request carrying an existing session cookie from an earlier login as proof that SPNEGO is working.

## 35. Technical Testing: LDAP Password Bind

**Lab with test DC/AD and trusted LDAPS certificate:**

1. User visits the form login over HTTPS.
2. App submits username/password to configured `ActiveDirectoryLdapAuthenticationProvider` or `BindAuthenticator`.
3. Provider connects to the right LDAP server over a valid TLS certificate.
4. Correct username/password bind → Authentication succeeds.
5. Wrong password → authentication denied; no user session created.
6. Disabled/locked/expired account → denied per AD policy.
7. Invalid/expired TLS certificate → fail closed; no plaintext fallback.
8. Test LDAP signing policy and CBT appropriate to simple vs. SASL bind.
9. Test injection strings in username; search filters remain safe.
10. Verify app logs/APM contain no raw credentials.
11. Enforce brute-force/rate limits and verify AD lockout policy.
12. After bind success, local account/tenant permissions are still checked.

**Use managed dummy test passwords**; never store real employee AD passwords in fixtures or attach HAR files with credentials to tickets.

## 36. How Is Testing LDAP SASL/GSSAPI Different?

If the product or integration layer uses LDAP SASL/GSSAPI:
1. Determine whether the **LDAP client principal** is actually the service or a delegated user.
2. Verify acquisition of Kerberos credentials/TGT in the right realm and SPN for the LDAP service.
3. Enable SASL mechanism GSSAPI and enforce signing/sealing/TLS per security policy.
4. If using LDAP over TLS with AD CBT enforced, verify channel binding support.
5. Verify the LDAP bind succeeds for the **intended LDAP session principal**.
6. Verify directory ACLs allow reading only required data.
7. Confirm **no HTTP browser Authentication is created** solely because a backend LDAP SASL bind succeeded.
8. With Kerberos constrained delegation, enforce strict delegation policy and never export tickets carelessly.

**A successful service LDAP GSSAPI bind proves the service holds credentials to call the directory; it does not prove any browser user was verified.** If user delegation is needed, that is a separate authentication/authorization flow requiring auditing.

## 37. Comprehensive Test Matrix

| # | Test Case | Expected Outcome |
| --- | --- | --- |
| 01 | HTTP SPNEGO with valid ticket, right SPN/keytab | Spring creates matching verified principal |
| 02 | HTTP SPNEGO without service ticket | 401 challenge/deny |
| 03 | HTTP Negotiate with actual NTLM fallback | Never marked as Kerberos pass |
| 04 | SPNEGO wrong service principal | Fail closed |
| 05 | SPNEGO keytab stale KVNO | Decrypt/accept fails without matching key |
| 06 | Kerberos client/KDC/service clock drift past limit | Authentication fails |
| 07 | Expired Kerberos ticket | Rejected |
| 08 | Replayed Kerberos token | Rejected by replay policy |
| 09 | Wrong realm without trust | No user authentication created |
| 10 | Valid cross-realm trust | Preserves verified realm; checks app authorization |
| 11 | Same username in two realms | Not auto-linked |
| 12 | Browser disallowed from Negotiate | No user forged from header |
| 13 | SPNEGO succeeds, yet account disabled | Denied |
| 14 | SPNEGO succeeds, yet tenant mismatch | 403 |
| 15 | SPNEGO succeeds, yet missing role | 403 |
| 16 | LDAP simple bind valid password over TLS | Authentication succeeds |
| 17 | LDAP simple bind wrong password | Denied |
| 18 | LDAP simple bind without TLS | Not executed / insecure path rejected |
| 19 | Untrusted LDAPS certificate | Fail closed |
| 20 | LDAP hostname mismatch | Fail closed |
| 21 | STARTTLS upgrade fails | Plaintext password is never sent |
| 22 | AD account locked/disabled | Proper bind/access denial |
| 23 | Password expired / must change | Classified accurately without leaking subcodes |
| 24 | LDAP search filter contains injection characters | Escaped/bounded search; no bypass |
| 25 | LDAP search returns multiple users | Does not arbitrarily pick a user to bind |
| 26 | LDAP group named ROLE_ADMIN | Does not auto-grant admin |
| 27 | LDAP group removed, stale Spring session | Revocation/online guard per SLA |
| 28 | LDAP SASL/GSSAPI bind succeeds | Proves LDAP session only |
| 29 | LDAP SASL/GSSAPI with wrong service principal | Bind fails |
| 30 | TLS + SASL missing required CBT | Rejected per AD policy |
| 31 | Non-TLS SASL missing required LDAP signing | Rejected per AD policy |
| 32 | Plain LDAP simple bind 389 when DC requires secure bind | Rejected |
| 33 | Kerberos form password provider | App sees password; not logged as seamless SPNEGO |
| 34 | Kerberos service-ticket provider | App does not need user password |
| 35 | Portal uses OIDC IdP backed by AD | App receives token; not misclassified as LDAP/SPNEGO |
| 36 | Proxy strips Negotiate Authorization header | Proxy issue detected; no X-User fallback |
| 37 | Wrong LDAP DC/domain URL | Does not authenticate against wrong directory |
| 38 | Directory outage during password login | New binds fail / controlled availability |
| 39 | KDC outage with OS-cached ticket | Behavior depends on ticket/service; no false auto-login |
| 40 | Password changed, stale app session | Session revocation per policy |
| 41 | Kerberos service keytab password rotated | Check KVNO/pod rollout |
| 42 | Local user mapping using substring before @ | Security test fails with duplicate realms |
| 43 | OIDC token sent as HTTP Negotiate ticket | Wrong protocol rejected |
| 44 | LDAP password posted to non-login API | Rejected / credentials never logged |
| 45 | Group membership belongs to tenant A, request targets tenant B | 403 |
| 46 | User has valid Kerberos ticket, yet no local account | Fail closed / JIT per policy |
| 47 | Browser logout then SSO auto-works again | Expected if TGT remains valid |
| 48 | LDAP simple bind passwords accidentally logged | Security QA fails |
| 49 | Credential downgrade to form bypassing MFA policy | Rejected |
| 50 | Search-bind service account has overly broad write rights | Least-privilege QA fails |

**PASS is not just HTTP 200/302**: there must be evidence that **the exact intended authentication mechanism**, principal/source, and account/tenant were used, without leaking passwords or service secrets.

## 38. Failure Models and Diagnostic Steps

**When SPNEGO fails to log in:**
1. Is `WWW-Authenticate: Negotiate` present?
2. Does the browser actually send a Negotiate token? Is the mechanism Kerberos or NTLM?
3. Are the TGT and service ticket unexpired? Check OS ticket cache if permitted.
4. Does the SPN match the browser hostname after canonicalization?
5. Are KDC realm/trust correct?
6. Does the keytab match the service account/principal/KVNO/enctype/key material?
7. Are client/KDC/service clocks synchronized?
8. Does the proxy forward the complete Authorization header?
9. Are Spring provider/entrypoint/filter on the right SecurityFilterChain?
10. Did Kerberos pass while `UserDetailsService`/tenant policy denied access?

**When LDAP password login fails:**
1. Does the browser form post to the right HTTPS endpoint?
2. Does username/UPN/DN resolve the right entry? Are LDAP filters escaped?
3. Does the app connect to the right AD/DC/LDAPS hostname?
4. Are TLS certificate chain/hostname/truststore valid?
5. Is AD simple bind blocked by signing/TLS policy?
6. Is the password right, or is the account disabled/locked/expired?
7. What is the LDAP bind/result code?
8. Does the service search account still hold the minimal required permissions?
9. Is the LDAP provider being called through the wrong AuthenticationManager?
10. Did bind succeed while app account/roles/tenant denied access?

**Never use one combined runbook to "fix both together":** resetting a service keytab will not fix a wrong password; raising clock skew will not fix LDAP TLS; loosening a user search filter will not fix a Kerberos SPN.

## 39. Logging and Observability Model

Suggested metrics instrumented by app/infra, **not all provided automatically by Spring Security**:

| Metric | Purpose |
| --- | --- |
| `authentication_kerberos_spnego_total` | Requests checked via Kerberos |
| `authentication_ldap_simple_bind_total` | Password LDAP bind attempts |
| `authentication_ldap_sasl_gssapi_total` | Directory GSSAPI binds |
| `authentication_unexpected_ntlm_fallback_total` | Policy-violating NTLM usage |
| `authentication_kerberos_ticket_error_total` | Ticket/SPN/realm/KVNO errors |
| `authentication_ldap_tls_failure_total` | TLS/certificate/hostname errors |
| `authentication_ldap_invalid_credentials_total` | Invalid bind credentials |
| `authentication_directory_unavailable_total` | AD/LDAP failures |
| `authentication_account_disabled_total` | Local user status denials |
| `authentication_tenant_denied_total` | Membership/resource denials |
| `authentication_mfa_downgrade_blocked_total` | Assurance-bypass attempts |
| `authentication_credential_exposure_incident_total` | Passwords/tickets/keytabs accidentally logged |

**Audit events should record** timestamp, auth mechanism, trusted realm/directory ID, pseudonymized principal/local account, tenant, policy version, success/failure category, and correlation ID. **Never log** raw passwords, LDAP bind secrets, `Authorization: Negotiate` headers, Kerberos tickets, keytab contents, or session cookies.

**Never allow emails, raw UPNs, password error messages containing PII, or token values as unbounded metric labels.**

## 40. Runbook for Migrating from AD Password Forms to SSO

1. **Inventory**: which apps currently accept AD passwords via LDAP, which already use Kerberos/OIDC/SAML, directory DCs, tenants, and role mappings.
2. **Measure**: confirm LDAP binds enforce TLS/hostname verification and audit for zero password logs.
3. **Choose**: intranet managed clients can use Kerberos SPNEGO; Internet/mobile usually fit an OIDC/SAML IdP.
4. **Register**: SPNs/keytabs, realm trusts, and browser Negotiate policies if choosing Kerberos.
5. **Map identity**: verified Kerberos principal / issuer+subject → local account, never relying on email-only matching.
6. **Decouple groups**: LDAP is solely a directory attributes source, never auto-granting roles.
7. **Set assurance**: specify endpoints requiring MFA, device posture, or step-up auth.
8. **Configure**: isolate routes/providers and eliminate unnecessary password fallbacks.
9. **Canary**: subset of users, browsers, VPN/networks, and devices; signed, redacted logs/metrics.
10. **Test negative**: wrong SPN, wrong realm, plaintext LDAP, password logs, downgrade, disabled account, tenant mismatch.
11. **Cut over**: phase out direct password collection in apps, keeping emergency flows only when security-reviewed.
12. **Observe**: login successes by method, NTLM fallbacks, 401 loops, and 403 permission issues.
13. **Revoke**: proper session/token/cookie handling on user disable/mover/leaver events.
14. **Rollback safely**: never re-open plaintext LDAP, never trust arbitrary Kerberos realms, and never bypass MFA.

**Migration objective:** reduce password exposure and centralize authentication policy, **not** weaken application authorization.

## 41. Self-Assessment Questions

**1. Does Kerberos SSO send the AD password directly to the Spring web app?**  
Normally no. The browser/OS sends a Kerberos SPNEGO ticket for the HTTP service; the app verifies the ticket.

**2. Does LDAP simple bind send the user password to the directory?**  
Yes. In form login, the app also receives the password; TLS must protect the directory connection.

**3. Does LDAP bind ever use Kerberos?**  
Yes. LDAP SASL/GSSAPI can use Kerberos to authenticate an LDAP session.

**4. Does a successful LDAP SASL/GSSAPI bind prove the browser logged in via HTTP SPNEGO?**  
Not automatically. They are two separate security contexts and service principals.

**5. Is every AD password login an LDAP simple bind?**  
No. It can use a password-based Kerberos flow or identity federation.

**6. Why is an HTTP service keytab required for Kerberos SPNEGO?**  
The service acceptor needs key material to decrypt and verify service tickets for its SPN.

**7. Why doesn't Spring LDAP bind simply use UserDetailsService to fetch a password hash?**  
The directory verifies the password during the bind; Spring does not pull AD password hashes into the app.

**8. Is LDAPS the same as LDAP signing?**  
No. LDAPS/TLS provides confidentiality and integrity; signing provides message integrity primarily for non-TLS SASL sessions.

**9. Does LDAP channel binding token apply to simple bind over TLS?**  
Not under AD CBT policy; CBT applies to TLS+SASL sessions.

**10. Does an initial 401 Negotiate received by the browser mean authentication failed?**  
No, it can be the normal challenge step.

**11. Are Kerberos principals with the same local username in two realms the same account?**  
No. Preserve source namespace and linking proof.

**12. Can a Spring Kerberos SSO app search LDAP for groups?**  
Yes. LDAP search is only for retrieving attributes/permissions per policy, not a replacement for ticket validation.

**13. Does changing an AD password automatically log users out of every Kerberos/LDAP app?**  
Not necessarily; issued tickets and application sessions have separate lifecycles.

**14. If an LDAP TLS certificate is invalid, should verification be disabled to let login pass?**  
No. Fix the server certificate, truststore, or hostname.

**15. Does a valid Kerberos ticket automatically grant admin rights in Spring?**  
No. The application must map approved authorities and check tenant/resource access.

## 42. Production Checklist

- [ ] Clearly distinguished Web Kerberos SPNEGO, LDAP simple bind, LDAP SASL/GSSAPI, and AD password login.
- [ ] Verified HTTP Negotiate actually uses Kerberos rather than mistaking NTLM fallback for it.
- [ ] Checked Kerberos SPN/realm/KDC/keytab/clocks and browser policy.
- [ ] Keytab protected as a secret, with owned rotation and pod consistency.
- [ ] LDAP simple bind runs strictly over LDAPS/STARTTLS with TLS certificate/hostname validation.
- [ ] No plaintext LDAP fallback when TLS fails.
- [ ] LDAP signing, sealing, and CBT applied appropriately to SASL or TLS per policy.
- [ ] AD passwords handled minimally in apps; never stored, logged, or casually forwarded.
- [ ] LDAP search filters escaped and scope bounded.
- [ ] Service search-bind account obeys least privilege.
- [ ] Spring Security uses the right provider/filter/entrypoint per route.
- [ ] Spring Security Kerberos extension installed when SPNEGO is needed; do not assume starter-security suffices.
- [ ] Spring LDAP provider matches the actual directory/AD schema and configuration.
- [ ] LDAP directory lookup success is never treated as user authentication success.
- [ ] Password-based Kerberos AuthenticationProvider is not mistaken for seamless browser SSO.
- [ ] Group/GrantedAuthority mapping goes through an approved allowlist scoped by issuer/realm/tenant.
- [ ] Active user account and local tenant/resource authorization are enforced.
- [ ] Downgrade/MFA/assurance policy defined for hybrid login methods.
- [ ] Password reset/account disable has matching session/ticket revocation SLAs.
- [ ] Tests cover Kerberos ticket/SPN/realm/clock/keytab and LDAP password/TLS/lockout.
- [ ] Tests confirm LDAP SASL/GSSAPI is never mistaken for HTTP browser login.
- [ ] Audit/metrics distinguish sources without exposing secrets or PII.
- [ ] Canary and rollback never weaken credential transport or ticket validation.

## 43. Conclusion

**Kerberos HTTP SPNEGO SSO uses Kerberos tickets already issued by the OS/KDC; LDAP simple bind verifies username/password sent by the app to the directory; "AD password login" is a business label that can be implemented across multiple protocols.** LDAP SASL/GSSAPI is a special case using Kerberos within LDAP and **does not turn an LDAP session into a web SSO session**.

In Spring Security, use the **Spring Security Kerberos extension** with SPNEGO filter/entrypoint and service-ticket validator for HTTP Negotiate; use **Spring Security LDAP / ActiveDirectoryLdapAuthenticationProvider** for form password binds when required, with trusted LDAPS/STARTTLS and strict password controls. After authentication succeeds, **both must map external identity to a local account and enforce authorization by roles/tenant/resource**.

**Design rule:** never infer a mechanism from the name "AD login"; verify **who receives the password, who issues and verifies the ticket, which protocol protects the wire, and which policy governs permissions**. That is the foundation for choosing proper SSO, reducing credential exposure, and never confusing LDAP directory lookups with authentication evidence.

### Official References

- Spring Security — LDAP Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Spring Security — LdapAuthenticationProvider Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/LdapAuthenticationProvider.html
- Spring Security — ActiveDirectoryLdapAuthenticationProvider Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring Security Kerberos — SPNEGO/Negotiate, KerberosAuthenticationProvider and KerberosServiceAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Microsoft Learn — LDAP Signing Overview for Active Directory: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing
- Microsoft Learn — LDAP Channel Binding for AD DS: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding
- Microsoft Learn — Enable LDAP signing and reject insecure simple binds: https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/enable-ldap-signing-in-windows-server
- MIT Kerberos — Kerberos concepts and admin documentation: https://web.mit.edu/kerberos/krb5-current/doc/
- RFC 4120 — The Kerberos Network Authentication Service (V5): https://www.rfc-editor.org/rfc/rfc4120
- RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication: https://www.rfc-editor.org/rfc/rfc4559
- RFC 4511 — LDAPv3 Protocol, Bind and Operations: https://www.rfc-editor.org/rfc/rfc4511
- RFC 4513 — LDAP Authentication Methods and Security Mechanisms: https://www.rfc-editor.org/rfc/rfc4513
- RFC 4752 — The Kerberos V5 (GSSAPI) SASL Mechanism: https://www.rfc-editor.org/rfc/rfc4752
- RFC 4515 — LDAP String Representation of Search Filters: https://www.rfc-editor.org/rfc/rfc4515
