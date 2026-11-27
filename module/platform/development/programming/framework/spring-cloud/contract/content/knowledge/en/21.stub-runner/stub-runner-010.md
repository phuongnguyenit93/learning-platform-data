# Mapping Artifacts to Service IDs with Service Discovery Integration

## Lesson objectives

In **Spring Cloud Contract**, the **producer** describes HTTP or messaging behavior using Groovy/YAML DSL; the tool generates producer tests and builds a **stub artifact** for the **consumer** to run with **Stub Runner**. When a consumer calls a fixed address directly, pointing to the stub's port is straightforward. However, in microservices architectures, clients commonly call services by **logical name** instead of server addresses: for example, Feign calling `orders-api`, or a load-balanced `RestTemplate` calling `http://orders-api`.

In that scenario, **two identification systems** exist:

- **Artifact ID**: part of the stub JAR's coordinates in a Maven/artifact repository, used to **download the right stub bundle**.
- **Service ID**: the service name the consumer application uses with **`DiscoveryClient`**, **Spring Cloud LoadBalancer**, Feign, or a discovery-aware HTTP client, used to **route calls**.

The two names can match, yet **do not have to match**. The **Stub Runner Spring Cloud** integration lets stub instances be discovered via service discovery and configures mappings from artifact IDs to the service IDs used by the consumer.

After this lesson, you will be able to:

1. Distinguish `groupId`, `artifactId`, `version`, `classifier`, `port`, and `serviceId`.
2. Explain the roles of `DiscoveryClient` and `ReactorServiceInstanceLoadBalancer` when Stub Runner runs HTTP stubs.
3. Use `spring.cloud.contract.stubrunner.ids-to-service-ids` to map artifacts to consumer service names.
4. Set up consumer tests with `@AutoConfigureStubRunner` and a load-balanced client.
5. Diagnose situations where stubs started yet Feign/WebClient/RestTemplate still call the wrong target.
6. Design CI checks verifying the right stub version without accidentally calling real services.

## 1. The problem: artifact name and service name do not match

Suppose Checkout Service needs to query Order Service. The producer publishes stubs as follows:

~~~text
groupId      com.example.orders
artifactId   order-contract-stubs
version      1.4.2
classifier   stubs

Stub artifact coordinates:
com.example.orders:order-contract-stubs:1.4.2:stubs
~~~

Yet Checkout calls the logical service:

~~~text
orders-api
~~~

Example Feign client:

~~~java
@FeignClient(name = "orders-api")
public interface OrderClient {

    @GetMapping("/api/orders/{id}")
    OrderResponse findById(@PathVariable("id") String orderId);
}
~~~

`OrderResponse` is an illustrative application DTO. In this code, `orders-api` is the **service ID Feign routes to**, not a JAR filename and not an HTTP endpoint path.

If Stub Runner downloads `order-contract-stubs` and opens an HTTP stub on a random port without registering it under `orders-api`, the consumer can fail with:

- No instances found for service ID `orders-api`.
- Client falls back to real discovery and calls an unintended server.
- Stub server responds when called directly at `localhost:port`, yet Feign still fails.

**The solution is not changing the contract URL** from `/api/orders/{id}` to another URL. What needs fixing is the **bridge between the stub's artifact identity and the consumer's service ID**.

## 2. Two distinct steps: resolving the artifact and finding a ServiceInstance

~~~mermaid
flowchart TD
    A["Consumer integration test"] --> B["Stub Runner"]
    B --> C["Resolve stub JAR<br/>group:artifact:version:classifier"]
    C --> D["Start HTTP stub<br/>localhost:allocated port"]
    D --> E["Stub Runner Spring Cloud<br/>map artifact → service ID"]
    E --> F["DiscoveryClient / LoadBalancer"]
    G["Feign / RestTemplate / WebClient<br/>calls orders-api"] --> F
    F --> H["Select ServiceInstance<br/>of running stub"]
    H --> D
    D --> I["Return HTTP response from mapping"]
    I --> J["Consumer verifies behavior"]
~~~

Distinguish each step:

| Step | Input | Result |
| --- | --- | --- |
| **Artifact resolution** | `com.example.orders:order-contract-stubs:1.4.2:stubs` | Downloads the exact JAR containing stub mappings |
| **Stub startup** | JAR contents, stub server configuration | A simulated HTTP server on host/port |
| **Service ID mapping** | Running artifact and consumer's service name | Stub is recognized under logical name, e.g., `orders-api` |
| **Service discovery** | `getInstances("orders-api")` or instance selection request | List/instance with URI pointing to the stub |
| **Consumer HTTP request** | Endpoint `/api/orders/ORD-1001` | HTTP response defined by the stub mapping |

**Mapping does not alter the stub JAR's contents.** It controls how the consumer test finds the stub instance. If a mapping inside the JAR returns 404 due to a request mismatch, changing the service ID cannot fix a wrong method, path, header, or body matcher.

## 3. Understanding each kind of ID accurately

A Stub Runner ID can contain:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs
       group             artifact       version classifier
~~~

In Stub Runner configuration, a **port** can also appear:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs:8090
~~~

| Concept | Example | Where is it used? |
| --- | --- | --- |
| **group ID** | `com.example.orders` | Artifact namespace in the repository |
| **artifact ID** | `order-contract-stubs` | Identifies the stub module/artifact |
| **version** | `1.4.2` | Selects the artifact version |
| **classifier** | `stubs` | Selects the stub JAR instead of the main application JAR |
| **stub port** | `8090` or dynamic port | HTTP server port run by Stub Runner |
| **service ID** | `orders-api` | Name used by the consumer for service discovery |
| **endpoint path** | `/api/orders/ORD-1001` | Request the HTTP stub must match |

Only the **first four parts** form the artifact coordinates in this example. `port` is a Stub Runner runtime parameter; `service ID` is a service-discovery-layer name; `endpoint path` belongs to the HTTP contract.

Notably, the producer's `spring.application.name` and publication `artifactId` are often named similarly by team convention, yet **no rule forces them to match**. The service ID called by the consumer may be an alias kept for historical reasons or deployment architecture.

## 4. Where does Stub Runner Spring Cloud plug in?

Spring Cloud Contract provides **Stub Runner Spring Cloud** integration to expose stub servers through Spring Cloud's instance lookup mechanisms. Spring docs describe integration with:

- **`DiscoveryClient`**: API to query the list of instances for a service ID.
- **`ReactorServiceInstanceLoadBalancer`**: instance-selection mechanism in Spring Cloud LoadBalancer for reactive flows.

When configured properly, clients using the **discovery/load-balanced** path can call stubs instead of real services. No production Eureka, Consul, or ZooKeeper needs to run just so a consumer can test a dependency.

### Integration is not automatic for every HTTP client

| How consumer calls | Goes through service discovery? | Consequence |
| --- | --- | --- |
| `@FeignClient(name = "orders-api")` with proper load-balancing integration | Yes, per Feign/Spring Cloud config | Can select the stub registered under `orders-api` |
| `@LoadBalanced RestTemplate` calling `http://orders-api` | Yes | Can resolve `orders-api` to the stub instance |
| `@LoadBalanced WebClient.Builder` calling `http://orders-api` | Yes | Can use Spring Cloud LoadBalancer to reach the stub |
| `new RestTemplate()` calling `http://orders-api` | Usually no | `orders-api` may be treated as a DNS hostname, not a service ID |
| `WebClient.create("http://localhost:8080")` | Bypasses service ID | Artifact → service ID mapping has no effect |
| HTTP client calling a URL from a static config variable | Depends on client | May need direct test URL override rather than discovery |

**Both sides must be configured:** Stub Runner registers the right logical name, **and** the consumer client actually uses load balancing/discovery. A valid map in YAML cannot turn a plain `RestTemplate` into a load-balanced client.

## 5. Configuring ids-to-service-ids in consumer tests

Suppose the stub has artifact ID `order-contract-stubs`, while the consumer calls service ID `orders-api`.

Reference test configuration in `src/test/resources/application-contract.yml`:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          order-contract-stubs: orders-api
~~~

Read in this direction:

~~~text
Artifact ID in Stub Runner   →   Service ID used by consumer
order-contract-stubs         →   orders-api
~~~

**Do not reverse the direction.** Writing `orders-api: order-contract-stubs` means something else and will not solve this scenario.

In Spring Boot, `ids-to-service-ids` is kebab-case property notation; in some docs/examples or programmatic config you will see `idsToServiceIds`. Property names and binding must be verified against the Spring Cloud Contract version in use.

### When group IDs must be distinguished

If multiple producers share the same artifact ID, using only the `order-contract-stubs` key can be ambiguous. Configuration supports Ivy-style identifier keys, such as a `groupId:artifactId` pair:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          "com.example.orders:order-contract-stubs": orders-api
          "com.example.billing:payment-contract-stubs": billing-api
~~~

**Double quotes around keys containing colons** are required so YAML parses them cleanly as string keys. Matcher resolution uses artifact ID / Ivy notation per your Stub Runner version's capabilities; verify the actual mapping against loaded stubs.

Notice that group `com.example.orders` in the example **differs** from the `orders-api` service namespace. Mapping does not require them to share a prefix.

### What if no mapping is configured?

Examples in Spring Cloud Contract docs describe inferring the service ID from the stub's `artifactId`. Thus, if the artifact ID itself is `orders-api` and the consumer also calls `orders-api`, custom mapping may not be needed.

However, when the artifact ID is `order-contract-stubs` while the consumer calls `orders-api`, **declare an explicit mapping** and include a test checking `DiscoveryClient.getInstances("orders-api")` rather than relying on inferred names.

## 6. Complete consumer integration test flow example

Suppose Checkout defines a `RestTemplate` as a load-balanced bean:

~~~java
package com.example.checkout.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class CheckoutHttpConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate ordersRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Consumer uses the service ID without hardcoding stub ports:

~~~java
package com.example.checkout.orders;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class OrderLookup {

    private final RestTemplate restTemplate;

    public OrderLookup(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String getOrderJson(String orderId) {
        return restTemplate.getForObject(
            "http://orders-api/api/orders/{id}",
            String.class,
            orderId
        );
    }
}
~~~

To keep the lesson simple, the example returns a JSON string. In real applications, use a DTO and check the fields the consumer needs, rather than comparing JSON key order literally.

With Stub Runner and a Spring Boot test environment:

~~~java
package com.example.checkout.orders;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("contract")
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-contract-stubs:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderDiscoveryContractTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Autowired
    OrderLookup orderLookup;

    @Test
    void shouldFindStubThroughOrdersApiServiceId() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("orders-api");
        assertFalse(instances.isEmpty(),
            "orders-api must resolve to a stub instance");

        String json = orderLookup.getOrderJson("ORD-1001");
        assertNotNull(json);
        assertTrue(json.contains("\"PAID\""));
    }
}
~~~

This is an **example skeleton**; real tests need dependencies, annotations, and packages configured for your Spring Boot/Spring Cloud versions, plus the `1.4.2` stub JAR installed in local Maven. `@ActiveProfiles("contract")` causes Spring to load `application-contract.yml` in the example.

Expected sequence:

1. Stub Runner downloads `com.example.orders:order-contract-stubs:1.4.2:stubs`.
2. Stub Runner starts the HTTP stub on a selected port.
3. Spring Cloud integration registers the stub under `orders-api` per the mapping.
4. `DiscoveryClient.getInstances("orders-api")` returns at least one `ServiceInstance`.
5. `OrderLookup` calls `http://orders-api/...` using the load-balanced `RestTemplate`.
6. Consumer receives the stub's response and verifies its business logic.

**Do not stop at `assertFalse(instances.isEmpty())`.** That only confirms an instance was found. There must be real requests going through the application client and assertions on responses or post-processing application state.

### With Feign

If Checkout uses Spring Cloud OpenFeign:

~~~java
@FeignClient(name = "orders-api")
interface OrderClient {

    @GetMapping("/api/orders/{id}")
    OrderResponse getOrder(@PathVariable("id") String id);
}
~~~

Feign must be enabled/configured for the project with appropriate load-balancing integration. Identifier `orders-api` is the exact service ID the mapping must provide—**it does not need to match the artifact name**. `@FeignClient` by itself does not prove stubs loaded successfully; consumer tests must actually invoke methods and assert outcomes.

### With reactive WebClient

Example Spring Cloud LoadBalancer configuration for `WebClient`:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
~~~

When the consumer uses this builder to call `http://orders-api/api/orders/...`, calls can use discovery/load balancing. If you create another builder via `WebClient.builder()` at the call site without a load-balancing filter, Stub Runner's mapping will not affect that client.

## 7. Do not confuse service ID with endpoint name or instance ID

Suppose the stub runs on:

~~~text
http://127.0.0.1:10876
~~~

And the consumer calls:

~~~text
http://orders-api/api/orders/ORD-1001
~~~

With discovery/load-balancing integration, the consumer does not need to know port `10876`. It requests an instance belonging to service ID `orders-api`. The load balancer retrieves the stub's address and dispatches the HTTP request there.

| Field | Illustrative value | Should it be hardcoded in consumer code? |
| --- | --- | --- |
| Service ID | `orders-api` | May be an explicit constant/config in the client |
| Stub host/port | `127.0.0.1:10876` | No, if the client uses discovery; port may be dynamic |
| Artifact coordinates | `com.example.orders:order-contract-stubs:1.4.2:stubs` | Placed in test/CI configuration |
| HTTP path | `/api/orders/ORD-1001` | Defined by contract, port-independent |
| Instance ID | May be generated by adapter | Should not be inferred from artifact or used as service ID |

**Service ID mapping does not rename all instance metadata.** Its main job is ensuring the application locates the stub under the agreed service name. Advanced `ServiceInstance` properties such as metadata, scheme, secure flag, or zone must be checked separately if the application depends on them.

## 8. DiscoveryClient and LoadBalancer: check both layers

A consumer might call directly:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("orders-api");
~~~

Or let a Feign client, `RestTemplate`, or load-balanced `WebClient` choose an instance.

These two interactions are related yet distinct:

- **DiscoveryClient**: returns instance lists by service ID; sees registered stubs.
- **LoadBalancer**: selects an instance to execute the request; may apply selection logic, retries, or metadata filters.

Stub Runner Spring Cloud integrates with discovery and Spring Cloud LoadBalancer, yet that **does not guarantee every custom client or custom instance-selection policy automatically uses the stub**.

For example, an application might have a custom `ServiceInstanceListSupplier` filtering by zone or metadata. If the stub instance lacks the metadata required by that filter, `DiscoveryClient` may see the service while the client still fails to pick an instance. In that situation, inspect client/test configuration and metadata policies rather than immediately editing HTTP contracts.

## 9. Protecting tests from real service discovery

In consumer integration tests, you typically do not want to hit real Eureka/Consul/ZooKeeper or an external Config Server. Those external sources can make tests:

- Unreproducible between laptops and CI.
- Dependent on DNS/network and access permissions.
- Accidentally call staging/production services instead of stubs.
- Keep PASSing thanks to real service responses, masking broken stub mappings.

Stub Runner Spring Cloud documentation describes **stub service discovery** mode and options to coordinate with an existing `DiscoveryClient`. Related properties you may encounter:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        cloud:
          enabled: true
          loadbalancer:
            enabled: true
          stubbed:
            discovery:
              enabled: true
~~~

The snippet above illustrates **the intent of enabling Stub Runner Spring Cloud, load-balancing integration, and stubbed discovery**, not a substitute for checking defaults in your specific version.

**When delegating to an existing `DiscoveryClient`:** some versions support `spring.cloud.contract.stubrunner.cloud.delegate.enabled` to combine real discovery results with stubs. Default rules and scope for that option must be checked for your running version. In CI requiring strict isolation, verify **no unintended real instance** appears among instances selectable by the consumer.

You do not always have to disable every external discovery source; some pipelines intentionally mix in certain real test services. In those cases, **declare the scope clearly**, control endpoints, and never allow silent fallback to production.

### Why does stubbed service discovery still require client configuration?

Suppose stubbed discovery registered `orders-api`, yet the client is constructed as:

~~~java
RestTemplate restTemplate = new RestTemplate();
restTemplate.getForObject(
    "http://orders-api/api/orders/ORD-1001",
    String.class
);
~~~

Without an interceptor/load balancer, `orders-api` is treated as a DNS hostname. Adding `ids-to-service-ids` to YAML **does not make** this client use `DiscoveryClient`.

You must inject a `@LoadBalanced`-annotated `RestTemplate` or use another properly configured test HTTP calling mechanism.

## 10. Multiple stubs and service ID collisions

Suppose Checkout has two dependencies:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs
com.example.billing:billing-contract-stubs:2.2.0:stubs
~~~

Mapping configuration:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          "com.example.orders:order-contract-stubs": orders-api
          "com.example.billing:billing-contract-stubs": billing-api
~~~

The consumer can call:

~~~text
http://orders-api/api/orders/ORD-1001
http://billing-api/api/payments/PAY-1001
~~~

This requires two independent checks: `orders-api` resolves to the Order stub, and `billing-api` resolves to the Billing stub. If both are mistakenly mapped to `orders-api`, the load balancer receives incompatible instances under one service ID and requests fail intermittently depending on instance selection.

**Never intentionally map multiple artifacts to one service ID** unless genuinely modeling multiple instances of the same service with compatible behavior. If multiple stub versions of the same service ID run simultaneously, test outcomes can become unstable when mappings differ; isolate each version combination under test.

### Verification table

| Loaded artifact | Expected service ID | Representative request |
| --- | --- | --- |
| `order-contract-stubs:1.4.2` | `orders-api` | `GET /api/orders/ORD-1001` |
| `billing-contract-stubs:2.2.0` | `billing-api` | `GET /api/payments/PAY-1001` |

After starting Stub Runner, confirm both service IDs have instances, URIs point to the right stub servers, and requests to each service ID return the expected responses.

## 11. When artifact ID and service ID match

A project has:

~~~text
artifactId = inventory-service
serviceId  = inventory-service
~~~

In this case, default mapping based on `artifactId` may already work. You can let Stub Runner Spring Cloud register under that name without an explicit map.

Still, before omitting the map, check:

1. Does the downloaded artifact have the exact group/artifact/version/classifier?
2. Is there an instance in `DiscoveryClient.getInstances("inventory-service")`?
3. Does the consumer's real HTTP client use that exact service ID?
4. Does a consumer request actually reach the stub on the Stub Runner-allocated port?

Do not assume identical artifact and service strings mean **all connections** automatically route to the stub. Client setup, auto-configuration, and dependency versions still apply.

## 12. Using dynamic ports instead of locking ports just to form service IDs

Stub Runner handles HTTP stub server port selection; omitting the port usually enables automatic port selection per configuration. With discovery integrated, the consumer **does not need to hardcode ports** in logic:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-contract-stubs:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

The client still calls:

~~~text
http://orders-api/api/orders/ORD-1001
~~~

Benefits:

- Parallel tests or CI runs suffer fewer fixed-port collisions.
- No port updates in service code when Stub Runner switches instances.
- Easy to run the same consumer test across machines.

**Dynamic ports do not fix wrong mappings.** If the test cannot find `orders-api`, check mapping and discovery integration. If the client finds an instance yet gets HTTP 404, inspect request mappings inside the stub JAR. If `Connection refused`, verify the stub server is running and the instance URI/port is accurate.

## 13. Do not confuse HTTP service discovery integration with message destinations

A message contract might use:

~~~groovy
outputMessage {
    sentTo("orders.events")
    body(eventType: "ORDER_PAID", orderId: "ORD-1001")
}
~~~

`sentTo("orders.events")` is a **message destination** in the messaging model; it is not a service ID for Feign or `RestTemplate` to locate an HTTP stub.

| Mechanism | Required identifier | Used for what? |
| --- | --- | --- |
| HTTP Stub Runner + DiscoveryClient | `orders-api` | Consumer finds HTTP stub server via service discovery |
| HTTP artifact resolution | `com.example.orders:order-contract-stubs:1.4.2:stubs` | Downloads stub JAR |
| Message contract | `orders.events` | Specifies where producer emits messages per messaging adapter |
| Message stub label | `order_paid` | Can trigger message stubs via Stub Runner when adapter supports it |

**Never use `ids-to-service-ids` to rename Kafka topics or RabbitMQ routing keys.** That is a messaging binding/destination concern requiring separate configuration and testing.

## 14. Symptoms of each failure type

| Symptom | Possible cause | Verification step |
| --- | --- | --- |
| Stub Runner fails to download JAR | Wrong coordinates or `stubsMode`/repository | Check group, artifact, version, classifier, and source |
| Stub server runs yet `getInstances("orders-api")` is empty | Missing name map or Stub Runner Spring Cloud inactive | Check `ids-to-service-ids`, auto-configuration, and classpath |
| `getInstances` returns instance yet Feign fails | Feign/LB or metadata filter drops the instance | Check load balancer and Feign service ID |
| `RestTemplate` fails DNS resolution for `orders-api` | Client is not a `@LoadBalanced RestTemplate` | Inspect the bean actually injected |
| Consumer connects yet receives 404 from stub | HTTP request does not match mapping | Check method, path, headers, query, body |
| Consumer receives real service response | Discovery/fallback hit non-test instance | Isolate discovery and verify actual URI |
| Two dependencies return mixed-up data | Two artifacts mapped to the same service ID | Check map keys/values and instance list |
| Local PASS, CI fails resolution | JAR only exists in local Maven cache | Publish artifact or configure REMOTE with fixed version |
| Test PASSes yet new behavior breaks production | Consumer using outdated stub version | Pin version and rerun consumer with new stub |
| Another test affects discovery | Shared context/registry, multiple stubs under one service ID | Isolate configuration, lifecycle, and test execution |

Before editing any contract, pinpoint whether the failure sits in **JAR download**, **stub startup**, **service ID mapping**, **instance selection**, or **HTTP request matching**.

## 15. Layer-by-layer verification workflow

~~~mermaid
flowchart TD
    A["Consumer test starts"] --> B{"Downloaded right stub JAR?"}
    B -->|No| X["Check GAV/classifier/repository"]
    B -->|Yes| C{"Stub server running?"}
    C -->|No| Y["Check startup logs/port"]
    C -->|Yes| D{"Service ID mapped properly?"}
    D -->|No| Z["Check ids-to-service-ids"]
    D -->|Yes| E{"DiscoveryClient sees stub instance?"}
    E -->|No| U["Check Stub Runner Spring Cloud"]
    E -->|Yes| F{"HTTP client uses LoadBalancer?"}
    F -->|No| V["Check Feign/RestTemplate/WebClient"]
    F -->|Yes| G{"Request matches stub mapping?"}
    G -->|No| W["Inspect method/url/header/body"]
    G -->|Yes| H["Assert consumer behavior and record evidence"]
~~~

This workflow avoids a common trap: seeing HTTP 404 and loosening regexes in the contract while the consumer was actually hitting a different instance; or editing service IDs while Stub Runner never loaded the right stub JAR.

### What should a solid test verify?

1. **Artifact identity:** Stub Runner loaded the exact `1.4.2` JAR, not a dynamic version or uncontrolled cache.
2. **Logical identity:** Service ID `orders-api` has an active instance when tests run.
3. **Actual URI:** The instance selected by the load balancer truly points to the test stub server, not another environment.
4. **HTTP mapping:** Requests emitted by the consumer match contract scenarios.
5. **Consumer outcome:** Consumer applies the response accurately; e.g., Checkout displays/propagates status `PAID` as required.

Vaguely confirming "Stub Runner started" is insufficient.

## 16. CI and cross-version compatibility

Suppose producer `order-service:1.5.0` changes its response structure and publishes a new stub. Consumer Checkout still calls `orders-api` via Feign.

If Checkout's CI uses:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs
~~~

then a passing CI run only means Checkout is compatible with tested scenarios of **stub 1.4.2**. It **does not prove** Checkout is compatible with producer `1.5.0`.

Release gates should link:

~~~yaml
# Team-designed CI record template;
# not a default output of Spring Cloud Contract.
producer_revision: "order-service@abc123"
contract_revision: "contracts@def456"
stub_artifact: "com.example.orders:order-contract-stubs:1.5.0:stubs"
consumer_version: "checkout-service:2.8.0"
service_id: orders-api
stub_discovery_instance_verified: true
actual_consumer_call_verified: true
producer_contract_tests: PASS
consumer_stub_tests: PASS
~~~

In CI, you should:

- Publish new stubs only from producer builds where **generated producer tests** actually ran and passed.
- Lock versions and artifact checksums where repository policy allows.
- Download the right stub version before running consumer tests.
- Verify artifact → service ID mapping and routing through the real client.
- Prevent silent fallback to staging/production services.
- Record verified consumer versions and scenarios explicitly.

**Compatibility evidence always has boundaries.** Stub Runner + discovery mapping tests how the consumer uses service names in test environments, yet does not verify production Eureka/Consul/Kubernetes setups, authentication, TLS, or load capacity.

## 17. Practice exercises

### Exercise A — Filling in the mapping

Producer publishes artifact:

~~~text
com.example.inventory:inventory-contracts:3.2.1:stubs
~~~

Consumer calls `http://inventory-api/api/stock/SKU-1001` using a load-balanced `RestTemplate`.

**Task:** write the YAML config for `ids-to-service-ids`, identifying which is the artifact ID and which is the service ID.

**Hint:**

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          inventory-contracts: inventory-api
~~~

### Exercise B — Service not found

Stub Runner starts the Order stub on port `11021`. `DiscoveryClient.getInstances("orders-api")` returns an empty list. Feign remains configured with `name = "orders-api"`.

**Task:** list the check order from artifact ID to map, classpath, and auto-configuration. Explain why port 11021 alone does not let Feign discover the service.

**Hint:** port is the physical stub address; Feign resolves by service ID. Mapping and `DiscoveryClient`/LoadBalancer integration are required.

### Exercise C — Non-load-balanced client

A developer configures the map properly and `DiscoveryClient` sees `inventory-api`, yet `new RestTemplate()` still fails with a DNS error when calling `http://inventory-api`.

**Task:** diagnose the issue and propose how to configure the client.

**Hint:** use a `@LoadBalanced RestTemplate` or a client genuinely integrated with Spring Cloud LoadBalancer; the map does not alter a `RestTemplate` instantiated with `new`.

### Exercise D — Duplicate service ID

Both `order-contract-stubs` and `billing-contract-stubs` are mapped to `orders-api`. Tests intermittently receive Billing mappings.

**Task:** redesign the map and explain how to verify instance/route lists via tests.

**Hint:** assign distinct service IDs `orders-api` and `billing-api` matching what consumers actually use; verify each client and endpoint.

### Exercise E — Avoid calling production services

The consumer has a real `DiscoveryClient` on the classpath. During some CI runs testing `orders-api`, requests unexpectedly reach staging.

**Task:** propose a discovery-isolation policy and instance-URI verification, noting limits of the delegate option.

**Hint:** disallow unintended merging/fallback; check Stub Runner Spring Cloud flags for your version and assert every selected instance belongs to test stub infrastructure.

### Exercise F — Comparing version evidence

Order Service 1.5.0 renamed field `status` to `paymentStatus`, yet Checkout 2.8.0 still PASSes with stub 1.4.2.

**Task:** evaluate the compatibility claim and propose a release gate using the right new stub and service ID.

**Hint:** producer 1.5.0 must be verified with the new contract; consumer 2.8.0 must run against the new build's stub and call through `orders-api`. Passing on stub 1.4.2 does not answer that question.

## 18. Checklist for mapping stub artifacts to service IDs

- [ ] Identified exact `groupId`, `artifactId`, `version`, and `classifier` of the stub JAR.
- [ ] Identified the **service ID the consumer actually uses**, not inferred from producer package names.
- [ ] If the two names differ, configured `ids-to-service-ids` in **artifact → service ID** direction.
- [ ] If multiple artifacts share an `artifactId`, used an unambiguous key.
- [ ] Stub Runner loads the right artifact from `LOCAL`/`REMOTE`/`CLASSPATH` per selected configuration.
- [ ] HTTP stub server starts cleanly; stub ports may vary across runs.
- [ ] Stub Runner Spring Cloud integration and `DiscoveryClient`/LoadBalancer are active.
- [ ] `DiscoveryClient.getInstances(serviceId)` returns expected instances per scenario.
- [ ] Feign, `RestTemplate`, or `WebClient` is configured as **load-balanced** when calling by service ID.
- [ ] No staging/production instances are unexpectedly selected in consumer CI.
- [ ] HTTP service IDs are not confused with messaging `sentTo` destinations or message stub labels.
- [ ] Consumer tests genuinely send requests via service ID and assert business outcomes.
- [ ] Producer contract tests passed on the build tied to the stub artifact.
- [ ] Consumer CI uses the **new stub version** when evaluating compatibility with a new producer.
- [ ] CI reports record artifact, contract revision, service ID, and verified consumer versions.

**Remember:** `artifactId` helps Stub Runner **locate the right JAR**, while `serviceId` helps the consumer app **locate the right HTTP stub instance**. When the two names differ, use `ids-to-service-ids` to connect them while ensuring the HTTP client uses discovery/load balancing and CI never accidentally calls real services. A proper mapping only ensures the consumer test reaches the right stub; compatibility evidence also requires generated producer tests, accurate mappings, and consumer assertions on the exact artifact version.

## References

- [Spring Cloud Contract — Stub Runner Spring Cloud](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-cloud.html): `DiscoveryClient`, load balancer integration, and `idsToServiceIds` mapping.
- [Spring Cloud Contract — Configuration Properties](https://docs.spring.io/spring-cloud-contract/reference/configprops.html): `ids-to-service-ids`, `cloud.enabled`, and `cloud.loadbalancer.enabled` properties.
- [Spring Cloud Contract — Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): Stub Runner IDs syntax and stub resolution sources.

**Version note:** examples in this lesson illustrate common behavior and configuration; before applying them to a real project, consult documentation for the exact Spring Cloud Contract/Spring Cloud/Spring Boot versions locked in your build and inspect actual generated behavior.
