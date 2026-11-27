# 10.10. Handling Extension Fields in the Token Response

## 1. Context: Token Endpoint Returns More Than Standard OAuth 2.0 Fields

In a **Spring Security OAuth 2.0 OIDC Client** application, after the browser completes authentication/authorization at the identity provider, the backend uses the authorization code to call the **Token Endpoint**. A successful response includes not only an Access Token, but also potentially a Refresh Token, an ID Token (when using OpenID Connect), and provider-specific attributes.

For example, an Authorization Server returns:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "scope": "openid profile email api.read",
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token_expires_in": 86400,
  "ext_expires_in": 600,
  "session_state": "server-side-session-reference",
  "tenant_id": "company-a",
  "account_region": "ap-southeast-1"
}
~~~

This is an **illustrative** payload, not a valid token for real application use. A real provider may return fewer fields or use different names.

Common implementation scenarios:

1. Spring Security needs to read the **standard** fields to construct `OAuth2AccessTokenResponse`.
2. OIDC login needs to retain `id_token` to verify the user's identity.
3. Some systems need to read extra metadata such as `tenant_id` or Refresh Token expiration for business logic or monitoring.
4. A legacy provider may use a non-standard format (such as `expires_in_ms` instead of `expires_in`), causing the default converter to fail.
5. The application must handle extension fields **without breaking token verification, leaking secrets, or turning external metadata into trusted access rights**.

This lesson examines **the token response model, mapping into Spring Security, where to customize the token response converter, and how to use extension fields safely in a Servlet client**.

## 2. What Is a Token Response and Where Does It Fit in the Authorization Code Flow?

The Authorization Code flow distinguishes two messages: the response from the authorization endpoint arriving via the **browser**, and the response from the token endpoint arriving **directly at the backend**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Boot Servlet OAuth2 Client
    participant AS as OAuth2/OIDC Provider
    U->>C: GET /oauth2/authorization/company
    C-->>U: 302 authorization endpoint (state, PKCE...)
    U->>AS: Login / consent
    AS-->>U: 302 callback with authorization code + state
    U->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Restore authorization request and validate correlation
    C->>AS: POST token endpoint with code, client auth, PKCE verifier
    AS-->>C: JSON token response: standard + extension fields
    C->>C: Token response converter builds OAuth2AccessTokenResponse
    C->>C: Verify OIDC ID Token if openid scope
    C-->>U: Login session / success handler
~~~

**A token response is not an OAuth authorization callback.** An `error` parameter alongside `state` in the callback is handled as an authorization response; token endpoint errors may return HTTP 400 with JSON `error`/`error_description`. Never use the same parsing path for both a successful response and an error response.

Minimal token request illustrating the form body:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_VALUE&redirect_uri=...&code_verifier=...
~~~

Depending on client type, the request must also include **client authentication** such as `client_secret_basic` or `private_key_jwt`. Do not omit client authentication just because the snippet above omits all HTTP headers.

## 3. Standard Fields and Extension Fields Must Be Distinguished

### 3.1. Common OAuth 2.0 Token Response Fields

| Field | Role | How to Interpret During Processing |
| --- | --- | --- |
| `access_token` | Credential granting resource access | Mandatory for a successful Bearer token response |
| `token_type` | Token type, usually `Bearer` | Never assume every token type works like Bearer |
| `expires_in` | Access Token lifetime, in **seconds** | Must convert to valid seconds; never confuse with milliseconds |
| `refresh_token` | Token used to request a new token if issued | Optional; not returned by every flow |
| `scope` | Actual granted scopes, if present in the response | Typically a space-delimited string |

In OAuth 2.0, `expires_in` is recommended though not strictly mandatory in every response. If a provider omits it, the client needs an appropriate token lifecycle policy; never assume the Access Token lasts forever.

Example scope value:

~~~json
{
  "scope": "openid profile email api.read"
}
~~~

This is **a single string** of space-separated scopes, not a JSON array under standard token response syntax.

### 3.2. Field Added by OpenID Connect: `id_token`

In an **OIDC Authorization Code flow**, the token response also includes **`id_token`**:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile",
  "id_token": "HEADER.PAYLOAD.SIGNATURE"
}
~~~

`id_token` is an **OIDC-standardized** component, not an arbitrary vendor custom field. In Spring Security's generic `OAuth2AccessTokenResponse` API, it appears inside `additionalParameters` because it is not a core property of the OAuth 2.0 Access Token response model.

**Never strip `id_token` when customizing a converter.** Spring Security needs it for OIDC authentication; missing an ID Token in a valid OIDC response or dropping it during conversion causes login to fail.

Nor does an ID Token **become trustworthy** merely by sitting in `additionalParameters`. The OIDC client must still verify signature, issuer, audience, timestamps, and transaction bindings such as `nonce` when applicable.

### 3.3. Provider-Specific Extension Fields

The following names are **examples** seen in specific systems; they must not be treated as a mandatory OAuth 2.0/OIDC field set:

| Illustrative Field | Possible Meaning | Notes |
| --- | --- | --- |
| `refresh_token_expires_in` | Refresh Token expiration in seconds | Exact semantics and calculation defined by provider |
| `ext_expires_in` | Extended lifetime under a custom policy | Not synonymous with standard Access Token validity |
| `session_state` | IdP session-related metadata | Does not replace the application's HTTP session |
| `tenant_id` | Provider's tenant identifier | Use only after cross-checking against trusted issuer/identity |
| `account_region` | Data/account processing region | Business metadata, not an API permission |
| `not-before-policy` | Custom timestamp policy | Requires an explicit provider contract |
| `issued_token_type` | Issued token type in extended grants such as token exchange | Interpret strictly per the matching grant spec |
| `custom_claims` | Extended metadata as an object | Never trust by default to assign roles |

**The same field name can have different semantics across providers.** Use it only when provider documentation specifies its data type, unit, applicability, lifecycle, and security responsibilities.

### 3.4. Which Fields Affect Authentication?

| Data | Proof of OIDC Login? | Used to Call APIs? |
| --- | --- | --- |
| `id_token` | Yes, **after OIDC verification** | Never use in place of an Access Token |
| `access_token` | Does not by itself prove OIDC login | Yes, toward the Resource Server it was issued for |
| `refresh_token` | No | Never send to APIs; used only with the token endpoint per flow |
| `session_state` | No | No |
| `tenant_id` | Not sufficient alone as trusted identity | Does not grant scopes/roles |
| `refresh_token_expires_in` | No | No; informs lifecycle management if contracted |

Key principle: **metadata returned alongside an Access Token is not automatically signed, verified, or at the same trust level as an ID Token.** TLS on the token endpoint protects transit, yet the application must still decide which data is allowed to drive business decisions.

## 4. How Does Spring Security Represent a Token Response?

In Spring Security OAuth2 Client, the central type after successful conversion is:

~~~java
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
~~~

Commonly used methods:

~~~java
OAuth2AccessTokenResponse response = /* result from token client */;

String tokenValue = response.getAccessToken().getTokenValue();
Set<String> grantedScopes = response.getAccessToken().getScopes();
Instant expiresAt = response.getAccessToken().getExpiresAt();

OAuth2RefreshToken refreshToken = response.getRefreshToken();
Map<String, Object> extras = response.getAdditionalParameters();
~~~

The snippet above explains how to read values; import `java.time.Instant`, `java.util.Map`, `java.util.Set`, and `OAuth2RefreshToken` in real code.

### 4.1. What Is `additionalParameters`?

`OAuth2AccessTokenResponse.getAdditionalParameters()` holds a field-name-to-value map retained by the converter outside the core response attributes:

~~~java
Map<String, Object> extras = response.getAdditionalParameters();

Object idToken = extras.get("id_token");
Object refreshExpires = extras.get("refresh_token_expires_in");
Object sessionState = extras.get("session_state");
Object tenantId = extras.get("tenant_id");
~~~

With a proper converter, the map may contain:

~~~text
additionalParameters
  id_token: "HEADER.PAYLOAD.SIGNATURE"
  refresh_token_expires_in: 86400
  ext_expires_in: 600
  session_state: "..."
  tenant_id: "company-a"
  account_region: "ap-southeast-1"
~~~

**Never assume a field is always present** or always a `String`. JSON numbers may stay numeric types; objects/arrays may be `Map`/`List`. Check types before converting.

### 4.2. Is `additionalParameters` Where Spring Stores Tokens Forever?

No. Distinguish three lifecycles:

~~~text
HTTP token response from Authorization Server
            |
            v
OAuth2AccessTokenResponse
  accessToken, refreshToken, additionalParameters
            |
            v
OAuth2/OIDC Authentication flow
  ID Token consumed during OIDC login
            |
            v
OAuth2AuthorizedClient
  clientRegistration, principalName, accessToken, refreshToken
~~~

`OAuth2AuthorizedClient` retrieves the Access Token/Refresh Token for a registration and principal. That API **does not expose the entire `additionalParameters` map** from the token response by default.

If the application needs `tenant_id` or `refresh_token_expires_in` after login finishes, design a dedicated, secure, scoped storage channel (such as session metadata or an integration store) rather than assuming `OAuth2AuthorizedClientRepository` keeps every extension field.

### 4.3. Extension Fields Differ from JWT Claims

Do not equate them:

~~~text
Token response JSON:
{
  "access_token": "eyJ...",
  "tenant_id": "company-a"
}

Payload inside the Access Token if it is a JWT:
{
  "iss": "...",
  "aud": "...",
  "scope": "api.read",
  "tenant": "company-a"
}
~~~

`tenant_id` is metadata in the **response body**; `tenant` is a claim inside a token (if the token happens to be a JWT). They do not automatically share the same trust level, do not have to match, and never replace Resource Server validation of the Access Token.

In particular, an Access Token **can be an opaque string**. The Client does not need to parse tokens manually to handle extension fields in the response.

## 5. HTTP Response Conversion Flow in Spring Security Servlet

When `oauth2Login()` runs the Authorization Code flow:

~~~mermaid
flowchart TD
    A["Token Endpoint HTTP response"] --> B["HTTP message converter reads JSON -> Map"]
    B --> C{"Standard fields formatted properly?"}
    C -->|Yes| D["OAuth2AccessTokenResponse"]
    C -->|Needs provider adaptation| E["Custom map-to-token-response converter"]
    E --> D
    C -->|Invalid| F["Token response error / authentication failure"]
    D --> G["Access Token and Refresh Token"]
    D --> H["AdditionalParameters"]
    H --> I["ID Token processed by OIDC login"]
    H --> J["Provider metadata read by app if needed"]
    G --> K["OAuth2AuthorizedClient"]
    I --> L["OIDC principal after verification"]
~~~

In Spring Security 6.x, commonly referenced extension points include:

| Component | Responsibility |
| --- | --- |
| `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` | Sends token request and receives response after Authorization Code grant |
| `OAuth2AccessTokenResponseHttpMessageConverter` | Converts HTTP token response into `OAuth2AccessTokenResponse` |
| `Converter<Map<String, Object>, OAuth2AccessTokenResponse>` | Customizes mapping from parsed response map to object |
| `DefaultAuthorizationCodeTokenResponseClient` | `RestTemplate`-based token response client in Spring Security 6.x branches |
| `RestClientAuthorizationCodeTokenResponseClient` | `RestClient`-based token response client in newer supported Spring Security versions |
| `HttpSecurity.oauth2Login().tokenEndpoint()` | Configuration hook for Servlet OAuth2 Login's token response client |

**Pick the right API for your project's Spring Security version.** Class/method names and deprecation status differ across Spring Security 6.x, 7.x, and point releases. Never paste both `RestTemplate` and `RestClient` stacks into the same app just because both appear in documentation.

The examples below illustrate **mapping a map to a response and Spring Security 6.x `RestTemplate`-style integration**. On newer versions, keep the exact same extension-field principles while using the token response client recommended by that version.

## 6. If Defaults Already Retain Extension Fields, Do You Need a Custom Converter?

**Not always.** When a provider returns standard OAuth 2.0 JSON for the core fields, Spring Security's default converter builds `OAuth2AccessTokenResponse` and keeps extra fields in `additionalParameters`.

Example:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "api.read",
  "tenant_id": "company-a",
  "refresh_token_expires_in": 86400
}
~~~

With a standard payload like this, the default converter usually suffices—no custom code is needed just to receive `tenant_id`. Customize only for a clear reason, such as:

- The provider returns lifetime in `expires_in_ms` without `expires_in`.
- The provider returns `scope` as a non-standard array that must be normalized to an OAuth 2.0 string.
- The provider uses non-standard field names under an explicit integration contract.
- Custom data policy validation or rejecting an unsupported token response shape is needed.

**Never write a custom converter just to log the entire token response.** Doing so can accidentally log Access Tokens, Refresh Tokens, ID Tokens, and sensitive metadata.

## 7. Customizing the Converter: Preserve Standard Fields and Metadata

Suppose a legacy provider has a special contract:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in_ms": 300000,
  "scope": "api.read",
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token_expires_in": 86400,
  "tenant_id": "company-a"
}
~~~

`expires_in_ms` is not a standard OAuth 2.0 field name, whereas `expires_in` uses **seconds**. We will write a converter that converts `expires_in_ms` to seconds only when `expires_in` is absent, builds the response, and **keeps every field outside the standard core fields**.

### 7.1. A Self-Contained Illustrative Converter

~~~java
package com.example.security.oauth2;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

public final class VendorTokenResponseConverter
        implements Converter<Map<String, Object>, OAuth2AccessTokenResponse> {

    @Override
    public OAuth2AccessTokenResponse convert(Map<String, Object> body) {
        if (body == null) {
            throw invalidResponse("Token response body is missing");
        }

        String accessToken = requireText(body, "access_token");
        String tokenType = requireText(body, "token_type");
        if (!"Bearer".equalsIgnoreCase(tokenType)) {
            throw invalidResponse("Only token_type=Bearer is supported");
        }

        long expiresIn = parseExpirySeconds(body);
        Set<String> scopes = parseScopes(body.get("scope"));

        OAuth2AccessTokenResponse.Builder builder =
            OAuth2AccessTokenResponse.withToken(accessToken)
                .tokenType(OAuth2AccessToken.TokenType.BEARER)
                .expiresIn(expiresIn)
                .scopes(scopes);

        Object refresh = body.get("refresh_token");
        if (refresh instanceof String value && !value.isBlank()) {
            builder.refreshToken(value);
        }

        // Remove only fields already mapped to the core model.
        // id_token and vendor metadata must be preserved.
        Map<String, Object> extras = new LinkedHashMap<>(body);
        extras.remove("access_token");
        extras.remove("token_type");
        extras.remove("expires_in");
        extras.remove("refresh_token");
        extras.remove("scope");

        return builder.additionalParameters(extras).build();
    }

    private static long parseExpirySeconds(Map<String, Object> body) {
        Object seconds = body.get("expires_in");
        if (seconds != null) {
            return positiveLong(seconds, "expires_in");
        }

        Object millis = body.get("expires_in_ms");
        if (millis != null) {
            long value = positiveLong(millis, "expires_in_ms");
            long secondsValue = value / 1000L;
            if (secondsValue < 1) {
                throw invalidResponse("expires_in_ms must be >= 1000");
            }
            return secondsValue;
        }

        // Example strict policy because this provider guarantees a TTL.
        throw invalidResponse("Missing token lifetime per provider contract");
    }

    private static long positiveLong(Object raw, String field) {
        try {
            long result = Long.parseLong(raw.toString());
            if (result <= 0) {
                throw new NumberFormatException("non-positive");
            }
            return result;
        } catch (NumberFormatException ex) {
            throw invalidResponse("Invalid value for " + field);
        }
    }

    private static Set<String> parseScopes(Object raw) {
        if (raw == null) {
            return Collections.emptySet();
        }
        if (!(raw instanceof String scopeString)) {
            throw invalidResponse("scope must be a space-delimited string");
        }
        return Arrays.stream(scopeString.trim().split("\\s+"))
            .filter(value -> !value.isEmpty())
            .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private static String requireText(
            Map<String, Object> body, String field) {
        Object raw = body.get(field);
        if (!(raw instanceof String text) || text.isBlank()) {
            throw invalidResponse("Missing required field: " + field);
        }
        return text;
    }

    private static OAuth2AuthenticationException invalidResponse(
            String reason) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token_response", reason, null));
    }
}
~~~

This snippet uses Java 17 syntax (`instanceof` pattern matching), fitting most Spring Boot 3.x projects. It is a **converter tailored for one specific provider contract**, not a general replacement for Spring Security's default converter across all cases.

Intentional design choices:

1. **`access_token` and `token_type` required:** because the example app supports only Bearer Access Tokens.
2. **`expires_in` takes priority:** if the provider returns the standard field, keep seconds untouched.
3. **`expires_in_ms` is strictly an agreed fallback:** convert milliseconds to seconds; never mistake `300000 ms` for `300000 s`.
4. **`scope` follows OAuth 2.0 format:** space-delimited string.
5. **`refresh_token` is optional:** omit Refresh Token if absent.
6. **`extras` preserves `id_token` and vendor metadata:** avoids losing required OIDC data.
7. **Exceptions never contain token values:** error messages mention only field names/error types, never credentials.

If a provider validly omits `expires_in` per OAuth 2.0, this strict converter **does not apply verbatim**. Design a lifetime policy matching the provider contract rather than inventing an arbitrary TTL and treating it as guaranteed.

### 7.2. Why Not Use `Map<String, String>` for Everything?

JSON responses can contain numbers and objects:

~~~json
{
  "expires_in": 300,
  "refresh_token_expires_in": 86400,
  "tenant": {
    "id": "company-a",
    "region": "ap-southeast-1"
  },
  "features": ["reports", "directory"]
}
~~~

`Map<String, Object>` preserves those types, whereas forcing everything to `String` breaks structure or causes `ClassCastException`. For extension fields, check types per contract:

~~~java
Object raw = response.getAdditionalParameters().get("tenant_id");
if (raw instanceof String tenantId && !tenantId.isBlank()) {
    // Use only after matching tenant against trusted application config.
}
~~~

For large integers, never cast blindly to `Integer` if values can exceed 32-bit range. For durations in seconds, parse numeric types explicitly and enforce reasonable bounds.

## 8. Wiring the Converter into Servlet OAuth2 Login's Token Endpoint

In Spring Security **6.x using `DefaultAuthorizationCodeTokenResponseClient`**, you can swap the message converter on the `RestTemplate` calling the token endpoint:

~~~java
package com.example.security.oauth2;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.DefaultAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.client.RestTemplate;

@Configuration
public class TokenEndpointConfig {

    @Bean
    OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            customAuthorizationCodeTokenClient() {

        OAuth2AccessTokenResponseHttpMessageConverter converter =
            new OAuth2AccessTokenResponseHttpMessageConverter();
        converter.setAccessTokenResponseConverter(
            new VendorTokenResponseConverter());

        RestTemplate restTemplate = new RestTemplate(
            List.of(new FormHttpMessageConverter(), converter));

        // Preserve OAuth 2.0 Token Endpoint error response handling.
        restTemplate.setErrorHandler(new OAuth2ErrorResponseErrorHandler());

        DefaultAuthorizationCodeTokenResponseClient client =
            new DefaultAuthorizationCodeTokenResponseClient();
        client.setRestOperations(restTemplate);
        return client;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
                customAuthorizationCodeTokenClient) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(
                        customAuthorizationCodeTokenClient)))
            .build();
    }
}
~~~

**Version boundary:** the sample above shows the `RestTemplate`-style token client API of Spring Security 6.x. In newer versions featuring `RestClientAuthorizationCodeTokenResponseClient`, use that token client's response converter configuration API instead of creating a `RestTemplate` just to follow an older example. Some older classes are deprecated or replaced across branches; never apply code without checking the docs for your Spring Security version.

**Do not attach a custom token client blindly to every registration.** Configuring `oauth2Login().tokenEndpoint()` above can affect all logins handled by that `SecurityFilterChain`. If your app has multiple providers and only one returns legacy fields, branch accurately per provider contract or isolate separate token clients—never force `expires_in_ms` logic onto standard providers.

### 8.1. Why Must `OAuth2ErrorResponseErrorHandler` Be Preserved?

The token endpoint can return HTTP 400:

~~~json
{
  "error": "invalid_grant",
  "error_description": "Authorization code is invalid or expired"
}
~~~

This is an **OAuth2 error response**, not a successful token response. If you customize `RestTemplate` and omit a proper error handler, the application may throw hard-to-classify exceptions or attempt to parse the error JSON as a token object, producing misleading messages and difficult debugging.

Never forward raw `error_description` values from a provider to the browser or log full response bodies, as external payloads may contain sensitive information.

### 8.2. Placing the Extension Point Correctly in Spring Security

~~~text
oauth2Login()
  .tokenEndpoint(...)
    .accessTokenResponseClient(...)
      -> POST Authorization Code to Token Endpoint
      -> Handle success and error responses
      -> OAuth2AccessTokenResponse (extras intact)
    -> OIDC validation and Authentication
~~~

Do not modify `OAuth2UserService` just to convert `expires_in_ms`: the user service loads and maps user details after token exchange has already completed. Token response parsing errors belong in the **token response client/converter**, right where data enters the framework.

Conversely, mapping a UserInfo claim to a display name belongs in the user service or application mapper, **not** in the token response converter.

## 9. Does Extension Data Survive After Authorization Code Login?

Once the converter returns `OAuth2AccessTokenResponse`:

- The framework uses the Access Token and Refresh Token for `OAuth2AuthorizedClient`.
- For OIDC, `id_token` is processed by the OIDC authentication pipeline.
- Fields like `tenant_id` or `refresh_token_expires_in` can be read at **the point where the token response is handled**.
- However, `OAuth2AuthorizedClient` does not persist all `additionalParameters` by default for later retrieval.

Design question: **if you want to display `refresh_token_expires_in` on a connection management page hours later, where should it be stored?**

Consider these options:

| Approach | When Appropriate | Safety Conditions |
| --- | --- | --- |
| Do not store; consume immediately on arrival | Field only guides an immediate decision or metric | Never log tokens; read only needed metadata |
| Store normalized metadata in server-side session | Needed only for the current web session | Bind to user and registration, enforce TTL, clear on logout |
| Store in a backend integration table | Need to track connection lifecycle beyond a session | Encrypt/control access, key by user/provider, delete on disconnect |
| Avoid vendor fields; rely on standard APIs | Provider does not guarantee field stability | Minimize coupling |

If you need to **pass metadata from the token response to a business service**, design a clean hook to inspect and process the response when the token client receives it. Never try to recover a lost parameter map by parsing raw tokens off the authorized client.

**Never dump the entire `additionalParameters` map straight into a database.** That map may contain `id_token` and other sensitive attributes; extract, validate, and store only the minimal fields required by policy.

## 10. Token Response on Refresh: Not Identical to the First Exchange

A common mistake is inspecting extension fields only on the **Authorization Code token response** and assuming they appear on every refresh.

When the Access Token expires, the OAuth2 Client may send:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
~~~

Actual requests also include client authentication and any provider-required parameters. The response might look like:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "api.read",
  "refresh_token": "NEW_REFRESH_TOKEN_VALUE",
  "refresh_token_expires_in": 72000
}
~~~

Points to understand:

1. The Authorization Server **may** rotate Refresh Tokens; if a new one is returned, the client must store it per framework management.
2. Some providers **omit Refresh Tokens** on some refresh calls; do not interpret absence as revoking the existing token if your library/token manager retains the prior token by rule.
3. **Do not assume `id_token` appears in refresh responses.** Any OIDC rules for refresh responses containing ID Tokens still apply when present.
4. Extension fields like `refresh_token_expires_in` may be updated, omitted, or change meaning across grants.
5. **Customizing the Authorization Code token client does not automatically apply to the Refresh Token grant.** In Spring Security, configure the corresponding refresh token response client / authorized client provider if refresh flows must handle extension fields too.

### 10.1. When Do You Need Custom Refresh Handling?

Suppose a provider emits `expires_in_ms` on both initial and refresh token responses. If the initial converter handles it properly while refresh still uses a default converter that ignores `expires_in_ms`, token lifecycle tracking or refreshes will break.

Therefore, when customizing response formats, identify **every grant the application actually uses**:

| Grant / Flow | Needs Token Response Handling? | Configuration Point |
| --- | --- | --- |
| Authorization Code / OIDC Login | Yes | `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)` |
| Refresh Token | Yes, if the client refreshes tokens | Token response client on the refresh provider / authorized client manager |
| Client Credentials | Yes, for backend service clients | Authorized client provider for Client Credentials |
| Token Exchange | Yes, if integrating extended grants | Token client/provider matching the grant and token exchange spec |

Never assume a converter wired for authorization code handles every token request in the app. Map out the entire refresh/re-issuance architecture.

## 11. Mistakes Related to Expiration and Scope

### 11.1. `expires_in` Is in Seconds, Not Milliseconds

Example:

~~~text
expires_in = 300       -> 300 seconds = 5 minutes
expires_in_ms = 300000 -> 300000 milliseconds = 5 minutes (per vendor contract)
~~~

If `expires_in_ms=300000` is misread as **seconds**, the app thinks the token lasts roughly 1,000 times longer than reality. API calls keep sending an expired token, triggering repeated 401s.

Conversely, reading `expires_in=300` as milliseconds marks the token expired almost immediately, causing excessive refreshes. Normalize units **before constructing `OAuth2AccessTokenResponse`**.

### 11.2. Refresh Tokens Do Not Share Default Expiration with Access Tokens

`expires_in` describes the Access Token. `refresh_token_expires_in` (if present) may describe the Refresh Token, yet you must read provider docs to know when it starts counting, whether sliding expiration applies, and whether revocation policies can shorten it.

Never pass `refresh_token_expires_in` into `OAuth2AccessTokenResponse.Builder.expiresIn(...)`. Doing so corrupts the Access Token lifecycle.

### 11.3. Never Grant Extra Scopes from Metadata

Example token response:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read",
  "tenant_id": "company-a",
  "role_hint": "admin"
}
~~~

Never treat `role_hint=admin` in the response as approved administrative rights. The Resource Server must validate the token, audience, scopes, and API policies; internal roles require dedicated mapping/synchronization.

If `scope` is omitted from the token response, OAuth 2.0 defines how granted scopes relate to requested scopes. Never assume "no `scope` field means all permissions"; follow protocol rules and how Spring Security/the provider represent scopes.

### 11.4. `issued_token_type` in Token Exchange

In OAuth 2.0 Token Exchange (RFC 8693), `issued_token_type` has grant-specific meaning, such as the type of token returned. Never equate it with `token_type`:

| Field | Question Answered |
| --- | --- |
| `token_type` | How does the client present the token to the resource server? e.g., `Bearer` |
| `issued_token_type` | Which token type was issued per the token exchange protocol? e.g., a token-type identifier URI |

Only support token exchange when both the authorization server and Spring Security client are configured properly; never see `issued_token_type` and manually alter `OAuth2AccessToken` types or skip audience/token-purpose checks.

## 12. Security When Handling Extension Fields

### 12.1. Maintain Proper Trust Boundaries

Response fields arrive from a **trusted configured** token endpoint, yet they do not replace client-side security checks. A `tenant_id` or `roles` string in JSON carries no standard OAuth 2.0 semantics forcing a resource server to accept it.

Principles:

- The token endpoint URL must come from configuration/discovery for a **trusted issuer**, never from unchecked input.
- Use HTTPS and verify TLS certificates. Never disable server identity verification on connection errors.
- For OIDC, keep `id_token` intact and let **OIDC validation** verify signature, issuer, audience, expiration, and bindings.
- Send Access Tokens **only to appropriate resource servers**; never reuse an ID Token as an Access Token.
- If extension metadata influences permissions, verify issuer, tenant mapping, and internal policy. Never grant privileges simply because a provider sent a string looking like `admin`.
- When a field changes type or is missing, fail safely or apply a contracted fallback—never default to overly broad access.

### 12.2. Never Log Full Token Responses

Avoid:

~~~java
// Do not use in production:
logger.info("token response: {}", response);
logger.info("extra params: {}", response.getAdditionalParameters());
~~~

Because `additionalParameters` may contain an **ID Token** or sensitive personal data. The full `OAuth2AccessTokenResponse` also holds the Access Token and possibly a Refresh Token.

Instead, log only safe metadata:

~~~text
event=oauth_token_response_received
registration=company
grant=authorization_code
has_id_token=true
has_refresh_token=true
extension_fields_count=3
correlation_id=internal-safe-reference
~~~

This is a suggested log format, not default framework output. `correlation_id` should be independent of authorization codes, Access Tokens, Refresh Tokens, PKCE verifiers, and session cookies.

### 12.3. Never Turn Arbitrary Values into Redirect URLs

If a provider returns extension fields like `next_url`, `redirect`, or `login_hint`, never use them directly as a browser redirect URL. Extension metadata can be abused if the app turns it into an open redirect. Rely on application-controlled route allowlists and let Spring Security login success/failure handlers drive navigation.

### 12.4. Bound Size and Data Types

A token response can include long JSON extensions, nested objects, or large lists. When persisting partial metadata, enforce size, depth, and TTL limits, accepting only known fields. Never copy the raw extension map into sessions, cookies, logs, or databases simply because the converter preserves it.

## 13. Common Errors and How to Analyze Them

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Token endpoint succeeds yet Spring fails to parse response | Non-standard `token_type`, `access_token`, or `expires_in` type | Compare a **token-redacted** payload with the RFC/provider contract; normalize only the necessary exception |
| OIDC login reports missing ID Token | Custom converter stripped `id_token` from additional parameters | Preserve `id_token` when building `OAuth2AccessTokenResponse` |
| OIDC ID Token has invalid issuer/signature/audience | Invalid token or wrong provider/registration | Never disable validation; fix issuer, JWKS, audience, and provider config |
| Token expired yet app thinks it is still valid | `expires_in_ms` was read as seconds | Normalize units before building the response |
| Access Token refreshes constantly | `expires_in` treated as milliseconds or returned near zero | Verify contract and TTL conversion |
| `tenant_id` exists in response yet unreadable after login | `OAuth2AuthorizedClient` does not store raw `additionalParameters` | Design controlled extraction/persistence when the token response arrives |
| Initial login works yet refresh fails | Customized only Authorization Code converter; refresh still uses default | Configure the refresh token client/provider if needed |
| API returns 403 despite `role_hint=admin` | Vendor field is not equivalent to API-enforced scopes/roles | Configure proper token audience/scopes and API policies |
| Provider returns `scope` as an array | Format deviates from standard OAuth2 token response | Ask provider to fix or handle with a contracted custom converter |
| Numeric field throws `ClassCastException` | Casting `Long` to `Integer` or JSON number to `String` | Check `Number`/`String`; parse units and ranges explicitly |
| Custom converter exception contains raw tokens | Throwing/logging raw response map | Replace with error codes and non-sensitive field names |
| Converter wired yet never seems to run | Wrong security chain or wrong token client wired | Check `oauth2Login().tokenEndpoint()` on the Servlet chain handling the callback |
| Provider returns `invalid_grant` from token endpoint | Invalid/expired authorization code, PKCE, or redirect URI mismatch | Handle as an OAuth error response; do not parse as a successful token |

### 13.1. Distinguishing Mapping Errors from Real Token Errors

These two errors have completely different causes:

~~~text
Mapping error:
  Token response has expires_in_ms per contract
  -> current converter only understands expires_in
  -> normalize the field before creating the response

Invalid token:
  Token response has id_token
  -> signature, issuer, aud, nonce, or exp is invalid
  -> OIDC login must reject; fix configuration/issuer/token
~~~

**Never use a custom converter to "patch up" an invalid ID Token.** A converter only shapes token response data representation; OIDC identity verification is a separate security boundary whose rules must never be skipped.

## 14. Example: Using Metadata Safely in Business Logic

Suppose a multi-tenant system needs to know which tenant a user belongs to in order to render the right UI after login. The provider returns `tenant_id` at the token endpoint.

A sound design:

1. **Normalize response:** converter keeps `tenant_id` in `additionalParameters`.
2. **Read field at token receipt:** verify it is a properly formatted string within size bounds.
3. **Cross-check verified identity:** use `iss`/`sub` from the OIDC ID Token alongside a trusted tenant mapping.
4. **Persist minimal metadata only:** e.g., an internal tenant ID mapped after verification, without storing Access Tokens or ID Tokens inside metadata fields.
5. **Authorize separately:** reading/writing tenant data must still be checked by the application or API; `tenant_id` does not replace authorization policies.

~~~mermaid
flowchart TD
    A["Token response has tenant_id and id_token"] --> B["Response converter preserves additionalParameters"]
    B --> C["OIDC client verifies ID Token"]
    C --> D{"iss + sub identity valid?"}
    D -->|No| E["Reject login"]
    D -->|Yes| F["Match tenant_id against trusted mapping"]
    F --> G{"Tenant allowed?"}
    G -->|No| H["Deny linking or restrict access"]
    G -->|Yes| I["Save minimal tenant metadata"]
    I --> J["API enforces policy on each resource"]
~~~

With a pure OAuth2 provider that does not issue an ID Token, obtain the account identifier from a trusted profile API per the provider contract and account-linking policy; never assume `tenant_id` in the response authenticates the user by itself.

## 15. Practice Scenarios

### Scenario A: Extension Field Does Not Affect Standard Parsing

Provider returns `access_token`, `token_type=Bearer`, `expires_in=300`, and `tenant_id`.

**Approach:** prefer the default converter. `tenant_id` can remain in `additionalParameters`; only add logic if business features truly need it.

### Scenario B: `expires_in_ms` Replaces `expires_in`

Provider returns `expires_in_ms=300000`.

**Approach:** only if this is a confirmed contract, convert to `300` seconds via a converter; handle negative, zero, overflow, or invalid types. Never alter token contents or invent an infinite expiration.

### Scenario C: OIDC Includes `id_token` Yet Custom Converter Drops It

The app strips every field outside the five basic OAuth 2.0 fields, causing `id_token` to vanish.

**Result:** OIDC login can fail. Preserve `id_token` inside `additionalParameters` so the framework can verify it per OIDC.

### Scenario D: Refresh Response Differs from Initial Response

Initial login returns `expires_in=300`, while refresh returns `expires_in_ms=300000`.

**Approach:** locate the separate token response client used for refreshes. Changing only the converter on `oauth2Login().tokenEndpoint()` may miss the refresh path.

### Scenario E: Metadata Hints at Admin Role

The provider returns `role_hint=admin` in the token response JSON, yet the Access Token lacks the required API scope.

**Conclusion:** never grant admin permissions or alter scopes on the client. Establish a trusted authorization source and enforce policies at the Resource Server/application.

### Scenario F: Token Response Contains Numeric Field as String

Provider returns `"refresh_token_expires_in": "86400"` instead of a JSON number.

**Approach:** parse it only if needed by the app and documented by the provider; use explicit number/string validation. Never cast directly to `Long` or treat it as the Access Token's `expires_in`.

### Scenario G: Extension Field Needed Hours Later

The app needs `tenant_id` when the user revisits a connection management page, when only `OAuth2AuthorizedClient` remains.

**Approach:** add a dedicated extraction/persistence step for validated metadata when the token response arrives, with TTL and user/provider bindings. Do not expect `OAuth2AuthorizedClient` to carry all `additionalParameters`.

### Scenario H: Token Endpoint Returns Error JSON

Provider returns HTTP 400 with `error=invalid_grant`, `error_description`.

**Approach:** process via the OAuth2 error handler; never feed error JSON into the success response converter or show raw error descriptions to the browser.

## 16. References

- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — OAuth2AccessTokenResponse Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/endpoint/OAuth2AccessTokenResponse.html
- Spring Security — OAuth2AccessTokenResponseHttpMessageConverter Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/http/converter/OAuth2AccessTokenResponseHttpMessageConverter.html
- OAuth 2.0 Authorization Framework, Section 5.1 — Successful Response: https://www.rfc-editor.org/rfc/rfc6749#section-5.1
- OAuth 2.0 Authorization Framework, Section 5.2 — Error Response: https://www.rfc-editor.org/rfc/rfc6749#section-5.2
- OpenID Connect Core 1.0 — Token Response: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Token Exchange (RFC 8693): https://www.rfc-editor.org/rfc/rfc8693

## 17. Conclusion

A token endpoint response may carry **standard OAuth 2.0 fields**, **OIDC's `id_token`**, and **provider-defined extension metadata**. In Spring Security, `OAuth2AccessTokenResponse` is the central object, while `additionalParameters` retains fields outside the core model.

~~~text
Token Endpoint JSON
  |
  +-- Standard fields
  |     access_token, token_type, expires_in, refresh_token, scope
  |     -> OAuth2AccessTokenResponse: AccessToken / RefreshToken
  |
  +-- OIDC ID Token
  |     id_token
  |     -> additionalParameters
  |     -> OIDC login validation
  |
  +-- Provider-specific metadata
        refresh_token_expires_in, session_state, tenant_id, ...
        -> additionalParameters
        -> extract, validate, and store only when genuinely needed
~~~

**Implementation priority:** use the default converter whenever responses are standard; customize only what is necessary when a provider has an explicit exception contract; always preserve `id_token` for OIDC as well as PKCE and token lifecycle semantics; and never promote extension fields into verified access permissions. Finally, remember that **Authorization Code, Refresh Token, and other grants can use distinct token response clients**, so verify the exact extension point before applying a converter.
