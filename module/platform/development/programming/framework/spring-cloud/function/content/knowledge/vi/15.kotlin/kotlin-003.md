# Khai báo hàm bằng @Bean với chữ ký kiểu rõ ràng

## 1. Tại sao phải công bố chữ ký của functional bean?

Trong **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), ta đóng gói logic nghiệp vụ bằng `Supplier`, `Function` và `Consumer`, sau đó tái sử dụng qua HTTP, luồng sự kiện hoặc môi trường serverless bằng các adapter phù hợp. `FunctionCatalog` giúp tra cứu hàm, chuẩn hóa cách gọi, hỗ trợ composition và chuyển đổi thông điệp theo kiểu đầu vào/đầu ra.

Kotlin cho phép viết lambda rất ngắn:

~~~kotlin
val normalize = { value: String -> value.trim().uppercase() }
~~~

Nhưng một biến chứa lambda **không tự động là Spring bean**. Ngay cả khi thêm `@Bean`, việc công bố kiểu không rõ ràng khiến hợp đồng với các adapter, người đọc code và `FunctionCatalog` khó xác minh.

Mục tiêu của bài là khai báo **`@Bean` có return type tường minh**, để:

- Biết chính xác hàm nhận kiểu `I` và trả kiểu `O` nào.
- Phân biệt `Supplier`, `Function`, `Consumer`, kể cả khi dùng Kotlin function type.
- Giữ thông tin kiểu hỗ trợ chuyển đổi JSON/message và composition.
- Đăng ký bean với đúng tên và tra cứu nó qua `FunctionCatalog`.
- Kiểm thử cả **logic Kotlin** lẫn **quá trình Spring nhận diện functional bean**.

## 2. Các chữ ký Kotlin tương ứng ba interface của Java

Spring Cloud Function hỗ trợ Kotlin lambda đã đăng ký thành Spring bean (nhờ nhận diện kiểu function của Kotlin trên classpath), bên cạnh các Java functional interface chuẩn.

| Kiểu Kotlin | Mục đích | Tương ứng Java |
| --- | --- | --- |
| `() -> O` | Tạo một `O` mà không nhận input | `Supplier<O>` |
| `(I) -> O` | Biến đổi `I` thành `O` | `Function<I, O>` |
| `(I) -> Unit` | Nhận `I` và thực hiện tác dụng phụ | `Consumer<I>` |

Ví dụ:

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

Các phương thức `@Bean` này phải được khai báo trong **lớp cấu hình Spring thực sự được nạp**. Điểm quan trọng nhất là kiểu trả về của từng phương thức:

- `newCode(): () -> String` nêu rõ bean không nhận đối số và trả `String`.
- `normalizeCode(): (String) -> String` nêu rõ kiểu input lẫn output.
- `auditCode(): (String) -> Unit` nêu rõ đây là thao tác không trả payload nghiệp vụ.

Kotlin `(String) -> String` dựa vào kiểu function của Kotlin trên JVM, không phải chính `java.util.function.Function<String, String>`. Spring Cloud Function nhận diện và chuẩn hóa những Kotlin lambda phù hợp khi chúng đã là bean. `Unit` trong Kotlin không có nghĩa phải phát một đối tượng `Unit` như payload trên output messaging.

## 3. Ví dụ hoàn chỉnh: đăng ký Supplier, Function và Consumer

Một hệ thống quản lý đơn hàng cần tạo đơn mẫu, chuẩn hóa mã đơn, phân loại đơn và ghi audit. Cách khai báo rõ kiểu trong **Kotlin/JVM**:

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

    // 0 -> 1: tương ứng Supplier<Order>.
    @Bean
    fun sampleOrder(): () -> Order = {
        Order(
            id = UUID.randomUUID().toString(),
            totalVnd = 250_000L
        )
    }

    // 1 -> 1: tương ứng Function<String, String>.
    @Bean
    fun normalizeOrderId(): (String) -> String = { rawId ->
        rawId.trim().uppercase(Locale.ROOT)
    }

    // 1 -> 1: tương ứng Function<Order, Decision>.
    @Bean
    fun classifyOrder(): (Order) -> Decision = { order ->
        Decision(
            orderId = order.id,
            category = if (order.totalVnd >= 1_000_000L)
                "PRIORITY" else "STANDARD"
        )
    }

    // 1 -> 0: tương ứng Consumer<Decision>.
    @Bean
    fun auditDecision(): (Decision) -> Unit = { decision ->
        println("Đã phân loại " + decision.orderId
                + ": " + decision.category)
    }
}
~~~

Các lớp `Order`/`Decision` là **data class**: kiểu dữ liệu nghiệp vụ không phụ thuộc HTTP hay broker. Các bean được đăng ký khi Spring khởi tạo `OrderFunctions` trong application context. Ví dụ dùng Java/Kotlin đủ mới cho `uppercase(Locale.ROOT)`; `println` chỉ minh họa, nên thay bằng logger hoặc audit service trong production.

### 3.1. Phân tích hợp đồng của từng bean

| Bean name mặc định | Kiểu bean | Input | Output |
| --- | --- | --- | --- |
| `sampleOrder` | `() -> Order` | Không có | `Order` |
| `normalizeOrderId` | `(String) -> String` | `String` | `String` |
| `classifyOrder` | `(Order) -> Decision` | `Order` | `Decision` |
| `auditDecision` | `(Decision) -> Unit` | `Decision` | Không có payload nghiệp vụ |

**Tên bean mặc định** thường lấy từ tên phương thức `@Bean`. `FunctionCatalog.lookup("classifyOrder")` tìm bean tên `classifyOrder`, không tìm bằng tên `OrderFunctions` hay kiểu trả về `Decision`.

### 3.2. Kiểu suy luận có sai không?

Đoạn sau là Kotlin hợp lệ và có thể được Spring Cloud Function nhận diện:

~~~kotlin
@Bean
fun classifyInferred() = { order: Order ->
    Decision(order.id, "STANDARD")
}
~~~

Tuy nhiên, ở ranh giới public bean, khai báo dưới dạng:

~~~kotlin
@Bean
fun classifyExplicit(): (Order) -> Decision = { order ->
    Decision(
        order.id,
        if (order.totalVnd >= 1_000_000L) "PRIORITY" else "STANDARD"
    )
}
~~~

giúp người đọc và công cụ thấy hợp đồng `(Order) -> Decision` ngay trên method, thay vì phải suy từ biểu thức. Không nên tuyên bố mọi hàm `@Bean` dùng kiểu suy luận đều thất bại; **kiểu tường minh là quy ước thiết kế tốt**, không phải lời khẳng định compiler luôn không suy được kiểu.

## 4. @Bean phải thuộc một cấu hình được Spring phát hiện

Một Kotlin lambda dù đúng generic cũng **không tự xuất hiện** trong `FunctionCatalog`. Quy trình thực tế:

~~~text
@Configuration (được Spring scan/import)
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

Nếu chỉ có:

~~~kotlin
fun uppercaseValue(value: String): String = value.uppercase()

val uppercaseLambda: (String) -> String = { it.uppercase() }
~~~

thì Spring không tự động xem hai khai báo trên là bean. Đăng ký một hàm có sẵn bằng cách tham chiếu đến nó:

~~~kotlin
@Configuration
class ReusedFunctions {

    @Bean
    fun uppercaseValueBean(): (String) -> String = ::uppercaseValue
}
~~~

Tên để tra cứu lúc này là `uppercaseValueBean`. Có thể chỉ định tên bằng `@Bean("externalUppercase")`; khi đó phải tra cứu `externalUppercase`.

**Kotlin class mặc định là `final`.** Với Spring Boot, plugin `kotlin("plugin.spring")` thường được dùng để tự mở lớp/thành viên có annotation Spring phù hợp, phục vụ cơ chế proxy của Spring. Nó **không thay thế** việc khai báo `@Bean` và không tự biến mọi top-level function thành Spring bean.

## 5. Java functional interface trong Kotlin: lựa chọn tường minh khác

Trong cùng dự án Kotlin, có thể khai báo bean trả trực tiếp `Supplier`, `Function`, `Consumer` của Java:

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

| Khía cạnh | Kotlin function type | Java SAM interface viết bằng Kotlin |
| --- | --- | --- |
| Return type của bean | `(String) -> String` | `Function<String, String>` |
| Kiểu JVM gốc | Kotlin `Function1` | Java `Function` |
| Cú pháp lambda | `{ value -> ... }` | `Function { value -> ... }` |
| Cách SCF hỗ trợ | Nhận diện và chuẩn hóa Kotlin lambda | Hỗ trợ trực tiếp từ mô hình Java |
| Thường chọn khi | Ưu tiên Kotlin idiomatic | Cần rõ Java API/SAM type |

Đừng hiểu hai cách là phải khai báo **hai bean cho cùng một nhiệm vụ**. Chọn một hợp đồng public nhất quán và kiểm thử tương ứng.

## 6. Thông tin generic giúp chuyển đổi payload

Chữ ký `(Order) -> Decision` nói rằng hàm nhận một `Order` và trả một `Decision`. Nếu adapter nhận JSON:

~~~json
{
  "id": "O-101",
  "totalVnd": 1500000
}
~~~

thì khi converter được cấu hình phù hợp, kết quả nghiệp vụ có thể được serialize thành:

~~~json
{
  "orderId": "O-101",
  "category": "PRIORITY"
}
~~~

Để chuyển dữ liệu từ JSON thành Kotlin `data class` cần dependency JSON/Kotlin module thích hợp với phiên bản Spring Boot/Jackson đang dùng, và payload phải đúng schema. **Chữ ký rõ ràng không thay thế validation**: ví dụ một request không có `totalVnd` cần được xử lý lỗi theo chính sách của ứng dụng.

### 6.1. Tránh Any khi đã biết kiểu nghiệp vụ

~~~kotlin
// Kiểu quá rộng nếu thực chất chỉ xử lý Order.
@Bean
fun identityUnclear(): (Any) -> Any = { it }

// Công bố hợp đồng cụ thể.
@Bean
fun orderSummary(): (Order) -> String = { order ->
    order.id + ":" + order.totalVnd
}
~~~

`(Any) -> Any` đôi khi là chủ đích, nhưng nếu adapter phải tạo `Order` từ JSON, generic `Any` không truyền đạt đích chuyển đổi. Java/Kotlin trên JVM có **type erasure**; việc lưu lambda dưới kiểu quá rộng có thể làm mất metadata cần thiết ở ranh giới framework.

Với `@Bean`, nên công bố đủ kiểu, đặc biệt khi có generic lồng nhau. Nếu đăng ký hàm thủ công không qua method metadata, có thể cần `FunctionRegistration` để cung cấp thông tin kiểu. Không tự suy rằng một lambda object luôn mang đầy đủ `I/O` tại runtime.

### 6.2. Collection không phải nhiều output

~~~kotlin
data class OrderWithItems(
    val id: String,
    val skus: List<String>
)

@Bean
fun extractSkus(): (OrderWithItems) -> List<String> =
    { order -> order.skus }
~~~

Một bean trả `List<String>` vẫn là **một function có một giá trị trả về**. Số phần tử trong list không phải số output binding. Khi đi qua HTTP, adapter có thể serialize list thành JSON array; Spring Cloud Stream có những trường hợp xử lý batch/message list riêng, nhưng không vì thế mà tạo ra nhiều destination tự động.

## 7. Khai báo Message<T> khi cần header

Nếu cần `correlationId` hoặc thông tin trace, có thể công bố message type rõ ràng:

~~~kotlin
import org.springframework.context.annotation.Bean
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

// Đặt @Bean này trong một lớp @Configuration.
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

`Message<Order>` có **payload Order cùng headers**, không phải hai input binding. Code chủ động giữ header `correlationId` trong message kết quả. Khi đổi payload, không được giả định tất cả headers tự được sao chép giữa mọi adapter/converter.

Khi không cần header, chữ ký `(Order) -> Decision` thường đơn giản hơn. Hãy chọn kiểu đầu vào theo **thông tin nghiệp vụ thực sự cần**.

## 8. Chữ ký reactive phải nêu rõ cả kiểu publisher

Spring Cloud Function còn hỗ trợ Project Reactor `Flux`/`Mono`. Trong Kotlin có thể khai báo:

~~~kotlin
import org.springframework.context.annotation.Bean
import reactor.core.publisher.Flux

// Đặt @Bean này trong một lớp @Configuration.
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

Hàm này có **một luồng vào, một luồng ra**. `Flux<Decision>` có thể phát nhiều bản ghi nhưng vẫn là một output binding logic nếu dùng Spring Cloud Stream.

**Khác biệt vòng đời:** reactive function thường thiết lập pipeline lúc được gọi; các phần tử chạy sau khi có subscription. Không mặc nhiên áp dụng toàn bộ cơ chế retry/error handler imperative cho từng phần tử trong `Flux`.

### 8.1. Nhiều cổng cần kiểu TupleN<Flux<...>>

Nếu cần chia một nguồn thành hai cổng khi dùng Spring Cloud Stream, khai báo hợp đồng rõ ràng:

~~~kotlin
import java.util.function.Function
import reactor.core.publisher.Flux
import reactor.util.function.Tuple2
import reactor.util.function.Tuples

// Đặt @Bean này trong một lớp @Configuration.
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

Ví dụ cố ý dùng **Java `Function` với generic công bố đầy đủ** cho hợp đồng nhiều cổng: một input binding và hai output binding khi adapter hỗ trợ function arity reactive. `getT1()` tương ứng output 0, `getT2()` tương ứng output 1.

`autoConnect(2)` giả định **cả hai output có subscriber**; nếu chỉ một output được subscribe, nguồn có thể không kết nối. Thiết kế thực tế cần kiểm tra subscription, backpressure và lỗi của từng nhánh.

**Không nhầm:** `Flux<Tuple2<A, B>>` là một luồng phát các cặp; `Tuple2<Flux<A>, Flux<B>>` là hai luồng độc lập. Và HTTP/serverless không tự tạo hai endpoint hay hai response chỉ vì chữ ký bean trả tuple.

## 9. Chọn hàm và cấu hình adapter

Với nhiều bean trong application context, nên chỉ định tên cần dùng:

~~~yaml
spring:
  cloud:
    function:
      definition: classifyOrder
~~~

Ví dụ khi tích hợp **Spring Cloud Stream**:

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

`-in-0` và `-out-0` là tên binding của Spring Cloud Stream, không phải tên biến Kotlin. Cần có Spring Cloud Stream và binder thích hợp; một `@Bean` đơn thuần **không tạo message broker/topic**.

### Composition chỉ ghép các hàm tương thích

~~~kotlin
@Bean
fun cleanCode(): (String) -> String =
    { code -> code.trim().uppercase() }

@Bean
fun appendReady(): (String) -> String =
    { code -> code + "-READY" }
~~~

Hai bean trên có thể ghép:

~~~properties
spring.cloud.function.definition=cleanCode|appendReady
~~~

Giá trị đầu ra `String` của `cleanCode` phù hợp với đầu vào `String` của `appendReady`. Đây là **ghép tuần tự** chứ không phải tự động chia dữ liệu sang nhiều destination. Nếu ghép `(Order) -> Decision` với `(String) -> String`, cần chuyển đổi hợp đồng rõ ràng; không nên dựa vào việc hai bean đều có chữ `Function`.

## 10. Xác minh bằng unit test và FunctionCatalog

Để biết logic hoạt động, gọi lambda trực tiếp. Để biết framework nhận diện bean, khởi tạo Spring context và tra cứu bằng `FunctionCatalog`.

### 10.1. Unit test trực tiếp

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

Unit test này kiểm tra quy tắc phân loại và giá trị biên, **chưa** chứng minh Spring đã tạo functional bean.

### 10.2. Spring context test cho FunctionCatalog

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
        ) { "Không tìm thấy classifyOrder trong FunctionCatalog" }

        val result = function.apply(Order("O-103", 1_500_000L))

        assertEquals(
            Decision("O-103", "PRIORITY"), result
        )
    }
}
~~~

Test này yêu cầu dependency `spring-cloud-function-context` và Spring Boot Test phù hợp. Nó xác minh **bean được đăng ký và có thể tra cứu** qua catalog. `lookup` có thể trả về wrapper tích hợp chuyển đổi/composition, vì vậy không cần và không nên so class runtime của kết quả tra cứu với lambda gốc.

Muốn kiểm tra JSON HTTP hoặc topic messaging, cần thêm **adapter integration test**; unit/context test chưa xác minh serializer, headers, destination và trigger bên ngoài.

## 11. Lỗi thường gặp khi khai báo @Bean Kotlin

| Hiện tượng | Nguyên nhân cần xem | Cách kiểm tra |
| --- | --- | --- |
| Lambda gọi trực tiếp được, nhưng catalog không tìm thấy | Bean chưa đăng ký hoặc sai tên | Xác minh `@Configuration`, package scan và tên `@Bean` |
| Bean có trong Spring context nhưng không nhận diện được | Chữ ký không phù hợp, thiếu hỗ trợ Kotlin/type metadata | Công bố return type và kiểm tra dependency/framework |
| Lỗi proxy `@Configuration` trong Kotlin | Lớp mặc định `final` | Dùng `kotlin("plugin.spring")` hoặc cấu hình `open` phù hợp |
| Dữ liệu JSON không chuyển thành `Order` | Converter/Kotlin Jackson module thiếu hoặc schema sai | Kiểm tra payload, `content-type` và kiểu input |
| Chữ ký `(Any) -> Any` gây chuyển đổi khó lường | Generic quá rộng | Khai báo `(Order) -> Decision` |
| Adapter bind nhầm bean khi có nhiều hàm | Chưa chọn `definition` | Đặt `spring.cloud.function.definition` rõ ràng |
| Coi `Unit` là một output event bắt buộc | Nhầm consumer với function | Dùng `(I) -> Unit` cho tác dụng phụ |
| Hiểu `List<O>` là nhiều output binding | Nhầm giá trị Collection với arity | Xem hợp đồng function và adapter |
| `suspend`/`Flow` bị xem như `Function`/`Flux` | Khác mô hình thực thi/coroutine | Dùng bridge/adapter được hỗ trợ, không suy diễn tự động |
| Catalog test qua, nhưng broker không nhận message | Sai binding/binder/destination | Viết integration test với adapter thực tế |

### Nullability không đồng nghĩa response trống được hỗ trợ mọi nơi

~~~kotlin
@Bean
fun lookupCategory(): (String) -> String? = { id ->
    if (id.isBlank()) null else "STANDARD"
}
~~~

Chữ ký Kotlin này có thể biên dịch, nhưng `null` không mặc nhiên là message payload hợp lệ hoặc HTTP response giống nhau với mọi adapter. Với nghiệp vụ thật, nên quy định rõ chính sách “không có kết quả”: kiểu kết quả tường minh, lỗi có cấu trúc hoặc một luồng không phát phần tử tùy hợp đồng.

## 12. Bài tập tự kiểm tra

**Câu 1.** Hàm sau có tên bean mặc định, kiểu đầu vào và kiểu đầu ra nào?

~~~kotlin
@Bean
fun parseCode(): (String) -> Long = { it.toLong() }
~~~

**Đáp án:** Bean `parseCode`, input `String`, output `Long`; tương ứng `Function<String, Long>`.

**Câu 2.** `@Bean fun inferred() = { value: String -> value.uppercase() }` có nhất thiết không được Spring Cloud Function nhận diện không?

**Đáp án:** Không nên khẳng định như vậy. Kotlin có thể suy kiểu function phù hợp. Dù vậy, `fun inferred(): (String) -> String` làm rõ và ổn định hợp đồng tại ranh giới bean.

**Câu 3.** `@Bean fun audit(): (Order) -> Unit` có phải output `Unit` cần được gửi thành message?

**Đáp án:** Không. Đây là consumer tương ứng `Consumer<Order>`, không trả payload nghiệp vụ.

**Câu 4.** Tại sao `(Order) -> Decision` hỗ trợ conversion tốt hơn `(Any) -> Any` khi nhận JSON đơn hàng?

**Đáp án:** Nó cho biết kiểu đích cụ thể để framework chọn converter, đồng thời giúp kiểm tra hợp đồng của dữ liệu vào/ra.

**Câu 5.** Chỉ gọi `OrderFunctions().classifyOrder()` trong unit test có đủ chứng minh `FunctionCatalog` tìm thấy bean không?

**Đáp án:** Chưa. Cần khởi tạo Spring application context, gọi `FunctionCatalog.lookup("classifyOrder")` và kiểm tra kết quả.

**Câu 6.** `@Bean fun extractSkus(): (OrderWithItems) -> List<String>` có tạo từng ấy output binding theo số SKU không?

**Đáp án:** Không. Một `List` chứa nhiều phần tử vẫn là **một giá trị trả về**. Adapter quyết định serialize/truyền kết quả theo hợp đồng riêng.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model, Kotlin lambda support và FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Boot — Kotlin Support, Kotlin runtime và reflection](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Framework — Khai báo @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Kotlin — Spring compiler plugin](https://kotlinlang.org/docs/kotlin-spring-plugin.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
