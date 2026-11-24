# Các toán tử `apply` và `accept` với tên hàm hoặc hàm ghép

## 1. Bối cảnh và mục tiêu

**Spring Cloud Function (SCF)** cung cấp mô hình lập trình bằng ba interface Java: `Supplier<T>` tạo dữ liệu, `Function<T,R>` biến đổi dữ liệu và `Consumer<T>` nhận dữ liệu để thực hiện một hành động. Các hàm được quản lý qua **`FunctionCatalog`**, có thể được ghép (*function composition*) và tái sử dụng với adapter HTTP, luồng sự kiện hoặc môi trường serverless. Logic trong các hàm không cần biết giao thức đang gọi chúng.

**Spring Integration** cung cấp `IntegrationFlow` và các Enterprise Integration Patterns (EIP) như message channel, transformer, filter, router, wire tap, splitter, aggregator và service activator. Khi kết hợp với Spring Cloud Function, một luồng thông điệp cần gọi đúng hàm nghiệp vụ trong catalog mà vẫn giữ quyền điều phối ở tầng Integration.

Module `spring-cloud-function-integration` bổ sung **`FunctionFlowBuilder`** và **`FunctionFlowDefinition`**. Hai toán tử cần học trong bài này là:

- `apply(String functionDefinition)`: gọi một **`Function`** có đầu ra để chuyển message sang bước tiếp theo.
- `accept(String consumerDefinition)`: gọi một **`Consumer`** để tiêu thụ dữ liệu và kết thúc luồng; định nghĩa truyền vào có thể là một chuỗi `Function` kết thúc bằng `Consumer`.

Cả hai đều nhận **tên hoặc định nghĩa hàm ghép** mà `FunctionCatalog` hiểu, chẳng hạn `"normalizeCode"` hoặc `"normalizeCode|classifyCode"`.

Sau bài này, bạn sẽ có thể: phân biệt `apply` với `accept`, ghép function có kiểu tương thích, xen các EIP giữa các lời gọi, xây một flow chạy được, kiểm thử theo đúng ngữ nghĩa message và tìm lỗi thường gặp khi chạy.

## 2. Vị trí của apply và accept trong Integration DSL

### 2.1. Sơ đồ luồng

~~~mermaid
flowchart LR
    A["Nguồn: channel / Supplier / adapter"] --> B["FunctionFlowBuilder"]
    C["FunctionCatalog"] -. "lookup tên / composition" .-> D["apply: Function"]
    C -. "lookup tên / composition" .-> F["accept: Consumer"]
    B --> D
    D --> E["EIP: filter / router / wireTap..."]
    E --> F
    F --> G["Tác động cuối: lưu / gửi / ghi nhận"]
~~~

`FunctionFlowBuilder` được tự động cấu hình với catalog khi module `spring-cloud-function-integration` tương thích có trên classpath. Một lệnh như:

~~~java
return builder
        .from("tickets.input")
        .apply("normalizeCode")
        .accept("archiveCode");
~~~

được đọc như sau:

1. Nhận message trên channel `tickets.input`.
2. Tìm `normalizeCode` trong catalog và gọi `Function` để lấy đầu ra.
3. Đưa đầu ra tới `archiveCode`, một `Consumer` ở điểm cuối.

Ở đây, `"tickets.input"` là **tên channel** của Spring Integration; `"normalizeCode"` và `"archiveCode"` là **tên function trong catalog**. Chúng thuộc hai không gian khái niệm khác nhau, kể cả khi đều được biểu diễn bằng `String`.

### 2.2. So sánh trực tiếp

| Tiêu chí | `apply("name")` | `accept("name")` |
| --- | --- | --- |
| Đối tượng được tra cứu | `Function<T,R>` | `Consumer<T>` |
| Đầu vào | Payload hoặc message theo chữ ký hàm và wrapper của SCF | Payload hoặc message theo chữ ký consumer |
| Kết quả nghiệp vụ | Có `R` để bước tiếp theo sử dụng | `void`; không có payload kết quả để tiếp tục |
| Vị trí sử dụng | Đầu, giữa hoặc trước cuối chuỗi | Thường ở điểm kết thúc của flow |
| Định nghĩa ghép phù hợp | `f1|f2` với kết quả cuối là `Function` | `f1|f2|consumer` với kết quả cuối là `Consumer` |
| Liên hệ EIP | Thường đóng vai trò biến đổi message/payload | Thường tương ứng endpoint tiêu thụ/service activator |
| Mục đích | Xử lý rồi chuyển tiếp | Xử lý và kết thúc |

**Điểm cần nhớ:** `apply` không phải là cú pháp đồng nghĩa với `Function.apply(...)` trên Java object bất kỳ. Ở đây nó là một **toán tử DSL** nhận *tên definition*, dùng catalog tìm function, rồi tích hợp function đó với cơ chế xử lý message.

## 3. Dependency và điều kiện chạy

Module `spring-cloud-function-integration` được giới thiệu từ **Spring Cloud Function 4.0.3**. Dự án cần phiên bản SCF, Spring Integration và Spring Boot tương thích.

### 3.1. Maven

Ví dụ đoạn trong `pom.xml`, với Spring Cloud BOM và Spring Boot dependency management đã được cấu hình ở project:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-function-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các dependency được định nghĩa không kèm version ở đây vì ví dụ giả định dự án đã quản lý phiên bản phù hợp qua BOM. Nếu thêm version thủ công, phải kiểm tra khả năng tương thích thay vì phối trộn các major version.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 3.3. Điều kiện để DSL hoạt động

- Các bean kiểu `Supplier`, `Function` hoặc `Consumer` được Spring phát hiện và đăng ký vào catalog.
- Spring có thể inject `FunctionFlowBuilder`.
- Tên được truyền vào `apply`/`accept` có trong catalog và có loại interface phù hợp.
- Channel nguồn tồn tại hoặc được tạo theo cấu hình Spring Integration.
- Đầu ra hàm trước tương thích với đầu vào hàm sau, bao gồm cả trường hợp có chuyển đổi payload hoặc message wrapper.

Không cần tự `new FunctionFlowBuilder(...)` hoặc tự viết implementation của `FunctionCatalog` trong ứng dụng Spring Boot thông thường khi auto-configuration đã hoạt động.

## 4. Cơ chế tên đơn và tên hàm ghép

### 4.1. Gọi theo tên đơn

Giả sử catalog có:

~~~java
@Bean
Function<String, String> normalizeCode() {
    return value -> value.strip().toUpperCase(Locale.ROOT);
}

@Bean
Consumer<String> printCode() {
    return value -> System.out.println("Code: " + value);
}
~~~

Luồng:

~~~java
return builder
        .from("codes.input")
        .apply("normalizeCode")
        .accept("printCode");
~~~

Tương ứng với việc catalog tìm `normalizeCode` rồi `printCode` theo tên. Tuy nhiên, builder gắn chúng vào **IntegrationFlow** và cơ chế message endpoint; nó không chỉ đơn giản chạy hai lệnh Java khi Spring tạo bean.

### 4.2. Gọi một composition với dấu `|`

SCF hỗ trợ **declarative composition**. Với:

~~~text
trimCode     : Function<String, String>
uppercaseCode: Function<String, String>
classifyCode : Function<String, TicketDecision>
~~~

ta có:

~~~java
.apply("trimCode|uppercaseCode|classifyCode")
~~~

Luồng logic là:

~~~text
String
  → trimCode → String
  → uppercaseCode → String
  → classifyCode → TicketDecision
~~~

Đầu ra cuối cùng vẫn có giá trị `TicketDecision`, nên chuỗi phù hợp cho `apply`. Việc ghép nằm trong `FunctionCatalog`; **không tự sinh ra ba message channel** giữa ba function.

### 4.3. Composition kết thúc ở Consumer

Với `Consumer<TicketDecision> captureDecision`:

~~~java
.accept("trimCode|uppercaseCode|classifyCode|captureDecision")
~~~

Ta nhận được một chuỗi có **đầu vào String nhưng không có kết quả trả về**, vì bước cuối là consumer. Đây là tình huống dành cho `accept`.

~~~mermaid
flowchart LR
    A["String đầu vào"] --> B["trimCode"]
    B --> C["uppercaseCode"]
    C --> D["classifyCode"]
    D --> E["captureDecision: Consumer"]
    E --> F["Kết thúc"]
~~~

**Không đảo tùy tiện thứ tự composition:** `Consumer` không có dữ liệu đầu ra để nối với `Function` tiếp theo. Một định nghĩa như `"captureDecision|uppercaseCode"` không phải chuỗi `Function` hợp lệ.

### 4.4. Bảng kết quả theo loại hàm

| Composition | Kết quả logic | Toán tử phù hợp |
| --- | --- | --- |
| `Function<A,B> | Function<B,C>` | `Function<A,C>` | `apply(...)` |
| `Function<A,B> | Consumer<B>` | `Consumer<A>` | `accept(...)` |
| `Supplier<A> | Function<A,B>` | `Supplier<B>` | Dùng nguồn `Supplier`/`fromSupplier(...)` hoặc adapter phù hợp |
| `Supplier<A> | Consumer<A>` | `Runnable` | Không coi là `Function` đầu vào message cho `apply(...)` |
| `Consumer<A> | Function<A,B>` | Không thể composition theo thứ tự này | Không hợp lệ |

Một số kiểu dữ liệu có thể được SCF chuyển đổi qua wrapper/converter, nhưng **không nên dựa vào một phép chuyển đổi không rõ hợp đồng**. Trong ví dụ, hãy giữ các Java generic đầu vào/đầu ra tương thích rõ ràng.

## 5. Ví dụ end-to-end: phân loại mã phiếu hỗ trợ

### 5.1. Yêu cầu

Một ứng dụng nhận mã phiếu dạng chuỗi thông qua `DirectChannel`. Quy tắc:

1. Xóa khoảng trắng ở đầu và cuối.
2. Chuyển mã thành chữ hoa theo `Locale.ROOT`.
3. Loại message có mã rỗng.
4. Phân loại: mã bắt đầu `VIP-` là `EXPRESS`; các mã còn lại là `STANDARD`.
5. Ghi kết quả cuối cùng vào queue nội bộ để có thể quan sát và kiểm thử.

Ta dùng:

- `trimCode`, `uppercaseCode` và `classifyCode` làm các `Function` tái sử dụng.
- `captureDecision` làm `Consumer`.
- `filter(...)` làm EIP **Message Filter** ở giữa bước chuẩn hóa và phân loại.
- `FunctionFlowBuilder.apply(...)` và `accept(...)` để gọi tên trong catalog.

~~~mermaid
flowchart LR
    I["tickets.input"] --> A["apply(trimCode|uppercaseCode)"]
    A --> B{"filter: không rỗng?"}
    B -->|Có| C["apply(classifyCode)"]
    B -->|Không| X["Loại message"]
    C --> D["accept(captureDecision)"]
    D --> O["Queue<TicketDecision>"]
~~~

### 5.2. Các bean nghiệp vụ

Đặt file `TicketFunctions.java` trong package `example.ticket` (Java 17+):

~~~java
package example.ticket;

import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record TicketDecision(String code, String lane) {}

@Configuration
public class TicketFunctions {

    @Bean
    Function<String, String> trimCode() {
        return String::strip;
    }

    @Bean
    Function<String, String> uppercaseCode() {
        return text -> text.toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, TicketDecision> classifyCode() {
        return code -> {
            if (code.isBlank()) {
                throw new IllegalArgumentException("Mã phiếu rỗng");
            }
            String lane = code.startsWith("VIP-")
                    ? "EXPRESS" : "STANDARD";
            return new TicketDecision(code, lane);
        };
    }

    @Bean("capturedDecisions")
    Queue<TicketDecision> capturedDecisions() {
        return new ConcurrentLinkedQueue<>();
    }

    @Bean
    Consumer<TicketDecision> captureDecision(
            @Qualifier("capturedDecisions")
            Queue<TicketDecision> decisions) {
        return decisions::add;
    }
}
~~~

Những function này không có phụ thuộc vào HTTP controller, broker, tên channel hay cách Spring Integration nhận message. Chúng cũng có thể được một adapter của SCF gọi lại qua HTTP, sự kiện hoặc môi trường serverless, sau khi adapter tương ứng được cấu hình.

`captureDecision` là consumer có **side effect** (thay đổi queue); trong ứng dụng thật, nơi này có thể lưu database, ghi audit hoặc gửi kết quả sang dịch vụ khác. Khi đó cần chính sách lỗi và idempotency phù hợp.

### 5.3. Cấu hình IntegrationFlow

Đặt file `TicketIntegration.java` cùng package:

~~~java
package example.ticket;

import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
public class TicketIntegration {

    @Bean("tickets.input")
    MessageChannel ticketInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ticketFlow(FunctionFlowBuilder builder) {
        return builder
                .from("tickets.input")
                .apply("trimCode|uppercaseCode")
                .filter(String.class, code -> !code.isBlank())
                .apply("classifyCode")
                .accept("captureDecision");
    }
}
~~~

Đọc đoạn DSL theo thứ tự:

1. `from("tickets.input")` nối flow với message channel.
2. `apply("trimCode|uppercaseCode")` tra cứu một **composition gồm hai function**; kết quả là `String`.
3. `filter(String.class, ...)` kiểm tra payload đã chuẩn hóa; message rỗng bị bỏ theo chính sách của filter.
4. `apply("classifyCode")` gọi function trả về `TicketDecision`.
5. `accept("captureDecision")` chuyển kết quả tới consumer và kết thúc flow.

Trong cấu hình này, phương thức `accept(...)` là toán tử cuối nên **không thêm `.get()` phía sau**. Tài liệu chính thức của Spring Cloud Function cũng dùng `.accept("consumerName")` làm kết thúc khi trả về `IntegrationFlow`.

### 5.4. Khởi động ứng dụng

Một Spring Boot application đặt cùng package hoặc package cha để scan các bean:

~~~java
package example.ticket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TicketApplication {
    public static void main(String[] args) {
        SpringApplication.run(TicketApplication.class, args);
    }
}
~~~

### 5.5. Gửi message thử

Trong code đã có `ApplicationContext context`:

~~~java
MessageChannel input =
        context.getBean("tickets.input", MessageChannel.class);

input.send(new GenericMessage<>("  vip-005  "));
~~~

Thêm import `org.springframework.messaging.MessageChannel` và `org.springframework.messaging.support.GenericMessage`.

Với `DirectChannel` và các handler đồng bộ của ví dụ, sau `send(...)`, queue `capturedDecisions` nhận giá trị:

~~~text
TicketDecision[code=VIP-005, lane=EXPRESS]
~~~

Với message `"   "`, bước `trimCode` trả chuỗi rỗng, filter loại message và `captureDecision` không được gọi. **Giá trị trả về của `MessageChannel.send(...)` không phải chỉ báo “phiếu đã được xử lý nghiệp vụ thành công”**: nó phản ánh việc gửi/tiếp nhận theo contract của channel, trong khi message có thể đã bị filter hoặc các bước downstream xử lý theo cách riêng.

## 6. Ba cách kết hợp apply và accept

Cùng những function ở phần 5, có thể chọn một trong các cấu trúc dưới đây.

### 6.1. Mỗi Function là một bước apply riêng

~~~java
@Bean
IntegrationFlow splitStepsFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.splitInput")
            .apply("trimCode")
            .apply("uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .apply("classifyCode")
            .accept("captureDecision");
}
~~~

Đây là **biến thể thay thế**, yêu cầu channel `tickets.splitInput` được khai báo trước. Mỗi function hiện ra như một bước riêng trong DSL, cho phép thêm operator EIP giữa chúng.

### 6.2. Composition trong apply, Consumer đơn ở cuối

~~~java
@Bean
IntegrationFlow composedApplyFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.composedApplyInput")
            .apply("trimCode|uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .apply("classifyCode")
            .accept("captureDecision");
}
~~~

Đây là cấu trúc của ví dụ chính, chuyển hai bước biến đổi liền kề thành một composition. Những function bên trong composition **không tự tạo ra channel riêng**.

### 6.3. Composition kết thúc bằng Consumer trong accept

~~~java
@Bean
IntegrationFlow composedAcceptFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.composedAcceptInput")
            .apply("trimCode|uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .accept("classifyCode|captureDecision");
}
~~~

Giải thích:

- `apply("trimCode|uppercaseCode")` trả `String`.
- Filter giữ những chuỗi hợp lệ.
- `accept("classifyCode|captureDecision")` gọi tiếp `Function<String,TicketDecision>` rồi chuyển `TicketDecision` vào `Consumer<TicketDecision>`.

Đây là ví dụ rõ nhất cho thấy tham số của `accept` **không nhất thiết chỉ gồm một tên consumer**; nó có thể là *composition* kết thúc ở consumer.

> Các đoạn ở mục 6 là **các phương án triển khai độc lập**, không phải yêu cầu đăng ký cả ba trong cùng demo. Mỗi phương án có channel đầu vào riêng; nếu nhiều flow cùng ghi vào một consumer/queue, cần phân biệt nguồn sự kiện và tránh kiểm thử bị trộn dữ liệu.

### 6.4. Vì sao không gộp toàn bộ thành một accept?

Một biến thể ngắn hơn là:

~~~java
return builder
        .from("tickets.allInOneInput")
        .accept("trimCode|uppercaseCode|classifyCode|captureDecision");
~~~

Tuy nhiên, nó **không tương đương** với demo vì **không còn EIP Filter**. Mã rỗng sẽ đi vào `classifyCode` và gây `IllegalArgumentException`, thay vì được filter loại bỏ.

Nếu bước kiểm tra có ý nghĩa “bỏ message trước khi đi tiếp”, hãy giữ `filter(...)` hoặc thiết kế lại hợp đồng nghiệp vụ. Đừng xóa những EIP cần thiết chỉ để composition ngắn hơn.

## 7. Điều kiện tương thích kiểu và contract dữ liệu

### 7.1. Cách kiểm tra khi ghép

Với định nghĩa:

~~~text
f1: Function<A, B>
f2: Function<B, C>
c : Consumer<C>
~~~

ta có:

~~~text
apply("f1|f2") → Function<A,C>
accept("f1|f2|c") → Consumer<A>
~~~

Đầu ra của `f1` phải khớp hoặc chuyển đổi được một cách có kiểm soát sang đầu vào `f2`; kết quả của `f2` phải tương thích với consumer `c`.

Ví dụ sai về mặt hợp đồng:

~~~java
Function<String, Integer> parseAmount = Integer::parseInt;
Function<OrderRequest, String> formatOrder = OrderRequest::id;

// Không thể kỳ vọng Integer tự biến thành OrderRequest:
.apply("parseAmount|formatOrder")
~~~

Thêm converter có thể giải quyết một số trường hợp, nhưng không nên cho rằng SCF tự hiểu mọi cấu trúc dữ liệu nghiệp vụ. Hãy chọn chữ ký rõ ràng và test composition thực tế.

### 7.2. Kiểu nào không hợp với toán tử nào?

| Định nghĩa được truyền vào | `apply` | `accept` |
| --- | --- | --- |
| `"uppercaseCode"` (Function) | Phù hợp | Không phù hợp nếu không có Consumer cuối |
| `"uppercaseCode|classifyCode"` (Function cuối) | Phù hợp | Không phù hợp nếu chuỗi còn trả một kết quả |
| `"captureDecision"` (Consumer) | Không phù hợp | Phù hợp |
| `"classifyCode|captureDecision"` (Consumer cuối) | Không phù hợp | Phù hợp |
| `"supplierName"` (Supplier) | Không phù hợp làm Function nhận input | Không phù hợp làm Consumer nhận input |
| `"consumer|function"` | Không hợp lệ | Không hợp lệ |

Trong một số phiên bản, lỗi sai kiểu có thể xuất hiện khi dựng flow, khi lookup hoặc khi message thật đi qua endpoint. Vì vậy cần kiểm tra tên và kiểu ngay từ bước test Spring context, không chỉ dựa vào code biên dịch.

### 7.3. Sự khác biệt giữa Java `Function.andThen` và SCF composition

Trong Java thuần:

~~~java
Function<String, String> trim = String::strip;
Function<String, String> upper =
        value -> value.toUpperCase(Locale.ROOT);

Function<String, String> combined = trim.andThen(upper);
~~~

Trong SCF:

~~~java
Function<String, String> combinedFromCatalog =
        catalog.lookup("trimCode|uppercaseCode");
~~~

Điểm khác biệt là SCF cho phép composition thông qua **tên function** đã đăng ký, đồng thời catalog wrapper có thể cung cấp các cơ chế chuyển đổi/message phù hợp với framework. Cả hai vẫn là **pipeline biến đổi**, không phải broker, transaction hay một tập EIP tự phát.

## 8. EIP xen giữa các bước gọi function

Một lợi ích của `FunctionFlowBuilder` là bạn vẫn có thể sử dụng toán tử của Spring Integration.

| EIP | Vị trí điển hình | Ví dụ ý nghĩa |
| --- | --- | --- |
| **Message Filter** | Sau `apply("normalize...")` | Loại message rỗng hoặc không đạt điều kiện. |
| **Content-Based Router** | Sau `apply("classify...")` | Gửi message tới channel theo `lane` hoặc `tier`. |
| **Wire Tap** | Trước/sau bước xử lý cần quan sát | Sao chép message cho audit/debug mà không làm đổi payload chính. |
| **Message Channel** | Giữa các bước hoặc tại biên | Truyền message; loại channel ảnh hưởng sync/async/buffering. |
| **Splitter / Aggregator** | Khi một message phải tách thành nhiều message rồi hợp nhất | Cần correlation, release strategy, timeout và trạng thái. |
| **Error Channel** | Khi một endpoint/adapter hỗ trợ error flow | Xử lý failure theo hợp đồng vận hành. |

Ví dụ thay consumer cuối bằng router:

~~~java
@Bean
IntegrationFlow routingFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.routingInput")
            .apply("trimCode|uppercaseCode")
            .filter(String.class, code -> !code.isBlank())
            .apply("classifyCode")
            .route(TicketDecision.class, TicketDecision::lane,
                    mapping -> mapping
                            .channelMapping("EXPRESS", "tickets.express")
                            .channelMapping("STANDARD", "tickets.standard"))
            .get();
}
~~~

Đoạn này cần các channel `tickets.routingInput`, `tickets.express` và `tickets.standard` cùng downstream handlers tương ứng. Nó là **ví dụ riêng** để minh họa EIP Router, không phải phần bắt buộc của demo phần 5. Function `classifyCode` chỉ tính `TicketDecision`; router mới quyết định channel đích.

**Cẩn thận với vị trí của `accept`:** khi đã kết thúc ở consumer, không còn payload reply để tiếp tục router. Nếu cần định tuyến theo kết quả, đặt `apply` trả dữ liệu trước router, rồi mới đến các consumer/handler ở cuối mỗi nhánh.

## 9. Dùng apply/accept sau fromSupplier

`FunctionFlowBuilder` còn hỗ trợ `fromSupplier("supplierDefinition")`. Trong mô hình này, nguồn chủ động cung cấp dữ liệu và Spring Integration thường gọi nó bằng poller:

~~~java
@Bean
Supplier<String> ticketSource() {
    return () -> "VIP-PULSE";
}

@Bean
IntegrationFlow supplierFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("ticketSource",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1000)))
            .apply("trimCode|uppercaseCode")
            .accept("classifyCode|captureDecision");
}
~~~

Cần import `java.util.function.Supplier` và `org.springframework.integration.dsl.Pollers`. Đoạn này minh họa một flow thay thế. Vì supplier luôn trả cùng chuỗi `"VIP-PULSE"`, consumer sẽ nhận message giống nhau theo lịch; đây là chủ đích minh họa nguồn định kỳ, **không phù hợp nếu mỗi phiếu chỉ được xử lý một lần**.

Các mối quan hệ:

- `fromSupplier("ticketSource")` tìm `Supplier` trong catalog để tạo nguồn.
- `apply(...)` nhận từng payload được phát theo lịch và tạo kết quả.
- `accept(...)` tiêu thụ kết quả ở cuối.
- Nhịp polling, số message mỗi lượt, lifecycle và xử lý lỗi thuộc về endpoint/poller, không tự phát sinh từ `Supplier.get()`.

Nếu `Supplier` lấy rồi xóa dữ liệu từ queue/DB, failure ở phía sau có thể làm mất item trước khi xử lý thành công. Cần thiết kế acknowledgment/checkpoint, transaction hoặc redrive theo yêu cầu production.

## 10. Payload, Message header và chuyển đổi dữ liệu

### 10.1. Payload khác với Message

Spring Integration truyền các message có dạng khái niệm:

~~~text
Message<String>
  payload: "  vip-005  "
  headers:
    id: ...
    timestamp: ...
    traceId: "trace-005"   (nếu có)
~~~

Một `Function<String,String>` như `trimCode` chỉ cần nội dung nghiệp vụ. Khi dùng `apply("trimCode")`, catalog wrapper và integration endpoint điều phối việc gọi theo chữ ký hàm.

Khi cần truy cập metadata, khai báo rõ function nhận `Message<T>`:

~~~java
@Bean
Function<Message<String>, Message<String>> markProcessed() {
    return message -> MessageBuilder.fromMessage(message)
            .setHeader("processingStage", "NORMALIZED")
            .build();
}
~~~

Cần import `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`.

Đừng tự động ghép `Function<Message<String>, Message<String>>` với `Function<String,TicketDecision>` rồi suy ra mọi header luôn được giữ nguyên. **Kiểm thử kết quả thực tế ở biên từng adapter và wrapper**; một số header thuộc giao thức vận chuyển như acknowledgment hoặc partition có quy tắc riêng.

### 10.2. JSON, byte[] và POJO

Một function có `Function<OrderRequest, RoutingDecision>` không đồng nghĩa mọi input JSON string đều có thể gửi vào flow mà không cần chuyển đổi:

~~~text
Kafka/HTTP bytes hoặc JSON string
    → [deserializer / message converter phù hợp]
    → OrderRequest
    → apply("validateOrder|classifyOrder")
    → RoutingDecision
~~~

Content type, chữ ký generic, converter trên classpath và cấu hình adapter quyết định cơ chế chuyển đổi. Một unit test `Function.apply(POJO)` thành công chưa đủ để đảm bảo production nhận JSON hợp lệ; cần test ranh giới message và adapter.

### 10.3. Các function reactive

SCF còn hỗ trợ `Function<Flux<T>, Flux<R>>`. Đầu vào của function này là **một publisher**, không phải một payload `T` đơn lẻ. Không giả định rằng:

~~~java
.apply("reactiveFunction")
~~~

sẽ tự chuyển mọi message `T` thành một subscription `Flux<T>` đúng kỳ vọng trong mọi phiên bản và loại flow.

Khi dùng reactive endpoint/channel, cần hiểu subscription, backpressure, cách phát nhiều phần tử, cách hoàn tất và propagation lỗi. Hãy thiết kế một reactive flow cụ thể và kiểm thử cách `Flux` được chuyển thành message, thay vì dùng chung giả định của ví dụ imperative `String → TicketDecision`.

## 11. Lỗi, retry và ngữ nghĩa điểm kết thúc

Một số lỗi có thể phát sinh:

| Tình huống | Biểu hiện | Cách xử lý |
| --- | --- | --- |
| Không có function tên `trimCode` | Builder/catalog không tra cứu được định nghĩa cần thiết. | Xác nhận tên bean, component scanning, auto-configuration, version. |
| `apply("captureDecision")` | Consumer không phù hợp toán tử cần Function có đầu ra. | Dùng `accept("captureDecision")`. |
| `accept("classifyCode")` | Function có đầu ra, không phải consumer kết thúc. | Dùng `apply("classifyCode")` rồi `accept("captureDecision")`. |
| `apply("classifyCode|trimCode")` | Kiểu đầu ra `TicketDecision` không khớp input `String` của `trimCode`. | Sắp xếp đúng thứ tự/kiểu dữ liệu. |
| Payload sai kiểu hoặc converter thiếu | `ClassCastException`, lỗi conversion hoặc validation. | Kiểm tra contract input và converter ở adapter. |
| Mã rỗng sau khi filter bị bỏ | Không có kết quả ở consumer; có thể là hành vi hợp lệ. | Nếu cần lưu audit, cấu hình discard channel hoặc tracking. |
| Consumer lưu DB thất bại | Exception ở endpoint cuối; item có thể đã được tiêu thụ ở nguồn. | Retry có giới hạn, idempotency, DLQ/error flow theo hạ tầng. |
| Message bị xử lý hai lần | Retry/redelivery hoặc nhiều binding/flow. | Kiểm tra đường đi và khóa idempotency. |

### 11.1. Đường đi exception

Với `DirectChannel` đồng bộ trong ví dụ, exception từ function hoặc consumer thường lan theo call stack của message sender. Với `ExecutorChannel`, polling endpoint hoặc broker adapter, thời điểm và nơi xử lý lỗi có thể khác; cần cấu hình error channel, retry advice, binder retry hoặc DLQ phù hợp với hạ tầng thực tế.

**`apply` và `accept` không tự đảm bảo retry, exactly-once hay transaction phân tán.** Composition cũng không đảm bảo rollback nếu consumer đã có side effect trước khi một bước sau đó thất bại.

### 11.2. Quan sát theo ranh giới

Có thể đặt `.log(...)` hoặc `wireTap(...)` trong flow để theo dõi message. Tuy nhiên, log dữ liệu nghiệp vụ cần tránh để lộ thông tin nhạy cảm, và logging ở giữa một composition như `"f1|f2"` không xuất hiện như một endpoint EIP độc lập. Nếu cần đo latency/lỗi của từng bước, hãy cân nhắc tách từng function thành `apply` riêng, hoặc đo trực tiếp trong function theo cơ chế quan sát phù hợp.

## 12. Kiểm thử: function, catalog và IntegrationFlow

### 12.1. Unit test logic nghiệp vụ

Không cần khởi động Spring:

~~~java
TicketFunctions functions = new TicketFunctions();

String normalized = functions.uppercaseCode()
        .apply(functions.trimCode().apply(" vip-005 "));

TicketDecision decision =
        functions.classifyCode().apply(normalized);

assertEquals("VIP-005", decision.code());
assertEquals("EXPRESS", decision.lane());
~~~

Cần JUnit 5 và static import `org.junit.jupiter.api.Assertions.assertEquals`. Thêm trường hợp `" normal-006 "` → `STANDARD` và `"   "` → chuỗi rỗng sau chuẩn hóa. Unit test trên không kiểm tra EIP Filter, vì filter nằm ở IntegrationFlow.

### 12.2. Test lookup/composition

Trong Spring context có `FunctionCatalog`:

~~~java
@Autowired
FunctionCatalog catalog;

@Test
void shouldComposeFunctionsByName() {
    Function<String, TicketDecision> pipeline =
            catalog.lookup("trimCode|uppercaseCode|classifyCode");

    assertNotNull(pipeline);

    TicketDecision result = pipeline.apply(" vip-005 ");
    assertEquals("VIP-005", result.code());
    assertEquals("EXPRESS", result.lane());
}
~~~

Kiểm thử này chứng minh tên có trong catalog và chuỗi function tương thích trên dữ liệu được chọn. Có thể kiểm thêm một composition kết thúc ở consumer:

~~~java
Consumer<String> pipeline =
        catalog.lookup("trimCode|uppercaseCode|classifyCode|captureDecision");

assertNotNull(pipeline);
// Khi gọi pipeline.accept(...), kết quả nằm ở queue của consumer.
~~~

Đây là phép kiểm thử catalog, chưa phải xác nhận message đã đi qua channel, filter, router hoặc adapter.

### 12.3. Integration test flow đồng bộ

Một test Spring Boot với đúng cấu hình demo:

~~~java
package example.ticket;

import java.util.Queue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = TicketApplication.class)
class TicketFlowTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    @Qualifier("capturedDecisions")
    Queue<TicketDecision> capturedDecisions;

    @Test
    void shouldApplyCompositionAndAcceptResult() {
        capturedDecisions.clear();

        MessageChannel input =
                context.getBean("tickets.input", MessageChannel.class);
        input.send(new GenericMessage<>("  vip-005  "));

        TicketDecision result = capturedDecisions.poll();

        assertNotNull(result);
        assertEquals("VIP-005", result.code());
        assertEquals("EXPRESS", result.lane());
    }

    @Test
    void shouldFilterBlankTicket() {
        capturedDecisions.clear();

        MessageChannel input =
                context.getBean("tickets.input", MessageChannel.class);
        input.send(new GenericMessage<>("   "));

        assertTrue(capturedDecisions.isEmpty());
    }
}
~~~

Với `DirectChannel` và consumer queue đồng bộ của demo, có thể đọc kết quả ngay sau `send(...)`. Nếu thay bằng executor, poller hoặc broker, test cần cơ chế chờ có thời hạn và tránh chia sẻ queue/context giữa các test chạy đồng thời.

Để kiểm thử **`accept("classifyCode|captureDecision")`**, tạo flow thay thế ở mục 6.3 với channel riêng, rồi kiểm tra cùng kết quả. Đây là kiểm chứng trực tiếp composition kết thúc bằng consumer, thay vì chỉ kiểm tra một function.

### 12.4. Những thuộc tính nên xác minh khi nối adapter thật

- Chữ ký đầu vào sau JSON deserialization có khớp generic của function không?
- Header trace/correlation có được giữ đúng ở đầu ra cần quan sát không?
- Message lỗi nghiệp vụ bị filter, ném exception hay chuyển sang error flow?
- Khi consumer thất bại và broker redeliver, side effect có idempotent không?
- Có nhiều flow/binding cùng xử lý một sự kiện ngoài ý muốn không?

## 13. Quan hệ với spring.cloud.function.definition

Property quen thuộc:

~~~properties
spring.cloud.function.definition=trimCode|uppercaseCode|classifyCode
~~~

thường được adapter hoặc binder của SCF sử dụng để chọn function cần gọi. Trong khi đó:

~~~java
return builder
        .from("tickets.input")
        .apply("trimCode|uppercaseCode")
        .accept("classifyCode|captureDecision");
~~~

là **cấu hình cụ thể của một IntegrationFlow**. Hai cách đều dùng ý tưởng function definition trong catalog nhưng có vị trí điều khiển khác nhau:

- `spring.cloud.function.definition`: thành phần có trách nhiệm đọc property (ví dụ HTTP/broker adapter) sẽ chọn definition để kích hoạt.
- `apply(...)` và `accept(...)`: chính Integration DSL chỉ định function nào chạy trong flow đó.
- Channel `tickets.input` phải có sender hoặc inbound adapter kết nối; property không tự tạo channel và không tự kết nối Kafka topic tới nó.

Nhờ tách ranh giới này, cùng `trimCode`, `uppercaseCode` hoặc `classifyCode` vẫn có thể được tái sử dụng qua HTTP, sự kiện, serverless hoặc một Spring Integration flow, trong khi mỗi môi trường có hợp đồng giao nhận và lỗi riêng.

## 14. Những nhầm lẫn phổ biến

1. **Dùng `apply("consumerName")`:** consumer có `void` return và không cung cấp kết quả để bước tiếp theo dùng.
2. **Dùng `accept("functionName")` rồi kỳ vọng có reply:** `accept` dành cho kết thúc ở consumer; muốn trả kết quả, dùng `apply` và cấu hình đầu ra/request-reply rõ ràng.
3. **Nhầm dấu `|` với Message Channel:** `"f1|f2"` là composition trong catalog, không tạo một message channel ở giữa hai hàm.
4. **Ghép sai generic:** `Function<A,B>` không thể nối tùy tiện với `Function<C,D>` khi `B` không chuyển được sang `C`.
5. **Gộp cả flow thành accept và bỏ EIP:** filter, router, wire tap, splitter hoặc aggregator có hành vi độc lập; cần giữ chúng nếu yêu cầu nghiệp vụ hoặc vận hành đòi hỏi.
6. **Đặt xử lý vận chuyển vào function thuần:** hàm phân loại không cần biết tên Kafka topic; router/adapter chịu trách nhiệm gửi đúng nơi.
7. **Cho rằng FunctionCatalog tự retry:** retry, DLQ, ack, transaction, idempotency thuộc cấu hình endpoint/binder và thiết kế hệ thống.
8. **Giả định mọi input được tự chuyển thành POJO:** cần contract serialization, content type và converter kiểm thử được.
9. **Đăng ký nhiều flow thử nghiệm trên cùng input mà không kiểm soát:** có thể gây xử lý trùng, cùng ghi một queue hoặc không rõ flow nào thực sự nhận message.

## 15. Bài tập thực hành

1. Thay `classifyCode` thành `Function<String, TicketDecision>` có thêm tuyến `REVIEW` cho mã bắt đầu `RISK-`. Sử dụng EIP router gửi ba loại quyết định tới ba channel.
2. Viết hai cấu hình độc lập: một dùng `apply("trimCode").apply("uppercaseCode")`, một dùng `apply("trimCode|uppercaseCode")`. So sánh payload đầu ra và vị trí bạn có thể chèn `wireTap`.
3. Tạo một flow có `.accept("classifyCode|captureDecision")`. Viết integration test chứng minh consumer nhận `TicketDecision` từ input String.
4. Bỏ filter của demo, chạy message chỉ có khoảng trắng, quan sát lỗi của `classifyCode`. Bổ sung discard/error policy có chủ đích và giải thích sự khác nhau.
5. Thay input channel bằng `fromSupplier` với queue nguồn. Kiểm thử nhịp polling, trường hợp supplier trả `null`, và giải thích vì sao unit test trực tiếp function không xác nhận được source lifecycle.

## 16. Câu hỏi tự đánh giá

- Vì sao `apply("f1|f2")` phù hợp khi `f2` trả dữ liệu, còn `accept("f1|f2|c")` phù hợp khi `c` là consumer?
- Vì sao thứ tự `Consumer|Function` không hợp lệ?
- Có thể chèn `filter(...)` giữa hai function nằm trong cùng một composition `"f1|f2"` không? Nếu muốn filter, cần tổ chức flow như thế nào?
- Tên truyền vào `from("channel")` và `apply("function")` được phân giải ở những tầng nào?
- Khi một message bị loại bởi filter, tại sao không thể dựa vào `send(...)` để kết luận consumer đã xử lý nó?
- Nếu consumer ghi database thất bại sau khi source đã lấy dữ liệu, bạn sẽ đặt retry/idempotency ở đâu?

## 17. Tài liệu tham khảo

- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): mô tả `FunctionFlowBuilder`, `FunctionFlowDefinition`, `apply` và `accept`, cùng ví dụ composition kết thúc bằng consumer.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, composition, chuyển đổi dữ liệu, `Supplier`, `Function` và `Consumer`.
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html): `IntegrationFlow` và cách tổ chức các endpoint.
- [Spring Integration — java.util.function Interfaces Support](https://docs.spring.io/spring-integration/reference/functions-support.html): tương tác giữa Java function interface và Spring Integration.

**Kết luận:** Trong `FunctionFlowBuilder`, `apply("name")` gọi `Function` và giữ đầu ra cho flow; `accept("name")` gọi `Consumer` để kết thúc xử lý. Cả hai đều hiểu **định nghĩa hàm ghép qua dấu `|`** theo `FunctionCatalog`, với điều kiện kiểu dữ liệu và loại hàm cuối phù hợp. Hãy ghép các phép biến đổi liền kề khi có lợi, giữ EIP cần thiết trong IntegrationFlow và quản lý conversion, retry, header và adapter ở đúng ranh giới để một logic nghiệp vụ có thể dùng lại qua HTTP, sự kiện hoặc serverless.
