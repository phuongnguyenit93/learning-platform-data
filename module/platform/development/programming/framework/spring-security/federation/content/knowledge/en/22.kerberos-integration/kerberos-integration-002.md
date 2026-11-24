# SpnegoEntryPoint and the WWW-Authenticate: Negotiate Response

**SPNEGO (Simple and Protected GSS-API Negotiation Mechanism)** allows browsers and web applications to negotiate authentication mechanisms over HTTP; in enterprise environments, it typically uses **Kerberos** to implement **Integrated Windows Authentication (IWA)**, enabling domain-logged-in users to access applications without re-entering their passwords. In **Spring Security - federation**, the **Spring Security Kerberos** extension provides the `SpnegoEntryPoint` class to emit the appropriate HTTP authentication challenge: **`401 Unauthorized`** with the **`WWW-Authenticate: Negotiate`** header.

Key point: **`SpnegoEntryPoint` does not verify Kerberos tickets and does not log users in.** It only asks the client to initiate (or continue) **HTTP Negotiate authentication**. Upon receiving the challenge, the browser may request a service ticket from the KDC/Active Directory and send **`Authorization: Negotiate <base64-token>`** on the next request. **Decrypting/verifying the token** belongs to `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, and `KerberosTicketValidator` (commonly `SunJaasKerberosTicketValidator`) for the respective Spring Security Kerberos version.

This lesson explains **the role of 401/headers, the challenge–response cycle, the difference between 401 and 403, SecurityFilterChain configuration, fallback login, SPN/keytab/DNS/browser preconditions, proxies, and security tests**. Illustrative Spring code is clearly separated from a **standalone runnable Java 17 program** simulating the HTTP state machine.

> **Security principle:** authenticate the user only when the server **has successfully validated the GSS/SPNEGO token for the right service principal and trust policy**, and the application has also verified account status/authorities. **Never treat merely seeing an `Authorization: Negotiate ...` string as proof of authentication.**

## 1. Context: When Is SPNEGO/Kerberos Useful?

An enterprise has:

- **KDC / Active Directory** managing a realm, for example `CORP.EXAMPLE.ORG`.
- A domain-joined user machine with a valid TGT, where the browser allows **Integrated Authentication** for `https://portal.example.org`.
- A Spring Boot Servlet backend behind a reverse proxy; the service has an **HTTP service principal** `HTTP/portal.example.org@CORP.EXAMPLE.ORG` and a matching **keytab** to decrypt/verify Kerberos AP-REQs.
- User `alice@CORP.EXAMPLE.ORG` is Kerberos-authenticated, yet the Portal still needs to look up the **local account**, check whether it is locked, map authorities, and enforce access control.

When the user accesses `/reports`, Spring Security requires authentication. The browser is prompted with the Negotiate scheme, automatically acquires a service ticket (if allowed and credentials exist), and sends the token to the Portal. The user **does not hand their password to the Portal**. This is a form of SSO between a Windows/Kerberos realm and a web application, but it is **not identical to SAML, OIDC, or CAS**; each protocol has distinct credentials, messages, and trust boundaries.

### 1.1. Roles

| Component | Role | What Must Be Verified |
| --- | --- | --- |
| **Browser/HTTP client** | Receives challenge, sends Negotiate token. | Browser policy permits automatic Kerberos use for the exact URL. |
| **KDC/AD** | Issues TGTs and service tickets for SPNs. | Realm trust, valid account/service principal, lifetime/clock policy. |
| **SPN** `HTTP/portal.example.org` | Kerberos identity of the web service. | Matches the FQDN the user visits; do not confuse `HTTP` with cleartext HTTP. |
| **Server keytab** | Holds keys for the SPN to accept service tickets. | File permissions, KVNO/enctype, account, rotation, never exposed in builds/logs. |
| **`SpnegoEntryPoint`** | `AuthenticationEntryPoint` emitting the challenge. | HTTP 401 and `WWW-Authenticate: Negotiate`. |
| **`SpnegoAuthenticationProcessingFilter`** | Reads `Authorization: Negotiate`, creates the authentication request. | Never treat the raw header/username as already verified. |
| **`KerberosServiceAuthenticationProvider`** | Authenticates the request token via the ticket validator. | SPNEGO/GSS-API validation before loading the user. |
| **`KerberosTicketValidator`** | Verifies the token for the server principal/keytab. | Kerberos validation, handling replay/clock/crypto per GSS/Kerberos. |
| **`UserDetailsService`** | Loads the local user and `GrantedAuthority` set. | Locked/disabled status, tenant, Portal-specific permissions. |
| **`SecurityContextRepository`** | Persists auth state across requests when configured. | Session fixation, lifetime, correctness across multiple nodes. |

## 2. What Do HTTP 401 and WWW-Authenticate: Negotiate Mean?

HTTP authentication uses a **challenge–response** mechanism:

- The server returns **`401 Unauthorized`** when a request hits a protected area without accepted credentials.
- The **`WWW-Authenticate`** header indicates the authentication scheme the server supports. For SPNEGO, the scheme is **`Negotiate`**.
- A supporting and permitted client retries the request with **`Authorization: Negotiate <base64-GSSAPI-token>`**.
- The server verifies the token via GSS-API/Kerberos, completing or requesting another handshake round as required by the protocol.
- Once authenticated and authorized, the server returns 2xx; if **authenticated but lacking permissions**, the application usually returns **403 Forbidden**, rather than looping 401 challenges indefinitely.

Initial challenge example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
Cache-Control: no-store
Content-Length: 0
~~~

**An empty data portion in `WWW-Authenticate: Negotiate` is normal on the first round.** It does not mean a ticket is missing due to a server bug. Per RFC 4559, a continuation may return the header carrying a GSS-API token for the client to process further.

The client may send:

~~~http
GET /reports HTTP/1.1
Host: portal.example.org
Authorization: Negotiate YIIF...BASE64_GSSAPI_TOKEN...
Cookie: JSESSIONID=optional-existing-session
~~~

The token above is an **illustrative placeholder**, not a real credential. Base64 is merely an **encoding**, offering no confidentiality of its own. **Never log raw Authorization headers into logs, tracing, analytics, bug reports, or frontend consoles.**

### 2.1. Why Isn't the Challenge a Login Form?

Form login tends to look like:

~~~text
GET /reports -> 302 Location: /login -> browser renders form
~~~

Negotiate tends to look like:

~~~text
GET /reports -> 401 WWW-Authenticate: Negotiate
browser looks up credentials / service ticket
GET /reports + Authorization: Negotiate <token>
server validates -> 200, or continuation/failure
~~~

With HTTP authentication, **401 is a valid starting point**, not necessarily an incident. Monitoring tools that alert purely on "401 seen" can fire false positives, because an unauthenticated browser's first request intentionally receives a 401. Measure the full **401 challenge → token retry → authentication success/failure** ratio, not 401 counts in isolation.

### 2.2. How Do Kerberos Tickets Differ from HTTP Authorization Headers?

- The **TGT** lets the client request service tickets from the KDC; browsers do not send the raw TGT to the web app.
- The **Service ticket** is issued by the KDC for the service principal `HTTP/portal.example.org`.
- The **GSS-API/SPNEGO token** is carried in `Authorization: Negotiate`, and may contain Kerberos tokens tied to the service ticket and negotiation.
- The **HTTP session cookie** is local state created by the application after authentication (if session-based), not a TGT or service ticket.
- **HTTP authentication negotiation** may require multiple HTTP exchanges; sending a username once is not enough.

Kerberos/SPNEGO avoids sending the user's password to the Portal, yet you must still protect **tokens, keytabs, browser policies, DNS/SPNs, TLS, and local authorization**.

## 3. Exact Role of SpnegoEntryPoint

The class resides in:

~~~java
org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint
~~~

and implements:

~~~java
org.springframework.security.web.AuthenticationEntryPoint
~~~

When an unauthenticated request needs access to a protected resource, Spring Security's `ExceptionTranslationFilter` invokes `AuthenticationEntryPoint.commence(...)` in the `SecurityFilterChain` flow. With the default `SpnegoEntryPoint`, the core logic is:

~~~java
response.addHeader("WWW-Authenticate", "Negotiate");
response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
response.flushBuffer();
~~~

**This is an illustrative API logic excerpt, not the full class.** Real responses may include extra headers added by Spring/container/proxy; what matters are the Negotiate header and HTTP 401.

**`SpnegoEntryPoint` does NOT:**
- Create or verify Kerberos AP-REQs, read keytabs, or contact the KDC.
- Check whether principal `alice@REALM` belongs to an admin group.
- Place an authenticated `Authentication` into the `SecurityContext` by inferring it from an HTTP header.
- Replace `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, or `SunJaasKerberosTicketValidator`.
- Guarantee that every browser supports or chooses to send Negotiate.
- Issue an HTTP session or handle logout/revocation once Kerberos authentication succeeds.

### 3.1. Constructors of SpnegoEntryPoint

Per the Spring Security Kerberos JavaDoc:

| Constructor | Behavior |
| --- | --- |
| `new SpnegoEntryPoint()` | Returns **401 + `WWW-Authenticate: Negotiate`** only, no form fallback. |
| `new SpnegoEntryPoint("/login")` | Returns **401 + Negotiate** and **server-side forwards** to `/login` for fallback content. |
| `new SpnegoEntryPoint("/login", HttpMethod.GET)` | Same as above, but the request is forwarded using the specified method. |

In versions providing the `forwardMethod` constructor, the method parameter can force the forwarded request to be treated as **GET** instead of preserving the original POST (semantics must be considered). **The forward path is relative to the web application context, starting with `/`; it must never be an absolute URL.** Never read `forwardUrl` from a client query parameter.

**Common misconception:** `new SpnegoEntryPoint("/login")` uses **`RequestDispatcher.forward`**, **not** `302 Location: /login`. In the official implementation, the status remains **401** and the **`WWW-Authenticate: Negotiate`** header is added before forwarding. Supporting browsers typically try Negotiate; non-supporting clients may see the fallback body. For the fallback to be usable, you must **build a dedicated login endpoint/page body** and form authentication mechanism, not just instantiate the entry point.

### 3.2. 401 vs. 403 in Spring Security

| State | Typical Outcome | Cause |
| --- | --- | --- |
| **Unauthenticated** requesting `/reports`. | **401 + Negotiate**. | `AuthenticationEntryPoint` invites authentication. |
| Browser sends malformed token/wrong service principal. | Authentication fails; may **re-challenge 401** or invoke error handler per config. | Cannot prove Kerberos identity. |
| Authenticated as `alice` but lacks `reports:read`. | **403 Forbidden**. | Authorization failure, not missing credentials. |
| Local user `DISABLED` despite valid Kerberos ticket. | Authentication failure / deny, depending on flow. | Local policy admission failure. |
| Endpoint `/public/**` configured with `permitAll`. | 200/public response, no challenge required. | Kerberos not needed for this route. |
| Valid `OPTIONS` CORS preflight. | Handled by CORS policy, typically skips Negotiate handshake. | Prevents browser CORS from being blocked by useless 401s. |

**Do not fix 403 by emitting infinite 401 challenges**; authorization is separate from authentication. If a local account lacks a role, fix entitlements/mappers per policy rather than loosening `.anyRequest().permitAll()`.

## 4. End-to-End Flow: From Challenge to Kerberos Authentication

~~~text
Browser                        Spring Security                   KDC/AD
  |                                 |                              |
  | GET /private                    |                              |
  |-------------------------------->|                              |
  |                                 | check SecurityContext        |
  |                                 | anonymous + protected route  |
  |                                 | ExceptionTranslationFilter   |
  |<--------------------------------|                              |
  | 401 WWW-Authenticate: Negotiate |                              |
  |                                 |                              |
  | Browser policy: trust URL       |                              |
  | Existing TGT or OS credentials  |                              |
  | request service ticket for      |                              |
  | HTTP/portal.example.org         |                              |
  |--------------------------------------------------------------->|
  |<---------------------------------------------------------------|
  | service ticket for SPN          |                              |
  |                                 |                              |
  | GET /private                    |                              |
  | Authorization: Negotiate <GSS token>                           |
  |-------------------------------->|                              |
  |                SpnegoAuthenticationProcessingFilter             |
  |                   creates KerberosServiceRequestToken          |
  |                   -> AuthenticationManager                      |
  |                   -> KerberosServiceAuthenticationProvider      |
  |                   -> SunJaasKerberosTicketValidator             |
  |                   -> JAAS/GSS accept service ticket with keytab |
  |                   -> principal alice@CORP.EXAMPLE.ORG          |
  |                   -> UserDetailsService -> local status/roles  |
  |                   -> authenticated Authentication              |
  |<--------------------------------|                              |
  | 200 /private (if allowed)       |                              |
~~~

**Note:** this diagram depicts a single successful Kerberos token round-trip; **SPNEGO/GSS** can require exchanging multiple tokens. The server sometimes returns **`WWW-Authenticate: Negotiate <response-token>`** for the client to complete mutual authentication. Do not hardcode clients around the assumption of "strictly one 401 then 200", and do not use a plain JSON body to force a browser to treat negotiation as succeeded.

### 4.1. Separating Responsibilities Across 4 Classes

| Class | Input | Output / Responsibility |
| --- | --- | --- |
| `SpnegoEntryPoint` | Spring authentication entry point invoked. | **401 + header challenge** to the HTTP client. |
| `SpnegoAuthenticationProcessingFilter` | `Authorization: Negotiate <base64>`. | Extracts structurally valid token, dispatches authentication request via manager. |
| `KerberosServiceAuthenticationProvider` | `KerberosServiceRequestToken`. | Calls validator, obtains Kerberos principal, calls `UserDetailsService`, builds authenticated token. |
| `SunJaasKerberosTicketValidator` | GSS-API token, server SPN/keytab. | Validates Kerberos via JAAS/GSS; does not perform local RBAC. |

Some guides use the word "ticket" for both the HTTP Negotiate token and the Kerberos AP-REQ. In application code, **never slice Base64 and parse the username yourself**. Parsing/accepting the GSS context belongs to the tested validator/framework.

### 4.2. What Do Client-Side Headers Look Like?

~~~http
GET /private HTTP/1.1
Host: portal.example.org
Authorization: Negotiate YII...opaque-base64-gss-token
~~~

In a server-to-client continuation token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate YII...server-gss-continuation
~~~

In some mutual authentication flows, a success response may also carry a token:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate YII...server-final-gss-token
Content-Type: application/json
~~~

The strings after `Negotiate` here are **placeholders**, unusable for real authentication. Per RFC 4559, the initial challenge typically carries **no** gssapi-data; continuation or final steps **may** carry data. Do not treat `WWW-Authenticate` on a 200 response as an identity token to store arbitrarily in the browser.

## 5. Preconditions for the Browser to Actually Answer Negotiate

Seeing **401 + Negotiate** is only a **necessary condition**, not a sufficient one.

1. The machine/browser has valid **Kerberos credentials** or can obtain credentials from the login session.
2. The **URL host** and website zone are permitted by browser/OS policy to send Integrated Authentication. Browsers typically negotiate automatically only for allowlisted/intranet/trusted URIs, not arbitrary Internet hosts.
3. DNS/hostname of the URL resolves to the **correct SPN**; the KDC has service principal `HTTP/portal.example.org` bound to the right account and the service's keytab.
4. Client/KDC/server clocks are synchronized within Kerberos limits, and realm trust and DNS SRV/KDC discovery work.
5. The HTTP challenge is not stripped by a proxy/gateway; the browser's Authorization request reaches the right backend; `WWW-Authenticate` responses are preserved.
6. HTTPS certificate, hostname, SNI, and trusted proxy configuration match.
7. The server acceptor has a **readable keytab** with the right encryption keys/KVNO; local user mapping does not unexpectedly drop the domain/realm.
8. No captive portal/SSO gateway middlebox returns 302 instead of the challenge or rewrites `WWW-Authenticate` to Basic.
9. The browser is not in a privacy/anonymous/Incognito profile or network zone blocking SSO, and the user has not explicitly disabled Negotiate.

### 5.1. SPN HTTP/fqdn Differs from URL Scheme

Example:

~~~text
Public URL:      https://portal.example.org
Kerberos SPN:    HTTP/portal.example.org@CORP.EXAMPLE.ORG
KDC realm:       CORP.EXAMPLE.ORG
Service account: svc-portal
Keytab:          /etc/security/keytabs/portal-http.keytab
~~~

The `HTTP/` prefix in the SPN is a **Kerberos service class**; it does not mean the web app must run **cleartext HTTP**. **HTTPS remains mandatory in production** to protect cookies, exchanged tokens, and mitigate MITM/captive proxies.

When using a DNS alias `portal.corp.example.org` → `portal.example.org` or a load balancer, **the SPN/KDC/SSO policy must match the host the client actually uses**. Browsers and Kerberos libraries may canonicalize hostnames differently; inspect real requests/KDC logs rather than guessing aliases. Never fix `KRB_AP_ERR_MODIFIED` by disabling ticket validation.

### 5.2. NTLM Fallback and Downgrade

**Negotiate is the HTTP authentication scheme name for SPNEGO, not a private name for Kerberos.** Depending on Windows/browser/OS and library settings, SPNEGO can negotiate **Kerberos or NTLM**. If the organization requires **Kerberos-only**, client/OS/server policies and the validator must **prevent NTLM fallback**, rather than merely checking that the header contains the word `Negotiate`.

Example of two requests that both carry a Negotiate header yet **differ in underlying mechanism**:

~~~text
Authorization: Negotiate <SPNEGO-token-with-Kerberos>
Authorization: Negotiate <SPNEGO-token-with-NTLM>
~~~

These are notations, not real headers. Do not classify tokens with Base64 prefix regexes; use GSS/provider/authentication systems capable of verifying and reporting the actually negotiated mechanism. If Spring Kerberos is configured to accept only Kerberos, do not validate NTLM by bypassing checks. **Do not open an unprotected Basic fallback just so "every machine can log in".**

## 6. Spring Security Kerberos: Modules and Version Caveats

This SPNEGO integration belongs to the **Spring Security Kerberos extension**, not enabled automatically by `spring-boot-starter-security`. Artifacts may include:

~~~xml
<!-- Declare dependencies in a Maven project with appropriate version management -->
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-client</artifactId>
</dependency>
~~~

**This is an illustrative `pom.xml` fragment.** Pick an extension release compatible with **Spring Security core**, the Java runtime, and the Servlet namespace. Modern versions use `jakarta.servlet`, while older articles/branches may use `javax.servlet`; **never mix Jakarta/Javax binaries** and never guess a version into production. Inspect the dependency tree, BOM, API JavaDoc for your exact version, and run end-to-end tests with a real KDC.

### 6.1. Bean Emitting the 401 Challenge

~~~java
@Bean
SpnegoEntryPoint spnegoEntryPoint() {
    return new SpnegoEntryPoint();
}
~~~

When supporting non-domain browsers as well, consider:

~~~java
@Bean
SpnegoEntryPoint spnegoEntryPoint() {
    return new SpnegoEntryPoint("/login");
}
~~~

**These two beans are mutually exclusive alternatives**; do not declare both with the same name. With the fallback, **401 + Negotiate still applies**, and `/login` content is **forwarded internally**. Ensure the fallback URL is accessible without causing an authentication loop or method mismatch. Do not turn `/login` into a place that "self-issues a Principal" from email/password without a valid authentication provider.

### 6.2. Kerberos Ticket Validator Using a Keytab

Illustrative bean:

~~~java
@Bean
SunJaasKerberosTicketValidator kerberosTicketValidator() {
    SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
    validator.setServicePrincipal(
            "HTTP/portal.example.org@CORP.EXAMPLE.ORG");
    validator.setKeyTabLocation(
            new FileSystemResource(
                "/etc/security/keytabs/portal-http.keytab"));
    validator.setDebug(false);
    return validator;
}
~~~

Imports in the Spring project:

~~~java
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
~~~

**A keytab is a sensitive credential**: mount it from a secret manager with restricted filesystem permissions; never commit it to git/docker images/public classpath. The server service principal must **have an active key inside the keytab**, matching the KVNO/encryption types of the account in the KDC. In several environments, a `file:/...` path is preferred over a classpath resource when JAAS needs real file access. Never enable `setDebug(true)` in production because Kerberos/GSS logs can expose sensitive details.

### 6.3. Verification Provider and User Mapping

~~~java
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
~~~

Imports:

~~~java
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
~~~

`KerberosServiceAuthenticationProvider` runs **GSS ticket validation** and then loads `UserDetails` and `GrantedAuthority`. A Kerberos-authenticated `alice@CORP.EXAMPLE.ORG` **does not mean** she has been granted `ROLE_ADMIN` or access to every tenant. `UserDetailsService` must map the realm/canonical username to a stable local account, verify `disabled/locked` status, and enforce managed entitlements.

### 6.4. SpnegoAuthenticationProcessingFilter

~~~java
@Bean
SpnegoAuthenticationProcessingFilter spnegoFilter(
        KerberosServiceAuthenticationProvider provider) {

    SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
    filter.setAuthenticationManager(new ProviderManager(provider));
    return filter;
}
~~~

Imports:

~~~java
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
~~~

This is a **partial configuration**. You must **register the filter in the right SecurityFilterChain**, supply a `UserDetailsService`, Java runtime/KDC config, and decide the session strategy/context repository as needed.

**Important caveat for recent versions:** `SpnegoAuthenticationProcessingFilter` provides options such as `setSkipIfAlreadyAuthenticated(true)` (default), `setSessionAuthenticationStrategy(...)`, `setSecurityContextRepository(...)`, `setSuccessHandler(...)`, and `setFailureHandler(...)`. Check defaults for your running version; **do not assume every request has auth saved into HttpSession just because a Negotiate header was seen once**. Choose session persistence or per-request SPNEGO explicitly to safeguard expected behavior.

### 6.5. Sample SecurityFilterChain

In Spring Boot Servlet:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        SpnegoEntryPoint entryPoint,
        SpnegoAuthenticationProcessingFilter spnegoFilter)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**", "/error").permitAll()
            .requestMatchers("/admin/**").hasAuthority("app:admin")
            .anyRequest().authenticated())
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(entryPoint))
        .addFilterBefore(spnegoFilter,
            UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
~~~

Imports:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
~~~

The `securityFilterChain` example is a **method in a Spring `@Configuration` with `@Bean`**, not standalone Java SE code. The `entryPoint` and `spnegoFilter` beans must be declared as shown above, alongside Spring Boot Web/Security and Kerberos extension dependencies. Depending on the app, filter placement and the HTTP entry point may need a dedicated `RequestMatcher` so Negotiate is not emitted on OAuth APIs or admin-only exceptions.

**Code note:** with SPNEGO, `UsernamePasswordAuthenticationFilter.class` is typically an **ordering anchor** in the chain, not an implication that password authentication is enabled. Inspect the live chain with redacted Spring Security debug logging, avoiding registering the same filter in both the Servlet container and the Spring Security chain where tokens would be processed twice.

### 6.6. Why EntryPoint Alone Is Not Enough

If you only configure:

~~~java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(new SpnegoEntryPoint()));
~~~

Spring can still return the 401 challenge, yet **no filter/provider may be listening for `Authorization: Negotiate`** to authenticate it. The usual outcome is **401 → browser sends token → still 401**, looking like an infinite loop. You must wire filter + manager/provider + validator + local user mapping together.

Conversely, having only `SpnegoAuthenticationProcessingFilter` without `SpnegoEntryPoint` may leave the browser **never receiving an HTTP Negotiate challenge** on protected routes, depending on the chain's default entry point. Client "preemptive Authorization" exists, but you should never rely on it when designing web SSO.

## 7. Form Login Fallback: Internal Forward with Status 401

`SpnegoEntryPoint("/login")` is useful when serving two user groups:

- Domain-joined machines whose browsers support IWA/SPNEGO.
- Personal/non-domain machines or clients without Kerberos support that need a form login fallback backed by **another policy-compliant provider**, such as LDAP authentication over TLS or OIDC on a separate flow.

### 7.1. Response Sequence

~~~text
GET /reports (anonymous)
   |
   v
Spring EntryPoint.commence
   |
   +-- HTTP status = 401
   +-- WWW-Authenticate = Negotiate
   +-- RequestDispatcher.forward("/login")
        |
        +-- HTML body of fallback page (app-defined)
        +-- status/header remain 401 + Negotiate
~~~

**Not a 302 redirect.** When a browser does not support Negotiate, it can render the forwarded fallback page. When it does, it usually tries Kerberos first. Browsers differ in their UI behavior on 401 challenges or auth scheme selection; run E2E tests with target clients.

### 7.2. Fallback Must Not Weaken Authentication

1. The `/login` route must be accessible without causing a `401 → forward /login → authentication entry point → ...` loop.
2. If `/login` serves HTML, emit **anti-cache headers** and XSS defenses; never embed Kerberos tokens in HTML.
3. If using a password form, serve solely over **HTTPS**, with CSRF protection, rate limiting, lockout/abuse controls, and a real credential-verifying provider.
4. Never use `?username=alice` query parameters or an `X-Remote-User` header lacking a trusted proxy boundary as an authenticated fallback.
5. On an original POST request, a server-side forward preserving the method can break handlers; versions supporting the `(String, HttpMethod)` constructor can force `GET` for the fallback, though API semantics/CSRF must be tested. For APIs, **401 JSON/Negotiate** is usually cleaner than forwarding HTML.
6. Do not mix `WWW-Authenticate: Negotiate` and Basic without a real use case and TLS; browsers may pick an unintended mechanism.
7. If Kerberos-authenticated but lacking an app role, return **403** per authorization policy; never bounce users back into a login form to gain extra privileges.

### 7.3. When Multiple Entry Points Are Needed Across Areas

An application may have:
- `/intranet/**` → SPNEGO.
- `/api/**` → OAuth2 Resource Server/JWT.
- `/public/**` → unauthenticated.
- `/admin/**` → SPNEGO + additional MFA/step-up policy.

Use **multiple `SecurityFilterChain` beans with explicit `securityMatcher` and order**, or `defaultAuthenticationEntryPointFor(..., RequestMatcher)` where appropriate. **Never** emit a Negotiate header for every endpoint via a global entry point; browsers may attempt ambient credentials out of scope, especially with CORS and SPAs.

## 8. Proxies, Load Balancers, and Hostnames: Cause of Many 401 Loops

### 8.1. Reverse Proxies Must Not Drop HTTP Auth Headers

Inspect both directions:

~~~text
Browser -> HTTPS reverse proxy -> Spring Backend
  Authorization: Negotiate <opaque-token>
           MUST reach trusted Kerberos-accepting backend

Spring Backend -> reverse proxy -> Browser
  HTTP 401
  WWW-Authenticate: Negotiate
           MUST reach browser unchanged as intended
~~~

If the gateway strips `Authorization` or permits only Bearer, the Spring filter never sees the token. If the gateway strips `WWW-Authenticate` or turns 401 into a 302 redirect to a gateway login portal, the browser never initiates SPNEGO. If both the proxy and backend **attempt to terminate Kerberos**, establish **one authoritative trust boundary**; never assume both can consume the same AP-REQ and construct principals independently.

### 8.2. SPN of the Public Hostname, Not the Pod Hostname

Public URL:

~~~text
https://portal.example.org
~~~

Yet actual backend:

~~~text
http://portal-service.namespace.svc.cluster.local:8080
~~~

The browser requests a ticket for **`HTTP/portal.example.org`**, not `HTTP/portal-service.namespace.svc.cluster.local`. The backend validator/keytab must hold keys for the **public host's SPN**, regardless of the internal HTTP host. Client-to-proxy HTTPS and network trust between proxy and backend must be carefully engineered; an untrusted backend path can leak Negotiate tokens.

### 8.3. Multi-Node Service Keys

If both Node A and Node B accept Kerberos directly for the same `HTTP/portal.example.org`, nodes need **valid credentials for the same service principal/keys** (or an alternative delegation/proxy termination design) with secure keytab distribution/rotation. Never copy keytabs through logs or repositories. If session/auth state is stored locally, users switching nodes may trigger re-authentication; depending on policy, SPNEGO can renegotiate or use shared sessions. Test both **sticky session failover** and load balancer health routes.

### 8.4. TLS and Channel Binding / Extended Protection

SPNEGO/Kerberos authenticates the service principal, yet **HTTP Negotiate does not replace TLS**. Where Extended Protection for Authentication/channel binding is enforced, ensure TLS termination and channel binding tokens align across browser, proxy, and SPNEGO acceptor. Terminating TLS at ingress while the backend accepts SPNEGO can affect certain channel binding modes; test against realm/security policy and never blindly disable EPA/CBT to "fix 401".

## 9. Accurately Identifying Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Protected GET returns 302 to `/login`, no 401 Negotiate. | Spring entry point is still form login/default handler. | Inspect `SecurityFilterChain` and `exceptionHandling`; check response headers. |
| 401 has Negotiate but browser never sends `Authorization`. | Browser lacks credentials/URL not allowlisted/intranet or client unsupported. | Check browser policy, Kerberos TGT, and domain before blaming the validator. |
| Browser sends Authorization then gets repeated 401s. | Wrong keytab/SPN/realm, filter not running, provider unregistered, NTLM fallback rejected. | Check filter invocation, sanitized GSS error, SPN/KDC/keytab. |
| `KRB_AP_ERR_MODIFIED`. | Server lacks matching SPN/KVNO key, duplicate SPN, wrong service account. | Check SPN registry, keytab, account rotation, and DNS aliases. |
| `KRB_AP_ERR_SKEW` or clock skew. | Client/KDC/server clocks drifted beyond policy. | Sync NTP, inspect timezone/clock without disabling validation. |
| `KRB5KDC_ERR_S_PRINCIPAL_UNKNOWN`. | KDC cannot find SPN for the host the client accessed. | Verify `HTTP/<FQDN>` in realm and hostname canonicalization. |
| GSS: `Message stream modified` / `Integrity check` failed. | Key mismatch, corrupted token, wrong enctype, or proxy mangling data. | Keytab KVNO/enctype, Authorization passthrough via gateway, sanitized logs. |
| `GSSException: Defective token`. | Malformed header, invalid Base64, wrong mechanism (NTLM), middlebox truncated token. | Inspect scheme/header metadata without logging raw tokens. |
| KDC issues TGT but no HTTP service ticket. | Wrong SPN, realm trust, DNS/KDC policy, insufficient credentials. | `klist`/OS Kerberos tools on test machine, KDC audit logs. |
| 401 on alias URL while canonical hostname works. | SPN/browser allowlist and canonicalization differ. | Use canonical public URL, map SPNs accurately, test DNS. |
| Kerberos-capable browser shows fallback form. | 401 forwarded body, browser policy skips auto-Negotiate, proxy altered challenge. | Inspect actual `WWW-Authenticate` response and browser trusted URI policy. |
| Java throws `NoClassDefFoundError: jakarta.servlet`. | Old `javax` Kerberos extension mixed with newer `jakarta` Spring Security. | Align releases, dependency tree, and version locks. |
| Authenticated yet every call prompts Negotiate again. | SecurityContext/session not persisted per config; multiple nodes. | Inspect context repository, cookies, and auth state; never disable validation. |
| Valid Kerberos principal gets 403. | Local user disabled or missing role/permission/tenant. | Check local admission, granted authorities, method security. |
| Browser SPA API call fails with CORS error. | `OPTIONS` preflight hit with 401 challenge, wrong CORS config/trusted origin. | Place CORS filter before security, test `OPTIONS` and credentials policy. |
| `curl --negotiate` fails inside container. | Missing Kerberos credentials, wrong SPN/DNS, or curl lacks GSS support. | Verify curl build, `klist`, realm/keytab; never "bypass Negotiate". |
| Server sends Negotiate but browser sends NTLM. | Client/OS policy negotiates/downgrades SPNEGO. | Identify accepted mechanism, enforce Kerberos-only if required. |
| Negotiate prompt reappears after form login. | Misconfigured fallback EntryPoint/chain, Spring session not saved. | Separate matchers and auth success handlers, check forwarded 401. |
| Gateway turns 401 into 302. | Identity gateway/middleware intercepts route before Spring. | Clarify auth ownership at each hop; never trust unverified `X-User`. |

### 9.1. Useful Debugging Order

1. **Network:** does the first request receive 401 + `WWW-Authenticate: Negotiate`?
2. **Browser:** does the next request carry `Authorization: Negotiate`? If not, inspect browser policy/Kerberos client.
3. **KDC:** does the client hold a service ticket for **HTTP/public-FQDN**?
4. **Gateway:** does `Authorization` reach Spring and does 401 Negotiate reach the browser?
5. **Spring:** does `SpnegoAuthenticationProcessingFilter` execute and dispatch the token to `AuthenticationManager`?
6. **Validator:** are servicePrincipal/keytab/KVNO/enctype/realm/GSS configured accurately?
7. **Local account:** does `UserDetailsService` accept the principal and is the account ACTIVE?
8. **Authorization:** are role/tenant/resource permissions satisfied?
9. **Session:** is SecurityContext persisted per policy, and are session fixation/cookies/multi-node correct?
10. **Fallback:** if the browser lacks Kerberos, is appropriate login content rendered while still failing closed?

## 10. Manual Testing: Distinguishing Intentional 401 from Auth Failures

### 10.1. Testing the Challenge Without Credentials

Against a protected endpoint:

~~~bash
curl -i --max-time 10 https://portal.example.org/private
~~~

Without a valid cookie and before `curl` supplies GSS credentials, expect:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

**Sample output** depends on the gateway/filter and endpoint. If you see a 302 redirect, inspect the entry point/fallback/gateway before concluding Spring Kerberos is broken. Do not treat curl "receiving 401" as a server error: issuing that 401 challenge is the exact initial purpose of `SpnegoEntryPoint`.

### 10.2. Testing with a Client Holding Real Kerberos Credentials

On a machine with a GSSAPI-enabled Kerberos client/curl build and a valid ticket cache:

~~~bash
klist
curl --negotiate -u : -i https://portal.example.org/private
~~~

`curl --negotiate -u :` is common syntax on GSSAPI-enabled curl builds to use the active credential cache for Negotiate; actual behavior depends on build, Kerberos environment, and OS. **Never use real tickets in public demos or verbose `-v` logs containing Authorization**, especially on shared hosts. Never pass `curl -k` to skip TLS verification just because a certificate is missing.

**Success** means the service returns the protected resource after verifying the GSS context and local account/permissions; **not** merely observing the client send an Authorization header. On an endpoint requiring `app:admin`, a valid Kerberos login without the matching authority must receive 403.

### 10.3. Testing 401 ↔ 403 ↔ 200

| Case | Header / Condition | Expected |
| --- | --- | --- |
| Anonymous GET `/private`. | No Authorization/cookie. | **401 + Negotiate**. |
| Browser sends random token or fake Base64. | `Authorization: Negotiate fake`. | **Authentication fails**; 401/failure. |
| Browser holds valid SPN ticket and local user is ACTIVE. | Token verified. | **200** if authorized. |
| ACTIVE user lacks role on `/admin`. | Verified Kerberos identity, missing authority. | **403**, no admin access. |
| Local user DISABLED. | Kerberos verified, admission denied. | No authenticated session created. |
| Protected `POST /transfer` with session but missing CSRF token. | Valid local session, missing CSRF. | **403** CSRF per policy, not a KDC error. |
| Public `GET /public/ping`. | No Authorization. | 200, no challenge. |
| CORS `OPTIONS /private`. | Legitimate preflight + CORS policy. | Handled by CORS without forcing Negotiate on preflight. |
| Browser lacks Negotiate support, fallback enabled. | Anonymous GET. | 401 + Negotiate header, app fallback body; not a 302 from `SpnegoEntryPoint`. |
| Mismatched service SPN/keytab. | Token cannot be accepted. | No 200 authenticated, GSS failure safely logged. |
| Proxy strips `Authorization` header. | Browser sent Negotiate but backend never received it. | Backend keeps returning 401; E2E FAIL. |
| KDC/clock error. | Cannot acquire/validate service ticket. | Fail closed, never map user from self-asserted header. |

## 11. Standalone Java 17: State Machine Simulating Negotiate Challenge

The program below **does not implement Kerberos**. It simulates web-layer HTTP decisions: emitting **401 Negotiate** when unauthenticated, rejecting when a header is present but unverified by the validator, and returning 200 or 403 only after both validator and local policy accept the identity.

Key design property: it never accepts `Authorization` as self-proving; only the **simulated `validatorAccepted` flag** representing **verified GSS/provider output** transitions to authenticated. In production, that result must come from **Spring Security's `AuthenticationManager`**, never from an HTTP request flag.

File **`SpnegoChallengeDecisionDemo.java`**:

~~~java
public final class SpnegoChallengeDecisionDemo {

    record Request(boolean protectedResource,
                   boolean sessionAuthenticated,
                   boolean hasNegotiateHeader,
                   boolean validatorAccepted,
                   boolean localAccountActive,
                   boolean resourceAllowed) {}

    record Response(int status, String wwwAuthenticate, String reason) {
        @Override public String toString() {
            return status + " | " + wwwAuthenticate + " | " + reason;
        }
    }

    static Response decide(Request request) {
        if (!request.protectedResource()) {
            return new Response(200, "-", "PUBLIC");
        }

        boolean verifiedSession = request.sessionAuthenticated();
        boolean freshKerberos = request.hasNegotiateHeader()
                && request.validatorAccepted();

        if (!verifiedSession && !freshKerberos) {
            return new Response(401, "Negotiate",
                    request.hasNegotiateHeader()
                            ? "TOKEN_REJECTED" : "CHALLENGE");
        }

        if (!request.localAccountActive()) {
            return new Response(403, "-", "ACCOUNT_BLOCKED");
        }
        if (!request.resourceAllowed()) {
            return new Response(403, "-", "FORBIDDEN");
        }
        return new Response(200, "-", "ALLOWED");
    }

    public static void main(String[] args) {
        System.out.println(decide(
                new Request(false, false, false, false, true, false)));
        System.out.println(decide(
                new Request(true, false, false, false, true, true)));
        System.out.println(decide(
                new Request(true, false, true, false, true, true)));
        System.out.println(decide(
                new Request(true, false, true, true, true, true)));
        System.out.println(decide(
                new Request(true, false, true, true, true, false)));
        System.out.println(decide(
                new Request(true, false, true, true, false, true)));
        System.out.println(decide(
                new Request(true, true, false, false, true, true)));
        System.out.println(decide(
                new Request(true, true, false, false, true, false)));
    }
}
~~~

Compile/run:

~~~bash
javac SpnegoChallengeDecisionDemo.java
java SpnegoChallengeDecisionDemo
~~~

**Deterministic stdout:**

~~~text
200 | - | PUBLIC
401 | Negotiate | CHALLENGE
401 | Negotiate | TOKEN_REJECTED
200 | - | ALLOWED
403 | - | FORBIDDEN
403 | - | ACCOUNT_BLOCKED
200 | - | ALLOWED
403 | - | FORBIDDEN
~~~

**Line-by-line explanation:**
1. Public route skips Kerberos challenge.
2. Anonymous protected request receives a 401 challenge.
3. `Authorization: Negotiate` present, but validator rejects token → **still 401**.
4. Valid GSS token, ACTIVE local account, permitted → 200.
5. Valid GSS token, lacking permission → **403**, no repeated challenge.
6. Valid GSS token, local account blocked → denied.
7. Already authenticated session with permission → 200 without requiring Authorization on that request.
8. Already authenticated session lacking resource permission → 403.

**Limitations:** this code is a **policy simulation**, not an HTTP servlet; it does not create keytabs, contact a KDC, parse Base64/GSS, or handle multi-round SPNEGO, channel binding, session fixation, or Kerberos credential lifetimes. `validatorAccepted` merely represents **verified framework evidence**, and must never be copied from a form, JSON payload, or self-asserted header. Returning 403 for a blocked account is a simplified demo choice; real Spring authentication failures may return 401 depending on the flow.

## 12. Sessions, Reauthentication, and Expiry

### 12.1. When HttpSession Exists

A Servlet application typically stores the verified `Authentication` in `SecurityContext` so SPNEGO is not exchanged on every request. Yet behavior **depends on `SecurityContextRepository`, `SessionAuthenticationStrategy`, and session policy**.

With newer Spring Security Kerberos extension releases, `SpnegoAuthenticationProcessingFilter` has defaults around **skipIfAlreadyAuthenticated**, success handlers, and security context saving; check your framework version. Never assume the browser **always** resends Authorization on every request, or that the app **always** creates an HttpSession after the handshake.

### 12.2. Kerberos TGT and Local Session Have Two Separate Lifetimes

- The TGT or service ticket expires per KDC/Kerberos policy.
- The HTTP session has an idle/absolute TTL set by the application.
- The browser may still hold credentials to **re-execute Negotiate** when the local session expires.
- Local logout only invalidates the application session; if the client still has a valid TGT, the next request can automatically re-authenticate right away.

Thus **"logging out of the portal" does not equal "logging out of the Windows/Kerberos domain"**. If an application requires users to actively re-enter an authentication factor for sensitive operations, implement a policy-compliant reauthentication/step-up workflow; **default SPNEGO does not prove fresh MFA occurred at request time**.

### 12.3. Session Fixation and CSRF

Spring Security session fixation protection, appropriate `Secure`/`HttpOnly`/`SameSite` cookies, CSRF protection on state-changing requests, and per-resource authorization remain critical. Do not disable `.csrf()` globally just to use Kerberos; **ambient credentials** make CSRF even more important to guard against. For token-based APIs instead of cookies, design appropriate token audience/CORS/CSRF controls separately.

## 13. Kerberos Federation and Boundaries That Must Not Be Crossed

SPNEGO/Kerberos can be one **leg** in a broader federation architecture:

~~~text
Enterprise AD / KDC
       |
     Kerberos
       |
Browser -> Spring Portal (SPNEGO acceptor)
                 |
                 | local session / SecurityContext
                 |
                 +--> API with OAuth access token (separate protocol)
                 +--> SAML SP/IdP federation (separate protocol)
                 +--> OIDC broker (separate protocol)
~~~

A Kerberos ticket for `HTTP/portal.example.org` is **not** an OIDC ID Token for an RP or a SAML Assertion for another SP. If the Portal needs to call downstream services on the user's behalf, you need properly configured **Kerberos constrained delegation/S4U** in AD and service accounts, or an **OAuth2 token exchange/delegation** accepted by the Authorization Server, depending on architecture. **Never forward the browser's `Authorization: Negotiate` header to another API** expecting that API to accept it as logged in.

### 13.1. Authenticated Identity Is Not Application Authorization

When the provider receives Kerberos principal `alice@CORP.EXAMPLE.ORG`, the application still must:
- Bind the realm-qualified identity to a stable local account, without dropping the realm when multiple realms/trusts exist.
- Check local status `ACTIVE`/`LOCKED`/`DISABLED`.
- Map approved `GrantedAuthority` entries from a contracted local app/LDAP/directory.
- Enforce tenant/resource ownership and method-level authorization.
- Fail closed when account/policy services are unavailable, without falling back to an overly broad `ROLE_USER`.
- Never use workstation hostname, email, or an unverified `X-Remote-User` as the principal.

**Authn ≠ Authz.** 401 Negotiate only initiates authentication; a valid Kerberos ticket does not grant `admin` or `payments:approve`.

### 13.2. When a Reverse Proxy Terminates Kerberos Itself

Some environments use **IIS, Apache mod_auth_gssapi, an NGINX module, or an enterprise gateway** to handle Kerberos before Spring. In that model, the gateway may forward principal info via headers or an authenticated SSO session.

Use this pattern only when Spring **exclusively trusts the authenticated gateway**, the backend connection is secured with mTLS/network ACLs, the gateway **strips/overwrites all client-supplied identity headers**, and a documented trust contract exists. If both the gateway and `SpnegoAuthenticationProcessingFilter` read the same Authorization header, double authentication or gateway token consumption can occur. **Pick a single authoritative authenticator per request**, or configure explicit delegation cleanly.

## 14. Protocol and Operational Security

| Risk | Mitigation |
| --- | --- |
| **Kerberos token leak** in Authorization logs. | Redact request/response auth headers, never store raw Base64. |
| **Keytab compromise**. | Secret storage, tight ACLs, rotation, never bake into images. |
| **SPN mismatch**. | Register exact HTTP/public-FQDN, monitor duplicate SPNs/KVNO. |
| **Clock skew/realm misconfig**. | Managed NTP, DNS/KDC discovery, and trust relationships. |
| **NTLM downgrade**. | Enforce Kerberos-only where policy requires; verify actual mechanism. |
| **Proxy header stripping**. | End-to-end tests of `WWW-Authenticate` and `Authorization` through ingress. |
| **Loose Basic auth fallback**. | Enable only when required, over HTTPS, with real provider and rate limits. |
| **SPNEGO to unexpected origin**. | Keep browser intranet/trusted URI allowlists narrow, avoid arbitrary wildcards. |
| **Unauthorized account admission**. | `UserDetailsService` enforcing status/role/tenant checks. |
| **CSRF via ambient credentials**. | CSRF tokens, SameSite, origin checks, and safe HTTP method rules. |
| **Host header/SPN confusion**. | Pin public host/trusted proxy, never pick keytab/realm from arbitrary Host headers. |
| **Failure loops**. | Bound challenge retries, log reason codes, never weaken trust to silence 401s. |
| **DoS via oversized tokens**. | Header size limits, rate limits, timeouts, reject invalid GSS tokens. |
| **Stale local sessions**. | Idle/absolute timeouts, reauth policy, revocation, and account status checks. |
| **Jakarta/Javax rollout issues**. | Lock extension/core versions, run compile and integration tests. |

A `401 WWW-Authenticate: Negotiate` header itself **does not expose a password**, yet it can trigger **ambient authentication** in trusted browsers. Therefore, never emit challenges for an unapproved host, never enable wildcard "Kerberos SSO for all websites", and protect service principals from DNS spoofing/TLS interception.

## 15. End-to-End Test Suite for SpnegoEntryPoint

| Case | Expected Result |
| --- | --- |
| Anonymous request to `/protected`. | **401** and `WWW-Authenticate: Negotiate` header. |
| Anonymous request to `/public`. | **200** or public response, no 401 Negotiate. |
| Domain browser with TGT, URL allowlisted. | Follow-up sends `Authorization: Negotiate`; Kerberos validator authenticates. |
| Browser lacks TGT or URL not allowlisted. | Does not auto-send credentials; if fallback enabled, renders login content. |
| `new SpnegoEntryPoint("/login")`. | **401 + Negotiate** with **internal forward**, no automatic 302. |
| Unauthenticated protected POST with login forward. | Check method semantics, preserve CSRF/authorization. |
| Sending `Authorization: Negotiate invalid-token`. | No authenticated principal/session created. |
| Valid token but local user DISABLED. | Authentication/admission rejected. |
| Valid user lacking admin permissions. | **403** on `/admin`; no privilege escalation from Kerberos. |
| Valid user with permissions. | **200** on protected endpoint. |
| Wrong SPN `HTTP/wrong.example.org`. | Ticket not accepted for Portal. |
| Wrong keytab/stale KVNO. | Validation failure, never fail-open. |
| Clock skew beyond policy. | KDC/GSS fails; checks remain enabled. |
| Proxy strips `WWW-Authenticate`. | Browser fails to negotiate; test FAILS. |
| Proxy strips `Authorization`. | Backend cannot validate token; test FAILS. |
| NTLM selected under Kerberos-only policy. | Rejected/denied, never silently accepted. |
| Client sends oversized/malformed token. | Safely rejected/limited, no DoS or credential logging. |
| 401 continuation with GSS data. | Client/library follows protocol without truncating token. |
| Client finishes mutual auth with 200 + header. | Gateway does not break final handshake. |
| Valid `OPTIONS` preflight. | Handled by CORS policy without demanding Kerberos on preflight. |
| Browser session expires while TGT remains valid. | Can renegotiate; distinguish new session from old session. |
| Local user revoked while session active. | Authorization/status policy blocks within SLA; do not trust Kerberos forever. |
| Two nodes share SPN with mismatched keys. | Failover test catches error, fix keytab distribution. |
| Forged `X-Remote-User` sent directly to backend. | Header stripped/ignored unless from trusted gateway. |
| Missing `spring-security-kerberos` dependency. | Clear build/runtime failure, not conflated with KDC errors. |

**Acceptance criteria:** do not merely count 401/200; verify **challenge, Authorization exchange, GSS validation, local account admission, authorities, session lifecycle, and refusal cases**. In integration tests, use a test KDC/AD with dedicated SPN/keytab; never copy production keytabs or tokens into tests.

## 16. Common Misconceptions

1. **"`SpnegoEntryPoint` verifies Kerberos tokens itself."** False: it only produces the HTTP 401 challenge.
2. **"401 means the application is broken."** False: 401 + Negotiate is the standard initial step when credentials are absent.
3. **"The server must return 302 to /login to use SPNEGO."** False: it uses an HTTP authentication challenge.
4. **"`SpnegoEntryPoint("/login")` is a 302 redirect."** False: it uses `RequestDispatcher.forward` and preserves 401/Negotiate.
5. **"Having `Authorization: Negotiate` means authenticated."** False: the GSS token must pass the validator/acceptor.
6. **"`Negotiate` always means Kerberos."** False: the mechanism can negotiate NTLM if client/server policies allow it.
7. **"No SPN is needed if the keytab belongs to the right user."** False: service tickets target exact `HTTP/<host>` SPNs and matching keys.
8. **"HTTPS is equivalent to Kerberos."** False: TLS protects the transport channel; Kerberos authenticates the principal via GSS.
9. **"SPN `HTTP/` means the server must run unencrypted HTTP."** False: it is a Kerberos service class; the site still uses HTTPS.
10. **"A valid Kerberos ticket guarantees the user has `ROLE_ADMIN`."** False: application permissions require local authorization.
11. **"Basic auth works automatically when SpnegoEntryPoint is enabled."** False: fallback requires its own form/provider; passwords are not accepted automatically.
12. **"If `curl` fails Negotiate, the server is broken."** Not necessarily: curl/OS need GSS support and credentials.
13. **"Disabling certificate verification makes Kerberos safer."** False: it weakens TLS and can break trust.
14. **"A proxy can strip `WWW-Authenticate` and browsers will still use SPNEGO."** You cannot rely on clients sending preemptive tokens on their own.
15. **"One HTTP 401 then 200 is always the entire handshake."** False: SPNEGO/GSS may require continuation rounds.
16. **"Once Kerberos stores the user in session, every request is authorized forever."** False: session timeouts, account revocation, and policies must be enforced.
17. **"SPNEGO is the same as OIDC/SAML/CAS."** False: different protocols, tokens, and endpoints.
18. **"Reading a username from a reverse proxy header is equivalent to GSS validation."** Only when an authenticated gateway trust boundary exists that blocks header spoofing.
19. **"Kerberos login proves fresh MFA occurred."** False: there is no freshness/assurance guarantee without explicit policy and evidence.
20. **"Just having `SpnegoEntryPoint` and a securityFilterChain is production-ready."** False: you still need SPN/keytab/KDC/validator/user mapping/observability and tests.

## 17. Production Deployment Checklist

1. Have you clearly confirmed the app uses **SPNEGO/Kerberos HTTP authentication**, without confusing it with OIDC/SAML/CAS?
2. Do clients/browsers have TGT/realm access and a trusted URI allowlist scoped strictly to the right hosts?
3. Is the initial HTTP request challenged with **401 + `WWW-Authenticate: Negotiate`**?
4. Do follow-up requests carry `Authorization: Negotiate` cleanly through proxies to the backend without leaking into logs?
5. Are `SpnegoAuthenticationProcessingFilter`, `AuthenticationManager`, `KerberosServiceAuthenticationProvider`, and `KerberosTicketValidator` wired correctly?
6. Do the `HTTP/public-fqdn@REALM` SPN, keytab, KVNO, encryption types, keytab rotation, and AD account align?
7. Are HTTPS, trusted TLS certificates, proxy/ingress header preservation, and channel binding policy in place as needed?
8. Is Kerberos-only/NTLM fallback restricted per organizational policy?
9. Does `UserDetailsService` map realm-qualified principals, local account status, and app entitlements properly?
10. Are **401 and 403** handled distinctly without turning missing permissions into login loops?
11. If `SpnegoEntryPoint("/login")` is enabled, are **401 forwarding**, fallback page content, and HTTP method safety accounted for?
12. Does fallback login have an independent provider, HTTPS, CSRF/rate limiting, and a clear admission policy?
13. Are SecurityContext repository/session strategy, session fixation, and local logout behavior explicitly defined?
14. Do CORS preflight/API endpoints use appropriate entry points without emitting out-of-scope Negotiate challenges?
15. Do multi-node deployments have matching SPN keytabs, session consistency, and failover tests?
16. Do logs/APM redact Authorization/GSS tokens, enforce size limits, and record reason codes?
17. Do you have unit tests for challenges and GSS integration tests against a test KDC/AD covering wrong SPN/keytab/clock, replay, and disabled/unauthorized local users?
18. Have you separated Kerberos authentication from downstream API delegation and revocation policies?

## 18. Self-Check Knowledge Questions

1. **What does `SpnegoEntryPoint` return when unauthenticated?** — **401** and `WWW-Authenticate: Negotiate`.
2. **What does the browser send next?** — `Authorization: Negotiate <GSS-API/SPNEGO token>`.
3. **Which Spring class receives that header?** — `SpnegoAuthenticationProcessingFilter`.
4. **Which class validates the service ticket?** — `KerberosServiceAuthenticationProvider` invoking `KerberosTicketValidator`, such as `SunJaasKerberosTicketValidator`.
5. **What does a web service SPN look like?** — `HTTP/portal.example.org@CORP.EXAMPLE.ORG`.
6. **Does `SpnegoEntryPoint("/login")` redirect or forward?** — **Server-side forward**, keeping HTTP 401 + Negotiate.
7. **Why can a 401 be completely normal?** — Because HTTP auth requires a challenge before the browser sends credentials.
8. **Why not create a principal just because a Negotiate header is present?** — Because the header can hold a fake/corrupt token or one for another SPN; GSS must validate it.
9. **After authentication, what is returned if the user lacks a role?** — Usually **403 Forbidden**.
10. **Does SPNEGO always use Kerberos only?** — No; the Negotiate mechanism can fall back to NTLM depending on policy/implementation.
11. **Why does the public hostname matter for the keytab?** — Clients request service tickets for `HTTP/public-host`, so the server acceptor needs the key for that SPN.
12. **Why can a proxy cause 401 loops?** — It may strip or alter `Authorization` or `WWW-Authenticate`.
13. **Does Kerberos TGT expiration immediately invalidate the HttpSession?** — Not automatically; they are separate lifecycles.
14. **Does local logout delete the OS Kerberos TGT?** — No; the next request can automatically renegotiate.
15. **Is `SpnegoEntryPoint` alone enough for Kerberos login?** — No; you also need the filter, provider, validator, local mapping, and SPN/keytab setup.
16. **Is HTTPS enough to prove a Kerberos user?** — No; TLS only secures the channel, whereas GSS validation proves the principal.
17. **Should a `/public` request return 401 Negotiate?** — No, when configured with `permitAll`.
18. **How should browsers that do not support Negotiate be handled?** — Use a properly designed fallback or return an informative 401; never grant access automatically.
19. **Why not forward the Negotiate token directly to another API?** — The ticket is bound to the service principal/trust; use proper delegation or token exchange.
20. **How should 401 behavior be tested?** — Verify status and headers, then test E2E across browser/KDC/validator/local permissions, not just `curl` 401.

## References

- [Spring Security Kerberos API — SpnegoEntryPoint constructors, commence, forward behavior](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html)
- [Spring Security Kerberos API — SpnegoAuthenticationProcessingFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html)
- [Spring Security Kerberos API — KerberosServiceAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html)
- [Spring Security Kerberos API — SunJaasKerberosTicketValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html)
- [Spring Security Kerberos open-source implementation — SpnegoEntryPoint.java](https://github.com/spring-projects/spring-security-kerberos/blob/main/spring-security-kerberos-web/src/main/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.java)
- [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication in Microsoft Windows](https://www.rfc-editor.org/rfc/rfc4559.html)
- [RFC 4178 — The SPNEGO GSS-API Mechanism](https://www.rfc-editor.org/rfc/rfc4178.html)
- [RFC 4120 — The Kerberos Network Authentication Service (V5)](https://www.rfc-editor.org/rfc/rfc4120.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
