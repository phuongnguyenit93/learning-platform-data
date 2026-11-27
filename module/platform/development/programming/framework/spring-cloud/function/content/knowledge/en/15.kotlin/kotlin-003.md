# Declaring Functions via @Bean with Explicit Type Signatures

## 1. Why Must the Signature of a Functional Bean Be Declared Explicitly?

In **Spring Cloud Function** (the `SPRING_CLOUD_FUNCTION` module), we package business logic using `Supplier`, `Function`, and `Consumer`, and then reuse it across HTTP, event streams, or serverless environments through appropriate adapters. `FunctionCatalog` helps look up functions, standardize invocation, support composition, and convert messages based on input/output types.

Kotlin lets you write very concise lambdas:

~~~kotlin
val normalize = { value: String -> value.trim().uppercase() }
~~~

However, a variable holding a lambda **is not automatically a Spring bean**. Even when adding `@Bean`, an unclear type declaration makes the contract harder to verify for adapters, code readers, and `FunctionCatalog`.

The goal of this guide is to declare **`@Bean` with an explicit return type**, so that:

- You know precisely which input type `I` the function takes and which output type `O` it returns.
- You distinguish between `Supplier`, `Function`, and `Consumer`, even when using Kotlin function types.
- You preserve type information to support JSON/message conversion and composition.
- You register the bean under the right name and look it up via `FunctionCatalog`.
- You test both the **Kotlin logic** and **Spring's functional bean recognition process**.

## 2. Kotlin Signatures Corresponding to the Three Java Interfaces

Spring Cloud Function supports Kotlin lambdas registered as Spring beans (by recognizing Kotlin function types on the classpath), alongside the standard Java functional interfaces.

| Kotlin Type | Purpose | Java Equivalent |
| --- | --- | --- |
| `() -> O` | Produces an `O` without taking input | `Supplier<O>` |
| `(I) -> O` | Transforms `I` into `O` | `Function<I, O>` |
| `(I) -> Unit` | Receives `I` and performs a side effect | `Consumer<I>` |

Example:

~~~kotlin
@Bean
fun newCode(): () -> String = { "ORD-101" }

@Bean
fun normalizeCode(): (String) -> String =
    { value -> value.trim().uppercase() }

@Bean
fun auditCode(): (String) -> Unit =
    { value -> println("AUDIT: " + value) }
~~~

These `@Bean` methods must be declared inside a **Spring configuration class that is actually loaded**. The most important part is the return type of each method:

- `newCode(): () -> String` makes clear that the bean takes no arguments and returns `String`.
- `normalizeCode(): (String) -> String` makes clear both the input and output types.
- `auditCode(): (String) -> Unit` makes clear that this operation returns no business payload.

Kotlin `(String) -> String` relies on Kotlin's function type on the JVM, not `java.util.function.Function<String, String>` itself. Spring Cloud Function recognizes and normalizes eligible Kotlin lambdas once they are registered as beans. `Unit` in Kotlin does not mean emitting a `Unit` object as a messaging output payload.

## 3. Complete Example: Registering Supplier, Function, and Consumer

An order management system needs to generate sample orders, normalize order IDs, classify orders, and record audit logs. Here is how to declare them with explicit types in **Kotlin/JVM**:

~~~kotlin
package example.orders

import java.util.Locale
import java.util.UUID
import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

data class Order(
    val id: String,
    val totalVnd: Long
)

data class Decision(
    val orderId: String,
    val category: String
)

@SpringBootApplication
class OrdersApplication

fun main(args: Array<String>) {
    runApplication<OrdersApplication>(*args)
}

@Configuration
class OrderFunctions {

    // 0 -> 1: corresponds to Supplier<Order>.
    @Bean
    fun sampleOrder(): () -> Order = {
        Order(
            id = UUID.randomUUID().toString(),
            totalVnd = 250_000L
        )
    }

    // 1 -> 1: corresponds to Function<String, String>.
    @Bean
    fun normalizeOrderId(): (String) -> String = { rawId ->
        rawId.trim().uppercase(Locale.ROOT)
    }

    // 1 -> 1: corresponds to Function<Order, Decision>.
    @Bean
    fun classifyOrder(): (Order) -> Decision = { order ->
        Decision(
            orderId = order.id,
            category = if (order.totalVnd >= 1_000_000L)
                "PRIORITY" else "STANDARD"
        )
    }

    // 1 -> 0: corresponds to Consumer<Decision>.
    @Bean
    fun auditDecision(): (Decision) -> Unit = { decision ->
        println("Classified " + decision.orderId
                + ": " + decision.category)
    }
}
~~~

The `Order`/`Decision` classes are **data classes**: business data types independent of HTTP or any broker. The beans are registered when Spring initializes `OrderFunctions` in the application context. The example uses a recent enough Java/Kotlin version for `uppercase(Locale.ROOT)`; `println` is only for illustration and should be replaced with a logger or audit service in production.

### 3.1. Analyzing Each Bean's Contract

| Default Bean Name | Bean Type | Input | Output |
| --- | --- | --- | --- |
| `sampleOrder` | `() -> Order` | None | `Order` |
| `normalizeOrderId` | `(String) -> String` | `String` | `String` |
| `classifyOrder` | `(Order) -> Decision` | `Order` | `Decision` |
| `auditDecision` | `(Decision) -> Unit` | `Decision` | No business payload |

The **default bean name** is typically derived from the `@Bean` method name. `FunctionCatalog.lookup("classifyOrder")` searches for the bean named `classifyOrder`, not by the name `OrderFunctions` or the return type `Decision`.

### 3.2. Is Type Inference Wrong?

The following snippet is valid Kotlin and can be recognized by Spring Cloud Function:

~~~kotlin
@Bean
fun classifyInferred() = { order: Order ->
    Decision(order.id, "STANDARD")
}
~~~

However, at a public bean boundary, declaring it as:

~~~kotlin
@Bean
fun classifyExplicit(): (Order) -> Decision = { order ->
    Decision(
        order.id,
        if (order.totalVnd >= 1_000_000L) "PRIORITY" else "STANDARD"
    )
}
~~~

lets readers and tooling see the `(Order) -> Decision` contract right on the method, instead of having to infer it from the body expression. One should not claim that every `@Bean` function using type inference will fail; **explicit types are a sound design convention**, not a claim that the compiler always fails to infer the type.

## 4. `@Bean` Must Belong to a Configuration Discovered by Spring

A Kotlin lambda, even with proper generics, **does not automatically appear** in `FunctionCatalog`. The actual flow is:

~~~text
@Configuration (scanned/imported by Spring)
    |
    +-- @Bean fun classifyOrder(): (Order) -> Decision
                    |
                    v
          Spring ApplicationContext
             bean "classifyOrder"
                    |
                    v
       Kotlin lambda recognition/wrapper
                    |
                    v
             FunctionCatalog
             lookup("classifyOrder")
                    |
                    v
        HTTP / Stream / Serverless adapter
~~~

If you only have:

~~~kotlin
fun uppercaseValue(value: String): String = value.uppercase()

val uppercaseLambda: (String) -> String = { it.uppercase() }
~~~

then Spring does not automatically treat these two declarations as beans. Register an existing function by referencing it:

~~~kotlin
@Configuration
class ReusedFunctions {

    @Bean
    fun uppercaseValueBean(): (String) -> String = ::uppercaseValue
}
~~~

The lookup name in this case is `uppercaseValueBean`. You can specify a custom name with `@Bean("externalUppercase")`; in that case, you must look up `externalUppercase`.

**Kotlin classes are `final` by default.** With Spring Boot, the `kotlin("plugin.spring")` plugin is typically used to automatically open Spring-annotated classes/members as required by Spring's proxy mechanism. It **does not replace** declaring `@Bean` and does not automatically turn every top-level function into a Spring bean.

## 5. Java Functional Interfaces in Kotlin: Another Explicit Option

Within the same Kotlin project, you can declare beans that directly return Java's `Supplier`, `Function`, and `Consumer`:

~~~kotlin
import java.util.Locale
import java.util.function.Consumer
import java.util.function.Function
import java.util.function.Supplier
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@Configuration
class JavaStyleFunctions {

    @Bean
    fun fixedCode(): Supplier<String> =
        Supplier { "ORD-101" }

    @Bean
    fun uppercaseCode(): Function<String, String> =
        Function { input -> input.trim().uppercase(Locale.ROOT) }

    @Bean
    fun logCode(): Consumer<String> =
        Consumer { input -> println("AUDIT: " + input) }
}
~~~

| Aspect | Kotlin Function Type | Java SAM Interface Written in Kotlin |
| --- | --- | --- |
| Bean return type | `(String) -> String` | `Function<String, String>` |
| Native JVM type | Kotlin `Function1` | Java `Function` |
| Lambda syntax | `{ value -> ... }` | `Function { value -> ... }` |
| How SCF supports it | Recognizes and normalizes Kotlin lambdas | Supported directly from the Java model |
| Commonly chosen when | Preferring idiomatic Kotlin | Needing explicit Java API/SAM types |

Do not interpret these two approaches as having to declare **two beans for the same task**. Choose one consistent public contract and test accordingly.

## 6. Generic Type Information Helps Payload Conversion

The signature `(Order) -> Decision` states that the function accepts an `Order` and returns a `Decision`. If an adapter receives JSON:

~~~json
{
  "id": "O-101",
  "totalVnd": 1500000
}
~~~

then when a converter is properly configured, the business result can be serialized as:

~~~json
{
  "orderId": "O-101",
  "category": "PRIORITY"
}
~~~

Converting JSON into a Kotlin `data class` requires the JSON/Kotlin module dependency appropriate for the Spring Boot/Jackson version in use, and the payload must match the schema. **An explicit signature does not replace validation**: for example, a request missing `totalVnd` must be handled according to the application's error policy.

### 6.1. Avoid `Any` When the Business Type Is Known

~~~kotlin
// Type is too broad if it actually only processes Order.
@Bean
fun identityUnclear(): (Any) -> Any = { it }

// Publish a concrete contract.
@Bean
fun orderSummary(): (Order) -> String = { order ->
    order.id + ":" + order.totalVnd
}
~~~

`(Any) -> Any` is occasionally intentional, but if an adapter needs to instantiate `Order` from JSON, the generic type `Any` fails to convey the conversion target. Java/Kotlin on the JVM have **type erasure**; storing a lambda under an overly broad type can lose metadata needed at the framework boundary.

With `@Bean`, you should declare full types, especially when generics are nested. If registering a function manually without method metadata, you may need `FunctionRegistration` to supply type information. Do not assume a lambda object always carries complete `I/O` type info at runtime.

### 6.2. A Collection Is Not Multiple Outputs

~~~kotlin
data class OrderWithItems(
    val id: String,
    val skus: List<String>
)

@Bean
fun extractSkus(): (OrderWithItems) -> List<String> =
    { order -> order.skus }
~~~

A bean returning `List<String>` is still **a single function with a single return value**. The number of elements in the list is not the number of output bindings. Over HTTP, the adapter can serialize the list as a JSON array; Spring Cloud Stream has dedicated handling for batch/message list cases, but it does not automatically create multiple destinations because of that.

## 7. Declaring `Message<T>` When Headers Are Needed

If you need `correlationId` or tracing metadata, you can declare the message type explicitly:

~~~kotlin
import org.springframework.context.annotation.Bean
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

// Place this @Bean inside a @Configuration class.
@Bean
fun classifyMessage(): (Message<Order>) -> Message<Decision> = { input ->
    val order: Order = input.payload
    val decision = Decision(
        orderId = order.id,
        category = if (order.totalVnd >= 1_000_000L)
            "PRIORITY" else "STANDARD"
    )

    val builder = MessageBuilder.withPayload(decision)
    input.headers["correlationId"]?.let { correlation ->
        builder.setHeader("correlationId", correlation)
    }
    builder.build()
}
~~~

`Message<Order>` contains an **`Order` payload along with headers**, not two input bindings. The code explicitly preserves the `correlationId` header on the resulting message. When changing payloads, do not assume all headers are automatically copied across every adapter/converter.

When headers are not needed, the signature `(Order) -> Decision` is usually simpler. Choose the input type based on the **business information actually needed**.

## 8. Reactive Signatures Must Declare Both Publisher Types Explicitly

Spring Cloud Function also supports Project Reactor `Flux`/`Mono`. In Kotlin, you can declare:

~~~kotlin
import org.springframework.context.annotation.Bean
import reactor.core.publisher.Flux

// Place this @Bean inside a @Configuration class.
@Bean
fun classifyStream(): (Flux<Order>) -> Flux<Decision> = { orders ->
    orders.map { order ->
        Decision(
            order.id,
            if (order.totalVnd >= 1_000_000L)
                "PRIORITY" else "STANDARD"
        )
    }
}
~~~

This function has **one input stream and one output stream**. `Flux<Decision>` can emit many records while remaining a single logical output binding when used with Spring Cloud Stream.

**Lifecycle difference:** a reactive function usually constructs the pipeline when invoked; items flow once a subscription occurs. Imperative retry/error-handler mechanisms do not automatically apply item-by-item inside a `Flux`.

### 8.1. Multiple Ports Require `TupleN<Flux<...>>` Types

If you need to split one source into two ports when using Spring Cloud Stream, declare the contract explicitly:

~~~kotlin
import java.util.function.Function
import reactor.core.publisher.Flux
import reactor.util.function.Tuple2
import reactor.util.function.Tuples

// Place this @Bean inside a @Configuration class.
@Bean
fun splitOrders(): Function<
    Flux<Order>,
    Tuple2<Flux<Order>, Flux<Order>>
> = Function { input ->
    val shared: Flux<Order> = input.publish().autoConnect(2)
    val priority = shared.filter { it.totalVnd >= 1_000_000L }
    val standard = shared.filter { it.totalVnd < 1_000_000L }
    Tuples.of(priority, standard)
}
~~~

This example intentionally uses **Java `Function` with fully declared generics** for a multi-port contract: one input binding and two output bindings when the adapter supports reactive function arity. `getT1()` corresponds to output 0, and `getT2()` corresponds to output 1.

`autoConnect(2)` assumes **both outputs have subscribers**; if only one output is subscribed to, the upstream source may not connect. A production design should examine subscriptions, backpressure, and errors on each branch.

**Do not confuse:** `Flux<Tuple2<A, B>>` is a single stream emitting pairs; `Tuple2<Flux<A>, Flux<B>>` is two independent streams. And HTTP/serverless does not automatically create two endpoints or two responses just because a bean signature returns a tuple.

## 9. Selecting Functions and Configuring Adapters

With multiple beans in the application context, specify the target name explicitly:

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrder
~~~

Example when integrating with **Spring Cloud Stream**:

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrder
    stream:
      bindings:
        classifyOrder-in-0:
          destination: orders.created
          content-type: application/json
        classifyOrder-out-0:
          destination: orders.classified
          content-type: application/json
~~~

`-in-0` and `-out-0` are Spring Cloud Stream binding names, not Kotlin variable names. Spring Cloud Stream and a suitable binder are required; a `@Bean` by itself **does not create a message broker/topic**.

### Composition Only Combines Compatible Functions

~~~kotlin
@Bean
fun cleanCode(): (String) -> String =
    { code -> code.trim().uppercase() }

@Bean
fun appendReady(): (String) -> String =
    { code -> code + "-READY" }
~~~

These two beans can be composed:

~~~properties
spring.cloud.function.definition=cleanCode|appendReady
~~~

The `String` output of `cleanCode` matches the `String` input of `appendReady`. This is **sequential composition**, not automatic fan-out to multiple destinations. To compose `(Order) -> Decision` with `(String) -> String`, an explicit contract conversion is needed; do not rely solely on the fact that both beans are functions.

## 10. Verifying with Unit Tests and `FunctionCatalog`

To verify that the logic works, call the lambda directly. To verify that the framework recognizes the bean, start the Spring context and look it up via `FunctionCatalog`.

### 10.1. Direct Unit Test

~~~kotlin
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class OrderFunctionsUnitTest {

    @Test
    fun classifiesPriorityOrder() {
        val classify: (Order) -> Decision =
            OrderFunctions().classifyOrder()

        val result = classify(Order("O-101", 1_000_000L))

        assertEquals(
            Decision("O-101", "PRIORITY"), result
        )
    }

    @Test
    fun classifiesStandardOrder() {
        val classify = OrderFunctions().classifyOrder()
        val result = classify(Order("O-102", 999_999L))

        assertEquals(
            Decision("O-102", "STANDARD"), result
        )
    }
}
~~~

This unit test checks the classification rule and boundary values, and **does not** prove that Spring created a functional bean.

### 10.2. Spring Context Test for `FunctionCatalog`

~~~kotlin
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

@SpringBootTest(classes = [OrdersApplication::class])
class OrderFunctionsCatalogTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun canLookupClassifyOrder() {
        val function = requireNotNull(
            catalog.lookup<Function<Order, Decision>>(
                "classifyOrder"
            )
        ) { "classifyOrder not found in FunctionCatalog" }

        val result = function.apply(Order("O-103", 1_500_000L))

        assertEquals(
            Decision("O-103", "PRIORITY"), result
        )
    }
}
~~~

This test requires the `spring-cloud-function-context` dependency and appropriate Spring Boot Test support. It verifies that **the bean is registered and can be looked up** through the catalog. `lookup` may return a wrapper integrating conversion/composition, so you neither need to nor should compare the runtime class of the lookup result with the original lambda.

To verify JSON HTTP or topic messaging, add an **adapter integration test**; unit/context tests do not verify serializers, headers, destinations, and external triggers.

## 11. Common Mistakes When Declaring Kotlin `@Bean` Functions

| Symptom | Cause to Check | How to Verify |
| --- | --- | --- |
| Lambda works when called directly, but catalog cannot find it | Bean is not registered or wrong name | Verify `@Configuration`, package scan, and `@Bean` name |
| Bean exists in Spring context, but is not recognized | Incompatible signature, missing Kotlin/type metadata support | Declare explicit return type and check dependencies/framework |
| `@Configuration` proxy error in Kotlin | Class is `final` by default | Use `kotlin("plugin.spring")` or appropriate `open` modifiers |
| JSON data does not convert to `Order` | Missing converter/Kotlin Jackson module or schema mismatch | Check payload, `content-type`, and input type |
| `(Any) -> Any` signature causes unpredictable conversion | Generic type is too broad | Declare `(Order) -> Decision` |
| Adapter binds the wrong bean when multiple functions exist | `spring.cloud.function.definition` is not set | Set `spring.cloud.function.definition` explicitly |
| Treating `Unit` as a mandatory output event | Confusing consumer with function | Use `(I) -> Unit` for side effects |
| Interpreting `List<O>` as multiple output bindings | Confusing a Collection value with arity | Review function and adapter contracts |
| Treating `suspend`/`Flow` as `Function`/`Flux` | Different execution/coroutine models | Use supported bridges/adapters, do not assume automatic mapping |
| Catalog test passes, but broker receives no messages | Wrong binding/binder/destination | Write an integration test with the actual adapter |

### Nullability Does Not Mean Empty Responses Are Supported Everywhere

~~~kotlin
@Bean
fun lookupCategory(): (String) -> String? = { id ->
    if (id.isBlank()) null else "STANDARD"
}
~~~

This Kotlin signature compiles, but `null` is not automatically a valid message payload or identical HTTP response across all adapters. For real business cases, explicitly define the "no result" policy: an explicit result type, a structured error, or an empty stream depending on the contract.

## 12. Self-Check Exercises

**Question 1.** What are the default bean name, input type, and output type of the following function?

~~~kotlin
@Bean
fun parseCode(): (String) -> Long = { it.toLong() }
~~~

**Answer:** Bean `parseCode`, input `String`, output `Long`; equivalent to `Function<String, Long>`.

**Question 2.** Does `@Bean fun inferred() = { value: String -> value.uppercase() }` necessarily fail to be recognized by Spring Cloud Function?

**Answer:** You should not claim that. Kotlin can infer the appropriate function type. Nevertheless, `fun inferred(): (String) -> String` makes the contract clearer and more stable at the bean boundary.

**Question 3.** Does `@Bean fun audit(): (Order) -> Unit` produce a `Unit` output that should be sent as a message?

**Answer:** No. This is a consumer equivalent to `Consumer<Order>` and returns no business payload.

**Question 4.** Why does `(Order) -> Decision` support conversion better than `(Any) -> Any` when receiving order JSON?

**Answer:** It specifies the concrete target type so the framework can select a converter, and it helps validate the input/output data contract.

**Question 5.** Is calling `OrderFunctions().classifyOrder()` in a unit test enough to prove `FunctionCatalog` can find the bean?

**Answer:** Not yet. You need to start the Spring application context, call `FunctionCatalog.lookup("classifyOrder")`, and verify the result.

**Question 6.** Does `@Bean fun extractSkus(): (OrderWithItems) -> List<String>` create as many output bindings as the number of SKUs?

**Answer:** No. A `List` containing multiple elements is still **a single return value**. The adapter determines how to serialize/transmit the result according to its own contract.

## References

- [Spring Cloud Function — Programming model, Kotlin lambda support, and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Boot — Kotlin Support, Kotlin runtime, and reflection](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Framework — Declaring @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Kotlin — Spring compiler plugin](https://kotlinlang.org/docs/kotlin-spring-plugin.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
