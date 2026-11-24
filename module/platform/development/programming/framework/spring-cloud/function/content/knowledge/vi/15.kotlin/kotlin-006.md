# Dùng Mono hoặc Flux từ hàm Kotlin

## 1. Tại sao Spring Cloud Function kết hợp tốt với Reactor?

**Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`) cho phép tổ chức logic nghiệp vụ thành các `Supplier`, `Function` và `Consumer`. Những hàm này được `FunctionCatalog` quản lý để tra cứu, chuyển đổi thông điệp, composition và triển khai với các adapter như HTTP, Spring Cloud Stream hay môi trường serverless. Ý tưởng chính là **hợp đồng hàm không gắn chặt với cách gọi**.

Khi xử lý dữ liệu bất đồng bộ, một hàm có thể trả về **publisher** thay vì trả ngay một giá trị. Spring Cloud Function hỗ trợ hai kiểu của Project Reactor:

- `Mono<T>`: publisher phát **0 hoặc 1** giá trị `T`, sau đó hoàn tất; hoặc kết thúc bằng lỗi.
- `Flux<T>`: publisher phát **0 đến nhiều** giá trị `T`, có thể hữu hạn hoặc chạy lâu dài; hoặc kết thúc bằng lỗi.

Ví dụ trong Kotlin:

~~~kotlin
val one: Mono<String> = Mono.just("O-101")
val many: Flux<String> = Flux.just("O-101", "O-102", "O-103")
~~~

Điểm quan trọng là `Mono` và `Flux` **không phải bản thân giá trị String hoặc List**. Chúng mô tả một quá trình phát tín hiệu khi có **subscriber**.

~~~text
Kotlin function bean
      |
      v
Function<Flux<Order>, Flux<Decision>>
      |
      +---- nguồn Publisher<Order>
      |          |
      |          v
      |     map/filter/flatMap...
      |          |
      +---- đích Publisher<Decision>
                 |
          adapter subscribe
                 |
          dữ liệu mới chạy
~~~

Bài này tập trung vào: cách khai báo reactive functional bean bằng Kotlin, phân biệt `Mono`/`Flux`, xử lý null và lỗi, sự khác biệt khi gọi qua HTTP với messaging, subscription/backpressure và kiểm thử `StepVerifier`.

## 2. Mono và Flux: kiểu trả về khác với Collection

| Đặc tính | `Mono<T>` | `Flux<T>` |
| --- | --- | --- |
| Số tín hiệu `onNext` | 0 hoặc 1 | 0 đến N |
| Có thể hoàn tất không có giá trị? | Có, `Mono.empty()` | Có, `Flux.empty()` |
| Có thể chạy liên tục? | Chờ kết quả lâu nhưng tối đa 1 giá trị | Có thể vô hạn |
| Ví dụ | Tìm một đơn hàng, xác minh quyền truy cập | Dòng sự kiện đơn hàng, stream kết quả tìm kiếm |
| Toán tử điển hình | `map`, `flatMap`, `switchIfEmpty`, `then` | `map`, `filter`, `flatMap`, `concatMap`, `buffer` |
| Có phải List? | Không | Không |

Một `Mono<List<Order>>` phát **một danh sách**; một `Flux<Order>` phát **từng đối tượng `Order`**. Hai mô hình có thể chứa cùng dữ liệu nhưng khác hợp đồng:

~~~kotlin
val batch: Mono<List<String>> =
    Mono.just(listOf("A", "B", "C"))

val events: Flux<String> =
    Flux.fromIterable(listOf("A", "B", "C"))
~~~

`batch` có **một `onNext` chứa List ba phần tử**. `events` có **ba `onNext`**, mỗi lần chứa một chuỗi. Một HTTP response trả JSON array, một message mang array và ba message trên broker cũng không đồng nghĩa nhau; adapter quyết định cách xuất dữ liệu.

### 2.1. Các tín hiệu của Reactive Streams

~~~text
Mono.just("A"):       onSubscribe -> onNext("A") -> onComplete
Mono.empty():         onSubscribe -> onComplete
Mono.error(error):    onSubscribe -> onError(error)

Flux.just("A","B"):   onSubscribe -> onNext("A")
                                    -> onNext("B") -> onComplete
Flux.never():         onSubscribe -> ... không hoàn tất
~~~

`onComplete` và `onError` là các tín hiệu kết thúc **loại trừ nhau** trong một subscription. Reactor không phát phần tử `null` qua `onNext`.

## 3. Chuẩn bị dependency cho ứng dụng Kotlin

Đoạn trích `build.gradle.kts` sau nhấn mạnh các phần cần thiết, giả định dự án đã quản lý phiên bản Spring Boot, Spring Cloud Function và Kotlin bằng plugin/BOM tương thích:

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

    // reactor-core thường đến từ Spring Cloud Function/Spring stack;
    // chỉ khai báo trực tiếp khi cần kiểm soát dependency rõ ràng.
    implementation("io.projectreactor:reactor-core")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Đây không phải một build script độc lập hoàn chỉnh. `kotlin("plugin.spring")` hỗ trợ proxy các lớp Spring trong Kotlin (mặc định `final`); `kotlin-stdlib` chứa runtime Kotlin, còn `reactor-core` chứa `Mono`, `Flux` và các toán tử. Khi cần JSON của Kotlin `data class`, bổ sung Jackson Kotlin module phù hợp với phiên bản Spring Boot/Jackson; khi dùng messaging, bổ sung **Spring Cloud Stream và binder** tương ứng.

### 3.1. Reactor Kotlin Extensions là thư viện tùy chọn

Các phương thức Java của Reactor **đã dùng được trực tiếp từ Kotlin**. Nếu muốn cú pháp Kotlin ngắn hơn, Reactor cung cấp thêm module:

~~~kotlin
dependencies {
    implementation("io.projectreactor.kotlin:reactor-kotlin-extensions")
}
~~~

Ví dụ:

~~~kotlin
import reactor.core.publisher.Flux
import reactor.kotlin.core.publisher.toFlux

val withoutExtensions: Flux<Int> =
    Flux.fromIterable(listOf(1, 2, 3))

val withExtensions: Flux<Int> =
    listOf(1, 2, 3).toFlux()
~~~

`toFlux()` chỉ khả dụng khi có dependency và import extension phù hợp. Không bắt buộc cài Reactor Kotlin Extensions để khai báo `Function<Flux<I>, Flux<O>>`.

## 4. Ví dụ hoàn chỉnh: Function Kotlin với Mono và Flux

Giả sử hệ thống phân loại đơn hàng: đơn trị giá từ 1.000.000 VND trở lên là `PRIORITY`; còn lại là `STANDARD`. Quy tắc nghiệp vụ được viết tách khỏi giao thức:

~~~kotlin
package example.reactive

import java.util.function.Function
import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

data class Order(
    val id: String,
    val totalVnd: Long
)

data class Decision(
    val orderId: String,
    val category: String
)

fun decide(order: Order): Decision {
    require(order.id.isNotBlank()) { "id không được rỗng" }
    require(order.totalVnd >= 0L) { "totalVnd không được âm" }
    return Decision(
        orderId = order.id,
        category = if (order.totalVnd >= 1_000_000L)
            "PRIORITY" else "STANDARD"
    )
}

@SpringBootApplication
class ReactiveOrdersApplication

fun main(args: Array<String>) {
    runApplication<ReactiveOrdersApplication>(*args)
}

@Configuration
class ReactiveOrderFunctions {

    // Một giá trị đầu vào, một kết quả bất đồng bộ.
    @Bean
    fun classifyOne(): Function<Order, Mono<Decision>> =
        Function { order ->
            Mono.fromSupplier { decide(order) }
        }

    // Một Flux đầu vào, một Flux đầu ra: pipeline sự kiện.
    @Bean
    fun classifyStream(): Function<Flux<Order>, Flux<Decision>> =
        Function { orders ->
            orders.map { order -> decide(order) }
        }
}
~~~

`decide` là hàm Kotlin thông thường, có thể unit test riêng. Hai functional bean chỉ khác **cách biểu diễn dữ liệu đến/đi**:

| Bean | Chữ ký | Đơn vị xử lý |
| --- | --- | --- |
| `classifyOne` | `Function<Order, Mono<Decision>>` | Một `Order` được chuyển thành kết quả bất đồng bộ có tối đa một giá trị |
| `classifyStream` | `Function<Flux<Order>, Flux<Decision>>` | Một publisher đơn hàng được biến đổi thành publisher kết quả |

**Không nên giả định hai bean hoạt động tương đương với mọi adapter.** `Function<Order, Mono<Decision>>` hữu ích khi môi trường hỗ trợ reactive result cho từng invocation (chẳng hạn web adapter phù hợp); `Function<Flux<Order>, Flux<Decision>>` là mẫu thường dùng cho pipeline stream được Spring Cloud Stream bind. Mỗi adapter có hợp đồng subscription và result riêng cần kiểm tra.

### 4.1. Viết bean bằng Kotlin function type thay vì Java Function

Spring Cloud Function cũng nhận diện Kotlin lambda được đăng ký thành bean:

~~~kotlin
// Đặt phương thức bên trong lớp @Configuration được nạp.
@Bean
fun uppercaseStream(): (Flux<String>) -> Flux<String> = { input ->
    input
        .map { it.trim().uppercase() }
        .filter { it.isNotEmpty() }
}
~~~

Return type `(Flux<String>) -> Flux<String>` là một Kotlin function type, tương ứng mô hình functional bean sau khi Spring Cloud Function chuẩn hóa. Khi tích hợp API Java hoặc cần hợp đồng tường minh ở JVM, chọn `java.util.function.Function<Flux<I>, Flux<O>>` cũng hoàn toàn phù hợp.

## 5. Mono: kết quả có, không có hoặc lỗi

`Mono<T>` có ba cách kết thúc thông dụng:

~~~kotlin
import reactor.core.publisher.Mono

val found: Mono<String> = Mono.just("O-101")
val missing: Mono<String> = Mono.empty()
val failed: Mono<String> =
    Mono.error(IllegalArgumentException("ID không hợp lệ"))
~~~

### 5.1. Mono.just và Mono.fromSupplier có thời điểm tính khác nhau

~~~kotlin
val eager: Mono<Decision> =
    Mono.just(decide(Order("O-101", 500_000L)))

val lazy: Mono<Decision> =
    Mono.fromSupplier {
        decide(Order("O-101", 500_000L))
    }
~~~

`Mono.just(...)` nhận **giá trị đã được tính trước** lúc khai báo publisher; `Mono.fromSupplier { ... }` trì hoãn việc gọi supplier đến lúc có subscription. Với hàm có phép tính tốn tài nguyên hoặc có thể thất bại, thời điểm thực thi ảnh hưởng đến nơi lỗi được ném và vòng đời xử lý.

Nếu cần tạo **một publisher khác cho mỗi lần subscribe**, có thể sử dụng `Mono.defer { ... }`:

~~~kotlin
val deferred: Mono<String> = Mono.defer {
    Mono.just("READY")
}
~~~

Không phải mọi publisher đều tự động thực thi một lần duy nhất: nhiều publisher Reactor mặc định là **cold**, có thể chạy lại logic cho từng subscription. Tránh đặt side effect quan trọng trong một publisher bị subscribe lặp nếu chưa có chính sách idempotency.

### 5.2. Không phát null: dùng Mono.justOrEmpty

Kotlin cho phép chuỗi nullable `String?`, nhưng Reactor không cho phép một phần tử `null`:

~~~kotlin
fun normalizedCode(raw: String?): Mono<String> {
    val value: String? = raw
        ?.trim()
        ?.takeIf { it.isNotEmpty() }

    return Mono.justOrEmpty(value)
}
~~~

Kết quả:

- `normalizedCode("  SAVE10 ")` phát `"SAVE10"` rồi hoàn tất.
- `normalizedCode(null)` hoàn tất **không phát giá trị**.
- `normalizedCode("   ")` cũng hoàn tất rỗng vì chuỗi không có nội dung.

`Mono.empty()` nghĩa là **không có dữ liệu trong subscription**, không mặc nhiên đồng nghĩa HTTP 404, HTTP 204 hay một message lỗi. Cách adapter thể hiện việc này phải được kiểm chứng theo môi trường.

### 5.3. Tách rõ giá trị trống với lỗi

~~~kotlin
fun lookupOrderId(id: String?): Mono<String> {
    if (id == null) return Mono.empty()
    if (id.isBlank()) {
        return Mono.error(IllegalArgumentException("id không được rỗng"))
    }
    return Mono.just(id.trim())
}
~~~

Ở đây chúng ta cố ý chọn:

- Input `null`: không tìm được dữ liệu.
- Input chỉ gồm khoảng trắng: lỗi validation.
- Input khác: một kết quả.

Đó là **quy tắc của ví dụ**, không phải định nghĩa chung bắt buộc của Spring Cloud Function.

### 5.4. Mono<Void> khác Mono<Unit>

Trong Kotlin:

~~~kotlin
val hasUnitValue: Mono<Unit> = Mono.just(Unit)
val noPayload: Mono<Void> = Mono.empty()
~~~

`Mono<Unit>` ở ví dụ đầu **thực sự phát một phần tử Unit**. `Mono<Void>` thường được dùng trong API Reactor/Java để biểu diễn **completion không mang dữ liệu**.

Toán tử `then()` trên publisher tạo `Mono<Void>`, bỏ qua các phần tử nguồn và chỉ phát tín hiệu hoàn tất/lỗi:

~~~kotlin
fun auditAll(orders: Flux<Order>): Mono<Void> =
    orders
        .doOnNext { order -> println("AUDIT: " + order.id) }
        .then()
~~~

**Cảnh báo:** nếu `orders` là luồng sự kiện **không bao giờ kết thúc**, `then()` cũng không phát `onComplete` bình thường. `doOnNext` chỉ minh họa side effect, không phải một cơ chế audit bền vững; trong production cần thiết kế lưu trữ, lỗi và acknowledgment đúng với môi trường.

## 6. Flux: biến đổi dòng sự kiện trong Kotlin

`Flux<T>` thích hợp khi một hàm cần nhìn nhiều dữ liệu cùng lúc hoặc vận hành như stream processor.

~~~kotlin
val input: Flux<String> =
    Flux.just(" O-101 ", "", " O-102 ")

val output: Flux<String> = input
    .map { value -> value.trim() }
    .filter { value -> value.isNotEmpty() }
    .map { value -> value.uppercase() }
~~~

Kết quả có hai `onNext`: `"O-101"`, `"O-102"`.

### 6.1. map, filter, flatMap và concatMap

| Toán tử | Tác dụng | Khi nào chọn |
| --- | --- | --- |
| `map { }` | Đồng bộ, một phần tử thành một phần tử | Chuyển `Order` thành `Decision` |
| `filter { }` | Giữ/bỏ phần tử theo điều kiện | Chọn message phù hợp |
| `flatMap { Mono/Flux }` | Kết hợp các publisher con, có thể xử lý đồng thời | I/O bất đồng bộ, một input cho 0..N output |
| `concatMap { Mono/Flux }` | Xử lý publisher con tuần tự, bảo đảm thứ tự phát theo nguồn | Cần thứ tự nghiệp vụ |
| `flatMapSequential { }` | Cho phép subscribe đồng thời nhưng phát theo thứ tự nguồn | Cân bằng concurrency/thứ tự |
| `buffer(n)` | Gom một số phần tử thành `List<T>` | Batch processing có giới hạn |
| `take(n)` | Lấy tối đa n phần tử rồi hủy subscription | Kiểm thử, giới hạn stream |

Ví dụ một đơn hàng có nhiều SKU và muốn phát từng SKU trên cùng một `Flux`:

~~~kotlin
data class OrderWithSkus(
    val id: String,
    val skus: List<String>
)

val extractSkus: (Flux<OrderWithSkus>) -> Flux<String> = { orders ->
    orders.flatMapIterable { order ->
        order.skus.map { sku -> order.id + ":" + sku }
    }
}
~~~

Một đầu vào `OrderWithSkus` có ba SKU có thể phát **ba phần tử trên cùng một output publisher**. Nó không làm Spring Cloud Stream tự tạo ba output binding.

### 6.2. Thứ tự và đồng thời

Khi xử lý I/O bất đồng bộ, `flatMap` có thể khiến kết quả về khác thứ tự nguồn:

~~~kotlin
import java.time.Duration

val processed: Flux<String> = Flux.just("A", "B")
    .flatMap { value ->
        val wait = if (value == "A")
            Duration.ofMillis(100) else Duration.ofMillis(10)
        Mono.just(value).delayElement(wait)
    }
~~~

Trong điều kiện bình thường ví dụ này có thể phát `B` trước `A`. Nếu thứ tự là yêu cầu nghiệp vụ, dùng `concatMap` hoặc toán tử phù hợp thay vì suy rằng `flatMap` tự giữ thứ tự.

### 6.3. Cold publisher và subscription

~~~kotlin
val source = Flux.defer {
    println("Có subscriber mới")
    Flux.just("A", "B")
}
~~~

Đoạn in log trong `Flux.defer` chạy khi có subscription. Nếu subscribe hai lần, đoạn tạo publisher có thể chạy hai lần. Với một nguồn có truy vấn database hay side effect, việc subscribe lặp có thể dẫn đến tải tăng hoặc thực thi lại công việc.

Spring Cloud Function khai báo bean là cách **đăng ký hàm**; nó không có nghĩa mọi publisher do hàm tạo ra đã được subscribe. Adapter quản lý cách kết nối và tiêu thụ publisher theo hợp đồng riêng.

## 7. Spring Cloud Stream: hàm reactive được thiết lập một lần

Trong Spring Cloud Stream, có khác biệt lớn giữa:

~~~kotlin
Function<Order, Decision>

Function<Flux<Order>, Flux<Decision>>
~~~

Hàm **imperative** thường được framework gọi **cho từng message**. Hàm **reactive** thường được gọi **một lần để tạo pipeline**, sau đó các message đi qua pipeline đó.

~~~text
IMPERATIVE
  message A ---> apply(A) ---> decision A
  message B ---> apply(B) ---> decision B

REACTIVE
  input Flux  ---> apply(input Flux) ---> output Flux
                       |
           pipeline được kết nối/subscribe
                       |
             nhiều message chảy qua
~~~

Đây là lý do retry/error handling dành cho mỗi invocation của imperative function **không tự động** kiểm soát từng phần tử bên trong pipeline reactive. Framework/binder cần được đánh giá theo mô hình đã chọn.

### 7.1. application.yml cho classifyStream

Giả sử ứng dụng đã bổ sung Spring Cloud Stream và binder phù hợp, cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: classifyStream
    stream:
      bindings:
        classifyStream-in-0:
          destination: orders.created
          group: order-classifiers
          content-type: application/json
        classifyStream-out-0:
          destination: orders.classified
          content-type: application/json
~~~

Spring Cloud Stream gắn `classifyStream-in-0` vào topic/queue đầu vào và `classifyStream-out-0` vào đích đầu ra. Spring Cloud Function biết kiểu generic `Flux<Order>` và `Flux<Decision>`; `content-type` giúp xác định định dạng message.

**Không có output binding thứ hai** chỉ vì `Flux<Decision>` phát nhiều phần tử. Số cổng xác định từ chữ ký hàm; số message được phát trên cổng phụ thuộc dữ liệu.

Nếu ứng dụng có nhiều bean (như `classifyOne` và `classifyStream`), nên đặt rõ `spring.cloud.function.definition` để không bind nhầm.

### 7.2. Một Flux có backpressure đến broker không?

**Không mặc nhiên.** Reactor hỗ trợ backpressure ở tầng Reactive Streams, nhưng tác dụng xuyên suốt đến nguồn/đích phụ thuộc **binder**. Với binder thông thường không reactive, ứng dụng vẫn sử dụng được `map`, `filter`, `flatMap`... nhưng không nên khẳng định có backpressure end-to-end.

Cần kiểm tra: khả năng backpressure của binder, giới hạn bộ nhớ, độ song song, tốc độ consumer/producer, retry, DLQ và cách adapter xử lý publisher khi lỗi. Những câu hỏi này quan trọng hơn việc chỉ thấy kiểu `Flux` trong signature.

## 8. Web adapter: một response có thể mang publisher

Nếu dùng adapter web phù hợp, một bean có thể xử lý một lời gọi HTTP và trả một `Mono` phản ánh kết quả bất đồng bộ. Ví dụ `classifyOne` ở phần 4 có hợp đồng `Function<Order, Mono<Decision>>`, không phụ thuộc trực tiếp vào Spring MVC hay WebFlux trong business code.

Tuy nhiên, cần phân biệt:

| Mẫu trả về | Ý nghĩa nghiệp vụ | Điều adapter phải quyết định |
| --- | --- | --- |
| `OrderDecision` | Một DTO | JSON và mã HTTP status |
| `Mono<OrderDecision>` | Tối đa một DTO bất đồng bộ | Khi nào subscribe; serialize khi có kết quả |
| `Mono.empty<OrderDecision>()` | Hoàn tất không có dữ liệu | HTTP status/response body tùy adapter |
| `Flux<OrderDecision>` | Nhiều kết quả | Gom mảng hay streaming/SSE tùy content negotiation |
| `Mono.error(...)` | Lỗi bất đồng bộ | Ánh xạ exception sang response |

Không được suy rằng mọi adapter HTTP tự động mở một stream vô hạn hoặc hai HTTP endpoint vì một hàm trả `Flux` hay tuple các `Flux`. HTTP có mô hình request/response riêng; nếu cần API phức tạp, có thể viết Spring WebFlux controller gọi lại service/hàm nghiệp vụ.

Với serverless cũng tương tự: một invocation chịu timeout, payload và trigger contract của nền tảng; không nên trả `Flux.never()` chỉ vì Reactor cho phép publisher vô hạn.

## 9. Supplier<Flux<T>> và nguồn sự kiện

Không phải reactive bean nào cũng là `Function`. Ta có thể khai báo **Supplier** không nhận đầu vào và trả một `Flux`:

~~~kotlin
import java.time.Duration
import java.util.function.Supplier
import org.springframework.context.annotation.Bean
import reactor.core.publisher.Flux

data class Heartbeat(val sequence: Long)

// Đặt @Bean trong lớp @Configuration thích hợp.
@Bean
fun heartbeatEvents(): Supplier<Flux<Heartbeat>> =
    Supplier {
        Flux.interval(Duration.ofSeconds(1))
            .map { count -> Heartbeat(count) }
    }
~~~

Khi được dùng như một nguồn stream ở adapter hỗ trợ, reactive `Supplier<Flux<T>>` thường được gọi để lấy publisher rồi **subscribe vào publisher đó**; với nguồn vô hạn như `Flux.interval`, không cần và không nên hiểu là framework gọi `get()` mỗi giây như poller imperative.

Nếu reactive supplier trả **một Flux hữu hạn** và yêu cầu poll lại nhiều lần, Spring Cloud Function có annotation `@PollableBean` để cung cấp **metadata** cho framework tích hợp; bản thân annotation không thực hiện scheduling. Khi chọn cách này cần đối chiếu phiên bản SCF/Stream, cơ chế poller và ý nghĩa “mỗi lần poll” trong ứng dụng thực tế.

### 9.1. Vì sao không dùng Flux.interval bừa bãi?

`Flux.interval` phụ thuộc thời gian, tạo nguồn phát liên tục. Nếu downstream không tiêu thụ đủ nhanh hoặc sink/binder gặp lỗi, cần chính sách rõ ràng cho backpressure, hủy subscription và lifecycle. Ví dụ heartbeat chỉ nhằm dạy cách viết chữ ký; production không nên coi nó là cơ chế lịch chạy đáng tin cậy thay cho scheduler hoặc nguồn message được quản lý.

## 10. Consumer<Flux<T>> và Mono<Void>

Reactive consumer có một giới hạn quan trọng: `Consumer<Flux<T>>` (hoặc Kotlin function trả `Unit`) không trả publisher kết quả cho framework subscribe.

~~~kotlin
import java.util.function.Consumer
import reactor.core.publisher.Flux

val riskyConsumer: Consumer<Flux<Order>> =
    Consumer { orders ->
        // Tự đăng ký subscription, từ đây code chịu trách nhiệm lifecycle.
        orders.subscribe { order -> println(order.id) }
    }
~~~

Đây là ví dụ **cần thận trọng**, không phải khuyến nghị mặc định. Khi tự subscribe, lỗi, hủy stream và shutdown có thể khó kiểm soát, nhất là trong hệ thống messaging.

Spring Cloud Stream gợi ý cân nhắc hàm trả completion publisher, ví dụ:

~~~kotlin
import java.util.function.Function
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

val auditStream: Function<Flux<Order>, Mono<Void>> =
    Function { orders ->
        orders
            .doOnNext { order -> println("AUDIT: " + order.id) }
            .then()
    }
~~~

`then()` chuyển stream thành `Mono<Void>`: có thể biểu diễn **hoàn tất hoặc lỗi** nhưng không phát output value. Nếu input `Flux` sống suốt vòng đời ứng dụng, `Mono<Void>` có thể **không hoàn tất**; đây là đặc tính của stream, không phải nhất thiết là bug.

Không nên tự đổi sang `Mono<Unit>` với kỳ vọng giống hệt: `Mono.just(Unit)` phát một phần tử `Unit` thực, còn `Mono<Void>` thể hiện completion không có phần tử.

## 11. Xử lý lỗi: một phần tử sai có thể làm dừng cả Flux

Xét bean `classifyStream`:

~~~kotlin
orders.map { order -> decide(order) }
~~~

Hàm `decide` gọi `require`. Nếu một đơn có `totalVnd < 0`, toán tử `map` phát `onError`. Theo ngữ nghĩa Reactive Streams, lỗi terminal **kết thúc subscription**, không chỉ bỏ qua một bản ghi rồi tự tiếp tục.

### 11.1. onErrorResume ở ngoài luồng không bảo toàn các phần tử sau lỗi

~~~kotlin
val recovered: Flux<Decision> =
    orders
        .map { decide(it) }
        .onErrorResume { error ->
            Flux.just(Decision("UNKNOWN", "FAILED"))
        }
~~~

Khi gặp lỗi, chuỗi nguồn bị hủy và `onErrorResume` chuyển sang publisher dự phòng. Nó **không** tự động quay lại các message chưa xử lý của publisher nguồn. Không dùng mẫu này nếu yêu cầu là “một bản ghi lỗi nhưng mọi bản ghi kế tiếp vẫn chạy”.

### 11.2. Xử lý lỗi riêng cho từng bản ghi

Có thể đặt một publisher con quanh mỗi đơn hàng:

~~~kotlin
import java.util.function.Function
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

@Configuration
class SafeOrderFunctions {

    @Bean
    fun classifySafely(): Function<Flux<Order>, Flux<Decision>> =
        Function { orders ->
            orders.concatMap { order ->
                Mono.fromCallable { decide(order) }
                    .onErrorResume(IllegalArgumentException::class.java) {
                        Mono.just(Decision(order.id, "REJECTED"))
                    }
            }
        }
}
~~~

Trong ví dụ này, lỗi `IllegalArgumentException` của một đơn được đổi thành một `Decision(REJECTED)` trên **publisher con**; stream bên ngoài có thể tiếp tục xử lý các đơn khác. `concatMap` giúp giữ thứ tự. Đây là **chính sách nghiệp vụ cụ thể**: đối với lỗi tạm thời của database hoặc downstream, có thể cần retry/DLQ thay vì trả `REJECTED`.

### 11.3. Retry ở đúng phạm vi

`retryWhen(...)` đặt quanh **toàn bộ Flux** có thể resubscribe nguồn và làm chạy lại dữ liệu đã xử lý, dẫn đến side effect lặp hoặc duplicate events. Khi retry một thao tác I/O riêng cho từng bản ghi, ưu tiên áp dụng retry **bên trong publisher con**, có giới hạn số lần, backoff và kiểm soát idempotency.

Các tính năng error handling/retry theo message của Spring Cloud Stream dành cho **imperative message handler** không tự động có tác dụng tương tự đối với reactive pipeline. Hãy dùng các toán tử Reactor (`onErrorResume`, `retryWhen`, `doOnError`...) và kiểm tra hành vi thực tế của binder.

Không dùng `onErrorContinue` như một cách “chữa mọi lỗi” nếu chưa hiểu toán tử nào hỗ trợ và các rủi ro mất dữ liệu/khó truy vết.

## 12. Blocking I/O và scheduler

**Reactive không tự động có nghĩa non-blocking.** Gọi JDBC truyền thống, truy cập file đồng bộ hay HTTP client blocking ngay trong `map` có thể giữ một thread quá lâu.

Mẫu khái niệm để đưa thao tác blocking sang scheduler phù hợp:

~~~kotlin
import reactor.core.publisher.Mono
import reactor.core.scheduler.Schedulers

// blockingLookup là một hàm đồng bộ đã có từ hệ thống cũ.
fun lookupAsync(id: String, blockingLookup: (String) -> String): Mono<String> =
    Mono.fromCallable { blockingLookup(id) }
        .subscribeOn(Schedulers.boundedElastic())
~~~

`Schedulers.boundedElastic()` là lựa chọn thường dùng để cô lập thao tác blocking hữu hạn; nó **không biến** truy cập database blocking thành driver reactive thực thụ. Nếu tải lớn, cần giới hạn concurrency và đánh giá tài nguyên thread/connection pool.

So sánh:

| Cách thực thi | Đặc điểm |
| --- | --- |
| `map { blockingCall() }` | Có nguy cơ chặn thread xử lý tín hiệu hiện tại |
| `Mono.fromCallable { blockingCall() }.subscribeOn(boundedElastic())` | Chuyển công việc blocking sang scheduler phù hợp |
| Dùng WebClient/R2DBC/reactive driver | Tận dụng I/O không chặn khi driver thực sự hỗ trợ |

Trong Kotlin, `suspend fun` và `Flow<T>` thuộc mô hình coroutine, **không đồng nhất** với Reactor `Mono/Flux`. Có thể chuyển đổi bằng các thư viện bridge như `kotlinx-coroutines-reactor` khi cần, nhưng không thể tự mặc định mọi `suspend` function sẽ là một functional bean `Function<I, Mono<O>>`.

## 13. Kiểm thử bằng StepVerifier

`reactor-test` cung cấp `StepVerifier` để xác nhận chính xác các tín hiệu `onNext`, `onComplete` và `onError`. Đây là cách phù hợp để test function trả publisher, thay vì tự gọi `subscribe()` rồi hy vọng test chạy xong đúng lúc.

### 13.1. Unit test cho Mono

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.test.StepVerifier

class MonoFunctionTest {

    @Test
    fun classifyOneEmitsExactlyOneDecision() {
        val bean = ReactiveOrderFunctions().classifyOne()
        val publisher = bean.apply(Order("O-101", 1_500_000L))

        StepVerifier.create(publisher)
            .expectNext(Decision("O-101", "PRIORITY"))
            .verifyComplete()
    }

    @Test
    fun optionalCodeCanCompleteEmpty() {
        StepVerifier.create(normalizedCode("   "))
            .verifyComplete()

        StepVerifier.create(normalizedCode(" SAVE10 "))
            .expectNext("SAVE10")
            .verifyComplete()
    }
}
~~~

`verifyComplete()` của Mono trống **không** được hiểu thành “đã gửi một response rỗng”; test mới xác nhận tín hiệu Reactor.

### 13.2. Unit test cho Flux

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

class FluxFunctionTest {

    @Test
    fun classifiesEveryEvent() {
        val input = Flux.just(
            Order("O-101", 1_000_000L),
            Order("O-102", 250_000L)
        )
        val output = ReactiveOrderFunctions()
            .classifyStream()
            .apply(input)

        StepVerifier.create(output)
            .expectNext(Decision("O-101", "PRIORITY"))
            .expectNext(Decision("O-102", "STANDARD"))
            .verifyComplete()
    }

    @Test
    fun invalidOrderTerminatesRawPipeline() {
        val input = Flux.just(
            Order("O-103", -10L),
            Order("O-104", 500_000L)
        )
        val output = ReactiveOrderFunctions()
            .classifyStream()
            .apply(input)

        StepVerifier.create(output)
            .expectError(IllegalArgumentException::class.java)
            .verify()
    }
}
~~~

Test thứ hai minh họa việc **một lỗi kết thúc Flux**. Không nên kỳ vọng `O-104` vẫn được xử lý sau `onError` của cùng subscription.

### 13.3. Test chính sách lỗi từng phần tử

~~~kotlin
import org.junit.jupiter.api.Test
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

class SafeFluxFunctionTest {

    @Test
    fun badOrderDoesNotStopFollowingOrders() {
        // Lớp cấu hình được định nghĩa ở phần 11.2.
        val output = SafeOrderFunctions()
            .classifySafely()
            .apply(Flux.just(
                Order("O-201", -1L),
                Order("O-202", 500_000L)
            ))

        StepVerifier.create(output)
            .expectNext(Decision("O-201", "REJECTED"))
            .expectNext(Decision("O-202", "STANDARD"))
            .verifyComplete()
    }
}
~~~

Đoạn test gọi `SafeOrderFunctions` đã được khai báo ở phần 11.2. Trong project thật, cần bảo đảm lớp cấu hình này được Spring nạp khi sử dụng bean trong môi trường adapter.

### 13.4. Test publisher theo thời gian bằng virtual time

Không cần chờ thời gian thật khi kiểm tra `Flux.interval`:

~~~kotlin
import java.time.Duration
import org.junit.jupiter.api.Test
import reactor.core.publisher.Flux
import reactor.test.StepVerifier

class HeartbeatTest {

    @Test
    fun emitsTwoTicksWithVirtualTime() {
        StepVerifier.withVirtualTime {
            Flux.interval(Duration.ofSeconds(1)).take(2)
        }
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(2))
            .expectNext(0L, 1L)
            .verifyComplete()
    }
}
~~~

Ở đây publisher được tạo **bên trong supplier của `withVirtualTime`**, để Reactor dùng virtual scheduler khi phù hợp. Đây là test Reactor đơn vị, chưa nói gì về thời gian giao message ngoài broker.

### 13.5. FunctionCatalog test

Với ứng dụng Spring Boot đã nạp `ReactiveOrderFunctions`, có thể kiểm tra bean qua `FunctionCatalog`:

~~~kotlin
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog
import reactor.core.publisher.Flux

@SpringBootTest(classes = [ReactiveOrdersApplication::class])
class CatalogReactiveFunctionTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun findsReactiveFunction() {
        val function = catalog.lookup<
            Function<Flux<Order>, Flux<Decision>>
        >("classifyStream")

        assertNotNull(function)
    }
}
~~~

Unit test chứng minh logic xử lý `Mono/Flux`, còn test catalog chứng minh Spring đã đăng ký và nhận diện bean. Để xác nhận JSON/topic/destination hoạt động, phải có **integration test của web/stream/serverless adapter**.

## 14. Giới hạn và những lỗi dễ gặp

| Lỗi hoặc nhầm lẫn | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Xem `Mono<T>` như `T` | Mono chỉ phát dữ liệu khi được subscribe | Dùng toán tử, trả publisher cho adapter và test bằng StepVerifier |
| Xem `Flux<T>` là `List<T>` | Flux có thể vô hạn, có error/cancellation | Không gọi `collectList()` trên stream không kết thúc |
| Dùng `Mono.just(null)` | Reactor không cho phần tử null | `Mono.justOrEmpty(...)` hoặc `Mono.empty()` |
| Coi `Mono.empty()` là HTTP 404 cố định | HTTP mapping phụ thuộc adapter | Xác định và test HTTP contract |
| Dùng `Mono<Unit>` như `Mono<Void>` | Unit là phần tử thật, Void thường chỉ completion | Chọn kiểu hoàn tất đúng mục đích |
| Tự `subscribe()` trong mọi function | Tách vòng đời khỏi framework, khó theo dõi lỗi | Trả publisher; chỉ subscribe thủ công khi thật sự quản lý vòng đời |
| Đặt `retryWhen` lên toàn stream bừa bãi | Có thể resubscribe và lặp side effect | Retry theo đơn vị công việc, idempotency và giới hạn |
| Dùng `onErrorResume` ngoài Flux để tiếp tục mọi message | Nó chuyển sang fallback khi nguồn đã lỗi | Xử lý lỗi ở publisher con cho từng phần tử |
| Giả định backpressure xuyên Kafka/Rabbit | Binder có thể không reactive | Kiểm tra binder và giới hạn tài nguyên |
| Gọi blocking API trong `map` | Có thể giữ thread xử lý quá lâu | Reactive driver hoặc `boundedElastic` có kiểm soát |
| Cho rằng reactive function được gọi mỗi message | Với Spring Cloud Stream thường tạo pipeline một lần | Hiểu lifecycle/subscription và retry tương ứng |
| Nhầm `Flux<Tuple2<A,B>>` với hai cổng | Đây là một luồng các cặp | Nhiều output cần `Tuple2<Flux<A>,Flux<B>>` và adapter hỗ trợ |
| Xem Kotlin `Flow` như Reactor `Flux` | API và coroutine model khác nhau | Dùng cầu nối tương thích khi cần |

### Checklist khi đưa hàm Kotlin reactive vào production

1. Kiểu bean rõ ràng: `Function<Flux<I>,Flux<O>>`, `Function<I,Mono<O>>` hay `Supplier<Flux<O>>`.
2. Xác định **ai subscribe**, khi nào và publisher hữu hạn/vô hạn.
3. Chỉ ra rõ nghĩa của **0 phần tử**, **1 phần tử** và **onError**.
4. Xử lý null ở biên JSON/Java thay vì truyền null qua `Mono/Flux`.
5. Giới hạn concurrency và đánh giá nguồn blocking.
6. Kiểm thử riêng lỗi theo từng phần tử nếu dòng phải tiếp tục sau một bản ghi xấu.
7. Kiểm tra binder có hỗ trợ backpressure/retry/DLQ theo nhu cầu không.
8. Giữ logic nghiệp vụ độc lập, đưa transport/serialization vào adapter.
9. Kiểm thử `StepVerifier`, `FunctionCatalog` và một luồng end-to-end với môi trường thực tế.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Mono<List<Order>>` và `Flux<Order>` đều có thể chứa ba đơn hàng. Điểm khác nhau là gì?

**Đáp án:** `Mono<List<Order>>` phát **một phần tử List**; `Flux<Order>` phát từng `Order` dưới dạng nhiều `onNext`. Hai kiểu có hợp đồng streaming/serialization khác nhau.

**Câu 2.** Vì sao `Mono.justOrEmpty(null)` không tương đương `Mono.just(null)`?

**Đáp án:** `justOrEmpty(null)` tạo publisher **hoàn tất rỗng**. Reactor không cho phép `onNext(null)`, nên `Mono.just(null)` không phải cách hợp lệ để phát giá trị null.

**Câu 3.** Hàm `Function<Flux<Order>, Flux<Decision>>` trong Spring Cloud Stream thường được gọi lại cho từng Order?

**Đáp án:** Không. Nó thường được gọi một lần để thiết lập pipeline; các phần tử đi qua luồng đã được subscribe. Đây là khác biệt quan trọng với `Function<Order, Decision>` imperative.

**Câu 4.** Nếu trong `orders.map(::decide)`, một đơn bị lỗi và `decide` ném exception, các đơn phía sau có tiếp tục trên cùng subscription?

**Đáp án:** Không theo mặc định: exception tạo `onError` terminal. Cần chính sách phục hồi **theo từng phần tử** hoặc thiết kế nhánh lỗi nếu không muốn dừng luồng.

**Câu 5.** `Mono.just(Unit)` và `orders.then()` có giống nhau?

**Đáp án:** Không. `Mono.just(Unit)` phát một `Unit`, còn `then()` trả `Mono<Void>` chỉ thông báo completion/error, không phát `Unit`.

**Câu 6.** Dùng `Flux` với regular Kafka binder có bảo đảm backpressure từ broker đến consumer?

**Đáp án:** Không. Mức hỗ trợ backpressure phụ thuộc binder và các thành phần nguồn/đích thực tế.

**Câu 7.** Vì sao unit test gọi `classifyStream().apply(Flux.just(...))` chưa chứng minh broker đã nhận được message?

**Đáp án:** Unit test chỉ kiểm tra pipeline Reactor, không kiểm tra binding, serialization, broker, partition, retry và delivery.

**Câu 8.** Khi nào nên dùng `flatMap` thay cho `map`?

**Đáp án:** Khi mỗi phần tử phải tạo một **publisher con** như `Mono` do I/O bất đồng bộ, hoặc có thể cho 0..N kết quả. Nếu chỉ biến đổi đồng bộ `T -> R`, `map` dễ hiểu hơn.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming Model: Reactor, FunctionCatalog, Supplier và Function Arity](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages: Reactive Functions/Suppliers/Consumers](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Error Handling: khác biệt imperative và reactive](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Project Reactor — Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Project Reactor — Kotlin Support và Reactor Kotlin Extensions](https://projectreactor.io/docs/core/release/reference/kotlin.html)
- [Project Reactor — Testing với StepVerifier và VirtualTime](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Kotlin — Coroutines và Flow](https://kotlinlang.org/docs/flow.html)
