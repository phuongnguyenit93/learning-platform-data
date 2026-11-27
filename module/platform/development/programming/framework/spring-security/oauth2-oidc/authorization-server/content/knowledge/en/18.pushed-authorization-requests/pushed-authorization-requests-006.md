# Enforcing Per-Client PAR Policy

**Pushed Authorization Requests (PAR)** is a mechanism standardized in **RFC 9126** that lets an OAuth 2.0/OpenID Connect (OIDC) client send authorization request parameters directly to the Authorization Server over an HTTP back-channel connection, then use a short-lived `request_uri` to direct the user's browser to the Authorization Endpoint. Rather than placing all of `scope`, `redirect_uri`, `state`, `nonce`, `code_challenge`, and extension parameters in the browser URL, the client **pushes** them to the server first and receives a reference.

In many organizations, not every client migrates to PAR at the same time. An application handling payments or sensitive data may **require PAR**, while an older internal web client is permitted to use standard authorization requests during a transition period. The direct problem of this lesson is: **configuring and enforcing a mandatory PAR policy per client, rather than just enabling `/oauth2/par` server-wide**.

This lesson belongs to the **PAR** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, in the track for designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using **Spring Security** and **Spring Authorization Server** in a Spring Boot application.

> **Important distinction:** "The Authorization Server **supports** PAR" means the `/oauth2/par` endpoint can accept requests. "Client X **requires** PAR" means the Authorization Endpoint must **reject** any direct authorization request for X lacking a valid `request_uri` **created by the PAR Endpoint and bound to X**. These two statements are not synonymous.

**Version scope:** Configuration examples use **Spring Authorization Server 1.5.x** with Spring Security 6.5.x/Spring Boot 3.x. PAR was introduced into Spring Authorization Server in **1.5**. In Spring Security 7.x, Authorization Server was integrated into Spring Security, so exact API names and policy configuration capabilities must be checked against that version's docs. The examples below avoid assuming a `requirePushedAuthorizationRequests(true)` setter in `ClientSettings.Builder` in 1.5.x: **that setter does not exist in the official API of that version**.

## 1. Why must some clients use PAR?

A traditional authorization request URL looks like:

```text
GET https://login.example.com/oauth2/authorize
    ?response_type=code
    &client_id=payments-portal
    &redirect_uri=https%3A%2F%2Fpayments.example.com%2Flogin%2Foauth2%2Fcode%2Fcentral
    &scope=openid%20payments.read
    &state=RANDOM_STATE
    &code_challenge=CHALLENGE_VALUE
    &code_challenge_method=S256
    &nonce=RANDOM_NONCE
```

Even though HTTPS protects data in transit, **the query string** still travels through the browser and can appear in history, observability tools, reverse proxy logs, or improperly configured integrations. If the request carries `authorization_details`, `claims`, or sensitive business data, the URL can become too long or leak unnecessary information.

PAR helps:

1. **Reduce authorization request data visible on the front-channel**: the browser primarily receives `client_id` and `request_uri`.
2. **Validate early** the client, callback, scopes, and certain policy conditions at the PAR Endpoint.
3. **Bind** a stored authorization request to the client that pushed the request.
4. **Limit parameter tampering via URL** because the server looks up the original content from the stored reference.
5. **Create risk-based mandatory policies**: high-sensitivity clients cannot fall back to the traditional URL flow to bypass rules.

PAR does not on its own prevent all phishing, XSS, CSRF, session abuse, open callbacks, or token theft. In the Authorization Code Flow, you still need **PKCE**, `state`, redirect URI validation, appropriate client authentication, OIDC validation, and access token verification at the Resource Server.

### 1.1. Multi-client scenario

Suppose Central Login has three applications (plus a mobile client):

| Client | Characteristics | PAR policy | Reason |
|---|---|---|---|
| `payments-portal` | Confidential BFF, sensitive payment data | **Mandatory** | Reduce front-channel parameters; disallow fallback |
| `reports-console` | Confidential app, internal info | **Mandatory** | Integration contract requires PAR and PKCE |
| `legacy-staff-portal` | Legacy confidential web app | **Not yet mandatory** during migration | Needs time to upgrade OAuth client |
| `mobile-public` | Public mobile client | Depends on threat model and support | Still uses `none` + PKCE; PAR does not give a public client a secret |

All four clients can talk to the same **PAR Endpoint**. What differs is **behavior at the Authorization Endpoint for each client ID**, not creating four different PAR URLs.

## 2. PAR works across two HTTP requests and a code exchange step

```mermaid
sequenceDiagram
    autonumber
    participant Client as payments-portal (BFF)
    participant PAR as POST /oauth2/par
    participant Browser as Browser
    participant Authorize as GET /oauth2/authorize
    actor User as User
    participant Token as POST /oauth2/token

    Client->>Client: Generate state, nonce, PKCE verifier/challenge
    Client->>PAR: POST form authorize params + client authentication
    PAR->>PAR: Verify client, redirect URI, grant, scope, PKCE
    PAR-->>Client: 201 Created: request_uri + expires_in
    Client-->>Browser: 302 /oauth2/authorize?client_id=...&request_uri=...
    Browser->>Authorize: GET /oauth2/authorize with request_uri
    Authorize->>Authorize: Check request_uri, client binding, expiry, policy
    Authorize->>User: Login and consent if required
    Authorize-->>Browser: Redirect callback with code + state
    Browser-->>Client: Callback code + state
    Client->>Client: Verify state and retrieve transaction verifier
    Client->>Token: Exchange code + verifier + client authentication
    Token-->>Client: Access token / ID token per policy
```

**Note:** PAR **does not replace** the Authorization Code Flow. The Authorization Server still issues an authorization code, and the client still exchanges the code at `/oauth2/token`. PAR only changes **how the authorization request is transported and bound** prior to user authentication/authorization.

### 2.1. What does the PAR POST contain?

Example for a confidential client:

```http
POST /oauth2/par HTTP/1.1
Host: login.example.com
Authorization: Basic <base64(payments-portal:client-secret)>
Content-Type: application/x-www-form-urlencoded

response_type=code&client_id=payments-portal&redirect_uri=https%3A%2F%2Fpayments.example.com%2Flogin%2Foauth2%2Fcode%2Fcentral&scope=openid%20payments.read&state=RANDOM_STATE&code_challenge=CHALLENGE&code_challenge_method=S256&nonce=RANDOM_NONCE
```

At the PAR Endpoint, the client authenticates using the mechanism matching its client type and registration. Confidential clients can use `client_secret_basic`, `private_key_jwt`, or another supported method; public clients using `none` have no secret to prove identity. For public clients, abuse controls and PKCE must be evaluated separately.

**Do not send `request_uri` in the POST request to the PAR Endpoint.** RFC 9126 requires rejecting a PAR request containing the `request_uri` parameter, because that parameter is only issued by the server after the request is accepted.

### 2.2. Successful PAR response

```http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "request_uri": "urn:ietf:params:oauth:request_uri:OPAQUE_REFERENCE",
  "expires_in": 60
}
```

`request_uri` is a **reference to the authorization request accepted/stored by the server**, not an authorization code, access token, or arbitrary URL for the browser to fetch. `expires_in` is the number of seconds the reference remains accepted; the number `60` is merely illustrative, not a default guaranteed by all Spring versions.

### 2.3. Browser carries only the reference

After receiving `request_uri`, the client redirects the browser:

```http
GET /oauth2/authorize?client_id=payments-portal&request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3AOPAQUE_REFERENCE HTTP/1.1
Host: login.example.com
```

Do not append a new `scope` or `redirect_uri` to this URL to alter the original request. The server must use **the pushed content** along with binding checks. The client still keeps `state`, `nonce`, and `code_verifier` in its own transaction state to verify the callback/token response.

## 3. Conditions on `request_uri` per RFC 9126

| Rule | Meaning | Bug to prevent |
|---|---|---|
| Issued by PAR Endpoint | Do not accept client-fabricated references | "Has `request_uri`, so let it pass" |
| Unguessable | Value contains a sufficiently strong cryptographic random component | Sequential IDs or predictable values |
| Bound to pushing client | `client_id` at authorize must match the PAR client | Client A uses B's `request_uri` |
| Time-limited | Must be rejected once `expires_in` elapses | Browser reopens old URL hours later |
| Single-use per RFC guidance | Client uses `request_uri` only once; server should enforce one-time except valid reload cases | Replay / request swapping |
| No conflicting parameter overrides | Authorization request must not be silently altered by new query params | Scope escalation, redirect change, state swap |
| Standard authorization validation | PAR does not waive grant, consent, PKCE, or redirect checks | "Already pushed, so valid forever" |

**RFC 9126:** Clients **must use a request URI only once**. Authorization Servers **should** treat the reference as single-use, though they may permit repeated requests due to browser reloads. Therefore, tests must distinguish unauthorized replay from reload behavior supported by the server version; do not claim every second request is always rejected in all configurations.

### 3.1. `request_uri` is not a URL for the backend to fetch arbitrarily

With PAR, the `request_uri` value is issued by the Authorization Server and may be an **opaque URN**. Never pass it into an HTTP client to fetch a client-supplied URL: that easily leads to SSRF if misimplemented. The framework must look up the reference from a trusted data source and verify client binding, expiry, and state.

### 3.2. `request_uri` TTL is not the login duration

The lifetime of `request_uri` defines the window to begin using the reference at the Authorization Endpoint, **not identical** to the lifetime of an access token, authorization code, refresh token, or login session. When login/consent spans multiple steps, test the TTL and saved-request restoration behavior of your specific version.

Clients should issue `POST /oauth2/par` **close to the time of redirecting to `/oauth2/authorize`**, rather than pre-pushing batches minutes in advance. When a reference expires, initiate a new PAR per contract; do not extend TTL indefinitely to hide architectural flaws.

## 4. Mandatory PAR policy: support vs. enforcement

RFC 9126 permits the **Authorization Server to mandate PAR globally or per client**. If a client must use PAR, a direct authorization request lacking a PAR-Endpoint-issued `request_uri` must be rejected with an `invalid_request` error.

### 4.1. Four cases at the Authorization Endpoint

| Client | Request to `/oauth2/authorize` | Expected outcome |
|---|---|---|
| `payments-portal` requires PAR | Has `client_id` and **no `request_uri`** | **Reject with `invalid_request`** |
| `payments-portal` requires PAR | Has valid `request_uri` pushed by this exact client | Continue login/consent per policy |
| `legacy-staff-portal` does not require PAR yet | Valid traditional authorization request | May proceed |
| `legacy-staff-portal` does not require PAR yet | Valid PAR usage | May still proceed; "not mandatory" does not mean "PAR forbidden" |

Do not use an open/closed endpoint list as a substitute for a per-client policy. A working `/oauth2/par` endpoint still leaves high-risk clients able to send direct authorize requests if the server does not **enforce** the rejection rule.

### 4.2. Right place to enforce

- **PAR Endpoint** authenticates the client if applicable, receives and validates the pushed request, and stores the reference data.
- **Authorization Endpoint** must apply the **per-client mandatory PAR condition** before issuing an authorization code or proceeding to unnecessary login/consent steps.
- **OAuth2AuthorizationService** or the framework's state store owns request/code data and associated bindings.
- **Token Endpoint** still checks the authorization code, PKCE, client authentication, and redirect binding.

Merely adding a flag in a database or client admin UI **does not enforce** requests at the Authorization Endpoint on its own.

## 5. API limitations in Spring Authorization Server 1.5.x

Spring Authorization Server 1.5.x includes:

- `OAuth2AuthorizationServerConfigurer.pushedAuthorizationRequestEndpoint(...)` to customize the PAR Endpoint;
- `AuthorizationServerSettings.Builder.pushedAuthorizationRequestEndpoint("/oauth2/par")` to set the path;
- `OAuth2PushedAuthorizationRequestEndpointFilter` and `OAuth2PushedAuthorizationRequestAuthenticationProvider`;
- `OAuth2AuthorizationEndpointConfigurer` to customize authorization requests/consent and providers;
- `RegisteredClient`, `ClientSettings`, and `RegisteredClientRepository` for client metadata.

**However:** `ClientSettings.Builder` in 1.5.x **does not expose** a `requirePushedAuthorizationRequests(boolean)` method; `ClientSettings` also has no `isRequirePushedAuthorizationRequests()` getter in the official API. Therefore, the following **is not valid code** for that version:

```java
// DOES NOT EXIST in SAS 1.5.x ClientSettings.Builder:
ClientSettings.builder()
    .requirePushedAuthorizationRequests(true)
    .build();
```

There are two ways to implement an application policy:

1. **Dedicated policy repository:** For example, `ParPolicyRepository` mapping `RegisteredClient.id` to `requirePar`, managed alongside client registration.
2. **Explicitly owned custom setting:** Use `ClientSettings.Builder.setting("app.security.require_par", Boolean.TRUE)` and read it back via `getSetting(...)`; the application owns persistence, migration, and enforcement handling.

The following example uses the **custom setting**, because it keeps the **per-client** nature visible right where `RegisteredClient` is constructed. The name `app.security.require_par` is a **custom convention in this lesson**, **not** a standard key that Spring understands automatically or that RFC metadata advertises automatically.

### 5.1. Do not confuse RFC metadata with builder APIs

RFC 9126 defines metadata names:

- `pushed_authorization_request_endpoint`: PAR capability/address of the Authorization Server.
- `require_pushed_authorization_requests` in **Authorization Server metadata**: announces that the server requires PAR for **all** authorization requests under a global policy.
- `require_pushed_authorization_requests` in **client metadata**: announces that **that specific client** may initiate authorization only via PAR.

In a **mixed deployment** (where only `payments-portal` and `reports-console` require it), do not publish a global `require_pushed_authorization_requests=true` boolean, because that falsely signals **all** clients must use it. Provide onboarding docs/communication channels or per-client dynamic client metadata tailored to the deployment.

If implementing Dynamic Client Registration, verify whether your framework version actually supports storing and publishing that metadata field. Never assume calling `.setting("app.security.require_par", true)` produces `require_pushed_authorization_requests` in discovery or client registration responses.

## 6. Registering two `RegisteredClient` instances with different policies

The example below uses **Spring Authorization Server 1.5.x** and custom `ClientSettings`. Both clients use Authorization Code, PKCE, and client authentication; only one client is marked **PAR-required**.

```java
package example.authserver.config;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration(proxyBeanMethods = false)
public class ClientRegistryConfig {

    public static final String REQUIRE_PAR =
            "app.security.require_par"; // Application-defined setting.

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder encoder, Environment env) {

        RegisteredClient payments = RegisteredClient
            .withId("payments-portal-registration")
            .clientId("payments-portal")
            .clientSecret(encoder.encode(
                env.getRequiredProperty("PAYMENTS_CLIENT_SECRET")))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "https://payments.example.com/login/oauth2/code/central")
            .scope(OidcScopes.OPENID)
            .scope("payments.read")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .setting(REQUIRE_PAR, true)
                .build())
            .build();

        RegisteredClient legacy = RegisteredClient
            .withId("legacy-staff-registration")
            .clientId("legacy-staff-portal")
            .clientSecret(encoder.encode(
                env.getRequiredProperty("LEGACY_CLIENT_SECRET")))
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "https://staff.example.com/login/oauth2/code/central")
            .scope(OidcScopes.OPENID)
            .scope("profile")
            .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(false)
                .setting(REQUIRE_PAR, false)
                .build())
            .build();

        return new InMemoryRegisteredClientRepository(List.of(payments, legacy));
    }
}
```

### 6.1. Role of each configuration layer

| Component | Function | What does **not** happen automatically? |
|---|---|---|
| `clientId` | Protocol client identifier | Not a credential |
| `clientSecret` / `client_secret_basic` | Authenticates confidential client at PAR/token endpoints | Does not replace `request_uri`, PKCE, or consent |
| `authorization_code` | Enables user-facing flow | Does not mandate PAR |
| `requireProofKey(true)` | Requires Authorization Code + PKCE | Does not mandate PAR |
| `requireAuthorizationConsent(...)` | Policy for user scope approval | Does not decide PAR |
| `setting(REQUIRE_PAR,true)` | **Stores custom policy** for the client | **Does not self-enforce** without validation/guard |
| `redirectUri` | Callback allowlist | Must not relax to wildcards just because PAR is used |

**Production:** Do not rely on `InMemoryRegisteredClientRepository` for real policy storage. With JDBC/custom repositories, ensure custom settings serialize/deserialize cleanly, keep `RegisteredClient.id` stable, and stay synchronized across nodes. Do not arbitrarily change `client_id`/internal IDs because authorizations/consents may reference the registration.

## 7. Enforcing mandatory PAR at the Authorization Endpoint

The key is not merely modifying the PAR Endpoint. A client can skip `/oauth2/par` and send directly:

```http
GET /oauth2/authorize?response_type=code&client_id=payments-portal&redirect_uri=https%3A%2F%2Fpayments.example.com%2Flogin%2Foauth2%2Fcode%2Fcentral&scope=openid%20payments.read&state=SAMPLE_STATE&code_challenge=CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.com
```

If `payments-portal`'s policy requires PAR, the Authorization Server must reject **before issuing a code**, even when `response_type`, `redirect_uri`, `scope`, and PKCE are all valid.

### 7.1. Two validation tiers to preserve

**Tier 1 — Per-client check:** For a client configured with `REQUIRE_PAR=true`, an HTTP request entering `/oauth2/authorize` must carry **one** non-empty `request_uri`. A direct request lacking the reference is rejected with `invalid_request`.

**Tier 2 — Standard protocol check:** Was `request_uri` actually created by the PAR Endpoint, unexpired, bound to the exact client, not reused contrary to policy, and pointing to a validated request? **Spring Authorization Server** must continue checking all of these conditions. Tier 1 only looks at parameter **presence**, which is **not sufficient** to prove a valid PAR.

Never build a filter that treats `request_uri=anything` as valid and mints a code itself. After the guard, the request must flow into **Spring's native Authorization Endpoint**.

### 7.2. Filter example for per-client policy

To inspect parameters **on the original HTTP request** before the Authorization Endpoint dereferences `request_uri`, you can place an early `OncePerRequestFilter` **inside the protocol SecurityFilterChain**. The code below implements **Tier 1**; all Tier 2 validation remains Spring's responsibility.

```java
package example.authserver.security;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequireParForClientFilter extends OncePerRequestFilter {

    // Same key used when building RegisteredClient.
    private static final String REQUIRE_PAR = "app.security.require_par";

    private final RegisteredClientRepository clients;
    private final String authorizationPath;

    public RequireParForClientFilter(
            RegisteredClientRepository clients,
            AuthorizationServerSettings serverSettings) {
        this.clients = clients;
        this.authorizationPath = serverSettings.getAuthorizationEndpoint();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Filter only the Authorization Endpoint; do not affect /oauth2/par,
        // /oauth2/token, /login, /oauth2/jwks, metadata...
        return !authorizationPath.equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String[] ids = request.getParameterValues(OAuth2ParameterNames.CLIENT_ID);

        if (ids != null && ids.length != 1) {
            rejectInvalidRequest(response);
            return;
        }

        if (ids == null || !StringUtils.hasText(ids[0])) {
            // Let the underlying framework return missing/invalid client_id errors.
            chain.doFilter(request, response);
            return;
        }

        RegisteredClient client = clients.findByClientId(ids[0]);

        if (client == null) {
            // DO NOT redirect to a self-declared callback for an unknown client.
            // The underlying framework must handle non-existent clients.
            chain.doFilter(request, response);
            return;
        }

        boolean parRequired = Boolean.TRUE.equals(
            client.getClientSettings().getSetting(REQUIRE_PAR));

        if (parRequired) {
            String[] uris = request.getParameterValues(
                OAuth2ParameterNames.REQUEST_URI);

            if (uris == null || uris.length != 1
                    || !StringUtils.hasText(uris[0])) {
                rejectInvalidRequest(response);
                return;
            }
        }

        // Presence of request_uri is not enough to trust it.
        // Let Spring check client binding, expiry, pushed content...
        chain.doFilter(request, response);
    }

    private static void rejectInvalidRequest(
            HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        response.getWriter().write("{\"error\":\"invalid_request\"}");
    }
}
```

**Scope/limitations of the example:**

- This is an **application guard**, not a built-in Spring Authorization Server filter.
- If `client_id` is unspecified, the filter lets the **framework** handle it rather than guessing the client from an unverified `request_uri`.
- If a PAR-required client sends `request_uri=garbage`, the guard lets it past **Tier 1**; the framework must reject it at **Tier 2**.
- Returning HTTP `400` with `invalid_request` **directly from the server** avoids redirecting to an unverified `redirect_uri`. If replaced by an integrated OAuth authorization error handler, preserve the boundary of **never redirecting to untrusted URIs**.
- `getServletPath()` works for servlet examples with the Authorization Endpoint at a single internal path. With context paths, multiple issuers, proxy rewrites, or custom routing, test and adjust the matcher based on actual configuration.
- If production has global/tenant PAR logic or real-time policy updates, the guard must use the **same policy source** as client administration. Never store a separate local allowlist that drifts across nodes.

### 7.3. Registering the filter before the protocol endpoint

Example using Spring Security 6.x APIs, placing the guard **early before `SecurityContextHolderFilter`** (a standard filter with a known order). Because the guard only reads request parameters and looks up registered clients, it **does not need a principal from `SecurityContext`**.

```java
package example.authserver.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

import example.authserver.security.RequireParForClientFilter;

@Configuration(proxyBeanMethods = false)
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            RegisteredClientRepository clients,
            AuthorizationServerSettings settings) throws Exception {

        OAuth2AuthorizationServerConfigurer as =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(as.getEndpointsMatcher())
            .with(as, server -> server
                .pushedAuthorizationRequestEndpoint(
                    Customizer.withDefaults()))
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated());

        // Do not annotate RequireParForClientFilter with @Component:
        // it is registered only in the protocol chain here.
        http.addFilterBefore(
            new RequireParForClientFilter(clients, settings),
            SecurityContextHolderFilter.class);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

**This configuration snippet is not a standalone runnable Authorization Server:** you still need token signing keys/JWK source, `OAuth2AuthorizationService`, `OAuth2AuthorizationConsentService`, issuer, user store/password encoder, and other environment-specific beans. If OIDC is enabled, add the corresponding OIDC configuration. None of these are waived just because PAR is used.

**Note on filter order:** Spring Security orders filters internally; placing the guard before `SecurityContextHolderFilter` ensures it does not depend on a login session, but requires **real HTTP testing** to prove the guard runs **before** `OAuth2AuthorizationEndpointFilter` on your version. Avoid also registering the same filter with the servlet container, which could cause it to run outside the protocol chain or twice.

### 7.4. Why not just add an `AuthenticationProvider`?

If you write a custom provider checking PAR and call `authorizationEndpoint.authenticationProvider(provider)`, that normally **adds** the provider to the list. The original provider may already handle the request before the new provider runs, allowing policy **bypass**. When altering providers or converters, understand and test ordering; if you need to **replace** the default provider, use `authorizationEndpoint.authenticationProviders(...)` and preserve default validations.

In 1.5.x, `OAuth2AuthorizationCodeRequestAuthenticationProvider` has `setAuthenticationValidator(...)`, yet `request_uri` data may already have passed through dereferencing/conversion. To reliably inspect **parameters of the original HTTP request**, the example places a guard before the Authorization Endpoint. If implementing via a provider validator, prove a **trustworthy** signal that the original request truly arrived via PAR rather than only inspecting resolved parameters.

**Never replace default redirect URI/scope validation** with a custom validator that only checks PAR and omits the other checks.

## 8. Enabling the PAR path in `AuthorizationServerSettings`

In Spring Authorization Server 1.5.x, the default path for PAR is `/oauth2/par`. You can declare it explicitly:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .authorizationEndpoint("/oauth2/authorize")
        .pushedAuthorizationRequestEndpoint("/oauth2/par")
        .tokenEndpoint("/oauth2/token")
        .build();
}
```

`AuthorizationServerSettings` **defines endpoint URIs**; it **does not store which clients require PAR**. If changed to `/oauth2/v1/par`, PAR-aware clients, discovery metadata, filters/matchers, and reverse proxies must all agree. The guard in section 7 accepts `settings.getAuthorizationEndpoint()` to avoid hard-coding the endpoint.

### 8.1. Why not block all of `/oauth2/authorize` at the firewall?

Both PAR and direct authorization pass through `/oauth2/authorize`. Blocking all traffic there prevents even PAR-using clients from letting users log in. You must distinguish **requests carrying a validly issued `request_uri`** from requests attempting to pass parameters directly.

Likewise, allowing `/oauth2/par` while blocking `/oauth2/authorize` or redirecting every request to `/login` will prevent PAR from completing.

### 8.2. HTTPS, issuer, and proxies

- `issuer` must be the public HTTPS URL trusted by clients, browsers, and Resource Servers.
- Because the PAR Endpoint is back-channel, it must support client authentication, TLS, and request body limits.
- Trust forwarded headers only from trusted reverse proxies.
- Avoid leaking internal/pod hostnames into metadata or redirect URIs.
- With multiple issuers/tenants, evaluate policy against the **exact issuer and tenant `RegisteredClient`**, never looking up clients from an unsafe shared namespace.

## 9. Required changes on the OAuth2 Client side

**If the server requires PAR while the client still builds direct redirects**, logins will fail. The client must support the sequence:

1. Construct the full authorization request (`state`, PKCE challenge, `nonce`, `scope`, `redirect_uri`).
2. POST parameters to `/oauth2/par` with **client authentication** matching registration.
3. Read the `201 Created` response and store `request_uri`/`expires_in` with the transaction.
4. Redirect the browser to `/oauth2/authorize?client_id=...&request_uri=...`.
5. Receive the callback, match `state`, then exchange the authorization code using the original verifier and client auth if required.
6. Clean up transaction state upon success or failure.

Spring Security OAuth2 Client uses `OAuth2AuthorizationRequestResolver` and `OAuth2AuthorizationRequestRedirectFilter` to initiate the Authorization Code Flow. **Do not assume** that merely adding `pushed-authorization-request-endpoint` to a `ClientRegistration` config file makes the default resolver execute PAR POSTs automatically. You need a **PAR-aware client implementation/library** or tested custom logic that manages `state`, `code_verifier`, and callbacks.

### 9.1. Traditional client configuration does not auto-upgrade to PAR

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          central:
            provider: central
            client-id: payments-portal
            client-secret: "REPLACE_FROM_SECRET_MANAGER"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, payments.read
        provider:
          central:
            issuer-uri: https://login.example.com
```

This is a **basic OAuth2 Client registration** config, **not an example of a PAR-enabled client**. The secret value is just a placeholder; never commit real secrets. To pass the guard for `payments-portal`, the application must execute a PAR POST before redirecting; if it lacks that capability yet, **do not enable the mandatory PAR flag in production before upgrading the client**.

### 9.2. Keep `state` and PKCE intact across both steps

In Authorization Code + PKCE, `code_verifier` is kept by the client, `code_challenge` is placed in the **pushed request**, and the original verifier is used when exchanging the code. Regenerating the verifier after the PAR response will cause `invalid_grant` at the Token Endpoint.

`state` links the callback to the authorization transaction; do not generate a fresh `state` when moving from the PAR response to the browser redirect. Similarly, if the OIDC request has a `nonce`, preserve its link to ID token validation.

### 9.3. Do not put sensitive parameters back into the URL

If after pushing, the client still redirects to:

```text
/oauth2/authorize?client_id=payments-portal&request_uri=...&
    scope=payments.write&redirect_uri=https://attacker.example/cb
```

then it **defeats the purpose of PAR**. The Authorization Endpoint must use the pushed request and reject conflicting values per profile; never let new query params escalate scopes or change callbacks. In deployment testing, proactively write adversarial tests for this scenario.

## 10. HTTP/curl: illustrating the happy path and rejected paths

### 10.1. Step 1 — Client pushes the authorization request

Test-environment example of a confidential BFF client:

```bash
curl --request POST "https://login.example.com/oauth2/par" \
  --user "$PAYMENTS_CLIENT_ID:$PAYMENTS_CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "response_type=code" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "redirect_uri=https://payments.example.com/login/oauth2/code/central" \
  --data-urlencode "scope=openid payments.read" \
  --data-urlencode "state=$OAUTH_STATE" \
  --data-urlencode "code_challenge=$PKCE_CHALLENGE" \
  --data-urlencode "code_challenge_method=S256" \
  --data-urlencode "nonce=$OIDC_NONCE"
```

The variables `OAUTH_STATE`, `PKCE_CHALLENGE`, and `OIDC_NONCE` must be securely generated per transaction. The example does not generate them itself. If valid, you receive JSON with `request_uri` and `expires_in`; **do not forward the entire JSON response to the browser**—build the redirect only from the reference value.

Note that `curl --user` can expose credentials in command-line/process listings depending on the environment; never use real secrets in documentation or public CI logs.

### 10.2. Step 2 — Redirect browser to the Authorization Endpoint

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "request_uri=$REQUEST_URI"
```

This command simulates the HTTP GET; it does not complete login/consent. Without a browser session, the server may redirect to the login page; that is expected behavior. In a real application, this is a **browser redirect**, not the backend calling `curl` to complete login on the user's behalf.

### 10.3. Negative test — Bypassing PAR with a standard authorization URL

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "response_type=code" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "redirect_uri=https://payments.example.com/login/oauth2/code/central" \
  --data-urlencode "scope=openid payments.read" \
  --data-urlencode "state=$OAUTH_STATE" \
  --data-urlencode "code_challenge=$PKCE_CHALLENGE" \
  --data-urlencode "code_challenge_method=S256"
```

**Expected outcome for the example filter:** HTTP `400` with `{"error":"invalid_request"}`, **no redirect containing an authorization code**. If the request still proceeds to login or issues a code, check whether the guard runs on the exact protocol chain and before the endpoint.

### 10.4. Negative test — Fake reference

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "client_id=payments-portal" \
  --data-urlencode "request_uri=urn:ietf:params:oauth:request_uri:FAKE"
```

The example filter only confirms the parameter **exists**; **Spring Authorization Server** must reject because the reference is **invalid**. If a fake request still reaches code issuance, that is a critical bug in the PAR request URI handling layer.

### 10.5. Legacy client is still allowed to authorize directly

```bash
curl --get --include "https://login.example.com/oauth2/authorize" \
  --data-urlencode "response_type=code" \
  --data-urlencode "client_id=legacy-staff-portal" \
  --data-urlencode "redirect_uri=https://staff.example.com/login/oauth2/code/central" \
  --data-urlencode "scope=openid profile" \
  --data-urlencode "state=$OAUTH_STATE" \
  --data-urlencode "code_challenge=$PKCE_CHALLENGE" \
  --data-urlencode "code_challenge_method=S256"
```

If all other parameters are valid, the legacy client can continue the authentication flow. **Not requiring PAR** does not mean "skip redirect URI/PKCE/state" or "grant every permission"; all protocol validations remain intact.

## 11. Metadata, compatibility, and notifying clients

### 11.1. Discovery metadata

An Authorization Server supporting PAR can advertise:

```json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "pushed_authorization_request_endpoint": "https://login.example.com/oauth2/par",
  "token_endpoint": "https://login.example.com/oauth2/token"
}
```

This example is not complete metadata. When applying **a global policy requiring PAR for all clients**, standard metadata allows:

```json
{
  "require_pushed_authorization_requests": true
}
```

**However, in a mixed deployment** (only `payments-portal` and `reports-console` require it), do not publish a global boolean `true`. Per-client policy can be communicated via client registration metadata, onboarding docs, or a trusted admin API depending on deployment.

### 11.2. Do not confuse PAR with JAR and FAPI

| Technology | Mechanism | Relationship |
|---|---|---|
| **PAR (RFC 9126)** | Client sends authorization parameters over back-channel, receives `request_uri` | Focus of this lesson |
| **JAR (RFC 9101)** | Authorization Request packaged as a signed/encrypted JWT Request Object where applicable | Can combine with PAR; not enabled automatically by PAR alone |
| **PKCE (RFC 7636)** | Binds authorization code to client's verifier | Still required in Authorization Code per policy |
| **FAPI Security Profiles** | High security requirements for financial APIs and similar | May mandate PAR, JAR, and other controls per specific profile |

PAR **does not create a non-repudiable signature** over the full authorization request merely by using HTTPS and client authentication. If a partner requires a signed JWT Request Object, implement and test JAR separately rather than assuming `/oauth2/par` already satisfies it.

## 12. Designing a per-client policy rollout

Switching all clients from direct authorization to mandatory PAR at once can disrupt logins. A safe rollout should have a clear **per-client configuration lifecycle**.

### 12.1. Four recommended operational states

| State | PAR request | Direct authorization | When to use |
|---|---|---|---|
| **Legacy** | Allowed if client supports | Allowed | Application not yet upgraded |
| **Ready/Observe** | Allowed | Allowed and metrics recorded | Testing PAR-capable client |
| **Required** | Allowed | **Reject `invalid_request`** | Verified client works completely with PAR |
| **Disabled/Revoked** | Rejected per policy | Rejected | Client revoked/contract expired |

The `ClientSettings.setting(..., Boolean)` example only expresses **two states: Required vs. Not required**; it has no built-in four-state enum or lifecycle. If the product needs all four states, design a dedicated `ParPolicyRepository` or extend admin metadata; do not overload a boolean to implicitly represent every state.

### 12.2. Migration steps for a client

1. **Inventory:** Identify owner, client ID, client type, grants, redirect URIs, where authorization requests are built, and OAuth2 Client library.
2. **Assess:** Can the client POST PAR before redirecting? Can it manage `state`/PKCE/nonce end-to-end?
3. **Configure:** Complete the PAR Endpoint, registered client, auth method, and PKCE requirement.
4. **Stage testing:** Happy path, direct bypass, expired `request_uri`, wrong-client URI, bad scope/redirect, login/consent, and concurrent sessions.
5. **Observe:** Enable PAR on the client while still accepting direct requests; measure PAR adoption rate and errors.
6. **Require:** Flip `REQUIRE_PAR=true` for that exact client, rolling out consistently across nodes.
7. **Monitor:** Track `invalid_request`, `invalid_client`, `invalid_scope`, login failure rate, and latency from PAR POST to authorize GET.
8. **Controlled rollback:** If needed, adjust the client's policy via the security change process; never disable redirect URI/PKCE checks or open defaults for all clients.

### 12.3. Configuration sources must be consistent

If node A considers `payments-portal` Required while node B considers it Legacy, a load balancer can make a login session succeed or fail unpredictably. Ensure `RegisteredClientRepository`, `app.security.require_par`, `OAuth2AuthorizationService`, and issuer/settings stay consistent across nodes. On changes, track `version`/`updatedAt` for auditing and verifying which nodes loaded the new configuration.

## 13. Testing: mandatory PAR must prove bypass is impossible

### 13.1. Integration test matrix

| Test case | Client / Request | Expectation |
|---|---|---|
| Mandatory PAR happy path | `payments-portal` pushes successfully, authorizes via URI, login/consent, token exchange | Tokens issued per policy |
| Direct request blocked | `payments-portal` sends authorize with valid scope/PKCE but **no `request_uri`** | `invalid_request`, no code issued |
| Blank `request_uri` | `request_uri=` | Rejected |
| Duplicate `request_uri` | Two different values | Rejected |
| Fake `request_uri` | Self-made URI absent from PAR store | Rejected |
| Expired `request_uri` | Used after `expires_in` | Rejected |
| Wrong-client URI | URI created by client A, GET authorize with B's `client_id` | Rejected; no code issued |
| Replay/reload | Reuse URI after consumption | Per implementation's one-time policy; never re-issue improperly |
| Query override | Valid URI plus higher scope/wrong redirect added to browser URL | Cannot escalate scope or alter callback |
| Invalid redirect at push | `/oauth2/par` receives unregistered callback | Rejected at PAR Endpoint |
| Invalid scope at push | Requests unregistered scope | Rejected |
| Wrong PAR client secret | Incorrect Basic secret | `invalid_client`; no URI issued |
| Missing state | Client fails to generate/match state | OAuth2 Client test must reject bad callback |
| Missing PKCE | Client `requireProofKey(true)` missing challenge/verifier | Token issuance cannot complete |
| Consent | Client requires consent; scopes pushed | Consent page shows right permissions, handles approve/deny |
| Legacy direct | `legacy-staff-portal` uses valid direct authorize | Login proceeds |
| Legacy PAR | `legacy-staff-portal` uses PAR | Can proceed when endpoint supports it |
| Setting changed only | `REQUIRE_PAR=true` set without configuring guard | Test must **catch bypass**, not pass |
| Endpoint path changed | `/oauth2/par` moved to `/oauth2/v1/par` | Client/discovery/routing consistent |
| Multi-node | PAR POST on node A, authorize GET on node B | Resolves request URI and exact policy |
| No data leakage | Inspect logs/referer/analytics | No leakage of pushed form, client secret, code, verifier |
| Revocation/expiry | Client disabled or URI expired | No code/token issued |

### 13.2. Filter-level test with MockMvc

The snippet below illustrates test intent (fixture/authentication setup varies by project):

```java
// Test intent: payments-portal requires PAR but accesses directly.
mvc.perform(get("/oauth2/authorize")
        .param("response_type", "code")
        .param("client_id", "payments-portal")
        .param("redirect_uri",
                "https://payments.example.com/login/oauth2/code/central")
        .param("scope", "openid payments.read")
        .param("state", "test-state")
        .param("code_challenge", "test-challenge")
        .param("code_challenge_method", "S256"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("invalid_request"));
```

**The snippet above is not a complete integration test**: the `mvc` fixture must boot the proper Spring context, protocol `SecurityFilterChain`, `RegisteredClientRepository`, and filter guard. A real PKCE challenge in a happy path must be validly formatted; in a case rejected early for missing PAR, an illustrative value only helps verify the guard runs before the remaining steps.

### 13.3. Testing the client with real HTTP

An end-to-end test should preserve browser sessions/cookies and run:

1. Client creates valid state/verifier/nonce; sends PAR POST.
2. Confirm `201` response, `request_uri`, and `expires_in`.
3. Browser opens authorize with that exact URI; logs in if not logged in.
4. Consent if required; callback receives valid code/state.
5. Client verifies state, exchanges code with original verifier.
6. Resource Server receives access token, validates `aud`, scope, tenant, and operation permissions.

To test **two concurrent tabs**, create two pushed requests with distinct state/verifiers. Never store a global `currentRequestUri` or `currentVerifier` that gets overwritten.

### 13.4. Never skip version tests

On every Spring Security/Spring Authorization Server upgrade, verify:

- The filter guard still runs before the Authorization Endpoint;
- `AuthorizationServerSettings` returns the right URIs;
- PAR Endpoint still supports converters/providers as before;
- `request_uri` data remains queryable after redirect/login/consent;
- JDBC/persistence schema stores custom client settings and authorization state properly;
- Client SDKs still build PAR requests and store state/PKCE properly.

## 14. Common errors and troubleshooting

| Symptom | Likely cause | How to resolve |
|---|---|---|
| `POST /oauth2/par` returns 404 | Spring Authorization Server too old, configurer not applied, or different path | Check version ≥ 1.5, endpoint settings, and routes |
| `/oauth2/par` returns `invalid_client` | Wrong secret/method or non-existent client | Match registration and client authentication |
| `/oauth2/par` returns `invalid_scope` | Scope not in allowlist | Fix requested permissions; do not broaden every client |
| `/oauth2/par` returns redirect error | Callback does not match registration | Fix exact redirect URI/issuer/proxy |
| `/oauth2/authorize` still accepts direct requests for Required client | Guard not attached, wrong filter order, or policy not read | Test bypass, check filter order and settings |
| Client just switched to Required fails login | Client has not migrated to PAR POST yet | Upgrade client before enforcing |
| `request_uri` not found after login | TTL expired, state not saved/not synced across nodes | Check expiry, saved requests, and authorization store |
| Valid `request_uri` but different client ID | Reference belongs to another client | Reject; do not remove client binding |
| Empty scope/consent when using PAR | Mapping bug or version/framework regression | Test pushed scopes and custom consent pages |
| Redirect loop | Misconfigured login/session/SecurityFilterChain | Check chain order, CSRF/session, cookies |
| Token endpoint `invalid_grant` | Verifier mismatch, code expired/already used | Do not regenerate PKCE between PAR and token request |
| PAR receives weird fake URIs or oversized URLs | Missing input validation/rate limiting | Bound body size, DoS protection, authenticate clients |
| Metadata says all clients require PAR while legacy still works directly | Global metadata contradicts policy | Fix metadata or complete migration |
| Missing needed API claim | PAR is not a token customizer | Check token settings/customizers and Resource Server policy |
| One node accepts PAR, another rejects URI | State store or issuer out of sync | Shared authorization store, synchronize policies |
| Front-channel URL still contains sensitive claims | Client pushed yet still appended old query params | Redirect only with client ID + request URI |

### 14.1. Never "fix" errors by removing other protection layers

If PAR fails due to a callback mismatch, **do not open wildcard redirect URIs**. If the token endpoint returns `invalid_grant`, **do not disable PKCE**. If browser reloads expire URIs, **do not make `request_uri` live forever**. Fix the real root cause in the client, authorization storage, clocks, routing, or UX.

## 15. Operating and observing per-client policy

### 15.1. Metrics to track

Monitor by client and environment:

- `POST /oauth2/par` success/failure rates;
- Rate of direct authorizations rejected due to `require_par`;
- Rates of expired, already-used, and wrong-client `request_uri` errors;
- Time from PAR response to browser authorize GET;
- Login and consent success/failure, authorization code/token errors;
- Client versions not supporting PAR;
- PAR Endpoint load, oversized request counts, `429` rate limits;
- Client configuration drift across nodes.

Audit events should record `client_id`, policy decision, endpoint, correlation ID, error category, and processing duration. **Never log verbatim** client secrets, `request_uri`, codes, verifiers, access/refresh tokens, cookies, or raw authorization requests containing personal data.

### 15.2. Data consistency

PAR relies on temporarily stored state keyed by request reference, so multiple instances require consistent storage/lookup. At the same time, ensure `RegisteredClientRepository` updates policies atomically across versions to avoid node A seeing "Required" while node B sees "Legacy". Use JDBC or an appropriate store matching your running Spring Authorization Server's capabilities; avoid claiming a default storage type automatically solves concurrency/replay without testing.

### 15.3. Incident response

If you discover a PAR-required client can still authorize directly, treat it as a **security regression**. You must:

1. Confirm the request went through the right filter chain/host/issuer.
2. Inspect client policy from the repository and cached data.
3. Check filter order; verify direct requests are blocked **before code issuance**.
4. Temporarily alert on that client and block at the application layer safely if needed.
5. Re-test valid `request_uri`, expired, wrong-client, and query-override scenarios.
6. Assess the scope of codes/tokens issued before patching and decide on revocation if risk exists.

Do not fix by blocking all `/oauth2/authorize` traffic on the network or disabling login for all clients.

## 16. Hands-on exercise

**Prompt:** A system has `payments-portal` and `legacy-staff-portal`. Both use Authorization Code + PKCE. `payments-portal` requires PAR; `legacy-staff-portal` does not yet. Both share issuer `https://login.example.com` and PAR Endpoint `/oauth2/par`.

**Implementation requirements:**

1. Register both `RegisteredClient` entries with stable IDs and exact redirect URIs.
2. Attach per-client policy via `ClientSettings.setting("app.security.require_par", boolean)` or a policy repository.
3. Apply a protocol chain with the PAR Endpoint and the guard before the Authorization Endpoint.
4. Payments client POSTs PAR, receives `request_uri`, and browser uses a URL with only client ID/request URI.
5. Perform login/consent and code exchange with matching state/PKCE.
6. Send a direct authorization request for payments: receive `invalid_request`, **no code**.
7. Send a direct authorization request for legacy: still processed under normal policy.
8. Send fake, expired, and another-client `request_uri`: all rejected.
9. Check other grants, metadata, multi-node setups, and slow login/consent flows.
10. Only once all tests pass should the Required policy be enabled in production.

**Acceptance criteria:** PAR is genuinely enforced **per client**, does not break other clients' logins, never trusts fake `request_uri`, does not widen scopes/redirects, preserves PKCE/state, and keeps credentials/sensitive request payloads out of browser URLs.

## 17. Self-assessment questions

1. How does supporting PAR differ from enforcing PAR?
2. Why must the client POST `/oauth2/par` **before** redirecting the browser?
3. What fields are in a successful PAR response, what HTTP status code is returned, and what is `request_uri` used for?
4. Why must `request_uri` be bound to the client that pushed it?
5. If a Required client sends a direct authorization request that still has valid PKCE, what must the server do?
6. Is a non-empty `request_uri` sufficient proof that a pushed request is valid?
7. Why is the TTL of `request_uri` not identical to the TTL of an authorization code or login session?
8. Can PAR be required per client in RFC 9126? How does global metadata differ from per-client metadata?
9. Why cannot `ClientSettings.Builder.requirePushedAuthorizationRequests(true)` be used in Spring Authorization Server 1.5.x?
10. Does `ClientSettings.setting("app.security.require_par", true)` enforce policy on its own? What additional component is needed?
11. Why must a filter inspect the original HTTP authorize request rather than only looking at already-resolved parameters?
12. When adding a new `AuthenticationProvider`, what bypass risk can occur?
13. Does PAR replace PKCE, consent, or OIDC `nonce`?
14. Why does a public client using PAR not automatically have a safe client secret?
15. When migrating a client from Legacy to Required, which tests must pass first?
16. If a client POSTs PAR on node A but authorization on node B fails, what should you check?

## 18. Official references

- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126): PAR protocol, `request_uri`, `expires_in`, global/per-client mandatory PAR, metadata, and security.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer` and `AuthorizationServerSettings` including the PAR path.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2PushedAuthorizationRequestEndpointConfigurer` and `OAuth2AuthorizationEndpointConfigurer`.
- [Spring Authorization Server 1.5.x — ClientSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): list of supported builder methods; no require-PAR setter in 1.5.x.
- [Spring Authorization Server 1.5.x — AbstractSettings.AbstractBuilder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AbstractSettings.AbstractBuilder.html): `setting(name, value)` method for application metadata.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): `OAuth2AuthorizationRequestResolver`, Authorization Code + PKCE, client request handling.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE still required alongside PAR.
- [RFC 9101 — JWT-Secured Authorization Request](https://www.rfc-editor.org/rfc/rfc9101): JAR can be combined with PAR in profiles requiring Request Objects.

**Takeaway:** An Authorization Server **having** `/oauth2/par` does not mean it **enforces PAR for any client**. With Spring Authorization Server 1.5.x, you can store an application flag in `ClientSettings` or a policy repository, yet you must **enforce it at the Authorization Endpoint**: Required clients missing a valid `request_uri` must be rejected with `invalid_request`. A guard only checks parameter presence; Spring must still verify that the reference was issued by the PAR Endpoint, matches the client, is unexpired, and has not been altered contrary to policy. Preserving PKCE, `state`, redirect URI validation, consent, and negative-path testing is essential for safely rolling out per-client PAR in a Spring Boot system.
