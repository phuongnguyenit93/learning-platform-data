# Basic Authentication, API Keys, and OAuth2 Client Credentials

## Goals and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot orchestrates integration flows across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. When Order Service calls Inventory API, Pricing API, or an ERP, the flow needs more than valid JSON/XML: it must **authenticate the calling service's identity**, enforce permissions, protect credentials, and respond appropriately when connections fail.

Three common HTTP service-to-service authentication schemes:

- **HTTP Basic Authentication:** sends a username/password pair in the HTTP `Authorization` header.
- **API key:** sends a provider-contracted key, typically in a dedicated HTTP header.
- **OAuth2 Client Credentials:** uses client identity to request a **short-lived access token** from an Authorization Server, then sends that token to a Resource Server.

This lesson belongs to the **Connection Security** chapter, topic **Basic authentication, API keys, and OAuth2 Client Credentials**. It focuses on using `RestClient`, `WebClient`, and HTTP Interfaces in Spring Boot, while tying security to transactions, retries, idempotency, testing, and observability.

After this lesson, you can:

1. Distinguish the three mechanisms and choose based on the partner's contract.
2. Configure Basic and API key auth on an outbound HTTP client without leaking them to other clients.
3. Set up OAuth2 client registrations, `client_credentials`, `scope`, and `token-uri`.
4. Use an `OAuth2AuthorizedClientManager` suited for Quartz jobs, broker consumers, and outbox workers.
5. Automatically attach Bearer tokens via Spring Security or a narrowly scoped interceptor.
6. Understand token storage/reuse, expiration, re-issuance, and secret rotation.
7. Distinguish 401, 403, 429, TLS, token endpoint, and business rejection errors.
8. Design multi-layer tests and monitoring without exposing credentials.

> **Principle:** Successful authentication does not imply permission on every resource; an HTTPS-protected connection returning HTTP 200 does not guarantee the downstream transaction committed once.

## 1. Which Layer Does Authentication Belong To in an Integration?

~~~mermaid
flowchart LR
    O["Order Service"] --> B["HTTP Basic"]
    O --> K["API key"]
    O --> T["OAuth2 client_credentials"]
    B --> R["Partner Resource API"]
    K --> R
    T --> AS["Authorization Server"]
    AS -->|"Access token"| O
    O -->|"Bearer token"| R
    R --> P["Validate identity, scope, resource policy"]
~~~

A secure integration has multiple layers:

| Layer | Examples | Responsibility |
| --- | --- | --- |
| Transport channel | HTTPS, TLS, mTLS | Encrypt and verify peer via certificates |
| HTTP authentication | Basic, API key, Bearer token | Identify the client |
| Application authorization | Scope, role, tenant, resource ownership | Decide permitted operations |
| Data contract | JSON Schema, XML/XSD, DTO validation | Prevent malformed data |
| Consistency | SQL transactions, outbox/inbox, idempotency | Protect business side effects |
| Operations | Logging, metrics, alerts, key rotation | Detect and recover from incidents |

**Do not confuse mTLS with these three mechanisms:** mTLS proves a peer owns a private key/certificate at the TLS layer. Basic/API key/OAuth2 are application-level mechanisms. A system may require **both mTLS and OAuth2** if the threat model demands it.

### 1.1. Comparison Table

| Criterion | Basic | API Key | OAuth2 Client Credentials |
| --- | --- | --- | --- |
| HTTP credential | `Authorization: Basic ...` | Vendor-specific header | `Authorization: Bearer ...` |
| Root secret | Password | API key | Client secret, private key, or mTLS credential |
| Has token endpoint? | No | Not by default | Yes |
| Credential sent to resource API | Base64 username/password | API key | Access token issued by AS |
| Expiration | Per password policy | Per key policy | Access token typically short-lived |
| Scope and audience | Vendor-specific if any | Vendor-specific if any | Standard mechanisms in Authorization/Resource Servers |
| Rotation | Rotate password | Rotate API key | Rotate client secret and re-issue access tokens |
| User identity | Not by default | Not by default | Typically represents an application, not a user |
| Common errors | Wrong password, realm | Revoked key, quota | `invalid_client`, `invalid_scope`, `invalid_token` |

API keys lack a single universal wire format across providers. OAuth2 is more complex but excels when scoped permissions, short-lived tokens, and decoupling Authentication Server from Resource Server are needed.

## 2. Preparing the Spring Boot Project

With Spring Boot 3.2+ and Java 17+, `RestClient` is a convenient synchronous HTTP client. Add the OAuth2 client starter when OAuth2 is needed:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Only when OAuth2 Client is needed:
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Only when using WebClient/reactive:
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    // Monitoring, if needed:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Not every app needs both MVC and WebFlux. With Boot 4/Spring Security 7, starter names or package locations of certain APIs may change; use the BOM and verify actual project dependencies/Javadocs.

Spring Boot pre-configures `RestClient.Builder` and `WebClient.Builder` when the corresponding starters are present. Instead of one global client holding every credential, create **one outbound client bean per partner**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerHttpConfiguration {

    @Bean
    RestClient partnerClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example.org")
                .build();
    }
}
~~~

`https://partner.example.org` is an illustrative address; in production, supply it from environment-specific configuration. A `RestClient.Builder` is stateful: when creating multiple clients from the same builder, settings can accumulate; inject dedicated Boot builders or clone when appropriate.

## 3. HTTPS Is a Prerequisite

Base64 in Basic auth is not encryption; API keys and Bearer tokens are also bearer credentials that anyone who intercepts them can replay. Therefore:

- Call resource APIs and OAuth2 token endpoints over HTTPS.
- Verify certificate chains and hostname SANs.
- Never use a trust-all `TrustManager` or always-true `HostnameVerifier`.
- Keep secrets out of URLs/query params, stack traces, and access logs.
- Block redirects to unapproved domains carrying Authorization headers.
- Separate dev/staging/production credentials and truststores.
- Enforce network egress allowlists, timeouts, and concurrency limits.
- Maintain a revoke/rotate process if a key leaks.

TLS protects the channel, yet the server must still verify credential validity and principal permissions. If Inventory API receives a token with `scope=inventory.read`, it must not allow `POST /reservations` merely because the token signature is valid.

## 4. HTTP Basic Authentication

HTTP Basic uses the header:

~~~http
GET /v1/products/P-100 HTTP/1.1
Host: catalog.example.org
Authorization: Basic <redacted>
~~~

The value after `Basic` is Base64 of username/password per Basic scheme encoding rules. **Base64 does not hide the password from anyone reading the header**.

### 4.1. Configuring the Secret

~~~yaml
integrations:
  catalog:
    base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
    username: ${CATALOG_USERNAME}
    password: ${CATALOG_PASSWORD}
~~~

Environment variables must be injected by secret management. Never commit real passwords into source or YAML.

### 4.2. Attaching Basic Auth to a Specific `RestClient`

~~~java
// CatalogClientConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            @Value("${integrations.catalog.base-url}")
            String baseUrl,
            @Value("${integrations.catalog.username}")
            String username,
            @Value("${integrations.catalog.password}")
            String password) {

        return builder
                .baseUrl(baseUrl)
                .defaultHeaders(headers ->
                        headers.setBasicAuth(username, password))
                .build();
    }
}
~~~

This is **preemptive** Basic auth: the header is added on the very first request. Some HTTP stacks use challenge/response with `401 WWW-Authenticate` or a transport credential provider. Choose what fits the partner and HTTP client in use.

Use this bean solely for calling Catalog API. When multiple `RestClient` beans exist, inject explicitly with `@Qualifier("catalogRestClient")` so Payment code never accidentally uses Catalog credentials.

### 4.3. Calling the API

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogGateway {

    private final RestClient client;

    public CatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    public ProductDto find(String sku) {
        return client.get()
                .uri("/v1/products/{sku}", sku)
                .retrieve()
                .body(ProductDto.class);
    }
}
~~~

`ProductDto` is an application-defined DTO. The client must have request timeouts and proper error mapping; default `retrieve()` throws exceptions on HTTP 4xx/5xx.

### 4.4. Limitations of Basic Auth

| Scenario | Conclusion/Mitigation |
| --- | --- |
| 401 after password change | Workload secret may be stale; do not retry infinitely |
| 403 | Client may be authenticated yet lack permission |
| Password contains non-ASCII | Confirm server charset/challenge policy |
| Sharing one password across APIs | Increases blast radius if one leaks |
| Password rotated while client runs | Existing bean may still hold old credentials |
| Logging HTTP headers to debug | Risk of leaking Base64-encoded password |
| Redirect to another host | Ensure credentials are never forwarded to unexpected hosts |

Never use an admin account or an end-user password for an integration worker when a least-privilege service account can be provisioned.

## 5. API Keys

An API key is a provider-defined credential. It takes many forms:

~~~http
GET /v1/quotes HTTP/1.1
Host: pricing.example.org
X-API-Key: <redacted>
~~~

Or another vendor:

~~~http
Authorization: ApiKey <redacted>
~~~

There is no single standard mandating `X-API-Key` or the `ApiKey` prefix. Read header names, signature algorithms if any, quotas, permissions, and rotation schedules from the provider's documentation/contract.

### 5.1. Configuring an API Key with `RestClient`

~~~yaml
integrations:
  pricing:
    base-url: ${PRICING_BASE_URL:https://pricing.example.org}
    api-key: ${PRICING_API_KEY}
~~~

~~~java
// PricingClientConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PricingClientConfiguration {

    @Bean
    RestClient pricingRestClient(
            RestClient.Builder builder,
            @Value("${integrations.pricing.base-url}")
            String baseUrl,
            @Value("${integrations.pricing.api-key}")
            String apiKey) {

        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-API-Key", apiKey)
                .build();
    }
}
~~~

If the partner uses `Authorization: ApiKey ...`, replace `defaultHeader(...)` per contract. Never send **both** header forms just because you are unsure which is expected.

### 5.2. Avoid Keys in Query Strings

~~~text
https://pricing.example.org/v1/quotes?api_key=SECRET
~~~

A URL like this easily lands in reverse proxy logs, client telemetry, history, error reports, and cache keys. Prefer passing API keys in headers over HTTPS. If a vendor only supports query parameters, enforce strict redaction, redirect controls, and log retention limits.

### 5.3. API Keys, Rate Limits, and Permissions

A valid API key can still receive HTTP 429 due to quota exhaustion; that is not necessarily an authentication failure. Keys may also be restricted by IP, endpoint, environment, or tenant. Do not assume every 403 means a bad key, and do not amplify retries in a way that worsens quota exhaustion.

Best practices:

1. Issue distinct keys per application/environment.
2. Restrict endpoints/roles/quotas.
3. Never share keys through broker payloads or outbox rows.
4. Rotate using dual-active windows when supported by the vendor.
5. Monitor key expiry/revocation and fall back per policy.
6. Never put keys into metric labels or log fields.

## 6. OAuth2 Client Credentials: Two Exchanges

The OAuth2 Client Credentials Grant fits confidential clients—such as services or background jobs calling APIs on behalf of **the application itself**. It involves no browser redirect and does not inherently carry an end-user identity.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant A as Authorization Server
    participant I as Inventory Resource Server
    O->>A: POST /oauth2/token grant_type=client_credentials
    Note over O,A: Client authenticates using client secret/private key/mTLS
    A-->>O: Bearer access token, expires_in, scope
    O->>I: HTTPS Authorization: Bearer access-token
    I->>I: Validate token, audience, scope and business policy
    I-->>O: Protected resource response
~~~

**Distinguish the credentials:**

| Component | Sent Where? | Used For? |
| --- | --- | --- |
| Client ID | Authorization Server | Identifies the OAuth2 client |
| Client secret | Authorization Server, via configured method | Proves client identity |
| Access token | Resource Server | Authorizes resource access per claims/policy |
| Token URI | Authorization Server | Endpoint issuing tokens |
| API base URL | Resource Server | Business endpoint |
| Scope | Requested from AS | Checked by Resource Server |
| Audience | Identifies target API | Prevents cross-target token misuse |

### 6.1. Token Request

Redacted example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credential-redacted>

grant_type=client_credentials&scope=inventory.read%20inventory.reserve
~~~

Here `Authorization: Basic` **authenticates the OAuth2 client at the token endpoint** using `client_secret_basic`, distinct from sending Basic directly to the Inventory Resource API.

Another AS might require `client_secret_post`, `private_key_jwt`, or mTLS client authentication. Never send the client secret in both the body and Authorization header unless the contract specifies it.

Example response:

~~~json
{
  "access_token": "<redacted>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "inventory.read inventory.reserve"
}
~~~

Access tokens can be JWTs **or opaque tokens**. Do not assume the client can decode/verify every token; the Resource Server validates via issuer/signature or introspection, audience, expiry, scope, and authorization rules.

### 6.2. `client_credentials` vs. `authorization_code`

| Property | `client_credentials` | `authorization_code` |
| --- | --- | --- |
| Represented account | Application/service | User and user's delegation |
| Requires browser redirect? | No | Yes |
| Quartz/outbox worker | Suitable | Should not depend on a user HTTP session |
| Refresh token | Usually not issued | May be issued |
| Obtaining a new token | Re-send client credentials when needed | Refresh/re-authorize |
| Security model | Service credentials and scoped access token | User consent/session/token policy |

An event sitting in an outbox for hours should not carry the Bearer token of the user who originally called HTTP: that token could expire, have the wrong audience, and risk leaking in databases/brokers.

## 7. Spring Boot OAuth2 Registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-client:
            provider: inventory-idp
            client-id: ${INVENTORY_OAUTH_CLIENT_ID}
            client-secret: ${INVENTORY_OAUTH_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - inventory.read
              - inventory.reserve
        provider:
          inventory-idp:
            token-uri: ${INVENTORY_TOKEN_URI:https://auth.example.org/oauth2/token}

integrations:
  inventory:
    base-url: ${INVENTORY_API_URL:https://inventory.example.org}
~~~

| Setting | Meaning |
| --- | --- |
| `registration.inventory-client` | Client ID within Spring Security |
| `provider: inventory-idp` | References Authorization Server details |
| `client-id` | Identity registered with the AS |
| `client-secret` | Sensitive secret; never commit to repository |
| `authorization-grant-type` | Specifies `client_credentials` |
| `client-authentication-method` | How client credentials are sent to AS |
| `scope` | Requested permissions; AS may not grant all |
| `provider.inventory-idp.token-uri` | Endpoint issuing access tokens |
| `integrations.inventory.base-url` | Resource API, independent of token URI |

With the OAuth2 client dependency and a valid registration, Boot auto-configures `ClientRegistrationRepository` and the authorized client service. **Declaring YAML alone does not add Authorization headers to every `RestClient`**: you must wire the manager/interceptor/filter properly.

### 7.1. Do Not Confuse Client Registration with Principal

`inventory-client` is the **client registration ID** selecting credentials and token endpoint. A `principal` used in the authorized-client cache scopes token storage. Background services should use a stable principal such as `order-integration-service`, not `orderId` or a random UUID per call.

When multiple partners need separate audiences/scopes, define separate registrations per partner. Never attach one global token to all URLs.

## 8. Manager for Background Services Without a User Session

Spring Security provides `OAuth2AuthorizedClientManager` to obtain and manage tokens. An integration worker running in Quartz, a Kafka listener, or an outbox relay normally **has no `HttpServletRequest`**, so use `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

### 8.1. Creating the Manager

~~~java
// ServiceOAuth2Configuration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class ServiceOAuth2Configuration {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The manager stores/reuses access tokens in `OAuth2AuthorizedClientService` keyed by registration + principal. When expired, the client credentials provider requests a **new token** per policy (no refresh token by default).

Never cache raw token strings indefinitely in a static field. Account for expiry, clock skew, `401 invalid_token`, and concurrent acquisition.

### 8.2. Token Provider

~~~java
// InventoryAccessTokenProvider.java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public class InventoryAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public InventoryAccessTokenProvider(
            OAuth2AuthorizedClientManager serviceAuthorizedClientManager) {
        this.manager = serviceAuthorizedClientManager;
    }

    public String accessToken() {
        var request = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-client")
                .principal("order-integration-service")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                    "Unable to authorize inventory-client");
        }

        return client.getAccessToken().getTokenValue();
    }
}
~~~

`principal("order-integration-service")` is a stable logical name for the service-level authorized client, **not a real user**. If multiple manager beans exist, use `@Qualifier` to inject the right bean.

**Never log** `client.getAccessToken().getTokenValue()`, even at DEBUG level.

## 9. OAuth2 with `RestClient`

### 9.1. Explicit Approach: Client-Scoped Interceptor

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryOAuthHttpConfiguration {

    @Bean
    RestClient inventoryOAuthRestClient(
            RestClient.Builder builder,
            InventoryAccessTokenProvider tokenProvider,
            @Value("${integrations.inventory.base-url}")
            String baseUrl) {

        return builder
                .baseUrl(baseUrl)
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().setBearerAuth(
                            tokenProvider.accessToken());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

This client is dedicated strictly to Inventory API. When no cached token exists, the interceptor triggers a call to the AS, adding latency; enforce separate timeouts/token endpoint retry limits. Avoid one client hitting arbitrary dynamic URLs with a default Bearer token, as redirects or cross-origin calls can leak tokens.

### 9.2. Spring Security's `OAuth2ClientHttpRequestInterceptor`

In Spring Security 6.4+ and 7.x, `OAuth2ClientHttpRequestInterceptor` is available for `RestClient`. Spring Security can attach the Bearer token and manage authorized-client lifecycle.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class ManagedOAuthClientConfiguration {

    @Bean
    RestClient inventoryManagedClient(
            RestClient.Builder builder,
            OAuth2AuthorizedClientManager serviceAuthorizedClientManager) {

        var interceptor =
                new OAuth2ClientHttpRequestInterceptor(
                        serviceAuthorizedClientManager);
        interceptor.setPrincipalResolver(
                new RequestAttributePrincipalResolver());

        return builder
                .baseUrl("https://inventory.example.org")
                .requestInterceptor(interceptor)
                .build();
    }
}
~~~

When calling:

~~~java
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

InventoryResponse response = inventoryManagedClient.post()
        .uri("/v1/reservations")
        .attributes(clientRegistrationId("inventory-client"))
        .attributes(principal("order-integration-service"))
        .body(request)
        .retrieve()
        .body(InventoryResponse.class);
~~~

`request` and `InventoryResponse` are application DTOs. Use **one of the two approaches**: either a custom token interceptor or the Spring Security interceptor, never stack both on the same client.

**Version note:** the Spring Security API above is not present in older Boot/Security releases. On Boot 3.2/Security 6.2, use a manager + custom interceptor or a `WebClient` OAuth2 filter instead.

### 9.3. Warning About Default Token Scope

Avoid calling `setDefaultOAuth2AuthorizedClient(true)` on a client serving multiple partners or carrying a logged-in user's token. A default client can attach the token to **every request**; prefer explicit registration/principal resolution or dedicated per-downstream client beans.

## 10. OAuth2 in `WebClient`/Reactive

With Spring WebFlux, use `ReactiveOAuth2AuthorizedClientManager` so acquiring tokens does not block the event loop.

### 10.1. Reactive Manager for Background Services

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class ReactiveOAuth2Configuration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### 10.2. `WebClient` Filter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient inventoryWebClient(
        WebClient.Builder builder,
        ReactiveOAuth2AuthorizedClientManager reactiveManager) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            reactiveManager);

    return builder
            .baseUrl("https://inventory.example.org")
            .filter(oauth2)
            .build();
}
~~~

Request with explicit registration ID:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<InventoryResponse> result = inventoryWebClient.post()
        .uri("/v1/reservations")
        .attributes(clientRegistrationId("inventory-client"))
        .bodyValue(request)
        .retrieve()
        .bodyToMono(InventoryResponse.class);
~~~

The reactive example assumes a stable service-tier principal/context managed per configuration; check the authorized-client cache scope in your runtime environment. Never call blocking `manager.authorize(...)` directly on a Netty event loop.

## 11. HTTP Interface Clients and Spring Integration

With `@HttpExchange` / `@GetExchange`, security is still provided by the underlying `RestClient`/`WebClient`. No interface annotation fetches OAuth2 tokens if the transport is unconfigured.

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.bind.annotation.PathVariable;

@HttpExchange("/v1")
public interface InventoryHttpApi {

    @GetExchange("/products/{sku}")
    InventoryProduct find(@PathVariable String sku);
}
~~~

Create the proxy from the OAuth2-configured `RestClient`:

~~~java
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

HttpServiceProxyFactory factory =
        HttpServiceProxyFactory.builderFor(
                RestClientAdapter.create(inventoryOAuthRestClient))
                .build();

InventoryHttpApi api =
        factory.createClient(InventoryHttpApi.class);
~~~

`InventoryProduct` is an illustrative DTO. `HttpServiceProxyFactory` signatures evolve across Spring Framework versions; verify exact signatures in your project.

Spring Integration HTTP outbound gateways also need their own HTTP client/message sender: declaring an OAuth2 registration in YAML does not make every outbound adapter attach Bearer tokens automatically. For SOAP, transport-level HTTP Basic/Bearer **differs from WS-Security UsernameToken** in the SOAP Header.

Kafka, RabbitMQ, PostgreSQL, and Redis use their own transport/driver authentication and TLS; do not use HTTP API key headers to authenticate Kafka brokers or Redis ACLs.

## 12. Resource Server Must Validate Tokens and Permissions

An access token issued by an OAuth2 AS may carry claims such as:

~~~json
{
  "iss": "https://auth.example.org",
  "aud": ["inventory-api"],
  "scope": "inventory.read inventory.reserve",
  "client_id": "order-integration-service"
}
~~~

This is an illustrative payload, **not a signed JWT**. The Resource Server must validate signature/JWKS or token introspection, expiry, issuer, audience, scopes, and business resource permissions.

For multi-tenant APIs:

- `scope=inventory.reserve` only indicates the operation category.
- The caller must still be authorized for the specific tenant/warehouse.
- Never trust a client-supplied `tenantId` without authorization checks.
- Avoid sharing one client credential across all tenants when policies can be isolated by identity.
- Never forward an Inventory access token to Payment API even if both share an Authorization Server.

### 12.1. Client Credentials Do Not Replace User Delegation

Client Credentials normally represent the service itself, not the current user. If "on behalf of user" semantics or user identity auditing is required, use a proper delegation flow (such as token exchange/authorization-code per policy), rather than stuffing an email/userId into a custom header and treating it as an OAuth2 user claim.

## 13. Token Caching, Expiry, and Errors

~~~mermaid
flowchart TD
    A["Outbound call"] --> B{"Valid access token cached?"}
    B -->|"Yes"| C["Send Bearer token to API"]
    B -->|"No"| D["Call token endpoint"]
    D --> E{"AS issues token?"}
    E -->|"Yes"| F["Save authorized client"]
    F --> C
    E -->|"No"| G["Auth acquisition error"]
    C --> H["Handle result 2xx/401/403/429/5xx"]
~~~

The token cache must be scoped per application principal + registration, use an expiry safety margin, and handle concurrent token acquisition. **Never mint a new token per message** while a valid token can be reused; that overloads the AS and triggers rate limits.

Client Credentials typically have no refresh token: when an access token nears expiry, the client requests a new token under the grant; do not assume the AS returns a `refresh_token`.

### 13.1. Error Matrix

| Response | Common Cause | Resolution |
| --- | --- | --- |
| Token endpoint `invalid_client` | Wrong secret/client auth method | Fix config; do not retry continuously |
| Token endpoint `invalid_scope` | Scope not granted by AS | Fix registration/policy |
| Token endpoint 429/503 | AS overloaded or temporarily down | Bounded retry, backoff/circuit breaker |
| Resource 401 `invalid_token` | Expired/invalid/wrong-audience token | Evict cached token and re-acquire per policy |
| Resource 403 `insufficient_scope` | Valid token lacking required permission | Fix scopes/authorization |
| Resource 429 | Quota/rate limit | Backoff, bulkhead |
| Resource 503 | Downstream unavailable | Retry when side effects are safe |
| HTTPS PKIX error | Missing CA/intermediate | Fix truststore/cert |
| Hostname verification failure | SAN/DNS mismatch | Fix host or certificate |

Specifically: **Token endpoint errors and Resource API errors hit two different downstreams**. If token acquisition failed, Inventory API never received the request. If a valid token was sent yet an Inventory `POST` timed out, the business side effect may already have occurred.

### 13.2. Clock Skew and Concurrency

Authorization Server, Resource Server, and client clocks must be synchronized. Clock skew can cause a resource server to reject a token before the client considers it expired. Configure an appropriate skew margin; never extend token lifetimes by disabling expiry checks on the server.

A service handling hundreds of concurrent calls when a token expires could trigger a stampede to request tokens simultaneously. Check your token manager/cache implementation and real AS capacity, applying backpressure/locking/cache coordination where needed rather than writing an untested custom cache.

## 14. Secrets Management and Credential Rotation

### 14.1. Where Should Secrets Live?

Use Vault/Secret Manager/Kubernetes Secrets/External Secrets or controlled workload identities. Requirements:

- Never commit client secrets/API keys/Basic passwords to Git.
- Never embed secrets in message payloads or outbox rows.
- Never log access tokens, Authorization headers, or token response bodies.
- Restrict read permissions per workload.
- Audit who/which service rotated secrets.
- Maintain a revoke and rotation runbook if a credential leaks.

### 14.2. Basic / API Key Rotation

1. Issue a new credential from the provider; if dual-active is supported, keep the old one active during the cutover window.
2. Update the secret manager.
3. Roll out clients and verify requests succeed with the new credential.
4. Revoke the old credential.
5. Verify error rates and confirm no stale clients remain.

If a `RestClient` was constructed with `defaultHeader`, updating a secret on disk/env **does not automatically update headers** on running clients. Restart/rebuild the client or implement controlled dynamic secret lookup.

### 14.3. OAuth2 Rotation

Rotating `client-secret` affects obtaining new tokens. Previously issued access tokens may remain valid until expiry depending on AS policy. Steps:

- Prepare the new secret/certificate.
- Update the client registration and deploy.
- Verify new tokens are acquired with the right audience/scopes.
- Revoke the old secret after the transition window.
- If existing tokens must be invalidated immediately, use AS revocation/introspection/policy.

For high-security systems, an AS may support `private_key_jwt` or mTLS client authentication instead of shared secrets. Those also require certificate/key lifecycle management and replay protection.

## 15. Timeouts, Retries, and Idempotency

An OAuth2-protected call can span **token acquisition + API call + retries**:

~~~text
Token endpoint connect/read
       ↓
Resource API connect/read
       ↓
Retry delay + additional attempts
       ↓
Business deadline
~~~

Distinguish timeouts:

| Timeout | Impact |
| --- | --- |
| Pool acquisition | Waiting for an idle HTTP connection |
| TCP connect | Opening TCP connection to AS/API |
| TLS handshake | Authenticating server/client and establishing channel |
| Response/read | Waiting for data from AS/API |
| Total operation deadline | Overall time across steps and retries |
| Business deadline | SLA from event/command to business outcome |

**Auth config errors are generally non-retryable.** `invalid_client` and missing scopes cannot be solved by endless exponential retries. For 429/503, bounded retries with jitter may apply per contract.

### 15.1. Timeout After Sending Leaves Outcome Unknown

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant I as Inventory API
    participant D as Inventory Database
    O->>I: POST reserve operationId=R-100, Bearer token
    I->>D: COMMIT reservation
    I--xO: Response lost
    O->>O: Timeout, outcome UNKNOWN
    O->>I: Retry with same operationId
    I->>D: Check idempotency key
    I-->>O: Return original result
~~~

Basic/API key/OAuth2 only authenticate; they **do not prevent duplicate side effects**. For mutating commands, enforce stable `operationId`/idempotency keys, partner status lookups, or reconciliation.

### 15.2. Outbox and Transaction Boundaries

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Update business state"]
    B --> D["Insert outbox intent"]
    D --> E["Outbox worker"]
    E --> F["Obtain credential/token"]
    F --> G["HTTP partner"]
    G --> H["Confirmed / Rejected / Unknown"]
~~~

Write SQL state and outbox intent in the same local transaction, then call the API after commit. If HTTP times out, do not assume failure; the relay retains the intent for retry/reconciliation. Keep tokens out of outbox payloads. Broker consumers only ACK after business processing or durable handoff meets policy.

Never let `RestClient` retry a `POST` 3 times, Spring Retry retry 3 times, and the broker redeliver 3 times without an overall retry budget and monitoring.

## 16. Testing Basic and API Keys

### 16.1. Header Tests with `MockRestServiceServer`

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BasicClientTest {

    @Test
    void includesBasicHeader() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer mock =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
                .baseUrl("https://catalog.test")
                .defaultHeaders(h ->
                        h.setBasicAuth("svc-test", "test-password"))
                .build();

        String raw = "svc-test:test-password";
        String expected = "Basic " +
                Base64.getEncoder().encodeToString(
                        raw.getBytes(StandardCharsets.ISO_8859_1));

        mock.expect(requestTo("https://catalog.test/v1/ping"))
                .andExpect(method(org.springframework.http.HttpMethod.GET))
                .andExpect(header(HttpHeaders.AUTHORIZATION, expected))
                .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

        String body = client.get()
                .uri("/v1/ping")
                .retrieve()
                .body(String.class);

        assertEquals("ok", body);
        mock.verify();
    }
}
~~~

This test uses **fake credentials** and opens no TLS socket. It verifies the Authorization header is formatted properly, not HTTPS trust/SANs. For API keys, assert `X-API-Key` is present on the Pricing client and **absent** on Catalog/Inventory clients.

### 16.2. Testing Against Credential Leakage

- Assert HTTP redirects to another host do not carry credentials.
- Assert wire logs/error messages/metrics contain no Authorization headers or API keys.
- Verify secrets never appear in SQL outbox rows or broker payloads.
- Verify startup fails cleanly if required env secrets are missing/malformed.
- Test key rotation overlap between old/new keys and observe 401/403 behavior per policy.

## 17. Testing OAuth2 Client Credentials

A solid test uses an **Authorization Server stub** and a **Resource API stub**:

~~~text
Order Service
  ├─ AS token stub: /oauth2/token
  └─ Inventory API stub: /v1/reservations
~~~

Key assertions:

1. Token request uses `grant_type=client_credentials`.
2. Client ID/auth method match the token endpoint contract.
3. Client secret never appears in Resource API requests.
4. Resource API receives `Authorization: Bearer test-access-token`.
5. Token is reused while unexpired.
6. Expired token triggers re-acquisition per policy.
7. Token endpoint `invalid_client` does not cause a retry storm.
8. API `401 invalid_token` and `403 insufficient_scope` are classified differently.
9. Inventory token is never sent to Payment API.
10. App principal remains stable across multiple Quartz/broker messages.

Mocking `OAuth2AuthorizedClientManager` checks that the interceptor attaches a Bearer token, yet does not prove **token acquisition/expiry/persistence**. Use WireMock/MockWebServer or equivalent fixtures to test both hops.

### 17.1. Real TLS Testing

Mock HTTP tests do not verify CA chains/hostnames. When environments require mTLS or custom TLS trust, run integration tests against a TLS-enabled test server:

| Case | Expectation |
| --- | --- |
| Valid CA and SAN | HTTPS passes |
| Untrusted CA | SSL handshake fails |
| URL host mismatches SAN | Hostname verification fails |
| Missing client cert when server `need` | Handshake fails |
| TLS passes, missing scope | API 403 |
| OAuth2 Bearer token wrong audience | Resource Server rejects |

Never pass TLS tests using a trust-all manager.

## 18. Observability and Runbook

### 18.1. Measuring the Right Error Categories

| Signal | Meaning |
| --- | --- |
| `integration.auth.token.request` | Token endpoint call count |
| `integration.auth.token.failure` | Token acquisition errors |
| `integration.http.client.duration` | API latency |
| `integration.http.client.unauthorized` | Resource API returned 401 |
| `integration.http.client.forbidden` | Resource API returned 403 |
| `integration.http.client.throttled` | Resource API returned 429 |
| TLS handshake failures | CA/SAN/client certificate issues |
| `integration.outbox.oldest.age` | Unfinished business intents |
| `integration.operation.unknown` | Unconfirmed remote outcomes |

Never merge AS token endpoint latency and Inventory API latency into an undiagnosable "Inventory request duration". When tokens are cached, requests skip the AS; during an AS outage, downstream APIs may keep working until cached tokens expire.

Metric tags should have low cardinality such as `downstream=inventory`, `auth_scheme=oauth2`, `outcome=success/error`. Never use raw tokens/keys, `orderId`, certificate serials, emails, or full URLs with queries as tags.

### 18.2. Log Redaction

Redact these values:

~~~text
Authorization: Basic ****
Authorization: Bearer ****
X-API-Key: ****
client_secret=****
access_token=****
refresh_token=****
~~~

Logs should capture logical partner name, method, route template, status, error category, duration, and trace ID—never secrets or sensitive payloads.

### 18.3. Runbook

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| Basic 401 after deploy | Secret/bean still holds old password | Check secret mounts and rotation |
| API key 403 | Key revoked or missing permission | Check vendor policy |
| OAuth2 `invalid_client` | Wrong secret/client auth method | Fix registration/credentials |
| OAuth2 `invalid_scope` | Scope not granted by AS | Fix permissions |
| Token present yet API 401 | Expired token/wrong audience | Check resource validation/invalidation |
| API 403 | Insufficient scope or business permission | Check policy |
| Unusual spike in token requests | Broken token cache/principal or very short expiry | Check manager and concurrency |
| TLS PKIX path building failed | Missing CA/intermediate | Fix trust material |
| TLS hostname mismatch | SAN mismatches URL | Fix endpoint/certificate |
| 429/503 | Rate limit or outage | Backoff/bulkhead/circuit breaker |
| POST timeout after write | Remote may have committed | Idempotency/status lookup |
| Token appears in logs | Unredacted wire logging | Stop logging, revoke/rotate per incident plan |

**Never fix** 401/403 by granting global permissions, never fix TLS errors with trust-all, and never infinitely retry a revoked client secret.

## 19. Implementation Checklist

- [ ] Selected mechanism per API contract: Basic, API key, or OAuth2 Client Credentials.
- [ ] Resource and token endpoints both use HTTPS with certificate chain/hostname verification.
- [ ] Secrets injected by secret manager/env, never hardcoded or logged.
- [ ] Each partner has an isolated outbound client and credential scope.
- [ ] Basic uses a least-privilege service account with a rotation policy.
- [ ] API key sent in header per vendor contract when possible, avoiding query strings.
- [ ] OAuth2 registration has right client ID, secret/method, token URI, and scopes.
- [ ] For Quartz/outbox/broker workers, manager supports service-tier execution without user sessions.
- [ ] Authorized-client cache uses a stable principal, not per-event/order IDs.
- [ ] Resource Server validates issuer, audience, expiry, scopes, and business permissions.
- [ ] Timeouts, retry budget, and classification of `invalid_client`/401/403/429/503 are clear.
- [ ] Tested token expiry/renewal, rotation, and credential leak prevention.
- [ ] Bearer tokens/API keys never leak via redirects, logs, or outbox/broker payloads.
- [ ] HTTP POST side effects have business idempotency/reconciliation.
- [ ] Covered by header tests, AS + API stub tests, TLS tests, and failure-window tests.
- [ ] Observability separates auth acquisition, HTTP downstream, and business outcomes.

**Remember:** Basic sends username/password, API keys send a vendor-contracted credential, and OAuth2 Client Credentials uses service identity to request a **short-lived access token**. All three require HTTPS, secret protection, explicit client scoping, authorization checks, retries/idempotency, and real testing. In Spring Boot, `RestClient`/`WebClient` only send the right credential when we configure **the exact adapter and HTTP transport**; never smear one downstream's authentication across the entire application.

## References

- [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): client registration, providers, and auto-configuration.
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): managers, service-tier client credentials, and providers.
- [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `RestClient` interceptor and application principals.
- [Spring Security — Reactive Authorized Clients](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): `WebClient` filter/reactive managers.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClient.Builder` and HTTP configuration.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): HTTP Interfaces and client APIs.
- [RFC 7617 — HTTP Basic Authentication](https://www.rfc-editor.org/rfc/rfc7617): Basic scheme, encoding, and challenges.
- [RFC 6749 — OAuth 2.0 Client Credentials](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): grant type.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer tokens and error semantics.
- [RFC 8705 — OAuth2 Mutual-TLS Authentication](https://www.rfc-editor.org/rfc/rfc8705): mTLS token endpoint/client authentication.
- [OWASP — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): storage and rotation.
- [OWASP — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): HTTPS, tokens, and API protection.
