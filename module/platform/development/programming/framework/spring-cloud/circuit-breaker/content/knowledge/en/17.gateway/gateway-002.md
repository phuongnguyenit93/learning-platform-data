# Choosing Integration for Gateway WebFlux and Verifying Version Support

## Starting from the Right Gateway Type

Spring Cloud Gateway has different execution models. This article focuses on **Gateway Server WebFlux**, running on Spring WebFlux, Reactor, and a non-blocking I/O model. In that model, the `CircuitBreaker` route filter uses the reactive API of Spring Cloud Circuit Breaker, namely `ReactiveCircuitBreakerFactory` and `ReactiveCircuitBreaker`.

This is the deciding factor when choosing dependencies. Gateway WebFlux requires a Circuit Breaker provider with reactive integration. If the application uses Resilience4j, the typical choice is the `spring-cloud-starter-circuitbreaker-reactor-resilience4j` starter. The imperative starter `spring-cloud-starter-circuitbreaker-resilience4j` is for synchronous calls and is not a substitute for a reactive provider in a WebFlux filter chain.

Before adding dependencies, identify what your application uses:

| Application type | Execution stack | Circuit Breaker integration to consider |
| --- | --- | --- |
| Spring Cloud Gateway Server WebFlux | WebFlux, Reactor, typically Reactor Netty | Reactive Circuit Breaker provider; for Resilience4j, the Reactor Resilience4j starter. |
| Synchronous Spring MVC service application | Servlet, synchronous Java calls | Imperative Circuit Breaker provider or Resilience4j Spring Boot integration. |
| Spring Cloud Gateway Server Web MVC | Servlet and MVC filter functions | Check Gateway MVC documentation and compatible providers for the release train; do not mechanically apply WebFlux guides. |

Do not infer the Gateway type solely from the project being named Spring Cloud Gateway. Check the actual starter, application type, and route filter API. Mixing `spring-boot-starter-web` with a WebFlux stack unintentionally can cause Spring Boot to select a servlet application type or create unpredictable configuration. Keep Gateway WebFlux purely reactive if that is the chosen architecture.

## Choosing Compatible Starters

For a Gateway WebFlux application using Resilience4j, dependencies typically include Gateway WebFlux and the reactive Circuit Breaker provider. Example for Gateway lines using the traditional aggregate starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
</dependencies>
```

In newer Spring Cloud Gateway lines, Gateway artifacts may be split by server implementation; a WebFlux application may require a dedicated starter such as `spring-cloud-starter-gateway-server-webflux`. Artifact names, packaging, and route configuration namespaces change across major versions/release trains. Therefore, take the dependencies from the documentation page for the exact version in use, and keep the reactive Circuit Breaker starter on the same release train.

Do not add both the imperative and reactive Resilience4j Circuit Breaker starters at the same time just "to be safe." Choosing the right type for the call model helps auto-configuration create the right factory and avoids bringing unnecessary configuration into the context. If the application also has a separate synchronous service, that service can use imperative integration in its own appropriate module; Gateway WebFlux still needs reactive integration.

## Managing Versions with the Spring Cloud BOM

Spring Boot, Spring Cloud Gateway, Spring Cloud Circuit Breaker, and underlying libraries must belong to a compatible combination. Use the Spring Cloud BOM to manage Spring Cloud artifact versions, and use Spring Boot dependency management for foundational libraries such as Spring Framework and Reactor.

Maven example:

```xml
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
```

Declare the BOM version according to the release train published by Spring as compatible with your project's Spring Boot version. Do not pick the latest Gateway version and pair it with an older Spring Boot or Spring Cloud Circuit Breaker line. Also do not override Reactor, Spring Framework, or Resilience4j individually without confirming the compatibility matrix.

Gradle example:

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation "org.springframework.cloud:spring-cloud-starter-gateway"
    implementation "org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j"
}
```

If the release train in use requires a dedicated Gateway WebFlux artifact, swap the Gateway dependency according to that release's documentation. Do not guess artifact names; verify that the dependency exists in the BOM and repository your project uses.

## Checking the Support Matrix Before Implementation

Verify compatibility layers in the following order:

1. **Spring Boot:** determine the Boot version and Java runtime the application uses.
2. **Spring Cloud release train:** choose the train published as compatible with that Boot version.
3. **Gateway implementation:** confirm the project uses Gateway Server WebFlux and pick the right starter/artifact for the release train.
4. **Circuit Breaker provider:** for Resilience4j, choose the Reactor provider starter from the corresponding Spring Cloud line.
5. **Reactor and Resilience4j:** let the BOM manage versions first; override only with good reason and after checking compatibility.

Release trains can change artifacts, packages, property namespaces, and auto-configuration conditions. Therefore, do not use a fixed version table in this article as a substitute for the project's official matrix. Record the actual resolved versions from the dependency graph and cross-check release notes for the exact Gateway, Circuit Breaker, and Spring Boot versions before upgrading.

Some differences to watch out for:

| Component | What to verify |
| --- | --- |
| Gateway starter | Aggregate starter or dedicated WebFlux starter in the current release train. |
| Route properties | Route configuration namespace of the exact Gateway major version; do not assume every line uses the same prefix. |
| Circuit Breaker starter | Whether it provides a `ReactiveCircuitBreakerFactory` compatible with WebFlux or only an imperative factory. |
| Filter factory | Whether the `CircuitBreaker` route filter is registered in the application context by auto-configuration. |
| Resilience4j config | Instance, TimeLimiter, and status code properties supported in the current provider version. |

## Inspecting the Runtime Dependency Graph

After declaring dependencies, inspect the runtime classpath to detect missing modules or version conflicts:

```bash
# Maven
mvn dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

Look for the following groups:

- The corresponding Spring Cloud Gateway WebFlux/server WebFlux.
- Spring WebFlux and Reactor Core.
- Spring Cloud Circuit Breaker core.
- Reactive Resilience4j provider and the Resilience4j modules required by the provider.
- Reactor Netty or the server runtime matching Gateway WebFlux.

Verify there are no two different versions of Spring Cloud Circuit Breaker or Resilience4j pulled in via transitive dependencies. If you see `NoClassDefFoundError`, check for a missing runtime module. If you see `NoSuchMethodError` or `AbstractMethodError`, check whether the artifacts were resolved from the same compatible release line.

## Confirming Auto-Configuration Creates the Reactive Factory

The Gateway CircuitBreaker filter requires a reactive factory. You can enable the condition evaluation report when starting the application:

```bash
java -jar gateway-app.jar --debug
```

In the Condition Evaluation Report, look for Spring Cloud Circuit Breaker Resilience4j and Gateway auto-configurations. Check classpath conditions, missing beans, enable/disable properties, and reasons configurations did not match.

You can check the ApplicationContext in a development environment by injecting `ReactiveCircuitBreakerFactory` into a diagnostic bean or viewing beans via Actuator if the endpoint is enabled and secured. A context starting up successfully does not yet prove the route filter is using the right provider; verify that the route has the `CircuitBreaker` filter and the breaker name is created according to configuration.

If the Gateway filter reports it cannot find a reactive factory or fails to register the filter, check in order:

1. Is the right reactive Circuit Breaker starter on the runtime classpath?
2. Is the Gateway running with the WebFlux application type?
3. Is there an auto-configuration exclusion or a property disabling the provider?
4. Is there a custom `ReactiveCircuitBreakerFactory` bean or another bean altering the factory creation conditions?
5. Are the Gateway, Circuit Breaker core, and provider versions from the same compatible combination?

Do not resolve errors by manually creating a factory before understanding why auto-configuration did not run. Doing so can hide classpath issues and prevent provider configurations from being applied.

## Configuring a CircuitBreaker Route on Gateway WebFlux

Example of a route to the catalog service. The namespace below illustrates a common configuration form in Gateway lines using `spring.cloud.gateway.routes`; use the corresponding prefix in the documentation of the Gateway major version you are deploying:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: http://catalog-service:8080
          predicates:
            - Path=/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogGateway
                fallbackUri: forward:/fallback/catalog
                statusCodes:
                  - "500"
                  - "502"
                  - "503"
                  - "504"
```

In a newer Gateway major version, the prefix may sit under a dedicated namespace for Gateway Server WebFlux. Do not declare both prefixes at once hoping one of them works; use the exact property namespace of the running release and verify the route is loaded at runtime.

The filter uses the reactive factory to wrap forwarding to the target route. `name` is the breaker identifier. `fallbackUri` in `forward:` form forwards internally to a handler inside the Gateway. `statusCodes` lists response statuses that the filter should treat as failures. Only pick statuses that indicate the dependency is degraded; do not treat every 4xx as an infrastructure failure by default.

## Configuring the Resilience4j Instance

With the Resilience4j provider, configure an instance whose name matches `catalogGateway`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogGateway:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

The breaker evaluates up to the 20 most recent outcomes and begins calculating the rate only after at least 10 recorded calls. When the failure rate reaches or exceeds 50%, it can transition to `OPEN`. After the wait duration, the breaker can enter `HALF_OPEN` and allow up to three trial calls as configured.

If the filter and the instance do not use the same name, the breaker may receive default settings or not pick up the policy you expect. Check the name received by the factory and metrics under that name. Detailed properties should be cross-checked against the Resilience4j version resolved by the BOM.

## Fallbacks Must Be Reactive Handlers in the Gateway

Example of a controller handling the internal URI `/fallback/catalog`:

```java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GatewayFallbackController {

    @RequestMapping("/fallback/catalog")
    public Mono<ResponseEntity<Map<String, String>>> catalogFallback() {
        Map<String, String> body = Map.of(
            "code", "CATALOG_UNAVAILABLE",
            "message", "The catalog service is temporarily unable to process the request."
        );

        return Mono.just(ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(body));
    }
}
```

The handler returns HTTP 503 so clients recognize the service is temporarily unavailable. If the Gateway has cached data or an alternative source, it can return an appropriate response, but it should clearly mark stale data or uncertain status. A fallback should not call back into the failing route itself, because doing so can create a loop or pile additional load onto the dependency.

## Distinguishing Reactive Filters from Imperative Calls

Gateway WebFlux processes requests with a reactive pipeline. The CircuitBreaker filter integrates with `ReactiveCircuitBreakerFactory`; forwarding and fallback occur over publishers. Do not use an imperative `CircuitBreakerFactory` to wrap a publisher and then call `block()` in the filter chain.

If another synchronous service application also needs call protection, it can use an imperative factory or Resilience4j annotations separately. That is a decision for the synchronous module/service, not a reason for Gateway WebFlux to switch to an imperative provider.

Similarly, do not run a blocking HTTP client on the event loop. If the Gateway needs to invoke a blocking library inside a custom filter or handler, you must isolate the work on an appropriate scheduler, set timeouts, and limit concurrency; prefer built-in reactive APIs such as WebClient for network calls.

## Testing Against the Actual Version

After configuring, test with a mock target service capable of returning successes, errors, and delayed responses. Steps to perform:

1. Start the Gateway and confirm the application type is reactive.
2. Confirm the route and CircuitBreaker filter are loaded from the right configuration namespace.
3. Send a request when the dependency returns 200; the response should pass through normally.
4. Have the dependency return a status listed in `statusCodes`; confirm the breaker records a failure and the fallback is invoked as configured.
5. Make the dependency unreachable; confirm the exception is recorded by the provider and the fallback executes.
6. Send enough failures to open the breaker; confirm subsequent requests are not forwarded to the dependency.
7. Observe after the `OPEN` duration; confirm `HALF_OPEN` behavior and trial call results.
8. Check metrics, logs, and traces for the breaker name, rejected call counts, and fallback counts.

Correlate results across the route filter, Resilience4j metrics, and the number of requests the target service actually received. A fallback returning HTTP 503 does not by itself prove the Circuit Breaker is open; the cause could also be a timeout or a transient connection error.

## Common Integration Selection Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using an imperative Circuit Breaker starter for Gateway WebFlux | No reactive provider compatible with the filter chain. | Choose the Reactor provider starter. |
| Confusing Gateway MVC and Gateway WebFlux | Artifact, filter API, and application type mismatch. | Verify the server implementation before picking dependencies. |
| Pairing Gateway with incompatible Spring Boot/Spring Cloud | Auto-configuration, linkage, or startup failures. | Use the matching release train matrix and BOM. |
| Copying property prefixes from another major version | Routes fail to load or filters do not appear. | Use the namespace of the exact Gateway version. |
| Dependency present but no reactive factory | Auto-configuration excluded or provider missing. | Check the condition report and runtime classpath. |
| Mismatched breaker name | Instance does not receive expected configuration. | Align `name` between the route and Resilience4j. |
| Calling `block()` inside a Gateway filter | Blocks the event loop and degrades concurrency. | Keep the pipeline reactive end-to-end. |
| Checking only the fallback response | Can confuse a timeout with the `OPEN` state. | Correlate state, events, and requests reaching the dependency. |

Choosing the right integration for Gateway WebFlux means choosing the right server implementation, a reactive Circuit Breaker provider, and a compatible Spring Boot/Spring Cloud version combination. Then you must verify that the factory, filter, route properties, and fallback are actually active at runtime. This process ensures the Gateway protects dependencies via a reactive pipeline without accidentally introducing synchronous calls or configuration from a different major version into the system.
