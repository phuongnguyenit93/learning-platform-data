# ClientRegistration, Redirect URI, and Client Identity Details in Spring Security

> **Context:** A Java 17+ application using Spring Boot 3.x and Spring Security 6.x wants to log users in via an OAuth 2.0 / OpenID Connect (OIDC) provider, such as an internal identity system. This lesson focuses on **client application identity details** (`client_id`, `client_secret`, `registrationId`), `ClientRegistration` configuration, **redirect URI**, and related integration errors. OAuth 2.0 specifies the authorization workflow; when standard user identity authentication is needed, prefer **OIDC** on top of OAuth 2.0.

## 1. What Can You Do After This Lesson?

- Identify the **client application**, **provider / authorization server**, **user (resource owner)**, and **callback-receiving application** in the authorization code flow.
- Clearly explain the difference between Spring's `registrationId`, the IdP-issued `client_id`, `client_secret`, `issuer`, `clientName`, and user identity (`iss` + `sub`).
- Know which fields belong to `ClientRegistration`, which fields Boot maps from `application.yml`, and where they are stored via `ClientRegistrationRepository`.
- Correctly pair the **login initiation URI**, **authorization-code callback redirect URI**, and **post-login destination URI**; understand why these three URIs are not synonymous.
- Configure a real OAuth 2.0 / OIDC client with secrets kept outside source code; troubleshoot callback errors, HTTPS proxy setup, scopes, and client authentication methods.
- Establish security principles for redirect URIs, `state`, PKCE, OIDC `nonce`, issuer/audience, and secret rotation; build a pre-production checklist.

## 2. Role Map: Who Establishes Whose Identity?

In a Spring MVC application, roles are clearly separated:

| Role / Data | Who Owns It? | What Is It Used For? |
| --- | --- | --- |
| **Client application** | Spring Boot application | Initiates login requests, receives callbacks, and exchanges authorization codes at the token endpoint |
| **Authorization Server / OpenID Provider (OP)** | Identity Provider (IdP) | Authenticates users, handles consent/policies, issues authorization codes and tokens |
| **`client_id`** | Issued by the IdP to the **client application** | Identifies the application at authorization/token endpoints; typically appears in authorization URLs, **not a password** |
| **`client_secret`** or client private key | Managed securely server-side by the application | Authenticates a **confidential client** at the token endpoint using the registered method |
| **`registrationId`** | Spring Security inside the application | **Internal** key name to select a `ClientRegistration`, e.g., `company`; not necessarily equal to `client_id` |
| **`issuer`** | Identity Provider | Trusted identity and metadata root of the IdP; in OIDC, must match the validated issuer in the ID Token |
| **`sub`** of the ID Token | Assigned by the IdP to the user account | Subject identifier; typically paired with `iss` to uniquely identify the account in the app |
| **`redirect_uri`** | Declared by client, allowed by IdP | Endpoint in the app to which the browser is redirected **back** carrying `code` and `state` |
| **`scope`** | Requested by client, controlled by IdP | Range of requested data/permissions; `openid` signals OIDC for the login workflow |

**Very common confusion:** `client_id` proves *which application the client claims to be*, not *who the logged-in user is*. This ID is generally public data. `client_secret` is meaningful only when running server-side where secrets can be kept; it must never be embedded in an SPA, browser JavaScript, mobile app, or desktop distribution. Meanwhile, `registrationId` is a configuration key Spring uses for routing, not an OAuth credential.

### Authorization Code + OIDC Flow (Conceptual)

~~~text
Browser                 Spring Security client                 IdP / OIDC Provider
   |  GET /private                |                                     |
   |----------------------------->|                                     |
   |  302 to /oauth2/authorization/company                              |
   |<-----------------------------|                                     |
   |  GET /oauth2/authorization/company                                 |
   |----------------------------->|                                     |
   |                              | create request + state (+PKCE/nonce)|
   |<------------- 302 to authorization_uri ?client_id&redirect_uri&state...
   |--------------------------------------------------------------------->|
   |                              |                                     | login + consent
   |<----------- 302 to https://app.example.test/login/oauth2/code/company?code=...&state=...
   |----------------------------->|                                     |
   |                              | verify state and stored request     |
   |                              | POST code to token endpoint         |
   |                              |------------------------------------>|
   |                              |<------------- token response -------|
   |                              | validate ID Token if using OIDC     |
   |<-------------- establish authentication and redirect after login   |
~~~

The diagram above omits cookies, sessions, error handling, and TLS details. The authorization code passes through the **browser** to the callback; exchanging the code for tokens happens between the client backend and the token endpoint over a server channel. Do not hand-roll token exchange flows when Spring Security already provides and properly configures them.

## 3. What Does `ClientRegistration` Contain?

`org.springframework.security.oauth2.client.registration.ClientRegistration` is the model describing a registered OAuth 2.0 or OIDC client. Key properties:

| Java Property | Spring Boot Property | Meaning |
| --- | --- | --- |
| `registrationId` | `registration.<id>` (map key) | Local identifier, unique in the repository |
| `clientId` | `registration.<id>.client-id` | The `client_id` value issued to the app by the IdP |
| `clientSecret` | `registration.<id>.client-secret` | Credential of a confidential client, kept on the backend |
| `clientAuthenticationMethod` | `registration.<id>.client-authentication-method` | How the client authenticates at the token endpoint, e.g., `client_secret_basic` |
| `authorizationGrantType` | `registration.<id>.authorization-grant-type` | For browser-based login, `authorization_code` |
| `redirectUri` | `registration.<id>.redirect-uri` | Callback URI or template, e.g., `{baseUrl}/login/oauth2/code/{registrationId}` |
| `scopes` | `registration.<id>.scope` | Requested scopes, such as `openid`, `profile`, `email` |
| `clientName` | `registration.<id>.client-name` | Display label on the login page, not a security identity |
| `providerDetails.authorizationUri` | `provider.<id>.authorization-uri` | Endpoint the browser is navigated to for login/consent |
| `providerDetails.tokenUri` | `provider.<id>.token-uri` | Endpoint where the backend sends the authorization code to exchange for tokens |
| `providerDetails.issuerUri` | `provider.<id>.issuer-uri` | Trusted issuer, typically used for OIDC discovery |
| `providerDetails.jwkSetUri` | `provider.<id>.jwk-set-uri` | Public key endpoint used to verify token signatures |
| `providerDetails.userInfoEndpoint` | `provider.<id>.user-info-uri` and related fields | Reads user info if available per provider mechanism |

`ClientRegistrationRepository` provides lookup by `registrationId`, e.g., `findByRegistrationId("company")`. A common implementation is `InMemoryClientRegistrationRepository`. Spring Boot can auto-build the repository from properties. In WebFlux, the corresponding interface is `ReactiveClientRegistrationRepository` (e.g., `InMemoryReactiveClientRegistrationRepository`).

Further distinguish these two classes:

- `ClientRegistration` = **the application's registration configuration with an IdP**.
- `OAuth2AuthorizedClient` = details of an authorized client tied to a principal and its corresponding tokens, managed by `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` in the Servlet model.

Changing `client_id` or registering another provider updates **client configuration**, without automatically migrating or refreshing previously issued tokens.

## 4. Configuring an OIDC Client with Spring Boot

Suppose the application is served at `https://app.example.test`, using an IdP whose issuer is `https://id.example.test/realms/staff`. The IdP admin team has created a **Web application confidential client** for the backend and provisioned `client_id`/`client_secret` through a secret management system.

In a Spring Boot project using Gradle Groovy, add the core dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Declare `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: staff-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: "Company SSO"
        provider:
          staff-idp:
            issuer-uri: "https://id.example.test/realms/staff"
~~~

**The values in this example are illustrative domains and configuration variables.** Before running, you must be provisioned real `client_id`/`client_secret` by the IdP in an approved environment, ensure DNS/TLS reachability, and register the matching public callback. Never commit real secrets to YAML files, test fixtures, or logs. In environments with a secret manager/Kubernetes Secret/Vault, inject secrets at runtime per governance policy.

Important lines:

1. `registration.company` sets `registrationId = "company"`; the default login initiation path is `/oauth2/authorization/company`.
2. `provider: staff-idp` points to the provider configuration; **`company` and `staff-idp` are two separate configuration names**. Multiple registrations can share a single provider.
3. `client-id` is the application ID issued by the IdP; it must belong to the right client, tenant/realm, and environment. Do not substitute a user id, group id, email, or `registrationId`.
4. `client-secret` is used at the token endpoint with `client_secret_basic` if issued and supported by the IdP. If the IdP requires `private_key_jwt` or another method, configure it compatibly; do not change it arbitrarily.
5. `authorization-grant-type: authorization_code` is for interactive browser login flows; `client_credentials` issues tokens for servers/applications with no user login or browser callback.
6. `scope: openid` enables **OIDC** handling in Spring Security when supported by the provider; `profile`/`email` merely request claims and do not guarantee the IdP issues them or turn them into authorities.
7. `provider.staff-idp.issuer-uri` allows the framework to discover OIDC/OAuth metadata when the provider publishes valid discovery. Startup may need to reach that metadata; a wrong issuer, TLS error, or IdP without discovery metadata can prevent the application from starting. If the provider does not support discovery, configure the required endpoints explicitly per the provider's documentation.

### Java Servlet Configuration to Enable OAuth2 Login

File `src/main/java/example/security/SecurityApplication.java` in a Spring Boot project with the dependencies above:

~~~java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String publicPage() {
            return "Welcome";
        }

        @GetMapping("/private")
        String privatePage() {
            return "Signed in";
        }
    }
}
~~~

This example is **a minimal complete Spring Boot application in terms of Java code**; to actually log in, you need a real provider, credentials, HTTPS/trust, registered callbacks, and the project's Spring Boot/JDK build plugins. Do not compile this file standalone with `javac` because it depends on Spring libraries; in a Boot project run `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`). Accessing `/private` while unauthenticated triggers the login mechanism; the request completes only when the IdP and callback are operational.

If your application is **WebFlux**, you must use `SecurityWebFilterChain`/`ServerHttpSecurity` and the corresponding reactive repository; the `HttpSecurity` example here is specifically for Servlet.

## 5. Redirect URI: Three Paths That Must Not Be Confused

Suppose `registrationId = company`:

| URL Type | Example | Handler |
| --- | --- | --- |
| **OAuth Login Initiation** | `https://app.example.test/oauth2/authorization/company` | Client-side Spring Security receives the request and builds the authorization request |
| **IdP Authorization Endpoint** | `https://id.example.test/realms/staff/protocol/openid-connect/auth` (IdP-dependent) | IdP displays login/consent |
| **OAuth Redirect URI / Callback** | `https://app.example.test/login/oauth2/code/company` | Client-side Spring Security receives `code` and `state` |
| **Post-Login Destination** | `https://app.example.test/private` or saved request | Application navigates the user after authentication completes |

`redirect_uri` is where the **Authorization Server sends the authorization response back via the browser**; it is neither the URL taking the user to the IdP login page nor the post-login dashboard page. Systems also have a separate **logout callback/post-logout redirect URI**, which must not be mixed with the OAuth 2.0 authorization callback.

Spring Security Servlet uses these defaults:

~~~text
Initiate login : /oauth2/authorization/{registrationId}
Callback       : /login/oauth2/code/{registrationId}
redirect-uri   : {baseUrl}/login/oauth2/code/{registrationId}
~~~

With public base URL `https://app.example.test` and `registrationId = company`, the URI the IdP must **explicitly allow** is:

~~~text
https://app.example.test/login/oauth2/code/company
~~~

If you launch the app locally at `http://localhost:8080` and the IdP permits test callbacks, the corresponding URI is `http://localhost:8080/login/oauth2/code/company`. Do not add localhost callbacks to a production client unless genuinely needed and permitted by policy.

**Matching rules:** The authorization server should perform exact redirect URI matching against the registered allowlist. Pay close attention to scheme (`http` vs. `https`), domain, port, context path, letter casing, trailing slash, and `registrationId`. Avoid wildcards, user-supplied domains, callbacks redirecting to uncontrolled hosts, and paths with open-redirect behavior. Standard loopback redirect exceptions for certain native apps are not a reason to open wildcards for a web backend.

### Changing the Callback Requires Changing All Three Places

For example, if required to receive callbacks at `/auth/callback/company`, you must synchronize:

1. `ClientRegistration.redirectUri`: `{baseUrl}/auth/callback/{registrationId}`.
2. Spring Security's authorization response filter: `/auth/callback/*`.
3. The exact redirect URI list in the IdP: `https://app.example.test/auth/callback/company`.

Illustrative Servlet configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .redirectionEndpoint(endpoint -> endpoint
                            .baseUri("/auth/callback/*")))
            .build();
}
~~~

This code **replaces** the `securityFilterChain` method from the earlier example; do not declare two beans with the same function side by side. Also update the YAML line to:

~~~yaml
redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
~~~

If you only edit YAML and forget to update `redirectionEndpoint`, the IdP may return a code successfully, yet Spring will not intercept callbacks at the new path. If you only edit the Spring endpoint and forget the IdP configuration, the IdP may immediately reject the authorization request with `redirect_uri_mismatch` or an equivalent error.

## 6. `{baseUrl}`, HTTPS Proxies, and Deployment Paths

URI template variables supported by Spring Security include `{baseScheme}`, `{baseHost}`, `{basePort}`, `{basePath}`, and `{registrationId}`; `{baseUrl}` represents the combination of scheme, host, port, and base path. This is useful when the same configuration runs across local, staging, and production.

Real-world application example:

~~~text
Browser:     https://app.example.test/portal/private
Reverse proxy / ingress: TLS termination at public edge
Backend:     http://service:8080/portal/private

Callback public expected:
https://app.example.test/portal/login/oauth2/code/company
~~~

If the backend sees an internal scheme of `http`, host `service`, or port `8080` and computes:

~~~text
http://service:8080/portal/login/oauth2/code/company
~~~

then the IdP will very likely reject it or the browser will be unable to reach the callback. You must check trusted forwarded headers (`Forwarded` / `X-Forwarded-*`), public host, and context path configuration. In Spring Boot Servlet, `server.forward-headers-strategy` can be used per environment; for example, `framework` is appropriate only when your reverse proxy **strips/overwrites headers sent by external clients** and the app trusts only controlled proxies.

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Do not blindly trust `X-Forwarded-Host` coming from the internet: attackers can manipulate the generated URL if the proxy does not sanitize headers. Two commonly considered options are:

- **Absolute callback URI for production:** configure `redirect-uri: "https://app.example.test/login/oauth2/code/company"` to pin a fixed value per environment. Requires separate configuration for staging/local and verifying the callback path.
- **`{baseUrl}` template:** flexible across environments; strictly verify public origin, context path, and forwarded-headers policy through integration tests.

If the gateway prepends `/portal` while the app does not see that prefix, decide consistently where path rewriting and forwarded prefixes are handled; do not change the redirect URI alone when callback routing does not match.

## 7. Application Identity Details in the IdP

When creating a client in the IdP, you typically declare a set of settings like the following:

| IdP Item | Illustrative Value | Spring Equivalent |
| --- | --- | --- |
| Client type | Confidential web application (backend) | Client can keep a secret server-side |
| Client ID | `app-web-prod` (issued by IdP) | `client-id`, **not** `company` |
| Client secret / authentication method | Secret via Vault, HTTP Basic auth at token endpoint | `client-secret` / `client-authentication-method` |
| Grant types | Authorization Code | `authorization-grant-type: authorization_code` |
| Allowed redirect URIs | `https://app.example.test/login/oauth2/code/company` | Actual redirect must match this value |
| Issuer/tenant/realm | `https://id.example.test/realms/staff` | `provider.staff-idp.issuer-uri` |
| Allowed scopes | `openid`, `profile`, `email` | Permitted and requested scopes |
| Allowed origins / CORS (if any) | Origins required by the IdP | Do not confuse CORS config with the redirect URI allowlist |
| Post-logout redirect URIs (if any) | Logout URIs permitted by the IdP | Separate from the authorization callback |

**Different Client IDs across environments:** many organizations create separate apps `app-web-local`, `app-web-staging`, `app-web-prod`, each with its own credentials and callback allowlist. This limits blast radius if a secret leaks and allows independent rotation.

**One client with multiple providers/tenants:** if there are two IdPs or multiple realms, each `ClientRegistration` must point to that client's exact issuer and credentials. Never accept `issuer-uri`, `redirect-uri`, or `client-id` from untrusted HTTP queries to alter registrations at runtime. Every provider used for login must belong to an approved registry with explicit user mapping and account linking policies.

## 8. Confidential Client, Public Client, and PKCE

| Case | Can Keep Secret Safe? | Recommended Flow |
| --- | --- | --- |
| Backend web/BFF handling tokens | Yes, if the secret stays server-side | Authorization Code; use appropriate client authentication; prefer PKCE when IdP supports it |
| SPA running in browser | No | Authorization Code + PKCE with a **public client**; never ship a secret to the browser |
| Native mobile/desktop | No | Authorization Code + PKCE and policy-compliant registered/loopback callbacks |
| Service-to-service without browser/user | Potentially yes | `client_credentials`, without login callbacks or user ID Tokens |

**PKCE** adds `code_challenge` to the authorization request and `code_verifier` during code exchange, reducing the risk that someone else can use an intercepted authorization code. It **does not** make a `client_secret` safe when embedded in an SPA. Spring Security supports PKCE; for eligible public clients, the framework enables it automatically when configured with `client-authentication-method: none` and no `client-secret`, or you can configure PKCE for supported clients. Verify PKCE requirements at the IdP, especially for confidential clients.

Three distinct security values:

- **`state`:** binds the authorization response to the initiated request, defending against forged callbacks/CSRF and preserving association with the login session.
- **PKCE `code_verifier`:** binds the authorization code exchange to the party that created the authorization request.
- **OIDC `nonce`:** binds the ID Token to the corresponding authentication request, reducing replay risk; the framework and provider must coordinate properly.

Do not bypass these checks to “quickly fix” callback errors. The session/cookie storing the authorization request must be protected; in multi-instance deployments, configure suitable session storage so the callback can find the original request. When callback `state` is wrong or missing, investigate session, cookie, proxy, SameSite, load balancer, or request repository issues; never accept arbitrary `state` values.

## 9. Client ID, Issuer, and User Identity in OIDC

OAuth 2.0 defines **delegated resource access**. OIDC extends it with an ID Token to express **user authentication** within a specific issuer's context. With OIDC:

- `client_id` identifies **the application** to the IdP. One application serving thousands of users still shares the same `client_id` per environment.
- `iss` identifies **the ID Token issuer** and must match the configured trusted issuer.
- `aud` must contain the **client_id** of the application receiving the ID Token; audience checking is an essential part of validation.
- `sub` identifies **the user** within the issuer's scope; when a durable user key is needed, use the pair `(iss, sub)`. Do not assume `sub` is consistent across IdPs or clients when a provider uses pairwise subjects.
- `email` and `preferred_username` are provider-dependent claims that can change; do not use them as the sole security identifier without an explicit policy.
- `scope=openid` requests OIDC; `scope=profile,email` requests additional claims. **Scopes do not automatically become admin permissions or Spring authorities**.

Spring Security, when properly configured for OIDC, validates core ID Token conditions through its OIDC components; do not extract tokens from callbacks, Base64-decode them manually, and trust all claims. Distinguish ID Tokens used for **the client identifying the user** from Access Tokens used to **call protected resources**; never arbitrarily send an ID Token as a Bearer Access Token to a separate API.

Example retrieving validated info inside a protected controller:

~~~java
package example.security;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "issuer", user.getIdToken().getIssuer().toString(),
                "subject", user.getSubject());
    }
}
~~~

This is an **illustrative controller in an app serving OIDC users only**; if the app also supports non-OIDC OAuth2 or other authentication types, the `OidcUser` parameter may not be present and must be handled by principal type. An endpoint returning issuer + subject should be exposed only when actually required by a feature; production systems should consider avoiding unnecessary exposure of identifiers to clients.

## 10. Testing `ClientRegistration` with Java 17 and JUnit 5

You do not need to connect to a real IdP to verify that `ClientRegistration` fields are mapped properly. The example below builds an in-memory repository and verifies core fields; this is a **runnable unit test** when the project has `spring-boot-starter-oauth2-client` and JUnit 5.

File `src/test/java/example/security/ClientRegistrationContractTest.java`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class ClientRegistrationContractTest {

    @Test
    void resolvesExpectedClientIdentityAndRedirectTemplate() {
        ClientRegistration registration =
                ClientRegistration.withRegistrationId("company")
                        .clientId("web-test-client")
                        .clientSecret("test-only-secret")
                        .clientAuthenticationMethod(
                                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                                AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                        .scope("openid", "profile")
                        .authorizationUri("https://id.example.test/oauth2/authorize")
                        .tokenUri("https://id.example.test/oauth2/token")
                        .jwkSetUri("https://id.example.test/oauth2/keys")
                        .issuerUri("https://id.example.test")
                        .clientName("Test SSO")
                        .build();

        InMemoryClientRegistrationRepository repository =
                new InMemoryClientRegistrationRepository(registration);

        ClientRegistration actual = repository.findByRegistrationId("company");

        assertNotNull(actual);
        assertEquals("company", actual.getRegistrationId());
        assertEquals("web-test-client", actual.getClientId());
        assertEquals(AuthorizationGrantType.AUTHORIZATION_CODE,
                actual.getAuthorizationGrantType());
        assertEquals("{baseUrl}/login/oauth2/code/{registrationId}",
                actual.getRedirectUri());
        assertEquals("https://id.example.test",
                actual.getProviderDetails().getIssuerUri());
    }
}
~~~

Command to run in a Spring Boot project with Gradle wrapper:

~~~bash
./gradlew test --tests example.security.ClientRegistrationContractTest
~~~

On Windows use `.\gradlew.bat test --tests example.security.ClientRegistrationContractTest`. Expected result: **JUnit test passes**; no custom stdout from the test class. The string `test-only-secret` here is dummy data inside an offline test; never use it as a real secret.

This test only checks the model/repository. It **does not** prove HTTPS/TLS, metadata discovery, HTTP callbacks, token exchange, cookie state, PKCE, or end-to-end ID Token validation. Those require integration tests against a test IdP or an approved staging environment.

### Verifying Real Redirects via Browser/HTTP

In a properly configured test environment:

1. Navigate to `https://app.example.test/oauth2/authorization/company`.
2. Observe the HTTP 302 generated by Spring: the `Location` header must point to the **IdP's authorization endpoint** with the right `client_id` and `redirect_uri` (along with `response_type=code`, `state`, and other framework-generated parameters).
3. At the IdP, try logging in with a test account. The callback at `https://app.example.test/login/oauth2/code/company` must hit the right Spring filter and complete the code exchange.
4. Verify the user can access `/private` only when authenticated; errors are returned when `state` is wrong, code is expired, issuer is invalid, or token/audience is wrong.

Only use network/debugger tools in test environments. Authorization codes, `state`, session cookies, and tokens may contain sensitive data; never capture or share raw callback queries in logs/tickets. Do not manually type arbitrary `code` values into the callback to fake a successful login.

## 11. Common Issues and How to Diagnose Them

| Symptom | Common Cause | How to Check Properly |
| --- | --- | --- |
| IdP reports `redirect_uri_mismatch` / invalid redirect URI | Public URL differs from value registered at the IdP | Compare scheme, host, port, path, `registrationId`, trailing slash; inspect actual URL in authorization request |
| Callback returns 404 or hits another handler | `ClientRegistration.redirectUri` and Spring redirection endpoint do not match | Keep default `/login/oauth2/code/*` filter or align both sides if customized |
| Authorization URL has an unexpected `client_id` | Using wrong staging/tenant client or wrong registration | Cross-check the `registrationId` – `client_id` – `issuer` tuple and runtime config |
| Token endpoint reports `invalid_client` | Wrong/expired client secret, wrong authentication method, wrong client type | Check backend credentials and methods supported by IdP; never print secrets |
| Token endpoint reports `invalid_grant` | Expired/reused code, inconsistent redirect URI, wrong PKCE verifier | Check flow and timing; each authorization code may be used only as specified |
| Callback reports state/session not found | Browser lost session cookie, proxy/load balancer/session store issue | Inspect cookie policy, SameSite, TLS, session persistence, and auth request repository |
| URI becomes `http://internal:8080/...` | Backend builds `{baseUrl}` from internal host/protocol | Check trusted forwarded headers and ingress; test public origin |
| OIDC token rejected due to issuer/audience | Wrong realm/issuer, wrong client ID, or mismatched provider config | Verify discovery, issuer metadata, and client registration; never disable validation |
| Expected login path not found | Wrong `registrationId`, missing repository, or altered authorization endpoint | Check `/oauth2/authorization/{registrationId}` and security configuration |
| Login succeeds but user lacks app access permissions | Scope/claims/authorities mapping not configured properly | Separate authentication errors from authorization; review group/role mappings |
| After secret rotation, instances fail inconsistently | Instances still have stale credentials or old sessions/authorized clients | Review rotation strategy, rollout, and token/cookie state |

Never solve these errors by **opening wildcard callbacks**, disabling TLS, removing `state`, trusting all ID Tokens, switching to implicit flow, or printing `client_secret` for comparison. Those changes mask integration bugs and open security holes.

## 12. Procedure for Changing `client_id`, Secrets, and Redirect URIs

When deploying to a new environment or rotating credentials, proceed in order:

1. **Identify exact client/IdP details:** record non-secret app metadata including environment name, owner, `registrationId`, `client_id`, `issuer`, grant, and exact callback.
2. **Register client at IdP:** enable `authorization_code`, configure client type, authentication method, scopes, redirect allowlist, and PKCE policy. Create a separate client for production whenever possible.
3. **Provision secrets safely:** inject `client_secret`/private keys via a secret manager or approved deployment channel; restrict and audit read access.
4. **Synchronize callbacks:** compare `ClientRegistration.redirectUri`, the callback-handling filter, and the IdP allowlist; test behind proxies and with context paths if applicable.
5. **Deploy and verify:** test authorization request, callback, ID Token, failed logins, session, and post-login redirect using test accounts.
6. **Rotate with a controlled window:** if the IdP allows multiple active secrets concurrently, roll out the app in waves and then revoke the old secret; otherwise, plan synchronized rollout and rollback. Never store old secrets in tickets.
7. **Monitor operations:** login success/failure rates, `invalid_client`/`invalid_grant` errors, callback 4xx/5xx, issuer mismatches, and TLS handshakes; avoid logging raw tokens/codes/state.

A multi-tenant application needs a policy to determine the tenant from a trusted source before choosing a registration. Do not rely on an unverified user email domain to automatically select a privileged client or redirect host arbitrarily.

## 13. Pre-Production Checklist for OAuth2/OIDC Clients

- [ ] Unique `registrationId`, mapped accurately to `client_id`, `issuer`, provider endpoints, and deployment environment.
- [ ] Correct client type: confidential backend / public SPA; secrets never appear in frontend bundles, Git, URLs, logs, or telemetry.
- [ ] Uses Authorization Code, with PKCE per provider policy; never uses `client_credentials` for human login.
- [ ] Public redirect URI uses HTTPS, matches the IdP allowlist exactly, and contains no wildcards/open redirects.
- [ ] Login initiation URI, callback URI, and post-login URI are clearly designed; custom callbacks update Spring filter and IdP in sync.
- [ ] `{baseUrl}` computes the right scheme, host, port, and base path behind trusted reverse proxies; forged client headers cannot influence redirects.
- [ ] Spring Security stores and checks `state`, PKCE/nonce per specification; sessions/cookies are protected.
- [ ] OIDC ID Tokens are verified for signature, issuer, audience, validity period, and required constraints; user keys rely on issuer + subject.
- [ ] Scopes/claims and app permissions are explicitly mapped/checked; `client_id` is never used as a user permission.
- [ ] Integration tests exist for wrong redirect URI, `invalid_client`, state mismatch, expired code, wrong issuer/audience, and missing session.
- [ ] Secret rotation, certificate/key rotation, and IdP metadata changes have clear owners, error monitoring, and safe rollback plans.

**Key takeaway:** `ClientRegistration` describes **the Spring application's registration with an IdP**. `registrationId` is the key inside Spring, `client_id` is the application identifier at the IdP, and `client_secret` is the application's secret if it is a confidential client. `redirect_uri` is the callback permitted by the IdP and must match the path Spring actually handles. **User** identity in OIDC is verified from the token and issuer, not inferred from `client_id` or email alone.

## References

- [Spring Security — OAuth 2.0 Login: Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — OAuth 2.0 Login: Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth 2.0 Client: Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — Authorization Grants and PKCE](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — OAuth 2.0 Login with WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
