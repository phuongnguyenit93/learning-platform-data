# Enabling `saml2Login` and Identifying Required Public Endpoints

> **Scope:** SAML2 Registration in Spring Security (**Service Provider/Relying Party** application using **SAML 2.0 Web Browser SSO**). This lesson focuses on enabling the SAML login filter, identifying protocol URLs that the browser/IdP must reach before a session exists, and protecting all remaining business resources.

## 1. Expected Outcomes

After completing this lesson, you will be able to:

1. Explain why a SAML Service Provider (SP) application requires certain URLs to be **reachable while unauthenticated**, whereas business pages must still require authentication.
2. Enable `http.saml2Login(...)` in `SecurityFilterChain` and understand its relationship with `RelyingPartyRegistrationRepository`.
3. Accurately identify commonly used URLs: landing/login page, `AuthnRequest` initiation endpoint, **Assertion Consumer Service (ACS)** receiving `SAMLResponse`, **SP metadata** export endpoint, and optional Single Logout.
4. Configure `authorizeHttpRequests` using an **allowlist**, distinguishing `permitAll()` from excluding a URL entirely from the filter chain.
5. Explain why the ACS must accept POSTs from an unauthenticated browser while **still strictly validating the SAML Response**.
6. Build a Java 17+ Spring Boot example and test behavior when unauthenticated, when SAML succeeds, and when proof is invalid.
7. Recognize common pitfalls: accidentally opening `/**`, blocking ACS/metadata, wrong `registrationId`, wrong URLs due to a reverse proxy, CSRF failures, wrong certificates, and missing SAML logout.

**Key point:** "Public endpoint" means only that **no existing user session is required before the request is handled**. For SAML URLs, this is a protocol flow requirement, **not access to user data**.

## 2. Roles and Steps of Web SSO

In Spring Security SAML:

- **Asserting Party (AP), Identity Provider (IdP):** authenticates users and issues `SAML Response` containing identity assertions.
- **Relying Party (RP), Service Provider (SP):** the Spring application requiring login; sends `AuthnRequest`, receives `SAMLResponse` via ACS, validates it, and creates `Authentication`/local session.
- **`RelyingPartyRegistration`:** configuration binding one RP with one AP, containing `registrationId`, SP `entityId`, ACS endpoint, IdP SSO URL, verification certs, and signing options.
- **`RelyingPartyRegistrationRepository`:** where Spring looks up registrations when constructing requests or validating responses. Spring Boot can auto-create this bean from `spring.security.saml2.relyingparty.registration` when configured completely.

Typical SP-initiated SSO flow:

```text
(1) Browser                  Spring SP                     SAML IdP
       |                         |                             |
       | GET /private            |                             |
       |------------------------>|                             |
       |    no Authentication yet|                             |
       |<----- 302 login/SSO ----|                             |
       |                         |                             |
       | GET /saml2/authenticate/training                      |
       |------------------------>|                             |
       |<--- redirect AuthnRequest (SAMLRequest, RelayState) --|
       |                                                       |
       |------------- browser goes to IdP SSO ---------------->|
       |                     IdP login                         |
       |<------------- HTML page POST SAMLResponse ------------|
       |                                                       |
       | POST /login/saml2/sso/training                        |
       |------------------------>|  verify SAMLResponse        |
       |                         |  create Authentication + sess|
       |<----- redirect /private |                             |
       | GET /private + cookie   |                             |
       |------------------------>|                             |
       |<--------- 200 ----------|                             |
```

URLs at the initiation step and ACS must be available before a session exists. Spring's filters execute **before controller-level authorization**. Only after a valid response does the application have an authenticated user to serve `/private`, `/account`, or business routes.

**Note:** IdP-initiated SSO may lack a corresponding `AuthnRequest`; whether to accept it, `InResponseTo` constraints, and anti-replay must follow protocol/IdP policy. This exercise uses SP-initiated as the default to observe the full request–response correlation mechanism.

## 3. Listing Access Points by Purpose

The following paths are **default/common values in Spring Security SAML2 Login**. They are not a custom REST API you write yourself, and can vary with DSL customizations, versions, or reverse proxies.

| Path or Path Group | Method / Caller | Prior Session Required? | Actual Role |
| --- | --- | --- | --- |
| `/`, `/about`, public assets `/css/**`, `/js/**`, `/images/**` | GET, browser | **No** | Landing/login UI pages and static assets intentionally published by the app |
| `/login` | GET, browser | **No** | Spring's default generated login page, or a custom page with a controller |
| `/saml2/authenticate/{registrationId}` | Usually GET, browser | **No** | `Saml2WebSsoAuthenticationRequestFilter` builds `AuthnRequest` and redirects browser to IdP; some versions support `registrationId` query variants |
| `/login/saml2/sso/{registrationId}` | Usually POST, browser carrying IdP response | **No** | **ACS** processed by `Saml2WebSsoAuthenticationFilter`; logs in only if `SAMLResponse` is valid |
| `/login/saml2/sso` | POST in supporting configs/versions | **No** | ACS variant without registrationId in path; registration resolution must have a proper mechanism |
| `/saml2/metadata` | GET, IdP/admin/tool | **No, if intentionally exposed** | Exports metadata of SP registrations when `saml2Metadata(...)` is enabled |
| `/saml2/metadata/{registrationId}` | GET, IdP/admin/tool | **No, if exposed** | Metadata of a specific RP registration |
| `/saml2/service-provider-metadata/{registrationId}` | GET, IdP/admin/tool | **No, if exposed** | Compatible metadata endpoint name supported by Spring; **not synonymous with ACS** |
| `/logout` | Usually POST, browser with session | Per Spring logout mechanism | Ends local session; POST typically requires a CSRF token in session-based apps |
| `/logout/saml2/slo` | POST when SAML Single Logout is configured | Must accept appropriate IdP messages | Receives SAML LogoutRequest/LogoutResponse; **does not appear automatically via `saml2Login` alone** |
| `/private`, `/account/**`, `/admin/**`, business APIs | GET/POST/..., browser/client | **Yes** (and specific permissions) | Content that must be protected with `authenticated()` or explicit permission rules |

**Three easily confused concepts:**

1. **AuthnRequest endpoint** is the **outbound** point toward the IdP via the browser; it does not process `SAMLResponse`.
2. **ACS** is the **inbound** point from the IdP. Even though the browser POSTs without a login session, `SAMLResponse` must pass the SAML validator. Never write a custom controller to Base64-decode and trust `NameID`.
3. **SP metadata endpoint** publishes public configuration that the IdP needs to know, such as `entityID`, ACS, and public certificates when configured. It **differs** from IdP metadata, which the SP uses to obtain the IdP entity ID, SSO URL, and verification certificate.

A URL should be made public only if it genuinely serves a public page or the SAML protocol. Paths such as `/actuator/**`, `/admin/**`, `/api/**`, and `/internal/**` must never be added to the allowlist just to "make login work".

## 4. Preparing the Application and SAML2 Registration

### 4.1. Dependencies and Versions

Examples assume **Java 17+**, a compatible Spring Boot/Spring Security servlet stack, and a configured **test SAML2 IdP**. In Maven, use the Spring Boot parent/BOM to manage versions of the relevant dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
</dependencies>
```

This is a **dependencies snippet** to place inside `pom.xml` of a complete Spring Boot Maven project, not a full `pom.xml`. With Gradle, pick the equivalent dependencies. Exact APIs can vary across major versions, so match Spring Security documentation/versions to your application instead of mixing Spring Security 5, 6, and 7 examples.

### 4.2. Declaring an RP Registration Named `training`

`src/main/resources/application.yml` illustrating **manual IdP configuration**:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          training:
            assertingparty:
              entity-id: https://idp.example.test/saml
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.example.test/saml/sso
                sign-request: false
```

**Prerequisites to run for real:** `https://idp.example.test/...` and `idp-signing.crt` are illustrative values only, **not immediately usable servers/certificates**. Replace them with the **real** `entityID`, SSO URL, and X.509 certificate **of an approved test IdP**. Place the PEM/DER certificate in a format supported by Spring config at `src/main/resources/saml/idp-signing.crt`. The certificate is used to **verify signatures from the IdP**, not as the SP's private key.

Depending on the IdP, configuration can be loaded from **trusted IdP metadata** instead of entering each field manually:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          training:
            assertingparty:
              metadata-uri: https://idp.example.test/saml/metadata
```

This is an **alternative approach**; do not mix it indiscriminately with the manual entry template. If loading metadata at startup, the SP may fail to start if the IdP metadata endpoint is unreachable; plan caching/refresh and trust management per environment.

`training` is the `registrationId` used in the example URLs. With defaults, Spring uses equivalent values:

- **SP entityID:** `{baseUrl}/saml2/service-provider-metadata/{registrationId}`.
- **ACS:** `{baseUrl}/login/saml2/sso/{registrationId}`.
- **AuthnRequest:** `/saml2/authenticate/{registrationId}`.

For example, if the app's public URL is `https://app.example.test`, the ACS is `https://app.example.test/login/saml2/sso/training`. Register the **exact** SP `entityID` and HTTPS ACS on the IdP system. Never equate the app-chosen `registrationId` with the protocol-validated `entityID`.

**Why `sign-request: false`?** This value is only for when a test IdP permits unsigned `AuthnRequest`s. If the IdP requires signed requests, configure the **SP signing certificate/private key** and update metadata/SP registration; never turn off a production IdP's signing requirement just to get connected.

## 5. Enabling `saml2Login` and Defining the Allowlist in Java

File `src/main/java/com/example/samllab/SecurityConfig.java`, used in a Spring Boot application with package `com.example.samllab`:

```java
package com.example.samllab;

import jakarta.servlet.DispatcherType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                // Needed for application error dispatches
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()

                // Truly public landing pages, login page, and UI assets
                .requestMatchers(HttpMethod.GET,
                    "/", "/about", "/login", "/error",
                    "/css/**", "/js/**", "/images/**",
                    "/favicon.ico").permitAll()

                // Initiate SAML SSO, export metadata for IdP/partners
                .requestMatchers(HttpMethod.GET,
                    "/saml2/authenticate/**",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()

                // ACS receives SAMLResponse via HTTP POST from browser
                .requestMatchers(HttpMethod.POST,
                    "/login/saml2/sso",
                    "/login/saml2/sso/**").permitAll()

                // Business authorization rules must precede general rules
                .requestMatchers("/admin/**").hasRole("ADMIN")

                // All other business URLs require authentication
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

**The class above is part of a Spring Boot application**, not a single-file program runnable with `javac SecurityConfig.java` because it requires dependencies and a bean context. It uses the `jakarta.servlet.DispatcherType` import appropriate for Spring Boot 3+/Spring Security 6+. In the same source package, a minimal startup application can be:

```java
package com.example.samllab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlLabApplication.class, args);
    }
}
```

You can add a controller to observe access rules:

```java
package com.example.samllab;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SAML SP is ready";
    }

    @GetMapping("/private")
    public String privateArea(Authentication authentication) {
        return "Authenticated via SAML";
    }
}
```

At `/private`, the `Authentication` parameter is only validly populated after login; the example intentionally **does not return the full SAML assertion or sensitive attributes** in the response. Real resources must still check business authorization. `/about` only needs to remain in the allowlist if the app actually provides that public page; `permitAll` **does not create routes/controllers**.

### 5.1. Line-by-Line Configuration Analysis

- `authorizeHttpRequests(...)` applies rules top-down by **first matching matcher**. The `/admin/**` rule comes before `anyRequest().authenticated()` to require stronger privileges than basic login.
- `.saml2Login(Customizer.withDefaults())` adds SAML login configuration. Spring registers the required filters to generate `AuthnRequest`, process `SAMLResponse` at the ACS, and create the authentication object. Without a valid `RelyingPartyRegistrationRepository`, login **cannot work on its own**.
- `.saml2Metadata(Customizer.withDefaults())` **enables SP metadata export**. It is not the same as login functionality; metadata may need to be provided to the IdP so it knows the SP entityID and ACS.
- `.requestMatchers(...).permitAll()` lets a request **pass URL authorization checks without a session**, without removing `SecurityFilterChain`. Steps such as SAML signature verification, anti-replay, security headers, and CSRF on other endpoints remain active.
- `.requestMatchers(HttpMethod.POST, "/login/saml2/sso/**")` reflects that the ACS receives **POSTs without an existing session**. If the request contains forged SAML, wrong signature, wrong issuer, wrong time window, or wrong audience, **the authentication filter must still reject it**.
- `.dispatcherTypeMatchers(DispatcherType.ERROR)` supports the application's error dispatcher. If an error page displays sensitive info, restrict error data returned to users; `permitAll` is no reason to leak stack traces.
- `.requestMatchers("/admin/**").hasRole("ADMIN")` is merely an example authorization rule. **SAML group/permission attributes do not automatically turn into `ROLE_ADMIN`**; trusted mapping and application tests are needed. Someone who just completed SAML login may still receive `403` at `/admin/**` because they lack the role.

With only **one** IdP, Spring can send the browser straight into the login flow; with multiple registrations, the login UI typically offers an IdP choice. Exact navigation behavior depends on custom login page config, sessions, and version.

### 5.2. When Using a Custom Login Page

Example HTML on a public login page:

```html
<a href="/saml2/authenticate/training">Sign in with IdP</a>
```

When setting `.saml2Login(saml2 -> saml2.loginPage("/login"))`, you must **implement** `GET /login` yourself (controller and view/HTML), permit that URL in `authorizeHttpRequests`, and provide a link to `/saml2/authenticate/training`. Declaring a custom login page **does not auto-generate the HTML page**. Never link directly to the ACS as a login button: the ACS is solely for responses from the IdP.

For SP-initiated flows, users can visit `/private` and let Spring initiate the redirect, or navigate directly to `/saml2/authenticate/training`. Both lead to IdP authentication, provided registrations and session/correlation work properly.

## 6. Public Does Not Mean Insecure: Mandatory Protection Layers

### 6.1. The ACS Must Accept POSTs Before a User Has a Session

`SAMLResponse` is usually delivered by the IdP through the browser using **HTTP-POST binding**. Therefore a browser **not yet authenticated at the SP** must be able to POST to the ACS. Yet this endpoint **is not a login API accepting arbitrary username/password or JSON**. Spring Security processes the response via `Saml2WebSsoAuthenticationFilter` and the corresponding SAML/OpenSAML verifier.

Items to validate on the response, per binding and profile:

- IdP/entityID is in the trusted list and message/assertion signatures are verified per policy.
- `AudienceRestriction`/`Recipient`/`Destination` target the exact SP/ACS.
- `NotBefore`/`NotOnOrAfter`, validity window, anti-replay, and `InResponseTo` correlation for SP-initiated flows.
- Success response status, subject/`NameID`, and other SAML profile constraints.
- HTTPS transport and proper signing certificate/rollover management.
- Group/role attributes from the IdP are converted into SP permissions only after explicit verification and mapping.

**Never add an arbitrary `@PostMapping("/login/saml2/sso/...")`** to receive SAMLResponse manually and decode Base64. Opening a controller in place of the filter can bypass protocol checks and introduce identity spoofing vulnerabilities.

### 6.2. ACS and CSRF: Narrow Exemption, Never Disable App-Wide

Spring Security protects against CSRF by default for state-changing requests in apps using **session cookies**. However, a SAML HTTP-POST from an IdP does not carry the SP app's CSRF token. `saml2Login` registers a **targeted CSRF exemption for the corresponding WebSSO processing endpoint**; business form POST endpoints still require CSRF protection.

**Never use** `csrf(AbstractHttpConfigurer::disable)` for the entire web app just because the ACS needs to accept POSTs. If you customize `loginProcessingUrl`/ACS matcher, verify that the CSRF exemption applies **precisely to the real URL**, never opening `/login/**`, `/**`, or all POSTs broadly. `permitAll` is a **URL authorization** rule, **distinct** from bypassing CSRF checks; adding `permitAll` does not fix a CSRF mismatch.

Do not confuse `POST /logout` using a session cookie with the SAML ACS callback. Local logout usually goes through Spring's logout mechanism with proper CSRF; if SAML SLO is enabled, use the framework's SLO endpoints/filters and validate logout message signatures.

### 6.3. `permitAll` Differs from `web.ignoring()`

`permitAll()`: requests still pass through Spring Security filters, retaining relevant authentication/protocol safeguards and security headers. `web.ignoring()`: excludes requests from the Spring Security filter chain; this can skip essential filters or security headers. For metadata, login pages, and static assets, **prefer `permitAll`** whenever possible. Never use `web.ignoring("/login/saml2/sso/**")` or `web.ignoring("/saml2/**")` to fix a 403 error.

### 6.4. Expose Only What the IdP Actually Needs

**SP metadata** is typically a public document containing entityID, ACS, bindings, and **public** certificates. Allowing GET from the IdP/operator does not require exposing it to the open Internet if organizational policy calls for controlled metadata exchange. You can distribute it via admin channels or restrict ingress access, as long as the IdP can obtain metadata and cert updates.

Never put **private keys**, secrets, raw SAML assertions, session cookies, or tokens into metadata or logs. Do not return a metadata list covering all tenants if the system has legitimate reasons to limit tenant enumeration; in that case use per-registration endpoints or private metadata exchange.

## 7. Single Logout Is a Separate Add-On Feature

`saml2Login` handles **login**, and does not automatically enable SAML **Single Logout (SLO)**. If you only need to end the local session, use Spring's local logout. If both IdP and SP support SLO, configure SP logout message signing, metadata with logout endpoints, request/response handling policies, and add:

```java
http
    .saml2Logout(Customizer.withDefaults());
```

This is an **addition to the same `HttpSecurity`**, not a standalone `SecurityFilterChain` or complete Java program. SAML logout flows typically need `/logout/saml2/slo` (or the configured URL) accepting POSTs from the IdP; docs and versions vary on path variants, so cross-check URLs against live metadata and config. Never put all `/logout/**` URLs under `permitAll` out of habit.

SLO works only when **the IdP supports it**, the SP has signing keys/certificates, and both sides are configured accordingly. Test both **SP-initiated logout** and **IdP-initiated logout**; ending the local session **does not guarantee** the SSO session at the IdP has ended.

## 8. Multiple SecurityFilterChains, Reverse Proxies, and URL Configuration

### 8.1. Chain-Level Matchers Differ from Authorization-Level Matchers

When a project has multiple filter chains, `securityMatcher("/api/**")` routes only API requests into that chain. If you put `saml2Login` in a chain matching only `/private/**`, endpoints like `/saml2/authenticate/**` and `/login/saml2/sso/**` **may not be handled by that chain**.

Conceptual example:

```text
Chain #1: /api/**                -> Resource Server (Bearer token)
Chain #2: remaining URLs         -> SAML2 Login + metadata + web session
```

In this setup, ensure the second chain is registered and handles **all of AuthnRequest/ACS/login/metadata**. Putting `permitAll` authorization matchers on the wrong chain will not fix the problem. Verify `@Order`, `securityMatcher`, and which filter chain actually handles each URL.

With Spring Boot, defining a custom `@Bean SecurityFilterChain` causes Boot's default security config to back off; you must then **explicitly call `saml2Login`** in the right chain. Having the SAML2 dependency on the classpath does not mean a custom chain enables SSO automatically.

### 8.2. HTTPS, baseUrl, and Forwarding Headers

SP metadata and AuthnRequests can contain `entityID`, ACS URL, and `Destination`. URLs derived from `{baseUrl}` depend on the **scheme, host, and port Spring sees**. Behind a TLS-terminating reverse proxy, if Spring thinks it is at `http://internal-host:8080`, metadata may advertise the wrong ACS even when browsers use `https://app.example.org`.

Measures:

1. Assign a canonical HTTPS domain for the SP and register it accurately at the IdP.
2. Configure the proxy to forward scheme/host accurately; the backend **must trust forwarded headers only from trusted proxies**, and the proxy must strip spoofed headers sent directly by clients.
3. Choose the forwarded-header strategy suited to Spring Boot/container, such as `server.forward-headers-strategy` when topology requires it.
4. After deployment, **inspect live SP metadata** and compare `entityID`, ACS URL, and bindings with IdP config; test browser redirects and POST callbacks.
5. Never skip TLS/host verification or "patch" SAMLResponse to bypass a `Destination`/`Recipient` mismatch.

Reverse-proxy URL errors are a frequent cause of login loops: after the IdP authenticates successfully, the browser POSTs to an ACS with the wrong host or HTTP, and the SP fails to complete the session.

### 8.3. Post-Login Redirects and RelayState

The application should return users to their intended page **solely via trusted saved-request/navigation mechanisms**. Never take raw `RelayState` or a `next` parameter from an unauthenticated request and call `sendRedirect` to an arbitrary URL: that creates an open redirect. RelayState serves SAML request/response correlation and is not a license to redirect to arbitrary domains.

## 9. Testing Each Endpoint Against a Matrix

Assume the RP runs at `https://app.example.test` and the test IdP is properly registered. The commands below are illustrative; replace FQDNs/certificates with your live environment and **never use `curl -k` to bypass TLS**.

```bash
curl -i https://app.example.test/
curl -i https://app.example.test/login
curl -i https://app.example.test/saml2/metadata/training
curl -i https://app.example.test/saml2/authenticate/training
curl -i https://app.example.test/private
```

**Meaning of results:**

| Test | Expected Outcome |
| --- | --- |
| GET `/` without cookie | HTTP 200 with "SAML SP is ready" if controller is created |
| GET `/login` without cookie | Public login page or redirect to IdP per config; does not require prior login session |
| GET `/saml2/metadata/training` | HTTP 200 with SAML metadata XML if `saml2Metadata`/registration are valid; metadata contains valid entityID/ACS |
| GET `/saml2/authenticate/training` | Starts SSO, typically 302 to IdP's SAML SSO endpoint with `SAMLRequest` |
| GET `/private` without cookie | Never returns private data; typically redirects to login/SSO via 302 in web apps |
| POST `/login/saml2/sso/training` with fake form/no SAMLResponse | **Does not log in successfully**; returns error response/redirect per failure handler |
| Browser completes valid SAMLResponse from IdP | SP verifies, creates session, GET `/private` returns 200 |
| Logged-in user without `ROLE_ADMIN` | Access to `/admin/**` must be denied if endpoint exists |
| Expired SAMLResponse, wrong issuer/audience/signature, wrong recipient, replay | SP rejects authentication even though ACS is a "public" URL |
| GET `/internal/config` without session | Cannot access data; prompts login or denies per chain/policy |

**Browser testing is mandatory** to verify bindings, cookies, and sessions, because seeing 302/200 via `curl` does not prove the full authentication flow. After successful login, inspect Network in DevTools but **never copy/post raw SAMLResponse or session cookies** to public issues or docs.

You can run a Maven app with Boot parent using:

```bash
./mvnw spring-boot:run
```

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. If IdP metadata/cert/config is incomplete, the app may fail to start or redirect/login may fail; that is an integration error, not proof that the allowlist is wrong.

### 9.1. Isolated Access-Control Testing

A self-review should include:

1. Probe business URLs without cookies, ensuring **no private data is returned**.
2. Verify GET `/saml2/metadata/training` outputs accurate **SP metadata**, returning no private keys or secrets.
3. Verify GET `/saml2/authenticate/training` creates a request to the right IdP; an invalid registrationId must never silently map to an arbitrary IdP.
4. Send a forged POST to the ACS and confirm **no** authenticated session is created.
5. Use a SAMLResponse signed by the genuine test IdP; confirm actual access to `/private`.
6. Test unmapped claims/roles and `/admin/**`; valid authentication alone is insufficient for admin access.
7. Stop the test IdP or swap certificates in the test environment and retry, confirming login **fails closed** rather than falling back to unverified headers/emails.
8. Verify CSRF remains enforced on session-backed **business POSTs**; ACS is a narrow filter-level exemption.
9. Test local logout and, if SLO is enabled, bidirectional IdP ↔ SP logout per the agreed binding.

Exact HTTP status codes can depend on failure handlers, error pages, and request types. Base conclusions on the presence/absence of sessions and protected data, not a single isolated 302 or 403 status.

## 10. Common Errors and Diagnostics

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| Accessing `/private` returns 403 instead of redirect | Entry point, chain/matcher, or login config not applied | Identify which `SecurityFilterChain` handles the URL; ensure `saml2Login` is in the web chain |
| GET `/saml2/authenticate/training` returns 404 or misses IdP | Wrong registrationId, filter absent from chain, missing `RelyingPartyRegistrationRepository` | Check registration name, dependency, chain matcher, and IdP SSO URL |
| ACS `/login/saml2/sso/training` returns 403 CSRF | Changed ACS path mismatches CSRF exemption, or request misses filter | Check live ACS URL and filter/CSRF matcher; never disable CSRF app-wide |
| ACS returns 404 or authentication failure | IdP posts to different ACS than configured, missing/wrong response, wrong cert/signature/audience | Compare IdP ACS, SP metadata, redacted logs, and certificates |
| GET `/saml2/metadata/training` returns 404 | `saml2Metadata` not enabled or filter missing from chain | Enable metadata DSL in the web chain; verify active endpoint |
| GET metadata redirects 302 to login | Metadata lacks proper public rule, or another chain requires auth | Add GET metadata to the right chain's allowlist or exchange metadata over controlled channels |
| Login UI shows yet clicking login returns 404 | Link points straight to ACS or wrong registration name | Link must be `/saml2/authenticate/training` and registrationId must exist |
| Login succeeds yet `/admin` returns 403 | Role/authority not mapped or user lacks permission | Check `GrantedAuthority` and SAML attribute mapping; never remove `hasRole` to fix 403 |
| IdP authenticates yet loops back to login | Scheme/host/proxy mismatch, cookie/session dropped, wrong ACS, or assertion failure | Compare URL/cookies/SAML validation; fix trusted forwarded headers |
| SAML logs show timestamp error | Clock skew or expired/not-yet-valid assertion | Sync NTP, inspect `NotBefore`/`NotOnOrAfter`, never drop time checks |
| GET `/actuator/health`/static fails | Path not permitted or controller/resource missing | Permit only specific needed endpoints; **never** expose all of actuator/internal |
| Enabled `saml2Login` yet SAML Single Logout does not work | `saml2Logout` or signing credentials unconfigured, or IdP lacks support | Integrate SLO separately and test signed messages/bindings |
| One public rule accidentally bypasses all Security | Used `web.ignoring`, wrong chain matcher, or `permitAll("/**")` | Restore narrow allowlist; verify sensitive requests traverse filters |

**Optimal troubleshooting order:**

```text
1. Does the request URL hit the right SecurityFilterChain?
2. Does the URL match the corresponding SAML route/filter?
3. Is registrationId registered and IdP metadata/certificate valid?
4. Do the ACS/entityID exported in SP metadata match the IdP?
5. Are HTTP binding/method and CSRF matcher correct?
6. Does the Response have valid signature, issuer, audience, recipient, and time?
7. If login succeeds: are session cookie and GrantedAuthority created properly?
8. If still failing: check proxy/clock/cert/IdP logs without logging raw assertions.
```

## 11. Design Decisions to Document Explicitly in the Project

For each SP registration, concisely document:

- **Trusted IdP:** entityID, SSO endpoint, metadata source, and verification certificate.
- **SP public identity:** entityID, ACS URL, canonical HTTPS host, and accepted bindings.
- **Internal RegistrationId:** value and resolution method, especially with multiple IdPs/tenants.
- **Public URL allowlist:** login/asset pages, AuthnRequest endpoint, ACS, metadata exposed to IdP, and error dispatch.
- **Private URL policy:** business pages, APIs, admin, health/management endpoints; authorization beyond merely authenticated.
- **CSRF:** exact ACS exemption within `saml2Login`; keep CSRF protection on session-backed app POSTs.
- **Session:** Secure/HttpOnly cookies, SameSite suited for SAML POST flows and proxies, timeout, session fixation, and logout.
- **SLO enabled or not:** dedicated endpoints and signing certificate; never confuse local logout with IdP logout.
- **Monitoring:** audit authentication/authorization and signature/timestamp/issuer errors without logging raw assertions or private keys.
- **Regression testing:** both public paths must stay reachable unauthenticated, and all private paths must deny access when unauthenticated.

**Lesson completion criteria:** With a real registered test IdP, accessing `/private` while logged out initiates SAML SSO; `AuthnRequest` sends the browser to the right IdP; the IdP POSTs a valid `SAMLResponse` to the HTTPS ACS; Spring Security validates it and creates a session; the user can view only authorized resources. GET metadata operates per exposure policy. Non-allowlisted and unauthorized URLs remain blocked. When POSTing invalid signature/issuer/audience to the ACS, the SP must never create a session.

## 12. References to Cross-Check Against Your Active Version

1. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — `saml2Login`, `RelyingPartyRegistration`, AuthnRequest/ACS, and URI patterns.
2. [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — `/saml2/authenticate/{registrationId}` URL, signing, and bindings.
3. [Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html) — `saml2Metadata`, metadata endpoints, and publishing SP descriptors.
4. [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — matcher order, `permitAll`, `hasRole`, distinguishing chain matchers from authorization matchers.
5. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — protecting state-changing requests and narrow endpoint exemptions.
6. [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html) — SAML SLO, logout requests/responses, signing requirements, and endpoints.
7. [Spring Security — Saml2LoginConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html) — filters/endpoints configured by `saml2Login`.
