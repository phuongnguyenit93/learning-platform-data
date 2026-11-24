# Kiểm thử hàm Kotlin qua FunctionCatalog

## 1. Mục tiêu: kiểm tra đúng hợp đồng mà adapter thực sự nhìn thấy

Trong module **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được đóng gói bằng `Supplier`, `Function` và `Consumer`. `FunctionCatalog` nhận diện các functional bean, chuẩn hóa lời gọi, hỗ trợ composition và chuyển đổi thông điệp để một hàm có thể được tái sử dụng qua HTTP, hệ thống sự kiện hoặc môi trường serverless với adapter phù hợp.

Trong Kotlin, một lambda được viết ngắn gọn:

~~~kotlin
val normalize: (String) -> String = { it.trim().uppercase() }
~~~

Kiểm thử `normalize(" o-101 ") == "O-101"` chỉ cho thấy **logic Kotlin** chạy đúng. Nó **chưa** chứng minh:

- Lambda đã được đăng ký thành Spring bean.
- Spring Cloud Function đã nhận diện bean đó trong `FunctionCatalog`.
- Tên dùng để tra cứu chính xác.
- Kiểu tham số/kiểu kết quả được suy ra đúng cho wrapper của catalog.
- Composition hoặc chuyển đổi `Message` được thực hiện như mong đợi.
- Adapter ngoài hệ thống đã nối HTTP endpoint, input/output binding hoặc serverless trigger đúng.

Vì vậy, bài này tổ chức kiểm thử thành các lớp:

~~~text
       Kotlin business logic
               |
         UNIT TEST thuần
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

**Phạm vi chính:** kiểm thử Spring Cloud Function bằng Kotlin và JUnit 5, **không cần chạy broker hoặc web server** trong những test catalog cơ bản. Test HTTP, message broker và serverless được tách ra vì chúng có trách nhiệm bổ sung.

## 2. FunctionCatalog là gì và khác ApplicationContext như thế nào?

`ApplicationContext` quản lý toàn bộ bean Spring, bao gồm các đối tượng `@Configuration`, service và những bean có kiểu functional. `FunctionCatalog` cung cấp một góc nhìn dành riêng cho các hàm mà Spring Cloud Function nhận diện.

| Truy cập | Đối tượng nhận được | Điều kiểm thử |
| --- | --- | --- |
| `OrderFunctions().normalizeCode()` | Kotlin lambda được tạo trực tiếp | Logic thuần, **không** khởi động Spring |
| `context.getBean("normalizeCode")` | Spring bean gốc (có thể là Kotlin `Function1`) | Bean đã được đăng ký trong context |
| `catalog.lookup("normalizeCode")` | Hàm đã được framework bọc/chuẩn hóa | Catalog nhận diện tên và có thể áp dụng khả năng SCF |
| `catalog.lookup("normalizeCode|prefixCode")` | Function composition | Hai hàm được ghép theo thứ tự, kiểu đầu ra/đầu vào tương thích |

Điểm mấu chốt: **catalog lookup không nhất thiết trả cùng class runtime với bean gốc**. Theo tài liệu Spring Cloud Function, kết quả `lookup` được *instrumented* (bọc) để cung cấp tính năng như chuyển đổi kiểu và composition. Không nên dùng `assertSame(beanGoc, catalogResult)` hoặc so tên class để xác nhận đúng/sai.

### 2.1. Các dạng lookup thường dùng

~~~kotlin
// Java interface mà Kotlin có thể dùng để tham chiếu kết quả.
import java.util.function.Function
import org.springframework.cloud.function.context.FunctionCatalog

fun normalizeThroughCatalog(catalog: FunctionCatalog, input: String): String {
    val function = requireNotNull(
        catalog.lookup<Function<String, String>>("normalizeCode")
    ) { "Không tìm thấy normalizeCode" }

    return function.apply(input)
}
~~~

Phương thức generic `lookup<T>(...)` cho phép code Kotlin **khai báo kiểu mong đợi**; bản thân tham số generic không phải một lần validation mạnh mẽ rằng function của bạn chắc chắn trả chính xác `T`. Trách nhiệm thiết kế chữ ký bean và kiểm thử **đầu vào/đầu ra thực tế** vẫn thuộc về người viết.

Tài liệu cũng có ví dụ dùng overload với `Function::class.java`:

~~~kotlin
val fn = catalog.lookup<Function<String, String>>(
    Function::class.java,
    "normalizeCode"
)
~~~

Đây là cách yêu cầu một **function**, thay vì supplier hoặc consumer. Các overload và lớp wrapper có thể có khác biệt giữa phiên bản; ở ví dụ đơn giản, `lookup("normalizeCode")` thường dễ đọc hơn.

## 3. Chuẩn bị ứng dụng Kotlin mẫu để kiểm thử

Các ví dụ dưới đây dùng Kotlin/JVM, Spring Boot, Spring Cloud Function, Project Reactor và JUnit 5. Cùng một package `example.catalog` giúp `@SpringBootApplication` quét các bean và lớp cấu hình liên quan.

### 3.1. Data class và quy tắc nghiệp vụ thuần

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
    require(order.id.isNotBlank()) { "id không được rỗng" }
    require(order.totalVnd >= 0) { "totalVnd không được âm" }

    return Decision(
        orderId = order.id,
        category = if (order.totalVnd >= 1_000_000)
            "PRIORITY" else "STANDARD"
    )
}
~~~

`decideOrder` không biết về HTTP request, Kafka topic hay Lambda event. Điều này giúp test nghiệp vụ mà không phải tạo `ApplicationContext`.

### 3.2. AuditStore để kiểm chứng side effect

Consumer thường chỉ thực hiện tác dụng phụ, nên cần một đối tượng quan sát được trong test:

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

Đây là một **test double đơn giản đặt trong ví dụ**. Khi làm ứng dụng thật, audit nên đi qua một interface/service phù hợp; không dùng danh sách trong bộ nhớ làm lưu trữ bền vững.

### 3.3. Khai báo bean Kotlin và Java SAM cùng một cấu hình

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

    // Kotlin function type: tương ứng Java Supplier<String>.
    @Bean
    fun seedCode(): () -> String = { "O-101" }

    // Kotlin function type: tương ứng Java Function<String, String>.
    @Bean
    fun normalizeCode(): (String) -> String = { raw ->
        raw.trim().uppercase(Locale.ROOT)
    }

    // Phục vụ test composition.
    @Bean
    fun prefixCode(): (String) -> String = { normalized ->
        "CHECKED:" + normalized
    }

    // Java SAM viết bằng Kotlin, với generic nghiệp vụ rõ ràng.
    @Bean
    fun classifyOrder(): Function<Order, Decision> =
        Function { order -> decideOrder(order) }

    // Kotlin (String) -> Unit: tương ứng một Consumer<String>.
    @Bean
    fun auditCode(): (String) -> Unit = { code ->
        auditStore.add(code.trim())
    }

    // Hàm khai báo Message đầu vào/đầu ra để minh họa headers.
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

    // Reactive function: nhận một Flux và trả một Flux.
    @Bean
    fun classifyStream(): Function<Flux<Order>, Flux<Decision>> =
        Function { orders ->
            orders.map { order -> decideOrder(order) }
        }
}
~~~

Ví dụ có nhiều bean **cố ý** để kiểm thử tra cứu tên, loại hàm và composition. Do đó khi đưa ứng dụng vào Spring Cloud Stream phải chọn rõ bean bằng `spring.cloud.function.definition`, không kỳ vọng framework tự chọn đúng hàm giữa nhiều ứng viên.

### 3.4. Entry point Spring Boot

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

Khi chạy test, `CatalogLessonApplication` được sử dụng làm cấu hình Spring Boot. Lớp `CatalogFunctions` và `AuditStore` cùng package hoặc package con nên có thể được component scan phát hiện. Nếu đặt chúng ngoài phạm vi scan, cần cấu hình import/scan tương ứng.

## 4. Dependency kiểm thử cần có

Đoạn trích `build.gradle.kts` (không phải một build script hoàn chỉnh):

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

Giả định phiên bản plugin và thư viện Spring đã được quản lý bằng các plugin/BOM tương thích. `kotlin-stdlib` thường đã được Kotlin Gradle plugin thêm tự động. Khi cần Jackson deserialize `data class` từ JSON, thêm Jackson Kotlin module và các dependency JSON phù hợp với Spring Boot đang dùng. **Test catalog thuần không cần thêm broker hoặc web adapter**.

Phân biệt:

| Dependency | Mục đích trong bài |
| --- | --- |
| Kotlin JVM/stdlib/reflection | Biên dịch và nhận diện kiểu Kotlin |
| Kotlin Spring compiler plugin | Hỗ trợ mở lớp/thành viên có annotation Spring cho proxy |
| Spring Boot starter | Tạo application context |
| `spring-cloud-function-context` | Cung cấp `FunctionCatalog` và wrapper |
| Spring Boot Test + JUnit Jupiter | Tạo test context và assertion |
| `reactor-test` | `StepVerifier` kiểm tra luồng reactive |
| Jackson Kotlin module (tùy chọn) | Test conversion JSON ↔ Kotlin DTO |
| Spring Cloud Stream Test Binder (tùy chọn) | Test binding messaging; **không thuộc** catalog test đơn giản |

## 5. Cấp kiểm thử thứ nhất: unit test không khởi động Spring

Test trực tiếp bean hoặc pure function rất nhanh, phù hợp với các quy tắc nghiệp vụ, dữ liệu biên và exception.

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

Điều **đã được kiểm chứng**: logic phân loại và lambda chạy đúng khi tạo trực tiếp. Điều **chưa được kiểm chứng**: annotation `@Bean` có hiệu lực, Spring có đăng ký bean, catalog có nhận diện Kotlin `Function1` hay không, và message converter có hoạt động hay không.

## 6. Cấp thứ hai: integration test với FunctionCatalog

`@SpringBootTest` khởi tạo một application context thực. Ta inject `FunctionCatalog` rồi tra cứu hàm theo **tên bean**.

### 6.1. Tra cứu Kotlin lambda và kiểm tra giá trị trả về

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
        ) { "Không tìm thấy normalizeCode" }

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

Đây là test quan trọng nhất của bài: **truy cập qua `FunctionCatalog`, không gọi trực tiếp bean gốc**. Chữ ký Kotlin `(String) -> String` được Spring Cloud Function nhận diện như functional bean tương ứng Java `Function`.

> Tại sao đặt `spring.cloud.function.single-function-fallback-enabled=false`? Nếu catalog chỉ có **một** function, Spring Cloud Function có cơ chế fallback cho phép tra cứu bằng tên rỗng hoặc tên không khớp. Tắt fallback khiến bài test về tên sai có ý nghĩa ngay cả khi số bean thay đổi. Với nhiều functional bean, vẫn nên tra cứu đúng tên tường minh.

### 6.2. Về kiểu trả về của lookup

Spring Cloud Function có thể trả về một **wrapper** cài đặt các interface Java tương ứng. Trong Kotlin, generic ở `lookup<Function<Order, Decision>>` giúp code gọi `apply` một cách thuận tiện, nhưng do Java generics có type erasure, **đây không thay thế việc assert dữ liệu**.

Không nên viết:

~~~kotlin
// Sai hướng kiểm thử: phụ thuộc class của lambda/wrapper.
// assertEquals(originalBean.javaClass, catalogFunction.javaClass)
~~~

Hãy kiểm tra **tên bean**, **loại hợp đồng** và **kết quả thực tế**. Cách bọc lambda có thể thay đổi theo Spring Cloud Function version mà không làm thay đổi hợp đồng nghiệp vụ.

## 7. Kiểm thử Supplier và Consumer qua catalog

Kotlin có function type `() -> O` và `(I) -> Unit`. Spring Cloud Function ánh xạ chúng tương ứng với `Supplier<O>` và `Consumer<I>`.

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

Test `Consumer` không nên chỉ so sánh kết quả với `Unit`: nghiệp vụ của consumer nằm ở **side effect**. Ở đây ta kiểm tra dữ liệu được `AuditStore` ghi nhận. Trong hệ thống thực, có thể dùng mock repository/service hoặc một test double được inject rõ ràng.

### 7.1. Kiểm thử không chạy song song khi dùng trạng thái chia sẻ

`@SpringBootTest` có thể tái sử dụng application context giữa nhiều test. `AuditStore` ở ví dụ là singleton chứa mutable state; nếu chạy test song song hoặc có nhiều test ghi cùng lúc, kết quả có thể bị nhiễu.

Để tránh flaky test:

- Dọn dữ liệu ở `@BeforeEach` hoặc `@AfterEach`.
- Dùng mock, test-specific bean hay kho dữ liệu cô lập nếu cần.
- Không bật parallel execution cho các test dùng singleton mutable state trừ khi có cơ chế cô lập.
- Không dùng test này như bằng chứng rằng một broker thật đã acknowledgment hoặc persist dữ liệu.

## 8. Kiểm thử Function Composition

Composition cho phép nối output của một function vào input của function tiếp theo:

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

Trong `FunctionCatalog`, chuỗi định nghĩa `normalizeCode|prefixCode` biểu diễn một **pipeline**.

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

**Lưu ý:** Hai pipeline ở ví dụ có thể cho kết quả khác nhau vì `prefixCode` thêm chuỗi `"CHECKED:"` phía trước, còn `normalizeCode` `trim()` **toàn bộ** chuỗi (không loại khoảng trắng bên trong). Ở pipeline `prefixCode|normalizeCode`, chuỗi trung gian là `"CHECKED: o-101 "`; sau `trim().uppercase()` còn `"CHECKED: O-101"`.

Composition không phải fan-out: nó không tự tạo hai output binding hoặc hai endpoint. Nếu hai hàm không tương thích kiểu, có thể cần converter; đừng mặc nhiên mọi chuỗi ghép đều chạy đúng chỉ vì cú pháp `a|b` được chấp nhận.

## 9. Kiểm thử Message headers qua FunctionCatalog

Khi functional bean xử lý Spring Messaging `Message<T>`, payload và headers cùng nằm trong một message. Ví dụ `traceCode` của bài:

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

Test qua catalog:

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

**Bài học:** Đừng giả định mọi header của message đều tự động được sao chép sau khi đổi payload; ví dụ đã chọn rõ `requestId` để giữ. Khi dùng wrapper/cấu hình content-type khác, Spring Cloud Function có thể chuyển đổi payload của message; test hiện tại chỉ kiểm tra đường đi `Message<String>` đã được khai báo rõ.

## 10. Kiểm thử chuyển đổi JSON: tách type information khỏi content type

`FunctionCatalog` có thể phối hợp kiểu đích của function với thông tin `contentType` của message để chọn converter. Đầu vào thường đến dưới dạng `Message<byte[]>` hoặc `Message<String>`, trong khi bean muốn nhận `Order`.

~~~text
Incoming Message<byte[]>
  payload     = bytes JSON
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
 result (DTO / serialized payload theo ngữ cảnh)
~~~

### 10.1. Test JSON converter cần chú ý phiên bản Jackson

Để kiểm chứng hành vi JSON mà không cần broker, có thể gửi `Message<byte[]>` trực tiếp tới hàm tra cứu từ catalog. Đầu ra có thể là DTO trực tiếp hoặc message/payload đã được serialize tùy cách lookup và conversion đang dùng. **Không nên ép kết quả sang `Decision` một cách mù quáng nếu bạn đã yêu cầu output content type.**

Ví dụ dưới đây dành cho **Spring Boot 3.x, Jackson 2** và yêu cầu có `jackson-module-kotlin` cùng converter phù hợp trong runtime:

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
                "Kiểu output chưa được test hỗ trợ: "
                    + body.javaClass.name
            )
        }

        assertEquals(Decision("O-301", "PRIORITY"), decision)
    }
}
~~~

Đây là một **test tích hợp chuyển đổi của catalog**, chưa phải test HTTP/Kafka. `lookup<Function<Any, Any>>` chỉ nhằm cho phép truyền `Message<byte[]>` vào wrapper trong test; nó **không đổi chữ ký nghiệp vụ thực** của bean `classifyOrder`.

Khi dùng **Spring Boot 4.x/Jackson 3**, dependency và package JSON có thể chuyển sang `tools.jackson.*`; phải thay import/mapper API thích hợp với stack thực tế. Nếu converter của phiên bản bạn dùng trả kết quả dưới dạng khác, hãy xác định và assert **hợp đồng output mong muốn**, không âm thầm cho test pass với kiểu ngoài dự kiến.

### 10.2. Các trường hợp âm cần kiểm tra

| Input thử nghiệm | Mục tiêu |
| --- | --- |
| JSON hợp lệ, `application/json` | Converter tạo đúng `Order` |
| JSON thiếu trường `id` | Hành vi deserialize hoặc validation |
| JSON có `totalVnd` không hợp lệ | Kiểm tra lỗi chuyển kiểu |
| Payload text nhưng đặt `contentType` không phù hợp | Kiểm tra đường xử lý converter mismatch |
| ByteArray JSON nhưng không có `contentType` | Xem hành vi mặc định của phiên bản |
| JSON có field thừa/không mong đợi | Kiểm tra chính sách deserialize |

Không khẳng định tất cả lỗi trên đều phải ném cùng một exception. Có lỗi xảy ra ở converter, có lỗi xảy ra bên trong `decideOrder`, và có lỗi được wrapper/adapter biến đổi. Trong test catalog, nên tách rõ **nguồn lỗi** thay vì assert một kiểu exception duy nhất cho mọi trường hợp.

## 11. Kiểm thử hàm reactive qua FunctionCatalog

Bean `classifyStream` có chữ ký:

~~~kotlin
Function<Flux<Order>, Flux<Decision>>
~~~

Đây là **một luồng đầu vào và một luồng đầu ra**; việc `Flux` phát nhiều phần tử không tạo thêm output binding. Nếu nguồn là publisher, hãy dùng `StepVerifier` thay vì tự gọi `subscribe()` rồi kiểm tra trong thread khác.

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

Test cuối xác nhận: khi `decideOrder` ném exception trong `map`, publisher phát `onError` và kết thúc subscription; bản ghi phía sau không tự chạy tiếp. Nếu yêu cầu nghiệp vụ là “một bản ghi lỗi không dừng luồng”, cần bọc lỗi ở **publisher con theo từng message** rồi kiểm thử chính sách đó.

### 11.1. Reactive test không chứng minh broker có backpressure

Kiểm thử `StepVerifier` của một `Flux.just(...)` là kiểm thử **Reactor và catalog**. Nó không chứng minh:

- Kafka/Rabbit binder đã được cấu hình.
- Có backpressure xuyên suốt từ broker đến logic.
- Bản ghi đã được acknowledgment hay commit offset.
- Retry, DLQ, partition và ordering ngoài hệ thống hoạt động.

Đó là trách nhiệm của test Spring Cloud Stream/binder. Trong Spring Cloud Stream, reactive function thường được gọi một lần để dựng pipeline; error handler của imperative message handler không mặc nhiên áp dụng trên từng phần tử bên trong `Flux`.

## 12. Kiểm thử theo tên, theo definition và lọc bean

### 12.1. Tên bean mặc định và tên tự chỉ định

~~~kotlin
@Bean("externalNormalize")
fun normalize(): (String) -> String = { it.trim().uppercase() }
~~~

Với cách đặt tên này, test catalog phải lookup `externalNormalize`. Tra cứu theo tên method `normalize` không nhất thiết tìm thấy, đặc biệt khi đã tắt fallback:

~~~kotlin
val fn = requireNotNull(
    catalog.lookup<Function<String, String>>("externalNormalize")
)
~~~

### 12.2. Kiểm thử nhiều function trong cùng context

Nếu ứng dụng có nhiều functional bean, `spring.cloud.function.definition` giúp adapter chọn đúng hàm. Tuy nhiên, **một unit/catalog test có thể tra cứu từng bean độc lập** mà không cần bind chúng ra ngoài.

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrder
~~~

Ví dụ YAML này chỉ có tác dụng khi adapter/framework sử dụng `definition`. Nó **không** có nghĩa catalog chỉ chứa một bean hay mọi `lookup` sẽ tự chuyển sang `classifyOrder`.

### 12.3. Danh sách tên có thể được khởi tạo lười

Spring Cloud Function có cơ chế **lazy registration** của functional beans. Nếu chỉ kiểm tra `catalog.getNames(...)` ở thời điểm chưa có lookup, cách và thời điểm bean được đăng ký có thể làm bạn hiểu sai kết quả.

Để test một bean cụ thể, **tra cứu đúng tên rồi kiểm thử giá trị** là tiêu chí mạnh hơn chỉ kiểm tra một danh sách tên. Có thể dùng `getNames(...)` để chẩn đoán, nhưng đừng xem nó như phép xác nhận nghiệp vụ duy nhất.

### 12.4. Bean bị loại khỏi catalog

Thuộc tính `spring.cloud.function.ineligible-definitions` cho phép loại các bean không nên xem là functional bean. Khi `lookup` thất bại dù `ApplicationContext` có bean, hãy kiểm tra:

- Bean có đúng loại `Supplier`/`Function`/`Consumer` hoặc Kotlin lambda được hỗ trợ không?
- Bean name có chính xác không?
- Bean có nằm trong tập bị loại bởi `ineligible-definitions` không?
- Kotlin runtime/type metadata và phiên bản Spring Cloud Function có phù hợp không?

## 13. Khi nào nên dùng ApplicationContextRunner?

`@SpringBootTest` khởi tạo ứng dụng gần với runtime thật nhưng có thể chậm hoặc kéo theo nhiều auto-configuration. Khi chỉ muốn kiểm thử **một tổ hợp cấu hình**, có thể cân nhắc `ApplicationContextRunner` từ Spring Boot Test.

Tuy nhiên, `ApplicationContextRunner` **không tự mang đầy đủ Spring Cloud Function auto-configuration**. Nếu chỉ đăng ký `CatalogFunctions`, context có thể có bean Kotlin mà không có `FunctionCatalog`.

Thiết kế đúng cần nạp **các cấu hình Spring Cloud Function phù hợp** với phiên bản đang dùng và những bean liên quan, sau đó assert `FunctionCatalog` tồn tại. Vì danh sách auto-configuration và API có thể thay đổi theo phiên bản Spring Boot/SCF, không nên copy cứng một danh sách từ tutorial cũ mà bỏ qua BOM của dự án.

**Quy tắc thực hành:** bắt đầu bằng `@SpringBootTest(classes = [CatalogLessonApplication::class])` để có một baseline đáng tin cậy; chỉ tối ưu thành slice/context runner khi biết rõ những auto-configuration cần thiết.

## 14. Phân biệt catalog integration test với adapter integration test

| Cấp test | Ví dụ | Đảm bảo | Chưa đảm bảo |
| --- | --- | --- | --- |
| Unit Kotlin | `decideOrder(Order(...))` | Quy tắc nghiệp vụ | Spring context/catalog |
| Spring bean | `context.getBean("normalizeCode")` | Bean được đăng ký | Wrapper và converter của catalog |
| FunctionCatalog | `catalog.lookup("normalizeCode")` rồi `apply` | Đúng tên, wrapper, hành vi functional | HTTP route, topic, Lambda trigger |
| Catalog message conversion | Gọi `FunctionCatalog` với `Message<byte[]>`, `application/json` | Kiểu đích và converter chạy trong context | Broker/web thực tế |
| Catalog reactive | `StepVerifier` trên `Flux` từ catalog | Reactor signals và biến đổi | Backpressure và ACK của binder |
| Web adapter | HTTP request thực qua test client | URL, HTTP status, JSON/headers | Kafka/SQS delivery |
| Stream adapter | Test Binder hoặc broker integration test | Binding, serialization, destination | Serverless trigger |
| Serverless adapter | Invocation qua handler/event mẫu | Event contract, output mapping | Những trigger khác hoặc hạ tầng production |

Để **thử HTTP**, thêm adapter web phù hợp và viết test gửi request thực tới endpoint được export; đừng coi `lookup` thành công là bằng chứng route đã được expose. Để **thử messaging**, dùng Spring Cloud Stream Test Binder/broker test, gửi thông điệp đến `classifyOrder-in-0` và kiểm tra `classifyOrder-out-0`. Để **thử serverless**, gọi handler với event đúng loại trigger và xác minh response/exception của nền tảng.

## 15. Chẩn đoán khi kiểm thử FunctionCatalog thất bại

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Unit test pass, catalog lookup null | `@Bean` chưa được scan, sai tên | Kiểm tra package, `@Configuration`, bean name |
| Spring có bean nhưng catalog không nhận diện | Return type không thuộc dạng hỗ trợ hoặc thiếu Kotlin integration | Công bố `() -> O`, `(I) -> O`, `(I) -> Unit` hoặc Java SAM tường minh |
| Tra cứu tên sai vẫn trả function | Cơ chế fallback khi catalog có đúng một function | Tắt `single-function-fallback-enabled` trong negative test |
| `ClassCastException` khi gọi `apply` | Dùng generic mong đợi không khớp hợp đồng thực hoặc version không tương thích | Kiểm tra signature, lookup wrapper và BOM |
| Test composition cho kết quả khác | Đổi thứ tự `a|b` | Assert từng stage và thứ tự pipeline |
| Gọi qua `ApplicationContext` được nhưng không chuyển JSON | Bỏ qua wrapper/converter của catalog | Test `Message` qua catalog với content type |
| JSON vào được nhưng DTO bị sai/null | Missing fields, Jackson Kotlin module, default/nullable không phù hợp | Kiểm tra schema, converter và type metadata |
| Test Consumer pass nhưng không ghi audit | Chỉ assert consumer tồn tại, chưa kiểm side effect | Inject test double và assert tác dụng phụ |
| Test `Flux` không chạy | Không có subscriber | Dùng `StepVerifier` hoặc adapter thực sự subscribe |
| `Flux` dừng sau một dữ liệu sai | `onError` terminal | Thiết kế xử lý lỗi từng phần tử nếu cần |
| Test catalog pass nhưng topic không có message | Chưa có binder hoặc destination sai | Viết Spring Cloud Stream adapter test riêng |
| Test catalog phụ thuộc HTTP server không cần thiết | Khởi động quá nhiều context | Dùng `WebEnvironment.NONE` khi không test web |
| Test không ổn định khi chạy song song | Singleton state bị chia sẻ | Cô lập state, reset test double, tránh parallel không kiểm soát |

### Checklist khi nhận một test lỗi

1. Đảm bảo business logic pass bằng unit test thuần trước.
2. Kiểm tra ứng dụng test đã load đúng `@SpringBootApplication`/`@Configuration`.
3. Xác nhận bean gốc tồn tại và có **tên đúng**.
4. Kiểm tra kiểu của `@Bean`: Kotlin lambda hay Java `Function`/`Supplier`/`Consumer`?
5. Tra cứu đúng tên qua `FunctionCatalog`, xác minh hành vi thay vì class wrapper.
6. Khi test JSON, kiểm tra `contentType`, target type và converter/Jackson dependency.
7. Khi test reactive, kiểm tra subscription và `onError` bằng `StepVerifier`.
8. Chỉ sau các bước trên mới kiểm tra HTTP/binder/serverless adapter.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `CatalogFunctions(AuditStore()).normalizeCode()(" a ")` chạy đúng không đủ chứng minh Spring Cloud Function hoạt động?

**Đáp án:** Đó là lời gọi Kotlin trực tiếp, chưa khởi tạo Spring context và chưa đi qua `FunctionCatalog` để kiểm tra tên bean, wrapper, conversion hay composition.

**Câu 2.** Tại sao nên dùng `catalog.lookup<Function<String,String>>("normalizeCode")` và assert kết quả, thay vì so `javaClass` của hàm trả về?

**Đáp án:** Spring Cloud Function có thể bọc bean để hỗ trợ tính năng tích hợp. Hợp đồng và hành vi quan trọng hơn class runtime cụ thể.

**Câu 3.** Có ba functional bean trong context. Nếu muốn tra cứu bean `classifyOrder`, nên dùng tên nào?

**Đáp án:** Tên bean `classifyOrder`; không dựa vào fallback một hàm duy nhất. Khi adapter chọn function để bind, cấu hình `spring.cloud.function.definition=classifyOrder`.

**Câu 4.** `lookup("normalizeCode|prefixCode")` có tự tạo hai output binding không?

**Đáp án:** Không. Composition là pipeline tuần tự, ở ví dụ này đầu ra cuối là một chuỗi `String`.

**Câu 5.** Một Kotlin consumer `(String) -> Unit` được tra cứu thành công. Test nào xác nhận nghiệp vụ?

**Đáp án:** Gọi consumer và kiểm tra **side effect** bằng mock/test double, chẳng hạn nội dung được thêm vào `AuditStore`.

**Câu 6.** Khi gửi `Message<byte[]>` chứa JSON vào hàm `Function<Order,Decision>`, vì sao cần cả generic type và `contentType`?

**Đáp án:** Generic cho biết **kiểu đích Order**, còn `contentType` cho biết định dạng JSON để converter chọn cách giải mã phù hợp.

**Câu 7.** `StepVerifier` pass với `Flux.just(...)` qua catalog có khẳng định Kafka message đã commit offset không?

**Đáp án:** Không. Đây là test Reactor/catalog; binder, broker, retry và acknowledgment phải được xác minh bằng adapter integration test.

**Câu 8.** Vì sao test một tên function không tồn tại đôi khi vẫn nhận được một function?

**Đáp án:** Khi catalog chỉ chứa một function, Spring Cloud Function có single-function fallback. Trong negative test cần tắt fallback hoặc thiết kế context có nhiều function với tên rõ ràng.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model, FunctionCatalog, Kotlin Lambda support](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Functional Bean Definitions và test qua FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — Kotlin Support](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Spring Cloud Stream Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Project Reactor — Testing với StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
