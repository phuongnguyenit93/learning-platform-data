# IntegrationFlow và khai báo luồng bằng Java DSL

## 1. IntegrationFlow giải quyết vấn đề gì?

Trong module **Spring Boot Integration**, một ứng dụng thường phải nhận yêu cầu HTTP, kiểm tra dữ liệu, truy cập cơ sở dữ liệu, gọi dịch vụ ngoài, đẩy thông điệp lên broker hoặc gửi email. Nếu viết tất cả bước này trong một service lớn, luồng xử lý nhanh chóng khó kiểm soát: logic nghiệp vụ trộn với chuyển đổi dữ liệu, routing, retry, concurrency và cách giao tiếp với hệ thống ngoài.

**Spring Integration** triển khai các mẫu **Enterprise Integration Patterns (EIP)**. Thay vì bắt các thành phần phụ thuộc trực tiếp vào nhau, ta nối chúng qua **message**, **channel** và **endpoint**. Với **Java DSL**, giao diện `IntegrationFlow` cho phép khai báo chuỗi endpoint ngay trong cấu hình Java có type checking, hỗ trợ IDE và được Spring quản lý vòng đời.

Xét nhu cầu tiếp nhận đơn hàng:

1. Controller hoặc thành phần đầu vào gửi lệnh `OrderCommand`.
2. Luồng kiểm tra số lượng, chuẩn hóa mã hàng.
3. Luồng gọi dịch vụ nghiệp vụ giữ hàng.
4. Kết quả `OrderResult` được trả về cho phía gửi.
5. Một sự kiện đã được xác nhận có thể được chuyển sang luồng gửi email hoặc cập nhật read model bất đồng bộ.

~~~mermaid
flowchart LR
    A["HTTP controller / Gateway"] --> B["orders.submit"]
    B --> C["Filter"]
    C --> D["Transformer"]
    D --> E["Service Activator"]
    E --> F["OrderResult"]
    F --> A
    E -. "Sự kiện sau commit" .-> G["Broker / luồng thông báo"]
~~~

Các bước trong sơ đồ không nhất thiết tạo thread, hàng đợi hay transaction mới. **Cấu hình channel và endpoint quyết định cách thực thi**; riêng việc viết `IntegrationFlow` không tự làm luồng trở thành bất đồng bộ hoặc bền vững.

## 2. Các thành phần và trách nhiệm

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Message<T>` | Đóng gói `payload` cùng `headers` để truyền giữa endpoint. | Payload `OrderCommand`, header `correlationId`. |
| `MessageChannel` | Điểm kết nối giữa producer và consumer. | `orders.submit` hoặc `notifications.in`. |
| `MessageHandler` / `Service Activator` | Thực hiện tác dụng nghiệp vụ, có thể tạo reply. | Gọi `OrderService.reserve(...)`. |
| `Transformer` | Chuyển đổi biểu diễn payload. | Chuẩn hóa SKU, chuyển DTO sang command nội bộ. |
| `Filter` | Cho phép hoặc loại thông điệp theo điều kiện. | Loại lệnh có số lượng không hợp lệ. |
| `Router` | Chọn kênh đích theo nội dung hoặc header. | Event `CREATED` sang email, `CANCELLED` sang thông báo hủy. |
| `Splitter` và `Aggregator` | Chia tập phần tử rồi gom kết quả theo correlation/release strategy. | Chia lô chi tiết đơn thành từng dòng và gom kết quả. |
| `Gateway` | Tạo ranh giới gọi Java/HTTP với hệ thống message; có thể request/reply. | `OrderGateway.submit(...)`. |
| `IntegrationFlow` | Khai báo chuỗi các endpoint và channel được Spring đăng ký. | `orderSubmissionFlow`. |
| Channel adapter / gateway adapter | Kết nối flow với Kafka, RabbitMQ, JDBC, HTTP, file, mail... | Inbound message adapter và outbound gateway. |

Một message có thể có header `id`, `timestamp`, `replyChannel`, `errorChannel` và header nghiệp vụ. **Message là envelope**, không bảo đảm đối tượng payload bên trong bất biến; khi qua nhiều thread, tránh mutate chung một object rồi dựa vào thứ tự thực thi.

Các EIP có thể ghép với nhau, nhưng mỗi bước cần có **hợp đồng dữ liệu**: nhận payload gì, có thay payload/header không, trả reply hay chỉ tạo side effect, lỗi được phát hiện ở đâu.

## 3. Chuẩn bị một ứng dụng Spring Boot

Ví dụ dùng **Java 17+, Spring Boot 3.x và Spring Integration 6.x**. Với Maven, dependency tối thiểu là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Starter cung cấp lõi Spring Integration và tích hợp với cấu hình Spring Boot. Adapter cho HTTP, JDBC, AMQP, Kafka, mail... có **dependency và cấu hình riêng**; chỉ thêm khi flow thực sự giao tiếp với hệ thống tương ứng. Khi cần kiểm thử bằng JUnit, bổ sung `spring-boot-starter-test` và module test liên quan của Spring Integration nếu dùng các tiện ích chuyên biệt.

Tổ chức mã nguồn mẫu:

~~~text
src/main/java/com/example/integration/
├── IntegrationApplication.java
├── order/
│   ├── OrderCommand.java
│   ├── ValidatedOrder.java
│   ├── OrderResult.java
│   ├── OrderGateway.java
│   ├── OrderHandler.java
│   └── OrderFlowConfiguration.java
└── notification/
    ├── OrderEvent.java
    └── NotificationFlowConfiguration.java
~~~

Nếu tạo gateway thông qua interface đánh dấu `@MessagingGateway`, bật scanning phù hợp cho interface đó:

~~~java
package com.example.integration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class IntegrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IntegrationApplication.class, args);
    }
}
~~~

`@IntegrationComponentScan` tìm các interface gateway trong package được quét, tạo proxy để mã Java bình thường gọi vào flow. Nếu không muốn dùng interface gateway, ứng dụng cũng có thể gửi message tới channel qua `MessagingTemplate` hoặc kết nối trực tiếp qua inbound adapter. Với Spring Boot, các bean `IntegrationFlow` được nhận diện và đăng ký bởi hạ tầng Spring Integration.

## 4. Ví dụ đầy đủ: nhận lệnh bằng Gateway, xử lý bằng Java DSL

### 4.1. Định nghĩa hợp đồng dữ liệu

Các type dưới đây đặt trong từng file Java tương ứng; `record` phù hợp với DTO/command bất biến ở ranh giới:

~~~java
package com.example.integration.order;

public record OrderCommand(String orderId, String sku, int quantity) {}
~~~

~~~java
package com.example.integration.order;

public record ValidatedOrder(String orderId, String sku, int quantity) {}
~~~

~~~java
package com.example.integration.order;

public record OrderResult(String orderId, String status) {}
~~~

Một gateway khai báo đầu vào cần gửi đến:

~~~java
package com.example.integration.order;

import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface OrderGateway {
    @Gateway(requestChannel = "orders.submit")
    OrderResult submit(OrderCommand command);
}
~~~

Mỗi lần gọi `submit`, proxy tạo message, đưa payload vào channel `orders.submit` và chờ reply để ánh xạ thành `OrderResult`. Với kênh đồng bộ như `DirectChannel`, lời gọi thường chạy cùng thread của caller. Khi thay channel/endpoint thành bất đồng bộ, cần thiết lập và kiểm soát timeout phản hồi phù hợp với yêu cầu người gọi.

### 4.2. Tách tác vụ nghiệp vụ thành một handler

~~~java
package com.example.integration.order;

import org.springframework.stereotype.Service;

@Service
public class OrderHandler {
    public OrderResult reserve(ValidatedOrder order) {
        // Ví dụ minh họa: ứng dụng thật sẽ gọi miền nghiệp vụ,
        // ghi dữ liệu hoặc điều phối một adapter ngoài.
        return new OrderResult(order.orderId(), "ACCEPTED");
    }
}
~~~

`ACCEPTED` ở đây chỉ là giá trị do handler mô phỏng trả về, không đại diện mặc định cho việc database đã commit hay cổng thanh toán đã xác nhận. Ở hệ thống thật, tên trạng thái cần phản ánh đúng mức cam kết (`RECEIVED`, `PENDING`, `RESERVED`...).

### 4.3. Khai báo IntegrationFlow

~~~java
package com.example.integration.order;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderSubmissionFlow(OrderHandler handler) {
        return IntegrationFlow.from("orders.submit")
                .filter(
                        OrderCommand.class,
                        command -> command.quantity() > 0,
                        spec -> spec.throwExceptionOnRejection(true))
                .transform(
                        OrderCommand.class,
                        command -> new ValidatedOrder(
                                command.orderId(),
                                command.sku().trim(),
                                command.quantity()))
                .handle(
                        ValidatedOrder.class,
                        (payload, headers) -> handler.reserve(payload))
                .get();
    }
}
~~~

Giải thích từng mắt xích:

1. `IntegrationFlow.from("orders.submit")` tạo một **điểm đầu vào** và liên kết flow với channel có tên `orders.submit`. Nếu chưa có channel cùng tên, hạ tầng có thể tạo channel phù hợp theo DSL; vì vậy phải quan sát kiểu channel thực tế thay vì tự suy đoán.
2. `filter(OrderCommand.class, ...)` kiểm tra số lượng. `throwExceptionOnRejection(true)` biến việc từ chối thành ngoại lệ để caller biết rõ input bị loại. Nếu không cấu hình như vậy, Filter có thể bỏ message bị loại mà không tạo reply; với request/reply điều này có thể dẫn tới việc gateway chờ tới timeout.
3. `transform(OrderCommand.class, ...)` thay payload bằng `ValidatedOrder` đã chuẩn hóa SKU. Trong ví dụ, `sku` phải khác `null`; ở ứng dụng thật cần xác thực input trước khi gọi `trim()` để trả lỗi hợp lệ thay vì `NullPointerException`.
4. `handle(ValidatedOrder.class, (payload, headers) -> ...)` đóng vai trò **Service Activator**, gọi handler nghiệp vụ với payload đã đổi kiểu.
5. `get()` kết thúc định nghĩa DSL, trả về `IntegrationFlow`. Khi Spring đăng ký flow, các endpoint trung gian và channel cần thiết được dựng thành bean hạ tầng.
6. Giá trị `OrderResult` từ handler trở thành reply. Gateway request/reply dùng cơ chế `replyChannel` của message để trả kết quả cho caller; ví dụ này không cần tạo response channel thủ công.

Flow trông tuyến tính nhưng có thể biến thành topology rẽ nhánh hoặc gọi adapter. Đừng biến các lambda trong DSL thành nơi chứa SQL, giao dịch, vòng lặp HTTP hoặc quy tắc nghiệp vụ lớn: giữ chúng ngắn để dễ kiểm thử và quan sát.

### 4.4. Gọi flow từ API bên ngoài

Controller có thể inject `OrderGateway` như một service thông thường:

~~~java
package com.example.integration.order;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderGateway gateway;

    public OrderController(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @PostMapping
    public ResponseEntity<OrderResult> submit(@RequestBody OrderCommand command) {
        return ResponseEntity.ok(gateway.submit(command));
    }
}
~~~

Với HTTP thực tế, cần có Bean Validation/kiểm tra dữ liệu, ánh xạ ngoại lệ thành `400` hoặc mã lỗi nghiệp vụ phù hợp, xác thực người dùng và xử lý timeout. Ví dụ chỉ thể hiện ranh giới giữa HTTP controller và flow; `ResponseEntity.ok(...)` không phải hợp đồng chuẩn cho mọi thao tác đặt hàng.

## 5. Các thao tác Java DSL thường dùng

DSL là cách tổ hợp các EIP bằng chuỗi phương thức trên `IntegrationFlowDefinition`:

| DSL | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `from(...)` | Chỉ định input channel, adapter hoặc nguồn phát sinh message. | Nguồn pollable có thể cần cấu hình poller. |
| `channel(...)` | Chỉ định channel trung gian hoặc thay đổi dispatch/concurrency. | Kiểu channel ảnh hưởng threading và transaction. |
| `filter(...)` | Loại các message không thỏa điều kiện. | Chọn xử lý từ chối: bỏ, ném lỗi, discard channel. |
| `transform(...)` | Đổi payload (và có thể header nếu trả một message mới). | Giữ contract rõ, kiểm tra null và serialization. |
| `route(...)` | Chọn một hoặc nhiều nhánh dựa trên giá trị/điều kiện. | Phải có chính sách cho giá trị chưa biết. |
| `split(...)` | Chia collection/stream thành các message con. | Cần quản lý correlation và sequence khi gom lại. |
| `aggregate(...)` | Gom các message liên quan thành kết quả. | Cần release strategy, timeout và message store khi lưu trạng thái. |
| `enrichHeaders(...)` | Thêm metadata vào header. | Tránh ghi PII, token hoặc giá trị quá lớn. |
| `publishSubscribeChannel(...)` | Phát một message tới nhiều subscriber. | Không tự cung cấp lưu trữ bền vững hoặc giao nhận tới subscriber offline. |
| `handle(...)` | Gọi service, message handler hoặc outbound adapter. | Phân biệt handler có reply và handler chỉ tạo side effect. |
| `bridge()` | Nối các channel khi cần chia pipeline thành các đoạn. | Không tạo thay đổi payload; hữu ích khi nối topology. |
| `get()` | Hoàn tất định nghĩa `IntegrationFlow`. | Hạ tầng Spring tạo endpoint khi bean được đăng ký. |

Với một luồng dài, nên đặt tên các channel có ý nghĩa nghiệp vụ: `orders.submit`, `orders.validated`, `orders.confirmed`. Nếu một đoạn cần tách thành nhiều flow, có thể dùng một channel chung làm điểm nối. Việc dùng channel name rõ ràng cũng hỗ trợ logging, tracing và kiểm thử.

## 6. Router: phân nhánh theo loại sự kiện

Một hệ thống có thể nhận nhiều sự kiện đơn hàng rồi chọn workflow khác nhau. Ví dụ:

~~~java
package com.example.integration.notification;

public record OrderEvent(String eventId, String type, String orderId) {}
~~~

~~~java
package com.example.integration.notification;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class NotificationFlowConfiguration {

    @Bean
    IntegrationFlow routeOrderEvents() {
        return IntegrationFlow.from("order.events.in")
                .route(
                        OrderEvent.class,
                        OrderEvent::type,
                        mapping -> mapping
                                .channelMapping("CREATED", "order.events.created")
                                .channelMapping("CANCELLED", "order.events.cancelled"))
                .get();
    }

    @Bean
    IntegrationFlow createdEventFlow(NotificationHandler handler) {
        return IntegrationFlow.from("order.events.created")
                .handle(handler, "notifyCreated")
                .get();
    }

    @Bean
    IntegrationFlow cancelledEventFlow(NotificationHandler handler) {
        return IntegrationFlow.from("order.events.cancelled")
                .handle(handler, "notifyCancelled")
                .get();
    }
}
~~~

Ở ví dụ này, `NotificationHandler` là bean ứng dụng có hai phương thức `notifyCreated(OrderEvent)` và `notifyCancelled(OrderEvent)`. Các handler có thể chỉ tạo side effect mà không cần reply. Event loại `CREATED` được chuyển tới channel tương ứng; event `CANCELLED` đi sang nhánh còn lại.

**Quyết định bắt buộc khi sử dụng router:** Nếu nhận event có `type` chưa được hỗ trợ, xử lý như thế nào? Cần chọn rõ route mặc định, channel lỗi hoặc từ chối theo hợp đồng. Không để một loại sự kiện mới bị bỏ qua âm thầm trong luồng nghiệp vụ quan trọng. Nếu cần gửi cùng event đến **nhiều** consumer độc lập, dùng `publishSubscribeChannel` hoặc broker pub/sub phù hợp thay vì giả định router luôn broadcast.

## 7. Channel quyết định đồng bộ, bất đồng bộ và mức độ bền vững

Một flow viết bằng cùng cú pháp DSL có thể có hành vi thời gian khác nhau chỉ vì cách chọn channel.

| Channel | Đặc điểm thực thi | Phù hợp với | Lưu ý |
| --- | --- | --- | --- |
| `DirectChannel` | Dispatcher gọi handler trong thread của bên gửi, đồng bộ. | Pipeline request/reply ngắn, cần dùng transaction hiện tại khi phù hợp. | Handler chậm trực tiếp làm caller chậm; lỗi có thể lan trở lại. |
| `ExecutorChannel` | Chuyển handler sang executor, tách thread. | Bước xử lý không cần chặn caller ngay lúc gửi. | Không tự bền vững, không tự truyền transaction/thread-local; cần giới hạn hàng chờ. |
| `QueueChannel` | Lưu message vào queue để consumer poll. | Tách producer/consumer và điều tiết tốc độ xử lý. | Queue mặc định trong bộ nhớ; muốn khôi phục qua restart cần thiết kế message store bền vững. |
| `PublishSubscribeChannel` | Phân phối tới nhiều subscriber, mặc định thường thực thi đồng bộ nếu không cấu hình executor. | Fan-out nội bộ tiến trình. | Subscriber offline không tự được phát lại; lỗi một handler có thể ảnh hưởng luồng dispatch. |
| Broker channel adapter | Đưa/nhận message qua broker ngoài ứng dụng. | Giao tiếp liên dịch vụ, cần durability/ack/retry phù hợp. | Bảo đảm phụ thuộc broker, transaction, ack và thiết kế idempotency. |

Để dùng executor do Spring quản lý:

~~~java
import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AuditFlowConfiguration {

    @Bean
    ThreadPoolTaskExecutor auditExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("audit-flow-");
        return executor;
    }

    @Bean
    IntegrationFlow auditFlow(
            ThreadPoolTaskExecutor auditExecutor,
            AuditHandler handler) {
        return IntegrationFlow.from("audit.in")
                .channel(spec -> spec.executor(auditExecutor))
                .handle(handler, "store")
                .get();
    }
}
~~~

`AuditHandler` ở đây là một service của ứng dụng có phương thức `store(AuditEvent)`. Với `ExecutorChannel`, bước xử lý phía sau channel chạy trên worker thread của executor khi được dispatch thành công. `send(...)` hoàn tất không có nghĩa tác vụ đã được ghi vào database hoặc thông báo đã tới đích. Nếu pool và queue đầy, cần chính sách từ chối/backpressure; số liệu `active thread` và `queue depth` phải được theo dõi. Các giá trị 2/4/100 chỉ minh họa, cần cân chỉnh theo latency và tải thực tế.

**Ranh giới transaction:** Một transaction từ request thread không tự chuyển sang thread của `ExecutorChannel`. Nếu handler bất đồng bộ cần ghi JPA, hãy mở transaction ở service handler hoặc listener phía sau channel. Không thực hiện một update quan trọng chỉ bằng cách gửi vào executor nội bộ rồi coi đó là ghi nhận bền vững.

## 8. Input/output adapter và Gateway

Một `IntegrationFlow` có thể bắt đầu hoặc kết thúc tại nhiều công nghệ tích hợp:

- **HTTP**: inbound gateway nhận request, outbound gateway gọi dịch vụ ngoài và nhận response. Áp dụng timeout, map status code và xác thực phù hợp.
- **JDBC/JPA**: adapter polling hoặc message-driven component phối hợp với database; transaction thuộc về tài nguyên được quản lý và phạm vi poller/handler.
- **AMQP/Kafka**: inbound adapter nhận message từ broker, outbound adapter publish event/command. Phải hiểu ack, retry, partition/ordering và schema của broker đã chọn.
- **File/SFTP**: lấy file, parse, split bản ghi, lưu kết quả. Nên thiết kế marker/checkpoint và bảo đảm idempotency để tránh xử lý một file nhiều lần.
- **Mail**: outbound mail adapter gửi thông báo; lỗi SMTP và thành công nghiệp vụ được xử lý riêng.

Khác biệt quan trọng giữa hai loại gateway/adapter:

| Thành phần | Hành vi kỳ vọng |
| --- | --- |
| **Inbound channel adapter** | Tạo message gửi vào flow, thường one-way; nguồn có thể là polling/event. |
| **Outbound channel adapter** | Nhận message rồi gửi đi, thường one-way, không tạo reply nghiệp vụ. |
| **Inbound gateway** | Biến request từ bên ngoài thành message rồi chờ phản hồi từ flow để trả lại. |
| **Outbound gateway** | Gửi yêu cầu ra hệ thống ngoài và đưa response trở lại flow. |

Ví dụ, nếu flow cần gửi HTTP tới Inventory để biết tình trạng giữ hàng trước khi trả kết quả, một **outbound gateway** phù hợp hơn **outbound channel adapter** chỉ gửi thông điệp một chiều. Nếu chỉ thông báo sự kiện `OrderConfirmed` sang broker sau commit, một outbound adapter là đủ khi hợp đồng không đòi response nghiệp vụ ngay trong flow.

Adapter không thay đổi bản chất transaction xuyên hệ thống. Gọi một HTTP endpoint trong transaction JPA không kéo transaction đó sang dịch vụ đích. Khi database commit nhưng broker publish bị lỗi hoặc tiến trình chết, cần cân nhắc **transactional outbox** thay vì mặc định hai thao tác là atomic.

## 9. Header, correlation và chia/gom message

Trong pipeline, header giúp truyền metadata tách khỏi payload. Ví dụ:

| Header | Cách dùng | Tránh nhầm |
| --- | --- | --- |
| `replyChannel` | Địa chỉ phản hồi cho gateway request/reply. | Không phải nơi lưu kết quả bền vững. |
| `errorChannel` | Kênh nhận một số lỗi xử lý theo cơ chế error flow. | Không bảo đảm mọi ngoại lệ được gửi tới đây trong mọi kiểu channel. |
| `correlationId` | Nhóm các message thuộc cùng thao tác khi split/aggregate. | Không thay thế trace ID, operation ID hay idempotency key. |
| `sequenceNumber`, `sequenceSize` | Thông tin vị trí và số lượng phần tử khi split/gom. | Chưa đủ nếu thông điệp có thể thiếu hoặc đến muộn. |
| `eventId`, `schemaVersion` (header ứng dụng) | Dedupe, tương thích hợp đồng, xử lý message version. | Không trùng với `MessageHeaders.ID` do framework tạo. |

Một flow tách dòng hàng rồi gom lại có thể mô tả:

~~~mermaid
flowchart LR
    A["Order: 3 lines"] --> S["Splitter"]
    S --> L1["Line 1"]
    S --> L2["Line 2"]
    S --> L3["Line 3"]
    L1 --> V["Validate/Enrich"]
    L2 --> V
    L3 --> V
    V --> G["Aggregator"]
    G --> R["Kết quả tổng hợp"]
~~~

`Splitter` có thể thêm correlation và sequence headers hỗ trợ `Aggregator` nhận diện các message cùng nhóm. Tuy nhiên, nếu có nhiều luồng xử lý song song, message đến không đều, lỗi giữa chừng hoặc số lượng phần tử không biết trước, aggregator cần **release strategy**, **group timeout**, **message store** và chính sách cho nhóm chưa hoàn chỉnh. Dùng mặc định không có nghĩa một nhóm sẽ luôn được giải phóng trong mọi tình huống.

Với message đi qua broker, cần xác định header nào được map sang giao thức và có được giữ nguyên qua serialization hay không. Không dựa vào header Java object không serializable; dùng ID ổn định, định dạng thời gian, schema version rõ ràng và giới hạn kích thước message.

## 10. Xử lý lỗi, retry và luồng không đồng bộ

Spring Integration có hạ tầng xử lý lỗi, advice và error channel, nhưng **đường đi của ngoại lệ phụ thuộc endpoint/channel**:

1. **Luồng đồng bộ qua `DirectChannel`:** ngoại lệ trong filter/handler thường lan về bên gửi; HTTP controller hoặc gateway có thể chuyển thành phản hồi lỗi.
2. **Luồng bất đồng bộ qua executor/poller:** lỗi phát sinh trên thread khác; tùy cấu hình, hạ tầng có thể chuyển `ErrorMessage` tới error channel. Phía gửi ban đầu không nhận được trực tiếp ngoại lệ xử lý về sau.
3. **Inbound broker adapter:** cơ chế retry/ack/redelivery/DLQ cần phối hợp với adapter và broker; việc ném lỗi không tự đồng nghĩa đã đưa message vào DLQ.
4. **Outbound HTTP/SMTP:** phân biệt lỗi tạm thời với lỗi cố định; giới hạn retry/backoff và tránh lặp side effect khi kết quả chưa rõ.

### 10.1. Thiết kế retry theo bản chất lỗi

| Loại lỗi | Chính sách thường phù hợp |
| --- | --- |
| Payload thiếu trường, sai phiên bản schema | Từ chối có lý do, đưa vào kênh xử lý lỗi/điều tra; retry y nguyên thường không giúp ích. |
| HTTP 429, timeout mạng, broker unavailable | Retry có giới hạn với backoff/jitter, timeout và circuit breaker phù hợp. |
| Unique constraint do message trùng | Dedupe theo `eventId`/idempotency key; xác nhận đã xử lý nếu đó là bản sao hợp lệ. |
| Handler có bug hoặc không tương thích schema | DLQ/quarantine, sửa lỗi rồi replay có kiểm soát. |
| Lỗi sau khi hệ thống ngoài đã commit nhưng trước khi trả lời | Tra cứu trạng thái/idempotency; retry mù có thể tạo tác dụng kép. |

Khi chọn `RequestHandlerRetryAdvice` hoặc retry của adapter, cần biết **vị trí đặt retry**: áp cho handler nào, exception nào được retry, có bao nhiêu lần và lỗi cuối cùng đi đâu. Retry của một handler có side effect phải sử dụng ID ổn định để an toàn khi nhận trùng.

### 10.2. Error channel và error message

`ErrorMessage` là một message có payload biểu diễn lỗi (thường là `MessagingException`) và có thể giữ bản gốc/failedMessage để hỗ trợ chẩn đoán. Có thể xây flow chuyên xử lý lỗi hoặc cấu hình channel lỗi dành riêng cho một endpoint. Khi dùng channel toàn cục `errorChannel`, đừng giả định nó trở thành “dead-letter queue” bền vững: channel nội bộ và broker DLQ là hai khái niệm khác nhau.

Các handler lỗi nên ghi **loại lỗi, endpoint, message ID, correlation ID và thời điểm**. Chỉ log dữ liệu cần thiết, không ghi token, credential hoặc payload chứa thông tin nhạy cảm. Nếu muốn replay, lưu bản tin theo hợp đồng bền vững và quản lý số lần thử/chế độ retry bằng storage phù hợp, không chỉ dựa vào log.

## 11. Transaction và xử lý trùng trong IntegrationFlow

Một flow có thể gọi repository JPA trong `@Transactional` của service, nhưng điều đó **không tự mở rộng transaction** sang HTTP, Redis hoặc broker ngoài. Ví dụ:

~~~mermaid
sequenceDiagram
    participant Producer as Order Service
    participant DB as Orders DB
    participant Broker as Message Broker
    participant Consumer as Email Consumer
    Producer->>DB: Transaction cập nhật Order + ghi Outbox
    DB-->>Producer: Commit
    Producer->>Broker: Outbox relay publish event
    Broker-->>Producer: Ack
    Broker->>Consumer: OrderConfirmed
    Consumer->>Consumer: Kiểm tra eventId, gửi email
~~~

Khi cần bảo đảm sự kiện được phát sau khi dữ liệu Order đã commit, một lựa chọn phổ biến là **transactional outbox**:

1. Ghi thay đổi nghiệp vụ và một bản ghi outbox trong **cùng transaction database**.
2. Relay đọc outbox và publish qua adapter tới broker, đánh dấu thành công theo acknowledgement phù hợp.
3. Consumer xử lý idempotent; nếu relay chết sau publish nhưng trước khi ghi dấu, event có thể được gửi lại.
4. Theo dõi tuổi bản ghi outbox, retry count, backlog, DLQ và thực hiện đối soát khi cần.

Điều này giữ đúng ranh giới: Spring Integration giúp ghép channel và endpoint; transaction manager/JPA bảo vệ giao dịch cục bộ; broker bảo đảm việc vận chuyển theo cấu hình; **idempotency và reconciliation** bảo vệ nghiệp vụ trước message lặp hoặc trạng thái không chắc chắn.

Nếu dùng `ExecutorChannel` hoặc adapter polling, transaction cần đặt tại vị trí phù hợp với thread tiêu thụ. Nếu cần kiểm soát offset/ack khi đọc Kafka hoặc RabbitMQ, phải kết hợp với chính sách container/adapter, tránh ack quá sớm trước khi thay đổi nghiệp vụ được ghi bền vững.

## 12. Kiểm thử Java DSL và các luồng tích hợp

Kiểm thử nên phân tách ba mức:

| Mức | Điều xác minh | Phương pháp |
| --- | --- | --- |
| **Unit** | Lambda/filter/transformer và quy tắc nghiệp vụ trả đúng kết quả. | Test trực tiếp hàm/domain service. |
| **Integration trong ApplicationContext** | Bean `IntegrationFlow` được đăng ký, gateway/channel/routing chạy đúng; reply và lỗi hoạt động. | `@SpringBootTest`, gọi gateway, assert kết quả và nhánh route. |
| **End-to-end với hệ thống ngoài** | DB/broker/HTTP adapter, transaction, ack, retry, replay và schema. | Testcontainers, mock HTTP server hoặc sandbox tương ứng. |

Với flow `orderSubmissionFlow` ở trên, một kiểm thử request/reply đơn giản:

~~~java
package com.example.integration.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderFlowIntegrationTest {
    @Autowired
    OrderGateway gateway;

    @Test
    void submitValidOrderReturnsReply() {
        OrderResult result = gateway.submit(
                new OrderCommand("order-101", " SKU-01 ", 2));
        assertEquals("order-101", result.orderId());
        assertEquals("ACCEPTED", result.status());
    }

    @Test
    void invalidQuantityIsRejected() {
        assertThrows(
                RuntimeException.class,
                () -> gateway.submit(new OrderCommand("order-102", "SKU-02", 0)));
    }
}
~~~

Ở dự án thật, nên assert **loại ngoại lệ/ngữ nghĩa lỗi cụ thể** sau khi đã thống nhất cách mapping error, thay vì chỉ `RuntimeException` như bài kiểm tra cơ bản này. Các ca cần bổ sung gồm:

- **Filter:** input invalid không gọi handler; reply/exception đúng hợp đồng gateway.
- **Transformer:** SKU được chuẩn hóa; null/blank, encoding và field bắt buộc được xử lý rõ.
- **Router:** `CREATED`/`CANCELLED` đi đúng nhánh; event lạ có chính sách đã định nghĩa.
- **Thread boundary:** flow có executor không dựa vào transaction/thread-local của request; timeout và queue saturation có kết quả kiểm soát.
- **Retry:** lỗi tạm thời retry đúng số lần; lỗi cố định bị loại/dlq; không tạo side effect trùng.
- **Transactional outbox:** crash trước/sau commit và trước/sau publish không làm mất sự kiện đã cam kết; consumer idempotent.
- **Contract:** event có schema version, correlation/event ID; consumer cũ không bị phá bởi thay đổi tương thích.

Trong test, với channel bất đồng bộ nên dùng cơ chế chờ có timeout và kiểm tra điều kiện cuối, tránh `Thread.sleep(...)` cố định. Test chỉ chạy với mock handler không chứng minh được bảo đảm ack/transaction thật của broker; cần test tích hợp riêng cho phần adapter và database.

## 13. Quan sát, hiệu năng và triển khai

Để vận hành flow nhiều endpoint, nên thu thập:

- **Latency theo endpoint và end-to-end:** thời gian từ inbound tới phản hồi; p95/p99 khi có deadline.
- **Thông lượng và lỗi:** số message gửi/nhận/xử lý, tỷ lệ fail, retry, reject, drop và timeout.
- **Backpressure:** chiều dài queue, số thread đang bận, số request chờ, consumer lag và message cũ nhất.
- **Độ tin cậy:** DLQ, duplicate rate, số outbox event chưa publish, số job cần đối soát.
- **Truy vết:** correlation ID, trace ID, event ID, origin và destination channel; tránh dùng một ID cho mọi mục đích.

Spring Integration có hỗ trợ cơ chế theo dõi message và observation/metrics khi được cấu hình cùng hệ sinh thái Micrometer/Actuator. Cần xem phiên bản Spring Integration và Boot hiện dùng để lựa chọn observation, message history, channel interceptors hoặc tích hợp tracing, tránh phát log payload đầy đủ trong sản xuất.

Một số lỗi thiết kế lặp lại:

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Coi mọi `IntegrationFlow` đều async | Gateway bị chậm hoặc timeout bất ngờ. | Chọn channel/threading rõ, đặt latency budget. |
| Dùng `ExecutorChannel` như queue bền vững | Mất tác vụ khi ứng dụng chết. | Dùng broker hoặc persistent message store nếu yêu cầu durability. |
| Filter bỏ message của gateway mà không reply | Caller chờ đến timeout. | Ném lỗi có kiểm soát hoặc trả kết quả từ chối rõ ràng. |
| Router thiếu nhánh không biết | Event mới bị xử lý sai hoặc mất. | Định nghĩa route mặc định, error handling và contract test. |
| Retry side effect không có idempotency | Gửi email/thu tiền/ghi DB trùng. | Ổn định operation key, inbox/outbox, đối soát. |
| Trộn mapping nghiệp vụ lớn vào DSL lambda | Khó test, khó debug và khó version. | Tách handler/service/DTO, để DSL thể hiện topology. |
| Bật async giữa transaction rồi mong rollback toàn bộ | DB commit lệch hoặc handler chạy ngoài transaction. | Thiết kế transaction tại consumer và nhất quán cuối cùng. |

## 14. Cách chọn cấu trúc flow trong dự án thật

Khi thiết kế một IntegrationFlow mới, thực hiện theo trình tự:

1. **Định nghĩa hợp đồng message:** payload, version, header cần thiết, dữ liệu nhạy cảm và tên channel.
2. **Vẽ các bước EIP:** input, filter/validate, transform, route, handle và output; xác định đâu là nghiệp vụ, đâu là adapter.
3. **Quyết định đồng bộ/bất đồng bộ ở từng ranh giới:** người gửi có cần kết quả ngay không, có cho phép trạng thái `PENDING` không, thông điệp có phải được lưu bền vững không.
4. **Xác định transaction và idempotency:** owner dữ liệu, điểm commit, retry, dedupe, cách xử lý timeout sau khi đối tác đã commit.
5. **Xử lý đường lỗi:** lỗi validation, lỗi tạm thời, retry exhaustion, DLQ, cảnh báo và replay.
6. **Kiểm thử và quan sát:** dùng kiểm thử context và kiểm thử tích hợp với adapter thật, thu thập metric theo channel/endpoint để phát hiện backlog.

**IntegrationFlow và Java DSL** giúp diễn đạt luồng tích hợp Spring Boot bằng các thành phần có trách nhiệm rõ ràng, dễ tái sử dụng và quan sát. Sự đúng đắn của một luồng vẫn nằm ở hợp đồng dữ liệu, ranh giới transaction, cơ chế truyền thông điệp, khả năng xử lý trùng và cách hệ thống phục hồi sau lỗi. Chọn channel, gateway, router và adapter dựa trên những yêu cầu đó thì DSL mới phản ánh chính xác hành vi của hệ thống trong thực tế.
