# Testing Kotlin Functions via FunctionCatalog

## 1. Goal: Verify the Exact Contract That Adapters Actually See

In the **Spring Cloud Function** module (`SPRING_CLOUD_FUNCTION`), business logic is packaged as `Supplier`, `Function`, and `Consumer` beans. `FunctionCatalog` recognizes functional beans, standardizes invocation, supports composition, and converts messages so a single function can be reused across HTTP, event systems, or serverless environments with an appropriate adapter.

In Kotlin, a lambda can be written concisely:

~~~kotlin
val normalize: (String) -> String = { it.trim().uppercase() }
~~~

Testing `normalize(" o-101 ") == "O-101"` only shows that the **Kotlin logic** runs properly. It does **not** prove:

- The lambda was registered as a Spring bean.
- Spring Cloud Function recognized that bean inside `FunctionCatalog`.
- The lookup name is accurate.
- Parameter/return types were inferred correctly for the catalog wrapper.
- Composition or `Message` conversion behaves as expected.
- External adapters properly wire HTTP endpoints, input/output bindings, or serverless triggers.

Therefore, this guide organizes testing into layers:

~~~text
       Kotlin business logic
               |
         Pure UNIT TEST
               |
       Spring ApplicationContext
               |
    FUNCTION CATALOG INTEGRATION TEST
       /       |          \
  lookup     compose     Message / Flux
       \       |          /
               |
      ADAPTER INTEGRATION TEST
   HTTP / Spring Cloud Stream / Serverless
~~~

**Primary scope:** testing Spring Cloud Function with Kotlin and JUnit 5, **without needing to run a broker or web server** in basic catalog tests. HTTP, message broker, and serverless tests are separated because they carry additional responsibilities.

## 2. What Is FunctionCatalog and How Does It Differ from ApplicationContext?

`ApplicationContext` manages all Spring beans, including `@Configuration` objects, services, and beans of functional types. `FunctionCatalog` provides a dedicated view over the functions recognized by Spring Cloud Function.

| Access | Object Returned | What It Tests |
| --- | --- | --- |
| `OrderFunctions().normalizeCode()` | Directly instantiated Kotlin lambda | Pure logic, **without** starting Spring |
| `context.getBean("normalizeCode")` | Raw Spring bean (may be a Kotlin `Function1`) | Bean is registered in the context |
| `catalog.lookup("normalizeCode")` | Framework-wrapped/normalized function | Catalog recognizes the name and can apply SCF capabilities |
| `catalog.lookup("normalizeCode|prefixCode")` | Function composition | Two functions composed in order with compatible output/input types |

Key point: **catalog lookup does not necessarily return the exact same runtime class as the original bean**. According to Spring Cloud Function documentation, the `lookup` result is *instrumented* (wrapped) to provide features such as type conversion and composition. Do not use `assertSame(originalBean, catalogResult)` or compare class names to assert correctness.

### 2.1. Common Lookup Forms

~~~kotlin
// Java interface that Kotlin can use to reference the result.
import java.util.function.Function
import org.springframework.cloud.function.context.FunctionCatalog

fun normalizeThroughCatalog(catalog: FunctionCatalog, input: String): String {
    val function = requireNotNull(
        catalog.lookup<Function<String, String>>("normalizeCode")
    ) { "normalizeCode not found" }

    return function.apply(input)
}
~~~

The generic `lookup<T>(...)` method lets Kotlin code **declare the expected type**; the generic parameter itself is not a strong validation check guaranteeing your function actually returns `T`. Designing the bean signature and testing **actual inputs/outputs** remain the developer's responsibility.

Documentation also shows examples using the overload with `Function::class.java`:

~~~kotlin
val fn = catalog.lookup<Function<String, String>>(
    Function::class.java,
    "normalizeCode"
)
~~~

This explicitly requests a **function**, rather than a supplier or consumer. Overloads and wrapper classes can vary slightly across versions; in simple examples, `lookup("normalizeCode")` is usually easier to read.

## 3. Preparing a Sample Kotlin Application for Testing

The examples below use Kotlin/JVM, Spring Boot, Spring Cloud Function, Project Reactor, and JUnit 5. Sharing the `example.catalog` package lets `@SpringBootApplication` scan the related beans and configuration classes.

### 3.1. Data Classes and Pure Business Rules

~~~kotlin
package example.catalog

data class Order(
    val id: String,
    val totalVnd: Long
)

data class Decision(
    val orderId: String,
    val category: String
)

fun decideOrder(order: Order): Decision {
    require(order.id.isNotBlank()) { "id must not be blank" }
    require(order.totalVnd >= 0) { "totalVnd must not be negative" }

    return Decision(
        orderId = order.id,
        category = if (order.totalVnd >= 1_000_000)
            "PRIORITY" else "STANDARD"
    )
}
~~~

`decideOrder` knows nothing about HTTP requests, Kafka topics, or Lambda events. This allows testing business logic without creating an `ApplicationContext`.

### 3.2. `AuditStore` for Verifying Side Effects

Consumers usually only perform side effects, so an observable object is needed in tests:

~~~kotlin
package example.catalog

import java.util.concurrent.CopyOnWriteArrayList
import org.springframework.stereotype.Component

@Component
class AuditStore {
    private val recorded = CopyOnWriteArrayList<String>()

    fun add(code: String) {
        recorded.add(code)
    }

    fun snapshot(): List<String> = recorded.toList()

    fun clear() {
        recorded.clear()
    }
}
~~~

This is a **simple test double placed in the example**. In a real application, auditing should go through an appropriate interface/service; do not use an in-memory list as durable storage.

### 3.3. Declaring Kotlin and Java SAM Beans in One Configuration

~~~kotlin
package example.catalog

import java.util.Locale
import java.util.function.Function
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder
import reactor.core.publisher.Flux

@Configuration
class CatalogFunctions(private val auditStore: AuditStore) {

    // Kotlin function type: corresponds to Java Supplier<String>.
    @Bean
    fun seedCode(): () -> String = { "O-101" }

    // Kotlin function type: corresponds to Java Function<String, String>.
    @Bean
    fun normalizeCode(): (String) -> String = { raw ->
        raw.trim().uppercase(Locale.ROOT)
    }

    // For composition tests.
    @Bean
    fun prefixCode(): (String) -> String = { normalized ->
        "CHECKED:" + normalized
    }

    // Java SAM written in Kotlin, with explicit business generics.
    @Bean
    fun classifyOrder(): Function<Order, Decision> =
        Function { order -> decideOrder(order) }

    // Kotlin (String) -> Unit: corresponds to a Consumer<String>.
    @Bean
    fun auditCode(): (String) -> Unit = { code ->
        auditStore.add(code.trim())
    }

    // Function declaring input/output Message to illustrate headers.
    @Bean
    fun traceCode(): Function<Message<String>, Message<String>> =
        Function { incoming ->
            val requestId = incoming.headers["requestId"]
            val builder = MessageBuilder
                .withPayload(incoming.payload.trim().uppercase(Locale.ROOT))

            if (requestId != null) {
                builder.setHeader("requestId", requestId)
            }
            builder.build()
        }

    // Reactive function: takes a Flux and returns a Flux.
    @Bean
    fun classifyStream(): Function<Flux<Order>, Flux<Decision>> =
        Function { orders ->
            orders.map { order -> decideOrder(order) }
        }
}
~~~

The example intentionally defines multiple beans to test name lookup, function kinds, and composition. Therefore, when deploying the application into Spring Cloud Stream, explicitly choose the target bean with `spring.cloud.function.definition` rather than expecting the framework to pick the right one among multiple candidates.

### 3.4. Spring Boot Entry Point

~~~kotlin
package example.catalog

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class CatalogLessonApplication

fun main(args: Array<String>) {
    runApplication<CatalogLessonApplication>(*args)
}
~~~

When running tests, `CatalogLessonApplication` is used as the Spring Boot configuration. `CatalogFunctions` and `AuditStore` are in the same package or subpackage so component scanning can discover them. If placed outside the scan scope, configure imports/scanning accordingly.

## 4. Required Test Dependencies

`build.gradle.kts` snippet (not a complete build script):

~~~kotlin
plugins {
    kotlin("jvm")
    kotlin("plugin.spring")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-function-context")
    implementation(kotlin("reflect"))

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Assumes plugin and Spring library versions are managed by compatible plugins/BOMs. `kotlin-stdlib` is usually added automatically by the Kotlin Gradle plugin. When Jackson needs to deserialize `data class` types from JSON, add the Jackson Kotlin module and JSON dependencies matching your Spring Boot version. **Pure catalog tests do not need a broker or web adapter**.

Distinction:

| Dependency | Purpose in This Guide |
| --- | --- |
| Kotlin JVM/stdlib/reflection | Compiles and recognizes Kotlin types |
| Kotlin Spring compiler plugin | Opens Spring-annotated classes/members for proxying |
| Spring Boot starter | Creates the application context |
| `spring-cloud-function-context` | Provides `FunctionCatalog` and wrappers |
| Spring Boot Test + JUnit Jupiter | Creates the test context and assertions |
| `reactor-test` | `StepVerifier` for testing reactive streams |
| Jackson Kotlin module (optional) | Tests JSON ↔ Kotlin DTO conversion |
| Spring Cloud Stream Test Binder (optional) | Tests messaging bindings; **not part of** simple catalog tests |

## 5. First Testing Layer: Unit Tests Without Starting Spring

Testing beans or pure functions directly is fast and well-suited for business rules, boundary values, and exceptions.

~~~kotlin
package example.catalog

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

class PureLogicTest {

    @Test
    fun classifyPriorityOrder() {
        val result = decideOrder(Order("O-101", 1_000_000))
        assertEquals(Decision("O-101", "PRIORITY"), result)
    }

    @Test
    fun classifyStandardOrder() {
        val result = decideOrder(Order("O-102", 999_999))
        assertEquals(Decision("O-102", "STANDARD"), result)
    }

    @Test
    fun rejectInvalidAmount() {
        assertThrows(IllegalArgumentException::class.java) {
            decideOrder(Order("O-103", -1))
        }
    }

    @Test
    fun kotlinLambdaWorksWithoutSpring() {
        val functions = CatalogFunctions(AuditStore())
        val lambda: (String) -> String = functions.normalizeCode()
        assertEquals("O-101", lambda(" o-101 "))
    }
}
~~~

What **has been verified**: classification logic and the lambda run properly when instantiated directly. What **has not yet been verified**: whether `@Bean` annotations take effect, whether Spring registers the bean, whether the catalog recognizes Kotlin `Function1`, and whether message converters work.

## 6. Second Layer: Integration Tests with FunctionCatalog

`@SpringBootTest` boots a real application context. We inject `FunctionCatalog` and look up functions by **bean name**.

### 6.1. Looking Up Kotlin Lambdas and Checking Return Values

~~~kotlin
package example.catalog

import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

@SpringBootTest(
    classes = [CatalogLessonApplication::class],
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = [
        "spring.cloud.function.single-function-fallback-enabled=false"
    ]
)
class CatalogLookupTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun kotlinLambdaIsRegisteredAndCallable() {
        val function = requireNotNull(
            catalog.lookup<Function<String, String>>("normalizeCode")
        ) { "normalizeCode not found" }

        assertEquals("O-101", function.apply(" o-101 "))
    }

    @Test
    fun javaSamFunctionIsRegisteredAndCallable() {
        val function = requireNotNull(
            catalog.lookup<Function<Order, Decision>>("classifyOrder")
        )

        assertEquals(
            Decision("O-104", "PRIORITY"),
            function.apply(Order("O-104", 1_500_000))
        )
    }

    @Test
    fun missingNameIsNotAccidentallyMatched() {
        val missing = catalog.lookup<Function<String, String>>(
            "functionThatDoesNotExist"
        )
        org.junit.jupiter.api.Assertions.assertNull(missing)
    }
}
~~~

This is the centerpiece test of this guide: **access via `FunctionCatalog`, not by calling the raw bean directly**. The Kotlin signature `(String) -> String` is recognized by Spring Cloud Function as a functional bean matching Java `Function`.

> Why set `spring.cloud.function.single-function-fallback-enabled=false`? When the catalog contains only **one** function, Spring Cloud Function has a fallback mechanism allowing lookup with an empty or non-matching name. Disabling fallback keeps negative name tests meaningful even when the number of beans changes. With multiple functional beans, you should still look up the exact explicit name.

### 6.2. About the Return Type of `lookup`

Spring Cloud Function may return a **wrapper** implementing the corresponding Java interfaces. In Kotlin, generics on `lookup<Function<Order, Decision>>` let code call `apply` conveniently, but due to JVM generic type erasure, **this does not replace asserting data**.

Do not write:

~~~kotlin
// Wrong testing approach: depends on the lambda/wrapper class.
// assertEquals(originalBean.javaClass, catalogFunction.javaClass)
~~~

Check the **bean name**, **contract kind**, and **actual results**. How lambdas are wrapped can change across Spring Cloud Function versions without changing the business contract.

## 7. Testing Supplier and Consumer Through the Catalog

Kotlin has function types `() -> O` and `(I) -> Unit`. Spring Cloud Function maps them to `Supplier<O>` and `Consumer<I>` respectively.

~~~kotlin
package example.catalog

import java.util.function.Consumer
import java.util.function.Supplier
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

@SpringBootTest(
    classes = [CatalogLessonApplication::class],
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CatalogSupplierConsumerTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Autowired
    lateinit var store: AuditStore

    @AfterEach
    fun clearAudit() {
        store.clear()
    }

    @Test
    fun kotlinSupplierCanBeLookedUp() {
        val supplier = requireNotNull(
            catalog.lookup<Supplier<String>>("seedCode")
        )
        assertEquals("O-101", supplier.get())
    }

    @Test
    fun kotlinConsumerPerformsObservableSideEffect() {
        val consumer = requireNotNull(
            catalog.lookup<Consumer<String>>("auditCode")
        )
        consumer.accept(" O-201 ")

        assertEquals(listOf("O-201"), store.snapshot())
    }
}
~~~

A `Consumer` test should not simply compare the result with `Unit`: a consumer's business value lies in its **side effect**. Here we assert the data recorded by `AuditStore`. In a real system, you can use a mock repository/service or an explicitly injected test double.

### 7.1. Avoid Parallel Execution When Sharing Mutable State

`@SpringBootTest` can reuse an application context across multiple tests. `AuditStore` in this example is a singleton holding mutable state; if tests run in parallel or multiple tests write concurrently, results can interfere with each other.

To avoid flaky tests:

- Clean up data in `@BeforeEach` or `@AfterEach`.
- Use mocks, test-specific beans, or isolated stores when needed.
- Do not enable parallel execution for tests sharing singleton mutable state unless isolation is in place.
- Do not treat this test as proof that a real broker has acknowledged or persisted data.

## 8. Testing Function Composition

Composition chains the output of one function into the input of the next function:

~~~text
input " o-101 "
       |
       v
normalizeCode: (String) -> String
       |
      "O-101"
       |
       v
prefixCode: (String) -> String
       |
       v
   "CHECKED:O-101"
~~~

In `FunctionCatalog`, the definition string `normalizeCode|prefixCode` represents a **pipeline**.

~~~kotlin
package example.catalog

import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

@SpringBootTest(classes = [CatalogLessonApplication::class])
class CatalogCompositionTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun compositionAppliesFunctionsInOrder() {
        val pipeline = requireNotNull(
            catalog.lookup<Function<String, String>>(
                "normalizeCode|prefixCode"
            )
        )

        assertEquals(
            "CHECKED:O-101",
            pipeline.apply(" o-101 ")
        )
    }

    @Test
    fun reversingCompositionChangesOutput() {
        val pipeline = requireNotNull(
            catalog.lookup<Function<String, String>>(
                "prefixCode|normalizeCode"
            )
        )

        assertEquals(
            "CHECKED: O-101",
            pipeline.apply(" o-101 ")
        )
    }
}
~~~

**Note:** The two pipelines in this example produce different outputs because `prefixCode` prepends `"CHECKED:"`, while `normalizeCode` calls `trim()` on the **entire** string (without removing internal spaces). In `prefixCode|normalizeCode`, the intermediate string is `"CHECKED: o-101 "`; after `trim().uppercase()`, it becomes `"CHECKED: O-101"`.

Composition is not fan-out: it does not create two output bindings or two endpoints. If two functions have incompatible types, a converter may be needed; do not assume every composed chain runs properly merely because the `a|b` syntax is accepted.

## 9. Testing Message Headers via FunctionCatalog

When a functional bean processes Spring Messaging `Message<T>`, both payload and headers live inside one message. The `traceCode` example from this guide:

~~~kotlin
@Bean
fun traceCode(): Function<Message<String>, Message<String>> =
    Function { incoming ->
        val requestId = incoming.headers["requestId"]
        val builder = MessageBuilder
            .withPayload(incoming.payload.trim().uppercase(Locale.ROOT))
        if (requestId != null) {
            builder.setHeader("requestId", requestId)
        }
        builder.build()
    }
~~~

Testing via the catalog:

~~~kotlin
package example.catalog

import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

@SpringBootTest(classes = [CatalogLessonApplication::class])
class CatalogHeadersTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun preservesSelectedHeaderAndChangesPayload() {
        val function = requireNotNull(
            catalog.lookup<
                Function<Message<String>, Message<String>>
            >("traceCode")
        )

        val incoming: Message<String> = MessageBuilder
            .withPayload(" o-101 ")
            .setHeader("requestId", "req-101")
            .build()

        val outgoing: Message<String> = function.apply(incoming)

        assertEquals("O-101", outgoing.payload)
        assertEquals("req-101", outgoing.headers["requestId"])
    }
}
~~~

**Lesson:** Do not assume every message header is automatically copied after changing the payload; the example explicitly chose `requestId` to preserve. Under different wrappers or content-type configurations, Spring Cloud Function may convert message payloads; the current test specifically verifies the explicitly declared `Message<String>` path.

## 10. Testing JSON Conversion: Separating Type Information from Content Type

`FunctionCatalog` can combine the function's target type with the message's `contentType` metadata to select a converter. Inputs often arrive as `Message<byte[]>` or `Message<String>`, whereas the bean expects `Order`.

~~~text
Incoming Message<byte[]>
  payload     = JSON bytes
  contentType = application/json
          |
          v
 FunctionCatalog wrapper
  target input = Order
          |
          v
 JSON MessageConverter
          |
          v
 classifyOrder(): Function<Order, Decision>
          |
          v
 result (DTO / serialized payload depending on context)
~~~

### 10.1. JSON Converter Tests Must Mind the Jackson Version

To verify JSON behavior without a broker, you can pass a `Message<byte[]>` directly into the function looked up from the catalog. The output may be the DTO directly or a serialized message/payload depending on the lookup and conversion setup. **Do not blindly cast the result to `Decision` if you requested an output content type.**

The example below is for **Spring Boot 3.x, Jackson 2** and requires `jackson-module-kotlin` and a suitable converter on the runtime classpath:

~~~kotlin
package example.catalog

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import java.nio.charset.StandardCharsets
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog
import org.springframework.messaging.Message
import org.springframework.messaging.MessageHeaders
import org.springframework.messaging.support.MessageBuilder
import org.springframework.util.MimeTypeUtils

@SpringBootTest(classes = [CatalogLessonApplication::class])
class CatalogJsonConversionTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    private val mapper = jacksonObjectMapper()

    @Test
    fun convertsJsonMessageIntoOrder() {
        val function = requireNotNull(
            catalog.lookup<Function<Any, Any>>("classifyOrder")
        )

        val json = """
            {"id":"O-301","totalVnd":1500000}
        """.trimIndent().toByteArray(StandardCharsets.UTF_8)

        val input: Message<ByteArray> = MessageBuilder
            .withPayload(json)
            .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.APPLICATION_JSON
            )
            .build()

        val result: Any = function.apply(input)
        val body: Any = if (result is Message<*>) {
            result.payload
        } else {
            result
        }

        val decision: Decision = when (body) {
            is Decision -> body
            is ByteArray -> mapper.readValue(
                body, Decision::class.java
            )
            is String -> mapper.readValue(
                body, Decision::class.java
            )
            else -> error(
                "Output type not yet supported by test: "
                    + body.javaClass.name
            )
        }

        assertEquals(Decision("O-301", "PRIORITY"), decision)
    }
}
~~~

This is a **catalog conversion integration test**, not an HTTP/Kafka test. `lookup<Function<Any, Any>>` is only used so the test can pass `Message<byte[]>` into the wrapper; it **does not alter the actual business signature** of the `classifyOrder` bean.

When using **Spring Boot 4.x/Jackson 3**, JSON dependencies and packages may move to `tools.jackson.*`; replace imports/mapper APIs to match your actual stack. If the converter in your version returns the result in a different form, identify and assert **the expected output contract** rather than silently letting a test pass with an unexpected type.

### 10.2. Negative Cases to Test

| Test Input | Objective |
| --- | --- |
| Valid JSON, `application/json` | Converter constructs `Order` accurately |
| JSON missing `id` field | Deserialization or validation behavior |
| JSON with invalid `totalVnd` | Type conversion failure behavior |
| Text payload with mismatched `contentType` | Converter mismatch handling path |
| JSON `ByteArray` without `contentType` | Default behavior for the version in use |
| JSON with extra/unexpected fields | Deserialization policy |

Do not assume all of these errors must throw the exact same exception. Some errors occur inside the converter, some inside `decideOrder`, and others are transformed by wrappers/adapters. In catalog tests, separate the **error source** clearly instead of asserting a single exception type for every case.

## 11. Testing Reactive Functions via FunctionCatalog

The `classifyStream` bean has the signature:

~~~kotlin
Function<Flux<Order>, Flux<Decision>>
~~~

This is **one input stream and one output stream**; a `Flux` emitting multiple items does not create extra output bindings. When the source is a publisher, use `StepVerifier` instead of calling `subscribe()` manually and checking on another thread.

~~~kotlin
package example.catalog

import java.util.function.Function
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

@SpringBootTest(classes = [CatalogLessonApplication::class])
class CatalogReactiveTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun reactiveFunctionHandlesMultipleOrders() {
        val function = requireNotNull(
            catalog.lookup<Function<Flux<Order>, Flux<Decision>>>(
                "classifyStream"
            )
        )

        val input = Flux.just(
            Order("O-401", 2_000_000),
            Order("O-402", 250_000)
        )
        val output: Flux<Decision> = function.apply(input)

        StepVerifier.create(output)
            .expectNext(Decision("O-401", "PRIORITY"))
            .expectNext(Decision("O-402", "STANDARD"))
            .verifyComplete()
    }

    @Test
    fun invalidEventTerminatesUnprotectedPipeline() {
        val function = requireNotNull(
            catalog.lookup<Function<Flux<Order>, Flux<Decision>>>(
                "classifyStream"
            )
        )

        val output = function.apply(
            Flux.just(
                Order("O-403", -1),
                Order("O-404", 500_000)
            )
        )

        StepVerifier.create(output)
            .expectError(IllegalArgumentException::class.java)
            .verify()
    }
}
~~~

The last test confirms that when `decideOrder` throws an exception inside `map`, the publisher emits `onError` and terminates the subscription; subsequent records do not automatically continue. If the business requirement is "one bad record does not stop the stream", wrap errors in a **per-message inner publisher** and test that policy explicitly.

### 11.1. Reactive Tests Do Not Prove Broker Backpressure

Testing a `Flux.just(...)` with `StepVerifier` tests **Reactor and the catalog**. It does not prove:

- A Kafka/RabbitMQ binder is configured.
- End-to-end backpressure exists from the broker to the logic.
- Records are acknowledged or offsets committed.
- External retries, DLQs, partitions, and ordering work.

Those are the responsibility of Spring Cloud Stream/binder tests. In Spring Cloud Stream, a reactive function is normally invoked once to construct the pipeline; imperative message handler error handlers do not automatically apply per element inside a `Flux`.

## 12. Testing by Name, by Definition, and Bean Filtering

### 12.1. Default Bean Names and Custom Explicit Names

~~~kotlin
@Bean("externalNormalize")
fun normalize(): (String) -> String = { it.trim().uppercase() }
~~~

With this naming, catalog tests must look up `externalNormalize`. Looking up by the method name `normalize` will not necessarily find it, especially with fallback disabled:

~~~kotlin
val fn = requireNotNull(
    catalog.lookup<Function<String, String>>("externalNormalize")
)
~~~

### 12.2. Testing Multiple Functions in the Same Context

If an application has multiple functional beans, `spring.cloud.function.definition` helps adapters select the right function. However, **unit/catalog tests can look up each bean independently** without binding them externally.

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrder
~~~

This YAML snippet only takes effect when an adapter/framework reads `definition`. It does **not** mean the catalog holds only one bean or that every `lookup` automatically redirects to `classifyOrder`.

### 12.3. Name Lists Can Be Lazily Initialized

Spring Cloud Function uses **lazy registration** for functional beans. Inspecting `catalog.getNames(...)` before any lookup has occurred can cause you to misinterpret the result depending on how and when beans are registered.

To test a specific bean, **looking up the exact name and asserting its behavior** is stronger than checking a list of names alone. You can use `getNames(...)` for diagnostics, but do not treat it as the sole business verification.

### 12.4. Beans Excluded from the Catalog

The `spring.cloud.function.ineligible-definitions` property excludes beans that should not be treated as functional beans. When `lookup` fails even though `ApplicationContext` contains the bean, check:

- Is the bean of a supported `Supplier`/`Function`/`Consumer` or Kotlin lambda type?
- Is the bean name exact?
- Is the bean excluded by `ineligible-definitions`?
- Do the Kotlin runtime/type metadata and Spring Cloud Function version match?

## 13. When Should ApplicationContextRunner Be Used?

`@SpringBootTest` starts the application close to real runtime conditions, though it can be slower or pull in many auto-configurations. When you only want to test **a specific configuration combination**, you can consider `ApplicationContextRunner` from Spring Boot Test.

However, `ApplicationContextRunner` **does not automatically include all Spring Cloud Function auto-configurations**. If you only register `CatalogFunctions`, the context may contain your Kotlin beans without `FunctionCatalog`.

A proper setup must load the **Spring Cloud Function configurations appropriate** for your version along with the relevant beans, and then assert that `FunctionCatalog` exists. Because auto-configuration lists and APIs can change across Spring Boot/SCF versions, do not hardcode a list copied from an old tutorial while ignoring your project's BOM.

**Practical rule:** start with `@SpringBootTest(classes = [CatalogLessonApplication::class])` for a reliable baseline; only optimize into slice/context runner tests when you know the exact auto-configurations required.

## 14. Distinguishing Catalog Integration Tests from Adapter Integration Tests

| Test Level | Example | Guarantees | Does Not Guarantee |
| --- | --- | --- | --- |
| Kotlin unit | `decideOrder(Order(...))` | Business rules | Spring context/catalog |
| Spring bean | `context.getBean("normalizeCode")` | Bean is registered | Catalog wrapper and converters |
| FunctionCatalog | `catalog.lookup("normalizeCode")` then `apply` | Exact name, wrapper, functional behavior | HTTP routes, topics, Lambda triggers |
| Catalog message conversion | Call `FunctionCatalog` with `Message<byte[]>`, `application/json` | Target type and converter run in context | Real broker/web behavior |
| Catalog reactive | `StepVerifier` on `Flux` from catalog | Reactor signals and transformations | Binder backpressure and ACKs |
| Web adapter | Real HTTP request via test client | URL, HTTP status, JSON/headers | Kafka/SQS delivery |
| Stream adapter | Test Binder or broker integration test | Bindings, serialization, destinations | Serverless triggers |
| Serverless adapter | Invocation via handler/sample event | Event contract, output mapping | Other triggers or production infra |

To **test HTTP**, add the appropriate web adapter and write a test sending real requests to the exposed endpoint; do not treat a successful `lookup` as proof that a route is exposed. To **test messaging**, use Spring Cloud Stream Test Binder/broker tests, send a message to `classifyOrder-in-0`, and inspect `classifyOrder-out-0`. To **test serverless**, invoke the handler with an event matching the trigger type and verify the platform response/exception.

## 15. Troubleshooting When FunctionCatalog Tests Fail

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| Unit test passes, catalog lookup returns null | `@Bean` not scanned, wrong name | Check packages, `@Configuration`, bean name |
| Bean exists in Spring, but catalog does not recognize it | Return type is unsupported or missing Kotlin integration | Declare explicit `() -> O`, `(I) -> O`, `(I) -> Unit`, or Java SAM |
| Wrong name lookup still returns a function | Single-function fallback when catalog has one function | Disable `single-function-fallback-enabled` in negative tests |
| `ClassCastException` when calling `apply` | Expected generic does not match actual contract or version mismatch | Check signatures, lookup wrappers, and BOM |
| Composition test yields unexpected output | Reversed `a|b` order | Assert each stage and pipeline order |
| Works via `ApplicationContext`, fails JSON conversion | Bypassed catalog wrapper/converter | Test `Message` via catalog with content type |
| JSON enters, but DTO is wrong/null | Missing fields, Jackson Kotlin module, unsuitable defaults/nullability | Check schema, converter, and type metadata |
| Consumer test passes, but no audit recorded | Only asserted consumer exists without checking side effects | Inject a test double and assert side effects |
| `Flux` test does not run | No subscriber | Use `StepVerifier` or a subscribing adapter |
| `Flux` stops after one bad record | Terminal `onError` | Design per-element error handling if needed |
| Catalog test passes, but topic gets no messages | Missing binder or wrong destination | Write a separate Spring Cloud Stream adapter test |
| Catalog test unnecessarily boots an HTTP server | Loading too much context | Use `WebEnvironment.NONE` when not testing web |
| Tests are flaky when run in parallel | Shared singleton state | Isolate state, reset test doubles, avoid uncontrolled parallelism |

### Checklist When Investigating a Failing Test

1. Ensure pure business logic passes unit tests first.
2. Verify the test application loads the right `@SpringBootApplication`/`@Configuration`.
3. Confirm the raw bean exists and has the **right name**.
4. Check the `@Bean` type: Kotlin lambda or Java `Function`/`Supplier`/`Consumer`?
5. Look up the exact name via `FunctionCatalog`, verifying behavior rather than wrapper classes.
6. When testing JSON, verify `contentType`, target type, and converter/Jackson dependencies.
7. When testing reactive functions, verify subscriptions and `onError` with `StepVerifier`.
8. Only after those steps, verify the HTTP/binder/serverless adapter.

## 16. Self-Check Questions

**Question 1.** Why is `CatalogFunctions(AuditStore()).normalizeCode()(" a ")` running cleanly insufficient to prove Spring Cloud Function works?

**Answer:** That is a direct Kotlin invocation; it neither starts a Spring context nor goes through `FunctionCatalog` to test bean naming, wrappers, conversion, or composition.

**Question 2.** Why should you call `catalog.lookup<Function<String,String>>("normalizeCode")` and assert the output, instead of comparing `javaClass` of the returned function?

**Answer:** Spring Cloud Function may wrap the bean to support integration features. The contract and behavior matter more than the specific runtime class.

**Question 3.** There are three functional beans in the context. If you want to look up the `classifyOrder` bean, which name should you use?

**Answer:** The bean name `classifyOrder`; do not rely on single-function fallback. When an adapter selects a function to bind, configure `spring.cloud.function.definition=classifyOrder`.

**Question 4.** Does `lookup("normalizeCode|prefixCode")` automatically create two output bindings?

**Answer:** No. Composition is a sequential pipeline; in this example the final output is a single `String`.

**Question 5.** A Kotlin consumer `(String) -> Unit` is looked up successfully. Which test verifies its business behavior?

**Answer:** Invoke the consumer and check its **side effect** via a mock/test double, such as checking the entries added to `AuditStore`.

**Question 6.** When sending a `Message<byte[]>` containing JSON into `Function<Order,Decision>`, why are both the generic type and `contentType` needed?

**Answer:** The generic type indicates the **target type `Order`**, while `contentType` indicates JSON formatting so the converter picks the appropriate decoder.

**Question 7.** Does `StepVerifier` passing on `Flux.just(...)` through the catalog prove a Kafka message committed its offset?

**Answer:** No. That is a Reactor/catalog test; binders, brokers, retries, and acknowledgments must be verified with adapter integration tests.

**Question 8.** Why does testing a non-existent function name sometimes still return a function?

**Answer:** When the catalog contains only one function, Spring Cloud Function has a single-function fallback. In negative tests, disable the fallback or build a multi-function context with explicit names.

## References

- [Spring Cloud Function — Programming model, FunctionCatalog, Kotlin Lambda support](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Functional Bean Definitions and testing via FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — Kotlin Support](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Spring Cloud Stream Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
