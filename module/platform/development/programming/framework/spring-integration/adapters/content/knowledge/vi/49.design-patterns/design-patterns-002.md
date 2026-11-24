# Event-driven Consumer Pattern trong Spring Integration Adapters

> **Chương:** Design patterns  
> **Chủ đề:** Event-driven consumer pattern  
> **Phạm vi:** Kết nối hệ thống bên ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel của **Spring Integration**; hiểu luồng thông điệp qua HTTP, JMS, AMQP, Kafka, file, SFTP và cơ sở dữ liệu. Tập trung vào hợp đồng message, cách kích hoạt consumer, xử lý lỗi, độ tin cậy, điều tiết tải và vòng đời kết nối.

## 1. Mục tiêu học tập và bài toán cần giải quyết

Một ứng dụng tích hợp phải phản ứng khi có dữ liệu mới: đơn hàng đã tạo, giao dịch đã duyệt, tệp hoàn tất hoặc message đến từ broker. Thay vì liên tục hỏi “đã có gì mới chưa?”, **Event-driven Consumer** để một nguồn hoặc thành phần trung gian **kích hoạt quá trình xử lý khi message được chuyển tới consumer**.

Sau bài học, bạn có thể:

1. Giải thích Event-driven Consumer trong Enterprise Integration Patterns (EIP) và phân biệt với Polling Consumer.
2. Xác định **ai chủ động phát sự kiện, ai giữ message trước lúc nhận, ai quyết định acknowledgment** trong mỗi luồng tích hợp.
3. Dùng **SubscribableChannel**, **DirectChannel**, **ExecutorChannel**, **PublishSubscribeChannel** và service activator của Spring Integration đúng vai trò.
4. Phân biệt **message-driven inbound adapter** (ví dụ JMS, AMQP, Kafka) với **inbound gateway** (ví dụ HTTP request/reply).
5. Thiết kế hợp đồng payload/header, correlation, ordering, retry, dead-letter, idempotency và kiểm soát dữ liệu đầu vào.
6. Hiểu khác biệt giữa **message đã được channel tiếp nhận**, **handler đã chạy** và **nghiệp vụ đã commit**.
7. Nhận ra trường hợp file/SFTP/DB cần poll hoặc nguồn thay đổi được phát thành event thông qua một lớp trung gian.
8. Thiết kế bài lab với Java DSL, kiểm thử lỗi và checklist vận hành production.

**Câu hỏi chính:** Làm sao phản ứng nhanh với dữ liệu mới **mà vẫn đúng nghiệp vụ khi message đến trùng, đến sai thứ tự, bị xử lý lỗi hoặc consumer tạm thời dừng**?

## 2. Event-driven Consumer là gì?

**Event-driven Consumer** là mẫu mà một thành phần tiêu thụ được gọi hoặc được thông báo **khi message có sẵn** theo cơ chế của nguồn, broker hoặc channel. Ở phía ứng dụng, handler thường được đăng ký làm subscriber/listener thay vì tự gọi một lịch hỏi dữ liệu nghiệp vụ.

Ví dụ hệ thống đặt hàng phát sự kiện OrderCreated; message đi vào broker, sau đó listener/container chuyển đến handler để cập nhật kho:

~~~text
10:00:00  Order Service tạo đơn ORD-1007 và ghi sự kiện
10:00:00  Broker nhận message, lưu/phát theo contract đã cấu hình
10:00:00  Listener nhận một message sẵn sàng xử lý
10:00:00  Spring Integration chuyển thành Message<OrderCreated>
10:00:00  Handler kiểm tra schema, business key, ghi trạng thái kho
10:00:00  Consumer/broker ghi nhận ack/commit theo chính sách
~~~

Không phải hệ thống nào cũng hoàn thành trong cùng mili giây. **Event-driven không có nghĩa zero latency**, “không bao giờ poll ở lớp transport” hoặc “đúng một lần end-to-end”.

### 2.1. Event, command và message

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event** | Sự kiện mô tả điều đã xảy ra | OrderCreated, PaymentApproved |
| **Command** | Yêu cầu thành phần khác thực hiện hành động | ReserveInventory, GenerateInvoice |
| **Message** | Đơn vị dữ liệu được hệ tích hợp vận chuyển | Payload OrderCreated cùng headers |
| **Consumer** | Thành phần nhận và xử lý message | Handler cập nhật trạng thái đơn |
| **Producer** | Thành phần tạo/gửi message | Order Service hoặc inbound adapter |
| **Broker** | Thành phần trung gian giữ/phân phối message nếu có | JMS broker, RabbitMQ, Kafka |
| **MessageChannel** | Abstraction định tuyến message bên trong Spring Integration | DirectChannel, ExecutorChannel |

Một **event** được mô tả ở mức nghiệp vụ; một **message** là envelope kỹ thuật. Một message có thể chứa command, event hoặc request/reply. Vì vậy một handler được gọi khi message tới channel có thể là event-driven xét theo kỹ thuật, dù payload là command.

### 2.2. Mặt mạnh và đánh đổi

**Ưu điểm:**

- Phản ứng khi có message, không cần lịch quét dữ liệu nghiệp vụ thường xuyên.
- Có thể giảm các lượt hỏi rỗng và độ trễ phát hiện dữ liệu so với polling thưa.
- Dễ kết nối với broker, listener hoặc HTTP inbound request đã có sẵn cơ chế dispatch.
- Cho phép phân tách producer và consumer, triển khai nhiều handler và thay đổi luồng tích hợp qua channel.

**Đánh đổi:**

- Cần hiểu rõ **cơ chế giao/nhận và ack** của broker/transport; không có bảo đảm chung cho mọi adapter.
- Sự kiện có thể lặp, bị trễ hoặc đến khác thứ tự mong muốn.
- Consumer quá chậm có thể làm backlog, tăng memory hoặc giảm khả năng đáp ứng của upstream.
- Khi event có nhiều subscriber, mỗi subscriber cần sở hữu logic lỗi và idempotency của mình.
- Khi thêm bất đồng bộ, tracing, transaction và thời điểm hoàn tất cần được thiết kế lại.

### 2.3. Ví dụ không nên chọn pattern này một cách máy móc

Nếu đối tác chỉ đưa file lên SFTP mỗi giờ và **không cung cấp sự kiện hoàn tất file**, Spring Integration thường cần **SFTP inbound polling adapter** để phát hiện file trước. Có thể chuyển file thành một message và **xử lý event-driven ở channel phía sau**; nhưng nhánh lấy dữ liệu từ SFTP vẫn do poller kích hoạt.

Tương tự, gọi REST API bằng HTTP outbound gateway khi nhận một event **không biến REST server thành message broker**. Từng lớp phải được mô tả đúng nguồn, đích và contract.

## 3. So sánh Event-driven Consumer và Polling Consumer

| Tiêu chí | Event-driven Consumer | Polling Consumer |
| --- | --- | --- |
| Tín hiệu bắt đầu | Message/notification được dispatch khi có dữ liệu | Scheduler/trigger gọi thao tác nhận |
| Spring Integration endpoint thường gặp | Consumer trên SubscribableChannel; message-driven inbound adapter | PollingConsumer trên PollableChannel; SourcePollingChannelAdapter trên MessageSource |
| Channel nội bộ | DirectChannel, ExecutorChannel, PublishSubscribeChannel | QueueChannel, PriorityChannel |
| Ví dụ nguồn | HTTP request, JMS/AMQP listener, Kafka listener | File/SFTP polling, database query, HTTP changes API |
| Độ trễ | Phụ thuộc transport, listener, hàng chờ và xử lý | Thêm thời gian chờ đến lượt poll tiếp theo |
| Lỗi và redelivery | Phụ thuộc broker/container/transaction và channel | Phụ thuộc source, filter, poller, ack và retry |
| Điều tiết tải | Prefetch, consumer concurrency, executor queue, broker lag | Poll interval, maxMessagesPerPoll, receiveTimeout |
| Thứ tự | Theo contract producer, broker partition/queue, concurrency | Theo source ordering, claim, batch và concurrency |
| Khả năng mở rộng | Listener/consumer group, partition, subscriber | Nhiều poller, lock/lease/metadata store |

**Điểm dễ nhầm:** Kafka Java consumer client có vòng gọi **poll() bên trong**, nhưng trong Spring Integration, **message-driven Kafka inbound adapter** dùng listener container để chuyển record vào flow. Không nên suy từ tên phương thức client rằng endpoint Spring Integration đang dùng **PollingConsumer**.

### 3.1. Khi nào phải dùng cả hai?

Giả sử SFTP nhận dữ liệu vào một ứng dụng có broker:

~~~mermaid
flowchart LR
    SFTP["SFTP: file chưa có cơ chế push"] --> POLL["SFTP SourcePollingChannelAdapter"]
    POLL --> VAL["Validate / Transform"]
    VAL --> BROKER["Outbound Adapter: publish event"]
    BROKER --> IN["Message-driven inbound adapter"]
    IN --> CH["SubscribableChannel"]
    CH --> BIZ["Handler cập nhật nghiệp vụ"]
~~~

**Đầu vào SFTP dùng polling**, trong khi **đầu nhận từ broker dùng event-driven consumer**. Hai pattern bổ trợ nhau; không cần ép toàn hệ thống thành một mẫu duy nhất.

## 4. Vị trí trong Spring Integration

Spring Integration tổ chức hệ thống theo thông điệp, channel và endpoint. Một consumer không nhất thiết trực tiếp biết producer dùng Kafka, HTTP hay filesystem; adapter có nhiệm vụ chuyển giao thức ngoài thành Spring **Message** phù hợp.

~~~mermaid
flowchart TD
    A["JMS/AMQP/Kafka listener hoặc HTTP inbound gateway"] --> ADAPTER["Inbound Adapter / Gateway"]
    ADAPTER --> CHANNEL["MessageChannel"]
    CHANNEL --> HANDLER["Service Activator / Filter / Router / Transformer"]
    HANDLER --> NEXT["Outbound Adapter / Gateway"]
    NEXT --> DEST["Database / API / Broker / File"]
    HANDLER --> AUDIT["Observability + error handling"]
    ADAPTER --> AUDIT
~~~

### 4.1. Năm thành phần cần phân biệt

1. **Inbound channel adapter:** nhận dữ liệu từ bên ngoài và phát message vào channel. Có thể là message-driven hoặc polling tùy nguồn và implementation.
2. **Inbound gateway:** nhận yêu cầu bên ngoài, đưa vào flow và thường chờ một **reply** để trả lại cho người gọi.
3. **MessageChannel:** định nghĩa cách chuyển một Spring Message từ endpoint này sang endpoint khác.
4. **MessageHandler/Service Activator:** xử lý message, có thể biến đổi hoặc tạo side effect.
5. **Outbound adapter/gateway:** gửi message ra hệ thống ngoài; adapter thường một chiều, gateway có request/reply.

Không nên gọi **event-driven** là một protocol cụ thể. HTTP request, JMS listener, RabbitMQ listener và Kafka listener có những đặc tính delivery rất khác nhau dù cùng có thể kích hoạt handler khi message tới.

### 4.2. Các loại channel liên quan

| Channel | Mô hình dispatch | Hệ quả |
| --- | --- | --- |
| **DirectChannel** | Gửi message đến một subscriber handler được chọn, thường trên thread người gửi | Dễ truyền exception và transaction context đồng bộ; handler chậm làm chậm sender |
| **ExecutorChannel** | Dispatch sang TaskExecutor | Tách thread, tăng concurrency; không được coi lời gọi send thành công là nghiệp vụ đã xong |
| **PublishSubscribeChannel** | Phát cho nhiều subscriber | Mỗi subscriber có side effect/lỗi riêng; cần hiểu thứ tự, executor và failure semantics |
| **QueueChannel** | Lưu message cho consumer chủ động gọi receive() | **PollableChannel**, thường cần polling consumer; không phải event-driven dispatch trực tiếp |
| **PriorityChannel** | PollableChannel ưu tiên message khi nhận | Ưu tiên không đồng nghĩa ordering theo thời gian |
| **RendezvousChannel** | Kênh trao đổi có cơ chế rendezvous/synchronous handoff | Thiết kế backpressure và blocking khác queue đơn giản |

Mặc định, **DirectChannel** có thể chuyển message trực tiếp tới handler trên cùng thread; nhưng nếu flow có một channel bất đồng bộ phía sau, thành công của lời gọi gửi phía trước không đảm bảo toàn bộ pipeline đã xử lý. **PublishSubscribeChannel** phát tới nhiều subscriber, còn DirectChannel không phải broadcast.

### 4.3. Một sơ đồ thread và thời điểm hoàn tất

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant D as DirectChannel
    participant H as Handler
    participant DB as Database
    P->>D: send(message)
    D->>H: handle(message) cùng call stack
    H->>DB: Ghi nghiệp vụ
    DB-->>H: Commit thành công
    H-->>D: Return
    D-->>P: send hoàn tất
    Note over P,DB: Chỉ minh họa luồng đồng bộ, không phải bảo đảm giao dịch đa hệ.
~~~

Nếu đổi DirectChannel thành ExecutorChannel, **sender** có thể trả về sau khi message được chấp nhận vào executor, còn handler chưa chạy. Cần giám sát kết quả downstream và xử lý lỗi theo đường bất đồng bộ.

## 5. Event-driven không đồng nghĩa “không bao giờ polling”

Mỗi lớp có thể dùng kỹ thuật riêng:

- JMS/AMQP listener có thể có một container và consumer callback từ broker; app flow nhận message-driven.
- Kafka consumer client phải poll broker để duy trì group/offset; **listener container** quản lý vòng poll và phát message cho Spring Integration.
- HTTP server chờ request trên socket; khi request đến, inbound gateway khởi tạo flow theo yêu cầu, không cần poll nguồn dữ liệu nghiệp vụ.
- File/SFTP/JDBC thường cần lịch polling, trừ khi có change notification/CDC/event source đáng tin được triển khai.
- QueueChannel nội bộ tích trữ message và yêu cầu một consumer chủ động `receive()`.

**Bài tập nhỏ:** ghi nhãn riêng cho ba câu: “client Kafka poll broker”, “Spring Integration Kafka adapter message-driven”, “handler trên DirectChannel được gọi khi send”. Ba câu đều có thể đúng đồng thời; chúng mô tả **ba tầng khác nhau**.

## 6. Thiết kế message contract cho consumer

Một hệ event-driven chỉ dễ bảo trì khi producer và consumer thống nhất **sự kiện nào đã xảy ra**, **dữ liệu nào có trong message**, **version hợp đồng** và **trạng thái xử lý được xác nhận ra sao**.

### 6.1. Payload, headers và metadata

Spring Integration dùng **Message<T>** (thuộc Spring Messaging) để kết hợp payload với headers. Ví dụ JSON payload nghiệp vụ:

~~~json
{
  "eventId": "EVT-LAB-1042",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T10:01:23+07:00",
  "aggregateId": "ORD-LAB-0501",
  "aggregateVersion": 3,
  "tenantId": "TENANT-LAB-01",
  "data": {
    "customerId": "CUST-LAB-032",
    "currency": "VND",
    "amount": 250000
  }
}
~~~

Các giá trị trên là dữ liệu minh họa, không phải schema mặc định của Spring Integration hoặc một broker. Headers vận chuyển có thể chứa **message ID, timestamp, trace ID, correlation ID, content type, routing key, partition key, retry count** tùy adapter và mapping. Không nên giả định header từ một nguồn ngoài luôn đáng tin hay luôn tồn tại.

### 6.2. Checklist hợp đồng

- [ ] Mỗi event có **eventId/business key ổn định**, không chỉ message ID mới sinh khi retry.
- [ ] Có **event type** và **schema version** hoặc một cách xác định schema tương đương.
- [ ] Có khóa tài nguyên/aggregate và tenant nếu ứng dụng cần cách ly dữ liệu.
- [ ] Thời điểm sự kiện, thời điểm nhận và thời điểm xử lý được phân biệt.
- [ ] Payload có quy tắc validate, kiểu dữ liệu, đơn vị đo, encoding và giới hạn kích thước.
- [ ] Xác định nguồn nào được phép phát loại sự kiện này và kiểm tra authentication/authorization phù hợp.
- [ ] Không đặt credential, password, private key hoặc token thô trong payload/header/log.
- [ ] Consumer chịu được field tùy chọn, version đã biết hoặc từ chối schema không tương thích có kiểm soát.
- [ ] Có quy tắc cho event đến trễ, đến trùng và đến sai thứ tự.
- [ ] Có tiêu chí phân biệt **received**, **validated**, **processed**, **committed** và **acknowledged**.

**EventId không đồng nghĩa MessageHeaders.ID.** Một event được gửi lại có thể có một message ID kỹ thuật mới; business event ID phải ổn định để idempotency có hiệu lực qua retry, restart và redelivery.

### 6.3. Consumer không tin tất cả headers

Ví dụ, nếu message HTTP mang header `X-Tenant-Id: TENANT-B`, backend không được mặc nhiên cho phép user từ TENANT-A cập nhật dữ liệu TENANT-B. Tenant hoặc quyền phải được kiểm tra với danh tính và nguồn đáng tin. Tương tự, nếu broker chỉ đảm bảo producer có thể publish topic, consumer vẫn cần kiểm tra schema và điều kiện nghiệp vụ trước khi ghi dữ liệu nhạy cảm.

### 6.4. Version và khả năng tương thích

Giả sử OrderCreated v1 có `customerId` và `amount`, còn v2 thêm `currency`, `discount`. Có thể giữ compatibility bằng việc thêm field tùy chọn với default phù hợp; nhưng đổi ngữ nghĩa `amount` từ đơn vị tiền nhỏ nhất sang đơn vị tiền lớn là **thay đổi breaking** dù JSON vẫn parse được.

Quyết định được ghi:

| Tình huống | Cách xử lý gợi ý |
| --- | --- |
| Nhận schemaVersion được hỗ trợ | Parse/validate và xử lý |
| Nhận version chưa được hỗ trợ | Quarantine/DLQ, cảnh báo schema mismatch; không âm thầm bỏ |
| Thiếu trường bắt buộc | Reject có lý do hoặc chuyển kho lỗi |
| Có field mới không ảnh hưởng nghiệp vụ | Cho phép theo chính sách tương thích |
| Sự kiện quá cũ cho cùng aggregate | So version/trạng thái trước khi ghi; bỏ qua hoặc đối soát |

## 7. Java DSL: consumer event-driven đơn giản với DirectChannel

Ta bắt đầu không có broker để cô lập chính xác vai trò channel và handler. **Một producer gọi `send(message)`**, Spring Integration chuyển message tới service activator đang subscribe `DirectChannel`. Không có poller trong ví dụ này.

### 7.1. Cấu hình luồng Spring Integration

Mã minh họa theo phong cách Spring Integration 6.x và Java 17, dùng **spring-integration-core** và Spring context. Khi đưa vào dự án thật cần kiểm tra dependency/version thực tế.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class OrderEventIntegration {

    @Bean
    public MessageChannel orderEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow orderEventFlow() {
        return IntegrationFlow
                .from("orderEvents")
                .handle((MessageHandler) message -> {
                    Object payload = message.getPayload();
                    System.out.println("Received event: " + payload);
                    // Thực tế: validate -> idempotency -> business transaction.
                })
                .get();
    }
}
~~~

Handler đăng ký subscribe để nhận message được gửi vào channel có tên **orderEvents**. Với một DirectChannel đồng bộ và handler chỉ in log, lời gọi gửi có thể đợi tới khi handler trả về; nhưng **in log không phải một cam kết xử lý bền vững**.

### 7.2. Producer ở phía ứng dụng

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final MessageChannel channel;

    public OrderEventPublisher(
            @Qualifier("orderEvents") MessageChannel channel) {
        this.channel = channel;
    }

    public void publish(String eventId, String orderId) {
        String event = "OrderCreated:" + orderId;
        boolean accepted = channel.send(
                MessageBuilder.withPayload(event)
                        .setHeader("businessEventId", eventId)
                        .build()
        );
        if (!accepted) {
            throw new IllegalStateException("Message not accepted");
        }
    }
}
~~~

**Điểm cần hiểu:** Java producer đang gửi vào channel của ứng dụng, **không gửi tới broker bền vững**. Nếu quá trình gọi handler ném exception, sender đồng bộ có thể nhận exception; với một channel bất đồng bộ, kết quả `send()` thường chỉ nói rằng message được nhận để dispatch tiếp.

### 7.3. MessageHandler, Service Activator và transformer

Flow có thể gồm nhiều bước:

~~~text
OrderEventPublisher
  -> DirectChannel
  -> Filter (chỉ OrderCreated hợp lệ)
  -> Transformer (JSON -> OrderEvent DTO)
  -> Service Activator (businessService.accept)
  -> Outbound Adapter hoặc Gateway (khi cần)
~~~

Một transformer không nên quyết định commit nghiệp vụ chỉ từ việc parse thành công. Service activator phải kiểm tra **business key, trạng thái đơn hàng, quyền tenant, tính hợp lệ dữ liệu**, và chỉ công nhận xử lý thành công ở điểm kết quả được lưu theo contract.

### 7.4. Java annotation thay cho Java DSL

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class AuditEventHandler {

    @ServiceActivator(inputChannel = "orderEvents")
    public void onEvent(String payload) {
        System.out.println("Processed: " + payload);
    }
}
~~~

Chú ý ví dụ này là **một cách thay thế** handler đã khai báo trong DSL, không nên gắn cả hai vào cùng DirectChannel rồi tưởng cả hai luôn nhận mỗi message. **DirectChannel chọn một subscriber handler cho mỗi lần dispatch**, không broadcast; nếu cần fan-out, phải chọn cấu trúc channel phù hợp như PublishSubscribeChannel.

## 8. Dispatch bất đồng bộ với ExecutorChannel và fan-out

Một handler gọi API ngoài mất nhiều thời gian có thể làm thread nguồn bị giữ lâu. Bạn có thể **tách dispatch qua executor**, nhưng đổi lại phải quản lý queue, lỗi và thứ tự.

### 8.1. ExecutorChannel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.messaging.MessageChannel;

@Configuration
public class AsyncEventChannels {

    @Bean
    public ThreadPoolTaskExecutor orderEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-events-");
        return executor;
    }

    @Bean
    public MessageChannel asynchronousOrderEvents(
            ThreadPoolTaskExecutor orderEventExecutor) {
        return new ExecutorChannel(orderEventExecutor);
    }
}
~~~

**Những điểm phải thiết kế tiếp:**

- Khi executor queue đầy, `send()` có thể bị từ chối hoặc chịu chính sách rejection của executor. Không được mặc nhiên đánh rơi message.
- Handler chạy ở thread khác, transaction context của thread gửi **không tự động truyền sang**.
- Handler có thể xử lý song song, hoàn tất khác thứ tự gửi.
- Exception trong handler không nhất thiết quay về producer; cần error handling và giám sát.
- Queue trong executor không mặc định là **durable store** qua JVM crash.
- Nếu message đến từ JMS/AMQP/Kafka, phải kiểm tra lại **ack timing**; đẩy nhanh vào executor rồi ack broker quá sớm có thể mất dữ liệu khi JVM chết.

### 8.2. PublishSubscribeChannel để phát nhiều nhánh

~~~mermaid
flowchart LR
    EVENT["OrderCreated"] --> PUB["PublishSubscribeChannel"]
    PUB --> INVOICE["Invoice handler"]
    PUB --> INVENTORY["Inventory handler"]
    PUB --> ANALYTICS["Analytics handler"]
~~~

**Fan-out** hữu ích khi nhiều thành phần độc lập quan tâm một event. Nhưng một failure của invoice handler ảnh hưởng thế nào đến inventory handler tùy **channel dispatch, executor, transaction, error strategy**. Không mặc định cả ba nhận và commit thành công theo một giao dịch xuyên hệ.

Nếu yêu cầu **mỗi subscriber phải nhận lại message sau crash**, việc dùng một PublishSubscribeChannel trong bộ nhớ là chưa đủ; cân nhắc **broker topic/exchange, durable subscription, consumer group hoặc cơ chế outbox/inbox** phù hợp.

### 8.3. DirectChannel không phải broadcast

Nếu gắn hai service activator trên cùng DirectChannel, channel sẽ chọn subscriber cho từng message theo chiến lược dispatch. Với cách tổ chức mặc định, không nên mong cả hai handler đều chạy cho mỗi message. Chọn **PublishSubscribeChannel** khi mục đích là sao chép luồng message tới nhiều subscriber.

## 9. Message-driven inbound adapter và inbound gateway

Trong Spring Integration, event-driven thường bắt đầu từ **adapter hoặc gateway** nhận một tín hiệu bên ngoài. Hai loại endpoint không nên bị nhầm vì khác **hợp đồng reply/ack**.

| Inbound endpoint | Đầu vào | Kết quả hướng ứng dụng | Tình huống |
| --- | --- | --- | --- |
| **Message-driven inbound channel adapter** | Broker/container listener nhận message | Phát message tới channel, thường một chiều ở phía flow | JMS, AMQP, Kafka events |
| **Inbound gateway** | Request vào từ hệ thống khác | Gửi request vào flow và chờ hoặc ánh xạ reply | HTTP request, JMS/AMQP request-reply |
| **Polling inbound channel adapter** | MessageSource được lịch kích hoạt | Gửi message vừa lấy vào channel | File, SFTP, JDBC poll |
| **Application channel producer** | Code nội bộ gọi MessageChannel.send | Flow xử lý message ngay hoặc bất đồng bộ | Business service phát event nội bộ |

### 9.1. Một chiều khác request/reply

Khi khách hàng gọi HTTP **POST /orders**, server thường phải trả một HTTP response. Nếu dùng **HTTP inbound gateway**, request thành Spring Message; flow xử lý và trả reply dưới dạng HTTP response. Đây là *request/reply* dù handler được kích hoạt theo request.

Ngược lại, khi một RabbitMQ queue chứa **OrderCreated**, message-driven inbound adapter có thể chuyển message đến handler, sau đó acknowledgment với broker được xử lý theo cấu hình container. Không nên tự suy rằng mỗi event phải có reply message cho producer.

### 9.2. Đổi HTTP request thành event nghiệp vụ

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant H as HTTP Inbound Gateway
    participant V as Validate + Business Service
    participant O as Outbox
    participant B as Broker
    participant L as Message-driven Inbound Adapter
    participant S as Subscriber
    C->>H: POST /orders
    H->>V: Spring Message request
    V->>O: Commit order + outbox event
    V-->>H: Kết quả tạo đơn
    H-->>C: HTTP response
    O->>B: Publish (qua relay)
    B->>L: Deliver event
    L->>S: Process OrderCreated
~~~

Thiết kế này minh họa **transactional outbox**: lưu thay đổi nghiệp vụ và outbox record trong cùng transaction DB, rồi có relay phát event. Nếu relay chết sau khi publish nhưng trước khi đánh dấu đã phát, broker có thể nhận lại event; subscriber phải idempotent.

### 9.3. Không coi một HTTP 200 là toàn hệ thống đã xử lý

Khi gateway trả HTTP 200/201, nó thường xác nhận điều kiện của **request handler** theo hợp đồng API. Nó không chứng minh tất cả consumer bất đồng bộ đã hoàn tất. Nếu API nhận xử lý bất đồng bộ, có thể dùng 202 Accepted và một resource trạng thái; chính sách cụ thể tùy hệ thống.

## 10. Event-driven consumer với JMS, AMQP và Kafka

Điểm chung của ba hệ là có thành phần hạ tầng vận chuyển message, nhưng **acknowledgment, đơn vị ordering và cách redelivery** không giống nhau. Khi kết nối Spring Integration, nên chọn inbound adapter hoặc gateway phù hợp với **giao thức và mục đích**, không vì muốn mọi cấu hình trông giống nhau.

### 10.1. JMS: listener và transaction

**JMS** định nghĩa một API messaging Java với các destination như Queue và Topic. Message listener container nhận message và chuyển tới consumer. Spring Integration cung cấp các adapter/gateway JMS, bao gồm cách tiếp nhận **message-driven**.

Luồng điển hình:

~~~text
JMS Queue "orders.events"
    -> JMS listener container
    -> Spring Integration JMS message-driven inbound adapter
    -> MessageChannel
    -> validate + service activator
    -> database/outbound adapter
~~~

Một ví dụ Java DSL *minh họa* nhánh listener:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class JmsInboundFlow {

    @Bean
    public IntegrationFlow orderJmsFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(
                    Jms.messageDrivenChannelAdapter(connectionFactory)
                       .destination("orders.events")
                )
                .handle((MessageHandler) message -> {
                    Object event = message.getPayload();
                    System.out.println("JMS message: " + event);
                    // Business processing + idempotent persistence.
                })
                .get();
    }
}
~~~

Đây là ví dụ theo họ API Spring Integration JMS/Java DSL hiện đại; tên overload, container factory, package `jakarta.jms` và dependency cần đối chiếu với phiên bản đang sử dụng. Đoạn mã **chưa cấu hình durability, transaction manager hoặc DLQ**, nên không nên dùng nguyên trạng làm tiêu chuẩn production.

**Điểm phải quyết định trước khi triển khai:**

- JMS Queue thường giao message cho một consumer trong nhóm cạnh tranh; Topic có semantics publish-subscribe, durability phụ thuộc subscription và broker.
- Mode acknowledge như AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE hoặc phiên giao dịch có hành vi khác nhau; Spring listener container và adapter còn ảnh hưởng thời điểm ack thực tế.
- Nếu handler thất bại, message có được redeliver không, sau bao nhiêu lần, đưa vào DLQ ở đâu?
- Khi handler đẩy ngay sang **ExecutorChannel** rồi return, listener có thể kết thúc trước khi công việc bất đồng bộ thật sự commit. Không mặc định exception ở thread sau sẽ rollback việc tiêu thụ ở broker.
- Giao dịch JMS không tự bao trùm một HTTP request hoặc transaction ở DB khác; cần outbox/idempotency nếu không có cơ chế transaction phối hợp phù hợp.

### 10.2. AMQP/RabbitMQ: ack, nack, prefetch và dead-letter

AMQP broker như RabbitMQ quản lý queue, exchange và routing. Spring Integration có AMQP inbound adapter dựa trên listener container, đưa các message được broker giao tới channel.

| Thành phần | Ý nghĩa cần kiểm tra |
| --- | --- |
| **Exchange/routing key** | Producer phát message đến queue nào theo binding |
| **Queue** | Có durable không, message có persistent không, có TTL/quorum/policy không |
| **Consumer listener** | Bao nhiêu consumer, kết nối/channel nào nhận message |
| **Prefetch** | Một consumer được broker giao bao nhiêu message chưa ack |
| **Ack / nack / reject** | Khi xử lý xong, lỗi hoặc muốn requeue |
| **Dead-letter** | Message lỗi/TTL/quá chính sách chuyển đi đâu |
| **Ordering** | Concurrency, requeue và redelivery có thể thay thứ tự quan sát |

Giả mã kiến trúc:

~~~text
RabbitMQ orders.exchange
  -> orders.created.queue
  -> AMQP listener container
  -> AMQP message-driven inbound adapter
  -> DirectChannel
  -> validate + idempotent order handler
  -> ack theo cấu hình listener và kết quả xử lý
~~~

**Lưu ý ack:** không ack ngay khi chỉ vừa enqueue vào một executor memory nếu tiêu chí nghiệp vụ là DB đã commit. Nếu bắt buộc dùng async channel, cần một thiết kế bền vững và cách phối hợp acknowledgement rõ ràng. Với redelivery, cùng message có thể được xử lý lại; cần business idempotency.

**DLQ không phải thùng rác tự động:** phải có retention, cơ chế đọc/quarantine, phân loại lỗi, quyền truy cập, cảnh báo và quy trình replay có kiểm soát.

### 10.3. Kafka: listener container, partition và offset

Kafka lưu record trong topic phân partition. Consumer group phân chia partition cho các consumer instance; listener container có thể gọi handler khi record/batch được poll về.

~~~mermaid
flowchart LR
    PRODUCER["Order Service"] --> TOPIC["Kafka topic: orders.events"]
    TOPIC --> P0["Partition 0"]
    TOPIC --> P1["Partition 1"]
    P0 --> C0["Consumer group: instance A"]
    P1 --> C1["Consumer group: instance B"]
    C0 --> SI0["Spring Integration Kafka inbound adapter"]
    C1 --> SI1["Spring Integration Kafka inbound adapter"]
    SI0 --> H["Handler + idempotency"]
    SI1 --> H
~~~

**Cần biết chính xác:**

1. **Offset:** offset nào được commit và thời điểm commit so với handler/transaction?
2. **Group:** những consumer cùng group thường chia partition, không phải mỗi consumer nhận toàn bộ bản sao message.
3. **Partition key:** nếu cần thứ tự sự kiện của một aggregate, chọn key/partitioning phù hợp; Kafka bảo toàn thứ tự trong partition theo điều kiện của broker/producer, không bảo toàn thứ tự tổng qua mọi partition.
4. **Rebalance:** partition ownership thay đổi khi instance lên/xuống; một record có thể được xử lý lại nếu commit/processing chưa hoàn tất.
5. **Retry và DLT:** record lỗi được retry, bỏ qua hoặc đưa dead-letter topic theo cấu hình; không để một record hỏng làm treo cả partition vô thời hạn.
6. **Async handoff:** nếu listener trả về trước khi handler downstream commit, phải thiết kế lại offset/ack và failure path.

Kafka hỗ trợ nhiều lựa chọn như record/batch listener, transaction và error handlers; cấu hình thực tế phụ thuộc **Spring for Apache Kafka và Spring Integration Kafka** đang dùng. Không lấy một cấu hình auto-commit hoặc manual-ack làm quy luật chung cho mọi adapter.

### 10.4. Bảng so sánh cho quyết định thiết kế

| Câu hỏi | JMS | AMQP/RabbitMQ | Kafka |
| --- | --- | --- | --- |
| Đơn vị tiêu thụ | Message trong Queue/Topic | Message từ queue | Record/batch trong partition |
| Giao tiếp Spring Integration | JMS listener adapter/gateway | AMQP listener adapter/gateway | Kafka listener adapter |
| Xác nhận tiến độ | Ack/transaction theo session/container | Ack/nack và broker delivery | Commit offset/transaction theo container |
| Tái giao | Redelivery theo broker/session | Requeue/redelivery/DLQ | Reprocess từ offset, retry/DLT |
| Thứ tự | Tùy destination và concurrency | Tùy queue, concurrency, requeue | Trong partition, với điều kiện liên quan |
| Fan-out | Topic/subscription | Exchange → nhiều queue | Nhiều consumer group |
| Backpressure | Consumer concurrency/prefetch nếu hỗ trợ | Prefetch + concurrency + queue depth | Lag + partitions + concurrency |

Không có hàng nào đồng nghĩa **exactly-once trên tất cả đích ngoài**. Khi consumer cập nhật DB và sau đó gửi HTTP đến dịch vụ khác, bạn vẫn cần thiết kế idempotency và xử lý sự cố giữa hai thao tác.

## 11. HTTP, file, SFTP và database trong kiến trúc event-driven

Không phải giao thức nào cũng cung cấp “push event” nguyên bản theo cách ứng dụng cần. Ta có thể kết hợp adapter để chuyển đổi **sự xuất hiện của dữ liệu** thành message event-driven trong phần xử lý phía sau.

### 11.1. HTTP inbound gateway

HTTP server nhận request khi client gọi, Spring Integration **HTTP inbound gateway** chuyển request thành Message, định tuyến tới flow, chờ reply khi theo request/reply contract. Cần:

- Xác thực caller và kiểm tra authorization với resource thực tế.
- Giới hạn payload, validate schema, content type và tenant.
- Đặt timeout hợp lý; nếu xử lý dài, cân nhắc bất đồng bộ qua broker và 202 Accepted/status endpoint.
- Đảm bảo client retry HTTP không tạo side effect trùng; dùng business idempotency key nếu phù hợp.
- Không xem HTTP request header tùy ý là nguồn đáng tin của quyền truy cập.

Một HTTP outbound gateway gọi hệ ngoài sau khi nhận event cũng có thể timeout khi đích đã nhận yêu cầu. Consumer phải **đọc lại trạng thái hoặc retry idempotent** thay vì mặc định timeout nghĩa là bên kia chưa thực hiện.

### 11.2. File và SFTP: event-driven ở downstream, polling ở source

Trong nhiều thiết kế, file hoặc SFTP inbound adapter phải **poll để phát hiện file mới**. Khi adapter tạo Spring Message và gửi tới DirectChannel, các handler **được dispatch theo message**. Đây là một flow kết hợp:

~~~text
File/SFTP (poll theo lịch)
    -> Message<File> / Message<InputStream>
    -> DirectChannel
    -> Validate file hoàn tất
    -> Transform CSV/JSON
    -> Handler -> DB / outbound broker adapter
~~~

Với file/SFTP, dữ liệu có thể đang upload, nên cần quy ước tên tạm/rename, marker, bộ lọc đã nhận và metadata store bền vững. Không xóa/di chuyển file khi chỉ vừa gửi được message mà nghiệp vụ phía sau chưa commit. Nếu stream, phải quản lý tài nguyên stream/session và chiến lược retry tương ứng.

### 11.3. Database: polling, CDC và outbox

Database có thể cung cấp thay đổi theo ba hướng:

| Cách | Bản chất | Khi nào phù hợp |
| --- | --- | --- |
| **JDBC polling** | Chạy truy vấn theo lịch để tìm hàng READY | Ứng dụng nhỏ hoặc DB không có change stream |
| **CDC connector** | Đọc thay đổi từ log giao dịch, phát message | Cần dòng sự kiện thay đổi có nguồn DB và tooling phù hợp |
| **Transactional outbox** | Nghiệp vụ ghi bản ghi outbox trong cùng transaction, relay phát sự kiện | Muốn gắn commit nghiệp vụ với việc tạo bản ghi event đáng tin |

**CDC** có thể là event-driven xét từ consumer nhận từ broker, dù connector bên dưới đọc transaction log. **Outbox relay** cũng có thể dùng polling nhưng downstream Kafka/JMS listener vẫn là event-driven. Cần mô tả rõ nguồn sự thật và nơi quyết định một event đã được phát/nhận.

### 11.4. Khi nào gateway tốt hơn adapter?

| Nhu cầu | Gợi ý chọn |
| --- | --- |
| Nhận webhook rồi trả trạng thái xử lý cho caller | HTTP inbound gateway |
| Nhận một chiều từ queue events | Message-driven inbound adapter |
| Gọi API cần response để tiếp tục flow | Outbound gateway |
| Gửi thông báo/fire-and-forget sang một hệ đích | Outbound channel adapter |
| Gửi message và chờ reply qua JMS/AMQP | Inbound/outbound gateway với correlation và timeout |

Đừng dùng gateway request/reply cho event broadcast nếu không có nhu cầu reply. Mỗi reply chờ đồng bộ làm tăng coupling, nguy cơ timeout và nhu cầu giữ correlation state.

## 12. Delivery semantics: nhận message không phải xử lý exactly-once

Event-driven thường vận hành dưới một hoặc nhiều lớp bảo đảm:

| Mức mục tiêu | Mô tả | Hệ quả |
| --- | --- | --- |
| **At-most-once** | Một message không được redeliver sau khi hệ thống coi đã nhận | Có thể mất tác động nghiệp vụ khi lỗi sau ack |
| **At-least-once** | Message có thể được giao lại khi chưa xác nhận thành công | Cần idempotency để tránh side effect trùng |
| **Effectively-once** | Tác động nghiệp vụ cuối được bảo vệ khỏi duplicate | Cần business key, transaction phù hợp và reconciliation |
| **Exactly-once có phạm vi** | Một số broker/stream có transaction semantics trong tập giới hạn | Không tự bảo đảm HTTP, file, DB ngoài và toàn bộ hệ thống cùng đúng một lần |

### 12.1. Cửa sổ lỗi kinh điển

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant DB as Business DB
    B->>L: Deliver OrderCreated(eventId=E1)
    L->>DB: Insert order using E1
    DB-->>L: Commit success
    Note over L: JVM crash trước ack/offset commit
    B->>L: Redeliver E1
    L->>DB: Repeat operation
    Note over DB: Nếu không idempotent, side effect có thể lặp
~~~

**Nguyên tắc:** thiết kế khả năng nhận lại cùng event mà không phá dữ liệu, và không xác nhận quá sớm khi hành động nghiệp vụ chưa đạt điều kiện hoàn tất.

### 12.2. Một số lớp kiểm soát cần phối hợp

1. **Broker delivery/ack policy:** xác định khi nào message bị redeliver hoặc offset được commit.
2. **Consumer transaction:** xử lý trong DB với unique constraint/optimistic concurrency phù hợp.
3. **Inbox/idempotent repository:** lưu event đã xử lý theo business eventId có nguồn đáng tin.
4. **Outbox cho sự kiện phát tiếp:** gắn tạo event downstream với transaction nghiệp vụ.
5. **Reconciliation:** xử lý ACK mất, timeout và khoảng cách giữa nhiều hệ thống.
6. **Dead-letter/quarantine:** lưu sự kiện không xử lý được kèm lý do, owner và khả năng replay.

## 13. Idempotent Consumer và business key

Trong EIP, **Idempotent Consumer** là mẫu rất gần với Event-driven Consumer: khi cùng event được nhận lại, tác động không được nhân đôi ngoài chủ ý.

### 13.1. Chọn khóa ổn định

Một số lựa chọn:

- **eventId** do producer phát và giữ nguyên qua retry.
- **aggregateId + aggregateVersion** khi một phiên bản thay đổi nghiệp vụ cần xử lý một lần.
- **sourceSystem + businessKey + operationVersion** khi tích hợp nhiều nguồn.

Không nên chỉ dùng message ID của runtime hoặc timestamp nhận; chúng có thể thay đổi khi redelivery. Với multi-tenant, business key đôi khi cần bao gồm tenant/source để không gộp hai sự kiện hợp lệ của hai phạm vi khác nhau.

### 13.2. Inbox table mẫu

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(180) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Nếu handler cập nhật một DB nghiệp vụ, có thể ghi vào inbox **trong cùng DB transaction** với thay đổi nghiệp vụ. Khi duplicate làm vi phạm unique key, consumer có thể nhận diện đã xử lý. Nhưng cần kiểm tra liệu bản ghi inbox phản ánh **xử lý thành công** hay chỉ “đã bắt đầu”.

### 13.3. Giả mã idempotent event handler

~~~text
consume(message):
  event = validateSchemaAndSource(message)
  with transaction:
      if inbox.exists(consumerName, event.eventId):
          return ALREADY_PROCESSED

      current = loadAggregateForUpdate(event.aggregateId)
      if event.aggregateVersion <= current.lastAppliedVersion:
          inbox.recordProcessed(event.eventId)
          return STALE_OR_DUPLICATE

      applyBusinessChange(current, event)
      inbox.recordProcessed(event.eventId)
      commit

  acknowledgeByTransportContract()
~~~

Đây là mô hình logic, không phải Java hoàn chỉnh. Phải xử lý cạnh tranh bằng unique constraint và transaction đúng isolation; thao tác “check rồi insert” độc lập không atomic có thể cho hai consumer cùng đi qua. Nếu message chứa event version bị nhảy cóc, policy cần quyết định có chờ event thiếu hoặc lấy snapshot từ nguồn.

### 13.4. Side effect ngoài DB

Nếu consumer gửi email hoặc gọi HTTP payment API, giao dịch inbox trong DB **không rollback** email hay payment đã thực hiện. Cần:

- API đích hỗ trợ idempotency key hoặc query kết quả theo business key.
- Outbox/worker cho side effect sau commit với retry có kiểm soát.
- Reconciliation khi response bị mất nhưng side effect có thể đã xảy ra.
- Tránh “bắt exception rồi return success” khiến broker ack trước khi xử lý.

### 13.5. Nhiều subscriber phải dedupe theo consumer

Với một topic, Billing và Analytics đều cần xử lý E1 một lần **cho từng nghiệp vụ của mình**. Inbox key nên có **consumer name hoặc handler identity**. Nếu dùng một bộ dedupe toàn cục không phân biệt subscriber, Billing xử lý E1 xong có thể khiến Analytics bỏ qua E1 sai mục đích.

## 14. Ordering, concurrency và bảo đảm trạng thái nghiệp vụ

Event-driven thường nhấn mạnh tốc độ, nhưng **nhiều event đến cùng lúc không được làm trạng thái mới bị ghi đè bởi trạng thái cũ**.

### 14.1. Ba kiểu ordering khác nhau

| Kiểu thứ tự | Ví dụ | Điều kiện |
| --- | --- | --- |
| **Transport order** | Kafka trong cùng partition | Producer, partition key, retry và consumer phải đáp ứng điều kiện |
| **Processing start order** | Handler bắt đầu với E1 trước E2 | Executor concurrency và scheduling có thể thay đổi |
| **Commit order** | E2 commit trước E1 | Handler latency, DB lock, gọi API và retry ảnh hưởng |

Một queue giao E1 trước E2 **không tự bảo đảm E1 commit trước E2** nếu app dispatch qua nhiều thread. Khi trạng thái tài khoản, đơn hàng hoặc tồn kho có phụ thuộc chuỗi, dùng **aggregate version** hoặc xử lý tuần tự theo key để ngăn stale update.

### 14.2. Ví dụ event đến sai thứ tự

~~~text
E1: AccountStatusChanged(user=U7, version=5, status=ACTIVE)
E2: AccountStatusChanged(user=U7, version=6, status=DISABLED)

Consumer nhận E2 trước và lưu DISABLED.
E1 đến trễ.

Sai: ghi lại ACTIVE vì đây là message vừa nhận gần nhất.
Đúng: kiểm tra version 5 < version 6, bỏ qua hoặc đối soát theo nguồn.
~~~

Đây là bài toán **state versioning**, không thể sửa chỉ bằng tăng độ ưu tiên message. Khi một version bị thiếu, chính sách có thể yêu cầu đọc lại state từ nguồn có thẩm quyền hoặc chờ dữ liệu bổ sung.

### 14.3. Chiến lược chọn mức concurrency

- **Serial consumer:** phù hợp nghiệp vụ cần thứ tự đơn giản, throughput có giới hạn.
- **Partition theo business key:** giữ thứ tự trong cùng customer/order nhưng xử lý song song các key khác.
- **Optimistic concurrency:** ghi với điều kiện version chưa thay đổi; khi xung đột xử lý retry/skip có kiểm soát.
- **Pessimistic lock/claim:** bảo vệ hàng DB theo giao dịch, cần tránh lock quá lâu.
- **Compensation:** nếu đã phát tác động không đảo ngược, có quy trình bù trừ nghiệp vụ được cho phép.

### 14.4. Fan-out và trách nhiệm thành công

Giả sử OrderCreated được gửi tới ba handler **Inventory**, **Invoice** và **Analytics**:

~~~mermaid
flowchart TD
    E["OrderCreated E1"] --> TOPIC["Broker topic hoặc fan-out"]
    TOPIC --> A["Inventory: commit OK"]
    TOPIC --> B["Invoice: lỗi tạm thời"]
    TOPIC --> C["Analytics: xử lý OK"]
    B --> RETRY["Retry / DLT / Escalation"]
~~~

Đây không phải một distributed transaction mặc định. **Inventory thành công không có nghĩa Invoice đã thành công**, và retry của Invoice không cần chạy lại toàn bộ nghiệp vụ Inventory nếu mỗi subscriber có delivery/idempotency riêng.

Nếu cùng **PublishSubscribeChannel trong JVM**, cần xét failure propagation cụ thể và việc một handler lỗi có thể ảnh hưởng các subscriber khác khi dùng dispatch đồng bộ. Với broker nhiều queue/group, mỗi subscription quản lý tiến độ độc lập theo semantics của broker.

## 15. Error flow, retry và dead-letter

Một consumer có thể thất bại ở **nhận/deserialize**, **validate**, **nghiệp vụ**, **commit DB**, **gọi hệ ngoài**, hoặc **ack broker**. Không nên đẩy tất cả vào cùng một vòng retry không giới hạn.

### 15.1. Phân loại lỗi

| Loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Schema/deserialize** | JSON thiếu field bắt buộc, version chưa hỗ trợ | Quarantine/DLT, lưu lý do và owner; không retry vô hạn |
| **Authorization/source trust** | Event giả nguồn, tenant không hợp lệ | Từ chối, cảnh báo an ninh, không tạo side effect |
| **Business validation** | Đơn hàng vi phạm quy tắc đã xác định | Reject nghiệp vụ, audit, có thể không redeliver |
| **Transient infrastructure** | DB timeout, kết nối broker tạm lỗi, HTTP 503 | Retry với backoff và giới hạn |
| **Rate limit** | HTTP 429, quota của dịch vụ đích | Tôn trọng Retry-After và giảm concurrency |
| **Concurrency conflict** | Optimistic locking / unique constraint | Phân biệt duplicate hợp lệ với xung đột cần xử lý |
| **Poison message** | Một event luôn gây exception | DLT/quarantine sau giới hạn retry |
| **Ack failure/rebalance** | Business commit rồi offset chưa commit | Có thể redeliver, cần idempotency |

### 15.2. Đồng bộ khác bất đồng bộ trong xử lý exception

**DirectChannel + handler đồng bộ:** exception từ handler có thể đi ngược qua call stack tới inbound endpoint. Broker listener/container có thể dùng exception để quyết định rollback/redelivery nếu cấu hình phù hợp.

**ExecutorChannel:** handler chạy ở thread khác; producer hoặc listener thường **không thể nhận exception như một lời gọi đồng bộ bình thường**. Cần đường lỗi bất đồng bộ, retry và durable handoff nếu muốn bảo toàn message.

**Gateway:** exception hoặc timeout phải được ánh xạ thành response/cơ chế xử lý tương ứng. Không nên gửi HTTP 200 thành công khi downstream đã fail nhưng flow nuốt lỗi, trừ khi contract minh bạch chỉ xác nhận “đã tiếp nhận”.

### 15.3. ErrorChannel và ErrorMessage

Spring Integration hỗ trợ chuyển nhiều lỗi bất đồng bộ vào **error channel** dưới dạng **ErrorMessage**. Tuy nhiên nguồn lỗi, cách tạo ErrorMessage và đường đi thực tế phụ thuộc adapter, endpoint, cấu hình ErrorHandler và boundary bất đồng bộ.

**Checklist khi xây error flow:**

- [ ] Phân biệt lỗi nhận message, chuyển đổi dữ liệu, handler và outbound adapter.
- [ ] Log nguồn, business eventId, target, attempt, exception class và trace ID trong mức an toàn.
- [ ] Đừng ghi plaintext credential hoặc payload chứa dữ liệu nhạy cảm không cần thiết.
- [ ] Với transient error, xác định retry/backoff và số lần tối đa.
- [ ] Với lỗi không thể tự sửa, có DLT/quarantine và owner có khả năng replay.
- [ ] Xác minh error handler **ném lại**, **ack**, **nack** hay **nuốt lỗi** theo giao thức.
- [ ] Không đưa message vào một hàng lỗi **chỉ trong memory** rồi khẳng định đã bảo toàn qua crash.
- [ ] Theo dõi số lỗi lặp cùng key để tránh poison event gây nghẽn.

### 15.4. Retry và dead-letter thành một quy trình vận hành

~~~mermaid
flowchart TD
    M["Inbound event"] --> V{"Validate schema/source"}
    V -->|Sai| Q["Quarantine/DLT: reason + owner"]
    V -->|Đúng| H["Idempotent business handler"]
    H --> C{"Business commit?"}
    C -->|Đạt| ACK["Ack/offset theo transport"]
    C -->|Lỗi tạm| RT{"Retry budget còn?"}
    RT -->|Có| BACK["Backoff / redelivery"]
    BACK --> H
    RT -->|Hết| Q
    C -->|Permanent failure| Q
    Q --> OPS["Review + repair + controlled replay"]
~~~

**Replay phải có kiểm soát:** khi đưa message từ DLT vào luồng chính, không bỏ qua validation, idempotency hoặc version check; nếu lỗi là schema mismatch, cần triển khai consumer tương thích trước khi replay.

### 15.5. Khi acknowledgment không tự động phù hợp

Nếu một listener container xác nhận message ngay sau khi adapter **send thành công vào ExecutorChannel**, message có thể mất khi process chết trước business commit. Có vài hướng:

1. Giữ phần xử lý cần xác nhận **đồng bộ trong phạm vi listener/transaction** khi phù hợp tải.
2. Ghi message vào một **durable inbox/queue** trước khi ack broker, sau đó xử lý bất đồng bộ với retry.
3. Dùng manual ack/container mode được hỗ trợ và quản lý lifecycle/context đúng cách; kiểm tra các ràng buộc thread, ack và timeout của broker.
4. Thiết kế consumer at-least-once với idempotency và kiểm thử kill-process.

Không áp dụng manual acknowledgment một cách chung chung cho JMS, AMQP và Kafka; mỗi loại có contract và API riêng.

### 15.6. Sự khác biệt giữa DLT và lỗi nghiệp vụ

Một event **PaymentDeclined** là sự kiện nghiệp vụ hợp lệ, không phải lỗi hạ tầng cần DLT. Ngược lại, consumer không parse nổi PaymentApproved vì schema không tương thích là lỗi tích hợp. DLT dùng cho message **chưa được xử lý đúng theo contract**, còn trạng thái business như “từ chối thanh toán” cần thể hiện trong domain model.

## 16. Backpressure và năng lực xử lý

Event-driven consumer không có lịch hỏi nghiệp vụ để giảm/tăng nhịp đơn giản như polling; nhưng vẫn phải **giới hạn số message xử lý đồng thời** và phản ứng khi sink chậm.

### 16.1. Tại sao event đến nhanh có thể gây quá tải?

Giả sử producer gửi 500 event/giây, trong khi consumer ghi DB tối đa 300 event/giây. Phần chênh khoảng **200 event/giây** sẽ tích lũy ở broker, executor queue, một hàng đợi trung gian hoặc gây từ chối nhận theo cơ chế transport. Việc “tăng thread” không giải quyết nếu giới hạn cuối cùng là DB connection pool.

### 16.2. Cơ chế điều tiết theo tầng

| Tầng | Tín hiệu tải | Biện pháp |
| --- | --- | --- |
| Broker queue | Queue depth, unacked messages | Prefetch, concurrency, consumer autoscaling có giới hạn |
| Kafka topic | Consumer lag theo partition, processing duration | Consumer group/partition count, batch, giới hạn xử lý |
| DirectChannel | Latency sender/handler, thread bị giữ | Tối ưu handler, cân nhắc durable async handoff |
| ExecutorChannel | Active threads, queue depth, rejected tasks | Bounded queue, rejection policy, backpressure upstream |
| HTTP inbound | Request latency, timeout, 429/503, thread utilization | Rate limit, timeout, 202 + queue bền vững khi phù hợp |
| Database sink | Pool saturation, lock waits, commit latency | Batch, index, transaction ngắn, giảm tải đầu vào |
| External REST sink | Latency, 429, circuit open | Rate limit, bulkhead, retry/backoff, idempotency |

**Không dùng một queue vô hạn trong JVM** làm “giải pháp” cho tốc độ producer lớn hơn consumer. Nó chỉ dời backlog vào heap và có thể khiến tiến trình OOM, mất message đang chờ khi crash.

### 16.3. Chọn subscriber concurrency

Nếu một handler có latency trung bình 100 ms trong điều kiện ổn định, một worker lý thuyết có thể xử lý khoảng 10 tác vụ/giây trước overhead. Nhưng đây không phải hiệu năng bảo đảm: I/O, contention, GC, DB lock, message size và retry đều có thể làm khác biệt lớn.

Hãy đo:

- Throughput thực tế sau **business commit**, không chỉ messages received.
- Độ trễ P50/P95/P99 cho handler và đích.
- Backlog/lag và tuổi message lâu nhất chưa được xử lý.
- Số connection, pool saturation, CPU, heap và rejected task.
- Retry rate, DLT count và duplicate rate.

### 16.4. Chú ý fan-out

Một OrderCreated gửi tới ba subscriber có thể tạo **ba side effect**. Tổng tải không chỉ bằng số event vào, mà còn là fan-out và số outbound call của mỗi nhánh. Nếu một subscriber Analytics chậm, cần quyết định có cách ly backlog của nó khỏi Inventory/Billing hay không; broker topic/nhóm subscription độc lập có thể giúp làm rõ điểm quản lý áp lực.

## 17. Vòng đời kết nối, startup, shutdown và triển khai nhiều instance

### 17.1. Startup

Khi ứng dụng khởi động, listener/adapter thường tham gia lifecycle của Spring ApplicationContext. Từng connector phải có cấu hình xác thực, timeout và recovery riêng.

- [ ] Kiểm tra broker/topic/queue/destination thực sự tồn tại và app có quyền subscribe/consume.
- [ ] Kiểm tra schema/serializer/deserializer, content type và version phù hợp.
- [ ] Đặt cấu hình consumer group, client ID, prefetch, concurrency theo sản phẩm.
- [ ] Không tự động ghi đè offsets hoặc bỏ message tồn đọng ngoài chính sách.
- [ ] Khởi tạo idempotent repository/inbox, DB migrations và dependent services trước khi nhận tải quan trọng.
- [ ] Health endpoint phân biệt **app alive** với **consumer connected, assigned và đang xử lý tiến triển**.

### 17.2. Graceful shutdown

Khi nhận lệnh shutdown hoặc rolling deployment:

1. Ngừng nhận message mới hoặc tạm dừng listener theo lifecycle được hỗ trợ.
2. Cho các handler đang xử lý hoàn tất trong giới hạn shutdown hợp lệ, hoặc rollback/requeue theo transport.
3. Không ack/commit offset cho message mà business commit chưa đạt.
4. Đảm bảo message trong queue memory chưa xử lý không bị xem là đã bảo đảm giao nhận bền vững.
5. Theo dõi offset/queue depth và trạng thái transaction trước khi hạ instance.

Nếu shutdown timeout khiến process bị kill, **redelivery** có thể xảy ra; đó là lý do idempotency phải tồn tại trước khi bật rolling deployment.

### 17.3. Connection recovery

| Công nghệ | Rủi ro thường gặp | Cần kiểm tra |
| --- | --- | --- |
| JMS | Broker restart, session/consumer bị ngắt | Listener container reconnect, ack/transaction, redelivery |
| RabbitMQ | Connection/channel close, network partition | Reconnect, queue topology, prefetch, ack trạng thái |
| Kafka | Rebalance, broker leader change, max poll interval | Partition assignment, offset, retry và heartbeat |
| HTTP | TLS, request timeout, client retry | Idempotency key, status response, connection pool |
| Database | Pool exhaustion, deadlock, transaction timeout | Retry đúng loại lỗi, commit và inbox trạng thái |
| SFTP/File bridge | File chưa hoàn tất, session stale, rename | Polling/ready marker, metadata, reconnect |

Không phải mọi connector đều cần auto-reconnect vô hạn. Với lỗi credentials/permission, retry nhanh liên tục chỉ tạo tải và che dấu vấn đề cấu hình. Tách lỗi tạm thời khỏi lỗi cần người vận hành can thiệp.

### 17.4. Multi-instance và scaling

- **JMS Queue/RabbitMQ queue:** nhiều competing consumers có thể phân chia message; điều kiện ordering và redelivery cần đo.
- **JMS Topic/RabbitMQ fan-out:** muốn nhiều nghiệp vụ cùng nhận event, dùng subscription/queue phù hợp; không chỉ mở thêm consumer trong cùng nhóm cạnh tranh.
- **Kafka:** số consumer thực sự có partition được gán bị ràng buộc bởi số partition và group assignment; bật số replica lớn hơn partition không tự tăng throughput tuyến tính.
- **HTTP:** nhiều inbound gateway instance đằng sau load balancer nhận các request khác nhau; client retry có thể đến instance khác, nên state idempotency cần chia sẻ.
- **ExecutorChannel:** nhiều thread chỉ bảo vệ concurrency trong một JVM, không tự cung cấp distributed deduplication.

### 17.5. Event-driven không loại bỏ nhu cầu reconciliation

Nếu một producer phát event lỗi, broker quá hạn lưu giữ, consumer không được subscribe đúng hoặc schema thay đổi không tương thích, event có thể bị bỏ sót trong phạm vi tích hợp. Với nghiệp vụ quan trọng, nên có **đối soát trạng thái nguồn–đích** định kỳ, phát hiện drift và tái đồng bộ có kiểm soát.

## 18. Observability, kiểm toán và runbook

**Consumer sống** và **consumer xử lý đúng** là hai điều khác nhau. Một listener có thể vẫn kết nối broker nhưng luôn retry cùng poison message, không tiến bộ trong dữ liệu nghiệp vụ.

### 18.1. Chỉ số nên theo dõi

| Chỉ số | Mục đích | Dấu hiệu cảnh báo |
| --- | --- | --- |
| **messages received** | Tốc độ nhận từ adapter | Giảm đột ngột trong lúc nguồn vẫn phát |
| **processed/committed** | Tốc độ nghiệp vụ hoàn tất | Không tăng dù lượng message nhận lớn |
| **processing duration** | Độ trễ handler và downstream | P95/P99 tăng kéo dài |
| **queue depth / Kafka lag** | Backlog và độ trễ tiêu thụ | Tăng liên tục hoặc tuổi message quá hạn |
| **ack/offset commit lag** | Message đã xử lý nhưng tiến độ chưa được ghi | Độ trễ dài, rủi ro redelivery |
| **redelivery/retry** | Tải lặp và lỗi tạm thời | Cùng eventId retry quá ngưỡng |
| **DLT/quarantine count** | Lỗi không tự xử lý được | Tăng nhanh, không có owner xử lý |
| **duplicate suppressed** | Mức độ nhận lại cùng business event | Tăng sau restart/rebalance |
| **consumer connected/assigned** | Kết nối broker, Kafka partition assignment | Không có consumer active dù app alive |
| **executor queue/rejections** | Bất đồng bộ quá tải | Queue đầy, task bị từ chối |
| **last successful commit** | Tiến độ nghiệp vụ thực | Quá lâu khi nguồn đang có event |

Chỉ số cần định nghĩa **mẫu số, loại message, nguồn, consumer group và phạm vi môi trường**. Đừng gắn từng eventId hoặc payload làm nhãn metric vì cardinality rất cao và có thể làm rò dữ liệu.

### 18.2. Logging minh họa

~~~json
{
  "flow": "order-created-consumer",
  "eventId": "EVT-LAB-1042",
  "schemaVersion": 1,
  "consumer": "inventory-projection",
  "source": "orders.events",
  "stage": "BUSINESS_COMMIT",
  "attempt": 2,
  "result": "RETRYABLE_ERROR",
  "traceId": "TRACE-LAB-081",
  "durationMs": 145
}
~~~

Log này là ví dụ giả lập, không phải format mặc định của Spring Integration. Không log nguyên token, password, session cookie, private key hoặc dữ liệu cá nhân không cần thiết. Truy cập log và retention phải theo chính sách.

### 18.3. Ba runbook cần có

**Runbook A — Consumer lag tăng:** kiểm tra có message mới không, số partition/queue, listener connected, handler latency, DB pool, retries và concurrency; không tự tăng thread nếu đích đã quá tải.

**Runbook B — Một event gây lỗi lặp:** lấy eventId/schemaVersion, xác định lỗi transient hay permanent, giới hạn retry, chuyển DLT, thông báo owner, sửa nguyên nhân trước replay; không log dữ liệu bí mật.

**Runbook C — Consumer restart gây duplicate:** xem checkpoint/offset/ack, transaction và inbox business key; xác minh tác động nghiệp vụ không bị lặp, sửa redelivery path nếu cần; không tắt idempotency để che hiện tượng.

### 18.4. Checklist bằng chứng

- [ ] Có correlation từ producer eventId tới inbound adapter và handler.
- [ ] Biết event đã được nhận, validate, xử lý, commit và ack ở những thời điểm nào.
- [ ] Khi lỗi, xác định được attempt, nguyên nhân, message source và owner.
- [ ] DLT/quarantine có thể liệt kê, rà soát và replay trong phạm vi được phép.
- [ ] Có test xác minh process restart/redelivery không gây side effect trùng.
- [ ] Log và metrics không làm rò dữ liệu nhạy cảm.
- [ ] Có thể phân biệt một consumer backlog với một consumer đã mất subscription hoặc partition assignment.

## 19. Bài lab: xử lý OrderCreated theo event-driven flow

Lab được thiết kế để thực hành bằng **Java 17 và Spring Integration trong môi trường được phép**. Có thể bắt đầu chỉ bằng DirectChannel và một repository in-memory, rồi thay bằng JMS/AMQP/Kafka test broker và DB thử nghiệm để quan sát delivery thực tế.

### 19.1. Bối cảnh

**Order Service** phát OrderCreated. **Inventory Consumer** cập nhật projection tồn kho hoặc đơn chờ xử lý; **Analytics Consumer** cập nhật số liệu. Mỗi consumer cần tự ngăn event trùng và bảo toàn trạng thái đúng khi event đến muộn.

Dữ liệu giả:

~~~json
{
  "eventId": "EVT-LAB-2001",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "ORDER-LAB-1001",
  "aggregateVersion": 1,
  "tenantId": "TENANT-LAB-01",
  "data": {
    "sku": "SKU-LAB-A",
    "quantity": 2
  }
}
~~~

### 19.2. Thiết kế tối thiểu

~~~mermaid
flowchart TD
    P["Producer: OrderCreated"] --> B["Broker test hoặc DirectChannel"]
    B --> IA["Inbound Adapter / Channel"]
    IA --> V["Validate schema và tenant"]
    V --> IDEMP["Inbox: check business eventId"]
    IDEMP --> H["Business handler"]
    H --> DB["Persist/commit"]
    DB --> ACK["Ack/offset theo contract"]
    V -->|Invalid| Q["Quarantine/DLT"]
    H -->|Transient failure| RET["Retry + backoff"]
    RET --> H
~~~

Đối với **DirectChannel chỉ trong memory**, không có ack từ broker. Vì vậy phần ACK ở sơ đồ chỉ áp dụng khi bạn chuyển sang broker; lab nội bộ dùng **ghi nhận xử lý hoàn tất** để minh họa kết quả tương đương ở cấp nghiệp vụ.

### 19.3. Các bước thực hiện

**Bước 1 — Xây channel và service activator.** Sử dụng luồng DirectChannel ở phần 7; tạo handler parse `OrderCreated`, validate `eventId`, `aggregateId`, tenant và version. Từ chối field thiếu hoặc dữ liệu sai.

**Bước 2 — Lưu business idempotency key.** Tạo bảng inbox hoặc mock repository có ràng buộc unique theo `consumerName + eventId`. Không chỉ dùng một HashSet nếu muốn kiểm thử restart bền vững.

**Bước 3 — Xử lý business state.** Cập nhật trạng thái đơn hoặc tồn kho có `aggregateVersion`. Không cho event version cũ ghi đè version mới.

**Bước 4 — Gửi cùng event hai lần.** Kết quả nghiệp vụ chỉ có một tác động hợp lệ theo thiết kế; log được ghi nhận duplicate thay vì lặp side effect.

**Bước 5 — Gây lỗi sau commit trước ack.** Với broker test, giả lập crash/reset offset hoặc mất ack sau khi DB commit; khởi chạy lại và xác minh redelivery không làm lặp side effect. Với mock, gọi handler lần thứ hai sau khi ghi trạng thái thành công.

**Bước 6 — Tạo lỗi schema.** Gửi JSON thiếu eventId hoặc version không hỗ trợ; message được từ chối/quarantine theo policy, không retry vô hạn.

**Bước 7 — Tạo lỗi hạ tầng tạm thời.** Cho DB test lỗi một lần; consumer retry với backoff, không ghi inbox “xong” khi nghiệp vụ chưa commit.

**Bước 8 — Bật fan-out.** Cho Inventory và Analytics đăng ký độc lập. Cả hai xử lý cùng event theo **consumer-specific idempotency**, không dùng một hàng inbox chung khiến subscriber thứ hai bị bỏ qua.

**Bước 9 — Thử concurrency.** Phát hai event cùng aggregate với version 2 rồi version 1; phải ngăn trạng thái cũ ghi đè bằng kiểm tra version hoặc xử lý tuần tự theo key.

**Bước 10 — Ghi báo cáo.** Lưu Expected/Actual, eventId, attempt, commit status, retry/DLT và điểm đã kiểm chứng. Nêu rõ khác biệt giữa test DirectChannel và test broker.

### 19.4. Ma trận kiểm thử

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **ED-01** | Producer gửi event vào DirectChannel có một handler | Handler được kích hoạt khi gửi, không cần poller |
| **ED-02** | Không có message mới | Không có handler invocation do lịch polling |
| **ED-03** | Event thiếu trường bắt buộc | Không ghi nghiệp vụ; lỗi được ghi nhận |
| **ED-04** | Nhận schemaVersion chưa hỗ trợ | Quarantine/DLT hoặc reject có owner |
| **ED-05** | Nhận cùng eventId hai lần | Không lặp side effect nghiệp vụ |
| **ED-06** | Retry với technical message ID mới nhưng eventId giữ nguyên | Inbox vẫn phát hiện duplicate |
| **ED-07** | Event version 2 tới trước version 1 | Không ghi đè state mới bằng event cũ |
| **ED-08** | Handler DB lỗi trước commit | Có retry/redelivery theo hợp đồng; không ack thành công giả |
| **ED-09** | Commit thành công rồi broker ack mất | Redelivery an toàn nhờ idempotency |
| **ED-10** | Consumer dừng ngay khi xử lý | Sau restart không mất hoặc nhân đôi side effect ngoài thiết kế |
| **ED-11** | Một poison event lỗi nhiều lần | DLT/quarantine sau số retry có giới hạn |
| **ED-12** | Lỗi transient 503/timeout từ HTTP outbound gateway | Retry có backoff, không busy loop |
| **ED-13** | Một event hợp lệ được fan-out | Mỗi subscriber hợp lệ đều có cơ hội xử lý đúng contract |
| **ED-14** | Inventory thành công, Invoice thất bại | Retry Invoice không bắt Inventory làm lại nếu subscriptions độc lập |
| **ED-15** | Hai handler gắn cùng DirectChannel | Không giả định cả hai được broadcast mỗi message |
| **ED-16** | Đổi qua ExecutorChannel | Lỗi async không tự truyền đồng bộ về producer |
| **ED-17** | Executor queue đầy | Có rejection/backpressure được ghi nhận, không drop vô hình |
| **ED-18** | Kafka consumer group nhiều instance | Partition được phân phối theo group, lag được đo |
| **ED-19** | Kafka rebalance khi một record chưa commit | Record có thể được đọc lại; không mất state đúng |
| **ED-20** | RabbitMQ redelivery/requeue | Idempotency ngăn lặp, DLQ hoạt động theo policy |
| **ED-21** | JMS listener rollback do lỗi handler | Kiểm chứng redelivery/ack theo container setup |
| **ED-22** | HTTP client retry cùng idempotency key | Không tạo hai đơn hàng nếu contract yêu cầu một |
| **ED-23** | SFTP bridge poll file rồi gửi event broker | Phân biệt source polling và downstream event-driven |
| **ED-24** | Outbox relay phát lại sau restart | Consumer chịu được event gửi lặp |
| **ED-25** | Backlog tăng do DB nghẽn | Metrics/alert chỉ ra bottleneck, không tăng thread mù quáng |
| **ED-26** | Audit log có thông tin nhạy cảm | Redact credentials, giới hạn dữ liệu/nhãn |

### 19.5. Mẫu báo cáo kết quả lab

~~~yaml
testCase: ED-09
eventId: EVT-LAB-2001
consumer: inventory-projection
input: "Broker redelivers after business commit but before ack"
expected: "One business effect; duplicate detected"
actual: "Expected value from the experiment"
result: PENDING
evidenceRef: "lab://tests/ED-09"
verifiedAt: null
~~~

Đây là **mẫu báo cáo chưa chạy test**, không được coi `result: PENDING` là PASS. Khi chạy thật, điền actual, output của adapter, ảnh/log cần thiết đã ẩn dữ liệu nhạy cảm và kết quả readback.

### 19.6. Tăng độ khó

1. Thay DirectChannel producer bằng **JMS listener adapter** và cấu hình transaction/ack thật trong môi trường test.
2. Dùng **RabbitMQ fan-out exchange** với hai queue để mỗi nghiệp vụ quản lý retry/DLQ riêng.
3. Dùng **Kafka topic** có partition key là aggregateId để học ordering, offset và rebalance.
4. Đưa xử lý nặng qua ExecutorChannel, xác định cách tránh ack broker quá sớm.
5. Thêm **HTTP inbound gateway** nhận command, lưu order + outbox cùng DB transaction, relay phát event.
6. Thêm dashboard processed/received/lag/DLT và thực hiện drill khôi phục sau crash.

## 20. Anti-patterns và checklist áp dụng

### 20.1. Các anti-pattern phổ biến

| Sai lầm | Rủi ro | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| **“Kafka poll nên là PollingConsumer”** | Nhầm lẫn abstraction Spring Integration | Phân biệt client poll bên trong listener với SI PollingConsumer endpoint |
| **Đặt hai subscriber DirectChannel để broadcast** | Chỉ một handler có thể được chọn cho mỗi message | Dùng PublishSubscribeChannel hoặc broker fan-out |
| **Ack ngay sau khi enqueue vào ExecutorChannel** | Crash trước business commit làm mất message | Xử lý đồng bộ hoặc durable handoff/ack phối hợp |
| **Coi send thành công là nghiệp vụ thành công** | Che lỗi handler downstream/transaction | Theo dõi điểm commit và readback |
| **Không có business eventId** | Retry/redelivery tạo tác động trùng | Khóa idempotency ổn định |
| **Ghi inbox trước khi business commit** | Có thể bỏ sót event khi crash | Cùng transaction với thay đổi nghiệp vụ |
| **Retry vô hạn event sai schema** | Poison event chặn consumer và ngập log | DLT/quarantine có owner |
| **Nuốt mọi exception trong handler** | Broker có thể ack dù chưa xử lý đúng | Phân loại lỗi và để failure path theo contract hoạt động |
| **Bật executor queue không giới hạn** | OOM, thiếu backpressure, crash mất work | Bounded executor và durable broker khi phù hợp |
| **Tăng concurrency dù DB quá tải** | Tăng lock, retry, độ trễ | Đo bottleneck và giới hạn tải |
| **Tin message order là commit order** | State version cũ ghi đè mới | Version check hoặc serialize theo aggregate |
| **Dùng một inbox chung cho mọi subscriber** | Subscriber khác bỏ qua event hợp lệ | Idempotency scope theo consumer |
| **Quên stop/rebalance khi deploy** | Duplicate, lag, timeout | Graceful lifecycle và test restart |
| **Không đối soát trạng thái nguồn–đích** | Lỗi bị che sau mất event hoặc schema đổi | Reconciliation/repair theo nghiệp vụ |
| **Log toàn bộ payload/token** | Rò rỉ credential và dữ liệu khách hàng | Redaction, data minimization, retention |

### 20.2. Checklist thiết kế trước production

- [ ] Nguồn sự kiện, transport và loại inbound adapter/gateway được xác định đúng.
- [ ] Có lý do chọn event-driven thay cho polling, hoặc mô tả rõ flow kết hợp.
- [ ] Message contract có eventId, schemaVersion, aggregateId, tenant và policy validate.
- [ ] Hiểu threading của DirectChannel/ExecutorChannel/PublishSubscribeChannel.
- [ ] Không coi channel in-memory là durable broker nếu chưa có cơ chế lưu bền vững.
- [ ] Có điểm commit nghiệp vụ cụ thể trước acknowledgement/offset theo contract.
- [ ] Có phương án idempotency qua retry và restart.
- [ ] Ordering và concurrency được giới hạn theo key/partition hoặc version.
- [ ] Có đường DLT/quarantine, chính sách retry/backoff, owner và replay.
- [ ] Fan-out xác định subscriber nào được nhận event và ai chịu trách nhiệm khi nhánh lỗi.
- [ ] Có backpressure, giới hạn concurrency và capacity phù hợp với hệ đích.
- [ ] Startup/shutdown, reconnect và rolling deploy đã được kiểm thử.
- [ ] Theo dõi consumer lag/queue depth, processed commit, errors, duplicate và DLT.
- [ ] Event không được dùng làm nguồn quyền đáng tin nếu chưa xác thực và ủy quyền phù hợp.
- [ ] Có test redelivery sau commit, schema mismatch, poison message và stale event.
- [ ] Có runbook, audit trail và đối soát trạng thái nếu nghiệp vụ đòi hỏi.

## 21. Tổng kết và câu hỏi tự kiểm tra

### 21.1. Kiến thức cần nhớ

**Event-driven Consumer Pattern** cho phép một handler phản ứng khi message được dispatch tới consumer thay vì phải lên lịch hỏi dữ liệu nghiệp vụ. Trong **Spring Integration**, bạn thường nhìn thấy mẫu này ở:

- **Message-driven inbound adapter** từ JMS, AMQP hoặc Kafka listener container.
- **Inbound gateway** khi HTTP/JMS/AMQP request đến và cần phản hồi.
- **Service activator** đang subscribe một **SubscribableChannel** như DirectChannel hoặc ExecutorChannel.
- **PublishSubscribeChannel** khi một message cần đến nhiều subscriber trong ứng dụng.

Trong khi đó, **PollingConsumer** nhận từ **PollableChannel** như QueueChannel, và **SourcePollingChannelAdapter** nhận từ **MessageSource** như File/SFTP/JDBC. Các cơ chế này có thể nằm trong cùng hệ thống; chọn theo nguồn dữ liệu và delivery contract.

### 21.2. Tự trả lời

1. Khác biệt lớn nhất giữa event-driven consumer và polling consumer ở **điểm kích hoạt** là gì?
2. Vì sao Kafka client có poll nhưng Spring Integration Kafka inbound adapter vẫn được gọi là message-driven?
3. Khi có hai service activator trên cùng DirectChannel, cả hai có nhận cùng message không?
4. ExecutorChannel có giữ transaction context từ thread sender và bảo đảm handler đã commit khi send trả về không?
5. HTTP inbound gateway khác HTTP outbound gateway và message-driven inbound adapter ở vai trò nào?
6. Vì sao một JMS/AMQP/Kafka message có thể được nhận lại sau khi DB commit thành công?
7. Khi fan-out tới Inventory và Analytics, vì sao inbox idempotency nên có consumer identity?
8. Nếu OrderUpdated v8 commit trước v7, consumer ngăn stale update bằng cách nào?
9. Một poison event lỗi parse liên tục nên được xử lý ra sao sau giới hạn retry?
10. Consumer vẫn connected nhưng lag không giảm: bạn sẽ kiểm tra chỉ số/đường lỗi nào trước?

**Gợi ý ngắn:** (1) message dispatch vs scheduled receive; (2) transport client poll do container quản lý, abstraction SI là listener; (3) không mặc định broadcast; (4) không; (5) request-reply inbound, request-reply outbound và one-way listener; (6) ack/offset chưa ghi; (7) mỗi subscriber có tác động riêng; (8) kiểm tra version/partitioning; (9) quarantine/DLT có owner; (10) business commit, handler latency, retries, DB và backlog.

### 21.3. Nguyên tắc chốt

Một event-driven flow đáng tin không dừng ở việc **“handler đã được gọi”**. Cần chứng minh **message hợp lệ, đúng nguồn, được xử lý với idempotency, tuân thủ thứ tự nghiệp vụ và được ghi nhận thành công ở hệ đích**, cùng cơ chế retry, redelivery và phục hồi khi bất kỳ bước nào thất bại.

**Ghi nhớ:** *Event-driven giúp chọn lúc phản ứng; message contract, transaction, acknowledgment, idempotency, backpressure và observability quyết định phản ứng đó có thực sự đúng và bền vững hay không.*
