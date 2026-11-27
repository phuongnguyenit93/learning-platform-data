# Reconstructing the URI After Replacing Service Name with Physical Address

In a microservices architecture, an application typically knows the **logical name** of the target service without needing to know the address of each running replica. Spring Cloud LoadBalancer lets code call **inventory-service** in the URI. After choosing a **ServiceInstance**, it must transform that URI into a physical address that the HTTP client can connect to. This step is called **URI reconstruction**.

For example, Order Service creates a request:

~~~text
GET http://inventory-service/api/v1/stock/BOOK-01?warehouse=HCM
~~~

LoadBalancer selects an instance with host **10.20.1.17**, port **8082**, using HTTP. The URI sent down to the connector becomes:

~~~text
GET http://10.20.1.17:8082/api/v1/stock/BOOK-01?warehouse=HCM
~~~

Finding the right instance alone is not enough. If scheme, port, path, or query are reconstructed incorrectly, requests can hit the wrong endpoint, fail TLS handshakes, or alter business data. This lesson examines Spring Cloud LoadBalancer's URI reconstruction rules and how they manifest in RestClient, WebClient, and OpenFeign.

## 1. Distinguishing Logical URI from Physical URI

A **logical URI** is the address used by business code. Its host segment is the service ID, e.g., **inventory-service**. It is not necessarily a DNS hostname resolvable outside the system.

~~~text
https://inventory-service:9000/api/items/BOOK-01?include=price#details
|-----| |---------------| |--| |----------------| |-----------| |-----|
scheme       host         port       path           query       fragment
~~~

A **physical URI** contains the selected instance's address. For example:

~~~text
https://inventory-02.internal:8443/api/items/BOOK-01?include=price#details
~~~

| Component | Data Source After Selecting Instance | Basic Rule |
| --- | --- | --- |
| Scheme | Original URI and instance attributes | May change according to getScheme() / isSecure() |
| Host | ServiceInstance.getHost() | Replaces service ID with actual hostname/IP |
| Port | ServiceInstance.getPort() | Replaces original URI port with instance port |
| Path | Original request URI | Preserves path; does not automatically prepend a context path from the instance |
| Query | Original request URI | Preserves query parameters built by the client |
| Fragment | Original request URI | May remain on the URI object, though not sent to the server over HTTP |

The logical name answers **which service to call**; ServiceInstance answers **which replica to call**. When an instance is replaced in the registry, business code keeps calling the same service ID while the physical URI can vary from request to request.

## 2. Where Does URI Reconstruction Sit in the Processing Chain?

~~~mermaid
flowchart TD
    A["Business code creates logical URI"] --> B["RestClient / WebClient / OpenFeign"]
    B --> C["Spring Cloud LoadBalancer integration"]
    C --> D["Extract service ID from host"]
    D --> E["ServiceInstanceListSupplier"]
    E --> F["Discovery, cache, health, and filters"]
    F --> G["LoadBalancer selects an instance"]
    G --> H{"Instance found?"}
    H -->|Yes| I["Get host, port, scheme, isSecure"]
    I --> J["Reconstruct URI"]
    J --> K["HTTP connector sends request"]
    H -->|No| L["Report no-instance error"]
~~~

This flow consists of specific steps:

1. **HTTP client** builds the request from the URI template and arguments.
2. **LoadBalancer integration** identifies the service ID in the host portion of the logical URI.
3. **LoadBalancer** fetches the ServiceInstance list from the supplier, then picks an instance via Round Robin or another routing policy.
4. **URI reconstruction** computes the target scheme, host, and port while preserving the rest of the original URI.
5. **HTTP connector** sends method, headers, and body to the reconstructed address.

Discovery and the instance-selection algorithm are not components that rewrite API paths. Spring Cloud LoadBalancer selects the **connection target**; separate path rewrites by a Gateway or other filters must be evaluated independently.

If no instance is found, the request can fail right at step 3. At that point, **no valid physical URI exists** to send to. Changing URI reconstruction logic will not fix a missing-instance failure.

## 3. Which ServiceInstance Attributes Participate in Reconstruction?

Spring Cloud Commons defines the **org.springframework.cloud.client.ServiceInstance** interface. Key attributes include:

| API | Example | Role |
| --- | --- | --- |
| getServiceId() | inventory-service | Logical identifier for querying the instance list |
| getHost() | 10.20.1.17 | Physical host for the connection |
| getPort() | 8082 | Physical port for the connection |
| isSecure() | false | Signal supporting target scheme calculation |
| getScheme() | null, http, https | Explicit scheme provided by the instance if present |
| getUri() | http://10.20.1.17:8082 | Representative URI of the instance; does not replace the business request URI |

Example of constructing an instance for verification:

~~~java
ServiceInstance instance = new DefaultServiceInstance(
        "inventory-2",       // instance ID
        "inventory-service", // service ID
        "10.20.1.17",        // host
        8082,                // port
        false                // isSecure
);
~~~

In production, ServiceInstance objects usually come from Eureka, Consul, or another service discovery source. Register **host, port, and scheme consistently with the instance's network/TLS setup**, because LoadBalancer relies on this metadata to construct the physical target.

**Distinguishing getUri() from the reconstructed URI:** **LoadBalancerUriTools.reconstructURI(...)** uses getHost(), getPort(), and getScheme()/isSecure() alongside the original URI. It does not extract an arbitrary path from getUri() and splice it into the request. If the backend is deployed under a /inventory prefix, the client or a dedicated routing layer must include that prefix in the path before sending the request.

## 4. How Does LoadBalancerUriTools.reconstructURI Work?

Spring Cloud Commons provides the utility:

~~~java
URI physicalUri = LoadBalancerUriTools.reconstructURI(
        selectedInstance,
        originalUri
);
~~~

In the current implementation, the actual logic can be broken down into six steps:

1. Verify **selectedInstance** is non-null; throws IllegalArgumentException if null.
2. Read target host from **getHost()**.
3. Determine scheme: prefer **getScheme()** if present; if null, use the original or default scheme while considering **isSecure()**.
4. Determine port: use **getPort()** when non-negative; if negative, fall back to the default port for the scheme.
5. If host, port, and scheme all match the original URI, return the original URI unchanged.
6. Otherwise, build a new URI from the original URI using **UriComponentsBuilder**, replacing only scheme, host, and port.

Pseudocode to clarify the order:

~~~java
// Pseudocode: deriveScheme, defaultPort, rebuildFromOriginal
// illustrate the concept only and are not public Spring Cloud APIs.
String host = selectedInstance.getHost();

String scheme = selectedInstance.getScheme() != null
        ? selectedInstance.getScheme()
        : deriveScheme(originalUri.getScheme(), selectedInstance.isSecure());

int port = selectedInstance.getPort() >= 0
        ? selectedInstance.getPort()
        : defaultPort(scheme);

URI result = rebuildFromOriginal(originalUri, scheme, host, port);
~~~

In practice, applications using `@LoadBalanced` HTTP clients rarely call this utility manually. Spring Cloud performs the URI transformation inside an interceptor or exchange filter. The utility is helpful when testing the transformation in isolation or building a custom integration adapter.

### 4.1. Before-and-After URI Examples Table

Assume the instance does not declare a custom scheme (**getScheme() == null**):

| Original URI | Selected Instance | Reconstructed URI |
| --- | --- | --- |
| http://inventory-service/api/items/42 | 10.0.0.12:8081, secure=false | http://10.0.0.12:8081/api/items/42 |
| http://inventory-service:9000/api/items/42?lang=vi | inventory-02.internal:18080, secure=false | http://inventory-02.internal:18080/api/items/42?lang=vi |
| http://inventory-service/api/items/42 | inventory-03.internal:8443, secure=true | https://inventory-03.internal:8443/api/items/42 |
| https://inventory-service/api/items/42 | inventory-04.internal:8080, secure=false | https://inventory-04.internal:8080/api/items/42 |
| http://inventory-service/api/items/42 | 10.0.0.15, port=-1, secure=false | http://10.0.0.15:80/api/items/42 |

Notes from two important examples:

- **Original port does not dictate target port:** The original URI has port 9000, but the instance uses port 18080, so the physical URI uses 18080.
- **isSecure=false does not automatically downgrade https to http:** In the referenced implementation, if the original URI is HTTPS and the instance does not declare an explicit scheme, HTTPS is preserved. If the backend actually listens only on HTTP, the connection can fail at the TLS layer.

## 5. How Are Scheme and Port Derived?

### 5.1. getScheme() Takes Precedence

If the instance has **getScheme() != null**, that scheme is used directly. A custom implementation can declare a specific scheme, such as https.

If instance metadata specifies **getScheme() = "http"** while **isSecure() = true**, the explicit scheme still takes precedence. Contradictory attributes can send connections over the wrong protocol. Normalize them at the discovery source.

### 5.2. When getScheme() Is Null

With DefaultServiceInstance, getScheme() is typically null. According to the current LoadBalancerUriTools implementation:

- If the original URI has no scheme, it defaults to **http**.
- If **isSecure=true**, scheme **http** is upgraded to **https**.
- If **isSecure=true**, scheme **ws** is upgraded to **wss**.
- Other schemes not in the upgrade mapping are preserved as-is.
- When **isSecure=false**, the original scheme is preserved.

Treat the secure flag as **routing metadata**. It does not automatically configure TLS certificates, truststores, or connections to an HTTPS port. Both client and target service must still be deployed with matching TLS configurations.

### 5.3. When an Instance Does Not Publish a Port

In the current implementation:

- **getPort() >= 0:** uses the port published by the instance.
- **getPort() < 0** and scheme is **https:** uses port 443.
- **getPort() < 0** with other schemes: uses port 80.

This is a helper fallback rule, not a guarantee that the server is listening on that port. Registries should publish explicit ports in environments using custom ports.

### 5.4. Why Not Use lb:// Arbitrarily?

With RestClient and WebClient integrated via @LoadBalanced, standard examples use URLs like:

~~~text
http://inventory-service/api/items/42
~~~

The **lb://inventory-service** scheme typically appears in **Spring Cloud Gateway** route definitions. Gateway has a dedicated filter to interpret lb and resolve backend URIs. If you pass an lb:// URI directly into LoadBalancerUriTools yourself, the helper does not act as a generic converter turning custom schemes into HTTP; the output may retain the lb scheme if the instance provides no explicit scheme.

Distinguish these contexts:

| Context | Typical Declaration | Handled By |
| --- | --- | --- |
| RestClient / WebClient with @LoadBalanced | http://inventory-service/api/items | HTTP client LoadBalancer integration |
| OpenFeign with service ID | @FeignClient(name = "inventory-service") | Feign load-balancing adapter |
| Spring Cloud Gateway route | lb://inventory-service | Gateway LoadBalancer filter |

## 6. What Happens to Path and Query?

### 6.1. Preserving the Resource Path

Logical URI:

~~~text
http://inventory-service/api/v2/items/BOOK-01?warehouse=HCM&details=true
~~~

If instance **10.20.1.18:8083** is selected, the physical URI becomes:

~~~text
http://10.20.1.18:8083/api/v2/items/BOOK-01?warehouse=HCM&details=true
~~~

The **/api/v2/items/BOOK-01** path and **warehouse=HCM&details=true** query are not stripped or renamed just because another instance was chosen. LoadBalancer does not rewrite /api/v2 into /v1, strip prefixes, or alter query parameters.

If a backend requires a different prefix, that must be reflected in the logical URI or handled by a dedicated filter/router responsible for path modification.

### 6.2. Percent-Encoding and the % Character

A path segment may contain special characters. For example, an SKU might be **BOOK/2026** where `/` is part of the SKU value rather than a path segment separator. The URI may need to be represented as:

~~~text
http://inventory-service/api/items/BOOK%2F2026?city=Ho%20Chi%20Minh
~~~

After proper reconstruction:

~~~text
http://10.20.1.18:8083/api/items/BOOK%2F2026?city=Ho%20Chi%20Minh
~~~

LoadBalancerUriTools uses UriComponentsBuilder and checks raw path, raw query, and raw fragment for `%` characters to detect already percent-encoded URIs. If a URI is only partially encoded or input is malformed, a second encoding pass can re-encode percent signs, turning **%2F** into **%252F**.

This causes bugs that appear only with IDs containing `/`, spaces, `%`, or complex queries. Best practices:

1. Use Spring's URI builder/URI templates instead of manually concatenating user input strings.
2. Encode according to context: **path segment** vs. **query parameter**.
3. Pick one consistent encoding strategy across the entire client.
4. Do not pre-encode half of an argument and let another layer re-encode the entire URI.
5. Inspect raw path and raw query when diagnosing double-encoding.

URI reconstruction aims to preserve path/query semantics; it cannot repair an input URI that was already improperly encoded upstream.

### 6.3. Fragment

A URI object can contain a fragment, for example:

~~~text
http://inventory-service/api/items/42#description
~~~

UriComponentsBuilder can preserve the fragment in the reconstructed URI. However, fragments are not sent in the HTTP request-target, and servers cannot use them as routing parameters. Data needed by the backend must reside in the path, query, headers, or body per the API contract.

### 6.4. User Info

A URI of the form **http://user:password@inventory-service/...** contains user info. Since the utility starts from the original URI, that component can be carried over. Never put passwords, access tokens, or credentials in URIs: they easily leak into logs, metrics, and stack traces. Use proper authentication headers/mechanisms instead.

## 7. Java Practice: Reconstructing a URI Without Running a Registry

The following example calls LoadBalancerUriTools directly solely to observe the transformation:

~~~java
import java.net.URI;

import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerUriTools;

public class UriReconstructionExample {

    public static void main(String[] args) {
        URI original = URI.create(
                "http://inventory-service/api/items/BOOK%2F2026?warehouse=HCM");

        ServiceInstance instance = new DefaultServiceInstance(
                "inventory-2",
                "inventory-service",
                "10.20.1.17",
                8082,
                false);

        URI actual = LoadBalancerUriTools.reconstructURI(instance, original);

        System.out.println("Logical:  " + original);
        System.out.println("Physical: " + actual);
    }
}
~~~

Expected output:

~~~text
Logical:  http://inventory-service/api/items/BOOK%2F2026?warehouse=HCM
Physical: http://10.20.1.17:8082/api/items/BOOK%2F2026?warehouse=HCM
~~~

This snippet **does not look up or select an instance, send a request, or check health**. The instance is supplied upfront to verify the reconstruction transform in isolation.

If you change the instance to secure=true and port 8443, you can observe the scheme upgrade from http to https.

## 8. How Does RestClient Use the Physical URI?

With a Spring Cloud version supporting RestClient, create a builder with @LoadBalanced:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Usage in a business client:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    InventoryResponse getStock(String sku, String warehouse) {
        return restClient.get()
                .uri(
                        "http://inventory-service/api/stock/{sku}?warehouse={wh}",
                        sku,
                        warehouse)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

On the blocking path:

1. RestClient builds the logical URI from the template.
2. The interceptor extracts the service ID from the URI host.
3. BlockingLoadBalancerClient selects the corresponding ServiceInstance.
4. **LoadBalancerClient.reconstructURI()** builds the target URI, with **BlockingLoadBalancerClient** delegating to LoadBalancerUriTools.
5. The HTTP client executes the request against the physical URI.

For example, a request to the service ID:

~~~text
GET http://inventory-service/api/stock/BOOK-01?warehouse=HCM
~~~

may actually reach:

~~~text
GET http://10.20.1.17:8082/api/stock/BOOK-01?warehouse=HCM
~~~

If you create a plain RestClient via RestClient.create() without LoadBalancer integration, using host inventory-service does not automatically trigger instance selection. Depending on the environment, the request may fail with a DNS error if the logical hostname does not exist in name resolution.

## 9. WebClient Reconstructs URIs in the Reactive Pipeline

Spring Cloud provides ReactorLoadBalancerExchangeFilterFunction to integrate instance selection for reactive WebClient:

~~~java
@Configuration(proxyBeanMethods = false)
class ReactiveHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Business client:

~~~java
@Service
class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> getStock(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

The filter extracts the service ID from the request URI, asks ReactiveLoadBalancer to pick an instance, reconstructs the URI, and forwards the resulting ClientRequest to the physical address. If both discovery and the HTTP stack are reactive, instance selection runs without blocking the event loop.

Do not call **block()** inside a WebFlux handler to wait on LoadBalancer or the response. URI reconstruction is a lightweight transformation; network waits must still be governed by timeouts, bounded retries, and other resilience mechanisms.

## 10. OpenFeign Preserves URI Templates and Swaps Physical Endpoints

OpenFeign lets you declare HTTP clients as interfaces:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    InventoryResponse getStock(
            @PathVariable("sku") String sku,
            @RequestParam("warehouse") String warehouse);
}
~~~

Feign turns annotations and parameters into a request. When Spring Cloud LoadBalancer is present and no fixed URL is configured, **FeignBlockingLoadBalancerClient** selects an instance and reconstructs the URL before sending.

**Important:** if `@FeignClient` declares a fixed **url** or an equivalent static URL property is set, Feign may call that endpoint directly and bypass LoadBalancer. To use logical names, declare name and verify the spring-cloud-starter-loadbalancer dependency is present.

RestClient, WebClient, and OpenFeign have different adapters, yet share the same goal: translating the service ID into a real connection target while preserving the business endpoint built by the client.

## 11. Other Layers That Can Modify the URI

LoadBalancerUriTools handles scheme/host/port based on ServiceInstance; other components in the stack may modify path/query:

- **URI template expansion:** substitutes `{sku}` with values and encodes according to rules.
- **HTTP client interceptor/filter:** may append query parameters, headers, or rewrite the URL.
- **API Gateway:** strips prefixes, rewrites paths, selects routes and backends.
- **Reverse proxy/ingress:** may alter paths or route by headers.
- **Service mesh:** may add an external routing or proxy layer outside the process.

Example:

~~~text
Logical URI:       http://inventory-service/v1/items/42
Gateway rewrite:   /items/42
Selected instance: inventory-02.internal:8080
Backend URI:       http://inventory-02.internal:8080/items/42
~~~

The path changed due to the rewrite filter, while LoadBalancer provided the target instance. When using Spring Cloud Gateway with lb://, pay attention to ordering between the LoadBalancer filter and path-modifying filters such as StripPrefix or SetPath.

## 12. Implications for TLS, Headers, and Retries

### 12.1. Wrong Scheme Can Break TLS

If the registry registers secure=true while the service only serves HTTP, the reconstructed URI may use https and fail to connect. Conversely, an original URI using https can retain that scheme even for an instance with secure=false if no explicit getScheme exists.

With TLS, physical hostnames also interact with **certificate hostname verification** and **SNI**. If a certificate only matches the logical service ID while the HTTP client actually connects via a different hostname, review your certificate strategy and TLS termination at proxies. Never disable certificate verification to mask a configuration mismatch.

### 12.2. Host Header and HTTP Authority

The physical URI and HTTP Host/:authority are related, though adapters/proxies may override headers. HTTP clients usually derive authority from the target URI; however, do not assume every request always keeps the logical service ID or always sends the physical host. If a backend relies on virtual hosting, inspect the actual request on the receiving side.

### 12.3. Retries Can Produce Different Physical URIs

The initial request may go to **10.20.1.17:8082**, while a retry is routed by LoadBalancer to **10.20.1.18:8083**. Each attempt then has a different physical URI, even though the service ID, path, and business payload are identical.

For POST/PUT/PATCH requests with side effects, apply safe retry contracts. A timeout does not prove the server failed to complete the business action. For non-idempotent operations, use idempotency keys or equivalent deduplication mechanisms.

### 12.4. Stale Instances Can Still Be Selected

URI reconstruction can be syntactically flawless while pointing to a dead instance because the registry or cache has not refreshed yet. Check discovery, health checks, and cache TTL. LoadBalancerUriTools itself does not open connections to verify health.

## 13. Layer-by-Layer Error Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| UnknownHostException with service ID | HTTP client lacks LoadBalancer integration | Check `@LoadBalanced` builder and adapter/dependencies |
| No instance found | Discovery or supplier returned an empty list | Check service ID, registry, cache, health filters |
| Connected to wrong port | Wrong port in registry | Check getPort() of the selected instance |
| SSLHandshakeException | Inconsistent scheme/certificate/TLS | Check getScheme(), isSecure(), SNI, truststore |
| Backend 404 despite right instance selected | Wrong path or path rewritten by filter/proxy | Compare logical URI, post-filter URI, and backend route |
| Query shows %252F or %2520 | Double encoding or partially encoded input | Check raw path/query and URI builder |
| Retry hits another instance then fails | Stale cache or inconsistent local state across instances | Check health, discovery, sessions, idempotency |
| Backend sees unexpected Host header | Adapter/proxy/filter altered authority | Log received headers on server and inspect adapter |

The investigation order should be **logical URI → service ID → instance list → selected instance → reconstructed URI → network request → response**. This clarifies whether the bug occurred before or after reconstruction.

## 14. Practice: Verifying URI Reconstruction

### 14.1. Testing with Two Local Replicas

Suppose two inventory-service instances both expose GET /api/stock/{sku}:

| Instance | Address | Returned Response |
| --- | --- | --- |
| Inventory A | http://localhost:8081 | instanceId=inventory-a |
| Inventory B | http://localhost:8082 | instanceId=inventory-b |

SimpleDiscoveryClient configuration:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Step-by-step practice:

1. Create a `@LoadBalanced` RestClient.Builder in the caller application that includes spring-cloud-starter-loadbalancer.
2. Call the logical URI **http://inventory-service/api/stock/BOOK-01?warehouse=HCM** multiple times.
3. Verify the response's instanceId alternates according to the selection policy, typically Round Robin by default.
4. Verify the backend receives path **/api/stock/BOOK-01** and query **warehouse=HCM** on both instances.
5. Test a URI with special characters in a path segment; confirm no double-encoding occurs.
6. Test an actually configured HTTPS endpoint and confirm the physical URI scheme matches.
7. Stop one instance and observe the update delay across discovery/cache/health. Requests failing during the stale cache window are not necessarily URI reconstruction bugs.

**SimpleDiscoveryClient** is convenient for local testing with static lists; it does not auto-detect starting or stopping processes and does not replace a dynamic registry.

### 14.2. Standalone Test for Port and Query

No running server is needed to verify pure reconstruction:

~~~java
URI original = URI.create(
        "http://inventory-service:9000/api/items/42?lang=vi");

ServiceInstance instance = new DefaultServiceInstance(
        "inventory-b", "inventory-service", "localhost", 8082, false);

URI result = LoadBalancerUriTools.reconstructURI(instance, original);

URI expected = URI.create(
        "http://localhost:8082/api/items/42?lang=vi");

if (!expected.equals(result)) {
    throw new IllegalStateException("Unexpected URI: " + result);
}
~~~

The result confirms port 9000 in the logical URI was replaced by instance port 8082 while path and query remained intact. You can extend this check with secure=true instances, https original URIs, encoded path values, or port -1.

## 15. Checklist

- [ ] Logical URI has the correct service ID in the host portion.
- [ ] HTTP client is integrated with `@LoadBalanced` or the corresponding Feign adapter.
- [ ] Instance host, port, getScheme(), and isSecure() are consistent.
- [ ] Original URI port is replaced by the instance port.
- [ ] Path, query, and business data remain intact after instance selection.
- [ ] Parameters with special characters are encoded appropriately and only once.
- [ ] Do not assume instance getUri() automatically injects a context path into requests.
- [ ] Distinguish client `http://service-id` URLs from Gateway `lb://` routes.
- [ ] Verify TLS, SNI, certificates, and hostname verification when schemes change.
- [ ] Bound retries and ensure idempotency for operations with side effects.
- [ ] Log only URIs stripped of tokens, credentials, and sensitive data.

## 16. Conclusion

**URI reconstruction bridges ServiceInstance selection and the actual HTTP connection.** Spring Cloud LoadBalancer relies on instance metadata to substitute scheme, host, and port while preserving the logical URI's path and query. When failures happen, distinguish missing-instance errors, URI transformation errors, and backend communication errors.

Understanding secure flags, default ports, percent-encoding, and rewrite filters helps applications coordinate RestClient, WebClient, and OpenFeign reliably across multi-replica deployments.

## 17. References

- [Spring Cloud LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): HTTP client integrations and ServiceInstance selection.
- [Spring Cloud Commons - Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): service discovery and client-side load balancing.
- [LoadBalancerUriTools.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerUriTools.java): implementation resolving scheme, host, port, and encoded URIs.
- [BlockingLoadBalancerClient.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/blocking/client/BlockingLoadBalancerClient.java): blocking integration path and reconstructURI.
- [ServiceInstance.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java): instance data contract.
- [Spring Cloud Gateway LoadBalancer Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html): lb:// syntax and route filter ordering.
