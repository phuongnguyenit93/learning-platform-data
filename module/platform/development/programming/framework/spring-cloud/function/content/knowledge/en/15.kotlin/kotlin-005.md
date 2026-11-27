# Generic Types, Kotlin POJOs, and JSON Conversion

## 1. Why Do Data Types Matter in Spring Cloud Function?

In **Spring Cloud Function** (the `SPRING_CLOUD_FUNCTION` module), business logic is registered as a `Supplier`, `Function`, or `Consumer` for protocol-independent reuse. `FunctionCatalog` recognizes and normalizes beans, supports composition, converts messages, and lets an appropriate adapter expose the function over HTTP, event systems, or serverless environments.

Most data crossing system boundaries does not already exist as a Kotlin object. HTTP and brokers typically transmit **JSON text** or **`byte[]`**, while business functions need concrete types like `OrderRequest`. When generics are involved—such as `List<OrderLine>` or `Envelope<OrderRequest>`—the question "what type is the input?" becomes even more critical.

~~~text
HTTP / message broker / serverless event
         |
         v
  JSON / byte[] / String
         |
         | content-type + target type of the functional bean
         v
  MessageConverter / JSON mapper
         |
         v
  OrderRequest (Kotlin data class)
         |
         v
  Function<OrderRequest, OrderDecision>
         |
         v
  OrderDecision
         |
         v
  JSON / message / response (per adapter)
~~~

This guide clarifies four commonly conflated topics:

1. **Kotlin POJOs**: why a `data class` with a primary constructor differs from a traditional JavaBean, and what is required to deserialize it?
2. **Generic types**: why `List<OrderLine>`, `List<Map<String, Any>>`, and `Envelope<OrderRequest>` cannot be substituted arbitrarily?
3. **Content type**: `application/json` only describes the format; it does not by itself specify which Java/Kotlin class to instantiate.
4. **Adapter boundaries**: a single Kotlin bean can be reused across HTTP/messaging/serverless, but serialization, data validation, and error handling must suit each environment.

## 2. What Is a Kotlin POJO and How Does It Differ from a Traditional JavaBean?

A *Plain Old Java Object* (POJO) in the context of Spring Cloud Function is simply a business data class that does not need to extend a framework class or implement a special interface. In Kotlin, `data class` is a very common choice:

~~~kotlin
data class OrderLine(
    val sku: String,
    val quantity: Int
)

data class OrderRequest(
    val orderId: String,
    val amountVnd: Long,
    val lines: List<OrderLine>,
    val couponCode: String? = null
)

data class OrderDecision(
    val orderId: String,
    val category: String,
    val totalQuantity: Int,
    val couponApplied: Boolean
)
~~~

`data class` generates useful capabilities such as `equals`, `hashCode`, `toString`, `copy`, and `componentN`. Using `val` makes objects less prone to unexpected mutation after creation. However:

- It **does not guarantee** valid JSON input on its own.
- It **does not create** an HTTP endpoint or broker binding on its own.
- It **does not require a no-argument constructor**; a JSON mapper needs to recognize the primary constructor and its parameters.
- It **does not turn** `List<OrderLine>` into multiple output ports.

Corresponding JSON example:

~~~json
{
  "orderId": "O-101",
  "amountVnd": 1500000,
  "lines": [
    { "sku": "SKU-A", "quantity": 2 },
    { "sku": "SKU-B", "quantity": 1 }
  ],
  "couponCode": "SAVE10"
}
~~~

Here, `lines` is **a single property holding a list of objects**, not multiple messages. Upon successful deserialization, each element in the list has type `OrderLine`, allowing the code to read `line.quantity` without casting from `Map` or `Any`.

### 2.1. When to Use `data class`, `class`, or `value class`?

| Kotlin Type | Typical Purpose | Notes at the JSON Boundary |
| --- | --- | --- |
| `data class` | Input/output DTOs with clear properties | Requires a mapper supporting Kotlin constructors/nullability |
| Regular `class` | Objects with custom rules/behavior | Check constructors, getters, and JSON mapper annotations |
| `enum class` | A finite set of values | Must handle unrecognized external strings |
| `sealed class/interface` | Multiple distinct structured result shapes | Polymorphic JSON typically requires dedicated metadata/annotations |
| `@JvmInline value class` | Wraps a single value for stronger type safety | Jackson support and format depend on versions; requires testing |

In introductory practices, **`data class` with concretely typed properties** is usually easier to integrate than starting with complex polymorphic types or value classes.

## 3. Dependencies: Kotlin Runtime, Jackson Kotlin Module, and Spring Cloud Function

A Kotlin/Spring Cloud Function project must distinguish between dependencies for **function recognition** and dependencies for **JSON conversion**:

| Component | Role |
| --- | --- |
| `kotlin-stdlib` | Kotlin runtime and function types |
| `kotlin-reflect` | Kotlin reflection and metadata so integration libraries can infer type info |
| `kotlin("plugin.spring")` | Opens eligible Spring-annotated classes/members for proxying; a compiler plugin |
| `spring-cloud-function-context` | `FunctionCatalog` and the functional bean mechanism |
| Jackson Kotlin module | Supports primary constructors, default parameters, nullable properties, and Kotlin constructs in JSON mapping |
| Spring Cloud Function web adapter | Exposes functions over HTTP when needed |
| Spring Cloud Stream and binder | Connects input/output bindings to a broker when needed |

**You do not need to add the Jackson Kotlin module just to write a Kotlin `(String) -> String` lambda.** The JSON module is needed when the application actually serializes/deserializes structured Kotlin data.

### 3.1. Dependency Example in Gradle Kotlin DSL

The following snippet illustrates the relevant dependencies. Real projects must manage **plugin and Spring Boot/Spring Cloud versions** through compatible plugins/BOMs:

~~~kotlin
plugins {
    kotlin("jvm")
    kotlin("plugin.spring")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-function-context")

    implementation(kotlin("stdlib"))
    implementation(kotlin("reflect"))

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

This is **not** a complete `build.gradle.kts`; `kotlin-stdlib` may already be added automatically by the Kotlin Gradle plugin. If HTTP or messaging is needed, add the starter/adapter and binder corresponding to your version.

**Note on Jackson 2 and Jackson 3:**

~~~kotlin
// For Spring Boot 3.x projects using Jackson 2:
// implementation("com.fasterxml.jackson.module:jackson-module-kotlin")

// For Spring Boot 4.x projects using Jackson 3:
// implementation("tools.jackson.module:jackson-module-kotlin")
~~~

Choose **one line according to your actual Jackson generation**; do not add both just to "cover all bases". Spring Boot 4.x documentation treats Jackson 3 as the default/preferred choice while supporting Jackson 2 for migration needs. The appropriate Kotlin module is normally auto-registered by Boot when present on the classpath. Packages/imports between Jackson 2 and 3 are also **different**.

The JSON mapper example in the testing section below **explicitly uses Jackson 2/Spring Boot 3.x**; do not copy those imports verbatim into Jackson 3 while ignoring API differences.

## 4. Declaring Functional Beans with Concrete Generic Types

Business logic should receive data already deserialized into `OrderRequest`, instead of manually parsing JSON strings in every function:

~~~kotlin
package example.orders

import java.util.function.Function
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

data class OrderLine(
    val sku: String,
    val quantity: Int
)

data class OrderRequest(
    val orderId: String,
    val amountVnd: Long,
    val lines: List<OrderLine>,
    val couponCode: String? = null
)

data class OrderDecision(
    val orderId: String,
    val category: String,
    val totalQuantity: Int,
    val couponApplied: Boolean
)

fun decideOrder(order: OrderRequest): OrderDecision {
    require(order.orderId.isNotBlank()) { "orderId must not be blank" }
    require(order.amountVnd >= 0) { "amountVnd must not be negative" }
    require(order.lines.all { it.sku.isNotBlank() && it.quantity > 0 }) {
        "Each line must have a SKU and quantity > 0"
    }

    val normalizedCoupon = order.couponCode
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

    return OrderDecision(
        orderId = order.orderId,
        category = if (order.amountVnd >= 1_000_000L)
            "PRIORITY" else "STANDARD",
        totalQuantity = order.lines.sumOf { it.quantity },
        couponApplied = normalizedCoupon != null
    )
}

@Configuration
class OrderFunctions {
    @Bean
    fun classifyOrder(): Function<OrderRequest, OrderDecision> =
        Function { order -> decideOrder(order) }
}
~~~

Key takeaways:

1. `Function<OrderRequest, OrderDecision>` expresses **concrete** types on both ends.
2. `OrderRequest.lines` retains the `List<OrderLine>` type instead of flattening into `List<Any>`.
3. `decideOrder` is **pure business logic**: independent of HTTP headers, message brokers, or JSON formatting.
4. The `require` checks execute **after** data has been constructed into `OrderRequest`. If JSON fails to deserialize, the lambda may never be invoked.

Similarly, you can use a **Kotlin function type**:

~~~kotlin
@Bean
fun classifyOrderKotlin(): (OrderRequest) -> OrderDecision = ::decideOrder
~~~

Spring Cloud Function supports recognizing Kotlin lambdas registered as beans. Both declaration styles are valid, though if **both** are present in the same application and bound by an adapter, specify the target function explicitly with `spring.cloud.function.definition`. Subsequent examples use **a single bean** named `classifyOrder`.

### 4.1. Avoid Overly Broad Types at the JSON Boundary

~~~kotlin
// Overly generic declaration: framework struggles to infer target DTO type.
val unclear: Function<Any, Any> = Function { it }

// Publish a precise contract.
val typed: Function<OrderRequest, OrderDecision> =
    Function { decideOrder(it) }
~~~

When receiving `byte[]`/JSON, the converter needs to know the **target object** is `OrderRequest`, not just `Any`. The bean signature is a primary source of metadata for `FunctionCatalog` and adapters to select the conversion mechanism.

## 5. Kotlin Generics: Nested Types Cannot Be Ignored

### 5.1. Collection Generics Inside DTOs

In the example:

~~~kotlin
val lines: List<OrderLine>
~~~

`List` is just the container class; `OrderLine` specifies the **element** type. If you use:

~~~kotlin
val lines: List<Map<String, Any?>>
~~~

then business logic must access `map["sku"]`, `map["quantity"]`, cast types, and handle nulls manually. Data might pass through the JSON layer only to cause late type errors inside business logic.

For stable APIs, prefer well-structured DTOs over `Map<String, Any?>` unless the data genuinely has a dynamic schema.

### 5.2. Type Erasure on the JVM

With Java/Kotlin generics, many type arguments are erased at runtime (*type erasure*):

~~~kotlin
fun inspect(value: List<String>) {
    println(value.javaClass) // Does not fully reveal T = String.
}
~~~

Consequently, a JSON mapper may need a **type token** to distinguish:

~~~kotlin
List<OrderLine>
List<Map<String, Any?>>
Envelope<OrderRequest>
Envelope<OrderDecision>
~~~

If the converter only knows the raw class `List::class.java`, objects in a JSON array may become `Map` instead of `OrderLine`. If it only knows `Envelope::class.java`, the `payload` field may be deserialized into a broad type or `Map`.

**Solution:** Declare exact generics on `@Bean` and, when invoking a JSON mapper directly for nested generic types, use Jackson's `TypeReference`/`JavaType` or equivalent. Do not assume generics survive every wrapper, reflection path, or adapter automatically.

### 5.3. Generic Wrapper `Envelope<T>`

~~~kotlin
data class Envelope<T>(
    val traceId: String,
    val payload: T
)

@Bean
fun classifyEnvelope():
    Function<Envelope<OrderRequest>, Envelope<OrderDecision>> =
    Function { incoming ->
        Envelope(
            traceId = incoming.traceId,
            payload = decideOrder(incoming.payload)
        )
    }
~~~

This bean should live inside a `@Configuration` class alongside the declared DTO types. It keeps `traceId` separate from the business payload.

The exact contract is:

~~~text
Envelope<OrderRequest>
       |
       v
   classifyEnvelope
       |
       v
Envelope<OrderDecision>
~~~

`Envelope<Any>` would be far less clear because the converter could not easily tell that `payload` must become `OrderRequest`. Even though `Function<Envelope<OrderRequest>, Envelope<OrderDecision>>` fully declares the generics, **runtime recovery of nested generics must still be tested against your actual `FunctionCatalog` and adapter versions**.

## 6. Jackson Kotlin Module and Data Class Constructors

The Jackson Kotlin module supports Kotlin-specific features:

- **Primary constructor**: instantiates `data class` types even without a no-arg constructor.
- **Parameter names**: maps JSON properties to constructor parameters.
- **Nullability**: checks compatibility of non-null/nullable properties during deserialization.
- **Default arguments**: uses default values for missing parameters in supported cases.
- **Kotlin generic types**: combines Kotlin metadata with Jackson's generic type resolution.

Example:

~~~kotlin
data class Customer(
    val id: String,
    val name: String = "UNKNOWN",
    val email: String? = null
)
~~~

When JSON contains only `{"id":"C-101"}`, a mapper configured with the proper Kotlin module can generally use the defaults `name = "UNKNOWN"` and `email = null`.

**Do not assume "missing property" and "property with JSON `null`" are the same.** A field present with `null` may follow different rules from a completely absent field, depending on the Kotlin type and Jackson settings such as `NullIsSameAsDefault` or `@JsonSetter`.

### 6.1. Table of Null/Missing Behaviors to Test

| Kotlin Declaration | Incoming JSON | Design Expectation and Notes |
| --- | --- | --- |
| `val id: String` | `"id": "C-101"` | Valid |
| `val id: String` | `id` absent | Missing required constructor value; typically fails with the Kotlin module |
| `val id: String` | `"id": null` | Non-null violation; typically fails with the Kotlin module |
| `val email: String? = null` | `email` absent | Can use default `null` |
| `val email: String? = null` | `"email": null` | Nullable accepts null |
| `val name: String = "UNKNOWN"` | `name` absent | Can use default value |
| `val name: String = "UNKNOWN"` | `"name": null` | Do not assume it is treated as missing; depends on policy |
| `val amountVnd: Long` | `"amountVnd": null` | Requires null-checking configuration for primitive numeric types |

The last point is especially hazardous: for JVM primitive types like `Long`/`Int`/`Boolean`, **Jackson can coerce JSON `null` to the JVM default value (`0`/`false`)** under certain configurations, even when the Kotlin property is non-null. When using Jackson 2, consider `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` (or the equivalent setting for your Jackson generation), and test both null and missing cases.

### 6.2. Default Values Do Not Replace Validation

~~~kotlin
data class OrderWithDefaults(
    val orderId: String,
    val amountVnd: Long = 0L,
    val lines: List<OrderLine> = emptyList()
)
~~~

This might be a reasonable contract for a draft-creation request, yet **dangerous** if a payment request requires supplying an amount. JSON missing `amountVnd` could silently become `0L` and pass through processing as a valid order. Only declare defaults when they carry genuine business meaning.

If a field is required, keep it required and validate explicitly. When returning error responses for external data, test both **deserialization errors** and **business validation errors**.

## 7. Testing Conversion from JSON to DTOs and Generic Collections

The following example is specifically for **Jackson 2 + `jackson-module-kotlin` on Spring Boot 3.x**. Its goal is to demonstrate testing mappings cleanly **without needing an HTTP server or broker**:

~~~kotlin
import com.fasterxml.jackson.core.type.TypeReference
import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class OrderJsonTest {

    private val mapper = jacksonObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)

    @Test
    fun readsNestedOrderLines() {
        val json = """
          {
            "orderId": "O-101",
            "amountVnd": 1500000,
            "lines": [
              { "sku": "SKU-A", "quantity": 2 },
              { "sku": "SKU-B", "quantity": 1 }
            ],
            "couponCode": "SAVE10"
          }
        """.trimIndent()

        val order: OrderRequest = mapper.readValue(json)

        assertEquals("O-101", order.orderId)
        assertEquals(2, order.lines.size)
        assertEquals(OrderLine("SKU-A", 2), order.lines.first())
        assertEquals("SAVE10", order.couponCode)
    }

    @Test
    fun readsGenericEnvelope() {
        val json = """
          {
            "traceId": "trace-101",
            "payload": {
              "orderId": "O-102",
              "amountVnd": 500000,
              "lines": []
            }
          }
        """.trimIndent()

        val type = object : TypeReference<Envelope<OrderRequest>>() {}
        val envelope: Envelope<OrderRequest> =
            mapper.readValue(json, type)

        assertEquals("trace-101", envelope.traceId)
        assertEquals("O-102", envelope.payload.orderId)
        assertEquals(null, envelope.payload.couponCode)
    }
}
~~~

In the second test, `TypeReference<Envelope<OrderRequest>>` preserves the **concrete type of the `payload` field**, unlike passing only `Envelope::class.java`. For Spring Boot 4.x/Jackson 3, use the corresponding artifacts and package APIs (such as `tools.jackson.*`); do not reuse the `com.fasterxml.jackson.*` imports above as-is.

This is a **unit test for the JSON mapper**: it does not prove which converter `FunctionCatalog` selects or how an HTTP/message adapter handles headers.

## 8. FunctionCatalog: Target Java Type + contentType Determine Conversion

Spring Cloud Function includes mechanisms to convert data from raw forms such as JSON strings or `byte[]` into the type required by the function. According to official documentation, the framework uses:

1. **The function's parameter type** (for example, `OrderRequest`).
2. **Content type** (for example, `application/json`).
3. **`MessageConverter`** or **`ConversionService`**, depending on whether the input is a Spring `Message` or a plain value.

Example conversion flow:

~~~text
Incoming Message<byte[]>
 payload     = bytes containing OrderRequest JSON
 contentType = application/json
        |
        v
 FunctionCatalog / adapter
   target input = OrderRequest
        |
        v
 JSON MessageConverter + appropriate mapper
        |
        v
 Function<OrderRequest, OrderDecision>
        |
        v
 OrderDecision
~~~

**`contentType = application/json` does not automatically pick the `OrderRequest` class.** It only indicates the **data format**. The target type comes from the function signature or permitted conversion metadata.

When the input is a `Message`, the framework typically looks for a suitable `MessageConverter`; for non-`Message` inputs, `ConversionService` may be involved. Do not assume every adapter directly calls a single `ObjectMapper` injected by the application; Spring Cloud Function uses its own JSON mapper and converter abstractions.

### 8.1. Unbounded Types and Dynamic Type Parameters

Spring Cloud Function has a mechanism to specify types via MIME parameters like `application/json;type=...` in certain scenarios using functions declared with `Object`. This is **not** a reason to omit generics from every function.

Resolving data types from externally supplied class names carries security risks. According to Spring Cloud Function documentation, this dynamic type mechanism requires allowed classes to be listed in `META-INF/deserializable.types`. For normal API contracts, **prefer strongly typed DTOs** rather than accepting arbitrary client-controlled class names.

### 8.2. Do Not Confuse FunctionCatalog with Jackson ObjectMapper

`FunctionCatalog` manages and invokes normalized functions. Jackson is only one of the tools used to **serialize/deserialize JSON**. When diagnosing issues:

- If the function cannot be looked up via `lookup`: check bean registration/function name.
- If calling the function with a pre-built `OrderRequest` works, but receiving JSON fails: check the converter, schema, Jackson Kotlin module, and `content-type`.
- If both work, yet messages never reach the topic: check bindings, binder, and broker configuration.

## 9. Deploying via Spring Cloud Stream: Both Input and Output Are Typed

Suppose you bind the `classifyOrder` bean from section 4:

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

Diagram:

~~~text
orders.created
   JSON OrderRequest
        |
        v
 classifyOrder-in-0
        |
        v
 classifyOrder(): Function<OrderRequest, OrderDecision>
        |
        v
 classifyOrder-out-0
        |
        v
 orders.classified
   JSON OrderDecision
~~~

This configuration requires **Spring Cloud Stream with an appropriate binder** (Kafka, RabbitMQ, or another system). Having a `@Bean` does not create a broker automatically. Content type can be specified via binding configuration or message headers depending on the adapter's mechanism; if the configuration does not match the actual data, the converter may fail.

### 9.1. `Message<OrderRequest>` Preserves Headers

If business logic needs trace/correlation headers:

~~~kotlin
import java.util.function.Function
import org.springframework.context.annotation.Bean
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

// Place this @Bean inside a @Configuration class.
@Bean
fun classifyWithHeaders():
    Function<Message<OrderRequest>, Message<OrderDecision>> =
    Function { incoming ->
        val decision = decideOrder(incoming.payload)
        val builder = MessageBuilder.withPayload(decision)

        incoming.headers["correlationId"]?.let { correlation ->
            builder.setHeader("correlationId", correlation)
        }
        builder.build()
    }
~~~

The signature `Message<OrderRequest>` represents **an explicitly typed payload along with headers**, and does not increase the number of input bindings. The example copies **selected headers**; do not assume every header is automatically preserved after changing the payload.

When headers are not needed, `Function<OrderRequest, OrderDecision>` remains the cleaner contract.

### 9.2. `List<T>` and `Flux<T>` Do Not Create Multiple Output Bindings

~~~kotlin
// A single return value that is a Collection.
Function<OrderRequest, List<OrderDecision>>

// A reactive publisher emitting multiple elements.
Function<reactor.core.publisher.Flux<OrderRequest>,
         reactor.core.publisher.Flux<OrderDecision>>
~~~

Both signatures describe **one logical output**; the list size or number of `onNext` emissions does not determine the number of output bindings. Spring Cloud Stream has dedicated batch producer handling for certain `List<Message<T>>` signatures, yet multiple messages on a single binding still do **not** mean multiple topics.

If you want two independent reactive output bindings, Spring Cloud Function's arity model uses a structure such as `Tuple2<Flux<A>, Flux<B>>` with a supporting adapter, rather than `List<Output>`.

## 10. Renaming JSON Fields, Optional Fields, and Validation

### 10.1. When JSON Field Names Differ from Kotlin Property Names

Suppose clients send `order_id`, while in Kotlin you want to keep `orderId`. With **Jackson 2**, one option is placing the annotation on the constructor parameter:

~~~kotlin
import com.fasterxml.jackson.annotation.JsonProperty

data class ExternalOrder(
    @param:JsonProperty("order_id")
    val orderId: String,

    @param:JsonProperty("amount_vnd")
    val amountVnd: Long
)
~~~

Kotlin has multiple annotation use-site targets (`@param:`, `@field:`, `@get:`). Annotating the constructor parameter fits how Jackson resolves parameter names when instantiating a setterless `data class`. **When migrating to Jackson 3**, use the corresponding annotations/packages and test both input and output: an annotation might not rename both serialization and deserialization as expected. If you need the same name in both directions, clearly check annotation placement and mapper policy.

### 10.2. Validation Is Not Enabled Merely by Using a `data class`

A DTO can use Bean Validation:

~~~kotlin
import jakarta.validation.constraints.Min
import jakarta.validation.constraints.NotBlank

data class ValidatedOrder(
    @field:NotBlank
    val orderId: String,

    @field:Min(0)
    val amountVnd: Long
)
~~~

These annotations require suitable validation dependencies, such as the Spring Boot validation starter with a Jakarta Validation provider. **Important:** Placing `@field:NotBlank` on a DTO does not guarantee Spring Cloud Function automatically invokes Bean Validation on every message. You must configure a validation layer, an appropriate controller/adapter, or invoke `Validator` explicitly and define how validation failures are handled.

Combine validation at two layers:

- **Deserialization:** Can the JSON be converted into the DTO with the right types?
- **Business validation:** Does the DTO satisfy the business rules?

### 10.3. Date/Time and Monetary Fields

For VND currency, `Long` representing whole units is usually easier to reason about than `Double` when fractional units are unnecessary. If fractional units are stored, consider `BigDecimal` with an explicit rounding contract. For `Instant`/`LocalDate`, you need a mapper supporting Java date/time types and an agreed format/time zone. These are schema/serialization concerns, not merely Kotlin syntax details.

## 11. Testing Three Layers: Business, JSON Mapper, and Adapter

### 11.1. Business Unit Tests Without JSON

~~~kotlin
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

class OrderLogicTest {

    @Test
    fun classifiesPriorityAndCountsItems() {
        val request = OrderRequest(
            orderId = "O-101",
            amountVnd = 1_500_000L,
            lines = listOf(OrderLine("SKU-A", 2),
                           OrderLine("SKU-B", 1)),
            couponCode = " SAVE10 "
        )

        val result = decideOrder(request)

        assertEquals(
            OrderDecision("O-101", "PRIORITY", 3, true),
            result
        )
    }

    @Test
    fun rejectsNegativeAmount() {
        assertThrows(IllegalArgumentException::class.java) {
            decideOrder(
                OrderRequest("O-102", -1L, emptyList())
            )
        }
    }
}
~~~

This test proves the business logic and Kotlin data types work; it does **not** test Jackson or Spring Cloud Function.

### 11.2. Spring Context Test for `FunctionCatalog`

~~~kotlin
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

// Assumes the application context loads OrderFunctions.
@SpringBootTest
class OrderFunctionCatalogTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun findsTypedFunction() {
        val function = requireNotNull(
            catalog.lookup<Function<OrderRequest, OrderDecision>>(
                "classifyOrder"
            )
        )

        val input = OrderRequest(
            "O-103", 500_000L, listOf(OrderLine("SKU-X", 1))
        )
        val output = function.apply(input)

        assertEquals("STANDARD", output.category)
        assertEquals(1, output.totalQuantity)
    }
}
~~~

`FunctionCatalog.lookup(...)` verifies that the bean can be located and invoked under a normalized Java contract. It **does not yet prove** the pipeline converting raw JSON/`byte[]` through a specific adapter. If you need to test conversion inside the catalog, invoke through the appropriate message interface and content type for your version in a dedicated test.

### 11.3. Adapter Integration Tests

| Environment | What to Verify |
| --- | --- |
| HTTP | Send real JSON to the endpoint; verify status, content type, JSON output, missing/null fields |
| Spring Cloud Stream | Send a message to `classifyOrder-in-0` using Test Binder/broker; read `classifyOrder-out-0`; verify JSON/headers |
| Serverless | Use a sample trigger event; verify handler/serialization, timeout, and output |

A deserialization error may occur **before** `decideOrder` ever runs, so you cannot conclude an adapter works solely because business unit tests pass.

### 11.4. Minimum JSON Test Cases to Include

| Case | Expectation to Verify |
| --- | --- |
| DTO with all fields, nested `lines` | Deserializes cleanly into `List<OrderLine>` |
| Missing `couponCode` | Uses nullable default if the mapper supports it properly |
| `couponCode: null` | Nullable field is handled properly |
| `orderId` missing/null | Does not slip through processing as a valid ID |
| `amountVnd: null` | Does not silently coerce to `0` if forbidden by contract |
| `quantity` is an invalid string | Converter fails or rejects per policy |
| JSON array into `List<OrderRequest>` | Generics are preserved rather than becoming a list of `Map` |
| `Envelope<OrderRequest>` | `payload` field is instantiated with the right type |
| Wrong `contentType` header | Converter mismatch is caught |
| JSON names differ from Kotlin properties | Annotations/naming strategies apply correctly in both directions |

## 12. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `FunctionCatalog.lookup("classifyOrder")` returns null | Bean not scanned or name mismatch | Check `@Configuration`, `@Bean`, `definition` |
| JSON becomes `Map` instead of `OrderRequest` | Target/generic type was lost | Declare explicit bean return type; use a type token if parsing directly |
| `data class` fails to deserialize | Missing Jackson Kotlin module, incompatible constructor/fields | Verify dependencies, schema, and registered mapper |
| Non-null field receives null | Nullability/primitive coercion config is not strict enough | Try the corresponding `FAIL_ON_NULL_FOR_PRIMITIVES` setting; test null/missing |
| Generic list contains `LinkedHashMap` | Only raw `List::class.java` was supplied | Use `TypeReference<List<YourDto>>` or a complete target type |
| Input 1 is parsed using Input 0's type | Wrong multi-input binding order | Check `TupleN<Flux<T>>` and `-in-0`/`-in-1` |
| JSON uses `order_id` while DTO uses `orderId` | Naming strategy/annotation mismatch | Apply appropriate annotations/mappings and test serialization |
| Converter reports unsupported content type | Wrong header/setting or missing converter | Check payload, `application/json`, and selected converter |
| Function processes properly, but topic has no messages | Binder/destination/producer issue | Check Spring Cloud Stream bindings and broker |
| Spring Boot 4 uses Jackson 2 imports | Mixed up Jackson generations | Check the BOM and switch artifacts/APIs to the right version |
| Collection element count mistaken for output count | Confusing generic payload with function arity | Distinguish `List<T>`, `Flux<T>`, and `TupleN<Flux<...>>` |

### Pre-Deployment Checklist

1. `@Bean` has **concrete input/output types** and an unambiguous name.
2. DTOs use `data class`/POJOs with sensible constructors, nullability, and defaults.
3. Nested collections retain concrete generics without inadvertently degrading to `Any`.
4. Kotlin runtime/reflection and JSON module match the Spring Boot/Jackson version.
5. `content-type` and binding/destination names are accurate.
6. Tests cover direct DTO parsing, generic wrapper parsing, missing/null fields, and primitive coercion.
7. Tests cover `FunctionCatalog` and the actual adapter in use.
8. External data errors are not masked by accidental defaults; logging/validation/acknowledgment policies are explicit.

## 13. Self-Check Exercises

**Question 1.** How do the two signatures below differ?

~~~kotlin
Function<OrderRequest, List<OrderDecision>>
Function<List<OrderRequest>, OrderDecision>
~~~

**Answer:** The first accepts one request and returns a **`List` value**. The second accepts **a list of requests** and returns a single decision. Both have one logical input and one logical output; multiple bindings are not created merely because `List` appears.

**Question 2.** Why is `List<OrderLine>` safer than `List<Map<String, Any?>>` when the schema is known?

**Answer:** The generic `OrderLine` provides an explicit element type and data structure; mappers and business logic can inspect `sku` and `quantity` without casting from a `Map`.

**Question 3.** Is `content-type: application/json` sufficient for the converter to know it should instantiate `Envelope<OrderRequest>`?

**Answer:** No. Content type only indicates the format. The converter also needs the **target type**, especially the generic type of the `payload` field.

**Question 4.** For `data class Customer(val id: String, val name: String = "UNKNOWN")`, is JSON omitting `name` the same as JSON setting `"name": null`?

**Answer:** Not by default. A missing property can fall back to the default parameter; an explicit null depends on nullability and mapper configuration.

**Question 5.** Why should you test `amountVnd: null` for a non-null `Long`?

**Answer:** Some Jackson configurations can coerce null for primitive types into JVM default values like `0`. Strict null policies, validation, and tests are needed.

**Question 6.** Why does a passing `decideOrder(OrderRequest(...))` test not prove an HTTP endpoint can parse JSON?

**Answer:** The unit test supplies an already-constructed Kotlin DTO. It bypasses JSON/`byte[]` conversion, header/`content-type` handling, and adapter wiring.

**Question 7.** When is `TypeReference<Envelope<OrderRequest>>` needed?

**Answer:** When **manually calling** a Jackson mapper to deserialize JSON into a nested generic type where raw `Envelope::class.java` does not carry sufficient type information.

## References

- [Spring Cloud Function — Programming model: FunctionCatalog, Type conversion, Kotlin lambdas](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Boot — Kotlin support and Kotlin JSON module](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Boot — JSON mapping and Jackson 2/3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Jackson Kotlin module — Constructor, default parameters, generic types](https://github.com/FasterXML/jackson-module-kotlin)
- [Spring Cloud Stream — Producing and consuming messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Kotlin — Generics and type erasure](https://kotlinlang.org/docs/generics.html)
- [Kotlin — Null safety](https://kotlinlang.org/docs/null-safety.html)
