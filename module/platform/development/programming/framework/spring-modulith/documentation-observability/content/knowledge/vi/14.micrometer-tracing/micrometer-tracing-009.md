# Propagation qua message hoặc event boundary

## 1. Vì sao trace context phải đi cùng message?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, các application module có thể phối hợp qua lời gọi API hoặc domain event. Ví dụ, module `ordering` phát `OrderPlaced`; module `notification` nhận sự kiện để gửi email; module `reporting` cập nhật dữ liệu thống kê. Khi mọi xử lý nằm trong cùng một call stack, tracing thường có thể giữ quan hệ cha/con giữa các span.

Khi công việc đi qua một **ranh giới thực thi**, tình huống thay đổi:

- Listener chạy trên executor thread khác.
- Event được gửi qua Kafka, RabbitMQ hoặc một broker.
- Message được consumer xử lý trong tiến trình khác.
- Event được externalize, retry hoặc xử lý lại sau khi ứng dụng khởi động lại.

Thread mới không tự có `ThreadLocal` của thread cũ; tiến trình khác cũng không thể đọc bộ nhớ của tiến trình gửi. Nếu trace context không được truyền, consumer vẫn có thể xử lý message nhưng span của nó bắt đầu thành một trace độc lập hoặc không có quan hệ với trace ban đầu.

**Propagation** là việc mang ngữ cảnh trace qua ranh giới đó. Với message boundary, trace context thường được **inject vào message headers** ở phía producer và **extract từ headers** ở phía consumer. Với event bất đồng bộ trong cùng tiến trình, context có thể cần được capture/restore qua executor thread. Hai cơ chế có liên quan nhưng không giống nhau.

Bài học thuộc chương **Micrometer tracing** của `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục tiêu của module là tài liệu hóa ranh giới application module và quan sát tương tác khi hệ thống Spring Boot vận hành, bao gồm module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt propagation qua thread với propagation qua message/process boundary.
2. Mô tả vai trò của Micrometer Tracing `Propagator`, trace context và message headers.
3. Giải thích W3C Trace Context với `traceparent`, `tracestate` và baggage.
4. Hiểu producer span, consumer span và quan hệ trace giữa chúng.
5. Chọn cách tích hợp tự động của framework messaging hoặc cách inject/extract thủ công khi thật sự cần.
6. Áp dụng context propagation cho Spring Modulith application event và listener bất đồng bộ.
7. Phân biệt trace continuity với Event Publication Registry, retry, delivery guarantee và idempotency.
8. Kiểm chứng end-to-end và chẩn đoán trường hợp message được xử lý nhưng trace bị đứt.

## 2. Hai loại boundary cần xử lý khác nhau

Trước khi cấu hình, hãy xác định công việc vượt qua ranh giới nào.

| Boundary | Ví dụ | Cách truyền context phù hợp |
| --- | --- | --- |
| **Thread boundary trong cùng tiến trình** | `@ApplicationModuleListener`, `@Async`, `Executor`. | Capture/restore Micrometer context qua executor, ví dụ `ContextPropagatingTaskDecorator`. |
| **Message boundary trong cùng tiến trình** | Hàng đợi nội bộ hoặc message abstraction có producer/consumer. | Gắn context vào carrier/headers theo instrumentation messaging; không chỉ dựa vào `ThreadLocal`. |
| **Process/service boundary** | Kafka, RabbitMQ, HTTP, cloud queue. | Inject trace context vào headers ở sender và extract ở receiver bằng propagator/instrumentation. |
| **Retry hoặc replay về sau** | Publication được xử lý lại sau lỗi hoặc sau restart. | Có thể là execution mới; dùng correlation ID nghiệp vụ để liên kết lịch sử, không giả định trace gốc còn active. |

~~~mermaid
flowchart TB
    A["Application event / message được phát"]
    B{"Ranh giới thực thi?"}
    C["Cùng tiến trình, thread khác"]
    D["Message / process boundary"]
    E["Capture / restore context<br/>TaskDecorator / executor"]
    F["Inject trace context<br/>message headers"]
    G["Restore current context<br/>trên worker thread"]
    H["Extract context<br/>tại consumer"]
    I["Tạo span consumer"]
    A --> B
    B --> C --> E --> G --> I
    B --> D --> F --> H --> I
~~~

Không nên dùng `ContextPropagatingTaskDecorator` như giải pháp duy nhất cho Kafka hoặc RabbitMQ: decorator chỉ bao bọc task trong cùng tiến trình, không tự ghi `traceparent` vào message. Ngược lại, chỉ thêm message headers không giải quyết một executor nội bộ không được cấu hình propagation.

## 3. Trace context chứa những gì?

Một trace được tạo từ các span. Mỗi span có định danh riêng và có thể liên hệ với span cha. Để tiếp tục trace qua ranh giới, producer truyền đủ context cần thiết để consumer biết trace nào đang được tiếp nối.

| Thành phần | Ý nghĩa |
| --- | --- |
| **Trace ID** | Định danh chung của một trace; các span liên quan có thể dùng cùng trace ID. |
| **Span ID** | Định danh của một span cụ thể, ví dụ producer span. |
| **Parent span ID** | Thông tin quan hệ cha/con dùng để dựng cây span. |
| **Trace flags** | Các cờ context, thường bao gồm trạng thái sampled. |
| **Trace state** | Thông tin bổ sung theo vendor/tracing system nếu được sử dụng. |
| **Baggage** | Các key/value được chủ đích truyền qua nhiều hop; không phải dữ liệu xác thực. |

### 3.1. W3C Trace Context

W3C Trace Context định nghĩa các HTTP header chuẩn:

- **`traceparent`:** mang version, trace ID, parent ID và trace flags.
- **`tracestate`:** mang thông tin vendor-specific tùy chọn.

Ví dụ minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

Các giá trị trên chỉ để minh họa cấu trúc; không phải trace ID của một request thực tế. `traceparent` giúp consumer tiếp tục đúng trace và biết span nào là parent theo context được truyền. `tracestate` có thể được giữ hoặc cập nhật theo quy tắc của tracing implementation.

### 3.2. Baggage khác trace context như thế nào?

**Trace context** là metadata cần thiết để liên kết span. **Baggage** là dữ liệu ứng dụng muốn chuyển tiếp qua các hop, chẳng hạn một phân loại được cho phép. Không nên đưa mọi thuộc tính request vào baggage.

| Dữ liệu | Có nên truyền? | Lý do |
| --- | --- | --- |
| Trace ID / parent ID / flags | Có, qua propagator. | Cần cho quan hệ trace. |
| Baggage key đã được phê duyệt | Có thể. | Hữu ích khi nhiều service cần một giá trị ngữ cảnh nhỏ, ổn định. |
| `orderId` | Cân nhắc, thường dùng correlation field/log hoặc span attribute. | Giá trị có cardinality cao; không tự động biến nó thành baggage. |
| Email, số điện thoại, token, thông tin thanh toán | Không truyền qua baggage mặc định. | Rủi ro riêng tư và bảo mật. |
| Role/tenant dùng để cấp quyền | Không dùng trace header làm nguồn quyết định quyền. | Trace context không phải cơ chế xác thực/ủy quyền. |

Trace headers có thể đến từ client hoặc message bên ngoài và phải được xem là dữ liệu không đáng tin cậy. Không dùng `traceparent`, baggage hay `tracestate` để quyết định quyền truy cập, tenant isolation hoặc xác thực message.

## 4. Micrometer Tracing `Propagator`

Micrometer Tracing định nghĩa abstraction `Propagator` để truyền trace context mà không buộc code nghiệp vụ phụ thuộc trực tiếp vào Brave hoặc OpenTelemetry.

Hai thao tác chính:

| Thao tác | Phía | Mục đích |
| --- | --- | --- |
| `inject(...)` | Producer/sender | Ghi context của span hiện hành vào carrier, ví dụ message headers. |
| `extract(...)` | Consumer/receiver | Đọc context từ carrier để tạo span có quan hệ với trace đã truyền. |

Một carrier có thể là map, HTTP request/response, Kafka headers hoặc kiểu dữ liệu riêng của broker. Propagator không cần biết nội dung nghiệp vụ của message; nó chỉ làm việc với carrier và các getter/setter được cung cấp.

### 4.1. Luồng producer

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant T as Tracer
    participant PR as Propagator
    participant H as Message headers
    participant B as Broker
    P->>T: tạo producer span
    T-->>P: span context
    P->>PR: inject(context, carrier, setter)
    PR->>H: ghi traceparent / tracestate
    P->>B: gửi message + headers
~~~

Producer span mô tả hoạt động gửi message. Context được inject thường là context của producer span đang active, để span phía consumer có thể liên kết với đúng bước gửi.

### 4.2. Luồng consumer

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant H as Message headers
    participant PR as Propagator
    participant T as Tracer
    participant C as Consumer
    B->>C: nhận message
    C->>PR: extract(carrier, getter)
    PR-->>C: span builder / extracted context
    C->>T: tạo consumer span từ context
    T-->>C: consumer span
    C->>C: xử lý nghiệp vụ trong scope
    C->>T: kết thúc span
~~~

Consumer không tự tin vào trace ID được gửi đến để thực hiện nghiệp vụ bảo mật. Nó chỉ dùng context đã extract để liên kết telemetry; việc xác thực message phải dựa trên cơ chế của broker, chữ ký hoặc hệ thống identity phù hợp.

## 5. Ví dụ inject/extract với carrier dạng Map

Khi framework messaging chưa có instrumentation tương ứng hoặc cần tích hợp một transport riêng, có thể dùng `Propagator` với một carrier đơn giản. Ví dụ dưới đây tập trung vào **cơ chế API**; phần gửi/nhận thực tế phải thay bằng Kafka, RabbitMQ hoặc message client đang dùng.

### 5.1. Producer: inject context vào headers

~~~java
package com.example.shop.messaging;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
class MessageTraceHeaders {

    private final Tracer tracer;
    private final Propagator propagator;

    MessageTraceHeaders(Tracer tracer, Propagator propagator) {
        this.tracer = tracer;
        this.propagator = propagator;
    }

    Map<String, String> createHeaders() {
        Map<String, String> headers = new HashMap<>();
        Span current = tracer.currentSpan();

        if (current != null) {
            propagator.inject(
                current.context(),
                headers,
                (carrier, key, value) -> carrier.put(key, value)
            );
        }

        return headers;
    }
}
~~~

Điểm cần chú ý:

1. `Tracer.currentSpan()` có thể trả `null` nếu không có span hiện hành.
2. Chỉ inject khi có context phù hợp; message vẫn có thể được gửi khi không có trace hiện hành.
3. Carrier `Map` chỉ là ví dụ. Với Kafka, phải chuyển các cặp key/value thành Kafka headers theo API broker; với RabbitMQ, dùng message properties/headers.
4. Không tự đặt header `traceparent` bằng cách nối chuỗi trace ID. Propagator chịu trách nhiệm định dạng và inject theo propagation type đã cấu hình.

Trong ứng dụng thực tế, producer instrumentation thường tạo producer span trước, mở scope cho span đó rồi gọi `createHeaders()` khi gửi message. Khi đó context được inject là context của hoạt động gửi, không chỉ là context HTTP bất kỳ.

### 5.2. Consumer: extract và tạo span

~~~java
package com.example.shop.messaging;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
class MessageTraceConsumer {

    private final Tracer tracer;
    private final Propagator propagator;

    MessageTraceConsumer(Tracer tracer, Propagator propagator) {
        this.tracer = tracer;
        this.propagator = propagator;
    }

    void consume(Map<String, String> headers, Runnable businessWork) {
        Span.Builder extracted = propagator.extract(headers, Map::get);
        Span consumerSpan = tracer.nextSpan(extracted)
            .name("orders.consume")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(consumerSpan)) {
            businessWork.run();
        }
        catch (RuntimeException ex) {
            consumerSpan.error(ex);
            throw ex;
        }
        finally {
            consumerSpan.end();
        }
    }
}
~~~

Ví dụ cho thấy ý nghĩa của extraction và scope. Trong ứng dụng thật, phải xem cách tracer/bridge đang cấu hình tạo span khi extracted context không có hoặc không hợp lệ, và chọn chính sách xử lý lỗi phù hợp. Không nên bắt mọi exception rồi bỏ qua, vì điều đó có thể làm broker đánh dấu message thành công dù nghiệp vụ thất bại.

**Quan trọng:** Đây là ví dụ tích hợp mức thấp. Nếu Spring Kafka, Spring AMQP hoặc một framework đã tự động tạo producer/consumer observations và inject/extract headers, không thêm đoạn manual này song song. Làm cả hai có thể tạo span trùng hoặc propagation hai lần.

## 6. Ưu tiên instrumentation của messaging framework

Với transport phổ biến, lựa chọn đầu tiên thường là dùng observation/tracing support có sẵn trong framework. Framework biết cách tạo producer/consumer observation, làm việc với header API của broker và liên kết context theo phiên bản được hỗ trợ.

### 6.1. Spring Kafka

Spring Kafka có hỗ trợ Micrometer Observation cho producer và listener container ở các phiên bản hiện đại. Khi bật observation, instrumentation có thể tạo span cho thao tác gửi/nhận và truyền trace context qua Kafka headers khi tracing được cấu hình.

Ví dụ cấu hình khái niệm với Spring Kafka 3.x:

~~~java
@Configuration
class KafkaObservationConfiguration {

    @Bean
    KafkaTemplate<String, OrderPlaced> kafkaTemplate(
            ProducerFactory<String, OrderPlaced> producerFactory) {
        KafkaTemplate<String, OrderPlaced> template =
            new KafkaTemplate<>(producerFactory);
        template.setObservationEnabled(true);
        return template;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderPlaced>
            kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderPlaced> consumerFactory) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderPlaced>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setObservationEnabled(true);
        return factory;
    }
}
~~~

Đây là ví dụ cấu hình phần observation, không phải toàn bộ cấu hình Kafka: broker, serializer/deserializer, group ID và error handler vẫn cần được thiết lập theo ứng dụng. Tên API và mặc định cần đối chiếu phiên bản Spring Kafka thực tế. Với các phiên bản/framework cũ, observation có thể chưa được hỗ trợ hoặc cấu hình khác.

Sau khi bật, kiểm tra:

- Producer span có được tạo khi gửi message không?
- Trace headers có xuất hiện trên message đã gửi không?
- Consumer span có liên kết với producer context không?
- Consumer error được ghi nhận và xử lý theo retry/DLQ policy ra sao?

Không tự thêm `traceparent` bằng tay nếu instrumentation của Kafka đã đảm nhiệm propagation.

### 6.2. Spring AMQP / RabbitMQ

Spring AMQP cũng có hỗ trợ Micrometer Observation cho các thao tác template và listener container trong các phiên bản tương ứng. Khi bật, `RabbitTemplate` và listener container có thể tạo observation cho send/receive. Cần kiểm tra tài liệu của phiên bản Spring AMQP đang dùng để biết thuộc tính bật observation, cấu hình listener factory và các dependency tracing cần thiết.

Điểm chung với Kafka là **framework phải có cơ hội nhìn thấy cả producer và consumer**. Nếu chỉ instrument producer mà listener phía consumer không được instrument, trace có thể dừng ở broker. Nếu consumer chạy ở service khác, context phải được truyền qua message headers và được extract ở service đó.

### 6.3. Tại sao không nên tự làm propagation khi framework đã làm?

- Tránh tạo hai producer spans cho một lần gửi.
- Tránh inject header hai lần hoặc ghi đè context không đúng.
- Tôn trọng quy ước của framework về batch, retry và consumer records.
- Giảm code phụ thuộc vào cấu trúc header nội bộ của broker.
- Dễ nâng cấp cùng phiên bản framework và Micrometer.

Chỉ tự viết adapter `Propagator` khi transport không được instrument, framework không hỗ trợ trường hợp cần thiết hoặc có một yêu cầu tích hợp đặc thù đã được kiểm chứng.

## 7. Spring Modulith application event: cùng tiến trình và qua broker

Không phải mọi application event đều đi qua message broker. Cần phân biệt hai tình huống.

### 7.1. Event nội bộ tiến trình

Giả sử `ordering` phát `OrderPlaced` và `notification` dùng `@ApplicationModuleListener`. Đây là application event trong cùng ứng dụng Spring:

~~~java
package com.example.shop.notification;

import com.example.shop.ordering.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Xử lý thông báo.
    }
}
~~~

`@ApplicationModuleListener` là shortcut cho listener chạy bất đồng bộ, theo transaction phase sau commit và trong transaction riêng theo semantics của Spring Modulith. Nó **không tự biến event nội bộ thành một message đi qua broker**.

Khi listener chuyển sang executor thread khác, cần truyền context qua thread boundary. Với executor do ứng dụng tự cấu hình, có thể dùng:

~~~java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
~~~

và bảo đảm Micrometer Context Propagation có trên classpath, listener thật sự sử dụng executor đó, async processing được bật theo cấu hình. Cách này capture/restore context trong cùng tiến trình; không inject `traceparent` vào một message không tồn tại.

### 7.2. Event được externalize qua broker

Nếu event được chuyển ra một hệ thống messaging, producer/consumer trở thành hai đầu của message boundary. Khi đó cần instrumentation của adapter/broker hoặc `Propagator` inject/extract trace context vào headers.

~~~mermaid
flowchart LR
    subgraph AppA["Ứng dụng A"]
        O["ordering"]
        P["Event publisher"]
        S["Messaging producer"]
        O --> P --> S
    end
    H["Broker headers<br/>traceparent / tracestate"]
    subgraph AppB["Ứng dụng B"]
        R["Messaging consumer"]
        N["notification"]
        R --> N
    end
    S --> H --> R
~~~

Spring Modulith có các cơ chế hỗ trợ externalization event qua integration tương ứng. Việc cấu hình externalization, transaction và publication registry là phần riêng của messaging/event architecture; **trace propagation không tự cấu hình externalization**. Hãy xác định rõ adapter nào thực hiện publish và consumer nào nhận event, rồi kiểm tra propagation ở đúng hai đầu.

### 7.3. Event Publication Registry và trace context là hai chuyện khác nhau

Event Publication Registry theo dõi trạng thái publication tới transactional listener và hỗ trợ xử lý lại các publication chưa hoàn tất theo cấu hình. Registry giúp giải quyết khía cạnh **reliability/visibility của event processing**.

Trace context giúp liên kết **các span của một luồng xử lý**. Nếu một publication được retry sau restart, lần thực thi mới có thể xảy ra khi trace ban đầu không còn active. Không nên giả định retry phải mang parent span của HTTP request gốc.

Nên giữ một correlation ID nghiệp vụ ổn định (ví dụ `orderId`) trong payload hoặc log metadata đã được phê duyệt để tìm các lần thử liên quan. Correlation ID này khác trace ID và không thay thế trace context chuẩn.

## 8. W3C propagation và cấu hình Spring Boot

### 8.1. Chọn propagation format

Micrometer Tracing có thể dùng các propagation type được bridge hỗ trợ, phổ biến gồm W3C Trace Context và B3. W3C sử dụng `traceparent`/`tracestate`; B3 có định dạng header riêng. Các service trong cùng một luồng phải thống nhất hoặc có cấu hình chuyển đổi tương thích.

Ví dụ cấu hình Spring Boot cho W3C (hãy xác nhận property theo dòng Boot cụ thể):

~~~yaml
management:
  tracing:
    propagation:
      type: w3c
    sampling:
      probability: 1.0
~~~

Giá trị sampling `1.0` phù hợp môi trường dev/test nhỏ. Production cần chọn sampling theo lưu lượng và chi phí. Nếu các service dùng propagation type khác nhau mà không có hỗ trợ chuyển đổi, consumer có thể không extract được parent context.

### 8.2. Baggage chỉ nên khai báo khi có mục đích rõ

Ví dụ một ứng dụng cần chuyển tiếp một phân loại đã được phê duyệt:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-tier
      correlation:
        fields:
          - tenant-tier
~~~

Đây là ví dụ property theo Spring Boot tracing configuration; tên và hỗ trợ cần đối chiếu phiên bản. Baggage remote field có thể được đưa vào headers để truyền qua các hop; correlation field có thể được đưa vào MDC/log context nếu logging integration hỗ trợ.

Không thêm `tenant-id`, user ID hoặc dữ liệu nhạy cảm một cách mặc định. Nếu có nhu cầu truyền tenant context, phải xem xét threat model, quyền truy cập, masking và chính sách lưu trữ. Baggage là metadata telemetry, không phải bằng chứng user đã được xác thực cho tenant đó.

### 8.3. Không copy toàn bộ request context vào message

Message payload nên mang dữ liệu nghiệp vụ cần cho consumer. Trace headers nên mang dữ liệu tracing. Baggage chỉ mang các giá trị được cho phép. Tránh copy toàn bộ HTTP headers sang message vì có thể mang theo:

- Authorization token hoặc cookie.
- Thông tin cá nhân.
- Header nội bộ không có ý nghĩa ở consumer.
- Dữ liệu có cardinality cao hoặc quá lớn.

Giữ ranh giới rõ giúp message gọn, giảm rủi ro rò rỉ và tránh nhầm telemetry metadata với business contract.

## 9. Batch, fan-out và retry: không phải lúc nào cũng là một cây đơn giản

### 9.1. Fan-out một event thành nhiều message

Một producer có thể phát một event tới nhiều consumer. Mỗi consumer có thể có span riêng, cùng liên hệ với context producer. Điều này tạo nhiều nhánh telemetry:

~~~mermaid
flowchart TB
    P["Producer span: OrderPlaced"]
    A["Consumer span: email"]
    B["Consumer span: inventory projection"]
    C["Consumer span: analytics"]
    P --> A
    P --> B
    P --> C
~~~

Sơ đồ chỉ minh họa quan hệ logic; cách biểu diễn parent/child hoặc span links tùy messaging instrumentation và semantics của batch/fan-out. Không tự tạo quan hệ cha/con bằng cách gán cùng một trace ID nếu không có parent context hợp lệ.

### 9.2. Batch consumer

Consumer có thể nhận nhiều message trong một lần poll. Một span xử lý batch không nhất thiết có thể có một parent duy nhất đại diện đúng cho mọi message. Instrumentation có thể dùng span links hoặc semantics riêng cho batch. Ưu tiên cơ chế của framework và OpenTelemetry/Micrometer integration thay vì tự gán parent từ message đầu tiên cho toàn batch.

### 9.3. Retry và dead-letter queue

Retry có thể phát sinh nhiều lần thực thi:

~~~text
Producer trace P-1
  └── Message M

Consumer attempt 1: lỗi
Consumer attempt 2: lỗi
Consumer attempt 3: thành công
~~~

Mỗi lần thử có thể tạo span riêng. Nếu retry xảy ra trong cùng một tiến trình và context được giữ, chúng có thể được liên kết theo cách instrumentation định nghĩa. Nếu retry diễn ra sau restart, từ scheduler hoặc DLQ redrive, không mặc định trace gốc còn active.

Hãy dùng các trường riêng:

| Trường | Mục đích |
| --- | --- |
| Trace ID / span ID | Liên kết telemetry của một execution/trace. |
| Message ID | Nhận diện một message trong hệ thống messaging. |
| Correlation ID nghiệp vụ | Liên hệ các bước hoặc lần thử thuộc cùng một giao dịch nghiệp vụ. |
| Attempt number | Phân biệt lần xử lý/retry nếu hệ thống có ghi nhận. |

Không dùng một trường thay cho tất cả. `messageId` hoặc `orderId` không phải trace ID; trace ID cũng không phải khóa idempotency.

## 10. Kiểm chứng end-to-end

### 10.1. Kịch bản thực hành

Tạo một luồng đặt hàng:

1. Client gọi HTTP endpoint tạo đơn hàng trong ứng dụng A.
2. Module `ordering` lưu đơn và phát `OrderPlaced`.
3. Adapter gửi event qua broker.
4. Consumer trong ứng dụng B nhận message.
5. Module `notification` gửi thông báo hoặc ghi nhận kết quả.

Trong môi trường thử nghiệm, cấu hình instrumentation và tracing backend ở cả producer lẫn consumer. Gửi một message có `messageId` và `orderId` giả lập, không dùng dữ liệu khách hàng thật.

### 10.2. Checklist phía producer

- Có producer observation/span cho thao tác publish/send không?
- Propagator có inject `traceparent` hoặc propagation header tương ứng không?
- Header có được broker adapter serialize và lưu cùng message không?
- Có vô tình ghi đè context bằng header rỗng hoặc context từ một request khác không?
- Sampling flag có được giữ đúng không?

### 10.3. Checklist phía consumer

- Consumer instrumentation có bật không?
- Header có đến nguyên vẹn sau broker không?
- Propagator có extract đúng format không?
- Consumer span có dùng extracted context hoặc span link phù hợp không?
- Nếu context không có, hệ thống có xử lý như một root/new trace theo chính sách không?
- Exception có được ghi nhận và trả về cơ chế retry/DLQ phù hợp không?

### 10.4. Kiểm tra message headers

Với môi trường dev, có thể log **tên header propagation đã được cấu hình** và trạng thái có/không của chúng, nhưng tránh log toàn bộ header tùy ý. Không ghi authorization token, cookie hoặc baggage nhạy cảm.

W3C message có thể mang `traceparent` và `tracestate`; nếu dùng B3 thì tên header khác. Không kiểm tra cứng `traceparent` khi cấu hình đang dùng B3. Hãy đọc danh sách fields từ propagation implementation hoặc cấu hình đã chọn.

### 10.5. Đối chiếu trace trong backend

Trace kỳ vọng có thể có:

~~~text
Trace: POST /orders
└── HTTP server span
    └── ordering module-entry span
        └── messaging producer span
            └── messaging consumer span
                └── notification module-entry span
~~~

Đây là hình dạng minh họa cho một message và một consumer. Tên span, parent/child hoặc link phụ thuộc framework, batch semantics, thời điểm gửi/nhận và cách tracing backend hiển thị. Nếu listener xử lý sau commit hoặc retry về sau, trace có thể được nối theo context được lưu hoặc xuất hiện như execution khác.

### 10.6. Kiểm tra Actuator liên quan

~~~bash
# Module graph runtime, không phải trace data.
curl -s http://localhost:8080/actuator/modulith

# Event publication counters.
curl -s http://localhost:8080/actuator/metrics/module.events.published

# Các meter đã đăng ký.
curl -s http://localhost:8080/actuator/metrics
~~~

Không có endpoint Actuator mặc định trả toàn bộ distributed traces chỉ vì đã bật Micrometer Tracing. Traces được tìm trong backend đã cấu hình. Counter `module.events.published` xác nhận hoạt động phát event được instrument, không xác nhận consumer hoàn tất.

## 11. Phân biệt propagation với reliability

Propagation đảm bảo **ngữ cảnh tracing được truyền**. Nó không đảm bảo message được giao ít nhất một lần, đúng một lần hoặc xử lý thành công.

| Khía cạnh | Cơ chế thường liên quan | Câu hỏi được trả lời |
| --- | --- | --- |
| Trace continuity | Micrometer `Propagator`, W3C/B3 headers, messaging instrumentation. | Span producer và consumer liên hệ như thế nào? |
| Thread context | `ContextPropagatingTaskDecorator`, executor context snapshot. | Observation hiện hành có được giữ khi đổi thread? |
| Event publication tracking | Spring Modulith Event Publication Registry. | Publication tới transactional listener đã hoàn tất chưa? |
| Delivery/retry | Broker acknowledgement, retry policy, DLQ, durable queue. | Message được giao lại hoặc giữ lại thế nào khi lỗi? |
| Idempotency | Business key, deduplication store, transaction design. | Xử lý lặp có gây tác dụng phụ lặp không? |
| Business correlation | `orderId`, `messageId`, correlation key đã được kiểm soát. | Các lần xử lý có cùng thuộc một giao dịch nghiệp vụ không? |

Spring Modulith Event Publication Registry có thể theo dõi publication và hỗ trợ phục hồi những publication chưa hoàn tất theo cấu hình. Nhưng nếu một publication được resubmit sau khi process restart, không thể giả định request HTTP ban đầu vẫn có current span. Cần correlation ID nghiệp vụ để tìm các execution liên quan.

**Trace continuity không phải exactly-once delivery.** Ngược lại, message được xử lý thành công cũng không chứng minh trace headers đã được truyền đúng.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Producer có span nhưng consumer bắt đầu trace mới | Trace header không được inject, không được lưu trên message hoặc consumer không extract đúng. | Kiểm tra instrumentation producer/consumer, carrier và propagation type. |
| Không thấy `traceparent` | Đang dùng B3 hoặc propagation format khác; không có span hiện hành; instrumentation chưa bật. | Kiểm tra cấu hình propagator và current span, không giả định mọi hệ thống dùng W3C. |
| Có header nhưng trace ID khác | Header bị ghi đè, consumer tạo root span hoặc framework không nhận diện carrier. | So sánh header tại producer và consumer, kiểm tra extraction. |
| Listener async trong cùng app mất trace | Executor thread không được truyền context. | Dùng `ContextPropagatingTaskDecorator` trên đúng executor. |
| Trace ID có nhưng không thấy consumer span | Consumer instrumentation/handler/exporter/sampling có vấn đề. | Kiểm tra consumer span lifecycle và backend. |
| Một message tạo hai producer spans | Manual instrumentation chạy song song với framework auto-instrumentation. | Chọn một đường instrument, bỏ phần trùng. |
| Batch trace có quan hệ cha/con khó hiểu | Một batch có nhiều message và nhiều parent context. | Dùng framework semantics/span links; không tự chọn parent tùy tiện. |
| Retry sau restart không cùng trace | Lần retry là execution mới, trace gốc đã kết thúc. | Dùng correlation ID/message ID; không ép parent trace cũ nếu không còn context hợp lệ. |
| Trace headers mất sau broker | Adapter không preserve headers, serializer/filter loại bỏ header. | Kiểm tra broker record properties và mapping headers của adapter. |
| Baggage quá lớn hoặc lộ dữ liệu | Propagate quá nhiều request metadata. | Allowlist baggage, giới hạn kích thước, loại bỏ thông tin nhạy cảm. |
| Consumer chạy nhưng publication vẫn chưa hoàn tất | Exception, transaction rollback hoặc registry chưa đánh dấu hoàn thành. | Kiểm tra transaction listener, registry và retry policy. |
| Trace có đầy đủ nhưng event bị xử lý lặp | Reliability/idempotency là vấn đề khác propagation. | Kiểm tra acknowledgement, retry, deduplication và idempotent handler. |

### Quy trình chẩn đoán theo thứ tự

Khi consumer không nối được trace, kiểm tra lần lượt:

1. Producer có span active tại thời điểm gửi không?
2. Framework messaging có tạo producer observation/span không?
3. Propagator đã inject fields vào carrier chưa?
4. Broker adapter có giữ các header đó không?
5. Consumer nhận đúng header và dùng cùng propagation format không?
6. Consumer instrumentation có extract context trước khi xử lý không?
7. Sampling/exporter/backend có thu thập span không?
8. Nếu chỉ là event nội bộ cùng tiến trình, executor có context decorator không?
9. Nếu là retry/replay, đây có phải execution mới cần correlation ID thay vì parent span cũ không?

## 13. Nguyên tắc triển khai an toàn

1. **Ưu tiên auto-instrumentation:** dùng hỗ trợ Micrometer Observation của Spring Kafka, Spring AMQP hoặc client framework nếu phù hợp phiên bản.
2. **Không inject/extract hai lần:** tránh trùng span hoặc ghi đè trace headers khi framework đã làm.
3. **Chọn propagation format thống nhất:** W3C hoặc B3 theo khả năng tương thích của hệ thống.
4. **Allowlist baggage:** chỉ truyền những trường có mục đích và được phép; giới hạn kích thước và độ nhạy cảm.
5. **Không dùng trace context để cấp quyền:** trace headers là telemetry metadata, không phải identity token.
6. **Giữ payload nghiệp vụ độc lập:** message payload mang dữ liệu domain; headers mang transport/telemetry context.
7. **Phân biệt thread và message boundary:** TaskDecorator không thay thế message propagator.
8. **Thiết kế retry/idempotency riêng:** tracing không bảo đảm delivery hoặc không xử lý lặp.
9. **Giữ correlation ID ổn định cho nghiệp vụ:** dùng khi cần liên kết retry/replay sau khi trace gốc đã kết thúc.
10. **Quan sát cả producer và consumer:** một đầu không instrument thì trace có thể dừng ở boundary.

## 14. Bài tập thực hành

### Bài 1 — Phân biệt hai loại propagation

Tạo một `@ApplicationModuleListener` xử lý event bằng executor trong cùng ứng dụng. Quan sát trace trước và sau khi gắn `ContextPropagatingTaskDecorator`. Giải thích tại sao không cần message header nếu event vẫn ở cùng tiến trình.

### Bài 2 — Inject/extract với carrier giả lập

Dùng `Propagator` và một `Map<String, String>` làm carrier. Tạo producer span, inject context vào map, extract ở consumer và tạo span consumer. Xác nhận trace ID được liên kết. Không dùng map làm giải pháp production nếu broker/framework có carrier riêng.

### Bài 3 — Dùng instrumentation Spring Kafka

Bật observation ở producer template và listener container trong môi trường test. Gửi một message và tìm producer/consumer spans. Xác nhận các trace headers được truyền qua broker; không thêm manual injection nếu framework đã tự thực hiện.

### Bài 4 — Tái hiện lỗi mất header

Trong môi trường thử nghiệm, cấu hình adapter loại bỏ trace headers. Quan sát consumer bắt đầu trace mới hoặc không có parent context. Khôi phục header mapping và so sánh. Không thay đổi hệ thống production để làm bài này.

### Bài 5 — Phân biệt retry và trace

Cho consumer xử lý lỗi rồi retry. Ghi `messageId`, correlation ID nghiệp vụ và trace ID của từng attempt. Giải thích vì sao các attempt có thể có span/trace khác nhau nhưng vẫn thuộc cùng một giao dịch nghiệp vụ.

### Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `ThreadLocal` không đủ để truyền trace context qua Kafka?

**Đáp án:** Producer và consumer có thể chạy trên thread hoặc tiến trình khác; bộ nhớ thread-local không đi cùng message. Phải inject context vào headers và extract ở consumer.

**Câu 2.** `Propagator.inject(...)` và `extract(...)` làm gì?

**Đáp án:** Inject ghi context của span vào carrier ở phía gửi; extract đọc carrier ở phía nhận để xây dựng context cho span tiếp theo.

**Câu 3.** `traceparent` có phải dữ liệu xác thực không?

**Đáp án:** Không. Nó là header liên kết trace, không được dùng để xác định danh tính hoặc quyền truy cập.

**Câu 4.** Vì sao `ContextPropagatingTaskDecorator` không thay thế `Propagator` cho broker?

**Đáp án:** Decorator capture/restore context khi task đổi thread trong cùng tiến trình; Propagator inject/extract context qua carrier/message boundary.

**Câu 5.** Nếu Event Publication Registry retry sau restart, có nhất thiết dùng trace ID của request gốc không?

**Đáp án:** Không. Đó có thể là execution mới khi trace cũ đã kết thúc; dùng correlation ID nghiệp vụ để liên kết các lần xử lý.

**Câu 6.** Nếu Spring Kafka đã bật observation và tự truyền trace headers, có nên inject thủ công thêm lần nữa?

**Đáp án:** Không. Tránh instrumentation trùng và header bị ghi đè; chỉ tự xử lý khi framework không hỗ trợ tình huống cụ thể.

## 15. Tài liệu tham khảo

- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/): `Propagator`, `Tracer`, bridge Brave/OpenTelemetry và context propagation.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): span, trace context, scope và propagator.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing bridge, propagation, baggage, sampling và exporter.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry và truyền context qua executor.
- [Spring Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): producer/consumer observations và cấu hình Kafka.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/micrometer-observation.html): quan sát RabbitTemplate và listener container.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): application events, module listeners và Event Publication Registry.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): định dạng `traceparent` và `tracestate`.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): inject/extract context qua ranh giới dịch vụ.

**Ghi nhớ:** với event nội bộ chuyển thread, capture/restore context trên executor; với message qua broker hoặc service boundary, inject trace context vào headers ở producer và extract ở consumer. Hãy ưu tiên instrumentation của framework, dùng W3C/B3 nhất quán và allowlist baggage. Trace continuity giúp điều tra luồng xử lý, còn Event Publication Registry, retry, acknowledgement và idempotency mới giải quyết độ tin cậy của event.
