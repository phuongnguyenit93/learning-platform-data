# Integrating OAuth2 Login and Calling an External API on Behalf of the User

## 1. Goal of This Integrated Practice

A Spring MVC web application lets users **sign in via an Identity Provider (IdP)** and then access an **API on another system on that exact user's behalf**. For example, user Alice opens an account management page, signs in at the IdP, and asks the backend application to fetch her profile from the Partner API. The application must never fetch Bob's data, must never expose the access token to the browser, and must never confuse an ID Token with an API access token.

This practice combines **Spring Security OAuth2 Login** and **Spring Security OAuth2 Client** on the **Servlet stack**, using **Java 17+, Spring Boot 3.x, Spring Security 6.x**. We will build a simple **backend-for-frontend (BFF)**:

- The user accesses the backend via a browser; Spring Security redirects to the IdP via the **Authorization Code flow**.
- The backend handles the OAuth2/OIDC callback, completes authentication, and maintains the login session with an HttpSession/cookie.
- Spring Security stores an **OAuth2AuthorizedClient** bound to the **client registration** and current principal; this object holds the access token issued for the user.
- On GET **/api/partner/profile**, the backend resolves the authorized client for that exact user and sends **Authorization: Bearer access_token** to **https://api.example.test/v1/profile**.
- The Partner API is a separate **resource server** responsible for verifying the token, issuer/audience, expiry, and scopes; the backend never sends an ID Token or login password to the Partner API.
- The browser receives only the selected profile data—**never** raw access tokens, refresh tokens, or client secrets.

**Example limitations:** the domains **idp.example.test** and **api.example.test** are placeholders with no live services. The code is a coherent Spring Boot sample requiring a real OpenID Connect-capable IdP, Partner API, client registration, and scopes to run end-to-end. The mocked-HTTP outbound test can run independently of an IdP when placed into a matching Boot project.

## 2. Distinguishing Login from API Calling Rights

### 2.1. OAuth2 Login Does Not Automatically Grant Access to Every API

**oauth2Login()** lets an application authenticate users through an Authorization Server/IdP and create an Authentication for the web session. **oauth2Client()** supports client authorization and manages **OAuth2AuthorizedClient** when the application needs to call external systems. The two features are related, yet **not synonymous**.

| Component | Role in Practice | What to Avoid |
| --- | --- | --- |
| **Browser** | Holds session cookie to access the BFF | Storing refresh tokens or client secrets in JavaScript |
| **Spring MVC BFF** | OAuth2 Client and RP; handles login/callback, stores authorized client, calls Partner API | Forwarding access tokens arbitrarily to client-supplied URLs |
| **Authorization Server / IdP** | Authenticates Alice, issues authorization code, exchanges code for tokens | Issuing tokens with wrong audience or over-broad scopes |
| **Partner API / Resource Server** | Receives access token, enforces the API's own policy | Trusting the BFF session cookie or ID Token in place of an access token |
| **OAuth2AuthorizedClient** | Binds ClientRegistration, principalName, access token, and optional refresh token | Using Alice's token while handling Bob's request |

In OIDC, tokens typically include:

- **ID Token:** describes the authentication event/identity for the client (RP), targeted at the client's audience. **Never** automatically use it as a Bearer credential for the Partner API.
- **Access Token:** credential for calling resource APIs, carrying scopes and audience meant for the resource server.
- **Refresh Token:** sensitive credential sent to the AS token endpoint to obtain a new access token when issued. **Never send refresh tokens to the Partner API.**
- **Authorization Code:** short-lived code from the callback exchanged on the backend for tokens; not an API credential.
- **Session cookie:** how the browser proves its logged-in session to the BFF; not equivalent to an external access token.

**OAuth2 is a delegation protocol; OIDC adds login identity.** When scopes include **openid**, the IdP must support OIDC and have matching issuer/UserInfo/JWKS configuration. Never treat a non-OIDC OAuth2 access token as OIDC identity proof.

### 2.2. Authorization Code + Delegated API Call Diagram

~~~text
Browser (Alice)              Spring MVC BFF          IdP / AS             Partner API
      |                            |                     |                      |
      | GET /api/partner/profile   |                     |                      |
      |--------------------------->|                     |                      |
      | 302 to login page          |                     |                      |
      |<---------------------------|                     |                      |
      | GET /oauth2/authorization/partner                 |                      |
      |--------------------------->|                     |                      |
      | 302 /authorize?... state, nonce, redirect_uri     |                      |
      |<---------------------------|                     |                      |
      |----------------------------------------------->   |                      |
      |       sign in / consent to scopes                 |                      |
      |<-----------------------------------------------   |                      |
      | GET /login/oauth2/code/partner?code=...&state=...  |                      |
      |--------------------------->|                     |                      |
      |                            | POST token endpoint |                      |
      |                            |-------------------->|                      |
      |                            | access/ID/refresh   |                      |
      |                            |<--------------------|                      |
      |                            | verify login & create session              |
      | 302 / or original URL      |                     |                      |
      |<---------------------------|                     |                      |
      | GET /api/partner/profile   |                     |                      |
      |--------------------------->| resolve OAuth2AuthorizedClient             |
      |                            | GET /v1/profile                            |
      |                            | Authorization: Bearer <access-token>       |
      |                            |------------------------------------------->|
      |                            |       Profile JSON, if token is valid       |
      |                            |<-------------------------------------------|
      | 200 Selected profile JSON  |                     |                      |
      |<---------------------------|                     |                      |
~~~

In a real flow, Spring Security may show a default login page before the user clicks **/oauth2/authorization/partner**. A 302 does not guarantee it always jumps directly to the IdP; inspect the response and exception entry-point policy. **state** protects against CSRF in the authorization response; **nonce** is used in OIDC to bind the ID Token to the login request; **PKCE** adds protection for the Authorization Code per policy and client type. Never strip default checks just to make the callback work.

## 3. Architecture and Prerequisites Before Coding

Three systems or components are involved:

1. **BFF / OAuth2 Client**: Spring Boot 3.x running at **https://app.example.test** in staging/production; locally it can run at **http://localhost:8080** as appropriate for development.
2. **IdP / Authorization Server**: provides OIDC discovery (**issuer-uri**) and authorization, token, JWKS, and UserInfo endpoints as needed. Register a **confidential web client** with **client-id**, **client-secret** or an IdP-supported client authentication method, **Authorization Code flow**, and exact registered redirect URIs.
3. **Partner API**: a resource server capable of verifying the IdP's access tokens, requiring **scope api.profile.read** and the API's audience, and returning profile JSON authorized for that specific user.

**Default Spring Security OAuth2 Login callback path** for registrationId **partner**:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Examples:

~~~text
Local:       http://localhost:8080/login/oauth2/code/partner
Production:  https://app.example.test/login/oauth2/code/partner
~~~

These URIs must be registered at the IdP with matching scheme, hostname, port, and path. If the backend sits behind a TLS-terminating reverse proxy, configure trusted forwarded headers properly at ingress/app, never trusting spoofed **X-Forwarded-Host / X-Forwarded-Proto** from Internet clients. **Redirect URI mismatch** often occurs when the BFF believes its baseUrl is internal HTTP instead of public HTTPS.

**Scopes:** the example requests **openid** and **profile** for OIDC login, plus **api.profile.read** for calling the Partner API. The last scope name is an illustrative contract; adjust it to match the real Partner API. **Having a scope in an access token does not replace audience validation.** The Partner API must verify the token was issued specifically for it.

## 4. Creating the Spring Boot 3.x / Java 17 Project

A Gradle project with wrapper and structure:

~~~text
oauth-login-bff/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/
    ├── main/
    │   ├── java/com/example/oauthbff/
    │   │   ├── OAuthBffApplication.java
    │   │   ├── PartnerProfile.java
    │   │   ├── PartnerApiClient.java
    │   │   └── PartnerController.java
    │   └── resources/application.yml
    └── test/java/com/example/oauthbff/
        └── PartnerApiClientTest.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'oauth-login-bff'
~~~

**build.gradle** (versions pinned for illustration, not a recommendation to freeze this patch level permanently):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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

The project relies on Spring Framework 6.1+/Boot 3.2+ for **RestClient**; the illustrative Boot 3.5 setup satisfies that requirement. For other versions, verify BOM and APIs rather than mixing Spring Security 5.x into Boot 3.x.

### 4.1. application.yml: Registration and IdP Provider

File **src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-idp
            client-id: "${PARTNER_CLIENT_ID}"
            client-secret: "${PARTNER_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.profile.read
        provider:
          partner-idp:
            issuer-uri: "https://idp.example.test/realms/demo"

partner:
  api:
    base-url: "https://api.example.test"
~~~

Explanation:

- **registration.partner** defines a single **client registration**. Matching the name **partner** in **@RegisteredOAuth2AuthorizedClient("partner")** and the link **/oauth2/authorization/partner** is intentional.
- **provider.partner-idp.issuer-uri** lets Spring perform OIDC discovery. **The example issuer URL must be replaced with a real URL** providing valid metadata, HTTPS, and a working JWKS endpoint. Discovery may occur at startup: if the IdP is fake/unreachable, the app can **fail to start**, not just fail when a user logs in.
- **client-id / client-secret** come from environment variables; never commit real values. An IdP may require a different client authentication method; **client_secret_basic** fits a registered confidential web client.
- **scope api.profile.read** is the requested permission. The AS may grant fewer scopes; the backend should verify the token actually has the needed scope before calling, and the Partner API must still enforce its own policy.
- **redirect-uri** uses template variables supported by Spring Security OAuth2 Client. Ensure the public callback matches the IdP registration and trusted proxy config.
- **partner.api.base-url** must be a server-configured, controlled endpoint. **Never** accept an API URL from a user query parameter and forward the access token there, as that causes SSRF/token exfiltration.

### 4.2. Application and SecurityFilterChain

File **src/main/java/com/example/oauthbff/OAuthBffApplication.java**:

~~~java
package com.example.oauthbff;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class OAuthBffApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuthBffApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                // Authenticate users via OAuth2/OIDC Login.
                .oauth2Login(Customizer.withDefaults())
                // Enable the app to manage OAuth2 Authorized Clients.
                .oauth2Client(Customizer.withDefaults())
                // Spring Security CSRF remains enabled by default.
                .build();
    }
}
~~~

**Do not use SessionCreationPolicy.STATELESS on a BFF with oauth2Login** unless you have designed alternative persistence for OAuth2 Authorization Requests, state, SecurityContext, and authorized clients. Browser login and callback paths normally need session state. Do not copy a stateless Bearer JWT Resource Server configuration into this web BFF.

**Do not disable CSRF to "fix login callbacks".** Typical Authorization Code callbacks use GET with code/state, while the BFF uses cookies/sessions to authenticate the browser. Keep CSRF protection active for state-changing POST/PUT/DELETE requests. If the app defines multiple SecurityFilterChains, verify login/callback/API routes enter the right chain.

### 4.3. DTO for API Data, Never Receiving Tokens from the Browser

File **src/main/java/com/example/oauthbff/PartnerProfile.java**:

~~~java
package com.example.oauthbff;

// Assumed Partner API JSON:
// {"id":"42","displayName":"Alice"}
public record PartnerProfile(String id, String displayName) {
}
~~~

**PartnerProfile** contains only fields the application is permitted to expose. In real systems, avoid returning the Partner API's raw JSON directly if it may contain sensitive fields or differing object-level permissions; map it to a BFF-controlled DTO.

### 4.4. Backend Calling the Partner API with the Delegated Access Token

File **src/main/java/com/example/oauthbff/PartnerApiClient.java**:

~~~java
package com.example.oauthbff;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PartnerApiClient {

    private final RestClient restClient;

    public PartnerApiClient(
            RestClient.Builder builder,
            @Value("${partner.api.base-url}") String baseUrl) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }

    public PartnerProfile fetchProfile(OAuth2AccessToken accessToken) {
        // BFF does not call API if token lacks required scope.
        if (!accessToken.getScopes().contains("api.profile.read")) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Delegated scope missing");
        }

        try {
            PartnerProfile profile = restClient.get()
                    .uri("/v1/profile")
                    .headers(h -> h.setBearerAuth(
                            accessToken.getTokenValue()))
                    .retrieve()
                    .body(PartnerProfile.class);

            if (profile == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Partner API returned no profile");
            }
            return profile;
        } catch (RestClientResponseException exception) {
            // Never return raw tokens, URLs with secrets, or Partner API error bodies.
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, "Partner API request failed");
        }
    }
}
~~~

Key points:

1. **RestClient.Builder** is auto-configured by Spring Boot 3.2+ with spring-web; use dependency injection rather than building a client from a user-supplied URL.
2. **setBearerAuth(...)** places the token in the **Authorization** header toward the **fixed Partner API**. Never put the token in query strings, browser responses, or logs.
3. Scope is checked **at the BFF before the outbound call** to give clear user feedback, yet this is **not** the sole defense. The Partner API must verify the token cryptographically or via introspection and enforce **issuer, audience, expiry, and permissions**.
4. **RestClientResponseException** represents an HTTP error from the Partner API. The example maps it to a generic **502 Bad Gateway** without leaking upstream responses. Real systems need deliberate error mapping, safe telemetry, and reauthorization handling if the access token is revoked/401.
5. If a 200 response has an empty body, the app returns 502 instead of forwarding null as success. Never use unverified data to make ownership/authorization decisions.
6. In real deployments, configure **timeouts, connection pooling, retries only for safe operations, circuit breakers, and observability**. Never blindly retry sensitive POSTs (which can duplicate side effects), and never retry endlessly when the Partner API returns 401.

**Note:** the access token is passed in as **OAuth2AccessToken**, not an ID Token. Never fabricate a token from a username string or Authentication.getName(); only the AS issues tokens valid for the resource server.

### 4.5. Controller Resolving OAuth2AuthorizedClient for the Right Principal

File **src/main/java/com/example/oauthbff/PartnerController.java**:

~~~java
package com.example.oauthbff;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PartnerController {

    private final PartnerApiClient partnerApiClient;

    public PartnerController(PartnerApiClient partnerApiClient) {
        this.partnerApiClient = partnerApiClient;
    }

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
                "message", "Open /oauth2/authorization/partner to sign in");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication current) {
        return Map.of("user", current.getName());
    }

    @GetMapping("/api/partner/profile")
    public PartnerProfile partnerProfile(
            @RegisteredOAuth2AuthorizedClient("partner")
            OAuth2AuthorizedClient authorizedClient) {

        // Resolved for registration partner and the request's principal.
        // Token can be refreshed per authorized-client manager policy.
        return partnerApiClient.fetchProfile(
                authorizedClient.getAccessToken());
    }
}
~~~

**@RegisteredOAuth2AuthorizedClient("partner")** uses Spring Security OAuth2 Client's argument resolver to look up the authorized client bound to the principal and registration. It avoids manually fishing raw access tokens from session attributes or accepting tokens from the browser. The authorized-client manager can handle **refresh tokens** when configured, provided a valid refresh token exists and policy allows it; **never assume every AS issues refresh tokens** or that every 401 will auto-refresh cleanly.

**If the authorized client is missing or no longer valid:** depending on resolver/manager setup, the request may trigger a new authorization flow, an authentication error, or custom business handling. Never accept an arbitrary browser-chosen clientId to pull tokens from another registration. Keep registration IDs fixed per approved Partner API.

**Separating Identity vs. Authorization:** Alice logging in does not automatically entitle her to call **/v1/profile** or read someone else's record. If a BFF exposes an endpoint taking a profileId, enforce object-level checks and ensure the Partner API also enforces subject/tenant checks. This example exposes only a **current profile** endpoint without an arbitrary userId parameter to reduce IDOR risk.

## 5. Running the Real Flow Step-by-Step

### 5.1. Registering the Client at the IdP

In the IdP admin console, create a **confidential OIDC client**:

- **Client ID/secret** for the web BFF; enable the Authorization Code flow and matching client authentication.
- Redirect URI: **http://localhost:8080/login/oauth2/code/partner** for local development (or the corresponding public HTTPS URI in staging/prod).
- Allowed scopes **openid profile api.profile.read**, and configure the AS to issue an **access token accepted by the Partner API**.
- If the Partner API requires an **audience/resource indicator**, configure the AS/client per the provider's protocol; a valid scope with the wrong audience will still be rejected by the Partner API.
- Use an exact redirect URI allowlist—never broad wildcards or open redirects. Enable **PKCE** when required by AS/client policy and to strengthen authorization code protection.
- If refresh tokens are allowed, check the IdP's issuance rules; some IdPs require **offline_access** or specific consent policies. Do not request refresh tokens if the app does not need long-lived delegated access.

Set **PARTNER_CLIENT_ID** and **PARTNER_CLIENT_SECRET** in a secure runtime environment before starting. Never put secrets in source files, test snapshots, or exposed command lines.

### 5.2. Starting the App

~~~bash
./gradlew bootRun
~~~

In PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

While **issuer-uri** remains idp.example.test, startup/discovery cannot reach a real IdP; replace both the issuer and API base URL before end-to-end testing. If a real issuer does not support OIDC discovery, configure the explicit provider endpoints per the provider's documentation.

### 5.3. Walking Through in a Browser

1. Open **http://localhost:8080/** and receive the welcome JSON.
2. Navigate to **http://localhost:8080/oauth2/authorization/partner** to start the authorization code login.
3. The browser redirects to the IdP; sign in with test user Alice and approve the requested scopes.
4. The IdP redirects back to **/login/oauth2/code/partner?code=...&state=...**. Spring Security validates state, exchanges the code at the token endpoint, and establishes the login session.
5. Visit **http://localhost:8080/api/me** to verify the logged-in principal (the returned name comes from IdP/Spring configuration, not necessarily the literal string "alice").
6. Visit **http://localhost:8080/api/partner/profile**. The BFF resolves the authorized client and calls the Partner API using Alice's access token.
7. Observe the mapped profile JSON response. No access/refresh tokens appear in the URL, HTML, localStorage, or BFF JSON response.

**Do not run curl -L in ways that print authorization codes, Set-Cookie headers, or secrets into CI logs.** The Authorization Code flow relies on browser/session/state; manual curl commands can inspect redirects/headers with dummy data in isolated environments, but are not a complete login verification strategy.

## 6. Testing the API Client Without a Live IdP

A common mistake in integration exercises is testing only with **@WithMockUser** and claiming the access token was sent to the Partner API. That test is insufficient: @WithMockUser only sets a fake Authentication; **it does not create an OAuth2AuthorizedClient or perform any outbound HTTP request**.

We can deterministically test the outbound call using **@RestClientTest**, **MockRestServiceServer**, and a fake **OAuth2AccessToken**. This verifies the exact Authorization header and scope guard; it **does not** simulate the full OAuth2 Login callback.

File **src/test/java/com/example/oauthbff/PartnerApiClientTest.java**:

~~~java
package com.example.oauthbff;

import java.time.Instant;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.server.ResponseStatusException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match
        .MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match
        .MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match
        .MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response
        .MockRestResponseCreators.withSuccess;

@RestClientTest(PartnerApiClient.class)
@TestPropertySource(properties =
        "partner.api.base-url=https://api.example.test")
class PartnerApiClientTest {

    @Autowired
    PartnerApiClient partnerApiClient;

    @Autowired
    MockRestServiceServer server;

    private static OAuth2AccessToken accessToken(Set<String> scopes) {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-access-token-alice",
                now.minusSeconds(30),
                now.plusSeconds(300),
                scopes);
    }

    @Test
    void forwardsOnlyAccessTokenAsBearerHeader() {
        server.expect(requestTo(
                        "https://api.example.test/v1/profile"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer test-access-token-alice"))
                .andRespond(withSuccess(
                        "{\"id\":\"42\",\"displayName\":\"Alice\"}",
                        MediaType.APPLICATION_JSON));

        PartnerProfile result = partnerApiClient.fetchProfile(
                accessToken(Set.of("api.profile.read")));

        assertThat(result.id()).isEqualTo("42");
        assertThat(result.displayName()).isEqualTo("Alice");
        server.verify();
    }

    @Test
    void missingDelegatedScopeDoesNotCallPartnerApi() {
        assertThatThrownBy(() -> partnerApiClient.fetchProfile(
                accessToken(Set.of("openid", "profile"))))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("403");

        // No request expectation registered: if the service attempts
        // an outbound HTTP call, the mock server will flag the unexpected request.
        server.verify();
    }
}
~~~

Run just the outbound test suite in a project with the Gradle wrapper:

~~~bash
./gradlew test --tests com.example.oauthbff.PartnerApiClientTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.oauthbff.PartnerApiClientTest
~~~

**Both tests are expected to pass** when assembled into a Boot 3.5 project matching the sample. The first verifies the request targets the **exact fixed hostname/path**, uses **GET**, carries **Authorization: Bearer test-access-token-alice**, and maps JSON. The second verifies missing scopes are blocked before any outbound request. These are **code expectations**, not results from compiling/running in a live environment.

### 6.1. Integration Test Matrix to Add

| Scenario | Test Level | Expected Outcome |
| --- | --- | --- |
| No session → GET /api/partner/profile | MockMvc/web integration | Does not enter controller; redirects to login/IdP per entry point |
| Alice logs in via OIDC | Test IdP integration | State and callback verified; session bound to Alice |
| Client holds valid access token with right scope | Client unit/mock HTTP | Sends Bearer token to Partner API; receives profile |
| Token missing api.profile.read | Client unit | No outbound request sent; 403 at BFF per demo |
| Bob logs in after Alice | Full session integration | BFF resolves only Bob's authorized client, never Alice's token |
| Access token expired, refresh token present | OAuth2 client integration | Authorized-client manager refreshes if configured and AS accepts |
| Access token expired, cannot refresh | OAuth2 client integration | Requests reauthorization or fails safely without infinite loop |
| Partner API returns 401/token revoked | End-to-end | BFF never escalates privileges; clear retry/relogin strategy |
| Partner API returns 403/insufficient_scope | End-to-end | Never falls back to a service/admin token to bypass permissions |
| Partner API returns 5xx/timeout | Client/integration | Returns controlled error without leaking raw tokens or sensitive bodies |
| API receives wrong-audience token | Resource server integration | 401/403 per resource server policy; never trusts scopes alone |
| BFF logout | Web integration | Browser session invalidated; authorized-client storage handled per policy |
| Multiple BFF replicas | Distributed integration | Session/auth request/authorized-client stores stay consistent without cross-user leaks |
| XSS/CSRF against state-changing endpoints | Security integration | CSRF and cookie policies still protect the BFF |
| Proxy sends fake X-Forwarded-Host | Edge integration | Callback is not redirected to an attacker-controlled hostname |

**MockMvc supports** request post-processors like **oauth2Login()** and **oauth2Client()** in spring-security-test to set up authentication and authorized clients in the test context. However, those post-processors do not verify ID Token signatures or execute a real authorization code flow. Always pair them with test-IdP integration tests covering state/nonce, callback, issuer, audience, and persistence.

### 6.2. Do Not Confuse OAuth2 Login Tests with Delegated Token Tests

A test using **.with(oauth2Login())** can prove an endpoint reads the logged-in principal, yet **does not guarantee @RegisteredOAuth2AuthorizedClient has a real token** or that outbound calls carry the right Bearer header. Verify separately:

- Bean/scope of the authorized-client repository/manager.
- That the token for registration **partner** belongs to the current principal.
- That outbound requests send the **access token** rather than the ID Token.
- Expired-token errors, failed refreshes, and reauthorization.
- Multi-user tests: authorized clients are never shared across principals.

## 7. Refresh Tokens, Authorized Client Storage, and Sessions

### 7.1. What Happens When the Access Token Expires?

**OAuth2AuthorizedClient** contains ClientRegistration, principalName, the access token, and a refresh token (if issued). Spring Security provides **OAuth2AuthorizedClientManager**, **OAuth2AuthorizedClientService**, and **OAuth2AuthorizedClientRepository** to manage authorized clients.

A properly configured **authorized-client manager** can execute the **refresh_token grant** when the access token is near or past expiration and the AS issued a valid refresh token. Never assume automatic refresh behaves identically in every setup when:

- You manually read raw tokens from HttpSession and send them yourself.
- You configure a custom authorized-client manager/provider lacking refreshToken support.
- The AS did not issue a refresh token or the refresh token was revoked.
- The user session expired or the authorized-client repository lost its entry.
- The resource server returned 401 due to revocation or wrong audience rather than expiration.

**Never retry infinitely with the same token.** On a 401 from the Partner API, classify the cause: expiration, revoked token, wrong audience, missing entitlement, or AS outage. If refreshing/retrying, do so in a bounded, controlled way, never log token values, and never mask a 403 permission denial using a service's client_credentials token.

### 7.2. Sessions and Token Storage

In the Servlet BFF demo:

- The browser holds a session cookie; Spring Security persists the request's authentication context.
- Authorized clients are stored/loaded via the configured repository/service. A simple setup may use **InMemoryOAuth2AuthorizedClientService**; multi-replica production needs durable, properly shared storage.
- **Never store access tokens or refresh tokens in JavaScript localStorage just to call the Partner API** when using a BFF architecture. The backend holds tokens and returns only allowed data.
- Protect the authorized-client store because refresh tokens can mint fresh access tokens; apply encryption at rest, least-privilege access, rotation/retention, and auditing.
- On user logout, define how the session is cleared, how the local authorized client is removed, and whether **AS revocation** is needed. **Logging out of the BFF does not automatically revoke issued access tokens.**
- Across multiple instances, verify shared session stores, OAuth2 Authorization Request/state/nonce persistence, and authorized-client storage. Sticky sessions alone do not replace fault-tolerant design.
- When immediate revocation is required, the resource server/AS needs short TTLs, introspection, or a denylist—never rely solely on browser logout timing.

### 7.3. Tokens Must Only Be Sent to Trusted Destinations

RestClient in the example takes baseUrl from server configuration. In production:

- Use HTTPS and verify TLS certificates; never disable hostname verification.
- Configure outbound hostname allowlists, DNS/egress controls, redirect policies, and timeouts to mitigate SSRF/token leakage.
- Never accept a URL parameter from the browser as the destination for **Authorization: Bearer**.
- Be especially careful with HTTP 3xx: HTTP clients vary in redirect-following behavior; **never let the Authorization header be forwarded to an untrusted hostname**.
- Never put Bearer tokens in query strings, exception messages, metrics labels, access logs, or distributed tracing URLs.
- Avoid turning the BFF into an open generic proxy forwarding arbitrary methods/paths with user credentials without checking CSRF, method, scope, and object-level authorization.

## 8. Cookies, CSRF, SameSite, Browsers, and Reverse Proxies

**OAuth2 Login for web browsers typically uses session cookies**, so it must be engineered alongside browser security controls:

- **HttpOnly:** JavaScript cannot read the session cookie.
- **Secure:** transmit cookies over HTTPS only in production.
- **SameSite:** pick a value compatible with login redirects/callbacks and frontend topology rather than hardcoding without testing; consider OIDC `form_post` if used.
- **CSRF:** keep protection on state-changing POST/PUT/PATCH/DELETE endpoints; OAuth2 state does not replace CSRF tokens across BFF endpoints.
- **Session fixation:** let Spring Security rotate session identifiers on login per policy; never disable it just to make callbacks easier.
- **Redirect validation:** allow only registered IdP redirect URIs; never let arbitrary external returnUrls create open redirects.
- **Forwarded headers:** when ingress terminates TLS, accept only normalized headers from trusted proxies; never accept raw scheme/host headers directly from attackers.
- **CORS:** if an SPA on another origin calls the BFF with cookies, configure explicit CORS credentials, CSRF, and cookie policies. CORS **does not** prove authorization.
- **Content Security Policy:** mitigate XSS so attackers cannot hijack an active browser session to call the BFF.

**Browser sessions must never expose an endpoint returning raw tokens just because the user is logged in.** Even without tokens in localStorage, XSS can drive a logged-in session to invoke BFF endpoints; harden the UI, keep CSRF enabled, and constrain BFF scopes and allowed actions.

## 9. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Browser caught in infinite redirect to IdP | Session/state not saved, cookie not sent, wrong callback path | Check cookies, public URL, trusted headers, session store |
| **redirect_uri mismatch** | Internal baseUrl differs from public HTTPS, wrong port/path prefix, unregistered URI | Compare URI sent to IdP against actual redirect URI allowlist |
| Startup fails with issuer-uri set | OIDC discovery URL wrong/unreachable/TLS error | Use real issuer and verify metadata/JWKS in a trusted environment |
| Login succeeds yet API returns 401 | Access token expired, wrong audience, wrong issuer, or revoked | Check token contract, resource server validation, and authorized-client refresh |
| API returns 403 despite successful login | Token lacks scope or user lacks resource rights | Check consent/scopes/entitlements; never send ID token as access token |
| BFF returns 403 before outbound call | Access token lacks api.profile.read per demo policy | Inspect actual token scopes and client registration/consent |
| BFF returns 502 | Partner API 4xx/5xx or empty body per demo mapping | Safely check upstream status, circuit breaker, and JSON contract |
| Bob sees Alice's profile | Token/repository keyed by clientId instead of principal, or IDOR | Bind authorized client to principal; test multi-user and object ownership |
| Callback returns 404 | Wrong filter chain path, context path, or proxy rewrite | Check /login/oauth2/code/partner and Spring Security filter mappings |
| Leaked access token still works after logout | JWT exp still valid and AS/resource server do not revoke | Use shorter TTLs, revocation, or introspection as needed |
| BFF works on one node but fails multi-node | Local in-memory session/state/authorized-client store | Use shared persistence and verify consistency |
| UserInfo/login works, Partner API rejects token | Token meant for another client/UserInfo, missing API audience/scope | Configure explicit audience/resource and permissions for Partner API |
| 401 from API triggers retry loop | Client fails to distinguish expired/revoked/missing scope | Bound retries and apply proper refresh/reauth policy |
| Login behind proxy hits internal HTTP cookie/redirect errors | Misconfigured TLS termination/forwarded headers | Configure trusted proxy scheme/host and Secure cookies |

**Safe diagnostic logging:** log request ID, registrationId, endpoint name, upstream HTTP status, and error category; **never log access tokens, refresh tokens, authorization codes, client secrets, session cookies, or OIDC state/nonce**. When enabling Spring Security DEBUG/TRACE logging, do so only in controlled environments and avoid logging request headers containing secrets.

## 10. Practice Acceptance Checklist

### OAuth2 Login

- IdP supports OIDC discovery and compatible client registration with redirect URI matching **{baseUrl}/login/oauth2/code/{registrationId}**.
- Authorization Code flow validates state; nonce/ID Token validation matches OIDC; PKCE configured per AS/client policy.
- Session cookies, CSRF, session fixation, SameSite, and forwarded headers verified in both local and public HTTPS environments.
- **oauth2Login()** authenticates the user; login authentication is never conflated with resource API authorization.

### OAuth2 Authorized Client

- Access token is bound to the exact **registrationId** and **principalName**.
- Client secrets, refresh tokens, and authorized-client storage are never exposed to the browser.
- Refresh behavior is tested with expired tokens; when refresh fails, the system denies safely or triggers reauthorization.
- Logout/session expiry and token revocation are explicitly designed rather than assuming logout destroys every JWT.

### Partner API

- BFF calls only a **fixed, HTTPS, allowlisted base URL** and sends the access token in the Bearer header.
- Token carries **scope api.profile.read** plus the issuer/audience required by the Partner API; the Partner API enforces user/tenant/resource ownership itself.
- On Partner API errors, the BFF never reflects raw tokens or sensitive upstream error bodies.
- Never silently fall back to service/admin credentials when a user's access token is denied.
- Timeouts, safe retry/backoff, and outbound rate limits are configured appropriately.

### Testing

- Client unit tests verify the **exact Bearer header**, endpoint, and scope guard using **MockRestServiceServer**.
- Callback/login and session tests use Spring Test / a test OIDC IdP, **never** treating @WithMockUser as proof of real token handling.
- Two distinct users are tested to confirm separate authorized clients and resource permissions.
- Tests cover expired/refreshed/revoked access tokens, Partner 401/403/5xx, outages/timeouts, and session/logout.
- Production proxy HTTPS/public redirect URIs, path prefixes, CSRF, cookies, and CORS (if cross-origin frontend) are tested.
- Verified that access/refresh/ID tokens never appear in HTML, JSON, URLs, logs, or metrics.

**Conclusion:** **OAuth2 Login** authenticates the user to establish a web session; **OAuth2 Client** holds AS-granted access for the **right principal**; the **Partner API** decides whether the access token is valid and authorized for the resource. A secure BFF calls external APIs using an **access token with the right scope and audience**, keeps secrets on the backend, handles expiry/refresh/revocation, and thoroughly tests login, outbound Bearer headers, session isolation, and negative cases.
