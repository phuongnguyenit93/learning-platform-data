# Phụ thuộc Kotlin và cơ chế nhận diện functional bean

## 1. Vì sao Kotlin cần được cấu hình đúng khi dùng Spring Cloud Function?

**Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`) cho phép viết logic nghiệp vụ thành các hàm có thể tái sử dụng qua HTTP, hệ thống sự kiện hoặc môi trường serverless. Mô hình cơ bản xoay quanh `Supplier`, `Function` và `Consumer`; `FunctionCatalog` nhận diện các bean phù hợp, chuẩn hóa cách gọi, hỗ trợ composition và chuyển đổi thông điệp theo kiểu đầu vào/đầu ra.

Trong Kotlin, chúng ta có thể biểu diễn cùng ý tưởng bằng **function type** gọn hơn Java:

~~~kotlin
val supplier: () -> String = { "ORD-101" }
val function: (String) -> String = { it.trim().uppercase() }
val consumer: (String) -> Unit = { println("Đã nhận: $it") }
~~~

Tuy nhiên, những lambda trên **chỉ là các giá trị Kotlin**. Để chúng có mặt trong `FunctionCatalog`, framework cần:

1. **Các thư viện Kotlin thích hợp trên classpath** để nhận diện kiểu lambda của Kotlin.
2. **Cách đăng ký lambda thành Spring bean**, thông thường qua phương thức `@Bean` trong một lớp cấu hình Spring.
3. **Metadata kiểu đủ rõ**, để xác định đầu vào, đầu ra và xử lý chuyển đổi payload.
4. **Adapter phù hợp**, nếu muốn gọi hàm qua HTTP, topic/queue hoặc một nền tảng serverless.

Bài này tập trung vào **phụ thuộc Kotlin** và **quy trình nhận diện functional bean**. Nó không yêu cầu phải xây dựng ngay một dịch vụ Kafka hay một hàm serverless.

## 2. Quan hệ giữa Kotlin function type và ba interface Java

Spring Cloud Function hỗ trợ Kotlin lambda, kể cả các lambda khai báo bằng cú pháp `(A) -> B`, khi được đăng ký thành Spring bean. Framework ánh xạ hợp đồng của chúng sang ba dạng hàm Java quen thuộc:

| Kiểu hàm Kotlin | Ý nghĩa | Hợp đồng Java tương ứng |
| --- | --- | --- |
| `() -> O` | Không nhận đối số, tạo kết quả | `Supplier<O>` |
| `(I) -> O` | Nhận một giá trị, trả một giá trị | `Function<I, O>` |
| `(I) -> Unit` | Nhận một giá trị, không trả kết quả nghiệp vụ | `Consumer<I>` |

**Ví dụ tương đương về ý nghĩa:**

~~~kotlin
// Ba Kotlin function type.
val nextCode: () -> String = { "ORD-101" }
val normalize: (String) -> String = { it.trim().uppercase() }
val audit: (String) -> Unit = { println("AUDIT: $it") }
~~~

~~~java
// Ba Java functional interface tương ứng về hợp đồng.
Supplier<String> nextCode = () -> "ORD-101";
Function<String, String> normalize = value -> value.trim().toUpperCase();
Consumer<String> audit = value -> System.out.println("AUDIT: " + value);
~~~

Ở JVM, kiểu `(String) -> String` của Kotlin không đồng nhất về mặt class với `java.util.function.Function<String, String>`: Kotlin function type thường dựa trên `kotlin.jvm.functions.Function1`, còn Java `Function` có phương thức `apply`. **Spring Cloud Function có cơ chế nhận diện/bọc Kotlin lambda** để người dùng có thể làm việc với chúng qua mô hình functional bean chung.

Tương tự, `Unit` trong Kotlin không phải là Java `Void`. Framework hiểu mẫu `(I) -> Unit` như một **consumer** khi nhận diện kiểu lambda thích hợp, thay vì yêu cầu bạn viết Java `Consumer` trong mọi trường hợp.

### 2.1. Cú pháp gần giống nhau nhưng không phải đều được hỗ trợ tự động

| Dạng khai báo | Có đủ để trở thành functional bean? |
| --- | --- |
| `val transform = { x: String -> x.uppercase() }` trong một hàm bất kỳ | **Chưa**; đây chỉ là một giá trị lambda |
| `fun transform(x: String): String = x.uppercase()` ở top level | **Chưa**; Spring không tự đăng ký mọi top-level function |
| `@Bean fun transform(): (String) -> String = { it.uppercase() }` | **Có thể được nhận diện** khi Spring đã đăng ký bean và hỗ trợ Kotlin được kích hoạt |
| `@Bean fun transform(): java.util.function.Function<String, String> = Function { ... }` | Bean trực tiếp dùng interface Java mà Spring Cloud Function nhận diện |
| `suspend (String) -> String` | **Không** mặc nhiên cùng chữ ký với `Function<String, String>`; cần cơ chế adapter/coroutine phù hợp |

Không nên nhầm **Kotlin function type** với **functional bean**. “Functional” trong Spring Cloud Function ám chỉ bean có hợp đồng được `FunctionCatalog` quản lý, không chỉ là bất kỳ hàm/lambda nào trong mã nguồn.

## 3. Các dependency cần thiết

Một dự án Kotlin/Spring Cloud Function phải có dependency của **Kotlin**, **Spring Boot/Spring Cloud Function**, và nếu cần, **adapter giao tiếp**. Không phải dependency nào cũng tham gia trực tiếp vào việc nhận diện lambda.

| Thành phần | Vai trò | Khi nào cần |
| --- | --- | --- |
| Kotlin JVM compiler/plugin | Biên dịch mã Kotlin thành JVM bytecode | Mọi dự án Kotlin trên JVM |
| `org.jetbrains.kotlin:kotlin-stdlib` | Các lớp runtime như `Function0`, `Function1`, `Unit` | Mọi ứng dụng Kotlin; Kotlin Gradle plugin thường thêm tự động |
| `org.jetbrains.kotlin:kotlin-reflect` | Hỗ trợ reflection và metadata Kotlin mà các thành phần Spring có thể sử dụng | Dependency chuẩn trong ứng dụng Spring Boot dùng Kotlin |
| `kotlin("plugin.spring")` | Tự động mở (`open`) các lớp/thành viên có annotation Spring cần proxy | Khuyến nghị cho cấu hình/bean Kotlin |
| `org.springframework.cloud:spring-cloud-function-context` | Cung cấp `FunctionCatalog` và mô hình thực thi Spring Cloud Function | Phần lõi của ví dụ trong bài |
| Spring Boot starter | Tạo và khởi động application context, cấu hình Spring | Ứng dụng Spring Boot |
| Jackson Kotlin module | Serialize/deserialize `data class` và kiểu Kotlin khi dùng JSON/Jackson | Khi trao đổi JSON, đặc biệt có constructor/property Kotlin |
| `spring-cloud-function-web` | Ánh xạ hàm thành HTTP endpoint | Chỉ khi sử dụng web adapter |
| Spring Cloud Stream + binder | Nối input/output binding với broker | Chỉ khi sử dụng messaging |

Điểm phân biệt quan trọng: **Kotlin runtime libraries cung cấp điều kiện để framework nhận biết Kotlin lambda**, còn `kotlin-spring` chủ yếu giải quyết chuyện **class Kotlin mặc định là `final` và Spring cần proxy**. Thêm compiler plugin không thay thế việc đăng ký `@Bean` hoặc bổ sung runtime dependency.

### 3.1. Gradle Kotlin DSL: cấu hình nền tảng

Ví dụ phần liên quan của `build.gradle.kts`:

~~~kotlin
plugins {
    // Phiên bản được quản lý trong cấu hình Gradle của dự án.
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

Đây là **đoạn cấu hình phụ thuộc**, giả định dự án đã quản lý các phiên bản plugin và Spring Boot/Spring Cloud qua Gradle plugin/BOM thích hợp. Nó không phải một file `build.gradle.kts` hoàn chỉnh để chạy độc lập. Nếu Kotlin Gradle plugin đã tự thêm `kotlin-stdlib`, có thể không cần khai báo lại `stdlib`.

**Phiên bản phải tương thích:** chọn phiên bản Spring Boot, Spring Cloud Function và Kotlin từ cùng một dải hỗ trợ; dùng BOM/dependency management chính thức thay vì tự ghép ngẫu nhiên các version. Một ví dụ dependency được viết cho Spring Boot 3.x không nên được bê nguyên sang Spring Boot 4.x nếu tên artifact của thư viện tích hợp đã thay đổi.

### 3.2. Khi cần JSON cho Kotlin data class

Nếu HTTP hoặc message adapter nhận JSON và cần tạo Kotlin `data class`, thêm Jackson Kotlin module phù hợp với thế hệ Jackson/Spring Boot:

~~~kotlin
dependencies {
    // Spring Boot 3.x / Jackson 2:
    // implementation("com.fasterxml.jackson.module:jackson-module-kotlin")

    // Spring Boot 4.x / Jackson 3:
    // implementation("tools.jackson.module:jackson-module-kotlin")
}
~~~

Chỉ chọn **dòng ứng với stack thực tế**, đồng thời kiểm tra dependency management của Spring Boot. Spring Boot có thể tự phát hiện/đăng ký Jackson Kotlin module khi nó có mặt trên classpath. Module JSON không phải điều kiện duy nhất để Spring Cloud Function nhận diện một lambda `(String) -> String`; nó phục vụ **chuyển đổi payload có cấu trúc Kotlin**.

### 3.3. Có phải thêm `spring-cloud-function-kotlin`?

Tài liệu **cũ** của Spring Cloud Function 2.x/3.x và ví dụ Spring Cloud Data Flow từng hướng dẫn thêm artifact `org.springframework.cloud:spring-cloud-function-kotlin`.

Tài liệu Spring Cloud Function **hiện hành** trình bày rằng chỉ cần **Kotlin SDK libraries trên classpath** để cơ chế hỗ trợ Kotlin lambda được tự động kích hoạt. Vì vậy, hãy **đối chiếu phiên bản Spring Cloud Function đang dùng** trước khi sao chép dependency từ bài viết cũ. Không mặc định thêm artifact của một thế hệ khác vào dự án mới.

## 4. Ví dụ đăng ký Kotlin lambda thành Spring bean

Ví dụ đầy đủ sau sử dụng cấu hình Spring Boot và trả về **Kotlin function type** tường minh:

~~~kotlin
package example.function

import java.util.Locale
import java.util.UUID
import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@SpringBootApplication
class KotlinFunctionApplication

fun main(args: Array<String>) {
    runApplication<KotlinFunctionApplication>(*args)
}

@Configuration
class KotlinFunctionBeans {

    // 0 -> 1: tương ứng Supplier<String>.
    @Bean
    fun generateOrderId(): () -> String = {
        UUID.randomUUID().toString()
    }

    // 1 -> 1: tương ứng Function<String, String>.
    @Bean
    fun normalizeOrderId(): (String) -> String = { orderId ->
        orderId.trim().uppercase(Locale.ROOT)
    }

    // 1 -> 0: tương ứng Consumer<String>.
    @Bean
    fun auditOrderId(): (String) -> Unit = { orderId ->
        println("Đã xử lý đơn hàng: $orderId")
    }
}
~~~

Giả định `KotlinFunctionBeans` nằm trong package được ứng dụng Spring Boot quét. `kotlin("plugin.spring")` giúp các cấu hình có annotation Spring được mở cho cơ chế proxy khi cần. Trong ứng dụng thực tế, thay `println` bằng logger hoặc cơ chế audit phù hợp.

**Khi application context khởi tạo:**

1. Spring phát hiện lớp cấu hình và gọi các phương thức có `@Bean`.
2. Mỗi phương thức cung cấp **một bean** chứa lambda Kotlin có kiểu cụ thể.
3. Spring Cloud Function phát hiện các bean đủ điều kiện, nhận diện hình dạng function type và đưa chúng vào cơ chế `FunctionCatalog`.
4. Framework bọc/chuẩn hóa Kotlin lambda thành hợp đồng tương ứng `Supplier`, `Function`, `Consumer` để các adapter và tính năng như chuyển đổi thông điệp có thể sử dụng.

~~~text
@Bean fun normalizeOrderId(): (String) -> String
                     |
                     v
        Spring ApplicationContext
        bean: "normalizeOrderId"
                     |
                     v
      Kotlin lambda recognition/wrapper
                     |
                     v
             FunctionCatalog
        lookup("normalizeOrderId")
                     |
                     v
  HTTP / Stream / serverless adapter
         (theo cấu hình riêng)
~~~

Tên bean thường được lấy từ **tên phương thức `@Bean`**. Nếu dự án có nhiều functional bean, adapter nên được cấu hình chọn rõ hàm, chẳng hạn:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrderId
~~~

Khi dùng Spring Cloud Stream, khai báo `spring.cloud.function.definition` càng quan trọng để xác định bean được bind với topic/queue nào. Bản thân cấu hình này **không tạo broker** và không buộc ứng dụng phải chạy HTTP.

## 5. Khi nào nên dùng interface Java ngay trong Kotlin?

Kotlin tương tác trực tiếp được với `java.util.function.Supplier`, `Function` và `Consumer`. Khi cần kiểu Java rõ ràng ngay trên chữ ký bean, có thể viết:

~~~kotlin
import java.util.Locale
import java.util.function.Consumer
import java.util.function.Function
import java.util.function.Supplier
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

@Configuration
class JavaInterfaceFunctionBeans {

    @Bean
    fun staticCode(): Supplier<String> =
        Supplier { "ORD-101" }

    @Bean
    fun normalizeCode(): Function<String, String> =
        Function { value -> value.trim().uppercase(Locale.ROOT) }

    @Bean
    fun logCode(): Consumer<String> =
        Consumer { value -> println("AUDIT: $value") }
}
~~~

Hai cách khai báo đều có thể được Spring Cloud Function sử dụng, nhưng có điểm khác biệt:

| Đặc điểm | Kotlin function type | Java functional interface trong Kotlin |
| --- | --- | --- |
| Chữ ký bean | `(String) -> String` | `Function<String, String>` |
| Kiểu JVM gốc | Kotlin `Function1` | Java `Function` |
| Nhận diện qua `FunctionCatalog` | Framework cần nhận biết và bọc Kotlin lambda | Interface Java thuộc mô hình lõi |
| Phong cách | Tự nhiên với Kotlin | Tường minh khi tích hợp mã Java |
| Consumer | `(String) -> Unit` | `Consumer<String>` |

**Khuyến nghị thực hành:** Trong ứng dụng chủ yếu dùng Kotlin, chọn function type khi phù hợp và kiểm thử qua `FunctionCatalog`. Trong thư viện có nhiều consumer Java, hoặc khi muốn tránh phụ thuộc vào nhận diện Kotlin lambda tại ranh giới bean, chữ ký Java `Function<I, O>` cũng là một lựa chọn rõ ràng.

Không có lý do phải khai báo **hai bean cho cùng một chức năng** chỉ để dùng cả hai kiểu. Hãy chọn một cách khai báo nhất quán cho từng chức năng.

## 6. FunctionCatalog nhận diện gì và bỏ qua gì?

### 6.1. Điều kiện cần để một lambda xuất hiện trong catalog

`FunctionCatalog` không quét mọi hàm Kotlin trong classpath. Lambda cần được **đăng ký thành Spring bean** và có **kiểu được hỗ trợ**. Với `@Bean fun normalizeOrderId(): (String) -> String`, kiểu đầu vào `String` và đầu ra `String` được thể hiện rõ trên chữ ký của bean method.

Ngược lại:

~~~kotlin
// Chỉ là một hàm Kotlin thông thường, không phải Spring bean.
fun normalizeOrderId(value: String): String =
    value.trim().uppercase()

// Chỉ là một thuộc tính top-level, Spring không tự đăng ký.
val normalizeLambda: (String) -> String = { it.trim().uppercase() }
~~~

Hai khai báo này **không tự xuất hiện** trong `FunctionCatalog`. Có thể đăng ký chúng một cách tường minh thông qua `@Bean`, ví dụ:

~~~kotlin
@Bean
fun normalizeOrderIdBean(): (String) -> String = ::normalizeOrderId
~~~

Hãy bảo đảm phương thức `@Bean` ở trong một lớp cấu hình Spring được quét/khởi tạo. Tên được tra cứu ở ví dụ sau là `normalizeOrderIdBean`, không phải `normalizeOrderId`.

### 6.2. Bean name và kiểu generic đều quan trọng

Khi một dự án có nhiều hàm, `FunctionCatalog` cần biết **tên** để chọn đúng hàm. Khi làm chuyển đổi JSON hoặc composition, framework còn cần **kiểu đầu vào/đầu ra** để chọn converter phù hợp.

Ví dụ:

~~~kotlin
data class Order(val id: String, val totalVnd: Long)
data class Decision(val id: String, val priority: Boolean)

@Bean
fun classifyOrder(): (Order) -> Decision = { order ->
    Decision(
        id = order.id,
        priority = order.totalVnd >= 1_000_000L
    )
}
~~~

Chữ ký `(Order) -> Decision` cung cấp hợp đồng để một adapter JSON có thể chuyển payload thành `Order` rồi serialize `Decision`, với điều kiện converter/Jackson module và dữ liệu đầu vào phù hợp.

Nếu thay kiểu cụ thể bằng `Any` hoặc ẩn hoàn toàn kiểu generic trong đăng ký thủ công, chức năng chuyển đổi có thể thiếu thông tin để xác định mục tiêu. Vì vậy, nên khai báo **return type của `@Bean` một cách tường minh**, đặc biệt khi ứng dụng sử dụng composition hoặc nhận payload từ bên ngoài.

### 6.3. Functional bean không đồng nghĩa functional-style application context

Hai khái niệm này dễ bị nhầm:

- **Functional bean:** bean biểu diễn `Supplier`, `Function` hoặc `Consumer`; có thể được tạo bằng `@Bean` thông thường.
- **Functional bean registration:** cách đăng ký bean bằng API như `GenericApplicationContext.registerBean(...)` và `FunctionRegistration`, có thể dùng để tối ưu những ứng dụng ít bean.

Trong mô hình đăng ký thủ công, thông tin generic có thể bị mất khi chỉ đưa một instance lambda vào context. Spring Cloud Function có `FunctionRegistration` để cung cấp metadata kiểu cần thiết. Không nên bắt đầu bằng đăng ký thủ công khi `@Bean` tường minh đã đáp ứng yêu cầu.

## 7. Kiểm tra nhận diện bằng FunctionCatalog

Sau khi ứng dụng khởi tạo, cách kiểm tra đáng tin cậy là tra cứu bean **qua `FunctionCatalog`**, không chỉ lấy bean trực tiếp từ `ApplicationContext`. Bean gốc là giá trị bạn đăng ký; kết quả tra cứu trong catalog có thể đã được framework bọc để hỗ trợ conversion và composition.

Ví dụ Kotlin:

~~~kotlin
import java.util.function.Function
import org.springframework.cloud.function.context.FunctionCatalog
import org.springframework.stereotype.Component

@Component
class FunctionCatalogProbe(
    private val catalog: FunctionCatalog
) {
    fun normalize(value: String): String {
        val function = requireNotNull(
            catalog.lookup<Function<String, String>>("normalizeOrderId")
        ) {
            "Không tìm thấy functional bean normalizeOrderId"
        }

        return function.apply(value)
    }
}
~~~

Khi gọi `normalize(" ord-42 ")`, kỳ vọng là `"ORD-42"`. Đây là ví dụ sử dụng catalog ở mức Spring Cloud Function; nếu không tìm thấy hàm, hãy kiểm tra tên bean và điều kiện nhận diện Kotlin trong application context.

**Kiểm thử Spring Boot** giúp xác định cấu hình thực sự có hiệu lực:

~~~kotlin
import java.util.function.Function
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.cloud.function.context.FunctionCatalog

@SpringBootTest(classes = [KotlinFunctionApplication::class])
class KotlinFunctionCatalogTest {

    @Autowired
    lateinit var catalog: FunctionCatalog

    @Test
    fun kotlinLambdaIsAvailableThroughCatalog() {
        val function = requireNotNull(
            catalog.lookup<Function<String, String>>("normalizeOrderId")
        )

        assertEquals("ORD-42", function.apply(" ord-42 "))
    }
}
~~~

Đây là **integration test ở mức application context**: nó kiểm tra bean đã được đăng ký và catalog nhận diện được Kotlin lambda. Không cần kết nối Kafka hay chạy HTTP. Nếu một test thất bại do phiên bản framework, hãy kiểm tra version matrix và runtime dependencies trước khi thay đổi logic.

### 7.1. Tự kiểm tra không cần integration adapter

Unit test Kotlin thuần có thể gọi lambda trực tiếp:

~~~kotlin
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class KotlinFunctionUnitTest {

    @Test
    fun normalizesOrderCode() {
        val normalize = KotlinFunctionBeans().normalizeOrderId()
        assertEquals("ORD-42", normalize(" ord-42 "))
    }
}
~~~

Unit test này xác nhận **hành vi lambda**, nhưng **chưa chứng minh** Spring đã đăng ký bean vào `FunctionCatalog`. Hai cấp kiểm thử phục vụ hai mục đích khác nhau.

## 8. Tái sử dụng cùng lambda qua các adapter

Khi bean đã được nhận diện trong catalog, ứng dụng có thể dùng nó qua adapter phù hợp.

| Môi trường | Vai trò của adapter | Điều cần bổ sung |
| --- | --- | --- |
| HTTP | Ánh xạ request thành input của hàm và chuyển output thành response | `spring-cloud-function-web` và web runtime phù hợp |
| Spring Cloud Stream | Nối input/output binding với topic/queue | Spring Cloud Stream và binder tương ứng |
| Serverless | Biến invocation/event của nền tảng thành lời gọi hàm | Adapter AWS/Azure/GCP tương ứng và cấu hình trigger |

Ví dụ với Spring Cloud Stream, nếu bind hàm `normalizeOrderId`:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrderId
    stream:
      bindings:
        normalizeOrderId-in-0:
          destination: orders.raw
        normalizeOrderId-out-0:
          destination: orders.normalized
~~~

Đoạn cấu hình này **chỉ có ý nghĩa** khi ứng dụng đã cài Spring Cloud Stream cùng binder. Kotlin lambda không tự tạo topic/queue.

Với HTTP, một adapter web có thể công bố functional bean thành endpoint; với serverless, adapter phải hiểu event/request theo hợp đồng của nền tảng. Khả năng gọi một hàm qua adapter **không thay đổi cách Spring nhận diện bean**, nhưng có thể đặt thêm giới hạn về payload, vòng đời và kiểu đầu vào/ra.

### 8.1. Composition

Spring Cloud Function hỗ trợ composition bằng cách chọn nhiều bean theo thứ tự:

~~~properties
spring.cloud.function.definition=normalizeOrderId|appendSuffix
~~~

Điều kiện: ứng dụng phải thực sự có bean `appendSuffix` với **kiểu vào tương thích kiểu ra** của `normalizeOrderId`. Ví dụ:

~~~kotlin
@Bean
fun appendSuffix(): (String) -> String = { "$it-READY" }
~~~

Composition tạo một pipeline tuần tự. Nó không tự biến một Kotlin lambda thành nhiều cổng đầu vào/ra, và cũng không khắc phục lỗi bean chưa được nhận diện trong catalog.

## 9. Các giới hạn thường gặp của kiểu Kotlin

### 9.1. `Unit`, `Void` và nullability

Trong Kotlin:

~~~kotlin
val log: (String) -> Unit = { println(it) }
val length: (String) -> Int = { it.length }
val optional: (String) -> String? = { value ->
    if (value.isBlank()) null else value
}
~~~

- `(String) -> Unit` có ý nghĩa consumer; nó **không phát payload kết quả nghiệp vụ** như `Function<String, String>`.
- `String?` thể hiện giá trị có thể null ở Kotlin, nhưng không có nghĩa tất cả adapter đều chấp nhận null làm message payload hoặc HTTP response theo cùng cách. Cần quy định rõ cách biểu diễn trường hợp không có kết quả.
- Kotlin type system giúp phát hiện lỗi null trong mã Kotlin, nhưng dữ liệu JSON bên ngoài vẫn cần được validation để tránh thiếu trường hoặc sai cấu trúc.

### 9.2. `suspend`, `Flow` và reactive publisher

Kotlin coroutine và Spring Cloud Function có thể phối hợp khi có các lớp tích hợp phù hợp, nhưng **không nên đánh đồng**:

~~~kotlin
suspend (String) -> String

kotlinx.coroutines.flow.Flow<String>

reactor.core.publisher.Flux<String>
~~~

Một `suspend` function có cơ chế thực thi riêng và không tự được nhận diện là `java.util.function.Function<String, String>` thông thường. `Flow` không tự đồng nghĩa `Flux`; nếu cần chuyển qua lại, phải dùng các API bridge và dependency thích hợp, chẳng hạn `kotlinx-coroutines-reactor`. Chỉ thêm dependency coroutine không tự động biến mọi `suspend fun` thành functional bean.

### 9.3. Kotlin class mặc định final

Ví dụ:

~~~kotlin
@Configuration
class MyConfiguration {
    @Bean
    fun normalize(): (String) -> String = { it.uppercase() }
}
~~~

Kotlin class mặc định là `final`. Khi Spring cần tạo subclass proxy cho lớp cấu hình, điều này có thể trở thành vấn đề. `kotlin("plugin.spring")` sẽ tự thêm tính `open` phù hợp cho nhiều annotation Spring thông dụng, trong đó có `@Configuration` qua cơ chế meta-annotation.

Nếu không dùng plugin, có thể cần viết `open class`/`open fun` hoặc chọn cơ chế cấu hình Spring không yêu cầu subclass proxy, tùy tình huống. Trong ứng dụng Kotlin/Spring Boot thông thường, **dùng Kotlin Spring compiler plugin** là lựa chọn thuận tiện.

## 10. Chẩn đoán khi Kotlin bean không xuất hiện trong catalog

Hãy kiểm tra lần lượt từ **bean registration** đến **catalog** và **adapter**:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `ApplicationContext` không có bean | `@Bean` nằm ngoài component scan; lớp cấu hình không được nạp | Kiểm tra package scan và `@Configuration`/`@SpringBootApplication` |
| Bean có trong context nhưng catalog lookup không tìm thấy | Chữ ký lambda không phù hợp, thiếu hỗ trợ Kotlin hoặc bean bị đánh dấu không đủ điều kiện | Kiểm tra Kotlin runtime libraries, kiểu trả về `@Bean`, log của SCF |
| `catalog.lookup("normalize")` không tìm thấy | Tên bean khác tên đang gọi | Kiểm tra tên phương thức `@Bean` hoặc tên tường minh của bean |
| Kotlin lambda dùng được trực tiếp nhưng qua HTTP lỗi | Thiếu web adapter hoặc sai content type/request | Kiểm tra dependency HTTP, endpoint, payload |
| Bean chạy trong unit test nhưng Spring khởi tạo lỗi | Lớp cấu hình Kotlin final hoặc phiên bản plugin không tương thích | Kiểm tra `kotlin("plugin.spring")`, Kotlin/Spring version |
| JSON không chuyển thành `data class` | Thiếu Jackson Kotlin module hoặc schema không đúng | Kiểm tra converter, group/artifact đúng phiên bản, JSON thực tế |
| Có nhiều functional bean nhưng adapter chọn nhầm | Không khai báo rõ `spring.cloud.function.definition` | Chọn đúng tên bean |
| Composition thất bại | Kiểu đầu ra và đầu vào giữa các hàm không tương thích hoặc bean không tồn tại | Tra cứu từng bean trước khi ghép |
| `suspend fun` không được tìm như Java `Function` | Đó là coroutine signature, không phải Java `Function<I, O>` chuẩn | Tạo adapter rõ ràng hoặc dùng API bridge được hỗ trợ |

Lưu ý: Spring Cloud Function có thể loại trừ một số bean vốn có kiểu functional nhưng không định dùng làm chức năng nghiệp vụ. Nếu có cấu hình `spring.cloud.function.ineligible-definitions`, hãy kiểm tra xem tên bean cần dùng có bị loại không.

### Quy trình xác minh đề xuất

1. Kiểm tra Kotlin compiler plugin và runtime dependencies được resolve đúng.
2. Xác nhận `@Bean` thực sự thuộc một cấu hình Spring đang được nạp.
3. Dùng function type rõ ràng, ví dụ `(String) -> String`.
4. Đặt tên bean nhất quán; khai báo `spring.cloud.function.definition` khi dùng adapter.
5. Tra cứu bằng `FunctionCatalog.lookup(...)` trong test Spring context.
6. Sau cùng mới kiểm tra HTTP/message/serverless adapter và định dạng payload.

## 11. Những sai lầm cần tránh

1. **Cho rằng mọi Kotlin lambda đều tự thành bean.** Chỉ những lambda được Spring đăng ký theo cơ chế phù hợp mới có thể được catalog nhận diện.
2. **Nhầm chức năng của `kotlin-spring` với `kotlin-stdlib`.** Một bên là compiler plugin mở lớp cho Spring, một bên là runtime của kiểu Kotlin.
3. **Bỏ qua `kotlin-reflect` trong ứng dụng Kotlin/Spring Boot.** Điều này có thể làm các tính năng Spring cần reflection hoạt động không đầy đủ.
4. **Sao chép dependency `spring-cloud-function-kotlin` từ tài liệu rất cũ mà không kiểm tra version.** Tài liệu hiện hành mô tả kích hoạt hỗ trợ Kotlin bằng Kotlin SDK libraries.
5. **Không khai báo return type cụ thể ở `@Bean`.** Điều này khiến người đọc khó nhận diện hợp đồng và có thể làm phức tạp việc suy kiểu khi tích hợp.
6. **Nhầm `Unit` với một kết quả nghiệp vụ.** Consumer nhận dữ liệu và thực hiện tác dụng phụ; đừng kỳ vọng có một payload trả về chỉ vì Kotlin biểu diễn `Unit` thành một kiểu.
7. **Coi `suspend` hoặc `Flow` là `Function`/`Flux` mà không có lớp thích ứng.** Đây là các mô hình lập trình khác nhau.
8. **Chỉ kiểm tra gọi lambda trực tiếp.** Kiểm thử qua `FunctionCatalog` là bước xác nhận cấu hình Spring Cloud Function đã nhận diện bean.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Đoạn sau có tự xuất hiện trong `FunctionCatalog` không?

~~~kotlin
val upper: (String) -> String = { it.uppercase() }
~~~

**Đáp án:** Không. Nó mới là một biến chứa lambda Kotlin. Cần đăng ký nó thành Spring bean hoặc qua một cơ chế đăng ký hợp lệ.

**Câu 2.** Vì sao `@Bean fun upper(): (String) -> String` có thể được Spring Cloud Function xử lý như `Function<String, String>`?

**Đáp án:** Spring Cloud Function hỗ trợ nhận diện Kotlin lambda (dựa trên Kotlin libraries/metadata trên classpath) và bọc chúng vào mô hình functional bean tương ứng trong catalog.

**Câu 3.** `@Bean fun audit(): (String) -> Unit` tương ứng interface Java nào?

**Đáp án:** `Consumer<String>`. `Unit` ở đây thể hiện thao tác không trả kết quả nghiệp vụ, dù bản thân nó là một kiểu Kotlin.

**Câu 4.** Hai dependency `kotlin("plugin.spring")` và `kotlin("reflect")` có cùng mục đích không?

**Đáp án:** Không. `plugin.spring` là plugin **biên dịch** giúp Spring proxy các lớp/thành viên phù hợp; `kotlin-reflect` là thư viện **runtime** cung cấp khả năng reflection.

**Câu 5.** Một lambda Kotlin chạy đúng khi gọi trực tiếp nhưng không tìm thấy qua `FunctionCatalog`. Nên kiểm tra điều gì đầu tiên?

**Đáp án:** Xem lambda đã được đăng ký thành bean, nằm trong phạm vi Spring scan và có kiểu `@Bean` được nhận diện hay chưa; sau đó mới kiểm tra hỗ trợ Kotlin/runtime dependency.

**Câu 6.** Cần đưa `Order` dạng Kotlin `data class` từ JSON vào hàm `(Order) -> Decision`. Những lớp phụ thuộc nào quan trọng?

**Đáp án:** Spring Cloud Function cùng adapter mong muốn, Kotlin runtime/reflection và **Jackson Kotlin module phù hợp với Spring Boot/Jackson đang dùng** để hỗ trợ serialize/deserialize cấu trúc Kotlin.

## Tài liệu tham khảo

- [Spring Cloud Function — Programming model, Kotlin Lambda support](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Functional Bean Definitions và FunctionRegistration](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Boot — Kotlin Support, dependencies, JSON và null-safety](https://docs.spring.io/spring-boot/reference/features/kotlin.html)
- [Kotlin — Kotlin Spring compiler plugin](https://kotlinlang.org/docs/kotlin-spring-plugin.html)
- [Kotlin — Reflection và kotlin-reflect](https://kotlinlang.org/docs/reflection.html)
- [Spring — Kotlin Support in Spring Cloud Function (bài giới thiệu lịch sử)](https://spring.io/blog/2018/09/11/kotlin-support-in-spring-cloud-function)
