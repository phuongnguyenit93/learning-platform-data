# 18.9. 403 Responses and Distinguishing Insufficient Permissions from Invalid Tokens

## 1. Context: REST Client Already Has an Access Token, Yet the API Still Rejects It

In Spring Security OAuth 2.0/OIDC Client, after a user logs in through an OpenID Provider, a Servlet application can store an <code>OAuth2AuthorizedClient</code> and use its access token to call a protected REST API.

A common scenario:

1. The user logs in successfully via OIDC.
2. Spring Security created an <code>Authentication</code> and saved the authorized client.
3. The backend retrieves the access token via <code>OAuth2AuthorizedClientManager</code> or <code>@RegisteredOAuth2AuthorizedClient</code>.
4. <code>RestClient</code> sends a request to the Resource Server with the header <code>Authorization: Bearer ...</code>.
5. The REST API returns **HTTP 403 Forbidden**.

The question is: **does 403 mean the access token expired or is invalid, or is the token valid yet lacks sufficient permissions?**

These are two distinct types of failures requiring different responses:

- If the token is invalid/expired, the Client may need to refresh, obtain a new token, or initiate a new authorization flow.
- If the token is valid yet lacks the scope, role, permission, or access rights to the data object, refreshing the same token with the same permissions **will not fix it**.
- If the 403 originates from a CSRF filter, reverse proxy, WAF, or the application's own backend, it must not be blamed on the OpenID Provider's access token.

> **Key message:** For OAuth 2.0 Bearer Tokens, the critical standard signal is **HTTP status + <code>WWW-Authenticate</code> challenge + endpoint context**. Never conclude "invalid token" from an HTTP 403 alone.

This lesson explains how to distinguish and handle REST API responses when **Spring Security OAuth2 Client on Servlet** is the caller. To diagnose root causes accurately, it also examines how the receiving Resource Server typically decides between 401 and 403.

## 2. Distinguishing Authentication and Authorization

Two related yet independent security questions:

**Authentication:** Does the request carry valid credentials that establish the caller's identity?

**Authorization:** Is the authenticated subject permitted to perform the action on that specific resource?

Example:

~~~text
GET /api/reports/2026
Authorization: Bearer <access-token>
~~~

The Resource Server may process it as:

~~~mermaid
flowchart TD
    A["REST request to Resource Server"] --> B{"Appropriate Bearer credential present?"}
    B -->|No| U["401: authentication required / supply credential"]
    B -->|Yes| C{"Can the token be verified?"}
    C -->|No: expired, revoked, wrong issuer...| V["401: invalid_token per Bearer semantics"]
    C -->|Yes| D{"Are scope, role, policy, ownership sufficient?"}
    D -->|No| F["403: forbidden"]
    D -->|Yes| S["2xx: request processed"]
~~~

This diagram illustrates the **typical standard model**, not a guarantee that every API always returns those exact codes. A gateway might return 403 before the request reaches the Resource Server, an API might return 404 to conceal unauthorized resources, and a custom provider might return non-RFC 6750 error JSON.

### 2.1. Key Semantics Table

| Scenario | Typical HTTP Status | Additional Signal | OAuth2 Client Action |
|---|---|---|---|
| Missing Bearer token | **401** | <code>WWW-Authenticate: Bearer ...</code> | Verify `Authorization` header sending and authorized client |
| Access token expired | **401** | <code>error="invalid_token"</code> | Check refresh capability or re-authorize |
| Token revoked | **401** | Possibly <code>invalid_token</code> | Do not retry infinitely; obtain a valid token per grant/policy |
| Wrong issuer, audience, or signature | **401** | Usually <code>invalid_token</code> | Fix `ClientRegistration`/token audience/Resource Server config |
| Valid token yet missing scope | **403** | <code>error="insufficient_scope"</code>, possibly <code>scope="..."</code> | Inspect granted permissions; may need new authorization/consent |
| Valid token, sufficient scope, missing business role | **403** | Possibly no Bearer error code | Check role/authority/permission; do not refresh blindly |
| Valid token, user does not own the resource | **403** or **404** | Business policy/ownership | Check object access rules; keep access blocked |
| CSRF rejected inside the web app itself | **403** | Not necessarily related to <code>WWW-Authenticate</code> | Check request method, CSRF token, `SecurityFilterChain` |
| WAF/API gateway blocks request | **403** | Gateway-specific headers/body | Inspect gateway/network policies |

**Do not treat "401 = expired token, 403 = missing scope" as an absolute formula.** A more accurate rule uses HTTP semantics, Bearer challenges, and the origin of the error.

## 3. RFC 6750 and `WWW-Authenticate`: Signals Worth Reading

Under RFC 6750 on Bearer Token Usage, a Resource Server can use the <code>WWW-Authenticate</code> header to inform the Client of the authentication scheme and related error.

### 3.1. Invalid Token: `invalid_token`

Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token", error_description="The access token expired"
Cache-Control: no-store
~~~

<code>invalid_token</code> covers cases where the token is **expired**, **revoked**, **structurally malformed**, or otherwise rejected by the Resource Server. You cannot conclude solely from <code>invalid_token</code> that the cause is definitely <code>exp</code>.

Another example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token"
~~~

A Resource Server is not required to disclose sensitive details about why it rejected a token. The Client must respect what it receives without inventing a specific cause.

### 3.2. Valid Token Yet Insufficient Permissions: `insufficient_scope`

Example:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="reports-api", error="insufficient_scope", scope="reports.write"
~~~

Meaning:

- The Resource Server accepted a Bearer credential, yet the permissions it represents **are insufficient for the operation**.
- <code>scope="reports.write"</code> describes the scope the Resource Server requires or suggests under Bearer semantics.
- The Client must never treat that scope string as an instruction to automatically request whatever permissions the API suggests.

In RFC 6750, <code>insufficient_scope</code> uses HTTP **403**; the <code>scope</code> parameter on the challenge is optional. A Resource Server may omit the required scope if policy forbids disclosing it.

### 3.3. Missing Credential

Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api"
~~~

When a request **contains no authentication information at all**, RFC 6750 notes that the server should not include an error code describing a bad token, because no token was present to evaluate.

Hence <code>401</code> does not necessarily mean <code>invalid_token</code>: the Client might have forgotten to send the header, the HTTP client interceptor might not be attached, or the request hit the wrong endpoint requiring a different authentication scheme.

### 3.4. Malformed Bearer Request: `invalid_request`

Syntax errors in token usage or sending tokens via multiple methods simultaneously can result in:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

This is an **error on a request carrying a Bearer token to a Resource Server**, distinct from the <code>invalid_request</code> a Token Endpoint can return in an OAuth2 token response. Always consider whether the target endpoint is a Token Endpoint or a Resource Server.

### 3.5. Comparing the Three Core Bearer Error Codes

| Bearer Error Code | Typical HTTP Status per RFC 6750 | Meaning |
|---|---|---|
| <code>invalid_request</code> | **400** | Bearer request has invalid syntax/method |
| <code>invalid_token</code> | **401** | Supplied token was rejected |
| <code>insufficient_scope</code> | **403** | Token does not grant required permissions |

**These codes differ from Token Endpoint errors** such as <code>invalid_grant</code> or <code>invalid_client</code>. The Token Endpoint issues/refreshes tokens; the Resource Server validates Bearer tokens used to call APIs.

## 4. Parsing `WWW-Authenticate` Accurately

Documentation examples typically display a single challenge:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

In real HTTP traffic, the header may:

- Contain multiple <code>WWW-Authenticate</code> header fields or multiple challenges.
- Contain quoted or unquoted parameters per allowed syntax.
- Have irregular whitespace.
- Contain an <code>error_description</code> with commas or characters requiring quoting.
- Include other schemes alongside Bearer, such as Basic.

Therefore, **never parse challenges with <code>split(",")</code> or <code>contains("invalid_token")</code> and base security decisions on the result**. When accurate challenge classification is needed, use a parser compliant with HTTP authentication grammar or built-in support from your library/HTTP client.

In a diagnostic layer:

1. Read **all** relevant <code>WWW-Authenticate</code> headers.
2. Distinguish the <code>Bearer</code> scheme from Basic or custom schemes.
3. Read the <code>error</code> parameter within the exact Bearer challenge.
4. Keep the HTTP status to evaluate combined semantics.
5. Never echo <code>error_description</code>, <code>error_uri</code>, or entire raw headers to the frontend.

**Note:** Headers coming from a Resource Server/gateway are still external system input. Never let those headers directly drive privilege changes, scope escalations, or redirect URLs.

## 5. HTTP 403 Is Not Always `insufficient_scope`

HTTP status 403 means the server understood the request yet **refuses to authorize it**. The reason does not have to belong to OAuth 2.0.

### 5.1. Missing Scope

Suppose the Client holds:

~~~text
granted scopes: reports.read
request:        POST /reports/approve
required scope: reports.approve
~~~

The Resource Server may return:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.approve"
~~~

If the access token is still valid and unexpired, a normal refresh token grant **does not elevate granted scopes**. To obtain new permissions, the application may need a new authorization/consent flow with valid scopes permitted by the user and Authorization Server, or an administrator must grant permissions per policy.

### 5.2. Missing Business Role/Authority

Suppose the access token already carries <code>reports.read</code>, yet the user lacks the <code>FINANCE_REVIEWER</code> role required to view financial reports.

The Resource Server may reject with 403 **without** attaching <code>insufficient_scope</code>. In that case, check:

- Roles/permissions from the internal authorization system.
- How roles/claims map to <code>GrantedAuthority</code>.
- ABAC/RBAC, tenant, department, and data-visibility policies.
- Whether newly granted permissions take effect immediately or require refreshing session/entitlement caches.

Never turn this 403 into <code>invalid_token</code>.

### 5.3. Missing Permissions on a Specific Object

Suppose a user holds role <code>REPORT_VIEWER</code> yet is only permitted to view branch A's reports. A request to view branch B's report may receive 403.

Some APIs intentionally return **404** to avoid leaking that the resource exists. That is an API authorization design choice; the Client should never use 403/404 to probe unauthorized data.

### 5.4. CSRF Inside the Servlet Application Itself

If Spring MVC uses session-based authentication and CSRF protection, a POST/PUT/DELETE missing a valid CSRF token can be blocked by Spring Security with 403 **before any REST Client calls a downstream API**.

Example:

~~~text
Browser --POST /payments--> Spring MVC + CSRF Filter
                              |
                              +-- 403 due to CSRF

Browser --GET /reports--> Spring MVC --RestClient--> Resource Server
                                              |
                                              +-- 403 due to API policy
~~~

Both HTTP 403s share the same status code, yet have **different origins**. Never "fix" CSRF by refreshing an access token. Nor disable CSRF globally just to avoid a 403 when the application uses session cookies.

### 5.5. Gateway, Reverse Proxy, WAF, and Network Policies

An API gateway may return 403 due to:

- IP/region or network policy.
- Wrong API key/service identity.
- Rate limits or quotas surfaced by the gateway as 403.
- WAF flagging a suspicious request.
- Disallowed route or tenant path.

Many such responses lack <code>WWW-Authenticate: Bearer ...</code>, or carry gateway-specific headers. Classification requires knowing **whether the request reached the Resource Server or was blocked at an earlier layer**.

### 5.6. CORS and the Browser

<code>RestClient</code> inside Spring Boot runs **server-side** and is not subject to browser CORS enforcement when the backend calls APIs. CORS arises when the **browser directly** calls another origin or at a gateway handling preflight requests.

If the browser reports a "CORS error," identify the actual request:

- Browser → Servlet backend: may involve CORS/CSRF on the backend.
- Backend <code>RestClient</code> → API: server-to-server HTTP; diagnose directly via status/headers/responses.

Do not widen CORS configuration just to deal with a 403 from a backend REST Client.

## 6. Processing Flow on the Servlet OAuth2 Client

To avoid blurring responsibilities, separate the two systems:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant WEB as Spring MVC / OAuth2 Client
    participant M as Authorized Client Manager
    participant RS as Resource Server

    B->>WEB: GET /my/reports
    WEB->>M: authorize or load authorized client for current principal
    M-->>WEB: Appropriate access token
    WEB->>RS: GET /api/reports + Authorization: Bearer ...
    alt Token rejected
        RS-->>WEB: 401 + Bearer invalid_token
        WEB->>WEB: Classify authentication failure
        WEB-->>B: Message/recovery per policy
    else Token valid yet lacks permissions
        RS-->>WEB: 403 + Bearer insufficient_scope or policy 403
        WEB->>WEB: Classify authorization failure
        WEB-->>B: 403 or matching business error
    else Valid request with sufficient permissions
        RS-->>WEB: 200 data
        WEB-->>B: 200 application result
    end
~~~

**A successful OIDC Login does not prove API access is granted.** The ID Token proves identity to the Client; the access token is issued for specific resources/scopes. The backend must use the right token, and the Resource Server must independently verify both credentials and permissions.

### 6.1. Data to Observe

To find the root cause:

- <code>registrationId</code> of the authorized client.
- <code>principalName</code> of the current user (logged according to privacy policy).
- Token expiry; presence/absence of a refresh token (never print token values).
- Granted scopes in <code>OAuth2AccessToken.getScopes()</code>.
- HTTP method, normalized API path, and status.
- Parsed <code>error</code> value from the Bearer challenge if available.
- Correlation ID across backend, gateway, and Resource Server.

Never treat scopes in `ClientRegistration` as **granted scopes**: a Client may request many scopes while the Authorization Server grants fewer. To check granted scopes for an authorized client, inspect the access token metadata received by the OAuth2 Client.

## 7. How Does Spring Security Resource Server Typically Return 401 and 403?

Although this lesson focuses on the Servlet OAuth2 **Client**, understanding Resource Server behavior enables accurate diagnosis.

### 7.1. Resource Server Validating a Bearer Token

With a JWT-based Spring Security Resource Server:

~~~java
package example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/reports/write/**")
                    .hasAuthority("SCOPE_reports.write")
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

For a complete illustration, the Resource Server also needs dependencies and issuer configuration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/company
~~~

This code uses Spring Boot 3/Spring Security 6; endpoints, issuer, and scopes are examples. Production systems must also address **audience validation**, algorithm/key trust, tenant isolation, and exact authorization rules. Basic <code>issuer-uri</code> configuration does not automatically verify every API's audience; if an API requires a specific audience, configure an appropriate validator.

With the default JWT Resource Server, scopes are normally converted into authorities prefixed with <code>SCOPE_</code>. Therefore:

~~~java
.hasAuthority("SCOPE_reports.write")
~~~

differs from:

~~~java
.hasRole("REPORTS_ADMIN")
~~~

Business roles and scopes are two different authorization mechanisms. If the API uses a custom converter to map claims or uses opaque token introspection, actual authorities may differ; never assume every token is a JWT or every provider uses the <code>scope</code> claim identically.

### 7.2. Invalid Token

If signature, issuer, expiry, or configured token validation rules fail, the Resource Server produces no valid authentication; the response is normally 401 via the Bearer authentication entry point.

When a user is not validly authenticated, the API should not return 403 <code>insufficient_scope</code> merely to hide that the token could not be verified.

### 7.3. Valid Token Yet Missing `SCOPE`

If a valid JWT has <code>scope="reports.read"</code> while a write endpoint requires <code>SCOPE_reports.write</code>, the Resource Server can return 403. Under standard Bearer authorization failure handling, Spring Security can attach <code>WWW-Authenticate</code> with <code>error="insufficient_scope"</code>.

Do not rely on responses always containing <code>scope="reports.write"</code>: the suggested scope attribute is optional and depends on the Resource Server's configuration/version/implementation.

### 7.4. Controllers/Domain Services Can Also Decide 403

Example ownership check:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Report readReport(String reportId, Authentication authentication) {
    // The domain service must also check which tenant this report belongs to,
    // and whether the user is allowed to view that specific object.
    return reportService.readAuthorized(reportId, authentication);
}
~~~

This snippet illustrates a second authorization layer. In practice, enable <code>@EnableMethodSecurity</code> and let the domain service check object permissions before returning data. **Scopes permit categories of actions**, yet are usually insufficient on their own to prove permission on an individual report.

## 8. Configuring OAuth2 Client Using `RestClient` in Servlet

Example Servlet backend logging in via OIDC and then calling the Reports API.

### 8.1. Dependencies and Registration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: reports-web
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company

app:
  reports:
    base-url: https://api.example.org
~~~

<code>reports.read</code> is only an illustrative scope and must be granted by the Authorization Server for that exact API. An access token issued for a UserInfo endpoint may not work for the Reports API due to a different **audience**.

Real secrets must reside in environment variables/secret managers. Configuration does not guarantee the API automatically accepts the token: the Resource Server still verifies issuer, audience, scopes, and its own policies.

### 8.2. `SecurityFilterChain` for Web Login

~~~java
package example.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

In this architecture:

- <code>oauth2Login()</code> executes the Authorization Code Flow and OIDC authentication.
- <code>oauth2Client()</code> supports OAuth2 Client features in the Servlet context when the application uses authorized clients to call APIs.
- Browser authentication is held in the corresponding security context/session.
- Access tokens for calling REST APIs are stored in authorized client storage by registration/principal.

Never disable CSRF just because the application uses OAuth2 Client; for form/session-based web apps, CSRF and API Bearer tokens are separate protective layers.

## 9. Java Example: Calling the API and Classifying 401/403

To stay focused on HTTP responses, the example uses <code>RestClient</code> with an access token already resolved by Spring Security. With Spring Framework 6.1+ (e.g., Spring Boot 3.2+), <code>RestClient</code> supports synchronous HTTP calls.

### 9.1. Business Exception Without Leaking Upstream Bodies

Define the failure categories the application needs to distinguish:

~~~java
package example.reports;

public enum ReportsApiFailureKind {
    UPSTREAM_AUTHENTICATION_REJECTED,
    UPSTREAM_ACCESS_DENIED,
    UPSTREAM_UNAVAILABLE
}
~~~

~~~java
package example.reports;

public final class ReportsApiException extends RuntimeException {

    private final ReportsApiFailureKind kind;
    private final int upstreamStatus;

    public ReportsApiException(
            ReportsApiFailureKind kind,
            int upstreamStatus,
            Throwable cause) {
        super("Reports API call failed", cause);
        this.kind = kind;
        this.upstreamStatus = upstreamStatus;
    }

    public ReportsApiFailureKind kind() {
        return kind;
    }

    public int upstreamStatus() {
        return upstreamStatus;
    }
}
~~~

The application **never embeds raw API bodies or Bearer tokens into exception messages**. The underlying `Throwable` can still hold HTTP details, so configure logging carefully and never serialize exceptions/stack traces directly to the browser.

### 9.2. `ReportsApiClient` Using `RestClient`

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.ResourceAccessException;

@Service
public class ReportsApiClient {

    private final RestClient restClient;

    public ReportsApiClient(
            RestClient.Builder builder,
            @Value("${app.reports.base-url}") String baseUrl) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }

    public String readReports(OAuth2AuthorizedClient authorizedClient) {
        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        try {
            return restClient.get()
                .uri("/v1/reports")
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);

        } catch (HttpClientErrorException.Unauthorized ex) {
            // HTTP 401: Resource Server rejected authentication.
            // Not yet conclusively due to expiration.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_AUTHENTICATION_REJECTED,
                ex.getStatusCode().value(),
                ex);

        } catch (HttpClientErrorException.Forbidden ex) {
            // HTTP 403: usually insufficient permissions or policy denial.
            // Do not auto-refresh or request a new scope.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_ACCESS_DENIED,
                ex.getStatusCode().value(),
                ex);

        } catch (RestClientResponseException ex) {
            // Other HTTP errors, such as 429/502/503, require separate policies.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_UNAVAILABLE,
                ex.getStatusCode().value(),
                ex);

        } catch (ResourceAccessException ex) {
            // Timeouts, connection resets, DNS/TLS... may have no HTTP status.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_UNAVAILABLE,
                0,
                ex);
        }
    }
}
~~~

This example illustrates **status classification at the HTTP layer**; it does not yet inspect Bearer challenges to distinguish <code>invalid_token</code>, <code>insufficient_scope</code>, or gateway 403s. Scenarios requiring finer decisions should add a verified parser/policy.

HTTP status `0` indicates **no valid HTTP response was received**, not that the API returned HTTP 0.

The example returns <code>String</code> for simplicity—never log raw responses containing sensitive data; production code typically uses schema- and size-validated DTOs. `RestClient` should also configure appropriate connect/read timeouts.

### 9.3. Controller with the Current User's Authorized Client

~~~java
package example.reports;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    private final ReportsApiClient reportsApiClient;

    public ReportsController(ReportsApiClient reportsApiClient) {
        this.reportsApiClient = reportsApiClient;
    }

    @GetMapping("/my/reports")
    public String reports(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient) {

        return reportsApiClient.readReports(authorizedClient);
    }
}
~~~

<code>@RegisteredOAuth2AuthorizedClient("company")</code> resolves the authorized client for the registration and current principal/request. If no authorized client exists or authorization fails, handle the error at the web/security boundary; never fall back to another user's token.

The controller layer must not treat a Reports API 403 as "the user is logged out." The API denying a specific permission does not necessarily invalidate the application's OIDC session.

### 9.4. Mapping Errors Back to the Browser Per Application Contract

~~~java
package example.reports;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ReportsApiExceptionHandler {

    public record ErrorResponse(String code, String message) {}

    @ExceptionHandler(ReportsApiException.class)
    ResponseEntity<ErrorResponse> handle(ReportsApiException exception) {
        return switch (exception.kind()) {
            case UPSTREAM_AUTHENTICATION_REJECTED ->
                ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorResponse(
                        "reports_upstream_auth_failed",
                        "Unable to authenticate with the reporting service"));

            case UPSTREAM_ACCESS_DENIED ->
                ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(new ErrorResponse(
                        "reports_access_denied",
                        "You do not have permission to view this data"));

            case UPSTREAM_UNAVAILABLE ->
                ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorResponse(
                        "reports_upstream_unavailable",
                        "Reporting service is temporarily unavailable"));
        };
    }
}
~~~

This is **one mapping option**, not a mandatory rule for every API gateway/BFF:

- If the backend authenticated the user in the app yet cannot authenticate upstream, it can return **502** when that is an infrastructure integration failure. Never blindly return 401 to the browser and force the user to re-enter their password.
- If the upstream 403 genuinely reflects **the current user's permissions**, the app can return **403** per its API contract.
- If the 403 came from the **backend's service credential** or gateway configuration, returning 403 with "You do not have permission" is misleading; classify it as an upstream/integration failure before mapping.
- Never forward upstream <code>WWW-Authenticate</code> headers or exception stack traces straight to the browser.

In a real application, add safe handling for connection/TLS failures, malformed response JSON, and telemetry. The example above focuses strictly on separating authentication from authorization.

## 10. Inspecting Challenges in `RestClient` Exceptions

For 401/403 errors, <code>RestClientResponseException</code> exposes HTTP response headers, for example:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClientResponseException;

HttpHeaders responseHeaders = exception.getResponseHeaders();
if (responseHeaders != null) {
    var challenges =
        responseHeaders.get(HttpHeaders.WWW_AUTHENTICATE);

    // These challenges must be parsed per HTTP authentication grammar
    // if you need to check Bearer error="invalid_token"/"insufficient_scope".
}
~~~

Here <code>exception</code> is a <code>RestClientResponseException</code> caught from `RestClient`. <code>challenges</code> may be <code>null</code> or an empty list.

In practice:

~~~text
401 + Bearer invalid_token
    → Access token authentication rejected

403 + Bearer insufficient_scope
    → Resource Server requires permissions/scopes absent from the token

403 + no Bearer challenge
    → Check business policy, gateway, WAF, app routes, CSRF...
~~~

Never display raw <code>error_description</code> to users or use <code>error_uri</code> from the header to build unvalidated redirects; those values are controlled by the upstream.

## 11. When Should You Refresh or Request a New Token?

This is the most error-prone decision if based solely on HTTP status.

### 11.1. `401 invalid_token` Case

If a trusted Resource Server returns 401 with Bearer <code>invalid_token</code>:

1. Verify the target API has the right audience/issuer and the token was issued for that API.
2. Check whether the token expired or was revoked.
3. Determine whether the authorized client holds a refresh token or the grant supports acquiring a new token.
4. Use the appropriate authorized-client manager/provider and storage to obtain the **current valid token**.
5. Retry the API request only if safe and permitted by policy; bound the attempt count.

Never assume calling <code>manager.authorize()</code> again automatically yields a different token: the manager may return the old authorized client if the access token is not close enough to expiry. When the API rejected a token whose metadata still looks unexpired, evaluate **token invalidation** and the OAuth2 Client integration's failure handler.

### 11.2. `403 insufficient_scope` Case

Do not automatically refresh with the same refresh token and retry multiple times. The refresh token grant normally issues an access token with the same authorized scope; it does not escalate privileges just because the target API asked for another scope.

Resolution steps:

- Check the scopes **requested** in `ClientRegistration`.
- Check the scopes actually **granted** in the token response.
- Check which scope the Resource Server requires for the called HTTP method/path.
- Verify the user/client holds sufficient entitlements at the Authorization Server/domain service.
- If supported by the product, initiate a **new authorization/consent flow** to request extra permissions per policy.
- If the user is not allowed, return an explicit access-denied error; never attempt to bypass the Resource Server.

If a user only has read permission, seeing <code>reports.write</code> in a header does not turn them into someone permitted to write.

### 11.3. `403` Without OAuth Signals

Never automatically delete authorized clients or log users out. Investigate gateways, CSRF, endpoints, tenants, roles, and business policies.

If the proxy/BFF itself calls the API using a **client credentials token** and the upstream rejects it because the service lacks permissions, an end user re-logging in via OIDC cannot fix it.

### 11.4. Retry Matrix

| Scenario | Refresh/Reauthorize? | Auto-Retry API? |
|---|---|---|
| 401 Bearer <code>invalid_token</code> due to expiry, matching grant exists | Possible | Only when a new token exists, request is safe, and attempts are bounded |
| 401 token has wrong audience/issuer | Fix registration/token acquisition | Do not retry blindly with old token |
| 401 without Bearer challenge, possibly blocked by gateway | Investigate error source | Do not delete token automatically |
| 403 Bearer <code>insufficient_scope</code> | May need new scope/consent grant per policy | Do not auto-retry with same token |
| 403 missing role or object permission | Cannot be fixed by refreshing | Do not retry as a transient error |
| 403 web app CSRF | Fix request CSRF/session | Unrelated to OAuth refresh |
| 403 WAF/gateway | Investigate gateway/network policy | Do not request broader tokens automatically |
| 429/503 from API | Not necessarily token-related | Bounded retry/backoff if request is idempotent |

### 11.5. Be Careful with State-Changing Requests

For idempotent GETs, a single retry after acquiring a different token may be acceptable. For POSTs creating invoices, transferring funds, or mutating data, the backend may have processed part of the operation before the Client saw a timeout.

Never retry infinitely or auto-retry POSTs without idempotency/transaction correlation mechanisms. Token refreshing and business request retries are two separate concerns.

## 12. `OAuth2AuthorizedClientManager` and Handling Failed Authorized Clients

Spring Security provides:

- <code>OAuth2AuthorizedClientManager</code> to coordinate authorize/refresh.
- <code>OAuth2AuthorizedClientService</code> or <code>OAuth2AuthorizedClientRepository</code> to store state.
- <code>OAuth2AuthorizationFailureHandler</code> as an extension point to handle authorization failures per configuration.
- HTTP integrations that attach Bearer tokens and forward Resource Server failures to failure handlers in matching versions.

Key point to understand:

> **The manager only knows which tokens are issued/stored. If you invoke `RestClient` manually without wiring 401/403 responses into failure handling, the manager has no way of knowing the downstream API just rejected the token.**

When using Spring Security's built-in HTTP integration, you can configure behavior when a Resource Server reports an invalid token. Still, verify the API of the **exact Spring Security version** running in your project, as classes/hooks and defaults evolve across releases.

### 12.1. The Failure Handler Should Not Delete Tokens on Every 403

Suppose a user has a valid token with scope <code>reports.read</code>. The API rejects a POST with 403 <code>insufficient_scope</code>. If the Client deletes the authorized client every time it sees 403, it can cause a loop:

~~~text
403 insufficient_scope
    → delete authorized client
    → user re-logs in / new token still only has reports.read
    → POST again
    → 403 insufficient_scope
    → loop...
~~~

The issue is **insufficient permissions**, not a structurally broken token. The proper fix is aligning scopes/roles/policies and granting additional permissions per contract.

### 12.2. Why Not Delete Unconditionally After 401?

In a multi-instance environment:

~~~text
Instance A uses access token A0, API returns 401
Instance B refreshes and saves new authorized client A1/R1
Instance A sees the error and calls removeAuthorizedClient unconditionally
~~~

If A deletes by registration/principal without version checks, it can wipe out **B's freshly saved token**. In systems using refresh token rotation, this bug loses the new refresh token and forces the user to log in again.

With shared storage, consider:

- Conditional deletes or compare-and-set based on token state versions.
- Reloading the latest authorized client before removing/retrying.
- Synchronizing invalid-token failures with the refresh coordinator.
- Bounding reauthorizations/retries and avoiding reusing rejected old tokens.

Do not rely solely on a JVM-local static lock as if it solved races across multiple replicas.

### 12.3. Do Not Turn 403 into 401 in the Resource Server

Some developers try always returning 401 on access denial so the browser automatically re-logs in. When the token is already valid and the user simply lacks permission, returning 401 is semantically wrong and can create login loops.

In a Resource Server:

- Authentication failure or missing valid credentials → 401 per Bearer semantics.
- Authentication succeeded yet authorization failed → 403.

If customizing entry points/access denied handlers, preserve that distinction and never leak sensitive data in responses.

## 13. Requested Scopes Differ from Granted Scopes

In `ClientRegistration`:

~~~yaml
scope:
  - openid
  - profile
  - reports.read
  - reports.write
~~~

This is **the list the Client wants to request**, not proof the Authorization Server granted all of them to every user.

After token exchange, <code>OAuth2AccessToken.getScopes()</code> is a metadata source for **scopes returned in the token response** (depending on provider/implementation behavior). Example:

~~~java
Set<String> grantedScopes =
    authorizedClient.getAccessToken().getScopes();

boolean mayHaveReadScope = grantedScopes.contains("reports.read");
boolean mayHaveWriteScope = grantedScopes.contains("reports.write");
~~~

Never treat <code>mayHaveWriteScope</code> as the API's final authorization decision. The Resource Server still validates the token and permission policies on every request.

Additional notes:

- A JWT access token carries a <code>scope</code>/<code>scp</code> claim per provider format.
- An opaque token may require introspection at the Resource Server.
- Providers may return granted scopes in token responses or follow custom rules.
- Scopes may be only one condition; roles, tenants, ABAC, or ownership also trigger 403s.

### 13.1. User Logged In via OIDC, Yet Lacks an Access Token for the Right API

If <code>scope: [openid, profile]</code> is meant for login, the access token may only suit the UserInfo Endpoint. Sending it to the Reports API can yield 401 for wrong audience or 403 for insufficient permissions.

Successfully receiving an ID Token **does not give the access token permission to call every API**. Configure `ClientRegistration`/resource authorizations matching your IdP/API architecture.

### 13.2. Internal Roles Change After Login

If the application or Resource Server caches roles at login time, a newly promoted user may still see 403, or a user whose access was revoked must be blocked promptly per policy.

This is an authorization synchronization/caching issue. Refreshing an access token may or may not update permission claims depending on the Authorization Server; never treat token refresh as a reliable mechanism for forcing role synchronization across all systems.

## 14. Direct REST Client vs. Spring OAuth2 Client Interceptor

There are two general ways to send a Bearer token:

**Approach 1 — Obtain the authorized client yourself and set the Bearer header.**

~~~java
headers.setBearerAuth(
    authorizedClient.getAccessToken().getTokenValue());
~~~

This makes the HTTP boundary obvious, though the application must handle 401/403 and appropriate refreshes/retries itself.

**Approach 2 — Use Spring Security's HTTP client integration.**

In supported Spring Security releases, such as Spring Security 6.4+, <code>OAuth2ClientHttpRequestInterceptor</code> exists for <code>RestClient</code>. The interceptor uses an authorized client manager to inject access tokens via matching registration/principal resolvers, and supports integrating failure handling when a Resource Server rejects tokens.

Do not copy interceptor configuration code from a different Spring Security version without checking the API. Furthermore:

- Choose trusted registration IDs; never read them from arbitrary query parameters.
- Use the current `Authentication` or a composite principal suited to the grant.
- Define failure handler behavior for <code>invalid_token</code>.
- Never turn <code>insufficient_scope</code> into "request new tokens endlessly."
- Never auto-retry POST/PUT without idempotency guarantees.

What matters is not which interceptor is "cleverer," but **having one consistent place to enforce token lifecycle, authentication failures, and authorization failures**.

## 15. Distinguishing Errors Across Three HTTP Boundaries

In a Servlet Backend For Frontend (BFF) application, the same HTTP 403 status can originate at three places:

~~~mermaid
flowchart LR
    B["Browser"] --> APP["Spring MVC / SecurityFilterChain"]
    APP --> CLIENT["RestClient + authorized client"]
    CLIENT --> G["API Gateway"]
    G --> RS["Resource Server"]
    APP --> A["403 at web app: role/CSRF"]
    G --> GW["403 at gateway: WAF/network/API key"]
    RS --> R["403 at Resource Server: scope/policy/object"]
~~~

### 15.1. Browser → Web App

If the browser receives 403 directly from Spring MVC, check whether the request even reached the controller:

- Did the CSRF filter reject it before the controller?
- Did <code>authorizeHttpRequests</code> or <code>@PreAuthorize</code> deny it?
- Which `SecurityFilterChain` processed the request?
- Are the session and principal still valid?

Do not diagnose by inspecting downstream tokens if the downstream was never called.

### 15.2. Web App → Gateway

If `RestClient` receives 403, check whether a reverse proxy/gateway sits in front of the Resource Server. Inspect correlation IDs and safe gateway logs rather than automatically re-sending access tokens multiple times.

### 15.3. Gateway → Resource Server

If the Resource Server generated the response, inspect Bearer challenges, token validation, scope-to-authority mapping, and business authorization. Keep internal API error codes distinct from standard OAuth 2.0 error codes.

### 15.4. Be Careful with Exception Mapping

An upstream HTTP 403 might be mapped by the backend to 502 as a **service integration failure**, or to 403 because **the user lacks permissions**. This depends on the API contract and credential source—never apply one rigid mapping across every route.

Using helpful application error codes like <code>reports_access_denied</code> or <code>upstream_auth_failed</code> lets the frontend respond properly without receiving raw internal upstream details.

## 16. Concrete Scenarios

### 16.1. Expired Access Token

~~~http
GET /v1/reports HTTP/1.1
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="expired"
~~~

Interpretation: The API no longer accepts the token. If the authorized client has a valid refresh token and the manager is configured for refresh, a new token can be obtained. Never conclude from a single description string that all providers share identical semantics.

### 16.2. Unexpired Token Yet Read-Only Scope

~~~http
POST /v1/reports/approve HTTP/1.1
Authorization: Bearer READ_ONLY_TOKEN
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.approve"
~~~

Interpretation: The user/Client lacks the required permission. Refreshing under the same grant/scope will not fix it; inspect permission policies and authorization flows.

### 16.3. Valid Token, User Outside Tenant

~~~json
{
  "error": "tenant_access_denied",
  "message": "Resource is outside your tenant"
}
~~~

This HTTP 403 response is an **API-defined business error**, not the standard <code>insufficient_scope</code> code. The Client must handle it per the API contract rather than checking OAuth scopes alone.

### 16.4. Valid Token Yet Blocked by WAF

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/html
X-Request-Id: gateway-request-placeholder

<html><body>Request denied</body></html>
~~~

Do not parse HTML and conclude the Bearer token is bad. Inspect WAF/gateway policies, paths, and safe request IDs.

### 16.5. 403 Due to CSRF at the Web App

~~~text
Browser POST /profile/update
    → Spring Security CSRF filter
    → Missing CSRF token
    → 403
~~~

No need to call the Token Endpoint or refresh `OAuth2AuthorizedClient`. Fix the client/browser CSRF request matching the session mechanism.

### 16.6. 401 Because Token Has the Wrong Audience

~~~text
Access token issued for UserInfo/API A
REST Client sends it to Reports API B
Reports API B rejects the token
~~~

If the Resource Server checks audience, the API can return 401 Bearer <code>invalid_token</code>. Refreshing to get a new token with the same old audience **will not fix** the misconfiguration. Fix `ClientRegistration`/resource authorization.

## 17. Common Mistakes When Handling 403

| Mistake | Why It Is Problematic | Right Approach |
|---|---|---|
| Deleting authorized client on every 403 | Token may still be valid yet lack role/scope | Classify Bearer challenge and policy |
| Forcing user to re-login on 403 | Logging in again does not grant new permissions | Check authorization/entitlements |
| Copying scope from header straight into request | API must not dictate privilege escalation | Follow trusted authorization/consent policies |
| Treating every 401 as expired token | May be wrong audience, issuer, missing header, or gateway auth | Read challenge and verify registration |
| Treating every 403 as `insufficient_scope` | Could be CSRF, WAF, role, or object ownership | Identify the boundary producing the error |
| Checking only requested scopes in YAML | Granted scopes may be fewer | Inspect granted scopes and API policy |
| Assuming scoped access token grants access to all objects | Role/tenant/ownership can still deny | Enforce business authorization at Resource Server |
| Retrying POST infinitely after refresh | Easily creates duplicate actions | Bounded retries and idempotency when required |
| Sending raw Bearer `error_description` to frontend | Can leak data or cause log injection | Use safe application error codes and messages |
| Disabling CSRF to "fix" web app 403s | Weakens session security | Fix CSRF token/request or configure intentionally |
| Sending ID Token instead of access token | ID Token is not for Resource Servers per OAuth2 Bearer usage | Use access token with matching audience |
| Decoding JWT and trusting permissions without signature validation | Untrusted when unverified | Let Resource Server validate completely |
| Unconditional token state deletion in multi-instance setups | May delete another node's fresh token | Conditional delete/versioning or coordinator |
| Ignoring actual HTTP status/headers | Cannot tell if gateway or Resource Server failed | Log status and safe correlation ID |

## 18. Step-by-Step 403 Diagnosis Process

When <code>RestClient</code> receives 403:

1. **Identify the exact request.** HTTP method, API path, registration ID, target system, timestamp, correlation ID.
2. **Identify the response source.** Did the 403 come from the browser-facing web app, gateway/WAF, or Resource Server?
3. **Read HTTP status and <code>WWW-Authenticate</code> challenges.** Is there a Bearer scheme? Is <code>insufficient_scope</code> present?
4. **Verify credential type.** User access token from Authorization Code or service token from Client Credentials? Right API/audience?
5. **Compare granted permissions.** Scopes in authorized client/token response vs. API scope/policy.
6. **Check roles/entitlements/tenant/object ownership.** Do not focus solely on scopes.
7. **Check session and CSRF** if the 403 originated inside the Servlet app itself.
8. **Check gateway logs** if status lacks Bearer indicators and the gateway enforces its own policies.
9. **Choose recovery.** 403 missing permissions → return permission error or valid authorization flow; 401 invalid token → token lifecycle; gateway failure → operations.
10. **Never log tokens/secrets.** Record sanitized metadata only.

Decision tree:

~~~text
Receive HTTP 403
  |
  +-- 403 at the Servlet app itself?
  |       |
  |       +-- Yes: check SecurityFilterChain, CSRF, method security
  |
  +-- 403 from downstream API?
          |
          +-- WWW-Authenticate has Bearer insufficient_scope?
          |       |
          |       +-- Yes: missing scope → investigate permissions/consent
          |
          +-- No Bearer challenge?
                  |
                  +-- API business 403? → role, tenant, object ownership
                  |
                  +-- Gateway/WAF 403? → network/gateway policy
                  |
                  +-- Unknown? → keep safe error, investigate further
~~~

If receiving **401** instead of 403, follow the Bearer <code>invalid_token</code> or missing authentication branch. Do not confuse it with <code>invalid_grant</code> returned by the **Token Endpoint** on refresh.

## 19. Monitoring Errors in Production

To prevent refresh/login loops and spot authorization issues, monitor:

| Metric or Log Field | Purpose |
|---|---|
| <code>registrationId</code> | Identify the corresponding Client/provider |
| <code>upstreamService</code> | Distinguish Reports API, Billing API, gateway |
| <code>httpMethod</code> and route template | Identify endpoint/operation without logging URLs with sensitive data |
| <code>upstreamStatus</code> | Track 401/403/429/5xx |
| Allowlisted <code>bearerErrorCode</code> | Separate `invalid_token`, `insufficient_scope` |
| <code>grantedScopeCategory</code> | Observe permissions in aggregate if policy permits |
| <code>tokenRefreshAttempted</code> | Detect refresh loops |
| <code>reauthorizationRequired</code> | Track re-login/re-consent prompts |
| <code>correlationId</code> | Trace across backend/gateway/API |

Never include access tokens, refresh tokens, client secrets, authorization codes, state, nonce, raw ID Tokens, or <code>Authorization</code> headers in logs/metrics.

In particular, **never use raw <code>error_description</code> as a metric label**, as it may contain sensitive data and creates unbounded cardinality.

### 19.1. Loop Alerts

A common bug signature:

~~~text
GET API → 403 insufficient_scope
OAuth2 Client → deletes token
Browser → login
GET API → 403 insufficient_scope
Browser → login
...
~~~

This is an authorization issue rather than a logout/refresh issue. Metrics counting re-logins and consecutive 403s per registration/route help pinpoint the root cause.

## 20. Exercises and Practice Scenarios

### Exercise 1 — Distinguishing Two Responses

Response A:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Response B:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

**Question:** How do the two responses differ?

**Answer:** A shows the Bearer token was rejected; evaluate token lifecycle, audience/issuer, expiry, and refresh capability. B shows the token lacks the permissions/scopes required by the API; refreshing with the same permissions will not add scopes.

### Exercise 2 — 403 Despite Successful OIDC Login

The user logged in via OIDC and <code>OidcUser.getIdToken()</code> is valid, yet Reports API returns 403.

**Question:** Can we conclude the ID Token is wrong?

**Answer:** No. The ID Token serves identity authentication with the OIDC Client. Reports API uses an access token and its own authorization. Check scopes, audience, roles, tenant, object ownership, and the 403 source.

### Exercise 3 — Can Refreshing Fix Missing Scope?

The token was granted <code>reports.read</code> and the API requires <code>reports.approve</code>. The backend holds a refresh token.

**Question:** Should it refresh continuously?

**Answer:** No. The refresh token grant does not mint new permissions. Re-examine registration, consent, OP policies, and business permissions; only request additional scopes via a valid flow if the user/Client is permitted.

### Exercise 4 — Missing Header

The API returns:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/html

<html><body>Denied by gateway</body></html>
~~~

**Question:** Is there enough evidence of <code>insufficient_scope</code>?

**Answer:** No. This may be a gateway/WAF policy. Inspect request path, routing, network policy, and gateway logs; do not automatically delete tokens or force the user to re-login.

### Exercise 5 — CSRF

The browser sends a POST to a session-based Servlet application, and the request gets 403 before the controller executes.

**Question:** Is inspecting `OAuth2AuthorizedClient` the first step?

**Answer:** No. Inspect `SecurityFilterChain`, the CSRF filter, and whether the request carries a valid CSRF token. This is likely a 403 at the web app before any `RestClient` call to the API occurred.

### Exercise 6 — Wrong Audience

The backend takes a token with audience <code>userinfo-api</code> and sends it to <code>billing-api</code>. The API returns 401 <code>invalid_token</code>.

**Question:** Should that same token be refreshed and reused?

**Answer:** No, if the new token still targets the old audience. Update `ClientRegistration`/token acquisition to obtain a token matching the target audience, scopes, and API contract.

### Exercise 7 — Object Authorization

The token holds <code>reports.read</code>, the user has role `REPORT_VIEWER`, yet the report belongs to another tenant.

**Question:** Can the Resource Server return 403?

**Answer:** Yes. Scopes/roles do not override tenant and ownership checks. Some APIs may return 404 to avoid disclosing the resource, depending on contract.

### Exercise 8 — Multi-Instance and Cleanup

Node A gets 401 using old token A0. Simultaneously, node B refreshes and saves A1/R1. Node A tries calling <code>removeAuthorizedClient</code>.

**Question:** What is the risk?

**Answer:** Unconditional deletion by registration/principal can wipe out A1/R1. Re-read state, use conditional delete/versioning, and coordinate with the refresh workflow.

### Exercise 9 — Designing Error-Handling REST Client

Design a service with:

1. Spring Security OAuth2 Client registration using Authorization Code Flow.
2. Authorized client with the right principal and granted scopes.
3. `RestClient` sending the Bearer access token to the right Resource Server.
4. Classification of HTTP 401 and 403, reading Bearer challenges when present.
5. No automatic refresh on <code>insufficient_scope</code>.
6. Retrying <code>invalid_token</code> only if a new token can be obtained and the request is safe.
7. Distinguishing CSRF/web-app 403s from downstream 403s.
8. Returning safe application error codes to the frontend.
9. Never logging raw tokens, credentials, or upstream error descriptions.

### Exercise 10 — Checking Expected Status Codes

Fill in the appropriate RFC 6750 status for these Bearer cases:

| Case | Answer |
|---|---|
| No Bearer credential supplied for a protected resource | 401 and Bearer challenge |
| Bearer token rejected as invalid | 401 <code>invalid_token</code> |
| Token valid yet lacks required scope | 403 <code>insufficient_scope</code> |
| Malformed Bearer request | 400 <code>invalid_request</code> as applicable |

Note that this exercise applies to **standard Bearer semantics** and does not rule out custom gateway/business API responses.

## 21. Key Takeaways

- **HTTP 401** usually indicates an **authentication** issue; with Bearer tokens, <code>invalid_token</code> signals the Resource Server rejected the token.
- **HTTP 403** usually indicates an **authorization** issue; <code>insufficient_scope</code> per RFC 6750 means the token lacks sufficient scope. Still, 403 does not automatically mean missing scope.
- Read <code>WWW-Authenticate</code> alongside HTTP status and identify the **origin**: Servlet app, gateway, or Resource Server.
- **Successful OIDC Login does not automatically grant API permissions**. The ID Token proves identity to the Client; the access token must have the right audience/scope, and the Resource Server also enforces business policies.
- **Refresh tokens are not a self-escalation mechanism.** For permission-related 403s, inspect granted scopes, roles, tenants, ownership, and valid consent/authorization flows.
- <code>RestClient</code> attaching Bearer headers manually may need manual error handling. When using OAuth2 Client HTTP integrations, verify the failure handler for your exact Spring Security version.
- Never delete authorized clients or force re-logins on every 403; never turn CSRF/gateway/business-policy 403s into token errors.
- When retrying after 401, require a genuinely new suitable token, bounded retries, idempotency, and coordinated token state across instances.
- Never log access tokens, refresh tokens, Client secrets, or raw upstream errors. Return safe frontend messages and retain diagnostic data per policy.

### References

- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage**, Section 3: <code>WWW-Authenticate</code>, <code>invalid_request</code>, <code>invalid_token</code>, and <code>insufficient_scope</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework**: distinguishing Authorization Server/Token Endpoint, Resource Server, access tokens, and scopes.
- **Spring Security Reference — OAuth2 Client (Servlet):** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientManager</code>, <code>@RegisteredOAuth2AuthorizedClient</code>, and REST HTTP client integration.
- **Spring Security Reference — OAuth2 Resource Server:** Bearer Token Authentication, JWT/opaque validation, authority mapping, and authorization error handling.
- **Spring Security Reference — Servlet Authorization and CSRF Protection:** <code>SecurityFilterChain</code>, <code>authorizeHttpRequests</code>, method security, and CSRF.
- **Spring Framework Reference — REST Clients:** <code>RestClient</code>, response status handling, and <code>RestClientResponseException</code>.
- **OpenID Connect Core 1.0:** ID Token, OIDC Login, UserInfo, and relationship with OAuth2 Authorization Code Flow.
