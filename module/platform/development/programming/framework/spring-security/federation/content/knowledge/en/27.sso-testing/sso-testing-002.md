# Testing Multiple Applications Sharing an IdP and Login Session

> **Module:** Spring Security – federation · **Parent topic:** SSO Testing. This Knowledge article explains how to test **cross-application Single Sign-On (SSO)** when Application A and Application B share an Identity Provider (IdP) while keeping **separate local HTTP sessions, client registrations, token audiences, and business permissions**. The content focuses on Spring Security OIDC Authorization Code, browser E2E, session isolation, logout scenarios, and comparisons with SAML2/CAS. SSO testing cannot simply be two passing `MockMvc.with(oidcLogin())` requests.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Accurately map the relationships between **IdP session**, **local session A**, **local session B**, cookie/browser context, authorization code, and ID Token audience.
2. Explain why sharing an IdP **does not mean** two applications share `JSESSIONID`, `SecurityContext`, access tokens, refresh tokens, or local authorities.
3. Configure two OIDC clients `client-A` and `client-B` with the same trusted issuer but separate client IDs, secrets, redirect URIs, and session cookies.
4. Run two Spring Boot instances from a single codebase behind an HTTPS proxy with two hostnames to eliminate false positives caused by `localhost` cookies.
5. Design a browser test within a **single browser context** verifying interactive login on A and session reuse on B at the IdP without a new credential ceremony.
6. Distinguish the count of **authorization requests**, **authorization code token exchanges**, and **interactive IdP authentication ceremonies**.
7. Test independent identity/tenant/roles, noting that OIDC `sub` may be **pairwise** per client/sector and never assuming `sub_A == sub_B`.
8. Apply `prompt=none`, `prompt=login`, `max_age`, `auth_time`, and `acr`/`amr` per contract; understand when the IdP must re-prompt for consent/MFA/reauthentication.
9. Distinguish local logout of A, OP session expiration, RP-Initiated Logout, and front-/back-channel Single Logout with or without delivery.
10. Know the meaning of `iss`, `aud`, `sid`/`sub`, `jti`, and `events` in an OIDC Back-Channel Logout Token, without confusing it with an ID Token or Servlet session ID.
11. Use Spring Security Test `oidcLogin()` for single-app controller/authorization testing without treating it as proof of two-app SSO.
12. Run an offline Java 17 program with deterministic stdout to distinguish two local sessions, the IdP session, logout, and browser profile isolation.
13. Design signed fixture tests/test-IdP E2E, negative tests, and chaos tests for SAML2, CAS, cookie SameSite, IdP outages, key rotation, and network issues.
14. Record logs/metrics safely, build an acceptance matrix, and write a runbook for diagnosing SSO failures.

**Baseline:** Java 17, Spring Boot 3.3.x/Spring Security 6.3.x are used as learning examples; before production, choose versions still receiving security patches. URLs `a.example.test`, `b.example.test`, and `idp.example.test` are illustrative—no live DNS/HTTPS or IdP is pre-deployed. Snippets marked *test fragment* require test infrastructure; only the standalone Java 17 example can run immediately without external services.

## 2. Model: One IdP, Three Independent Sessions

~~~text
                      +--------------------------+
                      |  OP / IdP                 |
                      |  idp.example.test         |
                      |  central SSO session      |
                      |  cookie IDP_SESSION       |
                      +-------------+------------+
                                    |
                           browser redirects
                         +----------+----------+
                         |                     |
          +--------------v------------+  +-----v-------------------+
          | App A: a.example.test     |  | App B: b.example.test  |
          | client_id=client-A        |  | client_id=client-B     |
          | cookie APP_A_SESSION      |  | cookie APP_B_SESSION   |
          | local app session A       |  | local app session B    |
          | APP_ORDER_READ            |  | APP_REPORT_READ        |
          +---------------------------+  +-------------------------+
~~~

Alice opens A:
1. The browser has no session A → A initiates an OAuth2/OIDC authorization request with `client_id=client-A`.
2. The browser reaches the IdP, and the user logs in/completes MFA per policy. The IdP creates its own **SSO session** on the browser.
3. The IdP returns an **authorization code for A** to callback A. A exchanges the code at the token endpoint, verifies the ID Token, and creates a **separate HTTP session at A**.
4. Alice opens B in the **same browser context**. The browser has no session B → B initiates a **new authorization request**, this time with `client_id=client-B`.
5. The browser is redirected to the IdP. If the IdP session is still valid, B's consent/assurance is satisfied, and policy does not require reauthentication, the IdP issues a code for B **without prompting for a password again**.
6. B verifies the ID Token for **audience B** and creates its own local session.
7. A/B can serve subsequent requests via local sessions without continuously calling the IdP.

### 2.1. Post-SSO State Table

| Component | Owning Authority | State After A+B Login | Scope |
| --- | --- | --- | --- |
| OP/IdP session | IdP | ACTIVE | Usually browser/IdP-specific. |
| A HttpSession | A/container/session store A | ACTIVE | A only. |
| B HttpSession | B/container/session store B | ACTIVE | B only. |
| ID Token A | Issued by IdP, verified by A | `aud=client-A` | Cannot be used as ID Token B. |
| ID Token B | Issued by IdP, verified by B | `aud=client-B` | Cannot be used as ID Token A. |
| Authorization Code A | Issued by OP for client A | Consumed once | Must not be transferred to B. |
| Authorization Code B | Issued by OP for client B | Consumed once | Must not be transferred to A. |
| Local role A | A/local authorization store | `APP_ORDER_READ` | Does not transfer to B automatically. |
| Local role B | B/local authorization store | `APP_REPORT_READ` | Does not transfer to A automatically. |

**One sign-in** typically means **one interactive ceremony at the IdP**, **not** only one authorization request. Even when the user sees no login form on B, the OP still receives an authorize request for B and issues a new code/token.

### 2.2. Browser Cookie Jar

~~~text
idp.example.test -> IDP_SESSION=op-1
a.example.test   -> APP_A_SESSION=a-71
b.example.test   -> APP_B_SESSION=b-29
~~~

A host-only cookie for A is not automatically sent to B, nor is a host-only IdP cookie copied into A/B cookies. **Ports are not part of cookie origin scope**: testing two apps on `localhost:8081`/`localhost:8082` with the same `JSESSIONID` can cause collisions. Reliable E2E tests should use **two hostnames** behind a TLS proxy rather than faking SSO by setting `Domain=.example.test` on app session cookies.

### 2.3. Distinguishing SSO from a Shared Application Session

Mistakes:
- Copying A's `JSESSIONID` cookie into B and asserting B returns 200.
- Configuring Spring Session Redis for A/B with the same namespace and accidentally sharing `SecurityContext`.
- Letting B trust an ID Token or access token with `aud=client-A`.
- Pre-creating session B before opening B, then concluding the IdP reused the session.
- Setting all endpoints to `permitAll`, seeing HTTP 200, and reporting PASS.

Correct: B must undergo **its own client B authentication flow** handled by the protocol verifier before creating session B, while the **IdP session from A** avoids re-prompting for credentials if policy permits.

## 3. Standard E2E Test Environment

| Location | Simulated URL | Verification Key |
| --- | --- | --- |
| IdP sandbox | `https://idp.example.test/realms/workforce` | OIDC Discovery, JWKS, test user, and real cookie session. |
| Application A | `https://a.example.test` | Registered client-A, callback A, cookie A. |
| Application B | `https://b.example.test` | Registered client-B, callback B, cookie B. |
| Callback A | `https://a.example.test/login/oauth2/code/central` | Exact match in A's allowed redirect URIs. |
| Callback B | `https://b.example.test/login/oauth2/code/central` | Exact match in B's allowed redirect URIs. |
| OIDC test user | `alice-test` | Active, clearly defined assurance policy. |
| Fresh browser | Empty cookie storage | Inherits no IdP/A/B sessions from prior tests. |
| Second browser | Separate profile/context | Not used to prove cookie sharing; used only to test isolation. |

You may use a Keycloak test realm or another IdP sandbox with:
- Two independent client registrations, two separate redirect URIs and logout URLs.
- A real SSO session with explicitly defined consent/remember-me/MFA policies.
- Audit events distinguishing **interactive authentication** from an authorization request reusing an existing session.
- Test signing keys/certificates and HTTPS trust, never production secrets.
- The ability to reset sessions between tests, manage test data, and disable/revoke test users.
- If testing Back-Channel Logout, the OP and both RPs must support/register endpoints, signature validation, and session mapping.

### 3.1. Do Not Use a “Test IdP” That Only Returns Mocked JSON

A mock `GET /authorize` returning a hardcoded HTTP 302 and a token endpoint returning a static ID Token can exercise one client flow, but **does not prove shared IdP browser cookie/SSO**. Multi-app testing requires a user-agent and an IdP enforcing session reuse/consent/reauthentication policies.

### 3.2. Executing in CI

- Each CI run gets an isolated namespace of users/clients/ports or sandbox.
- Create test users and inject credentials via a secret manager; never hard-code passwords/MFA seeds in Git.
- Do not persist Selenium/Playwright profiles across tests unless explicitly testing persistence.
- Use HTTPS with valid browser certs/trust; never disable TLS verification in production.
- Pin compatible browser/driver/IdP versions and retain anonymized audit event IDs, never cookies/tokens.
- Use state-based waits instead of overly broad `Thread.sleep(...)`; OIDC redirects have latency.
- Clean up local sessions, IdP sessions, and test users after each scenario rather than just closing tabs.

## 4. Happy Path Scenario: A Logs In, B Reuses the IdP Session

### 4.1. Sequence

~~~text
Browser context FRESH
    |
    | GET https://a.example.test/me
    v
App A -> IdP authorize (client-A, state_A, nonce_A, PKCE_A)
    |
    | IdP login user Alice (interactive)
    | IdP browser session OP-1 established
    v
IdP -> A callback with code_A/state_A
    |
    | A validates state/nonce/iss/aud/signature/time
    | A creates local session A-71
    v
GET /me at A -> 200, app=A, authenticated=true

SAME browser context:
    |
    | GET https://b.example.test/me
    v
App B -> IdP authorize (client-B, state_B, nonce_B, PKCE_B)
    |
    | Browser sends OP-1 IdP cookie
    | OP policy allows reuse: no new credential prompt
    v
IdP -> B callback with code_B/state_B
    |
    | B verifies token audience client-B, local identity
    | B creates local session B-29
    v
GET /me at B -> 200, app=B, authenticated=true
~~~

### 4.2. QA PASS Criteria

1. Before A, there is no app A session, B session, or OP browser cookie.
2. A initiates the proper `client-A` flow and completes one **interactive IdP authentication ceremony**.
3. A's ID Token `aud` matches A, and local session A is created after validation.
4. Before B, B has **no** local session yet.
5. B initiates **authorization request B** with its own `state_B`, `nonce_B`, and PKCE/code exchange B.
6. B reuses the OP browser session with **no second credential ceremony** under a policy requiring no step-up/consent.
7. B's ID Token `aud` matches B, session B is created, and B's authorization is independent.
8. Reloading A/B does not trigger a new flow while local sessions remain valid.
9. Cookies A and B are host-only and do not overwrite each other; the OP cookie belongs to the IdP.
10. IdP audit confirms one interactive sign-in despite **two authorization requests**.

**Do not check only** that A and B both return HTTP 200; local session leaks or `permitAll` controllers can produce false positives.

### 4.3. Automating with Selenium (Illustrative Fragment)

This snippet requires Selenium 4, JUnit 5, ChromeDriver, a real reverse proxy/test IdP, and test fixtures to complete login. **It is not a standalone runnable Java file**, unlike `MultiAppSsoSessionDemo` in section 11.

~~~java
// E2E test FRAGMENT in JUnit + Selenium:
WebDriver browser = new ChromeDriver();
try {
    browser.get("https://a.example.test/me");

    // Helper depends on the test IdP; never hard-code real passwords.
    completeInteractiveLoginAtTestIdp(
        browser, testCredentialsFromVault
    );

    WebDriverWait wait = new WebDriverWait(
        browser, Duration.ofSeconds(20)
    );
    wait.until(ExpectedConditions.urlContains("a.example.test"));

    // Parse JSON response/read test instrumentation to assert
    // app A authenticated. Do not rely only on URL or source text.
    assertEquals("A", readAppIdFromCurrentResponse(browser));

    // REUSE the same WebDriver/cookie jar for B.
    browser.get("https://b.example.test/me");
    wait.until(ExpectedConditions.urlContains("b.example.test"));
    assertEquals("B", readAppIdFromCurrentResponse(browser));

    // Instrumented test IdP: 2 authorization requests occurred
    // but only 1 interactive credential ceremony.
    assertEquals(2, testIdpAudit.authorizationRequests());
    assertEquals(1, testIdpAudit.interactiveLogins());
} finally {
    browser.quit();
}
~~~

`completeInteractiveLoginAtTestIdp`, `readAppIdFromCurrentResponse`, and `testIdpAudit` are **sandbox-dependent test harness helpers** that must be implemented; do not treat this snippet as standalone executable code. Selenium/Playwright runs in a real browser, yet results still require server-side audit checks rather than using screenshots as authentication proof.

### 4.4. Two Separate Browser Profiles

To test isolation, open a new profile `browser-private` **without the OP cookie**:
- Visiting B must trigger login/identity selection per policy, not inherit Alice from the work profile.
- If the device has IWA/Kerberos/passkey auto-authentication, the IdP may sign in quickly again **using a different method**, which must be kept separate from cookie SSO tests.
- Never use a different browser profile for step B in the **SSO happy path**, because doing so intentionally breaks browser cookie sharing.
- Browser tabs in the **same profile** typically share the cookie jar; they do not necessarily share in-memory JS state/localStorage across different origins.

## 5. Verifying the IdP Actually Reused the Session

**The browser not showing a login form** is an insufficient signal: a password manager/passkey/Windows IWA may auto-authenticate, or the browser may still hold a local session B from another test.

Prioritize:
- IdP audit recording **interactive** authentication events separately from authorize/token issuance events.
- Recording the IdP's internal OP session ID/ref for the same browser per privacy policy.
- A/B auditing callbacks with their respective `client_id` and local session generation.
- `auth_time` from validated ID Tokens as a supporting signal, without requiring equality across all profiles/IdP policies or replacing interactive flow logs.
- Whether B already had a local session before the request.
- Properly host-scoped cookies without exposing raw cookie values.

### 5.1. Non-Identical Counts

~~~text
authorization_requests  = 2   (A and B)
authorization_codes     = 2   (code_A, code_B)
token_exchanges         = 2   (each client exchanges its own code)
interactive_logins      = 1   (when OP session reuse succeeds)
local_sessions_created  = 2   (A and B)
~~~

If `interactive_logins=2`, check whether B intentionally required reauthentication/consent/step-up or the OP cookie was not sent. If `authorization_requests=1` yet B logs in “immediately” when B had no prior local session, check for a bypass or accidental session sharing.

### 5.2. A and B Need Not Have Equal `sub` Values

OIDC supports **pairwise subject identifiers**: the same person can be issued different `sub_A` and `sub_B` by the IdP per sector/client. Identity linking to local accounts must rely on **verified issuer + subject and an approved mapping**, or an authoritative directory crosswalk—never compare raw `sub` across clients as proof of SSO.

Matching email or `email_verified=true` also does not prove A and B represent the same local user; when testing two clients, verify the user via IdP test audits and trusted provisioning IDs rather than email alone.

## 6. OIDC `prompt=none`, `prompt=login`, `max_age`, and `auth_time`

### 6.1. `prompt=none`

When an RP sends an authorize request with `prompt=none`, the OP **must not display interactive UI**. If it cannot satisfy the request, the OP returns an appropriate error such as `login_required`, `interaction_required`, `consent_required`, or `account_selection_required`.

| OP Condition | Expectation |
| --- | --- |
| Session active and B needs no consent/step-up | Silent authorization may succeed. |
| IdP session expired/absent | `login_required`, no local B session issued. |
| Consent for client B not yet granted | `consent_required` or equivalent error. |
| B requires fresh MFA | `interaction_required` under prompt none; interactive flow needed. |
| Multiple IdP accounts, selection needed | `account_selection_required` when applicable. |
| Iframe silent auth blocked by third-party cookies | May fail even when top-level redirect SSO works normally. |

Do not use `prompt=none` to bypass passwords/MFA. It merely asks the IdP to leverage an **existing valid authentication session**, or **reject** when evidence is lacking.

### 6.2. `prompt=login` and `max_age`

`prompt=login` instructs the OP to reauthenticate. `max_age` specifies the maximum age of authentication; when requested, the client should validate the returned `auth_time` per OIDC. `max_age=0` generally requires fresh authentication per profile; it does not guarantee MFA if the IdP only prompts for a password.

**Test case:** A already has an OP session, and B requests `max_age=300` or a stronger ACR. B may prompt for step-up/password/MFA. That is **not necessarily an SSO FAIL**: tests must check B's policy and ensure standards are not lowered just to achieve “no second prompt.”

### 6.3. `iat` Is Not `auth_time`

A freshly issued ID Token for B can have a current `iat` while `auth_time` reflects the earlier authentication at A. Never use B's session creation time or the ID Token's issued time as proof that the user just completed MFA.

### 6.4. Third-Party Cookies and Iframes

Top-level redirects to the IdP differ from hidden-iframe silent authentication. Browsers may block third-party cookies inside iframes, causing `prompt=none` to fail while a top-level redirect to the IdP still achieves SSO. Tests must record the user-agent/browser settings rather than concluding the IdP policy is wrong just because an iframe fails.

## 7. Spring Boot: Two Applications from One Codebase

The project below demonstrates **two OIDC Relying Parties** runnable from the same source using different env vars. Each app has its own client ID and cookie. A test IdP and HTTPS proxy must still be stood up; **do not claim this is a runnable end-to-end demo without an OP**.

### 7.1. Structure

~~~text
multi-rp-oidc-test/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/multirp/
    │   ├── MultiRpApplication.java
    │   ├── WebSecurityConfig.java
    │   └── SessionInfoController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'multi-rp-oidc-test'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. `application.yml`

~~~yaml
server:
  port: ${APP_PORT:8081}
  servlet:
    session:
      timeout: 20m
      cookie:
        name: ${APP_COOKIE_NAME:RP_SESSION}
        http-only: true
        secure: true
        same-site: lax

app:
  name: ${APP_NAME:A}

spring:
  security:
    oauth2:
      client:
        registration:
          central:
            provider: central
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          central:
            issuer-uri: ${OIDC_ISSUER}
~~~

The IdP must register **two clients**:

~~~text
Application A:
  APP_NAME=A
  APP_PORT=8081
  APP_COOKIE_NAME=APP_A_SESSION
  OIDC_CLIENT_ID=client-A
  OIDC_CLIENT_SECRET=<secret-A-from-vault>
  OIDC_ISSUER=https://idp.example.test/realms/workforce

Application B:
  APP_NAME=B
  APP_PORT=8082
  APP_COOKIE_NAME=APP_B_SESSION
  OIDC_CLIENT_ID=client-B
  OIDC_CLIENT_SECRET=<secret-B-from-vault>
  OIDC_ISSUER=https://idp.example.test/realms/workforce
~~~

`client_id` must be **distinct** when the two apps are two independent RPs. In code, the internal registration ID `central` can match because each instance has its own config context. Redirect URIs for A and B are independent URLs:

~~~text
https://a.example.test/login/oauth2/code/central
https://b.example.test/login/oauth2/code/central
~~~

Backends A:8081 and B:8082 are exposed behind an HTTPS proxy on **two different hostnames**; use trusted forwarded headers/public URL configuration so `{baseUrl}` matches each client's callback. Never trust arbitrary `Host`/`X-Forwarded-Host` headers sent by internet clients. Do not use the same `localhost` hostname on two ports and assume session cookies are isolated by port. During direct HTTP development, `Secure` cookies may not be sent by browsers; E2E should use TLS rather than disabling protections in production.

### 7.3. `MultiRpApplication.java`

~~~java
package com.example.multirp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiRpApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiRpApplication.class, args);
    }
}
~~~

### 7.4. `WebSecurityConfig.java`

~~~java
package com.example.multirp;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                // A and B must grant APP_ADMIN independently per local policy.
                .requestMatchers("/admin/**").hasAuthority("APP_ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                // Local logout only; does not automatically log out IdP or B.
                .logoutUrl("/logout")
                .logoutSuccessUrl("/")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            .build();
    }
}
~~~

The application creates a local `SecurityContext` after the framework validates the OIDC callback. `/admin/**` is denied by default without local `APP_ADMIN`; roles are never inherited automatically from an SSO cookie. Production must load enabled status/tenant/roles from a trusted identity link `(iss,sub)` and local authorization store, checking MFA/ACR/freshness if an endpoint requires them.

### 7.5. `SessionInfoController.java`

~~~java
package com.example.multirp;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionInfoController {

    private final String appName;

    public SessionInfoController(
            @Value("${app.name}") String appName) {
        this.appName = appName;
    }

    @GetMapping("/")
    public Map<String, String> index() {
        return Map.of(
            "app", appName,
            "login", "/oauth2/authorization/central");
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "app", appName,
            "authenticated", authentication.isAuthenticated(),
            "authType",
                authentication.getClass().getSimpleName());
    }

    @GetMapping("/admin/check")
    public Map<String, String> admin() {
        return Map.of("app", appName, "status", "allowed");
    }
}
~~~

The controller intentionally **does not** return raw ID Tokens, access tokens, emails, `sub`, or session IDs over a public API. To confirm the same test subject at A and B, check IdP test audits and approved local identity mappings rather than `/me` alone.

### 7.6. Running

~~~bash
./gradlew bootRun
~~~

From the same JAR, two independent processes/containers can run with separate env vars, each having its own session store and cookie. A test IdP with configured issuer, client secrets, and registered callback URLs is required; otherwise startup or login may fail. Never place client credentials on command lines logged in CI shell history.

If both use Redis/Spring Session, configure **separate namespaces for A and B** so session keys/`SecurityContext` do not collide. Shared Redis does not mean shared RP sessions; it is an infrastructure dependency requiring isolation.

## 8. Mandatory HTTP/Protocol Tests Beyond Browser Behavior

### 8.1. Client and Callback Binding

- Authorization request from A includes `client_id=client-A`, redirect URI A, `state_A`, `nonce_A`, PKCE challenge A.
- B includes `client_id=client-B`, redirect URI B, `state_B`, `nonce_B`, PKCE challenge B.
- Code A is single-use at A; presenting code A at B must be rejected by the token endpoint.
- B must reject an ID Token with `aud=client-A`, even with a valid IdP signature.
- B must reject `state_A`/`nonce_A` or unregistered redirect URIs.
- Never allow the browser to select an unallowlisted issuer via `?issuer=https://evil.example`.
- Validate ID Token `iss`, `aud`, `exp`, signature/JWKS, and `nonce` via the framework; don't decode without verify.
- Verify session ID rotation after login, `Secure`/`HttpOnly`/`SameSite` cookies, and CSRF on business POSTs.

### 8.2. Authorization and Account Mapping

| User/Permission | App A | App B |
| --- | --- | --- |
| Alice has `APP_ORDER_APPROVE` at A, `APP_REPORT_READ` at B | Approves per order ownership | Views reports only per B permissions |
| Alice disabled at B | Does not automatically affect A access | Deny B |
| Alice belongs to tenant-A at A, tenant-B at B | Checks resource-A tenant | Checks resource-B tenant |
| Matching external email, different issuer/sub | No auto-link | No auto-link |
| `sub_A != sub_B` due to pairwise | Lookup approved A identity | Lookup approved B identity |
| B requires recent phishing-resistant MFA | A's policy does not substitute | B must check verified ACR/AMR/auth_time |

**A shared IdP session only assists authentication UX; it never transfers roles or tenant entitlements between two apps.** If B accepts a self-asserted group name from client A's token to grant admin rights, that is a trust boundary failure.

## 9. Local Logout Is Not Global Logout

### 9.1. Local Logout at A

~~~text
Before:
  IdP session ACTIVE
  A session ACTIVE
  B session ACTIVE

POST https://a.example.test/logout
  -> Spring LogoutFilter invalidates A HttpSession

After:
  IdP session ACTIVE
  A session ENDED
  B session ACTIVE
~~~

**This is normal behavior** with `.logout(...)` in the Spring Boot example. When the user returns to A immediately, A redirects the user to the IdP; since the IdP session remains active, it **may issue a new code without re-prompting for credentials**, and A creates a new local session. Do not conclude local logout failed simply because the user gets back into A quickly.

Proper tests must confirm **A's old session ID was invalidated**—not just that the UI showed a logout message—and that B's session remained unaffected.

### 9.2. IdP/OP Session Expiration

If the OP session expires while A and B still hold local HttpSessions:

~~~text
IdP session=EXPIRED
A local session=ACTIVE
B local session=ACTIVE
~~~

A/B may continue returning 200 based on local sessions until app timeout or SLO/revocation occurs. **Clearing the IdP cookie does not automatically clear A/B HttpSessions**. Therefore, distinguish *user experience logout* from *global session revocation* as two separate requirements.

### 9.3. RP-Initiated Logout in OIDC

OIDC RP-Initiated Logout 1.0 allows an RP to redirect the browser to the OP's `end_session_endpoint` with `id_token_hint` (recommended), a registered `post_logout_redirect_uri`, and `state` when used. Spring Security provides `OidcClientInitiatedLogoutSuccessHandler`:

~~~java
// Configuration FRAGMENT replacing the local logout handler in section 7.
// Requires matching ClientRegistrationRepository bean/imports for your version.
OidcClientInitiatedLogoutSuccessHandler opLogout =
    new OidcClientInitiatedLogoutSuccessHandler(
        clientRegistrationRepository
    );
opLogout.setPostLogoutRedirectUri("{baseUrl}");

http.logout(logout -> logout
    .logoutSuccessHandler(opLogout)
    .invalidateHttpSession(true)
    .clearAuthentication(true));
~~~

This is a **wiring fragment**; do not paste it verbatim into code that already called `http.build()`. Imports:
`org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler` and `org.springframework.security.oauth2.client.registration.ClientRegistrationRepository`.

Initiating OP logout requires provider Discovery/`end_session_endpoint` support and a registered post-logout URI. **There is no guarantee B logs out immediately** without front-/back-channel notification or B session expiry. Reaching a "logged out" page is not a distributed transaction confirming every RP.

## 10. Back-Channel Logout and Front-Channel Logout

### 10.1. OIDC Back-Channel Logout Token

The IdP can send a **signed Logout Token JWT** to each registered RP. The token must undergo trust validation per OIDC Back-Channel Logout 1.0, including:
- `iss`: approved issuer;
- `aud`: client ID of the receiving RP; A and B must each match their own audience;
- `iat`, `exp`, `jti`: timestamps/event ID for validation and replay controls;
- `events` containing key `http://schemas.openid.net/event/backchannel-logout`;
- `sid` or `sub` (or both) per supported profile;
- **must not** contain `nonce`;
- trusted signature/algorithm; reject unsigned/`alg=none`.

`sid` in a Logout Token is an OP-profile opaque session identifier, **not** a Servlet `JSESSIONID`. The RP must store a properly scoped `issuer+subject/sid→local session(s)` binding to invalidate sessions. If the Logout Token has only `sub`, the intent may be to revoke that subject's RP sessions per profile. Never match by email or terminate all users sharing a display name.

### 10.2. Idempotency, Replay, and Late Arrival

- The OP may send duplicates on retries or proxy retransmissions; receivers must be idempotent.
- Session already timed out/locally logged out before notification → no-op, never create a new session.
- Old session A ended and the user logged in again creating a new session A generation → old notification must not wrongly destroy the new generation when event binding is session-specific.
- If the notification lacks `sid` and is subject-wide, handle the exact **specified scope** without narrowing or widening the verified token's intent.
- `jti` replay cache and TTL require policy; never log raw tokens.
- An HTTP timeout/502 from B does not prove whether B invalidated or kept the session; check server-side state.
- Never trust a browser sending `?sid=...` or `?sub=...` to trigger a session revocation API.

### 10.3. Front-Channel Logout

An OP may use browser iframes/redirects to invoke RPs' logout endpoints. Delivery depends on browser/tabs/third-party cookies/SameSite/CSP and network conditions. Never use a finished iframe load as proof that local session B was invalidated; send a fresh request to B or inspect its session store/audit.

### 10.4. Outcome Matrix

| Event | IdP Session | Local A | Local B |
| --- | --- | --- | --- |
| Local logout A | Active | Ended | Active |
| Revisit A while OP active | Active | New session A created | Active |
| OP expires, no notifications | Ended | May remain | May remain |
| RP-Initiated OP logout from A, no propagation | Ended if OP handles | Ended | May remain |
| Signed back-channel notifications processed at A+B | Ended | Ended | Ended |
| B callback blocked by network | Ended | Per delivery at A | May remain |
| B session timed out before notification | Depends | Depends | Already ended |

**Proving federation-wide logout requires evidence from each RP**, not just the OP logout response.

## 11. Standalone Java 17: Simulating Two RPs and One OP

This example **runs with JDK 17 alone**. It illustrates the separation of three sessions and two browser contexts; it does not process signed OIDC tokens, Servlet/Redis, or guarantee delivery. Use it to verify expected logic before writing browser E2E tests.

### 11.1. `MultiAppSsoSessionDemo.java`

~~~java
import java.util.HashMap;
import java.util.Map;

public final class MultiAppSsoSessionDemo {

    static final class Idp {
        private final Map<String, String> sessions = new HashMap<>();
        private int interactiveLogins = 0;

        void login(String browser, String user) {
            sessions.put(browser, user);
            interactiveLogins++;
        }

        String sessionUser(String browser) {
            return sessions.get(browser);
        }

        boolean active(String browser) {
            return sessions.containsKey(browser);
        }

        void logout(String browser) {
            sessions.remove(browser);
        }

        int loginCount() {
            return interactiveLogins;
        }
    }

    static final class App {
        private final Map<String, String> localSessions =
            new HashMap<>();

        String visit(String browser, Idp idp) {
            if (localSessions.containsKey(browser)) {
                return "LOCAL_SESSION";
            }
            String subject = idp.sessionUser(browser);
            if (subject == null) {
                return "LOGIN_REQUIRED";
            }
            // Simulates a new authorization code flow for this RP.
            localSessions.put(browser, subject);
            return "SSO_NO_PROMPT";
        }

        void logout(String browser) {
            localSessions.remove(browser);
        }

        boolean active(String browser) {
            return localSessions.containsKey(browser);
        }
    }

    public static void main(String[] args) {
        Idp idp = new Idp();
        App a = new App();
        App b = new App();
        String work = "work-browser";
        String privateBrowser = "private-browser";

        System.out.println("initialA=" + a.visit(work, idp));
        idp.login(work, "alice");

        System.out.println("firstA=" + a.visit(work, idp));
        System.out.println("firstB=" + b.visit(work, idp));
        System.out.println("interactiveLogins=" + idp.loginCount());

        a.logout(work);
        System.out.println("afterLocalLogoutA=" + a.active(work));
        System.out.println("afterLocalLogoutB=" + b.active(work));
        System.out.println("idpStillActive=" + idp.active(work));

        System.out.println("reenterA=" + a.visit(work, idp));
        System.out.println("loginCountAfterReenter=" +
            idp.loginCount());

        // IdP ends session, but RP sessions can stay active
        // without notification.
        idp.logout(work);
        System.out.println("opEndedButAActive=" + a.active(work));
        System.out.println("opEndedButBActive=" + b.active(work));

        a.logout(work);
        b.logout(work);
        System.out.println("visitBWithoutOp=" + b.visit(work, idp));

        idp.login(privateBrowser, "bob");
        System.out.println("privateB=" +
            b.visit(privateBrowser, idp));
        System.out.println("workBAfterLogout=" + b.active(work));

        // New IdP session for Alice and fresh local RP sessions.
        idp.login(work, "alice");
        a.visit(work, idp);
        b.visit(work, idp);
        System.out.println("beforeFederatedA=" + a.active(work));
        System.out.println("beforeFederatedB=" + b.active(work));

        // Only models successful notifications to A and B.
        idp.logout(work);
        a.logout(work);
        b.logout(work);
        System.out.println("afterFederatedA=" + a.active(work));
        System.out.println("afterFederatedB=" + b.active(work));
        System.out.println("bobStillActive=" +
            b.active(privateBrowser));
        System.out.println("totalInteractiveLogins=" +
            idp.loginCount());
    }
}
~~~

### 11.2. Run Command and Stdout

~~~bash
javac --release 17 MultiAppSsoSessionDemo.java
java MultiAppSsoSessionDemo
~~~

**Exact stdout:**

~~~text
initialA=LOGIN_REQUIRED
firstA=SSO_NO_PROMPT
firstB=SSO_NO_PROMPT
interactiveLogins=1
afterLocalLogoutA=false
afterLocalLogoutB=true
idpStillActive=true
reenterA=SSO_NO_PROMPT
loginCountAfterReenter=1
opEndedButAActive=true
opEndedButBActive=true
visitBWithoutOp=LOGIN_REQUIRED
privateB=SSO_NO_PROMPT
workBAfterLogout=false
beforeFederatedA=true
beforeFederatedB=true
afterFederatedA=false
afterFederatedB=false
bobStillActive=true
totalInteractiveLogins=3
~~~

**Interpretation:**
- One IdP login for Alice suffices for A and B to receive two local sessions when policy permits.
- Local logout of A does not change B or the IdP session.
- Revisiting A while the OP session is active yields a **new SSO session at A** without increasing credential ceremonies.
- OP logout alone **does not** remove local A/B sessions.
- Once both OP and local B sessions end, B must log in again.
- `private-browser` for Bob has its own OP session; it does not inherit Alice, and logging Alice out does not remove Bob's session.
- Only the final branch simulates both notifications arriving and being processed so A/B both end.
- The program does not validate JWTs, cookies, SAMLResponses, CAS tickets, networking, or session stores. Never use a `Map`/boolean browser ID as a production mechanism.

## 12. MockMvc, Spring Security Test, and Scope Limits

`spring-security-test` provides `SecurityMockMvcRequestPostProcessors.oidcLogin()`:

~~~java
// Test one already-authenticated request; NOT cross-app SSO:
mvc.perform(get("/me").with(oidcLogin()))
    .andExpect(status().isOk());
~~~

This tests a fake `OidcUser` injected into `SecurityContext`; it does not:
- create a browser IdP cookie;
- perform A→IdP / B→IdP authorization redirects;
- exchange real authorization codes/tokens;
- validate `state`, `nonce`, PKCE, and ID Token signatures in the mocked flow;
- create two local sessions across two hostnames;
- prove B reuses the OP session without a password prompt;
- exercise logout notifications between two apps.

Use MockMvc to test:
- authorization manager/method security of **one app**;
- local principal mapping, enabled status, roles, and tenant;
- CSRF on POSTs;
- controller JSON/HTTP status and error handling.

Use **browser E2E + a test IdP with real browser sessions** to prove cross-app SSO. To test OIDC callback/Logout Token signatures, use protocol integration with a real provider/crypto validation, not just `oidcLogin()`.

## 13. SAML2: Two Service Providers Sharing an Identity Provider

When A/B use SAML2:
1. SP A sends `AuthnRequest A` to the IdP; the IdP creates an SSO session and returns a **SAML Response scoped specifically to ACS-A**.
2. SP B sends `AuthnRequest B`; the IdP can reuse the valid IdP session and return a **separate SAML Response to ACS-B** without prompting for a password.
3. A/B verify signatures/assertions, Issuer, AudienceRestriction, Recipient/Destination, InResponseTo/Conditions, and their own RP registrations.
4. A/B create separate `HttpSession` instances and enforce NameID/immutable identity mapping and local roles.

Protocol-specific tests:
- **Audience A must not be accepted at B**, even though the assertion is signed by the same IdP.
- SP A/B `entityId`, ACS, trust certificates, and signing policies must be isolated properly.
- SAML `persistent NameID` may be issued pairwise per SP; do not require raw NameID A=B.
- SAML SLO uses `SessionIndex`/LogoutRequest/LogoutResponse, signed/verified per contract—not Servlet session IDs.
- Local logout A does not log out B; federated SLO requires enabling `saml2Logout`, configuring the IdP, and testing callback delivery/ack/timeouts.
- `MockMvc.with(authentication(new Saml2Authentication(...)))` only tests post-authentication authorization; it **does not** prove IdP cookie sharing or SAML signature verification.

For SAML cross-site POSTs to ACS, verify SameSite cookie/session correlation; never disable app-wide validation/CSRF just to make 403s disappear in tests.

## 14. CAS: Shared TGT/TGC, Two Separate Service Tickets

When A/B are CAS services:
- The browser holds a CAS **TGC cookie**, and the CAS server holds the **TGT** — this is the shared SSO session.
- On first access to A, CAS issues **ST-A** for service URL A; A validates ST-A once and creates HttpSession A.
- On first access to B, CAS can issue a new **ST-B** using the active TGT without re-prompting for a password; B validates ST-B for service URL B and creates HttpSession B.
- ST-A cannot be used at B; service-ticket binding and single-use validation must be enforced.
- CAS Single Sign Out uses ticket/session mapping at each service, with callbacks per profile whose delivery may be best-effort; test duplicates, timeouts, missing callbacks, and multi-node routing.
- Local logout at A does not automatically destroy the CAS TGT unless the application explicitly invokes CAS logout by design.

**Do not mix terminology:** OIDC ID Token/Logout Token, SAML Response/SessionIndex, and CAS ST/TGT/TGC are different artifacts. An identity broker may support multiple protocols, yet never assume all protocols share an OP cookie/session when multiple intermediary IdPs/realms exist.

## 15. Cookies, SameSite, HTTPS, and Session Fixation

### 15.1. Two Apps on Localhost: Two Ports Do Not Guarantee Cookie Isolation

Cookies are generally scoped by domain/path/name, not TCP port. If A on `localhost:8081` and B on `localhost:8082` both set `JSESSIONID` with path "/", cookies can overwrite each other. Tests easily suffer 302 login loops or false passes.

**Test recommendation:** use different hostnames for A/B; host-only local cookies, distinct names, HTTPS, and explicit proxy routes. Never set `Domain=.example.test` on all app cookies just to “get SSO.”

### 15.2. SameSite and Redirect Methods

- OIDC Authorization Code callbacks are typically top-level GETs, so `SameSite=Lax` often works across browsers/configs.
- SAML2 ACS is typically a cross-site POST; if session/state cookies are blocked by SameSite, correlation can fail.
- `SameSite=None` in modern browsers generally requires `Secure`, and does not replace CSRF protection.
- Hidden-iframe silent auth and OIDC front-channel logout can be blocked by third-party cookie restrictions even while top-level redirects succeed.
- Use pinned browser versions/contexts and test each profile rather than blindly enabling `SameSite=None` system-wide without evaluating CSRF/third-party cookies.
- Trust Forwarded Host/Proto only from proxies that strip spoofed inbound headers. Wrong public baseUrls break redirect URIs and ID Token audience flows.

### 15.3. SecurityContext/Session Store

- A/B can use Spring Session on a shared Redis cluster, but **namespaces and session store policies must stay separate** to prevent SecurityContext/role leakage.
- Multi-node A1/A2: the OIDC state/nonce authorization request repository must locate the right session when the IdP callback lands on a different node.
- Rotate the session ID upon successful authentication to defend against session fixation.
- Local session idle timeout and OP session max lifetime can differ; do not require them to expire simultaneously without an SLO contract.
- Browser logout UI is not proof the server invalidated the session; send a new request with the old cookie and verify 401/redirect.
- All business POSTs require CSRF/session/authorization per policy; OIDC callbacks are handled by the framework per protocol, not opened indiscriminately.

## 16. Testing Failures, Expiry, and Elevated Privileges

### 16.1. Local Session A Expired, OP Still Active

~~~text
OP=ACTIVE, A=EXPIRED, B=ACTIVE
GET A /me -> A starts new authorize flow -> OP reuses SSO
A creates a NEW local session
B unchanged
~~~

Tests must distinguish the new session generation from the old one and re-verify account enabled status/roles. Never reuse a stale `SecurityContext`.

### 16.2. OP Session Expired, Local A/B Still Active

~~~text
OP=EXPIRED, A=ACTIVE, B=ACTIVE
GET A /me -> may return 200 using A local session
GET B /me -> may return 200 using B local session
~~~

If business rules require synchronized revocation, enable back-channel/SLO or separate session revalidation/revocation. Do not assume OP session expiry automatically revokes local sessions.

### 16.3. IdP Outage

- Existing local sessions may continue working per app policy even when the IdP is offline.
- B without a local session cannot complete a new OIDC login.
- Never “fall back” to a default user when the IdP is unreachable.
- Test DNS/TLS/JWKS cache, metadata endpoint, key rotation, token validation failures, and timeouts.
- If using another IdP as fallback, enforce separate identity linking policies; never auto-merge by email.
- Never run chaos tests against a production IdP.

### 16.4. Step-Up at B

A user may enter A with BASIC assurance while B requires recent MFA/phishing-resistant authentication:
- B sends `acr_values`, `max_age`, or a policy-specific challenge to the IdP per contract.
- The IdP may demand re-interaction despite an active SSO session.
- After the callback, B verifies validated `acr`/`amr`/`auth_time` alongside local identity and roles.
- Never weaken B's policy just to achieve “sign in once” in tests.
- A fresh ID Token `iat` does not prove the user just completed MFA.

## 17. Cross-Application Test Matrix

| ID | Scenario | Outcome |
| --- | --- | --- |
| T01 | Fresh browser GET A. | No local auth yet; redirects to approved IdP. |
| T02 | First IdP login with client-A. | One interactive auth; session A created validly. |
| T03 | Same browser visits B for the first time. | B runs its own authorize flow but reuses OP session if policy allows. |
| T04 | B already has a session from an earlier test. | Test must reset to avoid false passes. |
| T05 | A/B have distinct client IDs. | Each ID Token matches its own audience. |
| T06 | A/B callback redirect URIs swapped. | Reject. |
| T07 | ID Token `aud=A` sent to B. | Reject, no session B created. |
| T08 | Authorization code A attempted at B. | Reject client/redirect/code binding. |
| T09 | State A sent to callback B. | Reject. |
| T10 | Nonce A reused for B. | Reject. |
| T11 | Two apps share issuer with different client secrets. | No shared tokens/secrets. |
| T12 | A/B share cookie name on different localhost ports. | Test detects collision risk; never assume origin isolation. |
| T13 | Host-only APP_A_SESSION and APP_B_SESSION. | Cookies properly isolated per origin. |
| T14 | Second browser context without OP session. | Does not inherit Alice; fresh login per policy. |
| T15 | Two tabs in same browser profile. | Can reuse OP cookie/session. |
| T16 | Browser blocks third-party iframe cookies. | Silent iframe may fail; test top-level redirect separately. |
| T17 | Prompt none, OP session active, consent sufficient. | Silent authorization may succeed. |
| T18 | Prompt none, OP session absent. | `login_required` or equivalent, no local login. |
| T19 | Prompt none, B needs step-up. | `interaction_required`, no MFA bypass. |
| T20 | B requires missing consent. | Consent prompt/error per policy, no auto-grant. |
| T21 | B requires phishing-resistant method. | Exact method/ACR/auth_time, no policy downgrade. |
| T22 | `max_age=0` with older OP session. | Reauth, verify auth_time per spec. |
| T23 | Fresh ID Token `iat`, stale `auth_time`. | Do not treat as fresh MFA. |
| T24 | Pairwise `sub` A != `sub` B for same user. | Proper identity mapping, no false failure. |
| T25 | Same email, different issuers/subjects. | Do not auto-link accounts. |
| T26 | User disabled at B but active at A. | B denies per local state. |
| T27 | A has APP_ORDER_APPROVE, B only APP_REPORT_READ. | No cross-app privilege escalation. |
| T28 | Tenant A tries accessing tenant B resource. | Deny even when SSO succeeded. |
| T29 | Reload active local A/B sessions. | No unexpected IdP redirect. |
| T30 | Local logout A. | A ended, B and OP still active. |
| T31 | Reenter A right after local logout while OP active. | New local session A via IdP SSO; old session not reused. |
| T32 | OP logout/expiry without notification. | Local A/B sessions may persist; no false global success. |
| T33 | RP-Initiated Logout A to `end_session_endpoint`. | OP logout per contract, B checked separately. |
| T34 | B lacks back-channel logout support. | B may stay active; document limitation accurately. |
| T35 | Signed/valid Back-Channel Logout Token `aud=B`. | B revokes exact local session(s). |
| T36 | Back-channel token with invalid signature/issuer/audience. | Reject. |
| T37 | Logout Token missing `events` or containing `nonce`. | Reject per spec. |
| T38 | Duplicate `jti`, expired/late event. | Idempotent; does not kill a newer session generation. |
| T39 | OP notification dropped at proxy. | B may remain active; alert/reconcile. |
| T40 | Bob in private-browser, Alice logs out in work browser. | Bob's sessions remain untouched. |
| T41 | Local session A times out while OP active. | A re-authorizes and creates a new session. |
| T42 | OP session times out while A/B local active. | Not auto-synced without SLO. |
| T43 | IdP offline while A/B local sessions active. | Follows app policy; no fake new auth issued. |
| T44 | IdP offline when B has no session. | B login fails closed. |
| T45 | Key rotation/JWKS changes. | Validly signed tokens pass; untrusted signers rejected. |
| T46 | Overlapping Spring Session Redis namespaces. | Test catches cross-app leak. |
| T47 | Callback arrives at a different replica node. | State/nonce/session repository stays consistent. |
| T48 | SAML Assertion issued for SP A sent to SP B. | Reject audience/recipient/InResponseTo. |
| T49 | Different pairwise SAML2 NameIDs. | Do not assume different people. |
| T50 | SAML local logout A. | B session remains unless SLO is configured. |
| T51 | CAS ST-A validated at service B. | Reject service binding/replay. |
| T52 | CAS TGT logout, one SLO callback lost. | That service's local session may remain. |
| T53 | MockMvc `oidcLogin()` passes at A/B. | Unit/authorization pass only; does not prove SSO. |
| T54 | Browser password manager autofills credentials on B. | IdP audit distinguishes real reauth from session reuse. |
| T55 | OP session holds multiple accounts, selection needed. | Account selection handled by IdP; no wrong user auto-login. |
| T56 | User switches identity in same browser with stale A session. | Do not mix local principals/permissions. |
| T57 | B local OAuth refresh token persists after OP logout. | Test revocation/lifetime separately. |
| T58 | CI logs ID Token/cookies/session IDs. | QA fail; redact and rotate as needed. |
| T59 | SLO completed but browser tab shows stale DOM. | Fresh server request confirms authorization. |
| T60 | Upgrade IdP/browser/Spring Security version. | Re-run SSO/CSRF/cookie/logout regressions. |

### 17.1. Acceptance Criteria

A **multi-app SSO** scenario passes when:
1. Both RPs use distinct approved client registrations and redirect URIs.
2. In a fresh browser context, A completes a valid interactive login.
3. B executes its own authorize flow and reuses the OP session without a second credential prompt **when policy allows**.
4. IdP instrumentation verifies the count of interactive auth ceremonies rather than inferring from HTTP 200/screenshots.
5. Local A/B sessions stay separate, cookies do not collide, and audience/state/nonce match.
6. Local identities/tenants/roles never leak across apps; pairwise IDs are handled per contract.
7. Local logout is distinguished from OP/global logout; if testing SLO, evidence confirms each RP session was genuinely revoked.
8. Coverage includes expired sessions, IdP outages, blocked cookies, and negative tokens.

## 18. Troubleshooting

### 18.1. B Prompts for Login Again Even Though A Logged In

Check:
- Same browser context, or did the test runner spawn a new profile?
- Does B redirect to the **same trusted IdP issuer** and same cookie session domain/profile?
- Is the IdP session active, and is the cookie unblocked/unexpired?
- Does B have a different `prompt=login`/`max_age`/step-up/consent requirement from A?
- Browser third-party cookie policies or silent-auth iframes?
- Clock sync, proxy `Host`/`X-Forwarded-Proto`, issuer metadata, TLS/callback config?
- Did App B already hold a stale local session causing redirect loops?
- How many interactive events appear in IdP authentication logs?

Never “fix” this with shared `JSESSIONID`, disabling signature/MFA checks, or using A's token at B.

### 18.2. B Returns HTTP 200 Immediately Without Visiting the IdP

Possible causes:
- Session B already existed from a previous test;
- Route B is `permitAll`;
- Cookies A/B were shared via an overly broad Domain/path/namespace;
- The test used MockMvc `oidcLogin()`;
- The reverse proxy routed both hostnames to the same app.

Reset browser/IdP sessions and assert client-B's authorize flow and local session B creation.

### 18.3. After Logging Out of A, Re-entering A Succeeds Immediately

A's local session ended while the OP session stayed alive, so SSO re-login creates a new session A. This may be expected behavior. If global logout is required, configure OP logout + approved back-/front-channel propagation and verify each RP.

### 18.4. After IdP Logout, B Is Still Accessible

Check:
- Is local session B still active?
- Did the OP send a signed notification to B?
- Does B have the right receiver and `sid/sub` mapping to its session store?
- Was B's callback blocked by firewall/TLS/CSRF/routing/authorization?
- Are there late/duplicate events or multi-node store issues?
- Does B use refresh tokens/API credentials with a separate lifecycle?

Never report global logout success while B retains a session or lacks proof of revocation.

### 18.5. Browser-Only Tests Are Flaky

Pin browser versions; use explicit waits rather than fixed sleeps; test SameSite/third-party cookies/SSO iframes separately; reset IdP sessions and disable password-manager/extension popups; never use production credentials.

### 18.6. Apps A/B Mix Up Users/Roles

This is a security vulnerability: audit cookie `Domain`, session namespaces, wrong audiences, email-based account linking, pairwise subject assumptions, tenant scoping, trusted proxy identity headers, and session fixation. Revoke affected sessions/tokens and investigate.

## 19. Monitoring and Test Evidence

Suggested metrics (not built into Spring automatically):

~~~text
sso_authorize_started_total{app,client}
sso_callback_success_total{app,client}
sso_callback_error_total{app,reason_class}
sso_interactive_auth_total{idp,scenario}
sso_existing_op_session_reuse_total{app}
sso_local_session_created_total{app}
sso_local_logout_total{app}
sso_op_logout_total{app,result}
sso_backchannel_logout_received_total{app,result}
sso_backchannel_session_revoked_total{app}
sso_stepup_total{app,result}
sso_authorization_denied_total{app,reason_class}
~~~

Never use emails, `sub`, `sid`, tokens, session IDs, or raw IPs as metric labels. Tracing should use random/opaque test run IDs, with retention limits and read access controls on records.

### 19.1. Sample SSO Result

~~~text
scenario=T03
browser_context=opaque-ci-context
idp=approved-test-idp
appA_client=client-A
appB_client=client-B
idp_authorization_requests=2
idp_interactive_login_events=1
appA_session=ACTIVE_CONFIRMED
appB_session=ACTIVE_CONFIRMED
audience_validation_A=PASS
audience_validation_B=PASS
app_permissions=ISOLATED
result=PASS
~~~

### 19.2. Sample System-Wide Logout Result

~~~text
scenario=T35
op_session=ENDED_CONFIRMED
appA_logout_notification=VERIFIED
appA_session=REVOKED_CONFIRMED
appB_logout_notification=VERIFIED
appB_session=REVOKED_CONFIRMED
result=PASS
~~~

If B's callback is lost, accurately record `appB_session=UNKNOWN_OR_ACTIVE` and mark global revocation **FAIL**; never infer success from the OP logout page.

## 20. Self-Assessment

**1. Does sharing an IdP make A and B share an `HttpSession`?**  
No. Each RP creates its own local session after that client's authorization flow.

**2. Why does B still redirect to the IdP without prompting for a password?**  
B needs an authorization code specific to `client-B`; the IdP uses its existing browser session to issue the code.

**3. Can a single SSO flow involve two OAuth2 authorization requests?**  
Yes, one per app. The number of credential ceremonies can still be one.

**4. Is using two Selenium browser profiles correct for testing SSO?**  
Not for the shared-cookie happy path: you need **one** browser context. Use a separate profile to test isolation.

**5. May B accept an ID Token with `aud=A`?**  
No, audience/client binding must be enforced.

**6. If `sub_A != sub_B`, are they definitely two different people?**  
No. Pairwise subjects can differ per client/sector; use trusted mappings.

**7. Does `prompt=none` bypass authentication?**  
No. It tells the IdP to rely solely on existing evidence, and return an error if insufficient.

**8. Is `auth_time` when local session B was created?**  
No. It is when the IdP authenticated the end-user.

**9. Does local logout at A log out B?**  
Not by default. Session B and the IdP session may remain active.

**10. Does OP session expiration automatically destroy A/B?**  
Not without SLO/revocation propagation.

**11. Is a signed OIDC Logout Token the same as an ID Token?**  
No. A Logout Token carries `events` for back-channel logout and `sid`/`sub` per spec, without `nonce`.

**12. Does MockMvc `oidcLogin()` on A and B prove SSO?**  
No. It only mocks a principal for each app's individual requests.

**13. Do two apps on different localhost ports have strict cookie isolation?**  
No. Cookies are not port-scoped; use distinct hostnames in E2E tests.

**14. If B requires stronger MFA than A, can visiting B prompt for MFA?**  
Yes. That can be expected security policy, not an SSO bug.

**15. Do SAML/CAS share the same OIDC ID Token/Logout Token formats?**  
No. Each protocol/binding must be tested separately even within the same federation category.

## 21. Go-Live Checklist

- [ ] Sandbox IdP, real A/B apps, HTTPS, and distinct hostnames are in place.
- [ ] Both RPs have distinct client IDs, secrets, and callback/logout URLs matching trust configuration.
- [ ] Fresh browser context is reset with no leftover sessions from earlier tests.
- [ ] Interactive login on A through the IdP is tracked via audit/instrumentation.
- [ ] B executes its own authorize flow and reuses the OP session in the **same browser context** when policy permits.
- [ ] Confirmed only one interactive ceremony despite two authorization/token flows.
- [ ] OIDC state/nonce/PKCE/code binding/issuer/audience/expiry/signature are verified.
- [ ] OP session and local A/B sessions are clearly distinguished in logs and the test oracle.
- [ ] Cookies A/B are host-only, Secure, HttpOnly, and not shared via a common Domain.
- [ ] Localhost ports are not treated as cookie isolation; SameSite/third-party cookies tested in real browsers.
- [ ] Account linking uses trusted IDs, not email auto-matching; pairwise `sub` handled per contract.
- [ ] Local authorities, enabled status, tenant, and resource ownership are independent per app.
- [ ] Negative tests cover wrong audience, wrong issuer, swapped callbacks, and stale state/nonce.
- [ ] Tests cover `prompt=none` active/absent/consent/step-up, `max_age`/`auth_time` per policy.
- [ ] Local logout A verified separately and never labeled global logout.
- [ ] If RP-Initiated OP logout is enabled, `end_session_endpoint`/return URI are registered and tested.
- [ ] If OIDC Back-Channel Logout is used, signed JWT, events, sid/sub/jti, audience, and idempotent revocation are tested.
- [ ] If SAML2/CAS is used, assertions/tickets, SLO callbacks, signatures, service binding, and late/missing events are tested.
- [ ] Tested local/OP session expiry, IdP outage, key rotation, multi-node session stores, and restarts.
- [ ] MockMvc is used for local controllers/authorization, browser E2E for shared IdP sessions.
- [ ] No tokens/cookies/PII stored in CI logs/screenshots; secrets managed securely.
- [ ] Scenarios T01–T60 or equivalent coverage executed, with regressions re-run after version upgrades.

## Key Takeaways

> **One IdP session lets users sign into multiple applications without re-entering passwords, yet each application must keep its own authorization flow, session, token audience, and permissions.** Proper SSO testing goes through A and B in the **same browser context**, verifying **IdP session reuse and the number of interactive authentication ceremonies**, not merely two HTTP 200 responses or two MockMvc mock users. **Local logout is not global logout**; claiming federation-wide logout requires proving each RP's local session was revoked through a real SLO mechanism.

### Official References

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authorization Code flow, prompt none/login, max_age, auth_time, ID Token iss/aud/nonce.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): end_session_endpoint, id_token_hint, and post_logout_redirect_uri.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): signed Logout Token, events, sid/sub/jti, delivery, and revocation.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout via user agent/browser.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, authorization endpoint, and code callback.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): OidcClientInitiatedLogoutSuccessHandler.
- [Spring Security — MockMvc OAuth2 Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): oidcLogin() test fixture and limitations.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext, session fixation, lifecycle.
- [Spring Security — SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/IdP, AuthnRequest, ACS.
- [Spring Security — SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated SLO, LogoutRequest/LogoutResponse.
- [Apereo CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): TGT/TGC, ST per service, and SLO.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie/session security.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): MFA, reauthentication, and recovery controls.
