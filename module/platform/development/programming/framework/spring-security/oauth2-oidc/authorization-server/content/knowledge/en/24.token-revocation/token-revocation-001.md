# Purpose of OAuth2 Token Revocation

> **Chapter:** Revocation  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module Objective:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Example Scope:** OAuth 2.0 per RFC 7009 and Spring Authorization Server 1.x on the Servlet stack; API examples focus on the 1.5.x branch. Refer to the Javadoc of the library version being deployed.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why OAuth 2.0 needs a Token Revocation Endpoint and the risks it mitigates.
2. Distinguish between revoking an access token, a refresh token, an authorization grant, a login session, and OIDC logout.
3. Describe the RFC 7009 request/response, the meaning of `token_type_hint`, and how clients are authenticated.
4. Understand why the server returns HTTP 200 even when the token does not exist, has expired, or does not belong to the calling client.
5. Configure and test the Token Revocation Endpoint in Spring Authorization Server.
6. Understand the role of `OAuth2AuthorizationService` in storing token state and marking a token as invalidated.
7. Distinguish revocation effectiveness between self-contained JWTs and opaque/reference tokens validated via introspection.
8. Design cascade revocation between refresh tokens and access tokens according to RFC 7009 recommendations.
9. Build workflows for logout, compromised token handling, bulk revocation, and ensuring consistent state across multiple instances.
10. Test cases for valid tokens, nonexistent tokens, wrong client, already-revoked tokens, refresh rotation, and Resource Server caching.

**Key Takeaway:** OAuth2 Token Revocation allows a client to ask the Authorization Server to stop recognizing a token before it naturally expires. Marking a token as revoked in the AS only solves part of the problem; the Resource Server must have a way to become aware of that state. For JWTs verified completely locally, changes in the authorization database do not automatically invalidate an unexpired JWT immediately.

## 2. Why Is Token Revocation Needed?

Access tokens and refresh tokens have expiration times. If a token is leaked, a client is compromised, a user logs out, or access permissions change, waiting for the token to expire can be too long.

Example:

1. The `booking-bff` application receives an access token with a 30-minute TTL and a refresh token with a 7-day TTL.
2. The user logs out, or an administrator discovers that the refresh token has been copied.
3. If the AS has no revocation mechanism, anyone holding the refresh token can continue obtaining new access tokens until the refresh token expires.
4. The client sends a request to revoke the refresh token to the AS.
5. The AS authenticates the client, locates the corresponding authorization, and marks the token as revoked.
6. Subsequent refresh attempts must be rejected. Previously issued access tokens need to be handled according to the revocation policy and how the Resource Server verifies tokens.

The Token Revocation Endpoint is part of OAuth 2.0 to carry out steps 4 and 5 through a standard protocol.

### 2.1. Real-World Scenarios

| Scenario | Why Revocation Is Needed | Tokens Typically Affected |
| --- | --- | --- |
| User logs out of the application | Prevent the refresh token from continuing to mint new access tokens | Refresh token and, depending on policy, related access tokens |
| Device is lost | Prevent the device from continuing to use stored credentials | Refresh token/authorization of the device |
| Client secret or private credential is leaked | Prevent the client from continuing to use old tokens | Tokens/authorizations belonging to the client, along with credential rotation |
| Employee leaves the organization | Revoke permissions granted to the account | Grants/tokens related to the user |
| User revokes app consent/permissions | Stop the application from accessing data | Authorization grant and related tokens |
| Refresh token replay detected | Prevent a compromised token family from continuing to operate | The replayed token and tokens in the same family per policy |
| Significant tenant/role change | Prevent old tokens from retaining old permissions for too long | Tokens associated with the modified authorization |
| Security incident | Cut off access before tokens expire | Affected tokens, potentially the entire client/grant |

### 2.2. Revocation Is Not Deleting Tokens from the Client Device

A client may still hold the token string after the AS revokes it. Revocation cannot automatically delete copies in browser storage, mobile secure storage, logs, or memory.

The client must delete tokens from its local storage upon successful logout/revocation. The AS must stop accepting the token based on stored state and system policy.

### 2.3. Revocation Is Not an Authorization Check

Revoking a token prevents that token from being used further. It does not replace the Resource Server checking:

- Which issuer issued the token.
- Which audience/resource the token is intended for.
- Whether the token is still unexpired.
- Whether scopes/authorities are sufficient.
- Whether the user/client has permission for the specific data object.

An unrevoked token may still lack sufficient permissions to access an API. A revoked token must be rejected even if its signature and expiry are still valid.

## 3. OAuth 2.0 Token Revocation per RFC 7009

RFC 7009 defines an endpoint for clients to request that the AS revoke a token. The endpoint typically has the URL:

~~~text
/oauth2/revoke
~~~

The actual URL is published through the Authorization Server's metadata/configuration. Do not hardcode an assumed endpoint if the issuer metadata provides the official endpoint.

### 3.1. Basic Request

The client sends an HTTP POST with content type `application/x-www-form-urlencoded`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

Parameters:

| Parameter | Required? | Meaning |
| --- | --- | --- |
| `token` | Yes | Value of the access token or refresh token to be revoked |
| `token_type_hint` | No | Hint about the token type so the AS can look it up faster |
| `client_id` | Depends on client authentication method | Identifies a public client or a client not using HTTP Basic |
| Client authentication | Depends on client type | Proves the client is authorized to submit the revocation request |

`token_type_hint` is a hint, not proof of the token type. The AS may ignore the hint if it does not recognize it or cannot find the token under that hint, and then try other supported token types.

### 3.2. Common token_type_hint Values

RFC 7009 defines the following values:

- `access_token`
- `refresh_token`

Omitting `token_type_hint` does not mean the server cannot find the token. The AS can search across supported token types.

Do not use the hint to bypass checking which client owns the token. Token type and client revocation authorization are two independent checks.

### 3.3. Client Authentication

Confidential clients typically authenticate using their registered method, for example:

~~~http
Authorization: Basic <base64(client_id:client_secret)>
~~~

Public clients without a client secret must send `client_id` according to the applicable rules. The AS must establish the client context and only process requests consistent with policy.

If client A submits a token belonging to client B, the AS must not reveal whether that token exists. RFC 7009 requires responses not to help an attacker probe for another client's tokens.

### 3.4. Tokens Must Be in the Body, Not in the URL

Do not send tokens in the query string:

~~~http
# Avoid doing this
POST /oauth2/revoke?token=REFRESH_TOKEN_VALUE
~~~

Query strings are often recorded in access logs, reverse proxy logs, browser history, monitoring, and tracing. Send the token in the form body over HTTPS and configure request body redaction in intermediate components.

## 4. Response and Security Semantics of RFC 7009

### 4.1. Success Returns HTTP 200

When a revocation request is valid, the AS returns:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

The response body is typically empty. There is no `revoked: true` or `active: false` field in a revocation response.

Important point: the server returns HTTP 200 when the token has been revoked **or when the token does not exist, is invalid, or does not belong to the authenticated client**. This prevents the endpoint from becoming an oracle to probe whether someone else's token exists.

### 4.2. Why Does a Nonexistent Token Still Return 200?

Suppose an attacker has a guessable token string and sends it to the revocation endpoint. If the AS returned:

- `200` when the token exists.
- `404` when the token does not exist.

An attacker could use the response to test which tokens are active or belong to which account.

RFC 7009 chooses a success response for nonexistent tokens to reduce probing capability. Therefore, a client must not infer that a token was previously valid solely from HTTP 200.

### 4.3. Protocol Errors That May Still Return Errors

Request/authentication error cases may return an OAuth2 error:

| Error | Typical HTTP Status | Cause |
| --- | --- | --- |
| `invalid_request` | 400 | Missing `token` or malformed request |
| `invalid_client` | 401 | Invalid client authentication |
| `unsupported_token_type` | 400 | The AS does not support the requested token type per endpoint semantics |
| `server_error` | 500 | Internal error |
| `temporarily_unavailable` | 503 | The AS is temporarily unable to process the request |

Do not return `invalid_token` or `token_not_found` merely to reveal that a token does not exist. Cases where a token is unrecognized or does not belong to the authenticated client must be handled according to the RFC's privacy-preserving semantics.

### 4.4. How Should Clients Handle Responses?

- HTTP 200: treat the revocation request as processed per contract; clear local tokens as part of the logout flow.
- HTTP 400: fix the request, parameters, or token type hint if the error indicates an invalid request.
- HTTP 401: verify client credentials/mTLS/client authentication.
- HTTP 5xx: retry with appropriate backoff; do not log the token while diagnosing.
- Timeout: the outcome may be uncertain because the server might have revoked the token before the connection dropped. Retrying the request is safer if the endpoint handles retries idempotently per semantics.

Revocation should be safe to repeat: revoking an already-revoked token does not create new permissions and does not reactivate the token.

## 5. Access Tokens, Refresh Tokens, and Cascade Revocation

Revoking one token can affect other tokens generated from the same authorization grant.

### 5.1. Revoking a Refresh Token

When a refresh token is revoked:

- Subsequent refresh attempts using that token must fail.
- Per RFC 7009, if the AS supports access tokens, the AS **SHOULD** also revoke access tokens generated from the same authorization grant.
- If the authorization grant has multiple access tokens or refresh tokens due to rotation, the token family and related state need to be identified.

`SHOULD` in an RFC is a strong recommendation, allowing exceptions when documented reasons exist; in production systems, cascade behavior should be designed explicitly.

### 5.2. Revoking an Access Token

When an access token is revoked:

- The AS stops recognizing that token.
- RFC 7009 permits (MAY) the AS to revoke the corresponding refresh token used to create the access token.
- If the refresh token is not revoked, the client can obtain a new access token using the still-valid refresh token.

Therefore, when the goal is logout or incident response, revoking only the access token may not be enough. You must decide whether to also revoke the refresh token and the associated authorization grant.

### 5.3. Relationships Between Tokens

~~~mermaid
flowchart TD
    G["Authorization Grant<br/>User consent / client authorization"]
    C["Authorization Code"]
    A1["Access Token A"]
    R1["Refresh Token R1"]
    A2["Access Token B"]
    R2["Refresh Token R2<br/>after rotation"]
    G --> C
    C --> A1
    A1 --> R1
    R1 --> A2
    R1 --> R2

    R1 -.->|"Revocation per grant/family policy"| A1
    R1 -.->|"Cascade per RFC SHOULD"| A2
    R1 -.->|"Rotation/replay policy"| R2
~~~

This diagram only illustrates conceptual relationships. In practice, access tokens and refresh tokens may be created/stored within the same `OAuth2Authorization`, not every grant has a refresh token, and not every rotation implementation stores a separate token family.

### 5.4. Revoking a Token Does Not Automatically Delete the Entire Authorization

Different policies are possible:

- Revoke a single access token.
- Revoke the refresh token and its related access tokens.
- Revoke all tokens belonging to an authorization grant.
- Revoke all authorizations of a user for a client.
- Revoke all authorizations of a client when credentials are compromised.

RFC 7009 defines the endpoint around the submitted token. Extending that into logout-all-devices, revoke-all-client-grants, or user disabling is an application/AS policy that must be designed separately.

## 6. Spring Authorization Server Token Revocation Endpoint Implementation

### 6.1. Default Endpoint

Spring Authorization Server provides a Token Revocation Endpoint, typically at:

~~~text
POST /oauth2/revoke
~~~

Key components in the SAS 1.x branch include:

- `OAuth2TokenRevocationEndpointConfigurer`: DSL for configuring the endpoint.
- `OAuth2TokenRevocationEndpointFilter`: receives HTTP requests at the endpoint.
- `OAuth2TokenRevocationAuthenticationConverter`: converts the form request into an authentication request.
- `OAuth2TokenRevocationAuthenticationProvider`: verifies the token/client and processes revocation.
- `OAuth2AuthorizationService`: looks up and saves authorization/token state.

Package names and some extension points may vary by version; check the corresponding Javadoc before customizing.

### 6.2. SecurityFilterChain Configuration

Spring Authorization Server 1.x example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.tokenRevocationEndpoint(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

This example assumes the application already has required beans such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer/JWK configuration, and other chains for login/authorization endpoints. The Token Revocation Endpoint uses the client authentication context from the client authentication filters/providers configured in the AS.

In a standard configuration, the revocation endpoint is already part of the Authorization Server configurer. Calling `tokenRevocationEndpoint(Customizer.withDefaults())` makes the endpoint configuration site explicit; do not build a custom controller to handle token revocation instead of the framework.

### 6.3. Changing the Endpoint Path if Needed

`AuthorizationServerSettings` can configure the endpoint path per deployment:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .tokenRevocationEndpoint("/oauth2/revoke")
        .build();
}
~~~

This is a configuration fragment. If you change the path, update discovery metadata, API gateways, client configurations, firewall rules, monitoring, and integration tests. Do not let metadata advertise a URL different from the actual endpoint.

## 7. How Spring Authorization Server Processes Revocation

### 7.1. Finding the Token in the Authorization Store

After client authentication succeeds and the converter parses the request, the provider needs to:

1. Extract the token value and token type hint.
2. Find the authorization containing the corresponding token via `OAuth2AuthorizationService`.
3. Verify that the authorization belongs to the authenticated client.
4. Identify the token record and its current state.
5. Mark the token as invalidated in metadata/token state.
6. Save the updated authorization.
7. Complete the response according to RFC 7009 semantics.

Commonly used lookup API:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(token, tokenTypeHint);
~~~

Here `tokenTypeHint` can be `OAuth2TokenType.ACCESS_TOKEN` or `OAuth2TokenType.REFRESH_TOKEN`; whether the hint is null depends on the converter/request. The provider must handle unfound tokens using non-disclosing semantics.

### 7.2. The Authorization Record Is the Source of State

`OAuth2AuthorizationService` manages authorization state. When a token is revoked, the AS can store invalidation metadata corresponding to the token in the authorization.

At the model level, a token record can have attributes such as:

| Attribute | Meaning |
| --- | --- |
| Token value | The issued token value |
| Issued at | Timestamp of issuance |
| Expires at | Timestamp of expiration |
| Invalidated | Whether the token has been revoked/invalidated |
| Claims/metadata | Associated claims or metadata, if any |
| Authorization ID | The authorization/grant containing the token |
| Registered client ID | The client that received the token |

Do not write raw SQL updating an arbitrary column without understanding the schema and serialization of the implementation. Use `OAuth2AuthorizationService` to modify state through the model.

### 7.3. Storage Must Be Durable in Production

`InMemoryOAuth2AuthorizationService` is suitable for simple demos/tests. When the application restarts, in-memory data is lost; instances also do not share state.

Production should use durable persistence such as `JdbcOAuth2AuthorizationService` or another persistent implementation. Ensure:

- All AS instances read/write consistent authorization state.
- Transactions do not allow a success response while revocation state has not been persisted.
- Backup/restore does not unexpectedly resurrect revoked tokens.
- Lookups by token/index have adequate performance.
- Schema migrations preserve token state.
- Authorization caches do not serve stale state for too long.

### 7.4. Default Revocation Provider and Cascade Behavior

Do not assume every framework/version automatically revokes all related tokens according to your system's exact business policy. Verify the behavior of `OAuth2TokenRevocationAuthenticationProvider` in the SAS version you are running, specifically:

- When a refresh token is sent, are access tokens in the same authorization invalidated?
- When an access token is sent, is the refresh token invalidated?
- When a refresh token has rotated, are the old token and new token treated as the same family?
- How is a token not belonging to the authenticated client handled?
- Can an already-invalidated token be revoked again safely?

If product requirements call for RFC 7009 cascade behavior or revoking an entire token family, implement a clear policy around the authorization service/provider and write integration tests. Do not modify the database directly to bypass the SAS model.

## 8. Revocation Request Examples

### 8.1. Confidential Client Revoking a Refresh Token

~~~bash
curl --request POST \
  --user "booking-bff:CLIENT_SECRET" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "token=REFRESH_TOKEN_VALUE" \
  --data-urlencode "token_type_hint=refresh_token" \
  https://auth.example.test/oauth2/revoke
~~~

In production, do not put real secrets in shell history or CI logs. Use secret injection/credential stores, TLS, and redaction.

### 8.2. Revoking an Access Token

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_VALUE&token_type_hint=access_token
~~~

The AS authenticates the client, identifies the token, and applies revocation. The client must not expect to receive the active/inactive status of the token in the response.

### 8.3. Public Client

A public client without a secret can send `client_id` along with the token according to its registered authentication method:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

client_id=mobile-app&token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

The AS must bind the token to the identified client ID and apply the appropriate policy. Do not treat a client sending an arbitrary client ID as proof that it owns the token.

## 9. How Does Token Revocation Affect the Resource Server?

This is the most commonly misunderstood part.

### 9.1. Self-Contained JWTs and Local Verification

A Resource Server verifying JWTs locally typically performs:

1. Fetching the public key from JWKS.
2. Verifying the signature.
3. Checking issuer, audience, and expiration.
4. Mapping scopes/claims to authorities.

It does not query the AS's `OAuth2AuthorizationService` on every request. Therefore:

- The AS marks the JWT as revoked in the database.
- The RS can still verify the JWT's signature.
- `exp` has not passed and claims are still valid.
- The RS continues accepting the JWT unless additional revocation checks are in place.

**Revoking in the AS does not automatically invalidate self-contained JWTs across all Resource Servers immediately.**

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant DB as Authorization Store
    participant RS as Resource Server

    C->>AS: POST /oauth2/revoke + access token
    AS->>DB: Mark token invalidated
    AS-->>C: 200 OK
    C->>RS: API request + old JWT
    RS->>RS: Verify signature / iss / aud / exp locally
    Note over RS: Does not read revocation state from AS
    RS-->>C: May still accept until exp
~~~

### 9.2. Opaque/Reference Tokens and Introspection

With reference tokens, the RS typically calls the Introspection Endpoint. The AS reads the token state from the authorization store and returns `active`:

~~~json
{
  "active": false
}
~~~

After a token is revoked, introspection can return `active: false` and the RS rejects the token. This is a common way to achieve near-real-time revocation, depending on caching and store consistency.

If the RS caches an introspection response of `active: true` for 5 minutes, a revoked token may continue to be accepted during that cache window. Cache TTL is part of revocation latency.

### 9.3. Three Strategies for JWTs Needing Fast Revocation

| Strategy | How It Works | Trade-off |
| --- | --- | --- |
| Short access token TTL | JWTs expire quickly on their own | Not immediate revocation; clients refresh more frequently |
| Denylist/Revocation store | RS checks `jti` or token identifier in a store/cache | Requires online lookup and managing denylist data |
| Introspection/online authorization | RS queries the AS or a state service per request or with a short cache | Latency and dependency on AS availability |

You can combine a short TTL with event invalidation or a denylist. There is no way to make an already-issued JWT change its payload once it is on the client.

### 9.4. Caching Can Delay Revocation Effect

Even when using introspection:

- The RS may cache `active: true`.
- The gateway may cache authorization results.
- Services may maintain their own SecurityContext or session.
- Revocation events may arrive late or be lost.
- An in-flight request started before revocation may finish afterward.

Define the target clearly: whether revocation must take effect immediately, within a few seconds, or within at most a TTL window. For sensitive operations, an online authorization state check at execution time may be necessary.

## 10. Revocation, Logout, and Session Management

### 10.1. Logout Does Not Automatically Revoke Every Token

Application logout may involve several actions:

- Clearing the browser-side session cookie.
- Invalidating the server-side HTTP session.
- Deleting access/refresh tokens on the client.
- Calling the Token Revocation Endpoint for the refresh token.
- Revoking the authorization grant.
- Sending OIDC RP-Initiated Logout to the OP.
- Terminating the session at the identity provider.

These actions are not equivalent. Deleting a local cookie does not revoke a refresh token at the AS. Revoking a refresh token does not necessarily destroy the OP's browser session. OIDC logout does not automatically guarantee that all previously issued JWT access tokens are immediately rejected by the RS.

### 10.2. User Logging Out of a Single Device

A typical flow:

1. The client identifies the refresh token for the session/device to end.
2. Calls `/oauth2/revoke` with the refresh token and client authentication.
3. The AS marks the token as revoked and applies the cascade policy.
4. The client deletes local access/refresh tokens and related session state.
5. The RS detects the revoked token via introspection/denylist/TTL.
6. If using OIDC, the client performs RP-Initiated Logout when the OP session needs to end.

### 10.3. Logout All Devices

This is typically an extended business feature, not just a single RFC 7009 call. The system needs to locate all authorizations/grants belonging to a user, tenant, or client and revoke them according to policy.

An internal API may ask `OAuth2AuthorizationService` to find authorizations by principal/client and invalidate the related tokens. Authorization checks, auditing, transactions, and multi-instance consistency must be enforced.

Do not allow a mobile client to directly issue a "revoke all tokens of user X" command without proper authorization.

## 11. Refresh Token Rotation and Token Family Revocation

### 11.1. Rotation Creates Multi-Token State

When `reuseRefreshTokens(false)` is configured, the refresh flow can issue a new refresh token replacing the old one. The system must handle:

- Whether the old used refresh token is invalidated.
- Whether the new token belongs to the same authorization grant.
- How two concurrent requests using the same old token are handled.
- If the old token is replayed, whether the new token and access tokens in the same family are revoked.
- Which policy applies if the revocation endpoint receives the old token.

### 11.2. Replay Detection and Family Revocation

Example sequence:

~~~text
R1 --refresh--> A2 + R2
R1 is reused (replay)
=> detects that old credential was already consumed
=> revokes R2 and related access tokens per family policy
=> requires user/client to perform a new authorization
~~~

This is a common security policy with refresh token rotation. However, replay detection and family management depend on the authorization store/provider implementation. Do not assume that merely enabling `reuseRefreshTokens(false)` provides full token-family revocation.

### 11.3. Race Conditions

Two concurrent requests using R1 can arrive at two different AS instances at the same time. If storage lacks proper transactions/locking or compare-and-set, both may be processed inconsistently.

Tests should cover:

- One refresh request succeeds while the other is rejected.
- The old token cannot be reused after rotation.
- Revocation occurring concurrently with refresh does not allow a token to be unexpectedly re-issued.
- AS instances see the same updated state.
- Retries due to timeouts do not create an anomalous refresh chain.

## 12. Securing the Token Revocation Endpoint

### 12.1. Authenticate the Client Before Processing the Token

The revocation endpoint must use registered client authentication:

- `client_secret_basic`.
- `client_secret_post` if policy permits.
- `private_key_jwt`.
- mTLS client authentication.
- `none` for public clients via a supported mechanism.

Do not leave the endpoint as an anonymous API accepting any token and mutating system authorization state.

### 12.2. Verify Token Ownership

After authenticating the client, the AS must verify whether the token is associated with that client. Do not let client A revoke client B's token just because A knows the token string.

For tokens that do not exist or do not belong to the client, respond per RFC to prevent token enumeration. Do not return extra information such as user ID, owning client ID, or token expiration time.

### 12.3. TLS and Credential Protection

- Require HTTPS.
- Do not pass tokens in URLs/query strings.
- Do not log form bodies containing tokens.
- Redact `Authorization` headers, refresh tokens, and access tokens at proxies/APMs.
- Restrict read access to the authorization database.
- Protect the endpoint against brute-force/DoS with appropriate rate limiting.
- Use strong client authentication for confidential clients.
- Emit audit events without recording raw tokens.

### 12.4. Idempotency and Races

Revocation should be safe when the same token is submitted again:

- Active token: mark invalidated.
- Already invalidated token: do not resurrect the token.
- Token not found: respond per RFC semantics.
- Two concurrent revocation requests: final state remains invalidated.
- Revocation concurrent with refresh: transactions/locking must ensure tokens are not re-issued against policy.

Do not rely on a 200 response to assert that a specific token was found.

## 13. Testing the Token Revocation Endpoint

### 13.1. HTTP Test Matrix

| Test Case | Request | Expected Result |
| --- | --- | --- |
| Revoke valid refresh token | Valid client, active token, refresh hint | 200, token invalidated |
| Revoke valid access token | Valid client, active token, access hint | 200, token invalidated |
| Nonexistent token | Random token | 200 per RFC, non-disclosing |
| Already revoked token | Resubmit same token | 200, idempotent |
| Token owned by another client | Client A submits B's token | Non-disclosing, no unauthorized revocation |
| Missing token | Body without `token` | 400 `invalid_request` |
| Wrong client secret | Invalid Basic credentials | 401 `invalid_client` |
| Wrong type hint | Wrong/unrecognized hint | Server looks up other types or handles per RFC |
| Unsupported token type | Token type genuinely unsupported | Appropriate error, typically `unsupported_token_type` |
| Refresh after revoke | Attempt refresh with old token | Grant rejected |
| Revoked opaque access token | Introspection after revocation | `active: false` |
| Local JWT validation after revoke | RS only verifies JWT | May remain valid until expiry without online check |
| Cascade policy | Revoke RT | ATs in same grant handled per policy |
| Concurrent revocation | Two requests for same token | Final state remains invalidated |
| Refresh/revoke race | Two concurrent requests | No unauthorized token re-issuance |
| Audit/logs | Revocation request | No raw token in logs |

### 13.2. MockMvc Test Example

Example testing a confidential client revoking a refresh token:

~~~java
@Test
void revokeRefreshTokenReturnsOk() throws Exception {
    mockMvc.perform(post("/oauth2/revoke")
            .with(httpBasic("booking-bff", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("token", "known-refresh-token")
            .param("token_type_hint", "refresh_token"))
        .andExpect(status().isOk());
}
~~~

The test fixture needs:

- RegisteredClient `booking-bff` registered with the appropriate client authentication method.
- An authorization record containing refresh token `known-refresh-token`.
- An authorization service capable of finding the token and persisting invalidated state.
- The AS filter chain and revocation endpoint active.

**HTTP 200 alone does not prove the token was revoked**, because nonexistent tokens also return 200. You must read the authorization state or call the token/introspection endpoint to verify the token is no longer recognized.

### 13.3. Testing Token State via the Authorization Service

Integration test-style verification example:

~~~java
OAuth2Authorization authorizationBefore =
    authorizationService.findByToken(
        "known-refresh-token",
        OAuth2TokenType.REFRESH_TOKEN);

assertThat(authorizationBefore).isNotNull();

mockMvc.perform(post("/oauth2/revoke")
        .with(httpBasic("booking-bff", "test-only-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("token", "known-refresh-token")
        .param("token_type_hint", "refresh_token"))
    .andExpect(status().isOk());

OAuth2Authorization authorizationAfter =
    authorizationService.findByToken(
        "known-refresh-token",
        OAuth2TokenType.REFRESH_TOKEN);

assertThat(authorizationAfter).isNotNull();
assertThat(authorizationAfter.getRefreshToken().isInvalidated())
    .isTrue();
~~~

This is an illustrative example following the SAS 1.x model; depending on version, accessors and fixtures may need adjustment. If a provider deletes the record instead of retaining token metadata, the test must verify semantics through the appropriate API/service.

### 13.4. Testing a Client That Does Not Own the Token

Set up two clients A and B, each with its own token. Client A sends token B to the revocation endpoint:

- The endpoint still responds with non-disclosing semantics.
- Token B is not revoked by A's request.
- No response body reveals which client owns token B.
- Audit logs may record a generic outcome and the authenticated client A.

### 13.5. Testing Propagation to the Resource Server

For opaque tokens:

1. Call the API with an active token.
2. Revoke the token.
3. Call introspection and confirm `active: false`.
4. Call the API again and confirm the RS rejects it once cache expires/is invalidated.

For JWTs:

1. Call the API with a valid JWT.
2. Revoke at the AS.
3. If the RS only verifies locally, verify that the token may remain accepted until `exp`.
4. Enable a denylist/introspection/event strategy.
5. Confirm the RS rejects it within the defined revocation latency target.

Tests must reflect the real architecture rather than mocking the decoder to always return invalid after revocation and concluding that local JWTs have automatic revocation.

## 14. Operations and Observability

### 14.1. Audit Events

You can record the following fields:

- Timestamp.
- Correlation/request ID.
- Authenticated client ID.
- Token type hint.
- General outcome (processed/error).
- Error code if request malformed/client auth failure.
- Protected internal authorization/grant identifier, if needed for investigation.
- Request source (logout, admin, incident workflow).

Do not log raw access tokens, refresh tokens, authorization headers, or full request bodies.

### 14.2. Metrics

| Metric | Purpose |
| --- | --- |
| Revocation request count | Track volume |
| Revocation success/processing rate | Observe endpoint health |
| Invalid client rate | Detect credential/configuration issues |
| Revocation persistence latency | Measure state update duration |
| Introspection active/inactive count | Track validity at the RS |
| JWT denylist lookup/failure | Measure online revocation strategy |
| Revocation propagation delay | Measure time from AS revoke to RS deny |
| Refresh-after-revocation failures | Verify invalidated tokens are blocked |
| Concurrent refresh/revoke conflicts | Detect races |

Do not use token values as metric labels. Cardinality will explode and credentials risk exposure.

### 14.3. Revocation Latency Targets

Clearly define the time from when the AS confirms revocation to when all RS instances reject the token:

| Strategy | Typical Latency | Influencing Factors |
| --- | --- | --- |
| Local JWT + TTL | Up to token expiration | Access token lifetime, clock skew |
| JWT + denylist | Near real-time per store/cache | Event propagation, cache invalidation |
| Opaque + uncached introspection | Near real-time | Store consistency and network latency |
| Opaque + cached introspection | Up to cache TTL | Cache invalidation and refresh |
| Gateway-only revocation check | Depends on gateway | Paths bypassing gateway must be blocked |

These are architectural targets, not fixed guarantees of the RFC or framework. Sensitive APIs may require an online authorization state check per request.

## 15. Common Design Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Thinking HTTP 200 proves the token existed | Misunderstands RFC 7009 semantics | 200 does not disclose token state |
| Revoking refresh token without considering issued access tokens | Old access tokens may remain active | Design cascade/RS propagation |
| Thinking JWTs become invalid immediately when AS marks them revoked | Local RS still verifies signature and expiry | Introspection, denylist, or short TTL |
| Only deleting tokens on the client | Copied tokens remain usable | Call AS revocation and delete locally |
| Only deleting the session cookie | Refresh tokens may remain valid | Revoke tokens explicitly |
| Allowing Client A to revoke Client B's token | Cross-client denial of service | Check ownership/client binding |
| Passing tokens in URLs | Tokens leaked in logs/history | Form body over HTTPS |
| Logging the entire revocation request | Exposes refresh/access tokens | Redaction and audit metadata |
| Treating `token_type_hint` as truth | May miss tokens or mis-handle types | Hint is only for lookup optimization |
| Assuming SAS automatically cascades every token family | May miss required policy | Check provider version and test cascade |
| Using InMemoryAuthorizationService in production | Restarts/multi-instance lose state | Durable persistence |
| Caching introspection for too long | Slow revocation | TTL based on risk and invalidation |
| Not testing refresh/revoke races | Tokens may be re-issued unexpectedly | Transactions/locking and concurrency tests |
| Treating OIDC logout as access token revocation | APIs still accept old JWTs | Separate logout, session, and token revocation |
| Only asserting status 200 | Does not prove state changed | Verify authorization store/introspection/RS |

## 16. Self-Check Questions

**Question 1.** What is the main purpose of OAuth2 Token Revocation?

**Answer:** To allow a client to ask the AS to stop recognizing an access token or refresh token before it expires naturally, such as on logout, device loss, or credential compromise.

**Question 2.** Why does RFC 7009 return HTTP 200 when a token does not exist?

**Answer:** To prevent turning the endpoint into an oracle for attackers to probe tokens of other clients or users.

**Question 3.** Is `token_type_hint` required?

**Answer:** No. It is a hint to help the AS locate the token; it is not proof of token type and the AS can search other types.

**Question 4.** Does revoking a refresh token affect already-issued access tokens?

**Answer:** RFC 7009 strongly recommends that the AS revoke access tokens based on the same authorization grant when a refresh token is revoked. You should verify/implement cascade according to actual policy and version.

**Question 5.** Does revoking an access token require revoking the refresh token?

**Answer:** It is not required; the RFC allows the AS to revoke the corresponding refresh token. The decision depends on logout/incident goals.

**Question 6.** Why can a self-contained JWT still be usable after revocation?

**Answer:** The RS verifies signature and expiry locally without querying the invalidated state in the AS. A denylist, introspection/online check, or short TTL is needed.

**Question 7.** Why are opaque tokens easier to support near-real-time revocation with?

**Answer:** The RS typically introspects tokens with the AS; active/inactive state is read from the authorization store, provided caches do not hold stale results for too long.

**Question 8.** Is HTTP 200 from the revocation endpoint enough to test that a token has been revoked?

**Answer:** No. Nonexistent tokens also return 200. You must check authorization state, introspection, or RS behavior.

**Question 9.** Are logout and token revocation the same?

**Answer:** No. Logout may terminate sessions/cookies/OIDC OP sessions; revocation changes token state at the AS. A complete logout flow may need to perform both.

**Question 10.** If Client A sends Client B's token to the revocation endpoint, what should the AS do?

**Answer:** Do not revoke token B and do not disclose whether the token exists; respond according to RFC 7009 semantics.

## 17. Production Deployment Checklist

- [ ] Token Revocation Endpoint is enabled and its URL is accurately published.
- [ ] Requests use HTTPS, POST, and form body; tokens are never in the URL.
- [ ] Client authentication is configured per RegisteredClient.
- [ ] The AS verifies that the token belongs to the authenticated client.
- [ ] `token_type_hint` is treated as a hint, not a source of truth.
- [ ] Nonexistent/unowned tokens are handled with non-disclosing RFC 7009 semantics.
- [ ] Authorization store persists revocation state durably and shares it across AS instances.
- [ ] Refresh-token/access-token cascade behavior has been verified per RFC and SAS version.
- [ ] Refresh token rotation/replay has a clear family policy.
- [ ] Resource Servers have a strategy to detect revoked tokens.
- [ ] Local JWT validation is not mistaken for immediate revocation.
- [ ] Introspection/denylist cache TTL meets revocation latency targets.
- [ ] Logout distinguishes between sessions, refresh tokens, access tokens, and OIDC logout.
- [ ] Races between refresh and revocation are controlled.
- [ ] Auditing/metrics are in place without logging raw tokens or secrets.
- [ ] Tests cover active, revoked, nonexistent, wrong-client, malformed-request, cascade, and multi-instance cases.
- [ ] Runbooks exist for lost devices, token theft, client compromise, and logout-all-devices.

## 18. References and Conclusion

Standards and framework documentation:

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7009, Section 2 — Revocation Endpoint](https://www.rfc-editor.org/rfc/rfc7009#section-2)
- [RFC 7009, Section 2.1 — Revocation Request](https://www.rfc-editor.org/rfc/rfc7009#section-2.1)
- [RFC 7009, Section 2.2 — Revocation Response](https://www.rfc-editor.org/rfc/rfc7009#section-2.2)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — OAuth2TokenRevocationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenRevocationEndpointConfigurer.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)

**Conclusion:** OAuth2 Token Revocation provides a standard mechanism for clients to request that the AS stop recognizing a token before expiration. RFC 7009 intentionally returns HTTP 200 for nonexistent or unowned tokens to avoid leaking information. In Spring Authorization Server, the revocation endpoint works together with client authentication, the revocation provider, and the authorization service. To achieve real effectiveness, the system must also handle cascade between refresh and access tokens, persist state durably, and ensure Resource Servers recognize revoked tokens. In particular, locally verified self-contained JWTs do not automatically become invalid when the AS updates its database; introspection, a denylist, event invalidation, or a short TTL must be chosen based on the system's security and latency requirements.
