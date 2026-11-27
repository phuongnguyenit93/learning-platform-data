# 16.9. Handling `invalid_client`, `invalid_scope`, and Permission Boundaries

## 1. Problem: Service Cannot Obtain an Access Token or Is Denied API Access

In **Spring Security OAuth 2.0 OIDC Client**, the **Client Credentials** grant lets a backend service request an Access Token using **the client's own** credentials rather than through a user logging in on a browser. This is a common pattern for data processing jobs, system integrations, scheduled synchronization, and machine-to-machine (M2M) requests.

For example, the `report-exporter` service calls a reporting API every hour:

~~~text
report-exporter (OAuth2 Client)
    |
    | POST /oauth2/token
    | grant_type=client_credentials
    | client authentication
    | scope=reports.read
    v
Authorization Server
    |
    | access_token
    v
report-exporter
    |
    | GET /api/reports
    | Authorization: Bearer <access_token>
    v
Reports Resource Server
~~~

When everything aligns, the client receives an Access Token and sends it to the appropriate API. In practice, two very different failure groups occur:

1. **The Token Endpoint refuses to issue a token**, typically returning a JSON OAuth 2.0 error such as `invalid_client` or `invalid_scope`.
2. **A token was issued, yet the Resource Server rejects the request**, possibly returning HTTP `401` or `403`, for instance due to an expired Access Token, wrong audience, missing scope, or API policy denial.

These two groups require different diagnostics and handling. **Never try to fix `invalid_client` by adding scopes**, and never try to solve an HTTP 403 from the API by rotating the Client Secret when the real issue is insufficient permissions.

Lesson objectives:

- Understand the exact meaning of `invalid_client` and `invalid_scope` in the **Client Credentials grant**.
- Distinguish HTTP status codes, OAuth error codes, Bearer challenges, and API policies.
- Configure client authentication, token URIs, and scopes in Spring Security Servlet/backend applications.
- Handle errors through `OAuth2AuthorizedClientManager` without exposing credentials or retrying uncontrollably.
- Design minimal scopes, proper audience/resource targeting, and permission separation across services.
- Establish a troubleshooting workflow, observability, and test suite for M2M systems.

## 2. Client Credentials Is Not User OIDC Login

Before analyzing errors, identify the active grant:

| Property | Client Credentials | Authorization Code + OIDC Login |
| --- | --- | --- |
| Authorized principal | Application/client or service identity | User and authorized client |
| Browser redirect | Not needed | Yes |
| Authorization code | None | Yes |
| `state` and PKCE | Not used for this basic grant | Used to bind the transaction per config |
| `nonce` / ID Token | Not a standard part of Client Credentials | Related to OIDC authentication |
| Token Endpoint | Yes, using `grant_type=client_credentials` | Yes, using `grant_type=authorization_code` |
| Refresh Token | Per OAuth 2.0, usually **should not be issued** for Client Credentials | May be issued depending on provider/scope/policy |
| How new tokens are issued | Execute a new Client Credentials grant | Refresh Token grant or ask user to re-authorize |

**Client Credentials does not authenticate an end-user.** If a downstream API needs to know “which user is viewing the report,” a client credentials token alone does not supply that delegated user context. Never use a service token's `sub` or a simulated employee email to turn a machine identity into a user identity.

The module name includes OIDC because a Spring Security application can support both OAuth2 Client and OIDC Login, yet **Client Credentials is an OAuth 2.0 grant** that does not involve an ID Token or UserInfo.

## 3. Standard Token Request and Token Response

### 3.1. Request from a Confidential Client

A Token Endpoint request sent directly from the backend:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.net
Authorization: Basic <BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=reports.read
~~~

This is an **illustrative** request. Never put real client secret strings into documentation, logs, or repositories.

Explanation:

- `grant_type=client_credentials` selects the grant type.
- `scope` is an optional parameter requesting only the permissions needed for the job.
- With `client_secret_basic`, the client authenticates at the Token Endpoint via HTTP Basic Authentication.
- The Authorization Server validates client credentials, allowed grants, granted scopes, and other policies before issuing a token.
- The entire request must run over **HTTPS with TLS validation**.

If the client uses `private_key_jwt`, mTLS, or another authentication method, the request format differs. Do not change the client authentication method arbitrarily because each registration at the Authorization Server has an explicit contract.

### 3.2. Success Response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

Per OAuth 2.0, a success response contains `access_token` and `token_type`; `expires_in` states the Access Token's lifetime **in seconds** when returned. `scope` in the response, if returned, indicates the granted scope per OAuth 2.0 rules. **Do not assume every requested scope was granted** if the provider returns a different response than expected.

Refresh Tokens are generally not the default mechanism for Client Credentials; the client requests a new Access Token by authenticating again at the token endpoint. If a provider has a custom extension, read its specific contract rather than assuming it is standard behavior.

### 3.3. Error Responses

Example when the Token Endpoint rejects client authentication:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="token"
Cache-Control: no-store

{
  "error": "invalid_client"
}
~~~

Or when requesting a disallowed scope:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_scope",
  "error_description": "Requested scope is not allowed"
}
~~~

These responses are **examples**, not guarantees that every provider returns the same HTTP status, headers, or error descriptions. To classify errors, examine the **OAuth error code** and actual context rather than relying solely on HTTP status numbers.

**Never print raw `error_description` strings into UIs or production logs**: it is an externally supplied string that may contain internal details, sensitive data, or untrusted content.

## 4. `invalid_client`: The Authorization Server Rejects the Client Identity

### 4.1. Exact Meaning

In OAuth 2.0, `invalid_client` indicates **client authentication failed**—for example, unknown client, wrong credentials, improper client authentication delivery, or an unsupported authentication method.

With Client Credentials, this error occurs **at the step where the client proves its identity to the Token Endpoint**, before even considering which APIs the token can call.

Specific causes:

| Cause | Example |
| --- | --- |
| Wrong Client ID | Using a staging environment ID against the production Authorization Server |
| Wrong or rotated Client Secret | Service still uses the old secret after a rotation |
| Wrong client authentication method | Provider expects `client_secret_basic`, client sends `client_secret_post` form body |
| Wrong Token Endpoint / tenant | Client registered in realm A, calling `token-uri` of realm B |
| Client disabled | Service account locked, expired, or not yet activated |
| Invalid client certificate / JWT assertion | Expired mTLS cert or `private_key_jwt`, wrong issuer/audience, key, or assertion |
| Malformed header/encoding | Incorrectly constructed Basic header, improper client ID/secret encoding |
| Secret injection failure | Empty env var, missing secret mount, or unresolved config placeholder |

Some providers also use custom error codes for policies or similar situations. Always check Authorization Server documentation and audit events when determining the root cause.

### 4.2. Does HTTP 401 Always Mean `invalid_client`?

No. HTTP 401 **at the Token Endpoint** often relates to client authentication. If the OAuth response contains `invalid_client`, that error code confirms it. By contrast, HTTP 401 **from a Resource Server** during an API call usually refers to the **Access Token**, not client authentication at token issuance.

~~~text
POST https://auth.example.net/oauth2/token
  -> 401 + error=invalid_client
  => Check client authentication / token endpoint.

GET https://api.example.net/reports
  -> 401 + WWW-Authenticate: Bearer error="invalid_token"
  => Check the Access Token sent to the API.
~~~

Do not confuse the two requests just because both return 401.

### 4.3. How to Handle `invalid_client`

An ordered investigation sequence:

1. Verify that the **`registrationId` and `token-uri`** used by the app belong to the same Authorization Server/tenant as the client registration.
2. Confirm the **`client-authentication-method`** registered on the Authorization Server and configured in Spring Security.
3. Verify the **secret source** is working, without printing the secret to inspect it.
4. Check whether the client was disabled, deleted, revoked, or had credentials rotated.
5. If using a private key or mTLS, check certificate, key ID, assertion audience, timestamps, and trust chain.
6. Inspect Authorization Server logs using a safe **correlation ID** or request ID.
7. Fix the configuration/credentials before issuing a new token request.

**Never retry `invalid_client` infinitely.** If the secret is wrong or the client is disabled, rapid retries only add load and can trigger rate limiting or account lockout.

### 4.4. Do Not “Fix” `invalid_client` by Loosening Permissions

Expanding scope from `reports.read` to `reports.read reports.write` **will not fix** wrong client credentials. Likewise, switching to `client_secret_post` without a matching provider contract neither fixes the root cause nor is safe, as it increases the risk of secret exposure in certain observability layers.

Downgrading to a weaker authentication method or disabling TLS validation simply because the Token Endpoint returns `invalid_client` is **unacceptable**.

## 5. `invalid_scope`: The Client Requests an Invalid or Disallowed Scope

### 5.1. Meaning in OAuth 2.0

`invalid_scope` occurs when the requested scope is **invalid, unknown, malformed, or exceeds what the Authorization Server permits**.

For instance, client `report-exporter` is permitted:

~~~text
reports.read
metrics.read
~~~

Yet the request sends:

~~~text
scope=reports.read reports.admin
~~~

If `reports.admin` does not exist or is not granted to the client, the Token Endpoint may return:

~~~json
{
  "error": "invalid_scope"
}
~~~

This error concerns **the permissions requested at the Authorization Server**, and does not mean the client ID/secret is wrong.

### 5.2. Common Causes

| Cause | Example |
| --- | --- |
| Typo in scope name | `report.read` instead of `reports.read` |
| Scope not published by provider | Client requests `billing.export`, but Authorization Server only supports `billing.read` |
| Scope exists but is not granted to client | Service requests an admin scope outside allowed scopes |
| Scope meant for a different grant/client type | Scope allowed only for delegated users, not `client_credentials` |
| Wrong tenant/environment | Scope exists in staging, not yet created or enabled in production |
| Wrong parameter formatting | Scope passed as a JSON array or joined with the wrong delimiter |
| Default scopes changed | App sends no scope; Authorization Server applies an incompatible new default |
| Governance policy changed | Administrator removed an allowed scope from the client |

In standard OAuth 2.0 usage, `scope` in a token request is a **space-delimited string**, not a JSON array. With `application/x-www-form-urlencoded`, spaces must be properly encoded over HTTP.

### 5.3. `invalid_scope` Is Not Necessarily an API 403

Compare:

~~~text
Client requests disallowed scope:
  POST /oauth2/token
  scope=reports.admin
  -> HTTP 400 + error=invalid_scope

Client successfully requests token:
  scope=reports.read
  -> Access Token issued.

Client uses token having only reports.read to delete a report:
  DELETE /api/reports/123
  -> HTTP 403, possibly with insufficient_scope
~~~

`invalid_scope` happens when **requesting a token**. `insufficient_scope` typically relates to the **Resource Server rejecting a Bearer Token** for lacking permission for a specific operation. Both errors can stem from the same policy, yet occur at different protocol stages.

### 5.4. How to Handle `invalid_scope`

1. Confirm the scope name and registered policy at the Authorization Server.
2. Check whether that scope is permitted for the **Client Credentials grant**.
3. Compare the configured application scopes against the **minimum scopes** the API actually needs.
4. If a scope is no longer granted, either **remove the dependent feature** or request formal administrator approval.
5. Never automatically replace `reports.read` with `reports.admin` or `*`.
6. If multiple functions need different permissions, consider separating client registrations or service identities.
7. Track scope changes as configuration/authorization policy changes, backed by integration tests against the target API.

For non-interactive services, **there is no user consent screen to resolve `invalid_scope`**. An Authorization Server administrator or API permission owner must update the client registration/policy through proper governance.

## 6. Permission Boundaries: Receiving a Token Does Not Grant Full Access

Client Credentials authenticates the client and may yield a token for a specific resource. The Resource Server still decides whether the token has sufficient authority for an operation based on scope, audience, issuer, and business policies.

### 6.1. Four Boundaries Not to Mix

| Boundary | Question | Example |
| --- | --- | --- |
| **Client authentication** | Did the client prove its identity to the Token Endpoint? | Valid secret/certificate |
| **Grant permission** | Is the client allowed to use `client_credentials`? | Registration permits that grant |
| **Scope/audience issuance** | Did the Authorization Server issue a token for the requested scope and API? | `reports.read` for Reports API |
| **Resource Server authorization** | Is this specific token allowed to read/modify this data? | GET allowed, DELETE denied |

A client with a valid secret **does not automatically** hold `reports.admin`. An Access Token with scope `reports.read` **cannot automatically** be used on the Billing API. And a valid Reports API token can still be denied by resource-level policies.

### 6.2. Minimum Scope

For a job that only exports reports, the scope can be:

~~~text
reports.read
~~~

Never grant by default:

~~~text
reports.read reports.write reports.delete users.admin
~~~

just in case “we might need it later.” Every extra scope increases the blast radius if a secret or token leaks.

**Least privilege** applies on both sides:

1. The Client **requests** only needed scopes.
2. The Authorization Server **permits** only scopes appropriate for that service identity.
3. The Resource Server validates tokens and enforces policies per actual resource.

### 6.3. Audience/Resource Matters Just as Much as Scope

Example:

~~~text
Access Token A:
  issuer   = company-auth
  audience = reports-api
  scope    = reports.read

Access Token B:
  issuer   = company-auth
  audience = billing-api
  scope    = billing.read
~~~

Even if two APIs share identical scope names, an Access Token intended for API A must not be accepted automatically by API B. For JWT Access Tokens, the Resource Server must verify signature, issuer, audience, expiration, and scope/policy per contract. For opaque tokens, use introspection or provider-appropriate validation.

**OAuth2 scope does not replace audience.** Never rely solely on scope strings to send a token to any service with a different hostname.

Some providers use a dedicated `resource` or `audience` parameter when issuing tokens. This depends on extensions/provider contracts; configure it only when supported by the Authorization Server and required by integration docs.

### 6.4. Internal Roles Do Not Automatically Become Scopes

A web application might hold `ROLE_ADMIN` in `Authentication` after OIDC Login. That **does not give Client Credentials grant Access Tokens extra scopes** or allow a service token to call admin APIs.

Conversely, a client credentials token carrying `reports.read` does not prove a specific human user has `ROLE_READER` in the portal. These are two authorization concepts at different layers.

## 7. Configuring Spring Security for Client Credentials

### 7.1. Dependencies

For Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

If the application includes Spring MVC/Servlet controllers, add the appropriate web/security starters. In Spring Boot 4.x, Spring Security starters are modularized; pick dependencies matching your project's Spring Boot BOM/version. The Java examples below use standard OAuth2 Client APIs common in Spring Security 6.x.

### 7.2. `application.yml`

Example of a backend exporter:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Notes:

- `reports-service` is the **registration ID** referenced in Java code.
- `company-auth` defines the provider/token URI configuration.
- `client_secret_basic` must match the method registered on the Authorization Server.
- `client_credentials` needs no `redirect-uri`, `authorization-uri`, `state`, or `nonce` for this basic grant.
- `scope` is restricted to `reports.read` instead of requesting broad permissions.
- The client secret is not written literally in YAML; it comes from an appropriate secret manager/environment.
- Token URI must come from trusted config, never from user HTTP input.

### 7.3. Two Registrations for Two Different Permission Groups

If the application genuinely has two independent tasks:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-reader:
            provider: company-auth
            client-id: ${REPORTS_READER_CLIENT_ID}
            client-secret: ${REPORTS_READER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.read]
          billing-reader:
            provider: company-auth
            client-id: ${BILLING_READER_CLIENT_ID}
            client-secret: ${BILLING_READER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [billing.read]
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

This is an **alternative illustrative configuration** to the `reports-service` example, not a snippet to append on top of the previous YAML. Separating client identities allows independent permission granting/revocation and rotation when Authorization Server policies permit.

**You do not need a new client registration for every HTTP endpoint**; separation depends on trust boundaries, data sensitivity, and operational needs. Still, avoid a single client ID holding full permissions across unrelated APIs when a safer alternative exists.

## 8. `OAuth2AuthorizedClientManager` for Service-to-Service Calls

For Client Credentials running in scheduled jobs or services without a Servlet request, `AuthorizedClientServiceOAuth2AuthorizedClientManager` is the right choice.

### 8.1. Configuring the Manager

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ServiceOAuth2ClientConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            serviceAuthorizedClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Key points:

1. `clientCredentials()` enables the manager to request Access Tokens using that grant.
2. `OAuth2AuthorizedClientService` retains issued authorized clients for reuse by registration and principal name.
3. When a token expires or needs re-issuance, the manager collaborates with the provider to call the Token Endpoint.
4. No `HttpServletRequest` is required, fitting backend jobs.
5. Do not add `refreshToken()` merely wanting to “refresh” client credentials: this grant normally requests a **new token via client authentication**, without relying on a Refresh Token.

### 8.2. Calling `authorize()` with a Stable Service Principal

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-service")
        .principal("system-report-exporter")
        .build();

OAuth2AuthorizedClient authorizedClient =
    serviceAuthorizedClientManager.authorize(request);

if (authorizedClient == null) {
    throw new IllegalStateException(
        "Unable to obtain authorized client for reports-service");
}

// Use authorizedClient.getAccessToken() on the backend only.
~~~

Here `serviceAuthorizedClientManager` is dependency-injected into the calling class. `system-report-exporter` is a principal **serving as the service's storage key**, not an End-User authenticated by OIDC.

If you change the principal name randomly on each call, the manager will fail to locate the cached authorized client and keep re-issuing tokens. Use a stable namespace, separate true service identities, and never derive the principal from user input.

### 8.3. Saving a Token Does Not Mean It Works Everywhere

`OAuth2AuthorizedClientService` can load an issued client by `registrationId + principalName`, yet finding an Access Token **does not prove the Resource Server accepts it**.

~~~text
authorizedClient != null
  -> token record exists
  -> check lifecycle/grant via manager
  -> send token to API with right audience/scope
  -> API may still deny per policy.
~~~

## 9. Catching and Classifying OAuth2 Token Endpoint Errors

Spring Security may surface OAuth2 errors via `OAuth2AuthorizationException` or a related exception depending on layer/version. The OAuth2 error code is typically available via `OAuth2Error.getErrorCode()`.

### 9.1. Example Service Classifying `invalid_client` and `invalid_scope`

~~~java
package com.example.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.stereotype.Service;

@Service
public class ReportServiceTokenProvider {

    private static final Logger log =
        LoggerFactory.getLogger(ReportServiceTokenProvider.class);

    private final AuthorizedClientServiceOAuth2AuthorizedClientManager manager;

    public ReportServiceTokenProvider(
            AuthorizedClientServiceOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient requireAuthorizedClient() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-service")
                .principal("system-report-exporter")
                .build();

        try {
            OAuth2AuthorizedClient client = manager.authorize(request);
            if (client == null) {
                throw new IllegalStateException(
                    "Unable to issue token in current context");
            }
            return client;
        } catch (OAuth2AuthorizationException exception) {
            String code = exception.getError().getErrorCode();

            if ("invalid_client".equals(code)) {
                log.warn(
                    "OAuth2 M2M token request rejected: invalid_client; registration=reports-service");
                throw new ServiceCredentialException(
                    "Invalid OAuth2 client authentication configuration",
                    exception);
            }

            if ("invalid_scope".equals(code)) {
                log.warn(
                    "OAuth2 M2M token request rejected: invalid_scope; registration=reports-service");
                throw new ScopePolicyException(
                    "Requested scope not accepted by Authorization Server",
                    exception);
            }

            log.warn(
                "OAuth2 M2M token request failed; registration=reports-service; errorCode={}",
                safeCode(code));
            throw new UpstreamAuthorizationException(
                "Unable to obtain Access Token from Authorization Server",
                exception);
        }
    }

    private static String safeCode(String code) {
        if (code == null) {
            return "unknown";
        }
        return switch (code) {
            case "invalid_request", "unauthorized_client",
                 "unsupported_grant_type", "invalid_grant",
                 "server_error", "temporarily_unavailable" -> code;
            default -> "other";
        };
    }
}
~~~

**This is an illustrative handling structure:** `ServiceCredentialException`, `ScopePolicyException`, and `UpstreamAuthorizationException` are **project-defined application exceptions**. To use this in a real project, create those three exception classes or replace them with your application's exception hierarchy. The code uses Java 17 `switch` expressions.

Examples you must **never log**:

~~~java
// ANTI-PATTERN: risks logging raw OAuth2 tokens/secrets/error descriptions.
logger.error("OAuth error: {}", exception.getError().getDescription());
logger.error("Authorized client: {}", authorizedClient);
~~~

Some connection failures or HTTP responses that fail to parse as valid OAuth errors may throw different exceptions. Thus this classification **does not catch every network/TLS failure**; the integration layer needs proper timeout handling, transport exception handling, and monitoring.

### 9.2. One Way to Define Application Exceptions

~~~java
package com.example.service;

public class ServiceCredentialException extends RuntimeException {
    public ServiceCredentialException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

`ScopePolicyException` and `UpstreamAuthorizationException` can be declared similarly in **their own Java files in the project**. This example shows how to separate authentication config errors, scope policy errors, and general upstream errors without leaking tokens in user-facing messages.

If the application uses a scheduled job, the scheduler/worker can catch this exception and raise an operational alert. For a REST API calling the token manager indirectly, the controller can return a 503 or controlled business message depending on the failure—**never returning the Authorization Server's raw OAuth error description**.

### 9.3. Be Careful with the Manager's Failure Handler

`OAuth2AuthorizedClientManager` provides the **`OAuth2AuthorizationFailureHandler`** extension point. For certain grants, the failure handler may remove invalid authorized clients based on error codes and policy.

Do not customize the failure handler to:

- Wipe all authorized clients on every HTTP 500.
- Treat `invalid_client` as a signal to auto-create a new client registration.
- Retry Client Credentials infinitely inside the failure handler.
- Turn `invalid_scope` into a broader scope request without approval.

For alerting, it is better to emit minimal metrics/logs, preserve sensible default behavior, and handle retry/disable decisions in a controllable orchestration layer.

**An `invalid_client` error does not mean previously issued Access Tokens immediately become invalid on every Resource Server**; the Authorization Server and policies may dictate otherwise. Even so, never keep using old tokens to work around a revoked service identity; follow your system's lockout/incident response policy.

## 10. Retry Strategy: Do Not Treat Every Error the Same

Decision model:

~~~mermaid
flowchart TD
    A["Client Credentials token request failed"] --> B{"Cause?"}
    B -->|"invalid_client"| C["Do not retry blindly; fix client authentication/secret/tenant"]
    B -->|"invalid_scope"| D["Do not self-elevate scope; check allowlist and policy"]
    B -->|"unauthorized_client"| E["Check grant permissions and client registration"]
    B -->|"429 / 5xx / timeout"| F["Bounded retry, backoff, jitter, circuit breaker"]
    B -->|"Other / unknown"| G["Classify per provider contract; investigate safely"]
    C --> H["Operational alert and block dependent work"]
    D --> H
    E --> H
    F --> I["Succeed or fail with controlled error"]
    G --> H
~~~

### 10.1. Errors That Typically Should Not Be Auto-Retried

| Error | Common Cause | Recommended Policy |
| --- | --- | --- |
| `invalid_client` | Wrong or invalidated client authentication | Stop rapid retries; alert config/secret owner |
| `invalid_scope` | Wrong or disallowed scope requested | Stop automatic retries; update config/policy with approval |
| `unauthorized_client` | Client not permitted to use this grant | Check registration and grant permissions |
| `unsupported_grant_type` | Authorization Server does not support `client_credentials` in this setup | Fix configuration/provider; do not retry |
| `invalid_request` | Missing or malformed request parameters | Fix request serialization / auth method |

### 10.2. Errors That Can Be Retried After Evaluation

Cases like network timeouts, HTTP 429, 502/503, or transient Token Endpoint outages may suit **bounded retries**, provided you respect the provider's rate-limiting and retry policies.

A solid design typically includes:

- **Exponential backoff** instead of tight immediate retries.
- **Jitter** so multiple instances do not wake up the Token Endpoint simultaneously.
- Limits on retry attempts and total duration; never hang a job indefinitely.
- Honoring the `Retry-After` header when present and trusted.
- Circuit breakers or pausing sync during prolonged upstream outages.
- Monitoring that separates token endpoint unavailability from client authentication failures.

**Do not retry simultaneously from hundreds of pods right when an old token expires.** If needed, authorized client caching/coordination can reduce the “thundering herd” when a new token must be minted.

### 10.3. Never Retry by Expanding Permissions

Suppose requesting `scope=reports.read` fails. Never “try harder” with:

~~~text
scope=reports.read reports.write reports.admin
~~~

Widening permissions neither solves the underlying issue nor respects least privilege. An under-privileged client must report insufficient permissions or stay blocked until policy is legitimately updated.

## 11. Resource Server Returns 401 or 403: Handle Separately from Token Endpoint Errors

Once a token is issued, the client sends a request to the Reports API:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.net
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

### 11.1. HTTP 401 and `invalid_token`

The API may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Possible causes:

- Token expired or was revoked.
- Wrong issuer/audience, or token sent to an API other than the intended resource.
- Invalid JWT signature, out-of-sync JWKS/key rotation, or failed introspection.
- Malformed Bearer header or missing token.

The application may request a new token via `AuthorizedClientManager` when appropriate, yet **must not retry infinitely** if the token keeps getting rejected. If the API reports the wrong audience, re-issuing a token with the exact same configuration will not fix it.

### 11.2. HTTP 403 and `insufficient_scope`

Example:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

The token may be valid, yet lack sufficient permission to **modify** reports. Safe behavior:

1. Stop the denied operation.
2. Inspect the API contract and the scopes the endpoint requires.
3. If the service truly needs that operation, request permission through governance/admin workflow.
4. Separate read and write permissions where needed instead of granting `reports.write` to every read-only job.
5. Never alter the Access Token, manually append scopes, or bypass Resource Server authorization.

**HTTP 403 does not always mean missing scope.** The API may deny access due to tenant, ownership, resource state, IP policy, or another business condition. Only interpret it as `insufficient_scope` when indicated by the API/Bearer challenge or official documentation.

### 11.3. Comparison Table of Four Easily Confused Cases

| Failure Point | Signal | What to Investigate |
| --- | --- | --- |
| Token Endpoint | `invalid_client` | Client ID/secret/key/cert authentication and token URI |
| Token Endpoint | `invalid_scope` | Requested scope, allowed scopes, grant policy |
| Resource Server | `401 invalid_token` | Expired Access Token, wrong issuer/audience, revoked, bearer format |
| Resource Server | `403 insufficient_scope` | Scopes granted to token vs. permissions required by endpoint |

This is why recording only a generic `oauth_failed=1` metric is insufficient. Effective operations require knowing the **stage**, **registration**, **safe error code**, and **API involved**.

## 12. What If the Token Response Has a Narrower Scope Than Requested?

Client requests:

~~~text
scope=reports.read metrics.read
~~~

Yet the response returns:

~~~json
{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

Never assume the token includes `metrics.read` simply because **the initial request** asked for it. If the Authorization Server grants a scope different from the requested scope, the response must reflect the granted scope per OAuth 2.0 rules.

A service might need logic such as:

~~~java
OAuth2AuthorizedClient authorizedClient = /* manager result */;

Set<String> grantedScopes =
    authorizedClient.getAccessToken().getScopes();

if (!grantedScopes.contains("reports.read")) {
    throw new IllegalStateException(
        "Token was not granted required scope reports.read");
}
~~~

The snippet assumes an existing authorized client and an import for `java.util.Set`. Checking scopes on the client prevents API calls guaranteed to fail, yet **the Resource Server must still verify and enforce permissions** rather than trusting client-side scope checks.

Note: Some providers use `scp` or `scope` claims inside a JWT Access Token, or return the `scope` response field under custom contracts. Do not parse arbitrary JWTs to “inject” scopes into `OAuth2AccessToken`; rely on the OAuth2 response model and standard contract/validation.

### 12.1. If `scope` Is Omitted from the Token Response

OAuth 2.0 specifies rules for granted scopes when the response omits `scope` because it matches or differs from the request. Never interpret an absent `scope` field as “full permissions” or “zero permissions” across all providers; understand how Spring Security and your Authorization Server interpret this field per protocol.

For sensitive integrations, define expected scopes in the API contract rather than letting the service guess or widen permissions.

### 12.2. Scope Is a Permission Set, Not a Human Role

For example, `reports.read` might only allow the service to read general API-defined reports, while business rules still restrict tenants or report types. A Client Credentials token carries no user consent, so tenant/service-identity authorization must be enforced by the Resource Server independently of broad scopes.

## 13. Limiting Blast Radius with Multiple Client Identities

An organization has:

- `report-exporter` needing `reports.read`.
- `billing-reconciler` needing `billing.read`.
- `account-provisioner` needing `users.manage`.

If all three share one Client Secret carrying all scopes, leaking the secret in a less-trusted job lets an attacker mint high-privilege tokens.

A better architecture:

~~~mermaid
flowchart LR
    A["Report exporter"] --> B["Client registration: reports-reader"]
    C["Billing reconciler"] --> D["Client registration: billing-reader"]
    E["Account provisioner"] --> F["Client registration: provisioning-admin"]
    B --> G["Authorization Server"]
    D --> G
    F --> G
    G --> H["Scope/audience-bound Access Tokens"]
    H --> I["Resource Server policy"]
~~~

### 13.1. Separation Principles

1. Separate client credentials by **service boundary** and permission sensitivity.
2. Grant permissions per **actual API and task needed**; never give an admin client to a read-only job.
3. Manage secret/certificate lifecycles independently, with rotation and revocation.
4. Restrict network egress to the appropriate Token Endpoints and Resource Servers.
5. Monitor anomalous token issuance by client identity without logging credentials.
6. Use audience/resource binding when supported by the provider, preventing API A's token from working on API B.

Separating registrations does not eliminate risk if multiple registrations share **one over-privileged client ID/secret**. Actual permissions must be constrained at the Authorization Server, not merely in Java bean names.

### 13.2. Do Not Request Broad Scopes and Filter Permissions in Code

A setup along the lines of “request everything for convenience, and our service just won't call dangerous APIs” **does not achieve least privilege**. If credentials leak, an attacker can use the token to do what normal code avoids. Permission limits must be enforced by the Authorization Server and Resource Server.

## 14. Client Authentication Methods and `invalid_client`

### 14.1. `client_secret_basic`

~~~yaml
client-authentication-method: client_secret_basic
~~~

The HTTP request uses Authorization Basic per OAuth 2.0. For confidential clients with a client secret, this is standard. The secret **never appears in the form body** when Basic is used properly.

### 14.2. `client_secret_post`

~~~yaml
client-authentication-method: client_secret_post
~~~

The token request may carry `client_id` and `client_secret` in the form body when permitted by the provider. Use this only when explicitly registered/allowed. The Token Endpoint body is equally sensitive and can be captured by proxies or traces if logging is misconfigured.

Never cycle through authentication methods or send the same secret in multiple places without provider approval.

### 14.3. `private_key_jwt`, mTLS, and Non-Shared-Secret Mechanisms

Some M2M integrations use stronger client authentication:

- A JWT client assertion signed with the client's private key.
- Mutual TLS verifying the client's certificate.
- Custom authentication mechanisms supported by the Authorization Server.

These mechanisms reduce reliance on shared client secrets, yet still require strict key/certificate lifecycles, rotation, and policies. A wrong key, JWT audience, timestamp, or certificate will also cause the Authorization Server to return `invalid_client`.

**Never assume simply changing the YAML property to `private_key_jwt` is enough.** You must configure client assertions/certificates, key material, and token clients matching your Spring Security version and provider.

## 15. Secret Management and Handling Rotation

A very common real-world cause of `invalid_client` is unsynchronized **secret rotation**.

~~~text
T0: Authorization Server accepts secret V1
T1: V2 is created in the secret manager
T2: Some app instances still hold V1
T3: Authorization Server revokes V1
T4: Instances still holding V1 receive invalid_client
~~~

### 15.1. Sound Rotation Process

1. Prepare the new secret/certificate through a trusted management system.
2. If the Authorization Server supports a transition window, use an overlapping rotation policy.
3. Update the secret manager/mounts and roll out instances on a controlled schedule.
4. Verify token issuance using the right environment's service registration (without printing secrets).
5. Revoke old credentials per policy.
6. Monitor `invalid_client` rates and API call success after rotation.

**Never build a “fallback” to revoked secret V1 in production code.** An `invalid_client` error after rotation calls for tracking down which instance still runs stale configuration, not keeping old secrets alive forever.

### 15.2. Logging Must Never Expose Credentials

Avoid:

~~~java
// ANTI-PATTERN:
log.info("Client secret = {}", clientSecret);
log.error("Token request form = {}", requestBody);
~~~

Log only safe metadata such as:

~~~text
event=oauth2_client_credentials_failed
registration=reports-service
stage=token_endpoint
oauth_error=invalid_client
environment=production
correlation_id=internal-trace-9f2e
~~~

This is an **illustrative** log format, not default output. Never log Authorization headers, client assertions, Client Secrets, Access Tokens, or verbatim token responses / error descriptions.

## 16. Do Not Surface M2M Errors on User Login Screens

A background service has no human user waiting on a consent prompt. When the Authorization Server returns `invalid_scope` for `report-exporter`, showing a “You denied permission” page makes no sense.

Differentiate UX and operational responses:

| Context | Audience | Appropriate Response |
| --- | --- | --- |
| Scheduled job fails to get token | Operations team, integration owner | Alert with registration, error code, timestamp, task |
| Internal API fails due to token dependency | Upstream caller/service | Controlled application error code, clear retry policy |
| Web page needs data from an M2M API | End-user | Notice that feature is temporarily unavailable; hide client secrets and error internals |
| Admin updating scopes/credentials | Authorized admin | Config/secret rotation guidance and required permission levels |

`oauth2Login()`'s `AuthenticationFailureHandler` handles browser login failures—**it is not the central mechanism for catching Client Credentials errors in scheduled jobs**. Those errors occur in the client manager / token endpoint flow and are handled in the service, worker, and monitoring layers.

## 17. Authorized Client Storage and Permission Consistency

`OAuth2AuthorizedClientService` may store service tokens under the key:

~~~text
(registrationId, principalName)
~~~

Example:

~~~text
("reports-service", "system-report-exporter")
    -> OAuth2AuthorizedClient(accessToken, issuedAt, expiresAt, scopes)
~~~

### 17.1. Stored Tokens May Carry Old Permissions

Suppose the Authorization Server **narrows a client's allowed scopes**, yet the service still holds an Access Token issued before the change. The old token may remain valid until expiration or revocation, depending on policy.

Therefore:

- Do not treat editing YAML scopes as a mechanism to revoke previously issued tokens.
- For critical permission changes, plan token revocation, introspection, or cache invalidation across infrastructure.
- The Resource Server must not rely merely on “an authorized client record exists in the DB.”
- The client manager can reuse tokens until re-issuance is needed; scope/role changes at the Authorization Server are not guaranteed to take effect instantaneously.

### 17.2. One Token for Multiple Functions?

Never reuse the same Access Token across all APIs if the token's audience targets only one API. When a client needs multiple resources with different permissions, design matching authorized clients/registrations and token acquisition flows.

For opaque Access Tokens, never decode or assume scopes. Even for JWT Access Tokens, the client must not rely on unverified claims assuming the Resource Server will accept them.

### 17.3. Client Credentials and Cleanup

A service's authorized client can be removed when:

- The service/registration is retired.
- Tokens or credentials are revoked during incident response.
- Storage retention policies require cleanup.
- You need to force the next authorize call to obtain a token under updated config, through a safe and controlled mechanism.

However, **deleting a local authorized client does not revoke the token at the Authorization Server**. If access must stop immediately, use provider revocation and Resource Server enforcement.

## 18. Comprehensive Error-Handling Summary Table

| Stage | Code / Symptom | Common Meaning | Priority Action |
| --- | --- | --- | --- |
| Token Endpoint | `invalid_client` | Client authentication failed | Check ID/secret/method/key/tenant; stop blind retries |
| Token Endpoint | `invalid_scope` | Scope invalid or disallowed | Fix scope or policy with proper approval |
| Token Endpoint | `unauthorized_client` | Client not permitted to use grant | Check whether Client Credentials grant is enabled |
| Token Endpoint | `unsupported_grant_type` | Grant not supported | Check `grant_type` and provider |
| Token Endpoint | `invalid_request` | Missing or invalid request parameters | Check form encoding and token client |
| Token Endpoint | `400 invalid_grant` | Not typical of standard Client Credentials; may be another grant or extension | Inspect actual request/grant; don't blame everything on secrets |
| Token Endpoint | HTTP 429 / 5xx | Rate limit or transient upstream error | Bounded retry, backoff/jitter/`Retry-After` |
| Token Endpoint | TLS / timeout | Connection / certificate / network | Fix trust/network; retry per error category |
| Resource Server | `401 invalid_token` | Access Token invalid, expired, or rejected | Check issuer, audience, expiration, lifecycle |
| Resource Server | `403 insufficient_scope` | Missing API permission | Check granted scopes and Resource Server policy |
| Resource Server | Other HTTP 403 | Business/tenant/ownership policy | Investigate API authorization; do not self-elevate scope |
| Client Manager | `authorize()` returns null | No matching client / cannot authorize in context | Check manager, provider, registration/principal |
| Storage | Authorized client not found | Wrong key, store/session/restart | Check `registrationId + principalName` and backing store |

No single exception class is guaranteed to cover every row in this table. The HTTP layer, token client, Spring Security providers, and Resource Server may raise different exceptions or responses.

## 19. Ordered Debugging Workflow

### 19.1. When Token Endpoint Returns `invalid_client`

~~~text
1. Confirm the request uses grant_type=client_credentials.
2. Confirm the actual registrationId and token-uri.
3. Confirm the right environment/tenant/realm.
4. Check client ID and client authentication method.
5. Check secret manager or mounted keys/certificates.
6. Check whether the client was revoked, disabled, or rotated.
7. Cross-reference Authorization Server logs via correlation ID.
8. Fix config and retry in a controlled manner.
~~~

Never print secrets to the screen or logs for manual comparison. You can inspect secret presence or version metadata in the secret manager without exposing the value.

### 19.2. When Token Endpoint Returns `invalid_scope`

~~~text
1. Inspect the configured scope names (never credentials).
2. Cross-check scopes against Authorization Server documentation.
3. Verify the scopes are granted to the exact client in the right environment.
4. Verify the scopes are supported with client_credentials.
5. Check scope formatting and URL encoding.
6. Identify which features actually require each scope.
7. Request formal scope approval or reduce requested scopes/functionality.
8. Test the target API with a valid token once configuration is fixed.
~~~

### 19.3. When a Token Is Issued Yet the API Still Returns 403

~~~text
1. Identify the API endpoint and HTTP method being called.
2. Verify the token was issued for the right audience/resource.
3. Verify the granted scopes, not just requested scopes.
4. Inspect the Bearer challenge or API contract.
5. Check for tenant, ownership, IP, or resource-state policies.
6. Never self-elevate scopes or disable Resource Server authorization.
7. If the API requires a new scope, update policy through formal process.
~~~

## 20. Essential Test Scenarios

A good test suite separates the **Token Endpoint** from the **Resource Server**, using **mock/test-only** client credentials in the test environment.

| Scenario | Simulated Token Endpoint / API | Expected Result |
| --- | --- | --- |
| Valid client, valid scope | HTTP 200 token response | Manager creates and saves authorized client |
| Wrong Client Secret | `401 invalid_client` | Reports config error; no infinite retries |
| Wrong client authentication method | `invalid_client` | Preserves policy; fix registration |
| Disabled client | `invalid_client` or provider-specific policy error | Does not try to bypass via another client |
| Non-existent scope | `400 invalid_scope` | Does not auto-switch to admin scope |
| Scope not granted to client | `invalid_scope` | Alerts config/owner |
| `client_credentials` grant disallowed | `unauthorized_client` | Does not try to fake browser authorization code |
| Response scope narrower than requested | HTTP 200 with narrower `scope` | Does not assume broader scopes were granted |
| API receives expired token | `401 invalid_token` | Requests new token if appropriate, with limits |
| API rejects write operation | `403 insufficient_scope` | Blocks operation; does not self-grant permissions |
| API denies by tenant | HTTP 403 per policy | Does not blindly blame `invalid_scope` |
| Token Endpoint temporary 503 | HTTP 503 | Bounded backoff/jitter retry |
| Token Endpoint 429 | HTTP 429, possibly `Retry-After` | Limits retries and reduces concurrency |
| Two workers request tokens concurrently | Multiple instances | Avoids unnecessary request storms |
| Secret rotation | One instance old secret, one new secret | Cleanly observes `invalid_client` and safe rollout |
| Unknown error code | Provider-specific OAuth error code | Safe fallback; no crash from brittle parsing |
| Token response unexpectedly contains refresh token | Provider extension | Does not rely on it unless grant/policy is designed for it |

### 20.1. Unit Testing `OAuth2Error` Code Classification Without Network Calls

Error-classification logic can be extracted into a pure function:

~~~java
public enum TokenFailureKind {
    CLIENT_AUTHENTICATION,
    SCOPE_POLICY,
    GRANT_CONFIGURATION,
    OTHER
}

public static TokenFailureKind classify(String errorCode) {
    if ("invalid_client".equals(errorCode)) {
        return TokenFailureKind.CLIENT_AUTHENTICATION;
    }
    if ("invalid_scope".equals(errorCode)) {
        return TokenFailureKind.SCOPE_POLICY;
    }
    if ("unauthorized_client".equals(errorCode)
            || "unsupported_grant_type".equals(errorCode)) {
        return TokenFailureKind.GRANT_CONFIGURATION;
    }
    return TokenFailureKind.OTHER;
}
~~~

This is an **illustrative snippet** meant to live inside a utility class; place the enum and method in proper Java structure when implementing. Unit tests can assert:

~~~java
assertEquals(
    TokenFailureKind.CLIENT_AUTHENTICATION,
    classify("invalid_client"));

assertEquals(
    TokenFailureKind.SCOPE_POLICY,
    classify("invalid_scope"));

assertEquals(
    TokenFailureKind.OTHER,
    classify(null));
~~~

Unit testing error code classification **does not prove** the token client authenticates properly with the Authorization Server or that the Resource Server enforces scopes accurately. Integration tests against a provider/test server are needed to verify real requests/responses, along with separate Resource Server tests for 401/403.

### 20.2. Never Use Production Secrets in Tests

To simulate `invalid_client`, use **test-only** registrations/certs/secrets or a mock Token Endpoint—never send wrong production secrets repeatedly. Doing so can trigger security alerts, lock the client, or leak credentials into test logs.

## 21. Observability and Alerting Architecture

An M2M service can emit non-sensitive metrics:

~~~text
oauth2_token_authorization_total{
  registration="reports-service",
  outcome="failure",
  error_class="invalid_client"
}

oauth2_resource_call_total{
  resource="reports-api",
  outcome="forbidden",
  error_class="insufficient_scope"
}
~~~

This format **illustrates metric concepts**, not built-in Spring Security metric names.

### 21.1. Useful Signals

| Signal | Operational Meaning |
| --- | --- |
| Spike in `invalid_client` rate | Secret rotation, disabled client, wrong environment, or wrong auth method |
| `invalid_scope` rate after deployment | Config scopes changed, provider policy not updated |
| Excessive token issuance count | Cache/authorized client store failing to reuse, changing principal names, or very short token TTL |
| Spike in API HTTP 401 | Token expiry, audience/issuer mismatch, misconfigured resource |
| Spike in API HTTP 403 | Scope/tenant/policy change or client calling wrong endpoint |
| Token Endpoint timeouts/5xx | Connectivity/upstream outage; requires circuit breaker and sensible retries |

Never attach raw tokens, Client Secrets, certificate private keys, or unnecessary personal data to metric labels. High-cardinality labels like individual request IDs are also unsuitable for aggregated metrics.

### 21.2. When Should You Alert?

Because `invalid_client` and `invalid_scope` rarely self-heal, alerting the owner/service team early is far more useful than endless retries. Conversely, brief transient timeouts can be handled with bounded backoff before escalating.

A good alert includes **registration, environment, endpoint category (Token Endpoint vs. API), classified error code, and timestamp**. Never send tokens, secrets, or raw responses in alerts.

## 22. Common Implementation Mistakes

### 22.1. Using Client Credentials to “Impersonate” a Human User

`client_credentials` is machine-to-machine. If an API requires a delegated user, use the proper grant/flow for that purpose. Never hardcode `userId=admin` in a request to bypass permission checks.

### 22.2. Treating Every HTTP 401 as `invalid_client`

HTTP 401 at the Token Endpoint and HTTP 401 at the Resource Server mean different things. Verify which host/endpoint returned the error before rotating a client secret.

### 22.3. Self-Elevating Scope When Receiving `invalid_scope`

Expanding scopes to “try again” violates least privilege and usually fails anyway. Update scopes strictly per the API contract and approved permissions.

### 22.4. Requesting Broad Scopes Hoping Code Will Self-Restrain

If an Access Token carries admin scopes, an attacker who obtains the token can call admin APIs directly even if normal code does not. Enforce limits at the Authorization Server and Resource Server.

### 22.5. Putting Client Secrets in URLs or Logs

A Client Secret is a credential and should only be handled inside registered client authentication mechanisms. Never put it in query strings; never log HTTP Basic headers, secret-bearing form bodies, or JWT client assertions.

### 22.6. Retrying `invalid_client` Continuously

If credentials are wrong, every request fails again; rapid retries add load and risk account lockout. Halt retries for unrecoverable configuration/credential errors.

### 22.7. Deleting All Authorized Clients on Any Error

A Token Endpoint timeout does not prove previously issued tokens were revoked. Wiping the entire store or logging out all users causes unnecessary disruption. Base cleanup strictly on policy and error type.

### 22.8. Assuming Refresh Token Grant Applies to Client Credentials by Default

Normally Client Credentials receives no Refresh Token; the client requests new tokens using the `client_credentials` grant. Never add `offline_access` or OIDC end-user refresh logic just to “keep tokens alive longer.”

### 22.9. Mixing Access Tokens Across Multiple Resource Servers

A token meant for the Reports API is not implicitly usable on the Billing API. Verify audience/resource, scopes, and target-specific token configuration.

### 22.10. Checking Only Requested Scopes Instead of Granted Scopes

If the response carries narrower scopes, the application must never assume the missing scopes are present. The Resource Server determines final permissions, not client expectations.

### 22.11. Using an ID Token to Call M2M APIs

Standard Client Credentials does not produce a user ID Token. An ID Token from another OIDC login is not a service Access Token and must not be sent as a Bearer Token to an API.

### 22.12. Changing `client-authentication-method` Arbitrarily

If the Authorization Server registered `client_secret_basic`, do not switch to `client_secret_post` or `none` just by trial and error. Verify the contract and choose the exact method, especially with private-key JWT or mTLS.

## 23. Real-World Scenarios

### Scenario A — Secret Changed After Deployment

The job uses secret V1; the Authorization Server revoked V1 and accepts only V2. The Token Endpoint returns `invalid_client`.

**Resolution:** check the instance's secret version/mount, roll out V2 safely, verify the authentication method, never log V1/V2, and avoid infinite retries.

### Scenario B — Scope Exists Only in Staging

The app requests `reports.export` in production while that scope is configured only in staging. The Token Endpoint returns `invalid_scope`.

**Resolution:** align contract/policy through proper governance; if production has not granted the permission, the export feature must wait for approval rather than substituting an admin scope.

### Scenario C — API Returns 403 After Token Issuance

The client receives a token with `reports.read` and then calls `POST /reports` to create a report. The API requires `reports.write`.

**Resolution:** treat this as API authorization, not `invalid_client`. If the service genuinely needs write access, request the right permission through policy review.

### Scenario D — Using a Token from the Wrong Tenant

The backend calls tenant A's Token Endpoint, while the Reports API only trusts tenant B's issuer. The token response succeeds, and the API returns 401.

**Resolution:** fix the issuer/resource/audience mapping. Do not tweak scopes before confirming the tenant mismatch.

### Scenario E — Client Credentials Token Expires Mid-Job

A long-running job outlives the Access Token's lifetime; the API returns 401.

**Resolution:** use the manager to obtain a new token via client credentials when appropriate, apply bounded API retries, and ensure API operations are idempotent or protected against duplicate side effects.

### Scenario F — Token Endpoint Temporarily Returns 503

The Authorization Server undergoes brief maintenance while some workers need new tokens.

**Resolution:** apply backoff, jitter, circuit breakers, and threshold alerts. Avoid flooding hundreds of concurrent requests or switching to an untrusted endpoint.

### Scenario G — Client Requests Admin Permission “For Convenience”

A report-reading service was granted `reports.admin` even though it has no write or delete features.

**Resolution:** separate scopes/registrations, request only `reports.read`, and revoke excess admin permissions at the Authorization Server—do not rely solely on application code not calling dangerous endpoints.

### Scenario H — One Secret Shared Across Many Jobs

Three jobs share one client ID/secret with permissions to read reports, update users, and delete data.

**Resolution:** split service identities/credentials along trust boundaries, manage rotation and auditing independently, and apply strict audience/scope limits.

### Scenario I — Manager Issues Token Yet Some Nodes Keep Re-Requesting

Instance A already holds an Access Token in its in-memory store; Instance B does not see it and requests a new one.

**Resolution:** review authorized client service design, principal keys, and whether a shared store/coordination is needed; do not misclassify this as `invalid_scope`.

### Scenario J — Provider Changes Error Payload Structure

The Token Endpoint returns HTTP 400 with a custom body not matching `OAuth2Error` format. The app throws a transport/parse exception instead of a cleanly coded `OAuth2AuthorizationException`.

**Resolution:** classify by layer and provider contract with safe fallbacks, never logging verbatim bodies containing credentials or sensitive data. Do not assume every error arrives as either `invalid_client` or `invalid_scope`.

## 24. References

- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Client Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — `OAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — `AuthorizedClientServiceOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — `OAuth2AuthorizedClientProviderBuilder` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html
- OAuth 2.0 Authorization Framework (RFC 6749), Client Credentials Grant: https://www.rfc-editor.org/rfc/rfc6749#section-4.4
- OAuth 2.0 Authorization Framework (RFC 6749), Token Endpoint Error Response: https://www.rfc-editor.org/rfc/rfc6749#section-5.2
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Authorization Server Metadata (RFC 8414): https://www.rfc-editor.org/rfc/rfc8414
- Resource Indicators for OAuth 2.0 (RFC 8707): https://www.rfc-editor.org/rfc/rfc8707

## 25. Summary: Fix the Right Error Layer and Never Exceed Granted Permissions

~~~text
Service calls manager.authorize(...)
    |
    +-- Client Credentials token request
    |      |
    |      +-- invalid_client
    |      |      -> client authentication / secret / method / tenant
    |      |      -> stop blind retries, fix configuration
    |      |
    |      +-- invalid_scope
    |      |      -> invalid scope or exceeds grant policy
    |      |      -> never self-elevate permissions, check allowlist
    |      |
    |      +-- success
    |             -> OAuth2AuthorizedClient
    |             -> Access Token + granted scope/audience
    |             -> save / continue calling the right target API
    |
    +-- Resource Server response
           |
           +-- 401 invalid_token
           |      -> token validation, expiry, issuer/audience
           |
           +-- 403 insufficient_scope
           |      -> API scope / authorization policy
           |
           +-- other 403
                  -> tenant, ownership, resource policy, API contract
~~~

**Three most important principles:**

1. **`invalid_client` is a client authentication issue at the Token Endpoint**, not a request for more permissions; inspect credentials, authentication method, and provider/tenant.
2. **`invalid_scope` is a requested/granted scope issue**, not a reason to automatically widen scopes; apply least privilege and formal approval workflows.
3. **A successfully issued Access Token must still pass Resource Server checks** for issuer, audience, scope, and resource policies. Never confuse `invalid_scope` when requesting a token with `insufficient_scope` when calling an API.

With Spring Security, configure Client Credentials in **`ClientRegistration`**, coordinate issuance and reuse through **`OAuth2AuthorizedClientManager`**, classify errors at the right layer, and keep tokens and secrets inside a secure backend boundary. This keeps machine-to-machine services reliable without sacrificing least privilege or security controls.
