# Choosing Between Traditional and Functional Bean Registration

In **Spring Cloud Function**, business logic is expressed as `Supplier<T>`, `Function<I, O>`, and `Consumer<T>`. The framework registers these functions into `FunctionCatalog` so they can be looked up by name, composed, and reused across HTTP, events, or serverless environments. However, **how those functions are registered into the Spring context** affects what Spring must do at startup, how generic types are inferred, and how deeply the app integrates with the Spring Boot ecosystem.

There are two primary approaches:

- **Traditional:** uses `@SpringBootApplication`, `@Configuration`, and `@Bean` so Spring discovers beans automatically, combining Boot auto-configuration and dependency injection.
- **Functional bean definitions:** uses `FunctionalSpringApplication`, `ApplicationContextInitializer<GenericApplicationContext>`, and `context.registerBean(...)` to register functions explicitly, typically paired with `FunctionRegistration` containing type metadata.

These two styles are not two different programming languages; **the Java `Function.apply(...)` business logic can be completely identical**. The difference lies in **bootstrap, metadata, and integration capabilities**. Which choice yields better performance must be measured on your own application and deployment adapter.

This lesson belongs to the **Performance** chapter. After this lesson, you will be able to:

1. Compare traditional, functional, and hybrid modes across startup, auto-configuration, extensibility, and complexity.
2. Create two equivalent entrypoints for the same `Function<Request, Response>`.
3. Explain why functional registration needs to preserve input/output metadata instead of registering a lambda only under raw `Function.class`.
4. Look up the right function through `FunctionCatalog`, compose pipelines, and test inputs arriving from adapters.
5. Choose a registration style based on HTTP, broker, serverless, database workloads, and real operational requirements.
6. Measure **main-to-ready/process-to-ready**, **first invocation**, and **warm execution** separately before concluding “functional is faster.”

## 1. Same function, two ways to place it into the Spring context

Suppose a pricing service has the functionality:

```text
QuoteRequest(sku="BOOK-1", quantity=3)
                   ↓
             quote : Function
                   ↓
QuoteResult(sku="BOOK-1", totalVnd=150000)
```

The starting point should be a **clear Java contract**:

```java
Function<QuoteRequest, QuoteResult>
```

If a developer only looks at the business execution code, traditional and functional styles can produce identical results. However:

| Question | Traditional `@Bean` | Functional bean definitions |
| --- | --- | --- |
| Who creates the bean? | Spring processes `@Configuration`/`@Bean` methods | Code invokes `GenericApplicationContext.registerBean(...)` |
| Typical entrypoint | `@SpringBootApplication` + `SpringApplication.run(...)` | `@SpringBootConfiguration` + `FunctionalSpringApplication.run(...)` |
| Default Spring Boot auto-config? | Yes when using `@SpringBootApplication` | Full functional mode avoids enabling full Boot auto-config in the standard way |
| Where does generic metadata come from? | `@Bean` method signatures can be reflected by the framework | Usually requires `FunctionRegistration.type(...)` or a concrete generic implementation class |
| Does it use `FunctionCatalog`? | Yes | Yes |
| Can it compose `quote|format`? | Yes, once functions are registered and types match | Yes, with proper metadata and complete function registration |
| Datasource, web, security, metrics integration? | Convenient via auto-config/scanning | May require explicit registration/configuration or hybrid mode |
| Bootstrap cost | Can be higher in large apps with many configurations | Potential to be smaller for very compact functions |
| Main risk | Context contains unnecessary configurations/beans | Missing required beans, auto-config, or type metadata |

**Do not conclude that traditional is always slow** or that functional is always better. For a long-lived service with a database, multiple integrations, and health/metrics, functional setup costs may not pay off; for a small serverless function, reducing bootstrap can bring meaningful gains. Decisions must be grounded in measurements and functional requirements.

### The role of FunctionCatalog remains unchanged

Regardless of registration style, the goal is placing the function into the catalog:

```mermaid
flowchart TD
    A["Traditional: @Bean Function<I,O>"]
    B["Functional: FunctionRegistration + type"]
    C[Spring ApplicationContext]
    D[FunctionCatalog]
    E[lookup quote or quote|format]
    F[HTTP / Messaging / Serverless adapter]
    A --> C
    B --> C
    C --> D --> E --> F
```

The diagram shows a **conceptual model**. Adapters, wrappers, and lookup timing can vary by version. The goal is not adding another business abstraction layer, but clarifying the path Spring Cloud Function takes to reach a function.

## 2. Separating business code from registration style

We use Java 17 or later for `record`. The following three classes are **independent of Spring** and shared by both entrypoints:

```java
// File: demo/perf/QuoteRequest.java
package demo.perf;

public record QuoteRequest(String sku, int quantity) {}
```

```java
// File: demo/perf/QuoteResult.java
package demo.perf;

public record QuoteResult(
    String sku,
    int quantity,
    long totalVnd
) {}
```

```java
// File: demo/perf/QuoteLogic.java
package demo.perf;

import java.util.Locale;

public final class QuoteLogic {

    private QuoteLogic() {}

    public static QuoteResult calculate(QuoteRequest request) {
        if (request == null ||
            request.sku() == null ||
            !request.sku().matches("[A-Z0-9-]{1,24}") ||
            request.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid sku or quantity"
            );
        }

        long total = Math.multiplyExact(
            request.quantity(), 50_000L
        );
        return new QuoteResult(
            request.sku(),
            request.quantity(),
            total
        );
    }

    public static String format(QuoteResult result) {
        return result.sku() + ": " +
            String.format(Locale.ROOT, "%d VND", result.totalVnd());
    }
}
```

Example:

```text
Input:  {"sku":"BOOK-1","quantity":3}
Output: {"sku":"BOOK-1","quantity":3,"totalVnd":150000}

After format:
BOOK-1: 150000 VND
```

The logic imports no Spring, Jackson, Gson, HTTP, or binder classes. Therefore:

- The exact same `QuoteLogic.calculate(...)` can be called directly in unit tests.
- Both registration styles can use the method reference `QuoteLogic::calculate`.
- If performance results differ, we have a clean opportunity to analyze the **bootstrap/wrapper/adapter portion**, rather than changing the business algorithm at the same time.

**Concurrency note:** function beans are typically reused across multiple invocations. Logic that avoids storing mutable per-request state in singleton fields is much easier to keep safe. Functional registration does not automatically make a lambda with mutable state thread-safe.

## 3. Traditional approach: @SpringBootApplication + @Bean

A simple Spring Cloud Function application can use:

```java
package demo.perf;

import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TraditionalQuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            TraditionalQuoteApplication.class, args
        );
    }

    @Bean("quote")
    public Function<QuoteRequest, QuoteResult> quote() {
        return QuoteLogic::calculate;
    }

    @Bean("format")
    public Function<QuoteResult, String> format() {
        return QuoteLogic::format;
    }
}
```

Notable points:

1. `@SpringBootApplication` includes configuration declaration, standard Spring Boot auto-configuration, and component scanning.
2. The `@Bean` methods declare full `Function<QuoteRequest,QuoteResult>` and `Function<QuoteResult,String>`; the framework can infer generics from method signatures.
3. When Spring Cloud Function is installed and properly configured, `FunctionCatalog` finds both beans under the names `quote` and `format`.
4. Spring dependency injection is built in: `@Bean` methods can receive auto-configured or explicitly declared repository/service/client beans.
5. The app does not automatically expose an HTTP endpoint just by having `@Bean Function`; a compatible Web adapter and web runtime are required.

### Why is traditional convenient?

For example, if logic needs to call a service backed by a connection pool:

```java
@Bean("quote")
public Function<QuoteRequest, QuoteResult> quote(
        PricingService pricingService) {
    return pricingService::calculate;
}
```

This is an illustrative snippet assuming the application **already has a `PricingService` bean**. With traditional Spring Boot, starters and auto-configuration for datasources, transactions, security, and metrics can drastically reduce manual configuration code. Still, they require the proper dependencies and properties; simply using `@SpringBootApplication` does not magically wire every integration.

### Real-world performance risks

A large application may scan many components or initialize:

- Database connection pools even though the function does not need them.
- Broker clients/cloud SDKs unused in the current artifact.
- Schedulers/cache warm-ups via `@PostConstruct` or `ApplicationRunner`.
- Multiple converters/HTTP handlers/Actuator integrations.

Slow startup may come from those components, **not from the `@Bean` syntax itself**. Before switching an entire app to functional mode, inspect the dependency graph, conditions report, and startup steps to trim excess in the right places.

## 4. Functional approach: direct registration with GenericApplicationContext

Spring Cloud Function documentation describes **Functional Bean Definitions** for small applications needing fast startup. An equivalent example uses:

```java
package demo.perf;

import java.util.function.Function;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.cloud.function.context.FunctionRegistration;
import org.springframework.cloud.function.context.FunctionalSpringApplication;
import org.springframework.cloud.function.context.catalog.FunctionTypeUtils;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.support.GenericApplicationContext;

@SpringBootConfiguration
public class FunctionalQuoteApplication
        implements ApplicationContextInitializer<GenericApplicationContext> {

    public static void main(String[] args) {
        FunctionalSpringApplication.run(
            FunctionalQuoteApplication.class, args
        );
    }

    @Override
    public void initialize(GenericApplicationContext context) {
        Function<QuoteRequest, QuoteResult> quote =
            QuoteLogic::calculate;

        context.registerBean(
            "quote",
            FunctionRegistration.class,
            () -> new FunctionRegistration<>(quote)
                .type(FunctionTypeUtils.functionType(
                    QuoteRequest.class,
                    QuoteResult.class
                ))
        );

        Function<QuoteResult, String> format =
            QuoteLogic::format;

        context.registerBean(
            "format",
            FunctionRegistration.class,
            () -> new FunctionRegistration<>(format)
                .type(FunctionTypeUtils.functionType(
                    QuoteResult.class,
                    String.class
                ))
        );
    }
}
```

**The two entrypoints in section 3 and section 4 are alternative variants**; do not place both into the same artifact and run them with competing bootstrap mechanisms. In a learning project, you can separate source sets/modules or build two distinct JARs sharing `QuoteLogic`.

Differences from the traditional version:

| Traditional | Functional |
| --- | --- |
| `@SpringBootApplication` | `@SpringBootConfiguration` |
| `SpringApplication.run(...)` | `FunctionalSpringApplication.run(...)` |
| `@Bean Function<I,O>` | `context.registerBean(..., FunctionRegistration.class, ...)` |
| Framework reads generic metadata from `@Bean` method signature | Code supplies `FunctionTypeUtils.functionType(I.class,O.class)` |
| Boot auto-config/scanning typically enabled | Full functional mode avoids standard auto-config/scanning paths |

### Why is FunctionRegistration needed?

Once a lambda is created, runtime code may only see an instance of a generic lambda class. If registered under `Function.class`, concrete type parameters are not necessarily easy to infer via reflection.

`FunctionRegistration` stores the **target function + input/output metadata** so the catalog knows:

```text
quote:
    Function<QuoteRequest, QuoteResult>

format:
    Function<QuoteResult, String>
```

This metadata matters when an adapter receives JSON and must deserialize into `QuoteRequest`, when two functions are composed, or when serializing outputs. **Adding `contentType=application/json` cannot compensate for lost generic metadata.**

### Do not register a lambda as a raw Function and hope for the best

Risky example:

```java
// Avoid if the catalog needs to understand the lambda's generic types:
Function<QuoteRequest, QuoteResult> fn = QuoteLogic::calculate;
context.registerBean("quote", Function.class, () -> fn);
```

The code above is an **anti-pattern placed inside an initializer**, not a recommended approach. It can cause the framework to see only a raw `Function`, leading to wrong conversions or missing target types. Section 4 proactively uses `FunctionRegistration.type(...)`.

**You do not add type metadata to make Java's `apply(...)` operator execute faster.** Type metadata serves the catalog/converters and correctness, not a CPU optimization inside the calculation.

## 5. Another functional variant: class implementing Function directly

If an application has only one function and does not need multiple registrations, Spring Cloud Function also describes a functional app style that **implements the `Function<I,O>` interface directly on the class**:

```java
package demo.perf;

import java.util.function.Function;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.cloud.function.context.FunctionalSpringApplication;

@SpringBootConfiguration
public class SingleQuoteApplication
        implements Function<QuoteRequest, QuoteResult> {

    public static void main(String[] args) {
        FunctionalSpringApplication.run(
            SingleQuoteApplication.class, args
        );
    }

    @Override
    public QuoteResult apply(QuoteRequest request) {
        return QuoteLogic.calculate(request);
    }
}
```

The class exposes generics through `implements Function<QuoteRequest,QuoteResult>`, allowing the framework to inspect types at runtime. This is an **alternative variant** to the two earlier entrypoints, well suited when an application has a single primary function. It is less convenient when you need multiple individually named functions and compositions.

When using a concrete class instead of a lambda, you can register it via `FunctionRegistration<>(new MyFunction()).type(MyFunction.class)` in supported contexts. This helps with complex types, though you should verify the registration API of your specific Spring Cloud Function branch.

## 6. Keeping naming and composition consistent

With the two beans `quote` and `format` in either app, you can configure:

```yaml
spring:
  cloud:
    function:
      definition: quote|format
```

Logical flow:

```mermaid
flowchart LR
    A[QuoteRequest] --> B["quote: Function<QuoteRequest,QuoteResult>"]
    B --> C["QuoteResult"]
    C --> D["format: Function<QuoteResult,String>"]
    D --> E["String: BOOK-1: 150000 VND"]
```

The names `quote` and `format` in `FunctionCatalog` should stay identical between both variants. Renaming registrations during migration can break `spring.cloud.function.definition`, Spring Cloud Stream bindings, HTTP routes, and tests.

### Lookup via FunctionCatalog

```java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

// Inside a method/test with FunctionCatalog catalog injected:
Function<QuoteRequest, String> chain =
    catalog.lookup("quote|format");

String output = chain.apply(new QuoteRequest("BOOK-1", 3));
System.out.println(output); // BOOK-1: 150000 VND
```

Looking at this snippet:

- Both traditional and functional styles can supply functions to the catalog.
- The composition junction matches types: `QuoteResult → QuoteResult`.
- The input DTO is already constructed in Java, so this test **does not verify JSON conversion over HTTP**.
- The result is a logical string; the output adapter decides response/event formatting and headers.

When there is only one function in the catalog, Spring Cloud Function has a default lookup mechanism; however, when an application has multiple beans, specify names explicitly to avoid relying on discovery behavior.

## 7. Supplier and Consumer cases

Spring Cloud Function supports three standard interfaces:

| Type | Signature | Role | Has input? | Has Java output? |
| --- | --- | --- | --- | --- |
| Supplier | `Supplier<T>` | Supplies values | No | Yes |
| Function | `Function<I,O>` | Transforms values | Yes | Yes |
| Consumer | `Consumer<T>` | Processes values | Yes | No |

With the traditional style:

```java
@Bean
public java.util.function.Supplier<String> readiness() {
    return () -> "READY";
}

@Bean
public java.util.function.Consumer<QuoteResult> auditQuote() {
    return result -> System.out.println(
        "Processed quote " + result.sku()
    );
}
```

These are two sample beans inside a `@Configuration` class; `System.out` logging is purely illustrative. In production, use a properly configured logger and avoid logging sensitive data.

With functional registration, you must register `Supplier<T>`/`Consumer<T>` metadata correspondingly. If unsure about type inference, prefer a **concrete class implementing the parameterized interface** and register it as a `FunctionRegistration` according to your version's API rather than attaching raw `Supplier.class`/`Consumer.class`.

**Performance implication:** the function interface type does not dictate bean creation cost. A `Supplier` requiring a database connection can still force functional mode to initialize heavy resources. A `Consumer` receiving events will not automatically establish a message broker connection without the proper binder/adapter.

## 8. Auto-configuration reliance is the major decision boundary

According to Spring Cloud Function documentation, **full functional mode** suits small-scope apps with minimal reliance on Spring Boot auto-configuration. When an app needs complex integrations, you can:

1. Keep the `@Bean`/traditional style.
2. Use a **hybrid** style combining functional registration with required auto-configuration.

A hybrid setup mentioned in the documentation:

```java
@SpringBootConfiguration
@EnableAutoConfiguration
public class HybridApplication
        implements ApplicationContextInitializer<GenericApplicationContext> {
    // Register functions with context.registerBean(...)
    // and let Boot provide auto-config for needed integrations.
}
```

The snippet above is an **illustrative skeleton**, requiring appropriate imports and `main`/`initialize` methods when implemented. When opting for hybrid mode, the documentation notes disabling “full functional” mode so Boot can manage auto-configuration:

```properties
spring.functional.enabled=false
```

**Do not assume hybrid is automatically faster than traditional or pure functional.** Once auto-configuration is re-enabled, bean count and bootstrap work can climb significantly. The purpose of hybrid mode is **balancing integration convenience with registration control**, not guaranteeing lower startup in every application.

### What might be missing in pure functional mode?

| Feature | Traditional | Pure functional | What to check |
| --- | --- | --- | --- |
| Component scanning | Usually available | Does not follow full standard scanning | Do beans created via `@Component` exist? |
| `@Bean` config | Discovered by framework | Beans must be registered/configured functionally | Which beans were not created? |
| JDBC/DataSource | May auto-config via starter/props | May need manual beans or hybrid mode | Is there a connection pool? |
| Transaction management | May be configured by Boot/Spring | Should not be assumed present | Is there a transaction interceptor? |
| Security filter chain | May come from Spring Security/Boot | Needs proper integration with adapter | Are endpoints protected? |
| Observability/Actuator | May auto-config | Must inspect dependencies/beans/endpoints | Do health, metrics, and tracing still work? |
| HTTP/stream/serverless adapter | Depends on artifact/config | Depends on artifact/config and mode | Does the adapter start properly? |

An app that “boots faster” because it **accidentally omitted mandatory security, datasource, or broker clients** is not a successful optimization. Compare performance only when **both variants satisfy the exact same real functional requirements**.

## 9. Functional mode does not mean dropping all dependencies

Switching from `@SpringBootApplication` to `@SpringBootConfiguration` does not automatically strip JARs from the runtime classpath. If the build still includes:

- `spring-boot-starter-web`;
- database drivers;
- message binders;
- cloud SDKs;
- Jackson/Gson and modules;
- actuator/tracing exporters;

then the artifact still contains those libraries, even if some auto-configurations are skipped.

Therefore, optimization has two separate tracks:

```text
                  Goal: startup/footprint
                             |
              ┌──────────────┴──────────────┐
              │                             │
     Reduce runtime dependencies    Reduce bootstrap/bean work
              │                             │
        Edit build graph            Traditional / functional
              │                     / hybrid / targeted config
              └──────────────┬──────────────┘
                             |
                  Re-measure and verify features
```

A functional entrypoint can cut scanning/configuration work without **significantly shrinking the JAR**. To shrink the JAR/container image, clean up the dependency graph, split adapters by deployment, and inspect the built artifact.

### Only include adapters actually used

| Deployment | Adapter to consider | Avoid |
| --- | --- | --- |
| Local Java calling catalog | Spring Cloud Function context | Embedded web/binder when not required |
| HTTP | Web adapter + compatible web runtime | Unused broker binders |
| Event | Appropriate binder/messaging integration | Unnecessary web server |
| Serverless | Platform-specific adapter | Bundling every other adapter “just in case” |

This is architectural guidance, not a rigid dependency list. Services requiring HTTP health checks or simultaneous HTTP/event paths may need both. **Never trade operational requirements for a smaller footprint.**

## 10. Measuring performance properly: do not look only at one “Started application” log

A migration proposal is meaningful only when measuring these milestones:

| Metric | Where to measure? | Why does it matter? |
| --- | --- | --- |
| Process-to-ready | From external controller outside the process to readiness | Includes JVM bootstrap and Spring startup |
| Main-to-ready | From start of `main(...)` to `ApplicationReadyEvent` | Compares bootstrap observable inside the JVM |
| First catalog lookup | Around the first `catalog.lookup("quote")` | Detects lazy wrappers/registrations |
| First invocation | Around the first call after startup | Detects JIT, caches, lazy initialization |
| Warm function duration | Timer/JMH in warm state | Isolates steady-state logic execution |
| HTTP/event end-to-end | Client/broker/tracing | Includes adapter, serialization, queueing |
| Memory/RSS, CPU, GC | Runtime metrics | Reveals footprint and trade-offs |

**Lowering main-to-ready does not guarantee lower cold invocation latency**: some costs may shift to catalog lookup or the first request. Conversely, traditional mode might boot slower while running warm functions very quickly.

### Example startup instrumentation in a traditional app

```java
import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public static void main(String[] args) {
    long startNs = System.nanoTime();

    SpringApplication app =
        new SpringApplication(TraditionalQuoteApplication.class);
    app.addListeners(
        (ApplicationListener<ApplicationReadyEvent>) event ->
            System.out.println(
                "main_to_ready_ms=" +
                TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startNs
                )
            )
    );
    app.run(args);
}
```

The snippet above is an **alternative `main` method** for section 3's `main` method, not a top-level Java construct; place it inside `TraditionalQuoteApplication` when used. Pick an equivalent startup measurement mechanism for `FunctionalSpringApplication`, ensuring comparable boundaries and avoiding extra initialization in one variant that the other does not perform.

### Measuring lookup separately

```java
import java.util.function.Function;
import org.springframework.cloud.function.context.FunctionCatalog;

// Inside a test/method with FunctionCatalog catalog:
long lookupStarted = System.nanoTime();
Function<QuoteRequest, QuoteResult> fn =
    catalog.lookup("quote");
long lookupNs = System.nanoTime() - lookupStarted;

long firstStarted = System.nanoTime();
QuoteResult result = fn.apply(
    new QuoteRequest("BOOK-1", 3)
);
long firstNs = System.nanoTime() - firstStarted;

System.out.println("lookup_ns=" + lookupNs);
System.out.println("first_call_ns=" + firstNs);
System.out.println(result.totalVnd()); // 150000
```

This is an **exploratory measurement**: a single sample is not enough to draw conclusions. Repeat across multiple processes for startup, use many warmed-up samples for execution, and use Micrometer/JMH or appropriate benchmark tools. Do not mechanically add the two milestones together and label the sum “framework overhead.”

## 11. Designing a fair traditional vs. functional experiment

When comparing, hold constant:

1. **Logic:** identical `QuoteLogic`, inputs, and validation rules.
2. **JDK, Spring Boot, Spring Cloud Function, and dependency management.**
3. **Adapters and protocol contracts:** only compare startup when both variants serve the **same requirements**; if the functional variant lacks an HTTP endpoint, do not compare it against the traditional variant's HTTP latency.
4. **CPU/memory limits, OS, container image/base JDK**, garbage collector.
5. **Startup readiness definition**, timeout, and polling interval.
6. **Cold process count and warm sample count**, plus execution run order.
7. **Validation, security, observability, and external client configs** identical wherever required.

### A controlled experiment matrix

| Variant | Registration | Auto-config | Adapter | Goal |
| --- | --- | --- | --- | --- |
| A | Traditional `@Bean` | Standard Boot | HTTP | Baseline |
| B | Pure functional | Reduced auto-config per mode | No HTTP | Observe minimal cost **different feature set**, not comparable for endpoints |
| C | Functional/hybrid | Needed Boot auto-config | HTTP | Same-feature comparison against A |
| D | Traditional, trimmed dependencies | Standard Boot but clean classpath | HTTP | Isolate dependency impact from registration style |

**Only comparing A and C permits conclusions on the same HTTP contract.** B helps estimate minimal bootstrap, but is not evidence that functional yields similar savings in an HTTP app with full security, JSON conversion, and health checks.

### Hypothetical numbers table

| Metric | Traditional | Pure functional, tiny function | Hybrid with same adapter |
| --- | ---: | ---: | ---: |
| Main-to-ready p50 | 1,200 ms | 520 ms | 1,050 ms |
| First call p50 | 12 ms | 18 ms | 15 ms |
| Warm core p95 | 0.4 ms | 0.4 ms | 0.4 ms |
| HTTP endpoint | Yes | No in this measurement | Yes |

**All figures above were invented by the lesson for illustration**, not benchmarks of Spring Cloud Function. You cannot take 520 ms from pure functional and claim an HTTP app will drop by 680 ms if that app must re-enable a suite of auto-configurations.

### When are startup gains operationally meaningful?

- **Serverless/cold scaling:** a few hundred ms of bootstrap can affect initial latency when new environments spin up.
- **Long-lived services:** startup may only matter during rollouts/scale-out, whereas throughput, p95/p99 warm latency, and reliability dominate.
- **Backlogged consumers:** processing and draining backlog, client/binder creation speed, retries, and broker connectivity can dominate total time.

There is no universal “functional is N% faster” rule for all projects. Set a **performance budget** based on real SLOs.

## 12. Testing FunctionCatalog across both variants

A pure Java unit test without Spring:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class QuoteLogicTest {

    @Test
    void calculatesTotal() {
        QuoteResult result = QuoteLogic.calculate(
            new QuoteRequest("BOOK-1", 3)
        );
        assertEquals(150_000L, result.totalVnd());
    }
}
```

This test verifies **business logic**, not that beans/catalog/adapters are registered properly. Add a dedicated test through `FunctionCatalog`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.function.context.FunctionCatalog;

// The following members belong inside a Spring Test class
// initialized with either the traditional or functional entrypoint.
@Autowired
FunctionCatalog catalog;

@Test
void catalogAndCompositionWork() {
    Function<QuoteRequest, String> pipeline =
        catalog.lookup("quote|format");

    assertNotNull(pipeline);
    assertEquals(
        "BOOK-1: 150000 VND",
        pipeline.apply(new QuoteRequest("BOOK-1", 3))
    );
}
```

To run tests:

- For traditional, use `@SpringBootTest` specifying the right application class.
- For functional mode, Spring Cloud Function provides `@FunctionalSpringBootTest` test support in supported versions. Verify the exact package/dependency and annotations for your active version.
- Configure the test context properly so both entrypoints are not loaded at the same time.

Specifically: testing `new TraditionalQuoteApplication().quote().apply(...)` directly **does not verify catalog registration**. Testing only `catalog.lookup("quote")` with a pre-built DTO **does not verify JSON conversion over HTTP**.

### Testing HTTP if the artifact has a Web adapter

With a compatible Web adapter exposing the `quote` function:

```bash
curl -X POST http://localhost:8080/quote \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"sku":"BOOK-1","quantity":3}'
```

The expected response body is a representation of `QuoteResult("BOOK-1",3,150000)`, such as the corresponding JSON, assuming the adapter has proper JSON converters and response configuration. **You cannot run curl against plain Java beans alone**, and you must not assume pure functional automatically provides all Web auto-configuration that traditional mode includes.

### Testing events/serverless

For event binders, verify payload/header `contentType`, conversion into `QuoteRequest`, ack/retry, and that the binder actually invokes the function. For serverless, verify handler/adapter event envelope mapping, cold invocations, and output serialization.

Two variants cannot be considered runtime-equivalent merely because billing unit tests pass.

## 13. Generic metadata, JSON, and message conversion during migration

A common reason functional migrations “work in Java but break over HTTP/events” is **lost type information**.

In traditional mode:

```java
@Bean("quote")
public Function<QuoteRequest, QuoteResult> quote() {
    return QuoteLogic::calculate;
}
```

The framework can read `QuoteRequest` and `QuoteResult` from the method return generics. In functional mode, however, registering only:

```java
// Not recommended when generic-based conversion is required:
context.registerBean(
    "quote", Function.class,
    () -> (Function<QuoteRequest, QuoteResult>) QuoteLogic::calculate
);
```

exposes metadata solely as raw `Function.class`. The lesson's solution is:

```java
context.registerBean(
    "quote",
    FunctionRegistration.class,
    () -> new FunctionRegistration<
        Function<QuoteRequest, QuoteResult>
    >(QuoteLogic::calculate)
        .type(FunctionTypeUtils.functionType(
            QuoteRequest.class, QuoteResult.class
        ))
);
```

These snippets are **alternative options** inside the initializer; do not place two registrations named `quote` into the same context.

### Why isn't adding a JSON header enough?

Suppose the adapter has:

```text
payload: {"sku":"BOOK-1","quantity":3}
contentType: application/json
target type: ?
```

The `contentType` header only states the payload is JSON. To construct a Java `QuoteRequest` rather than a `Map<String,Object>`, the converter needs the **target type**; `FunctionRegistration.type(...)` can supply that information. This is a correctness requirement, not an optional tweak reserved for performance benchmarks.

### Collections and reactive types are even more sensitive

| Signature | Critical metadata |
| --- | --- |
| `Function<QuoteRequest, QuoteResult>` | Input/output DTOs |
| `Function<List<QuoteRequest>, List<QuoteResult>>` | Element type inside `List<T>` |
| `Consumer<Message<QuoteRequest>>` | `Message<T>` wrapper and payload type |
| `Function<Flux<QuoteRequest>, Flux<QuoteResult>>` | Publisher and element types |

Do not register `List.class` and assume the mapper automatically knows `QuoteRequest`. Do not treat `Flux<T>` as `List<T>` just because both carry elements of type `T`. When parameterized generic metadata is needed, use compatible type registration APIs and test the converters.

## 14. Choosing by project type

### Case A — Small function, few dependencies, cold start critical

A serverless function that only normalizes/formats data without JPA or many clients can benefit from **pure functional**. It still needs the proper serverless adapter and serialization. Measure **platform cold-start**, **first invocation**, and **warm runtime** to confirm real gains.

### Case B — HTTP service with security, database, health

**Traditional** often wins on operational simplicity thanks to Boot auto-configuration, DI, and the Spring ecosystem. You can trim dependencies, disable unused auto-configs, and narrow component scanning before considering hybrid mode. If you choose hybrid, compare variants sharing the same HTTP/security/health contract.

### Case C — High-volume event consumer

Broker connection costs, group coordination, serializers, retries, and message handling can outweigh creating two function beans. **Registration style** is rarely the primary factor in throughput. Prioritize measuring end-to-end backlog/throughput, error rate, GC, and broker client startup.

### Case D — Many functions, compositions, and converters

Traditional with explicit `@Bean` methods is usually easier to maintain and test; functional mode can still manage many `FunctionRegistration`s, but you must explicitly manage names, type metadata, and dependencies. If the app has many complex service beans, manual wiring cost and the risk of missing auto-config can outweigh minor startup savings.

### Quick decision table

| Criterion | Tends to favor | Reason |
| --- | --- | --- |
| One or a few pure functions without rich Boot integrations | Functional | Less bootstrap/scanning; types can be declared explicitly |
| Many Boot starters genuinely required | Traditional or hybrid | Keeps auto-config and DI straightforward |
| Serverless highly sensitive to cold start | Try functional and measure | Potential to reduce startup |
| Long-lived HTTP API with middleware/security | Traditional first | Streamlines lifecycle and full operations |
| Deeply nested DTOs/generics | Either, preserving metadata | Functional requires explicit type registration |
| Team lacks catalog/adapter tests | Traditional first, add tests | Migration is risky without a regression suite |
| Service already stable and startup meets SLO | No need to switch just for trends | Gains may not justify change cost |

## 15. Safe migration workflow

If you have a traditional Spring Cloud Function app and want to evaluate functional mode:

1. **Freeze the contract:** function names, generic signatures, inputs/outputs, compositions, headers.
2. **Decouple logic from Spring** if not already done: use business classes/methods callable directly.
3. **Record baseline:** startup, catalog lookup, first invocation, warm latency, footprint, errors.
4. **Create the functional entrypoint in a separate variant**: `@SpringBootConfiguration`, `FunctionalSpringApplication`, `ApplicationContextInitializer`.
5. **Register exact names and types:** `FunctionRegistration.type(...)` for lambdas needing generics.
6. **Verify every dependency/integration:** JSON converter, security, validation, database, messaging, serverless adapter, health/metrics.
7. **Pick full functional or hybrid:** if Boot auto-config is needed, test `@EnableAutoConfiguration` with `spring.functional.enabled=false` per your active branch's docs.
8. **Run regression tests:** Java logic, `FunctionCatalog`, composition, HTTP/event/serverless.
9. **Compare fairly:** check startup/cold and first/warm invocations in the same environment, including error rate.
10. **Decide to keep or roll back:** based on SLOs and maintenance cost, not a single “Started” log.

**Do not change two things at once when isolating performance causes:** switching registration, upgrading Spring Boot, and swapping JSON parsers simultaneously makes it impossible to tell what caused the difference. Separate changes into rollback-safe experiments.

## 16. Common issues and diagnosis

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Functional app lacks a key bean | Full functional mode doesn't scan/auto-config like traditional | Register needed bean or switch to hybrid |
| `FunctionCatalog.lookup("quote")` returns null | Wrong registration name / initializer didn't run | Check entrypoint, bean names, and context |
| HTTP JSON becomes `Map` instead of `QuoteRequest` | Raw `Function.class` / lost generic metadata | Use `FunctionRegistration.type(...)` |
| Composition `quote|format` fails | One function unregistered or type mismatch | Check catalog and output/input types |
| Functional app runs but HTTP endpoint is missing | Web adapter/bootstrap misconfigured | Check dependencies, mode, and adapter |
| Functional startup is fast but first call is very slow | Lazy resources or JIT/cache shifted to first call | Measure first vs. warm separately; intentional warm-up if suitable |
| Hybrid startup nearly matches traditional | Many auto-configs re-enabled | Inspect conditions report and bean creation |
| Validation annotations do not trigger | Validator/interceptor not created | Register/configure validation at the proper layer |
| Function needs repository but injection fails | Datasource/repository bean missing | Check auto-config or use traditional/hybrid |
| Metrics/health missing | Actuator/registry/beans not created | Ensure observability contract |
| Events not received | Missing binder/handler/metadata | Broker integration test, not only unit test |
| Changing registration does not improve warm latency | Logic/I/O is the real bottleneck | Profile and optimize core/adapter |

### Six questions to pinpoint the issue

1. Are you running **traditional, pure functional, or hybrid**? Which entrypoint is actually active?
2. Are function names in `FunctionCatalog` exact and complete?
3. Where does the framework learn the **input/output generics** of each function?
4. Which beans are created and which auto-configurations are active?
5. Do HTTP/event/serverless adapters actually handle payloads and headers properly?
6. Does the measurement refer to **startup, first call, or warm call**?

Do not fix a JSON issue by adding an entire unnecessary Boot starter if the root cause is simply missing type metadata. Conversely, do not hand-roll a repository bean when traditional/hybrid auto-configuration is clearer and fits the requirements.

## 17. Practice exercises

**Exercise 1 — Choosing registration style.** A serverless function only uppercases a `String` without using a database or web server. What is worth trying to reduce cold startup?

*Answer:* Try functional bean definitions with `FunctionalSpringApplication`, explicitly registering input/output types or implementing `Function<String,String>` directly on the class; keep the proper serverless adapter and measure actual cold/warm performance.

**Exercise 2 — Type metadata.** Why does traditional `@Bean Function<QuoteRequest,QuoteResult>` usually not need `FunctionRegistration.type(...)`, whereas a functional lambda registered with raw `Function.class` might?

*Answer:* The `@Bean` method signature exposes generics for framework inference; registering a raw lambda can lose metadata needed by converters and the catalog. `FunctionRegistration.type(...)` declares the target type pair explicitly.

**Exercise 3 — Functional mode and datasource.** After switching to pure functional mode, DataSource/repository beans disappear. Is this a bug in `QuoteLogic`?

*Answer:* Not necessarily. Pure functional mode does not enable all auto-configurations like traditional mode. If the app needs a datasource, register the integration appropriately or use traditional/hybrid mode with `@EnableAutoConfiguration` and `spring.functional.enabled=false` per version.

**Exercise 4 — Composition.** Two beans `quote: Function<QuoteRequest,QuoteResult>` and `format: Function<QuoteResult,String>` are registered. What is the configuration string?

*Answer:* `spring.cloud.function.definition=quote|format`. Test `FunctionCatalog.lookup("quote|format")` with a valid `QuoteRequest`.

**Exercise 5 — Unfair startup comparison.** Traditional includes Web adapter/security/health, while pure functional has only the core function. The functional build boots 600 ms faster. Can you conclude “switching registration saves 600 ms”?

*Answer:* No. The two builds are not functionally equivalent. Compare against a functional/hybrid build meeting the same adapter and security/health contracts, or explicitly note that functional is a different minimal configuration.

**Exercise 6 — Testing JSON.** `QuoteLogic.calculate(new QuoteRequest(...))` passes. Why do you still need an HTTP integration test after migration?

*Answer:* The unit test constructs DTOs directly and does not check generics, JSON converters, `Content-Type` headers, or the Web adapter. Migration can affect all of those.

**Exercise 7 — First invocation.** Main-to-ready drops 400 ms while first invocation rises 300 ms. What should you do before accepting the change?

*Answer:* Measure cold end-to-end and warm paths against workload/SLOs, identify what lazy work shifted costs, and track error rates; do not look solely at main-to-ready.

**Exercise 8 — Bean names.** In traditional mode, `@Bean("quote")` was migrated to `context.registerBean("calculate",...)`. Tests calling `catalog.lookup("quote")` start failing. Where is the bug?

*Answer:* The registration name no longer preserves the `quote` contract. Keep the same name or deliberately update related bindings/definitions/tests.

**Exercise 9 — Supplier and Consumer.** Can only `Function<I,O>` be registered in functional style?

*Answer:* No. Spring Cloud Function supports `Supplier<T>` and `Consumer<T>`; you still need to preserve generic/type metadata and verify trigger/ack timing determined by the adapter.

**Exercise 10 — When not to switch.** A Spring Boot API has many integrations, warm p95/p99 meets SLOs, and startup does not impact rollouts. Should you rewrite to functional mode just because docs say startup can be faster?

*Answer:* Not required. Weigh migration cost, maintainability, and test coverage; prioritize optimizing actual measured bottlenecks.

## 18. Key takeaways

- **Traditional and functional both feed `FunctionCatalog`**, differing only in how Spring instantiates beans and resolves type metadata.
- **Traditional `@Bean` shines in Boot auto-configuration, component scanning, and DI**, fitting apps with rich integrations.
- **Functional uses `FunctionalSpringApplication`, `@SpringBootConfiguration`, and `GenericApplicationContext.registerBean(...)`**, fitting small functions needing tight bootstrap control.
- **Preserve generic metadata via `FunctionRegistration.type(...)` when needed.** Registering raw lambdas alone can break JSON conversion and composition.
- **Hybrid restores Boot auto-configuration per the docs**, using `@EnableAutoConfiguration` and `spring.functional.enabled=false` on supported branches; this can reduce startup gains.
- **Do not confuse removing auto-config with removing dependencies**: functional mode does not shrink the JAR by itself or speed up CPU-bound functions.
- **Fair comparisons require equivalent features/adapters** and separate measurements for process-to-ready, main-to-ready, catalog lookup, first invocation, and warm execution.
- **Choose based on SLOs, complexity, and correctness**; prioritize testing Java logic, catalog/composition, and HTTP/event/serverless adapters.

**Official references:**

- [Spring Cloud Function — Functional Bean Definitions (5.0)](https://docs.spring.io/spring-cloud-function/reference/5.0/functional.html)
- [Spring Cloud Function — Programming Model (5.0)](https://docs.spring.io/spring-cloud-function/reference/5.0/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Reference](https://docs.spring.io/spring-cloud-function/reference/)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)

These examples illustrate architectural choices and bean registration styles. In real deployments, verify your **Spring Cloud Function, Spring Boot, JDK, and adapter versions**, measure in the same environment, and ensure full functionality before declaring a registration style optimal.
