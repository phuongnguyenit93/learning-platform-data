# Retrieving Dynamically Allocated Stub Ports or URLs

A consumer test using **Spring Cloud Contract Stub Runner** typically needs to call a producer's HTTP stub. If every developer, CI job, or test suite hardcodes `http://localhost:8089`, parallel runs can collide on ports, tests can hit the wrong stub version, or connection errors can occur even when the contract is completely valid. **Dynamic port allocation** lets Stub Runner choose an available port; the consumer test's job is to **look up the actual allocated URL or port**, then pass that address into the HTTP client code under test.

This lesson belongs to the **Stub Runner** chapter of the **SPRING_CLOUD_CONTRACT** module. Spring Cloud Contract uses Groovy/YAML DSL to define HTTP or messaging behavior, generates producer tests, packages and publishes stubs, and lets consumers run tests via Stub Runner in CI. The focus here is **avoiding hardcoded HTTP stub ports**, using APIs such as `StubFinder` or `@StubRunnerPort`, handling initialization lifecycles properly, and distinguishing **fetching artifacts from a repository** from **the stub server address used to send requests**.

## 1. Why should Stub Runner use dynamic ports?

Suppose **Order Service** (producer) publishes a stub artifact for **Billing Service** (consumer). An older test hardcodes:

~~~yaml
orders:
  base-url: http://localhost:8089
~~~

and points the HTTP client to that address. It only works if **the exact stub under test** happened to start on **exact port 8089**. Situations that commonly break this assumption:

| Situation | When hardcoding port | When retrieving dynamic address from Stub Runner |
| --- | --- | --- |
| Two CI jobs on the same host | Can collide on port, failing with `Address already in use`. | Each run can be assigned its own port. |
| Two producer stubs in one test | Risk mixing up Order Service and Customer Service addresses. | Look up each URL separately by stub coordinates. |
| Running multiple tests in parallel | Tests can connect to the wrong stub instance. | Each test/context uses its own instance address. |
| Changing port ranges in CI | Must edit hardcoded client configuration. | Tests read the actual port, independent of any fixed number. |
| Local and CI environments differ | `localhost:8089` may be unavailable. | Look up URL and resolve hostname within the active execution environment. |
| Stub has not started yet | HTTP client fails with connection refused that is hard to diagnose. | Lookup APIs and Stub Runner logs distinguish startup errors from mismatches. |

**A dynamic port does not change the HTTP contract.** The contract remains `GET /api/orders/42` with the agreed response. The address `http://localhost:NNNN` is merely the **test route** to that WireMock stub instance.

## 2. Distinguishing artifact, stub instance, port, and URL

Four concepts must be distinguished:

| Concept | Example | Meaning |
| --- | --- | --- |
| **Stub artifact** | `com.acme:order-service:1.0.0:stubs` | Maven coordinates identifying the contract/stub bundle packaged by the producer. |
| **Stub instance** | WireMock running from that artifact inside a test context | Process/server simulating the HTTP producer. |
| **Listening port** | `12543` | Actual port number chosen by Stub Runner at startup time. |
| **Base URL** | `http://localhost:12543` | Scheme + host + port for the HTTP client to send requests. |

An artifact **does not carry a fixed HTTP port**. The exact same `order-service-1.0.0-stubs.jar` can run on different ports across two test runs. Therefore, never bake a port number from a previous run into source code or treat it as part of the contract.

If an API client only accepts a **port**, you can look up the port. If the client accepts a **full address**, prefer retrieving the **base URL** because it carries both scheme and hostname without forcing every environment to be `localhost`.

~~~mermaid
flowchart TD
    A["Producer verification passes"] --> B["Publish order-service:1.0.0:stubs"]
    B --> C["Consumer test instructs Stub Runner to load artifact"]
    C --> D["Stub Runner starts HTTP stub on an available port"]
    D --> E["StubFinder / @StubRunnerPort looks up actual address"]
    E --> F["Configure consumer's OrderClient"]
    F --> G["Send HTTP request through real client code"]
    G --> H["Stub returns response per contract"]
    H --> I["Consumer test asserts processing outcome"]
~~~

**Ordering matters:** only look up the address **after** Stub Runner has created the stub instance for the test context. If you construct and configure the HTTP client too early with a dummy URL, Stub Runner starting later will not automatically update the base URL already held by the client.

## 3. Sample HTTP contract needed before running Stub Runner

We use a simple Order Service contract stored at `src/test/resources/contracts/orders/get_paid_order.groovy` in the producer:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service returns paid order'

    request {
        method 'GET'
        url '/api/orders/42'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(id: 42, status: 'PAID')
    }
}
~~~

This contract describes **HTTP behavior**, containing no `8089` or `12543` port. The Contract Verifier plugin generates producer tests, checks the real Order Service, and packages the mapping into the `stubs` artifact.

If the project uses YAML DSL, the same behavior can be expressed as:

~~~yaml
description: Order Service returns paid order
request:
  method: GET
  url: /api/orders/42
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Keep **only one active contract version** for this scenario in the build; do not load equivalent Groovy and YAML files simultaneously and generate duplicate tests/mappings.

On a Maven producer configured with Contract Verifier, reference commands:

~~~shell
mvn clean verify
mvn install
~~~

The first command must genuinely run **generated producer tests**; the second installs the `stubs` artifact into local Maven for consumer tests running in `LOCAL` mode. In real pipelines, configuration may vary to avoid repeating lifecycle phases. Only publish trustworthy stubs after producer verification passes.

## 4. Letting Stub Runner choose a port automatically

In the Billing Service project, add the `spring-cloud-starter-contract-stub-runner` test dependency with a version compatible with your Spring Boot/Spring Cloud versions. With JUnit 5 and Spring Boot Test, configure:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {
    // Test body will be added in subsequent sections.
}
~~~

The `ids` string has components:

~~~text
groupId:artifactId:version:classifier[:port]
com.acme:order-service:1.0.0:stubs
~~~

This declaration **does not request a specific port** at the end of the coordinates; Stub Runner can allocate an available port per configuration. Conversely, an example like:

~~~java
ids = "com.acme:order-service:1.0.0:stubs:8089"
~~~

means **fixing port 8089** for that instance. Specifying a static port is handy in simple scenarios, yet usually unsuitable when avoiding collisions across multiple test processes.

**Version warning:** coordinate syntax and port-selection rules belong to the Spring Cloud Contract API/configuration in use. Inspect startup logs, actual stub addresses, and resolver capabilities in your project version; do not assume **omitting the port** always equals **using port 0** across every API of every framework.

## 5. Preferred approach: looking up base URL with StubFinder

Spring Cloud Contract Stub Runner provides **`StubFinder`** to locate started stubs. Instead of placing `http://localhost:8089` in test code, look up the URL by **groupId and artifactId**.

Test example:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class DynamicStubAddressTest {

    @Autowired
    private StubFinder stubFinder;

    @Test
    void resolvesRunningStubAddress() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        assertThat(url.getProtocol()).isEqualTo("http");
        assertThat(url.getPort()).isPositive();
        assertThat(url.toExternalForm()).startsWith("http://");
    }
}
~~~

**The key element is calling `findStubUrl("com.acme", "order-service")`**. The result is the URL of the **stub instance started by Stub Runner**, not the Maven repository URL hosting the JAR. If the resolver cannot find a matching stub, never silently fall back to `localhost:8089`: that can mask an unloaded artifact error.

Lookup APIs and return types must be verified against the **installed library version**. Common Stub Runner versions offer `findStubUrl` taking group/artifact as well as variants taking Ivy notation; in a real project, use the signature actually present on your classpath. Here, passing two arguments disambiguates producer identity, especially when a test uses multiple artifacts.

### 5.1. When to use URL vs. when to use port?

If the HTTP client accepts a **base URL**, call:

~~~java
String baseUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
).toExternalForm();
~~~

If only the port number is needed, extract it from the URL:

~~~java
int port = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
).getPort();
~~~

However, `port` alone is insufficient if the stub runs on a **different host**, over **HTTPS**, or behind a **proxy**. A full URL fits applications configured via an `orders.base-url` property much better. Avoid concatenating `"http://localhost:" + port` manually when you can use the URL supplied by the resolver.

## 6. Hands-on: testing real client code with a dynamic URL

Obtaining a URL alone does not make a complete **consumer contract test**. We need to **send requests using Billing's actual `OrderClient` code**, catching path-building bugs, JSON parsing bugs, DTO mapping errors, or status handling issues.

A Spring Framework 6.1+ client using `RestClient`:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(RestClient.Builder builder, String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

In the real Billing application, this constructor can be invoked via `@Bean` or a component factory, passing the base URL from environment configuration. In the test, the **exact same client class** is instantiated with the **newly allocated Stub Runner URL**:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    private StubFinder stubFinder;

    @Autowired
    private RestClient.Builder restClientBuilder;

    @Test
    void readsPaidOrderUsingAllocatedStubUrl() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub is unavailable"
        );

        OrderClient client = new OrderClient(
            restClientBuilder, stubUrl.toExternalForm()
        );

        OrderClient.OrderDto order = client.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
    }
}
~~~

**Why is this example useful?** The test uses the application's **actual `OrderClient` class**, rather than calling WireMock with a standalone test-only HTTP client that bypasses Billing's logic. The address is supplied **after** Stub Runner starts, so no port guessing is needed.

This is a **conditional example**: it requires Spring Boot Test, Spring Cloud Contract Stub Runner, AssertJ, `RestClient`, and a `RestClient.Builder` provided by Spring Boot. Before running the test, the producer must install or publish the corresponding stub JAR. If your app uses `WebClient` or `RestTemplate`, the principle stays identical: create or configure the **real client** using the resolved base URL.

## 7. Using @StubRunnerPort when only the port number is needed

In many Spring Cloud Contract versions, the **`@StubRunnerPort`** annotation supports injecting a specific stub's port into a test. Usage concept:

~~~java
import org.springframework.cloud.contract.stubrunner.StubRunnerPort;

@StubRunnerPort("com.acme:order-service")
int orderServicePort;
~~~

You can then configure the client:

~~~java
String localBaseUrl = "http://localhost:" + orderServicePort;
~~~

**Choose the lookup key matching your installed version.** Some identifier forms use group/artifact, while some APIs support other forms; annotation usage/package and Spring Test injection support must be verified against generated metadata or classes on your classpath. If `@StubRunnerPort` does not fit your setup, **`StubFinder.findStubUrl(...)` is a clearer way** to identify the artifact and retrieve the URL at once.

**Limitation of port-only:** building `localhost` from a port only works when the HTTP stub actually listens on the **loopback of the same execution environment**. Inside containers, `localhost` within the consumer container is **not** the CI host or another container. In that setup, you need a URL with a hostname reachable by the client.

## 8. Spring Test lifecycle: avoid configuring base URL too early

This trap matters even more than choosing an API. If `OrderClient` is created along with the Spring application context using:

~~~java
@Value("${orders.base-url}")
String baseUrl;
~~~

then `orders.base-url` must already be right **before the bean is created**. Yet dynamic Stub Runner addresses are usually only known **after stubs have started in the test context**. You cannot arbitrarily add `@DynamicPropertySource` and access an unready `@Autowired StubFinder` instance from a static method; that has no guaranteed initialization order.

Sound options:

1. **Inject `StubFinder` into the test**, then instantiate the **real client code** with the retrieved URL as in Section 6. This is the simplest and most testable approach when the client constructor takes a base URL.
2. If the consumer requires a **Spring-managed `OrderClient` bean**, design a bean/factory in the test context **depending on `StubFinder`** so the client is built once the resolver holds a URL; verify initialization ordering in your framework version.
3. With frameworks offering official Stub Runner service discovery or property integration, you can reference **properties exported by Stub Runner** to inject the address; verify exact property names and when they become available instead of inventing keys and assuming they exist.
4. For tests hitting an **out-of-process** stub server, supply the base URL from CI/test config once the server is ready, rather than assuming a local `StubFinder` bean.

**Do not:** initialize `OrderClient` with `http://localhost:8089` upfront and expect mutating a test's `baseUrl` field later to update requests on an already-configured client. Most HTTP clients capture base URL settings at creation time; either recreate the client or use an abstraction designed to read dynamic endpoints intentionally.

### 8.1. Avoid global RestAssured.baseURI/port during parallel runs

Some tests write:

~~~java
RestAssured.baseURI = "http://localhost";
RestAssured.port = orderServicePort;
~~~

This is **shared static configuration** that easily collides when multiple test classes mutate `RestAssured.port` concurrently. If using Rest Assured, prefer setting base URI on a **per-test request specification**, or instantiate independent clients so each test binds to its own instance.

Similarly, never store a base URL in a shared static variable across contexts if tests can run across different workers/ports.

## 9. When multiple producer stubs run in the same test

Billing may call both **Order Service** and **Customer Service**. Configure Stub Runner with both artifacts:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.0.0:stubs",
        "com.acme:customer-service:2.3.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Look up addresses **per artifact**:

~~~java
URL ordersUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
);
URL customersUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "customer-service")
);

OrderClient orders = new OrderClient(
    restClientBuilder, ordersUrl.toExternalForm()
);
CustomerClient customers = new CustomerClient(
    restClientBuilder, customersUrl.toExternalForm()
);
~~~

`CustomerClient` here is a hypothetical project-defined client with a constructor accepting `RestClient.Builder` and its corresponding base URL. The rule is **never take one port and share it across two producers**. Stub Runner can start each artifact on a distinct port.

If two producers share an `artifactId` under different `groupId`s, look up by the **group/artifact pair** to avoid ambiguity. If one test simultaneously loads two **different versions of the same group/artifact**, verify multi-version resolution support and exact identification in your library version; do not assume a group/artifact-only lookup can distinguish both.

## 10. LOCAL, REMOTE, and stub address: two different kinds of "remote"

In `@AutoConfigureStubRunner`, configuring:

~~~java
stubsMode = StubRunnerProperties.StubsMode.LOCAL
~~~

typically means **finding stub artifacts in local Maven**. Whereas:

~~~java
stubsMode = StubRunnerProperties.StubsMode.REMOTE
~~~

typically means **downloading stub artifacts from a configured Maven repository**. After downloading, Stub Runner can still **start HTTP WireMock locally on the test host**, and you still **look up the dynamic port** the same way.

| Question | `LOCAL` | `REMOTE` |
| --- | --- | --- |
| Where is the `stubs` artifact fetched from? | Local Maven repository. | Remote Maven repository. |
| Do HTTP requests go to the Maven repository? | **No.** | **No.** |
| Can the HTTP stub server run in the local test process? | Yes. | Yes. |
| Can the HTTP stub port be dynamic? | Yes. | Yes. |
| What does the consumer use to find the URL? | `StubFinder` or equivalent API. | `StubFinder` or equivalent API after loading stubs. |

Example repository configuration in a test:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/maven-releases"
)
~~~

The repository address above is **illustrative**, not a real URL. Repository names, credentials, and versions are managed by CI. **Never use `repositoryRoot` as the HTTP base URL of `OrderClient`**: the repository serves Maven artifacts, not the `GET /api/orders/42` interface.

### 10.1. Stub Runner Server on another machine is a separate story

Spring Cloud Contract can also operate **Stub Runner Server** or start stubs outside the consumer test process. In that case, the stub address might be `http://stub-host:PORT` rather than `localhost`. Never infer a hostname from a **port number**; take the address published by the service or configure the right host/port in CI. In containers, verify both **listening address** and **client-reachable address**, as NAT/port mappings may differ.

## 11. Dynamic ports and containers / parallel CI

Common environments:

| Environment | Point to watch |
| --- | --- |
| Developer laptop | Another app might occupy 8089; use dynamic ports to avoid collisions. |
| CI runner building multiple modules | Each job loads different artifacts; do not share fixed ports or static fields. |
| Multiple CI processes on one host | Use the port allocated by Stub Runner within each process; never pass process A's port to B. |
| Consumer running in a Docker container | `localhost` is the **consumer container's** loopback, not necessarily reaching Stub Runner on the host. |
| Stub Runner running in its own container | Use container DNS/service name and properly published/routed ports. |
| Kubernetes test namespace | Can use Service DNS/URL instead of localhost port; wait for readiness and check network policies. |

**Dynamic ports do not fix all network issues.** If the HTTP client is not in the same network namespace as Stub Runner, `http://localhost:12543` cannot reach the stub even if the server is ready on the host. You then need a **routable address** in the active environment; avoid randomly changing port numbers "just to try your luck."

### 11.1. Should you sleep to wait for Stub Runner?

In proper Spring Test integration, stub creation belongs to `@AutoConfigureStubRunner`'s lifecycle. Tests should look up the URL and send requests once the context is initialized; if the stub fails to start, inspect the startup error. Using `Thread.sleep(3000)` neither proves the server is ready nor keeps CI fast and deterministic.

If the setup runs a stub server outside the Spring test lifecycle, implement a **readiness check with a bounded timeout** and send requests to target endpoints only after the server reports ready. Never substitute a fixed sleep for readiness verification.

## 12. Difference between "stub not found" and stub HTTP 404

Three commonly confused errors:

| Symptom | Possible meaning | Action |
| --- | --- | --- |
| `StubFinder` cannot find URL | Artifact not loaded, wrong coordinates, Stub Runner failed to start instance. | Check `ids`, classifier/version, local/remote repo, and startup logs. |
| `Connection refused` calling base URL | No server listening at host/port or client in wrong network namespace. | Check actual URL, readiness, firewall/container mapping. |
| HTTP `404` from a running WireMock server | Request does not match any mapping **or** mapping intentionally returns a business 404. | Compare method/path/headers/body against generated mappings; if testing business errors, assert error body/code. |

For example, the client calls:

~~~http
GET /api/orders/43
~~~

while the contract only defines `GET /api/orders/42`. The stub may return 404 because **no mapping exists**, not because real Order Service checked the database and concluded order 43 does not exist. To test `ORDER_NOT_FOUND` handling, add a dedicated error contract and assertions distinguishing it from no-match.

**Do not try to solve a 404 mapping mismatch by changing ports** once `StubFinder` returned a valid URL and the HTTP server responded. At that point, inspect the actual request and the mappings generated in the artifact.

## 13. Inspecting artifacts and logs when URL resolution fails

A systematic investigation workflow:

1. **Producer verification:** were Groovy/YAML contracts picked up by the plugin and did generated producer tests execute?
2. **Stub artifact:** did the producer build a JAR with classifier `stubs` for the exact `groupId:artifactId:version`?
3. **Storage location:** for `LOCAL`, was `mvn install` run into the test environment's active local Maven repo? For `REMOTE`, was it published to the repository with read permissions?
4. **Stub Runner startup:** what artifacts did logs find, what mappings were loaded, and which WireMock instance started?
5. **URL lookup:** did `StubFinder.findStubUrl(groupId, artifactId)` return the expected URL for the target artifact?
6. **HTTP reachability:** is the HTTP client in the same network namespace or does it need another hostname?
7. **Matching:** send method/path/body matching the contract and assert both status and business payload.

Avoid assuming JARs sit under identical `target`/`build` folders across every project; artifact paths depend on Maven/Gradle and build config. The invariant facts to verify are **Maven coordinates, classifier `stubs`, and version**.

### 13.1. Do not hand-edit generated mappings to "fix" URLs

The HTTP server address allocated by Stub Runner **does not belong in contract request matchers**. When a client fails to connect because the port changed, **fix client configuration**, never change DSL `url '/api/orders/42'` to `url 'http://localhost:12543/api/orders/42'`. The DSL specifies path/request semantics, whereas host/port belong to the test environment.

If a mapping fails to match a request, fix the contract or client code at the source and regenerate the artifact after producer verification. Hand-editing mapping files inside a JAR and republishing breaks the shared single source of truth between producer tests and stubs.

## 14. When should you still pin a fixed port?

Dynamic allocation is usually best for developers and parallel CI, though a fixed port can make sense when:

- You run a **manually managed Stub Runner Server** locally with a known port and explicit port management.
- An external test harness **does not support dynamic address discovery**, while the environment guarantees port exclusivity.
- Debugging tools or reverse proxies are statically configured to point at a standalone stub server.

When choosing a fixed port, document **who owns the port, its lifetime, collision safeguards, and readiness checks**. Do not make fixed ports the default for all consumer tests just because `localhost:8089` looks easy to write.

For standard Spring Boot tests, letting Stub Runner pick a port and looking up the URL with `StubFinder` is far less environment-coupled and scales cleanly.

## 15. Bringing dynamic URLs into CI to guard compatibility

A reliable pipeline can split into two branches joined by artifact versions:

~~~mermaid
flowchart TD
    A["Producer modifies API/contract"] --> B["Contract Verifier generates producer tests"]
    B --> C{"Producer verification passes?"}
    C -->|No| D["Block publish"]
    C -->|Yes| E["Build and publish order-service:version:stubs"]
    E --> F["Consumer CI downloads pinned artifact version"]
    F --> G["Stub Runner starts WireMock on available port"]
    G --> H["StubFinder returns instance base URL"]
    H --> I["OrderClient uses dynamic URL"]
    I --> J["Test status/body/errors per contract"]
~~~

CI checklist:

1. **Pin producer stub artifact versions**; do not rely on an implicitly shifting "latest."
2. **Do not use fixed ports** when multiple jobs can run inside the same network namespace.
3. **Do not hardcode `localhost`** if consumer and stub run in containers on different networks.
4. **Look up the address after startup** and configure the client with that URL, not a value remembered from a previous run.
5. **Keep tests genuinely exercising client code**; do not replace them with a raw GET directly to the stub just to confirm WireMock runs.
6. **Test negative paths too** (such as business 404) using dedicated mappings and error payloads to avoid false passes.
7. **Block stub publication when producer verification fails**; green consumer tests against unverified stubs provide zero guarantee about the real producer.

When testing messaging contracts simultaneously, remember that **Stub Runner can emit messages without needing an HTTP WireMock port for that scenario**. Dynamic ports in this lesson apply primarily to **HTTP stubs**; messaging requires binder/adapter/destination configuration and can use `StubTrigger` instead of HTTP URLs.

## 16. Practice: removing fixed ports from Billing Service

Given an Order Service producer that published `com.acme:order-service:1.0.0:stubs` and a Billing Service consumer:

1. **Create an HTTP contract** `GET /api/orders/42` → `200` with `{"id":42,"status":"PAID"}` using Groovy or YAML DSL.
2. **Run generated producer tests** to prove real Order Service satisfies the contract, then install or publish the `stubs` artifact.
3. **Create a real `OrderClient`** with a constructor taking a base URL instead of hardcoding `http://localhost:8089`.
4. **Configure `@AutoConfigureStubRunner`** on the consumer using `ids` **without a trailing port**; select `LOCAL` once the artifact is installed in local Maven.
5. **Inject `StubFinder`**, and call `findStubUrl("com.acme", "order-service")` after the test context initializes.
6. **Call `OrderClient` with the resolved URL**, asserting `id=42` and `status=PAID`. Do not merely assert that the URL has a positive port.
7. **Run two test suites concurrently** where supported by your machine/CI; verify neither contends for `8089` and each client hits its own stub.
8. **Add a Customer Service stub**, look up both URLs separately by group/artifact, and verify Order Service's port is not reused by mistake.
9. **Switch to `REMOTE`** after the producer publishes the artifact to a repository, keeping URL lookup logic unchanged, and confirm the repository URL **differs from** the HTTP stub URL.
10. **Introduce intentional failures**: change `artifactId` in `ids` or call an out-of-contract path; distinguish `StubFinder` errors, connection refused, and no-match 404, then restore.
11. **Test on containers/CI**, documenting whether client and stub share a network namespace; if not, configure a reachable hostname/service.

**Passing criteria:** the exact same consumer test runs cleanly when WireMock receives **different port numbers** without editing source code, still executes **real HTTP client code**, receives contract-compliant responses, and distinguishes **artifact resolution failures**, **connection failures**, and **unmatched request errors**.

## 17. Self-check questions

1. Is a stub's HTTP port stored inside `order-service-1.0.0-stubs.jar` or the `GET /api/orders/42` contract?
2. After removing `:8089` from `ids`, why must the HTTP client stop calling `localhost:8089`?
3. Does `StubFinder.findStubUrl(...)` return the **artifact repository** address or the **running stub server** address?
4. Why is retrieving the full URL usually better than retrieving only the port number?
5. When is `@StubRunnerPort` appropriate, and what is the limitation of assembling `localhost` manually?
6. Why cannot a static `@DynamicPropertySource` method arbitrarily access an uncreated `@Autowired StubFinder` bean?
7. When two producer stubs run concurrently, why must you look up URLs by producer identity?
8. Does `StubsMode.REMOTE` mean all HTTP requests go to the Maven repository or a remote stub host by default?
9. When does WireMock return 404 due to an unmatched request, and how does that differ from a business 404 error?
10. How can you verify dynamic ports are used properly while still protecting `OrderClient` logic?
11. Why might `localhost` inside a consumer container fail to reach a stub on the CI host?
12. Why are green consumer tests against stubs insufficient to skip generated producer verification before publishing?

**Remember:** **An HTTP stub's port is a runtime environment detail, not part of the producer–consumer contract**. Let Stub Runner allocate addresses per configuration, use **`StubFinder`** or an equivalent mechanism to retrieve **URL/port after startup**, and pass that address to **real client code**. Clearly separate `LOCAL/REMOTE` Maven repositories from the running HTTP stub server, avoid hardcoded ports in parallel CI, and verify both request matching and business responses. That keeps consumer contract tests reproducible and able to detect incompatible API changes without depending on a fixed port number.
