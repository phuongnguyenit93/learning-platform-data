# Kiểu generic, POJO Kotlin và chuyển đổi JSON

## 1. Tại sao kiểu dữ liệu lại quan trọng với Spring Cloud Function?

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), logic nghiệp vụ được đăng ký thành `Supplier`, `Function` hoặc `Consumer` để tái sử dụng độc lập với giao thức. `FunctionCatalog` nhận diện và chuẩn hóa các bean, hỗ trợ composition, chuyển đổi thông điệp và cho phép adapter phù hợp đưa hàm ra HTTP, hệ thống sự kiện hoặc môi trường serverless.

Hầu hết dữ liệu đi qua ranh giới hệ thống không tồn tại sẵn dưới dạng một đối tượng Kotlin. HTTP và broker thường truyền **JSON text** hoặc **byte[]**, trong khi hàm nghiệp vụ lại cần kiểu cụ thể như `OrderRequest`. Khi có generic, chẳng hạn `List<OrderLine>` hay `Envelope<OrderRequest>`, câu hỏi “đầu vào là kiểu gì?” càng quan trọng.

~~~text
HTTP / message broker / serverless event
         |
         v
  JSON / byte[] / String
         |
         | content-type + kiểu đích của functional bean
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
  JSON / message / response (theo adapter)
~~~

Bài này làm rõ bốn vấn đề thường bị trộn lẫn:

1. **POJO Kotlin**: tại sao `data class` có primary constructor khác JavaBean thông thường, và cần gì để deserialize?
2. **Generic type**: tại sao `List<OrderLine>`, `List<Map<String, Any>>` và `Envelope<OrderRequest>` không thể thay thế tùy tiện?
3. **Content type**: `application/json` chỉ mô tả định dạng, không tự chỉ ra kiểu lớp Java/Kotlin cần tạo.
4. **Ranh giới adapter**: một bean Kotlin có thể dùng lại qua HTTP/messaging/serverless, nhưng việc serialize, kiểm tra dữ liệu và xử lý lỗi phải phù hợp từng môi trường.

## 2. POJO Kotlin là gì và khác JavaBean truyền thống ở đâu?

*Plain Old Java Object* (POJO) trong ngữ cảnh Spring Cloud Function đơn giản là một lớp dữ liệu nghiệp vụ không cần kế thừa một lớp framework hay implement interface đặc biệt. Trong Kotlin, `data class` là lựa chọn rất phổ biến:

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

`data class` tạo ra các chức năng hữu ích như `equals`, `hashCode`, `toString`, `copy` và `componentN`. Việc sử dụng `val` giúp đối tượng sau khi tạo ít bị thay đổi bất ngờ. Tuy nhiên:

- Nó **không tự đảm bảo** input JSON hợp lệ.
- Nó **không tự tạo** HTTP endpoint hay binding trên broker.
- Nó **không bắt buộc có no-argument constructor**; một JSON mapper cần nhận diện primary constructor và các tham số.
- Nó **không tự biến** `List<OrderLine>` thành nhiều cổng đầu ra.

Ví dụ JSON tương ứng:

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

Ở đây, `lines` là **một thuộc tính chứa danh sách các object**, không phải nhiều message. Khi deserialize thành công, mỗi phần tử trong danh sách có kiểu `OrderLine`, nhờ đó code có thể đọc `line.quantity` mà không ép từ `Map` hay `Any`.

### 2.1. Khi nào dùng data class, class hoặc value class?

| Kiểu Kotlin | Mục đích điển hình | Lưu ý ở ranh giới JSON |
| --- | --- | --- |
| `data class` | DTO đầu vào/đầu ra với các thuộc tính rõ ràng | Cần mapper hỗ trợ constructor/nullability Kotlin |
| `class` thông thường | Đối tượng có quy tắc/hành vi riêng | Kiểm tra constructor, getter và annotation của JSON mapper |
| `enum class` | Một tập giá trị hữu hạn | Phải kiểm soát chuỗi không nhận diện được từ bên ngoài |
| `sealed class/interface` | Nhiều dạng kết quả có cấu trúc khác nhau | Polymorphic JSON thường cần metadata/annotation cấu hình riêng |
| `@JvmInline value class` | Bao một giá trị để tăng an toàn kiểu | Mức hỗ trợ Jackson và format phụ thuộc phiên bản; cần kiểm thử |

Trong những bài thực hành nhập môn, **`data class` với các thuộc tính kiểu cụ thể** thường dễ tích hợp hơn việc bắt đầu từ polymorphic hoặc value class phức tạp.

## 3. Dependency: Kotlin runtime, Jackson Kotlin module và Spring Cloud Function

Một dự án Kotlin/Spring Cloud Function cần phân biệt dependency **nhận diện hàm** với dependency **chuyển đổi JSON**:

| Thành phần | Vai trò |
| --- | --- |
| `kotlin-stdlib` | Runtime của Kotlin và các function types |
| `kotlin-reflect` | Reflection và metadata Kotlin để các thư viện tích hợp suy ra thông tin kiểu |
| `kotlin("plugin.spring")` | Mở các lớp/thành viên Spring-annotated phù hợp cho proxy; là compiler plugin |
| `spring-cloud-function-context` | `FunctionCatalog` và cơ chế functional bean |
| Jackson Kotlin module | Hỗ trợ primary constructor, default parameters, nullable property và cấu trúc Kotlin trong JSON mapping |
| Spring Cloud Function web adapter | Export function qua HTTP khi cần |
| Spring Cloud Stream và binder | Gắn input/output binding vào broker khi cần |

**Không phải thêm Jackson Kotlin module chỉ để viết Kotlin lambda `(String) -> String`.** Module JSON cần khi ứng dụng thực sự serialize/deserialize dữ liệu Kotlin có cấu trúc.

### 3.1. Ví dụ dependency trong Gradle Kotlin DSL

Đoạn sau minh họa các dependency liên quan. Dự án thực tế cần quản lý **phiên bản plugin và Spring Boot/Spring Cloud** qua plugin/BOM tương thích:

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

Đây **không phải** `build.gradle.kts` hoàn chỉnh; `kotlin-stdlib` có thể đã được Kotlin Gradle plugin thêm tự động. Nếu cần HTTP hoặc messaging, bổ sung starter/adapter và binder tương ứng với phiên bản đang dùng.

**Chú ý Jackson 2 và Jackson 3:**

~~~kotlin
// Với dự án Spring Boot 3.x dùng Jackson 2:
// implementation("com.fasterxml.jackson.module:jackson-module-kotlin")

// Với dự án Spring Boot 4.x dùng Jackson 3:
// implementation("tools.jackson.module:jackson-module-kotlin")
~~~

Chọn **một dòng theo thế hệ Jackson thực tế**, không thêm cả hai chỉ để “đủ thư viện”. Tài liệu Spring Boot 4.x hiện xem Jackson 3 là mặc định/ưu tiên và có hỗ trợ Jackson 2 cho nhu cầu chuyển đổi. Kotlin module phù hợp thường được Boot đăng ký tự động khi có trên classpath. Các package/import của Jackson 2 và 3 cũng **khác nhau**.

Ví dụ JSON mapper trong phần kiểm thử dưới đây **ghi rõ dùng Jackson 2/Spring Boot 3.x**; không sao chép nguyên import đó sang Jackson 3 mà bỏ qua khác biệt API.

## 4. Khai báo functional bean với generic kiểu cụ thể

Logic nghiệp vụ nên nhận dữ liệu đã được deserialize thành `OrderRequest`, thay vì tự parse chuỗi JSON ở từng hàm:

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
    require(order.orderId.isNotBlank()) { "orderId không được rỗng" }
    require(order.amountVnd >= 0) { "amountVnd không được âm" }
    require(order.lines.all { it.sku.isNotBlank() && it.quantity > 0 }) {
        "Mỗi dòng phải có SKU và quantity > 0"
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

Điểm quan trọng:

1. `Function<OrderRequest, OrderDecision>` thể hiện kiểu **cụ thể** ở cả hai đầu.
2. `OrderRequest.lines` giữ kiểu `List<OrderLine>`, không bị làm phẳng thành `List<Any>`.
3. Hàm `decideOrder` **thuần nghiệp vụ**: không phụ thuộc HTTP headers, message broker hoặc định dạng JSON.
4. Các quy tắc `require` chạy **sau khi** dữ liệu đã được tạo thành `OrderRequest`. Nếu JSON không thể deserialize, lambda có thể chưa được gọi.

Tương tự, có thể dùng **Kotlin function type**:

~~~kotlin
@Bean
fun classifyOrderKotlin(): (OrderRequest) -> OrderDecision = ::decideOrder
~~~

Spring Cloud Function có hỗ trợ nhận diện Kotlin lambda đã đăng ký thành bean. Hai cách khai báo đều có giá trị, nhưng nếu đặt **cả hai** trong cùng ứng dụng và đều được adapter bind, cần chọn rõ hàm bằng `spring.cloud.function.definition`. Ví dụ tiếp theo sử dụng **một bean** mang tên `classifyOrder`.

### 4.1. Tránh khai báo kiểu quá rộng ở ranh giới JSON

~~~kotlin
// Khai báo chung chung: framework khó suy ra kiểu DTO đích.
val unclear: Function<Any, Any> = Function { it }

// Công bố hợp đồng chính xác.
val typed: Function<OrderRequest, OrderDecision> =
    Function { decideOrder(it) }
~~~

Khi nhận byte[]/JSON, converter cần biết **đối tượng đích** là `OrderRequest` chứ không chỉ là `Any`. Chữ ký của bean là một nguồn metadata chính để `FunctionCatalog` và adapter lựa chọn cơ chế chuyển đổi.

## 5. Kotlin generic: kiểu lồng nhau không thể bỏ qua

### 5.1. Generic của Collection trong DTO

Trong ví dụ:

~~~kotlin
val lines: List<OrderLine>
~~~

`List` chỉ là lớp container; `OrderLine` mới nói lên kiểu của **phần tử**. Nếu dùng:

~~~kotlin
val lines: List<Map<String, Any?>>
~~~

thì business logic phải truy cập `map["sku"]`, `map["quantity"]`, ép kiểu và xử lý null bằng tay. Dữ liệu có thể vượt qua tầng JSON nhưng lỗi kiểu xuất hiện muộn trong nghiệp vụ.

Đối với API ổn định, ưu tiên DTO có cấu trúc rõ thay vì `Map<String, Any?>` trừ khi dữ liệu thực sự mang schema động.

### 5.2. Type erasure trên JVM

Với Java/Kotlin generics, nhiều tham số kiểu bị xóa ở runtime (*type erasure*):

~~~kotlin
fun inspect(value: List<String>) {
    println(value.javaClass) // Không cho biết đầy đủ T = String.
}
~~~

Do đó, một JSON mapper có thể cần **type token** để phân biệt:

~~~kotlin
List<OrderLine>
List<Map<String, Any?>>
Envelope<OrderRequest>
Envelope<OrderDecision>
~~~

Nếu converter chỉ biết lớp thô `List::class.java`, các object trong JSON array có thể trở thành `Map` thay vì `OrderLine`. Nếu chỉ biết `Envelope::class.java`, trường `payload` có thể bị deserialize thành kiểu rộng/Map.

**Giải pháp:** Công bố generic chính xác trong `@Bean` và, khi tự gọi JSON mapper cho kiểu generic lồng nhau, sử dụng `TypeReference`/`JavaType` hoặc cơ chế tương đương của Jackson. Không giả định generic sẽ được giữ đầy đủ qua mọi cách wrapper, reflection hay adapter.

### 5.3. Generic wrapper Envelope<T>

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

Bean này cần nằm trong lớp `@Configuration`, cùng các kiểu DTO đã khai báo. Nó giữ `traceId` độc lập với dữ liệu nghiệp vụ.

Hợp đồng chính xác là:

~~~text
Envelope<OrderRequest>
       |
       v
   classifyEnvelope
       |
       v
Envelope<OrderDecision>
~~~

`Envelope<Any>` sẽ kém rõ ràng hơn vì converter khó biết `payload` phải trở thành `OrderRequest`. Mặc dù chữ ký `Function<Envelope<OrderRequest>, Envelope<OrderDecision>>` thể hiện đầy đủ generic, **khả năng khôi phục nested generic ở runtime vẫn phải được kiểm thử cùng phiên bản FunctionCatalog và adapter**.

## 6. Jackson Kotlin module và constructor của data class

Jackson Kotlin module hỗ trợ các điểm đặc trưng của Kotlin:

- **Primary constructor**: khởi tạo `data class` ngay cả khi không có constructor rỗng.
- **Tên tham số**: liên hệ thuộc tính JSON với constructor parameters.
- **Nullability**: kiểm tra sự tương thích của các thuộc tính không-null/nullable khi deserialize.
- **Default arguments**: dùng giá trị mặc định cho tham số bị thiếu trong những trường hợp được hỗ trợ.
- **Generic Kotlin types**: kết hợp metadata Kotlin với khả năng nhận diện generic của Jackson.

Ví dụ:

~~~kotlin
data class Customer(
    val id: String,
    val name: String = "UNKNOWN",
    val email: String? = null
)
~~~

Khi JSON chỉ chứa `{"id":"C-101"}`, mapper đã đăng ký đúng Kotlin module thường có thể dùng các giá trị mặc định `name = "UNKNOWN"` và `email = null`.

**Không được suy rằng “thuộc tính thiếu” và “thuộc tính có JSON null” là một.** Một trường xuất hiện với giá trị `null` có thể chịu quy tắc khác trường hoàn toàn vắng mặt, tùy kiểu Kotlin và cấu hình Jackson như `NullIsSameAsDefault` hoặc `@JsonSetter`.

### 6.1. Bảng hành vi null/missing cần kiểm thử

| Khai báo Kotlin | JSON nhận được | Kỳ vọng thiết kế và lưu ý |
| --- | --- | --- |
| `val id: String` | `"id": "C-101"` | Hợp lệ |
| `val id: String` | Không có `id` | Thiếu giá trị constructor bắt buộc; thường lỗi với Kotlin module |
| `val id: String` | `"id": null` | Vi phạm non-null; thường lỗi với Kotlin module |
| `val email: String? = null` | Không có `email` | Có thể dùng default `null` |
| `val email: String? = null` | `"email": null` | Nullable chấp nhận null |
| `val name: String = "UNKNOWN"` | Không có `name` | Có thể dùng giá trị mặc định |
| `val name: String = "UNKNOWN"` | `"name": null` | Không coi mặc nhiên là thiếu; phụ thuộc policy |
| `val amountVnd: Long` | `"amountVnd": null` | Cần cấu hình kiểm soát null cho kiểu số nguyên thủy |

Điểm cuối đặc biệt nguy hiểm: với các kiểu primitive JVM như `Long`/`Int`/`Boolean`, **Jackson có thể dùng giá trị mặc định JVM (0/false) cho JSON null** trong một số cấu hình, ngay cả khi Kotlin property là non-null. Khi dùng Jackson 2, nên cân nhắc `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` (hoặc thiết lập tương ứng của thế hệ Jackson đang dùng), đồng thời kiểm thử các trường hợp null và missing.

### 6.2. Default value không thay cho validation

~~~kotlin
data class OrderWithDefaults(
    val orderId: String,
    val amountVnd: Long = 0L,
    val lines: List<OrderLine> = emptyList()
)
~~~

Đây có thể là hợp đồng hợp lý cho một request tạo bản nháp, nhưng lại **nguy hiểm** nếu một request thanh toán bắt buộc phải cung cấp amount. JSON thiếu `amountVnd` có thể biến thành `0L` và đi qua xử lý như đơn hợp lệ. Hãy chỉ khai báo default khi nó mang đúng ý nghĩa nghiệp vụ.

Nếu một trường bắt buộc, hãy giữ nó bắt buộc và validation rõ ràng. Nếu cần phản hồi lỗi cho dữ liệu ngoài hệ thống, kiểm tra cả **deserialize errors** lẫn **business validation errors**.

## 7. Thử chuyển JSON thành DTO và generic collection

Ví dụ sau dành riêng cho **Jackson 2 + `jackson-module-kotlin` của Spring Boot 3.x**. Mục đích là minh họa cách test mapping rõ ràng mà **không cần HTTP server hoặc broker**:

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

Ở test thứ hai, `TypeReference<Envelope<OrderRequest>>` giữ được **kiểu cụ thể của trường payload**, thay vì chỉ truyền `Envelope::class.java`. Với Spring Boot 4.x/Jackson 3, cần dùng artifact và package API tương ứng (ví dụ `tools.jackson.*`), không tái sử dụng nguyên các import `com.fasterxml.jackson.*` phía trên.

Đây là **unit test cho JSON mapper**: nó chưa chứng minh `FunctionCatalog` chọn converter nào hoặc adapter HTTP/message nhận header ra sao.

## 8. FunctionCatalog: kiểu Java đích + contentType quyết định chuyển đổi

Spring Cloud Function có cơ chế chuyển dữ liệu từ dạng raw như JSON string hoặc byte[] thành kiểu mà hàm cần. Theo tài liệu chính thức, framework sử dụng:

1. **Kiểu tham số của function** (ví dụ `OrderRequest`).
2. **Content type** (ví dụ `application/json`).
3. **MessageConverter** hoặc **ConversionService**, tùy đầu vào là Spring `Message` hay giá trị thường.

Ví dụ luồng chuyển đổi:

~~~text
Incoming Message<byte[]>
 payload    = bytes chứa JSON OrderRequest
 contentType = application/json
        |
        v
 FunctionCatalog / adapter
   target input = OrderRequest
        |
        v
 JSON MessageConverter + mapper thích hợp
        |
        v
 Function<OrderRequest, OrderDecision>
        |
        v
 OrderDecision
~~~

**`contentType = application/json` không tự chọn lớp `OrderRequest`.** Nó chỉ chỉ ra **định dạng dữ liệu**. Kiểu đích đến từ chữ ký hàm hoặc metadata chuyển đổi được cho phép.

Nếu đầu vào ở dạng `Message`, framework thường tìm `MessageConverter` phù hợp; với đầu vào không phải `Message`, `ConversionService` có thể tham gia. Đừng tự suy tất cả adapter đều gọi trực tiếp một `ObjectMapper` duy nhất mà ứng dụng đã inject; Spring Cloud Function có lớp trừu tượng JSON mapper và converter riêng.

### 8.1. Kiểu bất định và type parameter động

Spring Cloud Function có cơ chế chỉ định kiểu qua MIME parameter như `application/json;type=...` trong một số tình huống sử dụng hàm khai báo `Object`. Đây **không phải** lý do để bỏ generic khỏi mọi function.

Việc chuyển dữ liệu theo tên lớp lấy từ bên ngoài có rủi ro an ninh. Theo tài liệu Spring Cloud Function, cơ chế dynamic type này yêu cầu các lớp được phép trong `META-INF/deserializable.types`. Với hợp đồng API thông thường, **ưu tiên typed DTO rõ ràng**, không chấp nhận tùy ý một tên class do client điều khiển.

### 8.2. Không nhầm FunctionCatalog với Jackson ObjectMapper

`FunctionCatalog` quản lý và gọi những hàm đã chuẩn hóa. Jackson chỉ là một trong các công cụ **serialize/deserialize JSON**. Khi muốn xác định lỗi:

- Nếu không `lookup` được function: xem đăng ký bean/tên function.
- Nếu gọi function với `OrderRequest` đã tạo sẵn được nhưng nhận JSON thất bại: xem converter, schema, Jackson Kotlin module và `content-type`.
- Nếu cả hai đều ổn nhưng message không đến topic: xem binding, binder và cấu hình broker.

## 9. Triển khai qua Spring Cloud Stream: input/output đều có type

Giả sử bind bean `classifyOrder` trong phần 4:

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

Sơ đồ:

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

Cấu hình này cần **Spring Cloud Stream cùng binder thích hợp** (Kafka, RabbitMQ hoặc hệ thống khác). Việc có `@Bean` không tự tạo broker. Content type có thể được chỉ định từ binding hoặc message header theo cơ chế của adapter; nếu cấu hình không tương thích dữ liệu thật, converter có thể thất bại.

### 9.1. Message<OrderRequest> giữ headers

Nếu nghiệp vụ cần trace/correlation header:

~~~kotlin
import java.util.function.Function
import org.springframework.context.annotation.Bean
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

// Đặt @Bean này trong một lớp @Configuration.
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

Chữ ký `Message<OrderRequest>` thể hiện **payload có kiểu rõ ràng cùng headers**, không làm số lượng input binding tăng lên. Ví dụ sao chép **header được chọn**; không giả định mọi header sẽ tự động được giữ nguyên sau khi đổi payload.

Khi không cần headers, `Function<OrderRequest, OrderDecision>` vẫn là hợp đồng gọn hơn.

### 9.2. List<T> và Flux<T> không tạo nhiều output binding

~~~kotlin
// Một giá trị trả về là Collection.
Function<OrderRequest, List<OrderDecision>>

// Một reactive publisher phát nhiều phần tử.
Function<reactor.core.publisher.Flux<OrderRequest>,
         reactor.core.publisher.Flux<OrderDecision>>
~~~

Cả hai chữ ký đều mô tả **một output logic**; kích thước danh sách hoặc số lần phát `onNext` không xác định số output binding. Spring Cloud Stream có cơ chế batch producer riêng cho một số chữ ký `List<Message<T>>`, nhưng nhiều message trên một binding vẫn **không** đồng nghĩa nhiều topic.

Nếu muốn hai output binding reactive độc lập, mô hình arity của Spring Cloud Function sử dụng một cấu trúc như `Tuple2<Flux<A>, Flux<B>>` và adapter hỗ trợ, không phải `List<Output>`.

## 10. Đổi tên trường JSON, trường tùy chọn và validation

### 10.1. Khi tên JSON khác tên property Kotlin

Giả sử client gửi `order_id`, trong Kotlin muốn giữ `orderId`. Với **Jackson 2**, một lựa chọn là dùng annotation ở constructor parameter:

~~~kotlin
import com.fasterxml.jackson.annotation.JsonProperty

data class ExternalOrder(
    @param:JsonProperty("order_id")
    val orderId: String,

    @param:JsonProperty("amount_vnd")
    val amountVnd: Long
)
~~~

Kotlin có nhiều annotation use-site target (`@param:`, `@field:`, `@get:`). Annotation trên constructor parameter phù hợp với việc Jackson phải tìm đúng tên tham số khi khởi tạo một `data class` không có setter. **Khi migrate Jackson 3**, sử dụng annotation/package tương ứng và kiểm thử đầu vào/đầu ra: một annotation có thể không tự đổi tên ở cả serialization và deserialization như mong muốn. Nếu cần cùng tên cho cả hai chiều, hãy xác định rõ nơi đặt annotation và chính sách mapper.

### 10.2. Validation không được bật chỉ nhờ data class

Một DTO có thể dùng Bean Validation:

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

Các annotation này cần dependency validation phù hợp, ví dụ Spring Boot validation starter cùng Jakarta Validation provider. **Quan trọng:** Việc đặt `@field:NotBlank` trên DTO không đảm bảo Spring Cloud Function tự động gọi Bean Validation cho mọi message. Cần cấu hình một tầng kiểm tra, controller/adapter phù hợp hoặc gọi `Validator` chủ động và quy định cách xử lý kết quả lỗi.

Kết hợp validation ở hai tầng:

- **Deserialization:** JSON có thể chuyển thành DTO đúng kiểu hay không?
- **Business validation:** DTO có thỏa điều kiện nghiệp vụ hay không?

### 10.3. Trường thời gian và tiền tệ

Với tiền VND, `Long` biểu diễn số nguyên đồng thường dễ kiểm soát hơn `Double` khi không cần phần thập phân. Nếu lưu đơn vị có phần lẻ, cân nhắc `BigDecimal` và hợp đồng làm tròn rõ ràng. Với `Instant`/`LocalDate`, cần mapper hỗ trợ kiểu ngày giờ Java và thống nhất format/time zone. Đây là các vấn đề schema/serialization, không chỉ là vấn đề cú pháp Kotlin.

## 11. Kiểm thử ba lớp: business, JSON mapper và adapter

### 11.1. Unit test nghiệp vụ không cần JSON

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

Test này chứng minh logic nghiệp vụ và kiểu dữ liệu Kotlin hoạt động, **không** kiểm tra Jackson hay Spring Cloud Function.

### 11.2. Spring context test cho FunctionCatalog

~~~kotlin
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

// Giả định application context có nạp OrderFunctions.
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

`FunctionCatalog.lookup(...)` xác nhận bean có thể được tìm và gọi dưới dạng hợp đồng Java đã chuẩn hóa. Nó **chưa chứng minh** pipeline chuyển raw JSON/byte[] qua một adapter cụ thể. Nếu cần kiểm tra conversion trong catalog, hãy gọi qua interface/message và content type tương ứng trên phiên bản đang dùng, với test chuyên biệt.

### 11.3. Integration test của adapter

| Môi trường | Nội dung kiểm tra |
| --- | --- |
| HTTP | Gửi JSON thật tới endpoint; kiểm tra status, content type, JSON output, dữ liệu thiếu/null |
| Spring Cloud Stream | Gửi message đến `classifyOrder-in-0` bằng Test Binder/broker; đọc `classifyOrder-out-0`; kiểm tra JSON/headers |
| Serverless | Dùng event mẫu của trigger; kiểm tra handler/serialization, timeout và kết quả |

Một lỗi deserialize có thể xuất hiện **trước khi** `decideOrder` chạy, nên không thể kết luận adapter hoạt động chỉ vì unit test nghiệp vụ thành công.

### 11.4. Những case JSON tối thiểu cần có

| Case | Kỳ vọng cần kiểm chứng |
| --- | --- |
| DTO đủ trường, nested `lines` | Deserialize thành `List<OrderLine>` chính xác |
| `couponCode` thiếu | Dùng mặc định nullable nếu mapper hỗ trợ đúng |
| `couponCode: null` | Dữ liệu nullable được xử lý đúng |
| `orderId` thiếu/null | Không lọt vào xử lý như một ID hợp lệ |
| `amountVnd: null` | Không âm thầm chuyển thành 0 nếu hợp đồng cấm |
| `quantity` là chuỗi không hợp lệ | Converter báo lỗi hoặc từ chối theo policy |
| JSON array thành `List<OrderRequest>` | Generic được giữ, không thành danh sách `Map` |
| `Envelope<OrderRequest>` | Trường `payload` được tạo đúng kiểu |
| Header `contentType` sai | Phát hiện converter mismatch |
| Tên JSON khác property Kotlin | Annotation/naming strategy được áp dụng đúng cả hai chiều |

## 12. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| `FunctionCatalog.lookup("classifyOrder")` trả null | Bean chưa scan hoặc tên không khớp | Kiểm tra `@Configuration`, `@Bean`, `definition` |
| JSON thành `Map` thay vì `OrderRequest` | Kiểu đích/generic bị mất | Công bố return type bean rõ ràng, dùng type token nếu parse trực tiếp |
| `data class` không deserialize được | Thiếu Jackson Kotlin module, constructor/field không tương thích | Kiểm tra dependency, schema và mapper đã được đăng ký |
| Trường không-null bị nhận null | Config nullability/primitive coercion chưa đủ chặt | Thử `FAIL_ON_NULL_FOR_PRIMITIVES` tương ứng, kiểm thử null/missing |
| List generic chứa `LinkedHashMap` | Chỉ cung cấp raw `List::class.java` | Dùng `TypeReference<List<YourDto>>` hoặc kiểu mục tiêu đầy đủ |
| Input 1 bị đọc theo kiểu input 0 | Sai thứ tự multi-input binding | Kiểm tra `TupleN<Flux<T>>` và `-in-0`/`-in-1` |
| JSON dùng `order_id` nhưng DTO dùng `orderId` | Naming strategy/annotation chưa khớp | Dùng annotation/mapping phù hợp và test serialization |
| Converter báo không hỗ trợ content type | Header/setting không đúng hoặc thiếu converter | Kiểm tra payload, `application/json` và converter đang chọn |
| Hàm xử lý đúng nhưng topic không có message | Lỗi binder/destination/producer | Kiểm tra Spring Cloud Stream binding và broker |
| Spring Boot 4 dùng import Jackson 2 | Nhầm thế hệ Jackson | Xem BOM và đổi artifact/API đúng phiên bản |
| Số phần tử Collection bị nhầm thành số output | Nhầm generic payload và function arity | Phân biệt `List<T>`, `Flux<T>` và `TupleN<Flux<...>>` |

### Checklist trước khi triển khai

1. `@Bean` có **kiểu đầu vào/đầu ra cụ thể** và tên rõ ràng.
2. DTO dùng `data class`/POJO với constructor, nullable/default hợp lý.
3. Nested collections giữ generic cụ thể, không bị thay bằng `Any` ngoài ý muốn.
4. Kotlin runtime/reflection và JSON module phù hợp với phiên bản Spring Boot/Jackson.
5. `content-type` và tên binding/destination đúng.
6. Test parse trực tiếp DTO, parse generic wrapper, missing/null, primitive coercion.
7. Test qua `FunctionCatalog` và adapter thực sự sử dụng.
8. Lỗi dữ liệu ngoài hệ thống không bị che bằng default vô tình; có chính sách log/validation/acknowledgment rõ.

## 13. Bài tập tự kiểm tra

**Câu 1.** Hai chữ ký dưới đây khác nhau ở đâu?

~~~kotlin
Function<OrderRequest, List<OrderDecision>>
Function<List<OrderRequest>, OrderDecision>
~~~

**Đáp án:** Chữ ký đầu nhận một request và trả một **giá trị List**. Chữ ký sau nhận **một danh sách request** rồi trả một decision. Cả hai đều là một input và một output logic; không có nhiều binding chỉ vì xuất hiện `List`.

**Câu 2.** Tại sao `List<OrderLine>` an toàn hơn `List<Map<String, Any?>>` khi schema đã biết?

**Đáp án:** Generic `OrderLine` cung cấp kiểu phần tử và cấu trúc dữ liệu tường minh; mapper và business logic có thể kiểm tra `sku`, `quantity` mà không ép kiểu từ `Map`.

**Câu 3.** `content-type: application/json` có đủ để converter biết phải tạo `Envelope<OrderRequest>` không?

**Đáp án:** Không. Content type chỉ cho biết định dạng. Converter còn cần **kiểu đích**, đặc biệt kiểu generic của trường `payload`.

**Câu 4.** Với `data class Customer(val id: String, val name: String = "UNKNOWN")`, việc JSON không có `name` có giống JSON đặt `"name": null` không?

**Đáp án:** Không mặc định giống nhau. Missing property có thể dùng default parameter; explicit null phụ thuộc nullability và cấu hình mapper.

**Câu 5.** Vì sao cần kiểm tra `amountVnd: null` cho một `Long` không-null?

**Đáp án:** Một số cấu hình Jackson có thể chuyển null của kiểu primitive thành giá trị JVM mặc định như 0. Cần chính sách strict null, validation và test.

**Câu 6.** Vì sao test `decideOrder(OrderRequest(...))` thành công chưa chứng minh endpoint HTTP parse được JSON?

**Đáp án:** Unit test cung cấp DTO Kotlin đã được tạo sẵn. Nó bỏ qua việc converter phải parse JSON/byte[], xử lý header/content type và kết nối qua adapter.

**Câu 7.** Trường hợp nào cần `TypeReference<Envelope<OrderRequest>>`?

**Đáp án:** Khi **tự gọi** Jackson mapper để deserialize JSON sang kiểu generic lồng nhau mà raw `Envelope::class.java` không mang đủ type information.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model: FunctionCatalog, Type conversion, Kotlin lambdas](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Boot — Kotlin support và Kotlin JSON module](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Boot — JSON mapping và Jackson 2/3](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Jackson Kotlin module — Constructor, default parameters, generic types](https://github.com/FasterXML/jackson-module-kotlin)
- [Spring Cloud Stream — Producing and consuming messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Kotlin — Generics và type erasure](https://kotlinlang.org/docs/generics.html)
- [Kotlin — Null safety](https://kotlinlang.org/docs/null-safety.html)
