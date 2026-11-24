# Module `spring-cloud-function-integration`

## 1. Mục tiêu của bài học

**Spring Cloud Function (SCF)** khuyến khích viết nghiệp vụ qua ba hợp đồng `Supplier<T>`, `Function<T,R>` và `Consumer<T>`, rồi tra cứu/ghép chúng bằng `FunctionCatalog`. Hàm có thể được dùng lại khi được gọi qua HTTP, sự kiện, môi trường serverless hoặc trực tiếp từ một ứng dụng Spring.

**Spring Integration** cung cấp các thành phần để triển khai Enterprise Integration Patterns (EIP): message channel, transformer, filter, router, splitter, aggregator, gateway, polling adapter và error flow. Java DSL của Spring Integration cho phép mô tả đường đi của message dưới dạng `IntegrationFlow`.

Module **`spring-cloud-function-integration`** là cầu nối giữa hai mô hình. Điểm nổi bật của module là **`FunctionFlowBuilder`**, được tự động cấu hình với `FunctionCatalog` để Spring Integration DSL có thể tham chiếu hàm theo **tên định nghĩa**, thay vì buộc mỗi flow tự gọi `catalog.lookup(...)`. Module này xuất hiện từ Spring Cloud Function **4.0.3** và tiếp tục được mô tả trong tài liệu Spring Cloud Function hiện hành.

Sau bài học, bạn có thể:

- Giải thích nhiệm vụ của module và phân biệt nó với `spring-cloud-function-context`, Spring Integration Core và các adapter HTTP/broker.
- Khai báo dependency tương thích, tạo các hàm và dùng `FunctionFlowBuilder` để nối chúng thành `IntegrationFlow`.
- Hiểu chức năng của `fromSupplier(...)`, `from(...)`, `apply(...)`, `accept(...)` và tên composition trong `FunctionCatalog`.
- Kết hợp lời gọi hàm với EIP (filter, wire tap, channel, router), đồng thời nhận diện vấn đề type conversion, nhịp polling, lỗi và kiểm thử.

## 2. Vì sao cần một module tích hợp riêng?

Khi chỉ có SCF, một ứng dụng có thể khai báo:

~~~java
@Bean
Function<String, String> normalize() {
    return text -> text.trim().toUpperCase();
}
~~~

Hàm này không quy định message đến từ đâu và sẽ đi đến đâu. Khi cần xử lý thông điệp thực tế, một flow có thể phải làm thêm các bước như nhận từ channel, ghi audit, bỏ payload không hợp lệ, chuyển đổi, phân nhánh rồi gọi adapter gửi ra ngoài.

Spring Integration Java DSL vốn đã cho phép truyền trực tiếp instance `Function` vào transformer. Khi ứng dụng có nhiều hàm được đăng ký trong `FunctionCatalog` (bao gồm các hàm auto-configuration từ thư viện bên ngoài), thao tác theo **tên hàm** giúp flow diễn đạt rõ những gì được ghép, trong khi catalog chịu trách nhiệm tra cứu và hỗ trợ composition. Đây là vấn đề mà `spring-cloud-function-integration` giải quyết.

~~~mermaid
flowchart LR
    A["@Bean Supplier / Function / Consumer"] --> B["FunctionCatalog"]
    D["Hàm được auto-configure từ thư viện"] --> B
    B --> C["FunctionFlowBuilder"]
    C --> E["IntegrationFlow"]
    F["Inbound adapter / channel"] --> E
    E --> G["Filter / Router / Wire Tap"]
    G --> H["Consumer / outbound adapter"]
~~~

**Phân chia trách nhiệm:**

| Thành phần | Trách nhiệm chính |
| --- | --- |
| `spring-cloud-function-context` | Đăng ký, tra cứu và composition `Supplier`, `Function`, `Consumer` thông qua `FunctionCatalog`. |
| `spring-cloud-function-integration` | Cung cấp DSL tích hợp với `FunctionCatalog` qua `FunctionFlowBuilder` và `FunctionFlowDefinition`. |
| Spring Integration | Vận hành message channel, message endpoint, filter/router, poller, message store, error flow và các EIP khác. |
| `spring-cloud-function-web` | Adapter đưa function ra HTTP trong cấu hình được hỗ trợ. |
| Spring Cloud Stream cùng binder tương ứng | Kết nối function với các destination và broker như Kafka/RabbitMQ. |
| Serverless adapter | Ánh xạ event và vòng đời thực thi của nền tảng serverless tới function. |

Không nên hiểu việc thêm `spring-cloud-function-integration` đồng nghĩa ứng dụng tự có REST endpoint, Kafka consumer, transaction phân tán hoặc hệ thống retry bền vững. Những điều đó cần adapter và cấu hình riêng theo môi trường triển khai.

## 3. Khai báo dependency

### 3.1. Maven

Đặt dependency sau trong `pom.xml` của ứng dụng Spring Boot sử dụng Spring Cloud Function:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-integration</artifactId>
</dependency>
~~~

Đây là **tọa độ module**. Để ví dụ hoạt động, dự án còn cần những dependency nền tảng tương thích của Spring Boot, Spring Cloud Function và Spring Integration theo BOM hoặc dependency management của phiên bản Spring Cloud đang sử dụng. Nếu chưa có `spring-integration-core`/DSL trên classpath thông qua dependency transitively, hãy thêm cấu phần Spring Integration theo hướng dẫn của phiên bản đang dùng; nhiều dự án dùng `spring-boot-starter-integration` để có starter phù hợp.

Khi quản lý bằng Spring Cloud BOM tương thích, thường không khai báo riêng `<version>` cho `spring-cloud-function-integration`. **Không tự trộn** artifact của SCF 4.x/5.x với Spring Boot hoặc Spring Integration không tương thích; hãy chọn version train của dự án.

### 3.2. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-function-integration'
}
~~~

Ví dụ Gradle cũng giả định project đã quản lý phiên bản qua Spring Cloud BOM phù hợp.

### 3.3. Kiểm tra sau khi thêm thư viện

Ứng dụng tối thiểu có thể định nghĩa bean:

~~~java
@Bean
IntegrationFlow flow(FunctionFlowBuilder builder) {
    return builder
            .from("inputChannel")
            .apply("someFunction")
            .accept("someConsumer");
}
~~~

Nếu Spring không tạo được bean `FunctionFlowBuilder`, hãy kiểm tra classpath, Spring Boot auto-configuration, phiên bản dependency và việc cấu hình ứng dụng có tắt auto-configuration hay không. Nếu builder có mặt nhưng tên `someFunction` hoặc `someConsumer` không tồn tại trong catalog, lỗi là ở **định nghĩa hàm**, không phải ở việc thiếu message channel.

## 4. API trung tâm: `FunctionFlowBuilder` và `FunctionFlowDefinition`

Spring Cloud Function tạo `FunctionCatalog` chứa các function có thể được truy xuất theo tên. Module integration cung cấp `FunctionFlowBuilder` tự động kết nối với catalog. Các điểm API cần nhớ:

| API | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `FunctionFlowBuilder.from("channelName")` | Bắt đầu flow từ channel (cách dùng quen thuộc của Integration DSL). | `.from("orders.input")` |
| `FunctionFlowBuilder.fromSupplier("supplierName")` | Tìm `Supplier` trong catalog và dùng nó làm nguồn phát message. | `.fromSupplier("orderSource")` |
| `fromSupplier("name", endpointSpec)` | Cấu hình thêm endpoint/poller cho nguồn phát. | `.fromSupplier("orderSource", e -> e.poller(...))` |
| `FunctionFlowDefinition.apply("functionName")` | Tra cứu và áp dụng `Function` trong flow, tiếp tục cho ra dữ liệu. | `.apply("normalizeOrder")` |
| `FunctionFlowDefinition.accept("consumerName")` | Tra cứu `Consumer`, chuyển dữ liệu tới điểm kết thúc xử lý. | `.accept("sendNotification")` |
| `apply("f1|f2")` | Gọi composition của các function có kiểu tương thích. | `.apply("trimText|uppercaseText")` |
| `accept("f1|terminalConsumer")` | Ghép các bước và kết thúc ở một consumer. | `.accept("normalize|save")` |

Sau `from(...)` hay `fromSupplier(...)`, flow dùng `FunctionFlowDefinition`, một extension của Spring Integration DSL, nên vẫn có thể dùng các toán tử Spring Integration thông thường như `channel(...)`, `filter(...)`, `wireTap(...)`, `route(...)` hoặc `log(...)` ở vị trí phù hợp.

Cần chú ý các giới hạn:

- Tên trong `apply(...)` và `accept(...)` phải khớp tên mà **`FunctionCatalog` nhận diện**. Chúng không tự tham chiếu bean trùng tên bất kỳ kiểu nào.
- `apply(...)` cần một function có đầu ra dùng được cho bước kế tiếp. `accept(...)` là bước kết thúc khi flow muốn tiêu thụ kết quả.
- Composition `f1|f2` phải có kiểu đầu ra và đầu vào tương thích. Khi nối `Function<T,R>` với `Consumer<R>`, tên composition có thể được dùng trong `accept(...)`.
- `FunctionCatalog` có thể bọc function để hỗ trợ cơ chế chuyển đổi kiểu/message. Không nên mặc định rằng mọi Java object hoặc header bất kỳ sẽ được chuyển đổi đúng nếu thiếu content type, converter hoặc cấu hình thích hợp.
- Khi flow có rẽ nhánh, nhiều kênh, split/aggregate hoặc side effect, đó vẫn là trách nhiệm của Spring Integration DSL và các endpoint, không phải `FunctionFlowBuilder` tự thêm ngữ nghĩa EIP.

### 4.1. Từ phương thức gọi trực tiếp sang cú pháp theo tên

Không dùng module integration, ta có thể phải tự lookup:

~~~java
Function<String, String> normalize =
        functionCatalog.lookup("normalizeTicket");

// Sau đó truyền normalize vào logic xử lý hoặc một IntegrationFlow.
~~~

Dùng module integration:

~~~java
return functionFlowBuilder
        .from("ticket.input")
        .apply("normalizeTicket")
        .accept("recordTicket");
~~~

Đoạn thứ hai diễn đạt pipeline bằng tên trong catalog và vẫn có thể thêm EIP khác giữa các bước. Đây là cải thiện về khả năng biểu đạt và tổ hợp flow; **không** biến bản thân function thành broker hay HTTP controller.

## 5. Ví dụ thực hành: xử lý phiếu hỗ trợ

### 5.1. Yêu cầu

Giả sử hệ thống nhận mã phiếu hỗ trợ dạng chuỗi:

~~~text
  vip-2026-042
~~~

Quy tắc xử lý:

1. Cắt khoảng trắng và đổi thành chữ hoa.
2. Bỏ những message có mã rỗng sau chuẩn hóa.
3. Nếu mã bắt đầu bằng `VIP-`, đánh dấu `EXPRESS`, ngược lại `STANDARD`.
4. Thu kết quả vào một hàng đợi trong bộ nhớ để minh họa consumer. Môi trường thực tế có thể thay consumer bằng lưu DB hoặc gọi outbound adapter.

Chúng ta tách quy tắc nghiệp vụ thành function để dễ dùng lại, còn filter và đường đi message thuộc Spring Integration.

~~~mermaid
flowchart LR
    A["tickets.input"] --> B["apply normalizeTicket"]
    B --> C{"filter code không rỗng"}
    C -->|Giữ| D["apply classifyTicket"]
    C -->|Loại| X["Discard"]
    D --> E["accept captureTicket"]
    E --> F["Queue kết quả"]
~~~

### 5.2. Định nghĩa function và consumer

Ví dụ dùng Spring Boot 3.x hoặc bản Spring Boot tương thích với release train đã chọn, Java 17+; các import đầy đủ để nhìn rõ kiểu dữ liệu.

~~~java
package example.ticket;

import java.util.Locale;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record TicketDecision(String code, String lane) {}

@Configuration
public class TicketFunctions {

    @Bean
    Function<String, String> normalizeTicket() {
        return input -> input.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, TicketDecision> classifyTicket() {
        return code -> new TicketDecision(
                code,
                code.startsWith("VIP-") ? "EXPRESS" : "STANDARD");
    }

    @Bean
    Queue<TicketDecision> capturedTickets() {
        return new ConcurrentLinkedQueue<>();
    }

    @Bean
    Consumer<TicketDecision> captureTicket(
            Queue<TicketDecision> capturedTickets) {
        return capturedTickets::add;
    }
}
~~~

Hai function biểu diễn các phép biến đổi. `captureTicket` là consumer có **side effect**, do đó trong production cần chính sách lỗi, idempotency, transaction hoặc retry ở đúng nơi nếu chuyển sang database/broker. Chẳng hạn `normalizeTicket` hiện yêu cầu input khác `null`; nếu hệ thống nhận `null`, hãy xác định rõ hợp đồng input và cách báo lỗi.

### 5.3. Định nghĩa IntegrationFlow bằng FunctionFlowBuilder

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
                .apply("normalizeTicket")
                .filter(String.class, code -> !code.isBlank())
                .apply("classifyTicket")
                .accept("captureTicket");
    }
}
~~~

Mỗi dòng trong DSL có vai trò khác nhau:

- `from("tickets.input")`: lấy message từ một Spring Integration channel được đặt tên.
- `apply("normalizeTicket")`: tra cứu function trong catalog để chuẩn hóa payload.
- `filter(...)`: EIP **Message Filter** quyết định bỏ message rỗng; đây là hành vi của Spring Integration, khác với `Function<Boolean>` tự trả về giá trị boolean.
- `apply("classifyTicket")`: biến chuỗi thành `TicketDecision`.
- `accept("captureTicket")`: kết thúc pipeline tại consumer ghi dữ liệu vào queue.

Với `DirectChannel`, xử lý mặc định diễn ra đồng bộ trên cùng thread của bên gửi nếu không cấu hình thêm boundary bất đồng bộ. Việc chọn channel khác, adapter khác hoặc executor có thể thay đổi đặc tính thực thi.

### 5.4. Gửi message thử

Trong một Spring context đã khởi tạo các bean trên:

~~~java
MessageChannel input =
        context.getBean("tickets.input", MessageChannel.class);

input.send(new GenericMessage<>("  vip-2026-042  "));

// capturedTickets.poll() thu được:
// TicketDecision[code=VIP-2026-042, lane=EXPRESS]
~~~

Cần import `org.springframework.messaging.support.GenericMessage`, `org.springframework.messaging.MessageChannel` và một `ApplicationContext` tên `context`; `capturedTickets` ở đây là bean queue đã định nghĩa.

Luồng không tự lắng nghe HTTP hay Kafka: muốn nhận từ bên ngoài cần một inbound adapter hoặc binding đưa message vào `tickets.input`.

### 5.5. Dùng composition cho các bước liền kề

Nếu không cần EIP Filter đứng giữa bước chuẩn hóa và phân loại, có thể rút gọn:

~~~java
@Bean
IntegrationFlow simplerTicketFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.otherInput")
            .accept("normalizeTicket|classifyTicket|captureTicket");
}
~~~

Ở ví dụ này, `tickets.otherInput` là channel khác, phải được khai báo hoặc cấu hình tương ứng trước khi sử dụng. Phép ghép yêu cầu `normalizeTicket` trả `String`, `classifyTicket` nhận `String` và `captureTicket` nhận `TicketDecision`, tương thích với nhau.

**Không được coi hai pipeline hoàn toàn tương đương:** pipeline rút gọn bỏ bước filter, vì vậy chuỗi chỉ gồm khoảng trắng sẽ vẫn đi vào `classifyTicket`. Nếu logic “bỏ dữ liệu rỗng” là bắt buộc, hãy giữ filter hoặc chuyển chính sách kiểm tra sang một thành phần phù hợp.

## 6. Bắt đầu flow từ Supplier với `fromSupplier(...)`

Khi có nguồn dữ liệu do hàm cung cấp, ta có thể để `FunctionFlowBuilder` tra cứu `Supplier` theo tên:

~~~java
@Bean
Supplier<String> scheduledTicket() {
    return () -> "VIP-HEARTBEAT";
}

@Bean
Consumer<String> logTicket() {
    return code -> System.out.println("Received: " + code);
}

@Bean
IntegrationFlow supplierDrivenFlow(FunctionFlowBuilder builder) {
    return builder
            .fromSupplier("scheduledTicket",
                    e -> e.poller(Pollers.fixedDelay(5000)))
            .apply("normalizeTicket")
            .accept("logTicket");
}
~~~

Cần import `java.util.function.Supplier`, `java.util.function.Consumer`, `org.springframework.integration.dsl.Pollers` và các Spring annotation/IntegrationFlow tương ứng. `Pollers.fixedDelay(5000)` định cấu hình khoảng nghỉ giữa các lần poll ở ví dụ này; đơn vị là mili giây theo API DSL.

Trong luồng kiểu polling:

- `Supplier<T>` tạo dữ liệu khi poller gọi nó, thay vì nhận dữ liệu được đẩy từ channel.
- Nhịp gọi, số message mỗi lần poll, thread pool, xử lý lỗi và lifecycle phụ thuộc cấu hình endpoint/poller.
- Với supplier lấy từ queue, cần hiểu cách xử lý giá trị `null` khi không có item: trong các polling source thông thường, `null` nghĩa là không phát message trong lượt poll đó.
- Supplier có side effect (ví dụ lấy và xóa item khỏi queue) cần cân nhắc cơ chế xác nhận và khôi phục nếu downstream thất bại.

`fromSupplier(...)` hữu ích khi muốn dùng các nguồn trong `FunctionCatalog`, ví dụ function nguồn do thư viện hoặc auto-configuration cung cấp. Khi nguồn thực tế là broker/webhook, một inbound adapter chuyên dụng thường giúp xử lý acknowledgement, event lifecycle và thuộc tính transport đầy đủ hơn.

## 7. Kết hợp EIP của Spring Integration với function

Module tích hợp **không thay thế** Java DSL gốc. Bạn có thể đặt những operator EIP ngay giữa các function.

| Nhu cầu | Hướng giải quyết | Phần giữ lại trong function |
| --- | --- | --- |
| Quan sát message mà không đổi đường xử lý | `wireTap(...)` nối tới audit channel. | Biến đổi/kiểm tra payload. |
| Chỉ xử lý một nhóm message | `filter(...)` hoặc `route(...)`. | Hàm tính điều kiện hoặc khóa định tuyến nếu cần tái sử dụng. |
| Đổi thread hoặc buffer message | `channel(...)` với loại channel thích hợp. | Quy tắc nghiệp vụ độc lập lịch chạy. |
| Tách nhiều bản ghi con và ghép lại | `split(...)`, `aggregate(...)` với correlation và release strategy. | Hàm xử lý từng bản ghi, tính kết quả. |
| Gửi message sang hệ thống khác | Outbound adapter/handler hoặc consumer ở biên. | Tính toán nội dung cần gửi. |
| Xử lý lỗi tích hợp | Error channel, retry advice, binder retry/DLQ theo môi trường. | Xác định lỗi nghiệp vụ có thể báo lại. |

Ví dụ thêm Wire Tap khi có một audit channel đã được cấu hình và có consumer cho audit channel:

~~~java
@Bean
IntegrationFlow auditedFlow(FunctionFlowBuilder builder) {
    return builder
            .from("tickets.auditInput")
            .wireTap("tickets.auditChannel")
            .apply("normalizeTicket")
            .accept("logTicket");
}
~~~

Đoạn này **minh họa**, chỉ dùng khi đã tạo `tickets.auditInput`, `tickets.auditChannel` và endpoint nhận ở audit channel. Wire Tap là EIP riêng, không phải một đặc tính của tên composition trong catalog.

### 7.1. Function xử lý payload hay Message?

Hàm thuần:

~~~java
Function<String, String> normalizeTicket = String::trim;
~~~

Hàm cần metadata:

~~~java
Function<Message<String>, Message<String>> addStepHeader =
        message -> MessageBuilder.fromMessage(message)
                .setHeader("processingStep", "normalized")
                .build();
~~~

Cần import `org.springframework.messaging.Message` và `org.springframework.messaging.support.MessageBuilder`. Trường hợp hai, function chủ đích sử dụng message header. Cần kiểm thử xem các header nào được giữ qua những function/adapters đang dùng: header như `contentType`, correlation ID, partition key hay acknowledgement có thể có ngữ nghĩa riêng theo môi trường.

Chữ ký Java generic, payload thực tế và content type cùng ảnh hưởng tới chuyển đổi dữ liệu; không nên dựa vào suy luận kiểu để truyền payload bất kỳ xuyên qua cả chuỗi.

### 7.2. Liên hệ với reactive flow

Spring Cloud Function hỗ trợ các chữ ký reactive như `Function<Flux<T>, Flux<R>>`. Spring Integration có khả năng xây dựng flow reactive thông qua những operator/channel thích hợp, nhưng **không** nên đổi trực tiếp một `Function<T,R>` imperative thành `Function<Flux<T>,Flux<R>>` rồi giả định mọi operator blocking vẫn an toàn.

Khi phối hợp với reactive stream, cần xác định rõ ranh giới subscribe, backpressure, timeout, nguồn phát nhiều phần tử và cách forward lỗi. Tài liệu SCF đưa ra ví dụ nâng cao sử dụng nguồn HTTP, bất đồng bộ và `flux()` channel để minh họa điều này.

## 8. Phân biệt với `spring.cloud.function.definition`

`spring.cloud.function.definition` là thuộc tính thường được các adapter/binder dùng để chọn function hoặc composition cần kích hoạt:

~~~properties
spring.cloud.function.definition=normalizeTicket|classifyTicket
~~~

Trong một `IntegrationFlow` viết bằng `FunctionFlowBuilder`, tên đặt **trực tiếp** trong `apply(...)`/`accept(...)` cũng là chỉ dẫn tra cứu function:

~~~java
return builder
        .from("tickets.input")
        .apply("normalizeTicket|classifyTicket")
        .accept("captureTicket");
~~~

Hai cách đều có thể sử dụng `FunctionCatalog` nhưng **không có cùng tác dụng phụ**:

- Property có ý nghĩa với thành phần đọc nó (ví dụ adapter/binder) và không tự định nghĩa channel trong Spring Integration.
- Tên truyền vào DSL mô tả function mà flow cụ thể sẽ gọi, không có nghĩa mọi inbound adapter sẽ tự động trỏ đến flow ấy.
- Nếu sử dụng cả Spring Cloud Stream và Spring Integration trong một ứng dụng, hãy thiết kế rõ adapter/binding nào là nguồn thật để tránh vô tình xử lý một sự kiện hai lần.

## 9. Kiểm thử và chẩn đoán

### 9.1. Unit test function thuần

Các bean `normalizeTicket` và `classifyTicket` có thể được kiểm thử không cần Spring context:

~~~java
TicketFunctions config = new TicketFunctions();

String normalized =
        config.normalizeTicket().apply(" vip-007 ");

TicketDecision result =
        config.classifyTicket().apply(normalized);

assertEquals("VIP-007", result.code());
assertEquals("EXPRESS", result.lane());
~~~

Thêm các trường hợp `"  "`, `"standard-123"` và input không hợp lệ theo hợp đồng đã chọn. Đây là phần kiểm chứng **quy tắc nghiệp vụ**.

### 9.2. Integration test end-to-end của flow nội bộ

Trong test Spring Boot, có thể lấy message channel và queue kết quả qua injection:

~~~java
@SpringBootTest
class TicketFlowTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    Queue<TicketDecision> capturedTickets;

    @Test
    void routesVipTicketThroughCatalogFunctions() {
        MessageChannel input =
                context.getBean("tickets.input", MessageChannel.class);

        input.send(new GenericMessage<>("  vip-007  "));

        TicketDecision result = capturedTickets.poll();
        assertNotNull(result);
        assertEquals("VIP-007", result.code());
        assertEquals("EXPRESS", result.lane());
    }
}
~~~

Các import thường dùng gồm `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.context.ApplicationContext`, `org.springframework.messaging.MessageChannel`, `org.springframework.messaging.support.GenericMessage`, `org.junit.jupiter.api.Test` và các static assertion của JUnit 5. Test giả định cấu hình ứng dụng đã quét `TicketFunctions` cùng `TicketIntegration` và dự án có `spring-boot-starter-test`.

Vì demo dùng `DirectChannel` cùng consumer thêm kết quả vào queue, có thể xác nhận ngay sau `send(...)`. Nếu thay bằng channel bất đồng bộ hoặc broker, dùng cơ chế chờ có giới hạn và kiểm tra delivery semantics của môi trường tương ứng; không giữ giả định đồng bộ.

### 9.3. Bảng chẩn đoán nhanh

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Không inject được `FunctionFlowBuilder` | Thiếu module integration, Spring auto-configuration chưa chạy, dependency version không tương thích. |
| Không tìm thấy `normalizeTicket` | Tên bean/function sai, function không đăng ký vào catalog hoặc catalog không được khởi tạo như kỳ vọng. |
| `accept(...)` báo không có consumer phù hợp | Kiểu/định nghĩa cuối chuỗi không đúng, đang dùng consumer chưa được đăng ký. |
| `ClassCastException` hay lỗi converter | Payload, Java generic và content type thực tế không khớp; cần converter/mapper hoặc contract rõ ràng. |
| Không có message vào flow | Sai channel đích, inbound adapter chưa nối, `Supplier` chưa được poll hay poller không chạy. |
| Supplier được gọi liên tục hoặc quá chậm | Kiểm tra cấu hình poller, delay, scheduler và số message mỗi lần poll. |
| Dữ liệu bị xử lý trùng | Kiểm tra nhiều inbound binding, redelivery, số consumer/flow, và tính idempotent của xử lý cuối. |
| Exception không đi vào error channel như mong đợi | Kiểm tra đồng bộ/bất đồng bộ, error handler/advice, adapter và đường propagation của exception. |

Các lỗi chính sách như giá trị đầu vào không hợp lệ nên được phân biệt với lỗi hạ tầng (timeout, mất kết nối) để quyết định retry hợp lý; retry mãi cùng một input lỗi dữ liệu có thể tạo vòng lặp không cần thiết.

## 10. Các nguyên tắc triển khai

1. **Giữ function dễ tái sử dụng.** Tập trung vào nghiệp vụ, giới hạn phụ thuộc trực tiếp với transport hoặc message channel.
2. **Dùng catalog name một cách nhất quán.** Với nhiều bean cùng tên gần giống nhau, việc truyền tên sai vào DSL dễ tạo lỗi tại thời điểm dựng/chạy flow.
3. **Chọn DSL theo nhu cầu thực.** Nếu chỉ cần `f.andThen(g)`, một composition có thể đủ. Nếu cần EIP, bổ sung `IntegrationFlow` một cách có chủ đích.
4. **Tách điểm đầu và điểm cuối.** `fromSupplier(...)` là nguồn polling; `from(...)` nhận từ channel; `apply(...)` xử lý và tiếp tục; `accept(...)` chốt bằng consumer.
5. **Chú ý metadata của message.** Header có thể cần cho routing, correlation, tracing và acknowledgement; kiểm tra khả năng bảo toàn header trên từng adapter.
6. **Thiết kế retry/idempotency ở đúng ranh giới.** `FunctionFlowBuilder` không cung cấp bảo đảm giao nhận exactly-once hay transaction phân tán chỉ bằng việc gọi `apply(...)`.
7. **Giữ dependency theo một release train.** Kiểm tra sự tương thích giữa Spring Boot, Spring Cloud Function, Spring Integration và adapter thực tế của ứng dụng.
8. **Kiểm thử theo ba tầng.** Unit test function; test catalog/composition; integration test flow và điểm kết nối thực.

### Câu hỏi tự kiểm tra

- Khi nào nên dùng `fromSupplier("name")` thay vì `from("channelName")`?
- Vì sao `apply("f1|f2")` không thay thế được router hay aggregator của EIP?
- Nếu một function nhận `Message<Order>`, bạn cần kiểm thử gì ngoài payload?
- Vì sao bật `spring.cloud.function.definition` chưa đủ để tạo một broker consumer?
- Nếu message bị xử lý hai lần sau lỗi mạng, đâu là lớp phù hợp để đảm bảo idempotency?

## 11. Tài liệu tham khảo

- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): giới thiệu `spring-cloud-function-integration`, `FunctionFlowBuilder` và ví dụ DSL chính thức.
- [Spring Integration — java.util.function Interfaces Support](https://docs.spring.io/spring-integration/reference/functions-support.html): cách Spring Integration dùng `Supplier` và `Function` trong endpoint/flow.
- [Spring Cloud Function — Programming model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, định nghĩa hàm, composition, chuyển đổi dữ liệu và chức năng liên quan.

**Tổng kết:** `spring-cloud-function-integration` bổ sung API DSL để một `IntegrationFlow` truy xuất các hàm trong `FunctionCatalog` bằng tên, đặc biệt với `FunctionFlowBuilder.fromSupplier(...)`, `apply(...)` và `accept(...)`. Nhờ đó, logic viết bằng `Supplier`, `Function`, `Consumer` tiếp tục độc lập với cách gọi qua HTTP, sự kiện hoặc serverless, trong khi Spring Integration đảm nhiệm đường đi thông điệp, các EIP và cấu hình vận hành cụ thể.
