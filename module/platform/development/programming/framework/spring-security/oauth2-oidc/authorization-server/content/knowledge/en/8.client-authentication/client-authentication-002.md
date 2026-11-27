# `client_secret_basic` and `client_secret_post`

In OAuth 2.0/OpenID Connect (OIDC), **client authentication** is the process by which the Authorization Server verifies who a client application claims to be when calling endpoints that require client authentication, typically the **token endpoint**. Two common methods using a shared secret are **`client_secret_basic`** and **`client_secret_post`**. They differ in **where `client_id` and `client_secret` are transmitted in the HTTP request**, not in which type of client is issued a secret.

This lesson belongs to the **Client Authentication** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module and explains the standard syntax, how Spring Authorization Server recognizes and authenticates each method, `RegisteredClient` registration, Spring Security OAuth2 Client configuration, secret management, error handling, and testing. This is a key part of learning how to design, configure, secure, and operate an Authorization Server with Spring Boot.

> **Scope:** These two methods are intended for clients capable of keeping secrets, usually backend **confidential clients**. The HTTP/Java/YAML snippets illustrate the principles and require appropriate dependencies, AS configuration, Spring versions, and test data to run.

## 1. What Question Does Client Authentication Answer?

OAuth 2.0 involves distinct actors: the **user** (resource owner in many flows), the **OAuth2 Client** (the application requesting tokens), the **Authorization Server** (the token issuer), and the **Resource Server** (the API protecting resources).

Client authentication answers: **"Does the application sending the request actually possess the credentials registered for this `client_id`?"** It is not the question "Has the user logged in?"

For example, suppose a system has a background app `batch-reports` calling the token endpoint with the `client_credentials` grant:

1. An administrator registers `client_id=batch-reports` along with its authentication method and credentials at the Authorization Server.
2. The background app sends `POST /oauth2/token` with `grant_type=client_credentials` and credentials according to the registered method.
3. The Authorization Server verifies the **client identity**, grant, and allowed scopes.
4. If the request is valid, the AS issues an access token so the application can call protected APIs.

In the example above, **no end user logs in**, so there is no OIDC ID Token representing a recent user authentication event.

In the Authorization Code flow, a user may log in and grant consent beforehand, yet **a confidential client still has to authenticate itself when exchanging an authorization code for a token** if required by the AS. This mechanism does not replace validating the authorization code, redirect URI, or PKCE.

## 2. Quick Comparison of the Two Methods

| Criterion | `client_secret_basic` | `client_secret_post` |
|---|---|---|
| Where credentials are sent | HTTP header `Authorization: Basic ...` | HTTP body as `application/x-www-form-urlencoded` |
| `client_id`/`client_secret` parameters in body | Usually **absent**; credentials are in the Basic header | **Both** `client_id` and `client_secret` are present |
| Encoding algorithm on the request | Form URL-encode each component, join with `:`, then Base64 | Form URL-encode as fields in the body |
| Does Base64 protect the secret? | **No.** Base64 is only an encoding; anyone reading the header can decode it | Base64 is not used at this layer; anyone reading the body can still see the secret |
| Support under OAuth 2.0 RFC 6749 | AS **MUST support** HTTP Basic when issuing client passwords | AS **MAY support**, though RFC 6749 **does not recommend** it unless the client cannot use Basic |
| Common logging risk | Proxy/APM or HTTP client logs the `Authorization` header | Proxy/APM/framework logs request body/form parameters |
| Spring configuration | `ClientAuthenticationMethod.CLIENT_SECRET_BASIC` | `ClientAuthenticationMethod.CLIENT_SECRET_POST` |
| Essential prerequisites | Client has a secret, AS allows Basic, **HTTPS** | Client has a secret, AS allows Post, **HTTPS** |

**A sensible default when both the AS and client support it:** use `client_secret_basic`. Choose `client_secret_post` only when there is an evaluated compatibility requirement, request-body logging risks are controlled, and AS support is confirmed. For high-security requirements, an asymmetric authentication method such as `private_key_jwt` or mTLS may be needed instead of a shared secret; those are different mechanisms, not variants of Basic/Post.

### 2.1. "client_secret" Does Not Mean "client-side"

The name `client_secret` can mislead people into thinking the secret belongs in browser JavaScript code. That is **incorrect**: a client secret only provides authentication value when the application can keep it confidential, such as on a controlled backend. Embedding a secret in a SPA bundle, mobile app, public source code, or URL lets others extract it and impersonate the client.

A typical **public client** uses `ClientAuthenticationMethod.NONE` and Authorization Code + PKCE, not `client_secret_basic` or `client_secret_post` with a secret hardcoded in the browser.

## 3. `client_secret_basic` Flow: Credentials in the HTTP Basic Header

Under **RFC 6749 $2.3.1**, an Authorization Server must support HTTP Basic to authenticate clients issued a client password. In a request to the token endpoint, the client sends:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_OF_ENCODED_CLIENT_ID_COLON_ENCODED_CLIENT_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=documents.read
```

The long string after `Basic` is a **placeholder**, not a real credential. The standard steps to build the Basic payload are:

1. URL-encode `client_id` according to `application/x-www-form-urlencoded` rules (UTF-8).
2. URL-encode `client_secret` using the same rules.
3. Join the two encoded strings with **a single colon `:`**.
4. Base64-encode the combined string and place it in `Authorization: Basic <base64>`.

Illustrative expression:

```text
header = "Basic " + Base64(
  formUrlEncode(client_id) + ":" + formUrlEncode(client_secret)
)
```

**Important detail:** RFC 6749 does not simply require Base64 of the raw `client_id:client_secret` string when credentials contain special characters. Each component must be **form URL-encoded before joining**. For a hypothetical `client_id` of `report:agent` and illustrative secret `demo+value`:

```text
original client_id     = report:agent
original client_secret = demo+value
encoded client_id      = report%3Aagent
encoded secret         = demo%2Bvalue
string before Base64   = report%3Aagent:demo%2Bvalue
```

The `:` character in the ID is encoded as `%3A` to avoid confusion with the Basic separator; the `+` sign in the secret is encoded as `%2B`. The value `demo+value` is solely for explaining encoding and is **not a secret to use in real environments**.

### 3.1. Java Example Creating the Header to Understand the Format

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

// Demonstrates RFC 6749 encoding, not a reason to write your own OAuth2 Client.
String clientId = "report:agent";
String clientSecret = System.getenv("REPORT_AGENT_CLIENT_SECRET");

String encodedId = URLEncoder.encode(
    clientId, StandardCharsets.UTF_8);
String encodedSecret = URLEncoder.encode(
    clientSecret, StandardCharsets.UTF_8);

String credentials = encodedId + ":" + encodedSecret;
String authorizationHeader = "Basic " +
    Base64.getEncoder().encodeToString(
        credentials.getBytes(StandardCharsets.UTF_8));
```

This example does not handle missing environment variables, and `authorizationHeader` should never be logged. In real applications, use **Spring Security OAuth2 Client or an OAuth-aware HTTP client** to standardize encoding, retries, and security. Using `String` in Java also does not erase the credential from memory automatically.

### 3.2. How Is the Basic Header Protected?

HTTP Basic **does not encrypt** the secret; Base64 can be decoded trivially. **TLS/HTTPS is mandatory** to prevent eavesdropping in transit. Yet even over HTTPS, TLS termination points such as reverse proxies and the application itself can read the header. Therefore, you must **mask/strip the `Authorization` header from logs, traces, and error reporting**.

At the token endpoint, the `Authorization: Basic ...` header is used to **authenticate the client to the Authorization Server**. Do not confuse it with the `Authorization: Bearer <access_token>` header that the Client sends to a **Resource Server** to access APIs.

## 4. `client_secret_post` Flow: Credentials in the Form Body

With `client_secret_post`, the client sends `client_id` and `client_secret` as **HTTP POST body** parameters formatted as `application/x-www-form-urlencoded`:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=documents.read&client_id=batch-reports&client_secret=REDACTED_SECRET
```

`REDACTED_SECRET` is only a placeholder. Real credentials must be properly form URL-encoded and sent only over HTTPS. A dedicated HTTP client handles form-field encoding automatically; never concatenate raw secrets into a URL or query string.

Key points to remember:

- This is a **POST body**, **not** `/oauth2/token?client_secret=...` in the query string.
- The body must carry the proper `Content-Type: application/x-www-form-urlencoded` and form-encoded fields.
- The client **must not also send** `Authorization: Basic ...` on the same request. RFC 6749 specifies that a client **must not use more than one client authentication method in the same request**.
- The AS should accept `client_secret_post` only if that method is supported and permitted by the client's registration.
- Secrets can still be captured by HTTP body logging, reverse proxies, APMs, or middleware; do not treat the body as safe storage.

### 4.1. Why Does OAuth 2.0 Discourage client_secret_post?

RFC 6749 allows an AS to support sending client credentials in the form body **but does not recommend it**, limiting it to clients that cannot use HTTP Basic. Request bodies tend to pass through components that capture payloads for debugging, validation, and observability; sending secrets in form fields also makes accidental logging or telemetry capture more likely. However, **Basic is not immune to secret leakage either**, since reverse proxies can log raw headers.

Do not conclude "`client_secret_post` is always compromised" or "Basic is always safe." Both methods rely on a **shared secret**; security depends on TLS, the secret storage environment, client registration, log controls, access restrictions, and rotation processes.

## 5. Processing Flow in Spring Authorization Server

Spring Authorization Server uses components in the Spring Security filter chain to authenticate the client before executing the token grant. For these two methods, the logical flow can be illustrated as follows:

```mermaid
sequenceDiagram
    autonumber
    participant C as Backend OAuth2 Client
    participant F as OAuth2ClientAuthenticationFilter
    participant R as RegisteredClientRepository
    participant P as ClientSecretAuthenticationProvider
    participant T as OAuth2TokenEndpointFilter
    participant G as Grant AuthenticationProvider

    C->>F: POST /oauth2/token (Basic header or form body)
    F->>F: Identify client authentication method
    F->>P: Authentication request
    P->>R: findByClientId(clientId)
    R-->>P: RegisteredClient or null
    P->>P: Verify method, secret, expiration/policy
    alt Client authentication fails
        P-->>F: OAuth2AuthenticationException (invalid_client)
        F-->>C: OAuth2 error response
    else Client authentication succeeds
        P-->>F: Authenticated client principal
        F->>T: Forward token request processing
        T->>G: Verify grant_type, scope, and grant conditions
        alt Grant valid
            G-->>T: Token response
            T-->>C: 200 JSON access_token
        else Grant invalid
            G-->>T: OAuth2 error
            T-->>C: Appropriate error JSON
        end
    end
```

This is a **logical diagram**, not a depiction of every filter/handler detail across Spring versions. `OAuth2ClientAuthenticationFilter` can use specialized `AuthenticationConverter` implementations for Basic or Post; `ClientSecretAuthenticationProvider` is the component that validates client secrets. Only after the client is authenticated does `OAuth2TokenEndpointFilter` process the grant request. **Successful client authentication does not guarantee a token is issued**: the client must also be authorized for the grant, scope, and pass other checks.

### 5.1. RegisteredClient Determines Which Method Is Accepted

Spring stores client metadata as a `RegisteredClient`. Relevant fields include:

| Field | Role |
|---|---|
| `clientId` | Client identifier in the protocol |
| `clientSecret` | Encoded secret stored in a `PasswordEncoder`-compatible format |
| `clientSecretExpiresAt` | Secret expiration timestamp if applicable |
| `clientAuthenticationMethods` | **List of allowed methods**: Basic, Post, private_key_jwt, etc. |
| `authorizationGrantTypes` | Which grants the client is allowed to use |
| `scopes` | Scopes the client is allowed to request |
| `clientSettings` and `tokenSettings` | Client and token policies, independent of where the secret is sent |

If a client registered **Basic only** but sends `client_secret_post`, the AS must reject client authentication. **Knowing the right secret is not enough** if the secret is sent using a disallowed method.

### 5.2. Can a Client Register Both Basic and Post?

`RegisteredClient` can contain multiple `clientAuthenticationMethod(...)` entries if permitted by the AS configuration. That gives the client **options across separate requests**, **not** permission to mix a Basic header and a form secret in the **same request**.

In security design, enable only the methods the client genuinely needs. If both are enabled temporarily to migrate from Post to Basic, establish a time-bounded plan, monitor usage, and remove the unused method.

## 6. Example: Registering Two Confidential Clients

The following configuration illustrates two clients using the `client_credentials` grant, each permitted **only one** method:

```java
@Bean
PasswordEncoder clientSecretPasswordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder clientSecretPasswordEncoder) {

    String basicSecret = requiredEnv("BATCH_REPORTS_CLIENT_SECRET");
    String postSecret = requiredEnv("LEGACY_IMPORT_CLIENT_SECRET");

    RegisteredClient batchReports = RegisteredClient.withId(
            "batch-reports-internal-id")
        .clientId("batch-reports")
        .clientSecret(clientSecretPasswordEncoder.encode(basicSecret))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("documents.read")
        .build();

    RegisteredClient legacyImport = RegisteredClient.withId(
            "legacy-import-internal-id")
        .clientId("legacy-import")
        .clientSecret(clientSecretPasswordEncoder.encode(postSecret))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_POST)
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("documents.write")
        .build();

    return new InMemoryRegisteredClientRepository(
        batchReports, legacyImport);
}

private static String requiredEnv(String name) {
    String value = System.getenv(name);
    if (value == null || value.isBlank()) {
        throw new IllegalStateException("Missing required secret: " + name);
    }
    return value;
}
```

**Meaning of the example:**

- `batch-reports` allows only `client_secret_basic`; `legacy-import` allows only `client_secret_post`.
- Secrets are read from environment configuration at runtime and stored one-way encoded by `PasswordEncoder` in `RegisteredClient`. Using a controlled secret manager is preferable for many production environments.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` produces a hash string with an algorithm prefix, such as `{bcrypt}...`. The provider validating secrets must use a compatible encoder. Never store raw secrets or use `{noop}` in production.
- The `id` values in the example are fixed to illustrate a **stable** internal identifier. In a real system they must be unique; do not generate a new ID on every restart when authorizations/consents are persisted durably.
- `InMemoryRegisteredClientRepository` suits learning and testing. To persist clients across restarts and share across multiple AS instances, consider `JdbcRegisteredClientRepository` or custom persistence with migrations and data protection.
- This is **not yet a complete Authorization Server**: you still need `SecurityFilterChain`, `AuthorizationServerSettings`/issuer, keys/JWKs, `OAuth2AuthorizationService`, a token generator, and other beans depending on the flow.

A real application does not need to enable `client_secret_post` just because the library supports it. Prefer Basic for confidential clients with shared secrets when appropriate, and plan to upgrade the authentication mechanism if security requirements grow stronger.

### 6.1. Do Not Use Registration to Grant Blanket Permissions

Storing `scope("documents.write")` means the client **is allowed to request** this scope per configuration, not that it has unconditional access to every business record. The Authorization Server also evaluates the grant and issuance policies; the Resource Server still must verify the token, issuer, audience, scope, and resource permissions.

In `client_credentials`, the access token may represent the client itself; do not assume every token's `sub` is an end user. `openid` and an OIDC ID Token are **not the default outcome** of client credentials.

## 7. Configuring Spring Security OAuth2 Client to Use Basic or Post

**On the OAuth2 Client application side**, `spring.security.oauth2.client.registration` tells the client how to authenticate to the AS. This is **different** from `RegisteredClientRepository` on the Authorization Server side.

Example of the `batch-reports` client using Basic:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          batch-reports:
            provider: company-auth
            client-id: batch-reports
            client-secret: "${BATCH_REPORTS_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: documents.read
        provider:
          company-auth:
            token-uri: https://identity.example.com/oauth2/token
```

To configure another client using Post, the differing fields are:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-import:
            provider: company-auth
            client-id: legacy-import
            client-secret: "${LEGACY_IMPORT_CLIENT_SECRET}"
            client-authentication-method: client_secret_post
            authorization-grant-type: client_credentials
            scope: documents.write
        provider:
          company-auth:
            token-uri: https://identity.example.com/oauth2/token
```

Spring Boot uses this registration metadata to create a `ClientRegistration` in the **OAuth2 Client**. When an `OAuth2AuthorizedClientManager` or equivalent component executes the client credentials flow, the token request uses the configured authentication method. With Spring Security APIs, select the appropriate client provider/authorized client manager and authorized client persistence for your application context.

**Client-side configuration does not register the client at the AS.** The AS must have a matching `RegisteredClient` with the same `client_id`, method, secret, grant, and scopes. If any component mismatches, authentication or the token grant will fail.

### 7.1. Common Configuration Mismatches

| OAuth2 Client config | AS config | Result |
|---|---|---|
| Basic | Basic only | Can authenticate if ID/secret are correct and valid |
| Post | Post only | Can authenticate if ID/secret are correct and valid |
| Post | Basic only | Rejected due to wrong method, even with the right secret |
| Basic | Post only | Rejected due to wrong method, even with the right secret |
| Basic/Post | Client ID does not exist | `invalid_client` in the client authentication context |
| Basic/Post | Secret mismatch / expired | Client authentication fails |
| Valid Basic/Post | Client not permitted `client_credentials` | Client authentication may succeed, but token grant is rejected |

Do not rely on a specific error message to guess policy. Inspect both sides' registrations and **secret-redacted** logs.

## 8. Do Not Confuse Client Authentication with PKCE, User Login, and Bearer Tokens

| Mechanism | What does it protect or prove? | Can it replace a client secret? |
|---|---|---|
| `client_secret_basic` / `client_secret_post` | The client possesses the shared secret registered with the AS | These are the client authentication methods themselves |
| `Authorization Code + PKCE` | Binds the code to `code_verifier` to prevent stolen-code exchange | **Does not by default replace client authentication** for a confidential client |
| User login at the AS | Authenticates the resource owner's identity | Does not prove the OAuth2 Client possesses a secret |
| OIDC ID Token | Binds the user authentication event to the RP | Not a client secret or token request credential |
| `Authorization: Bearer <access_token>` | API access rights of the token holder | Not used to replace Basic/Post on normal token requests |
| `private_key_jwt` or mTLS | Authenticates the client using asymmetric keys or certificates | Can be an alternative method when supported by AS and client |

**PKCE and client authentication complement each other** in a confidential Authorization Code flow. PKCE mitigates the risk of an attacker intercepting and exchanging an authorization code; the client secret lets the AS verify the confidential client app at endpoints requiring authentication. They defend against different threats.

## 9. Common Errors and Response Contracts

When client authentication fails, Spring Authorization Server usually represents the result as an OAuth 2.0 error such as `invalid_client`. This error code comes from the **client authentication layer**, before the token grant succeeds.

### 9.1. Example Error Due to Invalid Secret or Method

An illustrative response:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json;charset=UTF-8
WWW-Authenticate: Basic realm="oauth2"
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_client"
}
```

This is an **example where the request attempted Basic authentication**. Under RFC 6749, if a client attempts to authenticate via the `Authorization` header, the AS must respond with `401` and an appropriate `WWW-Authenticate` challenge on failure. For `client_secret_post`, the HTTP status/headers may differ depending on endpoint contract and implementation (often `400` with `invalid_client`). **Do not assume every `invalid_client` error shares the same status or Basic challenge**.

Scenarios to distinguish:

| Condition | Typical error | Diagnosis |
|---|---|---|
| `client_id` does not exist | `invalid_client` | Registration and client identifier |
| Secret mismatch | `invalid_client` | Issued / active credentials |
| Secret expired (if configured) | `invalid_client` | `clientSecretExpiresAt` and rotation process |
| Client allows Basic only, sends Post | `invalid_client` | `clientAuthenticationMethods` |
| Client sends both Basic and Post in one request | Invalid request or client auth rejected per endpoint handling | Use **only one** method per request |
| Client authenticated, grant disallowed | `unauthorized_client` | `authorizationGrantTypes` |
| Client authenticated, invalid scope | `invalid_scope` | `scopes` and token grant |
| Invalid authorization code / refresh token | `invalid_grant` | Token grant, code/PKCE/binding; **distinct from** client secret errors |

Never include raw secrets, tokens, Basic credentials, or password-check details in `error_description`. Safe error responses should be concise and avoid helping attackers infer sensitive details beyond what the protocol requires.

### 9.2. Why Switching to Post Does Not Fix a Wrong Secret

Both methods use **the same type of shared secret**. If the secret sent by the client differs from the secret registered at the AS, switching from Basic to Post will not make authentication succeed unless the original bug was actually in **encoding or an incompatible method**. When debugging, check step by step:

1. Which `client_id` is sent and registered at the AS?
2. Does the AS allow Basic, Post, or another method?
3. Is the raw secret on the client side correct and unexpired?
4. Does the Basic encoding form URL-encode special characters before Base64?
5. Does the request have the right `Content-Type` and body/header, without sending duplicate methods?
6. Is a proxy, gateway, or security configuration stripping/altering the `Authorization` header or form body?

Never resolve issues by enabling both methods permanently or disabling client authentication.

## 10. Protecting Client Secrets End-to-End

### 10.1. TLS and Trust Boundaries

HTTP Basic Base64 only encodes; a form body is likewise readable wherever the HTTP request is decrypted. **HTTPS is the minimum requirement** in real deployments. If a reverse proxy terminates TLS and forwards internal traffic, clearly establish who can read requests, how TLS is maintained across the architecture, and forwarded header/host policies.

### 10.2. Logging, Tracing, and Metrics

| Surface | Basic | Post | Control |
|---|---|---|---|
| Gateway/proxy access logs | May log `Authorization` header | May log request body/form fields | Disable/redact sensitive data on both surfaces |
| APM/distributed tracing | May capture headers | May capture payloads | Redact at source, limit retention and access permissions |
| Exception/error responses | Easy to accidentally echo headers | Easy to accidentally echo request parameters | Never return credentials or stack traces to clients |
| Debug tools and HTTP history | May store Basic credentials | May store form bodies | Use test credentials only; never commit sessions/captures |
| Monitoring dashboards | Avoid labels containing secrets | Avoid labels containing secrets | Record only error codes, allowed client IDs, and appropriate correlation IDs |

To diagnose `invalid_client`, log **the error code, endpoint, method, request/correlation ID, and client ID at an appropriate level**. Never log `client_secret`, `Authorization` values, authorization codes, or tokens.

### 10.3. Storage, Distribution, and Rotation

- Use high-entropy secrets generated from a cryptographically secure random source; never use guessable passwords.
- Store plaintext secrets in a **secret manager** or equivalent with restricted access; on the AS side, use hashed/`PasswordEncoder`-compatible values when enforcing client-secret authentication.
- Never commit secrets to source code, shared `application.yml`, Docker images, CI output, or example docs.
- Rotate via a defined procedure: issue new credentials, distribute securely, update registration, monitor errors, and revoke old credentials per policy.
- Check rotation support in your model: a single `RegisteredClient` stores one `clientSecret` by default and **does not automatically support two parallel secrets** during a transition window. If zero-downtime rotation is needed, design and test the transition mechanism beforehand.
- For multi-instance AS deployments or cached `RegisteredClient` lookups, ensure secret/method updates take effect consistently; avoid one node accepting the old secret while another accepts the new one.

### 10.4. Choose Stronger Methods When Appropriate

Shared secrets have drawbacks: both the client and AS must participate in credential management, and credentials can be copied to impersonate the client. When security requirements are high or the number of systems is large, evaluate **`private_key_jwt` or mutual TLS** based on support on both sides. Do not treat moving credentials from the header to the body as a cryptographic upgrade.

## 11. Integration Testing Both Methods

Truly meaningful tests must go through the **Spring Security filter chain** at `/oauth2/token`. Testing `RegisteredClientRepository` directly can verify metadata, but does not prove converters, providers, and failure handlers behave properly.

### 11.1. Recommended Test Matrix

| Scenario | Registration | Request | Expected outcome |
|---|---|---|---|
| Valid Basic | Basic only | Basic header, right secret | Client auth succeeds; token can be issued if grant/scope are valid |
| Valid Post | Post only | Form body with `client_id` and `client_secret` | Same, per client policy |
| Post sent to Basic-only | Basic only | Credentials in body | No token issued, client authentication error |
| Basic sent to Post-only | Post only | Basic header | No token issued, client authentication error |
| Wrong secret | Right method | Fake secret | `invalid_client` |
| Non-existent client | None | Basic/Post | No token issued |
| Missing `client_secret` in Post | Post | Body has only `client_id` | Client cannot authenticate |
| Malformed Basic header | Basic | Invalid Base64 / credential pair | No token issued |
| Special characters in ID/secret | Valid Basic/Post | Uses proper RFC encoding | Authentication still succeeds |
| Both Basic and Post in one request | Both or one | Sends both header and body credentials | Rejected per request handling; never treated as dual authentication |
| Expired secret | Right method, expired secret | Previously valid secret | No token issued |
| Right secret, wrong grant | Right method | Disallowed `grant_type` | Token grant rejected; distinguish `invalid_client` vs. `unauthorized_client` |
| Right secret, wrong scope | Right method | Scope outside registration | Out-of-policy scope is not issued |

### 11.2. MockMvc Example for client_secret_basic

Assume the test environment has `batch-reports` registered with `CLIENT_SECRET_BASIC`, `client_credentials`, and `documents.read`; the secret is used solely in the test fixture:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ClientSecretAuthenticationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void basicClientCanObtainToken() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("batch-reports", "test-basic-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "documents.read"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.token_type").value("Bearer"));
    }
}
```

This snippet omits imports and required fixture/token-signing configuration. `httpBasic(...)` constructs a Basic authentication request via Spring Test; for client IDs/secrets containing special characters, **add tests explicitly verifying RFC 6749 form-encoding rules** in the client request converter in use. A `200` here also depends on properly configured token endpoint, grants, scopes, and AS beans.

### 11.3. MockMvc Example for client_secret_post

With the `legacy-import` registration supporting only `CLIENT_SECRET_POST`:

```java
@Test
void postClientCanObtainToken() throws Exception {
    mvc.perform(post("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "documents.write")
            .param("client_id", "legacy-import")
            .param("client_secret", "test-post-secret"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty());
}
```

This test method assumes it is inside the same class with the `mvc` field and matching fixture. **Do not add a Basic header to the Post request**. The `test-...` values are for testing only, never secrets for production.

### 11.4. Testing Wrong Methods and Wrong Credentials

Example Post request to a Basic-only registration:

```java
@Test
void postMethodIsRejectedForBasicOnlyClient() throws Exception {
    mvc.perform(post("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("client_id", "batch-reports")
            .param("client_secret", "test-basic-secret"))
        .andExpect(jsonPath("$.error").value("invalid_client"))
        .andExpect(result ->
            assertThat(result.getResponse().getStatus()).isBetween(400, 401));
}
```

This is a **method rejection test**, not a grant test: the secret is valid, but it was not sent using a method permitted by the registration. In a production test suite, assert the exact status/challenge specified by the contract of your Spring Authorization Server version rather than only checking a 400–401 range.

Beyond the response, verify in the test environment that **request/response logging and tracing do not contain credentials**, and that clients use the error code to halt or handle retries appropriately.

## 12. Operations and Troubleshooting

When encountering `invalid_client`, do not immediately change the authentication mechanism. Diagnose in order:

1. **Cross-check both registrations:** `client_id`, `ClientAuthenticationMethod`, endpoints, grants, and scopes.
2. **Check credential placement:** Basic requires the `Authorization` header; Post requires `client_id`/`client_secret` in the form body. Avoid sending both.
3. **Check encoding:** especially for `+`, `:`, `%`, `&`, and Unicode characters in secrets. Basic requires form URL-encoding **each component before Base64**.
4. **Check HTTP method and Content-Type:** the token endpoint uses POST with `application/x-www-form-urlencoded` body.
5. **Check secret expiration/rotation:** is the client's raw secret synchronized with the AS hash/registration, or has it expired or been rotated?
6. **Check reverse proxies:** is a proxy stripping the `Authorization` header, rewriting path/host, rejecting the request body, or enforcing header size limits?
7. **Distinguish error layers:** `invalid_client` is a client authentication error; `unauthorized_client` or `invalid_scope` can occur after the client is authenticated.
8. **Inspect logs safely:** use correlation IDs and error codes; never turn on raw secret or token logging to debug.

### 12.1. Migrating from client_secret_post to client_secret_basic

For a legacy client forced to use Post, if its client library now supports Basic, you can plan a migration:

1. Confirm the client system can build Basic headers **strictly per RFC 6749** and connects to the AS over HTTPS.
2. **Temporarily** add Basic to the client's registration if a transition period is needed, or schedule a synchronized cutover on both sides.
3. Thoroughly test all grants and production-like behavior with test secrets; monitor `invalid_client` errors without logging credentials.
4. Switch the client to Basic and verify traffic uses the new method.
5. Remove Post from `clientAuthenticationMethods` once compatibility is no longer needed, and update operational docs and regression tests.

**You do not need to rotate the secret just because its transmission location changed**, though you can combine it with a policy-driven secret rotation. If zero-downtime migration is required, account for registration caching and multi-instance AS deployments; never assume a repository update takes effect simultaneously across all nodes.

## 13. Common Misconceptions

| Misconception | Fact |
|---|---|
| "Basic safely encrypts the client secret because it uses Base64" | Base64 is encoding; you **must use HTTPS** and protect headers/logs |
| "Post is safer because the secret isn't in the header" | Request bodies can also be logged or captured by proxies/APMs |
| "Putting the secret in the query string is also client_secret_post" | **False**: Post uses the **form body**, not the URL query |
| "A client can send both Basic and Post to be extra sure" | **False**: never use multiple client auth methods on the same request |
| "Having a client secret grants permission to call any API" | The secret only authenticates the client; the AS checks grants/scopes and the Resource Server checks access tokens/permissions |
| "PKCE replaces the client secret for confidential web apps" | PKCE and client auth address different threats |
| "A SPA should use client_secret_post because forms are easy to send" | SPAs cannot keep secrets safely; use public client + PKCE |
| "If the secret is right but the method is wrong, the AS should still allow it" | The AS must enforce the methods **registered** for the client |
| "`invalid_client` always returns HTTP 400" | For Basic header authentication, RFC requires **401 + WWW-Authenticate** on client authentication failure |
| "`client_credentials` errors have nothing to do with client registration" | The AS still validates client ID, credentials, grant, and scopes |
| "Just switch from Basic to Post to fix any token error" | You must pinpoint the actual encoding, registration, secret, grant, or policy issue |

## 14. Pre-Deployment Checklist

1. **Is the client type right?** Confidential backend or public browser/mobile? Never issue shared secrets to public clients.
2. **Do methods match on both sides?** `client_secret_basic` or `client_secret_post` explicitly registered at the AS.
3. **Is the token request standard-compliant?** POST form body for the grant; Basic header or form `client_id`/`client_secret`, never mixed.
4. **Is encoding accurate?** For Basic, each credential is form URL-encoded before joining and Base64; for Post, the body is properly URL-encoded.
5. **Are TLS and proxies secure?** HTTPS, no secrets in query strings, no stripped headers, no raw credential logging.
6. **Are secrets managed safely?** High-entropy values, stored in a secret manager, hashed at the AS, with rotation and expiration processes.
7. **Minimal grants and scopes?** Client credentials only when appropriate, restricted scopes, and Resource Server authorization checks.
8. **Are both valid and invalid methods tested?** Basic success, Post success, wrong method, wrong secret, expired secret, bad grant, and special characters.
9. **Is monitoring safe?** Count `invalid_client`, track authentication failures without exposing secrets.
10. **Is there a change plan?** Method migration, multi-node/cache updates, and rollback aligned with operational requirements.

## 15. Summary

- **`client_secret_basic`** transmits credentials in `Authorization: Basic ...`; client ID and secret must be form URL-encoded before joining and Base64 encoding. RFC 6749 requires the AS to support Basic when issuing client passwords.
- **`client_secret_post`** transmits `client_id` and `client_secret` in the **HTTP POST form body**. It is an optional compatibility choice and **not recommended by RFC 6749** when Basic can be used.
- Both are **shared-secret client authentication** methods requiring HTTPS, backend secret protection, an appropriate `PasswordEncoder`, log redaction, and rotation procedures.
- In **Spring Authorization Server**, `RegisteredClient.clientAuthenticationMethods` defines accepted methods; `OAuth2ClientAuthenticationFilter` and authentication providers validate the client before processing the token grant.
- **Client authentication is not user authentication**, does not replace PKCE, and does not by itself guarantee an access token can access a specific API.

Understanding both methods accurately keeps Spring Security OAuth2 Client and Spring Authorization Server configurations consistent, helps pinpoint `invalid_client` errors, enables meaningful integration tests, and supports secure credential operations.

## 16. References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): **$2.3.1 Client Password** (Basic and form body), $3.2.1 (client authentication), $4.4 (client credentials), $5.2 (token error).
- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): HTTP Basic structure; note the additional form-encoding rules from RFC 6749 for OAuth client secrets.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): modern OAuth 2.0 security best current practices.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE and its relationship to protecting the Authorization Code flow.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): token endpoint authentication and metadata related to OIDC clients.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): `RegisteredClient`, client authentication, endpoints, and security configuration.
- [Spring Security OAuth2 Client Reference](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration`, token requests, and client authentication configuration.
