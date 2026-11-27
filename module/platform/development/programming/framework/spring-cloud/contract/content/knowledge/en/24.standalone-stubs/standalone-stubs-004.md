# Exposing Ports and URLs for Calling Applications

## Lesson Objectives

In **Spring Cloud Contract**, producers define HTTP or messaging behavior using the **Groovy/YAML DSL**. Contract Verifier generates producer-side tests, while stubs are packaged so consumers can test against them using **Stub Runner**. When running **standalone stubs**, an often-overlooked step is **exposing the actual address of the stub server to the calling application**.

A stub server may be up and running, yet the consumer still hits `Connection refused`, `UnknownHostException`, or HTTP 404 because the application is calling the wrong **host, port, scheme, or URL path**. In CI or Docker, mistakes happen even more easily when confusing Stub Runner's management port with an individual stub's HTTP port, or using `localhost` in the wrong network context.

After this lesson, you will be able to:

- Distinguish stub artifact coordinates from the **HTTP base URL** of a running stub.
- Distinguish the **standalone runner's management port** from the **request-serving port** of each HTTP stub.
- Design fixed or dynamic port selection and pass URLs to consumers.
- Configure Spring Boot clients, standalone `WireMockServer`, or standalone Stub Runner Boot appropriately for each scope.
- Understand the differences among **host port**, **container port**, Kubernetes Service, and service discovery.
- Build readiness checks with real requests and catch accidental calls to services outside the test environment.
- Use CI to verify producer contract tests, stub readiness, and consumer assertions together.

## 1. Identifiers That Must Not Be Equated

Suppose Order Service publishes a stub JAR with coordinates:

~~~text
com.example.orders:order-service:1.4.2:stubs
~~~

A standalone runner downloads the artifact and runs the Order stub on port `8090`. If Checkout runs on the same machine, the test call URL might be:

~~~text
http://localhost:8090/api/orders/ORD-1001
~~~

| Component | Example | Meaning |
| --- | --- | --- |
| **group ID** | `com.example.orders` | Artifact namespace in the repository |
| **artifact ID** | `order-service` | Module that published the stub |
| **version** | `1.4.2` | Artifact version |
| **classifier** | `stubs` | Selects the stub JAR rather than the application JAR |
| **stub host** | `localhost` | Hostname reachable from where the consumer runs |
| **stub HTTP port** | `8090` | HTTP listener port serving the mappings |
| **base URL** | `http://localhost:8090` | URL prefix configured for the HTTP client |
| **contract path** | `/api/orders/ORD-1001` | HTTP path described in the contract |
| **management port** | `8750` | Standalone runner control application port, if present |

**Artifact coordinates are not a URL.** Coordinates tell Stub Runner which set of mappings to load; the runtime and network determine the URL an application can reach.

Another common confusion: `8090` at the end of a Stub Runner ID can be the **HTTP stub port**, not a classifier or part of the Maven version.

## 2. Standalone Runner Managing Multiple Stub Servers

A standalone **Stub Runner Boot** instance can load multiple stub artifacts and start HTTP stub servers. For example:

~~~mermaid
flowchart LR
    R["Artifact repository"] --> S["Stub Runner Boot<br/>management: 8750"]
    S --> O["Order HTTP stub<br/>port 8090"]
    S --> P["Payment HTTP stub<br/>port 8091"]
    C["Checkout consumer test"] -->|"GET /api/orders/..."| O
    C -->|"GET /api/payments/..."| P
~~~

In this diagram:

- `8750` is the runner's **control application** port.
- `8090` is the HTTP port serving requests for the Order stub.
- `8091` is the HTTP port serving requests for the Payment stub.
- Checkout calls `http://localhost:8090/api/orders/ORD-1001`, **not** `http://localhost:8750/api/orders/ORD-1001` by default.
- The runner management API (if enabled) is separate from the business APIs simulated by WireMock.

When running a `WireMockServer` directly instead of Stub Runner Boot, there may be **only a single HTTP listener** and no separate management port at all. Do not force a two-port mental model onto every WireMock setup.

## 3. HTTP Contracts Define Paths, Not Stub Hosts

Example YAML contract:

~~~yaml
description: "Fetch a paid order"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

The contract specifies the **HTTP method, URL path, request headers, response status, and body**. It does not require the runner to live on `localhost` or port `8090`.

| Source of Truth | What It Determines |
| --- | --- |
| Contract DSL | Method/path/header/body matchers and responses |
| Contract Verifier | Generated producer tests and stub mappings |
| Stub artifact | Packages the right mapping set by group/artifact/version |
| Standalone runner | Which artifacts are loaded and which stub servers are started |
| Network/orchestration | Hostname, published ports, and routing |
| Consumer test config | Base URL or service ID used by the HTTP client |
| CI | Verifies the full chain and records the exact build tested |

Changing a stub's port is a **test execution change**, usually not a breaking HTTP API change. Changing `/api/orders/ORD-1001` or the `status` field, by contrast, can break consumers and must be verified via contracts.

## 4. Example Standalone Stub Runner Boot Configuration

Depending on the version, Stub Runner Boot accepts its ID list and runtime properties via application properties or CLI flags. The example below illustrates two different ports; **exact property names and JAR invocation must match the Stub Runner Boot version you use**:

~~~bash
java -jar stub-runner-boot.jar \
  --server.port=8750 \
  --stubrunner.ids=com.example.orders:order-service:1.4.2:stubs:8090 \
  --stubrunner.stubsMode=LOCAL
~~~

Expected meaning:

- `server.port=8750`: port of the Boot application orchestrating stubs.
- `stubrunner.ids=...:8090`: selects the artifact and assigns the HTTP port for the Order stub.
- `stubrunner.stubsMode=LOCAL`: uses the local artifact source supported by Stub Runner.

In Spring Boot tests using `@AutoConfigureStubRunner`, you will see the `spring.cloud.contract.stubrunner.*` namespace. In standalone Boot, some versions use `stubrunner.*`. **Do not guess namespaces**: check runtime configuration logs and the documentation for your exact release.

When choosing `LOCAL`, the runtime environment needs the corresponding stub JAR in its local repository. If the artifact lives in a remote Maven repository, configure the download source and credentials accordingly. **The runner process starting up does not prove the stub JAR was loaded.**

### When There Are Two Stub Artifacts

Conceptual declaration example:

~~~text
com.example.orders:order-service:1.4.2:stubs:8090
com.example.billing:payment-service:2.3.0:stubs:8091
~~~

How multiple IDs are delimited on the CLI or in YAML can vary by property binder/version; inspect the values the runner actually receives. Do not assume a string gets parsed into two artifacts just because it looks reasonable.

Once the stubs start properly:

~~~text
Order base URL:   http://localhost:8090
Payment base URL: http://localhost:8091
~~~

Port `8750` serves only the **runner management API** if provided by that version; never assume it also acts as an HTTP stub port.

## 5. Fixed Port or Dynamic Port?

| Choice | Advantages | Risks and Mitigations |
| --- | --- | --- |
| **Fixed**, e.g., 8090 | Easy to configure out-of-process clients | Another process may occupy it; CI needs job isolation |
| **Dynamic** | Avoids collisions; fits parallel tests | Must retrieve the port after startup and pass it to the consumer |
| **Port range** | Useful with firewall rules or many stubs | Needs an orchestrator and collision avoidance |
| **Fixed container internal port** | Easy calls between containers on the same network | Published host port can differ from internal port |

A frequent bug: WireMock picks a dynamic port while the client still calls `http://localhost:8090`. The client has no way to know the new port, and might even hit a completely different process.

### Example WireMockServer with a Dynamic Port

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

WireMockServer stub = new WireMockServer(
    wireMockConfig().dynamicPort()
);
stub.start();

try {
    int port = stub.port();
    String baseUrl = "http://localhost:" + port;
    // Pass baseUrl into the HTTP client and run assertions.
} finally {
    stub.stop();
}
~~~

This is the **WireMock Java API**, not an API for querying a remote runner's port. For a standalone process, obtain the port from fixed configuration, a runner query API supported by your version, or published orchestration metadata.

If the runner selects dynamic ports, the consumer must only start testing **after** the final address and port have been resolved.

## 6. Base URL Must Be Configured on the Consumer Application

Never hardcode stub URLs inside business logic:

~~~java
// Anti-pattern: test environment URL embedded in business code.
String url = "http://localhost:8090/api/orders/" + orderId;
~~~

For a Spring Boot consumer, you can configure:

~~~yaml
# application-contract.yml
orders:
  api:
    base-url: "http://localhost:8090"
~~~

Example client using Spring `RestClient`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OrderApiClient {
    private final RestClient restClient;

    public OrderApiClient(
        RestClient.Builder builder,
        @Value("${orders.api.base-url}") String baseUrl
    ) {
        restClient = builder.baseUrl(baseUrl).build();
    }

    public OrderResponse getById(String id) {
        return restClient.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderResponse.class);
    }
}
~~~

`OrderResponse` is an illustrative application DTO. Tests should inject the real stub URL; other runtimes point to their corresponding services. Never let a default `localhost:8090` leak into production configuration.

### Environment Variables for CI

~~~yaml
orders:
  api:
    base-url: "${ORDER_API_BASE_URL:http://localhost:8090}"
~~~

Environment/property placeholder resolution allows CI runners to inject `ORDER_API_BASE_URL`. In strict pipelines, you can **omit the default** so the build fails if no URL was published rather than silently hitting the wrong port.

Configuration must pass the **full scheme://host:port**; passing only a port number is insufficient when client and stub live in different network environments.

## 7. Injecting Dynamic URLs with DynamicPropertySource

A Spring Boot test managing WireMock itself can use `@DynamicPropertySource` to supply the URL:

~~~java
import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

@SpringBootTest
class OrderConsumerContractTest {

    static final WireMockServer STUB =
        new WireMockServer(wireMockConfig().dynamicPort());

    static {
        STUB.start();
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "orders.api.base-url",
            () -> "http://localhost:" + STUB.port()
        );
    }

    @AfterAll
    static void close() {
        STUB.stop();
    }
}
~~~

This is a **lifecycle and wiring skeleton**, without mappings or assertions yet. Starting inside a static initializer illustrates that the stub must be active before Spring reads dynamic properties. In a real project you can use the WireMock JUnit extension or a cleaner lifecycle hook.

An out-of-process test using **standalone Stub Runner Boot** cannot simply call `STUB.port()` like this. It must obtain the URL from the orchestrator, runner configuration, or a supported query API.

### When Stub Runner Runs in the Same Spring Test Context

Some `@AutoConfigureStubRunner` integrations provide utilities such as `StubFinder` or `@StubRunnerPort` to obtain stub URIs/ports:

~~~java
// Sketch — use the exact API for your version and initialization phase:
// URI stubUrl = stubFinder.findStubUrl("com.example.orders", "order-service");
// Build the HTTP client with stubUrl and verify the consumer.
~~~

Do not guess API signatures or blindly use `@DynamicPropertySource` regardless of lifecycle; in some setups Stub Runner starts **after** dynamic properties are registered. In those cases, use an alternative wiring strategy or a controlled fixed port.

## 8. From Host to Docker: Published Ports

Suppose the stub container listens for HTTP on port `8090`, while Docker publishes host port `18090`:

~~~text
Host port 18090 -> Container port 8090
~~~

A Compose configuration **illustrating the network topology**:

~~~yaml
services:
  order-stub:
    image: example/stub-runner-test:1.4.2
    ports:
      - "18090:8090"
      - "18750:8750"

  checkout-test:
    image: example/checkout-test:2.8.0
    environment:
      ORDER_API_BASE_URL: "http://order-stub:8090"
    depends_on:
      - order-stub
~~~

**There is no guarantee that `example/...` images exist.** This is a networking illustration; build/choose real images, start Stub Runner on the right port, supply/mount stub artifacts, and configure the repository for your chosen tooling.

Three perspectives:

| Where Is the Consumer? | Expected URL |
| --- | --- |
| Process or `curl` on the **host machine** | `http://localhost:18090/api/orders/ORD-1001` |
| Checkout container on the **same Compose network** | `http://order-stub:8090/api/orders/ORD-1001` |
| Process **inside the order-stub container** | `http://localhost:8090/api/orders/ORD-1001` |

`localhost` inside the Checkout container is the **Checkout container itself**, not the WireMock container. Port 18090 is published for the host, whereas containers on the same network typically call by service name and **internal port 8090**.

### Bind Interface vs. Destination Host

Inside a container, the stub process must listen on an interface reachable over the container network; usually that means binding to `0.0.0.0` when configurable. However, **`0.0.0.0` is a bind address**, not a hostname to put into a consumer's URL.

Docker's `ports` setting also **does not automatically make a process bound strictly to loopback inside the container reachable externally**; verify the actual listener and routing.

### depends_on Is Not Readiness

Compose can start `order-stub` before `checkout-test` while Stub Runner is still resolving artifacts. Plain `depends_on` does not prove mappings are ready. You need a readiness check and conditional wait with a finite timeout before the consumer sends requests.

## 9. Exposing Management Ports and Stub Ports in Containers

With the example standalone Stub Runner Boot setup:

~~~text
Host 18750 --> Container 8750 : Runner management
Host 18090 --> Container 8090 : Order HTTP stub
~~~

If someone sends GET `/api/orders/ORD-1001` to `localhost:18750`, the server will return 404 because that is the management port, not a WireMock mapping.

**Solution:** call `http://localhost:18090/api/orders/ORD-1001` from the host, or `http://order-stub:8090/api/orders/ORD-1001` from the Checkout container.

If the runner chooses a **dynamic port** while Docker only publishes `8090`, consumers outside the container cannot reach the real port. Assign a stable published port or have the orchestrator publish/forward the allocated port.

Never publish the management API or sensitive stubs directly to the internet. Keep them inside an internal test network with restricted access.

## 10. Kubernetes Services and Remote Environments

When consumers run in a cluster, the stable address is typically a **Kubernetes Service DNS**, not a Pod IP:

~~~text
http://order-stub.contract-test.svc.cluster.local:8090
~~~

This is an illustrative URL. A Service can expose a `port` different from the container's `targetPort`; verify the mapping in the actual manifests.

~~~mermaid
flowchart LR
    C["Checkout test Pod"] --> K["Kubernetes Service<br/>order-stub:8090"]
    K --> P["Stub Pod<br/>listener/targetPort"]
    P --> W["WireMock mappings"]
~~~

Cases to distinguish:

- Consumer in the same namespace: can use the short Service hostname.
- Consumer in another namespace: needs the full hostname or proper DNS.
- Consumer running outside the cluster: ClusterIP/Service DNS may be unreachable; requires `port-forward` or a controlled ingress/gateway.
- Testing through HTTPS ingress: requires matching scheme, certificate, and URL configuration.

**Never hardcode Pod IPs**, because Pods can be recreated and their IP addresses change.

## 11. Reverse Proxies and URL Path Prefixes

Producer stub mapping:

~~~text
GET /api/orders/ORD-1001
~~~

A test environment proxy publishes:

~~~text
https://stubs.test.internal/order-stub/api/orders/ORD-1001
~~~

Two possibilities:

1. The proxy **strips the `/order-stub` prefix** when forwarding; WireMock receives `/api/orders/ORD-1001` and the mapping matches.
2. The proxy preserves the prefix; WireMock receives `/order-stub/api/orders/ORD-1001`, causing an unmatched request if no matching rule exists.

Thus, an HTTP 404 on a URL with the right host and port is not necessarily a contract issue. Inspect the **actual request reaching WireMock** and the proxy's path-rewriting rules.

If the prefix only exists as a CI stub-publishing mechanism, do not add that prefix into the real producer's HTTP contract.

## 12. Readiness Checks Must Send Real Requests

Once you know the base URL, verify with `curl`:

~~~bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8090/api/orders/ORD-1001"
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ORD-1001","status":"PAID"}
~~~

Another request:

~~~bash
curl -i "http://localhost:8090/api/orders/ORD-NOT-FOUND"
~~~

may return 404 if there is no mapping. However, do not confuse a **WireMock unmatched 404** with a **404 error contract** carrying an official error body/schema. If a specific error response is needed, define a dedicated scenario/contract.

### Seeing a Live Process Is Not Enough

~~~mermaid
flowchart TD
    A["Start standalone runner"] --> B{"Process alive?"}
    B -->|No| X["Inspect startup logs"]
    B -->|Yes| C{"Stub artifact/version downloaded?"}
    C -->|No| Y["Check Maven repository and classifier"]
    C -->|Yes| D{"Stub listener open?"}
    D -->|No| Z["Check port/binding"]
    D -->|Yes| E{"Contract request returns right status/body?"}
    E -->|No| U["Check mapping, URL, headers"]
    E -->|Yes| F["Run consumer integration tests"]
~~~

Readiness should verify at least one meaningful request; when multiple critical dependencies exist, wait for each stub's readiness individually.

Avoid using a plain `Thread.sleep(5000)` and assuming all stubs are ready. Artifact download times vary between laptops and CI; poll conditionally with a finite timeout.

## 13. Do Not Confuse Service Discovery with a Fixed Base URL

A consumer might make calls using Feign:

~~~java
@FeignClient(name = "orders-api")
interface OrderClient {
    @GetMapping("/api/orders/{id}")
    OrderResponse getById(@PathVariable("id") String id);
}
~~~

Feign can query Spring Cloud LoadBalancer/DiscoveryClient to locate `orders-api` instead of using a direct URL. When Spring Cloud Stub Runner is integrated inside the test context, you may see a mapping property:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          order-service: orders-api
~~~

Here `order-service` is the **artifact ID** and `orders-api` is the **service ID**. This mapping helps consumer discovery resolve the HTTP stub instance when the integration components support it and are active.

Key distinctions:

- **Direct base URL**: HTTP client calls `http://localhost:8090` or an injected URL.
- **Service discovery**: client uses a service ID; the load balancer needs an instance whose host/port points to the stub.
- **Remote standalone process**: simply launching a JAR does not automatically register discovery entries into a Spring test context.

Do not set `ids-to-service-ids` on a standalone process and assume external Feign/WebClient beans will automatically find the stub. An actual discovery path must exist.

## 14. HTTPS and mTLS When Exposing URLs

When stubs serve HTTPS, the URL changes to:

~~~text
https://localhost:<httpsPort>/api/orders/ORD-1001
~~~

However, **changing `http` to `https` does not create a TLS listener**. Ensure that:

- WireMock or the proxy actually serves HTTPS.
- The client connects to the right HTTPS port.
- The certificate's SAN matches the called hostname.
- The client trusts the test certificate/CA via a proper truststore.
- Hostname verification remains enabled.
- With mTLS, both server and client verify each other's certificates.

If WireMock only opens HTTP `8090` while a proxy terminates HTTPS on `8443`, the TLS test verifies the **consumer → proxy** hop, not that WireMock itself uses HTTPS.

In Docker, a certificate issued for `localhost` is not automatically valid for `order-stub`; the SAN must reflect the real hostname.

## 15. Diagnosing Failures at the Right Layer

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| `Connection refused` | Wrong port, process not running, or unreachable listener | Check bind address, Docker port mapping, and logs |
| Timeout | Network, firewall, or service not ready yet | Check routing, readiness, and timeouts |
| `UnknownHostException` | Hostname cannot be resolved from consumer | Check DNS and network namespace |
| `SSLHandshakeException` | Wrong HTTPS port, trust issue, or certificate mismatch | Check TLS listener, SAN, and truststore |
| HTTP 404 on management port | Called runner control API by mistake | Call the actual stub server port |
| HTTP 404 on stub port | Request does not match mapping or wrong proxy rewrite | Check method, path, headers, and request journal |
| HTTP 200 with wrong payload | Wrong artifact/scenario or hit wrong stub server | Check GAV/classifier, mappings, and base URL |
| Local PASS, Docker FAIL | `localhost` or published/internal port confused | Check whether client runs on host or in container |
| Consumer calls staging | Property fallback or service discovery not isolated | Assert resolved URI instances and configuration |
| Consumer CI PASS despite producer API change | Using an outdated stub artifact version | Pin the new artifact and rerun consumer tests |

Helpful investigation order:

1. Was the stub artifact actually loaded?
2. Does the stub HTTP listener exist, and where is it listening?
3. Which network is the consumer in, and can it reach that host/port?
4. Is the HTTP/HTTPS scheme right?
5. Do the HTTP path, headers, and body matchers align?
6. Does the consumer assert business behavior or only HTTP status 200?

## 16. Safety When Exposing Stubs to Calling Apps

Standalone stubs can contain synthetic data, sample errors, and management APIs. Recommendations:

- Open ports only within internal/CI networks whenever possible; never expose management endpoints unnecessarily to the internet.
- Never place real emails, passwords, tokens, or production data in stub responses/headers.
- Never write artifact repository credentials into URL configs or logs.
- Keep stub artifacts version-pinned with traceable metadata.
- Never let CI jobs share a mutable runner without isolation.
- Clean up containers/processes after tests so ports are not left occupied on subsequent runs.
- When using TLS, configure proper test truststores/certificates; never disable TLS validation just to get a 200 response.

An internal URL is not automatically secret, but URLs carrying tokens, management addresses, request payloads, or sensitive metadata may need log and sharing controls.

## 17. CI: Exposing URLs Must Connect the Chain of Evidence

~~~mermaid
flowchart TD
    A["Review Groovy/YAML contract"] --> B["Generate producer tests"]
    B --> C{"Did producer tests really PASS?"}
    C -->|No| X["BLOCK"]
    C -->|Yes| D["Build and publish stub artifact"]
    D --> E["Start standalone stub runner"]
    E --> F["Obtain real host + stub HTTP port"]
    F --> G["Inject base URL into consumer"]
    G --> H["Readiness check with contract request"]
    H --> I{"HTTP response correct?"}
    I -->|No| X
    I -->|Yes| J["Consumer integration tests"]
    J --> K{"Assertions PASS?"}
    K -->|No| X
    K -->|Yes| L["Archive evidence and evaluate rollout"]
~~~

Illustrative CI record:

~~~yaml
# Designed by the project, not default SCC output.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
stub_artifact: "com.example.orders:order-service:1.4.2:stubs"
runner_mode: standalone
runner_management_port: 8750
stub_http_port: 8090
consumer_runtime: same-host
consumer_base_url: "http://localhost:8090"
stub_readiness: PASS
generated_producer_tests: PASS
consumer_stub_tests: PASS
~~~

Do not record `stub_readiness: PASS` manually. CI must send a request with the exact method/path and verify the response. Likewise, a consumer PASS against **stub version 1.4.2** does not prove compatibility with producer **1.5.0** unless tested against the new stub from that build.

## 18. Hands-On Exercises

### Exercise A — Distinguishing Management and Stub Ports

The standalone runner opens management on `8750` and the Order stub on `8090`. Checkout calls `http://localhost:8750/api/orders/ORD-1001` and gets 404.

**Task:** determine the right URL and explain why the management port is not the HTTP stub port.

**Hint:** on the same machine, use `http://localhost:8090/api/orders/ORD-1001`.

### Exercise B — Dynamic Port and Client Config

JUnit creates `WireMockServer` with `dynamicPort()`; `application-test.yml` hardcodes port `8090`.

**Task:** propose how to pass the dynamic port before the client uses the URL.

**Hint:** publish the URL via `@DynamicPropertySource` or an appropriate lifecycle fixture.

### Exercise C — Docker Networking

A WireMock container listens on 8090; Compose publishes `18090:8090`. One client runs on the host, while another runs inside a Checkout container.

**Task:** provide both base URLs.

**Hint:** the host uses `http://localhost:18090`, and the Checkout container uses `http://order-stub:8090`.

### Exercise D — Readiness

The runner process is alive but still downloading the artifact from the Maven repository. Checkout tests launch immediately and fail with 404/Connection refused.

**Task:** design a readiness check before consumer tests run.

**Hint:** wait until the stub returns the expected response for a contract request, with a finite timeout.

### Exercise E — Reverse Proxy

The proxy exposes `https://stubs.test.internal/order-stub/api/orders/ORD-1001`; WireMock only knows the mapping `/api/orders/ORD-1001`.

**Task:** explain why 404 can occur and how to verify path rewriting.

**Hint:** the proxy must strip the `/order-stub` prefix, or the mapping must be designed for the actual forwarded path.

### Exercise F — Stale Stub and Breaking Change

Order Service `1.5.0` renames `status` to `paymentStatus`, yet Checkout still runs via the standalone runner with artifact `1.4.2:stubs` and PASSES.

**Task:** is this sufficient evidence of backward compatibility?

**Hint:** no. You need producer tests and stub artifact `1.5.0` from the same contract revision, then run the Checkout version under evaluation against that exact artifact.

## 19. Port and URL Exposure Checklist

- [ ] Selected the right stub artifact `groupId:artifactId:version:classifier`.
- [ ] Stub JAR downloaded successfully and contains mappings for the expected contracts.
- [ ] Runner management port and stub HTTP port are clearly separated.
- [ ] URLs use the proper **scheme://host:port** for the consumer's location.
- [ ] Dynamic ports are passed to the consumer before tests make calls.
- [ ] With Docker, internal ports and published host ports are clearly distinguished.
- [ ] `localhost` is used only when the stub shares the consumer's network namespace.
- [ ] With Kubernetes, Service/Ingress routing is used instead of hardcoded Pod IPs.
- [ ] With proxies, path rewriting has been verified.
- [ ] Consumer clients receive the base URL via configuration rather than hardcoding it in business code.
- [ ] If using discovery, service IDs and `ServiceInstance` entries point to the stub.
- [ ] If using HTTPS, listeners, truststores, and hostnames are configured properly without trust-all hacks.
- [ ] Readiness checks send real contract requests rather than checking only PIDs or management health.
- [ ] Tests include assertions on responses and consumer business logic.
- [ ] Consumer CI never accidentally calls staging/production.
- [ ] CI validates generated producer tests before trusting stub artifacts.
- [ ] Consumers test against the stub artifact version matching the producer build under evaluation.
- [ ] Ports, artifacts, contract revisions, and test reports are recorded for traceability.
- [ ] Stub processes/containers are cleaned up and isolated after tests.

**Remember:** exposing a standalone stub is not just "opening a port." You must know **which artifact was loaded**, **which HTTP listener is serving the mappings**, and **which host and port the consumer can actually reach**, then inject the exact **base URL** into the client. Only when producer tests, stub readiness, and consumer assertions verify the matching revision/version together do CI results meaningfully detect incompatible API changes.
