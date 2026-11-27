# Spring-Independent Functions and External Adapters

A key goal of **SPRING_CLOUD_FUNCTION** is writing business logic as a **Supplier**, **Function**, or **Consumer** without forcing that logic to know who is invoking it: an HTTP endpoint, a message broker, a scheduler, or a serverless runtime. You can implement the logic in **plain Java**, then use an **adapter** to register it as a Spring bean and connect it to **FunctionCatalog**. As a result, the same calculation or business rule can be invoked directly in unit tests, exposed over HTTP, or used to process events without rewriting it.

This lesson belongs to the **Function Model** chapter, focusing on **dependency boundaries**: what belongs inside the Spring-independent business function, what belongs in the adapter, and how to wire the two together using dependency injection.

## 1. Understanding "Spring-Independent Functions" Properly

A business class is considered Spring-independent when its source code and contract do not require Spring APIs to execute. For example, the class may use:

- Java data types such as **String**, **BigDecimal**, **record**, or **List**.
- **java.util.function.Function<T, R>**, **Supplier<T>**, or **Consumer<T>**.
- Constructors to receive dependencies described by plain Java interfaces.
- Framework-neutral business libraries when genuinely needed.

Inside that core, there is no need for **@Component**, **@Service**, **@Bean**, **ApplicationContext**, **HttpServletRequest**, Spring Messaging's **Message**, or broker APIs.

~~~mermaid
flowchart LR
    A["HTTP request"] --> D["HTTP adapter"]
    B["Broker event"] --> E["Stream adapter"]
    C["Serverless invocation"] --> F["Serverless adapter"]
    D --> G["FunctionCatalog"]
    E --> G
    F --> G
    G --> H["Plain Java Function<T, R>"]
    H --> I["Result R"]
~~~

**Being Spring-independent does not mean having zero dependencies.** Logic may still need tax policies, a clock, or a data access port. The key point is that **the contracts of these dependencies belong to the core or plain Java**, while creating and wiring implementations belong to the outer environment.

In particular, avoid assuming that merely returning a **Function** object automatically equips the application with HTTP endpoints, Kafka connections, and serverless handlers. Each invocation mechanism requires its own matching **adapter, dependencies, and configuration**.

## 2. Distinguishing Business Function, Adapter, and Infrastructure

You can view the system across three layers of responsibility:

| Component | Responsibility | What It Should Know |
| --- | --- | --- |
| **Business core** | Validate rules, compute, transform input into output | DTOs/records, Java interfaces, business rules |
| **Spring adapter layer** | Create beans, inject dependencies, select Function names, map metadata when needed | Spring configuration, FunctionCatalog, Message |
| **Protocol/infrastructure adapter** | Receive/send HTTP, events, serverless invocations, convert data | HTTP, binders, brokers, runtime, serialization |

Desired dependency direction:

~~~mermaid
flowchart TB
    A["HTTP / Stream / Serverless adapter"] --> B["Spring Function binding"]
    B --> C["Plain Java core"]
    D["Database or API adapter"] --> E["Core port interface"]
    C --> E
~~~

Adapters **know** the core's data types in order to forward invocations; the core **does not need to know** which adapters will be deployed.

This pattern is commonly described as **ports and adapters**. Spring Cloud Function provides a convenient integration point for Java functions, yet you still need clearly designed ports and data boundaries to maintain real independence.

## 3. Plain Java Core Example: Calculating a Quote with Tax

Suppose a service needs to receive a quote ID and pre-tax amount, then return the tax amount and total amount. This is a straightforward transformation:

~~~text
QuoteRequest(orderId, netAmount)
          |
          v
Function<QuoteRequest, Quote>
          |
          v
Quote(orderId, netAmount, taxAmount, total)
~~~

To stay focused on architecture, the example uses a **fixed 10% tax rate** supplied by the adapter via configuration. In real applications, tax rates may depend on item category, region, or effective dates; those rules require an appropriate business model and data source.

### 3.1. A Single Java File Containing Only Business Logic

File **QuoteCore.java**:

~~~java
package example.core;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.function.Function;

public final class QuoteCore {

    private QuoteCore() {
    }

    public record QuoteRequest(
        String orderId,
        BigDecimal netAmount
    ) {}

    public record Quote(
        String orderId,
        BigDecimal netAmount,
        BigDecimal taxAmount,
        BigDecimal total
    ) {}

    public record TaxPolicy(BigDecimal rate) {
        public TaxPolicy {
            if (rate == null
                    || rate.signum() < 0
                    || rate.compareTo(BigDecimal.ONE) > 0) {
                throw new IllegalArgumentException(
                    "Tax rate must be between 0 and 1");
            }
        }
    }

    public static final class Calculator
            implements Function<QuoteRequest, Quote> {

        private final TaxPolicy policy;

        public Calculator(TaxPolicy policy) {
            if (policy == null) {
                throw new IllegalArgumentException(
                    "TaxPolicy is required");
            }
            this.policy = policy;
        }

        @Override
        public Quote apply(QuoteRequest request) {
            if (request == null
                    || request.orderId() == null
                    || request.orderId().isBlank()
                    || request.netAmount() == null
                    || request.netAmount().signum() < 0) {
                throw new IllegalArgumentException(
                    "Invalid quote request");
            }

            BigDecimal net;
            try {
                net = request.netAmount().setScale(
                    2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                    "Amount must have at most two decimal places", ex);
            }

            BigDecimal tax = net.multiply(policy.rate())
                .setScale(2, RoundingMode.HALF_UP);

            return new Quote(
                request.orderId(),
                net,
                tax,
                net.add(tax)
            );
        }
    }
}
~~~

What to notice:

1. Core code imports only **java.math** and **java.util.function**.
2. **Calculator** implements **Function<QuoteRequest, Quote>**, so **apply(...)** can be invoked directly.
3. **TaxPolicy** comes from the constructor, not from **@Autowired**, **Environment**, or Spring properties.
4. Each call constructs a new **Quote**; no shared mutable state object is modified.
5. Illustrative rounding rules are stated explicitly: input must have at most two decimal places; tax is rounded **HALF_UP** to two decimal places.

The **QuoteCore** class groups the example types so they can be copied in a single file. In larger projects, **QuoteRequest**, **Quote**, **TaxPolicy**, and **Calculator** are typically split into separate files, still inside the core package and free of Spring libraries.

## 4. Running the Java Core Without Starting Spring

Because **Calculator** is an ordinary Java class, it can be instantiated and invoked directly:

~~~java
package example.core;

import java.math.BigDecimal;

public class PlainJavaDemo {
    public static void main(String[] args) {
        QuoteCore.TaxPolicy policy =
            new QuoteCore.TaxPolicy(new BigDecimal("0.10"));

        QuoteCore.Calculator calculator =
            new QuoteCore.Calculator(policy);

        QuoteCore.Quote quote = calculator.apply(
            new QuoteCore.QuoteRequest(
                "ORD-101", new BigDecimal("100.00")
            )
        );

        System.out.println(quote.total()); // 110.00
    }
}
~~~

There is no ApplicationContext, HTTP server, broker, or function adapter in this snippet. This is direct proof that the tax calculation rules **do not require** Spring to execute.

A helpful characteristic is that **inputs and outputs remain strongly-typed Java records**. The adapter only needs to know how to build a **QuoteRequest** from an external protocol and how to represent **Quote** in the response.

## 5. Adapter Layer: Registering a Pure Function as a Spring Bean

Spring Cloud Function needs a **functional Spring bean** to register into **FunctionCatalog**. The adapter does this without adding Spring annotations to **QuoteCore**.

File **QuoteFunctionConfiguration.java** lives in the Spring application layer:

~~~java
package example.adapter.spring;

import java.math.BigDecimal;
import java.util.function.Function;

import example.core.QuoteCore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class QuoteFunctionConfiguration {

    @Bean
    QuoteCore.TaxPolicy taxPolicy(
            @Value("${app.tax-rate:0.10}") String rawRate) {
        return new QuoteCore.TaxPolicy(new BigDecimal(rawRate));
    }

    @Bean("calculateQuote")
    Function<QuoteCore.QuoteRequest, QuoteCore.Quote>
            calculateQuote(QuoteCore.TaxPolicy policy) {
        return new QuoteCore.Calculator(policy);
    }

    @Bean("formatQuote")
    Function<QuoteCore.Quote, String> formatQuote() {
        return quote -> quote.orderId()
            + ": " + quote.total().toPlainString();
    }
}
~~~

For Spring Boot to scan the configuration class, place it under a scanned package or import it explicitly in the bootstrap application. Example entrypoint:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FunctionApplication {
    public static void main(String[] args) {
        SpringApplication.run(FunctionApplication.class, args);
    }
}
~~~

With **example.FunctionApplication**, Spring Boot scans subpackages such as **example.adapter.spring** by default. **QuoteCore** needs no component scanning: it is plain Java code instantiated by Spring configuration via **new QuoteCore.Calculator(policy)**.

In the configuration snippet:

- **@Value** belongs to the adapter, reading the **app.tax-rate** property string; the core only receives **TaxPolicy**.
- **@Bean("calculateQuote")** gives the function a clear name for adapters to look up.
- **Function<QuoteRequest, Quote>** retains generic type information; the framework can use these types to perform conversions.
- **formatQuote** is another processing step used when composing functions; it does not alter the tax calculation code.

You can configure the tax rate:

~~~yaml
app:
  tax-rate: "0.10"

spring:
  cloud:
    function:
      definition: calculateQuote
~~~

**Note:** when an application contains multiple Function beans such as **calculateQuote** and **formatQuote**, specify **spring.cloud.function.definition** explicitly so the adapter knows which function to use. The **app.tax-rate** property is merely an application-defined example property, not a built-in Spring Cloud Function property.

## 6. Where Does Dependency Injection Live?

**Dependency injection (DI)** provides the objects a class needs instead of forcing the class to instantiate its own dependencies. In the example:

~~~text
app.tax-rate = "0.10"
       |
       v
Spring @Bean taxPolicy
       |
       v
new QuoteCore.Calculator(policy)
       |
       v
Spring @Bean("calculateQuote")
       |
       v
FunctionCatalog
~~~

This is **plain-Java constructor injection**, wired externally by Spring. Calculator does not need to know who invokes its constructor; a unit test can supply **TaxPolicy** the exact same way.

Placing **TaxPolicy** creation in the adapter brings an important benefit: when switching configuration from YAML to environment variables, a configuration server, or a secret store, **QuoteCore** can remain unchanged. Only if the tax rules themselves fundamentally change do you adjust the business logic or corresponding policy model.

Do not call **System.getenv(...)** directly inside **apply(...)** or inject **Environment** into the core just to fetch the tax rate. Doing so couples business logic to runtime configuration, making results harder to reproduce and test in isolation.

## 7. Bean Naming and FunctionCatalog

Spring Cloud Function detects **Supplier**, **Function**, and **Consumer** beans and provides lookup via **FunctionCatalog**. The name **calculateQuote** is the bean name defined by **@Bean**; it does not have to match the class name **QuoteCore.Calculator**.

~~~mermaid
flowchart LR
    A["QuoteCore.Calculator"] --> B["@Bean calculateQuote"]
    B --> C["FunctionCatalog"]
    C --> D["HTTP adapter"]
    C --> E["Stream adapter"]
    C --> F["Serverless adapter"]
~~~

A Spring class can look up a function by name via the catalog:

~~~java
package example.adapter.spring;

import java.util.function.Function;

import example.core.QuoteCore;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.stereotype.Component;

@Component
public class QuoteInvoker {

    private final FunctionCatalog catalog;

    public QuoteInvoker(FunctionCatalog catalog) {
        this.catalog = catalog;
    }

    public QuoteCore.Quote invoke(QuoteCore.QuoteRequest input) {
        Function<QuoteCore.QuoteRequest, QuoteCore.Quote> fn =
            catalog.lookup("calculateQuote");

        if (fn == null) {
            throw new IllegalStateException(
                "Function 'calculateQuote' not found");
        }

        return fn.apply(input);
    }
}
~~~

**QuoteInvoker** is Spring adapter code and can use constructor injection. **QuoteCore.Calculator** does not need to know **FunctionCatalog** exists.

The catalog may return a **wrapper** supporting conversion, composition, and message handling; do not cast the looked-up object to **Calculator**. Inside plain Java code, you can still call **Calculator.apply(...)** directly as shown earlier.

## 8. Using the Same Function over HTTP

To expose **calculateQuote** over HTTP, the application needs a compatible web adapter. Example Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

The Spring Cloud Function/Spring Boot versions should be managed using compatible project BOM versions. When the application uses the default port **8080** and configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote
~~~

you can send:

~~~bash
curl -i -X POST http://localhost:8080/calculateQuote \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ORD-101","netAmount":100.00}'
~~~

Example JSON result:

~~~json
{
  "orderId": "ORD-101",
  "netAmount": 100.00,
  "taxAmount": 10.00,
  "total": 110.00
}
~~~

The processing flow is:

~~~text
HTTP JSON body
  -> Web adapter / message conversion
  -> QuoteRequest
  -> FunctionCatalog: calculateQuote
  -> Calculator.apply(QuoteRequest)
  -> Quote
  -> JSON response
~~~

Inside the core, there is no **HttpServletRequest**, **ResponseEntity**, route, or status code. Those details belong to the HTTP adapter. If **apply(...)** throws **IllegalArgumentException**, do not assume the adapter returns HTTP 400 in all versions; the application should verify and design appropriate error mappings.

**Boundary with distinct responsibilities:** the converter accepts syntactically valid JSON, while **Calculator** enforces business validation. JSON with a negative amount may deserialize into a type-valid **QuoteRequest** yet still be rejected by Calculator according to business rules.

## 9. Using the Same Function over Events with Spring Cloud Stream

If the application needs to consume quote-request events and emit result events, you can keep **QuoteCore** and **QuoteFunctionConfiguration** unchanged and swap the integration mechanism to Spring Cloud Stream with an appropriate binder.

Example configuration:

~~~yaml
app:
  tax-rate: "0.10"

spring:
  cloud:
    function:
      definition: calculateQuote
    stream:
      bindings:
        calculateQuote-in-0:
          destination: quote-requests
        calculateQuote-out-0:
          destination: quote-results
~~~

Here:

- **calculateQuote-in-0** is the Function's input binding.
- **calculateQuote-out-0** is its output binding.
- **destination** identifies the broker's logical target.
- Spring Cloud Stream dependencies, the corresponding binder, an available broker, and connection properties are required.

~~~mermaid
flowchart LR
    A["Topic/Queue quote-requests"] --> B["Stream binder"]
    B --> C["QuoteRequest"]
    C --> D["calculateQuote.apply"]
    D --> E["Quote"]
    E --> F["Stream binder"]
    F --> G["Topic/Queue quote-results"]
~~~

What changes is **the adapter layer**, message format, and operational configuration. **Calculator.apply(...)** does not change. From a business standpoint, it still performs the **QuoteRequest → Quote** transformation.

Do not confuse **swapping adapters** with **delivery guarantees**. When using a broker, messages may be redelivered due to retries or redelivery policies; acknowledgment, dead-letter, partition, and ordering semantics depend on the binder. With the pure calculation in this example, recomputing the same input carries less risk than a Consumer writing to a database or calling a payment gateway. If you turn a Function into one with side effects, handle idempotency and transactions separately.

## 10. Using the Same Function in a Serverless Environment

A serverless adapter can receive an invocation from the platform, convert the event into a suitable input, and invoke the Function in the catalog:

~~~text
Serverless event
   -> runtime adapter
   -> QuoteRequest
   -> FunctionCatalog.lookup("calculateQuote")
   -> Calculator.apply(...)
   -> Quote
   -> result converted by runtime adapter
~~~

Logic in **QuoteCore** still needs no imports for AWS Lambda or any other cloud provider API. Even so, real execution depends on the platform:

- Runtime handler/adapter and dependencies.
- Packaging and Spring application context initialization.
- Event payload mapping rules, timeouts, and resource limits.
- Function definition selection and output conversion.
- Access permissions to external services if the Function performs I/O.

A serverless instance may be reused or newly created, and multiple invocations may run across different instances. Therefore, do not store long-lived business state in fields of Calculator, even if the Spring bean is singleton-scoped within an instance.

## 11. Composition: One Adapter for Multiple Plain Java Steps

Spring Cloud Function lets you compose functions by name, provided the output of each step is compatible with the input of the next step.

In the example, **calculateQuote** takes **QuoteRequest** and returns **Quote**, while **formatQuote** takes **Quote** and returns **String**:

~~~text
QuoteRequest
  -> calculateQuote
  -> Quote
  -> formatQuote
  -> String
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: calculateQuote|formatQuote
~~~

From input **ORD-101**, **100.00**, the result is the string **ORD-101: 110.00**.

~~~mermaid
flowchart LR
    A["QuoteRequest"] --> B["calculateQuote"]
    B --> C["Quote"]
    C --> D["formatQuote"]
    D --> E["String"]
~~~

Here, **formatQuote** lives in Spring configuration as a lambda, yet it could easily be extracted into another plain Java **Function<Quote, String>** if formatting logic becomes more complex or needs independent reuse.

The key point is that **composition does not require sub-functions to know about FunctionCatalog**. The catalog links them by name and input/output types. When using Stream, binding names for a composition may differ from those of a single function; check the naming conventions of the binder and framework version in use.

## 12. When Message Metadata Is Needed, How Does the Adapter Handle It?

Pure business logic usually needs only the **payload**. With HTTP or brokers, messages may carry **headers** such as correlation IDs, event types, tracing metadata, or content types.

If a business requirement genuinely needs a correlation ID to produce its output, there are two main options:

1. **Make the required data an explicit part of the business input** if correlation ID is part of the use case contract.
2. **Read and forward metadata in the adapter** if it only serves logging, tracing, or technical routing.

For example, a Spring adapter can receive **Message<QuoteRequest>**, invoke the core, and build a new **Message<Quote>** carrying the correlation ID to propagate:

~~~java
package example.adapter.spring;

import java.util.function.Function;

import example.core.QuoteCore;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration(proxyBeanMethods = false)
public class QuoteMessageConfiguration {

    @Bean("calculateQuoteMessage")
    Function<Message<QuoteCore.QuoteRequest>,
             Message<QuoteCore.Quote>>
            calculateQuoteMessage(
                @Qualifier("calculateQuote")
                Function<QuoteCore.QuoteRequest, QuoteCore.Quote>
                    calculator) {

        return input -> {
            QuoteCore.Quote quote =
                calculator.apply(input.getPayload());

            var builder = MessageBuilder.withPayload(quote);

            Object correlation =
                input.getHeaders().get("correlationId");
            if (correlation != null) {
                builder.setHeader("correlationId", correlation);
            }

            return builder.build();
        };
    }
}
~~~

This is an **additional adapter bean**, requiring zero changes to **QuoteCore**. When multiple Function beans exist, choose either **calculateQuote** or **calculateQuoteMessage** explicitly in **spring.cloud.function.definition** according to deployment needs.

Do not assume all HTTP headers or broker headers are preserved across every adapter. Avoid copying sensitive headers with no business purpose, and do not treat client-supplied headers as authorization proof unless validated by a trusted authentication layer.

## 13. What If Business Logic Needs a Database or Event Emission?

The core may need external data or side effects. **Remaining Spring-independent** is still possible via **interfaces (ports)**. The core defines the operations it needs; an external adapter supplies the implementation.

Example of a Consumer writing audit logs. Plain Java core:

~~~java
package example.core;

import java.util.function.Consumer;

public final class AuditCore {

    private AuditCore() {
    }

    public record AuditEvent(
        String eventId,
        String message
    ) {}

    // Port resides on the core side: describes the need, not JDBC/Kafka.
    public interface AuditSink {
        void save(AuditEvent event);
    }

    public static final class AuditConsumer
            implements Consumer<AuditEvent> {

        private final AuditSink sink;

        public AuditConsumer(AuditSink sink) {
            this.sink = java.util.Objects.requireNonNull(sink);
        }

        @Override
        public void accept(AuditEvent event) {
            if (event == null
                    || event.eventId() == null
                    || event.eventId().isBlank()) {
                throw new IllegalArgumentException("Invalid audit event");
            }

            sink.save(event);
        }
    }
}
~~~

The Spring adapter registers an implementation for the port and creates the Consumer:

~~~java
package example.adapter.spring;

import java.util.function.Consumer;

import example.core.AuditCore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditConfiguration {

    @Bean
    AuditCore.AuditSink auditSink() {
        // Demo adapter: replace with repository/transaction in production.
        return event -> System.out.println(
            "AUDIT " + event.eventId() + ": " + event.message());
    }

    @Bean("recordAudit")
    Consumer<AuditCore.AuditEvent> recordAudit(
            AuditCore.AuditSink sink) {
        return new AuditCore.AuditConsumer(sink);
    }
}
~~~

The same **AuditConsumer** works with an adapter writing via JDBC, calling REST, or sending messages, as long as that adapter fulfills the **AuditSink** contract. Core logic never has to import Spring Data classes, HTTP clients, or Kafka APIs.

**Decoupling dependencies does not solve side effects on its own.** A Consumer can be invoked again with the same event after retries; when persisting to a database, use **idempotency keys**, **unique constraints**, transactions, or outbox patterns as needed. Printing to the console is purely illustrative, not durable audit storage.

## 14. Designing Error Boundaries Between Core and Adapter

A business function can reject input or detect invalid state. For example, **QuoteCore.Calculator** throws **IllegalArgumentException** when the amount is negative or exceeds precision rules.

Adapters are responsible for interpreting errors for each protocol:

| Error from Core | HTTP Adapter | Stream Adapter | Serverless Adapter |
| --- | --- | --- | --- |
| Contract-violating input | Can map to client errors like 400 if configured accordingly | Can reject, skip, or send to dead-letter per policy | Returns error per event contract/runtime |
| Transient I/O failure | Can return server error, timeout, or retry at appropriate layer | Can retry with backoff per binder | Can fail invocation so trigger applies retries |
| Unsatisfied business rule | Returns structured error per API contract | Emits error event or processing status | Returns result/error per use case contract |

**Do not hard-code HTTP status codes, Kafka topic names, or runtime error envelopes inside the core** just because the current adapter needs them. If business requirements are complex, define dedicated exceptions or result types in the core and let the adapter map them to the appropriate protocol mechanism.

There is no universal default rule turning **IllegalArgumentException** from a Function into HTTP 400. Check the real adapter's error handling mechanism and write corresponding integration tests.

## 15. Testing the Core Without Spring

A major advantage of independent functions is fast, accurate testing with JUnit without booting an application context. Example:

~~~java
package example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class QuoteCoreTest {

    private final QuoteCore.Calculator calculator =
        new QuoteCore.Calculator(
            new QuoteCore.TaxPolicy(new BigDecimal("0.10"))
        );

    @Test
    void calculatesTaxAndTotal() {
        QuoteCore.Quote result = calculator.apply(
            new QuoteCore.QuoteRequest(
                "ORD-101", new BigDecimal("100.00")
            )
        );

        assertEquals(new BigDecimal("100.00"), result.netAmount());
        assertEquals(new BigDecimal("10.00"), result.taxAmount());
        assertEquals(new BigDecimal("110.00"), result.total());
    }

    @Test
    void rejectsNegativeNetAmount() {
        assertThrows(IllegalArgumentException.class,
            () -> calculator.apply(
                new QuoteCore.QuoteRequest(
                    "ORD-102", new BigDecimal("-1.00")
                )
            ));
    }

    @Test
    void rejectsExcessFractionalDigits() {
        assertThrows(IllegalArgumentException.class,
            () -> calculator.apply(
                new QuoteCore.QuoteRequest(
                    "ORD-103", new BigDecimal("1.234")
                )
            ));
    }
}
~~~

In unit tests, the test itself constructs **TaxPolicy**. That does not violate DI: constructor injection is a Java technique, while Spring is simply one way to supply objects at runtime.

For **AuditConsumer**, you can use a fake **AuditSink** to observe side effects:

~~~java
package example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class AuditCoreTest {

    @Test
    void delegatesToPort() {
        List<AuditCore.AuditEvent> captured = new ArrayList<>();
        AuditCore.AuditSink sink = captured::add;

        AuditCore.AuditConsumer consumer =
            new AuditCore.AuditConsumer(sink);

        consumer.accept(
            new AuditCore.AuditEvent("evt-001", "created")
        );

        assertEquals(1, captured.size());
        assertEquals("evt-001", captured.get(0).eventId());
    }
}
~~~

This test ensures the core calls the port properly. It **does not test** database durability or real event delivery; those require integration tests with the corresponding adapter.

## 16. Testing the Spring and Protocol Boundaries

Plain Java unit tests do not verify that Spring discovers the right bean or converts JSON/messages into expected types. Therefore, write integration tests focused on the adapters actually used.

Example testing **FunctionCatalog** with a Spring Boot application:

~~~java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.util.function.Function;

import example.core.QuoteCore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class QuoteFunctionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void catalogInvokesCoreFunction() {
        Function<QuoteCore.QuoteRequest, QuoteCore.Quote> fn =
            catalog.lookup("calculateQuote");

        assertNotNull(fn);

        QuoteCore.Quote result = fn.apply(
            new QuoteCore.QuoteRequest(
                "ORD-101", new BigDecimal("100.00")
            )
        );

        assertEquals(new BigDecimal("110.00"), result.total());
    }
}
~~~

This test requires **Spring Boot Test**, Spring Cloud Function, and appropriate dependencies on the test classpath. It only verifies the invocation path through **FunctionCatalog** inside the application context.

If integrating over HTTP, add real POST tests checking JSON, content types, and invalid inputs. If integrating over Stream, test conversion, bindings, retries, and redelivery scenarios. If deploying serverless, test event mapping and handlers per runtime. You do not need to spin up every adapter if a product uses only one protocol.

## 17. Common Architectural Pitfalls

| Symptom | Cause | Improvement |
| --- | --- | --- |
| Core imports **@Component**, **ApplicationContext**, or HTTP requests | Business logic depends on the framework | Move wiring and protocol mapping to the adapter |
| Unit tests must boot Spring just to compute an operation | Core reads config/dependencies directly from the container | Use constructor injection with plain Java types |
| Function bean does not appear in catalog | Bean not registered, wrong scan scope, or wrong function name | Check **@Bean**, name, and **function.definition** |
| Switching from HTTP to Stream requires rewriting calculations | Logic reads requests or builds responses directly | Define **Function<T, R>** over DTOs/records and separate adapters |
| **Function** serializes incorrectly | Ambiguous input/output generics or schema mismatch | Keep concrete generics and test conversion |
| Single successful call causes Consumer to write duplicate data | Retries/redelivery and missing idempotency | Use business event keys, unique constraints, and retry policies |
| Headers lost during composition | No metadata propagation strategy | Build Messages in the adapter and preserve required headers |
| Results differ across instances | Core holds mutable state in singletons or invalid local caches | Use stateless functions, shared stores, or proper concurrency control |
| Business errors turn into unexpected status codes | Adapter lacks error mapping | Write mappings per protocol contract and add integration tests |
| Core must know JDBC/Kafka details | Port depends on infrastructure implementations | Place interfaces at the core boundary, implementations in adapters |

A quick litmus test: **if you remove all Spring dependencies and run the core tests, can the business calculation still execute?** If yes, the calculation logic has likely preserved an independent boundary. That does not guarantee a perfect architecture, but it is a useful practical check.

## 18. Practice Exercises

**Exercise 1 — Separating logic from Spring.** Write a plain Java **Function<ShippingRequest, ShippingQuote>** that takes weight and delivery zone and returns the shipping fee. Then create a **@Bean("calculateShipping")** bean in a Spring configuration class. Write core unit tests without using **@SpringBootTest**.

**Exercise 2 — Swapping adapters.** Using **calculateQuote**, test it via HTTP POST and describe the Spring Cloud Stream configuration to consume **QuoteRequest** from the **quote-requests** topic and emit **Quote** to **quote-results**. Point out which lines in **QuoteCore** need to change, if any, and why.

**Exercise 3 — Composition.** Write a plain Java **Function<Quote, String>** to format the result string. Register it as the **formatQuote** bean, then configure **calculateQuote|formatQuote**. Test the output via FunctionCatalog.

**Exercise 4 — Interfaces for infrastructure.** Create a **Consumer<NotificationRequest>** accepting a plain Java **NotificationPort**. Write two implementations: a fake for unit tests and a notification-sending adapter in the outer layer. Explain why an HTTP client should not be injected directly into the core just to fulfill the use case.

**Exercise 5 — Metadata.** Define a **correlationId** header for an incoming message. Create a **Function<Message<QuoteRequest>, Message<Quote>>** adapter that calls Calculator and forwards the exact correlationId. Test that the core still calculates accurately when the header is missing.

**Exercise 6 — Architecture diagnosis.** A **@Service** class has a method taking **HttpServletRequest**, reading **Environment**, instantiating **KafkaTemplate**, and calculating a total. Refactor responsibilities into DTOs, a plain Java Function, port interfaces where needed, and adapters so the same calculation is reusable over HTTP and a broker.

### Key Takeaways

- A **Spring-independent function** is a business function using plain Java contracts and explicit data types, invokable and testable independently of the Spring container.
- The **external adapter layer** creates Spring beans, injects dependencies, registers names in **FunctionCatalog**, converts payloads/messages, and connects HTTP, Stream, or serverless runtimes.
- Use **constructor injection and port interfaces** when the core needs policies, repositories, or side effects; keep framework/infrastructure details out of calculation logic.
- **Composition** chains functions by name and type contracts. Adapters handle protocols, errors, metadata, and retries per deployment environment.
- Core unit tests verify **business rules**; integration tests verify **wiring, bean names, conversion, and protocols**. Both are essential when building reusable functions.
