# 10.12. Converting `OAuth2Error` and Handling Non-Standard Responses

## 1. Where Error Handling Fits at the Token Endpoint

In a **Spring Security OAuth 2.0/OIDC Client**, after the user is redirected back to the callback with a valid authorization code, the Client sends a request to the Authorization Server's **Token Endpoint** to exchange the code for tokens. For other grants, such as client credentials or refresh token, the Token Endpoint is likewise where token issuance or renewal requests are handled.

Most introductory Token Endpoint examples illustrate the success case:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "scope": "openid profile",
  "id_token": "ID_TOKEN_VALUE"
}
~~~

This response is only a structural example; token strings are placeholders. Depending on the grant, scope, Client, and provider, the token response may omit a refresh token or ID Token. In the OIDC Authorization Code Flow, the ID Token also undergoes dedicated validation once issued.

In practice, the Token Endpoint may also return standard OAuth 2.0 errors, provider-specific JSON error payloads, HTML error pages from reverse proxies/WAFs, HTTP 200 with an error body, malformed JSON, or connection errors before any response arrives. When that happens, the application must:

1. **Detect the failure** at the HTTP or protocol layer.
2. **Translate the error into a consistent representation** that Spring Security components can process.
3. **Never mistake an error for a valid token response.**
4. **Never expose** authorization codes, client secrets, access tokens, refresh tokens, or sensitive provider details in logs or browser responses.
5. **Preserve essential error semantics** so operations can diagnose and fix the actual root cause.

Spring Security's core value object for this is **<code>OAuth2Error</code>**. This lesson focuses on how to represent, convert, and safely handle non-standard responses at the Token Endpoint in an **OAuth2/OIDC Client** application, particularly with Servlet OAuth2 Login.

## 2. Standard OAuth 2.0 Errors at the Token Endpoint

### 2.1. Error Structure per RFC 6749

RFC 6749, Section 5.2, defines a Token Endpoint error response with these fields:

| Field | Required? | Contents |
|---|---|---|
| <code>error</code> | Yes | String error code, such as <code>invalid_grant</code> |
| <code>error_description</code> | No | Human-readable text to aid error diagnosis |
| <code>error_uri</code> | No | URI linking to error documentation |

Example error when an authorization code has expired:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "Authorization code is expired or invalid"
}
~~~

Core Token Endpoint error codes:

| Error Code | Common Meaning | Where to Investigate |
|---|---|---|
| <code>invalid_request</code> | Missing parameter, duplicate parameter, malformed syntax, or invalid request | Check form encoding, <code>grant_type</code>, required parameters |
| <code>invalid_client</code> | Client authentication failed or Client is unrecognized | Check client ID, secret, auth method, signing key if using private-key JWT |
| <code>invalid_grant</code> | Grant/code/refresh token is invalid, expired, revoked, already used, or failed binding checks | Check code lifecycle, redirect URI, PKCE, Client binding, refresh token |
| <code>unauthorized_client</code> | Client is not permitted to use the requested grant type | Check registration and Authorization Server policies |
| <code>unsupported_grant_type</code> | Token Endpoint does not support the requested grant type | Check <code>grant_type</code>, provider configuration, and protocol |
| <code>invalid_scope</code> | Scope is invalid, disallowed, or unsuitable for the grant | Check scopes and Client permissions |

**Never assume a single cause from one error code.** For example, <code>invalid_grant</code> can occur because an authorization code was used twice, a PKCE verifier was wrong, or the redirect URI mismatched. Nor does it imply whether the user's session is authenticated; state/callback checks happen before the Token Endpoint.

The Token Endpoint typically returns **HTTP 400** for invalid grant requests. For **<code>invalid_client</code>**, the server may return **HTTP 401**; if the Client used an HTTP <code>Authorization</code> header to authenticate, RFC 6749 requires a 401 response with a matching <code>WWW-Authenticate</code> header. Therefore, do not write logic assuming only HTTP 400 represents an OAuth 2.0 error.

### 2.2. HTTP Errors and OAuth Errors Are Two Distinct Pieces of Information

**HTTP status** describes the outcome at the HTTP layer. **OAuth error code** describes the protocol/business condition reported by the Authorization Server.

Example:

~~~text
HTTP status: 400
OAuth error: invalid_grant
Suspected cause: expired code, wrong PKCE, mismatched redirect URI...
~~~

These two fields relate to each other yet **do not replace one another**. An HTTP 502 from a gateway may contain no OAuth error code at all. Conversely, a misbehaving provider might return <code>{"error":"invalid_grant"}</code> with HTTP 200; the body still signals failure and must never be treated as a successful token response.

In operational design, retain the HTTP status separately in telemetry/exception context when needed, while <code>OAuth2Error</code> represents the normalized protocol error.

## 3. `OAuth2Error` and Exceptions in Spring Security

### 3.1. The `OAuth2Error` Class

Spring Security defines:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_grant",
    "Authorization code could not be redeemed",
    null
);
~~~

The three constructor arguments are:

1. <code>errorCode</code>: error code, e.g., <code>invalid_grant</code>.
2. <code>description</code>: descriptive message, which may be <code>null</code>.
3. <code>uri</code>: link to error documentation, which may be <code>null</code>.

<code>OAuth2Error</code> is an **error descriptor value**, not an HTTP response, and does not itself carry HTTP status, request ID, tokens, or session data. From an `OAuth2Error`, the application can classify failures, log safe telemetry, or wrap it in an exception.

### 3.2. `OAuth2AuthorizationException`

In OAuth 2.0 operations such as token exchange, failures during token acquisition are typically represented by <code>OAuth2AuthorizationException</code>:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_client",
    "Client authentication failed",
    null
);

throw new OAuth2AuthorizationException(error);
~~~

This exception lets callers retrieve the error via <code>getError()</code>. You can pass the underlying exception cause to the corresponding constructor for internal diagnostics, but never send stack traces or sensitive messages to the browser.

### 3.3. `OAuth2AuthenticationException`

When an error propagates into Spring Security's login/authentication flow, you may encounter <code>OAuth2AuthenticationException</code>. It is an <code>AuthenticationException</code> that also carries an <code>OAuth2Error</code>.

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_token_response",
    "Token endpoint response is not usable",
    null
);

throw new OAuth2AuthenticationException(error);
~~~

<code>invalid_token_response</code> in this example is an implementation/validation error code for token responses; **it is not one of the six core Token Endpoint error codes in RFC 6749 Section 5.2**. When using custom internal codes, clearly distinguish them from standard provider codes.

Classes to remember:

| Class | Represents | Where Commonly Seen |
|---|---|---|
| <code>OAuth2Error</code> | Error code, description, and error URI | Error model layer |
| <code>OAuth2AuthorizationException</code> | Failed OAuth authorization/token operation | OAuth2 token response client, authorized client manager |
| <code>OAuth2AuthenticationException</code> | Failure while creating/verifying authentication | OAuth2 Login, OIDC authentication provider |
| <code>AuthenticationFailureHandler</code> | How the app responds to the browser when login fails | Servlet OAuth2 Login |

Do not treat all of these exceptions as equivalent: **the failure stage** and **handling context** differ. For instance, a callback with a mismatched `state` fails before ever calling the token endpoint; never fabricate a Token Endpoint <code>invalid_grant</code> error for that situation.

## 4. Which Components Does a Token Response Pass Through?

In Spring Security Servlet Authorization Code Flow:

~~~mermaid
flowchart TD
    A["OAuth2LoginAuthenticationFilter receives callback"] --> B["OAuth2LoginAuthenticationProvider / OIDC provider"]
    B --> C["OAuth2AccessTokenResponseClient for authorization_code"]
    C --> D["HTTP request to Token Endpoint"]
    D --> E{"HTTP response"}
    E -->|2xx valid token JSON| F["Convert to OAuth2AccessTokenResponse"]
    E -->|4xx JSON OAuth error| G["Parse and convert to OAuth2Error"]
    E -->|Malformed format / transport error| H["Conversion error or HTTP-layer exception"]
    G --> I["OAuth2AuthorizationException"]
    H --> J["Adapter handles safely per provider, or fail closed"]
    J --> I
    I --> K["Login flow fails, AuthenticationFailureHandler"]
    F --> L["Subsequent OAuth2/OIDC authentication processing"]
~~~

Relevant APIs/classes:

- <code>OAuth2AccessTokenResponseClient&lt;T extends AbstractOAuth2AuthorizationGrantRequest&gt;</code>: contract to retrieve a token response for a grant request.
- <code>OAuth2AuthorizationCodeGrantRequest</code>: carries the details needed to exchange an authorization code for tokens.
- <code>OAuth2AccessTokenResponse</code>: represents a successfully converted token response.
- <code>OAuth2ErrorHttpMessageConverter</code>: converter for JSON OAuth 2.0 error responses in corresponding HTTP pipelines.
- <code>OAuth2AccessTokenResponseHttpMessageConverter</code>: converter used to read successful token responses, providing data conversion hooks.
- <code>OAuth2ErrorResponseErrorHandler</code>: handler usable in <code>RestTemplate</code>-based HTTP setups to translate standard errors into exceptions.

Actual HTTP client class names depend on your Spring Security version. For example, Spring Security 6.4+ provides <code>RestClientAuthorizationCodeTokenResponseClient</code>, whereas earlier versions use <code>DefaultAuthorizationCodeTokenResponseClient</code> with <code>RestOperations</code>. When customizing, use the exact APIs and extension points supported by your running version.

The key point is that **conversion goes in two directions**:

1. **Success converter:** turns valid token JSON into <code>OAuth2AccessTokenResponse</code>.
2. **Error converter / error handler:** recognizes error responses and turns them into <code>OAuth2Error</code>/<code>OAuth2AuthorizationException</code>.

Never turn an error JSON into a success token merely because the HTTP status is 200, and never fabricate a token response with an empty access token to hide an error.

## 5. Classifying Non-Standard Responses

Not every error response should be handled identically. Classify them clearly before writing an adapter.

| Actual Response | Assessment | Desired Behavior |
|---|---|---|
| HTTP 400 with JSON <code>{"error":"invalid_grant"}</code> | Standard error | Convert to OAuth2Error <code>invalid_grant</code> |
| HTTP 401 with JSON <code>{"error":"invalid_client"}</code> | Client auth error, potentially standard | Preserve error code; check Client authentication |
| HTTP 400 with <code>{"error_code":"CODE_EXPIRED"}</code> | Provider uses custom field name | Dedicated adapter maps per documented contract |
| HTTP 400 with <code>{"error":{"code":"INVALID_CODE"}}</code> | Nested JSON error object | Dedicated adapter reads provider schema |
| HTTP 200 with <code>{"error":"invalid_grant"}</code> | Provider sent wrong HTTP status | Detect error body and reject token exchange |
| HTTP 200 with <code>{"access_token": "...", "error": "..."}</code> | Contradictory, untrusted response | Reject; never arbitrarily pick one branch |
| HTTP 200 yet missing <code>access_token</code> or <code>token_type</code> | Success body fails token response contract | Report malformed response; never invent values |
| HTTP 502/503 with HTML body | Gateway/OP failure | Classify as infrastructure error; do not parse HTML as OAuth code |
| HTTP 429 with gateway-specific JSON | Rate limit | Record HTTP 429 and dedicated retry policy; never convert to <code>invalid_grant</code> |
| HTTP 302 to provider login page | Unexpected redirect from token endpoint | Do not follow redirects blindly; check URL, auth, and proxy |
| Timeout, DNS/TLS failure, connection reset | No complete OAuth response received | Record transport error; do not guess an OAuth error |
| HTTP 400 with non-JSON body or truncated JSON | Unparseable per protocol | Fail closed, emit safe technical error code |

**Fail closed** here means never allowing the login/token-exchange flow to proceed as successful without a valid, verified token response.

## 6. Safe Processing Order at the Token Endpoint Boundary

A reliable adapter does more than rename <code>error_code</code> to <code>error</code>. It enforces error detection rules, input bounds, and separation between protocol failures and network failures.

You can model it as:

~~~mermaid
flowchart TD
    A["Receive HTTP result from Token Endpoint"] --> B{"HTTP response received?"}
    B -->|No| N["Transport error: timeout, TLS, DNS..."]
    B -->|Yes| C{"Size / Content-Type acceptable?"}
    C -->|No| X["Invalid/unexpected token response"]
    C -->|Yes| D{"HTTP status"}
    D -->|2xx| E{"JSON has error or success fields?"}
    E -->|Error| L["Normalize provider error"]
    E -->|Valid token| S["Convert token response"]
    E -->|Missing/contradictory| X
    D -->|4xx| F{"Standard OAuth error or supported schema?"}
    F -->|Yes| L
    F -->|No| X
    D -->|429/5xx/redirect| G["Classify HTTP/provider failure"]
    L --> O["OAuth2Error, then appropriate exception"]
    X --> O
    G --> O
    N --> O
    S --> T["Continue OIDC/OAuth2 validation"]
~~~

### 6.1. Accept Only Schemas the Application Intentionally Supports

Suppose Provider A documents the response:

~~~json
{
  "error_code": "AUTHORIZATION_CODE_EXPIRED",
  "message": "Please authorize again",
  "request_id": "req-demo-42"
}
~~~

You can map <code>AUTHORIZATION_CODE_EXPIRED</code> to <code>invalid_grant</code> because **its semantics are explicitly confirmed**. Never write a blanket rule like "all HTTP 400 errors → invalid_grant"; that masks <code>invalid_client</code>, <code>invalid_scope</code>, and other failures.

If a provider does not document a custom schema, prefer **keeping a generic technical error** and logging safe classification metadata for investigation. Guessing root causes from English prose or HTML often breaks whenever the provider changes wording, localization, versions, or proxy layers.

### 6.2. Bound External Error Data

Provider error payloads are **untrusted data**:

- Cap the response size read into memory. A multi-megabyte HTML error page should never be buffered into an `OAuth2Error`.
- Never copy full bodies, stack traces, credential-bearing headers, or URLs containing authorization codes into <code>error_description</code>.
- Never reflect raw <code>error_description</code> values onto login pages or user-facing JSON.
- Never auto-open <code>error_uri</code> when the URI comes from an unverified provider; either drop it or allowlist trusted documentation hosts.
- Never normalize errors so broadly that monitoring loses visibility into HTTP 5xx, 429, TLS, or timeout failures.

## 7. Java Example: Normalizing Custom JSON Errors into `OAuth2Error`

Below is a simple mapper for **one specific provider**, illustrating solely the conversion of an error JSON already captured at the HTTP boundary. Suppose the provider documents the codes <code>AUTHORIZATION_CODE_EXPIRED</code>, <code>BAD_CLIENT_CREDENTIALS</code>, and <code>SCOPE_NOT_ALLOWED</code>.

Example using Jackson (typically included with Spring Boot web starter):

~~~java
package example.security.oauth2;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.security.oauth2.core.OAuth2Error;

import java.util.Set;

public final class ProviderTokenErrorMapper {

    private static final int MAX_ERROR_BODY_BYTES = 16 * 1024;
    private static final Set<String> STANDARD_CODES = Set.of(
        "invalid_request",
        "invalid_client",
        "invalid_grant",
        "unauthorized_client",
        "unsupported_grant_type",
        "invalid_scope"
    );

    private final ObjectMapper objectMapper;

    public ProviderTokenErrorMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * Receives HTTP status and a body already bounded/read at the HTTP layer.
     * Produces only safe error metadata; never constructs a token response.
     */
    public OAuth2Error fromHttpFailure(int httpStatus, byte[] body) {
        if (body == null || body.length == 0 ||
                body.length > MAX_ERROR_BODY_BYTES) {
            return genericError(httpStatus);
        }

        try {
            JsonNode root = objectMapper.readTree(body);
            if (root == null || !root.isObject()) {
                return genericError(httpStatus);
            }

            String code = text(root, "error");

            // Some providers return error as an object.
            if (code == null && root.path("error").isObject()) {
                code = text(root.path("error"), "code");
            }

            // Support only this provider's known custom schema.
            if (code == null) {
                code = text(root, "error_code");
            }

            String normalized = normalizeCode(code);
            if (normalized == null) {
                return genericError(httpStatus);
            }

            // Controlled message, never echoing raw messages.
            return new OAuth2Error(
                normalized,
                safeDescription(normalized),
                null
            );
        } catch (JsonProcessingException exception) {
            return genericError(httpStatus);
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual()) {
            return null;
        }
        String result = value.asText();
        return result.isBlank() ? null : result;
    }

    private static String normalizeCode(String providerCode) {
        if (providerCode == null) {
            return null;
        }
        if (STANDARD_CODES.contains(providerCode)) {
            return providerCode;
        }
        return switch (providerCode) {
            case "AUTHORIZATION_CODE_EXPIRED" -> "invalid_grant";
            case "BAD_CLIENT_CREDENTIALS" -> "invalid_client";
            case "SCOPE_NOT_ALLOWED" -> "invalid_scope";
            default -> null;
        };
    }

    private static OAuth2Error genericError(int httpStatus) {
        String code = httpStatus == 429
            ? "provider_rate_limited"
            : "provider_token_response_error";
        return new OAuth2Error(
            code,
            "OAuth2 token request could not be completed",
            null
        );
    }

    private static String safeDescription(String code) {
        return switch (code) {
            case "invalid_client" -> "Client authentication was rejected";
            case "invalid_grant" -> "Authorization grant was rejected";
            case "invalid_scope" -> "Requested scope was rejected";
            default -> "OAuth2 token request was rejected";
        };
    }
}
~~~

**Scope of this example:** <code>fromHttpFailure</code> normalizes only **responses already identified as errors**. It does not send token requests, inspect success bodies, or turn every HTTP 200 into an error. A complete adapter must check for success responses **before** invoking a success converter; when an HTTP 200 response carries an <code>error</code> field, the adapter must detect the anomaly and route to the error branch instead of the success converter.

Bound the body **while reading the HTTP stream**, rather than buffering unbounded bytes and checking <code>body.length</code> afterward. The length check inside the mapper is defense-in-depth, not a substitute for transport-layer limits.

### 7.1. Why Not Pass Through the Provider's `error_description` Directly?

A response might contain:

~~~json
{
  "error": "invalid_client",
  "error_description": "Secret rejected for client web-prod; token=...; trace=..."
}
~~~

Copying <code>error_description</code> verbatim to the UI or logs can leak secrets or internal infrastructure details. Mapping to fixed descriptions classifies the failure without letting provider-controlled strings propagate outward.

In internal monitoring, you can record **allowlisted error codes**, HTTP status, provider name, an app-generated correlation ID, and timestamp. Store a provider request ID only after validating its length, format, and data policy.

### 7.2. An Error Mapper Cannot Automatically Fix a Non-Standard Success Token Response

If a provider returns:

~~~json
{
  "token": "ACCESS_TOKEN_VALUE",
  "type": "Bearer",
  "expires": 3600
}
~~~

that is a **non-standard success schema**, different from error JSON. If supporting this provider is mandatory, the adapter must translate the payload into the standard shape before constructing <code>OAuth2AccessTokenResponse</code>:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600
}
~~~

Do so only when schema, data types, and values are **clearly documented**. Never blindly accept a field named <code>token</code> or default to <code>token_type=Bearer</code> without a compatibility contract. For OIDC, preserve <code>id_token</code> intact and pass it through ID Token validation; never use a mapper to skip signature or issuer verification.

## 8. Integrating into Spring Security OAuth2 Client

The extension point provided by Spring Security for the Authorization Code Flow is:

~~~java
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
~~~

Spring Security invokes this client when exchanging an authorization code for tokens. Your application can supply its own implementation via the DSL <code>oauth2Login().tokenEndpoint().accessTokenResponseClient(...)</code>.

### 8.1. Decorator Example for Already-Parsed Errors

When the library's HTTP converter **has already parsed an `OAuth2Error`**, you can wrap the token response client to normalize a provider-specific code. This is a simple wrapper independent of how HTTP requests are sent:

~~~java
package example.security.oauth2;

import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

public final class TranslatingAuthorizationCodeTokenClient
    implements OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest> {

    private final OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
        delegate;

    public TranslatingAuthorizationCodeTokenClient(
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest> delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AccessTokenResponse getTokenResponse(
            OAuth2AuthorizationCodeGrantRequest request) {
        try {
            return delegate.getTokenResponse(request);
        } catch (OAuth2AuthorizationException ex) {
            OAuth2Error original = ex.getError();

            if ("AUTHORIZATION_CODE_EXPIRED".equals(original.getErrorCode())) {
                OAuth2Error normalized = new OAuth2Error(
                    "invalid_grant",
                    "Authorization grant was rejected",
                    null
                );
                throw new OAuth2AuthorizationException(normalized, ex);
            }

            throw ex;
        }
    }
}
~~~

The wrapper preserves the delegate's behavior for valid responses and intervenes only when catching a known custom error code. It **cannot** repair HTML, malformed JSON, or HTTP 200 error bodies unless the delegate surfaces them as a matching <code>OAuth2AuthorizationException</code>.

To handle malformed responses, intercept at the **HTTP message conversion/error handling layer** of the token response client, or build a custom <code>OAuth2AccessTokenResponseClient</code> tailored to that provider. Never catch every <code>RuntimeException</code> from the delegate and return a fake token response.

### 8.2. Wiring the Custom Client into `oauth2Login()`

Servlet configuration example using the wrapper above; the code uses <code>RestClientAuthorizationCodeTokenResponseClient</code> available in Spring Security versions supporting `RestClient`:

~~~java
package example.security;

import example.security.oauth2.TranslatingAuthorizationCodeTokenClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var delegate = new RestClientAuthorizationCodeTokenResponseClient();
        var translatedClient =
            new TranslatingAuthorizationCodeTokenClient(delegate);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(translatedClient))
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/login?error")));

        return http.build();
    }
}
~~~

This example requires the <code>spring-boot-starter-oauth2-client</code> dependency, a valid <code>ClientRegistration</code>, and a Spring Security version featuring <code>RestClientAuthorizationCodeTokenResponseClient</code> (Spring Security 6.4+). On older Spring Security versions, the HTTP delegate is typically <code>DefaultAuthorizationCodeTokenResponseClient</code>; do not copy class names verbatim if your dependency version lacks that API.

<code>SimpleUrlAuthenticationFailureHandler</code> sends users to a generic error page, avoiding exposing sensitive messages from the token response. For custom UIs, display a user-friendly message and a support reference code; never embed raw provider <code>error_description</code> values into query strings.

> Do not configure a custom client just to rename error codes if the provider already returns standard errors and Spring Security handles them properly. Adding an adapter introduces extra code and failure modes, so use one only when backed by real evidence of provider differences.

### 8.3. Handling Non-Standard Responses at the HTTP Boundary

A practical adapter for a provider returning custom JSON typically layers responsibilities as follows:

~~~text
OAuth2AccessTokenResponseClient
  |
  +-- Build token request with proper grant / client authentication
  |
  +-- HTTP client (HTTPS, timeouts, redirect policy, body size limit)
  |
  +-- Inspect HTTP status + Content-Type
  |
  +-- Parse standard error or known custom JSON error
  |     -> ProviderTokenErrorMapper
  |     -> OAuth2AuthorizationException(OAuth2Error)
  |
  +-- Parse valid success token response per schema
        -> OAuth2AccessTokenResponse
~~~

Reuse the built-in token client and converter/error-handler hooks before writing a full token exchange from scratch. If a custom implementation is unavoidable, beyond parsing JSON you must handle <code>grant_type</code>, <code>code</code>, <code>redirect_uri</code>, client authentication, PKCE verifier, form encoding, HTTPS, and all OAuth2/OIDC rules accurately. Adjusting response parsing must never alter valid token request construction.

### 8.4. Do Not Confuse OAuth2 Login Errors with API Call Errors

<code>AuthenticationFailureHandler</code> handles **failed Servlet logins**, typically redirecting the browser. When the application proactively uses <code>OAuth2AuthorizedClientManager</code> to obtain tokens via client credentials or refresh tokens, errors surface in the service layer, background jobs, or HTTP API handlers—**bypassing the OAuth2 Login failure handler**.

Likewise, a Resource Server rejecting an access token with <code>invalid_token</code> in <code>WWW-Authenticate</code> is distinct from the Token Endpoint returning <code>invalid_grant</code>. Never collapse all OAuth errors into a single converter that ignores context.

## 9. HTTP 200 Containing an Error Body

This is an easy trap when relying solely on HTTP status codes:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "error_code": "AUTHORIZATION_CODE_EXPIRED",
  "message": "authorization code has expired"
}
~~~

If the HTTP library only triggers error handlers on 4xx/5xx statuses, this JSON enters the **success converter**. The success converter expects <code>access_token</code> and <code>token_type</code> and fails parsing/validation. A customized client must recognize this proprietary schema at the HTTP boundary and map it to <code>OAuth2Error("invalid_grant", ...)</code> as a **failure**, despite HTTP 200.

However, never write an overly loose rule such as:

~~~text
If the JSON response has a "message" field, treat it as an error.
~~~

Because <code>message</code> is not a standard error field and could appear in another valid object. The proper approach is **matching the specific provider's documented schema** and explicitly scoping supported states.

A response containing both <code>access_token</code> and <code>error</code> must also be rejected. That is contradictory data—classify it as an invalid token response rather than picking the convenient half to keep login going.

## 10. HTTP 401, 429, 5xx, and Transport Errors

### 10.1. HTTP 401 and `invalid_client`

<code>invalid_client</code> typically points to Client authentication issues:

- Secret mismatch or rotated secret.
- Wrong <code>client-authentication-method</code>, such as <code>client_secret_basic</code> vs. what the IdP registered.
- Staging Client ID/secret sent to the production Token Endpoint.
- Wrong key/certificate in asymmetric authentication setups.

Never automatically "retry without a secret" or switch from confidential Client to public Client to bypass errors. That changes the security model and usually just produces more failed requests.

### 10.2. HTTP 429: Rate Limiting

HTTP 429 indicates rate limiting at the provider or gateway. It **is not one of the six core Token Endpoint error codes**. You can record an internal code such as <code>provider_rate_limited</code> and keep status 429 in telemetry.

If the provider sends a <code>Retry-After</code> header, operational policies may consult it. However, never retry infinitely or retry blindly based on arbitrary error text. With authorization codes, code exchange is normally a **single-success operation**.

### 10.3. HTTP 5xx and Indeterminate Outcomes

Receiving HTTP 503 before the provider processes the grant may allow a bounded retry in some setups. Yet on a **timeout after sending the token request**, the Client cannot tell whether the Token Endpoint already consumed the authorization code and issued tokens.

Resending the same code automatically may return <code>invalid_grant</code> because the code was single-use. Therefore:

- Do not assume every timeout means "the server definitely never processed it."
- Do not auto-retry Authorization Code Exchange under policies meant for idempotent GET requests.
- Classify it as an **indeterminate outcome** and let the user start a fresh authorization flow where appropriate.
- For client credentials/refresh tokens, retry policies may differ, governed by provider semantics and documentation.

### 10.4. HTML or Redirects from a Gateway

Suppose the token endpoint returns:

~~~http
HTTP/1.1 502 Bad Gateway
Content-Type: text/html

<html><body>Upstream temporarily unavailable</body></html>
~~~

This is not a standard JSON `OAuth2Error`. Never regex-parse HTML looking for strings like <code>invalid_client</code> or <code>invalid_grant</code>. Classify it as an infrastructure/invalid-response failure and inspect the gateway, DNS, TLS, and Token Endpoint path.

If the token endpoint returns HTTP 302 to an interactive login page, inspect the configured endpoint URL and proxy authentication. A standard token exchange is backend-to-backend and must not rely on browser redirects or HTML forms.

## 11. OIDC: Token Response Errors and ID Token Verification

In the OIDC Authorization Code Flow, the token response typically includes <code>id_token</code>. After the HTTP response parses cleanly, the Client must still verify:

- The ID Token signature against trusted public keys from JWKS belonging to the trusted issuer.
- The <code>iss</code> claim matches the configured OpenID Provider.
- The <code>aud</code> claim matches the Client ID, along with <code>azp</code> constraints when applicable.
- <code>exp</code>, <code>iat</code>, and required time constraints.
- <code>nonce</code> when used in the authorization request and related OIDC bindings.

A provider returning HTTP 200 with valid JSON token fields yet an ID Token with the wrong issuer **is still an authentication failure**, not a success.

When customizing a success converter for provider-specific field names, never strip <code>id_token</code>, disable OIDC validation, or accept an unverified JWT as an ID Token. Normalizing the HTTP schema is only one part of protocol verification.

## 12. Application Behavior and User Experience When the Token Endpoint Fails

A Token Endpoint failure typically happens **after the user already interacted with the OP**, so displaying "Wrong password" can be completely misleading. Applications should present a generic yet helpful message:

> Unable to complete sign-in. Please try again. If the problem persists, contact support with your request reference.

Operationally, classify failures clearly:

| Internal Category | Examples | Recommended Action |
|---|---|---|
| Client configuration error | <code>invalid_client</code>, <code>unauthorized_client</code> | Alert operations; do not retry endlessly |
| Grant rejected | <code>invalid_grant</code> | Prompt to restart the login flow when appropriate |
| Invalid scope request | <code>invalid_scope</code> | Fix `ClientRegistration`/permissions |
| Malformed response | Broken JSON, missing <code>access_token</code>, HTML | Fail closed; inspect provider/gateway |
| Transient infrastructure | Timeout, 502, 503, 429 | Record metrics and apply proper recovery strategy |
| OIDC verification failure | Bad signature, issuer, audience, nonce | Reject authentication; inspect issuer/JWKS/flow |

With Servlet <code>oauth2Login()</code>, <code>AuthenticationFailureHandler</code> can send users back to the login page with a generic notice. If you need to distinguish failures for users, pass only an **app-controlled support code**, never raw OAuth errors, tokens, or callback query strings.

In a service-to-service Client Credentials Flow, the app may return HTTP 502/503 or a domain error to callers per API contract, without exposing raw Authorization Server internal error JSON.

## 13. Observing Errors in Production

A multi-provider system should track at minimum:

- **Allowlisted registration/provider name**, never a dynamic user-supplied URL.
- **Grant type**: `authorization_code`, `refresh_token`, `client_credentials`.
- **Failure stage**: request construction, HTTP transport, error response parsing, success converter, ID Token validation.
- **HTTP status** (when a response was actually received).
- **Normalized `OAuth2Error` code** or controlled internal error code.
- **Rate and trend** per provider/environment; app-generated correlation ID.

Strictly avoid putting into logs, metric labels, or UI-bound exceptions:

- <code>client_secret</code>, credential-bearing HTTP <code>Authorization</code> headers.
- Authorization codes, PKCE verifiers, refresh tokens.
- Raw access tokens, ID Tokens.
- Full callback URLs containing <code>code</code>/<code>state</code> query params.
- Unvetted raw Token Endpoint response bodies.

Never attach raw <code>error_description</code> values to metric labels—they risk leaking data and creating unbounded label cardinality. Use finite error categories.

When raw responses must be inspected in a developer-controlled test environment, use dummy data, keep sensitive logging off, and restrict access. Never rely on logging raw token traffic for production observability.

## 14. Common Design Mistakes

### 14.1. Catching Every Exception and Turning It into `invalid_grant`

~~~java
try {
    return delegate.getTokenResponse(request);
} catch (RuntimeException ex) {
    throw new OAuth2AuthorizationException(
        new OAuth2Error("invalid_grant")
    );
}
~~~

**Do not implement it this way.** It turns DNS failures, timeouts, JSON errors, and even application bugs into <code>invalid_grant</code>, sending operators down the wrong path and hiding real causes. Map only **confirmed schemas/error codes**; for everything else, preserve the exception or translate to a clearly classified internal error.

### 14.2. Assuming Any 2xx Response Is Always Successful

HTTP 200 can contain a proprietary error body or JSON missing mandatory fields. Validate contents before treating token exchange as complete. Never fabricate an empty access token just to prevent the converter from throwing.

### 14.3. Treating Every HTTP 401 as `invalid_client`

An HTTP 401 can come from a reverse proxy or gateway enforcing its own authentication layer separate from OAuth2 Client authentication. Conclude <code>invalid_client</code> only when the response/trusted source confirms it; otherwise preserve HTTP/infrastructure error classification.

### 14.4. Disabling TLS Verification or Following Arbitrary Redirects

Token requests carry credentials and authorization codes/refresh tokens over HTTPS. Never disable certificate checks or automatically follow HTTP 302 `Location` headers on token requests. The risk of leaking secrets far outweighs "getting login to pass."

### 14.5. Turning Internal Failures into Standard OAuth Errors with Wrong Semantics

Standard codes like <code>invalid_client</code> or <code>invalid_grant</code> carry specific protocol meaning. When the cause cannot be confirmed, use a clearly prefixed internal code such as <code>provider_token_response_error</code>. Never masquerade internal errors as standard OAuth errors emitted by the Authorization Server.

### 14.6. Neglecting `AuthenticationFailureHandler`

A token response client may classify errors cleanly, yet if the login layer leaks raw exception messages to the browser, sensitive details still escape. Handle errors end-to-end: **HTTP adapter → `OAuth2Error`/exception → authentication failure handler → safe user message**.

## 15. Practice Scenarios

### Exercise 1 — Standard `invalid_grant` Error

Token Endpoint returns:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant","error_description":"code already used"}
~~~

**Question:** What should <code>OAuth2Error.errorCode</code> be? Should you auto-retry with the same authorization code?

**Answer:** Keep <code>invalid_grant</code>. Do not auto-retry with the same code as if it were an idempotent request. Investigate used/expired codes, redirect URI, and PKCE; prompt the user to restart the login flow if appropriate.

### Exercise 2 — HTTP 200 Containing an Error

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"error_code":"AUTHORIZATION_CODE_EXPIRED","message":"expired"}
~~~

**Question:** Why shouldn't the success converter build an <code>OAuth2AccessTokenResponse</code>?

**Answer:** The body lacks mandatory token fields and reports a proprietary error schema. An adapter aware of the provider schema can map <code>AUTHORIZATION_CODE_EXPIRED</code> to <code>invalid_grant</code> and throw <code>OAuth2AuthorizationException</code>; HTTP 200 does not turn an error into success.

### Exercise 3 — Gateway Error Returning HTML

~~~http
HTTP/1.1 502 Bad Gateway
Content-Type: text/html

<html><body>Upstream unavailable</body></html>
~~~

**Question:** Should this be parsed as <code>invalid_client</code> because browser/login failed?

**Answer:** No. This is an HTTP/gateway error or non-standard response with no evidence of Client authentication failure. Record HTTP 502 with provider name, infrastructure failure category, and a safe correlation ID; display a generic login-failure notice.

### Exercise 4 — Misdirected Mapping

Provider returns:

~~~json
{
  "error_code": "SCOPE_NOT_ALLOWED",
  "message": "requested scope is not granted"
}
~~~

**Question:** Which code can this map to, and what should be checked?

**Answer:** If the provider contract confirms the semantics, map it to <code>invalid_scope</code>. Then check requested scopes in `ClientRegistration` and scope policies at the OP, rather than merely changing the error message.

### Exercise 5 — Timeout After Sending the Code

The Client sent the authorization code and hit a read timeout without receiving a response.

**Question:** Can you be certain the code wasn't consumed?

**Answer:** No. The Token Endpoint may have processed the request while the response was lost. Never blindly retry the same code; treat it as an indeterminate outcome and initiate a fresh flow when appropriate.

### Exercise 6 — Designing an Adapter for a Proprietary Provider

An internal provider returns two shapes:

~~~json
{"error":{"code":"BAD_CLIENT_CREDENTIALS","detail":"..."}}
~~~

~~~json
{"error":{"code":"AUTHORIZATION_CODE_EXPIRED","detail":"..."}}
~~~

Requirements:

1. At the HTTP boundary, enforce body size limits, Content-Type, HTTP status, and the published error schema.
2. Map <code>BAD_CLIENT_CREDENTIALS → invalid_client</code>, <code>AUTHORIZATION_CODE_EXPIRED → invalid_grant</code>.
3. Keep error descriptions app-controlled; never echo <code>detail</code>.
4. Throw <code>OAuth2AuthorizationException</code> carrying the appropriate <code>OAuth2Error</code>.
5. In OAuth2 Login, send users to a generic error page via <code>AuthenticationFailureHandler</code>.
6. For unknown JSON/HTML/timeouts, never misrepresent them as either of the two known error codes.

An adapter should only be built when the provider has a clear contract. Integration tests during the project's technical verification phase can use a mock Token Endpoint to exercise success, standard errors, proprietary errors, malformed bodies, and anomalous HTTP 200 responses.

## 16. Key Takeaways

- **Standard Token Endpoint errors** typically return JSON with <code>error</code> and optional <code>error_description</code> and <code>error_uri</code>; HTTP status is usually 400 or 401 for <code>invalid_client</code>.
- **<code>OAuth2Error</code>** holds an error code, description, and URI. <code>OAuth2AuthorizationException</code> typically represents token exchange failures; <code>OAuth2AuthenticationException</code> surfaces in authentication contexts.
- **<code>OAuth2AccessTokenResponseClient</code>** is the Token Endpoint extension point per grant; in Servlet OAuth2 Login, attach custom implementations via <code>oauth2Login().tokenEndpoint().accessTokenResponseClient(...)</code>.
- **Non-standard responses** must be classified by HTTP status, Content-Type, schema, and documented semantics. Never accept an HTTP 200 error as success, and never map every HTTP 400 to <code>invalid_grant</code>.
- **Connectivity / HTTP gateway errors** are not automatically OAuth errors from the Authorization Server. Timeouts after sending an authorization code leave an indeterminate state; avoid blind retries.
- **Provider error payloads are untrusted data.** Log only sanitized details, keep UI notices safe, and never bypass TLS, PKCE, or ID Token verification.

### References

- **RFC 6749 — The OAuth 2.0 Authorization Framework**, Sections 5.1 and 5.2: token success/error responses, error codes, and HTTP statuses.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: Bearer errors when a Resource Server rejects an access token; distinct from Token Endpoint errors.
- **RFC 7636 — Proof Key for Code Exchange (PKCE)**: token exchange using `code_verifier` and authorization code constraints.
- **OpenID Connect Core 1.0**: token responses in the OIDC Authorization Code Flow and ID Token verification.
- **Spring Security Reference — OAuth2 Client / OAuth2 Login**: token endpoint customization, `OAuth2AccessTokenResponseClient`, and authentication failure handling.
- **Spring Security Java API**: `OAuth2Error`, `OAuth2AuthorizationException`, `OAuth2AuthenticationException`, `OAuth2ErrorHttpMessageConverter`, and `OAuth2AccessTokenResponseHttpMessageConverter`.
