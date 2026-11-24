# CasAuthenticationFilter and Receiving Service Tickets in Spring Security CAS

## 1. Objectives, Context, and Scope

In **Spring Security – Federation** systems, a Java application can use **Central Authentication Service (CAS)** so users log in once and access multiple applications registered with the CAS server. When a user accesses a protected resource, the application **does not collect the CAS password directly**. The browser is redirected to the CAS Server, and after the user authenticates, the CAS Server redirects the browser back to an application **service URL** along with a **Service Ticket (ST)**.

The component that receives the callback in Spring Security is **CasAuthenticationFilter**. It receives the ticket, passes the authentication request to **AuthenticationManager -> CasAuthenticationProvider**, and the provider uses **TicketValidator** to contact the CAS Server and verify the ticket against the registered service. Only after CAS confirms the ticket and the application loads/checks the local account does Spring Security create an `Authentication` and establish the appropriate login session.

This lesson belongs to the **CAS Integration** group, with the following objectives:

1. Understand clearly how a **CAS Service Ticket** differs from a session cookie, Ticket-Granting Ticket (TGT), Proxy Ticket (PT), and OAuth/OIDC/SAML tokens.
2. Trace the flow **browser -> CAS login -> callback `/login/cas?ticket=...` -> filter -> provider -> CAS `serviceValidate` -> `SecurityContext`**.
3. Explain accurately the roles of **CasAuthenticationFilter, CasAuthenticationEntryPoint, ServiceProperties, CasAuthenticationProvider, TicketValidator, UserDetailsService**.
4. Configure **service URL, `filterProcessesUrl`, and CAS Server base URL** consistently, especially behind a reverse proxy / TLS termination.
5. Understand the properties of **single-use STs, short TTLs, and binding to a single service**; why you cannot trust a `ticket=ST-...` string directly or reuse a ticket.
6. Distinguish **stateful browser ticket login** from **CAS proxy ticket / stateless authentication**; avoid enabling proxy capabilities when not needed.
7. Read the differences between older CAS documentation and current Spring Security APIs accurately, avoiding `Authentication` token type mismatches during upgrades.
8. Study a Spring configuration example and a **standalone Java 17 program**, along with security tests, troubleshooting, and a deployment checklist.

**Core principle:** `CasAuthenticationFilter` **does not treat a ticket string in the URL as authenticated on its own**. It only initiates the authentication request; **only the CAS Server has authority to validate the ticket and service and return user information** over a protected validation channel.

## 2. Concepts Not to Be Confused

| Concept | Where Created / Managed | Purpose | Lifecycle / Trust |
| --- | --- | --- | --- |
| **CAS Server** | Central identity system | Authenticates users; issues and validates tickets | Must be a trusted configured CAS endpoint |
| **Service** | CAS-registered application | Callback target, e.g. `https://portal.example.test/login/cas` | Service ID must match CAS policy |
| **Service Ticket (ST)** | CAS Server | Opaque credential the app exchanges for a validation result | Bound to one service, short TTL, **single-use validation** |
| **Ticket-Granting Ticket (TGT)** | CAS Server | Represents the SSO session at CAS, allowing multiple STs to be issued | Not an ST; never sent to `/login/cas` |
| **Ticket-Granting Cookie (TGC)** | Cookie on the CAS domain | Lets the browser identify its SSO session/TGT to CAS | Not the application's session cookie |
| **HttpSession / JSESSIONID** | Spring application | Local login session after the ST has been verified | Distinct from CAS SSO session; has its own lifecycle |
| **Proxy Ticket (PT)** | CAS Server | Allows an intermediate service to call a downstream service on behalf of the user | Requires proxy profile/validator and dedicated trust policy |
| **Proxy-Granting Ticket (PGT)** | CAS Server | Authorizes a service to obtain PTs | Not an ST; requires proxy callback / PGT storage |
| **CAS assertion** | `TicketValidator` result | CAS authentication details and attributes confirmed by CAS | Trusted only after the validator accepts it |
| **Spring Authentication** | Spring Security | Principal + authorities + authenticated state inside the app | Must originate from a provider that verified the ticket and local policy |

**A ticket is not a user ID.** A string like `ST-opaque-abc` must never be decoded/parsed to infer a username, tenant, or permission. It is a **single-use credential** that must be sent to the CAS Server for validation.

**CAS Protocol differs from OIDC/SAML:** an ST is neither a JWT access token nor an OIDC ID Token, and the `ticket` query parameter is not a `SAMLResponse`. A CAS Server may also support OIDC/SAML, but the flow in this article is the **CAS protocol service ticket**.

### 2.1. Three Session States Existing Independently

~~~text
Browser
  |
  +-- CAS TGC cookie -> CAS Server maintains SSO session/TGT
  |
  +-- JSESSIONID cookie -> Spring app maintains local session
  |
  +-- callback ticket ST -> exchanged once at CAS validation endpoint
~~~

Once the ST is validated, the application typically stores `Authentication` in its local session. **The application must not hold onto the ST as a "login password" to re-validate on every request.** The CAS Server may keep its TGT session after the local session ends, so a user returning to the app can be issued a **new ST** by CAS without re-entering a password.

## 3. End-to-End CAS Service Ticket Flow

System example:

~~~text
CAS Server:  https://sso.example.test/cas
CAS login:   https://sso.example.test/cas/login
CAS validate:https://sso.example.test/cas/serviceValidate
SP service:  https://portal.example.test/login/cas
~~~

Diagram:

~~~text
Browser                        Spring Security app                    CAS Server
   |                                  |                                   |
   | GET /private                     |                                   |
   |--------------------------------->|                                   |
   |                                  | ExceptionTranslationFilter        |
   |                                  |   -> CasAuthenticationEntryPoint  |
   |<---------------------------------| 302 CAS /login?service=<SP service>
   |---------------------------------------------------------------------->|
   |                                  |                                   | authenticates
   |                                  |                                   | with credentials
   |<----------------------------------------------------------------------|
   | 302 https://portal.example.test/login/cas?ticket=ST-opaque-abc        |
   |--------------------------------->|                                   |
   |                                  | CasAuthenticationFilter            |
   |                                  | reads ticket request parameter    |
   |                                  | builds authentication request     |
   |                                  | AuthenticationManager               |
   |                                  |    -> CasAuthenticationProvider     |
   |                                  |           -> TicketValidator        |
   |                                  |----------------------------------->|
   |                                  | GET /serviceValidate               |
   |                                  | ?service=<exact-SP-service>         |
   |                                  | &ticket=<opaque-ST>                 |
   |                                  |<-----------------------------------|
   |                                  | CAS serviceResponse XML             |
   |                                  |  SUCCESS: user + attributes         |
   |                                  |  FAILURE: reason                    |
   |                                  | loads local user + authorities      |
   |                                  | creates CasAuthenticationToken       |
   |                                  | saves SecurityContext per config    |
   |<---------------------------------| redirects to original page          |
   | GET /private                     |                                   |
   |--------------------------------->| authorizes user per app policy      |
~~~

**Two separate paths:**

- **Browser redirect** to CAS `/login` and back to the service URL carrying `ticket`.
- **Server-to-server ticket validation** from the application to CAS `/serviceValidate` or a compatible CAS profile endpoint over HTTPS.

**Do not trust a callback merely because the browser was redirected from CAS.** A browser can call `/login/cas?ticket=...` directly; server-to-server verification and service binding are what establish the ticket's validity.

### 3.1. When Unauthenticated

Spring Security's `ExceptionTranslationFilter` hands the unauthenticated request to **CasAuthenticationEntryPoint**. The entry point builds the CAS Login URL based on:

- The CAS Server login URL, e.g. `https://sso.example.test/cas/login`.
- `ServiceProperties.service` specifying where CAS sends the browser back, e.g. `https://portal.example.test/login/cas`.
- Depending on `renew` or `gateway` settings, SSO vs. re-prompting behavior differs.

Example redirect:

~~~text
HTTP/1.1 302 Found
Location: https://sso.example.test/cas/login?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
~~~

**`service` in the query above must be URL-encoded**, and the decoded value must represent the exact registered service. Never manually splice `?`/`&` or normalize host/path by guesswork.

### 3.2. When CAS Authentication Succeeds

The CAS Server establishes or reads its own CAS SSO session, issues an **ST exclusively for the specified service**, and redirects:

~~~text
HTTP/1.1 302 Found
Location: https://portal.example.test/login/cas?ticket=ST-opaque-abc
~~~

`ST-opaque-abc` is an **illustrative placeholder, not a valid ticket**. Real tickets are randomly generated by CAS and cannot be guessed.

### 3.3. When Spring Receives the Callback

`CasAuthenticationFilter` listens on **/login/cas** by default. It detects requests to that path, reads `ticket`, and constructs an **unverified Authentication** to pass to `AuthenticationManager`.

- `ticket` is the temporary credential of the authentication request.
- The initial `principal` is a **CAS-specific/stateful identifier marker** used by the filter/provider, **not yet the real user**.
- Only after the CAS Server validates successfully does the provider receive the user/attributes and load application authorities.
- `AuthenticationManager` must have a **CasAuthenticationProvider** that supports that authentication request token type.

Do not write an `@GetMapping("/login/cas")` controller to read `ticket` and return a username directly. That belongs to the security filter chain and protocol client.

## 4. What Does `CasAuthenticationFilter` Do and Not Do?

**CasAuthenticationFilter** is a Spring Security **`AbstractAuthenticationProcessingFilter`**. For stateful browser CAS:

1. Processes only requests matching the configured **`filterProcessesUrl`**, defaulting to **/login/cas**.
2. Extracts `ticket` from the request parameter.
3. Creates an authentication request carrying the CAS ticket.
4. Invokes `AuthenticationManager.authenticate(...)`.
5. On success, applies the session strategy / success handler and persists **`SecurityContext`** via the properly configured `SecurityContextRepository`.
6. On failure, delegates to the failure handler and does not create an authenticated session.
7. If a request cache is present, it can return the user to the originally requested resource.

**Not the filter's standalone responsibility:**

- Validating tickets by string-comparing STs or checking an `ST-` prefix.
- Contacting the CAS Server by itself without a properly wired provider/validator.
- Trusting `username`, `roles`, or `tenant` parameters sent by the browser on the callback.
- Verifying proxy chains or service ticket lifecycles without a CAS validator.
- Granting business permissions simply because CAS returned a username.
- Automatically logging out CAS SSO/TGT or other applications simultaneously.

### 4.1. API Differences Across Spring Security Versions

**Note when cross-referencing docs:** some sections of the Spring Security CAS guide originate from older versions and describe `UsernamePasswordAuthenticationToken` with a special **`CAS_STATEFUL_IDENTIFIER`** principal. However, **current Spring Security 7.x** Javadocs describe `CasAuthenticationFilter` creating **`CasServiceTicketAuthenticationToken`** with `CasServiceTicketAuthenticationToken.CAS_STATEFUL_IDENTIFIER`, and `CasAuthenticationProvider` accepting that token type.

Comparison table:

| Documentation / Version | Request Token Description | Action Required |
| --- | --- | --- |
| Older CAS guides / pre-API-change versions | `UsernamePasswordAuthenticationToken` using a CAS-specific principal | Check the exact Javadoc for your project's version |
| Spring Security 7.x Javadoc | `CasServiceTicketAuthenticationToken` using a CAS-specific principal | Use filter and provider from the same compatible release |
| Successful authentication result | `CasAuthenticationToken` containing assertion and authorities | Never treat the initial request token as already authenticated |

**Do not hard-code a request token class from older docs and expect a newer provider to accept it.** Use APIs, filters, and providers from **the same Spring Security release line**, and run integration tests after upgrades.

Sources: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html and https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html .

## 5. `ServiceProperties`: The Most Important URL Contract

One of the most common deployment bugs is a **service URL mismatch** between when CAS issues an ST and when the application validates it.

Correct configuration example:

~~~text
ServiceProperties.service
  = https://portal.example.test/login/cas

CasAuthenticationFilter.filterProcessesUrl
  = /login/cas

CAS service registry
  permits https://portal.example.test/login/cas

CAS /login?service=...
  requests this service

CAS /serviceValidate?service=...
  sends this exact service
~~~

**The CAS Protocol binds an ST to the service for which it was issued.** The CAS Server must verify that the ticket is presented to the exact matching service during validation. An ST issued for `https://portal.example.test/login/cas` **must not** validate successfully for `https://reports.example.test/login/cas`.

### 5.1. Exact Matching and Normalization

The following URLs can **differ** at the service identity level:

~~~text
https://portal.example.test/login/cas
https://portal.example.test/login/cas/
http://portal.example.test/login/cas
https://portal.example.test:8443/login/cas
https://portal.internal:8080/login/cas
~~~

Check your **CAS service matching policy**: the CAS specification defines explicit service comparison, though some deployments implement custom matching/normalization in the service registry. To stay safe, **never rely on unguaranteed leniency**: pin one public HTTPS URL and use it consistently across CAS login, validation, and filter configuration.

**The service URL sent for validation does not include the newly received `ticket` query parameter**, unless a special profile/service identity was explicitly designed that way. Never pass the entire callback URL including `?ticket=ST-...` as a new service, because it will not match the service at issuance time.

### 5.2. Reverse Proxy and SSL Termination

A Java application may run as:

~~~text
Public: https://portal.example.test/login/cas
Ingress: https://edge.example.test -> http://app:8080
Internal servlet path: /login/cas
~~~

`ServiceProperties.service` must be the **CAS-registered public service URL**, not `http://app:8080/login/cas`. If the app is deployed under context path `/portal`, the service must reflect the actual path, such as `https://portal.example.test/portal/login/cas`.

- Configure `X-Forwarded-Proto`, `X-Forwarded-Host`, or `Forwarded` headers only from **trusted proxies**.
- Never use a client-controlled `Host` header to determine `service` arbitrarily.
- The CAS service registry should use an exact allowlist or tightly anchored patterns—**never allow all HTTPS URLs just for testing convenience**.
- Verify the actual `service` URL on both login redirects and validation requests using instrumentation **with tickets redacted**.

## 6. Ticket Validation Is the Trust Decision Step

`CasAuthenticationProvider` uses the CAS Java client's **`TicketValidator`** to send the ticket verification request to the CAS Server. For CAS 2.0, an example endpoint call is:

~~~text
GET https://sso.example.test/cas/serviceValidate
    ?service=https%3A%2F%2Fportal.example.test%2Flogin%2Fcas
    &ticket=ST-opaque-abc
~~~

For CAS 3.x when user attributes are needed, the server may expose **/p3/serviceValidate** with a compatible validator (such as **Cas30ServiceTicketValidator** in the Apereo CAS Java client). Do not mix 2.0, 3.0, JSON/XML, or proxy validators arbitrarily; test against your actual server and version.

**Important:** sending validation requests to the CAS Server must use **properly verified TLS** (certificate chain and hostname verification, never disabling SSL verification). If an attacker can forge the `TicketValidator` response, the application can be tricked into accepting a spoofed identity. Treat only a **successful response from a trusted CAS endpoint** as input to create an `Authentication`.

### 6.1. Example Successful `serviceValidate`

CAS Protocol 2.0 returns XML like the following (abbreviated):

~~~xml
<cas:serviceResponse
    xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-42</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

This is a **response structure template**, not a response from a live server. In a CAS 3.0 deployment with attributes, `/p3/serviceValidate` may also return:

~~~xml
<cas:serviceResponse
    xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-42</cas:user>
    <cas:attributes>
      <cas:employeeNumber>E-0042</cas:employeeNumber>
      <cas:department>engineering</cas:department>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Which attributes are released depends on the **CAS server attribute repository + service registry attribute release policy**. Never assume every application automatically receives complete groups, emails, departments, or a stable subject.

### 6.2. Example Failed Validation

~~~xml
<cas:serviceResponse
    xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    The service did not match the issued ticket.
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

Besides **INVALID_SERVICE**, you may encounter:

| Code / Situation | Primary Meaning | Handling |
| --- | --- | --- |
| **INVALID_TICKET** | Ticket does not exist, expired, already used, or unsuitable | Reject and initiate a new login flow |
| **INVALID_SERVICE** | Service sent for validation does not match the ticket's issued service | Reject; fix service URL/registry |
| **INTERNAL_ERROR** | CAS Server encountered an error while validating | Fail closed; appropriate monitoring/retry flow |
| TLS/timeout | Application cannot reach the trusted CAS Server | Fail closed; never offline-trust a ticket |
| XML/JSON parse error | CAS response is incompatible with the validator or malformed | Fail closed; fix profile/version |
| User disabled / no local mapping | CAS verified identity but app denies access | Do not create an `Authentication` with business privileges |

**Never send raw XML, tickets, TGC cookies, or SSO identifiers to public logs** for debugging; log a correlation ID, ticket-free service URL, HTTP status, and filtered error codes instead.

### 6.3. CAS Verifies the Service; Spring Still Resolves Local Users

A CAS **`authenticationSuccess`** response can supply a username, authentication date, attributes, and proxy chain. `CasAuthenticationProvider` then uses **UserDetailsService / AuthenticationUserDetailsService** to resolve **`GrantedAuthority`** values or a local user record per policy. If the local account is locked or disallowed from using the app, login must still be denied even though CAS verified a valid ST.

**CAS answers "who this person is according to CAS"; the application still decides "what they may do in this service."** Never map arbitrary attributes/groups to admin authority without an allowlist and authorization policy.

## 7. A Service Ticket Is Validated Only Once

Per the CAS specification:

- An ST is issued **for one service**.
- An ST **must be valid for only one validation attempt**, even if that attempt fails.
- Unused STs must have a short TTL and expire after the CAS Server's configured window.
- Tickets must have high entropy and be unpredictable.

Example:

~~~text
CAS issues ST-001 for service A.

A validate(ticket=ST-001, service=A) -> SUCCESS, ticket consumed.
A validate(ticket=ST-001, service=A) again -> INVALID_TICKET.

CAS issues ST-002 for service A.
B validate(ticket=ST-002, service=B) -> INVALID_SERVICE, ticket consumed.
A tries to reuse ST-002 -> INVALID_TICKET.

CAS issues ST-003 for service A.
Ticket expires before validation -> INVALID_TICKET.
~~~

**Do not cache an ST as an application-side session credential.** After successful validation, Spring should retain **`SecurityContext`/`HttpSession`**, avoiding ticket re-validation on every stateful request. Do not "retry 3 times with the same ST" when CAS returns `INVALID_SERVICE`; the first attempt already consumed the ST—the right fix is correcting the service URL and **initiating a new login to obtain a fresh ticket**.

### 7.1. Is Ticket Exposure in the Query String Dangerous?

Yes. An ST acts as a bearer-style credential during the brief window **before it is validated**. If the ticket leaks via browser history, referrer headers, proxy logs, or analytics before the application validates it, an attacker can try using it against **the service for which it was issued**.

Mitigations:

- Use HTTPS exclusively from CAS to browser and to the service.
- Set **`Referrer-Policy: no-referrer`** or equivalent on callbacks/sensitive areas; control redirects.
- **Redact `ticket` from access logs, reverse proxies, APM, traces, and error reporting.**
- Restrict scripts and third-party assets on the callback page.
- Never pass an ST into JavaScript/frontend state or persistent storage.
- After successful login, redirect to a clean URL without the ticket where appropriate.
- Never use an ST as a long-lived API token.

Single-use tickets shrink the reuse window, but **do not eliminate all pre-validation race risks**.

## 8. Roles of Spring Security Components

| Component | Responsibility | Common Mistake |
| --- | --- | --- |
| **CasAuthenticationEntryPoint** | Starts CAS login redirect when a resource requires authentication | Using the wrong CAS login URL or redirecting directly to `/login/cas` |
| **ServiceProperties** | Declares service identity and `renew`/`authenticateAllArtifacts` options | `service` differs from public URL or filter path |
| **CasAuthenticationFilter** | Receives ticket callback and builds the authentication request | Assuming a ticket in the URL means the user is logged in |
| **AuthenticationManager** | Routes to the matching provider | Forgetting to register a provider that handles CAS ticket tokens |
| **CasAuthenticationProvider** | Calls `TicketValidator`, loads `UserDetails`, produces auth result | Mixing CAS servers/tenants or trusting browser-supplied claims |
| **TicketValidator** | Contacts CAS Server to verify ticket and service, returns assertion | Disabling TLS verification or using the wrong CAS version endpoint |
| **UserDetailsService** | Maps CAS username to local account and authorities | Auto-granting `ROLE_ADMIN` from unapproved query params or attributes |
| **SecurityContextRepository** | Retains `Authentication` across stateful requests | Filter succeeds yet session is never persisted |
| **AuthenticationSuccessHandler** | Redirects user back to requested resource or target URL | Open redirect or leaving the ST in the URL |
| **AuthenticationFailureHandler** | Displays error without creating an authenticated session | Exposing raw tickets or validation internals to the browser |

Cleanly separating **redirect, ticket validation, session persistence, and local authorization** makes debugging precise: an HTTP 302 to CAS does not mean auth succeeded, and a CAS XML success does not mean the user is authorized for every resource.

## 9. Spring Security 7.x: Complete Java Configuration Showing All Wiring Points

Spring Security provides the **spring-security-cas** module. The following configuration illustrates a Servlet application using **stateful CAS Service Tickets** with Spring Security 7.x and current Java APIs. This is a **class inside a Spring Boot project with full dependencies and a `UserDetailsService`**; it is not a standalone file compiled with plain JDK.

### 9.1. Dependencies

`build.gradle` (Groovy DSL), assuming compatible Spring Boot dependency management is applied:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-cas'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Do not mix arbitrary CAS Client / Spring Security versions manually.** CAS support and Apereo Java CAS Client are normally resolved via the dependency graph; with a Spring Boot BOM, verify **actual version compatibility** and package classes in your project. Several APIs changed across Spring Security 5/6/7, such as token types and Jakarta Servlet packages. The code below targets documented 7.x API usage; run compile and integration tests on your organization's exact version before production.

### 9.2. Security Configuration

File `CasSecurityConfig.java`:

~~~java
package com.example.portal.security;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class CasSecurityConfig {
    private static final String CAS_BASE =
        "https://sso.example.test/cas";
    private static final String SERVICE =
        "https://portal.example.test/login/cas";

    @Bean
    ServiceProperties casServiceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService(SERVICE);
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
            ServiceProperties casServiceProperties,
            UserDetailsService userDetailsService) {
        CasAuthenticationProvider provider = new CasAuthenticationProvider();
        provider.setKey("portal-cas-provider-v1");
        provider.setServiceProperties(casServiceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(CAS_BASE));
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }

    @Bean
    SecurityFilterChain casSecurityFilterChain(
            HttpSecurity http,
            ServiceProperties casServiceProperties,
            CasAuthenticationProvider casAuthenticationProvider)
            throws Exception {
        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(CAS_BASE + "/login");
        entryPoint.setServiceProperties(casServiceProperties);

        CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setServiceProperties(casServiceProperties);
        casFilter.setAuthenticationManager(
            new ProviderManager(casAuthenticationProvider));
        casFilter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        casFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .authenticationProvider(casAuthenticationProvider)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .addFilterAt(casFilter, CasAuthenticationFilter.class);
        return http.build();
    }
}
~~~

### 9.3. Reading the Code by Responsibility

- **`ServiceProperties.setService`**: fixed public HTTPS service registered at the CAS Server and matching the callback URL handled by the filter.
- **`setSendRenew(false)`**: example allows reusing an existing CAS SSO session. If the system requires primary-credential reauthentication, configure `renew` properly for both login and validation.
- **`CasAuthenticationEntryPoint`**: redirects to `CAS_BASE + "/login"` with `service`.
- **`Cas20ServiceTicketValidator`**: performs CAS 2.0 ticket validation against the server base URL. If CAS 3 attributes are needed, use a compatible validator/profile rather than merely renaming the endpoint string by hand.
- **`CasAuthenticationProvider.setKey`**: internal provider/token identifier per contract, **not a cryptographic secret or CAS private key**.
- **`setUserDetailsService`**: local account loader. The application must provide a real `UserDetailsService` bean and authorization policy; the example does not fabricate sample usernames/passwords.
- **`CasAuthenticationFilter.setFilterProcessesUrl`**: ensures the callback is **`/login/cas`** and matches the path portion of `service`.
- **`setAuthenticationManager(new ProviderManager(...))`**: connects the filter to the CAS provider; do not just declare a provider bean and assume the filter discovers it.
- **`setSecurityContextRepository`**: persists `SecurityContext` in the session upon successful authentication. Current filter Javadocs note that the default repository does not necessarily persist across requests, so stateful setups should configure this explicitly.
- **`setSessionAuthenticationStrategy`**: rotates the session ID on login to mitigate session fixation; choose based on your actual setup.
- **`addFilterAt`**: inserts the filter into the Spring Security filter chain; never invoke `CasAuthenticationFilter` directly from a controller.

**Limitations of this example:** this is a minimal configuration for studying the ST path and excludes CAS-side service registry setup, logout/SLO, reverse proxy config, deployment TLS, health endpoints, resource authorization, password management, and testing. Check **package/method differences across Spring Security 6.x/7.x**, especially where newer versions change `SecurityContextRepository` requirements. Do not deploy this snippet as production-complete without running integration tests.

### 9.4. Avoiding Double Execution of the Filter

Spring Boot can automatically register any `jakarta.servlet.Filter` bean with the Servlet container **outside** the security filter chain if you expose it as a standard `@Bean`. Therefore, the example above **instantiates `CasAuthenticationFilter` inside the `SecurityFilterChain` method** instead of declaring a separate `@Bean CasAuthenticationFilter` that could accidentally create two registrations. If a real app needs a separate Filter bean, control Servlet `FilterRegistrationBean` and security chain ordering explicitly.

### 9.5. Where Success and Failure Handlers Fit

`CasAuthenticationFilter` inherits success/failure handler configuration from `AbstractAuthenticationProcessingFilter`. In a real application you can:

- Use **`SavedRequestAwareAuthenticationSuccessHandler`** to return users to the originally requested resource.
- Use a failure handler that directs to a CAS-appropriate error page without leaking tickets.
- Prevent open redirects and audit `defaultTargetUrl` and the request cache.
- Configure proper security headers, cookie policies, and logging filters so `ticket` is never exposed.
- If the app defines multiple `SecurityFilterChain` beans, verify that the filter belongs to the chain matching `/login/cas`.

## 10. CAS Server Configuration: Registering the Service

The CAS Server typically maintains a **service registry** controlling which services are allowed to authenticate. Example contract details to align on:

~~~text
CAS base:           https://sso.example.test/cas
CAS login:          https://sso.example.test/cas/login
CAS validation:     https://sso.example.test/cas/serviceValidate
Registered service: https://portal.example.test/login/cas
Service owner:      Portal Engineering
Allowed protocol:   CAS 2.0 Service Ticket
User attributes:    username; optional employeeNumber
Transport:          HTTPS only
~~~

On the CAS Server side, registered services may be stored as JSON, YAML, or in a database; **no single config file format applies to every CAS version**. Never modify a production service registry blindly from an example, and never open an unconditional `.*` pattern.

### 10.1. Why Does the CAS Server Need an Allowlist?

If CAS permits any arbitrary service URL, an attacker can trick CAS into redirecting the browser to an attacker-controlled endpoint or abuse an open service registry to obtain tickets in phishing scenarios. The CAS Protocol recommends managing permitted services and preferring HTTPS.

Register services according to:

- Proper public `https` scheme.
- Host/path belonging to the service's owning domain.
- Owner metadata, dev/UAT/prod environment, and exact callback.
- Per-service attribute release policy.
- Restriction of sensitive attributes, audit permissions, and change history.
- No service regexes containing overly broad host/path wildcards.

### 10.2. Never Send Passwords or TGTs to the Application

The SP/service receives only an **ST** and exchanges it for an assertion. The browser holds the **TGC** scoped to the CAS domain; the Spring app should never read the TGC cookie or store a TGT. Asking the CAS Server to "send the user's password" to the application to create a session is an architectural anti-pattern. CAS federation exists specifically to keep services from handling passwords directly.

## 11. `UserDetails`, CAS Attributes, and Local Authorization

After CAS validates the ST, the provider can obtain the username and attributes:

~~~text
CAS response:
  user            = employee-42
  employeeNumber  = E-0042
  department      = engineering

Local application:
  externalIdentity = (CAS issuer/service, employee-42)
  userId           = 865bb18a...
  enabled          = true
  tenant           = business-a
  roles            = [ROLE_REPORT_READER]
~~~

`employee-42` is only an example. Do not assume `cas:user` is globally unique across all CAS realms or tenants if your system integrates multiple CAS Servers. You may need to scope by **CAS provider / tenant / realm + subject** to avoid colliding users who share the same username string.

**`UserDetailsService` is not a ticket validator.** It runs **after CAS validation** to map the account, check enabled/locked status, and load authorities. If the application loads users from a database:

- Reject locked or deprovisioned accounts.
- Use a stable external ID if CAS provides one; agree on how username renames/reuse are handled.
- Never grant user or tenant roles merely because the browser sent `department=admin`.
- If CAS attributes are used for authorization, enforce an allowlist, contract/issuer scoping, and auditing.
- Enforce data-level authorization in local APIs rather than assuming any CAS-authenticated user may read all resources.

### 11.1. CAS 2.0 and CAS 3.0 Attributes

CAS 2.0 `/serviceValidate` returns success XML with `user`. CAS 3 `/p3/serviceValidate` supports returning attributes per service policy. If the application needs attributes and does not receive them:

1. Check whether the **validator** uses a compatible CAS 3 profile (e.g., `Cas30ServiceTicketValidator`).
2. Check whether the **CAS Server attribute repository** actually holds the data.
3. Check whether the **registered service attribute release policy** permits releasing those attributes.
4. Check whether `AuthenticationUserDetailsService` / custom mapping reads the assertion properly.
5. Never fall back to reading user roles from `/login/cas?role=admin` query params.

## 12. Stateful Service Tickets and Proxy Tickets Are Different Modes

### 12.1. Browser Stateful Authentication

The case covered in this lesson:

~~~text
Browser GET /login/cas?ticket=ST-...
CasAuthenticationFilter
   -> stateful authentication request
   -> CAS Service Ticket Validator
   -> local SecurityContext/HttpSession
~~~

After login, subsequent HTTP requests rely on the **local session**. Do not send an ST on every request. `ServiceProperties.authenticateAllArtifacts` normally **does not need to be enabled** in a single-URL stateful callback setup.

### 12.2. Stateless / Proxy Authentication

CAS also provides a **Proxy Ticket** mechanism for Service A calling Service B on a user's behalf:

~~~text
User -> Service A (already CAS-authenticated)
Service A -> CAS /proxy (using a valid PGT)
CAS -> PT issued for Service B
Service A -> Service B?ticket=PT-...
Service B -> CAS /proxyValidate?ticket=PT-...&service=B
~~~

This is an advanced capability **not required** for Service Ticket login. Spring Security Javadocs note that `CasAuthenticationFilter` can process proxy tickets across multiple URLs when:

- `ServiceProperties.authenticateAllArtifacts = true`.
- `ServiceAuthenticationDetailsSource` is used to build the **current service URL** accurately for validation.
- The provider uses a **proxy ticket validator**, such as `Cas20ProxyTicketValidator`, with a configured proxy chain policy.
- An appropriate `StatelessTicketCache` is configured when the protocol does not maintain an `HttpSession`, with strict security bounds.

**Do not enable `authenticateAllArtifacts=true` out of habit.** It lets the filter inspect artifacts on many URLs, increasing the risk of processing tickets in the wrong context. For a standard web app logging in via CAS, **stateful ST and `/login/cas` are normally sufficient**.

### 12.3. Proxy Chains Must Restrict Allowed Sources

Older examples sometimes show `acceptAnyProxy=true`. That may suffice for a lab, but it is **unsafe as a production default**. When using proxy authentication:

- Allow only **proxies on an approved allowlist**.
- Validate HTTPS proxy callbacks/PGTs strictly per spec.
- Scope where PTs may be used and enforce tight TTLs.
- Control `StatelessTicketCache` keys and eviction policies.
- Never confuse a PT with an ST: a service expecting browser STs must not accept PTs blindly.

## 13. `renew`, `gateway`, and `authenticateAllArtifacts`

These three options serve distinct purposes:

| Option | Meaning | Caution Required |
| --- | --- | --- |
| **`renew=true`** on CAS login | Demands authentication with primary credentials instead of reusing an existing SSO session | Not synonymous with MFA or all reauth steps; depends on CAS policy |
| **`gateway=true`** | Non-interactive login attempt; if no SSO session exists, may return without a ticket | Must handle callbacks with no ticket; never mark as authenticated |
| **`authenticateAllArtifacts=true`** on Spring side | Allows the filter to process ticket/proxy artifacts on URLs other than `filterProcessesUrl` | Requires service URL details and proxy validator; do not enable for simple stateful STs |

The CAS Protocol specifies that **`renew` and `gateway` must not be combined**; follow CAS Server documentation carefully if using either. If `gateway` returns without a ticket, the application must continue treating the request as **unauthenticated**, never trusting a `gateway` query flag or falling back to a higher-privileged anonymous user.

## 14. Standalone Java 17: Simulating Single-Use Service Tickets and Service Binding

The following program runs on **JDK 17+** with no CAS Server or Spring dependencies. It simulates the **CAS Server side** using an in-memory ticket registry to demonstrate:

- A ticket is issued for **one specific service**.
- Valid ticket + matching service + within TTL -> returns the principal confirmed by the registry.
- A single validation attempt **consumes** the ticket; a subsequent attempt fails.
- Wrong service, trailing `/` difference, expired ticket, or missing ticket -> rejected.
- A spoofed `user=admin` from the browser cannot override the username; only the registry/validator result is trusted input.

**Important limitation:** `FakeCasServer` **is not a CAS Server**; it omits cryptographic authentication, HTTPS, HTTP transport, CAS XML, Spring Security, and the CAS Java Client. `validate` in this simulation exists **solely to teach one-time/service-binding mechanics** and never replaces a production CAS `TicketValidator`. Never expose a method like this to browsers with a browser-supplied registry. All ticket data here is synthetic in-program test data.

File **CasServiceTicketLifecycleDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class CasServiceTicketLifecycleDemo {
    record Ticket(String value, String service, String username, Instant issuedAt) {}
    record Validation(boolean success, String username) {
        static Validation rejected() { return new Validation(false, ""); }
    }

    static final class FakeCasServer {
        private final Map<String, Ticket> issued = new ConcurrentHashMap<>();
        private final Set<String> allowedServices = Set.of(
            "https://portal.example.test/login/cas",
            "https://reports.example.test/login/cas");
        private final Duration ttl = Duration.ofSeconds(30);

        void issue(String ticket, String service, String username, Instant now) {
            if (!allowedServices.contains(service)) {
                throw new IllegalArgumentException("Unregistered service");
            }
            if (issued.putIfAbsent(ticket, new Ticket(
                    ticket, service, username, now)) != null) {
                throw new IllegalArgumentException("Duplicate ticket");
            }
        }

        Validation validate(String presentedTicket,
                            String requestedService, Instant now) {
            if (presentedTicket == null || presentedTicket.isBlank()) {
                return Validation.rejected();
            }
            // Simulates the CAS rule: ST is invalidated after validation attempt.
            Ticket original = issued.remove(presentedTicket);
            if (original == null) return Validation.rejected();
            if (!allowedServices.contains(requestedService)) {
                return Validation.rejected();
            }
            if (!original.service().equals(requestedService)) {
                return Validation.rejected();
            }
            if (now.isBefore(original.issuedAt())
                    || !now.isBefore(original.issuedAt().plus(ttl))) {
                return Validation.rejected();
            }
            return new Validation(true, original.username());
        }
    }

    public static void main(String[] args) {
        final String portal = "https://portal.example.test/login/cas";
        final String reports = "https://reports.example.test/login/cas";
        final Instant started = Instant.parse("2026-01-01T10:00:00Z");
        final FakeCasServer cas = new FakeCasServer();

        cas.issue("ST-opaque-1", portal, "employee-42", started);
        Validation accepted = cas.validate(
            "ST-opaque-1", portal, started.plusSeconds(2));
        System.out.println("serviceTicketAccepted=" + accepted.success());
        System.out.println("trustedUser=" + accepted.username());
        System.out.println("callbackUserIgnored="
            + !"admin-from-query".equals(accepted.username()));
        System.out.println("replayRejected=" + !cas.validate(
            "ST-opaque-1", portal, started.plusSeconds(3)).success());

        cas.issue("ST-opaque-2", portal, "employee-42", started);
        System.out.println("wrongServiceRejected=" + !cas.validate(
            "ST-opaque-2", reports, started.plusSeconds(2)).success());
        System.out.println("mismatchConsumesTicket=" + !cas.validate(
            "ST-opaque-2", portal, started.plusSeconds(3)).success());

        cas.issue("ST-opaque-3", portal, "employee-42", started);
        System.out.println("expiredTicketRejected=" + !cas.validate(
            "ST-opaque-3", portal, started.plusSeconds(31)).success());

        cas.issue("ST-opaque-4", portal, "employee-42", started);
        System.out.println("serviceUrlExact=" + !cas.validate(
            "ST-opaque-4", portal + "/", started.plusSeconds(2)).success());

        cas.issue("ST-opaque-5", reports, "analyst-7", started);
        System.out.println("otherServiceAccepted=" + cas.validate(
            "ST-opaque-5", reports, started.plusSeconds(2)).success());

        System.out.println("missingTicketRejected=" + !cas.validate(
            "", portal, started.plusSeconds(2)).success());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CasServiceTicketLifecycleDemo.java
java CasServiceTicketLifecycleDemo
~~~

**Exact stdout**:

~~~text
serviceTicketAccepted=true
trustedUser=employee-42
callbackUserIgnored=true
replayRejected=true
wrongServiceRejected=true
mismatchConsumesTicket=true
expiredTicketRejected=true
serviceUrlExact=true
otherServiceAccepted=true
missingTicketRejected=true
~~~

**Interpretation:**

- **`serviceTicketAccepted=true`**: ticket is valid and service matches.
- **`trustedUser=employee-42`**: username comes from the **validator/registry**, not a browser-chosen query param.
- **`callbackUserIgnored=true`**: spoofed input at the callback does not determine the principal.
- **`replayRejected=true`**: a consumed ST cannot be reused.
- **`wrongServiceRejected=true`**: Portal's ST is rejected for Reports.
- **`mismatchConsumesTicket=true`**: even a failed attempt with the wrong service consumes the ticket.
- **`expiredTicketRejected=true`**: an ST past its TTL is rejected.
- **`serviceUrlExact=true`**: a service URL with a differing trailing slash can be rejected under exact matching.
- **`otherServiceAccepted=true`**: Reports can use a separate ST issued specifically for Reports.
- **`missingTicketRejected=true`**: without an ST, authentication is rejected.

**Never run this program as a real auth endpoint.** It holds state in memory and does not handle distribution, restarts, browser redirects, CAS Server clock sync, or TLS security. Its goal is to demonstrate why **`ServiceProperties.service` must match** and why an ST is **single-use**.

## 15. Real-World Integration: Layered Testing

Before production, run end-to-end tests against a staging CAS Server and two registered services.

### 15.1. Happy-Path Test Plan

1. Visit **`https://portal.example.test/private`** without a local session.
2. Confirm Spring redirects to **CAS `/login?service=...`** with the exact service URL.
3. CAS authenticates and redirects the browser back to **`/login/cas?ticket=ST-...`**.
4. Spring `CasAuthenticationFilter` receives the callback; `CasAuthenticationProvider` calls the CAS Server validation endpoint.
5. Validation sends **ticket + exact service**; CAS returns **`authenticationSuccess`** and the username.
6. Provider loads `UserDetails`, checks enabled/locked status, and grants authorities per policy.
7. Spring persists **`Authentication`** and redirects to `/private`; subsequent requests rely on the local session.
8. Visit CAS Login from a second app to verify TGT/TGC and SSO behavior where permitted.

You do not need to view real tickets to prove success: log statuses and policy-hashed correlation IDs instead.

### 15.2. Negative Test Matrix

| Case | Input | Expected Result |
| --- | --- | --- |
| Callback without ticket | `GET /login/cas` | No `Authentication` created |
| Fake ticket | `ticket=ST-fake` | Rejected by CAS validation |
| Reused ticket | Already-validated ST | CAS returns `INVALID_TICKET` |
| Wrong service URL | Issued by CAS for Portal, validated as Reports | CAS returns `INVALID_SERVICE` |
| Trailing slash mismatch | Registered without trailing `/`, validated with `/` | Fails per matching policy |
| HTTP instead of HTTPS | `service=http://...` differs from registered HTTPS | Rejected; fix proxy/config |
| Expired ticket | ST exceeds TTL before validation | Rejected; initiate new login |
| CAS Server timeout | Cannot call `/serviceValidate` | Fail closed; do not create user |
| Invalid CAS TLS certificate | Untrusted hostname/chain | Fails; never disable TLS validation |
| CAS XML missing `authenticationSuccess` | Invalid/failure response | Fails; do not parse username ad hoc |
| Malformed CAS response | Broken XML/JSON or wrong namespace | Fails; do not bypass parser |
| Service absent from CAS registry | CAS rejects the service URL | Rejected per service registration |
| Local user disabled | CAS succeeds, app user disabled | No authenticated session created |
| Local user missing | CAS succeeds, no mapped user | Rejected or JIT per policy; never auto-grant privileges |
| Callback has `username=admin` | Ticket belongs to employee | Real username still comes from CAS validation |
| Callback has `roles=ADMIN` | CAS did not issue that role | `ROLE_ADMIN` not granted |
| CAS 2 validator when CAS 3 attributes needed | Incompatible validator/profile | Test catches missing attrs; fix config |
| Two CAS realms | Ticket from CAS A sent to app configured for CAS B | Rejected by CAS B |
| Two services | Portal's ST sent to Reports | Rejected |
| Proxy ticket sent to `serviceValidate` | PT instead of ST | Rejected per profile |
| Proxy trust disabled | PT presented at another endpoint | Not processed as stateful ST |
| Wrong stateless cache | Cache returns user out of scope | Tested/blocked in dedicated proxy design |
| Filter missing `AuthenticationManager` | Callback arrives but provider never runs | Config error caught before production |
| Filter on wrong path | `/callback` instead of `/login/cas` | Filter ignores it; fix service/processing URL |
| Filter in wrong `SecurityFilterChain` | `/login/cas` outside CAS chain | Fails to authenticate; fix matcher/order |
| `SecurityContext` not persisted | Callback succeeds but next request is anonymous | Configure stateful repository/session |
| Session fixation | Browser keeps old session ID after login | Session authentication strategy must rotate ID properly |
| Local logout | App clears session, CAS TGT remains | Can SSO again via **new ST**, not ST reuse |
| CAS logout | CAS TGT revoked | Never assume all app sessions are cleared unless SLO works |
| Reverse proxy host spoof | Client forges `X-Forwarded-Host` | Attacker cannot dictate service URL/callback |
| ST appears in logs | Proxy logs full query string | Redact; treat ticket exposure as incident |
| Overly broad CAS service registry | Wildcard for arbitrary domains | Reject improper onboarding |

### 15.3. Separating Three Failure Layers

~~~text
A. Browser never returns to /login/cas:
   CAS login URL, service registry, DNS/TLS, redirect, path.

B. Callback arrives but CAS validation fails:
   Used/expired ticket, wrong service, CAS SSL/trust,
   CAS 2/3 protocol, validation endpoint/profile.

C. CAS validation succeeds yet app still returns 403/anonymous:
   UserDetails/authorities, SecurityContextRepository,
   session fixation/cookie, SecurityFilterChain/authorization.
~~~

**Never "fix" Layer B errors by bypassing `TicketValidator` or creating a "temporary `Authentication`."** Find and correct the service URL, certificate, or server compatibility issue.

## 16. Detailed Troubleshooting

| Symptom | Possible Cause | Useful Checks |
| --- | --- | --- |
| Redirect loop CAS <-> app | Service URL mismatch causes ST validation failure | CAS registry, `ServiceProperties.service`, public URL |
| Browser has ticket but Spring does not authenticate | `/login/cas` mismatches `filterProcessesUrl` or filter missing from chain | Filter order, request matcher, path/context |
| `INVALID_SERVICE` | CAS service issued for ST differs from validation service | URL scheme/host/port/path/query, proxy |
| `INVALID_TICKET` on first attempt | ST expired, pre-consumed, unsynced CAS cluster ticket registry | CAS logs; never reuse ST |
| `INVALID_TICKET` on refresh | Browser refreshes callback URL containing consumed ST | Clean redirect after success; do not treat refresh as login |
| CAS Server `SSLHandshakeException` | Untrusted CA chain/hostname | JVM truststore, CAS server cert |
| CAS Server 404 `/serviceValidate` | Wrong base URL or endpoint | CAS 2/3 validation profile and context path |
| Java XML parser error | Incompatible CAS XML, or proxy/middleware returning HTML | HTTP status, `Content-Type`, parser, CAS logs |
| CAS success yet login fails | `userDetailsService` missing or disabled user | Principal mapping, local user state |
| 403 after CAS success | Authenticated but lacks required local authority | Authorities mapping / authorization policy |
| Spring Security 7 token mismatch | Legacy code checks `UsernamePasswordAuthenticationToken` | v7 Javadoc `CasServiceTicketAuthenticationToken` and provider |
| Session missing after callback | `SecurityContext` not persisted, cookie/`HttpSession` policy | `setSecurityContextRepository`, session store |
| Only on multi-node | App sessions not shared or CAS ticket store out of sync | Spring Session, CAS ticket registry, load balancer |
| Only in production | Public host, context path, trusted headers differ from UAT | Public URL vs. CAS registered service |
| Login prompts for password every time | `renew=true`, CAS TGT expired, browser not sending TGC | CAS login policy, cookies |
| `gateway` returns without ticket | User has no CAS SSO session | Handle anonymous cleanly per profile |
| Confused Proxy Ticket with ST | PT sent to `/serviceValidate` | Proxy validator/config/proxy policy |
| Still accesses app after CAS logout | Local `HttpSession` remains; no Single Logout | Integrate CAS SLO / separate session invalidation |
| Referrer/logs contain ST | Query callback logged by web/proxy | Redaction + `Referrer-Policy` and clean redirect |

### 16.1. Safe Logging Pattern

~~~text
event=CAS_ST_VALIDATION_FAILED
registration=portal-cas-prod
service=https://portal.example.test/login/cas
casEndpoint=https://sso.example.test/cas/serviceValidate
status=INVALID_SERVICE
requestId=trace-7f4e
elapsedMs=132
~~~

**Never write `ticket` to logs**, and never embed it in exception URLs or traces. Log usernames/attributes only when policy and privacy permit; logging an entire `CAS Assertion` can expose personal data.

### 16.2. Distinguishing CAS Auth Success from Local Authorization

A CAS-verified user may still receive HTTP 403 because they lack permission to read a resource. Inspect:

- `CasAuthenticationToken.isAuthenticated()` and authorities in the context under controlled logging.
- Whether `UserDetailsService` correctly mapped the external subject to a local user.
- Whether DB roles, tenant membership, and app policy permit access.
- Whether another filter chain resets `Authentication` or creates an anonymous context.
- Whether CSRF on a business POST rejects the request after login.

Do not blame every HTTP 403 on a broken CAS service ticket.

## 17. Pre-Production Security Checklist

- [ ] Clearly distinguished CAS Server, SP/service, ST, TGT/TGC, PT/PGT, and application `HttpSession`.
- [ ] Spring includes **spring-security-cas** compatible with dependencies / `cas-client`.
- [ ] `CasAuthenticationEntryPoint` redirects to the right CAS login URL and sends the **public service URL**.
- [ ] `ServiceProperties.service` matches the **registered service URL** and aligns with callback `filterProcessesUrl`.
- [ ] CAS service registry permits only valid HTTPS services, with no permissive wildcards.
- [ ] `CasAuthenticationFilter` sits in the right `SecurityFilterChain` with a proper `AuthenticationManager`.
- [ ] `CasAuthenticationProvider` has a `TicketValidator` calling the **trusted CAS Server**.
- [ ] TLS and hostname verification to the CAS validation endpoint **are never disabled**.
- [ ] ST is never treated as a JWT, username, long-lived session token, or self-readable string.
- [ ] ST is validated **once**, never cached as a credential, and fails closed on expiry/replay.
- [ ] App never trusts username/group/tenant sent by the browser to `/login/cas`.
- [ ] CAS success only authenticates a user if `UserDetails`/local policy permits; disabled accounts are denied.
- [ ] `SecurityContext` is persisted with the repository/session strategy required by the Spring version.
- [ ] Session ID rotates upon successful login per session fixation policy.
- [ ] Logging/proxy/APM/Referer redact the **`ticket` query parameter** and sensitive CAS Assertions.
- [ ] Service URL cannot be altered by untrusted `Host`/`X-Forwarded-Host` headers.
- [ ] If CAS 3 attributes are required, the validator/endpoint and attribute release policy are tested.
- [ ] `authenticateAllArtifacts`, proxy validators, and `acceptAnyProxy` are disabled when only browser ST login is needed.
- [ ] If proxy tickets are used, trusted proxy chains, PGT storage, and cache scope are strictly bounded.
- [ ] Request token version verified: Spring Security 7 **`CasServiceTicketAuthenticationToken`**; legacy docs may differ.
- [ ] Integration tests run against a real CAS Server or compatible test server, not only mocked ST unit tests.
- [ ] Rollback and config audit procedures exist for CAS URL, service registry, or TLS certificate changes.
- [ ] Local logout and CAS Single Logout are distinct flows; never assume app sessions end when CAS TGT expires without SLO.
- [ ] Monitoring tracks `INVALID_SERVICE`, `INVALID_TICKET`, TLS errors, user mapping failures, and redirect loops.

## 18. Self-Check Questions

**1. Why is `/login/cas?ticket=ST-...` insufficient proof that a user is authenticated?**

Because the ticket could be supplied by the browser itself. The filter must pass the ticket to the provider/validator so the CAS Server verifies it was issued for the right service, is unexpired, and has not been used.

**2. Does `CasAuthenticationFilter` call CAS `/serviceValidate` directly?**

Normally the filter passes the authentication request to **AuthenticationManager -> CasAuthenticationProvider**; the provider's **TicketValidator** sends the validation request to the CAS Server.

**3. What is `ServiceProperties.service` used for?**

It is the service identity / public callback URL sent to CAS login to issue the ticket and resent during validation. It must match the CAS-registered service and the URL handled by the filter.

**4. Why can switching HTTPS to HTTP or adding a trailing slash cause `INVALID_SERVICE`?**

Because service identity comparison can require an exact match. A ticket is issued only for the specified service, not arbitrary look-alike URLs.

**5. Can a CAS Service Ticket be reused after a successful validation?**

No. Per the CAS protocol, an ST is valid for only one validation attempt, even if that attempt fails. After stateful login, the app maintains its own session.

**6. Is a CAS TGT the same as the ST in the callback?**

No. The TGT represents the SSO session at CAS; the ST is issued by CAS specifically for one service and is single-use. The browser holds the TGC for CAS and does not send the TGT to `/login/cas`.

**7. Does CAS validation success mean the user is granted `ROLE_ADMIN` in the app?**

Not yet. The provider/`UserDetailsService` must map the account, check enabled/locked status, and assign authorities per local policy. CAS authentication is distinct from application authorization.

**8. Why must the response from `/serviceValidate` travel over verified TLS?**

Because the application relies on CAS's response to decide who the user is. If an attacker could spoof a CAS response or alter the username, they could forge an unauthorized `Authentication`.

**9. In Spring Security 7, what is `CasAuthenticationFilter`'s request token?**

Current Javadocs describe **`CasServiceTicketAuthenticationToken`**; older CAS docs may mention **`UsernamePasswordAuthenticationToken`**. Always check the API of the version you use.

**10. How do CAS 2.0 Service Tickets and CAS 3.0 attributes differ?**

CAS 2.0 service validation returns the user result; CAS 3.0 offers `/p3/serviceValidate` to return attributes per policy. Use a compatible validator/client and a CAS Server configured to release attributes.

**11. When should `authenticateAllArtifacts` be enabled?**

When implementing proxy or stateless CAS artifact authentication with a dedicated design, accurate service URL details, and a proper proxy validator. Do not enable it for standard browser ST login on `/login/cas`.

**12. Why can a user quickly SSO back in via CAS right after logging out of the app?**

Because the local session was cleared while the CAS TGT/TGC may still be active; CAS issues a **new ST** without prompting for a password again. That is not the old ST being reused.

**13. If the browser refreshes a consumed ST callback URL and gets `INVALID_TICKET`, what should be done?**

Never revalidate a consumed ST. Redirect to a clean URL after login and initiate a new login when needed, while auditing success handlers and callback caching.

**14. Can an ST issued for Reports be used to log in to Portal?**

No. Tickets are bound to the receiving service. The CAS Server must reject the mismatch, even if both apps belong to the same organization or CAS realm.

**15. Should ticket validation be implemented using only an in-app `Map`?**

No. The Java 17 `Map` in this article is merely a **CAS Server simulation** to teach one-time/service-binding rules. Production uses `TicketValidator` talking to a real CAS Server with TLS, a service registry, and proper session policies.

## 19. Official References

- Spring Security, **CAS Authentication**: entry point flow, `CasAuthenticationFilter`, `ServiceProperties`, `CasAuthenticationProvider`, `TicketValidator`, stateful/proxy tickets: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security Javadoc, **`CasAuthenticationFilter`**, `/login/cas` callback, `ServiceProperties`, `CasServiceTicketAuthenticationToken`, and `SecurityContextRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
- Spring Security Javadoc, **`CasAuthenticationProvider`**, `setServiceProperties`, `setTicketValidator`, `setUserDetailsService`, and CAS token handling: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Spring Security Javadoc, **`ServiceProperties`**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html
- Spring Security, **Servlet Authentication Architecture**, `AuthenticationManager`/`ProviderManager`, and `SecurityContext`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Apereo CAS, **CAS Protocol Specification 3.0**, `/login`, `/serviceValidate`, `/p3/serviceValidate`, single-use Service Tickets, and `INVALID_SERVICE`: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS, **CAS Protocol Ticket Validation**, service matching strategy: https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html
- Apereo Java CAS Client, **README**, Cas20/Cas30 `ServiceTicketValidator`s and proxy filter variants: https://github.com/apereo/java-cas-client/blob/master/README.md
- Apereo CAS, **Troubleshooting Guide**, invalid ticket/service and missing attributes: https://apereo.github.io/cas/development/installation/Troubleshooting-Guide.html

**Takeaway:** `CasAuthenticationFilter` receives an **opaque Service Ticket** at the `/login/cas?ticket=...` callback and sends an authentication request to **CasAuthenticationProvider**. The provider uses **TicketValidator to call the CAS Server** and verify that the ticket matches **`ServiceProperties.service`**, is unexpired, and has not been used. Only then does Spring Security have trusted username/attributes to build a **`CasAuthenticationToken`**, save the local session, and enforce business authorization. **The service URL must be consistent; STs are single-use; a ticket is not a user, not a TGT, and must never be trusted without CAS validation.**