# Declaring Functions with Lambdas, Method References, and Implementation Classes

In **SPRING_CLOUD_FUNCTION**, business logic can be written as a **lambda expression**, a **method reference**, or a **class implementing a functional interface**. All three approaches produce beans of type **Supplier<T>**, **Function<T, R>**, or **Consumer<T>** for Spring Cloud Function to register in **FunctionCatalog**. Afterward, the same logic can be invoked via HTTP, process events via Spring Cloud Stream, or run using a suitable serverless adapter, provided the corresponding data contract and integration configuration are satisfied.

This lesson belongs to the **Function Model** chapter. The goal is to understand when to choose each declaration style, write properly typed Java code, maintain stable bean names, test independently of protocols, and avoid common pitfalls when an application contains multiple functions.

## 1. Three Ways to Write, One Functional Contract

Spring Cloud Function builds on the familiar functional interfaces from **java.util.function**:

| Interface | Core Method | Contract | Role |
| --- | --- | --- | --- |
| **Supplier<T>** | **T get()** | () → T | Generate or provide data |
| **Function<T, R>** | **R apply(T input)** | T → R | Transform data |
| **Consumer<T>** | **void accept(T input)** | T → void | Process data, typically with side effects |

Each interface has exactly one abstract method, so it can be expressed as a lambda or a method reference. A class can also **implement** the interface to provide an explicit implementation.

Plain Java example: the same code normalization expressed in three syntaxes.

~~~java
import java.util.Locale;
import java.util.function.Function;

public class ThreeWaysJavaDemo {
    static class CodeNormalizer {
        String normalize(String input) {
            return input.trim().toUpperCase(Locale.ROOT);
        }
    }

    static class NormalizeCodeFunction
            implements Function<String, String> {
        @Override
        public String apply(String input) {
            return input.trim().toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        // 1. Lambda expression
        Function<String, String> lambda =
            input -> input.trim().toUpperCase(Locale.ROOT);

        // 2. Method reference to an existing method
        CodeNormalizer normalizer = new CodeNormalizer();
        Function<String, String> reference = normalizer::normalize;

        // 3. Class implementing Function
        Function<String, String> implementation =
            new NormalizeCodeFunction();

        System.out.println(lambda.apply(" ab-12 "));         // AB-12
        System.out.println(reference.apply(" ab-12 "));      // AB-12
        System.out.println(implementation.apply(" ab-12 ")); // AB-12
    }
}
~~~

The three forms are equivalent in **purpose** but differ in code organization: a lambda defines logic inline; a method reference points to an existing method; an implementation class places the contract, dependencies, and **apply** method into a dedicated Java type.

**Key distinction:** the expression **normalizer::normalize** creates a function object to be invoked *later*, whereas **normalizer.normalize(input)** invokes the method immediately at the time the expression is evaluated. The two cannot be substituted for each other when declaring a bean.

## 2. Setting Up the Problem: Calculating a Quote from an Order Request

Consider an application that receives **orderId**, **quantity**, and **unitPrice**, then calculates **subtotal**. We want the same transformation to appear in three declaration styles so readers can see the differences in syntax and code structure.

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["Function<QuoteRequest, Quote>"]
    B --> C["Quote"]
    D["Lambda"] -.-> B
    E["Method reference"] -.-> B
    F["Class implementing Function"] -.-> B
~~~

Data contract:

- **QuoteRequest** is a strongly-typed Java input consisting of order ID, quantity, and unit price.
- **Quote** is the output consisting of order ID and subtotal.
- All three bean styles delegate to a shared **QuoteCalculator** to guarantee **identical business rules**; the difference lies strictly in the declaration style.
- Use **BigDecimal** instead of **double** to avoid binary floating-point rounding errors when working with money. Production applications still require currency and rounding rules.

**Business note:** the example takes **unitPrice** from the input to illustrate Function structure. In real sales systems, prices used for billing must be verified against an authoritative pricing source; do not blindly trust client-submitted prices.

## 3. Complete Spring Boot Example with All Three Styles

The snippet below uses **Java 17+**, Spring Boot, and Spring Cloud Function in compatible versions. Each style is a **Function<QuoteRequest, Quote>** bean with its own name so learners can select and test each bean individually.

~~~java
package example.function;

import java.math.BigDecimal;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class QuoteApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteApplication.class, args);
    }

    // Input and output contracts.
    public record QuoteRequest(
        String orderId,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record Quote(
        String orderId,
        BigDecimal subtotal
    ) {}

    // Shared business logic for all three declaration styles.
    public static final class QuoteCalculator {
        public Quote calculate(QuoteRequest request) {
            if (request == null
                    || request.orderId() == null
                    || request.orderId().isBlank()
                    || request.quantity() <= 0
                    || request.unitPrice() == null
                    || request.unitPrice().signum() < 0) {
                throw new IllegalArgumentException("Invalid quote request");
            }

            BigDecimal subtotal = request.unitPrice()
                .multiply(BigDecimal.valueOf(request.quantity()));

            return new Quote(request.orderId(), subtotal);
        }
    }

    // Approach 3: Java class implementing the Function interface.
    public static final class QuoteFunction
            implements Function<QuoteRequest, Quote> {

        private final QuoteCalculator calculator;

        public QuoteFunction(QuoteCalculator calculator) {
            this.calculator = calculator;
        }

        @Override
        public Quote apply(QuoteRequest request) {
            return calculator.calculate(request);
        }
    }

    @Bean
    QuoteCalculator quoteCalculator() {
        return new QuoteCalculator();
    }

    // Approach 1: lambda expression.
    @Bean
    Function<QuoteRequest, Quote> quoteLambda(
            QuoteCalculator calculator) {
        return request -> calculator.calculate(request);
    }

    // Approach 2: method reference on an injected instance.
    @Bean
    Function<QuoteRequest, Quote> quoteMethodRef(
            QuoteCalculator calculator) {
        return calculator::calculate;
    }

    // Approach 3: instantiate the class implementing Function.
    @Bean
    Function<QuoteRequest, Quote> quoteClass(
            QuoteCalculator calculator) {
        return new QuoteFunction(calculator);
    }
}
~~~

This is **one application containing three beans with the same type contract** under three different names: **quoteLambda**, **quoteMethodRef**, and **quoteClass**. They can coexist in the Spring context; when using the HTTP adapter or Spring Cloud Stream, **explicitly select** which function to expose/bind to avoid ambiguous configuration.

A call with the input:

~~~json
{
  "orderId": "ORD-1001",
  "quantity": 3,
  "unitPrice": 120000
}
~~~

will produce the same business result:

~~~json
{
  "orderId": "ORD-1001",
  "subtotal": 360000
}
~~~

Each Function invokes **QuoteCalculator.calculate(...)**. If quantity is 0, unit price is negative, or order ID is blank, the calculator throws **IllegalArgumentException** before returning a result.

## 4. Approach 1 — Lambda Expression in @Bean

Lambda declaration in the main example:

~~~java
@Bean
Function<QuoteRequest, Quote> quoteLambda(
        QuoteCalculator calculator) {
    return request -> calculator.calculate(request);
}
~~~

A **lambda** has the form **(parameters) -> expression** or **(parameters) -> { block }**. The Java types of parameters and return value are inferred from the target type, here **Function<QuoteRequest, Quote>**.

Example of a multi-line lambda:

~~~java
Function<String, String> normalize = text -> {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("Empty code");
    }

    return text.trim().toUpperCase(java.util.Locale.ROOT);
};
~~~

When should you use a lambda?

- Short, direct logic that is easy to read at the declaration site.
- The function only needs one or a few dependencies injected into the **@Bean** method.
- No separate class with a public API or multiple internal helper methods is needed.

Points to note:

1. **@Bean** executes when Spring creates the bean, whereas **the lambda body** typically runs only when the adapter or caller actually invokes **apply(...)**. Thus **return request -> calculator.calculate(request)** differs from precomputing a result at startup.
2. A lambda can **capture** outer variables such as **calculator**. Captured objects must still be safe when accessed by multiple concurrent requests.
3. Avoid cramming numerous business branches, I/O calls, or complex error handling into a long lambda; extracting to a service or dedicated class is usually more maintainable.
4. **Function.apply(...)** declares no checked exceptions. If the logic uses APIs throwing checked exceptions, handle or wrap them intentionally—Java's rules cannot be bypassed.

Do not assume a lambda is automatically a **pure function**. A lambda that calls a database or mutates shared variables still has side effects; safety depends on internal logic, not syntax.

## 5. Approach 2 — Method Reference to an Existing Method

A method reference uses **::**, creating a function pointing to a method or constructor matching the target functional interface.

~~~java
@Bean
Function<QuoteRequest, Quote> quoteMethodRef(
        QuoteCalculator calculator) {
    return calculator::calculate;
}
~~~

The method **QuoteCalculator.calculate(QuoteRequest)** takes a **QuoteRequest** and returns a **Quote**, so this reference is compatible with **Function<QuoteRequest, Quote>**.

Common forms of method references:

| Form | Java Example | Illustrative Target Type |
| --- | --- | --- |
| **Static method** | **Integer::parseInt** | Function<String, Integer> |
| **Instance method of a particular object** | **calculator::calculate** | Function<QuoteRequest, Quote> |
| **Instance method of an arbitrary object of a type** | **String::trim** | Function<String, String> |
| **Constructor reference** | **ArrayList::new** | Supplier<ArrayList<String>> |

Plain Java example:

~~~java
import java.util.ArrayList;
import java.util.function.Function;
import java.util.function.Supplier;

Function<String, Integer> parseNumber = Integer::parseInt;
Function<String, String> trimText = String::trim;
Supplier<ArrayList<String>> listFactory = ArrayList::new;

int number = parseNumber.apply("42");
String trimmed = trimText.apply(" a ");
ArrayList<String> values = listFactory.get();
~~~

For **String::trim**, the receiver (the String object) is passed as the Function's parameter. For **calculator::calculate**, the receiver is already **calculator**, and only the **QuoteRequest** argument remains to be supplied.

Method references fit especially well when:

- A service already has a method with the exact signature.
- You want to reuse a business method across APIs, batch jobs, tests, and Spring Cloud Function.
- A lambda would simply delegate to another method, such as **input -> service.process(input)**.

Avoid two common mistakes. First, **return calculator.calculate(...)** is an eager computation call, not a function reference. Second, when a method is overloaded or return types mismatch, the compiler may fail to resolve a suitable method reference; check the target type or write an explicit lambda.

**A method reference does not automatically make business logic faster than a lambda.** Choose the expression that is clearest and satisfies the type contract; real performance depends on logic, I/O, and runtime characteristics.

## 6. Approach 3 — Class Implementing Function<T, R>

A class explicitly implementing the **apply(...)** method:

~~~java
public static final class QuoteFunction
        implements Function<QuoteRequest, Quote> {

    private final QuoteCalculator calculator;

    public QuoteFunction(QuoteCalculator calculator) {
        this.calculator = calculator;
    }

    @Override
    public Quote apply(QuoteRequest request) {
        return calculator.calculate(request);
    }
}
~~~

In the main example, the class is turned into a bean via:

~~~java
@Bean
Function<QuoteRequest, Quote> quoteClass(
        QuoteCalculator calculator) {
    return new QuoteFunction(calculator);
}
~~~

Advantages of a dedicated class:

- Can be given a name expressing its responsibility, documenting the contract, and allowing reuse across contexts.
- Easy to add constructor injection, internal helper methods, precondition checks, and Javadoc.
- Directly testable with **new QuoteFunction(calculator)** without needing a Spring context.
- Convenient when logic is lengthy, requires many dependencies, or has explicit error handling rules.

Declaring via **@Bean** is one way to register a class implementing the interface. Another option is creating a top-level class that **implements Function<QuoteRequest, Quote>**, annotating it with **@Component("quoteComponent")**, and letting component scanning register the bean, provided the class falls within Spring's scan scope. Use only **one** registration method per bean name; do not simultaneously declare **@Component("quoteClass")** and another **@Bean quoteClass(...)** and rely on bean overriding.

### Comparing the Three Approaches on the Same Problem

| Criterion | Lambda | Method Reference | Implementation Class |
| --- | --- | --- | --- |
| Syntax | **request -> ...** | **calculator::calculate** | **implements Function** |
| Where logic lives | Inside the lambda or delegated method | In an existing method | Inside **apply(...)** and helper methods |
| Best suited for | Short, simple processing | Service with matching signature | Longer logic, multiple internal responsibilities |
| Dependency injection | Via **@Bean** parameters and capture | Inject instance then reference method | Constructor injection or **@Bean** |
| Testing | Invoke **apply** | Test target method and **apply** | Instantiate and invoke **apply** |
| Function name in catalog | Registered bean name | Registered bean name | Registered bean name |

There is no requirement to pick a single syntax for every bean in a module. Use lambdas for short glue code, method references to reuse existing services, and implementation classes when a function has enough responsibility to warrant its own named type.

## 7. Why Must Generic Types Be Declared Explicitly?

Spring Cloud Function needs to know input/output types so adapters can decide how to convert data. For example:

~~~java
@Bean
Function<QuoteRequest, Quote> quoteLambda(
        QuoteCalculator calculator) {
    return request -> calculator.calculate(request);
}
~~~

The signature above describes **QuoteRequest → Quote**. If replaced by a raw type:

~~~java
// Avoid raw types missing generics in real applications:
@Bean
@SuppressWarnings("rawtypes")
Function ambiguousFunction() {
    return value -> value;
}
~~~

Java may still accept raw types, but information about **T** and **R** is lost or degraded, making it difficult for the framework's conversion mechanism to know which DTO to instantiate. To let HTTP adapters or message converters handle JSON reliably, prefer concrete generics, well-structured DTOs/records, and serialization tests.

Other variants also need the right interface:

~~~java
@Bean
java.util.function.Supplier<String> greeting() {
    return () -> "hello";
}

@Bean
java.util.function.Consumer<String> printAudit() {
    return System.out::println;
}
~~~

**greeting** is a Supplier; **printAudit** is a Consumer. They can be discovered by Spring Cloud Function as functional beans, but triggering them over HTTP or Stream differs from Function because one accepts no input and the other produces no output. **System.out::println** is only suitable for demonstration; real applications should use a proper logging or auditing system.

## 8. Naming and Registering with FunctionCatalog

Spring Cloud Function discovers functional beans in the Spring application context and registers them into **FunctionCatalog**. In the example:

~~~text
quoteLambda      : Function<QuoteRequest, Quote>
quoteMethodRef   : Function<QuoteRequest, Quote>
quoteClass       : Function<QuoteRequest, Quote>
~~~

Even though the Java implementations differ, adapters select a function by **bean name**, not by whether it is a lambda, method reference, or class instance.

When multiple functions exist, explicitly choose one:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteMethodRef
~~~

Change **quoteMethodRef** to **quoteLambda** or **quoteClass** to try another variant. The name in the definition must match an actual bean. You can specify an explicit name right in the declaration:

~~~java
@Bean("quoteApi")
Function<QuoteRequest, Quote> quoteForApi(
        QuoteCalculator calculator) {
    return calculator::calculate;
}
~~~

In this case, the registered bean name is **quoteApi**. This is an example of **another bean**, not an automatic alias for the previously declared **quoteMethodRef** bean.

### Looking Up a Function by Name

A Spring-managed class can receive **FunctionCatalog** via constructor injection:

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

    public QuoteApplication.Quote quote(
            QuoteApplication.QuoteRequest input) {

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> function =
            catalog.lookup("quoteMethodRef");

        if (function == null) {
            throw new IllegalStateException("Quote function not found");
        }

        return function.apply(input);
    }
}
~~~

**QuoteInvoker** is a separate class in the same package **example.function** as **QuoteApplication**. The catalog may return a function wrapped by the framework for conversion and composition; therefore, do not assume the lookup result always has the concrete class **QuoteFunction**. Business unit tests can call the bean directly, while integration tests should verify that catalog lookup works under the real contract.

## 9. Invoking the Function over HTTP Without Changing Logic

To use the web adapter, the project needs the appropriate dependency, for example with Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Suppose the configuration uses:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteMethodRef
~~~

When the application runs on the default port **8080** and the web adapter is active, you can test:

~~~bash
curl -i -X POST http://localhost:8080/quoteMethodRef \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-1001","quantity":3,"unitPrice":120000}'
~~~

Illustrative response:

~~~json
{
  "orderId": "ORD-1001",
  "subtotal": 360000
}
~~~

Data flow:

~~~mermaid
flowchart LR
    A["HTTP POST /quoteMethodRef"] --> B["JSON → QuoteRequest"]
    B --> C["FunctionCatalog"]
    C --> D["quoteMethodRef.apply(request)"]
    D --> E["Quote"]
    E --> F["JSON response"]
~~~

The **QuoteCalculator.calculate** logic remains independent of HTTP paths, HTTP headers, or controller frameworks. Error mapping, status codes, and JSON conversion belong to the adapter and application configuration. For example, **IllegalArgumentException** does not automatically guarantee an **HTTP 400** response unless a corresponding error-handling mechanism is designed and tested.

If you change the definition to **quoteLambda** or **quoteClass**, the same payload and expected result still apply; just call the corresponding endpoint exposed by the adapter for that function name.

## 10. Composition Does Not Depend on Declaration Style

All the beans implement **Function<T, R>**, so they can participate in **composition** according to the rule that the previous step's output is compatible with the next step's input.

Add a formatting bean to **QuoteApplication**:

~~~java
@Bean
Function<Quote, String> formatQuote() {
    return quote -> quote.orderId() + ":"
        + quote.subtotal().toPlainString();
}
~~~

When using **Function** with code inside the **QuoteApplication** class, the **Quote** type is resolved directly because it is a nested record in the class. Chain configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteClass|formatQuote
~~~

Processing path:

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["quoteClass"]
    B --> C["Quote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

The result for the example input is the string **ORD-1001:360000**. You can replace **quoteClass** with **quoteLambda** or **quoteMethodRef**, as long as each bean still returns **Quote**.

Composition does not inspect Java syntax styles. It relies on **type contracts** and Spring Cloud Function's wrapper/conversion mechanism. Thus a **Function<QuoteRequest, Quote>** cannot be composed directly with a **Function<OtherRequest, String>** merely because both beans are Functions.

**Configuration note:** do not supply two conflicting **spring.cloud.function.definition** values in the same effective configuration without clear override rules; select one function or one pipeline for the adapter.

## 11. Using the Same Function in Event Streams or Serverless

With **Spring Cloud Stream** and a suitable binder (Kafka, RabbitMQ, or another binder), a **Function<QuoteRequest, Quote>** can consume incoming events and emit results to another destination.

Example configuration for the **quoteClass** bean:

~~~yaml
spring:
  cloud:
    function:
      definition: quoteClass
    stream:
      bindings:
        quoteClass-in-0:
          destination: quote-requests
        quoteClass-out-0:
          destination: quote-results
~~~

**quoteClass-in-0** is the input binding and **quoteClass-out-0** is the output binding of the Function. This is only routing configuration; the application also requires Spring Cloud Stream dependencies, a binder, a broker, and valid connection details.

In this environment, the transformation can still be implemented with a lambda, method reference, or implementation class; input and output become message payloads handled by the binder/converter. Redelivered events, schema evolution, retries, partitions, or transactions are integration-system concerns and are not solved merely by changing Function declaration syntax.

Similarly, a **serverless** adapter can turn a runtime event into input, look up the function name, and invoke it. Packaging, handlers, triggers, timeouts, permissions, and data mapping depend on the platform. **The same QuoteCalculator code** can be reused; the integration layer still requires platform-specific configuration.

~~~text
                 +-- HTTP adapter --------+
QuoteRequest ----|-- Stream input --------|--> FunctionCatalog
                 +-- Serverless adapter --+          |
                                                    v
                                quoteLambda / quoteMethodRef / quoteClass
                                                    |
                                                    v
                                                  Quote
~~~

The diagram only illustrates the ability to **choose each adapter**, not that all run simultaneously when adding a single dependency.

## 12. What If Logic Needs Message or Headers?

The three declaration styles do not restrict Functions to plain DTOs. If metadata must be read or modified, use **Message<T>** in the generic signature.

Example additional Function inside **QuoteApplication**:

~~~java
@Bean
Function<
        org.springframework.messaging.Message<QuoteRequest>,
        org.springframework.messaging.Message<Quote>>
        quoteMessage(QuoteCalculator calculator) {

    return input -> org.springframework.messaging.support.MessageBuilder
        .withPayload(calculator.calculate(input.getPayload()))
        .copyHeaders(input.getHeaders())
        .setHeader("processedBy", "quoteMessage")
        .build();
}
~~~

This is a **lambda** accepting a Message and returning a Message. Equivalent implementations could be:

- A **method reference** to a service method with signature **Message<Quote> process(Message<QuoteRequest> input)**.
- A **class implementing Function<Message<QuoteRequest>, Message<Quote>>** with **apply(...)**.

Consider copying only necessary headers; do not assume every technical or client-supplied header should be forwarded to brokers or external systems. For Functions that process only payloads, adapters usually provide corresponding message conversion; introduce **Message** into the business signature only when metadata control is required.

## 13. Bean Lifecycle, State, and Concurrency

Singleton beans are typically instantiated once by Spring and reused across many invocations. This applies equally to lambdas, method references, and implementation classes.

Example that is unsafe under concurrent multi-threaded calls:

~~~java
@Bean
Function<String, Integer> unsafeCounter() {
    int[] count = {0};
    return input -> ++count[0];
}
~~~

The **count** variable is captured and can be updated concurrently without synchronization; moreover, state lives in a single instance and is inconsistent across multiple replicas. When processing independent data, keep functions **stateless**. When business logic requires shared state, choose proper concurrency controls and storage; switching to an implementation class does not automatically fix race conditions.

In **QuoteApplication**, the beans share a **QuoteCalculator** with no mutable state. Each call constructs a new **Quote** from input, making it safe for concurrent reuse.

Another mistake is precomputing a result at initialization time:

~~~java
@Bean
java.util.function.Supplier<java.time.Instant> startupTime() {
    java.time.Instant value = java.time.Instant.now();
    return () -> value;
}
~~~

The Supplier above always returns the timestamp from bean creation time. To obtain the current time on **each get() call**, write:

~~~java
@Bean
java.util.function.Supplier<java.time.Instant> currentTime() {
    return java.time.Instant::now;
}
~~~

This example shows that **execution timing** matters more than whether you use a lambda or a method reference. For timestamps needing deterministic unit tests, inject **Clock** and use **clock::instant**.

## 14. Common Mistakes When Declaring Functional Beans

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Spring cannot find function name | Bean name and **function.definition** mismatch | Check **@Bean**, method name, and definition |
| Multiple beans cause adapter to pick wrong or ambiguous function | No function definition selected | Explicitly configure function name or composition |
| Method reference fails to compile | Signature, parameter count, return type, or overload mismatch | Check target type, try an explicit lambda |
| JSON fails to convert to DTO | Raw types lost generics, invalid payload/content type | Declare concrete **Function<Input, Output>**, check converter |
| Bean created but logic runs unexpectedly early | Calling service during bean creation instead of returning lambda/reference | Distinguish **service.method(...)** from **service::method** |
| Java unit tests pass but HTTP fails | Adapter, conversion, or exception mapping untested | Add integration tests at real boundaries |
| Duplicate bean names | Both **@Component** and **@Bean** use the same name | Use one registration style or distinct names |
| Errors under concurrent requests | Lambda captures mutable state or class has mutable fields | Use stateless, immutable logic and proper synchronization |
| Switched to Stream but no messages arrive | Missing binder/broker, wrong binding or definition | Check dependencies, destination, in-0/out-0 |
| Expected Consumer to emit output but got nothing | Chose **Consumer<T>** with void signature | Choose **Function<T, R>** if output data is needed |

**Do not judge correctness by shorter code.** A one-line method reference can still invoke a method containing blocking I/O, side effects, or complex logic. Declaration style only determines how a behavior is expressed; behavior and error policies live in the implementation.

## 15. Testing All Three Declaration Styles

Function unit tests should invoke **apply(...)** directly. With **QuoteApplication**, we can verify that all three styles return the exact same result and enforce the same validation rules.

~~~java
package example.function;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class QuoteApplicationTest {

    private final QuoteApplication app = new QuoteApplication();

    private final QuoteApplication.QuoteCalculator calculator =
        app.quoteCalculator();

    private QuoteApplication.QuoteRequest request(int quantity) {
        return new QuoteApplication.QuoteRequest(
            "ORD-1001", quantity, new BigDecimal("120000")
        );
    }

    @Test
    void threeDeclarationsReturnTheSameBusinessResult() {
        var input = request(3);
        var expected = new QuoteApplication.Quote(
            "ORD-1001", new BigDecimal("360000")
        );

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> lambda =
            app.quoteLambda(calculator);

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> methodRef =
            app.quoteMethodRef(calculator);

        Function<QuoteApplication.QuoteRequest,
                QuoteApplication.Quote> classBased =
            app.quoteClass(calculator);

        assertEquals(expected, lambda.apply(input));
        assertEquals(expected, methodRef.apply(input));
        assertEquals(expected, classBased.apply(input));
    }

    @Test
    void invalidQuantityIsRejectedByAllThree() {
        var invalid = request(0);

        assertThrows(IllegalArgumentException.class,
            () -> app.quoteLambda(calculator).apply(invalid));

        assertThrows(IllegalArgumentException.class,
            () -> app.quoteMethodRef(calculator).apply(invalid));

        assertThrows(IllegalArgumentException.class,
            () -> app.quoteClass(calculator).apply(invalid));
    }
}
~~~

The first test verifies the **QuoteRequest → Quote** transformation; the second verifies invalid input handling. Both test only **Java logic** and wiring of the three functional forms.

For real applications, add integration tests matched to the deployment scope:

1. Spring application context creates all three beans and **FunctionCatalog.lookup(...)** resolves the exact names.
2. HTTP adapter converts JSON into **QuoteRequest** and produces a properly formatted response.
3. Composition **quoteClass|formatQuote** accepts input and outputs the expected String.
4. Stream adapter maps payload/schema and **in-0/out-0** bindings according to the broker in use.
5. Error mapping, retries, and metadata operate according to the transport channel contract.

You do not need to test HTTP, brokers, and serverless all together if a product uses only one protocol. Choose integration tests based on the adapters actually deployed.

## 16. Guide to Choosing a Declaration Style in Projects

Use the following questions before writing a bean:

| Situation | Usually Most Maintainable Style |
| --- | --- |
| A short transformation expression needing one dependency | Lambda |
| Service already has a method matching input/output | Method reference |
| Multiple branches, helpers, custom error policies | Class implementing Function |
| Want to reuse logic outside Spring Cloud Function | Method reference or standalone class, though a lambda calling a service also works |
| Need to unit test business rules separately | Extract logic into a service/POJO first, then pick an appropriate declaration |
| Multiple functions in one application | Use clear bean names and configure function definition |
| Need to handle message metadata | Use **Message<T>** generics when needed, regardless of declaration syntax |

An easy-to-follow design pattern is to **keep business rules in plain services**, then expose them as Function beans via lambdas or method references. When a function grows complex enough, a standalone implementation class can help organize logic more clearly. There is no rule forcing every project to use a single style.

## 17. Practice Exercises

**Exercise 1 — Comparing syntaxes.** Create three beans **normalizeLambda**, **normalizeReference**, and **normalizeClass**, all of type **Function<String, String>**, to normalize product code strings. Write unit tests feeding the same three inputs to compare results and errors.

**Exercise 2 — Dependency injection.** Create a **TaxCalculator** service with a **TaxQuote calculate(TaxRequest request)** method. Expose it via **TaxCalculator::calculate** in a Function bean, and explain the difference between **calculator::calculate** and **request -> calculator.calculate(request)**.

**Exercise 3 — FunctionCatalog.** Declare three beans with identical input/output. Use **catalog.lookup("normalizeReference")** and call **apply(...)**. Try renaming a bean or misconfiguring the definition and describe the error behavior.

**Exercise 4 — Composition.** Create an additional **Function<TaxQuote, String>** to format the result and configure **calculateTax|formatTax**. Sketch the input/output data type diagram at each step and test the pipeline through the catalog.

**Exercise 5 — From HTTP to events.** Choose one of the three quote beans, test it via HTTP POST, then describe how to configure Spring Cloud Stream to consume and emit messages. Identify what must change at the adapter layer and explain why the **QuoteCalculator** logic remains usable.

**Exercise 6 — Concurrency.** Create a lambda capturing a mutable counter variable and analyze why a race condition occurs when two threads invoke **apply(...)**. Propose how to eliminate state or apply proper concurrency control when state is a business requirement.

### Key Takeaways

- **Lambdas**, **method references**, and **classes implementing Function** are three ways to express logic under the same **Function<T, R>** contract in Java.
- Spring Cloud Function manages these objects when registered as functional beans; **FunctionCatalog** and adapters select by **bean name**, not by syntax.
- Maintain **concrete generic types** to support conversion, composition, and testing; use **spring.cloud.function.definition** when specifying a function or pipeline.
- Choose declaration styles based on complexity and maintainability. **No syntax guarantees statelessness, thread safety, idempotency, or error handling on its own**.
- The same logic can run over **HTTP**, **Spring Cloud Stream**, or **serverless** when paired with the right dependencies, adapters, and configuration; business logic should remain protocol-independent.
