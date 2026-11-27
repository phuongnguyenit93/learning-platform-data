# Distinguishing Between Calling by Service Name and Calling Direct URLs with RestTemplate

In a Spring Boot application using `RestTemplate`, two calls that look alike can go through **two different routing mechanisms**:

- **Calling by service name:** the client uses a service ID such as `catalog-service` and a `RestTemplate` integrated with **Spring Cloud LoadBalancer**. LoadBalancer retrieves the list of `ServiceInstance` entries, selects one replica, and forwards the request to that concrete address.
- **Calling a direct URL:** the client uses an actual target address, such as `http://10.0.1.21:8081`, through a plain `RestTemplate`. The address in the URL is handled by the HTTP client and DNS/network infrastructure without Spring Cloud LoadBalancer selecting a `ServiceInstance`.

The deciding factor **does not lie solely in the URL string**. The exact same URL `http://catalog-service/products` can be interpreted differently depending on **which `RestTemplate` bean is used**: a `@LoadBalanced` bean treats `catalog-service` as a service ID; a plain bean treats it as a hostname to resolve via existing networking mechanisms.

This lesson belongs to the **RestTemplate** chapter, focusing on recognizing call flows, declaring beans properly, verifying behavior, and avoiding confusion between client-side load balancing and calling a fixed endpoint.

## 1. Two URLs and Two Ways of Determining the Target

Suppose `order-service` needs to call `catalog-service`. The system runs two instances:

| Property | Instance 1 | Instance 2 |
|---|---|---|
| Service ID | `catalog-service` | `catalog-service` |
| Instance ID | `catalog-1` | `catalog-2` |
| URI | `http://10.0.1.21:8081` | `http://10.0.1.22:8081` |

Call by service ID:

~~~java
Product product = loadBalancedRestTemplate.getForObject(
        "http://catalog-service/products/{id}",
        Product.class,
        42L
);
~~~

The calling code does not specify which instance will receive the request. LoadBalancer uses the service ID `catalog-service`, retrieves the candidate list, and chooses one instance. For example, the request may go to `http://10.0.1.22:8081/products/42`.

Call by physical address:

~~~java
Product product = directRestTemplate.getForObject(
        "http://10.0.1.21:8081/products/{id}",
        Product.class,
        42L
);
~~~

The client explicitly specified the target `10.0.1.21:8081`. In this call, Spring Cloud LoadBalancer does not choose between `catalog-1` and `catalog-2` because `directRestTemplate` is a plain bean.

~~~mermaid
flowchart TD
    A["Order Service Application"]
    B["@LoadBalanced RestTemplate"]
    C["Plain RestTemplate"]
    D["http://catalog-service/products/42"]
    E["Spring Cloud LoadBalancer"]
    F["ServiceInstanceListSupplier"]
    G["catalog-1 or catalog-2"]
    H["http://10.0.1.21:8081/products/42"]
    I["HTTP transport, DNS/TCP/TLS"]
    J["Selected instance"]
    A --> B --> D --> E
    E --> F --> E
    E --> G --> I
    A --> C --> H --> I
    I --> J
~~~

The diagram illustrates the difference at the **endpoint resolution step**. Both approaches ultimately use the HTTP transport to send the request; only calling by service ID adds a client-side `ServiceInstance` selection step.

## 2. The Actual Role of @LoadBalanced

Spring Cloud Commons lets you declare a `RestTemplate` as a load-balanced client by putting the `@LoadBalanced` annotation on the bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

With proper configuration and the `spring-cloud-starter-loadbalancer` dependency, Spring Cloud attaches a LoadBalancer interceptor to this bean. The interceptor extracts the logical URL's hostname as the **service ID** and works with `BlockingLoadBalancerClient` to select a physical address.

When calling:

~~~text
http://catalog-service/products/42
~~~

the hostname `catalog-service` is a logical name. The HTTP transport does not need to resolve that hostname via DNS to a single server; the LoadBalancer adapter picks an instance and constructs the real target before the request is transmitted.

For this mechanism to work, both **a load-balanced configured bean** and a corresponding **instance provider** are required. That source can come from Eureka, Consul, another discovery integration, or a static list using `SimpleDiscoveryClient`.

### What Happens with a RestTemplate Without @LoadBalanced?

~~~java
@Bean
RestTemplate directRestTemplate() {
    return new RestTemplate();
}
~~~

`directRestTemplate` does not automatically integrate with Spring Cloud LoadBalancer simply because the project includes the LoadBalancer dependency. If you call `http://catalog-service/products/42` via this bean, the hostname `catalog-service` is processed as a regular network name. The request only succeeds if DNS, a hosts file, a service mesh, or other infrastructure makes that hostname reachable.

If Kubernetes provides DNS for `catalog-service`, the direct bean can still succeed, but target selection is performed by DNS/Kubernetes Service or the associated proxy—**not by Spring Cloud LoadBalancer's `ServiceInstance` selection inside this bean**.

## 3. Configuring Two RestTemplates Side by Side in One Application

In practice, an application may need both call styles: calling microservices by service ID and calling fixed URLs for an external system or an administrative endpoint.

You can explicitly declare two beans:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean("serviceRestTemplate")
    @LoadBalanced
    RestTemplate serviceRestTemplate() {
        return new RestTemplate();
    }

    @Bean("directRestTemplate")
    @Primary
    RestTemplate directRestTemplate() {
        return new RestTemplate();
    }
}
~~~

`@Primary` causes the plain bean to be preferred whenever an injection point asks for `RestTemplate` without a qualifier. For components where the intended behavior must be guaranteed, **inject using `@Qualifier`**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
class ProductGateway {

    private final RestTemplate serviceRestTemplate;
    private final RestTemplate directRestTemplate;

    ProductGateway(
            @Qualifier("serviceRestTemplate") RestTemplate serviceRestTemplate,
            @Qualifier("directRestTemplate") RestTemplate directRestTemplate
    ) {
        this.serviceRestTemplate = serviceRestTemplate;
        this.directRestTemplate = directRestTemplate;
    }

    Product getViaServiceId(long id) {
        return serviceRestTemplate.getForObject(
                "http://catalog-service/products/{id}",
                Product.class,
                id
        );
    }

    Product getFromSpecificInstance(long id) {
        return directRestTemplate.getForObject(
                "http://10.0.1.21:8081/products/{id}",
                Product.class,
                id
        );
    }
}

record Product(long id, String name) {}
~~~

These two methods demonstrate two distinct intents:

- `getViaServiceId()` is appropriate when you want the client to balance across available replicas.
- `getFromSpecificInstance()` is suited when intentionally targeting a specific endpoint, such as probing an instance under diagnosis.

The example assumes the endpoint returns JSON compatible with the `Product` record and that the application uses a Java version supporting records. `RestTemplate` can also be constructed with `RestTemplateBuilder` to leverage Spring Boot configuration; the key remains distinguishing a LoadBalancer-integrated builder/client from a plain builder/client.

### Why Not Use One Bean for Both URL Types?

A bean annotated with `@LoadBalanced` has an interceptor that treats the hostname as a service ID. Consequently, if you pass `http://10.0.1.21:8081/products` or `http://localhost:8081/products` to this bean, do not assume it will skip LoadBalancer: the interceptor may try resolving `10.0.1.21` or `localhost` as a service ID and fail to find any instance.

Use a **plain RestTemplate for physical URLs**. If a special requirement demands combining both modes behind one client, design an explicit routing selection mechanism instead of assuming the interceptor knows which URL is "direct."

## 4. Mechanism from Service ID to HTTP Request

With a `@LoadBalanced` bean, the typical call flow proceeds as follows:

1. Business code passes the URL `http://catalog-service/products/42`.
2. `RestTemplate` builds the request and passes it through configured interceptors.
3. The LoadBalancer interceptor extracts the service ID from the logical hostname.
4. `BlockingLoadBalancerClient` asks LoadBalancer to select a `ServiceInstance`; the `ServiceInstanceListSupplier` chain provides eligible candidates from discovery/cache/filters.
5. The integration component constructs the target URI from the chosen instance's host, port, and secure flag, preserving path, query, and required request parts.
6. `RestTemplate`'s HTTP request factory and transport open the connection, send the payload, and receive the response.

~~~mermaid
sequenceDiagram
    participant App as ProductGateway
    participant RT as @LoadBalanced RestTemplate
    participant LB as BlockingLoadBalancerClient
    participant Supplier as ServiceInstanceListSupplier
    participant HTTP as HTTP transport
    participant Catalog as Catalog instance
    App->>RT: GET http://catalog-service/products/42
    RT->>LB: Select instance for catalog-service
    LB->>Supplier: Fetch candidate list
    Supplier-->>LB: catalog-1, catalog-2
    LB-->>RT: catalog-2: 10.0.1.22:8081
    RT->>HTTP: GET http://10.0.1.22:8081/products/42
    HTTP->>Catalog: Send HTTP request
    Catalog-->>HTTP: HTTP response
    HTTP-->>App: Data or exception
~~~

The core takeaway is that **instance selection and HTTP execution are two distinct stages**. LoadBalancer selects from the candidate list; it does not replace TCP, TLS, sockets, or response body reading inside `RestTemplate`.

## 5. How URLs Are Resolved When Calling Directly

In a plain `RestTemplate`, the scheme, host, and port segments of the URL determine where the request is sent:

~~~text
https://api.partner.example:8443/v1/items/42
│       │                    │    └─ Path
│       │                    └────── Port
│       └─────────────────────────── Hostname
└─────────────────────────────────── Scheme
~~~

For a hostname, the transport or operating system may use DNS/hosts to resolve the address; for an IP literal, no DNS step is needed for that host itself. Proxies, service meshes, and network load balancers can still route further at the infrastructure layer.

This leads to an important distinction:

| Scenario | Uses Spring Cloud `ServiceInstance` selection? | What determines the target? |
|---|---|---|
| `@LoadBalanced RestTemplate` calling `http://catalog-service` | Yes | LoadBalancer and supplier by service ID |
| Plain `RestTemplate` calling `http://10.0.1.21:8081` | No | IP/port address in the URL |
| Plain `RestTemplate` calling `https://api.partner.example` | No | DNS, proxy, or network infrastructure |
| Plain `RestTemplate` calling Kubernetes Service DNS | Not in this client | Kubernetes Service/DNS/network |
| `@LoadBalanced RestTemplate` calling a physical host not registered as a service ID | Can still pass through LoadBalancer | Risks failing a service ID lookup |

Not every direct call lacks load balancing. A direct URL can point to a reverse proxy, API gateway, or network load balancer. The difference is that **Spring Cloud LoadBalancer in `RestTemplate` does not select the instance during that call**.

## 6. Example Running Two Replicas Without a Separate Registry

To learn how service-name calls work, you can use `SimpleDiscoveryClient` to declare a static list of `ServiceInstance` entries:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
~~~

Suppose two `catalog-service` processes run on the same machine as the calling application, listening on ports `8081` and `8082` respectively. Both expose a `GET /whoami` endpoint returning the instance ID.

Calling by service name:

~~~java
String selectedInstance = serviceRestTemplate.getForObject(
        "http://catalog-service/whoami",
        String.class
);
~~~

When LoadBalancer uses round-robin and both instances are in the candidate list, consecutive calls may alternate between the two IDs. The exact order depends on algorithm state, the instance list, and concurrency; do not assert that the very first call always goes to `8081`.

Calling a specific target:

~~~java
String fixedInstance = directRestTemplate.getForObject(
        "http://127.0.0.1:8081/whoami",
        String.class
);
~~~

This call always attempts to connect to `127.0.0.1:8081`. If the instance on that port stops serving, `directRestTemplate` will not fail over to `8082` via Spring Cloud LoadBalancer.

**Environment note:** `127.0.0.1` points to the client's own machine or network namespace. In Docker or Kubernetes, use hostnames/addresses reachable from the caller's runtime environment; `localhost` inside a container does not point to another container.

### Differences When One Instance Stops

| Condition | Calling by service ID | Calling a fixed URL |
|---|---|---|
| Both instances healthy | Can distribute across replicas | Always calls the specified endpoint |
| `8081` stopped and removed from supplier | Can select `8082` | Calling `8081` still fails |
| `8081` stopped but still in cache | May still pick `8081` and fail | Calling `8081` fails |
| Discovery returns empty list | No `ServiceInstance` to select | Still attempts to connect to the specified URL |
| LoadBalancer zone/hint config changes | Can alter the candidate list | Unaffected by this policy |

In static `SimpleDiscoveryClient` configuration, stopping a server **does not automatically remove its URI from YAML**. To observe list updates driven by instance lifecycle, use a dynamic service registry or a custom supplier for testing.

## 7. Common Errors and Their Meaning

The two types of `RestTemplate` can fail for different reasons even when calling the same API path.

| Symptom | Calling service ID with load-balanced bean | Calling URL with plain bean |
|---|---|---|
| No instance found | Wrong service ID, empty discovery, supplier filtered all candidates | No instance lookup step occurs |
| `UnknownHostException` | Selected instance's real hostname may be unresolvable; inspect target | Host in URL cannot be resolved via DNS/hosts |
| `Connection refused` | Selected instance is not listening on host:port | Specified target is not listening |
| Connect/read timeout | HTTP transport slow or backend failed to respond in time | HTTP transport slow or backend failed to respond in time |
| HTTP 404/500 | Response received from backend or intermediary; trace selected target | Response received from backend or intermediary |
| Stopped instance still called | Discovery/cache/health check may be stale | URL remains pinned to stopped instance |

When using `RestTemplate` with `DefaultResponseErrorHandler`, 4xx/5xx HTTP statuses are usually converted into exceptions such as `HttpClientErrorException` or `HttpServerErrorException`. Transport errors are typically wrapped in `ResourceAccessException`, while missing-instance failures may surface from the LoadBalancer layer as an exception or synthetic response depending on version/configuration.

Do not conclude "no servers available" solely from an HTTP 503: a proxy or the backend itself can also return 503. Check the service ID, selected instance, exception type, and actual HTTP response.

### Wrong RestTemplate Bean

A classic mistake is injecting a plain `RestTemplate` and expecting a logical URL to go through LoadBalancer automatically:

~~~java
// If this is a plain bean, host "catalog-service" is treated as a DNS host.
directRestTemplate.getForObject(
        "http://catalog-service/whoami",
        String.class
);
~~~

Without matching DNS/hosts entries, the call fails due to hostname resolution failure. The fix is to use the `@LoadBalanced` bean and ensure discovery provides instances for the service ID.

### Using a Load-Balanced Bean with localhost or an IP URL

~~~java
// Do not assume this is a physical call if the bean has @LoadBalanced.
serviceRestTemplate.getForObject(
        "http://localhost:8081/whoami",
        String.class
);
~~~

Depending on how the integration operates, `localhost` may be treated as a service ID. The fix is to use the `directRestTemplate` bean for fixed endpoints.

## 8. Timeouts, Retries, and Health Checks: Differences in Scope

Calling by service ID adds an instance selection step, but that **does not automatically configure connect timeouts, read timeouts, or retries** for HTTP requests.

`RestTemplate` timeouts depend on `ClientHttpRequestFactory` and the chosen HTTP transport. Illustrative example using a simple request factory:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(2000); // 2 seconds
factory.setReadTimeout(3000);    // 3 seconds

RestTemplate restTemplate = new RestTemplate(factory);
~~~

This snippet shows that timeouts belong to HTTP execution; it does not yet create a load-balanced bean. To use it with LoadBalancer, declare a `@LoadBalanced RestTemplate` bean configured with the appropriate request factory.

**Retries** must be configured and tested per integration. When retry is supported and enabled, a retry may hit the same instance or another instance depending on policy. Retrying does not automatically mean the discovery list has been refreshed; if a dead instance remains cached, requests may continue selecting that endpoint.

**Health checks** belong to the `ServiceInstance` provider or configured registry/supplier. If unhealthy endpoints are filtered out before selection, requests can avoid failing replicas. However, merely adding `@LoadBalanced` does not probe every instance with HTTP health checks on each request.

When calling state-mutating APIs (such as payments or order creation), account for idempotency before enabling retries to avoid re-sending operations already processed by the backend.

## 9. Choosing the Call Style Based on Real Requirements

| Requirement | Suitable approach | Reason |
|---|---|---|
| Inter-microservice communication with multiple replicas | `@LoadBalanced RestTemplate` + service ID | Avoids coupling to a fixed IP/port |
| System scaling instance counts via autoscaling | `@LoadBalanced RestTemplate` + dynamic discovery | Supplier can receive updated instance lists |
| Calling partner APIs via public hostname | Plain `RestTemplate` + real URL | Uses DNS/TLS/proxy per network configuration |
| Probing a specific failing instance | Plain `RestTemplate` + instance URI | Guarantees the request hits the exact endpoint under diagnosis |
| Calling a fixed reverse proxy or API gateway | Plain `RestTemplate` + gateway URL | Backend selection may be handled by the gateway |
| Using health, zone, or hint routing in Spring Cloud LoadBalancer | Load-balanced bean + service ID + appropriate supplier | Policies shape the candidate list |
| Bypassing discovery to call a known address | Plain bean + physical URL | HTTP client uses the specified address |

An application can combine both approaches, provided beans are explicitly named and injected to avoid selecting the wrong client.

## 10. Hands-On Verification of Request Routing

You can practice this in a simple setup with two `catalog-service` servers on ports `8081` and `8082`, plus an `order-service` client:

1. Configure two beans `serviceRestTemplate` (`@LoadBalanced`) and `directRestTemplate` (`@Primary`) as in section 3.
2. Configure `SimpleDiscoveryClient` for service ID `catalog-service` pointing to both instances.
3. Add a `GET /whoami` endpoint on each instance returning its name or port.
4. Call `serviceRestTemplate.getForObject("http://catalog-service/whoami", String.class)` and record results across multiple requests.
5. Call `directRestTemplate.getForObject("http://127.0.0.1:8081/whoami", String.class)` and compare.
6. Intentionally call `http://catalog-service/whoami` via the plain bean in an environment without matching DNS to see the difference.
7. Stop server `8081` and inspect behavior for both the direct call and the service-ID call. Remember that the static list still retains `8081`; to test failover after discovery updates, update configuration and restart the client or use dynamic discovery.
8. Log the service ID, selected instance URI (if available), HTTP status, exception, and call duration to separate target-selection errors from HTTP execution errors.

When verifying results, avoid assuming "request succeeded" means LoadBalancer was used. A plain bean calling via DNS or a proxy can also succeed. Real proof lies in **the injected bean, LoadBalancer interceptor, service ID, candidate list, and the actual endpoint chosen**.

## 11. Checklist When RestTemplate Calls the Wrong Target

Before changing configuration, verify each item in order:

- Does the `RestTemplate` bean in use have `@LoadBalanced`, or is it a plain bean?
- Is the URL a logical service ID or a physical hostname/IP? Is it paired with the right bean?
- Are `spring-cloud-starter-loadbalancer` and a discovery source configured for service-ID calls?
- Does the service ID in the URL match the registered name, and does the supplier return instances?
- Do the selected instance's host, port, and scheme fit the client's network environment?
- Did the failure occur during instance lookup, URI construction, connection opening, or HTTP response handling?
- Are retries, timeouts, and health checks properly configured and observable?
- If both beans exist, are `@Qualifier` or `@Primary` used explicitly to prevent mis-injection?

**Rule to remember:** `@LoadBalanced RestTemplate` treats the service ID as a logical hostname so Spring Cloud LoadBalancer selects a `ServiceInstance`. A plain `RestTemplate` sends requests to a concrete URL and relies on network mechanisms such as DNS, proxies, or gateways to reach the destination. Distinguishing the two behaviors keeps service calls reliable and enables accurate diagnosis of discovery, load balancing, timeout, and connection failures.

**Official documentation:**

- [Spring Cloud Commons – Spring RestTemplate as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html#spring-resttemplate-as-a-loadbalancer-client)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
