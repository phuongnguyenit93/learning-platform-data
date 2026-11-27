# Prerequisites and Learning Sequence of the Module

This lesson belongs to the **Overview** chapter of the **SPRING_CLOUD_CORE** module. The module's goal is to understand the core foundations of Spring Cloud in distributed systems: **Spring Cloud Commons**, **Spring Cloud Context**, externalized configuration, compatibility with **Spring Boot**, refresh mechanisms, discovery, service registries, inter-service communication, and testing and operating shared abstractions.

To learn effectively, distinguish two layers: **Spring Boot** helps build and run each individual application, whereas **Spring Cloud** adds abstractions and integration capabilities for multi-service environments. Certain Spring Cloud capabilities appear only when the corresponding dependencies and configuration are added; do not treat all of Spring Cloud as a single component that turns every feature on automatically.

## 1. What Should You Achieve After This Lesson?

After studying this lesson, you will be able to:

1. Self-assess whether you have sufficient foundations in Java, Spring Boot, HTTP, and application configuration to begin the module.
2. Select a compatible **JDK – Spring Boot – Spring Cloud release train** combination and diagnose library version mismatches.
3. Explain the responsibilities of Spring Cloud Commons and Spring Cloud Context using concrete examples.
4. Sketch how one service discovers another, selects an instance, and executes an HTTP call.
5. Plan hands-on practice progressing from local configuration to discovery, refresh, testing, and runtime observability.
6. Define completion criteria for each learning stage instead of merely finishing the reading.

## 2. Prerequisites

| Knowledge area | What to know before starting the module | How to self-check |
| --- | --- | --- |
| **Java and build tools** | Classes, interfaces, conceptual dependency injection; Maven or Gradle; environment variables; a JDK compatible with the chosen Spring Boot version. | Create and run a Java application; inspect the dependency tree; explain why a JAR is on the classpath. |
| **Spring Framework** | `ApplicationContext`, beans, `@Configuration`, `@Bean`, `@Component`, `@Autowired` or constructor injection; basic lifecycle and proxies. | Explain when beans are created and why calling through a proxy can differ from a direct call. |
| **Spring Boot** | Starters, auto-configuration, `application.yml`, profiles, `@ConfigurationProperties`, Actuator, and the application startup process. | Run a simple API with two profiles; override configuration via environment variables. |
| **HTTP and networking** | URLs, hostnames, ports, DNS, HTTP methods/statuses, timeouts, connection errors, JSON; client/server principles. | Call an endpoint with `curl` and distinguish 4xx errors, 5xx errors, and connection failures. |
| **Distributed systems** | A service has multiple instances; instances can fail or change addresses; network calls have latency and can fail. | Explain why `localhost` inside each container does not refer to the same machine. |
| **Testing and operations** | Unit/integration tests, logs, health checks, secret configuration variables, principle of least privilege. | Write a simple Spring Boot test and check application status using Actuator. |

You are **not required** to know Eureka, Consul, Kubernetes, Spring Cloud Config Server, or API Gateway beforehand. Those are specific products, implementations, or specialized components you can learn after understanding the shared abstractions. Docker is helpful for practicing multi-instance setups, though not a prerequisite to get started.

### 15–30 Minute Entry Check

Create a Spring Boot application with a `GET /greeting` endpoint. Configure the message in `application.yml` with a default value, then override it using an environment variable. Run the application on two different ports, call both with `curl`, and observe the responses.

If you cannot do this yet, review Spring Boot and externalized configuration first. If you can do it but cannot explain `ApplicationContext`, review beans, scopes, and how Spring manages objects; this knowledge is especially necessary when encountering `@RefreshScope`.

## 3. Concept Map Before Starting

The main building blocks relate to one another as follows:

~~~mermaid
flowchart LR
    C["Externalized configuration"] --> CTX["Spring ApplicationContext"]
    CTX --> A["order-service"]
    REG["Service registry or static config"] --> DISC["DiscoveryClient"]
    DISC --> LB["LoadBalancer"]
    A --> LB
    LB --> B1["inventory-service: instance A"]
    LB --> B2["inventory-service: instance B"]
    OBS["Logs, health, metrics"] -.-> A
    OBS -.-> B1
    OBS -.-> B2
~~~

The diagram is a **conceptual model**; it does not assert that Spring Cloud starts all of these components by default.

- **Spring Cloud Commons** provides shared abstractions such as `DiscoveryClient`, `ServiceInstance`, `ServiceRegistry`, and load-balancing integration mechanisms. Actual providers may vary.
- **Spring Cloud Context** provides capabilities related to the application context and configuration, including refresh scope. Startup configuration loading and runtime configuration refreshing must be treated as two separate concerns.
- **Discovery** answers the question “which instances of service X currently exist?”. A **service registry** is the mechanism managing instance registration info when a corresponding registry is used. Not every `DiscoveryClient` is backed by a real registry.
- **Load balancing** picks an instance from the available instance set; it does not guarantee timeouts, retries, circuit breakers, or business error handling when the target service fails.
- **Service communication** is the actual call—such as HTTP via `RestClient`, `WebClient`, or a matching client—typically using a logical service name instead of hardcoding a single instance address.

Understanding these boundaries prevents confusing abstractions, implementations, and runtime behavior.

## 4. Recommended Learning Sequence

Follow the order from top to bottom, as each stage prepares you for the next.

| Stage | Topic | Questions you must be able to answer | Hands-on deliverable |
| --- | --- | --- | --- |
| **0** | Spring Boot foundations and tooling | How does configuration enter an app? Where are beans created? | A running REST API whose port and message can be changed via the environment. |
| **1** | Version compatibility and dependency management | How are Spring Boot and Spring Cloud release trains paired? | A clean-building project whose dependency tree has no arbitrarily mixed Cloud versions. |
| **2** | Spring Cloud Commons | What do `DiscoveryClient`, `ServiceInstance`, and `ServiceRegistry` represent? | Read the instance list for a service ID from a simple discovery source. |
| **3** | Externalized config and Spring Cloud Context | Where do config values come from, when are they read, and when are they updated? | Change config per profile/environment; explain how refresh works and its limits. |
| **4** | Discovery and service registration | How does finding instances differ from registering instances? What happens when an instance disappears? | Two services; the caller locates instances by logical name. |
| **5** | Service communication and load balancing | What path does a request take from service ID to a specific instance? | Make HTTP calls by service name; observe timeouts and unavailable instances. |
| **6** | Testing, observability, and operations | How do you verify config, discovery, and failure behavior? | Automated tests, health endpoints, and logs sufficient to trace requests. |
| **7** | Capstone hands-on exercise | How do you assemble the abstractions without hardcoding a specific registry? | A mini-system with run instructions and a table of test results. |

You can study HTTP, Spring Boot, and testing skills in parallel, but **do not jump into refresh or load balancing before understanding bean scopes and discovery**.

## 5. Stages 0–1: Environment Setup and Locking Versions

### 5.1. Minimal setup

You need a JDK supported by your chosen Spring Boot version, an IDE or editor, Maven/Gradle, a terminal, and an HTTP client tool. Verify:

~~~bash
java -version
./mvnw -version
./mvnw dependency:tree
~~~

The `./mvnw` commands apply to Maven projects with the Maven Wrapper; on Windows you can use `mvnw.cmd`. If a project uses Gradle, run `./gradlew dependencies` and equivalent tasks. Verify builds succeed with the JDK version actually used in CI, not only on your personal machine.

### 5.2. Why must compatibility be checked?

Spring Cloud is published in **release trains**, each managing a set of Spring Cloud module versions and compatible only with specific Spring Boot lines. Finding a dependency in Maven Central does not prove an arbitrary pairing of Spring Boot and Spring Cloud will run properly.

Version selection workflow:

1. Choose a Spring Boot version accepted by the project, considering Java requirements and support policies.
2. Consult Spring Cloud's **official compatibility matrix** to pick a matching release train; read release notes when upgrading.
3. Use Spring Boot's dependency management and the **Spring Cloud BOM**. Avoid pinning individual Cloud module versions unless there is a verified reason.
4. Inspect the dependency tree, run startup tests, and re-test a business flow after changing versions.
5. When hitting compatibility errors, fix version alignment and dependency conflicts before altering application logic.

Example configuring **Cloud version management** in `pom.xml` for a project already managing Spring Boot via its parent/BOM:

~~~xml
<properties>
    <!-- Replace with the right release train per the compatibility matrix -->
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN` is a **placeholder to replace**, not a buildable version. Each capability, such as load balancing or a registry client, still requires its own dependency; the BOM only manages versions and **does not add libraries to the application automatically**.

**Completion milestone:** you can explain how to choose a Boot/Cloud pair, distinguish a BOM from a starter, and have a project that builds and boots tests with the chosen versions.

## 6. Stage 2: Mastering Spring Cloud Commons Before Choosing a Registry Technology

Commons establishes shared contracts so application code depends less on any single service discovery provider. Three abstractions to learn first:

| Abstraction | Responsibility | Notes |
| --- | --- | --- |
| `DiscoveryClient` | Queries known service names and `ServiceInstance` lists. | Can read from a real registry or static configuration; does not guarantee data is always fresh. |
| `ServiceInstance` | Describes an instance: service ID, host, port, URI, metadata (implementation-dependent). | One service ID can map to multiple instances; metadata does not guarantee the instance is healthy. |
| `ServiceRegistry` | Abstraction for registering/deregistering or managing registration status with a matching registry. | Not every environment needs or supports the same registration model. |

In your first practice exercise, you can use **SimpleDiscoveryClient**'s static configuration to learn lookup without installing a registry server:

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

This is illustrative configuration placed in the **caller** application. To run it, the project must include dependencies providing compatible Spring Cloud Commons/discovery; both target processes must also actually listen on the declared ports.

Sample code using the abstraction:

~~~java
@RestController
class DiscoveryLabController {
    private final DiscoveryClient discoveryClient;

    DiscoveryLabController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/lab/instances")
    List<String> inventoryInstances() {
        return discoveryClient.getInstances("inventory-service")
                .stream()
                .map(instance -> instance.getUri().toString())
                .toList();
    }
}
~~~

This example is for learning; internal inspection endpoints should be restricted or removed in production.

Once understood, replace the static discovery source with a suitable implementation such as Eureka, Consul, or a platform integration. When switching providers, review differences in registration, status updates, caching, metadata, and how long it takes to detect disconnected instances.

**Completion milestone:** you can explain why “no instances found” differs from “instance found but HTTP call failed,” and retrieve URI lists from a service ID.

## 7. Stage 3: Externalized Configuration, Spring Cloud Context, and Refresh

### 7.1. Foundations of externalized configuration

Spring Boot provides externalized configuration: config files, profiles, environment variables, command-line arguments, and other property sources can supply values for the same key. **Exact precedence order** depends on source types and startup mode; verify against the documentation for the version in use rather than memorizing one universal order for every case.

Example `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

app:
  greeting: ${APP_GREETING:Hello}
~~~

`APP_GREETING` is used when a matching environment variable exists; otherwise `Hello` is used. For multiple related properties, prefer type-safe binding with `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(String greeting) {}
~~~

Enable registration of the properties class with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(AppProperties.class)`, depending on application structure. Separating configuration from code lets the same build run across environments, though **secrets** should never be stored directly in the repository.

### 7.2. What happens when configuration changes at runtime?

Distinguish carefully:

- **Reading configuration at startup:** beans receive values during creation; editing a file on disk does not automatically change running beans.
- **Updating a property source:** the config source may change, yet existing beans have not necessarily re-read the value.
- **Spring Cloud Context refresh:** provides mechanisms to refresh configuration state and refresh-scoped beans when triggered properly.
- **`@RefreshScope`:** uses a proxy and cache so the target bean can be recreated after the scope is refreshed. It does not mean every bean in the application is recreated or every value changes instantaneously.

Minimal example:

~~~java
@Component
@RefreshScope
class GreetingService {
    private final String greeting;

    GreetingService(@Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    String greeting() {
        return greeting;
    }
}
~~~

Verification sequence: read the initial value → update **the configuration source actually used by the application** → trigger the refresh workflow supported and configured in your version → call the bean again through the proxy to verify the value. Without a mechanism to update the property source or trigger refresh, an unchanged result is expected.

In some dependency combinations, an Actuator endpoint for refresh may be available. Do **not assume this endpoint always exists or is exposed by default**; if used, verify dependencies, exposure settings, authentication, and access permissions. Never leave configuration-mutating endpoints open to arbitrary users.

**Completion milestone:** you can describe when configuration values are read, when a restart is required, when refresh takes effect, and cite one case where refresh does not update a bean as expected.

## 8. Stages 4–5: Discovery, Load Balancing, and Service Communication

Suppose `order-service` needs inventory from `inventory-service`. The manual approach is calling a fixed `http://localhost:8081`. That works while learning HTTP, but becomes inconvenient when running multiple instances, changing ports, or deploying across hosts.

Logical flow in a system with discovery and load balancing:

1. `order-service` sends a request to the **logical service name** `inventory-service`.
2. The discovery client supplies the currently known instances for that service ID.
3. The load balancer picks an instance according to policies and availability supported by the implementation.
4. The HTTP client sends the request to the selected instance's actual URI.
5. The application handles results, timeouts, or errors, deciding on retries/fallbacks per business requirements.

You can practice with Spring Framework's `RestClient` and Spring Cloud LoadBalancer integration **if your chosen release train supports that integration**. Example client configuration:

~~~java
@Configuration
class ClientConfiguration {
    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Once a Spring-managed builder and the appropriate LoadBalancer dependency are present, requests can use the service ID in the URI:

~~~java
String body = loadBalancedRestClientBuilder.build()
        .get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(String.class);
~~~

Here `loadBalancedRestClientBuilder` is the bean injected into the calling class; the snippet illustrates **the call portion**, not a complete standalone compilable class. If your project uses a different release train or HTTP client, use the load-balancing integration documented for that exact version.

Scenarios to test intentionally:

| Scenario | Expected observation | Key takeaway |
| --- | --- | --- |
| Both instances running | Requests succeed; you can observe which instance was chosen if responses/logs identify the source. | Discovery and load balancing are two separate steps. |
| One instance stops | A few requests may fail before discovery/health data updates or the client evicts the instance. | Discovery has lag, caching, and limitations. |
| No instances available | Caller cannot pick a valid target; must handle errors cleanly. | Lookup failure differs from a business 404 from the target service. |
| Instance accepts request but responds slowly | Timeouts may occur; retries should be used only when safe and bounded. | Prevent load amplification; consider idempotency. |
| Misconfigured service ID | Client cannot find the right service even though the registry is healthy. | Logical service names are part of the integration contract. |

**Do not equate** load balancing with a guarantee of availability. A system still needs timeouts, bounded retry strategies, idempotency handling, error observability, and graceful degradation when dependencies fail to respond.

## 9. Stage 6: Testing and Operating the Abstractions

Testing only the happy path is not enough. For Spring Cloud Core, verify at least these four behavioral groups:

| Test group | Examples | Evidence of success |
| --- | --- | --- |
| **Configuration** | Change env vars/profiles; omit a required property; pass a wrong data type. | App picks up the right values or fails fast with diagnosable errors. |
| **Context/refresh** | Change config source, trigger proper refresh, compare before/after responses. | Refresh-scoped beans update on cue; non-refreshable beans are clearly understood. |
| **Discovery/load balancing** | Return 0/1/n instances from a mock discovery source; alter instance URIs. | Client handles present, empty, and changing instance lists properly. |
| **Communication and faults** | Target returns 500, times out, refuses connections, or slows down. | Errors are logged with context, never block indefinitely; retry/fallback behaves properly. |

Suggested layered testing progression:

- **Unit tests** for business logic and rules deciding what to do when HTTP calls fail; mock dependencies at appropriate boundaries.
- **Spring tests / integration tests** for `@ConfigurationProperties` binding, auto-configuration, discovery clients, and real HTTP clients in controlled environments.
- **Smoke tests** across two real services: start up, call endpoints, stop one instance, and verify system behavior.
- **Operational checks** via logs, health/readiness probes, and metrics. Actuator can help, though exposed endpoints depend on configuration; never expose them indiscriminately in production.

Log key fields: service ID, target instance, response duration, error codes, and correlation/trace IDs if tracing is enabled. Never log tokens, passwords, or sensitive data. For inter-service requests, measure p95/p99 latency and error rates instead of relying on a gut feeling that “it works.”

## 10. Stage 7: Capstone Mini-Project

Build a small system consisting of `order-service` and **two instances** of `inventory-service`. All services can run locally on different ports.

**Functional requirements:**

1. `inventory-service` exposes `GET /api/stock/{sku}`, returning the SKU, remaining quantity, and an `instanceId` field to identify which instance handled the request.
2. `order-service` exposes `GET /api/orders/check/{sku}` and calls `inventory-service` by logical service name.
3. Configure instances initially with SimpleDiscoveryClient, then (if feasible) swap in the registry implementation you are studying.
4. Allow customizing a simple business property via externalized configuration.
5. Exercise refresh properly with enabled configuration, checking the difference between regular beans and refresh-scoped beans.
6. Write tests for success, no instances available, HTTP errors, and timeouts.
7. Add health endpoints and logs sufficient to identify which service/instance was responsible on failure.

**Verification script:** make consecutive calls to check service ID resolution; stop one instance; compare logs and responses before/after; edit configuration; observe behavior after refresh; re-run tests. When recording results, note exact libraries/versions, discovery source, timeout settings, and exposed endpoints, because those details directly affect observations.

A concise results table could include:

| Scenario | Expectation | Actual result | Explanation |
| --- | --- | --- | --- |
| Two instances ready | Calls by logical service name succeed | Fill in yourself | How the client selects instances |
| One instance stops | Brief errors/update lag may occur before stabilizing | Fill in yourself | Caching, health, and timeouts |
| No instances found | Error handled cleanly | Fill in yourself | Handling when discovery returns empty |
| Configuration changed | Output updates according to the active mechanism | Fill in yourself | Restart vs. refresh; affected beans |
| Target returns 5xx/timeout | Error and wait bound observed | Fill in yourself | Client error policy |

## 11. Common Mistakes When Getting Started

- **Learning product names before abstractions:** knowing how to run a registry without being able to explain how `DiscoveryClient` differs from `ServiceRegistry`. Practice with SimpleDiscoveryClient first before picking a provider.
- **Copying versions from outdated tutorials:** an example may pair Spring Boot and Spring Cloud versions incompatible with your current environment. Always verify the release train and dependency tree.
- **Confusing editing a YAML file with refresh:** a singleton bean can retain previously read values. Identify the config source, refresh trigger, and bean scope.
- **Thinking finding a URI is enough:** an instance may not be ready or may fail after discovery. Test HTTP/network failure scenarios.
- **Retrying every request:** unbounded retries can cause duplicate transactions or amplify load during an outage. Understand timeouts and idempotency.
- **Opening management endpoints wide for easy demos:** config and operational endpoints can be sensitive; expose only what is genuinely needed and restrict access.

## 12. Module Completion Checklist

You are ready to move on to deeper Spring Cloud topics once you can answer and demonstrate the following:

- [ ] Distinguish Spring Boot, Spring Cloud Commons, and Spring Cloud Context by concrete responsibilities.
- [ ] Select a Spring Cloud release train compatible with your project's Spring Boot and JDK versions.
- [ ] Explain how dependency management BOMs differ from actual dependencies.
- [ ] Use externalized configuration, profiles, and type-safe binding.
- [ ] Explain when beans receive updated configuration and when a refresh or restart is needed.
- [ ] Distinguish discovery, service registration, service instances, and load balancing.
- [ ] Call another service via service ID and handle the case where no instances are found.
- [ ] Test HTTP errors, timeouts, and instance state changes.
- [ ] Maintain basic logs/health/metrics without exposing sensitive management information.
- [ ] Complete the mini-project, recording run steps, tests, and notes on observability limits.

### What Should You Learn Next?

Once the core concepts are solid, expand according to system needs: **Spring Cloud Config** for centralized configuration management; a **discovery provider** suited to your environment; **Spring Cloud Gateway** as an API entry point; resilience mechanisms such as circuit breakers; distributed tracing; or cloud/Kubernetes integrations. These use or build upon the concepts learned here, while each component carries its own configuration, limitations, and version requirements.

**Documentation to consult during practice:** official Spring Boot documentation on externalized configuration and Actuator; Spring Cloud documentation on release trains, compatibility, Commons, Context, and LoadBalancer; and documentation for the discovery provider in use. Always check the exact version you selected rather than mixing configuration from multiple Spring Cloud generations.
