# Distinguishing KerberosAuthenticationProvider from Service Ticket Validation in Spring Security Kerberos

## 1. Why Must We Distinguish the Two Providers?

In a **Spring Security – federation** application, you may encounter two experiences side by side:

- A user opens an internal website on a domain-joined workstation. The browser automatically exchanges **HTTP Negotiate / SPNEGO** and the application signs them in without prompting for a password.
- A user connects from a device without Kerberos credentials or a browser that does not support Negotiate. The application renders a **form login**, and the user enters username/password to be verified against the Kerberos KDC/realm.

Both can use **Kerberos V5**, yet the inputs, where cryptography is verified, and which provider to choose **differ**:

1. `KerberosAuthenticationProvider` is the provider for the **username/password flow**, using **KerberosClient** (typically `SunJaasKerberosClient`) to log in with credentials via Kerberos/JAAS; afterward it loads the account/authorities via `UserDetailsService`.
2. `KerberosServiceAuthenticationProvider` is the provider for a **service ticket or SPNEGO token** sent by a browser/client to **an application acting as a service acceptor**. It requires **KerberosTicketValidator** (typically `SunJaasKerberosTicketValidator`) and the service's own **service principal/keytab** to verify via GSS/JAAS; afterward it also uses `UserDetailsService`.

Their similar names easily lead to misconfiguration: adding `KerberosAuthenticationProvider` **does not make browser SPNEGO work**, and adding `KerberosServiceAuthenticationProvider` **does not create a username/password verification screen**.

This lesson belongs to the **Kerberos Integration** group. Objectives:

- Distinguish **KerberosClient.login(username, password)** from **KerberosTicketValidator.validateTicket(byte[] token)** in terms of responsibility.
- Understand request Authentication types: `UsernamePasswordAuthenticationToken` and `KerberosServiceRequestToken`.
- Trace Spring Security form-login, SPNEGO, `ProviderManager`, `supports(...)`, `UserDetailsService`, and `SecurityContext` flows.
- Distinguish **KDC password verification during AS exchange** from **service acceptor AP-REQ/GSS token verification via keytab**.
- Configure one or both providers, including fallbacks and boundaries.
- Diagnose KDC, SPN, keytab, replay, clock skew, local user status, and access permission errors.
- Run a standalone **Java 17 demo** simulating provider routing and testing authentication-path confusion scenarios.

**Principle:** Look at **the type of evidence the caller presents**: username/password or a Kerberos service credential. From that, select the **provider with the right trust boundary**, rather than picking classes merely because "Kerberos" appears in the name.

## 2. The Big Picture

~~~text
                           Spring Security Servlet app
                                      |
                            AuthenticationManager
                            (ProviderManager)
                                /           \
                               /             \
                      FORM LOGIN           SPNEGO / HTTP
                         |                   NEGOTIATE
                         |                       |
               UsernamePassword           KerberosService
              AuthenticationToken         RequestToken
                         |                       |
                         v                       v
             KerberosAuthentication  KerberosServiceAuthentication
                   Provider                  Provider
                         |                       |
                         v                       v
                 KerberosClient           KerberosTicketValidator
                SunJaasKerberosClient     SunJaasKerberosTicketValidator
                         |                       |
                         v                       v
                    KDC/JAAS                JAAS/JGSS acceptor
             login(username,password)      servicePrincipal + keytab
                         \                       /
                          \                     /
                           v                   v
                         verified user principal
                                      |
                                      v
                         UserDetailsService / local policy
                                      |
                                      v
                         Authentication + GrantedAuthorities
                                      |
                                      v
                            SecurityContext / session
                                      |
                                      v
                              Application authorization
~~~

**The two providers do not call each other.** They are **two implementations of AuthenticationProvider** handling different Authentication request types. `ProviderManager` queries `supports(...)` and tries the appropriate provider per policy/registration order.

A Kerberos service may **use only SPNEGO**, **use only form login against the KDC**, or **combine both**. Enabling both is not mandatory.

## 3. Core Comparison Table

| Criterion | KerberosAuthenticationProvider | KerberosServiceAuthenticationProvider |
| --- | --- | --- |
| **Purpose** | Authenticates **username/password** against a Kerberos KDC | Authenticates **service ticket / SPNEGO token** at the receiving service |
| **Input** | User-supplied username and password | GSS-API/SPNEGO bytes from caller; typically in `Authorization: Negotiate` header |
| **Authentication request** | Usually `UsernamePasswordAuthenticationToken` | `KerberosServiceRequestToken` |
| **Cryptographic verifier** | `KerberosClient`, e.g., `SunJaasKerberosClient` | `KerberosTicketValidator`, e.g., `SunJaasKerberosTicketValidator` |
| **Network actor** | Web server uses username/password as a Kerberos client to authenticate via KDC/JAAS | Browser/OS holds ticket; web server uses keytab to accept and verify GSS token rather than performing password login |
| **Service keytab** | Not required solely to verify user/password | **Required** service principal/keytab or equivalent acceptor credentials per deployment |
| **User password** | **Yes**, app handles input password; must be strictly protected | **No**, app never needs to know the user's password |
| **KDC involvement** | Kerberos client runs login/AS flow per environment | Browser may use TGT to get ticket from KDC/TGS; acceptor can verify AP-REQ locally via keytab |
| **Browser flow** | Form POST typically to login processing URL | 401 `WWW-Authenticate: Negotiate`, browser replies with `Authorization: Negotiate` |
| **Typical filter** | `UsernamePasswordAuthenticationFilter` via `formLogin` DSL | `SpnegoAuthenticationProcessingFilter` |
| **EntryPoint** | Login page/redirect per form policy | `SpnegoEntryPoint`, optionally forwarding to a login page on fallback |
| **Post-authentication** | `KerberosUsernamePasswordAuthenticationToken` may hold a JAAS Subject for suitable use cases | Authenticated `KerberosServiceRequestToken` containing ticket validation/GSS context results |
| **Local account/roles** | `UserDetailsService` | `UserDetailsService` |
| **Common failures** | Wrong password, unreachable KDC, JAAS login failure, disabled account | Wrong SPN/keytab/KVNO, expired ticket, replay, invalid GSS/SPNEGO token |
| **Use cases** | Non-domain devices, deliberate form fallback | Integrated Windows Authentication/domain SSO, Kerberos HTTP acceptor |

**Note:** `UsernamePasswordAuthenticationToken` and `KerberosServiceRequestToken` are **Spring Authentication objects**, not raw KDC tickets or JWTs. And `KerberosUsernamePasswordAuthenticationToken` is a class in the Kerberos module **used as an appropriate login result**, not a "Kerberos service ticket".

## 4. Flow A: KerberosAuthenticationProvider — Username/Password

### 4.1. When Is This Flow Triggered?

Typically when:

- The user lacks OS Kerberos credentials or the browser does not use SPNEGO.
- The app deliberately offers form login for the user to submit username/password.
- The enterprise wants passwords verified against the KDC/realm rather than a local password database.
- The app supports SPNEGO simultaneously but maintains a fallback policy for non-domain devices.

Diagram:

~~~text
Browser                     Spring Web                    KDC / Realm
   |                            |                             |
   | GET /login                 |                             |
   |--------------------------->|                             |
   |<---------------------------| HTML form + CSRF            |
   |                            |                             |
   | POST /login                |                             |
   | username + password        |                             |
   |--------------------------->|                             |
   |                            | UsernamePassword            |
   |                            | AuthenticationFilter        |
   |                            |   -> ProviderManager        |
   |                            |   -> KerberosAuthentication |
   |                            |      Provider               |
   |                            |   -> SunJaasKerberosClient  |
   |                            |       .login(user,password) |
   |                            |---------------------------->|
   |                            |   JAAS/Kerberos login       |
   |                            |<----------------------------|
   |                            | KDC verified credentials    |
   |                            | UserDetailsService          |
   |                            |  check enabled/authorities  |
   |<---------------------------| Authentication + session   |
~~~

Spring should not compare plaintext passwords against a hardcoded string in business code. `SunJaasKerberosClient` uses the Java runtime's JAAS login module and KDC to perform authentication per realm/Kerberos configuration. The Javadoc-published method is:

~~~java
JaasSubjectHolder login(String username, String password);
~~~

That is the **`KerberosClient`** signature, not Spring AuthenticationProvider's `authenticate` method. `KerberosAuthenticationProvider` invokes this client through the Spring pipeline. Depending on config/version, the resulting JAAS Subject can serve multi-tier use cases; it does not imply every web app has delegation rights.

### 4.2. Using a KDC Differs from Checking a Local Password

`KerberosAuthenticationProvider` **is not** `DaoAuthenticationProvider`:

- `DaoAuthenticationProvider` usually loads a password hash from `UserDetailsService` and checks it with `PasswordEncoder`.
- `KerberosAuthenticationProvider` uses `KerberosClient` to **verify username/password against the Kerberos realm/KDC**.
- `ActiveDirectoryLdapAuthenticationProvider` (if used) performs separate AD/LDAP authentication, **not an alias** of KerberosAuthenticationProvider.
- If the organization uses an OIDC/SAML broker, that is a different trust/protocol and does not automatically replace the Kerberos provider.

Because a form-login app **receives user passwords**, it requires HTTPS, CSRF protection, rate limiting, minimal logging, zero password logging, no passwords in query strings, and credential-stuffing defenses per policy. One advantage of SPNEGO is that the web server **never receives the user's password directly**, so prefer SPNEGO whenever infrastructure permits.

### 4.3. Authentication Request and Result

Normally the Spring form filter creates a request:

~~~java
UsernamePasswordAuthenticationToken request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice@EXAMPLE.TEST", userSuppliedPassword);
~~~

This is an **illustrative snippet** at the Spring Authentication pipeline layer; with `formLogin`, the filter constructs the request automatically, so controllers should not call this themselves. Never hardcode or log passwords.

On success, the Kerberos module provides `KerberosUsernamePasswordAuthenticationToken` — extending `UsernamePasswordAuthenticationToken` — which may carry `JaasSubjectHolder` for use cases like `KerberosMultiTier`. These belong to **sensitive server-side credential context**; never serialize Subject/TGT/service credentials into JSON for the browser.

### 4.4. What the Form Provider Does **Not** Do

- Does not accept and verify `Authorization: Negotiate` in place of the service ticket provider.
- Does not replace browser SPNEGO/Kerberos acceptor keytabs.
- Does not imply the app emits HTTP `WWW-Authenticate: Negotiate`.
- Does not guarantee login succeeds if local policy denies the user.
- Does not revoke all TGTs or service tickets on the user's machine upon logout.
- Does not perform Kerberos constrained delegation to downstream services automatically.

## 5. Flow B: KerberosServiceAuthenticationProvider — Service Ticket

### 5.1. Client Holds a TGT Before Reaching the Website

In domain SSO, the OS/browser may already hold a **Ticket Granting Ticket (TGT)** from an AS exchange. To access `https://portal.example.test/private`, the client obtains or reuses a **service ticket** for the service principal:

~~~text
HTTP/portal.example.test@EXAMPLE.TEST
~~~

If no cached service ticket exists, the client uses the **TGT** in a TGS exchange to request a service ticket for this SPN. The browser does not need to send the user's password to the web app. **The TGT is never sent directly to the Spring web acceptor.**

### 5.2. HTTP Negotiate Challenge/Response

~~~http
GET /private HTTP/1.1
Host: portal.example.test

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

The client then sends:

~~~http
GET /private HTTP/1.1
Host: portal.example.test
Authorization: Negotiate <base64-SPNEGO-GSS-token>
~~~

These lines are **header illustrations**; the bracketed value is not a valid token. This is a **GSS/SPNEGO token**, not necessarily just a raw service ticket; it can contain an **AP-REQ and authenticator**, mechanism negotiation state, and may require multiple rounds. Never Base64-decode and parse usernames inside a controller.

### 5.3. Path Through Spring Security

~~~text
SpnegoEntryPoint: sends 401 / WWW-Authenticate: Negotiate
        |
        v
Browser: Authorization: Negotiate <token>
        |
        v
SpnegoAuthenticationProcessingFilter
  - reads header
  - decodes bytes from token
  - creates KerberosServiceRequestToken (unauthenticated)
        |
        v
ProviderManager
  - provider.supports(KerberosServiceRequestToken)
        |
        v
KerberosServiceAuthenticationProvider
  - KerberosTicketValidator.validateTicket
        |
        v
SunJaasKerberosTicketValidator
  - servicePrincipal = HTTP/portal.example.test@EXAMPLE.TEST
  - service keytab = /run/secrets/kerberos/http.keytab
  - JAAS/JGSS accept security context
  - verify Kerberos service ticket + authenticator
        |
        v
Verified user principal from validator
        |
        v
UserDetailsService / local user status & authorities
        |
        v
Authentication / SecurityContext
        |
        v
Application authorization
~~~

**`KerberosServiceAuthenticationProvider` does not verify user passwords.** It uses **KerberosTicketValidator** to check that the client holds a valid service credential scoped to the application's service identity; this is an **authentication path using previously issued proof**.

### 5.4. Why Are Keytab and SPN Needed?

A Kerberos service ticket is issued for an **exact service principal** and protected with the service's long-term key. For example:

~~~text
SPN:    HTTP/portal.example.test@EXAMPLE.TEST
Keytab: /run/secrets/kerberos/http.keytab
~~~

The service keytab must hold the key matching the principal, encryption type, and **KVNO** used by the KDC when issuing the service ticket. A wrong keytab/KVNO/SPN/hostname makes GSS accept fail even though the browser has a ticket and the KDC issued it cleanly.

**Never use a user password or the `krbtgt` key in place of a service keytab.** `krbtgt` is the TGS/KDC principal, not the website. Presenting a ticket for another service, such as `cifs/files.example.test`, must not authenticate as a ticket for `HTTP/portal.example.test`.

### 5.5. Do Not Confuse with "Single-Use Tickets" from Other Protocols

A Kerberos V5 service ticket can be reused across multiple **AP exchanges** while valid, provided the client generates a **fresh Authenticator** and the service accepts it per GSS/Kerberos policy. **Replayed authenticators** are rejected by replay protection; replaying the **exact same GSS/AP-REQ token** triggers a Kerberos error.

The `KerberosServiceRequestToken` Javadoc also notes that an already-authenticated token **must not be re-authenticated**, as doing so can trigger a Kerberos reply/replay error. This is a reminder **never to cache a raw SPNEGO token and re-submit it to authenticate every request**. Maintain an appropriate local SecurityContext/HttpSession or let the client initiate a fresh valid GSS exchange.

Do not apply **CAS Service Ticket single-use validation** rules to Kerberos service tickets; the two protocols differ.

## 6. Authentication Types and How ProviderManager Routes Requests

### 6.1. ProviderManager Queries supports(Class)

Spring Security defines the interface:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
    boolean supports(Class<?> authentication);
}
~~~

This is a **conceptual signature summary**; type parameters/annotations may vary by Spring Security version. Meaning:

- `supports` reports whether the provider **can** process an Authentication class.
- `authenticate` executes the real verification; it may return a successful Authentication, throw `AuthenticationException`, or return `null` if unable to handle per contract.
- `ProviderManager` manages multiple providers and selects providers based on request type/ordering.

Per the Kerberos documentation:

~~~text
Request: UsernamePasswordAuthenticationToken
          |
          +-> KerberosAuthenticationProvider
                    uses KerberosClient

Request: KerberosServiceRequestToken
          |
          +-> KerberosServiceAuthenticationProvider
                    uses KerberosTicketValidator
~~~

Never inspect `getPrincipal().toString()` to choose "SPNEGO or form": initially an SPNEGO token is unverified, so usernames from browsers or headers are untrusted. Route via properly configured **request classes and filters/endpoints**.

### 6.2. What Does Registering Both Providers Mean?

Example `ProviderManager` with both providers:

~~~java
AuthenticationManager manager = new ProviderManager(
    kerberosPasswordProvider,
    kerberosServiceTicketProvider);
~~~

Usage:

- Form-login dispatches username/password requests to **KerberosAuthenticationProvider**.
- The SPNEGO filter dispatches `KerberosServiceRequestToken` to **KerberosServiceAuthenticationProvider**.
- Both can share the same `UserDetailsService`/local account policy afterward.

**Provider ordering matters:** a `ProviderManager` may contain multiple providers supporting the **same request type**, such as `DaoAuthenticationProvider` and `KerberosAuthenticationProvider` both handling username/password in some setups. When one provider fails, Spring follows rules on whether to continue or stop based on `AuthenticationException` type. Therefore, define clearly:

- Which realm/KDC is authoritative for form authentication?
- Is fallback to local DB/LDAP allowed?
- Can a "KDC unavailable" error fall through to a weaker provider?
- Can a username valid in provider A log in via provider B with another password?
- Which provider outcomes are permitted to grant business permissions?

**Never add multiple providers assuming order can be ignored.** Run integration tests against the real provider manager for wrong-password, disabled, KDC outage, and wrong-token-type cases.

### 6.3. supports=true Is Not accepted=true

`supports(KerberosServiceRequestToken.class)` only indicates the provider **knows how to process that request class**, not that the ticket decrypted cleanly. An attacker's raw SPNEGO token can have the right request type yet **fail verification** inside `KerberosTicketValidator`.

Similarly, `supports(UsernamePasswordAuthenticationToken.class)` does not mean the password is correct. Wait for `authenticate` to return a verified result before using the principal for authorization.

## 7. Trust Boundary Comparison: KDC Login vs. Service Acceptor

| Question | Username/Password Flow | Service Ticket Flow |
| --- | --- | --- |
| Who supplies initial proof? | User/client form submits username + password | Browser/OS supplies GSS/SPNEGO token |
| Who verifies the password? | JAAS/KDC via KerberosClient login | **No password verification step at the service** |
| When is the KDC involved? | When KerberosClient executes login per realm policy | When client obtains TGT/ST, possibly cached; acceptor normally does not query KDC per request |
| Who holds the keytab? | Web keytab not required just to verify passwords | Server acceptor holds service keytab/acceptor credentials |
| How dangerous is credential compromise? | Web app compromise can expose user passwords | Keytab compromise allows impersonating the service/decrypting or processing tickets within key scope |
| Where does user identity proof come from? | KDC login result/JAAS Subject then local mapping | GSS ticket validation result then local mapping |
| Is local authorization needed? | **Yes** | **Yes** |
| Does it imply fresh MFA just completed? | **No**; depends on KDC/JAAS/pre-auth policy | **No**; SPNEGO alone does not prove MFA freshness |
| Does it automatically log out the whole domain? | **No** | **No** |

A successful `KerberosClient.login` can yield a JAAS Subject containing client-side Kerberos credentials for specialized use cases. **Never serialize a JAAS Subject or Kerberos credentials to the browser** and never grant the service blanket delegation to all backends. Using `KerberosMultiTier`/constrained delegation requires dedicated policies and service principal privileges.

## 8. Configuring Dependencies for Spring Security Kerberos

In Spring Security Kerberos **7.x**, the core modules use group `org.springframework.security`, for example:

~~~groovy
// build.gradle: Spring Boot/Spring Security project with managed versions
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-kerberos-core'
    implementation 'org.springframework.security:spring-security-kerberos-web'
}
~~~

If using only `KerberosAuthenticationProvider` outside web flows, the core module may suffice depending on dependencies. If using `SpnegoAuthenticationProcessingFilter`/HTTP, the web extension is required.

**Version matters greatly:** Spring Security Kerberos 7.x switched Maven coordinates to `org.springframework.security`. Spring Security 6.x/extension 2.x projects still use group `org.springframework.security.kerberos`. Never mix 6.x and 7.x JARs or pick random versions to fix `ClassNotFoundException`/`NoSuchMethodError`. Verify the BOM, dependency graph, Jakarta Servlet/Java versions, and matching docs.

Official source: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html .

### 8.1. Environment Prerequisites

Depending on the authentication path:

**KerberosClient Form:**

- Properly configured KDC/realm.
- DNS and `krb5.conf` or appropriate Java system properties.
- KDC permits username/password/JAAS login per policy.
- Application HTTPS and password/form protection policies.

**SPNEGO Service Ticket:**

- Client holds matching OS Kerberos credentials/TGT.
- Browser permits Integrated Authentication for the service.
- Service principal `HTTP/public-host@REALM` registered in KDC/AD.
- Service keytab matches principal/KVNO/enctype and is readable by the JVM.
- Consistent Java/Kerberos runtime, DNS, reverse proxy, and clock sync.
- `Authorization: Negotiate` header reaches the right server acceptor.
- Negotiated SPNEGO/GSS mechanism is actually Kerberos when required by policy (not silently NTLM).

## 9. Configuring KerberosAuthenticationProvider Standalone

Example bean configuration class in **Spring Boot/Spring Security Kerberos 7.x**. Imports and methods follow Spring Security Kerberos docs:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosClient;

@Configuration
public class KerberosPasswordProviderConfig {
    @Bean
    KerberosAuthenticationProvider kerberosPasswordProvider(
            UserDetailsService userDetailsService) {
        SunJaasKerberosClient client = new SunJaasKerberosClient();
        client.setDebug(false); // do not log credentials/JAAS details
        KerberosAuthenticationProvider provider =
            new KerberosAuthenticationProvider();
        provider.setKerberosClient(client);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }
}
~~~

This is a **configuration bean**, not a standalone Java application. To use it:

- Register the provider in an AuthenticationManager/SecurityFilterChain with `formLogin`.
- Supply a real `UserDetailsService`, never a dummy service granting ROLE_ADMIN to every user.
- Provide a `/login` page and CSRF token when using a custom form page.
- KDC/JAAS config must align with realm/user credentials.
- Ensure KerberosClient's auth result is the **authentication source**, never merely calling `userDetailsService.loadUserByUsername` and treating user existence as valid login.

**Do not copy JavaConfig snippets from docs that set `client.setDebug(true)` into production** without log governance, because Kerberos/JAAS debug logs can expose sensitive operational data.

### 9.1. Form Login Must Only Be Used Over HTTPS

A valid request might look like:

~~~http
POST /login HTTP/1.1
Host: portal.example.test
Content-Type: application/x-www-form-urlencoded

username=alice%40EXAMPLE.TEST&password=<sensitive-value>&_csrf=<csrf-token>
~~~

This is an illustrative structure **containing no real password**, not a full raw request. The server needs:

- Mandatory HTTPS and TLS trust policy.
- Valid CSRF token when using cookie-based forms.
- Zero password logging in access logs, APM, request body dumps, error pages, or exceptions.
- Brute-force protection and org-compliant lockout/step-up controls.
- Generic error responses on authentication failure to avoid excessive user enumeration.
- Never storing username/password in sessions/remember-me in unapproved ways.
- Erasing credentials where appropriate and avoiding retaining sensitive JAAS Subjects longer than needed.

### 9.2. UserDetailsService Can Fail After KDC Success

The KDC may confirm `alice@EXAMPLE.TEST` is valid while the local account is disabled or not yet onboarded. In that case, **do not issue an authenticated session** to that user, or handle JIT provisioning under explicit policy. `UserDetailsService` is the business mapper/authorizer, **not a substitute for KerberosClient checking passwords**.

## 10. Configuring KerberosServiceAuthenticationProvider Standalone

Example beans for website public FQDN `portal.example.test`:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class KerberosServiceTicketProviderConfig {
    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
            "HTTP/portal.example.test@EXAMPLE.TEST");
        validator.setKeyTabLocation(new FileSystemResource(
            "/run/secrets/kerberos/http.keytab"));
        validator.setDebug(false);
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceTicketProvider(
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

**You cannot run this snippet with `javac` alone**: it needs a Spring project, dependencies, realm configuration, a service principal, and a **real KDC/AD-issued keytab**. Without a test KDC, end-to-end SPNEGO handshakes cannot be verified.

### 10.1. Meaning of setTicketValidator

`SunJaasKerberosTicketValidator` is the Java/JGSS implementation for a **service acceptor**. It uses the service principal and keytab to verify Kerberos/SPNEGO tokens. Applications should never:

- Base64-decode Negotiate and trust any decoded username string.
- Parse a service ticket like JSON/JWT, assuming seeing `alice` means valid.
- Skip service principal matching or accept a TGT in place of a service ticket.
- Skip clock skew, ticket lifetime, authenticator replay, or GSS integrity checks.
- Accept another service's keytab or a keytab from an untrusted tenant.
- Trust an Internet-supplied `X-Forwarded-User` header to bypass the validator.

### 10.2. Why Doesn't the Ticket Validator Usually Call the KDC on Every Request?

The KDC issues the service ticket protected by the service's key. When the app receives an AP-REQ, JAAS/JGSS can **decrypt/verify it locally using the service keytab**, together with authenticator/session key/replay/time checks. Thus the KDC is not a required runtime API call **on every HTTP request**. If the browser already holds a cached service ticket, an SPNEGO login can succeed even without an immediate TGS exchange, depending on environment.

This also means disabling a user in the KDC **does not necessarily invalidate all already-issued service tickets immediately**. Near-real-time access revocation requires combining local session management, account status checks, ticket lifetime/policies, and matching authorization strategies.

## 11. SecurityFilterChain: SPNEGO-Only

If the application wants Kerberos HTTP SSO exclusively, you can build a SecurityFilterChain like this. This snippet uses the two beans from `KerberosServiceTicketProviderConfig` above:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class SpnegoOnlySecurityConfig {
    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider ticketProvider)
            throws Exception {

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(new ProviderManager(ticketProvider));
        filter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .authenticationProvider(ticketProvider)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .addFilterBefore(filter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

Key points:

- `SpnegoEntryPoint` responds with HTTP 401 and `WWW-Authenticate: Negotiate`.
- `SpnegoAuthenticationProcessingFilter` reads the header and creates the Authentication request; it **does not verify tickets by itself**.
- `ProviderManager(ticketProvider)` ensures the filter routes requests to **KerberosServiceAuthenticationProvider**.
- `setSecurityContextRepository(new HttpSessionSecurityContextRepository())` ensures successful auth persists in the local session for stateful web apps; the filter Javadoc warns the default may not save SecurityContext.
- `ChangeSessionIdAuthenticationStrategy` mitigates session fixation.
- `authorizeHttpRequests` enforces business constraints; the demo merely requires authentication for non-public URLs.
- No form-login provider is present; this is not "form-login with a hidden password prompt".

**Do not declare `@Bean SpnegoAuthenticationProcessingFilter` outside the filter chain without suppressing Servlet auto-registration**, as it may execute twice. With multiple SecurityFilterChains, place the filter in the exact matcher/chain covering routes that require Negotiate.

## 12. SecurityFilterChain: Combining SPNEGO and Form Fallback

An application serving both domain-joined machines holding Kerberos credentials and internal users on devices without integrated auth can combine **both providers**:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.kerberos.authentication.KerberosAuthenticationProvider;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;

@Configuration
public class SpnegoWithFormSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosAuthenticationProvider passwordProvider,
            KerberosServiceAuthenticationProvider ticketProvider)
            throws Exception {

        ProviderManager manager = new ProviderManager(
            passwordProvider, ticketProvider);

        SpnegoAuthenticationProcessingFilter spnegoFilter =
            new SpnegoAuthenticationProcessingFilter();
        spnegoFilter.setAuthenticationManager(manager);
        spnegoFilter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        spnegoFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/public/**", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll())
            .authenticationProvider(passwordProvider)
            .authenticationProvider(ticketProvider)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint("/login")))
            .addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Conditions for proper usage:**

1. Both provider beans must actually have configured `KerberosClient` and `KerberosTicketValidator`/`UserDetailsService`.
2. You must provide a **GET /login view/controller** to render the form and a matching POST login processing URL. This config **does not generate an HTML page automatically**.
3. `SpnegoEntryPoint("/login")` returns 401 Negotiate and optionally **forwards** to the fallback page; it **is not simply a direct HTTP 302 redirect**.
4. The form must carry a valid CSRF token and POST passwords over HTTPS.
5. SPNEGO-capable browsers can negotiate automatically; non-supporting browsers can use the form page depending on setup/agent behavior.
6. Session persistence must work across both form and SPNEGO. Test cookies/HttpSession/CSRF/session fixation on your Spring version.
7. If multiple providers support username/password, configure explicit precedence and fail-closed fallback; never let a KDC outage fall back to a weaker provider.
8. User identity from both paths must be scoped by **realm + principal**, checked for account enabled status, and mapped to authorities from a **consistent local policy**.
9. If UI/flows require separating SSO and form paths, use dedicated tested security matchers/filter chains rather than forcing a single shared chain.
10. Do not let the filter return 401 Negotiate to all API clients if APIs expect a different authentication scheme; design endpoints and client behavior cleanly.

**Avoid declaring all three SecurityFilterChain classes in sections 9–12 simultaneously in one sample project.** Sections 9 and 10 are two **provider bean configurations**, while sections 11 and 12 are **two alternative security chain designs**. Pick **one approach** or design multiple chains with clear matchers/order.

## 13. TGT, Service Ticket, SPNEGO Token, and JAAS Subject

Several data artifacts are easy to confuse:

| Artifact | Who Holds It? | Where Is It Used? | Direct Handling Provider? |
| --- | --- | --- | --- |
| **User password** | User / form request, KDC credential mechanism | `KerberosClient.login(...)` | **KerberosAuthenticationProvider** |
| **TGT** | Client OS/JAAS Subject/credential cache after AS exchange | KDC TGS to request service tickets | Never sent as a login header to the web app |
| **Service ticket** | Client obtained from TGS for one service SPN | AP-REQ to target service | **KerberosServiceAuthenticationProvider** via TicketValidator |
| **Authenticator** | Client generated using session key, paired with ticket | Kerberos AP-REQ/negotiation | Verified by JGSS/Kerberos library |
| **SPNEGO/GSS token** | Created by browser/OS | HTTP Authorization: Negotiate | SPNEGO filter + service ticket provider |
| **Service keytab** | Web service acceptor | Decrypts/verifies tickets for SPN | SunJaasKerberosTicketValidator |
| **JaasSubjectHolder** | Server-side JAAS login state | Can support multi-tier/credential handling | Present in KerberosClient/login result |
| **Spring SecurityContext** | Web app/session | Authorization across requests | Output of either flow after successful authentication |

**Do not treat a JAAS Subject as a user-visible session token.** A Subject can hold private credentials, TGT/service session keys, and sensitive data. Never place it in JSON, cookies, logs, or unencrypted shared caches.

### 13.1. Does a TGT Appear on the Form Path?

When `SunJaasKerberosClient.login(username,password)` succeeds, JAAS may populate a Subject holding Kerberos credentials depending on login/module settings. That is **completely different** from the web app accepting a browser's service ticket via SPNEGO. The form path is **the app actively acting as a client logging in with user credentials**; the service-ticket path is **the app passively acting as an acceptor**.

Depending on policy, retaining a JAAS Subject with user credentials on the web server introduces extra risk. **Never enable multi-tier/delegation** unless required and properly controlled.

### 13.2. SPNEGO Is Not Necessarily Always Kerberos

HTTP `Negotiate` can negotiate other GSS mechanisms, including **NTLM fallback** on some Windows setups. If policy permits only Kerberos, test the actual mechanism and configure clients/servers not to downgrade to NTLM. Never see `WWW-Authenticate: Negotiate` and assume "Kerberos is verified".

## 14. Authorization Boundary: Both Providers Need UserDetailsService

Whether username/password or a GSS token was verified by the Kerberos subsystem, **the application must decide whether the user may use the service and perform an action**.

Example:

~~~text
Kerberos identity: alice@EXAMPLE.TEST
Local user:        portal-user-17
Enabled:           true
Tenant:            finance
Granted authorities:
  ROLE_REPORT_READER
  ROLE_EMPLOYEE
~~~

Whereas:

~~~text
Kerberos identity: disabled@EXAMPLE.TEST
Local user:        portal-user-34
Enabled:           false
=> do not issue authenticated session/Authentication
~~~

Rules:

- Scope local identity by **username + Kerberos realm**, avoiding merging `alice@REALM_A` and `alice@REALM_B`.
- If using account linking/JIT provisioning, establish a clear contract and audit logging.
- Never trust `X-Remote-User`, email/headers/queries from the browser to override a KDC/GSS-verified username.
- Never turn group names, usernames, Host headers, or fake principals into dynamic admin roles.
- `UserDetailsService` may query LDAP/AD/local DB **to load user attributes and authorities**, yet finding a user record must never be treated as proof that a password or GSS token was valid.
- For sensitive resources, always enforce tenant/resource ownership independently of `isAuthenticated()`.
- If a user is disabled mid-session, implement session invalidation/account refresh outside the ticket-validation path.

**Kerberos authenticates the user; Spring Security authorizes based on principals/authorities and app policy.** Neither provider handles fine-grained business authorization on its own.

## 15. Standalone Java 17: Simulating Both Providers and Request Type Routing

This example **compiles on JDK 17+** without Spring Boot, KDC, AD, JAAS, GSS, or keytabs. It models the core decisions:

- `PasswordProvider` supports only `PasswordRequest`; simulates KDC password verification.
- `ServiceTicketProvider` supports only `TicketRequest`; simulates a GSS acceptor checking SPN, expiry, cryptographic proof, and replay.
- `ProviderManagerMock` selects the right provider by **request type**, never reading usernames or token text to guess the authentication flow.
- Both load permissions exclusively from **local account policy**, never from client-supplied token strings.
- Valid tickets for the HTTP SPN are accepted; **TGTs or CIFS tickets** are rejected by the web service.
- The same ticket with a **new authenticator** works while unexpired; **replaying the exact same authenticator** is rejected.
- Successful KDC verification for a locked local user is still denied.
- Wrong password, fake GSS proof, expired ticket, or unknown user must fail closed.

**Important warning:** this is a **FLOW SIMULATION**. `MockKdc` uses a fake password `lab-secret` in source, `cryptographicallyVerified` is a **simulated trusted verifier output** (never take such a boolean from HTTP/JSON), and the replay cache is just a single-JVM Set. **There is no real Kerberos cryptography**, no JAAS `login`, no GSS `acceptSecContext`, no session keys/keytabs, and no Kerberos protocol. This code **must never be used as a production authentication provider**.

File **KerberosProviderPathsDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class KerberosProviderPathsDemo {
    private static final String HTTP_SPN =
        "HTTP/portal.example.test@EXAMPLE.TEST";
    private static final Instant NOW =
        Instant.parse("2026-01-01T10:00:00Z");

    sealed interface Request permits PasswordRequest, TicketRequest {}

    record PasswordRequest(String user, char[] password)
            implements Request {}

    // Trusted metadata of a MOCK GSS verifier; never accept these fields
    // from an HTTP client in production.
    record TicketProof(String ticketId, String user, String spn,
                       Instant expiresAt, boolean cryptographicallyVerified,
                       String authenticatorId) {}
    record TicketRequest(TicketProof proof) implements Request {}

    record Account(boolean enabled, Set<String> roles) {}
    record Decision(boolean authenticated, String path,
                    String principal, Set<String> roles) {
        static Decision deny(String path) {
            return new Decision(false, path, "", Set.of());
        }
    }

    interface Provider {
        boolean supports(Request request);
        Decision authenticate(Request request);
    }

    static final Map<String, Account> ACCOUNTS = Map.of(
        "alice@EXAMPLE.TEST", new Account(
            true, Set.of("ROLE_REPORT_READER")),
        "disabled@EXAMPLE.TEST", new Account(
            false, Set.of("ROLE_REPORT_READER"))
    );

    static Decision allowLocalUser(String user, String path) {
        Account account = ACCOUNTS.get(user);
        if (account == null || !account.enabled()) {
            return Decision.deny(path);
        }
        return new Decision(true, path, user, account.roles());
    }

    static final class MockKdc {
        boolean login(String user, char[] password) {
            // Deliberately fake lab data. Production uses JAAS/KDC, not
            // a hard-coded local password or Arrays.equals.
            return (user.equals("alice@EXAMPLE.TEST")
                    || user.equals("disabled@EXAMPLE.TEST"))
                && Arrays.equals(password, "lab-secret".toCharArray());
        }
    }

    static final class PasswordProvider implements Provider {
        private final MockKdc kdc = new MockKdc();
        @Override public boolean supports(Request r) {
            return r instanceof PasswordRequest;
        }
        @Override public Decision authenticate(Request request) {
            if (!supports(request)) return Decision.deny("password");
            PasswordRequest r = (PasswordRequest) request;
            try {
                if (r.user() == null || r.password() == null
                        || !kdc.login(r.user(), r.password())) {
                    return Decision.deny("password");
                }
                return allowLocalUser(r.user(), "password");
            } finally {
                if (r.password() != null) {
                    Arrays.fill(r.password(), '\0');
                }
            }
        }
    }

    static final class MockGssAcceptor {
        private final Set<String> replayCache =
            ConcurrentHashMap.newKeySet();

        String validate(TicketProof p) {
            if (p == null || !p.cryptographicallyVerified()
                    || !HTTP_SPN.equals(p.spn())
                    || p.ticketId() == null || p.ticketId().isBlank()
                    || p.user() == null || p.user().isBlank()
                    || p.expiresAt() == null
                    || !NOW.isBefore(p.expiresAt())
                    || p.authenticatorId() == null
                    || p.authenticatorId().isBlank()) {
                return null;
            }
            // A real acceptor checks AP-REQ, session-key proof,
            // timestamp, service keytab, realm and GSS replay cache.
            if (!replayCache.add(
                    p.ticketId() + "/" + p.authenticatorId())) {
                return null;
            }
            return p.user();
        }
    }

    static final class ServiceTicketProvider implements Provider {
        private final MockGssAcceptor gss = new MockGssAcceptor();
        @Override public boolean supports(Request request) {
            return request instanceof TicketRequest;
        }
        @Override public Decision authenticate(Request request) {
            if (!supports(request)) return Decision.deny("service-ticket");
            String user = gss.validate(((TicketRequest) request).proof());
            return user == null ? Decision.deny("service-ticket")
                : allowLocalUser(user, "service-ticket");
        }
    }

    static final class ProviderManagerMock {
        private final Provider passwordProvider = new PasswordProvider();
        private final Provider ticketProvider = new ServiceTicketProvider();

        Decision authenticate(Request request) {
            if (passwordProvider.supports(request)) {
                return passwordProvider.authenticate(request);
            }
            if (ticketProvider.supports(request)) {
                return ticketProvider.authenticate(request);
            }
            return Decision.deny("unsupported");
        }
    }

    static TicketRequest ticket(
            String id, String user, String spn, boolean verified,
            String authenticator, Instant expiresAt) {
        return new TicketRequest(new TicketProof(
            id, user, spn, expiresAt, verified, authenticator));
    }

    public static void main(String[] args) {
        ProviderManagerMock manager = new ProviderManagerMock();
        PasswordProvider password = new PasswordProvider();
        ServiceTicketProvider service = new ServiceTicketProvider();

        TicketRequest initial = ticket(
            "st-1", "alice@EXAMPLE.TEST", HTTP_SPN, true,
            "auth-1", NOW.plus(Duration.ofMinutes(15)));
        System.out.println("formProviderSupportsPassword=" +
            password.supports(new PasswordRequest(
                "alice@EXAMPLE.TEST", new char[0])));
        System.out.println("formProviderDoesNotSupportTicket=" +
            !password.supports(initial));
        System.out.println("serviceProviderSupportsTicket=" +
            service.supports(initial));
        System.out.println("serviceProviderDoesNotSupportPassword=" +
            !service.supports(new PasswordRequest(
                "alice@EXAMPLE.TEST", new char[0])));

        Decision form = manager.authenticate(
            new PasswordRequest(
                "alice@EXAMPLE.TEST", "lab-secret".toCharArray()));
        System.out.println("formLoginAccepted=" + form.authenticated());
        System.out.println("wrongPasswordRejected=" +
            !manager.authenticate(new PasswordRequest(
                "alice@EXAMPLE.TEST", "bad".toCharArray())).authenticated());
        System.out.println("serviceTicketAccepted=" +
            manager.authenticate(initial).authenticated());
        System.out.println("sameAuthenticatorReplayRejected=" +
            !manager.authenticate(initial).authenticated());
        System.out.println("sameTicketFreshAuthenticatorAccepted=" +
            manager.authenticate(ticket(
                "st-1", "alice@EXAMPLE.TEST", HTTP_SPN, true,
                "auth-2", NOW.plusSeconds(900))).authenticated());
        System.out.println("tgtWrongSpnRejected=" +
            !manager.authenticate(ticket(
                "tgt-1", "alice@EXAMPLE.TEST",
                "krbtgt/EXAMPLE.TEST@EXAMPLE.TEST", true,
                "auth-tgt", NOW.plusSeconds(900))).authenticated());
        System.out.println("wrongServiceRejected=" +
            !manager.authenticate(ticket(
                "st-cifs", "alice@EXAMPLE.TEST",
                "cifs/files.example.test@EXAMPLE.TEST", true,
                "auth-cifs", NOW.plusSeconds(900))).authenticated());
        System.out.println("expiredTicketRejected=" +
            !manager.authenticate(ticket(
                "st-expired", "alice@EXAMPLE.TEST", HTTP_SPN, true,
                "auth-old", NOW.minusSeconds(1))).authenticated());
        System.out.println("fakeProofRejected=" +
            !manager.authenticate(ticket(
                "st-fake", "alice@EXAMPLE.TEST", HTTP_SPN, false,
                "auth-fake", NOW.plusSeconds(900))).authenticated());
        System.out.println("unknownLocalUserRejected=" +
            !manager.authenticate(ticket(
                "st-unknown", "unknown@EXAMPLE.TEST", HTTP_SPN,
                true, "auth-unknown", NOW.plusSeconds(900)))
            .authenticated());
        System.out.println("disabledLocalUserRejected=" +
            !manager.authenticate(ticket(
                "st-disabled", "disabled@EXAMPLE.TEST", HTTP_SPN,
                true, "auth-disabled", NOW.plusSeconds(900)))
            .authenticated());
        System.out.println("rolesComeFromLocalPolicy=" +
            form.roles().equals(Set.of("ROLE_REPORT_READER")));
        System.out.println("providerTypeConfusionRejected=" +
            !password.authenticate(ticket(
                "st-2", "alice@EXAMPLE.TEST", HTTP_SPN, true,
                "auth-3", NOW.plusSeconds(900))).authenticated());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 KerberosProviderPathsDemo.java
java KerberosProviderPathsDemo
~~~

**Exact stdout** (compiled and run with JDK 17):

~~~text
formProviderSupportsPassword=true
formProviderDoesNotSupportTicket=true
serviceProviderSupportsTicket=true
serviceProviderDoesNotSupportPassword=true
formLoginAccepted=true
wrongPasswordRejected=true
serviceTicketAccepted=true
sameAuthenticatorReplayRejected=true
sameTicketFreshAuthenticatorAccepted=true
tgtWrongSpnRejected=true
wrongServiceRejected=true
expiredTicketRejected=true
fakeProofRejected=true
unknownLocalUserRejected=true
disabledLocalUserRejected=true
rolesComeFromLocalPolicy=true
providerTypeConfusionRejected=true
~~~

### 15.1. Interpreting Results

- **formProviderSupportsPassword=true**: password provider accepts only the right request type.
- **serviceProviderSupportsTicket=true**: service-ticket provider accepts ticket requests.
- **formProviderDoesNotSupportTicket=true** and **serviceProviderDoesNotSupportPassword=true**: authentication paths are separated, preventing evidence from reaching the wrong provider.
- **formLoginAccepted=true**: right password in **mock KDC** and local user enabled.
- **wrongPasswordRejected=true**: wrong password is not authenticated.
- **serviceTicketAccepted=true**: service-ticket mock validation passes for the HTTP service principal.
- **sameAuthenticatorReplayRejected=true**: replay of the same authenticator is rejected.
- **sameTicketFreshAuthenticatorAccepted=true**: the same unexpired service ticket can participate in a new exchange with a fresh authenticator — unlike replaying raw tokens.
- **tgtWrongSpnRejected=true**: web service rejects credentials intended for `krbtgt`.
- **wrongServiceRejected=true**: a CIFS ticket cannot be used at the Portal.
- **expiredTicketRejected=true** and **fakeProofRejected=true**: invalid tokens are rejected.
- **unknownLocalUserRejected=true** and **disabledLocalUserRejected=true**: even after Kerberos verification, local user policy is enforced.
- **rolesComeFromLocalPolicy=true**: authorities come from the app's allowlist.
- **providerTypeConfusionRejected=true**: password provider rejects service ticket tokens.

**This code does not prove actual Spring Security providers ran**; it tests **routing architecture and rejection scenarios**. Integration tests with a real KDC/SPNEGO are required before production deployment.

## 16. Testing Mixed Authentication Methods in the Same Application

Some bugs appear only when **both providers** are present:

### 16.1. Form-Login Sends the Wrong Authentication Type

If a custom controller builds a `KerberosServiceRequestToken` from username/password instead of `UsernamePasswordAuthenticationToken`, the service ticket provider is selected erroneously. It can throw `GSSException` upon receiving text that is not a GSS token. **Never fix this by converting a password into bytes to fake an SPNEGO token.** Form-login must use the right authentication request and password provider.

### 16.2. Negotiate Header Routed Through Password Provider

If a custom filter turns a Base64 token string into a username, it bypasses real Kerberos proof and passes a "passwordless" user to KDC login. **Never do this.** The SPNEGO filter must pass **raw token bytes** into `KerberosServiceRequestToken` and the service-ticket provider.

### 16.3. Form Fallback Opens When KDC Is Unavailable

A policy flaw can happen if you register local `DaoAuthenticationProvider` alongside `KerberosAuthenticationProvider` and allow fallback when the Kerberos KDC errors out. A user with a local password could log in **without the KDC** even though the organization expects the KDC to be mandatory. If fallback is allowed, it requires approved policy, MFA/assurance, and account ownership — not merely "let the next provider try".

### 16.4. SPNEGO Failure Automatically Grants Anonymous Permissions

A 401 Negotiate when the browser lacks a TGT must never turn into **200 OK with ROLE_USER**. With a fallback form, the form must only render/sign in through **a fresh valid authentication flow**. Never build an Authentication from unverified browser data.

### 16.5. Session Switching from Provider A to Provider B

A user may log in via form and later send Negotiate with a different principal (e.g., a workstation logged into another domain account). Decide the policy:

- Keep the existing authenticated session or replace the principal?
- If replacing, require logout/re-login or confirmation?
- Is there a risk of session fixation or account confusion?
- Should `setSkipIfAlreadyAuthenticated(true)` be set on `SpnegoAuthenticationProcessingFilter`?
- How is account switching audited and which tenant's rights remain active?

This is a **product-specific** security decision. Never let the SPNEGO filter accidentally overwrite another user's session while keeping old local authorities.

### 16.6. Multiple Browsers and Client Types

An application may serve:

- Managed domain Chrome/Edge: SPNEGO.
- Off-domain Firefox/Chrome: form.
- Mobile/API clients: bearer tokens or another scheme, not Negotiate by default.
- Reverse proxy: with or without Kerberos termination, requiring a clear trust boundary.

A global `SpnegoEntryPoint` across all endpoints can make APIs return 401 Negotiate when clients expect a Bearer challenge; consider multiple `SecurityFilterChain` beans with separate matchers, entry points, and authorization policies.

## 17. Diagnosing Failures by Provider Path

| Symptom | Related Provider | Primary Likelihood | Safe Check |
| --- | --- | --- | --- |
| Form login fails even though browser SPNEGO works | Password provider | KDC/JAAS username-password path differs from existing credential cache | Filtered KerberosClient/KDC logs, realm, username format |
| Form returns bad credentials | Password provider | Wrong password, KDC rejection, invalid principal | Filtered auth logs, KDC codes |
| Form login never calls KDC | Password path/config | Form provider missing from manager; Dao provider intercepts first | ProviderManager, supports/ordering |
| Form succeeds yet user is locked | UserDetails/local auth | Enabled/locked policy not enforced | UserDetailsService, account status |
| GET /private returns 302 /login instead of 401 Negotiate | SPNEGO entrypoint | EntryPoint/form override | SecurityFilterChain and entry point |
| 401 Negotiate yet browser sends no token | Client | Browser policy, missing TGT, site lacks Integrated Auth | Klist, enterprise browser policy |
| Authorization: Negotiate sent yet 401 repeats | Service ticket provider | SPN/keytab/KVNO/enctype/GSS issue | Validator, keytab, AD SPN, GSS logs |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | Client TGS exchange | SPN absent in KDC | `kvno` and service account mapping |
| `KRB_AP_ERR_MODIFIED` | Service acceptor | Keytab/SPN/KVNO mismatch, duplicate AD SPN | KDC principal/keytab/AD |
| `KRB_AP_ERR_REPEAT` | Service acceptor | Authenticator replay/resubmitted GSS context | Replay cache, duplicate token handling |
| `KRB_AP_ERR_SKEW` | Kerberos | Clock drift beyond policy | NTP across KDC/client/server |
| `KRB_AP_ERR_TKT_EXPIRED` | Service acceptor | Service ticket expired | Klist, ticket times, policy |
| `GSSException: No valid credentials provided` | Service acceptor | Missing keytab or JVM cannot read it | Path, filesystem owner/permissions |
| `GSSException: Defective token` | SPNEGO | Altered token, mechanism/format mismatch, proxy mangled header | Header flow, mech, client/server versions |
| `GSSException: Channel binding mismatch` | SPNEGO/TLS | CBT/Extended Protection misaligned with TLS termination | Security/AD/TLS policy, no bypass |
| NTLM fallback | Browser/SSPI | Cannot resolve Kerberos SPN or client policy | Actual mech, Windows policy |
| Form succeeds, SPNEGO fails only in production | Service keytab/SPN | Form does not use acceptor keytab; SPNEGO does | Keytab/host/KVNO/ingress |
| SPNEGO succeeds, form fails | KDC/JAAS/password | Cached Kerberos credentials work, password path misconfigured | KDC login path, policy, user input |
| Both methods authenticate, API returns 403 | Local authorization | UserDetails/roles/resource policy denies | Authorities, tenant membership |
| User account switches after Negotiate | Session handling | Filter reauths with another principal or reuses session | SkipIfAlreadyAuthenticated, session policy |
| After logout browser immediately logs back in | OS credential cache | TGT/service ticket still cached | Local logout vs. domain SSO scope |
| Errors after service password rotation | Keytab KVNO | KDC issues tickets with new key, service holds old key | KVNO/enctype and rollout |
| Only one replica fails | Inconsistent keytab or config | Per-node mismatch | Deployment/node logs, secret version |

### 17.1. A Secret-Safe Debugging Sequence

1. Record whether the endpoint is **form** or **SPNEGO**.
2. Check **request type** and supporting provider; log class/category names, never credentials.
3. For form: check whether `KerberosClient.login` reaches the KDC, realm/user format, and JAAS error handling.
4. For SPNEGO: check `WWW-Authenticate: Negotiate`, whether the browser sends `Authorization: Negotiate`, and which SPN the client requested.
5. Run `klist`/`kvno` on an authorized test machine without exporting raw tickets.
6. On the service, check `klist -k -t -e /run/secrets/kerberos/http.keytab`, ownership, and KVNO/enctypes.
7. Check clock skew, AD SPN ownership, realm trust, and TLS termination/channel binding.
8. If Kerberos validation succeeds yet the app fails to log in, inspect `UserDetailsService` and session persistence.
9. If Authentication exists yet 403 occurs, inspect local authorities/tenant/resource ACLs; never weaken Kerberos security.
10. Never fix issues by disabling replay protection, trusting unverified HTTP headers, or logging passwords.

### 17.2. Sample Logs

~~~text
event=AUTH_FAILED
authPath=SPNEGO
requestTokenClass=KerberosServiceRequestToken
provider=KerberosServiceAuthenticationProvider
servicePrincipal=HTTP/portal.example.test@EXAMPLE.TEST
reason=SPN_OR_KEYTAB_MISMATCH
traceId=trace-a3b5
~~~

For the form path:

~~~text
event=AUTH_FAILED
authPath=FORM_KERBEROS
requestTokenClass=UsernamePasswordAuthenticationToken
provider=KerberosAuthenticationProvider
reason=KERBEROS_LOGIN_REJECTED
traceId=trace-f02d
~~~

Never log `Authorization: Negotiate`, Base64/GSS tokens, raw passwords, JAAS Subjects, keytab bytes, TGT/service session keys, or sensitive stack traces to public APM.

## 18. Negative Test Matrix

| Test Case | Input | Expected Result |
| --- | --- | --- |
| Valid form | username/password accepted by KDC, active local user | PASS |
| Form wrong password | Incorrect password | FAIL |
| Form missing password | Missing credential | FAIL |
| KDC offline on form | KerberosClient cannot reach AS/realm | Fail safely; no unapproved weaker-provider fallback |
| Valid SPNEGO | GSS token targeting exact SPN, matching keytab | PASS |
| User lacks TGT | Browser has no credential cache | 401/fallback per policy, no user created |
| Fake raw token | Base64 not representing a valid GSS/AP-REQ | FAIL |
| TGT used as web credential | Principal `krbtgt` instead of HTTP | FAIL |
| CIFS ticket sent to HTTP | `cifs/files` ticket | FAIL |
| Wrong host SPN | Client fetched HTTP/internal ticket for HTTP/public app | FAIL |
| KVNO/keytab mismatch | Service key differs from KDC-issued key | FAIL |
| Enctype mismatch | Server lacks compatible key | FAIL |
| Expired ticket | Kerberos endtime passed | FAIL |
| Stale authenticator | Timestamp beyond clock skew | FAIL |
| Raw token replay | Re-submitting identical AP-REQ/authenticator | FAIL |
| Valid service ticket + fresh authenticator | New valid exchange within lifetime | May PASS per Kerberos semantics |
| Wrong realm | Identity outside trusted realm | FAIL or policy-scoped identity |
| NTLM fallback under Kerberos-only policy | Negotiate selects NTLM | Policy FAIL |
| Form request sent to ticket provider | Unsupported request type | Not authenticated |
| Ticket request sent to password provider | Unsupported request type | Not authenticated |
| Unknown local user | KDC/GSS authenticates yet no local account, JIT disabled | FAIL |
| Disabled local user | KDC/GSS authenticates yet local account disabled | FAIL |
| User lacks role | Auth succeeds, resource requires role | 403; no privilege escalation |
| Principal switch across methods | Form alice, SPNEGO bob in same browser | Explicit reauth/session-switch policy |
| Provider order mismatch | Kerberos + Dao both support username/password | Test precedence/fallback |
| Form CSRF disabled | Unprotected POST /login | Security test FAIL |
| Password in access logs | Request body/URL logged | Security test FAIL |
| GSS token in logs | Authorization header exposed | Security test FAIL |
| Keytab in repo/container image | Secret committed/bundled | Security test FAIL |
| Duplicate AD SPN | Same SPN across multiple service accounts | Fail/investigate |
| HTTP without TLS | Negotiate used without protecting body/cookies | Security policy FAIL |
| Proxy identity spoofing | Client sends `X-Remote-User: alice` itself | Never accepted instead of GSS |
| Session fixation | Session ID unchanged after login per policy | Test and fix session strategy |
| Local logout | Spring session cleared while OS ticket remains | Auto-SPNEGO may recur; never claim domain logout |
| Multi-node mismatch | One instance holds old keytab | Test per node, no bypass |

**Real integration tests** against a test KDC/AD environment are mandatory before production: mock unit tests only verify routing and business logic, not real JAAS/GSS keys and tickets.

## 19. When to Choose Which Architecture?

### 19.1. SPNEGO Service-Ticket Provider Only

Best when:

- Internal intranet app where all clients hold enterprise Kerberos credentials.
- Goal is avoiding handling user passwords in the application.
- Domain SPNs/keytabs are IT-managed and browsers support Integrated Auth.
- Custom form fallback is unnecessary or handled at a separate access gateway.

Benefits: fewer password entry points; seamless domain SSO. Costs: requires SPN/keytab management, browser policies, and clock/realm/GSS troubleshooting.

### 19.2. KerberosAuthenticationProvider Only

Best when:

- Users must log in from machines without integrated browser auth.
- The organization permits the app to verify username/password via Kerberos KDC.
- The password flow has solid HTTPS, CSRF, rate limiting, and logging controls.
- Provisioning an HTTP SPN/keytab for SPNEGO is undesired or infeasible yet.

Benefits: independent of browser Negotiate. Costs: the app handles user passwords, carrying credential-handling risk and reducing passwordless SSO goals.

### 19.3. Combining Both

Best when:

- One group of users is domain-joined and another is not.
- Explicit security policy approves form fallback.
- The app can manage two authentication methods without introducing provider downgrades.

Requirements: explicitly define authentication types, provider ordering, entry points, session behavior, account linking, user authority mapping, and test failover cases.

### 19.4. Replacing with an OIDC/SAML Broker?

If the enterprise wants to offload direct KDC/password/SPNEGO handling from web apps, it can deploy a dedicated identity provider/broker and have apps use **OIDC Authorization Code** or **SAML**. Apps then need neither Kerberos provider, while the broker/gateway owns the Kerberos boundary. **That is a different architecture**, not merely swapping `AuthenticationProvider` classes.

## 20. Code Review and Operations Checklist

- [ ] Both flows clearly documented: **username/password** and **SPNEGO service ticket**.
- [ ] `KerberosAuthenticationProvider` configured with a `KerberosClient`, such as `SunJaasKerberosClient`.
- [ ] `KerberosServiceAuthenticationProvider` configured with a `KerberosTicketValidator`, such as `SunJaasKerberosTicketValidator`.
- [ ] `SpnegoAuthenticationProcessingFilter` converts Negotiate tokens into `KerberosServiceRequestToken` and targets the right AuthenticationManager.
- [ ] `UsernamePasswordAuthenticationFilter`/formLogin routes username/password to the right password provider.
- [ ] Service tickets are never treated as passwords, nor TGTs as web session credentials.
- [ ] `ProviderManager.supports`, provider ordering, and fallback policy verified for both request types.
- [ ] If Dao/LDAP also supports password requests, downgrade/KDC-unavailable behavior tested.
- [ ] `SpnegoEntryPoint` emits 401 Negotiate and optional form forward accurately without redirect loops.
- [ ] Form login uses HTTPS/CSRF/rate limiting; never logs passwords/JAAS Subjects.
- [ ] SPNEGO uses exact `HTTP/public-host@REALM` and a service keytab with valid KVNO/enctypes.
- [ ] Keytab never committed or stored in classpath/JARs/images.
- [ ] GSS acceptor validates ticket, authenticator, replay, clock skew, principal/realm, and SPN per policy.
- [ ] If Kerberos-only is required, tests verify unintended NTLM fallback is blocked.
- [ ] SecurityContextRepository/stateful session configured on the SPNEGO filter so subsequent requests stay authenticated.
- [ ] Session fixation policy applied to both form and SPNEGO.
- [ ] Local UserDetailsService checks active status, roles/tenant; never grants admin to all KDC users.
- [ ] Already-authenticated/used `KerberosServiceRequestToken` is never re-authenticated.
- [ ] Multi-tenant/cross-realm identity keys never collide across two realms sharing a username.
- [ ] Authentication success does not automatically authorize all business endpoints.
- [ ] Reverse proxy prevents clients from spoofing `Authorization`/`X-Remote-User` and TLS channel binding is designed properly.
- [ ] OS credential caches, user TGTs, service tickets, and Spring local sessions have clearly explained lifecycles.
- [ ] Local logout never promises clearing OS/domain Kerberos credentials.
- [ ] Maven/Gradle config uses matching Spring Security Kerberos 6.x or 7.x group/versions.
- [ ] Integration tests cover KDC/keytab, form, browser Negotiate, and negative cases.
- [ ] Separate monitoring tracks `FORM_KERBEROS` and `SPNEGO_SERVICE_TICKET`, with logs free of raw credentials.
- [ ] Runbook covers service keytab rotation, KVNO updates, rollback, and per-replica error tracking.
- [ ] Runbook covers KDC offline, clock skew, duplicate SPN, browser policy, and session/account confusion.

## 21. Self-Check Questions

**1. At which authentication step do KerberosAuthenticationProvider and KerberosServiceAuthenticationProvider differ?**

One verifies **username/password** via `KerberosClient`; the other verifies an **SPNEGO/service ticket** via `KerberosTicketValidator` using a keytab/service principal.

**2. Why isn't configuring KerberosAuthenticationProvider enough for automatic browser Negotiate SSO?**

Because browsers send a GSS token, not a password. You need `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, a TicketValidator, and a keytab.

**3. Does KerberosServiceAuthenticationProvider need Alice's password?**

No. It is a service acceptor verifying a Kerberos AP-REQ using service credentials, obtaining the principal via GSS validation.

**4. Why does the password provider need KerberosClient?**

So the application verifies username/password against the KDC via Kerberos/JAAS rather than comparing local password hashes.

**5. Can both providers share the same UserDetailsService?**

Yes. Once each method verifies identity, both can load local user/roles under a consistent realm/tenant policy.

**6. Is `KerberosServiceRequestToken` a TGT?**

No. It is a Spring Security Authentication object holding a GSS/SPNEGO token for the service acceptor; the TGT stays in the client credential cache/KDC TGS exchange.

**7. Can an SPNEGO token in the header be Base64-decoded to read and trust the username right away?**

No. It must pass through GSS/KerberosTicketValidator. Base64 is only transport encoding and proves nothing about token validity.

**8. Does `supports(UsernamePasswordAuthenticationToken.class)` mean the password is valid?**

No. `supports` only indicates the provider can handle that request type. `authenticate` determines the outcome after KerberosClient/KDC validation.

**9. Why does form login succeed while SPNEGO fails after changing the service account password?**

SPNEGO needs a keytab/KVNO matching the new KDC service key, whereas form username/password uses a different KerberosClient path. One working does not prove the other is configured properly.

**10. If a browser sends a CIFS ticket to an HTTP website, can it log in?**

No. Kerberos service tickets are bound to an SPN; the service acceptor must reject tickets not issued for it.

**11. Can a Kerberos service ticket only be used once?**

Not in the CAS ST sense. A Kerberos service ticket can be reused across AP exchanges while valid, yet **authenticator/GSS token replay** must be detected and rejected.

**12. Why can an authenticated Kerberos user still receive HTTP 403?**

Because local UserDetailsService/authorities or resource authorization denies the action. Authentication does not equal authorization.

**13. Should form fallback be enabled when the KDC is unreachable?**

Only if approved by security policy and the fallback offers equivalent or governed assurance. Never let provider ordering cause an unintended downgrade.

**14. What kinds of secrets must be protected across the two methods?**

Form login must protect user passwords/JAAS Subjects; SPNEGO must protect service keytabs and raw GSS tokens. Both require TLS, session security, and auditing.

**15. With `SpnegoEntryPoint("/login")`, does the browser always receive an HTTP 302 to the form?**

No. Per Javadoc, it emits **401 Negotiate** with an optional **forwardUrl** to the fallback form; do not confuse it with a simple 302 redirect.

**16. After local logout, can a user immediately log back in automatically via SPNEGO?**

Possibly, because the OS Kerberos TGT/service ticket remains cached. Local HttpSession logout differs from domain sign-out.

**17. Why must UserDetailsService never decide whether KDC credentials are valid?**

It handles local user mapping/authorities. Kerberos evidence must be verified beforehand by **KerberosClient** or **KerberosTicketValidator**.

**18. When should you consider OIDC instead of the two Kerberos providers?**

When the application wants to delegate KDC/SSO integration to a dedicated identity broker. The broker authenticates Kerberos while the app acts as an OIDC RP; that is a different federation architecture.

## 22. Official References

- Spring Security, **Spring and Spring Security Kerberos**, Authentication Provider, Spnego Negotiate, combined provider samples: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Spring Security, **Introduction to Kerberos**, Spring Security 7 dependency coordinates, Java 17/version compatibility: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security Javadoc, **KerberosAuthenticationProvider**, `setKerberosClient`, `setUserDetailsService`, and `supports`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosAuthenticationProvider.html
- Spring Security Javadoc, **KerberosServiceAuthenticationProvider**, Kerberos service ticket/SPNEGO validation, `setTicketValidator`, UserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- Spring Security Javadoc, **SunJaasKerberosClient**, `login(String username, String password)` using JAAS: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosClient.html
- Spring Security Javadoc, **KerberosServiceRequestToken**, unauthenticated byte token, authenticated validation result, re-authentication warning: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceRequestToken.html
- Spring Security Javadoc, **KerberosUsernamePasswordAuthenticationToken**, JaasSubjectHolder for multi-tier: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosUsernamePasswordAuthenticationToken.html
- Spring Security Javadoc, **SpnegoAuthenticationProcessingFilter**, reading header and setting SecurityContextRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Spring Security Javadoc, **SpnegoEntryPoint**, 401 Negotiate and form fallback forward: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html
- Spring Security, **Authentication Architecture**, ProviderManager, supports(), provider ordering: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- IETF **RFC 4120, Kerberos V5**, AS/TGS/AP exchange, service tickets, authenticators/replay: https://www.rfc-editor.org/rfc/rfc4120
- IETF **RFC 4559, SPNEGO-based Kerberos and NTLM HTTP Authentication**, `Authorization: Negotiate` and 401 challenge: https://www.rfc-editor.org/rfc/rfc4559
- MIT Kerberos, **kinit** and **klist**, credential cache/service principal troubleshooting: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kinit.html and https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html

**Summary:** **`KerberosAuthenticationProvider` verifies username/password using `KerberosClient`**, suitable for form login/KDC verification. **`KerberosServiceAuthenticationProvider` verifies service tickets/SPNEGO using `KerberosTicketValidator` and a service keytab**, suitable for browser Integrated Authentication. Pick the provider by **request type and trust boundary**, not by the generic word "Kerberos". After either, Spring Security must still load **local user/authorities**, persist SecurityContext appropriately, and enforce **business authorization**; never trust unverified raw headers, tokens, or user input.