# Inferring Input and Output Types from Generic Signatures

In Spring Cloud Function, a function can be invoked over HTTP, event messages, or serverless environments without rewriting business logic. To convert data from those protocols into appropriate Java objects, the framework needs to know **what type the function accepts and what type it returns**. The most important source of information is the generic signature of `Supplier`, `Function`, and `Consumer` declared in the application.

This lesson belongs to the **Data Types** chapter, focusing on how to read generic signatures, how Spring Cloud Function uses type information when registering functions in `FunctionCatalog`, the limitations imposed by Java type erasure, and how to avoid losing type information when writing beans.

## 1. Reading the Type Contract of the Three Function Kinds

Spring Cloud Function builds its programming model on three standard Java functional interfaces:

| Function Kind | Signature | Input Type | Output Type | Meaning |
| --- | --- | --- | --- | --- |
| Data source | `Supplier<T>` | No input parameter | `T` | Produces or supplies a value |
| Data transformation | `Function<T, R>` | `T` | `R` | Accepts a value of type `T`, returns a value of type `R` |
| Side-effect processing | `Consumer<T>` | `T` | No return value | Receives data for logging, storage, event emission… |

For example, the following signatures convey the data contract without depending on HTTP or a message broker:

```java
Supplier<OrderEvent> newOrderEvent;
Function<OrderRequest, OrderReceipt> createReceipt;
Consumer<OrderEvent> auditEvent;
```

- `newOrderEvent` produces an `OrderEvent`; it has no input type to infer.
- `createReceipt` accepts an `OrderRequest` and creates an `OrderReceipt`.
- `auditEvent` accepts an `OrderEvent` and **has no output**. `Consumer<T>` should not be interpreted as `Function<T, Void>`: the two interfaces have different method contracts (`accept` versus `apply`).

For `Function<T, R>`, the order of generic parameters is fixed: **`T` comes first as input, `R` comes second as output**. For instance, `Function<String, Integer>` accepts a string and returns an integer; not the other way around.

## 2. Why Declare Generics on the `@Bean` Method?

Consider a business function that calculates the total amount based on product quantity. The example below uses Java 17 or later for `record`; projects using an older Java version can replace `record` with a regular DTO class.

```java
package demo.function;

import java.math.BigDecimal;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record OrderRequest(String sku, int quantity) {}

    public record OrderTotal(String sku, BigDecimal total) {}

    @Bean
    public Function<OrderRequest, OrderTotal> calculateTotal() {
        BigDecimal unitPrice = new BigDecimal("125000");

        return request -> {
            if (request == null || request.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
            );
            return new OrderTotal(request.sku(), total);
        };
    }
}
```

The key lies in the method signature:

```java
@Bean
public Function<OrderRequest, OrderTotal> calculateTotal()
```

Spring can read **the declared return type of the bean method** and recognize the two generic arguments `OrderRequest` and `OrderTotal`. The lambda `request -> ...` provides the implementation logic, but you should not expect the framework to accurately deduce the two business types merely by inspecting the lambda object at runtime.

In an application configured with the Spring Cloud Function Web adapter, an HTTP call can convert incoming JSON into `OrderRequest`, invoke the function, and convert `OrderTotal` into outgoing JSON:

```bash
curl -X POST http://localhost:8080/calculateTotal \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BK-101","quantity":2}'
```

Illustrative result:

```json
{"sku":"BK-101","total":250000}
```

This HTTP example assumes the application has installed and enabled the corresponding Web adapter, has a JSON converter supporting DTOs, and exposes the `calculateTotal` endpoint. **The generic signature provides type information; by itself, it does not create an endpoint or install a JSON converter.**

## 3. How Does Type Inference Happen?

The processing flow can be visualized by the diagram:

```mermaid
flowchart TD
    A[@Bean method returns Function&lt;OrderRequest, OrderTotal&gt;]
    B[Spring reads declared generic metadata]
    C[Spring Cloud Function registers the function in FunctionCatalog]
    D[HTTP / messaging / serverless adapter receives data]
    E[Converts input to OrderRequest when a suitable converter exists]
    F[Invokes Function.apply logic]
    G[Converts OrderTotal to output format]
    A --> B --> C --> D --> E --> F --> G
```

Three points to distinguish:

1. **Compile-time type inference:** the Java compiler checks that the lambda accepts `OrderRequest` and returns `OrderTotal` according to the `Function<OrderRequest, OrderTotal>` declaration.
2. **Runtime type discovery:** the JVM performs *type erasure* on generics, yet generic signatures declared on methods/classes can still be read via reflection. Spring uses type-resolution mechanisms, such as `ResolvableType`, to process this metadata.
3. **Data conversion at the system boundary:** Spring Cloud Function can use type information to assist converting payloads from the adapter into the type the function expects. Whether conversion succeeds still depends on the input format, `content-type`, available converters, and how the adapter invokes the function.

Therefore, **knowing `Function<OrderRequest, OrderTotal>` does not mean any arbitrary JSON can be converted into `OrderRequest`**. For example, JSON missing a required field or containing a wrong-type value can still fail at the conversion layer or in business logic.

### Illustrating How to Read Signatures with `ResolvableType`

The snippet below uses Spring Framework's API to inspect generic metadata on the very method in the example, rather than mandatory internal code of `FunctionCatalog`:

```java
import java.lang.reflect.Method;
import org.springframework.core.ResolvableType;

Method method = OrderFunctions.class.getDeclaredMethod("calculateTotal");
ResolvableType signature = ResolvableType.forMethodReturnType(method);

Class<?> inputType = signature.getGeneric(0).resolve();
Class<?> outputType = signature.getGeneric(1).resolve();

System.out.println(inputType.getSimpleName());  // OrderRequest
System.out.println(outputType.getSimpleName()); // OrderTotal
```

`getGeneric(0)` points to the `T` argument of `Function<T, R>`; `getGeneric(1)` points to `R`. The result of `resolve()` may be `null` if a generic argument cannot be resolved to a concrete class, such as some cases involving an unbounded type variable.

## 4. Type Inference with `Message<T>` and Reactive Types

A generic argument does not have to be a DTO directly. It can be a *wrapper* class containing a DTO or a data stream.

| Signature | Readable Type Information | Usage Notes |
| --- | --- | --- |
| `Function<String, Integer>` | Payload `String` → `Integer` | The string is handled as the function's input value |
| `Function<OrderRequest, OrderTotal>` | Input DTO → Output DTO | Converters can use the DTO types to convert JSON |
| `Function<Message<OrderRequest>, Message<OrderTotal>>` | Message containing `OrderRequest` → Message containing `OrderTotal` | The function manipulates both payload and headers |
| `Consumer<Message<OrderEvent>>` | Message containing `OrderEvent` | No return result |
| `Supplier<Message<OrderEvent>>` | Message containing `OrderEvent` | Can also supply headers in the output |
| `Function<Flux<OrderRequest>, Flux<OrderTotal>>` | Reactor `Flux` stream on both sides | Applies the reactive stream processing model |
| `Function<List<OrderRequest>, List<OrderTotal>>` | DTO list → DTO list | Does not by default equate to a message broker stream or batch |

Example preserving headers while processing a message:

```java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
public Function<Message<OrderRequest>, Message<OrderRequest>> tagOrder() {
    return message -> MessageBuilder
        .withPayload(message.getPayload())
        .copyHeaders(message.getHeaders())
        .setHeader("processedBy", "tagOrder")
        .build();
}
```

The `tagOrder` snippet assumes `OrderRequest` is already declared in an accessible scope. The signature `Message<OrderRequest>` makes it clear that **the function's input object is `Message`**, while the inner payload has type `OrderRequest`. Adapters may supply or map message metadata through their own mechanisms; you should not assume every protocol preserves the exact same set of headers verbatim.

With Reactor, `Function<Flux<A>, Flux<B>>` is a contract that receives a publisher and returns a publisher. It differs from `Function<A, B>`, which receives one element and returns one element. The type of each element is still expressed via `A` and `B`, while timing of processing, element count, and error signaling belong to the reactive stream. If the application uses `Mono<T>`, the generic reading works similarly, with the characteristic that the stream has at most one element.

### Nested Generics

For the signature `Function<Message<List<OrderRequest>>, Message<OrderTotal>>`, you can read it from the outside in:

```text
Function<
    Message<List<OrderRequest>>,  // input: Message -> List -> OrderRequest
    Message<OrderTotal>           // output: Message -> OrderTotal
>
```

The framework can recognize not only the outer `Message` class but also the nested generic arguments, provided this information is preserved in the declaration. However, collection deserialization and batch handling still depend on the specific converter/adapter; verify them over the protocol in use.

## 5. Composing Multiple Functions Based on Input and Output Types

Spring Cloud Function supports *function composition* via function names in `FunctionCatalog` or the `spring.cloud.function.definition` configuration. Generic information helps developers determine whether links in the chain are compatible.

Suppose the application defines:

```java
@Bean
Function<OrderRequest, OrderTotal> calculateTotal() { /* ... */ }

@Bean
Function<OrderTotal, Invoice> createInvoice() { /* ... */ }
```

These are two **illustrative signatures**, not two complete compilable methods. You can declare the processing pipeline:

```yaml
spring:
  cloud:
    function:
      definition: calculateTotal|createInvoice
```

The type contract of the pipeline is:

```text
OrderRequest --calculateTotal--> OrderTotal --createInvoice--> Invoice
```

The `OrderTotal` output of the first function matches the `OrderTotal` input of the second function. Conversely, when chaining `Function<OrderRequest, OrderTotal>` with `Function<Customer, Invoice>`, the two types at the junction do not match. Do not rely on an unverified implicit conversion to make composition work; adjust the signatures or write an explicit conversion function.

When composition mixes a function handling `Message<T>` with a function taking only payload `T`, also check how the framework handles wrappers/headers at each junction. Checking Java type compatibility is only one part of verifying the entire data path.

## 6. Cases That Lose or Obscure Type Information

**Case 1 — using a raw type.**

```java
@Bean
@SuppressWarnings({"rawtypes", "unchecked"})
public Function unsafeFunction() {
    return value -> value;
}
```

`Function` without generic arguments prevents the bean signature from expressing concrete payload types. The compiler also cannot check inputs and outputs against the business contract. The framework may have to rely on other information or lack sufficient data to perform the desired conversion.

**Case 2 — declaring types too broadly.**

```java
@Bean
public Function<Object, Object> opaqueFunction() {
    return value -> value;
}
```

Here generic information is not completely erased, but it only states `Object` → `Object`. An adapter cannot conclude from this that the payload needs to be `OrderRequest`. `Function<?, ?>` or an overly general bean return type causes the same problem when concrete DTOs must be resolved.

**Case 3 — storing a lambda in a variable that drops the business contract.**

```java
Function raw = (Function) (value -> value);
```

Casting to a raw type removes generic checking at the usage site. Even if the inner logic always operates on a specific DTO, reflection on the lambda object is not a reliable way to recover that DTO's name.

**Case 4 — using unbounded generics.**

```java
class CommonFunctions<T> {
    Function<T, T> identity() {
        return value -> value;
    }
}
```

If `T` has not been bound to a concrete class at bean registration time, the system does not yet have enough metadata to know which DTO to deserialize. A concrete bean method should declare the actual data types, for example `Function<OrderRequest, OrderRequest>`.

**Case 5 — wrappers or proxies hiding the signature.**

A class implementing `Function<OrderRequest, OrderTotal>` can carry generic information on the interface it implements. However, if you register it via a factory, proxy, or a method returning `Object`/raw `Function`, the metadata observed by the framework may differ from what you expect. When using these techniques, verify both the registered type and the actual conversion behavior through the adapter.

To reduce risk: declare concrete types directly on `@Bean`, preserve generics across intermediate layers, prefer well-structured DTOs, and avoid unnecessary casts.

## 7. Verifying the Type Contract via `FunctionCatalog`

`FunctionCatalog` lets you look up functions by name or composition expression. The following example invokes a function registered in the Spring context with strongly typed Java data:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest
class OrderFunctionsTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void calculatesTotal() {
        Function<OrderFunctions.OrderRequest, OrderFunctions.OrderTotal> function =
            catalog.lookup("calculateTotal");

        OrderFunctions.OrderTotal result = function.apply(
            new OrderFunctions.OrderRequest("BK-101", 2)
        );

        assertEquals(new BigDecimal("250000"), result.total());
    }
}
```

This test requires a Spring Boot test environment with `OrderFunctions` scanned or imported into the context along with the relevant dependencies. It verifies the registered name and the function's logic on Java objects. To verify type inference when JSON or events pass through an adapter, **an integration test at the protocol boundary is also needed**, because a direct Java call does not exercise the payload conversion step.

When a request fails, you can diagnose in order:

1. Check whether `@Bean` returns `Supplier<T>`, `Function<T, R>`, or `Consumer<T>` with concrete types.
2. Check whether the name in `FunctionCatalog`/`spring.cloud.function.definition` selects the intended function or function chain.
3. Check whether the payload shape, `content-type`, converter, and DTO are compatible.
4. If using `Message<T>`, `List<T>`, `Flux<T>`, or `Mono<T>`, identify which layer is the wrapper, which is the business data, and how the adapter interprets them.
5. If the error only appears after composition, check whether each function's output matches the immediately following function's input.

## 8. Self-Check Practice

**Scenario A:** You declare `Function<String, Integer> countCharacters`. What input and output types can the framework read?

**Answer:** `String` as input and `Integer` as output. It is not necessary to inspect the lambda body to determine these two types.

**Scenario B:** A `@Bean` returns a raw `Function`, yet inside the lambda it processes `OrderRequest`. Why is the HTTP API not guaranteed to convert JSON into `OrderRequest`?

**Answer:** The published signature does not preserve `OrderRequest`; type erasure and the nature of lambdas do not guarantee enough metadata to recover the DTO. You should change the signature to `Function<OrderRequest, OrderTotal>` or an appropriate concrete contract.

**Scenario C:** Can `Function<OrderRequest, OrderTotal>` be composed with `Function<OrderTotal, Invoice>`? What else must be checked?

**Answer:** The two types at the junction are compatible in terms of declaration. You still need to check the logic, converters when going through an adapter, message wrappers, and actual behavior if using an external protocol.

**Scenario D:** Does `Consumer<Message<OrderEvent>>` return `Message<Void>`?

**Answer:** No. `Consumer` accepts a `Message<OrderEvent>` and returns no value. The invoking protocol may have its own acknowledgment response, but that is not a Java output type of `Consumer`.

## Takeaways

The generic signature is the **data contract** of a function in Spring Cloud Function: `Supplier<T>` specifies the supplied type, `Function<T, R>` specifies the input/output pair, and `Consumer<T>` specifies only the input. Keeping this contract clear on the bean helps both the framework and readers understand the expected types, supporting message conversion and function composition via `FunctionCatalog`. Type erasure does not wipe out metadata from a concrete generic declaration, nor does it let the framework guess business types obscured by raw types or overly broad declarations. To be confident a function runs properly over HTTP, messaging, or serverless, test both the Java logic and the conversion boundary of the adapter in use.
