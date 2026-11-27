# Bean Naming and Dependency Injection

In **SPRING_CLOUD_FUNCTION**, a **Supplier<T>**, **Function<T, R>**, or **Consumer<T>** is typically registered as a Spring bean. The bean name lets **FunctionCatalog** identify which logic to run; **dependency injection (DI)** supplies the logic with repositories, services, configuration, and supporting components without creating them manually. Together, these two mechanisms determine whether a function can be discovered, tested, and reused consistently across HTTP, events, or serverless environments.

This lesson belongs to the **Function Model** chapter. The focus is on naming beans clearly, declaring and injecting dependencies properly, distinguishing bean names from Java class/method names, selecting functions in multi-bean applications, and avoiding pitfalls around lifecycles, circular dependencies, or shared state.

## 1. What Is a Spring Bean in the Function Model?

A **Spring bean** is an object managed by the Spring application context. A bean can be:

- **Business bean**: a quote calculation service, repository, configuration accessor, or data normalizer.
- **Functional bean**: an object implementing **Supplier<T>**, **Function<T, R>**, or **Consumer<T>**.
- **Infrastructure bean**: a message converter, clock, HTTP client, or other supporting component.

A Java object created solely with **new** does not automatically become a Spring bean. When a bean is registered, Spring knows how to instantiate it, wire its dependencies, and manage its lifecycle.

~~~mermaid
flowchart LR
    A["PriceBook (bean)"] --> B["QuoteService (bean)"]
    B --> C["createQuote (Function bean)"]
    D["Spring ApplicationContext"] -. "instantiate and inject" .-> A
    D -. "instantiate and inject" .-> B
    D -. "instantiate and inject" .-> C
    C --> E["FunctionCatalog"]
    E --> F["HTTP / Stream / Serverless adapter"]
~~~

Spring Cloud Function focuses on **functional beans**: locating beans of the appropriate types, registering them in **FunctionCatalog**, and letting adapters invoke them by the selected name. Stable naming and controlled dependencies from bean construction onward keep business processing independent of protocols.

## 2. Naming Beans with @Bean

With Java configuration, **@Bean** registers a method's return value as a bean:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class SimpleFunctions {

    @Bean
    Function<String, String> normalizeCode() {
        return input -> input.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

When no explicit name is given, the default bean name is **normalizeCode**, matching the **@Bean** method name. Once the application context contains this bean, Spring Cloud Function can register the name **normalizeCode** in FunctionCatalog.

You can specify an explicit name using the annotation's argument:

~~~java
@Bean("productCodeNormalizer")
Function<String, String> normalizeCode() {
    return input -> input.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

With this declaration:

- **Java method name**: **normalizeCode**.
- **Registered bean name**: **productCodeNormalizer**.
- **Name used to select the function in FunctionCatalog/adapters**: **productCodeNormalizer**.

**Do not infer endpoint or function names from the class containing @Bean.** The registered bean name itself is the identifier matched against Spring Cloud Function configuration.

Spring also allows declaring multiple names for a bean, e.g., **@Bean({"productCodeNormalizer", "normalizeAlias"})**: the first is the primary name, and subsequent ones are aliases at the Spring container level. However, when relying on aliases for FunctionCatalog or adapter exposure, test alias lookup on the target library version. In documentation and deployment configurations, prefer **one clear primary name**.

## 3. Practical Example: Exposing a Quote Service as a Function

Suppose an application receives a request containing a product code and quantity. **PriceBook** is the system-managed unit price source; **QuoteService** validates the request and computes the total. The **createQuote** bean exposes the service logic as a function callable by Spring Cloud Function.

Input and output:

~~~text
QuoteRequest(requestId, sku, quantity)
             |
             v
     Function<QuoteRequest, Quote>
             |
             v
Quote(requestId, sku, quantity, unitPrice, total)
~~~

Java 17+ code example in a single file **NamedFunctionsApplication.java**:

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NamedFunctionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(NamedFunctionsApplication.class, args);
    }

    // DTOs for the function contract.
    public record QuoteRequest(
        String requestId,
        String sku,
        int quantity
    ) {}

    public record Quote(
        String requestId,
        String sku,
        int quantity,
        BigDecimal unitPrice,
        BigDecimal total
    ) {}

    // Example in-memory price source.
    public static final class PriceBook {
        private final Map<String, BigDecimal> prices;

        public PriceBook(Map<String, BigDecimal> prices) {
            this.prices = Map.copyOf(prices);
        }

        public BigDecimal priceOf(String sku) {
            BigDecimal price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException(
                    "Unknown SKU: " + sku);
            }
            return price;
        }
    }

    // Business service, unaware of HTTP or brokers.
    public static final class QuoteService {
        private final PriceBook priceBook;

        public QuoteService(PriceBook priceBook) {
            this.priceBook = priceBook;
        }

        public Quote quote(QuoteRequest request) {
            if (request == null
                    || request.requestId() == null
                    || request.requestId().isBlank()
                    || request.sku() == null
                    || request.sku().isBlank()
                    || request.quantity() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            String sku = request.sku()
                .trim().toUpperCase(Locale.ROOT);
            BigDecimal unitPrice = priceBook.priceOf(sku);
            BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
            );

            return new Quote(
                request.requestId(),
                sku,
                request.quantity(),
                unitPrice,
                total
            );
        }
    }

    @Bean
    PriceBook priceBook() {
        return new PriceBook(Map.of(
            "BOOK", new BigDecimal("85000"),
            "PEN", new BigDecimal("12000")
        ));
    }

    @Bean
    QuoteService quoteService(PriceBook priceBook) {
        return new QuoteService(priceBook);
    }

    // Method name is quoteFromService;
    // official Function bean name is createQuote.
    @Bean("createQuote")
    Function<QuoteRequest, Quote> quoteFromService(
            QuoteService quoteService) {
        return quoteService::quote;
    }

    @Bean("renderQuote")
    Function<Quote, String> renderQuote() {
        return quote -> quote.requestId() + ":"
            + quote.total().toPlainString();
    }
}
~~~

Here, Spring creates **PriceBook**, passes it to **QuoteService**, and injects **QuoteService** into the Function bean factory method. **createQuote** never calls **new QuoteService(...)** itself and does not need to know how **PriceBook** is built.

When calling **createQuote** with:

~~~json
{
  "requestId": "REQ-001",
  "sku": "book",
  "quantity": 3
}
~~~

the business result is:

~~~json
{
  "requestId": "REQ-001",
  "sku": "BOOK",
  "quantity": 3,
  "unitPrice": 85000,
  "total": 255000
}
~~~

**PriceBook** in this lesson is only in-memory sample data. In production systems, prices must come from an authoritative source with effective-date policies and explicit currency/rounding rules. The Function contract does not replace those business requirements.

## 4. How Does Dependency Injection Work?

In the example, **Spring** resolves dependencies based on the parameter types of **@Bean** methods:

~~~java
@Bean
QuoteService quoteService(PriceBook priceBook) {
    return new QuoteService(priceBook);
}

@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService(
        QuoteService quoteService) {
    return quoteService::quote;
}
~~~

Spring understands that a **PriceBook** bean is needed before constructing **QuoteService**. Likewise, **QuoteService** is needed before creating the **createQuote** bean.

~~~mermaid
flowchart LR
    A["@Bean PriceBook"] --> B["@Bean QuoteService(PriceBook)"]
    B --> C["@Bean createQuote(QuoteService)"]
    C --> D["FunctionCatalog: createQuote"]
    D --> E["apply(QuoteRequest)"]
~~~

There are three common ways to inject dependencies:

| DI Approach | Example | Assessment |
| --- | --- | --- |
| **Constructor injection** | **QuoteService(PriceBook priceBook)** | Preferred for required dependencies; easy to instantiate for tests |
| **@Bean method parameters** | **quoteFromService(QuoteService service)** | Ideal when declaring a Function from an existing service |
| **Field injection** | **@Autowired private PriceBook priceBook** | Usable, but makes dependencies less explicit and harder to test directly |

For a class with a single constructor, Spring automatically uses that constructor for dependency injection without requiring **@Autowired**. **@Bean** methods can also declare parameters for Spring to supply. Beans do not have to appear in creation order within the Java file; Spring resolves them using the dependency graph.

### Why Is DI Better Than Creating Dependencies Inside the Function?

Example to avoid:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteWithHiddenDependency() {
    QuoteService service = new QuoteService(
        new PriceBook(Map.of("BOOK", new BigDecimal("85000")))
    );
    return service::quote;
}
~~~

This code hardcodes how **PriceBook** is constructed inside the Function. When a real repository, cache, tracing, pricing configuration, or test mock is needed, you would have to edit the Function factory method directly.

DI lets you swap **PriceBook** or **QuoteService** at the configuration boundary, separating object construction from the **QuoteRequest → Quote** transformation responsibility.

**Note:** the example above uses **@Bean** receiving dependencies; it can just as easily accept Spring-managed repositories, gateways, or clients. You do not have to declare every dependency as a top-level class if a small configuration bean suffices.

## 5. Constructor Injection with @Component

Beyond **@Bean** methods, you can create a class implementing **Function** and annotate it with **@Component**.

Example of a separate class in the **example.function** package:

~~~java
package example.function;

import java.util.function.Function;
import org.springframework.stereotype.Component;

@Component("createQuote")
public final class CreateQuoteFunction
        implements Function<
            NamedFunctionsApplication.QuoteRequest,
            NamedFunctionsApplication.Quote> {

    private final NamedFunctionsApplication.QuoteService service;

    public CreateQuoteFunction(
            NamedFunctionsApplication.QuoteService service) {
        this.service = service;
    }

    @Override
    public NamedFunctionsApplication.Quote apply(
            NamedFunctionsApplication.QuoteRequest request) {
        return service.quote(request);
    }
}
~~~

Spring detects **@Component("createQuote")** if the class lies within component scan scope and passes **QuoteService** into its constructor. This class is still a Function named **createQuote**, serving the same role as the **@Bean("createQuote")** method.

**Choose one of the two registration forms.** When using **@Component("createQuote")**, remove the corresponding **@Bean("createQuote")** method from the main example. Keeping both can cause duplicate bean name errors or behavior relying on bean overriding, which should not be used as an implementation-selection mechanism.

If no name is specified on **@Component**, the default bean name is derived from the class name per Spring rules (for example, **CreateQuoteFunction → createQuoteFunction**). For names referenced by adapters or API docs, explicit naming reduces reliance on naming conventions.

## 6. Distinguishing Class Name, Method Name, Bean Name, and Function Definition

In the main example, four concepts can have different values:

| Concept | Example Value | Purpose |
| --- | --- | --- |
| Configuration class name | **NamedFunctionsApplication** | Java code organization |
| Bean factory method name | **quoteFromService** | Java factory method definition |
| Functional bean name | **createQuote** | Identifier in Spring container and FunctionCatalog |
| Function definition | **createQuote** | Selects the function or chain for adapters to use |

Select the function via configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote
~~~

Do not use **quoteFromService** as the definition when the bean has been explicitly named **createQuote**. Sharing the word "quote" does not make the framework infer an alias relationship.

In an application with multiple Functions, Suppliers, or Consumers, explicitly configuring **spring.cloud.function.definition** prevents adapters from guessing which function to expose or bind.

Renaming a bean changes an **integration identifier**: HTTP configurations, event bindings, compositions, or serverless handlers may still reference the old name. For deployed projects, treat renaming a function as an operational contract change and verify all consumers.

## 7. Looking Up Functional Beans via FunctionCatalog

Spring Cloud Function manages functional bean lookup through **FunctionCatalog**. A Spring class can receive the catalog via constructor injection and invoke functions by name.

~~~java
package example.function;

import java.util.function.Function;

import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class QuoteInvoker {
    private final FunctionCatalog catalog;

    public QuoteInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public NamedFunctionsApplication.Quote run(
            NamedFunctionsApplication.QuoteRequest request) {

        Function<
            NamedFunctionsApplication.QuoteRequest,
            NamedFunctionsApplication.Quote> function =
                catalog.lookup("createQuote");

        if (function == null) {
            throw new IllegalStateException(
                "Function 'createQuote' not found");
        }

        return function.apply(request);
    }
}
~~~

Here, **QuoteInvoker** receives **FunctionCatalog** from Spring; the catalog looks up the bean registered under **createQuote**. If the name is wrong or the bean is unregistered, **lookup(...)** will not return the desired function.

The object returned from the catalog may be **wrapped by the framework to support conversion, composition, and message handling**. Do not cast it to a concrete class like **CreateQuoteFunction** or assume object identity with the original bean.

**Distinguish two types of DI:**

- Injecting **QuoteService** into a Function bean: supplies dependencies to **business logic**.
- Injecting **FunctionCatalog** into an adapter or orchestrator: supplies a mechanism to **select logic by name**.

Both complement each other. Small applications may invoke injected Function beans directly; components requiring dynamic lookup by definition typically use FunctionCatalog.

## 8. Multiple Beans of the Same Type: @Qualifier and @Primary

When an application has multiple beans of the same type, type-based DI alone can become ambiguous.

Suppose we add another way to expose the same QuoteService in the main example:

~~~java
@Bean("previewQuote")
Function<QuoteRequest, Quote> previewQuote(QuoteService service) {
    return service::quote;
}
~~~

Now there are at least two beans of type **Function<QuoteRequest, Quote>**:

~~~text
createQuote  : Function<QuoteRequest, Quote>
previewQuote : Function<QuoteRequest, Quote>
~~~

If another class needs to directly inject **one** Function of this type, add **@Qualifier**:

~~~java
package example.function;

import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
public class QuoteUseCase {

    private final Function<
        NamedFunctionsApplication.QuoteRequest,
        NamedFunctionsApplication.Quote> calculator;

    public QuoteUseCase(
            @Qualifier("createQuote")
            Function<
                NamedFunctionsApplication.QuoteRequest,
                NamedFunctionsApplication.Quote> calculator) {
        this.calculator = calculator;
    }

    public NamedFunctionsApplication.Quote execute(
            NamedFunctionsApplication.QuoteRequest input) {
        return calculator.apply(input);
    }
}
~~~

**@Qualifier("createQuote")** selects a specific bean in Spring DI; **spring.cloud.function.definition=createQuote** selects a function for Spring Cloud Function's integration layer.

**@Primary** can help Spring choose a default candidate during type-based injection when multiple matching beans exist. However, **@Primary does not replace function definition** and should not be relied on to determine which endpoint/binding gets selected.

### Handling Multiple Implementations

| Situation | Resolution |
| --- | --- |
| Two services with the same interface injected into one class | Use **@Qualifier**, or **@Primary** if a genuine default exists |
| Multiple Functions with identical generic input/output | Name beans clearly; use **@Qualifier** when injecting directly |
| Adapter needs to expose exactly one Function | Configure **spring.cloud.function.definition** |
| Want to select an implementation by environment | Use profiles/conditional beans carefully, and verify which bean is registered |
| Need to run two Functions sequentially | Use composition, ensuring output/input compatibility |

**Do not equate bean names with Java variable names.** Naming a constructor parameter **createQuote** does not guarantee resolving ambiguity in all cases; explicit qualifiers are clearer, especially during project refactoring.

## 9. Composition Depends on Bean Names and Type Contracts

With **createQuote** and **renderQuote** from the main example, you can configure:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote|renderQuote
~~~

This represents the pipeline:

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["createQuote"]
    B --> C["Quote"]
    C --> D["renderQuote"]
    D --> E["String"]
~~~

The first step accepts **QuoteRequest** and returns **Quote**; the second accepts **Quote** and returns **String**. The result for the illustrative request is the string **REQ-001:255000**.

Spring Cloud Function can look up a composed definition via the catalog:

~~~java
Function<
    NamedFunctionsApplication.QuoteRequest,
    String> pipeline =
        catalog.lookup("createQuote|renderQuote");

if (pipeline == null) {
    throw new IllegalStateException("Pipeline not found");
}

String text = pipeline.apply(
    new NamedFunctionsApplication.QuoteRequest(
        "REQ-001", "BOOK", 3
    )
);
// "REQ-001:255000"
~~~

This snippet assumes a context where Spring injects **FunctionCatalog catalog** along with required imports; it is not a standalone Java file.

**Key rule:** names in composition must be valid bean names, and the output type of each step must be compatible with the input type of the next step. Dependency injection gives each bean the services it needs, but **it does not automatically resolve** chaining two incompatible data types.

If the **renderQuote** bean is renamed to **formatQuote**, the pipeline configuration must also change. This is why functional bean names should be treated as part of the deployment contract.

## 10. HTTP: Bean Names Determine Which Function Is Exposed

With the Spring Cloud Function Web adapter, you can use the Maven starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

The application requires compatible Spring Boot/Spring Cloud versions and appropriate web configuration. When selecting:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote
~~~

and running the application on the default port **8080**, you can invoke:

~~~bash
curl -i -X POST http://localhost:8080/createQuote \
  -H "Content-Type: application/json" \
  -d '{"requestId":"REQ-001","sku":"book","quantity":3}'
~~~

The adapter converts JSON into **QuoteRequest**, looks up **createQuote**, and invokes **apply(request)**. The resulting **Quote** can be serialized into JSON.

~~~text
HTTP POST /createQuote
  -> JSON conversion
  -> FunctionCatalog.lookup("createQuote")
  -> createQuote.apply(QuoteRequest)
  -> Quote
  -> HTTP response
~~~

**URL paths, function selection rules, and error mappings** are governed by the adapter, so verify the actual configuration. An **IllegalArgumentException** from QuoteService does not automatically guarantee HTTP 400 across all versions or configurations. **QuoteService.quote(...)** logic should stay independent of controllers, request headers, or response codes.

You do not need to inject **HttpServletRequest** into QuoteService just to share the same logic across HTTP and brokers. Business dependencies like price repositories or clocks can still be injected normally; per-call metadata should be passed through appropriate inputs/messages.

## 11. Spring Cloud Stream: Same Bean, Different Binding Names

With **Spring Cloud Stream** and a suitable binder, the same **createQuote** bean can consume an event and emit results through a broker:

~~~yaml
spring:
  cloud:
    function:
      definition: createQuote
    stream:
      bindings:
        createQuote-in-0:
          destination: quote-requests
        createQuote-out-0:
          destination: quote-results
~~~

- **createQuote-in-0** is the input binding of the **createQuote** Function.
- **createQuote-out-0** is the output binding.
- **destination** is the logical target name; the application also requires a binder, broker, and connection configuration.
- **QuoteService** and **PriceBook** are still injected by Spring during bean creation, regardless of where messages originate.

~~~mermaid
flowchart LR
    A["Broker: quote-requests"] --> B["Stream binder"]
    B --> C["createQuote bean"]
    D["QuoteService + PriceBook"] --> C
    C --> E["Broker: quote-results"]
~~~

When using **composition**, binding names and naming rules may depend on the composed definition string and library version; do not assume **createQuote-in-0/out-0** stays unchanged without verifying after changing the definition.

**Side effects and retries** remain separate concerns. Even when beans have proper DI, brokers can redeliver events and environments run multiple instances. If logic writes data or calls external systems, idempotency and transactions are needed at the appropriate layer. Replacing **@Bean** with **@Component** does not change message delivery semantics.

## 12. Serverless: Dependency Injection and Execution Lifecycle

When packaging Spring Cloud Function for a serverless environment, the runtime adapter receives an event, selects the function bean, and invokes it. The code:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService(
        QuoteService quoteService) {
    return quoteService::quote;
}
~~~

still uses Spring's DI model; business code does not need to recreate services on every invocation.

However, serverless instance lifecycles depend on the platform: the application may be reinitialized, reused across invocations, or run concurrently across multiple instances. Never treat a field inside a singleton bean as storage for long-lived business state.

Verify **handler**, packaging, dependencies, triggers, permissions, and function-name selection rules for the adapter in use. The catalog name **createQuote** is part of the configuration, though not every serverless platform automatically uses it as the public handler name.

## 13. Bean Lifecycle and Thread Safety

By default, most Spring application beans are **singletons within an application context**. The **createQuote** bean and injected services may be reused across many invocations. Therefore:

- Prefer **stateless services** and immutable DTOs/records.
- Do not store the current request in a field of QuoteService.
- Do not rely on singleton memory to coordinate across replicas.
- For stateful client or repository dependencies, respect that component's thread-safety contract.

Example to avoid:

~~~java
public final class UnsafeQuoteService {
    private String lastRequestId; // Shared mutable state.

    public void remember(String requestId) {
        lastRequestId = requestId;
    }

    public String lastRequestId() {
        return lastRequestId;
    }
}
~~~

If multiple HTTP requests or messages are processed concurrently, the field can be overwritten before another call finishes reading it. Constructor injection does not automatically make a mutable object thread-safe.

**Bean creation time also differs from function invocation time:**

~~~java
@Bean("currentTime")
java.util.function.Supplier<java.time.Instant> currentTime(
        java.time.Clock clock) {
    return clock::instant; // Invoked when Supplier.get() is triggered.
}
~~~

The Supplier bean is created during context startup; the timestamp is captured when **get()** executes. Conversely, if **clock.instant()** is called eagerly and a lambda returns that captured value, subsequent invocations will receive stale timestamps.

## 14. Common DI Mistakes

### 14.1. Calling a @Bean Method Directly to Obtain Dependencies

A mistake that easily appears during refactoring:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService() {
    QuoteService service = quoteService(priceBook());
    return service::quote;
}
~~~

This snippet invokes factory methods like regular Java methods. Container-related behavior may differ depending on class configuration (**@Configuration** proxying vs. **proxyBeanMethods = false**), and it obscures intent when the goal is simply dependency injection.

The clean approach is **receiving beans via parameters**:

~~~java
@Bean("createQuote")
Function<QuoteRequest, Quote> quoteFromService(
        QuoteService service) {
    return service::quote;
}
~~~

Spring supplies the exact managed bean. Do not rely on internal **@Bean** method calls as a primary DI mechanism.

### 14.2. Missing Dependency Bean

If a constructor or **@Bean** method requires **QuoteService**, but no matching bean exists in the application context, Spring usually cannot wire the dependency and will fail on startup.

Checklist:

1. Is there a **@Bean** or **@Component/@Service** registering QuoteService?
2. With **@Component**, is the class within Spring's component scan scope?
3. Is it excluded by **@Profile**, **@Conditional**, or environment configuration?
4. Are there multiple beans of the same type without **@Qualifier**?

### 14.3. Circular Dependencies

~~~text
ServiceA depends on ServiceB
ServiceB depends on ServiceA
~~~

Constructor injection exposes circular dependency designs; many Spring Boot applications reject circular references by default. Split responsibilities or extract shared logic into a third service. Avoid fixing this by arbitrarily switching everything to field injection or enabling circular references.

### 14.4. Duplicate Bean Names

If two methods both register **@Bean("createQuote")**, Spring may refuse to start when bean-definition overriding is disabled. Use distinct names or keep only one implementation per controlled profile.

### 14.5. Using @Primary to Select a Function for HTTP

**@Primary** helps Spring container DI choose among multiple candidates, but it does not replace Spring Cloud Function's function selection rules. When an application has multiple functions, configure **spring.cloud.function.definition** explicitly and test the corresponding endpoint or binding.

## 15. Naming Beans for Maintainable Code

Practical conventions:

| Topic | Suggestion | Example |
| --- | --- | --- |
| Function name | Use a verb describing the transformation | **createQuote**, **normalizeOrder** |
| Supplier name | Describe the data source | **loadConfiguration**, **generateHeartbeat** |
| Consumer name | Describe the handling action | **recordAudit**, **sendNotification** |
| Helper service name | Describe business responsibility | **QuoteService**, **PriceBook** |
| Name in configuration | Match bean name, stable across deployments | **spring.cloud.function.definition: createQuote** |
| Composition | Express left-to-right flow | **createQuote|renderQuote** |

There is no need to force a uniform technical prefix onto every bean name. Short, business-meaningful names aligned with endpoints, binders, or handlers make lookup and diagnostics easier for operators.

If a bean is renamed after deployment, audit all references: **application.yml**, binding configurations, integration docs, HTTP URLs, catalog lookup code, and tests. Bean names are part of the operational interface, even though Java method names can be safely refactored with an IDE.

## 16. Testing DI and Bean Names

You can test **business logic without Spring** by instantiating dependencies directly:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.Map;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class NamedFunctionsUnitTest {

    private final NamedFunctionsApplication.PriceBook book =
        new NamedFunctionsApplication.PriceBook(Map.of(
            "BOOK", new BigDecimal("85000")
        ));

    private final NamedFunctionsApplication.QuoteService service =
        new NamedFunctionsApplication.QuoteService(book);

    @Test
    void functionUsesInjectedService() {
        Function<
            NamedFunctionsApplication.QuoteRequest,
            NamedFunctionsApplication.Quote> fn =
                new NamedFunctionsApplication()
                    .quoteFromService(service);

        var quote = fn.apply(
            new NamedFunctionsApplication.QuoteRequest(
                "REQ-001", "book", 3
            )
        );

        assertEquals("BOOK", quote.sku());
        assertEquals(0,
            new BigDecimal("255000").compareTo(quote.total()));
    }

    @Test
    void invalidRequestDoesNotProduceQuote() {
        var fn = new NamedFunctionsApplication()
            .quoteFromService(service);

        assertThrows(IllegalArgumentException.class,
            () -> fn.apply(
                new NamedFunctionsApplication.QuoteRequest(
                    "REQ-002", "BOOK", 0
                )
            ));
    }
}
~~~

These two tests verify **QuoteService** and the Function object. They **do not prove** that Spring registered the expected bean name or injected dependencies inside an application context.

Add an integration test for that case. Example with **spring-boot-starter-test** and Spring Cloud Function on the test classpath:

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class FunctionRegistrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogFindsBeanByExplicitName() {
        assertNotNull(catalog.lookup("createQuote"));
        assertNotNull(catalog.lookup("renderQuote"));
    }
}
~~~

This test ensures the Spring context starts up and FunctionCatalog holds both required bean names. For fuller integration coverage, pass a **QuoteRequest** input through the looked-up function and assert the result; if using HTTP or Stream, add tests for JSON conversion, endpoints, or actual message bindings.

When only testing Java logic, unit tests suffice. When verifying **bean discovery, function names, DI, and adapters**, integration tests are indispensable.

## 17. Practice Exercises

**Exercise 1 — Default vs. explicit names.** Declare two Function beans of type **Function<String, String>**: name the first via the method name **normalizeSku**, and give the second **@Bean("normalizeExternalCode")** while naming the Java method **normalizeCode**. Predict which names appear in FunctionCatalog; write an integration test to verify.

**Exercise 2 — Constructor injection.** Create **InventoryService** with a **InventoryView getInventory(InventoryRequest request)** method and a dependency on **InventoryRepository**. Expose it via a **Function<InventoryRequest, InventoryView>** bean using a method reference, injecting the service through a **@Bean** parameter. Do not call **new InventoryRepository(...)** inside a lambda.

**Exercise 3 — Multiple beans of the same type.** Create **Function<OrderRequest, OrderResult>** beans named **validateOrder** and **validateOrderStrict**. Write a class using **@Qualifier("validateOrderStrict")** to inject the right implementation, then distinguish selecting with @Qualifier vs. **spring.cloud.function.definition**.

**Exercise 4 — Composition by name.** Write **Function<InventoryView, String> renderInventory**, compose it with **getInventory** using the definition **getInventory|renderInventory**. Explain why renaming a bean without updating the definition causes lookup to fail.

**Exercise 5 — Switching protocols.** Keep **QuoteService** and the **createQuote** bean unchanged. Configure the HTTP adapter to invoke via POST, then describe the input/output bindings needed when moving to Spring Cloud Stream. List the business dependencies injected by Spring and the settings belonging strictly to the adapter.

**Exercise 6 — Troubleshooting.** An application has two Function beans of the same type, a class injecting a Function without a qualifier, and **spring.cloud.function.definition** pointing to the Java method name instead of the **@Bean** name. Identify both independent errors, fix each one, and design an integration test for name registration.

### Key Takeaways

- **Bean names** are critical identifiers for Spring Cloud Function lookup and adapter function selection; **@Bean("name")** or **@Component("name")** fixes the name explicitly.
- **Dependency injection** supplies functions with required services, repositories, and configuration via constructors or **@Bean** parameters; business logic does not instantiate dependencies itself.
- **@Qualifier** and **@Primary** assist bean selection in Spring DI, whereas **spring.cloud.function.definition** selects a Function or Function chain for the integration layer.
- FunctionCatalog may wrap beans to support conversion and composition. Look up by exact name and test the real invocation path.
- Proper DI keeps the same business logic reusable across **HTTP, events, and serverless**; you must still manage thread safety, state, errors, and protocol boundaries.
