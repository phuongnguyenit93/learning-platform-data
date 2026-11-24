# Competing Consumers Pattern trong Spring Integration Adapters

> **Chương:** Design patterns  
> **Chủ đề:** Competing consumers pattern  
> **Phạm vi:** Module SPRING_INTEGRATION_ADAPTERS — kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và MessageChannel. Bài học đặt mô hình nhiều consumer cùng chia sẻ work vào luồng File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; đặc biệt nhấn mạnh hợp đồng message, giao nhận lại, lỗi, thứ tự, mở rộng tải và vòng đời kết nối.

## 1. Mục tiêu và câu hỏi mở đầu

Giả sử một ứng dụng nhận 50.000 thông điệp đơn hàng mỗi giờ. Một consumer đơn lẻ chỉ hoàn tất 5.000 thông điệp mỗi giờ. Hàng chờ ngày càng dài, mặc dù producer hoạt động bình thường. Ta muốn tăng số worker xử lý mà **không biến một công việc thành ba lần xử lý nghiệp vụ**.

**Competing Consumers** là mẫu nhiều consumer **cạnh tranh nhận những thông điệp công việc từ cùng một nguồn phân phối**. Thông thường một message được giao cho **một consumer tại một thời điểm**, còn các message khác được phân bổ cho worker khác. Mục tiêu là tăng năng lực xử lý, khả năng sẵn sàng và điều tiết tải, không phải phát bản sao mỗi message cho tất cả.

Sau bài này, người học có thể:

1. Diễn giải Competing Consumers trong Enterprise Integration Patterns (EIP) và phân biệt với Publish–Subscribe, Event-driven Consumer và Polling Consumer.
2. Xác định **đơn vị work**, **ranh giới của hàng đợi**, **consumer group/partition** và **điểm công nhận xử lý thành công**.
3. Thiết kế queue có nhiều worker trong Spring Integration qua **PollableChannel** hoặc message-driven inbound adapter của JMS/AMQP/Kafka.
4. Giải thích vì sao **DirectChannel có nhiều subscriber**, **QueueChannel có nhiều polling consumers** và **broker có competing consumers** không có tính bền vững và ack giống nhau.
5. Đánh giá **ack, retry, redelivery, idempotency, dead-letter, ordering, concurrency, prefetch và backpressure**.
6. Tính và đo throughput, backlog, thời gian chờ, nhu cầu autoscaling và giới hạn của sink.
7. Xử lý lỗi một worker, deploy rolling, broker mất kết nối, partition rebalance và message độc gây lỗi lặp.
8. Viết flow Java, mô phỏng work distribution, kiểm thử trùng lặp/lỗi và bàn giao runbook.

**Câu hỏi xuyên suốt:** *Làm sao chia công việc giữa nhiều consumer, mỗi worker có thể gặp lỗi hoặc bị tắt đột ngột, mà hệ thống vẫn duy trì kết quả nghiệp vụ đúng và khôi phục được?*

## 2. Khái niệm cốt lõi: cạnh tranh để nhận work

Một **work queue** tiếp nhận công việc từ một hoặc nhiều producer. Nhiều consumer đăng ký nhận từ cùng queue/destination hoặc cùng consumer group tương ứng. Khi có một message, cơ chế phân phối chọn một consumer có thể xử lý; consumer đó thực hiện nghiệp vụ và xác nhận theo hợp đồng của transport.

~~~mermaid
flowchart LR
    P1["Producer A"] --> Q["Work Queue / Shared Subscription"]
    P2["Producer B"] --> Q
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
    C1 --> DB["Business Store"]
    C2 --> DB
    C3 --> DB
~~~

Sơ đồ mô tả **phân phối work**, không có nghĩa mọi message trong queue đều được gửi đồng thời tới cả ba consumer. Ví dụ queue có W1, W2, W3, W4; một cách phân bổ hợp lệ là:

~~~text
W1 → consumer-1
W2 → consumer-2
W3 → consumer-3
W4 → consumer-2
~~~

**Không bảo đảm phân phối đều 1:1:1.** Một worker nhanh hơn, có prefetch cao hơn hoặc vừa reconnect có thể nhận nhiều message hơn. Thuật toán dispatch tùy broker, channel, listener container và tải thực tế.

### 2.1. Một message có thể được giao lại

Câu “mỗi message cho một consumer” nên hiểu theo **lần giao đang hoạt động**, không phải “một lần mãi mãi”. Nếu consumer-1 nhận W1 nhưng chết trước khi broker ghi nhận hoàn tất, W1 có thể được giao lại consumer-2. Do đó:

- Không dựa vào *consumerId* để suy ra work chỉ chạy một lần.
- Consumer phải xử lý được **duplicate** và trạng thái đã commit nhưng chưa ack.
- Thứ tự bắt đầu, thứ tự hoàn tất và thứ tự nhận lại có thể khác nhau.
- **Thành công của API nhận message** không tự chứng minh business transaction đã thành công.

### 2.2. Ba lợi ích chính

| Lợi ích | Cơ chế | Điểm cần kiểm chứng |
| --- | --- | --- |
| **Scale-out** | Nhiều worker xử lý các work item khác nhau | Throughput tăng tới khi chạm giới hạn broker/DB/API |
| **Availability** | Một worker chết, worker khác còn có thể nhận work | Redelivery/failover thực sự xảy ra theo transport |
| **Load leveling** | Queue hấp thụ đợt tăng tải ngắn | Queue capacity, tuổi backlog và giới hạn lưu giữ |

**Không phải lời hứa:** nhiều consumer không tự tạo exactly-once, không tự giữ thứ tự tổng thể, không tự chia đều CPU và cũng không làm downstream vô hạn dung lượng.

## 3. Phân biệt với các pattern gần nhau

| Pattern | Một message đến với ai? | Mục đích | Ví dụ |
| --- | --- | --- | --- |
| **Competing Consumers** | Một consumer trong nhóm cạnh tranh cho mỗi lần giao | Chia work và tăng throughput | Nhiều worker cùng nhận từ RabbitMQ queue |
| **Publish–Subscribe** | Mỗi subscriber/subscription có thể nhận một bản sao | Nhiều nghiệp vụ cùng quan tâm event | Billing và Analytics cùng nhận OrderCreated |
| **Event-driven Consumer** | Handler được kích hoạt khi message được dispatch | Cách nhận theo sự kiện | JMS/Kafka listener gọi handler |
| **Polling Consumer** | Consumer chủ động gọi receive theo lịch | Cách nhận từ source/channel | PollingConsumer đọc QueueChannel |
| **Message Router** | Chọn kênh/đích theo nội dung hoặc chính sách | Phân nhánh message | Route theo loại order |
| **Aggregator** | Gom nhiều message liên quan thành một kết quả | Tổng hợp | Ghép kết quả từ ba API |
| **Request–Reply Gateway** | Gửi request, chờ kết quả đúng correlation | Tương tác có phản hồi | HTTP/JMS gateway |

Competing Consumers mô tả **phân phối công việc**, trong khi Event-driven/Polling mô tả **cách được kích hoạt để nhận**. Vì thế một RabbitMQ listener có thể đồng thời là **event-driven consumer** và một thành viên **competing consumers**; một Spring **PollingConsumer** rút work từ **QueueChannel** cũng có thể cạnh tranh với một PollingConsumer khác.

### 3.1. Phân biệt fan-out và competing group

~~~mermaid
flowchart TB
    EVENT["OrderCreated"] --> BROKER["Broker Topic / Exchange"]
    BROKER --> QUEUE_A["Billing Queue"]
    BROKER --> QUEUE_B["Analytics Queue"]
    QUEUE_A --> BA1["Billing worker 1"]
    QUEUE_A --> BA2["Billing worker 2"]
    QUEUE_B --> AN1["Analytics worker 1"]
    QUEUE_B --> AN2["Analytics worker 2"]
~~~

Billing và Analytics nhận **bản sao logic của cùng event** qua hai subscription/queue khác nhau. Trong Billing, hai worker **cạnh tranh với nhau**; trong Analytics, hai worker cũng cạnh tranh. Nếu dùng một queue chung cho cả Billing và Analytics, có thể chỉ một bên nhận mỗi message, làm mất yêu cầu nghiệp vụ của bên kia.

### 3.2. Kafka consumer group không phải mỗi worker nhận cả topic

Trong Kafka, record được lưu trong **partition**. Các consumer cùng **group.id** phân chia partition; trong điều kiện assignment bình thường, một partition được giao cho một consumer member trong cùng group ở một thời điểm. Nếu muốn hai nghiệp vụ độc lập đều thấy event, chúng dùng **hai consumer group khác nhau** hoặc cơ chế tương đương, không đơn thuần tạo hai instance cùng group.

### 3.3. Điều kiện phù hợp

Nên cân nhắc competing consumers khi:

- Công việc có thể chia thành **nhiều đơn vị độc lập** hoặc được partition theo key.
- Có queue/broker/claim mechanism làm trung gian cho worker.
- Downstream chịu được mức concurrency mong muốn.
- Người học hoặc đội vận hành đã định nghĩa được ack, retry, idempotency và error policy.
- Năng lực xử lý một worker không theo kịp tốc độ work đến, hoặc cần dự phòng worker.

Không nên tăng worker mù quáng khi các message phải xử lý **tuần tự toàn cục**, chỉ có một lock độc quyền, API downstream bị rate limit rất thấp hoặc business side effect không có cách chống duplicate.

## 4. Kiến trúc Spring Integration cho Competing Consumers

Spring Integration cung cấp **MessageChannel**, **MessageHandler**, **service activator**, **inbound/outbound adapter**, **gateway**, **poller** và nhiều adapter cho hệ ngoài. Competing consumers có thể được tổ chức ở **hai cấp** cần phân biệt:

1. **Trong cùng JVM:** nhiều consumer lấy từ một **PollableChannel**, hoặc dispatch đến các subscribers của một DirectChannel.
2. **Tại hạ tầng ngoài JVM:** nhiều listener container/instance cùng nhận từ một **JMS/AMQP queue** hoặc một **Kafka consumer group**.

~~~mermaid
flowchart LR
    P["Application Producer"] --> Q["QueueChannel in JVM"]
    Q --> PC1["PollingConsumer A"]
    Q --> PC2["PollingConsumer B"]
    PC1 --> BIZ["Business Service"]
    PC2 --> BIZ
    EXT["Broker work queue / topic partitions"] --> IA1["Adapter instance A"]
    EXT --> IA2["Adapter instance B"]
    IA1 --> CH1["Local MessageChannel"]
    IA2 --> CH2["Local MessageChannel"]
    CH1 --> BIZ
    CH2 --> BIZ
~~~

### 4.1. Hệ quả của từng channel

| Channel | Phân phối message | Độ bền/ack cần hiểu |
| --- | --- | --- |
| **QueueChannel** | Nhiều polling consumers có thể nhận các message khác nhau | Thường trong memory; receive loại message khỏi queue, không phải ack broker bền vững |
| **DirectChannel** | Chọn một trong các handler subscriber cho mỗi message | Gọi handler đồng bộ; không phải durable work queue |
| **ExecutorChannel** | Dispatch message sang executor và handler | Queue của executor không mặc định bền vững; cần giới hạn capacity |
| **PublishSubscribeChannel** | Phát một message tới nhiều subscriber | **Không phải competing consumers** nếu mọi subscriber phải xử lý |
| **Broker adapter → DirectChannel** | Broker phân phối ở cấp listener; channel dispatch ở JVM | Broker ack và nghiệp vụ phải phối hợp, không suy từ send() |

**Đừng nhầm:** nếu ứng dụng có ba handler cùng subscribe **DirectChannel**, chỉ một handler được chọn cho mỗi message theo dispatcher. Nhưng đó **không thay thế broker queue** khi cần persist, redelivery sau crash và chia tải giữa nhiều server.

### 4.2. Message-driven khác polling

- Với **JMS/AMQP inbound adapter**, listener container nhận message từ broker theo cơ chế container rồi chuyển vào channel, thường là event-driven ở tầng Spring Integration.
- Với **QueueChannel**, một **PollingConsumer** gọi receive() theo poller để lấy message.
- Với **File/SFTP/JDBC inbound source**, một **SourcePollingChannelAdapter** lấy dữ liệu từ nguồn theo lịch rồi tạo message. Nếu nhiều instance cùng lấy một nguồn, cần lock/claim/metadata dùng chung; chỉ thêm replicas không tự tạo competing queue an toàn.
- Với **Kafka**, client bên dưới có poll loop, nhưng ở tầng Spring Integration message-driven inbound adapter thường dùng listener container; chia work dựa trên **consumer group và partition assignment**, không phải một QueueChannel duy nhất.

## 5. Định nghĩa work item và message contract

Trước khi cấu hình concurrency, cần xác định **một đơn vị công việc hoàn thành được là gì**: một order, một file, một hàng DB, một command, hay một batch? Nếu không, metrics và redelivery sẽ mơ hồ.

### 5.1. Envelope minh họa

~~~json
{
  "eventId": "WORK-LAB-0041",
  "eventType": "GenerateInvoice",
  "schemaVersion": 1,
  "tenantId": "TENANT-LAB-01",
  "businessKey": "ORDER-LAB-0088",
  "businessVersion": 2,
  "requestedAt": "2026-11-23T14:00:00+07:00",
  "data": {
    "orderId": "ORDER-LAB-0088",
    "invoiceType": "STANDARD"
  }
}
~~~

Đây là schema nghiệp vụ **giả lập**, không phải payload mặc định của JMS, AMQP hay Kafka. Spring **Message<T>** còn có headers phục vụ định tuyến và tracing; không được giả định mọi header từ nguồn ngoài đáng tin.

### 5.2. Checklist hợp đồng message

- [ ] **eventId hoặc workId** ổn định qua retry/redelivery, không chỉ message ID kỹ thuật mới.
- [ ] Có **businessKey** phù hợp cho idempotency và partition/ordering.
- [ ] Xác định một message là một work item hay một batch nhiều work item.
- [ ] Có schema/version, định dạng, encoding, giới hạn kích thước, trường bắt buộc.
- [ ] Kiểm tra tenant, nguồn phát và quyền gửi command trước side effect.
- [ ] Phân biệt trạng thái **RECEIVED, CLAIMED, PROCESSING, COMMITTED, ACKNOWLEDGED**.
- [ ] Có thời gian hiệu lực/deadline nghiệp vụ nếu work có thể đến muộn.
- [ ] Không lưu password, raw token, private key hoặc PII không cần thiết trong payload/headers/log.
- [ ] Có chính sách khi event đến trùng hoặc version cũ đến sau version mới.
- [ ] Có đường quarantine/DLQ và khả năng replay an toàn cho message không xử lý được.

### 5.3. Correlation không thay thế idempotency

**Correlation ID** liên kết các bước của một workflow hoặc request/reply; **business idempotency key** bảo vệ một tác động khỏi bị áp dụng lặp. Hai mục đích có thể chia sẻ giá trị theo thiết kế nhưng không mặc nhiên tương đương. Một message được broker redeliver có thể có message ID kỹ thuật khác nhưng workId nghiệp vụ vẫn giữ nguyên.

## 6. Java DSL: hai PollingConsumer cạnh tranh trên QueueChannel

Ta bắt đầu bằng **một JVM** để quan sát cơ chế lấy work trước khi thêm broker. Hai integration flows tiêu thụ từ cùng một **QueueChannel** có dung lượng giới hạn. Cả hai polling endpoints sẽ chủ động receive(); mỗi message được một endpoint nhận, không được broadcast.

### 6.1. Ví dụ Java 17 và Spring Integration 6.x

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class LocalCompetingConsumersConfig {

    @Bean
    public QueueChannel invoiceWorkQueue() {
        // Hữu hạn để tránh producer đẩy công việc vô hạn vào heap.
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow invoiceWorkerA(QueueChannel invoiceWorkQueue) {
        return IntegrationFlow
                .from(invoiceWorkQueue, endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(300))
                               .maxMessagesPerPoll(2)
                ))
                .handle((MessageHandler) message -> {
                    String workId = String.valueOf(message.getPayload());
                    System.out.println("worker-A handles " + workId);
                })
                .get();
    }

    @Bean
    public IntegrationFlow invoiceWorkerB(QueueChannel invoiceWorkQueue) {
        return IntegrationFlow
                .from(invoiceWorkQueue, endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(300))
                               .maxMessagesPerPoll(2)
                ))
                .handle((MessageHandler) message -> {
                    String workId = String.valueOf(message.getPayload());
                    System.out.println("worker-B handles " + workId);
                })
                .get();
    }
}
~~~

Đây là **cấu hình lab** minh họa nhiều consuming endpoints, không phải cấu hình production có transaction/retry bền vững. Khi chạy ở Spring Boot, đảm bảo Spring Integration core/DSL và component scan tương thích phiên bản dự án.

### 6.2. Producer gửi các work item

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class InvoiceWorkPublisher {
    private final MessageChannel channel;

    public InvoiceWorkPublisher(
            @Qualifier("invoiceWorkQueue") MessageChannel channel) {
        this.channel = channel;
    }

    public void enqueue(String workId) {
        boolean accepted = channel.send(
                MessageBuilder.withPayload(workId)
                              .setHeader("workId", workId)
                              .build(),
                1000L
        );
        if (!accepted) {
            throw new IllegalStateException("Work queue is full");
        }
    }
}
~~~

Gửi các ID khác nhau, ví dụ **W01–W10**, rồi quan sát đầu ra. **Không kỳ vọng worker A xử lý chính xác 5 message và worker B xử lý 5**: tốc độ, scheduler và tải quyết định phân bổ. Điều cần chứng minh là **không có ý định broadcast** và mỗi lần receive chọn một message khả dụng.

### 6.3. Hạn chế quan trọng của QueueChannel

**QueueChannel in-memory không thay cho durable broker queue.** Khi một polling consumer nhận message, message không còn nằm trong hàng chờ ban đầu theo cách của QueueChannel. Nếu handler đã dequeue rồi ném exception, không được giả định cơ chế **broker redelivery** sẽ tự chạy. Khi JVM chết, các message đang đợi trong memory có thể mất.

Để tiến tới production, chọn một trong các hướng tùy rủi ro:

1. Dùng **JMS/AMQP/Kafka** với cơ chế persistence, ack và recovery đã kiểm chứng.
2. Dùng **persistent message store** hoặc cơ chế giao dịch phù hợp được Spring Integration hỗ trợ; kiểm thử đúng phạm vi.
3. Nếu vẫn dùng queue memory cho công việc có thể tái tạo, lưu nguồn sự thật/work state bền vững và có reconciliation/replay.

### 6.4. maxMessagesPerPoll và số consumer

Hai worker với **maxMessagesPerPoll(2)** nghĩa là mỗi lượt poll của từng endpoint có thể lấy tối đa hai message, **không phải** toàn hệ luôn xử lý đúng bốn message/song song. Threading và concurrency phụ thuộc TaskScheduler/executor, thời gian handler và cấu hình poller. Nếu tất cả handler chậm mà scheduler có rất ít thread, thêm endpoint có thể không tạo tốc độ kỳ vọng.

## 7. Competing Consumers với JMS

Trong JMS, **Queue** thường đại diện point-to-point work distribution. Nhiều **MessageListener** tiêu thụ cùng queue là một cách triển khai competing consumers phổ biến. Broker phân phối message theo semantics JMS và cấu hình provider/container.

~~~mermaid
flowchart LR
    PRODUCER["Order Service"] --> Q["JMS Queue: invoice.jobs"]
    Q --> A["JMS Listener instance A"]
    Q --> B["JMS Listener instance B"]
    Q --> C["JMS Listener instance C"]
    A --> H["Idempotent invoice handler"]
    B --> H
    C --> H
~~~

### 7.1. Spring Integration message-driven inbound adapter

Ví dụ tối thiểu theo Java DSL, với dependency Spring Integration JMS, ConnectionFactory do ứng dụng cung cấp:

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
public class JmsInvoiceConsumerFlow {

    @Bean
    public IntegrationFlow invoiceJobs(ConnectionFactory connectionFactory) {
        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                         .destination("invoice.jobs"))
                .handle((MessageHandler) message -> {
                    String body = String.valueOf(message.getPayload());
                    System.out.println("Received invoice work: " + body);
                })
                .get();
    }
}
~~~

Nếu deploy nhiều instance cùng **queue invoice.jobs**, các listener có thể cạnh tranh nhận work. Cấu hình trên **chưa** xác định durability, transaction manager, delivery mode, redelivery policy hoặc DLQ. Phải kiểm tra và thiết lập chúng riêng theo JMS provider, Spring listener container và yêu cầu nghiệp vụ.

### 7.2. Chọn concurrency và acknowledgment

| Vấn đề | Câu hỏi thực tế |
| --- | --- |
| **Listener concurrency** | Một JVM dùng bao nhiêu consumers, có giới hạn kết nối/session? |
| **Transaction/ack mode** | Message được broker coi xử lý xong ở thời điểm nào? |
| **DB update** | Handler và JMS session có cùng transaction thật không? |
| **Redelivery** | Khi listener lỗi hoặc process chết, message có được giao lại không? |
| **Poison message** | Hết retry sẽ chuyển DLQ hay làm chặn queue? |
| **Ordering** | Khi nhiều consumers, có ràng buộc thứ tự hay message group không? |

**Cảnh báo về async handoff:** nếu JMS listener nhận W1, đẩy W1 sang **ExecutorChannel** rồi kết thúc, broker có thể ghi nhận hoàn tất **trước** khi worker async ghi DB. JVM chết tại khoảng trống đó có thể làm mất work. Phải định nghĩa ack/transaction và durable handoff theo thiết kế cụ thể, không chỉ thấy send() thành công.

### 7.3. JMS Topic khác JMS Queue

Mỗi subscription trên Topic có thể nhận một bản sao theo contract; nhiều consumer cùng chia work hay đều nhận một bản sao phụ thuộc **durable/shared subscription và cấu hình provider**. Vì vậy, đừng chỉ nói “JMS có ba listener thì là competing consumers” khi chưa xác định **destination là Queue hay Topic và cách subscribe**.

## 8. Competing Consumers với AMQP/RabbitMQ

Trong RabbitMQ, các producer thường publish tới **exchange**, message được route vào **queue**; **nhiều consumer của cùng queue** cạnh tranh nhận message. Để hai nghiệp vụ Billing và Analytics cùng nhận mỗi event, cần **hai queue được bind** theo đúng exchange/routing, mỗi queue có thể có tập competing consumers riêng.

~~~mermaid
flowchart TB
    P["Order Service"] --> EX["orders.events exchange"]
    EX --> BQ["billing.queue"]
    EX --> AQ["analytics.queue"]
    BQ --> B1["billing-worker-1"]
    BQ --> B2["billing-worker-2"]
    AQ --> A1["analytics-worker-1"]
    AQ --> A2["analytics-worker-2"]
~~~

### 8.1. Cấu hình listener container: những tham số cần hiểu

| Tham số | Ý nghĩa | Rủi ro khi đặt sai |
| --- | --- | --- |
| **Concurrent consumers** | Số listener xử lý song song | Vượt khả năng DB/HTTP đích |
| **Max concurrent consumers** | Giới hạn co giãn cục bộ nếu container hỗ trợ | Thread/connection tăng bất ngờ |
| **Prefetch** | Số message chưa ack có thể được giao trước | Worker chậm giữ quá nhiều work, phân phối không đều |
| **Ack mode** | Khi nào consumer ack/nack/reject | Ack sớm gây mất; requeue vô hạn gây loop |
| **Requeue policy** | Lỗi được giao lại hay đưa DLQ | Poison message gây nghẽn |
| **Queue durability** | Queue tồn tại qua restart theo cấu hình | Mất topology hoặc message nếu cấu hình không đáp ứng |
| **Publisher confirms** | Xác nhận producer publish tới broker | Không đồng nghĩa consumer đã xử lý business |

### 8.2. Thiết kế flow Spring Integration AMQP

Ở mức cấu trúc:

~~~text
RabbitMQ exchange
  → invoice.jobs.queue (durable theo nhu cầu)
  → Spring AMQP listener container (concurrency có giới hạn)
  → Spring Integration AMQP message-driven inbound adapter
  → DirectChannel
  → Service Activator: validate + idempotent DB transaction
  → Ack theo listener/adapter contract
~~~

Khi tích hợp thực tế, Spring Integration AMQP có cơ chế nối **AMQP message listener container** với **MessageChannel**. Tên factory method/overload có thể khác theo phiên bản Spring Integration/Spring AMQP; chọn từ API tương thích thay vì coi pseudocode trên là lệnh cần copy chạy.

### 8.3. Prefetch không phải số message xử lý xong

Nếu prefetch=50 và một consumer chậm, broker có thể đã giao nhiều message chưa ack cho nó. Worker nhanh khác **không nhất thiết** có thể giành lại message đang unacked từ worker chậm cho tới khi lỗi/disconnect/timeout theo broker. Prefetch quá cao có thể tăng latency đuôi và làm tải lệch; prefetch quá thấp có thể giới hạn throughput khi có round-trip đáng kể.

### 8.4. Redelivery và thứ tự

Consumer A nhận W1 và W2, chỉ commit W2, rồi kết nối đứt. Broker có thể đưa W1 vào đường redelivery; lúc đó W3 có thể đã được consumer B xử lý. **Thứ tự commit nghiệp vụ khác thứ tự publish** là điều cần kiểm thử. Không dùng một queue với nhiều consumer để thực hiện logic phụ thuộc thứ tự toàn cục nếu không có cơ chế ràng buộc bổ sung.

## 9. Competing Consumers trong Kafka consumer group

Kafka không dùng queue theo cùng mô hình RabbitMQ. Kafka lưu record theo **topic partitions**, consumer group thực hiện **partition assignment**, và offset phản ánh tiến độ đọc của nhóm.

### 9.1. Partition là đơn vị chia work

Giả sử topic **invoice.jobs** có ba partition và group **billing-workers** có hai consumer:

~~~mermaid
flowchart LR
    TOPIC["Kafka topic: invoice.jobs"] --> P0["Partition 0"]
    TOPIC --> P1["Partition 1"]
    TOPIC --> P2["Partition 2"]
    P0 --> C1["billing worker A"]
    P1 --> C1
    P2 --> C2["billing worker B"]
~~~

Một phân công khác cũng có thể hợp lệ, tùy assignor và trạng thái group. Nếu tăng lên **bốn consumer nhưng chỉ có ba partitions**, thường chỉ tối đa ba consumer trong group có partition được gán tại một thời điểm; consumer còn lại không tăng throughput bằng cách tự ý lấy cùng partition.

### 9.2. Điều kiện thứ tự

Kafka giữ **thứ tự record trong cùng partition** theo đặc tính producer/broker và cách đọc. Để các thay đổi của cùng một đơn hàng được xử lý theo thứ tự, thường chọn **orderId làm record key** để các event cùng order về cùng partition; nhưng nếu xử lý bất đồng bộ đa thread sau listener, thứ tự **business commit** vẫn có thể bị đảo.

### 9.3. Spring Integration Kafka inbound adapter

Trong Spring Integration, adapter **message-driven** Kafka thường nhận từ **Kafka listener container**, đưa record/batch vào MessageChannel. Client Kafka vẫn chạy poll loop bên dưới, nhưng không nên nhầm đó với **PollingConsumer** endpoint nhận từ QueueChannel.

~~~text
Kafka invoice.jobs topic partitions
  → Kafka listener container (group.id = billing-workers)
  → Spring Integration Kafka message-driven inbound adapter
  → MessageChannel
  → idempotent business handler
  → offset commit / ack theo container policy
~~~

**Chọn config theo phiên bản** Spring Kafka và Spring Integration Kafka: listener container có nhiều chế độ record/batch, ack, error handler và transaction khác nhau. Không tự suy rằng mặc định auto-commit là phù hợp.

### 9.4. Rebalance và consumer failover

Khi consumer A chết hoặc B được thêm vào group, Kafka có thể **rebalance**: partition assignment thay đổi. Nếu A đã ghi DB cho record R nhưng offset chưa commit, B có thể xử lý lại R. Điều này là cơ sở để áp dụng **idempotent consumer** theo business eventId hoặc business version.

### 9.5. Giới hạn scaling

- Số **partition** giới hạn số consumer active có partition trong một group.
- Nâng số partition có thể thay phân bố key và ảnh hưởng yêu cầu ordering; cần kế hoạch.
- Thêm consumer không tăng throughput nếu DB/sink đã bão hòa.
- Một partition nóng (*hot partition*) có thể làm lag cao dù partition khác xử lý nhanh.
- Không dùng cùng group ID cho hai nghiệp vụ đều cần nhận toàn bộ event.

## 10. File, SFTP, HTTP và Database: chưa có broker thì cạnh tranh thế nào?

Không phải nguồn dữ liệu nào cũng có queue broker điều phối delivery. Trong nhiều trường hợp phải **tạo một cơ chế claim work** trước khi cho nhiều instance xử lý.

### 10.1. File/SFTP: đừng để hai poller cùng đọc file

Hai instance Spring Integration cùng quét thư mục SFTP:

~~~text
Replica A: list remote → orders-001.csv
Replica B: list remote → orders-001.csv
A: filter local memory = unseen
B: filter local memory = unseen
A và B: cùng tải và xử lý file
~~~

Đây **không phải** competing consumers an toàn. Cần phương án như:

- Chỉ **một active poller** với leader election/failover.
- **Shared persistent metadata store** cho filter/claim phù hợp adapter.
- Remote rename/claim hoặc lock registry **khi nguồn hỗ trợ an toàn**, có cơ chế phục hồi.
- Chia thư mục/partition theo partner/source để mỗi worker sở hữu phần xác định.
- Đưa mỗi file thành **work message bền vững ở broker** rồi cho nhiều consumer xử lý.

**Không đánh dấu file processed trước khi nghiệp vụ commit** trừ khi đã có cơ chế phục hồi phù hợp. Lưu metadata “đã thấy” chỉ giải quyết duplicate detection ở một bước, không tự tạo exactly-once toàn flow.

### 10.2. Database: claim hàng READY bằng giao dịch

Nếu work được lưu trong bảng task, nên dùng quy trình state và owner:

~~~text
READY
  → CLAIMED(workerId, leaseUntil, attempt)
  → PROCESSING
  → COMPLETED
hoặc
  → RETRYABLE / DEAD_LETTER
~~~

Hai consumer không được thực hiện **SELECT READY** rồi độc lập xử lý mà không khóa/claim có điều kiện. Tùy DB, có thể dùng row locking, update có điều kiện, một transaction claim hoặc cơ chế lease. Cú pháp **FOR UPDATE SKIP LOCKED** chỉ dùng ở DB hỗ trợ và với transaction đúng; bản thân SELECT không đảm bảo chống xử lý trùng.

### 10.3. HTTP: load balancing khác competing queue

Nhiều HTTP server instances đằng sau load balancer có thể **chia các request độc lập**, nhưng HTTP không tự cung cấp **durable work queue, redelivery và per-message ack**. Nếu client retry sau timeout, request có thể đến instance khác; idempotency state phải được chia sẻ nếu có side effect.

Nếu cần nhận HTTP request nhanh rồi xử lý nền:

~~~mermaid
flowchart LR
    CLIENT["HTTP Client"] --> API["HTTP Inbound Gateway"]
    API --> STORE["Validate + persist job/outbox"]
    STORE --> ACCEPT["202 Accepted + jobId"]
    STORE --> BROKER["Durable work queue"]
    BROKER --> W1["Worker A"]
    BROKER --> W2["Worker B"]
    W1 --> DB["Business result"]
    W2 --> DB
~~~

Khi cần gọi API khác trong handler, **HTTP outbound gateway** có request/reply riêng; đừng coi reply timeout là bằng chứng API chưa tạo side effect.

### 10.4. JDBC Outbox: ranh giới giữa DB và broker

Transactional outbox cho phép cùng transaction DB ghi business change và outbox record. Một relay đọc outbox bằng polling/CDC và publish tới broker; ở phía broker, các competing consumers có thể xử lý event. Relay có thể publish lặp khi ACK bị mất, nên downstream vẫn cần idempotency.

### 10.5. Chọn tầng phân phối work

| Nguồn ban đầu | Tầng chia work hợp lý | Điểm khó |
| --- | --- | --- |
| JMS Queue | Broker queue/listeners | Ack/transaction/redelivery |
| RabbitMQ Queue | Broker queue/consumers | Prefetch, nack/requeue, DLQ |
| Kafka Topic | Partitions/consumer group | Offset, rebalance, ordering |
| HTTP Request | Load balancer hoặc enqueue job bền vững | Idempotency client retry, state job |
| SFTP/File | Shared claim hoặc broker stage | File hoàn tất, metadata, duplicate |
| JDBC READY tasks | Transactional claim/lease | Concurrency, lease expiry, rollback |
| QueueChannel in JVM | PollingConsumers cục bộ | In-memory durability, handler failures |

## 11. Delivery semantics: một message có thể được xử lý nhiều lần

Trong các hệ thống có broker, thường gặp **at-least-once delivery**: nếu một consumer chưa xác nhận kết quả theo contract, message có thể được giao lại. Đây là cơ chế hỗ trợ khôi phục nhưng đòi hỏi business logic idempotent.

### 11.1. Cửa sổ lỗi kinh điển

~~~mermaid
sequenceDiagram
    participant Q as Broker Queue
    participant A as Consumer A
    participant DB as Database
    participant B as Consumer B
    Q->>A: Deliver W1
    A->>DB: Commit invoice(W1)
    DB-->>A: COMMITTED
    Note over A: JVM crash trước ack broker
    Q->>B: Redeliver W1
    B->>DB: Lặp lại invoice(W1)?
    DB-->>B: Phải phát hiện duplicate
    B-->>Q: Ack sau xác minh
~~~

Nếu handler tạo invoice mới mỗi lần mà không có unique business key, **invoice bị tạo trùng**. Nếu handler ghi dedupe record sau commit ở một hệ khác rồi chết trước khi ghi, dedupe cũng không cứu được.

### 11.2. Ba mức mục tiêu thường thấy

| Mục tiêu | Cách hiểu thực tế | Rủi ro/điều kiện |
| --- | --- | --- |
| **At-most-once** | Không có cơ chế giao lại khi coi message đã nhận | Có thể mất work nếu xử lý lỗi sau ack |
| **At-least-once** | Work có thể được nhận lại đến khi thành công/hết chính sách | Cần idempotency và poison-message handling |
| **Effectively-once** | Tác động nghiệp vụ cuối cùng tương đương xử lý một lần | Unique business key + transaction + đối soát |

Một số nền tảng có **exactly-once processing** trong phạm vi hẹp, như một pipeline stream/transaction được hỗ trợ, nhưng điều đó **không tự bao trùm** file, REST API, email, database khác và side effect ngoài transaction. Tránh khẳng định một queue đã cấu hình durability nghĩa là business exactly-once.

### 11.3. Ack không đồng nghĩa commit nghiệp vụ

Các mốc cần phân biệt:

~~~text
PUBLISHED   → broker nhận message
DELIVERED   → listener nhận message
HANDLING    → handler bắt đầu
COMMITTED   → business transaction thành công
ACKNOWLEDGED → broker ghi nhận tiến độ theo contract
~~~

Vị trí tương đối của **COMMITTED** và **ACKNOWLEDGED** quyết định nguy cơ mất hay duplicate. Với HTTP outbound gọi service khác, không có ack broker cho side effect đó; cần cơ chế trạng thái/idempotency riêng.

### 11.4. Consumer chết giữa xử lý

| Thời điểm chết | Điều có thể xảy ra | Thiết kế giảm rủi ro |
| --- | --- | --- |
| Trước khi nhận message | Broker/queue vẫn giữ work | Availability của consumer khác |
| Sau khi giao, trước business commit | Message có thể redeliver | Transaction rollback/claim timeout |
| Sau business commit, trước ack | Message có thể redeliver và chạy trùng | Idempotency ở business store |
| Sau ack, trước side effect async | Work có thể bị mất nếu async không durable | Ack sau durable handoff hoặc sau hoàn tất phù hợp |
| Khi gửi reply qua HTTP | Đích có thể đã commit dù caller timeout | Idempotency key, status query/reconciliation |

**Câu hỏi nghiệm thu:** Sau khi kill consumer đúng vào thời điểm tệ nhất, hệ thống có thể nói chính xác **work nào chưa xong** và có đường xử lý lại an toàn không?

## 12. Idempotent Consumer: khóa nghiệp vụ là nền tảng

Trong competing consumers, idempotency không nên chỉ nằm ở producer hoặc hàng đợi. Hai worker có thể nhận cùng work sau redelivery, đồng thời một cơ chế retry ở ứng dụng cũng có thể gọi side effect nhiều lần.

### 12.1. Chọn idempotency key

Ví dụ GenerateInvoice có thể dùng:

~~~text
consumerName  = invoice-generation
businessKey   = TENANT-LAB-01 / ORDER-LAB-0088 / INVOICE-STANDARD
version       = 2 (nếu version là một phần nghiệp vụ)
~~~

Không dùng chỉ **message timestamp** hoặc **MessageHeaders.ID** làm key vì message có thể được tạo lại khi retry. Với **hai consumer logic khác nhau** (Billing và Analytics), khóa idempotency phải phân biệt nghiệp vụ/consumer để một bên xử lý xong không làm bên kia bỏ qua event hợp lệ.

### 12.2. Bảng idempotency trong database

~~~sql
CREATE TABLE processed_work (
    consumer_name VARCHAR(100) NOT NULL,
    work_key VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_reference VARCHAR(200),
    PRIMARY KEY (consumer_name, work_key)
);
~~~

Ở lab có thể dùng unique constraint của DB để xử lý hai worker đua nhau. Trong ứng dụng thật, cần đặt việc ghi processed_work **trong cùng transaction DB** với thay đổi nghiệp vụ nếu chúng cùng một DB.

### 12.3. Giả mã xử lý có transaction

~~~text
consume(work):
  validateSourceSchemaAndAuthorization(work)
  key = deriveStableBusinessKey(work)

  beginDbTransaction()
    if processedWork.existsForUpdate(consumerName, key):
        return ALREADY_COMPLETED

    current = loadInvoiceState(work.businessKey)
    if work.version < current.version:
        recordIgnoredStaleWork(consumerName, key)
        commit
        return STALE

    writeInvoiceIdempotently(work)
    processedWork.insert(consumerName, key, invoiceId)
  commitDbTransaction()

  acknowledgeBrokerAccordingToContract()
~~~

**Quan trọng:** Giả mã chưa xử lý hết race giữa thao tác check và insert. Cài đặt thực phải dùng **unique constraint, locking/isolation và xử lý duplicate-key conflict**. Nếu có một side effect HTTP bên ngoài transaction, vẫn cần cơ chế idempotency/reconciliation riêng tại đích.

### 12.4. Key reuse với payload khác

Nếu cùng workKey được gửi lại với dữ liệu khác, không nên âm thầm bỏ qua như duplicate hợp lệ. Có thể lưu **hash của các trường nghiệp vụ quan trọng** để phát hiện thay đổi payload không đúng hợp đồng, đưa vào quarantine hoặc xử lý version update theo quy định. Hash cần tính trên cấu trúc dữ liệu chuẩn hóa và không được trở thành cách lộ thông tin nhạy cảm.

### 12.5. Inbox/Outbox

- **Inbox:** ghi nhận message/work đã xử lý bởi consumer để chống lặp.
- **Outbox:** ghi sự kiện sẽ phát ra cùng transaction với thay đổi nghiệp vụ, sau đó một relay publish.
- **Relay:** có thể publish trùng khi broker ack mất; downstream cần inbox/idempotency.
- **Reconciliation:** phát hiện business state đã commit nhưng event hoặc readback chưa đi tới đích.

Một hệ thống dùng cả inbox và outbox vẫn phải xét transaction và broker bên ngoài. Không tự giả định hai bảng này tạo một giao dịch atomic qua mọi hệ thống.

## 13. Ordering: thêm consumer có thể phá thứ tự nghiệp vụ

### 13.1. Ba loại thứ tự khác nhau

| Loại | Ý nghĩa | Vì sao có thể khác? |
| --- | --- | --- |
| **Publish order** | Producer phát W1 trước W2 | Source clock hoặc producer concurrency |
| **Delivery/start order** | Consumer bắt đầu W1 trước W2 | Broker dispatch, prefetch, scheduling |
| **Commit order** | Nghiệp vụ W1 commit trước W2 | DB latency, retry, thread pool, side effect |

Nhiều competing consumers tăng throughput cho work **độc lập**, nhưng công việc có phụ thuộc cùng tài nguyên cần ràng buộc rõ.

### 13.2. Ví dụ Mover/Leaver giả lập để minh họa stale state

~~~text
Event A: AccountRoleChanged(user=U7, version=10, role=EDITOR)
Event B: AccountDisabled(user=U7, version=11)

Worker A nhận event A, xử lý chậm.
Worker B nhận event B, commit DISABLED.
Worker A commit EDITOR sau đó.
~~~

Nếu handler chỉ ghi last-write-wins theo thời điểm **commit**, người bị disable có thể được cấp lại quyền sai. Cần **version check**, conditional update, xử lý tuần tự theo userId/aggregateId hoặc cơ chế phối hợp tương ứng.

### 13.3. Chiến lược khi cần thứ tự

1. **Một consumer/partition theo aggregate:** các event cùng orderId/userId được giữ cùng partition/nhóm xử lý tuần tự khi transport cho phép.
2. **Versioned writes:** chỉ áp dụng event nếu version đủ mới; phát hiện gap.
3. **Serial executor theo key:** khóa hoặc queue per key ở handler, tránh global serialization nếu không cần.
4. **Optimistic locking:** update có điều kiện theo state version và retry/reload khi xung đột.
5. **Reconciliation:** đối chiếu state nguồn–đích để phát hiện drift nếu event bị thiếu hoặc xử lý ngoài thứ tự.

**Kafka ordering caveat:** cùng key thường về cùng partition trong một cấu hình partitioner phù hợp, nhưng nếu bạn đẩy record sang ExecutorChannel nhiều thread thì **thứ tự business commit** không còn được bảo vệ chỉ bằng thứ tự partition. Với JMS/RabbitMQ nhiều consumer, không giả định có một thứ tự tổng thể được bảo toàn.

## 14. Retry, redelivery và poison messages

Một **poison message** là message luôn làm handler thất bại, chẳng hạn schema không hỗ trợ hoặc dữ liệu nghiệp vụ không hợp lệ. Nếu broker liên tục giao lại nó cho cùng queue, throughput có thể suy giảm và log bị ngập.

### 14.1. Phân loại lỗi

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Transient network** | DB timeout, HTTP 503, broker reconnect | Retry/backoff có giới hạn |
| **Rate limit** | HTTP 429 | Tôn trọng Retry-After, giảm concurrency |
| **Schema invalid** | Thiếu trường bắt buộc | Quarantine/DLQ, không retry vô hạn |
| **Business rejection** | Đơn hàng bị hủy theo chính sách | Ghi outcome nghiệp vụ; không mặc định retry |
| **Unknown duplicate** | Cùng key, payload khác | Kiểm tra version/source, không bỏ qua âm thầm |
| **Stale version** | Event v10 đến sau v11 | Skip/reconcile có audit theo contract |
| **Unauthorized producer** | Event từ nguồn không hợp lệ | Từ chối và cảnh báo |
| **Connector misconfiguration** | Credential sai, queue không tồn tại | Escalation, tránh tight retry loop |

### 14.2. Quy trình lỗi

~~~mermaid
flowchart TD
    RECEIVE["Receive work"] --> VALID{"Validate source + schema"}
    VALID -->|Sai| QUAR["Quarantine / Dead Letter"]
    VALID -->|Đúng| EXEC["Idempotent handler"]
    EXEC --> OK{"Commit đạt?"}
    OK -->|Có| ACK["Ack / Offset commit phù hợp"]
    OK -->|Transient error| BUDGET{"Retry budget còn?"}
    BUDGET -->|Có| DELAY["Backoff + redelivery"]
    DELAY --> EXEC
    BUDGET -->|Không| QUAR
    OK -->|Permanent failure| QUAR
    QUAR --> OPS["Owner review + controlled replay"]
~~~

Đặt **retry budget** theo loại lỗi, mức rủi ro và SLA. Một retry trong handler và một retry tại broker có thể nhân số lần thực thi; ghi rõ lớp nào điều khiển retry để tránh **retry storm**.

### 14.3. Dead-letter queue không tự giải quyết lỗi

Một DLQ/DLT cần có:

- Dữ liệu đủ truy lại nguồn, workKey, error class và số lần thử.
- Phân quyền xem, hạn lưu giữ, redaction thông tin nhạy cảm.
- Owner/quy trình triage, sửa nguyên nhân và replay.
- Cơ chế tránh replay một message lỗi schema vào cùng binary cũ rồi lặp lại vô hạn.
- Metrics về tuổi message trong DLQ và số lượng chưa xử lý.

### 14.4. Một lỗi ảnh hưởng toàn hàng đợi như thế nào?

Khi các worker cạnh tranh trên một queue, một message lỗi có thể bị giao lại nhiều lần, “nhảy” giữa worker và tiêu tốn slot/prefetch, khiến những message tốt bị chậm. Giới hạn retry và đưa poison message sang nơi riêng giúp flow chính có thể tiếp tục; nhưng nếu message cần thứ tự cùng aggregate, bỏ qua nó có thể vi phạm nghiệp vụ, cần **policy cho event gap**.

### 14.5. Error channel trong Spring Integration

Spring Integration có **ErrorMessage**, errorChannel, advice và error handler; đường đi thực tế phụ thuộc synchronous/asynchronous boundary. Với DirectChannel lỗi có thể lan ngược về listener; với ExecutorChannel exception có thể xảy ra sau khi sender trả về. Khi cấu hình JMS/AMQP/Kafka inbound adapter, phải kiểm tra **việc exception được ném lại, bị nuốt hay chuyển error flow** có ảnh hưởng thế nào tới ack và redelivery.

Không suy rằng **thêm errorChannel** tự động bảo đảm broker sẽ redeliver. Cần integration test với listener container, transaction và failure handling thực tế của phiên bản.

## 15. Backpressure, prefetch và chọn concurrency

Competing Consumers tăng năng lực bằng số worker, nhưng có giới hạn từ network, DB connection pool, rate limit và tài nguyên xử lý.

### 15.1. Mô hình năng lực cơ bản

Gọi:

- **λ** = tốc độ work mới đến (items/second).
- **μ** = tốc độ xử lý trung bình bền vững của **một worker** (items/second).
- **N** = số worker thực sự hoạt động, không nhất thiết bằng số instance đã deploy.
- **C** = năng lực tối đa của hệ đích (items/second).

Thông lượng thực tế bị giới hạn xấp xỉ:

~~~text
throughput <= min(N × μ, C, broker/source capacity)
~~~

Ví dụ nguồn tạo 200 work/giây, mỗi worker làm được 30 work/giây và DB chịu tối đa 150 work/giây:

| Workers | Năng lực lý thuyết N × 30 | Thông lượng bị DB giới hạn | Backlog kỳ vọng khi arrival=200/s |
| --- | ---: | ---: | ---: |
| 2 | 60/s | 60/s | +140/s |
| 4 | 120/s | 120/s | +80/s |
| 5 | 150/s | 150/s | +50/s |
| 8 | 240/s | 150/s | +50/s |

Đây chỉ là **minh họa lý thuyết** trong điều kiện ổn định, chưa tính retries, hot partitions, I/O, batching hoặc contention. Thêm từ 5 lên 8 workers không làm DB vượt khả năng 150/s, thậm chí có thể tăng lock/retry.

### 15.2. Queue depth và backlog age

**Queue depth** nói bao nhiêu item còn chờ; **age of oldest unprocessed item** nói work lâu nhất đã chờ bao lâu. Cần nhìn cả hai vì queue 100 messages nhưng mỗi message đã chờ một giờ có thể nguy hiểm hơn queue 1.000 messages mới đến vài giây.

### 15.3. Prefetch và fairness

- Prefetch nhỏ giúp broker phân bổ cơ hội giữa workers nhưng có thể giảm throughput khi round-trip cao.
- Prefetch lớn giảm overhead nhưng một worker có thể giữ nhiều message chưa ack, tạo **unfair distribution** và latency đuôi.
- Batch lớn có thể tăng hiệu quả nhưng làm **đơn vị retry** phức tạp khi một item trong batch lỗi.
- Worker nhanh/chậm khác nhau khiến phân phối không đều; đừng đặt điều kiện nghiệm thu “mỗi worker nhận đúng 1/N”.

### 15.4. Bounded concurrency

Nếu consumer gọi một REST API có quota 50 requests/s, không nên tăng 100 threads để “đẩy cho nhanh”. Chọn **semaphore/bulkhead**, rate limiter hoặc worker concurrency phù hợp. Với ExecutorChannel, đặt queue capacity và rejection policy có chủ ý; queue trong heap không tự bền vững qua process crash.

### 15.5. Khi nào scale-out không còn tác dụng?

- Số partition Kafka ít hơn số consumer trong group.
- Một partition/key nóng mang phần lớn traffic.
- DB lock hoặc transaction serialization là nút thắt.
- Remote API trả 429/503 do quá quota.
- Queue/broker network throughput hoặc connection count chạm ngưỡng.
- Poison messages tạo nhiều retry hơn work thành công.
- Handler giữ lock xuyên HTTP request làm mọi worker chờ.

## 16. Autoscaling và phân bổ worker

Autoscaling không đơn thuần là “khi queue có work thì tạo thêm nhiều pods”. Cần lựa chọn **tín hiệu kích hoạt**, **giới hạn số worker**, **thời gian khởi động** và **ngưỡng scale-down** để không làm hệ thống dao động liên tục.

### 16.1. Chọn tín hiệu

| Tín hiệu | Hữu ích ở đâu? | Cạm bẫy |
| --- | --- | --- |
| **Queue depth** | JMS/AMQP work queue | Không phản ánh độ nặng khác nhau giữa messages |
| **Oldest message age** | Mọi queue có tracking thời gian | Cần định nghĩa thời điểm tạo work đáng tin |
| **Kafka consumer lag** | Consumer group theo partition | Lag cao một partition nóng không tăng theo số worker mãi |
| **Processing latency** | Handler/DB/HTTP sink | Có thể chỉ ra sink nghẽn, scale-out vô ích |
| **CPU/memory** | Worker compute-bound | Không phản ánh chính xác backlog khi I/O-bound |
| **Retry/DLQ growth** | Lỗi lặp và poison messages | Scale-out có thể nhân retry storm |

### 16.2. Quy trình autoscaling an toàn

1. Đặt **minimum replicas** đủ đáp ứng yêu cầu availability và recovery.
2. Đo backlog/age cùng **committed throughput**, không chỉ messages received.
3. Chọn giới hạn replicas phù hợp connection pool, DB quota, API rate limit, partitions.
4. Đặt thời gian ổn định trước khi scale up/down để tránh dao động.
5. Khi scale down, cho listener dừng nhận work và hoàn tất/rollback theo giao thức.
6. Kiểm tra rebalancing/requeue và duplicate; đảm bảo idempotency trước khi autoscale.
7. Định kỳ load test với message size và tỉ lệ lỗi gần tình huống thực.

### 16.3. Kafka scale khác AMQP

Với Kafka, tăng consumer hơn số partition thường không tăng số consumer active. Khi một partition nặng bất thường, có thể cần điều chỉnh partitioning/key/hot key hoặc tối ưu xử lý, không chỉ tăng số pods. Với RabbitMQ/JMS work queue, tăng consumers có thể tăng khả năng nhận message, nhưng vẫn bị giới hạn bởi broker, prefetch và hệ đích.

### 16.4. Không để autoscaler làm mất tính đúng

Thêm worker nghĩa là **tăng cơ hội chạy đồng thời**. Nếu idempotency dựa vào HashSet riêng từng JVM, hai instance sẽ không chia sẻ trạng thái và có thể tạo kết quả trùng. Khóa nghiệp vụ, unique constraint và claim/lease phải đặt ở hệ có phạm vi phù hợp.

## 17. Startup, shutdown và vòng đời kết nối

Khi chạy production, một worker có thể dừng vì deploy, mất broker, hết credential hoặc lỗi hệ đích. Pattern chỉ có ích nếu hệ thống có cách khôi phục work đang dở.

### 17.1. Startup checklist

- [ ] Destination/topic/queue, binding, permission và broker connection hợp lệ.
- [ ] Listener/container được quản lý lifecycle bởi Spring ApplicationContext.
- [ ] Consumer group, queue name, subscription type đúng với business fan-out hay competing.
- [ ] Schema/deserializer và business idempotency store đã sẵn sàng trước khi nhận tải.
- [ ] Concurrency/prefetch được giới hạn theo tài nguyên thật.
- [ ] Error handler, DLQ/retry, backoff và alert đã cấu hình/kiểm thử.
- [ ] Nếu DB claim: lease/owner/version có đường reclaim an toàn sau crash.
- [ ] Nếu File/SFTP: producer file-ready contract, persistent metadata, lock/claim đủ cho multi-instance.
- [ ] Không vô tình subscribe cùng production queue từ môi trường dev/test.

### 17.2. Graceful shutdown

~~~text
Signal shutdown
    ↓
Listener ngừng nhận thêm work (theo khả năng container)
    ↓
In-flight work hoàn tất hoặc rollback/requeue theo contract
    ↓
Chỉ ack / commit offset những work đạt điều kiện
    ↓
Đóng broker session, DB pool và resources
~~~

Nếu timeout shutdown khiến process bị kill, **message chưa ack có thể được giao lại**. Đó là kết quả có thể mong đợi với at-least-once; test cần chứng minh business không bị nhân đôi ngoài ý muốn. Không xóa dữ liệu source khi chưa có kết quả nghiệp vụ được ghi nhận.

### 17.3. Bảng lỗi vòng đời

| Tình huống | Triệu chứng | Cần xử lý |
| --- | --- | --- |
| JMS broker restart | Listener mất session | Reconnect, xác minh redelivery và in-flight state |
| RabbitMQ connection close | Unacked messages được broker xử lý theo chính sách | Reconnect, kiểm tra ack/requeue/DLQ |
| Kafka rebalance | Assignment đổi, processing pause | Commit/ack đúng, tránh duplicate và xử lý stale worker |
| DB connection pool hết | Handler timeout, backlog tăng | Giảm concurrency, pool/transaction tuning |
| HTTP sink chậm | Thread bị giữ, 429/503 | Rate limit/bulkhead/circuit breaker |
| SFTP session stale | File poll không tiến triển | Reconnect, metadata/claim reconciliation |
| Pod bị kill khi có work | Work dở có thể redeliver | Idempotency, recovery, graceful period |
| Credential rotation | Connection/auth thất bại | Secret lifecycle, alert, reconnect có kiểm soát |

### 17.4. Zombie worker và fencing

Với cơ chế lease (đặc biệt Database/Custom polling), worker A có thể vẫn chạy sau khi lease của nó hết, trong khi worker B đã claim lại cùng task. Nếu cả hai commit, có thể lặp side effect. **Fencing token hoặc version có điều kiện lúc commit** giúp loại bỏ một worker đã mất quyền sở hữu, nhưng phải áp dụng đến hệ thống ghi cuối; chỉ khóa ở bước nhận không đủ.

### 17.5. Topology và connection count

Nhiều containers/consumers thường tạo nhiều broker sessions/connections và DB connections. Hãy tính giới hạn tổng thể, không chỉ per worker. Khi cấu hình 10 pods × 8 listener threads, app có thể tạo tới hàng chục hoặc hơn kết nối/phiên tùy container. Điều chỉnh cùng với pool, broker quotas và resource limits.

## 18. Observability: đo tiến triển thật của Competing Consumers

Một hệ thống nhiều consumer có thể có vẻ khỏe mạnh vì message được **deliver rất nhanh**, nhưng DB không tăng kết quả do handler liên tục retry. Cần giám sát **end-to-end**, không chỉ số lần consume.

### 18.1. Bảng metrics

| Metric | Ý nghĩa | Cảnh báo gợi ý |
| --- | --- | --- |
| **published messages** | Work mới được đưa vào nguồn | Tốc độ bất thường hoặc ngừng phát |
| **deliveries / receives** | Message được broker/channel giao cho consumer | Tăng nhưng processed không tăng |
| **in-flight/unacked** | Work đang do consumer giữ/chưa ack | Tăng cao, phân bổ không đều |
| **committed success rate** | Tốc độ nghiệp vụ hoàn tất | Giảm trong khi backlog tăng |
| **processing latency P50/P95/P99** | Thời gian handler/side effect | Tail latency tăng |
| **queue depth / Kafka lag** | Số work chưa xử lý theo transport | Tăng liên tục trong tải bình thường |
| **oldest unprocessed age** | Độ trễ của work lâu nhất | Vượt mục tiêu nghiệp vụ |
| **retry/redelivery rate** | Lỗi hoặc xử lý lặp | Cao kéo dài hoặc lặp một business key |
| **duplicate suppressed** | Work trùng được bảo vệ | Tăng sau restart/rebalance |
| **DLQ/DLT count + age** | Work cần xử lý thủ công | Không có owner hoặc quá hạn |
| **worker active/idle** | Khả năng chia work thực tế | Một worker giữ quá nhiều unacked hoặc không có partition |
| **DB/HTTP sink latency, saturation** | Nút thắt hạ nguồn | Scale-out không làm throughput tăng |
| **last business commit** | Tiến triển nghiệp vụ xác thực | Nguồn có work nhưng không commit mới |

**Nhãn metrics** nên dùng tên flow, target, consumer group, queue/partition, môi trường, error class; không dùng toàn bộ businessKey, eventId hoặc payload làm label vì cardinality và nguy cơ lộ dữ liệu.

### 18.2. Ví dụ audit log an toàn

~~~json
{
  "flow": "invoice-jobs-consumer",
  "workId": "WORK-LAB-0041",
  "consumerName": "invoice-generation",
  "workerInstance": "worker-lab-b",
  "source": "invoice.jobs",
  "attempt": 2,
  "stage": "BUSINESS_COMMIT",
  "result": "SUCCESS",
  "durationMs": 193,
  "traceId": "TRACE-LAB-0041",
  "committedAt": "2026-11-23T14:00:13+07:00"
}
~~~

Đây là format **minh họa**, không phải log mặc định của Spring Integration. Trong môi trường thật, log phải giảm PII, không chứa secret và có phân quyền truy cập cùng retention policy phù hợp.

### 18.3. Phân phối không đều có phải lỗi?

Không nhất thiết. Worker A xử lý 800 message và B xử lý 200 trong cùng kỳ có thể do tốc độ handler hoặc prefetch. Điều cần đo là:

- Có worker nào bị **kẹt** không?
- Có **hot partition/key** không?
- Work quá hạn có tăng không?
- Có một worker giữ nhiều message **unacked** trong khi worker khác rảnh?
- Tổng throughput và độ trễ có đáp ứng mục tiêu không?

Nếu hiệu năng tốt và không có yêu cầu fairness đặc biệt, phân phối không đều có thể chấp nhận được.

### 18.4. Ba cảnh báo giúp phát hiện lỗi sớm

1. **No progress:** queue có work nhưng không có business commit mới trong thời gian vượt ngưỡng.
2. **Oldest work age vượt giới hạn:** worker còn chạy nhưng work quan trọng bị trì hoãn.
3. **Failure loop:** retry/DLQ tăng nhanh hơn throughput thành công, đặc biệt do cùng một schema hoặc remote sink.

## 19. Runbook sự cố thường gặp

Một mẫu vận hành cần trả lời **đang sai ở đâu, work nào bị ảnh hưởng, có nguy cơ mất/trùng không, ai chịu trách nhiệm, cách xác minh đã sửa**.

### 19.1. Runbook A — Backlog tăng nhanh

1. Kiểm tra tốc độ work vào và **business commits/s**, không chỉ broker delivery rate.
2. Kiểm tra độ trễ xử lý, retries, DB pool, API quotas và lock contention.
3. Kiểm tra số worker **thực sự active**: Kafka partition assignment hoặc JMS/AMQP listener health.
4. Kiểm tra prefetch/unacked và worker chậm giữ work.
5. Tăng concurrency có giới hạn **chỉ khi sink có dư năng lực**; nếu không, giảm tải/rate limit.
6. Đo lại queue depth, oldest age và commit throughput sau thay đổi.

### 19.2. Runbook B — Message bị xử lý hai lần

1. Lấy **workId/businessKey** và kiểm tra audit ở cả hai worker.
2. Xác định redelivery, manual retry, timeout ACK hay duplicate từ producer.
3. Kiểm tra unique constraint/idempotency transaction ở nghiệp vụ.
4. Nếu có side effect trùng, thực hiện remediation/compensation theo quyền và nghiệp vụ.
5. Thêm regression test **commit thành công, ack thất bại, redelivery**.
6. Không “sửa” bằng cách tắt broker redelivery khiến work lỗi bị mất.

### 19.3. Runbook C — Poison message chặn queue

1. Tìm workKey lặp lỗi, message schema và error class.
2. Phân loại permanent vs transient; không replay lỗi schema vào code chưa hỗ trợ.
3. Áp retry budget, chuyển DLQ/quarantine theo chính sách.
4. Rà soát dữ liệu độc lập, nguyên nhân và owner.
5. Chạy controlled replay sau khi sửa và ghi kết quả.

### 19.4. Runbook D — Worker không nhận được message

Kiểm tra queue/topic, consumer group, partition assignment, subscriptions, credentials, network, listener startup, health và cấu hình môi trường. Nếu worker A và B thuộc **hai group khác nhau**, họ có thể đều nhận mỗi event (fan-out logic), không phải chia work; kiểm tra trước khi tăng replica.

### 19.5. Runbook E — Dừng/triển khai lại giữa chừng

Ghi số in-flight/unacked, thời điểm last business commit, các transaction chưa xong, trạng thái listener/offset, queue lag và kết quả sau restart. Thực hiện test kill-process trong môi trường được phép; xác minh work chưa hoàn tất được nhận lại an toàn và không tạo double charge/invoice.

### 19.6. Runbook F — Hai poller SFTP nhận cùng file

Kiểm tra remote file ID/path, filter metadata của từng replica, shared lock/claim, producer rename/marker, trạng thái xử lý sau crash và business key. Khắc phục bằng shared/persistent metadata và idempotency end-to-end; không xóa file nguồn bừa bãi để dừng duplicate nếu chưa biết đã commit nghiệp vụ.

## 20. Hands-on lab: xử lý hóa đơn bằng nhiều worker

**Mục tiêu:** minh họa từ một work queue nội bộ đến một broker test, với nhiều consumer có thể nhận work khác nhau, và kiểm chứng **business effect chỉ xảy ra một lần** kể cả sau redelivery.

### 20.1. Bối cảnh

**InvoiceJob Producer** tạo work item để sinh hóa đơn. Mỗi work có **workId**, **tenantId**, **orderId** và **invoiceType**. Hệ thống nhận nhiều công việc độc lập, nhưng không được tạo hai hóa đơn cùng loại cho cùng order do retry/crash.

~~~json
{
  "workId": "WORK-LAB-0041",
  "type": "GenerateInvoice",
  "tenantId": "TENANT-LAB-01",
  "orderId": "ORDER-LAB-0088",
  "invoiceType": "STANDARD",
  "schemaVersion": 1
}
~~~

**Tiêu chí nghiệp vụ giả định:** mỗi bộ khóa (**tenantId, orderId, invoiceType**) có tối đa một hóa đơn đang hợp lệ. Đây là lựa chọn của lab, không phải quy tắc chung cho mọi hệ thống hóa đơn (ví dụ hóa đơn điều chỉnh có thể cần version và loại riêng).

### 20.2. Kiến trúc hai cấp

~~~mermaid
flowchart TD
    P["Producer"] --> IN["API / Application Service"]
    IN --> Q1["Phase A: QueueChannel in JVM"]
    Q1 --> W1["PollingConsumer A"]
    Q1 --> W2["PollingConsumer B"]
    W1 --> BIZ["Validate + Idempotent Invoice Service"]
    W2 --> BIZ
    IN --> Q2["Phase B: Durable Broker Queue"]
    Q2 --> A["Listener instance A"]
    Q2 --> B["Listener instance B"]
    A --> BIZ
    B --> BIZ
    BIZ --> DB["Test Database + unique key"]
    BIZ --> AUDIT["Test evidence"]
~~~

**Phase A và Phase B là hai lần thử riêng**, không phải producer cùng lúc phát cùng một work tới cả hai nhánh trừ khi bài lab cố ý kiểm tra trùng.

### 20.3. Bước 1 — Dựng QueueChannel nội bộ

Sử dụng cấu hình Java DSL ở phần 6. Đặt capacity=100, hai polling consumers dùng cùng QueueChannel. Producer gửi **WORK-LAB-001 đến WORK-LAB-010**. Ghi workId và workerId tại handler.

Kỳ vọng:

- Mỗi lần dequeue, một endpoint nhận work; không broadcast tới cả hai.
- Cả hai có thể nhận số lượng khác nhau.
- Work không có thứ tự hoàn tất bắt buộc giữa các consumer.
- Không suy luận về exactly-once sau crash vì QueueChannel đang trong memory.

### 20.4. Bước 2 — Thay log bằng business handler

Tạo một repository test để ghi invoice, dùng unique key ở DB:

~~~sql
CREATE TABLE invoice_lab (
    invoice_id VARCHAR(120) PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    order_id VARCHAR(120) NOT NULL,
    invoice_type VARCHAR(60) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_invoice_business
        UNIQUE (tenant_id, order_id, invoice_type)
);
~~~

Khi nhận work mới:

1. Validate schema, tenant và quyền của nguồn phát command.
2. Xác định business key, kiểm tra có invoice hợp lệ chưa.
3. Tạo invoice trong transaction có unique constraint; hai worker cùng thử phải xử lý conflict an toàn.
4. Ghi audit workId, result và thời điểm commit.
5. Không coi exception duplicate-key là lỗi dữ liệu nghiêm trọng nếu nó biểu thị một work đã được hoàn tất đúng; nhưng phải kiểm tra payload không mâu thuẫn.

**Điểm cần lưu ý:** một HashSet in-memory chỉ hữu ích để bắt đầu học; để chứng minh chống trùng qua restart và nhiều instance, cần kho bền vững.

### 20.5. Bước 3 — Mô phỏng hai worker cùng xử lý một business key

Gửi hai message có **workId khác** nhưng cùng business key hóa đơn; sau đó gửi lại đúng message thứ nhất. Cách xử lý đúng là bảo vệ theo nghiệp vụ:

~~~text
WORK-LAB-0041 → (TENANT-01, ORDER-88, STANDARD)
WORK-LAB-0042 → (TENANT-01, ORDER-88, STANDARD)
WORK-LAB-0041 → (TENANT-01, ORDER-88, STANDARD) [redelivery]

Expected: 1 invoice theo quy tắc lab; các lần sau được nhận diện
          là duplicate/đã có kết quả hoặc payload conflict.
~~~

Sự khác nhau giữa **workId duplicate** và **business key collision** rất quan trọng: trong một nghiệp vụ khác, hai workId hợp lệ có thể cùng target nhưng mang hai hành động khác nhau. Vì vậy phải định nghĩa key theo business contract.

### 20.6. Bước 4 — Thêm broker test

Chọn **JMS test broker hoặc RabbitMQ test container** được phép, không cần cả hai ngay. Tạo một queue invoice.jobs, hai listener/instances cùng subscribe. Với Spring Integration, dùng message-driven inbound adapter vào business handler. Thiết lập ack/transaction, retry và DLQ theo lựa chọn broker.

Quan sát sự khác biệt:

| Hạng mục | QueueChannel nội bộ | Broker queue |
| --- | --- | --- |
| Work đang chờ được lưu ở đâu? | Trong JVM theo cấu hình mẫu | Broker/store theo durability cấu hình |
| Khi một worker chết | Work đã dequeue có thể mất nếu không tự phục hồi | Broker có thể redeliver chưa ack theo semantics |
| Khi cả JVM chết | Queue memory không còn | Work tồn tại hay không tùy broker/durability |
| Chạy nhiều replicas | Không cùng chia sẻ một QueueChannel JVM | Có thể cùng nhận một queue |
| Ack | Không phải broker acknowledgment | Có cơ chế ack/transaction/redelivery |
| Thứ tự | Theo queue receive + worker scheduling | Theo broker/concurrency/prefetch |

### 20.7. Bước 5 — Fault injection

Chạy lần lượt:

- **DB timeout trước commit:** không được ghi thành công giả; message cần retry theo contract.
- **DB commit rồi worker chết trước ack:** broker redeliver; unique key/idempotency ngăn double invoice.
- **Một JSON sai schema:** sau retry hợp lý, message được quarantine/DLQ, không chặn mọi work tốt.
- **Worker A dừng đột ngột:** worker B còn có thể xử lý work được broker phân phối; test failover bằng readback.
- **Worker B xử lý chậm:** đo phân phối, prefetch/unacked và queue age.
- **Hai instances cùng xử lý conflict key:** DB vẫn chỉ có một hóa đơn theo business rule.

### 20.8. Bước 6 — Đo throughput và backlog

Tạo bộ dữ liệu 100 hoặc 1.000 work giả; tăng consumer từ 1 lên 2, 4, 8. Giữ cấu hình DB có giới hạn để thấy **điểm bão hòa**. Ghi số message/giây đã **commit**, không chỉ số receive. Đo cả queue depth, oldest age, retry và CPU/DB pool.

### 20.9. Bước 7 — Thử Kafka với consumer group

Nếu mở rộng, tạo topic test có **ba partitions**, group billing-workers, chạy lần lượt **1, 2, 3, 4 consumer instances**. Ghi:

1. Partition assignment.
2. Số consumer active thực nhận partitions.
3. Consumer lag và commit throughput.
4. Hành vi sau kill/restart một instance.
5. Ordering theo **orderId** và duplicate sau rebalance.

**Không kỳ vọng consumer thứ tư tăng throughput** khi group chỉ có ba partitions đang được gán.

### 20.10. Sản phẩm bàn giao lab

| Sản phẩm | Nội dung |
| --- | --- |
| Topology | Producer, queue/topic, worker, business DB, DLQ |
| Message contract | workId, tenant, order, business key, version |
| Worker implementation | Spring Integration endpoint và handler |
| Test DB schema | Unique key/idempotency và business state |
| Fault injection | Trước commit, sau commit/trước ack, poison message, worker crash |
| Observability | Commit rate, queue depth/lag, retries, DLQ age |
| Runbook | Retry, duplicate, backlog, worker restart và DLQ replay |
| Hạn chế | Điều gì là mô phỏng, điều gì đã xác minh với broker thực |

## 21. Ma trận kiểm thử Competing Consumers

Mỗi ca phải ghi **Input, Expected, Actual, PASS/FAIL/UNKNOWN, Evidence**. Cột Expected là tiêu chí thiết kế; không tự coi PASS khi mới viết mã nhưng chưa chạy thử.

| ID | Tình huống | Điều kiện PASS |
| --- | --- | --- |
| **CC-01** | Một QueueChannel, hai PollingConsumers | Một lần receive không broadcast cùng message tới cả hai |
| **CC-02** | QueueChannel rỗng | Không gọi business handler với payload rỗng |
| **CC-03** | Gửi 10 work items | Mỗi work hợp lệ có kết quả hoặc lỗi rõ, không bắt buộc chia đều |
| **CC-04** | QueueChannel đầy capacity | Producer được backpressure/failure có kiểm soát |
| **CC-05** | Handler sau QueueChannel ném lỗi | Không giả định broker redelivery; cơ chế phục hồi rõ |
| **CC-06** | Restart JVM khi queue memory còn message | Giới hạn độ bền được ghi nhận, không khẳng định không mất |
| **CC-07** | JMS Queue có ba listeners | Work được chia giữa listeners theo broker contract |
| **CC-08** | JMS Topic với hai subscription độc lập | Phân biệt fan-out với competing consumers |
| **CC-09** | JMS listener lỗi trước commit | Redelivery/rollback theo cấu hình được kiểm chứng |
| **CC-10** | RabbitMQ hai consumers cùng queue | Các deliveries được chia, không broadcast |
| **CC-11** | RabbitMQ prefetch cao + một worker chậm | Unacked/imbalance quan sát được, không có claim sai |
| **CC-12** | RabbitMQ nack/requeue lặp | Retry/DLQ có giới hạn, không infinite loop |
| **CC-13** | Kafka topic 3 partitions, group 2 consumers | Partition assignment hợp lệ, không trùng active owner |
| **CC-14** | Kafka 3 partitions, group 4 consumers | Consumer dư không tự tăng active partitions |
| **CC-15** | Kafka hai consumer groups | Mỗi group nhận event theo contract riêng |
| **CC-16** | Kafka rebalance khi chưa commit offset | Redelivery an toàn, không double business effect |
| **CC-17** | Kafka hot partition | Đo lag per partition, xác định giới hạn scale |
| **CC-18** | File/SFTP hai replicas không shared metadata | Phát hiện khả năng xử lý file trùng |
| **CC-19** | SFTP có shared claim và worker crash | Có recovery hợp lệ, không bỏ sót work |
| **CC-20** | JDBC hai worker claim một READY row | Chỉ một claim hợp lệ tại cùng thời điểm |
| **CC-21** | Lease DB hết hạn, worker cũ vẫn chạy | Fencing/version ngăn stale worker commit sai |
| **CC-22** | HTTP caller retry sang instance khác | Idempotency store chung tránh side effect trùng |
| **CC-23** | Business commit thành công, broker ack mất | Redelivery không tạo thêm invoice |
| **CC-24** | Hai workId khác nhau cùng business key | Unique constraint bảo vệ theo policy |
| **CC-25** | Cùng workId, payload mâu thuẫn | Không âm thầm bỏ; báo conflict hoặc xử lý version |
| **CC-26** | Schema invalid | Quarantine/DLQ có owner và reason |
| **CC-27** | DB timeout trước commit | Retry an toàn, không ghi processed sớm |
| **CC-28** | Worker A chết, worker B còn | Work chưa ack được tái phân phối theo contract |
| **CC-29** | Event v10 xử lý sau v11 | Không ghi đè trạng thái mới |
| **CC-30** | Hai consumers tăng lên tám nhưng DB bão hòa | Metrics chỉ ra bottleneck, không báo throughput giả |
| **CC-31** | Backlog age vượt ngưỡng | Alert phát hiện work lâu chưa hoàn tất |
| **CC-32** | DLQ replay sau sửa schema | Chạy lại có idempotency, không lặp side effect |
| **CC-33** | Shutdown khi còn unacked messages | Rollback/requeue/commit theo contract, không mất âm thầm |
| **CC-34** | API sink trả 429 | Giảm concurrency/backoff, tránh retry storm |
| **CC-35** | Authorization tenant không hợp lệ | Không xử lý side effect, có audit an toàn |
| **CC-36** | Logs chứa token/private key | Có redaction, không để lộ secret |

### 21.1. Mẫu báo cáo ca CC-23

~~~yaml
testCase: CC-23
workId: WORK-LAB-0041
scenario: "DB commit succeeds, worker dies before broker ack"
expected: "Broker redelivers; exactly one business invoice remains"
actual: "Fill after running the lab"
result: PENDING
evidenceRef: "lab://tests/CC-23"
owner: invoice-lab
verifiedAt: null
~~~

**Actual và evidenceRef phải đến từ lần chạy thử thật.** Nếu test không thể tạo crash đúng thời điểm, ghi **UNKNOWN/PENDING** và nêu rõ cách tái hiện còn thiếu, không điền PASS.

### 21.2. Những phép thử âm tính đặc biệt quan trọng

1. **Duplicate after commit:** redelivery sau khi DB commit.
2. **Poison-message loop:** lỗi schema không thể tự sửa, DLQ phải có tác dụng.
3. **Stale event:** message version cũ hoàn tất sau message mới.
4. **Shared storage race:** hai worker cùng claim một task.
5. **Wrong subscriber topology:** vô tình dùng một queue cho hai nghiệp vụ vốn đều cần message.
6. **Ack before async business completion:** listener kết thúc trong khi worker ExecutorChannel vẫn chạy.

Kết quả của sáu ca này thường có giá trị hơn việc chỉ chứng minh bốn worker cùng in ra console.

## 22. Anti-patterns và checklist production

### 22.1. Sai lầm thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| **Nhầm fan-out với competing consumers** | Một trong hai nghiệp vụ có thể không nhận event | Mỗi nghiệp vụ có queue/subscription/group riêng, cạnh tranh trong nhóm |
| **Cho rằng nhiều @ServiceActivator trên DirectChannel là durable queue** | Không có persistence/redelivery như broker | Dùng broker hoặc state store khi cần độ bền |
| **Dùng QueueChannel memory để xử lý giao dịch tài chính quan trọng** | Crash có thể mất work đang chờ/đã dequeue | Durable queue + idempotency + kiểm chứng failure |
| **Tăng workers nhưng DB đã hết capacity** | Tăng contention, retry và latency | Đo sink throughput, giới hạn worker, tối ưu DB |
| **Kafka nhiều consumers hơn partitions rồi mong nhanh hơn** | Consumer không có partition nhận sẽ nhàn rỗi | Điều chỉnh partitions/key hoặc handler, không chỉ replicas |
| **Dùng một Kafka group cho Billing và Analytics** | Các event bị chia, mỗi nghiệp vụ không thấy hết | Tách group theo logical subscriber |
| **Dùng metadata in-memory cho nhiều SFTP replicas** | Hai instance nhận cùng file | Shared persistent metadata/claim + business idempotency |
| **SELECT READY rồi xử lý ngay** | Hai DB workers cùng nhận task | Transactional claim/lock/lease |
| **Ack broker trước khi business commit** | Crash làm mất work dù broker tưởng xong | Ack sau điều kiện thành công hoặc durable handoff |
| **Tin ack/commit chứng minh exactly-once** | Redelivery sau commit có thể gây side effect lặp | Inbox/idempotency/unique business key |
| **Không giới hạn retry** | Poison message/retry storm làm nghẽn queue | Backoff, retry budget, DLQ, owner |
| **Prefetch quá cao không đo unacked** | Worker giữ nhiều message, fairness thấp | Điều chỉnh theo latency, tải, recovery |
| **Tăng concurrency khi cần thứ tự theo key** | Event cũ ghi đè event mới | Partition key, version check hoặc per-key serialization |
| **Chỉ đếm received làm throughput** | Handler có thể lỗi và không commit | Đo committed success và backlog age |
| **Dùng HashSet per-instance để dedupe production** | Mất sau restart và không chia sẻ giữa replicas | Unique constraint/idempotency store bền vững |
| **Không phân biệt business rejection và technical failure** | Retry sai hoặc bỏ work hợp lệ | Error taxonomy và outcome rõ ràng |
| **Coi HTTP load balancer như broker** | Không có durable ack/redelivery | Persist job/queue trước khi trả accepted |
| **Không kiểm tra graceful shutdown** | In-flight work không rõ trạng thái | Kill/restart test và runbook |
| **Log toàn payload/credentials** | Rò dữ liệu và secret | Redaction, tối thiểu hóa dữ liệu |

### 22.2. Checklist chọn Competing Consumers

- [ ] Đơn vị work được định nghĩa rõ; có business key ổn định.
- [ ] Đã xác định nhóm nghiệp vụ nào cần **cùng nhận tất cả event**, nhóm nào cần **chia work**.
- [ ] Đã chọn đúng topology: JMS Queue, RabbitMQ queue, Kafka consumer group hay cơ chế claim riêng.
- [ ] Khi dùng QueueChannel trong JVM, đã biết rõ hạn chế về persistence/redelivery.
- [ ] Khi dùng File/SFTP/JDBC, đã thiết kế shared claim/lock/metadata cho multi-instance.
- [ ] Message contract có schema version, nguồn, tenant và cách xác thực/ủy quyền.
- [ ] Đã xác định ack, offset commit hoặc mark processed tại điểm phù hợp.
- [ ] Có business idempotency dùng chung giữa các worker/restarts.
- [ ] Work key reuse và payload conflict có cách xử lý.
- [ ] Ordering và stale version được kiểm tra nếu công việc phụ thuộc state.
- [ ] Retry budget, backoff, DLQ/quarantine và replay policy có owner.
- [ ] Prefetch/batch/concurrency có giới hạn và được đo thực tế.
- [ ] Downstream có capacity tương ứng; rate limit và DB saturation được tính.
- [ ] Multi-instance/consumer group/partition assignments được kiểm chứng.
- [ ] Startup, graceful shutdown và broker reconnect có runbook.
- [ ] Metrics phân biệt delivered, processed, committed, acked và duplicated.
- [ ] Có alert backlog age, no progress, retry loop và DLQ overdue.
- [ ] Đã chạy test crash sau commit trước ack và stale event.
- [ ] Không đưa token/secret/PII không cần thiết vào logs và headers.
- [ ] Có bản đồ trách nhiệm từ source tới handler, business store và người trực vận hành.

### 22.3. Cây quyết định thiết kế

~~~mermaid
flowchart TD
    START{"Nhiều nghiệp vụ cần nhận mỗi event?"}
    START -->|Có| FAN["Tạo subscription / queue / group cho từng nghiệp vụ"]
    START -->|Không| Q{"Nguồn đã là durable work queue?"}
    FAN --> Q2["Competing workers trong từng subscription"]
    Q -->|JMS/AMQP| BROKER["Competing listeners cùng queue"]
    Q -->|Kafka| K["Cùng group; partition assignment"]
    Q -->|File/SFTP/DB| CLAIM["Shared claim / leader / durable broker stage"]
    Q -->|QueueChannel in JVM| LOCAL["Local PollingConsumers; xác định giới hạn durability"]
    Q2 --> SAFE["Ack + idempotency + ordering + errors"]
    BROKER --> SAFE
    K --> SAFE
    CLAIM --> SAFE
    LOCAL --> SAFE
    SAFE --> SCALE["Đo sink capacity + prefetch + backlog"]
    SCALE --> TEST["Crash/retry/rebalance test trước production"]
~~~

Nếu chưa thể trả lời **“work nào được coi là đã hoàn tất và ai chứng minh nó?”**, chưa nên tăng consumer count. Hãy thiết kế completion contract trước khi scale.

## 23. Tổng kết và câu hỏi tự đánh giá

### 23.1. Tám điều cần ghi nhớ

1. **Competing Consumers** là cách **chia công việc** giữa nhiều worker, không phải cách broadcast mọi message cho tất cả.
2. Nhiều consumer trên **JMS/AMQP queue** có thể cạnh tranh nhận work; với **Kafka**, phải hiểu **consumer group và partition assignment**.
3. **QueueChannel + PollingConsumers** minh họa cơ chế trong một JVM nhưng không tự có durability/ack như broker.
4. **Event-driven Consumer và Polling Consumer** mô tả cách kích hoạt, còn Competing Consumers mô tả phân phối work; các pattern có thể cùng tồn tại.
5. **File/SFTP/JDBC** cần shared claim/lock/metadata hoặc broker stage nếu có nhiều instance; quét cùng nguồn không tự tránh duplicate.
6. **Ack/offset** và **business commit** không phải cùng một mốc. Redelivery là tình huống bình thường cần được chịu đựng bằng idempotency.
7. **Thứ tự và concurrency** có thể xung đột; business version và partitioning theo key bảo vệ trạng thái quan trọng.
8. **Scale-out** chỉ hữu ích đến khi chạm giới hạn broker, partition, DB, API rate limit hoặc nghiệp vụ.

### 23.2. Câu hỏi tự kiểm tra

1. Vì sao ba consumer cùng một RabbitMQ queue **không** làm Billing, Analytics và Email mỗi bên nhận mọi event?
2. Nếu JMS listener A commit DB rồi chết trước ack, JMS listener B có thể làm gì và DB phải bảo vệ ra sao?
3. Khi nào hai PollingConsumers trên QueueChannel đủ cho lab nhưng không đủ cho xử lý tài chính production?
4. DirectChannel có nhiều subscribers khác PublishSubscribeChannel như thế nào?
5. Với Kafka topic ba partitions, thêm consumer thứ tư vào cùng group có làm tăng work parallelism không?
6. Vì sao prefetch lớn có thể khiến một worker giữ nhiều work chưa ack trong khi worker khác đang rảnh?
7. Tại sao hai poller SFTP đều dùng accept-once filter **trong memory** vẫn xử lý trùng file?
8. SELECT status=READY có ngăn được hai worker cùng lấy một hàng DB không?
9. Nếu event AccountDisabled v11 commit rồi AccountRoleChanged v10 đến muộn, cần kiểm tra gì?
10. Làm sao biết queue depth tăng là do thiếu worker hay vì DB/HTTP sink bị nghẽn?
11. DLQ cần những gì ngoài một queue chứa message lỗi?
12. Khi rolling deploy, điều gì sẽ xảy ra với message đang xử lý chưa ack?

**Gợi ý:** (1) cùng queue là chia work, muốn fan-out cần subscription/queue riêng; (2) redeliver, dùng idempotency/unique key; (3) durability, recovery và multi-instance; (4) một handler được chọn so với broadcast; (5) thường không khi không có partition được gán thêm; (6) unacked prefetch reservation; (7) JVM không chia sẻ metadata; (8) không, cần claim/transaction; (9) version/order; (10) đo committed throughput, latency và sink saturation; (11) retention, owner, triage/replay; (12) commit hoặc requeue/redelivery theo contract.

### 23.3. Kết luận

**Competing Consumers Pattern** là công cụ quan trọng để tăng thông lượng và khả năng phục hồi của hệ thống tích hợp: nhiều worker chia sẻ hàng đợi hoặc nhóm tiêu thụ để xử lý các work item **có thể phân phối**. Trong **Spring Integration Adapters**, mẫu này xuất hiện ở cả **PollingConsumer đọc QueueChannel**, **JMS/AMQP message-driven inbound adapter** và **Kafka consumer group**; đồng thời liên quan đến các luồng File, SFTP, HTTP, Database khi dữ liệu được chuyển thành durable work hoặc được claim an toàn.

Tuy nhiên, nhiều worker chỉ giải quyết **một phần năng lực nhận và xử lý**. Kết quả đáng tin phụ thuộc **message contract, idempotency, transaction, acknowledgment, dead-letter, ordering, backpressure, lifecycle và observability**. Khi bạn có thể chứng minh **một worker bị kill sau business commit nhưng trước ack, work được giao lại, business state vẫn đúng và không bị nhân đôi**, bạn đã đi từ hiểu pattern tới khả năng thiết kế một luồng competing consumers có thể vận hành.

**Nguyên tắc chốt:** *Chia việc để tăng tốc là dễ; chứng minh từng việc hoàn tất chính xác, không mất và không tạo tác động trùng sau lỗi mới là thước đo thiết kế Competing Consumers tốt.*
