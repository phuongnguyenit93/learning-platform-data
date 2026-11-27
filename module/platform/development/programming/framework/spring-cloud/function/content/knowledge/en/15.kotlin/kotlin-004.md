# Unit, Nullability, and Java Type Interoperability

## 1. Context: A Kotlin Type Can Be Interpreted Differently at the Java and Adapter Boundary

**Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`) decouples business logic from how a function is invoked: you can register a `Supplier`, `Function`, or `Consumer`, look it up via `FunctionCatalog`, perform composition, convert messages, and connect it over HTTP, events, or serverless environments via an appropriate adapter.

Kotlin supports non-null types, nullable types, and the `Unit` type. However, the Spring Cloud Function ecosystem runs on the JVM, where many APIs are declared in Java, including `java.util.function.Function`, `Consumer`, `Void`, and values that may be `null`. **Being valid in Kotlin does not always mean an adapter can represent that result as an HTTP response or a broker message.**

The three most important questions in this guide are:

1. **How does `Unit` differ from Java `void` and `java.lang.Void`?**
2. **How far do `T` and `T?` protect Kotlin code when data comes from Java, JSON, or a broker?**
3. **How do you write functional beans with clear contracts that do not accidentally emit `null` through Reactor/`Message`, while staying reusable?**

Examples throughout use orders, coupon codes, and classification results. Error-handling approaches are described explicitly without assuming that every HTTP, Spring Cloud Stream, or serverless adapter shares the same retry and serialization mechanics.

## 2. Kotlin Unit, Java void, and java.lang.Void Are Not Identical

### 2.1. Kotlin Unit Is a Type with a Singleton Value

In Kotlin, a function that returns no business value is declared with `Unit`:

~~~kotlin
fun recordAudit(orderId: String): Unit {
    println("AUDIT: " + orderId)
}

val result: Unit = recordAudit("O-101")
~~~

This function evaluates to Kotlin's **single `Unit` value**, which developers usually ignore because it only indicates that the operation finished. When the return type is omitted, a function that only performs side effects can also be inferred as `Unit` by Kotlin:

~~~kotlin
fun recordAuditBriefly(orderId: String) {
    println("AUDIT: " + orderId)
}
~~~

**Key point:** `Unit` is not `null`; nor is it a business payload to be emitted.

### 2.2. Java void Is a Special Method Return Type

Java uses `void` when a method returns no value:

~~~java
public void recordAudit(String orderId) {
    System.out.println("AUDIT: " + orderId);
}
~~~

When Kotlin **calls** a Java method returning `void`, Kotlin treats the result at the call site as `Unit`:

~~~kotlin
// Suppose legacyAudit is a Java object with a void recordAudit(String) method.
val outcome: Unit = legacyAudit.recordAudit("O-101")
~~~

This is a **Java → Kotlin interoperability** rule; it does not mean Java `void` is a class holding a `Unit` instance.

### 2.3. java.lang.Void Is a Reference Class, Not void

`java.lang.Void` is a special Java class that typically appears as a **generic type argument** when an API needs to represent "no result". It has no normal instances to return.

~~~java
// A Java Function still has a return type R, even if R is Void.
Function<String, Void> auditThenReturnNull = value -> {
    System.out.println(value);
    return null;
};

// A Java Consumer has no return value in its contract.
Consumer<String> audit = value -> System.out.println(value);
~~~

In Kotlin, `Void?` can represent the case where a Java `Void` result is `null`:

~~~kotlin
import java.util.function.Function

val legacy: Function<String, Void?> = Function { value ->
    println("AUDIT: " + value)
    null
}
~~~

This illustrates interoperating with a Java API that already chose `Void`. Do **not** use `Function<I, Void?>` to replace `Consumer<I>` in a new bean when the business logic genuinely only has side effects: recognition mechanisms and adapters may treat a `Function` with a nullable result differently from a `Consumer`.

| Concept | Practical Meaning | When to Use |
| --- | --- | --- |
| Kotlin `Unit` | Result type of an operation returning no business data | Kotlin function type `(I) -> Unit` |
| Java `void` | Java method with no return value | `Consumer.accept(...)` method, imperative APIs |
| Java `Void` | Reference type with no regular instances | Java APIs/generics requiring the `Void` type |
| Kotlin `Void?` | Typically only represents `null` for a `Void` result from Java | Legacy Java integration, with clear explanation |
| Kotlin `Nothing` | Type of an expression that never completes normally | `throw`, functions that always throw exceptions; **never** replaces `Unit` |

## 3. From (I) -> Unit to a Spring Cloud Function Consumer

Spring Cloud Function supports recognizing Kotlin lambdas registered as Spring beans. The Kotlin signature `(I) -> Unit` corresponds to Java's **`Consumer<I>`** model, while `(I) -> O` corresponds to **`Function<I, O>`**.

~~~kotlin
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@Configuration
class AuditFunctions {

    @Bean
    fun auditOrder(): (String) -> Unit = { orderId ->
        println("Recorded order: " + orderId)
    }
}
~~~

The `auditOrder` bean has a contract of **one input, no returned business payload**. When Spring Cloud Stream binds a consumer with this name, there will typically be an **input binding** `auditOrder-in-0` and no output binding derived from the `Unit` result.

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrder
    stream:
      bindings:
        auditOrder-in-0:
          destination: orders.audit
~~~

Messaging configuration requires Spring Cloud Stream and an appropriate binder. `auditOrder` can still be invoked directly in Kotlin; `@Bean` and `FunctionCatalog` do not create a broker by themselves.

### 3.1. Using Java Consumer in Kotlin Code Is Also Valid

~~~kotlin
import java.util.function.Consumer
import org.springframework.context.annotation.Bean

// Place inside a @Configuration class.
@Bean
fun auditWithJavaSam(): Consumer<String> =
    Consumer { orderId -> println("AUDIT: " + orderId) }
~~~

The return type here is `java.util.function.Consumer<String>`; the lambda is converted to a Java SAM. If other libraries already work with `Consumer`, this declaration keeps the Java boundary explicit.

**Do not confuse:**

~~~kotlin
// Consumer: no returned payload.
@Bean
fun audit(): (String) -> Unit = { println(it) }

// Function: returns a business status string.
@Bean
fun acknowledge(): (String) -> String = { "ACK:" + it }
~~~

If the client expects an `ACK` status as a message or response, declare an explicit business output type. If only logging is needed, `Unit` is the right contract.

### 3.2. Reactive Consumer Differs from Imperative Consumer

~~~kotlin
import reactor.core.publisher.Flux

// Do not copy blindly without controlling the subscription.
val reactiveConsumer: (Flux<String>) -> Unit = { events ->
    events.subscribe { println(it) }
}
~~~

`Consumer<Flux<T>>` or the equivalent Kotlin lambda receives the entire publisher and returns `Unit`/`void`, so there is no result publisher for the framework to subscribe to automatically. Calling `subscribe()` manually places subscription lifecycle, error handling, and cancellation responsibilities on the business code. According to Spring Cloud Function/Stream documentation, you should be cautious with this pattern; many cases fit better with a reactive function returning a completion-signaling publisher, such as `Function<Flux<T>, Mono<Void>>` when the adapter supports that signature.

## 4. Kotlin Nullability: String and String? Carry Different Contracts

Kotlin makes a clear distinction:

~~~kotlin
val required: String = "O-101"
val optional: String? = null

// required = null       // Compile error in standard Kotlin.
// optional.length       // Compile error without nullable handling.
val safeLength: Int = optional?.length ?: 0
~~~

| Notation | Contract | Safe Operations |
| --- | --- | --- |
| `String` | Kotlin caller must supply a non-null value | `value.length` |
| `String?` | Value may be absent | `value?.length`, `?:`, `if (value != null)` |
| `Any` | Non-null value that may belong to various types | Check/cast before type-specific operations |
| `Any?` | Arbitrary value or `null` | Check both type and null |
| `List<String?>` | List may contain null elements | `filterNotNull()` or per-element handling |
| `List<String>?` | The list itself may be null | `orEmpty()`, `?.` |

The last two collection types **differ**: one allows null **inside** the list, whereas the other allows the **entire list** to be null. When data arrives from JSON/Java, both constraints can affect conversion and validation.

### 4.1. Distinguish "Absent", "Empty", and "Invalid"

Coupon code example:

~~~kotlin
data class OrderInput(
    val id: String,
    val totalVnd: Long,
    val couponCode: String?
)
~~~

`couponCode: String?` lets the business logic treat the coupon code as optional. However, different situations can occur:

- `couponCode` has a valid string such as `"SAVE10"`.
- The field has value `null`.
- The field is an empty string `""` or whitespace only.
- The field is completely absent from JSON.
- The field contains a number or an object instead of a string.

You must not assume these cases are always handled identically by converters: the Jackson Kotlin module, constructor defaults, annotations, deserialization settings, and validation can determine whether parsing succeeds or fails. **A Kotlin nullable type does not by itself replace a JSON/schema contract or Bean Validation.**

## 5. Designing Beans with Nullable Inputs That Return Clear Results

Instead of returning `null` and leaving adapters to guess its meaning, return a data type that explicitly represents the state:

~~~kotlin
data class Decision(
    val orderId: String,
    val category: String,
    val note: String
)

@Configuration
class ClassificationFunctions {

    @Bean
    fun classifyOrder(): (OrderInput) -> Decision = { order ->
        require(order.id.isNotBlank()) {
            "order id must not be blank"
        }
        require(order.totalVnd >= 0L) {
            "totalVnd must not be negative"
        }

        val code: String? = order.couponCode
            ?.trim()
            ?.takeIf { it.isNotEmpty() }

        Decision(
            orderId = order.id,
            category = if (order.totalVnd >= 1_000_000L)
                "PRIORITY" else "STANDARD",
            note = code?.let { "COUPON:" + it } ?: "NO_COUPON"
        )
    }
}
~~~

This code has three layers of responsibility:

1. `OrderInput` defines the shape of data **after successful deserialization**.
2. `require(...)` checks runtime business invariants (blank `id`, negative `totalVnd`).
3. `couponCode?.trim()?.takeIf { ... }` handles the optional code; the resulting `Decision` always has a clear structure.

**Note:** if JSON is missing a required field or cannot be converted to `OrderInput`, the error may occur **before** the `classifyOrder` lambda is invoked. Likewise, `require` throwing `IllegalArgumentException` does not automatically become HTTP 400 or a dead-letter message: error reporting depends on the adapter and configuration.

### 5.1. An Explicit Status Output Value Instead of null

If you need to represent acceptance/rejection, you can return a DTO with status:

~~~kotlin
data class ValidationResult(
    val accepted: Boolean,
    val reason: String?
)

val validate: (OrderInput) -> ValidationResult = { order ->
    if (order.totalVnd < 0L) {
        ValidationResult(false, "NEGATIVE_AMOUNT")
    } else {
        ValidationResult(true, null)
    }
}
~~~

When serialized to JSON, `reason: String?` can be represented as `null` or omitted depending on the Jackson policy. Even so, **the `ValidationResult` itself is non-null** and has clear criteria to inspect: `accepted` indicates the outcome, and `reason` holds details when needed.

## 6. Why You Should Not Pass null Directly into a Message or Flux

In plain Kotlin, a function returning a nullable type can be valid:

~~~kotlin
val optionalCode: (String) -> String? = { raw ->
    raw.trim().takeIf { it.isNotEmpty() }
}
~~~

However, exposing `String?` at the **outer boundary of the application** is an integration decision. Adapters may interpret null differently: suppress sending a message, throw an error, substitute a value, or exhibit adapter-specific behavior. You cannot look solely at `(I) -> O?` and conclude you will get HTTP 204, JSON `null`, or an empty message.

### 6.1. Spring Message<T> Requires a Valid Payload

Spring Messaging's `Message<T>` contains a payload and headers. Standard builders do not accept a `null` payload:

~~~kotlin
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

val event: Message<String> =
    MessageBuilder.withPayload("ORDER_ACCEPTED").build()

// MessageBuilder.withPayload(null) is not the way to create "no event".
~~~

Instead of creating a `Message<String?>` holding null, clearly decide between **skipping**, **switching to an error message**, or **emitting a status payload**. The messaging/binder layer needs an explicit policy for missing data.

### 6.2. Reactor Does Not Emit null via onNext

In Reactive Streams, `onNext` must carry a non-null value; Project Reactor does not support emitting a null element as normal data.

If the value is optional, use `Mono.justOrEmpty(...)` or `Mono.empty()`:

~~~kotlin
import reactor.core.publisher.Mono

fun normalizeOptional(raw: String?): Mono<String> {
    val normalized: String? = raw
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

    // Has String -> one onNext; null -> onComplete, no onNext.
    return Mono.justOrEmpty(normalized)
}
~~~

| Case | Publisher | Signal |
| --- | --- | --- |
| Has value `"O-101"` | `Mono.just("O-101")` | 1 `onNext`, then `onComplete` |
| No value | `Mono.empty<String>()` | `onComplete`, no `onNext` |
| Has nullable variable | `Mono.justOrEmpty(value)` | Emits if present; completes empty if null |
| Business/parse error | `Mono.error<T>(exception)` | `onError` |

**Having no element is not synonymous with an error.** Likewise, not every null value should be silently skipped; this must follow business requirements.

### 6.3. With Flux, Filter Out Invalid Records Without Emitting null

A reactive functional bean can accept a stream of orders and emit results only for valid data:

~~~kotlin
import java.util.function.Function
import org.springframework.context.annotation.Bean
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

// Place inside an appropriate @Configuration class.
@Bean
fun selectValidOrders(): Function<Flux<OrderInput>, Flux<Decision>> =
    Function { orders ->
        orders.flatMap { order ->
            if (order.id.isBlank() || order.totalVnd < 0L) {
                Mono.empty<Decision>()
            } else {
                val code = order.couponCode
                    ?.trim()
                    ?.takeIf { it.isNotEmpty() }

                Mono.just(
                    Decision(
                        orderId = order.id,
                        category = if (order.totalVnd >= 1_000_000L)
                            "PRIORITY" else "STANDARD",
                        note = code?.let { "COUPON:" + it } ?: "NO_COUPON"
                    )
                )
            }
        }
    }
~~~

With this code, invalid data is **dropped** and produces no `onNext` result. This is only **an illustrative policy**, insufficient for systems requiring error auditing or dead-letter queues. If an error event must be emitted, create an error DTO and route it explicitly rather than using null to imply status.

**Ordering note:** `flatMap` may alter emission order in asynchronous scenarios. When ordering must be preserved, evaluate `concatMap` or another appropriate operator.

## 7. Platform Types When Kotlin Calls Java APIs

Kotlin strives for compile-time null safety, but many Java APIs do not declare nullability metadata. The resulting type is called a **platform type**, which the IDE may display as `String!` (an explanatory notation, **not Kotlin type syntax you can write in source**).

Suppose an older Java library has:

~~~java
public final class LegacyDirectory {
    public String findCustomerName(String customerId) {
        // May return null even though the signature has no annotation.
        return null;
    }
}
~~~

In Kotlin:

~~~kotlin
val nameFromJava = directory.findCustomerName("C-101")

// Compiles, but throws a runtime error if Java returns null.
// val size = nameFromJava.length

// Safer boundary: explicitly model the nullable value.
val safeName: String? = directory.findCustomerName("C-101")
val displayName: String = safeName?.trim() ?: "UNKNOWN"
~~~

When a platform value is coerced/assigned into a non-null `String` variable, the Kotlin compiler may insert a runtime check and throw an exception if Java actually returns `null`. Therefore, you cannot rely solely on code **compiling** to treat a Java data source as non-null safe.

### 7.1. Nullability Annotations in Java

Some Java libraries include `@Nullable`, `@NonNull`, or use **JSpecify**. Kotlin can read these annotations to translate Java types into concrete nullable/non-nullable types.

~~~java
import org.jspecify.annotations.Nullable;

public interface CustomerDirectory {
    @Nullable String findName(String customerId);
}
~~~

Kotlin understands the corresponding nullable contract when metadata and compiler settings are configured appropriately:

~~~kotlin
fun label(directory: CustomerDirectory, id: String): String {
    val name: String? = directory.findName(id)
    return name?.uppercase() ?: "ANONYMOUS"
}
~~~

**Version differences:** newer Spring Framework versions use JSpecify extensively; older versions may rely more on Spring `@Nullable`/JSR-305. Flags such as `-Xjsr305` and `-Xjspecify-annotations` depend on compiler/version to control strictness. Do not assume a flag from an older tutorial is still required for every modern Kotlin project.

## 8. Java Functional Interfaces and Nullable Return Types

On the Java side, there are the interfaces:

~~~java
Supplier<T>       // T get()
Function<T, R>    // R apply(T value)
Consumer<T>       // void accept(T value)
~~~

Kotlin can implement them directly via Java SAM conversion:

~~~kotlin
import java.util.function.Consumer
import java.util.function.Function
import java.util.function.Supplier

val supplier: Supplier<String> = Supplier { "ORD-101" }

val function: Function<String, String> = Function { code ->
    code.trim().uppercase()
}

val consumer: Consumer<String> = Consumer { code ->
    println("AUDIT: " + code)
}
~~~

**Regarding nullability:** Java generic `Function<T, R>` generally does not encode nullability without annotations. When Kotlin receives a `Function<String, String>` created by legacy Java code, do not treat the return value as guaranteed non-null merely because `String` was used as the generic argument. If the actual output can be null, check it at the Java boundary:

~~~kotlin
fun safeLegacyApply(
    external: Function<String, String>,
    code: String
): String {
    val result: String? = external.apply(code)
    return result?.trim()?.takeIf { it.isNotEmpty() }
        ?: "UNKNOWN"
}
~~~

This is a **defensive** example when calling Java: `String?` on the local variable reflects a cautious assumption about the platform result. When creating Java SAM beans in Kotlin yourself, actively maintain a non-null contract or model optional results with an explicit data type, and then test the adapter.

### 8.1. Unit Does Not Replace Void in Java Function Generics

Do not interpret:

~~~kotlin
val kConsumer: (String) -> Unit = { println(it) }
~~~

as if it were the same runtime interface as:

~~~kotlin
val jFunction: Function<String, Void?> = Function { value ->
    println(value)
    null
}
~~~

They differ in both **interface** and **result interpretation**. Spring Cloud Function has a mechanism to recognize `(I) -> Unit` as a consumer; conversely, `Function<I, Void?>` remains a Java `Function`. Do not alter signatures solely to avoid generic errors without evaluating the adapter.

## 9. Message<T>, Headers, and Nullability at the Conversion Boundary

Suppose a message carries an `OrderInput` payload and a `correlationId` header. If the header may be missing, treat it as optional data:

~~~kotlin
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

data class AuditedDecision(
    val orderId: String,
    val category: String,
    val correlationId: String?
)

// Place inside a @Configuration class.
@Bean
fun classifyWithHeader(): (Message<OrderInput>) -> Message<AuditedDecision> =
    { input ->
        val order = input.payload
        val correlationId: String? =
            (input.headers["correlationId"] as? String)

        val response = AuditedDecision(
            orderId = order.id,
            category = if (order.totalVnd >= 1_000_000L)
                "PRIORITY" else "STANDARD",
            correlationId = correlationId
        )

        MessageBuilder.withPayload(response).build()
    }
~~~

The code above intentionally **writes the correlation ID into the output payload** so readers can see how to distinguish an optional value from a header. If you need to preserve the header downstream, build the output message and **explicitly copy the desired header**:

~~~kotlin
val builder = MessageBuilder.withPayload(response)
correlationId?.let { builder.setHeader("correlationId", it) }
val output: Message<AuditedDecision> = builder.build()
~~~

This snippet illustrates **a replacement** for the `MessageBuilder.withPayload(response).build()` line in the previous function, not a standalone function lacking the `response` variable. Adapters may add or process headers on their own; do not assume all headers are automatically preserved across every transformation.

**Important:** `Message<OrderInput>` is still **one input binding**, not two bindings just because it contains a payload and headers. If the adapter receives empty or schema-invalid JSON, the converter may fail before invoking the function.

## 10. Impact on FunctionCatalog, Composition, and Each Adapter

### 10.1. FunctionCatalog Needs a Clear Type Contract

A Kotlin bean can be declared as:

~~~kotlin
@Bean
fun normalizeCode(): (String) -> String =
    { raw -> raw.trim().uppercase() }
~~~

After Spring creates the bean, `FunctionCatalog` can look it up by the name `normalizeCode` and return a normalized/wrapped function. Because `String -> String` is declared explicitly, converters and composition have the basis to determine the shape of data passing through the function.

If you use `(String) -> String?`, Kotlin expresses the **nullability** of the result; however, how an adapter represents it as an HTTP status, JSON, or message must be verified separately. **Do not invent a "null = do not emit" convention without integration tests.**

### 10.2. Composition Does Not Turn Unit into a Payload

Suppose two beans exist:

~~~kotlin
@Bean
fun normalize(): (String) -> String =
    { it.trim().uppercase() }

@Bean
fun auditNormalized(): (String) -> Unit =
    { println("AUDIT: " + it) }
~~~

The composition `normalize|auditNormalized` means **input string → normalize → side effect**, with no business payload returned from the consumer at the end. Conversely, you cannot assume the composition `auditNormalized|normalize` has a `String` output, because the preceding step provides no business value to pass into the next function.

For functions with nullable outputs, explicitly design how absence is handled before composing; do not rely on untested default framework behavior.

### 10.3. HTTP, Messaging, and Serverless Do Not Share the Same "Meaning of Null"

| Scenario | What Can Be Stated | What Must Be Verified per Adapter |
| --- | --- | --- |
| Kotlin consumer `(I) -> Unit` | No business output payload from the function | HTTP status, acknowledgment, retry |
| Kotlin `(I) -> O?` | Function can return nullable at the Kotlin level | Is null serialized, skipped, or treated as an error? |
| `Function<I, O>` returning an error DTO | An explicit result object exists | HTTP status/message destination |
| `Mono.empty()` | Publisher completes without `onNext` | Does the adapter send a message or simply complete? |
| `Mono.error(...)` | Publisher emits `onError` | Retry/DLQ/HTTP error/trigger failure |
| `Message<T>` | Has payload and headers | Which headers are preserved, actual content type |

A single piece of business logic can be reused, but **communication contracts** must be designed specifically for HTTP, events, or serverless. When you need to signal rejection or "not found", a `sealed result`, status DTO, or exception with a clear policy is usually safer than an ambiguous `null` result.

## 11. Testing Kotlin: Unit, Null, and Reactive Empty

### 11.1. Unit Testing Consumers

Do not test a consumer solely with `assertEquals(Unit, ...)` and consider the side effect verified. Use an observable dependency:

~~~kotlin
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class AuditLogicTest {

    @Test
    fun callsSideEffectAndReturnsUnit() {
        val recorded = mutableListOf<String>()
        val audit: (String) -> Unit = { recorded.add(it); Unit }

        val outcome: Unit = audit("O-101")

        assertEquals(Unit, outcome)
        assertEquals(listOf("O-101"), recorded)
    }
}
~~~

**Verifying the side effect** is the primary goal; comparing `Unit` merely reiterates the type contract.

### 11.2. Testing Optional Values

~~~kotlin
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class OptionalCodeTest {

    @Test
    fun trimsOptionalCodeOrReturnsNull() {
        val normalize: (String?) -> String? = { raw ->
            raw?.trim()?.takeIf { it.isNotEmpty() }
        }

        assertEquals("SAVE10", normalize(" SAVE10 "))
        assertEquals(null, normalize("   "))
        assertEquals(null, normalize(null))
    }
}
~~~

This test only proves **Kotlin semantics**. It does not tell you which HTTP status code will be returned or whether a binder sends a message when the result is null.

### 11.3. Testing Reactor Empty Completion and Data Emission

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.test.StepVerifier

class OptionalPublisherTest {

    @Test
    fun emitsDataWhenPresent() {
        StepVerifier.create(normalizeOptional(" O-101 "))
            .expectNext("O-101")
            .verifyComplete()
    }

    @Test
    fun completesWithoutDataWhenAbsent() {
        StepVerifier.create(normalizeOptional(" "))
            .verifyComplete()

        StepVerifier.create(normalizeOptional(null))
            .verifyComplete()
    }
}
~~~

`verifyComplete()` in the last two cases proves the publisher emits no items; it **does not** prove the adapter returned HTTP 204 or handled the missing data at the business level.

### 11.4. Spring Context Test via FunctionCatalog

To verify that `(I) -> Unit` is recognized properly, you need an **integration test that starts the Spring context**:

~~~kotlin
import java.util.function.Consumer
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

@SpringBootTest
class KotlinConsumerCatalogTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun kotlinConsumerIsDiscoverable() {
        val function = catalog.lookup<Consumer<String>>("auditOrder")
        assertNotNull(function)
    }
}
~~~

This example assumes `AuditFunctions` is inside the application context loaded by the Spring Boot test; you may specify `@SpringBootTest(classes = [...])` depending on project structure. It confirms catalog lookup succeeds, not binder/HTTP behavior.

## 12. Common Errors and Fixes

| Symptom | Reason | Fix |
| --- | --- | --- |
| Writing `(I) -> Unit` while expecting a business output response | Consumer returns no payload | Use `(I) -> O` and an explicit result DTO |
| Declaring `Function<I, Void?>` to simulate a consumer | Java `Function` differs from `Consumer` | Use `Consumer<I>` or Kotlin `(I) -> Unit` directly |
| Calling a Java API and hitting an NPE despite Kotlin compiling | Platform types do not guarantee non-null | Narrow boundary to `T?`, check, and add nullability annotations |
| JSON missing a required field stops the function from running | Deserialization fails before entering the lambda | Check schema, converter, and validation |
| `MessageBuilder.withPayload(null)` fails | Message payload cannot be constructed with null | Emit a status DTO or emit no event by design |
| `Mono.just(null)` throws an error | Reactor forbids `onNext(null)` | Use `Mono.justOrEmpty(...)`/`Mono.empty()` |
| `String?` to HTTP/broker behaves unexpectedly | Adapters have their own null-handling contracts | Write integration tests and decide explicitly on "no result" |
| `Consumer<Flux<T>>` does not process events | Nobody subscribes to the source | Design subscription/lifecycle or use a suitable reactive function |
| Sending `Unit` as a JSON payload produces strange types for clients | Confusing language return type with business output | Change contract to a DTO, `Consumer`, or completion publisher |
| Type errors on Java SAM | Confusing `Void`, `Unit`, Kotlin function type, and Java `Function` | Write full generic signatures and verify imports |

## 13. Self-Check Exercises

**Question 1.** Should `@Bean fun audit(): (OrderInput) -> Unit` be viewed as `Function<OrderInput, Unit>` or as a consumer when Spring Cloud Function recognizes Kotlin lambdas?

**Answer:** This is the Kotlin signature corresponding to **`Consumer<OrderInput>`** under Spring Cloud Function's Kotlin lambda support model. `Unit` is not a business payload.

**Question 2.** Is `Function<String, Void?>` returning `null` identical to `Consumer<String>`?

**Answer:** No. Java `Function` has a contract returning a type `R`, whereas `Consumer` has `void accept(T)`. They can lead to differences when the framework recognizes the bean and handles its output.

**Question 3.** An unannotated Java API returns `String`, yet in practice returns `null`. Kotlin may infer it as `String!`. What should a developer do?

**Answer:** Treat it as a platform type with no null-safety guarantee; narrow the result to `String?` and check it, or ask for nullability annotations on the Java API.

**Question 4.** In Reactor, does `Mono.justOrEmpty(null)` emit a null element or simply complete?

**Answer:** It completes **without** emitting `onNext`. Reactor does not allow null elements.

**Question 5.** Is JSON missing `id` for `OrderInput(val id: String, ...)` guaranteed to be passed into `classifyOrder` as an empty string?

**Answer:** No. The converter may fail deserialization before calling the function; default values, Jackson configuration, or validation determine how it is handled.

**Question 6.** When business logic needs to respond "order not found", should you prefer returning `null` or an explicit result?

**Answer:** Prefer an explicit contract (status DTO, sealed result, exception with a defined policy, or an empty-completing publisher when appropriate) so adapters interpret it consistently. Do not assume `null` will always become HTTP 404 or suppress a message.

**Question 7.** A Kotlin `(String) -> Unit` runs without error when called directly. Does that prove `FunctionCatalog` has registered the consumer?

**Answer:** Not yet. You need to register it as a Spring bean and test `FunctionCatalog.lookup(...)` inside an application context; adapters also require separate testing.

## References

- [Spring Cloud Function — Programming model and Kotlin lambda support](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and consuming messages, reactive functions](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Kotlin — Calling Java from Kotlin: void, platform types, nullability annotations](https://kotlinlang.org/docs/java-interop.html)
- [Kotlin — Null safety](https://kotlinlang.org/docs/null-safety.html)
- [Kotlin — Java to Kotlin nullability guide](https://kotlinlang.org/docs/java-to-kotlin-nullability-guide.html)
- [Spring Boot — Kotlin Support](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Framework — Kotlin Null-safety and JSpecify](https://docs.spring.io/spring-framework/reference/languages/kotlin/null-safety.html)
- [Project Reactor — Mono API, justOrEmpty/empty/error](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
