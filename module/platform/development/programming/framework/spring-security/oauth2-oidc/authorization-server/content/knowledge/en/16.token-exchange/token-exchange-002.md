# Registering the `token-exchange` Grant for Authorized Clients

## 1. The Problem: Not Every Client Should Be Allowed to Exchange Tokens

In the **Token Exchange** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we explore how to design, configure, secure, test, and operate an Authorization Server based on **Spring Security**, **Spring Authorization Server**, and **Spring Boot**.

Suppose user Alice logs into `orders-web` to view orders. That application receives an access token for the orders API and then calls the `orders-aggregator` service. The aggregator service needs to call `reports-api` to compile reports, but the original access token has an audience intended for the first API and should not be forwarded unchanged to every other service.

**OAuth 2.0 Token Exchange (RFC 8693)** allows an OAuth client to submit a **subject token** to the Token Endpoint and, if approved by the Authorization Server, receive a **new token** better suited to the target, audience, scope, and authorization context.

However, this is a sensitive capability: if every client could submit any token it obtained and exchange it for a token with a broader audience, Token Exchange could become a bypass for privilege escalation. Therefore, two layers of defense are needed:

1. **Registration:** only clients registered with the `urn:ietf:params:oauth:grant-type:token-exchange` grant may initiate the flow.
2. **Per-exchange authorization policy:** after authenticating the client and validating the subject token, the server issues a token only if the client–subject–target–scope–actor relationship is permitted by policy.

**Registering the grant is a necessary condition, not a blank check to exchange any token for any audience.**

### Learning Objectives

Upon completing this lesson, you will be able to:

- Distinguish the client making the exchange request, the subject in `subject_token`, the actor, and the target Resource Server.
- Register the token exchange grant using `RegisteredClient` and `AuthorizationGrantType.TOKEN_EXCHANGE`.
- Understand the roles of `RegisteredClientRepository`, the Token Endpoint, and the converters/providers in Spring Authorization Server.
- Identify mandatory security conditions beyond simply granting the client the grant type.
- Send RFC 8693 requests, read responses, and recognize common errors.
- Design allowlist policies, scope downscoping, audience restrictions, and negative tests.
- Distinguish framework token-exchange handling support from **business-level delegation/impersonation authorization**.

## 2. Four Identities/Components to Distinguish

| Component | Example | Role in the exchange |
| --- | --- | --- |
| **Authenticated requesting client** | `orders-aggregator` | Client calling `/oauth2/token` that must be authorized to use the grant |
| **Subject token** | Alice's previous access token | Evidence of the subject/context the client wants to exchange |
| **Actor token**, if any | Token identifying an intermediary actor | Supports delegation models according to policy |
| **Target Resource Server** | `reports-api` | Where the new token is intended to be used; determines target audience/permissions |

An **authenticated** client at the Token Endpoint is not automatically authorized to act on behalf of **any** subject. Holding a subject token also does not mean the possessing client has the right to carry that token over to another target. The Authorization Server must evaluate both sources of information together.

### Commonly Confused Grants

| Grant | What does the client do? | Does the Resource Owner interact? | Distinguishing factor |
| --- | --- | --- | --- |
| `authorization_code` | Exchanges an authorization code after user consent | Usually yes | Requires code, callback, PKCE |
| `client_credentials` | Requests a token on behalf of the application | No | No subject token submitted for exchange |
| `refresh_token` | Requests a new access token from a refresh token | Not during the refresh call | Uses a token designated as a refresh token per policy |
| **Token Exchange** | Requests a new security token by presenting a subject token | Does not require browser interaction at the exchange call itself | `subject_token`, `subject_token_type`, and exchange policy |

Token Exchange is a **Token Endpoint extension grant**, not a new `response_type` at `/oauth2/authorize`. Nor does it automatically turn an M2M client into user Alice.

## 3. What Does RFC 8693 Require in a Token Exchange Request?

Token Exchange uses `POST /oauth2/token` with an `application/x-www-form-urlencoded` body and the full grant value:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

### Key Parameters Table

| Parameter | Required? | Meaning |
| --- | --- | --- |
| `grant_type` | Yes | Always the RFC 8693 token exchange URN |
| `subject_token` | Yes | Token representing the subject the client wants to base the exchange on |
| `subject_token_type` | Yes | Identifier for the **input token type**, e.g., access token |
| `requested_token_type` | No | Desired type of token to be issued; if omitted, RFC 8693 specifies a default |
| `audience` | No | Logical name of the intended recipient of the new token; may appear multiple times |
| `resource` | No | Target resource/service URI; may appear multiple times |
| `scope` | No | Desired scopes for the new token |
| `actor_token` | No | Token of the acting party in a delegation model |
| `actor_token_type` | Yes **when `actor_token` is present** | Identifier for the actor token type |

Common **token type identifiers**:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
```

**Distinguish three URN/type strings:**

- `urn:ietf:params:oauth:grant-type:token-exchange` is the **grant type** in `grant_type`.
- `urn:ietf:params:oauth:token-type:access_token` is a **token type identifier**, used for `subject_token_type` or `requested_token_type`.
- `Bearer` is an **access token usage scheme** commonly returned in `token_type`; it is neither a grant type nor an RFC 8693 token type identifier.

Minimal HTTP request example with a target:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64-of-exchange-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SUBJECT_ACCESS_TOKEN
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=reports-api
&scope=orders.read
```

`SUBJECT_ACCESS_TOKEN` and the Basic header above are illustrative placeholders. In real systems, use TLS, secure client credentials, valid input tokens, and policy-approved targets. RFC 8693 does not require a client to use `client_secret_basic`; that is simply the method chosen for our confidential client example. With `private_key_jwt` or mTLS, client authentication works differently.

### The Response Differs from a Standard OAuth Token Response

```json
{
  "access_token": "NEW_TARGET_ACCESS_TOKEN",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

In RFC 8693, `issued_token_type` is a **required** field describing the security token type issued. `refresh_token` is not issued by default: issuing a refresh token during an exchange requires a dedicated policy and is generally inappropriate when exchanging a short-lived credential for another target.

## 4. Processing Sequence When a Client Is Permitted to Exchange

```mermaid
sequenceDiagram
    autonumber
    actor U as User Alice
    participant Web as orders-web
    participant A as orders-aggregator
    participant AS as Spring Authorization Server
    participant Repo as RegisteredClientRepository
    participant API as reports-api
    U->>Web: Log in / request to view orders
    Web->>AS: Authorization Code + PKCE
    AS-->>Web: Subject access token
    Web->>A: Send request protected by source token
    A->>AS: Token exchange + client authentication
    AS->>Repo: findByClientId(orders-aggregator)
    AS->>AS: Valid client with TOKEN_EXCHANGE?
    AS->>AS: Verify subject token, target, scope, and actor if present
    AS->>AS: Apply delegation / impersonation policy
    alt Allowed
      AS-->>A: New token, audience targeted at reports-api
      A->>API: Call API with new token
      API->>API: Verify iss, aud, exp, scope, subject type
      API-->>A: Return authorized data
    else Denied
      AS-->>A: OAuth error; do not issue new token
    end
```

The diagram depicts the **target architecture**, which includes the exchange policy implemented by the system. Do not infer that configuring a grant on `RegisteredClient` automatically sets up all actor checks, multi-issuer trust, or target-service audience enforcement.

### An Important Note About `subject_token`

The source token may carry `sub=alice` while having been issued for a different audience. Simply because an intermediary received that token to serve an initial request **does not mean** it is authorized to submit that token to any Token Endpoint or turn it into an administrative token. The Authorization Server must verify the source token's signature/state, issuer, appropriate audience/usage, lifetime, allowed acting/exchanging client, and target policy.

**Issuing a new token does not automatically invalidate the source token.** Revocation, replay prevention, token chaining, and the TTLs of both tokens are separate design decisions that must be tested.

## 5. How Spring Authorization Server Supports the `token-exchange` Grant

According to official documentation:

- `AuthorizationGrantType.TOKEN_EXCHANGE` has been included in Spring Security since **6.3**; this constant maps to the RFC 8693 token exchange URN.
- Spring Authorization Server provides `OAuth2TokenExchangeAuthenticationConverter` and `OAuth2TokenExchangeAuthenticationProvider` starting in the **1.3** line and includes them in the Token Endpoint's default configuration on supported versions.
- With the default Token Endpoint configuration on a compatible version, **you do not need to write a custom converter/provider just to recognize the grant**. You must register clients allowed to use the grant, configure token sources, and add real-world policies as required by your system.

Older versions or custom configurations that replace the provider list may lack this processing path. Before implementing, verify your actual version and Spring Boot dependency management rather than mixing APIs from different Spring Security / Spring Authorization Server lines.

| Component | Responsibility |
| --- | --- |
| `RegisteredClient` | Declares which client **is allowed** to use `TOKEN_EXCHANGE`, authentication methods, scopes |
| `RegisteredClientRepository` | Looks up the registration by identified client ID |
| `OAuth2ClientAuthenticationFilter` and client authentication providers | Authenticates confidential clients using their registered method |
| `OAuth2TokenEndpointFilter` | Handles incoming HTTP POST token requests |
| `OAuth2TokenExchangeAuthenticationConverter` | Parses the token exchange request body |
| `OAuth2TokenExchangeAuthenticationProvider` | Processes the token exchange grant per version capabilities |
| `OAuth2AuthorizationService` | Looks up/persists authorization/token state managed by the AS |
| `OAuth2TokenGenerator` | Generates new tokens based on context and policy |
| System policy/extension | Controls which client may exchange which tokens, for which targets and scopes |

**Both layers must succeed:** *client authentication* verifies the client's credentials, while *grant authorization* verifies that the registration allows `TOKEN_EXCHANGE` and that the exchange policy approves the specific request.

## 6. Registering the Token Exchange Grant for an Authorized Client

### 6.1. Configuring Two Client Types with Different Permissions

In this example, `orders-web` is the client logging users in via the Authorization Code Flow. `orders-aggregator` is a confidential backend **only granted** the Token Exchange grant to obtain new tokens based on a subject token and policy.

```java
package com.example.authorization;

import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration
public class TokenExchangeClientConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(PasswordEncoder encoder) {
        RegisteredClient ordersWeb = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("orders-web")
                .clientSecret(encoder.encode("lab-orders-web-secret"))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://orders.example.com/callback")
                .scope("orders.read")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        RegisteredClient aggregator = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("orders-aggregator")
                .clientSecret(encoder.encode("lab-aggregator-secret"))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.TOKEN_EXCHANGE)
                .scope("orders.read")
                .build();

        return new InMemoryRegisteredClientRepository(ordersWeb, aggregator);
    }
}
```

**Explanation of each choice:**

- `AuthorizationGrantType.TOKEN_EXCHANGE` is the permission **to use the extension grant**; it is neither a scope nor a client authentication method.
- `CLIENT_SECRET_BASIC` requires the aggregator to prove its identity with a client secret when calling the Token Endpoint. Registering a client with only `client_id` and no proper authentication method is risky for a token-exchanging endpoint.
- `scope("orders.read")` bounds part of the permissions the client may request. It **does not** mean the aggregator can arbitrarily mint `orders.read` for any user.
- Aggregator is **not** configured with `AUTHORIZATION_CODE` or `CLIENT_CREDENTIALS`; therefore, it cannot use those grants simply by existing in the repository.
- `orders-web` does not have `TOKEN_EXCHANGE`; if `orders-web` itself attempts an exchange grant request, it must be rejected by registration checks.
- No redirect URI is declared for the aggregator because exchange occurs **back-channel** at the Token Endpoint without issuing authorization codes via a browser.

This snippet only creates an **illustrative `RegisteredClientRepository`**. To run a complete Authorization Server, the application also needs HTTP Security configuration, issuer settings, signing keys/JWKs, user authentication (for Authorization Code Flow), `OAuth2AuthorizationService`, and related services. **The registration above does not implement the cross-client exchange policy** between `orders-web` tokens and the aggregator; that policy must be defined and tested separately.

Do not use hardcoded secrets, IDs randomly generated on each restart, or an in-memory repository as a production registration source. In real deployments, use a secret manager, hashed secrets, and persistent storage via JDBC or an appropriate repository implementation.

### 6.2. Enabling the Grant for an Existing Registered Client

If `orders-aggregator` already exists in the repository and has been approved for Token Exchange, **preserve its internal ID** and only add the grant:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

public void enableTokenExchange(
        RegisteredClientRepository repository,
        String clientId) {

    RegisteredClient current = repository.findByClientId(clientId);
    if (current == null) {
        throw new IllegalArgumentException("Unknown client");
    }

    // The caller of this method must be pre-approved by the administration system.
    RegisteredClient updated = RegisteredClient.from(current)
            .authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)
            .build();

    repository.save(updated);
}
```

This is **internal administrative** code, not an endpoint for clients to self-enable grants. You need authentication, administrative authorization, auditing, approval workflows, and concurrency control before allowing registration changes. Keeping the internal ID prevents breaking references to stored authorization records.

**Schema note:** When using `JdbcRegisteredClientRepository`, grant types are stored according to the schema and serialization mapping of your running Spring Authorization Server version. Never guess column names or serialization formats; use the official schema and test upgrades.

### 6.3. Do Not Grant Token Exchange Broadly

A straightforward allowlist policy:

| Client | Grant `TOKEN_EXCHANGE`? | Reason |
| --- | --- | --- |
| `orders-aggregator` | **Yes**, after approval | Backend needs downstream tokens and holds protected credentials |
| `orders-web` | No, per example requirements | Only performs initial user login/authorization |
| `public-spa` | No | Cannot protect a shared secret; must not be granted exchange by default |
| `batch-export` | No, if `client_credentials` suffices | Has no need to exchange user subject tokens |
| Unknown client | No | Not registered |

Never put `TOKEN_EXCHANGE` into a shared registration template just because "the server supports it." Every approved client must have an **owner**, use case, trusted subject token source, valid target/audience, allowed scopes, delegation level, and periodic review schedule.

## 7. Distinguishing Grant Registration from Exchange Authorization Policy

Once a `RegisteredClient` has `TOKEN_EXCHANGE`, the Authorization Server must still verify:

1. Has the client authenticated using its registered method?
2. Is the subject token genuine, of the right type, within the right issuer/trust boundary, unexpired, and unrevoked?
3. Is this client allowed to exchange **tokens from this subject/issuer/source client**?
4. Is the target `audience` or `resource` on the allowlist for that client and context?
5. Are the requested scopes permitted by policy and within the source token's permissions?
6. Is an `actor_token` present? If so, is the actor trusted and authorized for delegation?
7. Do the new token's TTL, issuer, subject/actor, audience, scope, and format match the target Resource Server's contract?

If any condition fails, **do not issue a new token**.

### 7.1. A Concrete Allowlist Policy

Example business rules for `orders-aggregator`:

```text
requesting_client       = orders-aggregator
accepted_subject_issuer = https://auth.example.com
accepted_subject_client = orders-web
allowed_subject_types   = access_token
allowed_target_audience = reports-api
allowed_scopes          = {orders.read}
max_issued_ttl          = 5 minutes
actor_token             = unsupported in this lab
```

The policy must be held by the **server**, never trusting client-submitted values. If `subject_token` already has `orders.read`, the new token in this example may only request `orders.read` or an allowed subset; it must never add `orders.write`, `admin`, or `audience=billing-api`.

This is a **policy definition model**, not a built-in property automatically enforced by `RegisteredClient`. Different Spring Authorization Server versions may provide different extension points; when strict cross-client, actor, and audience checks are required, you must use appropriate Token Endpoint extensions/validation and token generators.

### 7.2. Example Policy Decision Function Over Verified Data

The following Java method illustrates a **unit-testable decision class**, not something that auto-registers with Spring Authorization Server:

```java
package com.example.authorization;

import java.util.Set;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

public final class ExchangePolicy {

    public record VerifiedSubject(
            String issuer,
            String originalClientId,
            String subject,
            Set<String> scopes) {
    }

    private static final Set<String> ALLOWED_SCOPES = Set.of("orders.read");

    private ExchangePolicy() {
    }

    public static boolean mayExchange(
            RegisteredClient requestingClient,
            VerifiedSubject subject,
            String requestedAudience,
            Set<String> requestedScopes) {

        if (requestingClient == null || subject == null
                || requestedAudience == null || requestedScopes == null) {
            return false;
        }

        if (!"orders-aggregator".equals(requestingClient.getClientId())) {
            return false;
        }
        if (!requestingClient.getAuthorizationGrantTypes()
                .contains(AuthorizationGrantType.TOKEN_EXCHANGE)) {
            return false;
        }
        if (!"https://auth.example.com".equals(subject.issuer())) {
            return false;
        }
        if (!"orders-web".equals(subject.originalClientId())) {
            return false;
        }
        if (!"reports-api".equals(requestedAudience)) {
            return false;
        }
        return !requestedScopes.isEmpty()
                && subject.scopes().containsAll(requestedScopes)
                && requestingClient.getScopes().containsAll(requestedScopes)
                && ALLOWED_SCOPES.containsAll(requestedScopes);
    }
}
```

**Trust boundary:** The `VerifiedSubject` object **must be constructed from a subject token already verified by the Authorization Server** (or from a trusted authorization record), never from client-supplied JSON/body fields and certainly not from an unverified Base64URL-decoded JWT. The function above does not check token signatures, expiration, revocation status, actors, or target resource URIs — those checks must live in the protocol-handling layer.

Because this is a standalone policy function, **merely adding this code to the project does not make the Token Endpoint enforce it**. You must wire the policy into the appropriate authentication provider or validation pipeline without bypassing default framework checks. Before issuing the new token, the AS must also govern claims/TTL/audience generation and never trust unverified request attributes.

### 7.3. `actor_token` Is Not a Way to Self-Grant Authority

RFC 8693 allows token exchange with an `actor_token` to describe the acting party. An exchange with **only a subject token** typically implies impersonation per the RFC examples; adding an actor token and an appropriate policy can express delegation.

Do not assume that simply passing `actor_token` and `actor_token_type` will automatically cause Spring Authorization Server to emit an `act` claim with the right delegation chain. Always verify exact version capabilities and implement the corresponding policy/claims logic. In this lab, **actor tokens are not yet supported**; requests carrying an actor token should be safely rejected unless a handling policy is in place.

### 7.4. Why `audience` and `resource` Need an Allowlist

A client can send `audience=billing-api` or `resource=https://internal-admin.example.com/`. That is merely the client's **request**, not proof that it is permitted to access that target. The AS must map valid targets to issued audiences, constrain scopes, and issue tokens only for targets approved by system owners.

Never build the JWT `aud` claim by blindly copying every `audience` or `resource` from the request without validation. The target Resource Server must verify the audience **on the signed token**; otherwise, exchanged tokens could be used across unintended services.

## 8. Hands-On Flow: Registered Client Performing an Exchange

### 8.1. Prerequisites

To test the following flow in an **isolated environment**, prepare:

- An Authorization Server at `https://auth.example.com` (or localhost over HTTPS) with `/oauth2/token` and appropriate signing keys.
- `orders-web` able to complete Authorization Code + PKCE and obtain a real **subject access token** for a test user.
- `orders-aggregator` as a confidential client registered with `TOKEN_EXCHANGE` and a valid secret/key.
- An exchange policy deployed allowing the aggregator to exchange tokens sourced from `orders-web` for audience `reports-api` with scope `orders.read`.
- A token generator producing the target token with controlled claims/audience/TTL, and `reports-api` configured to validate the token.

The last point is crucial: **the `RegisteredClient` snippet in Section 6 alone is not enough** to ensure cross-client exchange succeeds for every subject token type or emits the desired audience. Without policy and token generation configured, the example below may be **rightly rejected** by the server or fail to emit the claims you expect.

### 8.2. Sending the Token Exchange Request

Assume `SUBJECT_ACCESS_TOKEN` is a real access token issued via the Authorization Code Flow:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-orders-aggregator-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SUBJECT_ACCESS_TOKEN
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=reports-api
&scope=orders.read
```

In PowerShell, you can test with `curl.exe` using demo values from environment variables:

```powershell
# These variables must be provided securely in the lab environment.
# Do not save production secrets or access tokens to files/logs.
$subjectToken = $env:LAB_SUBJECT_ACCESS_TOKEN
$clientSecret = $env:LAB_EXCHANGE_CLIENT_SECRET

if ([string]::IsNullOrWhiteSpace($subjectToken) -or
        [string]::IsNullOrWhiteSpace($clientSecret)) {
    throw "LAB_SUBJECT_ACCESS_TOKEN and LAB_EXCHANGE_CLIENT_SECRET must be configured"
}

$responseJson = curl.exe -sS `
    -u ("orders-aggregator:" + $clientSecret) `
    -H "Content-Type: application/x-www-form-urlencoded" `
    --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" `
    --data-urlencode "subject_token=$subjectToken" `
    --data-urlencode "subject_token_type=urn:ietf:params:oauth:token-type:access_token" `
    --data-urlencode "requested_token_type=urn:ietf:params:oauth:token-type:access_token" `
    --data-urlencode "audience=reports-api" `
    --data-urlencode "scope=orders.read" `
    "https://auth.example.com/oauth2/token"

$result = $responseJson | ConvertFrom-Json
if (-not $result.access_token) {
    throw "Exchange failed; check the error code at the AS"
}
$issuedAccessToken = $result.access_token
$result | Select-Object issued_token_type, token_type, expires_in, scope
```

**Security limitations of this lab command:** depending on the OS, `curl.exe -u` and form bodies may appear in process arguments, runtime environments, and diagnostic history. For production, use an HTTP client with safer secret/token handling, enforce HTTPS, never enable verbose logging for credentials, and never print raw tokens.

### 8.3. Inspecting the Response and Target Token

A valid response looks like:

```json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

The new token must carry an audience and scope matching policy, for example:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-1042",
  "aud": ["reports-api"],
  "scope": "orders.read",
  "client_id": "orders-aggregator"
}
```

This is an **illustrative JWT payload**, not a complete set of required claims or default framework guarantees. `sub` and `client_id` in the new token must follow the issuer's contract for the approved exchange type. If policy requires a delegation model, reliable actor information and dedicated verification are needed rather than inferring it from the source token.

The **Resource Server** must validate signature/state, `iss`, `aud=reports-api`, token expiration, scopes, and subject/actor policy. Decoding a JWT to read its payload is not signature verification. Finally, `GET /api/reports` should return only data permitted by the target policy.

### 8.4. Inspect Both the Original Token and the Exchanged Token

| Attribute | Original token | Exchanged token |
| --- | --- | --- |
| Issuer | AS that issued the source token | AS issuing the target token; may be the same or different per supported architecture |
| Audience | Intended for the initial receiving API | Intended **only** for the approved target |
| Subject | Subject of the source authorization | According to the approved delegation/impersonation policy |
| Client ID | Client that received the source token | Client authenticated to request the exchange, per issuer contract |
| Scope | Permissions in the source token | Cannot exceed limits of the source token, client, and exchange policy |
| Lifetime | Source token TTL | TTL assigned independently per policy, usually short |
| Revocation status | Follows source token lifecycle | Follows issued token lifecycle; requires linked policy if propagation is needed |

**Do not assume** the exchanged token is guaranteed to keep the same `sub`, include an `act` claim, or use the same token format; those details depend on the exchange profile and specific policy. An Authorization Server should issue only token types and actor semantics it knows how to verify, mint, and protect properly.

## 9. Common Errors When Registering the Grant and Calling the Token Endpoint

A Token Endpoint error can occur **before** processing the subject token—during client authentication, grant authorization checks, or target policy evaluation. Separate the root cause so you never "fix" it by loosening client permissions.

| Error / response code | Typical condition | How to diagnose |
| --- | --- | --- |
| `invalid_client` | Wrong secret/key, wrong authentication method, unregistered client, or expired credential | Verify client registration, method, and credential in internal logs |
| `unauthorized_client` | Client authenticated successfully, but **lacks `TOKEN_EXCHANGE`** | Check `authorizationGrantTypes` for that exact client |
| `unsupported_grant_type` | Authorization Server does not support/enable token exchange in the running configuration/version | Check framework version and Token Endpoint converters/providers |
| `invalid_request` | Missing or malformed `subject_token`/`subject_token_type`, invalid actor pair, conflicting parameters | Check RFC 8693 compliance and request parser; never log tokens |
| `invalid_grant` | Invalid, expired, revoked, wrong-type, or ineligible subject token | Check input token validation and client/authorization bindings |
| `invalid_scope` | Requested permission outside policy/registration or not granted | Compare requested scope with source token, client scopes, and allowlist |
| `invalid_target` | Invalid or disallowed `audience`/`resource` target per RFC 8693 | Check allowed targets list and audience mapping |
| `server_error` | Internal failure such as data store, signing key, or generator error | Check AS monitoring; never fall back to issuing tokens without policy |

**Note:** Exact error codes, HTTP status codes, and messages can vary depending on the failing stage, Spring Authorization Server version, and custom policies. This table shows **standard/typical semantics**, not a guarantee that every case returns the exact same error string.

### 9.1. When a Request Is Denied Even Though the Client Has `TOKEN_EXCHANGE`

Verify step by step:

1. Did the client **authenticate successfully**?
2. Does the registration include `AuthorizationGrantType.TOKEN_EXCHANGE`, or only `AUTHORIZATION_CODE`/`CLIENT_CREDENTIALS`?
3. Was the subject token recognized and validated by the AS according to the **declared token type**?
4. Is the client trying to exchange an ID Token for an access token when the system only accepts subject access tokens?
5. Which client/issuer was the subject token issued for; does policy allow the current client to exchange it?
6. Do the target scopes exceed the source token's scopes or policy?
7. Are `audience`/`resource` valid and on the allowlist?
8. Is an actor token included when the deployment does not yet support actor semantics?
9. Did the generator produce the new token with the expected audience and format?

In particular, **resolving `unauthorized_client` by adding the grant** does not guarantee downstream steps are safe. After updating a registration, re-run both positive and negative tests to prove exchange privileges were not opened too broadly.

### 9.2. Dangerous Implementation Mistakes

| Anti-pattern | Risk | Better design |
| --- | --- | --- |
| Granting `TOKEN_EXCHANGE` to every client | Expands attack surface and subject token abuse | Allowlist by use case, owner, and target |
| Checking only `client_id` without client authentication | Any holder of a source token can attempt exchanges | Confidential client authentication, rate limiting, policy |
| Decoding the source JWT without verifying it and trusting `sub`/`scope` | Forged data is used to mint genuine tokens | Verify cryptographic signature, issuer, audience, TTL, state |
| Copying request `scope` straight into the target JWT | Arbitrary privilege escalation via parameters | Downscope/constrain by source, registration, and target policy |
| Copying `audience` without validation | Unauthorized tokens minted for sensitive APIs | Per-client target allowlists and mappings |
| Treating every source token as a user token | Confuses client subjects with user subjects | Check source token type, grant, and principal contract |
| Allowing multi-issuer exchange without explicit trust | Low-trust tokens get "upgraded" | Explicit issuer trust, signature/JWKS/introspection, per-issuer policy |
| Assuming `actor_token` automatically establishes safe delegation | Actor spoofing or missing audit trail | Explicitly implement and validate actor chains |
| Leaving target token TTL unbounded | New credential outlives acceptable window | Short TTLs with explicit revocation/expiry policies |
| Testing only that the target token request returns HTTP 200 | Fails to catch audience/type/scope escalation | Test token issuance plus Resource Server enforcement |

## 10. Testing Grant Registration and Authorization Policy

Test at least three distinct layers:

1. **Repository/registration:** only approved clients have `TOKEN_EXCHANGE`; other clients do not.
2. **Token Endpoint:** client authentication, source token validation, and policy enforcement work for both success and failure paths.
3. **Resource Server:** the new token works only at the intended target with valid audience, scope, and subject/actor policy.

### 10.1. Unit Test for `RegisteredClient`

The following JUnit 5 assertions verify the **necessary** condition at registration:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@SpringBootTest
class ExchangeRegistrationTest {
    @Autowired
    private RegisteredClientRepository clients;

    @Test
    void onlyAggregatorHasExchangeGrant() {
        RegisteredClient aggregator =
                clients.findByClientId("orders-aggregator");
        RegisteredClient web = clients.findByClientId("orders-web");

        assertNotNull(aggregator);
        assertNotNull(web);
        assertTrue(aggregator.getAuthorizationGrantTypes().contains(
                AuthorizationGrantType.TOKEN_EXCHANGE));
        assertFalse(web.getAuthorizationGrantTypes().contains(
                AuthorizationGrantType.TOKEN_EXCHANGE));
    }
}
```

**This example assumes the project includes `spring-boot-starter-test` and exposes `RegisteredClientRepository` as a Spring bean.** You can replace `@SpringBootTest` with a unit test instantiating an in-memory repository directly to reduce test overhead. Passing the registration test **does not prove the server authorizes token exchange for every target**.

### 10.2. Matrix of Positive and Negative Tests

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| EX-01 | Authenticated `orders-aggregator` with grant, valid subject token, approved target/scope | Issues new token per policy |
| EX-02 | `orders-web` submits an exchange request without the grant registered | Denied, typically `unauthorized_client` |
| EX-03 | Non-existent client ID | Client authentication/identification rejected |
| EX-04 | Wrong or expired aggregator secret | Client authentication rejected |
| EX-05 | Wrong URN in `grant_type` | Not processed as Token Exchange |
| EX-06 | Missing `subject_token` | Request rejected |
| EX-07 | Missing `subject_token_type` | Request rejected |
| EX-08 | Unsupported `subject_token_type` | Safely rejected; never assume every string is an access token |
| EX-09 | Forged signature on subject token | No token issued |
| EX-10 | Expired subject token | No token issued |
| EX-11 | Subject token revoked in server state | Rejected per source-token state policy |
| EX-12 | Source token from a client/issuer outside allowlist | No token issued |
| EX-13 | Requests `scope=orders.write` when source only has `orders.read` | Denied; never grants permissions exceeding source and policy |
| EX-14 | Requests `audience=billing-api` outside allowlist | No billing token issued |
| EX-15 | Attempts to set `resource` to a sensitive internal URL | No unauthorized target token issued |
| EX-16 | Sends `actor_token` when deployment does not support actors | Safely rejected |
| EX-17 | Sends `actor_token` without `actor_token_type` | Invalid request rejected |
| EX-18 | Exchanges the same source token repeatedly | Enforces replay/rate-limit/issuance policy; do not assume source token is consumed |
| EX-19 | Target token missing expected audience | Target Resource Server rejects it |
| EX-20 | Target token has valid signature but wrong scope | Target Resource Server rejects it |
| EX-21 | Target token expired or wrong issuer | Resource Server rejects it |
| EX-22 | Client sends `sub=admin` in an extra parameter | AS never mints an admin token; trusts only verified subject and policy |
| EX-23 | Exchange requests an unsupported target token type | Rejected; never converts arbitrary token types |
| EX-24 | Two AS instances handle exchange concurrently with shared repository | Consistent outcomes; no policy bypass under race conditions |

### 10.3. Testing Scope/Audience Boundaries with a Pure Policy

With the `ExchangePolicy` class from Section 7, you can test using a pseudo-fixture:

```java
RegisteredClient requestingClient = clients.findByClientId("orders-aggregator");

ExchangePolicy.VerifiedSubject validatedSource =
        new ExchangePolicy.VerifiedSubject(
                "https://auth.example.com",
                "orders-web",
                "user-1042",
                Set.of("orders.read"));

boolean permitted = ExchangePolicy.mayExchange(
        requestingClient, validatedSource, "reports-api", Set.of("orders.read"));

boolean wrongAudience = ExchangePolicy.mayExchange(
        requestingClient, validatedSource, "billing-api", Set.of("orders.read"));

boolean escalatedScope = ExchangePolicy.mayExchange(
        requestingClient, validatedSource, "reports-api", Set.of("orders.write"));

assertTrue(permitted);
assertFalse(wrongAudience);
assertFalse(escalatedScope);
```

This test sample needs a repository fixture and JUnit 5 / Java collection imports to run. Crucially, **`VerifiedSubject` in a unit test is simulated verified data**; Authorization Server integration tests must still verify that real data comes from cryptographically validated tokens that clients cannot forge.

## 11. Safely Deploying and Operating Token Exchange

### 11.1. Configuring the Token Endpoint by Framework Version

In Spring Authorization Server versions supporting Token Exchange, `OAuth2TokenEndpointFilter` registers the necessary converters and providers by default. Example **Authorization Server `SecurityFilterChain` skeleton**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer as =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(as.getEndpointsMatcher())
            .with(as, Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated());

    return http.build();
}
```

This is **not the entire Spring Boot configuration**: you still need `RegisteredClientRepository`, `AuthorizationServerSettings`, signing keys/JWKs, token/authorization services, and login mechanisms if other clients use Authorization Code Flow. For REST clients calling token exchange, proper client authentication must also be configured. Never open the token endpoint publicly just to "make 401 errors go away."

**Distinguish two different Spring modules:**

- **Spring Authorization Server (AS):** decides which clients may perform exchanges and what tokens are issued; uses `RegisteredClient.authorizationGrantTypes`, `OAuth2TokenExchangeAuthenticationProvider`, and policy.
- **Spring Security OAuth2 Client:** on the service initiating the exchange; provides `TokenExchangeOAuth2AuthorizedClientProvider` or `RestClientTokenExchangeTokenResponseClient` depending on version and integration style.

Configuring `OAuth2AuthorizedClientProvider` on a client **does not grant the flow** on the Authorization Server. Conversely, registering `TOKEN_EXCHANGE` on the AS **does not automatically make downstream services send token exchange requests**.

### 11.2. Adding Policy Without Breaking Default Validation

In compatible Spring Authorization Server versions, `OAuth2TokenEndpointConfigurer` allows configuring `authenticationProviders(...)` and related converters/providers. When custom policies are required, you can extend the **grant processing step** at this endpoint with an explicitly designed policy component.

Never write a custom authentication provider that merely checks `clientId` and immediately mints a JWT. That easily skips subject token validation, grant checks, token type checks, actor validation, scope limits, and revocation checks. A safe integration path should:

1. Preserve or carefully replace default client authentication and validation steps.
2. Verify the source token against allowed issuers and token types.
3. Read authorization/claims from a **trusted source**, never from unverified JWT decoding.
4. Run `ExchangePolicy` on the verified subject and the requesting client's registration.
5. Only when policy approves, generate the target token with explicit audience/scope/TTL/actor.
6. Emit audit logs and test every denial path.

Because hooking policies into providers can vary across versions, this lesson does not assume every application can install one generic interceptor and automatically satisfy all of RFC 8693. If your version/framework lacks required features, build an extension following official documentation and thoroughly test the protocol before production use.

### 11.3. Operating Multiple Authorization Server Instances

In multi-node deployments:

- Use a shared client registration repository and authorization store so instance A does not have the grant while instance B lacks it.
- Synchronize updates to target allowlists, issuer trust, and policy versions; account for cache invalidation.
- Manage signing keys/JWKs consistently; Resource Servers must be able to validate exchanged tokens issued by any node.
- Define how source token state is checked (offline JWT, introspection, authorization storage) and acceptable revocation latency.
- Set target token TTLs conservatively so privileges are not extended past the source's expiration or authorization window unless policy permits.
- Rate-limit exchanges per client/subject/target and monitor newly issued token volumes.

**Hard problem:** The source token is revoked after the target token has been issued. RFC 8693 does not automatically force target tokens to be revoked alongside the source. If business requirements demand immediate access cutoff, design **linked lifecycle/revocation** or online introspection; never assume deleting the source authorization makes every Resource Server reject the target token immediately.

### 11.4. Auditing, Observability, and Responding to Abuse Signals

A useful audit event may look like:

```json
{
  "event": "token_exchange_decision",
  "requesting_client_id": "orders-aggregator",
  "source_issuer": "https://auth.example.com",
  "source_subject_reference": "pseudonymous-subject-id",
  "target_audience": "reports-api",
  "requested_scopes": ["orders.read"],
  "policy_version": "exchange-policy-v3",
  "outcome": "allowed",
  "correlation_id": "request-trace-id"
}
```

This is a **custom example schema**, not Spring Authorization Server's default log output. **Never log raw subject tokens, actor tokens, newly issued tokens, client secrets, Basic headers, or full JWT payloads.** Subjects and audiences can still be sensitive, so audit access and retention must be controlled.

Alert when:

- Unapproved clients repeatedly attempt the `TOKEN_EXCHANGE` grant.
- A single client suddenly exchanges tokens for an unusual number of targets or subjects.
- Rates of `invalid_grant`, `invalid_target`, or `unauthorized_client` spike.
- Issued token counts exceed normal baselines.
- Source tokens from unknown issuers or untrusted actor chains appear repeatedly.
- Registration or policy changes expand grants, scopes, or audiences rapidly without approval.

### 11.5. Process for Changing Exchange Permissions

When granting or revoking `TOKEN_EXCHANGE`:

1. Identify the owner, business justification, client authentication method, source issuers, subject types, target audiences, and scopes.
2. Perform a security review and assess delegation/impersonation needs; never let every client exchange every subject token by default.
3. Test registration, positive paths, negative paths, concurrency, and expired/revoked source tokens.
4. Roll out policy and repository updates consistently across all AS instances.
5. Monitor the Token Endpoint and Resource Servers after deployment.
6. Audit changes; define how already-issued tokens will be revoked if an over-broad grant is discovered.

Removing `TOKEN_EXCHANGE` from a registration stops **new exchange requests** from that client; it **does not automatically invalidate** previously issued target tokens. Manage token lifecycles according to security requirements.

## 12. Design Exercise, Review Questions, and Checklist

### 12.1. Exercise: Two Backends Holding Subject Tokens with Different Permissions

You manage three components:

| Component | Function | Token Exchange need |
| --- | --- | --- |
| `orders-web` | User logs in to view orders | Does not need direct exchange |
| `orders-aggregator` | Calls `reports-api` in an authorized context | Approved for bounded exchange |
| `billing-admin-service` | Billing administration | Must never use order subject tokens to obtain billing tokens |

Requirements:

1. Register `orders-web` with `AUTHORIZATION_CODE`; register the aggregator with `TOKEN_EXCHANGE`.
2. Choose an appropriate client authentication method for the aggregator.
3. Design policies for source issuer, original client, target audience, and scopes.
4. Describe what happens if `billing-admin-service` attempts an exchange request even with a valid subject token.
5. Test an aggregator request with `scope=orders.write` and `audience=billing-api`; explain why it must be rejected.
6. Describe how `reports-api` verifies the target access token and how to handle revocation of the source subject token.
7. Design a test proving that adding the grant to `RegisteredClient` **does not** cause policy to automatically allow a new target.

### 12.2. Self-Check Questions

**Q1.** Is adding `authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)` alone enough for the aggregator to exchange any access token for a billing token?  
**Answer:** No. Grant registration only permits using the grant type; subject tokens, client–subject authorization, audience, and scopes must all be enforced by policy.

**Q2.** In Token Exchange, do `grant_type` and `subject_token_type` share the same URN?  
**Answer:** No. The grant is `urn:ietf:params:oauth:grant-type:token-exchange`; the access token type is `urn:ietf:params:oauth:token-type:access_token`.

**Q3.** Is a client that only has the `client_credentials` grant implicitly permitted to perform token exchange?  
**Answer:** No. It needs `TOKEN_EXCHANGE` on its `RegisteredClient` as well as satisfying the remaining policy checks.

**Q4.** Who determines the `aud` of the new access token?  
**Answer:** The Authorization Server, based on allowed targets and issuance policy; never blindly copy request `audience`.

**Q5.** Does adding `actor_token` automatically guarantee safe delegation?  
**Answer:** No. You must validate the actor token type, identity, delegation relationship, chain, and token claims per implemented policy.

**Q6.** Does exchanging a token automatically revoke the source token?  
**Answer:** Not by default. The lifecycles of source and target tokens must be designed separately, with linked revocation if business rules require it.

**Q7.** Why should Token Exchange generally not be enabled for public clients?  
**Answer:** Token Exchange allows minting new credentials from an existing token. If the caller is hard to authenticate or lacks strict policy, a stolen token could be leveraged to request target tokens; evaluate client characteristics and appropriate protections carefully.

### 12.3. Implementation Checklist

- [ ] Confirmed that the running Spring Security / Spring Authorization Server version supports Token Exchange.
- [ ] Granted `AuthorizationGrantType.TOKEN_EXCHANGE` only to approved clients.
- [ ] Authenticated requesting clients with their registered method over secure TLS.
- [ ] Validated subject tokens for issuer/trust, signature or introspection, expiration, state, and token type.
- [ ] Explicitly specified which source tokens and original clients are eligible for exchange.
- [ ] Accepted actor tokens only if implementation and policy fully support them.
- [ ] Allowlisted target audiences/resources; never copied raw request targets into JWTs.
- [ ] Constrained target token scopes within source token, client registration, and target policy limits.
- [ ] Governed new token TTL, token type/format, and claims.
- [ ] Configured target Resource Servers to validate signature/state, issuer, audience, scope, and subject/actor.
- [ ] Written positive and negative tests covering grant, client auth, source token, target, scope, and actor.
- [ ] Established a token revocation and abuse-investigation strategy.
- [ ] Ensured registration, policy, signing keys, and authorization state are consistent across nodes.
- [ ] Excluded client secrets and all raw tokens from audit logs.
- [ ] Assigned owners, approvals, rollback/recovery, and post-deploy monitoring for grant/policy changes.

### Memory Map

```text
RegisteredClientRepository
    |
    +-- orders-web
    |       grants: authorization_code, refresh_token
    |       NO token_exchange
    |
    +-- orders-aggregator
            grants: token_exchange
            client authentication: client_secret_basic
            scopes: orders.read
                    |
                    v
Token Endpoint: POST /oauth2/token
    grant_type = urn:ietf:params:oauth:grant-type:token-exchange
    subject_token + subject_token_type
    audience / resource / scope (+ actor if policy supports)
                    |
                    v
Client authentication + verify grant in RegisteredClient
                    |
                    v
Verify subject token and actor (if present)
                    |
                    v
Authorization policy: client x source x target x scope
                    |
             +------+------+
             |             |
           DENY          ALLOW
             |             |
        OAuth error     Issue new token
                          with valid aud/scope/TTL
                              |
                              v
                    Resource Server validates
```

**Conclusion:** To **register the `token-exchange` grant for an authorized client**, assign `AuthorizationGrantType.TOKEN_EXCHANGE` specifically to the appropriate `RegisteredClient` and configure strong client authentication. Then, separately enforce **authorization for each exchange request**: subject token, optional actor, source issuer/client, target, scope, token type, and TTL must all be governed by server policy. That boundary is what separates Token Exchange as a trustworthy delegation mechanism from an unintended privilege-escalation path.

## Authoritative References

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): grant URN, subject/actor tokens, targets, responses, delegation, and security considerations.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, grant types, and repository.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): default Token Endpoint converters/providers.
- [Spring Authorization Server — `OAuth2TokenExchangeAuthenticationProvider` API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationProvider.html): grant processing component.
- [Spring Security — `AuthorizationGrantType` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/AuthorizationGrantType.html): `TOKEN_EXCHANGE` constant and other grants.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/): client-side components for obtaining tokens, including Token Exchange in supported versions.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Token Endpoint, client authentication, extension grants, and protocol errors.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): validation requirements and trust boundaries for JWT access tokens using this profile.
