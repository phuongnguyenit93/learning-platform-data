# Xử lý lỗi và metadata tại ranh giới luồng tích hợp

## 1. Tại sao cần quan tâm tới lỗi và metadata?

**Spring Cloud Function (SCF)** giúp đóng gói nghiệp vụ bằng `Supplier<T>`, `Function<T,R>`, `Consumer<T>`. Các hàm được tra cứu/ghép qua `FunctionCatalog` và có thể dùng lại trong HTTP, luồng sự kiện, serverless hoặc mã Java thông thường. Chữ ký `Function<OrderSubmitted,OrderDecision>` diễn đạt phép tính nghiệp vụ nhưng không quy định nguồn dữ liệu, điểm nhận kết quả hay cách xử lý khi có lỗi.

**Spring Integration** nối các hàm đó thành một `IntegrationFlow` thông qua Message Channel, Transformer, Router, Poller, Gateway và những Enterprise Integration Patterns (EIP) khác. Tại **ranh giới tích hợp**, hệ thống không chỉ cần payload hợp lệ mà còn phải biết thông điệp thuộc yêu cầu nào, lỗi được báo cho ai, dữ liệu có thể được phát lại hay không.

Có hai vấn đề xuyên suốt bài học:

1. **Metadata:** quản lý và truyền `traceId`, correlation ID, `replyChannel`, `errorChannel`, `contentType` và header của adapter/broker mà không làm lẫn chúng vào logic nghiệp vụ.
2. **Error handling:** phân biệt lỗi truyền ngược về caller khi xử lý đồng bộ với lỗi được chuyển thành `ErrorMessage` khi chạy qua poller, executor hay một cơ chế tích hợp bất đồng bộ.

Sau bài học, bạn có thể thiết kế một flow gọi `FunctionCatalog`, kiểm tra bảo toàn header qua transformer, đọc `ErrorMessage`, phân loại lỗi nghiệp vụ/hạ tầng và viết test phù hợp từng ranh giới.

~~~mermaid
flowchart LR
    A["HTTP / broker / serverless"] --> B["Adapter"]
    B --> C["Message: payload + headers"]
    C --> D["IntegrationFlow"]
    E["FunctionCatalog"] -. lookup .-> F["Function xử lý nghiệp vụ"]
    D --> F
    F --> G["Consumer / outbound adapter"]
    F -. "lỗi đồng bộ" .-> H["Caller / Gateway"]
    D -. "lỗi async hoặc poller" .-> I["ErrorMessage"]
    I --> J["errorChannel"]
    J --> K["Error handler / lưu lỗi / DLQ"]
~~~

## 2. Phân biệt payload và message envelope

Một `Message<T>` của Spring Messaging gồm **payload** và **headers**. Chẳng hạn:

~~~text
Message<OrderSubmitted>
  payload:
    orderId = "DH-107"
    totalVnd = 1500000
  headers:
    id = ...
    timestamp = ...
    traceId = "trace-9a1"
    businessCorrelationId = "order-DH-107"
    replyChannel = ... (nếu có gateway request/reply)
    errorChannel = ... (nếu có cấu hình đích báo lỗi)
~~~

`Message<T>` là hợp đồng của `org.springframework.messaging.Message`, còn `MessageHeaders` định nghĩa các metadata. Một domain function chỉ nhận `OrderSubmitted` sẽ nhìn thấy payload; function nhận `Message<OrderSubmitted>` có thể thấy cả headers.

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Payload | Dữ liệu nghiệp vụ cần xử lý. | `OrderSubmitted(orderId,totalVnd)` |
| Header nghiệp vụ | Giá trị phục vụ correlation, phiên bản sự kiện, phân loại... | `businessCorrelationId`, `schemaVersion` |
| Header quan sát | Liên kết trace/log giữa các dịch vụ. | `traceId` hoặc trace context chuẩn |
| Header Spring Messaging | Định danh message và đích reply/error. | `MessageHeaders.ID`, `TIMESTAMP`, `REPLY_CHANNEL`, `ERROR_CHANNEL` |
| EIP metadata | Hỗ trợ chia/gộp và điều phối message. | Correlation key, sequence number/size |
| Header transport | Tùy HTTP, Kafka, RabbitMQ hay serverless runtime. | Partition, delivery attempt, acknowledgement |

**Không dùng header `id` của Spring Messaging làm idempotency key nghiệp vụ.** Khi message được tạo lại, ID có thể khác trong khi đó vẫn là cùng một giao dịch. Dùng `eventId` ổn định, `orderId` cộng event version hoặc một business key phù hợp.

### 2.1. Tạo message có metadata ứng dụng

~~~java
Message<OrderSubmitted> message = MessageBuilder
        .withPayload(new OrderSubmitted(" dh-107 ", 1_500_000))
        .setHeader("traceId", "trace-9a1")
        .setHeader("businessCorrelationId", "order-DH-107")
        .build();
~~~

Cần import:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

Có thể giữ metadata ở envelope thay vì thêm `traceId` vào mọi domain record. Tuy vậy, nếu correlation ID là một phần của nghiệp vụ và cần tồn tại bền vững, hãy cân nhắc đặt nó trong payload hoặc mô hình lưu trữ phù hợp.

### 2.2. Header nào do framework sở hữu?

Spring Integration sử dụng `replyChannel` và `errorChannel` để điều phối phản hồi và lỗi trong những ngữ cảnh hỗ trợ. Splitter/Aggregator có thể tạo correlation/sequence headers. Adapter của broker có thể mang acknowledgement handle, delivery tag hoặc partition information. Không tự ghi đè metadata hệ thống hoặc chuyển nguyên mọi header ra ngoài khi không hiểu ý nghĩa của chúng.

Metadata có thể được chuyển đổi/lọc khi đi qua adapter. Header như `traceId` do ứng dụng đặt không đồng nghĩa tự động có distributed tracing đầy đủ; tracing còn phụ thuộc instrumentation và cơ chế propagation.

## 3. Bảo toàn metadata khi gọi FunctionCatalog

Giả sử catalog quản lý:

~~~java
@Bean
Function<OrderSubmitted, OrderDecision> classifyOrder() {
    return order -> {
        // Validation và phân loại dựa trên payload.
        return new OrderDecision(order.orderId(), "PRIORITY");
    };
}
~~~

Có thể tra cứu và dùng function làm transformer:

~~~java
Function<OrderSubmitted, OrderDecision> classify =
        catalog.lookup("classifyOrder");

return IntegrationFlow.from("orders.input")
        .transform(OrderSubmitted.class, classify::apply)
        .channel("orders.output")
        .get();
~~~

`transform(OrderSubmitted.class, ...)` nhận **payload**, tạo đầu ra mới và Spring Integration tiếp tục truyền một message phù hợp. Những header thích hợp thông thường được kế thừa qua transformer theo cơ chế của framework. Dù vậy, **không được giả định mọi header đều bất biến** qua các loại transformer, wrapper, message converter và outbound adapter.

Khi business function không cần metadata, cách xử lý payload thuần giúp nó dễ dùng lại trong HTTP, sự kiện hoặc serverless. Header vẫn được kiểm soát ở integration layer.

### 3.1. Khi function cần chính Message<T>

Nếu cần thêm header `processingStage`:

~~~java
@Bean
Function<Message<OrderSubmitted>, Message<OrderSubmitted>> markStage() {
    return incoming -> MessageBuilder.fromMessage(incoming)
            .setHeader("processingStage", "VALIDATED")
            .build();
}
~~~

`MessageBuilder.fromMessage(...)` có thể tạo message mới dựa trên thông điệp cũ và cập nhật một số header. Với function nhận toàn bộ message, endpoint gọi nó phải truyền **envelope**, không phải chỉ `message.getPayload()`. Java DSL có overload `transform(Message.class, ...)` dành cho trường hợp cần xử lý toàn bộ message.

Ví dụ cách tạo một processor message-aware:

~~~java
Function<Message<OrderSubmitted>, Message<OrderSubmitted>> stage =
        catalog.lookup("markStage");

return IntegrationFlow.from("orders.markInput")
        .transform(Message.class, incoming -> {
            // Xác định đúng kiểu payload tại ranh giới.
            OrderSubmitted payload =
                    (OrderSubmitted) incoming.getPayload();

            Message<OrderSubmitted> typed = MessageBuilder
                    .withPayload(payload)
                    .copyHeaders(incoming.getHeaders())
                    .build();

            return stage.apply(typed);
        })
        .channel("orders.markOutput")
        .get();
~~~

Đây là biến thể minh họa độc lập; channel đầu/ra phải được cấu hình. Việc tái tạo message có thể làm thay đổi `id`/`timestamp`, vì vậy test nên khẳng định các header **có ý nghĩa với contract** chứ không mặc định giữ mọi metadata do framework tạo.

### 3.2. Kiểm soát header trước khi ra khỏi hệ thống

| Tình huống | Cách xử lý |
| --- | --- |
| Transformer nội bộ thay đổi payload | Giữ trace/correlation cần thiết theo contract. |
| Gửi request đến dịch vụ khác | Chỉ map những header được phép, ưu tiên allowlist. |
| Splitter/Aggregator | Giữ hoặc sinh correlation/sequence theo quy tắc EIP. |
| Gateway request/reply | Đảm bảo đường reply không làm mất thông tin trả lời. |
| Gửi qua broker | Kiểm tra header mapper, serializer và loại metadata transport. |
| Logging/audit | Không log token, cookie, thông tin xác thực hoặc payload nhạy cảm. |

Spring Integration có `headerFilter(...)` để loại những header cụ thể. Tuy nhiên, bỏ `replyChannel` hoặc correlation metadata khi downstream còn dùng chúng có thể gây mất phản hồi hoặc lỗi ghép nhóm.

## 4. Hai đường đi của exception

Không có một cơ chế `errorChannel` duy nhất áp dụng cho mọi kiểu endpoint.

### 4.1. DirectChannel đồng bộ

~~~mermaid
sequenceDiagram
    participant Caller
    participant Channel as DirectChannel
    participant Flow as IntegrationFlow
    participant Function
    Caller->>Channel: send(message)
    Channel->>Flow: dispatch cùng thread
    Flow->>Function: apply(payload)
    Function--xFlow: throw exception
    Flow--xCaller: exception lan qua call stack
~~~

Khi handler chạy trên thread của caller qua `DirectChannel`, exception thường truyền về lời gọi `send(...)` hoặc messaging gateway. Nó có thể được bọc trong `MessagingException` hay exception chuyên biệt của transformer; gateway có thể unwrap nguyên nhân gốc theo hợp đồng.

**Chỉ gắn header `errorChannel` hoặc đăng ký một global error channel không khiến mọi lỗi đồng bộ tự động chuyển vào kênh đó.** Nếu HTTP/gateway cần response lỗi, tầng caller/adapter phải map exception hoặc dùng chính sách error flow đã thiết kế riêng.

### 4.2. Poller và xử lý bất đồng bộ

~~~mermaid
sequenceDiagram
    participant Scheduler as Poller / Executor
    participant Handler as Function / Handler
    participant Errors as MessagePublishingErrorHandler
    participant Channel as errorChannel
    participant Sink as Error subscriber
    Scheduler->>Handler: xử lý message
    Handler--xScheduler: exception
    Scheduler->>Errors: chuyển cho error handler
    Errors->>Channel: ErrorMessage(Throwable)
    Channel->>Sink: xử lý và quan sát
~~~

Spring Integration hỗ trợ xuất lỗi thành `ErrorMessage`. Trong những bối cảnh dùng `MessagePublishingErrorHandler`, destination lỗi được giải quyết tương tự reply: ưu tiên header `MessageHeaders.ERROR_CHANNEL` của message đang xử lý khi phù hợp, sau đó là global channel mang tên `errorChannel`.

Các task poller chuẩn sử dụng error publishing của Spring Integration scheduler theo cấu hình framework. Nếu dự án dùng scheduler hoặc error handler tùy chỉnh, cần bảo đảm cơ chế publish vẫn được gắn chính xác. Một số adapter/binder có hệ thống xử lý lỗi riêng.

| Bối cảnh | Hành vi điển hình | Nơi đặt chính sách |
| --- | --- | --- |
| `DirectChannel` đồng bộ | Exception lan về caller. | Caller, gateway, HTTP exception handler. |
| Poller chuẩn | ErrorMessage có thể được publish tới error channel. | Poller/error handler và error flow. |
| `ExecutorChannel` hoặc task async | Sender có thể đã rời đi, cần đường lỗi bất đồng bộ. | ErrorChannel/handler của channel và executor. |
| Kafka/RabbitMQ inbound | Ack, redelivery, retry, dead-letter theo binder/adapter. | Broker binding và consumer error policy. |
| Serverless event | Runtime/adapter quyết định timeout, retry và phản hồi lỗi. | Adapter cùng event source configuration. |

## 5. Bên trong ErrorMessage

`ErrorMessage` là `Message<Throwable>`, thuộc `org.springframework.messaging.support.ErrorMessage`. Payload của nó chứa một `Throwable`, có thể là `MessagingException` bao bọc nguyên nhân gốc. Khi có đủ ngữ cảnh, exception có `failedMessage` hoặc `ErrorMessage` có `originalMessage`.

~~~text
ErrorMessage
  payload: MessagingException hoặc Throwable
    cause: IllegalArgumentException / IOException / ...
    failedMessage: Message<?> (có thể null)
  originalMessage: Message<?> (có thể null)
  headers: ...
~~~

Ví dụ đọc thông tin một cách an toàn:

~~~java
void inspect(ErrorMessage error) {
    Throwable failure = error.getPayload();
    Message<?> failed = null;

    if (failure instanceof MessagingException messaging) {
        failed = messaging.getFailedMessage();
    }
    if (failed == null) {
        failed = error.getOriginalMessage();
    }

    Object correlation = failed == null ? null
            : failed.getHeaders().get("businessCorrelationId");

    System.out.println(failure.getClass().getSimpleName());
    System.out.println("Correlation: " + correlation);
}
~~~

Cần import `org.springframework.messaging.MessagingException`. Đừng giả định `getOriginalMessage()` hoặc `getFailedMessage()` luôn có dữ liệu: ví dụ lỗi xảy ra trước khi message hình thành, hoặc wrapper không mang đầy đủ thông điệp tại thời điểm tạo error message.

Global `errorChannel` mặc định thường là `PublishSubscribeChannel` với subscriber ghi log của framework. Có thể bổ sung subscriber để thu thập lỗi; trong production nên kiểm soát chính sách lỗi riêng cho từng flow và tránh xử lý trùng hoặc log dữ liệu nhạy cảm.

## 6. Ví dụ chạy: cùng function ở flow đồng bộ và polling

Ta xây ứng dụng phân loại đơn hàng bằng **một function duy nhất**:

~~~text
Đường A:
Message<OrderSubmitted> với traceId/correlation
  → orders.syncInput
  → FunctionCatalog.lookup("classifyOrder")
  → Transformer
  → TrackedDecision trong syncResults

Đường B:
Queue<OrderSubmitted> pendingOrders
  → Supplier<OrderSubmitted> pendingOrderSource
  → Poller mỗi 250ms
  → FunctionFlowBuilder.apply("classifyOrder")
  → Consumer<OrderDecision> capturePolledDecision

Đường lỗi:
polling task gặp exception
  → ErrorMessage
  → errorChannel
  → errorAudit
  → observedErrors
~~~

Các queue bên dưới chỉ phục vụ minh họa, không có persistence/transaction.

### 6.1. Dependency

Với Java 17+ và Spring Boot/Spring Cloud tương thích, đoạn Maven sau giả định dự án đã cấu hình Spring Boot parent và Spring Cloud BOM:

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

`spring-cloud-function-integration` cung cấp `FunctionFlowBuilder` để gọi `fromSupplier`, `apply` và `accept` theo tên trong catalog. Dự án chỉ cần lookup thủ công từ `FunctionCatalog` không bắt buộc sử dụng module DSL này.

### 6.2. Contract và function

Tạo `src/main/java/example/ordering/OrderFunctions.java`:

~~~java
package example.ordering;

import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderSubmitted(String orderId, long totalVnd) {}

record OrderDecision(String orderId, String lane) {}

record TrackedDecision(
        OrderDecision decision,
        String traceId,
        String businessCorrelationId) {}

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderSubmitted, OrderDecision> classifyOrder() {
        return order -> {
            if (order == null
                    || order.orderId() == null
                    || order.orderId().isBlank()
                    || order.totalVnd() <= 0) {
                throw new IllegalArgumentException(
                        "Đơn hàng không hợp lệ");
            }

            String normalized = order.orderId().strip()
                    .toUpperCase(Locale.ROOT);
            String lane = order.totalVnd() >= 1_000_000
                    ? "PRIORITY" : "STANDARD";

            return new OrderDecision(normalized, lane);
        };
    }
}
~~~

Function không biết channel, header, retry, REST endpoint hoặc broker. Hai luồng bên dưới đều tra cứu tên `classifyOrder` trong `FunctionCatalog`; một kết quả nghiệp vụ sẽ được sử dụng theo cách khác nhau ở từng đường đi.

### 6.3. Spring Integration configuration

Tạo `src/main/java/example/ordering/OrderIntegration.java`:

~~~java
package example.ordering;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.cloud.function.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

@Configuration
class OrderIntegration {

    @Bean("orders.syncInput")
    MessageChannel syncInput() {
        return new DirectChannel();
    }

    @Bean("syncResults")
    BlockingQueue<TrackedDecision> syncResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("pendingOrders")
    BlockingQueue<OrderSubmitted> pendingOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("polledResults")
    BlockingQueue<OrderDecision> polledResults() {
        return new LinkedBlockingQueue<>();
    }

    @Bean("observedErrors")
    BlockingQueue<ErrorMessage> observedErrors() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    Supplier<OrderSubmitted> pendingOrderSource(
            @Qualifier("pendingOrders")
            BlockingQueue<OrderSubmitted> queue) {
        return queue::poll;
    }

    @Bean
    Consumer<OrderDecision> capturePolledDecision(
            @Qualifier("polledResults")
            BlockingQueue<OrderDecision> results) {
        return results::add;
    }

    @Bean
    IntegrationFlow synchronousOrders(
            FunctionCatalog catalog,
            @Qualifier("syncResults")
            BlockingQueue<TrackedDecision> results) {

        Function<OrderSubmitted, OrderDecision> classify =
                Objects.requireNonNull(
                        catalog.lookup("classifyOrder"),
                        "Không tìm thấy classifyOrder");

        return IntegrationFlow.from("orders.syncInput")
                .transform(OrderSubmitted.class, classify::apply)
                .handle(OrderDecision.class, (decision, headers) -> {
                    results.add(new TrackedDecision(
                            decision,
                            (String) headers.get("traceId"),
                            (String) headers.get("businessCorrelationId")));
                    return null;
                })
                .get();
    }

    @Bean
    IntegrationFlow polledOrders(FunctionFlowBuilder builder) {
        return builder
                .fromSupplier("pendingOrderSource",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(250)
                                        .maxMessagesPerPoll(1)))
                .apply("classifyOrder")
                .accept("capturePolledDecision");
    }

    @Bean
    IntegrationFlow errorAudit(
            @Qualifier("observedErrors")
            BlockingQueue<ErrorMessage> errors) {
        return IntegrationFlow.from("errorChannel")
                .handle(message -> {
                    errors.add((ErrorMessage) message);
                })
                .get();
    }
}
~~~

Tạo `src/main/java/example/ordering/OrderApplication.java`:

~~~java
package example.ordering;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

**Giải thích:** `synchronousOrders` dùng `FunctionCatalog.lookup("classifyOrder")` rồi truyền kết quả vào Spring Integration transformer. Nó nhận message từ `DirectChannel` và giữ `traceId` cùng `businessCorrelationId` cho handler phía sau. `polledOrders` dùng `FunctionFlowBuilder` lấy supplier theo tên, gọi cùng business function và kết thúc bằng consumer.

`errorAudit` chỉ thu những error message **đã được publish** vào global `errorChannel`. Không được suy luận rằng mọi exception từ `orders.syncInput` cũng xuất hiện trong `observedErrors`.

## 7. Thử truyền metadata qua flow đồng bộ

~~~java
MessageChannel input =
        context.getBean("orders.syncInput", MessageChannel.class);

Message<OrderSubmitted> request = MessageBuilder
        .withPayload(new OrderSubmitted(" dh-107 ", 1_500_000))
        .setHeader("traceId", "trace-9a1")
        .setHeader("businessCorrelationId", "order-DH-107")
        .build();

input.send(request);
~~~

`context` là `ApplicationContext` đã được inject hoặc lấy từ Spring context. Với `DirectChannel`, các endpoint trong ví dụ chạy đồng bộ, nên `syncResults` có:

~~~text
TrackedDecision(
    decision = OrderDecision("DH-107", "PRIORITY"),
    traceId = "trace-9a1",
    businessCorrelationId = "order-DH-107"
)
~~~

Metadata đi qua transformer mà function không cần trực tiếp đọc nó. Nếu adapter đã bỏ header từ lúc ingress, downstream không thể khôi phục chính xác `traceId` chỉ dựa trên payload.

### 7.1. Một lỗi validation ở DirectChannel

~~~java
Message<OrderSubmitted> invalid = MessageBuilder
        .withPayload(new OrderSubmitted(" ", 100_000))
        .setHeader("traceId", "trace-invalid")
        .build();

input.send(invalid); // dự kiến ném RuntimeException
~~~

Function ném `IllegalArgumentException`. Spring Integration có thể bọc ngoại lệ này trong `MessageTransformationException` hoặc `MessagingException`; caller cần xử lý nguyên nhân theo contract. Việc dựa vào kiểu wrapper chính xác nên được kiểm chứng theo phiên bản.

Cơ chế này khác với `errorChannel`: sender ở đây còn trên cùng call stack khi lỗi xảy ra, nên nhận exception trực tiếp.

## 8. Thử lỗi qua Poller và errorChannel

Thêm một đơn không hợp lệ vào nguồn polling:

~~~java
pendingOrders.add(new OrderSubmitted(" ", 500_000));
~~~

`pendingOrderSource` trả giá trị đó ở lần poll kế tiếp; `classifyOrder` ném exception. Với task scheduler/error publisher mặc định của Spring Integration, một `ErrorMessage` có thể được gửi vào `errorChannel`. Subscriber `errorAudit` ghi lỗi vào `observedErrors` để quan sát.

~~~text
pendingOrders.poll()
    → classifyOrder
    → exception
    → MessagePublishingErrorHandler
    → ErrorMessage
    → errorChannel
    → errorAudit / observedErrors
~~~

Không lấy `observedErrors.poll()` ngay sau khi thêm đơn: lịch poll có thể chưa kích hoạt. Dùng `poll(timeout)` trong test.

### 8.1. Kiểm tra cause và message gốc

~~~java
ErrorMessage error =
        observedErrors.poll(3, TimeUnit.SECONDS);

assertNotNull(error);
Throwable failure = error.getPayload();

Message<?> failedMessage = null;
if (failure instanceof MessagingException messaging) {
    failedMessage = messaging.getFailedMessage();
}
if (failedMessage == null) {
    failedMessage = error.getOriginalMessage();
}
~~~

Trong test/source production, cần import `TimeUnit`, `MessagingException` và `Message`. Một số lỗi xảy ra khi chưa tạo message hoặc wrapper mất thông điệp gốc, vì vậy `failedMessage` có thể `null`. Đừng chỉ dựa vào trường này để điều tra thất bại; lưu correlation/event ID vào một nguồn quan sát bền vững.

### 8.2. Vấn đề item đã rời khỏi source

`pendingOrders::poll` **loại item khỏi queue** trước khi consumer xử lý xong. Nếu function ném lỗi hoặc process dừng, item không tự quay lại. `errorChannel` chỉ giúp truyền/quan sát lỗi, không phải cơ chế ack/redelivery bền vững.

Trong production cần source có checkpoint/ack/transaction hoặc cơ chế redrive. Với broker, hãy dựa vào hợp đồng của adapter/binder, không lấy hành vi queue trong RAM làm bảo đảm delivery.

## 9. Phân loại lỗi và chính sách phục hồi

| Loại lỗi | Ví dụ | Chính sách đề xuất |
| --- | --- | --- |
| Validation/business | Mã đơn rỗng, tổng tiền không hợp lệ. | Trả lỗi nghiệp vụ, từ chối hoặc đưa sang nhánh quarantine; không retry vô hạn. |
| Schema/conversion | JSON sai kiểu, thiếu field, content type không hợp lệ. | Báo lỗi ở biên, lưu ngữ cảnh an toàn và sửa contract/converter. |
| Hạ tầng tạm thời | DB bị ngắt ngắn hạn, API đối tác timeout. | Retry có giới hạn, backoff, timeout và metrics. |
| Vĩnh viễn | Quyền truy cập bị từ chối, định danh đối tác không tồn tại. | Không retry mãi; chuyển xử lý thủ công/DLQ nếu phù hợp. |
| Cấu hình/programming | Sai tên `FunctionCatalog.lookup(...)`, null bất ngờ. | Fail fast, sửa code/cấu hình, bổ sung test. |
| Delivery trùng | Broker redeliver hoặc client gửi lại request. | Idempotency theo khóa nghiệp vụ bền vững. |

Đối với lỗi nghiệp vụ dự kiến, có thể biểu diễn một kết quả rõ ràng thay vì ném exception cho mọi trường hợp:

~~~java
sealed interface OrderOutcome
        permits Accepted, Rejected {}

record Accepted(OrderDecision decision) implements OrderOutcome {}

record Rejected(String code, String reason) implements OrderOutcome {}
~~~

Đây là **thiết kế thay thế** cho chữ ký `Function<OrderSubmitted,OrderDecision>` trong ví dụ. Nếu chọn kiểu `OrderOutcome`, cần thay các handler downstream và có thể dùng EIP Router phân nhánh `Accepted`/`Rejected`.

### 9.1. Retry nằm ở đâu?

- **Handler/advice:** retry lời gọi hệ thống ngoài khi có lỗi tạm thời.
- **Polling adapter:** quyết định xử lý tiếp/lập lịch lại sau lỗi; phải xét item đã bị lấy khỏi source.
- **Broker binder:** redelivery, retry và DLQ theo broker.
- **Serverless runtime:** retry theo cấu hình event source/runtime.

Có thể có nhiều lớp retry chồng lên nhau. Nên xác định một chính sách tổng thể về deadline, số lần thử, backoff/jitter, circuit breaker và idempotency. Retry cùng một `orderId` có thể khiến consumer ghi DB/gửi email hai lần nếu thiếu chống trùng.

### 9.2. ErrorChannel khác Dead-Letter Queue

**`errorChannel`** là message channel trong ứng dụng Spring Integration, thường mang `ErrorMessage`. **DLQ** thường là destination lưu message lỗi của broker, có khả năng giữ/replay theo công cụ vận hành của broker. Hai khái niệm liên quan nhưng không thể thay thế nhau: subscribe `errorChannel` không tự lưu bền message hay tạo một Kafka DLQ.

### 9.3. Idempotency và transaction

Không sử dụng `MessageHeaders.ID` làm khóa chống trùng. Khóa thích hợp thường là `eventId` hoặc `orderId + eventVersion`. Để hỗ trợ nhiều instance, cần lưu trạng thái đã xử lý trong kho bền vững có unique constraint/transaction hoặc chiến lược atomic tương đương.

~~~text
Khi nhận event:
    key = eventId (ổn định qua redelivery)
    nếu key COMPLETED → trả kết quả cũ hoặc ack
    nếu key PROCESSING → xử lý concurrency/recovery
    nếu chưa có → claim atomically rồi thực hiện nghiệp vụ
    sau khi thành công → đánh dấu COMPLETED
~~~

Đây là mô hình ý tưởng, không phải thuật toán exactly-once hoàn chỉnh. Khi có nhiều hệ thống cùng tham gia, cần thiết kế transaction hoặc bù trừ phù hợp.

## 10. Metadata ở biên HTTP, broker và serverless

### 10.1. HTTP

Một request HTTP mang body (JSON) và headers riêng. Adapter cần chuyển body sang `OrderSubmitted`, map trace context theo chuẩn và ánh xạ lỗi tới HTTP status/error schema. Không giả định rằng function ném `IllegalArgumentException` thì mọi HTTP adapter mặc nhiên trả cùng một status code. Timeout và việc retry của client cũng cần được thiết kế rõ.

### 10.2. Broker

Kafka/RabbitMQ có message key, offset/partition hoặc delivery tag/ack. Binder hay inbound adapter quyết định những header nào xuất hiện trong Spring Messaging. Một consumer phải xử lý được redelivery và không cố chuyển nguyên acknowledgement object sang HTTP/serverless. Kiểm thử mapping header, serialization, DLQ và idempotency trên adapter thực tế.

### 10.3. Serverless

Serverless runtime có request/event ID, deadline, retry và logging riêng. Adapter quyết định cách biến event thành lời gọi function. Nếu muốn cùng logic tái sử dụng, function chỉ cần domain object; metadata của runtime được xử lý ở một lớp bao quanh hoặc trong `Message<T>` khi có contract rõ.

### 10.4. Routing theo header của SCF

Spring Cloud Function có `RoutingFunction` và hỗ trợ routing theo header `spring.cloud.function.definition` hoặc `spring.cloud.function.routing-expression` trong những ngữ cảnh phù hợp. Đây là **routing function** khác với EIP Content-Based Router của Spring Integration (chọn **message channel**). Nếu nguồn không tin cậy điều khiển routing, phải giới hạn tập function có thể gọi, tránh chấp nhận biểu thức tùy ý và kiểm tra đầu vào.

## 11. Kiểm thử đúng ranh giới

### 11.1. Unit test business function

~~~java
OrderFunctions functions = new OrderFunctions();

OrderDecision decision = functions.classifyOrder()
        .apply(new OrderSubmitted(" dh-107 ", 1_500_000));

assertEquals("DH-107", decision.orderId());
assertEquals("PRIORITY", decision.lane());

assertThrows(IllegalArgumentException.class, () ->
        functions.classifyOrder()
                .apply(new OrderSubmitted(" ", 100)));
~~~

Kiểm thêm ngưỡng đúng `1_000_000`, dưới ngưỡng, `null` và tổng tiền không hợp lệ. Unit test này không kiểm tra message headers hoặc error publishing.

### 11.2. Integration test cho header qua transformer

~~~java
@SpringBootTest(classes = OrderApplication.class)
class OrderMetadataTest {

    @Autowired ApplicationContext context;

    @Autowired
    @Qualifier("syncResults")
    BlockingQueue<TrackedDecision> results;

    @Test
    void preservesBusinessHeaders() {
        results.clear();

        MessageChannel input =
                context.getBean("orders.syncInput", MessageChannel.class);

        input.send(MessageBuilder
                .withPayload(new OrderSubmitted(" dh-107 ", 1_500_000))
                .setHeader("traceId", "trace-9a1")
                .setHeader("businessCorrelationId", "order-DH-107")
                .build());

        TrackedDecision actual = results.poll();
        assertNotNull(actual);
        assertEquals("DH-107", actual.decision().orderId());
        assertEquals("trace-9a1", actual.traceId());
        assertEquals("order-DH-107",
                actual.businessCorrelationId());
    }

    @Test
    void synchronousErrorReachesCaller() {
        MessageChannel input =
                context.getBean("orders.syncInput", MessageChannel.class);

        assertThrows(RuntimeException.class, () ->
                input.send(MessageBuilder.withPayload(
                        new OrderSubmitted(" ", 100))
                        .build()));
    }
}
~~~

Cần JUnit 5, Spring Boot Test, `@Autowired`, `@Qualifier`, `ApplicationContext`, `BlockingQueue`, `MessageChannel`, `MessageBuilder` và static imports của `Assertions`. Với `DirectChannel`, handler đã chạy khi `send` trả về, nên có thể đọc kết quả ngay. Nếu đổi sang executor, cần chờ có timeout.

### 11.3. Integration test polling + ErrorMessage

~~~java
@SpringBootTest(classes = OrderApplication.class)
class OrderPollingErrorTest {

    @Autowired
    @Qualifier("pendingOrders")
    BlockingQueue<OrderSubmitted> pending;

    @Autowired
    @Qualifier("observedErrors")
    BlockingQueue<ErrorMessage> errors;

    @Test
    void polledInvalidOrderIsReported() throws InterruptedException {
        pending.clear();
        errors.clear();

        pending.add(new OrderSubmitted(" ", 100));

        ErrorMessage failure = errors.poll(3, TimeUnit.SECONDS);
        assertNotNull(failure, "Chưa thấy lỗi trước timeout");
        assertNotNull(failure.getPayload());
    }
}
~~~

Test phụ thuộc scheduler/poller cùng error publisher chuẩn đang hoạt động. Với custom error handler không publish vào global `errorChannel`, test phải đổi theo config thực tế. Dùng `poll(timeout)` thay vì `Thread.sleep(...)` để tránh đoán thời điểm scheduler chạy.

### 11.4. Test khi triển khai adapter thật

| Kiểm thử | Điều cần khẳng định |
| --- | --- |
| JSON/body conversion | Payload vào function đúng kiểu, lỗi schema được báo có cấu trúc. |
| Trace/correlation header | Metadata còn đủ qua các hop đã thiết kế. |
| HTTP exception mapping | Validation và timeout trả status/error schema đúng hợp đồng. |
| Broker retry/redelivery | Consumer idempotent, không tạo side effect trùng. |
| DLQ/error store | Lỗi không hồi phục được lưu/quan sát đúng chỗ. |
| Lỗi không có failedMessage | Error handler chịu được thông điệp gốc bị thiếu. |
| Source polling lỗi giữa chừng | Có cơ chế phục hồi item hoặc đã chấp nhận mất item theo yêu cầu. |
| Gateway request/reply | Giữ reply contract, không biến consumer void thành reply không tồn tại. |

## 12. Chẩn đoán sự cố thường gặp

| Triệu chứng | Giải thích có thể | Cách xử lý |
| --- | --- | --- |
| Function không thấy `traceId` | Function chỉ nhận payload `T`. | Để integration layer quản lý header hoặc chuyển sang `Message<T>` nếu cần. |
| Mất `businessCorrelationId` qua adapter | Header mapper/converter đã bỏ header. | Thiết kế allowlist và test tại ranh giới. |
| `DirectChannel` ném lỗi nhưng `errorChannel` không nhận | Lỗi đồng bộ truyền về sender. | Map tại caller/gateway hoặc cấu hình error policy thích hợp. |
| Poller lỗi mà không có `ErrorMessage` | Custom scheduler không publish, endpoint chưa chạy hoặc chưa có item. | Kiểm tra poller và `MessagePublishingErrorHandler`. |
| `getOriginalMessage()` trả null | ErrorMessage không mang bản gốc ở điểm lỗi. | Kiểm thêm `MessagingException.failedMessage` và correlation store. |
| Retry tạo nhiều tác động phụ | Nhiều tầng retry và thiếu idempotency. | Giới hạn retry, lưu idempotency key. |
| Gateway timeout | Mất reply, flow kết thúc bằng consumer hoặc async quá chậm. | Kiểm tra `replyChannel`, endpoint và timeout. |
| Header nhạy cảm vào log | Log toàn bộ message/header. | Loại/che dữ liệu theo allowlist; cấu hình retention. |
| Function cast sai kiểu | JSON/converter/chữ ký generic không khớp. | Kiểm tra deserialize và contract đầu vào. |

## 13. Checklist triển khai

1. Xác định contract **payload** và **metadata** ở ingress/egress.
2. Đặt domain logic trong `Supplier`, `Function`, `Consumer`; chuyển phát/điều phối trong `IntegrationFlow` và adapter.
3. Quy định header được tạo ở đâu, cần giữ qua hop nào, và được phép xuất ra ngoài hay không.
4. Phân biệt exception trả caller với error publishing qua `ErrorMessage`.
5. Có chính sách retry riêng cho validation, hạ tầng tạm thời và lỗi vĩnh viễn.
6. Dùng idempotency key ổn định qua redelivery; không dùng message ID mới làm business key.
7. Kiểm tra nguồn polling/broker có ack, retry, dead-letter và khả năng khôi phục phù hợp.
8. Có logging/metrics/tracing đủ correlation, nhưng không lộ dữ liệu nhạy cảm.
9. Test unit function, flow đồng bộ, flow polling và adapter/binder thực tế.

### Bài tập mở rộng

- Thêm function `markStage` nhận `Message<OrderSubmitted>` để tạo header `processingStage`; kiểm thử trace và correlation trước/sau.
- Cấu hình một error flow phân loại validation với lỗi hạ tầng rồi ghi vào hai error store khác nhau.
- Thay `DirectChannel` bằng `ExecutorChannel` và so sánh đường exception, thời điểm xác nhận message.
- Giả lập consumer ghi DB thất bại; xây retry có giới hạn và idempotency bằng business key.
- Thử dùng Spring Integration Messaging Gateway, bảo toàn `replyChannel` và map lỗi trả caller.

## 14. Tài liệu tham khảo

- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, xử lý đồng bộ/bất đồng bộ và polling.
- [Spring Integration — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply, error propagation và gateway error channel.
- [Spring Integration — Transformers](https://docs.spring.io/spring-integration/reference/transformer.html): transform payload/message, null output, header filter.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel` và các loại channel.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `FunctionCatalog`, composition, message và function routing.
- [Spring Cloud Function — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/spring-integration.html): `FunctionFlowBuilder`, `fromSupplier`, `apply` và `accept`.

**Kết luận:** Tại ranh giới Spring Cloud Function và Spring Integration, payload giữ logic nghiệp vụ, còn message headers truyền thông tin trace, correlation, reply và lỗi. `DirectChannel` thường trả exception cho caller, trong khi polling và các thành phần bất đồng bộ có thể phát `ErrorMessage` qua `errorChannel`. Thiết kế rõ hợp đồng metadata, error classification, retry, idempotency và kiểm thử trên từng adapter giúp cùng một function phục vụ HTTP, sự kiện và serverless với khả năng quan sát và khôi phục phù hợp.
