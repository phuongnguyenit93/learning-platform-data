# Renewing Certificates and Credentials While the Application Is Running

In a microservice system using **Spring Cloud LoadBalancer**, Order Service calls Inventory Service using a logical URI such as **https://inventory-service/api/stock/BOOK-01**. LoadBalancer picks a **ServiceInstance** (for example `inventory-a.internal:8443`), while the HTTP transport performs the TLS handshake and the security layer attaches the matching token or credential for the call. After the application has been running for days, **TLS certificates, trust anchors, private keys, OAuth2 access tokens, client secrets, or API keys** can expire or require revocation. If the client only read them at startup, the application may continue using stale values even after the secret store has been updated.

**Renewing while the application is running** (runtime rotation / hot reload) is the process of issuing, verifying, and switching to new security material without forcing the entire system offline. This does not mean simply overwriting a file: the components holding **SSLContext, connection pools, HTTP clients, OAuth2AuthorizedClient, interceptors, or secret snapshots** must actually adopt the new version.

This lesson analyzes **TLS/mTLS rotation** and **credential/token rotation** separately, outlines Spring Cloud LoadBalancer's boundaries, explains how to manage RestClient, RestTemplate, WebClient, and OpenFeign, covers Secret volume integration, Spring Boot SSL bundles / Spring Cloud refresh, two-phase safe cutovers, post-rotation testing, observability, and rollback.

**Scope:** examples use Spring Boot 3.x/4.x, Spring Framework/Spring Security, and compatible Spring Cloud release trains. Package names and reload capabilities can vary across versions. Never assume that a configuration supported on an inbound web server automatically applies to **every outbound HTTP connector**. URLs, domains, certificate paths, and client registrations in this lesson are illustrative only.

## 1. Which Types of Material Need Rotation?

| Security Material | What Is It Used For? | Where Must Updates Take Effect on Change? |
| --- | --- | --- |
| **Server TLS certificate + private key** | Inventory proves server identity | TLS server connector on Inventory |
| **CA/truststore** | Order trusts Inventory's certificate chain | TrustManager/SSLContext of Order's HTTP client |
| **Client certificate + private key (mTLS)** | Order proves identity to Inventory | KeyManager/SSLContext of Order's HTTP client |
| **OAuth2 access token** | Sends Bearer authorization per request | Authorized client/token cache and HTTP interceptor/filter |
| **OAuth2 refresh token** | Exchanges for access token when grant permits | Authorized client manager/store |
| **OAuth2 client secret** | Authenticates application to Authorization Server | ClientRegistration/credentials of token client |
| **API key** | Authenticates to a specific downstream | Secret provider and per-request interceptor |
| **Service-to-service signing key** | Signs/verifies requests or JWTs | Key provider, JWKS/verifier, and key ID contract |
| **Trust policy/revocation state** | Evaluates whether certificates/keys are revoked | Trust validation, CRL/OCSP/transport policies |

Do not lump everything into a **token** variable: access tokens are usually short-lived with built-in reissuance, whereas client secrets or private keys are longer-lived credentials requiring secure rotation through a secret store. Refreshing an access token does **not** replace rotating an mTLS certificate, and vice versa.

### 1.1. Three Dimensions of Rotation

A change often requires synchronizing three places:

1. **Secret source:** Secret Manager, Kubernetes Secret, Vault, PKI/CA, or Authorization Server.
2. **Application/HTTP client:** file watcher, authorized client store, credential provider, TLS context, HTTP connection manager.
3. **Verifier side:** downstream server/trust policy, token issuer, JWKS, or systems accepting the new key.

If only the secret source changes without refreshing the client, requests keep sending stale values. If the client switches to new credentials before downstream accepts them, errors spike. If old material is revoked too early, live connections or in-flight tokens can lose access abruptly.

## 2. Where Does Spring Cloud LoadBalancer Sit in the Security Chain?

~~~mermaid
flowchart TD
    A["Order calls https://inventory-service/api/..."] --> B["@LoadBalanced RestClient/WebClient/Feign"]
    B --> C["LoadBalancer selects ServiceInstance"]
    C --> D["Reconstructs real host:port/scheme URI"]
    D --> E["HTTP connector + connection pool"]
    E --> F["TLS handshake: cert/trust/mTLS"]
    F --> G["HTTP headers: Bearer token/API key"]
    G --> H["Inventory authenticates and authorizes"]
    H --> I["Response / retry / metrics"]
    J["Secret Store / PKI / OAuth2"] --> K["Credential provider + TLS context manager"]
    K --> E
    K --> G
~~~

Spring Cloud LoadBalancer is responsible for **finding and selecting a target**, not issuing certificates, minting access tokens, swapping truststores, or ensuring tokens are refreshed. The logical URI may use a service ID, while TLS executes against **the hostname of the final connected URI**, governed by the HTTP engine.

Division of responsibilities:

| Component | Responsibility | What Not to Expect |
| --- | --- | --- |
| ServiceInstanceListSupplier | Instance list from discovery/cache/health/zone/hint | Issuing tokens, reloading certificates |
| RoundRobin/Random LoadBalancer | Selecting an instance | Verifying CAs or authorizing requests |
| LoadBalancer interceptor/filter | Rebuilding the request URI | Purging all old credentials from pools |
| HTTP client/SSLContext | TLS/mTLS, trust validation, connections | Knowing when an OAuth2 token expires |
| OAuth2AuthorizedClientManager | Acquiring/reissuing tokens per configured provider | Auto-swapping client secrets/mTLS when files change |
| Secret provider | Distributing current credentials | Guaranteeing clients already adopted the new version |
| Backend resource server | Checking tokens, scopes, audience, mTLS policy | Knowing why LoadBalancer picked instance A |

**Debugging clue:** after rotation, requests to A succeed while requests to B hit 401 or TLS handshake errors. A and B may be on **different generations of certificates/trust policies or token validators**, not a broken Round Robin algorithm.

## 3. One-Way TLS and mTLS Differ in What Must Be Refreshed

### One-Way TLS

~~~text
Order (client) ─── TLS ───> Inventory (server)
        verifies Inventory certificate using trust anchors
~~~

When Inventory replaces its server certificate, Order needs a compatible **trust chain** and valid hostname verification. If the CA stays the same and the certificate remains valid for the same hostname, the client can keep trusting it without changing its truststore. If the CA/root/intermediate changes, you must manage **trust rollover**.

### mTLS (Mutual TLS)

~~~text
Order (client cert + private key)
      ─── Mutual TLS verification ───>
Inventory (server cert + private key)
~~~

In addition to Order trusting Inventory, **Inventory also verifies Order's client certificate**. When Order's client certificate expires or is revoked, updating Order's truststore alone is not enough: you must rotate the **key material used by the KeyManager for new handshakes** and ensure Inventory trusts the new CA/client identity.

### 3.1. Lifecycle of an Open Connection

TLS certificates/private keys are normally selected and verified **at the start of a TLS handshake**. An open keep-alive connection **does not re-handshake on every HTTP request**; HTTP/2 can also multiplex many streams over one connection.

Consequently, right after loading new material:

- **Old connections** may keep operating over the already-established TLS session, depending on server/transport policies.
- **New connections** must use the new trust/key material if the HTTP client's TLS context was updated.
- **Old pools** may still retain sockets or an SSLContext captured from the old configuration.
- Changing a certificate file **does not prove** all outbound requests are using the new certificate.

When you must force a certificate-generation switch, **swap the HTTP client/pool cleanly**, stop leasing old connections, wait for in-flight requests to drain, and close old resources within a deadline. Closing the entire pool immediately can break in-flight requests.

## 4. Hostname Validation/SNI When LoadBalancer Rewrites URIs

Suppose code calls:

~~~text
https://inventory-service/api/stock
~~~

LoadBalancer selects:

~~~text
instance-a.internal:8443
~~~

The HTTP engine may connect to:

~~~text
https://instance-a.internal:8443/api/stock
~~~

With TLS, **certificate hostname verification** must match the endpoint identity checked by the client under its real configuration. If the certificate only contains DNS SAN **inventory-service** while the final URI has host **instance-a.internal**, the handshake or hostname verification step can fail. If endpoints are selected by IP, certificates must also cover an **IP SAN** or use an explicitly designed, trusted hostname/SNI mechanism.

Never "quick-fix" with:

- disabling certificate verification;
- using a **trust-all TrustManager**;
- disabling hostname verification;
- accepting arbitrary SNI or spoofing `Host` headers to slip past TLS;
- auto-redirecting bearer tokens to unapproved hosts.

**Proper design:** align service discovery, URI rewriting, DNS, certificate SANs, ingress/mesh topology, and mTLS policies. With a service mesh, TLS may terminate at sidecar proxies rather than inside Java clients; know which layer actually owns certificate rotation.

## 5. Two Phases to Rotate CAs/Trust Without Downtime

When changing a Certificate Authority (CA), swapping every side at once can split the cluster: callers trust only the new CA while some servers still present the old chain.

**Expand → migrate → contract** strategy:

~~~mermaid
flowchart LR
    A["Phase 0: Old CA only"] --> B["Phase 1: Trust old CA + new CA"]
    B --> C["Phase 2: Migrate server/client certs to new CA"]
    C --> D["Verify all instances, pools, and new handshakes"]
    D --> E["Phase 3: Remove old CA once safe"]
~~~

| Phase | Caller Truststore | Backend Certificate | Goal |
| --- | --- | --- | --- |
| 0 | CA-old | CA-old | Initial state |
| 1 | CA-old + CA-new | CA-old | Prepare without breaking existing trust |
| 2 | CA-old + CA-new | Gradually switch to CA-new | Rollout with overlap |
| 3 | CA-new | CA-new on all instances | Narrow trust after verification |

For **mTLS**, run the same sequence in the opposite direction: Inventory's server truststore accepts both old and new client CAs during the transition before Order switches its client certificate. If the new certificate carries a new identity or different scopes, update authorization policies in sync beforehand.

**Overlap duration** must cover Secret propagation, process reloads, connection draining, retries, multi-zone rollouts, and clock skew. Never hardcode "5 minutes is always enough"; size it from actual distribution latency and connection lifetimes.

### 5.1. Distinguishing Routine Certificate Renewal from Compromise Response

For routine expirations, overlap is a sound way to avoid outages. When a **private key is compromised**, however, continuing to accept the old CA/key for long to avoid disruption can be dangerous. Follow incident response: isolate the credential, revoke rapidly, block unintended usage, and accept controlled disruption if needed. **Availability must never be bought by keeping a compromised key trusted.**

## 6. Spring Boot SSL Bundles: Configuration and Reload Limits

Spring Boot lets you declare named **SSL bundles** to manage trust/key material. You can use PEM or JKS/PKCS12 and apply bundles to supporting components.

### 6.1. PEM Bundle for Server TLS

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-server:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/tls/server/tls.crt"
            private-key: "file:/etc/tls/server/tls.key"
server:
  port: 8443
  ssl:
    bundle: inventory-server
~~~

Spring Boot includes a file watcher for bundles supporting **reload-on-update**, with a configurable quiet period:

~~~yaml
spring:
  ssl:
    bundle:
      watch:
        file:
          quiet-period: 2s
~~~

**Caveat:** reload support depends on **which component consumes the SSL bundle**. In current Spring Boot documentation, consumers listed as supporting reload are **Tomcat web server and Netty web server**. Never extrapolate that property into a claim that RestClient, WebClient, Apache HC5, Reactor Netty **outbound clients**, Feign, or all database connections automatically swap their TLS contexts when files change.

Newly reloaded server certificates only affect **new TLS handshakes** per connector implementation; existing connections and external reverse proxies/meshes outside the JVM have their own lifecycles.

### 6.2. Trust Bundle for Outbound Callers

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-trust:
          truststore:
            certificate: "file:/etc/tls/client/inventory-ca.pem"
~~~

Spring Boot provides **SslBundles** and SSL helpers for RestClient/WebClient in supporting versions. Example SSL configuration on `RestClient.Builder`:

~~~java
@Bean
RestClient directInventoryRestClient(
        RestClient.Builder builder, RestClientSsl ssl) {
    return builder
            .baseUrl("https://inventory.example.internal")
            .apply(ssl.fromBundle("inventory-trust"))
            .build();
}
~~~

**This example applies the SSL bundle when building the client; it is not outbound hot reload.** The package of `RestClientSsl` changes between Spring Boot 3.x and 4.x; use imports matching your BOM. To call by service ID via Spring Cloud LoadBalancer, use a **`@LoadBalanced`** builder and ensure certificates/SANs match after URI rewriting.

If runtime trust rotation is needed on outbound clients, verify:

1. Whether the actual HTTP client consumer watches bundle updates.
2. Whether `SSLContext`/`TrustManager` is recreated after updates or frozen from startup.
3. Whether the connection pool issues new connections with the new TLS context.
4. Whether the active RestClient/RestTemplate/Feign/WebClient code path gets swapped after refresh.

**`SslBundles` constructs config material; the TLS engine and connection pool decide whether the new version is used on the next handshake.**

## 7. Kubernetes Secrets: Files Can Change While Apps Still Use Old Values

Kubernetes supports mounting Secrets as files inside containers. When a Secret updates, volume data typically updates via **eventual consistency** (latency depends on kubelet sync and caches/watches). This fits file-based rotation workflows:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order
          image: example/order-service:1.0
          volumeMounts:
            - name: inventory-credentials
              mountPath: /etc/inventory-credentials
              readOnly: true
      volumes:
        - name: inventory-credentials
          secret:
            secretName: inventory-client-tls
~~~

In this example, the secret holds relevant files such as `client.crt`, `client.key`, or `ca.crt`. Application paths point to **files inside the volume**, not copies baked into the classpath/JAR.

### 7.1. Two Major Pitfalls

- **Mounting via `subPath` does not receive Secret updates automatically:** Kubernetes explicitly documents this limitation. Never mount individual certificate files via `subPath` expecting watchers to see changes.
- **Secret values injected as environment variables** are loaded when the container/process starts; updating the Secret does not change environment variables in a running JVM. With env vars, a **rolling restart** is normally required to pick up new versions.

Even with an updated volume, Java libraries still have to **reopen files, reload trust/key material, and apply it to the live client**. An `SSLContext` built from files at startup does not continuously reread those files.

### 7.2. Avoiding Torn Certificate/Key Reads

Secret volumes can use symlinks and atomic snapshot swaps, yet an app reading **`client.crt` first and `client.key` second** right across a filesystem snapshot swap can pair mismatched files. Safe strategy:

1. Version secret material with explicit **generation/version** identifiers.
2. Read certificate and private key from **the same snapshot** whenever possible.
3. Verify the private key matches the certificate's public key.
4. Validate chain, EKU, SAN, validity dates, and trust policy.
5. Publish the new generation only after the entire material set validates.

Kubernetes offers other projected volume types, including cluster-version-dependent credential/certificate sources; never assume every cluster has the newest features. For Kubernetes projected pod certificates, documentation also recommends reading credential bundles from a single snapshot to prevent cert/key skew.

### 7.3. Restricting File Access Permissions

Never place private keys in public ConfigMaps, Git repositories, Docker images, or logs. Enforce least-privilege RBAC on Secrets, restrictive filesystem permissions, encryption at rest per policy, and dedicated secret providers when needed. For mTLS private keys, restrict read access strictly to the process signing handshakes.

## 8. Spring Cloud Refresh Differs from Rotating a TLS Context

Spring Cloud provides **`@RefreshScope`**, `ConfigurationProperties` rebinding, and `/actuator/refresh`. These mechanisms help applications pick up updated config values without restarting the whole process.

Example bean reading a secret from configuration:

~~~java
@ConfigurationProperties(prefix = "inventory.auth")
public record InventoryAuthProperties(String apiKey) {}
~~~

**Do not assume immutable records refresh via rebinding:** Spring Cloud documents that constructor-bound `ConfigurationProperties` (including Java records) cannot be refreshed through standard rebinding. For dynamic config, choose an explicit strategy such as a recreated **`@RefreshScope`** bean or a credential provider managing its own snapshot.

### 8.1. `@RefreshScope` Does Not Automatically Update Every Dependent Object

~~~java
@RefreshScope
@Component
class ApiKeySettings {
    private final String apiKey;

    ApiKeySettings(Environment environment) {
        this.apiKey = environment.getRequiredProperty(
                "inventory.auth.api-key");
    }

    String current() {
        return apiKey;
    }
}
~~~

Spring Cloud can refresh the proxy's target when the refresh scope cache is invalidated. However, if an HTTP interceptor **copied the API key string into its own field** at initialization, it still holds the old value. The right design is an interceptor that **reads a fresh snapshot per request**, or recreating and safely swapping the HTTP client/interceptor.

### 8.2. Refresh Endpoints Are Sensitive Admin Privileges

Never expose `/actuator/refresh`, `/actuator/env`, or Environment-updating POST endpoints to the Internet or broad mesh. Spring Cloud requires explicit exposure configuration to enable endpoints; guard them with authentication, authorization, network policies, auditing, and secret hygiene.

A bad refresh can break authentication, swap in an invalid truststore, or trigger rebuilding multiple HTTP clients under live traffic. Never treat refresh endpoints as routine endpoints for arbitrary callers.

**Note:** Spring Cloud Context Refresh is unsupported in certain AOT/native-image setups; documentation instructs disabling refresh accordingly. When running native images, pick dynamic credential providers or rolling restarts per actual support.

### 8.3. When Is a Rolling Restart Better Than Hot Reload?

Rolling restarts are usually easier to verify when:

- The HTTP client/transport does not support swapping `SSLContext` at runtime.
- Secrets are injected via environment variables.
- The team lacks a proven atomic-swap and safe connection-drain mechanism.
- Security policy requires completely deterministic client state after rotation.

This is not a failure of "zero downtime": **rolling deployments with readiness/liveness probes, sufficient replicas, and graceful shutdown** keep services serving smoothly while pods cycle. Choose hot reload when clearly required and tested—not out of an urge to avoid restarts at any cost.

## 9. Safe TLS Rotation Workflow for Outbound HTTP Clients

A rotation workflow should proceed as follows:

~~~mermaid
flowchart TD
    A["Secret/PKI issues generation N+1"] --> B["Distribute files/trust material"]
    B --> C["Reader detects new version"]
    C --> D["Read atomically + validate cert/key/chain"]
    D --> E{"Valid?"}
    E -->|No| F["Keep N, log error and alert"]
    E -->|Yes| G["Build SSLContext + HTTP client/pool generation N+1"]
    G --> H["Canary handshake with new credential"]
    H --> I{"Valid identity/trust?"}
    I -->|No| F
    I -->|Yes| J["Atomic swap new client for new requests"]
    J --> K["Drain in-flight requests on generation N"]
    K --> L["Close pool N at deadline"]
    L --> M["Metrics: activeGeneration=N+1"]
~~~

### 9.1. Why Build Both a New TLS Context and a New Pool?

HTTP engines normally build `SSLContext`/`TrustManager`/`KeyManager` when configuring connectors or opening connections. Some engines support dynamic material updates, yet there is no universal contract that all contexts/pools update automatically when files change.

The high-determinism approach is:

1. Build a **new client generation** with the new TLS material.
2. Run a **canary TLS handshake** against an appropriate test endpoint.
3. **Atomically swap** the pointer to the new client for new requests.
4. Let in-flight requests on the old client finish or hit their deadline.
5. Stop leasing old connections and close the old generation's pool.

Architecturally this applies to **RestClient + Apache HC5**, **RestTemplate**, **WebClient + Reactor Netty**, or **OpenFeign** transports, though **how resources drain and close differs**. Never take an Apache HC5 `close()` pattern and apply it verbatim to Reactor Netty/Feign.

### 9.2. Atomic Swap Pseudocode

~~~java
// PSEUDOCODE: ClientGeneration and factory are application-defined abstractions.
final class OutboundClientRouter {

    private final AtomicReference<ClientGeneration> active;

    OutboundClientRouter(ClientGeneration initial) {
        this.active = new AtomicReference<>(initial);
    }

    Mono<StockResponse> getStock(String sku) {
        // Capture generation on subscription when using Reactive streams.
        return Mono.defer(() -> {
            ClientGeneration generation = active.get();
            return generation.acquireAndCall(sku)
                    .doFinally(signal -> generation.release());
        });
    }

    void publishRotation(ClientGeneration verifiedNewGeneration) {
        ClientGeneration previous =
                active.getAndSet(verifiedNewGeneration);
        previous.stopAcceptingNewRequests();
        previous.closeAfterInFlightDrain();
    }
}
~~~

**This is not complete compilable code:** classes/methods `ClientGeneration`, `acquireAndCall()`, `release()`, drain, and reference counting are application-designed. It illustrates **never mutating the `SSLContext` of a client currently serving requests**. Moreover, `stopAcceptingNewRequests()`/`closeAfterInFlightDrain()` must guarantee atomicity between reading the generation and incrementing the in-flight reference count; otherwise a race can hand a new request an old generation that was just closed.

Especially in reactive code:

- A cold `Mono` may be subscribed **after** `getStock()` returns. Capture the client generation at subscription time or hold a valid lease.
- Each generation can have long-lived SSE/NDJSON in-flight streams. Enforce a **max drain duration** and an explicit stream-closing policy.
- Test concurrency and memory visibility under concurrent requests, not merely sequential runs.

### 9.3. Defining What Counts as a Successful Rotation

Never report success simply because a file watcher noticed a new file. A rotation succeeds when:

- The new material is valid and unexpired.
- The new HTTP client generation is published.
- **New connections** verify the right server cert or client cert identity.
- Calls by **service ID** preserve zone/hint/routing behavior.
- New requests route through the new generation.
- Old requests drain/close within bounds.
- TLS/401/403 errors do not spike abnormally.

If any step fails, keep the old generation while safe, fire alerts, and trigger rollback/incident procedures. **Never fall back to trust-all** "just to keep requests moving".

## 10. Configuration for RestClient, RestTemplate, and Apache HC5

Spring Boot can supply `RestClientSsl` and compatible builders to read bundles at initialization. With Apache HttpClient 5, TLS handling typically runs through Apache's connection manager/SSL strategy/trust config.

What to verify:

| Object | If Built Once at Startup | When Certificates Change |
| --- | --- | --- |
| RestClient | Holds request factory from startup | Does not automatically rebuild by default |
| RestTemplate | Holds request factory/interceptors | Does not automatically rebuild by default |
| Apache HC5 CloseableHttpClient | Holds pool/manager | Must decide how to swap manager/TLS material |
| Pool active connections | Hold established TLS sessions | Continue/close per drain policy |
| TLS trust material | May be baked into SSLContext/manager | Verify refresh hook or swap generation |

### 10.1. Do Not Just Put `@RefreshScope` on `RestClient.Builder`

Wrong assumption example:

~~~java
@Service
class InventoryClient {
    private final RestClient client;

    InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://inventory-service")
                .build();
    }
}
~~~

If the builder bean refreshes later, **the built client stored in `InventoryClient`'s `final` field** does not update automatically. To hot-reload physical clients, you must:

- place the right **client/adapter** inside the refresh boundary and prove resource lifecycles are cleaned up; or
- use a **routing/delegating client** resolving the active generation; or
- perform a rolling restart.

For an Apache HC5 request factory, close the old connection manager **after** draining—never send new requests onto a closed factory.

### 10.2. Token Rotation Does Not Always Require Replacing the RestClient Object

If `RestClient` attaches an interceptor reading a fresh token **on every request**, access tokens can rotate without rebuilding the `SSLContext`/pool:

~~~java
@Bean
RestClient inventoryClient(
        RestClient.Builder builder,
        CurrentTokenProvider tokenProvider) {
    return builder
            .baseUrl("https://inventory.example.internal")
            .requestInterceptor((request, body, execution) -> {
                String token = tokenProvider.getValidToken();
                request.getHeaders().setBearerAuth(token);
                return execution.execute(request, body);
            })
            .build();
}
~~~

`CurrentTokenProvider` is an application abstraction; it must manage expiry, synchronized refreshes, safe retries, and avoid token leakage. This snippet illustrates **attaching tokens at request time**, not a full OAuth2 implementation.

If the same `RestClient` calls **multiple external hosts** outside Inventory's scope, that interceptor can send the token to the wrong target. Use dedicated clients per downstream/audience, enforce redirect policies, and never copy `Authorization` across domains.

## 11. WebClient and Reactor Netty: TLS Context Differs from Token Filters

With **WebClient**, connection SSL/TLS is normally handled by `ClientHttpConnector`, such as `ReactorClientHttpConnector` backed by **Reactor Netty `HttpClient`**. An `ExchangeFilterFunction` can attach HTTP tokens per request.

These two mechanisms operate at different layers:

~~~text
WebClient request
  |
  +-- ExchangeFilterFunction adds Bearer token to HTTP header
  |
  +-- ReactorLoadBalancerExchangeFilterFunction selects instance
  |
  +-- ReactorClientHttpConnector
       |
       +-- HttpClient/ConnectionProvider: TLS context + connections
       +-- SSL handshake when opening a new socket
~~~

Swapping a Bearer token **normally does not require closing TCP pools**. Conversely, swapping a **client mTLS private key** normally requires ensuring the connector performs new handshakes with the new identity. With pooled connections, replacing a file on disk is not enough.

### 11.1. SSL Bundles Applied When Building WebClient

Spring Boot provides the `WebClientSsl` helper:

~~~java
@Bean
WebClient directInventoryWebClient(
        WebClient.Builder builder,
        WebClientSsl ssl) {
    return builder
            .baseUrl("https://inventory.example.internal")
            .apply(ssl.fromBundle("inventory-trust"))
            .build();
}
~~~

This applies the SSL bundle when **creating WebClient**; rotating trust/key material at runtime requires verifying whether the connector/consumer actually updates. Never assume Boot's helper automatically swaps SSL contexts inside existing pools. `WebClientSsl`'s package changes across Spring Boot versions; import the right one for your version.

To call **https://inventory-service**, use a **`@LoadBalanced WebClient.Builder`** and write an integration test verifying physical URIs/SANs/hostname verification remain valid.

### 11.2. Reactor Netty Client Generations

Design pattern for outbound mTLS:

~~~text
generation 17:
  SslContext(old certificate/key/trust)
  HttpClient(old SSL configuration)
  ConnectionProvider(old pool)
  WebClient(old connector)

generation 18:
  SslContext(new certificate/key/trust)
  HttpClient(new SSL configuration)
  ConnectionProvider(new pool)
  WebClient(new connector)
~~~

After generation 18 passes testing, the routing adapter directs new requests to WebClient 18. Pool 17 drains and closes per lifecycle and grace period.

**Note on Reactor Netty resources:** `HttpClient`, `ConnectionProvider`, and `LoopResources` can use global/shared resources. Never call `dispose()` recklessly on global resources as it can break other WebClients. Explicitly own **each application-created pool** and scope disposal strictly to it.

### 11.3. Reactive Does Not Mean Rotation Is Automatically Atomic

With WebClient:

- Creating a `Mono` does not mean the request has started.
- Subscription time after a swap is when client generation should be chosen.
- Canceling a request during drain can close the HTTP stream or interrupt backend work, yet **cannot roll back side effects that already happened**.
- A retrying operation can accidentally span **two certificate generations** if it picks a fresh client per attempt. Define and test this explicitly, especially while downstream policies are transitioning.

Never swap an SSL context mid-flight inside an existing TLS session. The TLS handshake establishes a connection's identity; to be certain new requests use new credentials, verify connection acquisition and pool lifecycles.

## 12. OpenFeign: Credentials per RequestInterceptor, TLS per HTTP Engine

OpenFeign in Spring Cloud typically uses **`FeignBlockingLoadBalancerClient`** to select a `ServiceInstance`. TLS is executed by the underlying HTTP client such as **Apache HttpClient 5**, **OkHttp**, or another client.

Example API key provider invoked **on every request**:

~~~java
interface RotatingApiKeyProvider {
    String currentKey();
}

@Configuration(proxyBeanMethods = false)
class InventoryFeignAuthConfiguration {

    @Bean
    RequestInterceptor inventoryApiKeyInterceptor(
            RotatingApiKeyProvider provider) {
        return template ->
                template.header("X-Inventory-Api-Key", provider.currentKey());
    }
}

@FeignClient(
        name = "inventory-service",
        configuration = InventoryFeignAuthConfiguration.class)
interface InventoryFeignClient {
    @GetMapping("/api/stock/{sku}")
    StockResponse stock(@PathVariable("sku") String sku);
}
~~~

**API key illustration only**, not a standard OAuth2 pattern. In production, `InventoryFeignAuthConfiguration` must be scoped **strictly to the named client**; if picked up by component scanning as a global Feign configuration, the interceptor can attach Inventory's API key onto requests of **other Feign clients**. Place it outside global scan packages or isolate configs appropriately.

### 12.1. Rotating an API Key Differs from Rotating an mTLS Certificate

- **API key:** once the provider returns the new value, Feign's `RequestInterceptor` attaches the new header on the next request without recreating pools.
- **OAuth2 bearer:** requires an authorized client manager handling expiry, scopes, audience, and token storage.
- **mTLS certificate/trust:** lives in Feign's underlying HTTP engine, typically requiring client/connection-manager reconfiguration and drain, or a rolling restart.

Never refresh just a Feign `RequestInterceptor` bean expecting **SSL sockets** to swap certificates; those are two separate layers.

### 12.2. Timeouts/Retries When Credentials Change

Feign, Spring Cloud LoadBalancer, and reverse proxies may each have retry policies. When a server returns **401/403**, never retry blindly with the same stale credential:

- 401 can stem from an expired token, revoked key, wrong issuer/audience, or clock skew.
- 403 can stem from mismatched scopes/policies, which refreshing a token usually will not fix.
- If refreshing an access token after 401 is supported, do so in **one bounded step** and ensure request bodies can be safely replayed.
- POSTs creating reservations/payments may have already caused side effects; retries require idempotency.

A fresh token does not guarantee the endpoint still grants the same scopes or permissions. Successful rotation must verify **authorization outcomes**, not merely that the token string changed.

## 13. OAuth2 Access Tokens, Refresh Tokens, and Client Secrets Have Different Lifecycles

For **OAuth2 `client_credentials`**, the app uses its client ID/secret (or another client authentication method) to **request a new access token** when needed. This grant usually does not issue refresh tokens like `authorization_code`; when the access token expires, call the Token Endpoint for a new token per provider policy.

For **`authorization_code` + `refresh_token`**, an authorized client manager can exchange an expired access token via the refresh token if configured and valid. **Never implement an "infinite 401 → refresh → replay" loop.**

### 13.1. Spring Security RestClient OAuth2

Spring Security supports **`OAuth2ClientHttpRequestInterceptor`** paired with **`OAuth2AuthorizedClientManager`**:

~~~java
@Bean
RestClient securedInventoryRestClient(
        RestClient.Builder builder,
        OAuth2AuthorizedClientManager manager) {

    OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(manager);

    oauth2.setClientRegistrationIdResolver(
            request -> "inventory-client");

    return builder
            .baseUrl("https://inventory.example.internal")
            .requestInterceptor(oauth2)
            .build();
}
~~~

This snippet illustrates **delegating token acquisition/renewal to Spring Security**, rather than hardcoding Bearer tokens. In service-to-service `client_credentials` backends, configure an appropriate **`ClientRegistrationRepository`, `OAuth2AuthorizedClientManager`/provider, and principal scope**; a default manager tied to a logged-in user does not fit scheduled jobs.

**Do not confuse:** the interceptor can fetch a new token when the old token expires, yet if the **OAuth2 client registration's client secret** rotates in the secret store, a manager/repository/token HTTP client holding old config can still send the old client secret. Rotating a **client secret** requires updating `ClientRegistration` or building a new auth-client generation and clearing caches per policy.

### 13.2. Spring Security WebClient OAuth2

For reactive apps, Spring Security provides **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** with **`ReactiveOAuth2AuthorizedClientManager`**:

~~~java
@Bean
WebClient securedInventoryWebClient(
        WebClient.Builder builder,
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
    oauth2.setDefaultClientRegistrationId("inventory-client");

    return builder
            .baseUrl("https://inventory.example.internal")
            .filter(oauth2)
            .build();
}
~~~

This pattern is for a **backend-specific client**, not for attaching a default token onto every `WebClient` in the app. Spring Security documentation warns that overly broad default authorized clients can send access tokens to unintended URLs.

To combine with Spring Cloud LoadBalancer, use a **`@LoadBalanced`** builder and test the filter chain. When the OAuth2 filter calls the Authorization Server itself, it needs a dedicated HTTP client/target so it does not create a circular dependency on the `inventory` service ID.

### 13.3. Caching and Token Refresh Thresholds

Suppose:

~~~text
access_token.expires_at = 12:00:00
clock_skew             = 30 seconds
request starts         = 11:59:40
~~~

If a downstream call can take 45 seconds, a token picked at 11:59:40 **can expire before the backend verifies it**. An authorized client provider normally applies clock skew and an early-refresh window before expiry; tune these to match real network latencies and clock skew.

Never store tokens permanently in a `final` field, cache under keys missing audience/scope/tenant, or share authorized clients across unequal principals. Conversely, never hit the Token Endpoint on **every request** while the token is still valid, as that causes excessive load and races.

### 13.4. Preventing "Thundering Herds" at Token Expiration

Many concurrent requests noticing an expired token can flood the Authorization Server simultaneously. A credential provider should:

- Cache by client registration and matching principal/audience/scope.
- Use **single-flight refresh** or proper synchronization to avoid hundreds of duplicate refreshes.
- Enforce timeouts, bounded retries, and a dedicated circuit-breaker/bulkhead for the **Token Endpoint**.
- Never reuse expired tokens indefinitely when the Authorization Server fails.
- Never log access tokens, refresh tokens, or client secrets in logs or metrics.

During key rotation at the Authorization Server, coordinate new token issuance timing with resource servers' ability to verify new JWT/JWKS keys. Rotating a client secret and rotating JWT signing keys are **two distinct workflows**.

## 14. API Key Rotation: Updating Snapshots Safely Across Threads

For systems using API keys instead of OAuth2, the golden rule is **never capture the API key into an interceptor at initialization**.

Example that **does not support runtime rotation**:

~~~java
String apiKeyAtStartup = secretProvider.readKey();

RestClient client = RestClient.builder()
        .defaultHeader("X-Inventory-Api-Key", apiKeyAtStartup)
        .build();
~~~

If `secretProvider` receives a new value 10 minutes later, that `RestClient` still holds the old value. Never try to fix this by mutating `defaultHeaders` on a singleton client from another thread.

### 14.1. A Provider Reading Snapshots per Request

~~~java
final class RotatingApiKeyProvider {
    private final AtomicReference<String> current =
            new AtomicReference<>();

    RotatingApiKeyProvider(String initial) {
        publish(initial);
    }

    String currentKey() {
        String key = current.get();
        if (key == null) {
            throw new IllegalStateException("No active API key");
        }
        return key;
    }

    void publish(String validatedNewKey) {
        if (validatedNewKey == null || validatedNewKey.isBlank()) {
            throw new IllegalArgumentException("Invalid API key");
        }
        current.set(validatedNewKey);
    }
}
~~~

This is an **illustrative data pattern**, not a production credential store. In practice:

- Never rely on `isBlank()` as the sole validation; check key ID/version, policy, and run a verification probe against a test endpoint.
- Load secrets from an authenticated provider, never from externally supplied client headers.
- Never print keys in exceptions/logs; log only non-sensitive **generation IDs**.
- Java `String` does not guarantee immediate memory zeroization after replacement; for high-security needs, consider key handles/HSMs/credential libraries with proper lifecycles.
- API key overlap may be needed: the server accepts both old and new keys during transition and revokes the old key only once all callers have updated.

### 14.2. WebClient Filter Pattern Fetching Keys per Subscription

~~~java
ExchangeFilterFunction apiKeyFilter = (request, next) ->
        Mono.defer(() -> {
            ClientRequest updated = ClientRequest.from(request)
                    .headers(headers -> headers.set(
                            "X-Inventory-Api-Key",
                            rotatingApiKeyProvider.currentKey()))
                    .build();
            return next.exchange(updated);
        });

WebClient client = webClientBuilder
        .baseUrl("https://inventory-service")
        .filter(apiKeyFilter)
        .build();
~~~

`rotatingApiKeyProvider` is the bean from the corresponding example; `webClientBuilder` must be `@LoadBalanced` if using a service ID host. `Mono.defer` ensures the key is fetched **when the request is subscribed**, fitting the cold `Publisher` model.

Never register a global filter attaching Inventory's API key to other downstreams. Every key must bind strictly to its **audience/host/service scope** with least privilege. Never send secret headers across redirects to untrusted hosts.

### 14.3. Never Use Refresh to "Recover" a Revoked Token

When an old API key is revoked on the server, requests carrying the old value may receive 401/403. The right response is **adopting the newly distributed version** or failing closed if unavailable—never falling back to an unauthorized key or retrying endlessly.

If the server supports a dual-key window, move all callers to the new key before revoking the old one. If key exposure is detected, revoke rapidly and trigger the security incident playbook.

## 15. Ordering mTLS and HTTP Credential Rotation by Environment

There is no single fixed sequence for every system. Evaluate two axes:

1. **Transport identity:** TLS certificates/trust, SANs, mTLS client certs.
2. **Application identity:** Bearer tokens, API keys, OAuth2 scopes, and audiences.

Example scenario:

~~~text
Inventory currently:
    server cert CA-old
    accepts client cert CA-client-old
    accepts tokens from issuer/key-old

Order currently:
    trusts CA-old
    client cert CA-client-old
    tokens issued by issuer/key-old
~~~

When rotating both PKI and OAuth2:

1. Distribute new trust anchors in both directions **before** swapping certificates.
2. Have resource servers accept **new JWT signing keys** (plus old keys during overlap, if policy allows).
3. Issue new server/client certificates and roll out via canary.
4. Ensure OAuth2 client registrations/token managers hold the new credentials.
5. Switch outbound client generations; test new TLS handshakes + Bearer authorization.
6. Monitor **mTLS handshake failures** separately from 401/403 (application auth).
7. Revoke old material after overlap ends, draining finishes, and security checks pass.

During a security incident, policy may require **immediate revocation** instead of maintaining overlap. Keep separate runbooks for routine expirations vs. compromised credentials.

### 15.1. JWT/JWKS Rotation Has Two Distinct Directions

- **Issuer/Auth Server:** generate new signing key, publish public key with key ID (`kid`), start signing new tokens, retain old keys long enough to verify live tokens when policy permits.
- **Resource server:** update JWKS/verifier caches to accept the new key before the issuer signs tokens with it, accounting for framework cache TTL/refresh behavior.

Never conflate updating a **resource server's JWKS** with reloading an **HTTP client's mTLS truststore**. Both involve public keys, yet serve completely different verification responsibilities.

### 15.2. Clock Skew and Validity Windows

NTP/clock skew affects both certificate validity (`notBefore`/`notAfter`) and OAuth2/JWT `nbf`/`exp`. If instance A's clock drifts by a few minutes while B's is accurate, clients can observe Round Robin failures even with identical credentials. Monitor time synchronization and apply reasonable skew policies—never disable expiration checks to mask skew.

## 16. Load Balancing During Rotation: Avoiding Half the Cluster on Old Policies

Spring Cloud LoadBalancer can pick **any eligible `ServiceInstance`** after discovery/cache/zone/hint filters. If Inventory instances roll out certificates or auth policies unevenly, requests can look like:

~~~text
Request 1: LB picks A -> TLS OK, HTTP 200
Request 2: LB picks B -> TLS handshake failed
Request 3: LB picks C -> TLS OK, HTTP 401
Request 4: LB picks A -> HTTP 200
~~~

Do not "fix" this by increasing retries endlessly. Retrying onto another instance can hide canary failures and distort error rates. Instead:

- Verify **A/B/C** individually with TLS handshakes and authenticated requests on each generation.
- Record **service ID, instance ID, zone, and certificate generation** in safe telemetry.
- Ensure publishers/registries/health checks reflect true readiness of the updated backend.
- Use **canary/rolling rollouts** before removing old CAs/keys.
- Bound retries; **never blindly retry 401/403** like timeouts/503s.

If you need to stop routing to an instance not yet meeting policy, update readiness/health or controlled metadata/routing. **`ZonePreference`** is not an mTLS authentication mechanism; a hint header is never proof of identity.

### 16.1. Service ID Differs from Physical TLS Identity

In logs, distinguish:

~~~text
logicalServiceId = inventory-service
selectedInstance = inventory-b
physicalHost     = inventory-b.internal
tlsPeerIdentity  = verified certificate SAN/subject
httpAuthAudience = inventory-api
credentialGen    = token-key-2026-11
~~~

Never log token values, private keys, raw certificate bytes, or client secrets. You may log a **public certificate fingerprint** when policy permits, though it never replaces chain/hostname verification and may still expose infrastructure details.

### 16.2. Retries and Credential Rotation

One logical request can span two attempts across two generations:

~~~text
Attempt 1 (generation N):
    TCP/TLS OK -> HTTP 401 due to expired token

Credential provider acquires fresh token or generation N+1 publishes

Attempt 2 (generation N+1):
    TLS OK -> HTTP 200
~~~

Permit this retry path **only if the OAuth2 provider and application contract support it**; avoid replaying state-changing POSTs without idempotency. If both Spring Cloud LoadBalancer and an OAuth2 filter retry independently, attempt counts can multiply.

## 17. Unit Testing: Proving Headers Actually Changed

A WebClient test with a fake `ExchangeFunction` can confirm **header values** are reread after publish:

~~~java
@Test
void usesCurrentApiKeyOnEachSubscription() {
    RotatingApiKeyProvider provider =
            new RotatingApiKeyProvider("key-generation-1");

    List<String> observed = new CopyOnWriteArrayList<>();

    ExchangeFunction fake = request -> {
        observed.add(request.headers()
                .getFirst("X-Inventory-Api-Key"));
        return Mono.just(ClientResponse.create(HttpStatus.OK)
                .body("ok")
                .build());
    };

    ExchangeFilterFunction rotating = (request, next) ->
            Mono.defer(() -> {
                ClientRequest updated = ClientRequest.from(request)
                        .headers(headers -> headers.set(
                                "X-Inventory-Api-Key",
                                provider.currentKey()))
                        .build();
                return next.exchange(updated);
            });

    WebClient client = WebClient.builder()
            .exchangeFunction(fake)
            .filter(rotating)
            .build();

    Mono<String> call = client.get()
            .uri("https://inventory.example.internal/test")
            .retrieve()
            .bodyToMono(String.class);

    StepVerifier.create(call).expectNext("ok").verifyComplete();
    provider.publish("key-generation-2");
    StepVerifier.create(call).expectNext("ok").verifyComplete();

    assertEquals(List.of("key-generation-1", "key-generation-2"),
            observed);
}
~~~

Example imports: `CopyOnWriteArrayList`, `List`, `Mono`, `StepVerifier`, `WebClient`, `ExchangeFunction`, `ExchangeFilterFunction`, `ClientRequest`, `ClientResponse`, `HttpStatus`, and JUnit assertions. String keys here are dummy test data.

**This test does not verify TLS, mTLS, or LoadBalancer.** It only confirms the WebClient filter reads the fresh snapshot per subscription. To prove certificates/connection pools swapped, run HTTP/TLS integration tests.

## 18. Integration Testing: Rotating Certificates Without Restarting the Caller

To genuinely prove **hot TLS rotation**, run a real HTTPS/mTLS test server rather than mocking HTTP responses. You can use **HTTPS MockWebServer**, HTTPS WireMock, or an embedded Netty/Tomcat test server with two certificate generations issued by test CAs.

### 18.1. Preparing Test PKI

Create two sets of test material **containing no production keys**:

~~~text
CA-old
  └── inventory-old.crt + inventory-old.key
  └── order-client-old.crt + order-client-old.key

CA-new
  └── inventory-new.crt + inventory-new.key
  └── order-client-new.crt + order-client-new.key
~~~

Test certificates must carry **valid SANs** for the hostnames used by the HTTP client, such as `localhost` or test domains; never disable hostname verification just to make tests pass easily. If tests use `localhost`, certs need `DNS:localhost`; if using an IP literal, certs need the matching IP SAN.

Spin up two servers or one server capable of swapping certificates/`SSLContext` for **new handshakes**. Open fresh connections using generation N and N+1 clients to verify trust transition cases.

### 18.2. Trust Rollover Test Matrix

| Client Trust | Server Certificate | Expectation |
| --- | --- | --- |
| CA-old | CA-old | TLS succeeds |
| CA-old | CA-new | TLS fails because new CA is untrusted |
| CA-old + CA-new | CA-old | TLS succeeds during overlap |
| CA-old + CA-new | CA-new | TLS succeeds during overlap |
| CA-new | CA-new | TLS succeeds after rotation |
| CA-new | CA-old | TLS fails once old CA is removed |
| CA-new, wrong SAN | CA-new, mismatched hostname | TLS/hostname verification fails |
| CA-new, mismatched private key | Invalid config | Rejects publishing new generation |

Each case must force a **fresh TCP/TLS handshake**, never reusing an already-open connection. If requests 1 and 2 share an HTTP/2 connection, tests can pass on the old TLS session even though the new truststore **was never applied**.

### 18.3. mTLS Test Matrix

Beyond server trust, Inventory must verify client identity:

| Client Certificate | Server Trust for Clients | Outcome |
| --- | --- | --- |
| client-old | CA-client-old | Succeeds |
| client-new | CA-client-old | Fails when CA-new is not yet trusted |
| client-new | CA-client-old + CA-client-new | Succeeds during overlap |
| client-new | CA-client-new | Succeeds after rotation |
| expired client certificate | Valid trust chain | Fails certificate validity check |
| no client certificate | Server requires mTLS | Handshake fails |

If the server also enforces authorization from certificate principals, verify identity, roles, and policies as well—not handshake success alone.

### 18.4. Testing Connection Pool Draining

1. Open a slow request A (server delays body) on generation N.
2. Wait until A genuinely begins executing on the server.
3. Publish generation N+1 after a canary handshake succeeds.
4. Send new request B and verify B uses **generation N+1 connection + client certificate**.
5. Let A finish and verify its body/status are not prematurely severed.
6. Confirm pool N stops accepting new requests and closes after draining.
7. Repeat with request A timing out/canceling to confirm zero in-flight reference leaks.

Look beyond HTTP status codes. Measure accepted connections/handshakes, peer certificate identities, active/idle pools, and per-generation request counts; log only safe fingerprints/key IDs, never private keys.

## 19. Integration Testing: Rotating API Keys/OAuth2 Under Traffic

Tests should span at least three layers:

### 19.1. Two-Phase API Key Test

A mock backend maintains state:

~~~text
Phase 0: accepts only key-old
Phase 1: accepts key-old and key-new
Phase 2: accepts only key-new
~~~

Test steps:

1. Client using `key-old` calls API, receives 200.
2. Server enables dual acceptance.
3. Credential provider publishes `key-new`.
4. New requests use `key-new` and receive 200 **without restarting the JVM**.
5. Server stops accepting `key-old`.
6. Confirm zero new requests use `key-old`; all new requests succeed.

Specifically test that keys never leak to a **second downstream** on redirects or when an HTTP client shares multiple base URLs.

### 19.2. OAuth2 Token Renewal Test

Using a mock Authorization Server or integration-test provider:

- Token T1 has a short expiry.
- Authorized client manager is properly configured for the grant (`client_credentials` or `refresh_token`).
- HTTP requests before expiry reuse T1 per cache policy.
- Once T1 expires or crosses the refresh threshold, the manager acquires token T2.
- Backend accepts T2, rejects expired tokens, and checks scopes/audience.
- When many concurrent requests trigger renewal together, token-endpoint calls do not spike uncontrollably.

**Do not conflate token renewal tests with client secret rotation.** A `client_credentials` flow can renew access tokens frequently while still using the old client secret. Testing client secret rotation must swap **registration/auth credentials** and verify new token requests use the new secret generation.

### 19.3. Controlled Failure Tests

| Injected Fault | Expected Behavior |
| --- | --- |
| Secret file temporarily holds mismatched cert/key | Does not publish new generation; keeps old generation if still safe |
| Secret volume has not updated yet | Does not report rotation success; metrics/alerts show pending |
| New API key not yet accepted by server | Canary fails; full traffic does not switch |
| Auth Server temporarily failing | No refresh storm; explicit timeout/backoff/deadline |
| Client secret revoked | Does not retry endlessly with old secret |
| Backend A rotated, B did not | Per-instance canary catches it; not masked by endless retries |
| Old connection closes after swap | In-flight requests drain per policy with no leaks |
| Old CA compromised | Revoked per security runbook; overlap not extended against policy |

### 19.4. Incorporating Spring Cloud LoadBalancer into Tests

Run two HTTPS/mTLS servers as **`ServiceInstance`s** of `inventory-service` via `SimpleDiscoveryClient` or a test supplier:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: https://inventory-a.internal:8443
              - uri: https://inventory-b.internal:8443
~~~

Host/port values here are examples; real tests should use dynamic ports with SAN-aligned test DNS/hostnames, or a controlled custom DNS resolver in tests.

Verify both requests via **`https://inventory-service`** and **the selected instance's TLS identity**, not just the logical URI. Calling `localhost` directly only exercises the HTTP transport without proving Spring Cloud LoadBalancer integration.

## 20. Observability: Knowing Which Generation Is Active

A rotation dashboard saying only "Secret updated at 12:00" is insufficient. Capture these signals:

| Signal | Question Answered |
| --- | --- |
| Active credential generation | Which version has the app published? |
| Secret observed generation | Which version has the file watcher/provider seen? |
| Certificate `notAfter`/days remaining | How soon will it expire? |
| Last successful client TLS handshake post-rotation | Is the client genuinely using the new material? |
| Rotation validation failures | Parse errors, key mismatch, chain/SAN errors? |
| TLS handshake failure rate | Trust/mTLS/SNI errors per instance? |
| HTTP 401/403 rate | Are application authorization failures rising? |
| OAuth2 token refresh failures | Are the token endpoint/client secret failing? |
| Old generation in-flight connections | How many requests/sockets remain to drain? |
| Connection pool pending/active | Did rotation trigger a connection storm? |
| Service ID / instance ID / zone | Are failures isolated to one backend or zone? |
| Rollout completion | How many pods/generations have updated? |

### 20.1. Never Let Metrics Leak Secrets

Never record:

- PEM certificate private keys or Secret contents.
- Bearer/refresh tokens.
- Client secrets, API keys, or HMAC signatures.
- `Authorization`/`Cookie` headers.
- Raw request/response bodies containing personal data.

Safe labels include **logical service ID**, **public generation ID**, error category, and status codes. Avoid unbounded high-cardinality labels like per-user IDs, unchecked token hashes, or instance IDs. You may record certificate expiration and a security-reviewed public fingerprint for debugging.

### 20.2. Classifying Errors at the Right Layer

~~~text
TLS: javax.net.ssl.SSLHandshakeException
    -> trust, certificate validity, SAN/SNI, mTLS client identity

HTTP: 401 Unauthorized
    -> missing/expired/wrong-audience/wrong-issuer token, invalid key

HTTP: 403 Forbidden
    -> scope/role/policy or unauthorized identity

HTTP: 503 Service Unavailable
    -> backend/gateway unavailable or LB has no instances

Transport: connect timeout/refused
    -> connection/network, not necessarily credential-related
~~~

In some stacks, TLS exceptions are wrapped inside `ResourceAccessException`, `WebClientRequestException`, or Feign exceptions. Inspect root causes, origins, and traces. **Never ramp up retries endlessly for 401/403/TLS handshake failures** caused by certificate mismatches or bad policies; that only adds load and hides the root cause.

## 21. Runbook When Rotation Breaks Production

Suppose rolling out `CA-new` to Inventory and Order starts causing intermittent failures:

1. **Isolate scope:** which service ID, zone, and instance ID fail? Are they TLS errors or HTTP 401/403s?
2. **Inspect PKI:** SANs, certificate chains, validity dates, EKUs, CA overlap, and clock skew.
3. **Inspect Secret propagation:** generation in Secret Manager, mounted volumes, and app-observed generation.
4. **Inspect runtime client:** `SSLContext` generation, pool generation, any lingering old sockets?
5. **Inspect LB:** are suppliers/discovery returning unrotated instances or stale metadata?
6. **Inspect auth:** access token audience/issuer/scopes, client registration secret, JWKS cache, and server verifiers.
7. **Pause rollout:** stop spreading failures across remaining pods before root cause is clear.
8. **Canary a fresh connection:** test A/B/zone with the new material without reusing old sockets.
9. **Controlled rollback** if old credentials are uncompromised and policy allows; if compromised, fast-replace instead of restoring dangerous credentials.
10. **Verify recovery:** error rates, successful TLS handshakes, 401/403 counts, renewed tokens, drained old pools.

### 21.1. Three Actions Never to Take During an Incident

- **Never disable hostname verification/trust validation** as a temporary "workaround".
- **Never enable infinite retries** on `SSLHandshakeException`, 401, or 403.
- **Never log full tokens, keys, or Secrets** to diagnose failures.

When troubleshooting, collect non-secret values: certificate subject/SAN/`notAfter`, verified peer identity, exception codes, credential generation, and trace/span IDs. Restrict access to PKI/credential telemetry per operational policy.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Replacing a PEM file and assuming the client rotated TLS | `SSLContext`/pool still holds the old generation | Verify consumer reload or swap client generation |
| Using server `reload-on-update` and assuming outbound WebClient auto-refreshes | Outbound connections stay on old material | Separate inbound server SSL from outbound connectors |
| Mounting Secrets via Kubernetes `subPath` | Files never receive automatic updates | Mount the whole Secret/projected volume directory |
| Reading secrets from env vars and expecting hot rotation | JVM retains initial environment variables | Use dynamic volume/secret providers or rolling restarts |
| Refreshing only `RestClient.Builder` | Already-built `RestClient` keeps old request factory | Refresh the right adapter or atomically swap the client |
| Swapping certificates without checking SAN/SNI | Per-instance TLS handshake/hostname verification failures | Align URI rewrites and certificate SANs |
| Changing client certificate without updating server trust | mTLS handshake fails | Perform trust overlap first |
| Switching CAs in one step without overlap | Half the cluster on old CA gets rejected | Expand → migrate → contract with canaries |
| Closing old pool immediately upon publish | In-flight requests are severed | Drain with deadline and lease/refcount tracking |
| Probing only a single instance | Assumes all replicas rotated | Canary every instance/zone with fresh TLS handshakes |
| Setting API key in `defaultHeader` at startup | Stuck on old API key forever | Interceptor/filter reads fresh snapshot per request |
| Placing an API key in global Feign configuration | Leaks credentials to other Feign clients | Use strictly scoped per-client configs |
| Treating access token expiry as client secret rotation | Manager keeps using old registration secret | Manage auth-client secret lifecycle separately |
| Replaying POST endlessly after 401 | Duplicate side effects / retry storms | Bound attempts, enforce idempotency, handle auth properly |
| Disabling verification to bypass TLS errors | Loses identity verification; MITM risk | Fix CA/SAN/truststore; never use trust-all |
| Exposing actuator refresh publicly | Unauthorized config/credential tampering | Authn/authz, network policies, and auditing |
| Logging certificate private keys/tokens | Credential leakage in logs | Log only safe generation/failure categories |
| Running dual trust too long after compromise | Extends exposure window for compromised keys | Follow incident-severity revocation procedures |
| Assuming 503 = certificate error | May be discovery/backend outage | Separate TLS, HTTP status, and no-instance failures |

## 23. Scenario Exercises

### 23.1. Scenario A: New Server Certificate from Same CA

Inventory replaces its old certificate with a new valid one signed by the same CA with the same DNS SANs. Order keeps its existing truststore and HTTP client.

**Question:** Must Order reload its truststore?

**Answer:** Not necessarily, because the trust anchor still trusts the new certificate chain as long as hostname, validity, EKU, and policy checks pass. However, verify that **fresh handshakes** to each instance succeed. Previously open connections do not prove the new certificate was validated.

### 23.2. Scenario B: Switching to a New CA

Order trusts only CA-old; Inventory-B switches to a certificate signed by CA-new.

**Question:** Does retrying onto A fully solve the incident?

**Answer:** No. Retries can temporarily mask the failure while A still uses CA-old, yet B keeps failing TLS. Order needs CA-old + CA-new trust overlap before servers switch certificates, verifying B with fresh connections before narrowing trust.

### 23.3. Scenario C: Short-Lived Tokens

Order uses `client_credentials` to get token T1, expiring after 5 minutes. A worker stores T1 in a `final` field of a singleton Feign interceptor.

**Question:** Why does Feign return 401 after 5 minutes?

**Answer:** The interceptor captured the stale token. Use an authorized client manager or token provider fetching a valid token at request time, caching by expiry and refreshing synchronously. Never replay T1 endlessly, nor call the Token Endpoint on every request.

### 23.4. Scenario D: Kubernetes Secret Updated, App Still Uses Old Material

Secret Manager holds generation N+1, the Kubernetes Secret updated, and the app mounts the file via **`subPath`**.

**Question:** Will a file watcher definitely see N+1?

**Answer:** No. Kubernetes documents that `subPath` mounts **do not auto-update** when Secrets change. Switch to directory mounts or rolling restarts; once the file truly updates on disk, still reload material and rotate the HTTP client generation.

### 23.5. Scenario E: Only WebClient Fails After Rotation

Outbound `RestClient` calls to the same downstream succeed, while `WebClient` throws `SSLHandshakeException`.

**Question:** Can we conclude Spring Cloud LoadBalancer is broken?

**Answer:** Not yet. Both clients may use **different HTTP engines, `SSLContext`s, truststores, and connection pools**. Check the SSL bundle consumer, underlying connector, selected instance, hostname verification, and active client generation—never compare only logical URIs.

### 23.6. Scenario F: mTLS Client Key Compromised

Order's mTLS key is found exposed. The server currently accepts both old and new client certs during overlap.

**Question:** Should we extend the overlap window for a gentle rollout?

**Answer:** No, if doing so conflicts with incident response requirements. Prioritize revoking/isolating the exposed key and issuing fresh material per the security runbook. Controlled brief disruption, rapid credential distribution, and narrowed client scopes are preferable to keeping a compromised key trusted.

## 24. Production Checklist Before Enabling Runtime Rotation

- [ ] Clearly identify what must rotate: **server cert, client mTLS cert, trust CA, access token, client secret, or API key**.
- [ ] Map logical service ID → selected `ServiceInstance` → physical host → TLS peer identity.
- [ ] Align certificate SANs/SNI/hostname verification with URI rewrites.
- [ ] Never use trust-all, disabled hostname verification, or private keys in source repos.
- [ ] Secrets carry generation/version, time-to-expiry, and audit trails.
- [ ] Kubernetes volumes receive updates; never rely on `subPath` or env vars for hot reload.
- [ ] Read certs/keys atomically from one snapshot, verifying key match, chain, and validity before publishing.
- [ ] Distinguish Spring Boot **server SSL bundle** reload from outbound client SSL contexts/pools.
- [ ] Identify the actual HTTP engine behind RestClient, RestTemplate, WebClient, and Feign.
- [ ] Have a tested **atomic swap + drain** mechanism or rolling restart strategy.
- [ ] Never use an HTTP client after its generation/pool has closed.
- [ ] Test in-flight requests, reactive cancellation, and long-lived streams during rotation.
- [ ] CA/trust rollovers use proper overlap; compromises follow a separate rapid-revocation runbook.
- [ ] `OAuth2AuthorizedClientManager`/providers use the right grant, expiry, and principal scope.
- [ ] Never confuse access token renewal with OAuth2 client secret/JWKS rotation.
- [ ] API key interceptors/filters read snapshots at request time, scoped to the right audience/downstream.
- [ ] Never place one service's credentials in a global Feign/WebClient config shared by other services.
- [ ] Bounded retries; never retry 401/403/TLS handshake errors endlessly.
- [ ] Canary handshakes and authorization tests across multiple instances/zones.
- [ ] Metrics cover credential generation, TLS errors, 401/403, token refresh failures, and pool draining.
- [ ] Actuator refresh/env endpoints are secured or disabled when unused.
- [ ] Rolling restart/readiness fallbacks exist where hot reload is unsupported.
- [ ] Rollback/incident runbooks exist, avoiding re-enabling compromised keys.
- [ ] Never log bearer tokens, private keys, API keys, or client secrets.
- [ ] Verify capabilities of Spring Boot/Spring Cloud/Spring Security/HTTP engines against your actual BOM.

## 25. Conclusion

**Renewing certificates and credentials while an application is running is never just swapping a file or hitting a refresh endpoint.** Spring Cloud LoadBalancer selects a **`ServiceInstance`**; HTTP transports and connection pools own **TLS sessions, `SSLContext`, and `KeyManager`/`TrustManager`**; OAuth2 clients/token providers own **access token and client secret lifecycles**. Each layer updates differently.

For safe rotation:

1. **Design trust/credential overlap** for routine rotations, paired with rapid-revocation playbooks for compromises.
2. **Distributing a secret is not enough:** validate and publish a new generation into the exact right client.
3. **TLS:** ensure fresh handshakes use the new certificates/trust; swap and drain HTTP pools if the transport lacks dynamic updates.
4. **OAuth2/API keys:** fetch valid credentials at request time rather than freezing them in singleton interceptors.
5. **Test for real:** simultaneously verify LoadBalancer-selected service IDs, physical TLS identities, HTTP authorization, and in-flight requests.
6. **Observe thoroughly:** track not just "rotation events" but also TLS handshakes, credential generations, 401/403s, fallbacks/retries, and pool draining.

In high-reliability systems, **controlled rolling restarts remain a valid choice** when outbound clients cannot guarantee hot reload. Never weaken TLS verification or prolong the life of a compromised key in pursuit of zero downtime.

## 26. References

- [Spring Boot – SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): PEM/JKS SSL bundles, `SslBundles`, `reload-on-update`, reload-supporting consumer limits, and file watchers.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClientSsl`/`WebClientSsl`, request factories, client builders, and applying SSL bundles.
- [Spring Boot – SSL Hot Reload](https://spring.io/blog/2023/11/07/ssl-hot-reload-in-spring-boot-3-2-0/): server-side SSL bundle reload mechanics when certificates update.
- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `@RefreshScope`, `ConfigurationProperties` rebinding, `/actuator/refresh`, security, and AOT/native limits.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `@LoadBalanced` RestClient, WebClient, and service IDs.
- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstanceListSupplier`, discovery, health, metadata, and retry-aware selection.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `FeignBlockingLoadBalancerClient`, named client configuration, and `RequestInterceptor`.
- [Spring Security – Authorized Client Features, Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `OAuth2ClientHttpRequestInterceptor` and `OAuth2AuthorizedClientManager` with RestClient.
- [Spring Security – Authorized Client Features, Reactive](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): `ServerOAuth2AuthorizedClientExchangeFilterFunction`, token acquisition, and refresh.
- [Spring Security – OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): refresh token grant and token response client configuration.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, RestTemplate, and SSL/transport abstractions.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient connectors and lifecycles.
- [Reactor Netty – HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): TLS, connection pooling, and HTTP client resources.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): mounted Secret update consistency, `subPath` limitation, env vars, and cluster propagation.
- [Kubernetes – Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/): projected secrets, pod certificates, symlink atomics, and reading credential material.
- [RFC 8446 – TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshakes, identities, and session resumption.
- [RFC 6749 – OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client credentials and refresh token grants.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authorization and token protection principles.
