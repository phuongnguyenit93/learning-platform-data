# Phạm vi hỗ trợ exactly-once và tính lũy đẳng của xử lý nghiệp vụ

## Mục tiêu bài học

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud tương ứng. Trong hệ thống messaging, một message có thể được giao lại khi subscriber nack, hết ack deadline hoặc mất kết nối. Ứng dụng cần phân biệt bảo đảm delivery của broker với việc một nghiệp vụ chỉ tạo side effect đúng một lần.

Google Cloud Pub/Sub có tính năng **exactly-once delivery** cho pull subscription. Tính năng này giúp subscriber biết acknowledgment đã được Pub/Sub xử lý thành công hay chưa và ngăn redelivery sau một acknowledgment thành công trong phạm vi được hỗ trợ. Tuy vậy, nó không tự tạo transaction phân tán giữa Pub/Sub, database và các API bên ngoài.

Sau bài học, bạn có thể:

1. Giải thích chính xác phạm vi bảo đảm exactly-once delivery của Pub/Sub.
2. Phân biệt redelivery, duplicate delivery và hai lần publish cùng một event nghiệp vụ.
3. Tạo pull subscription bật exactly-once delivery.
4. Hiểu yêu cầu regional affinity, ack response và ack ID mới nhất.
5. Nhận acknowledgment response bằng Java Pub/Sub client.
6. Phân biệt API ack của `PubSubTemplate` với API trả `AckResponse` của Java client.
7. Thiết kế inbox/idempotency key để bảo vệ side effect trong database và hệ thống ngoài.
8. Kiểm thử các tình huống ack thành công, ack không chắc chắn, redelivery và duplicate publish.

## 1. Exactly-once delivery có nghĩa gì?

### 1.1. Bảo đảm ở tầng Pub/Sub

Khi bật exactly-once delivery trên một pull subscription, Pub/Sub cung cấp các semantics chính:

- Subscriber có thể nhận biết request acknowledgment đã thành công hay thất bại.
- Khi Pub/Sub xác nhận ACK thành công, message đó sẽ không được giao lại cho subscription trong phạm vi region được hỗ trợ.
- Khi message vẫn outstanding và ack deadline chưa hết, Pub/Sub không redeliver message đó theo semantics exactly-once.
- Nếu message được giao lại do NACK hoặc ack deadline hết hạn, chỉ acknowledgment ID của lần giao mới nhất còn hợp lệ để ACK.

Điểm quan trọng là **exactly-once delivery gắn với Pub/Sub message ID trên một subscription**, không phải với nội dung JSON hoặc ID nghiệp vụ mà ứng dụng đặt trong payload.

### 1.2. Các loại “trùng” cần phân biệt

| Tình huống | Message ID | Exactly-once delivery xử lý? |
| --- | --- | --- |
| Subscriber NACK và nhận lại cùng message | Giữ nguyên message ID | Đây là redelivery hợp lệ; tính năng không loại bỏ retry do NACK |
| Ack deadline hết hạn, message được giao lại | Giữ nguyên message ID | Đây là redelivery hợp lệ; subscriber cần xử lý lại |
| Pub/Sub giao lại sau khi ACK đã được xác nhận thành công | Cùng message ID | Được ngăn trong phạm vi exactly-once và cùng region |
| Publisher gửi cùng event logic hai lần | Hai publish operation có thể có message ID riêng | Không được deduplicate chỉ bởi exactly-once delivery |
| Producer retry publish và tạo thêm một bản message | Có thể có message ID khác | Không được xem là một message delivery trùng; ứng dụng phải deduplicate bằng event ID |

Ví dụ producer tạo event `OrderPaid` với `eventId=evt-1001`, nhưng do timeout ở tầng ứng dụng nên gửi lại event đó bằng một publish request mới. Pub/Sub có thể xem đây là hai message khác nhau. Một subscription bật exactly-once vẫn có thể nhận cả hai message vì mỗi message có message ID riêng.

Vì vậy, hãy dùng hai lớp bảo vệ:

1. Exactly-once delivery để kiểm soát redelivery của cùng Pub/Sub message trong phạm vi hỗ trợ.
2. Idempotency ở tầng nghiệp vụ để chống hai message khác nhau đại diện cho cùng một event logic.

## 2. Exactly-once delivery không bảo đảm điều gì?

Tính năng này không:

- Làm cho publisher tự động deduplicate các lần publish cùng payload.
- Bảo đảm một database transaction và một ACK Pub/Sub commit nguyên tử cùng lúc.
- Bảo đảm một HTTP API bên ngoài chỉ được gọi đúng một lần.
- Bảo đảm không có retry sau NACK hoặc sau khi ack deadline hết hạn.
- Bảo đảm exactly-once xuyên nhiều region.
- Hỗ trợ push subscription hoặc subscription export trực tiếp tới BigQuery/Cloud Storage.
- Thay thế event ID, inbox table, idempotency key hoặc transactional outbox.

Ví dụ, consumer cập nhật số dư tài khoản trong database rồi gửi ACK. Nếu database commit thành công nhưng ACK bị lỗi mạng, message có thể được giao lại. Exactly-once không thể tự rollback transaction database đã commit. Consumer phải nhận ra event đã được áp dụng và không trừ tiền lần thứ hai.

## 3. Phạm vi hỗ trợ và giới hạn theo region

### 3.1. Chỉ hỗ trợ pull subscription

Exactly-once delivery hỗ trợ:

- Pull API.
- StreamingPull API.
- High-level subscriber client library sử dụng pull/StreamingPull.

Không hỗ trợ:

- Push subscription.
- BigQuery export subscription.
- Cloud Storage export subscription.
- Các subscription export khác mà Pub/Sub tự đẩy dữ liệu tới dịch vụ đích.

Lý do là pull subscriber chủ động gửi ACK request tới Pub/Sub và có thể nhận response cho biết ACK đã được xử lý. Với push, subscriber trả HTTP response nhưng không thể biết chắc Pub/Sub đã nhận và lưu acknowledgment đó hay chưa.

### 3.2. Guarantee chỉ trong một region

Pub/Sub exactly-once guarantee chỉ áp dụng khi các subscriber kết nối tới Pub/Sub trong **cùng một region**. Nếu cùng subscription có consumer chạy ở nhiều region, có thể xảy ra duplicate delivery dù tính năng đã bật.

Khi chạy ứng dụng trên Google Cloud trong một region, client thường kết nối endpoint cùng region. Với ứng dụng ngoài Google Cloud hoặc triển khai nhiều region, dùng locational endpoint để bảo đảm subscriber đi vào một region cụ thể.

Ví dụ endpoint:

```text
asia-southeast1-pubsub.googleapis.com:443
```

Đây chỉ là endpoint minh họa cho region Singapore. Tất cả subscriber của subscription cần được định tuyến nhất quán tới cùng region nếu muốn dựa vào guarantee exactly-once.

Publisher có thể publish từ region khác; giới hạn regional affinity áp dụng cho subscriber connection.

### 3.3. Pull subscription và ACK response

Exactly-once delivery dựa vào khả năng nhận kết quả ACK:

```mermaid
sequenceDiagram
    participant S as Subscriber
    participant P as Pub/Sub
    S->>P: Pull / StreamingPull
    P-->>S: Message + ack ID
    S->>S: Xử lý nghiệp vụ
    S->>P: Acknowledge(ack ID)
    P-->>S: ACK response
    alt ACK thành công
        S->>S: Ghi nhận hoàn tất
        Note over S,P: Không redeliver cùng message trong region
    else ACK thất bại hoặc không rõ kết quả
        S->>S: Giữ trạng thái xử lý và chờ kết quả/redelivery
        Note over S,P: Có thể giao lại; consumer phải idempotent
    end
```

Không nên coi việc gọi method `ack()` là bằng chứng ACK đã được Pub/Sub xác nhận. Ứng dụng cần quan sát response/future phù hợp với API đang sử dụng.

## 4. Bật exactly-once delivery cho subscription

### 4.1. Tạo pull subscription

Tạo subscription mới bật exactly-once:

```bash
gcloud pubsub subscriptions create orders-exactly-once-sub \
  --topic=orders \
  --enable-exactly-once-delivery
```

Nếu muốn đặt ack deadline ban đầu tường minh:

```bash
gcloud pubsub subscriptions create orders-exactly-once-sub \
  --topic=orders \
  --enable-exactly-once-delivery \
  --ack-deadline=60
```

Khi exactly-once được bật và không chỉ định ack deadline lúc tạo subscription, giá trị mặc định của subscription là 60 giây. Client high-level có thể tự gia hạn deadline trong lúc xử lý; giá trị subscription là deadline ban đầu.

### 4.2. Kiểm tra cấu hình

```bash
gcloud pubsub subscriptions describe orders-exactly-once-sub
```

Kiểm tra trường `enableExactlyOnceDelivery` là `true`, subscription dùng pull delivery và topic gắn đúng. Chỉ dùng quyền IAM cần thiết để tạo/quản lý subscription; runtime subscriber cần quyền consume subscription.

### 4.3. Cấu hình qua Java SubscriptionAdminClient

Nếu provision tài nguyên bằng Java:

```java
import com.google.cloud.pubsub.v1.SubscriptionAdminClient;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.ProjectTopicName;
import com.google.pubsub.v1.Subscription;
import java.io.IOException;

public Subscription createExactlyOnceSubscription(
        String projectId,
        String topicId,
        String subscriptionId) throws IOException {

    ProjectTopicName topicName =
            ProjectTopicName.of(projectId, topicId);
    ProjectSubscriptionName subscriptionName =
            ProjectSubscriptionName.of(projectId, subscriptionId);

    Subscription subscription = Subscription.newBuilder()
            .setName(subscriptionName.toString())
            .setTopic(topicName.toString())
            .setEnableExactlyOnceDelivery(true)
            .setAckDeadlineSeconds(60)
            .build();

    try (SubscriptionAdminClient adminClient =
                 SubscriptionAdminClient.create()) {
        return adminClient.createSubscription(subscription);
    }
}
```

Ví dụ sử dụng Application Default Credentials của môi trường chạy. Trong production, thường provision subscription bằng Terraform hoặc pipeline hạ tầng để quản lý IAM, retention, retry policy và exactly-once trong cùng một bản cấu hình.

## 5. Nhận ACK response bằng Java Pub/Sub client

### 5.1. Vì sao cần acknowledgment response?

Khi exactly-once được bật, subscriber cần biết ACK request đã được server xử lý thành công hay chưa:

- `SUCCESSFUL`: ACK được xác nhận; cùng message không được redeliver trong phạm vi guarantee.
- `INVALID`: ack ID không hợp lệ hoặc đã hết hạn; không retry ack ID cũ.
- `PERMISSION_DENIED`: principal không có quyền ACK.
- `FAILED_PRECONDITION`: trạng thái subscription hoặc request không đáp ứng điều kiện.
- `OTHER`: lỗi khác; kiểm tra nguyên nhân và chính sách retry của client.

Java client cung cấp:

- `MessageReceiverWithAckResponse`
- `AckReplyConsumerWithResponse`
- `AckResponse`

`AckReplyConsumerWithResponse.ack()` trả `Future<AckResponse>` để ứng dụng đọc kết quả từ Pub/Sub.

API `AckReplyConsumerWithResponse` hiện được Java API reference đánh dấu **Beta/Pre-GA**. Kiểm tra điều khoản hỗ trợ và phiên bản thư viện trước khi dùng làm phụ thuộc bắt buộc cho hệ thống production.

Tài liệu Pub/Sub hiện hành khuyến nghị Java client library phiên bản `1.139.0` trở lên cho hiệu năng và hỗ trợ exactly-once tốt nhất. Với Spring Boot, kiểm tra phiên bản `google-cloud-pubsub` thực tế được BOM resolve; không nâng riêng dependency nếu việc đó làm lệch bộ phiên bản đã được Spring Framework on Google Cloud kiểm thử.

### 5.2. Ví dụ subscriber nhận ACK response

```java
import com.google.cloud.pubsub.v1.AckReplyConsumerWithResponse;
import com.google.cloud.pubsub.v1.AckResponse;
import com.google.cloud.pubsub.v1.MessageReceiverWithAckResponse;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;
import com.google.pubsub.v1.PubsubMessage;
import java.time.Duration;
import java.util.concurrent.Future;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ExactlyOnceSubscriber {
    private final OrderProcessor orderProcessor;
    private final ProcessingRegistry processingRegistry;

    public ExactlyOnceSubscriber(
            OrderProcessor orderProcessor,
            ProcessingRegistry processingRegistry) {
        this.orderProcessor = orderProcessor;
        this.processingRegistry = processingRegistry;
    }

    public Subscriber start(String projectId, String subscriptionId) {
        ProjectSubscriptionName subscriptionName =
                ProjectSubscriptionName.of(projectId, subscriptionId);

        MessageReceiverWithAckResponse receiver =
                (PubsubMessage message,
                 AckReplyConsumerWithResponse ackConsumer) -> {
                    String eventId = message.getAttributesOrDefault(
                            "eventId", "missing-event-id");

                    try {
                        orderProcessor.processIdempotently(message);
                    } catch (Exception processingError) {
                        // Chỉ NACK khi nghiệp vụ thất bại trước khi gửi ACK.
                        try {
                            AckResponse nackResponse = ackConsumer.nack()
                                    .get(15, TimeUnit.SECONDS);
                            processingRegistry.markProcessingFailed(
                                    eventId,
                                    processingError.getClass().getSimpleName()
                                            + ":" + nackResponse.name());
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                            processingRegistry.markProcessingFailed(
                                    eventId, "NACK_UNCERTAIN");
                        } catch (ExecutionException | TimeoutException nackError) {
                            processingRegistry.markProcessingFailed(
                                    eventId, "NACK_UNCERTAIN");
                        }
                        return;
                    }

                    // Chỉ gửi ACK sau khi transaction nghiệp vụ đã commit.
                    Future<AckResponse> ackFuture = ackConsumer.ack();
                    try {
                        AckResponse response =
                                ackFuture.get(15, TimeUnit.SECONDS);
                        if (response == AckResponse.SUCCESSFUL) {
                            processingRegistry.markAckConfirmed(eventId);
                        } else {
                            processingRegistry.markAckUnconfirmed(
                                    eventId, response.name());
                        }
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        processingRegistry.markAckUncertain(eventId);
                    } catch (ExecutionException | TimeoutException ackError) {
                        // ACK có thể đã được server xử lý; không gửi NACK sau ACK.
                        // Nếu message redeliver, inbox/idempotency ngăn side effect lặp.
                        processingRegistry.markAckUncertain(eventId);
                    }
                };

        Subscriber subscriber = Subscriber.newBuilder(
                        subscriptionName, receiver)
                .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
                .setMinDurationPerAckExtensionDuration(
                        Duration.ofSeconds(60))
                .setMaxDurationPerAckExtensionDuration(
                        Duration.ofSeconds(120))
                .setMaxAckExtensionPeriodDuration(
                        Duration.ofMinutes(10))
                .build();

        subscriber.startAsync().awaitRunning();
        return subscriber;
    }
}
```

`OrderProcessor` và `ProcessingRegistry` là service nghiệp vụ cần triển khai. Ví dụ dùng subscriber client trực tiếp để nhận `AckResponse`; nó không phải một callback `PubSubTemplate.subscribe()` thông thường.

`OrderProcessor.processIdempotently()` phải deserialize message, ghi inbox và commit side effect trong một transaction trước khi trả về. `ProcessingRegistry` trong ví dụ chỉ lưu trạng thái vận hành/ACK để quan sát; nó không thay thế inbox transaction. Callback của `Subscriber` có thể chạy đồng thời trên nhiều thread, vì vậy các service và registry phải thread-safe.

Trong code production:

- Không block callback vô hạn; đặt timeout phù hợp cho ACK future.
- Nếu ACK response không rõ, giữ trạng thái xử lý bền vững và dựa vào idempotency khi redelivery.
- Không gửi NACK sau khi đã gửi ACK chỉ vì ACK future timeout; request đầu tiên có thể đã được xử lý thành công.
- Chỉ NACK khi nghiệp vụ thất bại trước bước gửi ACK.
- Dừng `Subscriber` graceful khi Spring context shutdown.

Giữ instance `Subscriber` trong bean/component và gọi `stopAsync()` khi Spring context đóng. Không tạo subscriber mới cho mỗi message hoặc mỗi request HTTP.

### 5.3. Lease extension và ack ID

Java high-level subscriber tự gia hạn ack deadline trong khi callback đang xử lý. Với exactly-once, cần tránh để ack ID hết hạn do mạng hoặc client không kịp gia hạn:

```java
Subscriber subscriber = Subscriber.newBuilder(subscriptionName, receiver)
        .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
        .setMinDurationPerAckExtensionDuration(Duration.ofSeconds(60))
        .setMaxDurationPerAckExtensionDuration(Duration.ofSeconds(120))
        .setMaxAckExtensionPeriodDuration(Duration.ofMinutes(10))
        .build();
```

Các giá trị chỉ là ví dụ. `minDurationPerAckExtension` và `maxDurationPerAckExtension` có giới hạn từ 0 đến 600 giây. Chọn giá trị đủ lớn để tránh hết deadline do biến động mạng, nhưng đừng đặt tùy tiện quá cao vì nếu worker chết, message có thể bị giữ lâu hơn trước khi redelivery.

Khi exactly-once được bật, ACK hoặc `ModifyAckDeadline` dùng ack ID đã hết hạn có thể trả `INVALID_ARGUMENT`. Nếu message đã được giao lại, chỉ ack ID của lần giao mới nhất mới hợp lệ.

## 6. Dùng exactly-once trong ứng dụng Spring Boot

### 6.1. Tạo subscription bằng hạ tầng, xử lý message bằng Spring

Spring Boot starter cung cấp `PubSubTemplate` cho publish, subscribe và pull:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
```

Dùng BOM Spring Framework on Google Cloud tương thích với Spring Boot của dự án. Không tự ghim riêng phiên bản `google-cloud-pubsub` nếu BOM đã quản lý dependency đó.

Subscription exactly-once là cấu hình của tài nguyên Pub/Sub, không phải một annotation trên `@Service`. Tạo subscription bằng Terraform, `gcloud` hoặc `SubscriptionAdminClient`, sau đó Spring consumer kết nối tới subscription đó.

### 6.2. `PubSubTemplate` và acknowledgment future

`PubSubTemplate.subscribe()` đưa message tới callback dưới dạng `BasicAcknowledgeablePubsubMessage`. Các method `ack()` và `nack()` của Spring wrapper trả `CompletableFuture<Void>`. Điều này cho phép ứng dụng theo dõi completion bất đồng bộ, nhưng kiểu trả về không đưa ra enum `AckResponse` như `SUCCESSFUL`, `INVALID` hoặc `PERMISSION_DENIED`.

Nếu ứng dụng cần phân loại chính xác server response của ACK, dùng Java client với `MessageReceiverWithAckResponse` và `AckReplyConsumerWithResponse` như phần trước. Không tự suy luận rằng mọi lời gọi `message.ack()` đã được Pub/Sub xác nhận chỉ vì callback đã chạy tới dòng đó.

Ví dụ Spring handler thông thường:

```java
pubSubTemplate.subscribe("orders-exactly-once-sub", message -> {
    String payload = message.getPubsubMessage()
            .getData()
            .toStringUtf8();

    try {
        orderService.processIdempotently(payload);
        message.ack().whenComplete((unused, error) -> {
            if (error != null) {
                // Ghi nhận ACK failure/uncertain; không lặp side effect.
            }
        });
    } catch (Exception error) {
        message.nack();
    }
});
```

`PubSubTemplate` vẫn hữu ích cho phần lớn tích hợp Spring. Nếu yêu cầu vận hành bắt buộc phải lưu trạng thái `AckResponse.SUCCESSFUL` hoặc phân biệt ack ID hết hạn, dùng subscriber API thấp hơn và kiểm tra tương thích phiên bản thư viện.

### 6.3. Kết nối subscriber tới một region

Nếu dùng Java `Subscriber` trực tiếp, đặt locational endpoint trên builder:

```java
Subscriber subscriber = Subscriber.newBuilder(
                subscriptionName, receiverWithResponse)
        .setEndpoint("asia-southeast1-pubsub.googleapis.com:443")
        .build();
```

Nếu triển khai Spring Boot ở nhiều vùng, bảo đảm mọi instance consume cùng subscription đều dùng endpoint cùng region. Một autoscaling group có instance ở hai region không đáp ứng regional affinity chỉ vì subscription đã bật exactly-once.

### 6.4. Cẩn thận với Spring Integration ack mode

Nếu dùng `PubSubInboundChannelAdapter`, các mode `AUTO`, `AUTO_ACK` và `MANUAL` điều khiển thời điểm Spring Integration gọi ack/nack. Chúng không thay thế việc kiểm tra server ACK response.

Với luồng nghiệp vụ cần kiểm soát chính xác:

- Chọn manual acknowledgment để không ack trước transaction.
- Lấy `BasicAcknowledgeablePubsubMessage` từ `GcpPubSubHeaders.ORIGINAL_MESSAGE`.
- Ghi nhận kết quả nghiệp vụ trước khi ack.
- Theo dõi future ack của Spring; nếu cần `AckResponse` cụ thể, dùng native Java subscriber API.

## 7. Tính lũy đẳng bằng inbox/idempotency table

### 7.1. Dùng event ID nghiệp vụ

Producer nên tạo `eventId` ổn định trước khi publish:

```json
{
  "eventId": "evt-01J9A7K2",
  "eventType": "OrderPaid",
  "orderId": "ord-1001",
  "schemaVersion": 1
}
```

Nếu publisher retry cùng event, phải giữ nguyên `eventId`. Không dùng Pub/Sub `messageId` làm khóa deduplication nghiệp vụ vì hai publish operation của cùng một event logic có thể nhận hai message ID khác nhau.

Khóa idempotency thường gồm `consumerName + eventId`, vì hai consumer khác nhau có thể cần xử lý cùng một event theo hai mục đích riêng.

### 7.2. Tạo bảng inbox

Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    pubsub_message_id VARCHAR(160),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
```

`processed_events` là inbox/deduplication registry. Unique key ngăn cùng một consumer áp dụng cùng event logic nhiều lần, kể cả khi Pub/Sub giao lại message hoặc producer publish trùng.

### 7.3. Ghi inbox và side effect trong cùng transaction

Ví dụ:

```java
@Transactional
public void processIdempotently(OrderPaid event, String pubsubMessageId) {
    int inserted = jdbcTemplate.update("""
            INSERT INTO processed_events(
                consumer_name, event_id, pubsub_message_id
            )
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            "billing-projection",
            event.eventId(),
            pubsubMessageId
    );

    if (inserted == 0) {
        // Event đã được áp dụng; không lặp side effect.
        return;
    }

    orderRepository.markPaid(event.orderId());
    accountRepository.recordPayment(event.orderId(), event.amount());
}
```

Insert inbox và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction database:

- Nếu transaction rollback, cả inbox row và side effect đều rollback; message có thể được retry.
- Nếu transaction commit, event được đánh dấu đã xử lý cùng side effect.
- Nếu ACK sau đó thất bại và message được giao lại, lần xử lý sau thấy inbox row và bỏ qua side effect.

Không insert inbox ở transaction riêng trước side effect. Nếu process crash giữa hai transaction, event có thể bị đánh dấu hoàn tất trong khi nghiệp vụ chưa được cập nhật.

### 7.4. Thứ tự xử lý

Luồng khuyến nghị:

```text
Nhận message
    ↓
Đọc eventId và validate
    ↓
Transaction:
  insert inbox nếu chưa tồn tại
  cập nhật nghiệp vụ
  commit
    ↓
Gửi ACK và đọc kết quả
    ↓
Nếu ACK không rõ: chờ redelivery, inbox ngăn side effect lặp
```

Nếu event đã tồn tại trong inbox, không thực hiện lại cập nhật. Vẫn cần gửi ACK cho lần giao hiện tại để message không tiếp tục retry.

### 7.5. Lưu trạng thái khi xử lý nhiều bước

Với workflow nhiều bước, một cột `processed_at` có thể chưa đủ. Dùng trạng thái rõ ràng như:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `RECEIVED` | Đã ghi nhận event |
| `PROCESSING` | Đang thực hiện workflow |
| `COMPLETED` | Tất cả side effect cần thiết đã hoàn tất |
| `RETRYABLE_FAILED` | Lỗi tạm thời, có thể tiếp tục |
| `PERMANENT_FAILED` | Lỗi cần can thiệp hoặc quarantine |

Nếu workflow kéo dài, không giữ một Pub/Sub message outstanding trong toàn bộ thời gian nhiều phút/giờ. Ghi job bền vững, ack event khởi tạo sau khi lưu job thành công và dùng worker/workflow riêng để tiếp tục.

## 8. Exactly-once với API và dịch vụ bên ngoài

### 8.1. Database transaction không bao phủ HTTP API

Giả sử consumer cần:

1. Cập nhật order trong PostgreSQL.
2. Gọi payment provider để capture tiền.
3. Gửi email xác nhận.
4. ACK Pub/Sub.

Không có transaction ACID duy nhất bao phủ cả PostgreSQL, HTTP payment API, email provider và Pub/Sub. Nếu payment API thành công nhưng response bị timeout, consumer không biết chắc provider đã capture tiền hay chưa. Nếu retry mù quáng, có thể capture hai lần.

Exactly-once delivery không giải quyết được ranh giới transaction này.

### 8.2. Dùng idempotency key ở downstream

Nếu API downstream hỗ trợ idempotency, gửi cùng một key cho mọi lần retry của cùng event:

```http
POST /payments/capture
Idempotency-Key: evt-01J9A7K2
Content-Type: application/json
```

Downstream cần lưu key và kết quả trong cùng transaction với side effect. Khi nhận lại cùng key, nó trả kết quả trước đó thay vì capture thêm lần nữa.

Không tạo key mới mỗi lần retry. Dùng event ID ổn định do producer tạo.

### 8.3. Dùng transactional outbox cho công việc tiếp theo

Nếu consumer cập nhật database và cần phát event tiếp theo, ghi outbox row trong cùng transaction:

```sql
CREATE TABLE outbox_events (
    event_id VARCHAR(160) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);
```

Transaction nghiệp vụ:

```java
@Transactional
public void markOrderPaid(OrderPaid event) {
    orderRepository.markPaid(event.orderId());
    outboxRepository.insert(
            event.eventId(),
            "OrderPaymentRecorded",
            serialize(event)
    );
}
```

Worker outbox publish các row chưa gửi tới Pub/Sub rồi đánh dấu đã gửi. Nếu worker crash sau publish nhưng trước khi cập nhật `published_at`, event có thể được publish lại. Consumer đích vẫn cần inbox/idempotency theo `eventId`.

Outbox giải quyết việc ghi database và ý định publish trong cùng transaction; nó không làm publish một lần tuyệt đối. Kết hợp outbox với idempotent consumer mới tạo được luồng chịu lỗi tốt.

### 8.4. Khi downstream không hỗ trợ idempotency

Nếu API ngoài không có idempotency key, không có cách chung để bảo đảm side effect chỉ xảy ra một lần qua một network timeout không rõ kết quả. Các lựa chọn:

- Tạo lớp adapter nội bộ có request ID và registry deduplication.
- Dùng trạng thái workflow để đối soát kết quả trước khi retry.
- Dùng API truy vấn trạng thái giao dịch trước khi gửi lệnh lần nữa.
- Dùng compensation/reconciliation khi không thể xác định kết quả.
- Chấp nhận at-least-once và thiết kế side effect có thể sửa/đối soát.

Không tuyên bố exactly-once business effect nếu hệ thống đích không thể nhận diện hoặc khử trùng lặp request.

## 9. Failure matrix: message có thể được xử lý lại khi nào?

| Điểm lỗi | Trạng thái nghiệp vụ | Trạng thái ACK | Điều cần làm |
| --- | --- | --- | --- |
| Crash trước transaction | Chưa commit | Chưa ACK | Pub/Sub giao lại; xử lý bình thường |
| Transaction rollback | Chưa commit | Chưa ACK/NACK | Retry theo policy |
| Commit thành công, crash trước ACK | Đã commit | Chưa ACK | Redelivery có thể xảy ra; inbox bỏ qua side effect và ACK |
| ACK request gửi đi nhưng response timeout | Đã commit | Không rõ | Giữ trạng thái; không lặp side effect; nếu redelivery, deduplicate rồi ACK |
| ACK response `SUCCESSFUL` | Đã commit | Đã xác nhận | Pub/Sub không redeliver cùng message trong region |
| ACK response `INVALID` | Có thể đã commit | Ack ID hết hạn/không hợp lệ | Không retry ack ID cũ; xử lý lần giao mới với idempotency |
| Producer publish cùng event hai lần | Cùng event ID, hai publish | Mỗi message có delivery state riêng | Inbox deduplicate theo event ID |
| Consumer chạy ở region khác | Có thể đã commit | Regional guarantee không áp dụng | Dùng một subscriber region hoặc thiết kế deduplication mạnh |
| Seek/replay subscription | Event có thể đã xử lý trước đó | Message được cố ý giao lại | Inbox vẫn cần giữ record trong khoảng replay |

### 9.1. Giữ inbox lâu bao lâu?

Thời gian lưu idempotency record phải dài hơn khoảng thời gian message có thể xuất hiện lại:

- Subscription retention.
- Dead-letter retention và thời gian chờ vận hành.
- Thời gian re-drive thủ công.
- Snapshot/seek replay window.
- Thời gian publisher có thể retry hoặc phát lại event.

Nếu xóa inbox row quá sớm, message được replay sau đó có thể tạo side effect lần nữa. Với event tài chính hoặc trạng thái không thể lặp, cân nhắc giữ khóa nghiệp vụ lâu dài hoặc duy trì ledger theo quy định dữ liệu.

### 9.2. Event ID phải được tạo ở producer

Event ID cần:

- Duy nhất trong phạm vi nghiệp vụ.
- Ổn định qua các lần retry publish cùng một event.
- Không phụ thuộc Pub/Sub message ID.
- Có quy ước theo producer/event type nếu nhiều hệ thống cùng phát event.
- Không chứa thông tin nhạy cảm hoặc dữ liệu cá nhân.

Không tạo UUID mới ở subscriber cho mỗi lần delivery; việc đó phá khả năng deduplicate.

## 10. Ordering kết hợp exactly-once

Pub/Sub hỗ trợ message ordering cùng exactly-once delivery. Tuy nhiên, khi dùng cả hai:

- ACK phải được gửi theo đúng thứ tự message trong cùng ordering key.
- ACK out-of-order có thể bị từ chối bằng lỗi tạm thời.
- Nếu deadline hết trước khi ACK theo thứ tự hợp lệ, message có thể redeliver.
- Throughput theo ordering key bị giới hạn ở mức hàng nghìn message/giây.

Nếu cần ordering, thiết kế callback để không ACK message sau trước message trước cùng key. Không đẩy từng message sang executor không giới hạn rồi ACK theo thứ tự hoàn thành ngẫu nhiên.

Seek/replay là thao tác có chủ đích thay đổi trạng thái acknowledgment. Message được giao lại sau seek vẫn là redelivery hợp lệ, kể cả subscription bật exactly-once. Vì vậy, inbox/idempotency vẫn cần thiết cho luồng replay.

## 11. Metrics, quota và troubleshooting

### 11.1. Metrics quan trọng

| Metric | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `subscription/exactly_once_warning_count` | Số sự kiện có thể dẫn đến redelivery liên quan ACK/ModifyAckDeadline thất bại | Phát hiện ack ID hết hạn, request lỗi hoặc vấn đề persistence phía dịch vụ |
| `subscription/expired_ack_deadlines_count` | Số lần ack deadline hết hạn | Kiểm tra subscriber xử lý chậm hoặc lease extension |
| `service.serviceruntime.googleapis.com/api/request_count` | Request API và response code | Phân tích lỗi ACK/ModifyAckDeadline đến API |
| `subscription/num_unacked_messages_by_region` | Số message chưa ack | Theo dõi backlog |
| `subscription/oldest_unacked_message_age_by_region` | Tuổi message chưa ack lâu nhất | Phát hiện subscriber bị tụt lại |

`exactly_once_warning_count` có thể tăng do lỗi phía client hoặc server và có thể noisy. Một ack ID không hợp lệ bị gửi lặp lại có thể làm metric tăng nhiều lần dù không phải mỗi lần đều tạo một redelivery thực tế.

### 11.2. Quota và latency

Exactly-once subscription có quota bổ sung theo region, bao gồm:

- Số message được consume từ các subscription bật exactly-once.
- Số message được ACK hoặc gia hạn deadline trên các subscription đó.

Exactly-once cũng có publish-to-subscribe latency cao hơn subscription thông thường. Nếu throughput là yêu cầu chính, dùng StreamingPull và đo thực tế trước khi bật trên toàn bộ workload.

### 11.3. Chẩn đoán lỗi ACK

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `INVALID_ARGUMENT` khi ACK | Ack ID đã hết hạn hoặc không phải ID mới nhất | Không retry ID cũ; nhận lần giao mới và dùng ID mới |
| `PERMISSION_DENIED` | Subscriber thiếu `roles/pubsub.subscriber` | Kiểm tra principal và IAM trên subscription |
| `exactly_once_warning_count` tăng | Ack/ModifyAckDeadline request lỗi hoặc ack ID không hợp lệ | Đối chiếu response code, expired deadline và client logs |
| Redelivery sau ACK timeout | Server có thể chưa nhận ACK hoặc response bị mất | Dùng inbox; không lặp side effect |
| Duplicate có message ID khác nhau | Producer phát cùng event nhiều lần | Deduplicate bằng event ID |
| Duplicate xuất hiện khi subscriber ở nhiều region | Regional guarantee không áp dụng | Định tuyến mọi subscriber tới một region |
| Throughput giảm sau bật exactly-once | Latency/quota tăng, ACK ordering hoặc flow control | Dùng StreamingPull, kiểm tra quota và đo ack latency |
| ACK out-of-order với ordering key | Callback hoàn tất không theo thứ tự | Tuần tự hóa xử lý/ACK theo key |

### 11.4. Đừng retry lỗi vĩnh viễn

Java client có thể tự retry một số lỗi tạm thời. Lỗi do ack ID không hợp lệ không thể khắc phục bằng cách gửi lại cùng ID. Cần phân loại lỗi:

- Lỗi tạm thời: để client retry theo chính sách.
- Ack ID hết hạn/invalid: dừng retry ID cũ; chờ redelivery.
- Permission denied: sửa IAM.
- Failed precondition: kiểm tra subscription state và request.
- Timeout không rõ kết quả: lưu trạng thái uncertain và dựa vào idempotency.

## 12. Kiểm thử exactly-once và idempotency

### 12.1. Unit test cho inbox

Kiểm thử business handler và inbox riêng:

1. Event mới được insert vào inbox và cập nhật nghiệp vụ.
2. Cùng `eventId` được xử lý lần thứ hai nhưng không cập nhật nghiệp vụ lần nữa.
3. Lỗi giữa transaction làm cả inbox row và business update rollback.
4. Hai worker đồng thời xử lý cùng event; unique constraint chỉ cho một transaction áp dụng side effect.
5. Event ID khác nhau nhưng payload giống nhau vẫn được xem là hai event khác, trừ khi business contract quy định ngược lại.

Test phải dùng database thật hoặc Testcontainers để xác minh unique constraint và transaction isolation. Mock repository đơn thuần không chứng minh concurrency/deduplication hoạt động đúng.

### 12.2. Integration test bằng Pub/Sub emulator

Emulator hữu ích cho các luồng cơ bản:

- Tạo topic/subscription và publish message.
- Đọc payload, attributes và message ID.
- Ack/nack và kiểm thử callback.
- Kiểm thử inbox/idempotency của ứng dụng.

Không dùng kết quả emulator làm bằng chứng rằng exactly-once server guarantee, regional affinity, quota hoặc ACK response của production đã được xác minh. Các semantics này cần kiểm thử trên Pub/Sub thật trong project sandbox.

### 12.3. Cloud sandbox test

Tạo pull subscription bật exactly-once:

```bash
gcloud pubsub topics create exactly-once-lab

gcloud pubsub subscriptions create exactly-once-lab-sub \
  --topic=exactly-once-lab \
  --enable-exactly-once-delivery \
  --ack-deadline=60
```

Các ca test:

| Ca test | Cách thực hiện | Kết quả cần xác minh |
| --- | --- | --- |
| ACK thành công | Nhận message và chờ `AckResponse.SUCCESSFUL` | Cùng message ID không được redeliver |
| NACK | Nhận message rồi NACK | Message có thể redeliver; message ID giữ nguyên |
| ACK response timeout | Xử lý nghiệp vụ, gửi ACK rồi làm mất/timeout response ở client test | Trạng thái không chắc chắn; inbox ngăn side effect lặp |
| Ack ID cũ | Đợi deadline hết, nhận delivery mới rồi thử ACK bằng ID cũ | Request cũ bị từ chối; dùng ID mới của delivery hiện tại |
| Publish trùng event | Publish hai lần cùng `eventId` nhưng hai publish operation | Có thể nhận hai Pub/Sub message ID; business side effect chỉ một lần |
| Subscriber khác region | Kết nối subscriber tới endpoint khác region | Không dựa vào exactly-once guarantee xuyên vùng |
| Ordering + exactly-once | Gửi nhiều message cùng key, ACK sai thứ tự | Quan sát lỗi ACK tạm thời/redelivery; sửa consumer để ACK tuần tự |
| Seek/replay | Seek subscription về snapshot hoặc timestamp | Message được replay có chủ đích; inbox vẫn chặn side effect lặp |

### 12.4. Kiểm thử quyền và cấu hình

- Subscriber có `roles/pubsub.subscriber` trên subscription.
- Subscription có `enableExactlyOnceDelivery=true`.
- Mọi subscriber dùng cùng locational endpoint.
- Subscription là pull, không phải push/export.
- Client library được quản lý theo BOM tương thích; với Java, dùng phiên bản client library được Google khuyến nghị trong tài liệu hiện hành.
- Theo dõi `exactly_once_warning_count`, `expired_ack_deadlines_count` và response code của ACK/ModifyAckDeadline.

## 13. Bài tập thực hành

Một hệ thống bán hàng nhận event `PaymentCaptured` trên topic `payments`. Consumer `ledger-service` ghi giao dịch vào PostgreSQL và phát event `LedgerEntryCreated` cho dịch vụ báo cáo.

### Yêu cầu

1. Tạo pull subscription `ledger-exactly-once-sub` bật exactly-once delivery.
2. Cấu hình consumer chạy trong một region và dùng locational endpoint phù hợp.
3. Tạo record `PaymentCaptured` với `eventId`, `paymentId`, `orderId`, `amount`, `currency`, `occurredAt`.
4. Viết inbox table có unique key `(consumer_name, event_id)`.
5. Ghi inbox và ledger entry trong cùng database transaction.
6. Dùng Java `MessageReceiverWithAckResponse` để nhận `AckResponse`.
7. Chỉ ghi trạng thái ACK confirmed khi response là `SUCCESSFUL`.
8. Nếu ACK timeout hoặc không rõ kết quả, không lặp ledger entry; chờ redelivery và dựa vào inbox.
9. Ghi outbox event `LedgerEntryCreated` trong cùng transaction với ledger entry.
10. Viết outbox publisher có retry và giữ nguyên event ID.
11. Kiểm thử publish trùng event, ACK timeout, redelivery, ack ID hết hạn và subscriber sai region.
12. Tạo dashboard cho exactly-once warnings, expired deadlines, backlog và xử lý nghiệp vụ.

### Ma trận đánh giá

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Event mới | Một ledger entry và một inbox record |
| Cùng event ID được giao lại | Không tạo ledger entry thứ hai |
| Producer publish cùng event hai lần | Hai message có thể được giao; chỉ một side effect |
| ACK thành công | Server xác nhận, message không redeliver trong region |
| ACK response không rõ | Redelivery có thể xảy ra; inbox ngăn side effect lặp |
| Database transaction rollback | Không có inbox record hoặc ledger entry dở dang |
| Outbox worker publish lại | Consumer báo cáo deduplicate theo event ID |
| Subscriber ở region khác | Không dựa vào guarantee exactly-once |
| Seek replay | Event được xử lý lại ở tầng delivery nhưng không lặp side effect |

### Tiêu chí hoàn thành

- Nêu được phạm vi pull-only và regional của Pub/Sub exactly-once.
- Phân biệt Pub/Sub message ID với event ID nghiệp vụ.
- Đọc và phân loại ACK response.
- Có inbox/idempotency transaction.
- Có outbox cho event phát sinh tiếp theo.
- Có test sandbox cho redelivery, duplicate publish và ack uncertainty.

## 14. So sánh với AWS và Azure

| Khía cạnh | Google Cloud Pub/Sub | AWS | Azure |
| --- | --- | --- | --- |
| Delivery guarantee | Exactly-once delivery cho pull subscription, trong một region | SQS FIFO có deduplication và ordering; Standard là at-least-once | Service Bus có duplicate detection theo MessageId trong cửa sổ cấu hình |
| Xác nhận | ACK response qua pull client | DeleteMessage/visibility timeout; FIFO dedup không thay transaction nghiệp vụ | Complete/Abandon và message lock |
| Dedup business event | Inbox/idempotency theo event ID | Consumer idempotency theo MessageDeduplicationId/business key | Duplicate detection theo MessageId và consumer idempotency |
| Ordering | Ordering key; ACK cần đúng thứ tự khi kết hợp exactly-once | FIFO MessageGroupId | Service Bus SessionId |
| Replay | Snapshot/seek; seek có thể chủ động redeliver | DLQ redrive hoặc event archive | DLQ resubmit hoặc event archive |
| Phạm vi | Subscriber phải cùng region | Theo queue/region và semantics của FIFO | Theo entity/namespace và cấu hình dịch vụ |

Không ánh xạ exactly-once của Pub/Sub thành một thuộc tính chung cho mọi dịch vụ messaging. SQS FIFO deduplication và Service Bus duplicate detection có cửa sổ/phạm vi riêng; chúng không tự tạo transaction exactly-once giữa broker và database của ứng dụng.

## Tổng kết

Google Cloud Pub/Sub exactly-once delivery ngăn redelivery của cùng một Pub/Sub message sau khi ACK được xác nhận thành công, trong phạm vi một region và chỉ với pull/StreamingPull subscription. NACK, ack deadline hết hạn và seek vẫn có thể khiến message được giao lại. Hai publish operation riêng biệt của cùng một event nghiệp vụ cũng có thể tạo các message ID khác nhau; exactly-once không deduplicate chúng.

Vì vậy, consumer Spring Boot vẫn cần event ID ổn định, inbox/idempotency table và transaction bao gồm cả dấu vết xử lý lẫn side effect database. Với API bên ngoài, dùng idempotency key ở hệ thống đích hoặc workflow/outbox có khả năng đối soát. Nếu cần xác nhận server ACK cụ thể, Java `MessageReceiverWithAckResponse` cung cấp `AckResponse`; API `PubSubTemplate` thông thường trả future `Void` và không phơi bày enum này.

Exactly-once là một lớp bảo vệ delivery hữu ích, còn tính lũy đẳng và transaction ở tầng nghiệp vụ mới bảo vệ dữ liệu khi process crash, ACK response không rõ, publisher retry hoặc event được replay.

## Tài liệu tham khảo

- [Google Cloud Pub/Sub — Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery) — phạm vi pull/region, ACK response, ack ID, quota và giới hạn ordering.
- [Google Cloud Pub/Sub — Subscribe with exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/samples/pubsub-subscriber-exactly-once) — ví dụ Java `MessageReceiverWithAckResponse` và `AckReplyConsumerWithResponse`.
- [Java AckReplyConsumerWithResponse API](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.pubsub.v1.AckReplyConsumerWithResponse) — ACK/NACK future và server response.
- [Java MessageReceiverWithAckResponse API](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.pubsub.v1.MessageReceiverWithAckResponse) — callback nhận message với acknowledgment response.
- [Java Subscriber.Builder API](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.pubsub.v1.Subscriber.Builder) — endpoint, lease extension và subscriber settings.
- [Spring Framework on Google Cloud — Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html) — `PubSubTemplate`, acknowledgment future và subscriber integration.
- [Google Cloud Pub/Sub — Pull subscriptions](https://docs.cloud.google.com/pubsub/docs/pull) — Pull/StreamingPull và high-level client.
- [Google Cloud Pub/Sub — Troubleshoot pull subscriptions](https://docs.cloud.google.com/pubsub/docs/pull-troubleshooting) — redelivery, duplicate publish, seek và ordering.
