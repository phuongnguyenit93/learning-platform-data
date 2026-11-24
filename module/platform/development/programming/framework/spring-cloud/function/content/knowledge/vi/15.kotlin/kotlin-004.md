# Unit, nullability và tương tác kiểu Java

## 1. Bối cảnh: một kiểu Kotlin có thể được hiểu khác ở ranh giới Java và adapter

**Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`) tách logic nghiệp vụ khỏi cách gọi hàm: ta có thể đăng ký `Supplier`, `Function` hoặc `Consumer`, tra cứu qua `FunctionCatalog`, thực hiện composition, chuyển đổi thông điệp rồi kết nối qua HTTP, sự kiện hoặc môi trường serverless bằng adapter phù hợp.

Kotlin hỗ trợ kiểu không-null, kiểu nullable và kiểu `Unit`. Tuy nhiên, hệ sinh thái Spring Cloud Function chạy trên JVM, nơi nhiều API được khai báo bằng Java, bao gồm `java.util.function.Function`, `Consumer`, `Void` và một số giá trị có thể là `null`. **Hợp lệ trong Kotlin không luôn đồng nghĩa với việc một adapter có thể biểu diễn kết quả ấy thành HTTP response hay message trên broker.**

Ba vấn đề quan trọng nhất của bài là:

1. **`Unit` khác Java `void` và `java.lang.Void` như thế nào?**
2. **`T` và `T?` bảo vệ mã Kotlin đến đâu khi dữ liệu đến từ Java, JSON hoặc broker?**
3. **Làm thế nào để viết functional bean có hợp đồng rõ ràng, không phát nhầm `null` qua Reactor/`Message`, đồng thời giữ được khả năng tái sử dụng?**

Ví dụ xuyên suốt dùng đơn hàng, mã giảm giá và kết quả phân loại. Những cách xử lý lỗi được mô tả rõ, không giả định mọi HTTP, Spring Cloud Stream hay serverless adapter có cùng cơ chế retry và serialization.

## 2. Kotlin Unit, Java void và java.lang.Void không đồng nhất

### 2.1. Kotlin Unit là một kiểu có giá trị singleton

Trong Kotlin, hàm không trả giá trị nghiệp vụ được khai báo với `Unit`:

~~~kotlin
fun recordAudit(orderId: String): Unit {
    println("AUDIT: " + orderId)
}

val result: Unit = recordAudit("O-101")
~~~

Hàm trên có kết quả là **giá trị `Unit` duy nhất** của Kotlin, nhưng lập trình viên thường bỏ qua vì nó chỉ biểu thị thao tác đã được thực hiện. Khi không khai báo return type, một function chỉ có side effect cũng có thể được Kotlin suy ra là `Unit`:

~~~kotlin
fun recordAuditBriefly(orderId: String) {
    println("AUDIT: " + orderId)
}
~~~

**Điểm then chốt:** `Unit` không phải `null`; cũng không phải một payload nghiệp vụ cần phát đi.

### 2.2. Java void là kiểu trả về đặc biệt của phương thức

Java sử dụng `void` khi một phương thức không trả giá trị:

~~~java
public void recordAudit(String orderId) {
    System.out.println("AUDIT: " + orderId);
}
~~~

Khi Kotlin **gọi** một phương thức Java trả `void`, Kotlin xem kết quả là `Unit` tại call site:

~~~kotlin
// Giả sử legacyAudit là đối tượng Java có method void recordAudit(String).
val outcome: Unit = legacyAudit.recordAudit("O-101")
~~~

Đây là quy tắc **tương tác Java → Kotlin**; nó không có nghĩa Java `void` là một lớp chứa instance `Unit`.

### 2.3. java.lang.Void là một lớp tham chiếu, không phải void

`java.lang.Void` là lớp Java đặc biệt, thường xuất hiện như **generic type argument** khi API cần biểu diễn “không có kết quả”. Nó không có instance thông thường để trả về.

~~~java
// Một Java Function vẫn có kiểu trả về R, dù R là Void.
Function<String, Void> auditThenReturnNull = value -> {
    System.out.println(value);
    return null;
};

// Java Consumer không có giá trị trả về ở hợp đồng.
Consumer<String> audit = value -> System.out.println(value);
~~~

Trong Kotlin, `Void?` có thể biểu diễn trường hợp kết quả Java `Void` là `null`:

~~~kotlin
import java.util.function.Function

val legacy: Function<String, Void?> = Function { value ->
    println("AUDIT: " + value)
    null
}
~~~

Đây là minh họa tương tác với một API Java đã chọn `Void`. **Không** nên dùng `Function<I, Void?>` để thay cho `Consumer<I>` trong một bean mới nếu nghiệp vụ thực sự chỉ có side effect: cơ chế nhận diện và adapter có thể xử lý một `Function` có kết quả nullable khác một `Consumer`.

| Khái niệm | Ý nghĩa thực tế | Nên dùng khi |
| --- | --- | --- |
| Kotlin `Unit` | Kiểu kết quả của thao tác không trả dữ liệu nghiệp vụ | Kotlin function type `(I) -> Unit` |
| Java `void` | Phương thức Java không có return value | Method `Consumer.accept(...)`, API imperative |
| Java `Void` | Reference type không có instance thông thường | API/generic Java yêu cầu kiểu `Void` |
| Kotlin `Void?` | Thường chỉ biểu diễn `null` cho kết quả `Void` từ Java | Tích hợp Java legacy, có giải thích rõ |
| Kotlin `Nothing` | Kiểu của biểu thức không bao giờ hoàn tất bình thường | `throw`, hàm luôn ném exception; **không** thay thế `Unit` |

## 3. Từ (I) -> Unit sang Consumer của Spring Cloud Function

Spring Cloud Function hỗ trợ nhận diện Kotlin lambda đã đăng ký thành Spring bean. Chữ ký Kotlin `(I) -> Unit` tương ứng với mô hình **`Consumer<I>`** của Java, trong khi `(I) -> O` tương ứng **`Function<I, O>`**.

~~~kotlin
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@Configuration
class AuditFunctions {

    @Bean
    fun auditOrder(): (String) -> Unit = { orderId ->
        println("Đã ghi nhận đơn hàng: " + orderId)
    }
}
~~~

Bean `auditOrder` có hợp đồng **một đầu vào, không trả payload nghiệp vụ**. Khi Spring Cloud Stream bind một consumer với tên này, thường sẽ có **input binding** `auditOrder-in-0` mà không có output binding suy ra từ kết quả `Unit`.

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

Cấu hình messaging yêu cầu Spring Cloud Stream và binder thích hợp. `auditOrder` vẫn có thể được gọi trực tiếp trong Kotlin; `@Bean` và `FunctionCatalog` không tự tạo broker.

### 3.1. Dùng Java Consumer trong mã Kotlin cũng hợp lệ

~~~kotlin
import java.util.function.Consumer
import org.springframework.context.annotation.Bean

// Đặt trong một lớp @Configuration.
@Bean
fun auditWithJavaSam(): Consumer<String> =
    Consumer { orderId -> println("AUDIT: " + orderId) }
~~~

Kiểu trả về lúc này chính là `java.util.function.Consumer<String>`; lambda được chuyển thành Java SAM. Nếu library khác đã làm việc với `Consumer`, cách khai báo này giúp ranh giới Java rõ ràng.

**Không nhầm**:

~~~kotlin
// Consumer: không có payload trả về.
@Bean
fun audit(): (String) -> Unit = { println(it) }

// Function: trả ra một chuỗi trạng thái nghiệp vụ.
@Bean
fun acknowledge(): (String) -> String = { "ACK:" + it }
~~~

Nếu client cần nhận trạng thái `ACK` như một message hay response, hãy khai báo kiểu đầu ra nghiệp vụ tường minh. Nếu chỉ ghi log thì `Unit` là hợp đồng đúng hơn.

### 3.2. Reactive Consumer khác imperative Consumer

~~~kotlin
import reactor.core.publisher.Flux

// Không nên sao chép máy móc nếu chưa kiểm soát subscription.
val reactiveConsumer: (Flux<String>) -> Unit = { events ->
    events.subscribe { println(it) }
}
~~~

`Consumer<Flux<T>>` hoặc Kotlin lambda tương đương nhận cả publisher và trả `Unit`/`void`, nên không có publisher kết quả để framework tự subscribe. Việc tự `subscribe()` đặt trách nhiệm quản lý vòng đời, lỗi và cancellation vào mã nghiệp vụ. Theo tài liệu Spring Cloud Function/Stream, cần thận trọng với mô hình này; nhiều trường hợp phù hợp hơn với một reactive function trả publisher có tín hiệu hoàn tất, ví dụ `Function<Flux<T>, Mono<Void>>` khi adapter hỗ trợ đúng chữ ký.

## 4. Nullability của Kotlin: String và String? mang hợp đồng khác nhau

Kotlin phân biệt rõ:

~~~kotlin
val required: String = "O-101"
val optional: String? = null

// required = null       // Lỗi biên dịch trong Kotlin thông thường.
// optional.length       // Lỗi biên dịch nếu không xử lý nullable.
val safeLength: Int = optional?.length ?: 0
~~~

| Ký hiệu | Hợp đồng | Thao tác an toàn |
| --- | --- | --- |
| `String` | Người gọi Kotlin phải cung cấp giá trị không-null | `value.length` |
| `String?` | Giá trị có thể không tồn tại | `value?.length`, `?:`, `if (value != null)` |
| `Any` | Giá trị không-null có thể thuộc nhiều kiểu | Kiểm tra/cast trước thao tác đặc thù |
| `Any?` | Giá trị bất kỳ hoặc `null` | Kiểm tra cả kiểu lẫn null |
| `List<String?>` | Danh sách có thể chứa phần tử null | `filterNotNull()` hoặc xử lý từng phần tử |
| `List<String>?` | Bản thân danh sách có thể null | `orEmpty()`, `?.` |

Hai kiểu collection ở cuối **khác nhau**: một kiểu cho phép null **bên trong** danh sách, kiểu kia cho phép **toàn bộ danh sách** null. Khi dữ liệu đến từ JSON/Java, cả hai ràng buộc có thể ảnh hưởng đến việc chuyển đổi và kiểm tra hợp lệ.

### 4.1. Cần phân biệt “vắng mặt”, “rỗng” và “không hợp lệ”

Ví dụ mã giảm giá:

~~~kotlin
data class OrderInput(
    val id: String,
    val totalVnd: Long,
    val couponCode: String?
)
~~~

`couponCode: String?` cho phép nghiệp vụ xem mã giảm giá là tùy chọn. Nhưng các tình huống có thể khác nhau:

- Trường `couponCode` có chuỗi hợp lệ như `"SAVE10"`.
- Trường có giá trị `null`.
- Trường là chuỗi rỗng `""` hoặc toàn khoảng trắng.
- Trường hoàn toàn vắng mặt trong JSON.
- Trường chứa số hoặc một object thay vì chuỗi.

Không được khẳng định các trường hợp này luôn được converter xử lý giống nhau: Jackson Kotlin module, constructor defaults, các annotation, cấu hình deserialization và validation có thể quyết định việc parse thành công hay thất bại. **Kotlin nullable type không tự thay thế hợp đồng JSON/schema hoặc Bean Validation.**

## 5. Thiết kế bean có đầu vào nullable mà vẫn trả kết quả rõ ràng

Thay vì trả `null` và để adapter tự đoán ý nghĩa, có thể trả một kiểu dữ liệu thể hiện rõ trạng thái:

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
            "id của đơn hàng không được để trống"
        }
        require(order.totalVnd >= 0L) {
            "totalVnd không được âm"
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

Đoạn trên có ba tầng trách nhiệm:

1. `OrderInput` định nghĩa hình dạng dữ liệu **sau khi deserialize thành công**.
2. `require(...)` kiểm tra các điều kiện nghiệp vụ ở runtime (giá trị `id` rỗng, `totalVnd` âm).
3. `couponCode?.trim()?.takeIf { ... }` xử lý mã tùy chọn; kết quả `Decision` luôn có cấu trúc rõ ràng.

**Chú ý:** nếu JSON thiếu trường bắt buộc hoặc không thể chuyển thành `OrderInput`, lỗi có thể xảy ra **trước** khi lambda `classifyOrder` được gọi. Việc `require` ném `IllegalArgumentException` cũng không mặc nhiên là HTTP 400 hay một dead-letter message: cách trả lỗi phụ thuộc adapter và cấu hình.

### 5.1. Một giá trị đầu ra có trạng thái rõ ràng thay vì null

Nếu cần biểu diễn chấp nhận/từ chối, có thể trả DTO với trạng thái:

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

Khi serialization thành JSON, `reason: String?` có thể được biểu diễn là `null` hoặc bỏ qua trường, tùy chính sách Jackson. Dù vậy, **bản thân kết quả `ValidationResult` không-null** và có tiêu chí đọc rõ ràng: `accepted` cho biết kết quả, `reason` chứa chi tiết khi cần.

## 6. Vì sao không nên đưa null trực tiếp vào message hoặc Flux?

Ở Kotlin thuần, một function trả nullable có thể hợp lệ:

~~~kotlin
val optionalCode: (String) -> String? = { raw ->
    raw.trim().takeIf { it.isNotEmpty() }
}
~~~

Nhưng đưa kiểu `String?` ra **biên ngoài ứng dụng** là một quyết định tích hợp. Các adapter có thể diễn giải null khác nhau: không gửi message, ném lỗi, dùng giá trị thay thế hoặc có behavior đặc thù. Không thể chỉ nhìn `(I) -> O?` mà kết luận sẽ có HTTP 204, JSON `null`, hoặc một message rỗng.

### 6.1. Spring Message<T> yêu cầu payload hợp lệ

Spring Messaging `Message<T>` chứa payload và headers. Các builder thông thường không chấp nhận payload `null`:

~~~kotlin
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

val event: Message<String> =
    MessageBuilder.withPayload("ORDER_ACCEPTED").build()

// MessageBuilder.withPayload(null) không phải cách tạo "không có sự kiện".
~~~

Thay vì tạo `Message<String?>` chứa null, nên xác định rõ việc **bỏ qua**, **đổi sang message lỗi**, hoặc **phát một payload trạng thái**. Phần messaging/binder cần có chính sách xử lý khi thiếu dữ liệu.

### 6.2. Reactor không phát null dưới dạng onNext

Trong Reactive Streams, `onNext` phải mang giá trị không-null; Project Reactor không hỗ trợ phát một phần tử null như một dữ liệu bình thường.

Nếu đầu vào tùy chọn, hãy dùng `Mono.justOrEmpty(...)` hoặc `Mono.empty()`:

~~~kotlin
import reactor.core.publisher.Mono

fun normalizeOptional(raw: String?): Mono<String> {
    val normalized: String? = raw
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

    // Có String -> một onNext; null -> onComplete, không có onNext.
    return Mono.justOrEmpty(normalized)
}
~~~

| Trường hợp | Publisher | Tín hiệu |
| --- | --- | --- |
| Có giá trị `"O-101"` | `Mono.just("O-101")` | 1 `onNext`, sau đó `onComplete` |
| Không có giá trị | `Mono.empty<String>()` | `onComplete`, không có `onNext` |
| Có biến nullable | `Mono.justOrEmpty(value)` | Có giá trị thì phát; null thì hoàn tất rỗng |
| Lỗi nghiệp vụ/parse | `Mono.error<T>(exception)` | `onError` |

**Không có phần tử không đồng nghĩa với lỗi.** Tương tự, không phải mọi giá trị null là hợp lệ để lặng lẽ bỏ qua; điều này phải tùy vào yêu cầu nghiệp vụ.

### 6.3. Với Flux, loại bản ghi sai mà không phát null

Một functional bean reactive có thể nhận chuỗi đơn hàng và chỉ phát kết quả cho dữ liệu hợp lệ:

~~~kotlin
import java.util.function.Function
import org.springframework.context.annotation.Bean
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

// Đặt trong lớp @Configuration thích hợp.
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

Với đoạn trên, dữ liệu sai bị **bỏ qua** và không tạo `onNext` kết quả. Đây chỉ là **một chính sách minh họa**, không đủ cho hệ thống cần truy vết lỗi hoặc dead-letter queue. Nếu phải phát sự kiện lỗi, hãy tạo DTO lỗi và định tuyến rõ ràng thay vì dùng null để ám chỉ trạng thái.

**Lưu ý thứ tự:** `flatMap` có thể thay đổi thứ tự phát trong các trường hợp bất đồng bộ. Khi bắt buộc giữ thứ tự, cần đánh giá `concatMap` hoặc toán tử thích hợp.

## 7. Platform types khi Kotlin gọi API Java

Kotlin cố gắng an toàn null ở compile time, nhưng rất nhiều Java API không khai báo thông tin nullable. Kiểu nhận được gọi là **platform type**, IDE có thể hiển thị dạng `String!` (ký hiệu giải thích, **không phải cú pháp kiểu Kotlin có thể viết trong source**).

Giả sử một thư viện Java cũ có:

~~~java
public final class LegacyDirectory {
    public String findCustomerName(String customerId) {
        // Có thể trả null dù chữ ký không có annotation.
        return null;
    }
}
~~~

Trong Kotlin:

~~~kotlin
val nameFromJava = directory.findCustomerName("C-101")

// Có thể biên dịch, nhưng ném lỗi runtime nếu Java trả null.
// val size = nameFromJava.length

// Ranh giới an toàn hơn: chủ động thể hiện giá trị nullable.
val safeName: String? = directory.findCustomerName("C-101")
val displayName: String = safeName?.trim() ?: "UNKNOWN"
~~~

Khi giá trị platform được ép/đưa vào biến `String` không-null, trình biên dịch Kotlin có thể thêm kiểm tra runtime và ném exception nếu Java thực tế trả `null`. Vì vậy không thể chỉ dựa vào việc code **biên dịch** mà xem nguồn dữ liệu Java là đáng tin cậy.

### 7.1. Các annotation nullability trong Java

Một số thư viện Java có `@Nullable`, `@NonNull` hoặc dùng **JSpecify**. Kotlin có thể đọc các annotation này để chuyển kiểu Java thành nullable/non-nullable cụ thể.

~~~java
import org.jspecify.annotations.Nullable;

public interface CustomerDirectory {
    @Nullable String findName(String customerId);
}
~~~

Kotlin sẽ hiểu hợp đồng nullable tương ứng khi metadata và compiler được cấu hình phù hợp:

~~~kotlin
fun label(directory: CustomerDirectory, id: String): String {
    val name: String? = directory.findName(id)
    return name?.uppercase() ?: "ANONYMOUS"
}
~~~

**Khác biệt phiên bản:** Spring Framework mới sử dụng JSpecify rộng rãi; các phiên bản cũ có thể dựa nhiều vào Spring `@Nullable`/JSR-305. Các cờ như `-Xjsr305` và `-Xjspecify-annotations` tùy compiler/phiên bản quyết định mức nghiêm ngặt. Đừng mặc định một cờ cấu hình từ tutorial cũ vẫn cần thiết cho mọi dự án Kotlin hiện nay.

## 8. Java functional interfaces và kiểu trả về nullable

Ở phía Java có các interface:

~~~java
Supplier<T>       // T get()
Function<T, R>    // R apply(T value)
Consumer<T>       // void accept(T value)
~~~

Kotlin có thể hiện thực trực tiếp bằng Java SAM:

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

**Về nullability:** Java generic `Function<T, R>` thường không mã hóa nullability nếu không có annotation. Khi Kotlin tiếp nhận một `Function<String, String>` được tạo bởi Java legacy, không nên coi giá trị trả về chắc chắn khác null chỉ vì đã chọn generic `String`. Nếu đầu ra thực tế có thể null, hãy kiểm tra nó tại ranh giới Java:

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

Đây là ví dụ **phòng vệ** khi gọi Java: `String?` ở biến cục bộ thể hiện giả định thận trọng với kết quả platform. Khi tự tạo bean Java SAM trong Kotlin, hãy chủ động giữ hợp đồng không-null hoặc thể hiện kết quả tùy chọn bằng một kiểu dữ liệu rõ ràng, rồi thử nghiệm adapter.

### 8.1. Unit không thay thế Void trong generic của Java Function

Không nên diễn giải:

~~~kotlin
val kConsumer: (String) -> Unit = { println(it) }
~~~

như thể nó là cùng một runtime interface với:

~~~kotlin
val jFunction: Function<String, Void?> = Function { value ->
    println(value)
    null
}
~~~

Chúng khác cả **interface** lẫn **cách diễn giải kết quả**. Spring Cloud Function có cơ chế nhận diện `(I) -> Unit` là consumer; ngược lại `Function<I, Void?>` về mặt Java vẫn là `Function`. Không thay đổi chữ ký chỉ để tránh lỗi generic mà không đánh giá adapter.

## 9. Message<T>, header và nullability ở biên chuyển đổi

Giả sử thông điệp mang payload `OrderInput` và header `correlationId`. Nếu header có thể thiếu, hãy xem nó là dữ liệu tùy chọn:

~~~kotlin
import org.springframework.messaging.Message
import org.springframework.messaging.support.MessageBuilder

data class AuditedDecision(
    val orderId: String,
    val category: String,
    val correlationId: String?
)

// Đặt trong một lớp @Configuration.
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

Mã trên cố ý **ghi correlation ID vào payload đầu ra** để người đọc thấy cách phân biệt giá trị tùy chọn với header. Nếu yêu cầu bảo toàn header trên đường truyền, cần xây dựng message đầu ra và **sao chép header mong muốn** một cách tường minh:

~~~kotlin
val builder = MessageBuilder.withPayload(response)
correlationId?.let { builder.setHeader("correlationId", it) }
val output: Message<AuditedDecision> = builder.build()
~~~

Đoạn bổ sung là **minh họa phần thay thế** cho dòng `MessageBuilder.withPayload(response).build()` trong hàm trước, không phải một hàm độc lập không có biến `response`. Adapter có thể thêm hoặc xử lý header riêng; không được giả định tất cả header tự động được giữ qua mọi phép biến đổi.

**Quan trọng:** `Message<OrderInput>` vẫn là **một input binding**, không phải hai binding vì có payload và headers. Nếu adapter nhận JSON rỗng/không đúng schema, converter có thể thất bại trước khi gọi hàm.

## 10. Tác động tới FunctionCatalog, composition và từng adapter

### 10.1. FunctionCatalog cần hợp đồng kiểu đủ rõ

Kotlin bean có thể được khai báo:

~~~kotlin
@Bean
fun normalizeCode(): (String) -> String =
    { raw -> raw.trim().uppercase() }
~~~

Sau khi Spring tạo bean, `FunctionCatalog` có thể tra cứu theo tên `normalizeCode` và đưa ra một function đã được chuẩn hóa/bọc. Nhờ khai báo rõ kiểu `String -> String`, converter và composition có cơ sở xác định dạng dữ liệu đi qua hàm.

Nếu dùng `(String) -> String?`, Kotlin mô tả **khả năng null** của kết quả; nhưng việc adapter thể hiện nó thành HTTP status, JSON hoặc message phải được xác minh riêng. **Không tự định nghĩa một quy ước “null = không phát” mà thiếu test tích hợp.**

### 10.2. Composition không biến Unit thành payload

Giả sử hai bean:

~~~kotlin
@Bean
fun normalize(): (String) -> String =
    { it.trim().uppercase() }

@Bean
fun auditNormalized(): (String) -> Unit =
    { println("AUDIT: " + it) }
~~~

Composition `normalize|auditNormalized` có ý nghĩa **chuỗi đầu vào → chuẩn hóa → side effect** và không có payload nghiệp vụ trả về từ consumer ở cuối. Ngược lại, không thể tự giả định composition `auditNormalized|normalize` có đầu ra String, vì phía trước không có giá trị nghiệp vụ đưa vào hàm sau.

Với các hàm có đầu ra nullable, hãy thiết kế rõ bước xử lý trường hợp vắng mặt trước khi composition; đừng dựa vào hành vi mặc định không được kiểm tra của framework.

### 10.3. HTTP, messaging và serverless không có cùng “ý nghĩa null”

| Tình huống | Điều có thể khẳng định | Điều phải xác minh theo adapter |
| --- | --- | --- |
| Kotlin consumer `(I) -> Unit` | Không có output payload nghiệp vụ từ hàm | HTTP status, acknowledgment, retry |
| Kotlin `(I) -> O?` | Hàm có thể trả nullable tại mức Kotlin | Null được serialize, bỏ qua hay báo lỗi? |
| `Function<I, O>` trả một DTO lỗi | Có một đối tượng kết quả rõ ràng | HTTP status/message destination |
| `Mono.empty()` | Publisher hoàn tất không có `onNext` | Adapter gửi thông điệp hay chỉ hoàn tất? |
| `Mono.error(...)` | Publisher phát `onError` | Retry/DLQ/HTTP error/trigger failure |
| `Message<T>` | Có payload và headers | Header nào được giữ, content type thực tế |

Một logic nghiệp vụ có thể được tái sử dụng, nhưng **hợp đồng giao tiếp** cần được thiết kế riêng cho HTTP, sự kiện hoặc serverless. Khi cần thông báo từ chối/không tìm thấy, một `sealed result`, DTO trạng thái hoặc exception có chính sách xử lý rõ ràng thường an toàn hơn một kết quả `null` mơ hồ.

## 11. Kiểm thử Kotlin: Unit, null và reactive empty

### 11.1. Unit test đối với consumer

Không nên chỉ kiểm thử consumer bằng `assertEquals(Unit, ...)` rồi coi như đã xác nhận tác dụng phụ. Hãy dùng một dependency quan sát được:

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

**Kiểm tra side effect** là mục tiêu chính; phép so sánh `Unit` chỉ giúp nhắc lại hợp đồng kiểu.

### 11.2. Kiểm thử giá trị tùy chọn

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

Test này chỉ chứng minh **ngữ nghĩa Kotlin**. Nó chưa nói HTTP sẽ trả mã trạng thái gì hoặc binder có gửi message khi kết quả null hay không.

### 11.3. Kiểm thử Reactor hoàn tất rỗng và có dữ liệu

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

`verifyComplete()` ở hai trường hợp cuối chứng minh publisher không phát phần tử, **không** chứng minh adapter đã phát HTTP 204 hoặc đã xử lý nghiệp vụ mất dữ liệu.

### 11.4. Spring context test qua FunctionCatalog

Muốn kiểm tra việc nhận diện `(I) -> Unit` đúng, cần **integration test khởi tạo Spring context**:

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

Ví dụ này giả định lớp `AuditFunctions` nằm trong application context được Spring Boot test nạp; có thể đặt `@SpringBootTest(classes = [...])` tùy cấu trúc dự án. Nó xác nhận catalog lookup thành công, không kiểm chứng binder/HTTP.

## 12. Bảng lỗi hay gặp và cách sửa

| Hiện tượng | Lý do | Cách sửa |
| --- | --- | --- |
| Viết `(I) -> Unit` nhưng mong có output response nghiệp vụ | Consumer không trả payload | Dùng `(I) -> O` và DTO kết quả tường minh |
| Khai báo `Function<I, Void?>` để mô phỏng consumer | Java `Function` khác `Consumer` | Dùng đúng `Consumer<I>` hoặc Kotlin `(I) -> Unit` |
| Gọi API Java rồi gặp NPE dù Kotlin đã biên dịch | Platform type không bảo đảm non-null | Ép boundary thành `T?`, kiểm tra và gắn nullability annotation |
| JSON thiếu trường bắt buộc làm hàm không chạy | Deserialization thất bại trước khi vào lambda | Kiểm tra schema, converter và validation |
| `MessageBuilder.withPayload(null)` thất bại | Message payload không được xây dựng bằng null | Phát DTO trạng thái hoặc không phát event theo thiết kế |
| `Mono.just(null)` gây lỗi | Reactor không cho phép `onNext(null)` | Dùng `Mono.justOrEmpty(...)`/`Mono.empty()` |
| `String?` ra HTTP/broker có hành vi lạ | Adapter có hợp đồng xử lý null riêng | Viết integration test và quyết định rõ “no result” |
| `Consumer<Flux<T>>` không xử lý sự kiện | Không ai subscribe nguồn | Thiết kế subscription/vòng đời hoặc dùng reactive function phù hợp |
| Gửi `Unit` như JSON payload và client thấy kiểu lạ | Nhầm kết quả ngôn ngữ với output nghiệp vụ | Đổi hợp đồng thành DTO, `Consumer` hoặc completion publisher |
| Lỗi type ở Java SAM | Nhầm `Void`, `Unit`, kiểu Kotlin function và Java `Function` | Ghi đầy đủ chữ ký generic, kiểm tra import |

## 13. Bài tập tự kiểm tra

**Câu 1.** `@Bean fun audit(): (OrderInput) -> Unit` nên được xem là `Function<OrderInput, Unit>` hay consumer khi Spring Cloud Function nhận diện Kotlin lambda?

**Đáp án:** Đây là chữ ký Kotlin tương ứng **`Consumer<OrderInput>`** theo mô hình Kotlin lambda support của Spring Cloud Function. `Unit` không phải payload nghiệp vụ.

**Câu 2.** `Function<String, Void?>` trả `null` có giống hệt `Consumer<String>` không?

**Đáp án:** Không. Java `Function` có hợp đồng trả về một kiểu `R`, còn `Consumer` có phương thức `void accept(T)`. Chúng có thể dẫn đến khác biệt khi framework nhận diện và xử lý output.

**Câu 3.** Java API không có annotation trả `String` nhưng thực tế trả `null`. Kotlin có thể suy thành `String!`. Lập trình viên nên làm gì?

**Đáp án:** Coi đây là platform type không bảo đảm null-safety; đưa kết quả sang `String?` rồi kiểm tra hoặc yêu cầu API Java bổ sung annotation nullability.

**Câu 4.** Trong Reactor, `Mono.justOrEmpty(null)` phát phần tử null hay chỉ hoàn tất?

**Đáp án:** Nó hoàn tất mà **không** phát `onNext`. Reactor không cho phép phần tử null.

**Câu 5.** JSON thiếu `id` của `OrderInput(val id: String, ...)` có chắc được đưa vào `classifyOrder` như chuỗi rỗng không?

**Đáp án:** Không. Converter có thể báo lỗi deserialize trước khi gọi hàm; việc có giá trị mặc định, cấu hình Jackson hay validation quyết định cách xử lý.

**Câu 6.** Khi nghiệp vụ cần phản hồi “không tìm thấy đơn”, nên ưu tiên trả `null` hay một kết quả rõ ràng?

**Đáp án:** Ưu tiên hợp đồng rõ ràng (DTO trạng thái, sealed result, exception có chính sách hoặc publisher hoàn tất rỗng khi phù hợp) để adapter diễn giải nhất quán. Không mặc định `null` sẽ luôn thành HTTP 404 hay không phát message.

**Câu 7.** Một Kotlin `(String) -> Unit` được gọi trực tiếp không lỗi. Điều đó có chứng minh `FunctionCatalog` đã đăng ký consumer chưa?

**Đáp án:** Chưa. Cần đăng ký thành Spring bean và kiểm thử `FunctionCatalog.lookup(...)` trong application context; adapter còn cần kiểm thử riêng.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model và Kotlin lambda support](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and consuming messages, reactive functions](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Kotlin — Calling Java from Kotlin: void, platform types, nullability annotations](https://kotlinlang.org/docs/java-interop.html)
- [Kotlin — Null safety](https://kotlinlang.org/docs/null-safety.html)
- [Kotlin — Java to Kotlin nullability guide](https://kotlinlang.org/docs/java-to-kotlin-nullability-guide.html)
- [Spring Boot — Kotlin Support](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Spring Framework — Kotlin Null-safety và JSpecify](https://docs.spring.io/spring-framework/reference/languages/kotlin/null-safety.html)
- [Project Reactor — Mono API, justOrEmpty/empty/error](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
