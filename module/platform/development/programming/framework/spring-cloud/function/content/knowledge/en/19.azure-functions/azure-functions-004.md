# Injecting Business Services and FunctionCatalog into a Handler

## 1. Problem: Azure Calls the Handler, Spring Provides the Business Logic

**Spring Cloud Function (SCF)** helps build reusable business logic through three Java interfaces: `Supplier<T>`, `Function<T,R>`, and `Consumer<T>`. Function beans are registered/resolved via **`FunctionCatalog`**, can be composed using definitions like `f1|f2`, convert data per SCF contracts, and can be reused from HTTP, event streams, or serverless platforms through the corresponding adapters.

**Azure Functions** handles triggering and execution in a serverless environment. In Java, the Azure Java Worker invokes a **`public` method** annotated with `@FunctionName` and a trigger annotation such as `@HttpTrigger` or `@QueueTrigger`. Azure does not automatically treat every `@Bean Function` in Spring as an Azure Function.

When deploying SCF on Azure, a sustainable structure is:

- **Azure handler** receives input/metadata, invokes business logic, and builds the response or output binding.
- **Spring service** implements reusable business rules and is injected into the handler.
- **Function beans** adapt service methods into `Function<T,R>` or `Consumer<T>`.
- **`FunctionCatalog`** looks up a function or composition by name, instead of having the handler know how to wire individual functions together.
- **`spring-cloud-function-adapter-azure`** connects the Java Worker with Spring dependency injection.

This lesson belongs to the **Azure Functions** chapter of the **SPRING_CLOUD_FUNCTION** module. Its focus is **injecting business services and `FunctionCatalog` into a handler**, rather than writing all business logic directly inside `@FunctionName` methods.

After this lesson, you will be able to: configure services, function beans, and constructor injection; distinguish direct bean injection from catalog lookup; write two Azure HTTP handlers reusing one business service; understand scope, concurrency, and cold start issues; and test and diagnose errors accurately across Azure, Spring, and SCF.

## 2. Architecture Diagram and Dependency Ownership

~~~mermaid
flowchart LR
    A["HTTP / Queue / Timer"] --> B["Azure Functions Host"]
    B --> C["Azure Java Worker"]
    C --> D["@FunctionName handler"]
    E["spring-cloud-function-adapter-azure"] -. "FunctionInstanceInjector / Spring DI" .-> D
    F["Spring ApplicationContext"] --> E
    F --> G["@Service OrderService"]
    F --> H["@Bean parseOrder / routeOrder"]
    H --> I["FunctionCatalog"]
    D -->|"direct call"| G
    D -->|"lookup parseOrder|routeOrder"| I
    I --> H
    H --> G
    D --> J["HTTP response / output binding"]
~~~

The diagram shows two business invocation paths:

1. **Direct Spring service path:** the handler injects `OrderService` and calls `service.parse(...)` and `service.classify(...)`.
2. **FunctionCatalog path:** the handler injects `FunctionCatalog` and calls `catalog.lookup("parseOrder|routeOrder")` to obtain a `Function<String,OrderDecision>`; the underlying function beans delegate to **the same `OrderService`**.

Both must produce **identical business results**, while the catalog additionally provides SCF wrapping and composition.

### 2.1. Who Creates Which Object?

| Object | Creator / Manager | When Used? |
| --- | --- | --- |
| `OrderService` annotated with `@Service` | Spring `ApplicationContext` | Parsing, validation, and classification logic. |
| `@Bean Function<String,OrderCommand>` | Spring; recognized by SCF in `FunctionCatalog` | Converts raw input into a domain object. |
| `@Bean Function<OrderCommand,OrderDecision>` | Spring; recognized by SCF in the catalog | Business decision step. |
| `FunctionCatalog` | Spring Cloud Function in the context | Name and composition lookup. |
| `OrderAzureHandler` annotated with `@Component` | Spring, bridged to the Java Worker by the Azure adapter | Handles invocations triggered by Azure. |
| `ExecutionContext` | Azure Functions runtime | **Per-invocation** metadata and logger. |
| `HttpRequestMessage<T>` | Azure Functions runtime/binding | Accesses HTTP body, headers, query parameters, and builds responses. |

**Note:** `@Component` does not automatically create an Azure HTTP endpoint; `@FunctionName` does not automatically create a Spring bean. The handler requires **both**: Spring managing the instance and Azure recognizing the method's trigger/binding.

### 2.2. Injector Mechanism

Azure Java Functions provides **`FunctionInstanceInjector`** in Java SPI so DI frameworks can supply instances of handler classes. The Spring Cloud Function Azure adapter integrates with this mechanism to supply Spring-managed handlers. In normal applications, **do not write a custom `FunctionInstanceInjector`** or manually call `new OrderAzureHandler(...)` when using the official adapter.

If Azure discovers the method but the injector fails to instantiate the bean, the function will still fail on the first invocation. Diagnose both **Azure discovery** and **Spring context creation**, not just the `@FunctionName` annotation.

## 3. Dependencies and Version Requirements

The `@Component` handler model using Spring DI via the adapter is documented by Spring Cloud Function for **SCF 4.0.0+**. Choose compatible versions of Spring Boot, Spring Cloud BOM, Azure Functions runtime, and Java compile target; do not mix major versions arbitrarily.

### 3.1. Maven Dependencies

For a project with a compatible Spring Boot parent and Spring Cloud BOM configured:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-adapter-azure</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.microsoft.azure.functions</groupId>
        <artifactId>azure-functions-java-library</artifactId>
        <version>1.3.1</version>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Version `1.3.1` of the Azure Java library is an **API illustration baseline**, not a claim of being the latest release. When starting a new project, obtain the Java library and Azure plugin versions from your organization's active templates/release notes. The SCF adapter version should be managed by the Spring Cloud BOM in lockstep with `spring-cloud-function-context`.

| Component | Purpose |
| --- | --- |
| `spring-cloud-function-adapter-azure` | Spring/SCF dependency injection for Java Azure Functions. |
| `spring-cloud-function-context` | `FunctionCatalog`, registration, and composition; usually pulled transitively by the adapter. |
| `spring-boot-starter` | Spring context, dependency injection, application configuration; does not require an embedded HTTP server. |
| `azure-functions-java-library` | `@FunctionName`, trigger annotations, `HttpRequestMessage`, and `ExecutionContext`. |
| `azure-functions-maven-plugin` | Build plugin generating `function.json`, staging layout, and packages; **not a runtime dependency**. |
| `spring-boot-starter-test` | JUnit/Spring integration tests. |

Do not add `spring-boot-starter-web` merely to handle an `@HttpTrigger`: the Azure Host is the HTTP runtime here. If you want Spring MVC controllers and filters, evaluate the separate `spring-cloud-function-adapter-azure-web` adapter; do not mix both strategies without reason.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-adapter-azure'
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.microsoft.azure.functions:azure-functions-java-library:1.3.1'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Gradle requires Spring Boot/Cloud dependency management and the `com.microsoft.azure.azurefunctions` plugin if using Gradle packaging. Choose **one** Azure build workflow (Maven or Gradle) per project.

### 3.3. Do Not Confuse the Adapter with FunctionInvoker

Some older guides extend the `FunctionInvoker` class. Current SCF documentation marks that approach **deprecated**; for new projects, write **`@Component` handlers + Azure `@FunctionName` annotations + injected services/catalog**.

## 4. Designing the Example Problem

A company receives orders as text payloads via an HTTP trigger:

~~~text
Input:  "  dh-401  |  1500000  "
Output: "DH-401|PRIORITY|1500000"
~~~

Rules:

- The order code must not be blank, is trimmed via `strip()`, and uppercased with `Locale.ROOT`.
- The total amount in VND must be a positive integer; input uses `|` to separate the two fields.
- Orders of **1,000,000 VND or more** are classified as `PRIORITY`; others as `STANDARD`.
- Malformed input is a **validation error** (HTTP 400), not a server error.
- Business logic accepts/returns Java domain types only and contains no Azure SDK imports.

Two endpoints are demonstrated:

| Azure Function | HTTP Route | Invocation Path |
| --- | --- | --- |
| `classifyByService` | `POST /api/orders/direct` | Handler -> `OrderService` directly. |
| `classifyByCatalog` | `POST /api/orders/catalog` | Handler -> `FunctionCatalog.lookup("parseOrder|routeOrder")`. |

In production, you normally only expose **one** public endpoint for the same business operation. Two endpoints are shown here solely to let learners compare both paths.

### 4.1. Two Java Records

Create `src/main/java/example/azure/OrderData.java`:

~~~java
package example.azure;

record OrderCommand(String id, long totalVnd) {}

record OrderDecision(String id, long totalVnd, String lane) {}
~~~

Both records are package-private and the handler/service live in the same `example.azure` package, so they are accessible here. To reuse them across packages/APIs, move each record into its own `public record` file matching its name.

### 4.2. Spring-Managed Business Service

Create `src/main/java/example/azure/OrderService.java`:

~~~java
package example.azure;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public OrderCommand parse(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing order data");
        }

        String[] parts = raw.split("\\|", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Format must be orderId|totalVnd");
        }

        String id = parts[0].strip().toUpperCase(Locale.ROOT);
        String money = parts[1].strip();

        if (id.isEmpty()) {
            throw new IllegalArgumentException("Order code must not be blank");
        }

        final long total;
        try {
            total = Long.parseLong(money);
        }
        catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Total amount must be an integer", ex);
        }

        if (total <= 0) {
            throw new IllegalArgumentException(
                    "Total amount must be greater than 0");
        }

        return new OrderCommand(id, total);
    }

    public OrderDecision classify(OrderCommand order) {
        if (order == null) {
            throw new IllegalArgumentException("Missing order object");
        }

        String lane = order.totalVnd() >= 1_000_000
                ? "PRIORITY" : "STANDARD";

        return new OrderDecision(
                order.id(),
                order.totalVnd(),
                lane);
    }
}
~~~

`@Service` is a Spring stereotype, essentially a `@Component` conveying business-layer semantics. It does **not** automatically register the service as a function in the catalog: `OrderService` does not implement `java.util.function.Function`.

**Why is a separate service important?** If all business logic lived inside `@FunctionName`, migrating to a Queue Trigger, Spring Cloud Stream, another HTTP adapter, or AWS Lambda would force duplicating code. A plain Java service simplifies unit testing, reuse, and centralizes business rules.

## 5. Registering Function Beans from a Spring Service

Create `src/main/java/example/azure/OrderFunctionConfig.java`:

~~~java
package example.azure;

import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctionConfig {

    @Bean
    public Function<String, OrderCommand> parseOrder(
            OrderService service) {
        return service::parse;
    }

    @Bean
    public Function<OrderCommand, OrderDecision> routeOrder(
            OrderService service) {
        return service::classify;
    }
}
~~~

Spring injects the same `OrderService` into both `@Bean` factory methods. SCF recognizes the two function beans under the names `parseOrder` and `routeOrder`.

`FunctionCatalog` can then look up:

~~~java
Function<String, OrderCommand> parser =
        catalog.lookup("parseOrder");

Function<OrderCommand, OrderDecision> classifier =
        catalog.lookup("routeOrder");

Function<String, OrderDecision> pipeline =
        catalog.lookup("parseOrder|routeOrder");
~~~

Because `parseOrder`'s output `OrderCommand` matches `routeOrder`'s input `OrderCommand`, the composition is:

~~~mermaid
flowchart LR
    A["String: dh-401|1500000"] --> B["parseOrder"]
    B --> C["OrderCommand"]
    C --> D["routeOrder"]
    D --> E["OrderDecision"]
~~~

**Clear distinctions:**

- `OrderService` is a standard Spring service injected directly.
- `parseOrder` and `routeOrder` are `Function` beans backed by the service's methods.
- `FunctionCatalog` provides a **canonical function representation**, optionally with wrappers, type conversion, and composition; it is more than just `ApplicationContext.getBean("parseOrder")`.
- You do not register Azure handlers in the catalog. `@FunctionName` is an Azure entrypoint, not an SCF function name.

### 5.1. Why Not Compose in the Wrong Order?

The chain `routeOrder|parseOrder` violates the type contract:

~~~text
routeOrder:  OrderCommand → OrderDecision
parseOrder:  String → OrderCommand

routeOrder|parseOrder: OrderDecision is not a String
~~~

SCF composition can convert types across some boundaries, but you must never assume every domain type automatically converts into every other type. Strictly typed pipelines must be tested with actual payloads and the adapter's converters.

### 5.2. Supplier/Consumer Can Also Reuse Services

Besides `Function`, you can define:

~~~java
@Bean
public Consumer<OrderCommand> auditOrder(OrderAuditService audit) {
    return audit::record;
}
~~~

This is just a **design variant**: `OrderAuditService` would need to exist if added to a project. A `Consumer<T>` terminates the pipeline and returns no value for an HTTP response. For example, `parseOrder|auditOrder` yields a **`Consumer<String>`**, not a `Function<String,OrderDecision>`. Do not use a void consumer as a request/reply endpoint while expecting an `OrderDecision`.

## 6. Spring Boot Entrypoint and Component Scanning Scope

Create `src/main/java/example/azure/AzureOrderApplication.java`:

~~~java
package example.azure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AzureOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(AzureOrderApplication.class, args);
    }
}
~~~

With all classes in `example.azure`:

- `@SpringBootApplication` scans `OrderService` (`@Service`).
- `OrderFunctionConfig` (`@Configuration`) creates the two function beans.
- `OrderAzureHandler` (`@Component`, written in Section 7) is instantiated by Spring.
- SCF registers the function beans into the catalog.
- The Azure adapter uses the Spring context to provide instances to the Azure Java Worker.

Do not call `SpringApplication.run(...)` on every invocation; the Azure app runs under the Azure Host, while the adapter initializes the Spring context and reuses it across the worker lifecycle.

If the handler lives outside the root package, use `@ComponentScan` or adjust the package structure. If Spring cannot scan the service/handler, Azure discovering the method is not enough for dependency injection to succeed.

## 7. Handler Injecting Both OrderService and FunctionCatalog

Create `src/main/java/example/azure/OrderAzureHandler.java`:

~~~java
package example.azure;

import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import java.util.logging.Level;

import com.microsoft.azure.functions.AuthorizationLevel;
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.HttpMethod;
import com.microsoft.azure.functions.HttpRequestMessage;
import com.microsoft.azure.functions.HttpResponseMessage;
import com.microsoft.azure.functions.HttpStatus;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.HttpTrigger;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class OrderAzureHandler {

    private final OrderService orderService;
    private final Function<String, OrderDecision> pipeline;

    public OrderAzureHandler(
            OrderService orderService,
            FunctionCatalog catalog) {

        this.orderService = orderService;
        this.pipeline = Objects.requireNonNull(
                catalog.lookup("parseOrder|routeOrder"),
                "Function composition not found");
    }

    @FunctionName("classifyByService")
    public HttpResponseMessage classifyByService(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/direct")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        return respond(request, context,
                raw -> orderService.classify(
                        orderService.parse(raw)));
    }

    @FunctionName("classifyByCatalog")
    public HttpResponseMessage classifyByCatalog(
            @HttpTrigger(
                    name = "request",
                    methods = {HttpMethod.POST},
                    authLevel = AuthorizationLevel.FUNCTION,
                    route = "orders/catalog")
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context) {

        return respond(request, context, pipeline);
    }

    private HttpResponseMessage respond(
            HttpRequestMessage<Optional<String>> request,
            ExecutionContext context,
            Function<String, OrderDecision> operation) {

        String input = request.getBody().orElse("");

        try {
            OrderDecision result = operation.apply(input);
            String output = result.id() + "|"
                    + result.lane() + "|"
                    + result.totalVnd();

            return request.createResponseBuilder(HttpStatus.OK)
                    .header("Content-Type",
                            "text/plain; charset=utf-8")
                    .body(output)
                    .build();
        }
        catch (IllegalArgumentException invalid) {
            return request
                    .createResponseBuilder(HttpStatus.BAD_REQUEST)
                    .body("Invalid order data")
                    .build();
        }
        catch (RuntimeException failure) {
            context.getLogger().log(
                    Level.SEVERE,
                    "Unexpected order processing error",
                    failure);
            return request.createResponseBuilder(
                            HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Unable to process request")
                    .build();
        }
    }
}
~~~

The two Azure methods:

1. `classifyByService` uses **`OrderService`** injected by Spring.
2. `classifyByCatalog` uses the **composition** returned by `FunctionCatalog`.
3. Both reuse the exact same parse/classify rules and return data under the same contract.
4. `respond(...)` handles the HTTP boundary: reading the body, separating 400 vs. 500 errors, and building the response.
5. `ExecutionContext` is a **method parameter** supplied by the Azure runtime per invocation, not a Spring singleton.
6. `@Component` belongs on the **class** so Spring manages the bean; `@FunctionName` belongs on the **method** so the Azure Host discovers it; `@HttpTrigger` belongs on the **parameter** to declare the HTTP binding.

### 7.1. Why Constructor Injection?

Constructor injection ensures required dependencies are resolved when Spring creates the handler, rather than failing only when the method is invoked. Marking fields `final` prevents accidental mutation. `Objects.requireNonNull(...)` makes a misspelled composition **fail fast**.

If two function beans share the `Function<String,String>` type and are injected directly, use `@Qualifier("beanName")` to avoid ambiguity; here the handler injects `OrderService` and `FunctionCatalog`, so that ambiguity does not arise.

### 7.2. HTTP Status Checks and Safe Logging

- Malformed input or missing body -> HTTP 400.
- Valid input processed successfully -> HTTP 200 with order ID, lane, and total amount.
- Infrastructure/unexpected exceptions -> HTTP 500 and server-side logging.
- Never return stack traces or internal `FunctionCatalog` details to callers.
- Never rely on function keys as the sole auth mechanism for sensitive systems; review Function App authentication, API gateways, identities, and access controls.
- In production, return a consistent error schema and correlation ID rather than plain text as in the demo.

### 7.3. Why Not Look Up the Catalog on Every Request?

When the definition is fixed like `parseOrder|routeOrder`, resolving the composition **once in the constructor** catches misconfigurations early and avoids repeated lookups. Inside a Spring-managed singleton, `pipeline` is a shared dependency; it and its underlying services/functions must be **thread-safe**.

When a definition genuinely must be chosen dynamically, enforce an explicit allowlist and authorization. Never read a function name directly from an untrusted query/header and invoke the catalog arbitrarily.

## 8. Running Locally and Observing Both Paths

Assume the Azure Functions Host runs locally on the default port:

~~~text
POST http://localhost:7071/api/orders/direct
POST http://localhost:7071/api/orders/catalog
~~~

Send the same request to each endpoint:

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/direct" \
  -H "Content-Type: text/plain" \
  --data "  dh-401  |  1500000  "
~~~

~~~bash
curl -i -X POST "http://localhost:7071/api/orders/catalog" \
  -H "Content-Type: text/plain" \
  --data "  dh-401  |  1500000  "
~~~

Expected result from both:

~~~text
HTTP/1.1 200 OK

DH-401|PRIORITY|1500000
~~~

Try other test cases:

| Input | Valid Output | HTTP |
| --- | --- | --- |
| `"dh-402|500000"` | `DH-402|STANDARD|500000` | 200 |
| `" dh-403 | 1000000 "` | `DH-403|PRIORITY|1000000` | 200 |
| `"  | 100000 "` | Missing order code | 400 |
| `"dh-404|abc"` | Total amount is not an integer | 400 |
| `"dh-405|0"` | Non-positive total amount | 400 |
| `"dh-406"` | Missing separator / total amount | 400 |
| Blank body | No valid data | 400 |

**You do not need two copies of the business rules** to expose two Azure endpoints. The only difference is one calls the injected service while the other calls the SCF-wrapped composed function.


## 9. Testing Independently of Azure: From Service to FunctionCatalog

Dependency injection lets you test different layers **without an Azure subscription**.

### 9.1. Unit Testing OrderService

Create `src/test/java/example/azure/OrderServiceTest.java`:

~~~java
package example.azure;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {

    private final OrderService service = new OrderService();

    @Test
    void normalizesAndClassifiesPriorityOrder() {
        OrderCommand order =
                service.parse("  dh-401  | 1500000 ");

        assertEquals("DH-401", order.id());
        assertEquals(1_500_000L, order.totalVnd());

        OrderDecision result = service.classify(order);
        assertEquals("PRIORITY", result.lane());
    }

    @Test
    void classifiesStandardOrder() {
        OrderDecision result = service.classify(
                service.parse("dh-402|500000"));

        assertEquals("STANDARD", result.lane());
        assertEquals("DH-402", result.id());
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> service.parse("  | 100000 "));
        assertThrows(IllegalArgumentException.class,
                () -> service.parse("dh-403|abc"));
        assertThrows(IllegalArgumentException.class,
                () -> service.parse("dh-403|0"));
    }
}
~~~

Unit tests verify business rules; they do not test the Spring context, Azure Host, function bindings, or JSON serialization. When adding a Queue Trigger, the same test suite still verifies parsing and classification rules.

### 9.2. Testing Spring Context and Catalog Composition

Create `src/test/java/example/azure/OrderCatalogTest.java`:

~~~java
package example.azure;

import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = AzureOrderApplication.class)
class OrderCatalogTest {

    @Autowired
    OrderService orderService;

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderAzureHandler azureHandler;

    @Test
    void serviceAndHandlerAreSpringBeans() {
        assertNotNull(orderService);
        assertNotNull(azureHandler);
    }

    @Test
    void catalogComposesFunctionsUsingService() {
        Function<String, OrderDecision> pipeline =
                catalog.lookup("parseOrder|routeOrder");

        assertNotNull(pipeline);

        OrderDecision result =
                pipeline.apply(" dh-401 | 1500000 ");

        assertEquals("DH-401", result.id());
        assertEquals("PRIORITY", result.lane());
        assertEquals(1_500_000L, result.totalVnd());
    }
}
~~~

This test proves Spring scans `OrderService` and the handler, registers both `Function` beans in the catalog, and verifies the composition type contract. Because the handler constructor uses `Objects.requireNonNull(...)`, a typo in the definition causes the **Spring test context to fail at startup** — a useful *fail-fast* safeguard.

### 9.3. Checking Azure Annotations Without Confusing Them with Host-Level Tests

A reflection test can verify the two Azure methods:

~~~java
@Test
void handlerMethodsExposeDistinctAzureNames()
        throws NoSuchMethodException {

    var direct = OrderAzureHandler.class.getMethod(
            "classifyByService",
            HttpRequestMessage.class,
            ExecutionContext.class);

    var catalog = OrderAzureHandler.class.getMethod(
            "classifyByCatalog",
            HttpRequestMessage.class,
            ExecutionContext.class);

    assertEquals("classifyByService",
            direct.getAnnotation(FunctionName.class).value());
    assertEquals("classifyByCatalog",
            catalog.getAnnotation(FunctionName.class).value());
}
~~~

Requires imports for the Azure types, `FunctionName`, and JUnit Assertions. This test **does not** prove the build plugin generated `function.json` or that the host discovered the functions properly.

### 9.4. Integration Test Matrix on the Local Azure Functions Host

After packaging with the Azure Maven/Gradle plugin, start Azure Functions Core Tools v4 and send POST requests to both routes.

| Test | Expected |
| --- | --- |
| Valid input to the service endpoint | HTTP 200 and expected body. |
| Same input to the catalog endpoint | Identical business result. |
| Malformed format, blank code, invalid amount | HTTP 400, no stack trace leaked. |
| GET to a POST-only route | Not handled as a valid POST. |
| Missing function key on Azure cloud | Rejected according to authorization policy. |
| Spring context failure | Logs pinpoint the failing dependency or catalog lookup. |
| Azure Host does not recognize method | Inspect metadata generated from annotations/plugin. |
| Changed JDK target or runtime | Verify compile target matches Java runtime. |

`@SpringBootTest` does not start the Azure Worker. Notably, if the service HTTP endpoint works while the catalog endpoint fails, inspect Spring function registration rather than changing HTTP annotations.

## 10. When to Inject a Service, a Function Bean, or FunctionCatalog?

Not every handler needs all three kinds of dependencies.

| Need | What to Inject | Reason |
| --- | --- | --- |
| Multiple business methods, validation, and repositories | `OrderService` or a service interface | Clear layering, easy to unit test and mock. |
| A single fixed transformation | `Function<T,R>`, with `@Qualifier` if needed | Simple, avoids catalog lookup. |
| Chaining multiple transformations | `FunctionCatalog` | Composition and SCF wrappers. |
| Controlled configurable definitions | `FunctionCatalog` with allowlist | Flexible, but requires validation and authorization. |
| Side effects with no reply | `Consumer<T>` or domain service | Fits events/queues, with distinct error/ack contracts. |
| Emitting data on a Timer trigger | `Supplier<T>` called by handler | Azure still requires the Timer Trigger. |

### 10.1. Multiple Function Beans with the Same Generic Type

Suppose there are two beans:

~~~java
@Bean
Function<String, String> trimCode() {
    return String::strip;
}

@Bean
Function<String, String> upperCode() {
    return String::toUpperCase;
}
~~~

Injecting solely by `Function<String,String>` causes ambiguity. Use a qualifier:

~~~java
@Component
class ExampleDependency {

    private final Function<String, String> trim;

    ExampleDependency(
            @Qualifier("trimCode")
            Function<String, String> trim) {
        this.trim = trim;
    }
}
~~~

This is an **illustrative fragment**; do not add this class to the main demo. Import `org.springframework.beans.factory.annotation.Qualifier`. With multiple service implementations, you can use `@Qualifier` or `@Primary` when architecturally meaningful, but never use `@Primary` just to mask picking the wrong service.

### 10.2. FunctionCatalog Is Not a Map of All Spring Beans

`FunctionCatalog` does not replace `ApplicationContext`. `OrderService` is a regular business bean; it is not automatically registered in the catalog because it is not a functional bean. To expose business logic in functional form, declare:

~~~java
@Bean
Function<OrderCommand, OrderDecision> routeOrder(
        OrderService service) {
    return service::classify;
}
~~~

SCF discovers the `Function` bean, while the service retains ownership of the business rules.

### 10.3. The Catalog Does Not Create HTTP Routes

`catalog.lookup("parseOrder|routeOrder")` only resolves a **function definition**. The HTTP route comes from `@HttpTrigger(route = "orders/catalog")`, and the Azure Function name comes from `@FunctionName`.

Never allow untrusted requests to look up arbitrary functions:

~~~java
// Do not do this without an allowlist/authorization:
String definition =
        request.getQueryParameters().get("function");
catalog.lookup(definition);
~~~

For dynamic routing, enforce an allowlist of function names/types, authenticate callers, restrict permissions, and audit usage. Some SCF routing mechanisms evaluate expressions, making untrusted input validation even more critical.

## 11. Scope, Bean Lifecycle, and Concurrency on Azure

### 11.1. Spring Singletons vs. Azure Invocations

`@Service` and `@Component` default to singleton scope in a Spring context. An Azure Java Worker may reuse the context and handler across multiple invocations; Azure can also execute concurrently and scale out across multiple worker instances.

- `OrderService` in the demo is **stateless**.
- `pipeline` is stored in a `final` field, and the underlying functions/services must also be thread-safe under concurrency.
- Never store request bodies, trace IDs, tokens, or `ExecutionContext` in mutable fields on the handler.
- A Spring singleton is not durable shared state across multiple Azure instances.
- For real state, use an appropriate database/queue/store with proper transaction and concurrency strategies.

Incorrect example:

~~~java
@Service
class UnsafeService {

    private String lastOrderId;

    String normalize(String id) {
        lastOrderId = id.strip();
        return lastOrderId;
    }
}
~~~

When concurrent invocations run, the field can be overwritten. This is an anti-pattern; never put it into production code.

### 11.2. ExecutionContext Belongs to Each Invocation

`ExecutionContext` is created by the Azure runtime and is suited for reading the invocation ID and logger:

~~~java
context.getLogger().info(
        "Invocation: " + context.getInvocationId());
~~~

Do not inject `ExecutionContext` into the constructor of a Spring singleton. SCF provides `AzureFunctionUtil.enhanceInputIfNecessary(...)` to add context to a `Message<?>` header when a function truly has a message-aware contract. However, when business logic does not need Azure metadata, keeping `ExecutionContext` in the handler makes the function easier to reuse.

### 11.3. Cold Start and the Dependency Graph

Initializing the Spring application context inside the Azure Worker can increase **cold start latency**, especially with many starters/auto-configurations or bean constructors performing blocking I/O.

1. Include only necessary dependencies on the classpath.
2. Never create a new Spring context per invocation.
3. Never run workflows or emit events from constructors.
4. Manage HTTP/database clients with proper lifecycles and thread safety.
5. Measure startup time, memory, and latency on the target hosting plan.
6. Distinguish bean initialization failures from business errors after the handler is invoked.

## 12. Injecting Configuration and External Dependencies

A service may require thresholds, repositories, API clients, or secrets. Use Spring DI and Azure App Settings/managed identities rather than hard-coding configuration values inside the Azure handler.

### 12.1. Replacing Thresholds with Configuration

Variant of `OrderService` (replaces the earlier constructor/logic; **do not create two beans with the same name**):

~~~java
@Service
public class OrderService {

    private final long priorityThreshold;

    public OrderService(
            @Value("${orders.priority-threshold:1000000}")
            long priorityThreshold) {
        this.priorityThreshold = priorityThreshold;
    }

    // The parse/classify methods shown in Section 4
    // should use priorityThreshold instead of the constant 1_000_000.
}
~~~

Requires importing `org.springframework.beans.factory.annotation.Value`. This variant only demonstrates configuration injection and is **not a standalone complete class to copy as-is**. In `application.properties`:

~~~properties
orders.priority-threshold=1000000
~~~

On Azure, use Function App settings to provide environment-specific configuration. When relying on environment variable naming conventions, verify that Spring Boot binds the expected value on your release train before depending on it.

### 12.2. Does a Service Depending on a Repository Need the Catalog?

No. Repositories and HTTP clients can be regular Spring beans:

~~~java
@Service
class OrderAuditService {

    private final AuditRepository repository;

    OrderAuditService(AuditRepository repository) {
        this.repository = repository;
    }

    void record(OrderDecision decision) {
        repository.save(decision);
    }
}
~~~

This is **design pseudocode**; define an actual `AuditRepository`/`save(...)` if adding it to a project. `FunctionCatalog` manages `Supplier`/`Function`/`Consumer` functions; services and repositories continue to use standard Spring DI.

### 12.3. Secrets and Access Permissions

- Never commit `local.settings.json` containing real connection strings or tokens.
- Use Azure App Settings, managed identities/Key Vault, or an appropriate secrets manager.
- Never include function keys in logs or response bodies.
- Do not confuse **being able to inject a service** with **having runtime permissions to Azure Storage/Databases**.
- Configure permissions, connections, and retries for each adapter and external service.


## 13. Reusing the Service and Catalog from a Queue Trigger

The two HTTP endpoints in Section 7 compare two injection styles. Yet the same **`OrderService`** and `parseOrder|routeOrder` composition can be invoked by an Azure Storage Queue Trigger without duplicating business rules.

Example **additional method** on `OrderAzureHandler`:

~~~java
@FunctionName("classifyQueuedOrder")
public void classifyQueuedOrder(
        @QueueTrigger(
                name = "order",
                queueName = "orders-input",
                connection = "AzureWebJobsStorage")
        String rawOrder,

        @QueueOutput(
                name = "decision",
                queueName = "orders-decisions",
                connection = "AzureWebJobsStorage")
        OutputBinding<String> output,

        ExecutionContext context) {

    OrderDecision decision = pipeline.apply(rawOrder);

    output.setValue(
            decision.id() + "|"
            + decision.lane() + "|"
            + decision.totalVnd());
}
~~~

Add imports:

~~~java
import com.microsoft.azure.functions.OutputBinding;
import com.microsoft.azure.functions.annotation.QueueOutput;
import com.microsoft.azure.functions.annotation.QueueTrigger;
~~~

This method only runs with the Azure Storage extension, connection settings, source/target queues, and matching package metadata. It is an **optional extension**, not needed for the two HTTP routes of the main demo.

### 13.1. Differences in Error Semantics

In the HTTP handler, `IllegalArgumentException` is converted into **HTTP 400** for the caller. With a Queue Trigger, if an exception is thrown from the pipeline, the Azure Functions Host/extension handles retries and poison-message routing per configuration. Therefore:

- Do not catch every exception, only log it, and return normally (`void`) if you expect Azure to retry.
- Validation-invalid data usually cannot be fixed by infinite retries; configure intentional quarantine/dead-letter/poison-message handling.
- `OutputBinding.setValue(...)` only sets the binding value; it does not guarantee a distributed transaction with database writes inside the service.
- Messages can be redelivered; use event IDs/business keys to prevent duplicate side effects.
- If queue messages arrive as JSON or CloudEvents, decode them properly at the **adapter boundary** before invoking `Function<String,OrderDecision>`.

### 13.2. When to Use Supplier or Consumer?

A `Supplier<OrderCommand>` can be invoked by a Timer Trigger to fetch data, but a **Supplier does not create a Timer schedule on its own**. A `Consumer<OrderDecision>` can call `OrderAuditService` to record an audit entry when a Queue Trigger fires, but a **Consumer does not return a response**. For HTTP request/reply, the handler must invoke a function/service that produces a result or explicitly build a response.

~~~java
@Bean
Consumer<OrderDecision> auditDecision(
        OrderAuditService audit) {
    return audit::record;
}
~~~

This is a variant depending on `OrderAuditService` defined in Section 12, not an extra bean required for the minimal demo. The composition `parseOrder|routeOrder|auditDecision` becomes a **`Consumer<String>`**, no longer a `Function<String,OrderDecision>`.

## 14. Packaging and Bootstrapping the Spring Context on Azure

Spring injection succeeding in `@SpringBootTest` **does not guarantee** the Azure Functions Host will discover the function. The Azure plugin must generate binding metadata `function.json` from Java annotations and build the proper package layout.

### 14.1. Specifying the Main Class

With Maven:

~~~xml
<properties>
    <java.version>17</java.version>
    <start-class>example.azure.AzureOrderApplication</start-class>
</properties>
~~~

You can set `MAIN_CLASS=example.azure.AzureOrderApplication` in local/Azure application settings. The adapter can look up the main class from the manifest if unspecified, but setting it explicitly removes ambiguity when multiple Spring Boot configurations exist on the classpath.

### 14.2. Maven Plugin Configuration

This is a **fragment** to combine with a POM that has an appropriate Boot parent and Cloud BOM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <configuration>
                <skip>true</skip>
            </configuration>
        </plugin>
        <plugin>
            <groupId>com.microsoft.azure</groupId>
            <artifactId>azure-functions-maven-plugin</artifactId>
            <version>1.22.0</version>
            <configuration>
                <appName>orders-functions-unique-demo</appName>
                <resourceGroup>orders-example-rg</resourceGroup>
                <region>eastasia</region>
                <hostJson>src/main/resources/host.json</hostJson>
                <runtime>
                    <os>linux</os>
                    <javaVersion>17</javaVersion>
                </runtime>
                <appSettings>
                    <property>
                        <name>FUNCTIONS_EXTENSION_VERSION</name>
                        <value>~4</value>
                    </property>
                </appSettings>
            </configuration>
            <executions>
                <execution>
                    <id>package-functions</id>
                    <goals>
                        <goal>package</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

`1.22.0` is the Azure Maven plugin version cited by Spring Cloud Function docs as a **reference minimum**, not the latest version. Update the app name, resource group, and region, and verify the runtime, hosting plan, and Azure Java SDK/library before deploying.

**Why disable Boot repackaging?** The Azure Java Worker expects the layout generated by the Azure plugin; a default **Spring Boot repackaged executable fat JAR** does not match that layout. If using a different packaging approach, follow the adapter guide for your target version.

### 14.3. host.json and local.settings.json

Simple `src/main/resources/host.json`:

~~~json
{
  "version": "2.0"
}
~~~

`local.settings.json` for development:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "FUNCTIONS_EXTENSION_VERSION": "~4",
    "MAIN_CLASS": "example.azure.AzureOrderApplication",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
~~~

`UseDevelopmentStorage=true` typically requires **Azurite** when the Azure Host or triggers use the Storage emulator. Never commit files containing real credentials. In the cloud, use Function App settings, managed identities, and secrets management per operational policy.

### 14.4. Packaging and Running Locally

~~~bash
./mvnw clean package
./mvnw azure-functions:run
~~~

With Gradle when the Azure Functions plugin and runtime configuration are in place:

~~~bash
./gradlew azureFunctionsPackage
./gradlew azureFunctionsRun
~~~

The Azure Host must recognize **`classifyByService`** and **`classifyByCatalog`** as two separate function definitions. If not, inspect the Azure plugin output, annotation scanning, and `function.json`, not just Spring component scan logs.

Deployment commands like `./mvnw azure-functions:deploy` can alter cloud resources and incur costs. This lesson only explains the workflow and does not run deployments or builds in STEP 4.

## 15. Troubleshooting: Distinguishing Three Error Layers

| Symptom | Likely Layer | How to Diagnose |
| --- | --- | --- |
| Azure Host does not list the handler | **Azure discovery/package** | Check `@FunctionName`, trigger, `public` method, Azure Maven/Gradle plugin, and `function.json`. |
| Host lists the function but does not handle HTTP | **Azure route/auth** | Check POST, URL prefix, function key, and host/runtime settings. |
| Handler constructor is not managed by Spring | **Adapter/DI** | Check `@Component`, `spring-cloud-function-adapter-azure`, main class, and Java Worker integration. |
| `NoSuchBeanDefinitionException` for `OrderService` | **Spring component scanning** | Check `@Service` and package `example.azure`. |
| `NoSuchBeanDefinitionException` for `FunctionCatalog` | **SCF context** | Check adapter version, dependencies, Boot/Cloud BOM, and auto-configuration. |
| `catalog.lookup("parseOrder|routeOrder")` returns null | **Catalog registration** | Check `@Bean` names, definition, and generic input/output types. |
| Ambiguity when injecting multiple `Function<String,String>` | **Spring bean resolution** | Use `@Qualifier` or design distinct bean types. |
| HTTP 400 despite seemingly valid input | **Input contract** | Check `|` delimiter, whitespace, numeric parsing, and validation. |
| `ClassCastException` invoking composition | **Type conversion** | Check SCF wrappers, generic signatures, serialized payloads, and catalog tests. |
| Spring test PASSES but Azure Worker fails | **Packaging/runtime** | Check JAR layout, main class, Java target, and dependencies. |
| Slow cold start | **Application context** | Trim unneeded starters, avoid I/O during bean creation, measure startup. |
| Queue event processed repeatedly | **Delivery/retry semantics** | Check idempotency key and Queue Trigger poison/retry policy. |
| Data from two requests gets mixed | **Concurrency** | Remove mutable fields from singleton services/handlers. |
| `@Bean Function` exists but no HTTP endpoint appears | **Azure annotation** | `@Bean` does not create `@FunctionName` or `@HttpTrigger`. |

### 15.1. Recommended Investigation Order

1. Did the Azure Maven/Gradle plugin generate metadata for both `@FunctionName` methods?
2. Did the Azure Host discover the right method names, triggers, and routes?
3. Is the Spring adapter on the runtime classpath and are all versions compatible?
4. Is `AzureOrderApplication` selected properly as the main class?
5. Did Spring scan the service, function configuration, and handler?
6. Did the constructor inject `OrderService` and `FunctionCatalog`?
7. Does the catalog hold both functions and is the composition type-compatible?
8. Are HTTP body, output, security, retries, and environment settings configured properly?

Following this order prevents confusing **Azure discovery**, **Spring dependency injection**, **SCF function lookup**, and **business validation**.

## 16. Practice Exercises and Self-Assessment Questions

### Exercises

1. **Change rules:** move the priority order threshold into Spring configuration; verify both endpoints return the same result.
2. **Add a function:** create `Function<OrderDecision,String> formatDecision`, compose `parseOrder|routeOrder|formatDecision`, and compare the output with the handler's response builder.
3. **Simulate dependency failure:** temporarily remove `@Service` from `OrderService`, run the Spring context test, and explain the root cause.
4. **Simulate naming failure:** change the composition to `parseOrder|missingRoute` and verify fail-fast behavior in the constructor.
5. **Qualifiers:** create two `Function<String,String>` beans, test injecting without a qualifier, then add `@Qualifier`.
6. **Queue reuse:** add the `classifyQueuedOrder` method and verify input validation, retries, idempotency, and the output binding.
7. **Concurrency:** temporarily add a mutable field to the service, send concurrent requests, and refactor it back to stateless.
8. **Infrastructure failure:** add a service calling an external API and design bounded retries/backoff and response mapping.
9. **Inspect the Azure package:** locate `function.json` for both routes and compare Azure metadata with Spring bean definitions.
10. **Switch text to JSON:** isolate serialization/validation inside the handler while keeping the service free of Azure SDK dependencies.

### Self-Assessment

- Why isn't `@Service OrderService` automatically registered by name in `FunctionCatalog`?
- Why can the same handler inject both a regular service and the catalog?
- What is the difference between injecting a function bean directly vs. calling `catalog.lookup("parseOrder")`?
- Why is `parseOrder|routeOrder` valid whereas `routeOrder|parseOrder` is not a type-safe composition?
- Why must you never call `SpringApplication.run(...)` on every invocation?
- When does Azure supply `ExecutionContext`, and why should it not be stored in a singleton?
- When Spring tests PASS but the Azure Host does not see the function, which layer must you investigate?
- For a Queue Trigger, why does catching every exception and returning normally lose retry behavior?
- Why should clients never be allowed to specify arbitrary function lookup names via query parameters?
- How do you reuse the same `OrderService` across HTTP, Queue, and other serverless platforms without leaking Azure APIs into the domain layer?

## 17. Official References

- [Spring Cloud Function — Microsoft Azure Functions](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html): `@Component`, injected services, `FunctionCatalog`, Azure Java Worker, main class, and packaging.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer`, catalog wrapping, composition, and type conversion.
- [Microsoft Learn — Azure Functions Java Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java): `@FunctionName`, `FunctionInstanceInjector`, Java triggers/bindings, and runtime.
- [Microsoft Learn — Azure HTTP Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-http-webhook-trigger): HTTP requests/responses, routes, authorization levels.
- [Microsoft Learn — Run Functions Locally](https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local): Functions Core Tools and local testing.
- [Microsoft Learn — Azure Functions Java Quickstart](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-java): Maven package/run/deploy and metadata.
- [Microsoft Learn — Azure Storage Queue Trigger](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger): retries, poison queues, and semantics differing from HTTP.
- [Spring Cloud Function Azure samples](https://github.com/spring-cloud/spring-cloud-function/tree/main/spring-cloud-function-samples): HTTP/Blob/Timer examples and adapter variants.

**Conclusion:** Spring dependency injection allows Azure handlers to call **standard business services**, while `FunctionCatalog` provides a way to invoke **`Supplier`, `Function`, and `Consumer` beans by name or composition**. Keep business logic inside services, expose transformations as function beans when needed, and inject the service/catalog into a `@Component` containing `@FunctionName` methods. Separating DI, function lookup, and Azure triggers/bindings enables reusing the same logic across HTTP, event streams, and serverless runtimes while controlling data types, bean lifecycles, retries, idempotency, and security.
