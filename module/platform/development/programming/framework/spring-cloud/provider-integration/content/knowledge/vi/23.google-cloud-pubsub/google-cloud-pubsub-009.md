# Tích hợp Spring Integration và Spring Cloud Stream theo nhu cầu

## Mục tiêu bài học

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud tương ứng. Khi dùng Google Cloud Pub/Sub, ứng dụng Spring có thể tích hợp ở nhiều mức abstraction: gọi `PubSubTemplate` trực tiếp, kết nối Spring Integration `MessageChannel` bằng channel adapter, hoặc dùng Spring Cloud Stream binder để viết producer/consumer theo mô hình hàm.

Bài học này giúp bạn chọn đúng cách tích hợp theo độ phức tạp của luồng message và mức kiểm soát cần thiết:

- **Spring Integration:** xây dựng luồng xử lý bằng channel, endpoint, router, transformer và error channel; điều khiển ACK/NACK theo message.
- **Spring Cloud Stream:** khai báo `Supplier`, `Function`, `Consumer` và binding tới destination; phù hợp microservice event-driven muốn giảm cấu hình broker-specific.
- **Pub/Sub template/client:** dùng khi cần API đặc thù, thao tác trực tiếp với topic/subscription hoặc kiểm soát hành vi không được abstraction hỗ trợ.

Sau bài học, bạn có thể:

1. Thêm đúng dependency và BOM cho Spring Integration hoặc Stream binder.
2. Tạo inbound/outbound channel adapter cho Pub/Sub.
3. Phân biệt streaming pull với synchronous pollable message source.
4. Chọn `AckMode.AUTO`, `AUTO_ACK` hoặc `MANUAL` và xử lý error channel đúng cách.
5. Mapping/filter header, ordering key và publish callback.
6. Viết functional `Consumer`/`Function` và cấu hình Stream binding, destination, group.
7. Quản lý topic/subscription tự động hoặc provision bằng hạ tầng.
8. Hiểu giới hạn partitioning và exactly-once của binder.
9. Kiểm thử và vận hành luồng message với retry, DLQ, metrics và graceful shutdown.

## 1. Chọn abstraction phù hợp

### 1.1. Ba cách tích hợp chính

Spring Framework on Google Cloud cung cấp ba hướng sử dụng Pub/Sub trong ứng dụng Spring:

| Hướng tích hợp | Thành phần chính | Điểm mạnh | Khi nên chọn |
| --- | --- | --- | --- |
| Pub/Sub template/client | `PubSubTemplate`, Java Pub/Sub client | Kiểm soát trực tiếp publish, pull, ack/nack và quản lý tài nguyên | Cần API đặc thù, logic ACK chi tiết, provisioning hoặc thao tác cấp thấp |
| Spring Integration | `PubSubInboundChannelAdapter`, `PubSubMessageSource`, `PubSubMessageHandler` | Kết nối Pub/Sub với `MessageChannel` và Enterprise Integration Patterns | Luồng có router, filter, transformer, aggregator, error channel hoặc nhiều bước tích hợp |
| Spring Cloud Stream binder | `spring-cloud-gcp-pubsub-stream-binder` | Functional programming model, binding và consumer group | Microservice producer/consumer muốn tập trung vào event contract và destination |

Các module có thể kết hợp trong cùng hệ thống, nhưng nên chọn một abstraction làm đường nhận message chính cho mỗi subscription. Không tạo hai consumer độc lập cùng đọc một subscription chỉ vì ứng dụng đã có cả Integration adapter và Stream binder.

### 1.2. Phân biệt channel adapter và binder

Spring Integration channel adapter nối một `MessageChannel` của ứng dụng với một topic hoặc subscription Pub/Sub. Ứng dụng khai báo channel và adapter, sau đó nối các endpoint như `@ServiceActivator`, `@Transformer`, `@Filter` hoặc router.

Spring Cloud Stream binder tạo binding giữa hàm ứng dụng và destination. Ví dụ, một bean `Consumer<OrderCreated>` được nối với subscription thông qua input binding; một bean `Function<OrderCreated, OrderAccepted>` có cả input và output binding.

Binder Pub/Sub được xây dựng dựa trên chính Spring Integration channel adapters. Vì vậy, nó kế thừa nhiều semantics của adapter như ACK mode, nhưng cung cấp cấu hình cấp cao hơn qua binding properties.

### 1.3. Những khác biệt cần biết trước khi chọn

| Nhu cầu | Spring Integration | Spring Cloud Stream binder |
| --- | --- | --- |
| Nhiều bước xử lý và routing | Mạnh, khai báo channel/endpoint | Có thể ghép function, nhưng ít linh hoạt hơn với flow phức tạp |
| Kiểm soát message gốc và ACK | Có `GcpPubSubHeaders.ORIGINAL_MESSAGE` và `AckMode` | Có ACK mode binder; kiểm tra header/API theo phiên bản binder |
| Producer publish callback | `PubSubMessageHandler` có success/failure callback | Producer mặc định async; có property bật sync send |
| Consumer group | Do subscription Pub/Sub quyết định | Khai báo qua `spring.cloud.stream.bindings.*.group` |
| Auto-create topic/subscription | Có thể provision riêng bằng `PubSubAdmin`/IaC | Binder hỗ trợ auto-create resource, mặc định bật |
| Partitioning của Stream | Không phải abstraction partition của binder | Pub/Sub binder hiện không hỗ trợ Spring Cloud Stream partitioning |
| Exactly-once ACK response | Streaming adapter chỉ cung cấp object ack/nack cơ bản | Spring Cloud GCP không expose `AckReplyConsumerWithResponse` cần cho exactly-once ACK response |

Không chọn Stream binder chỉ vì muốn dùng functional bean. Nếu yêu cầu exactly-once delivery cần đọc `AckResponse` từ Java client, dùng Java Pub/Sub API trực tiếp; tài liệu Google nêu Spring Cloud GCP không cung cấp `AckReplyConsumerWithResponse`.

## 2. Dependency và cấu hình nền

### 2.1. Spring Integration channel adapters

Với Maven, dùng Spring Framework on Google Cloud BOM để đồng bộ phiên bản starter và thư viện Pub/Sub:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
</dependencies>
```

Thay `${spring-cloud-gcp.version}` bằng phiên bản BOM tương thích với Spring Boot/Spring Framework của ứng dụng. Không tự ghim phiên bản `spring-integration-core` hoặc `google-cloud-pubsub` lệch khỏi BOM nếu không có lý do tương thích rõ ràng.

Gradle:

```kotlin
dependencies {
    implementation(platform("com.google.cloud:spring-cloud-gcp-dependencies:$springCloudGcpVersion"))
    implementation("com.google.cloud:spring-cloud-gcp-starter-pubsub")
    implementation("org.springframework.integration:spring-integration-core")
}
```

### 2.2. Spring Cloud Stream Pub/Sub binder

Nếu ứng dụng dùng functional binding, thêm binder:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-pubsub-stream-binder</artifactId>
</dependency>
```

Gradle:

```kotlin
dependencies {
    implementation("com.google.cloud:spring-cloud-gcp-pubsub-stream-binder")
}
```

Binder dùng Spring Integration adapters ở bên dưới. Dùng BOM Spring Framework on Google Cloud để quản lý phiên bản binder và starter; đồng thời đảm bảo phiên bản Spring Cloud Stream tương thích với phiên bản BOM đang chọn.

### 2.3. Cấu hình project và credentials

Ví dụ cấu hình chung:

```yaml
spring:
  cloud:
    gcp:
      project-id: acme-commerce-dev
```

Ở local, có thể dùng Application Default Credentials từ `gcloud auth application-default login`. Trên môi trường Google Cloud, ưu tiên service account gắn với workload hoặc Workload Identity. Runtime principal cần quyền Pub/Sub đúng phạm vi: publish topic, consume subscription hoặc quản lý tài nguyên tùy vai trò.

Không đưa service account key JSON vào source control hoặc `application.yml`. Nếu ứng dụng không tự tạo topic/subscription, không cấp quyền quản trị Pub/Sub cho runtime chỉ để chạy adapter.

## 3. Spring Integration inbound: Streaming Pull

### 3.1. `PubSubInboundChannelAdapter`

`PubSubInboundChannelAdapter` dùng Streaming Pull để nhận message liên tục từ subscription, chuyển message Pub/Sub thành Spring `Message` rồi gửi tới channel được cấu hình. Mặc định payload là `byte[]`; có thể đặt `payloadType` để converter trong `PubSubTemplate` chuyển sang DTO hoặc `String`.

Ví dụ khai báo channel và inbound adapter:

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import com.google.cloud.spring.pubsub.integration.AckMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class PubSubInboundConfiguration {

    @Bean
    public MessageChannel ordersInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public PubSubInboundChannelAdapter ordersInboundAdapter(
            MessageChannel ordersInputChannel,
            PubSubTemplate pubSubTemplate) {

        PubSubInboundChannelAdapter adapter =
                new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
        adapter.setOutputChannel(ordersInputChannel);
        adapter.setPayloadType(String.class);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }
}
```

`DirectChannel` chuyển message tới một subscriber handler theo cơ chế point-to-point. Dùng `PublishSubscribeChannel` khi chủ đích broadcast một message tới nhiều handler trong cùng application; phải cân nhắc rõ ACK semantics nếu một handler thành công còn handler khác thất bại.

### 3.2. Xử lý message và ACK thủ công

Ở chế độ `MANUAL`, adapter không tự ACK/NACK. Nó gắn `BasicAcknowledgeablePubsubMessage` vào header `GcpPubSubHeaders.ORIGINAL_MESSAGE`:

```java
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import java.util.concurrent.CompletableFuture;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderMessageHandler {
    private final OrderService orderService;

    public OrderMessageHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "ordersInputChannel")
    public void handle(Message<String> message) {
        BasicAcknowledgeablePubsubMessage original =
                message.getHeaders().get(
                        GcpPubSubHeaders.ORIGINAL_MESSAGE,
                        BasicAcknowledgeablePubsubMessage.class);

        try {
            orderService.processAndCommit(message.getPayload());
            CompletableFuture<Void> ackResult = original.ack();
            ackResult.whenComplete((unused, error) -> {
                if (error != null) {
                    // Ghi nhận ACK failure; message có thể được giao lại.
                }
            });
        } catch (Exception processingError) {
            original.nack();
        }
    }
}
```

`processAndCommit()` phải hoàn tất transaction database trước khi gọi `ack()`. `ack()`/`nack()` trả future; nếu ACK request thất bại hoặc response không rõ, message có thể được giao lại. Consumer cần idempotent theo event ID nghiệp vụ.

### 3.3. Ba acknowledgment mode

Inbound adapter hỗ trợ ba mode:

| Mode | Flow thành công | Flow lỗi không có error handler | Error handler hoàn tất bình thường |
| --- | --- | --- | --- |
| `AUTO` (mặc định) | ACK | NACK, redelivery ngay | ACK |
| `AUTO_ACK` | ACK | Không ACK/NACK; đợi deadline/lease | ACK |
| `MANUAL` | Không tự động hành động | Không tự động hành động | Không tự động hành động |

Điểm dễ nhầm: với `AUTO` và `AUTO_ACK`, adapter xem flow đã hoàn tất thành công nếu error handler bắt exception rồi return bình thường. Vì vậy, một message lỗi có thể bị ACK sau khi error handler chỉ ghi log. Nếu muốn hành vi mặc định khi lỗi (NACK ở `AUTO`, không hành động ở `AUTO_ACK`), error handler phải ném exception trở lại adapter.

Chọn mode theo yêu cầu:

- `AUTO`: đơn giản khi exception được propagate đúng và ACK sau khi toàn bộ flow thành công.
- `AUTO_ACK`: phù hợp khi cố ý muốn để message chưa ACK khi handler thất bại; phải hiểu message sẽ chờ deadline/lease thay vì NACK ngay.
- `MANUAL`: dùng khi cần quyết định ACK/NACK sau transaction, quarantine hoặc handoff bền vững.

### 3.4. Error channel

Có thể gắn error channel cho adapter:

```java
@Bean
public PubSubInboundChannelAdapter ordersInboundAdapter(
        MessageChannel ordersInputChannel,
        PubSubTemplate pubSubTemplate) {
    PubSubInboundChannelAdapter adapter =
            new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
    adapter.setOutputChannel(ordersInputChannel);
    adapter.setAckMode(AckMode.AUTO);
    adapter.setErrorChannelName("ordersErrors");
    return adapter;
}
```

Error handler có thể lấy message gốc từ failed message:

```java
@ServiceActivator(inputChannel = "ordersErrors")
public void handleError(Message<MessagingException> errorMessage) {
    Message<?> failedMessage = errorMessage.getPayload().getFailedMessage();
    BasicAcknowledgeablePubsubMessage original =
            failedMessage.getHeaders().get(
                    GcpPubSubHeaders.ORIGINAL_MESSAGE,
                    BasicAcknowledgeablePubsubMessage.class);

    // Chỉ ACK nếu đã lưu quarantine bền vững.
    // Nếu muốn AUTO mode NACK theo exception, ném lỗi trở lại adapter.
    original.nack();
}
```

Ví dụ này chọn NACK thủ công. Nếu error handler hoàn tất bình thường, adapter không còn coi flow là lỗi để áp dụng hành vi mặc định. Tránh vừa ACK/NACK thủ công vừa dựa vào auto mode cho cùng một message.

## 4. Spring Integration outbound: Publish lên topic

### 4.1. `PubSubMessageHandler`

Outbound channel adapter dùng `PubSubMessageHandler`. Nó nhận Spring `Message` từ channel, chuyển payload thành bytes bằng `PubSubMessageConverter` trong `PubSubTemplate` rồi publish tới topic:

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class PubSubOutboundConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "ordersOutputChannel")
    public MessageHandler ordersPublisher(PubSubTemplate pubSubTemplate) {
        PubSubMessageHandler handler =
                new PubSubMessageHandler(pubSubTemplate, "orders-events");

        handler.setSuccessCallback((messageId, originalMessage) -> {
            // Ghi metric publish success và messageId.
        });
        handler.setFailureCallback((cause, originalMessage) -> {
            // Ghi metric publish failure và correlation ID.
        });
        return handler;
    }
}
```

`PubSubMessageHandler` publish bất đồng bộ mặc định. Success callback nhận message ID do Pub/Sub cấp; failure callback nhận nguyên nhân lỗi và message gốc. Không coi việc gửi message vào channel là bằng chứng message đã được publish thành công.

### 4.2. Gửi message qua channel hoặc Messaging Gateway

Một `MessageChannel` có thể được inject vào service để gửi message:

```java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final MessageChannel ordersOutputChannel;

    public OrderEventPublisher(MessageChannel ordersOutputChannel) {
        this.ordersOutputChannel = ordersOutputChannel;
    }

    public void publish(OrderCreated event) {
        ordersOutputChannel.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventType", "OrderCreated")
                        .setHeader("eventId", event.eventId())
                        .build()
        );
    }
}
```

`send()` ở đây gửi tới channel nội bộ. Publish thực tế xảy ra trong `PubSubMessageHandler`; theo dõi success/failure callback để quan sát kết quả broker. Nếu nghiệp vụ cần retry publish bền vững sau khi process crash, dùng transactional outbox thay vì chỉ giữ message trong bộ nhớ.

### 4.3. Chọn topic bằng header hoặc SpEL

Mặc định handler publish tới topic khai báo trong constructor. Có thể override bằng `GcpPubSubHeaders.TOPIC`:

```java
Message<?> message = MessageBuilder.withPayload(event)
        .setHeader(GcpPubSubHeaders.TOPIC, "priority-orders")
        .build();
ordersOutputChannel.send(message);
```

Hoặc đặt topic expression:

```java
PubSubMessageHandler handler =
        new PubSubMessageHandler(pubSubTemplate, "default-orders");
handler.setTopicExpressionString("headers['targetTopic']");
```

Nếu destination được chọn từ header, validate giá trị trước khi gửi. Không để message không tin cậy tự do chọn topic vì có thể làm ứng dụng publish sang tài nguyên ngoài phạm vi mong muốn.

### 4.4. Synchronous publish khi cần truyền lỗi về caller

Outbound handler publish bất đồng bộ mặc định. Nếu muốn thao tác gửi chờ kết quả hoặc cấu hình timeout, dùng API của `PubSubMessageHandler` tương ứng với phiên bản thư viện. Không block thread HTTP chính mà không có timeout; với luồng nghiệp vụ cần độ tin cậy, outbox thường phù hợp hơn việc giữ request thread chờ Pub/Sub.

## 5. Pollable source: Synchronous Pull

### 5.1. Khi nào dùng `PubSubMessageSource`?

`PubSubInboundChannelAdapter` dùng Streaming Pull và thường cho throughput tốt với workload liên tục. Tuy nhiên, client có thể cache nhiều message; khi publish một batch lớn gồm message nhỏ nhưng mỗi message xử lý lâu, một subscriber có thể giữ phần lớn message trong cache dù còn subscriber khác rảnh.

`PubSubMessageSource` dùng synchronous pull và Spring Integration poller. Nó có thể giúp phân phối công việc đều hơn trong tình huống cache imbalance. Đây không phải lựa chọn nhanh hơn cho mọi workload: synchronous pull phù hợp khi cần kiểm soát nhịp poll hoặc phân phối batch; Streaming Pull phù hợp luồng message liên tục, throughput cao.

### 5.2. Cấu hình pollable source

```java
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubMessageSource;
import com.google.cloud.spring.pubsub.support.AcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.core.MessageSource;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.Header;

@Configuration
public class PubSubPollingConfiguration {

    @Bean
    @InboundChannelAdapter(
            channel = "ordersInputChannel",
            poller = @Poller(fixedDelay = "250"))
    public MessageSource<Object> ordersMessageSource(PubSubTemplate pubSubTemplate) {
        PubSubMessageSource source =
                new PubSubMessageSource(pubSubTemplate, "orders-sub");
        source.setAckMode(AckMode.MANUAL);
        source.setPayloadType(String.class);
        source.setBlockOnPull(true);
        source.setMaxFetchSize(50);
        return source;
    }
}
```

Các điểm cần chú ý:

- Mặc định synchronous pull trả về ngay nếu chưa có message; `setBlockOnPull(true)` yêu cầu chờ ít nhất một message.
- Mặc định mỗi lần pull lấy một message; `setMaxFetchSize()` đặt số message tối đa cho một lần poll.
- `setAckMode(MANUAL)` chuyển quyền ACK/NACK cho handler downstream.
- Poller delay và fetch size cần dựa trên latency mục tiêu, throughput và năng lực xử lý.

### 5.3. ACK message lấy từ pollable source

Với synchronous pull, header `GcpPubSubHeaders.ORIGINAL_MESSAGE` chứa `AcknowledgeablePubsubMessage`, có thể cung cấp ack ID và subscription name:

```java
@ServiceActivator(inputChannel = "ordersInputChannel")
public void handlePolledOrder(
        Message<String> message,
        @Header(GcpPubSubHeaders.ORIGINAL_MESSAGE)
        AcknowledgeablePubsubMessage original) {

    try {
        orderService.processAndCommit(message.getPayload());
        original.ack();
    } catch (Exception error) {
        original.nack();
    }
}
```

Streaming Pull adapter trả `BasicAcknowledgeablePubsubMessage`, có thể ACK/NACK message nhưng không expose ack ID để lưu lại xử lý về sau. Synchronous pull source dùng `AcknowledgeablePubsubMessage` có ack ID. Không lưu ack ID rồi sử dụng sau khi message đã hết deadline hoặc đã được giao lại; ack ID của lần giao cũ có thể không còn hợp lệ.

## 6. Header mapping, converter và ordering key

### 6.1. Header từ Pub/Sub vào Spring Message

Inbound adapter mặc định map attributes của Pub/Sub message thành Spring headers. Payload được chuyển đổi bởi `PubSubMessageConverter` trong `PubSubTemplate`; mặc định payload adapter là `byte[]`, có thể đổi sang `String` hoặc DTO bằng `setPayloadType()`.

Các header hệ thống như `GcpPubSubHeaders.ORIGINAL_MESSAGE` được adapter gắn để handler có thể ACK/NACK. Không xóa header này khi flow cần manual acknowledgment.

### 6.2. Header từ Spring Message ra Pub/Sub

Outbound adapter map các header Spring thành Pub/Sub attributes dạng chuỗi, ngoại trừ một số header nội bộ như `id`, `timestamp`, acknowledgement header và ordering key. Vì giá trị attributes của Pub/Sub là string, hãy serialize rõ các kiểu dữ liệu phức tạp thay vì giả định object header được giữ nguyên kiểu.

### 6.3. Ordering key

`GcpPubSubHeaders.ORDERING_KEY` được map tự động thành `PubsubMessage.orderingKey` và không được gửi như attribute thông thường:

```java
Message<OrderCreated> message = MessageBuilder.withPayload(event)
        .setHeader(GcpPubSubHeaders.ORDERING_KEY, event.orderId())
        .setHeader("eventId", event.eventId())
        .build();
ordersOutputChannel.send(message);
```

Khi publish message có ordering key, bật ordering trong cấu hình publisher:

```yaml
spring:
  cloud:
    gcp:
      pubsub:
        publisher:
          enable-message-ordering: true
```

Ordering key cần ổn định và có cardinality phù hợp. Nếu nhiều message cùng key phải được xử lý tuần tự, handler downstream cũng phải giữ thứ tự; chỉ đặt header không tự tuần tự hóa các side effect database.

### 6.4. Lọc header bằng `PubSubHeaderMapper`

Có thể tùy chỉnh các header được map:

```java
PubSubHeaderMapper mapper = new PubSubHeaderMapper();
mapper.setOutboundHeaderPatterns("!authorization", "!internal_*", "*");
ordersPublisher.setHeaderMapper(mapper);
```

Pattern được xét theo thứ tự khai báo; pattern đầu tiên có độ ưu tiên. Ví dụ loại `authorization` và các header `internal_*`, sau đó cho phép các header còn lại. Không publish access token, session ID hoặc dữ liệu bí mật trong Pub/Sub attributes.

### 6.5. Không nhầm header mapping với payload conversion

Header mapper xử lý metadata; message converter xử lý payload bytes và kiểu dữ liệu. Nếu DTO không deserialize được, kiểm tra `PubSubMessageConverter`, `payloadType`, content type và schema version. Nếu header bị mất, kiểm tra `PubSubHeaderMapper` hoặc `allowedHeaders` của Stream binder.

## 7. Spring Cloud Stream Pub/Sub binder

### 7.1. Functional programming model

Spring Cloud Stream từ phiên bản 3 hỗ trợ functional model với các bean `Supplier`, `Function` và `Consumer`:

- `Supplier<T>` phát message ra output binding.
- `Consumer<T>` nhận message từ input binding.
- `Function<T, R>` nhận input và phát kết quả ra output binding.

Ví dụ consumer:

```java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    @Bean
    public Consumer<OrderCreated> processOrder(OrderService orderService) {
        return orderService::processIdempotently;
    }
}
```

Với một bean `Consumer<OrderCreated>` tên `processOrder`, binding input mặc định là `processOrder-in-0`.

Ví dụ processor:

```java
@Bean
public Function<OrderCreated, OrderAccepted> acceptOrder(OrderService orderService) {
    return orderService::accept;
}
```

Function có input binding `acceptOrder-in-0` và output binding `acceptOrder-out-0`.

### 7.2. Cấu hình destination và consumer group

Ví dụ `application.yml` cho consumer:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-worker
          content-type: application/json
      gcp:
        pubsub:
          bindings:
            processOrder-in-0:
              consumer:
                auto-create-resources: false
                ack-mode: AUTO
                subscription-name: orders-sub
```

Ý nghĩa:

- `destination: orders` là Pub/Sub topic.
- `group: order-worker` tạo consumer group ổn định; binder ánh xạ thành subscription gắn với topic và group.
- `content-type: application/json` yêu cầu Stream content type conversion phù hợp với DTO.
- `auto-create-resources: false` yêu cầu topic/subscription đã được provision trước bằng IaC hoặc công cụ quản trị.
- `ack-mode: AUTO` ACK khi flow thành công và NACK khi lỗi được propagate đúng về adapter.

Tên binding mặc định theo convention `<functionName>-in-<index>` hoặc `<functionName>-out-<index>`. Nếu function có nhiều input/output, index phân biệt từng cổng.

### 7.3. Producer và Function output

Với Function có input và output:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          group: order-worker
          content-type: application/json
        acceptOrder-out-0:
          destination: accepted-orders
          content-type: application/json
      gcp:
        pubsub:
          bindings:
            acceptOrder-in-0:
              consumer:
                auto-create-resources: false
                ack-mode: AUTO
                subscription-name: orders-sub
            acceptOrder-out-0:
              producer:
                auto-create-resources: false
                sync: false
```

Producer của binder publish bất đồng bộ mặc định. Đặt `sync: true` khi cần propagate lỗi publish về caller theo semantics của binder; vẫn cần timeout và retry policy phù hợp.

### 7.4. Consumer group quyết định subscription

Với Pub/Sub, mỗi subscription nhận bản copy độc lập của message. Spring Cloud Stream group ánh xạ tới subscription:

| Cấu hình | Hành vi |
| --- | --- |
| Cùng `destination`, cùng `group` trên nhiều instance | Các instance cùng consume một subscription; Pub/Sub phân phối message giữa chúng |
| Cùng `destination`, group khác nhau | Mỗi group có subscription riêng và nhận bản copy của message |
| Không khai báo `group` | Binder tạo anonymous subscription; subscription này được dọn khi binder shutdown |

Với workload production, luôn khai báo group có tên ổn định để subscription bền vững qua restart và scale. Không dùng anonymous subscription nếu cần giữ backlog khi toàn bộ instance dừng.

### 7.5. Auto-create resource

Pub/Sub binder hỗ trợ tự tạo topic/subscription nếu chưa tồn tại; `auto-create-resources` mặc định bật. Khi bật, destination trở thành tên topic. Với consumer có group, subscription thường được đặt theo dạng `<topic>.<group>` nếu không chỉ định subscription riêng.

Trong môi trường production, thường nên provision topic/subscription bằng Terraform hoặc pipeline hạ tầng, sau đó đặt `auto-create-resources: false`. Cách này giúp review IAM, retention, retry policy, DLQ, ordering và exactly-once trước khi deploy ứng dụng.

Nếu để binder tự tạo resource, cần đảm bảo runtime principal có quyền tạo topic/subscription. Không cấp quyền quản trị rộng chỉ để ứng dụng khởi động; có thể tạo sẵn tài nguyên bằng deployment pipeline.

### 7.6. ACK mode của binder

Binder cung cấp ba mode giống inbound channel adapter:

| Mode | Hành vi |
| --- | --- |
| `AUTO` (mặc định) | ACK khi xử lý thành công; NACK khi exception được propagate |
| `AUTO_ACK` | ACK khi thành công; khi lỗi không NACK ngay, để deadline/redelivery xử lý |
| `MANUAL` | Ứng dụng chịu trách nhiệm ACK/NACK |

Với `MANUAL`, ứng dụng cần giữ message headers và lấy original message handle theo API của phiên bản binder. Nếu function chỉ nhận DTO trần (`Consumer<OrderCreated>`), code nghiệp vụ không có `Message<?>` để đọc header. Khi cần ACK thủ công, dùng function nhận `Message<OrderCreated>` và xác minh header `GcpPubSubHeaders.ORIGINAL_MESSAGE` được binder chuyển tới consumer trong phiên bản đang dùng. Nếu yêu cầu ACK response cụ thể hoặc exactly-once delivery, binder không expose `AckReplyConsumerWithResponse`; dùng Java Pub/Sub client trực tiếp.

### 7.7. Header allowlist

Binder có property `allowedHeaders` cho producer và consumer. Chỉ các header trong danh sách được chuyển qua binder:

```yaml
spring:
  cloud:
    gcp:
      pubsub:
        bindings:
          processOrder-in-0:
            consumer:
              allowed-headers: eventId,eventType,schemaVersion
          acceptOrder-out-0:
            producer:
              allowed-headers: eventId,eventType,schemaVersion
```

Header allowlist hữu ích để giữ contract rõ ràng và tránh vô tình phát metadata nội bộ. Không đưa authorization token, cookie hoặc thông tin nhạy cảm vào message headers.

### 7.8. Giới hạn partitioning

Spring Cloud Stream Pub/Sub binder hiện không hỗ trợ Spring Cloud Stream partitioning. Pub/Sub có ordering key ở tầng broker, nhưng ordering key không đồng nghĩa với Stream binder partitioning; chúng có semantics và cấu hình riêng.

Nếu cần partitioned processing theo key ở mức Stream, cần đánh giá binder khác có hỗ trợ partitioning hoặc tự thiết kế routing bằng ordering key/consumer logic trên Pub/Sub. Không bật `partitioned: true` rồi giả định Pub/Sub binder sẽ tạo partition routing như Kafka.

## 8. Retry, error handling và dead-letter flow

### 8.1. Phân biệt retry của framework và retry của Pub/Sub

Có hai tầng retry độc lập:

| Tầng | Cơ chế | Mục tiêu |
| --- | --- | --- |
| Spring Integration/Stream | Retry handler, error channel, `maxAttempts`, backoff của consumer | Thử lại xử lý trong process trước khi kết luận handler thất bại |
| Pub/Sub subscription | NACK hoặc ack deadline hết, retry policy, dead-letter topic | Giao lại message từ broker khi subscriber không ACK |

Ví dụ, Spring Cloud Stream có thể thử gọi function vài lần trong cùng một delivery. Nếu vẫn thất bại và exception được propagate tới inbound adapter ở `AUTO`, adapter NACK message; Pub/Sub tiếp tục redelivery theo subscription retry policy. Một message vì vậy có thể được xử lý nhiều lần trong cùng delivery và nhiều delivery khác nhau.

Không cấu hình retry vô hạn ở cả hai tầng. Đặt số lần retry trong process có giới hạn, rồi dùng Pub/Sub retry/backoff và DLQ để cô lập message lỗi kéo dài.

### 8.2. Error channel của Spring Integration

Error channel cho phép ghi log, phân loại lỗi hoặc lưu quarantine. Nhưng cần hiểu ACK semantics:

- Với `AckMode.AUTO`, exception đi tới adapter sẽ NACK; nếu error handler bắt lỗi rồi return bình thường, adapter có thể ACK.
- Với `AckMode.AUTO_ACK`, exception không tự NACK; nếu error handler hoàn tất bình thường, adapter có thể ACK.
- Với `AckMode.MANUAL`, error handler phải quyết định ACK/NACK rõ ràng.

Nếu lưu quarantine thành công rồi muốn kết thúc message, ACK sau khi ghi bền vững. Nếu muốn Pub/Sub retry hoặc chuyển DLQ, NACK hoặc propagate exception theo mode đã chọn. Không chỉ log exception rồi return nếu message vẫn cần xử lý lại.

### 8.3. Cấu hình DLQ ở subscription

Dead-letter topic là thuộc tính của subscription Pub/Sub. Có thể provision ngoài ứng dụng bằng Terraform hoặc `gcloud`:

```bash
gcloud pubsub subscriptions update orders-sub \
  --dead-letter-topic=orders-dlq \
  --max-delivery-attempts=8 \
  --min-retry-delay=10s \
  --max-retry-delay=300s
```

Pub/Sub service agent cần `roles/pubsub.publisher` trên DLQ topic và `roles/pubsub.subscriber` trên subscription nguồn. Tạo thêm subscription riêng trên DLQ topic để đọc và điều tra message lỗi. Không dựa vào một error channel trong JVM làm DLQ bền vững nếu process có thể restart hoặc mất dữ liệu.

### 8.4. Chống duplicate và idempotency

Spring Integration và Stream binder không thay đổi at-least-once delivery của Pub/Sub. Consumer nên dùng event ID ổn định và transaction inbox để bảo vệ side effect:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong cùng transaction, insert event ID và cập nhật nghiệp vụ. Nếu insert xung đột, event đã được xử lý; bỏ qua side effect và ACK delivery hiện tại. Đừng dùng Pub/Sub message ID thay cho event ID nghiệp vụ vì hai lần publish cùng event có thể tạo message ID khác nhau.

## 9. Quản lý tài nguyên, health và lifecycle

### 9.1. Provision topic/subscription

Có hai lựa chọn:

| Cách | Ưu điểm | Lưu ý |
| --- | --- | --- |
| Binder auto-create | Khởi động nhanh ở local/dev, giảm cấu hình ban đầu | Runtime cần quyền tạo resource; subscription có thể được tạo theo group/anonymous convention |
| IaC/`PubSubAdmin` | Review được IAM, retention, retry, DLQ, ordering và exactly-once | Cần pipeline tạo tài nguyên trước khi deploy consumer |

Với production, provision bằng IaC thường dễ kiểm soát hơn. Ứng dụng chỉ nhận quyền publish/subscribe đúng tài nguyên. Nếu dùng `PubSubAdmin` trong ứng dụng, xử lý `ALREADY_EXISTS` và không chạy nhiều instance đồng thời với quyền quản trị rộng.

### 9.2. Health indicator cho subscriber

Spring Framework on Google Cloud có health indicator `pubsub-subscriber`. Với `PubSubInboundChannelAdapter`, có thể gắn `HealthTrackerRegistry` được auto-configure:

```java
@Bean
public PubSubInboundChannelAdapter ordersInboundAdapter(
        MessageChannel ordersInputChannel,
        PubSubTemplate pubSubTemplate,
        HealthTrackerRegistry healthTrackerRegistry) {

    PubSubInboundChannelAdapter adapter =
            new PubSubInboundChannelAdapter(pubSubTemplate, "orders-sub");
    adapter.setOutputChannel(ordersInputChannel);
    adapter.setAckMode(AckMode.MANUAL);
    adapter.setHealthTrackerRegistry(healthTrackerRegistry);
    return adapter;
}
```

Bật Spring Boot Actuator health endpoint theo chính sách ứng dụng và bảo vệ endpoint quản trị. Health indicator cho biết tình trạng subscriber client; nó không thay dashboard Pub/Sub backlog, oldest unacked age hoặc DLQ metrics.

### 9.3. Graceful shutdown

`PubSubInboundChannelAdapter` là Spring lifecycle endpoint; Spring quản lý start/stop khi application context khởi động hoặc đóng. Không tự tạo subscriber mới trong mỗi request hoặc callback. Khi shutdown:

1. Ngừng nhận công việc mới theo lifecycle của adapter.
2. Cho handler đang chạy hoàn tất trong khoảng thời gian graceful shutdown.
3. ACK message đã commit nghiệp vụ.
4. Không ACK message chưa hoàn tất; để Pub/Sub redeliver sau deadline/lease.
5. Đảm bảo idempotency khi instance mới nhận lại message.

Với binder, để binding lifecycle được quản lý bởi Spring Cloud Stream và không xóa subscription production trong hook shutdown của ứng dụng.

## 10. Kiểm thử Integration và Stream binder

### 10.1. Unit test business handler

Tách business service khỏi adapter/binder để test:

- Payload hợp lệ cập nhật nghiệp vụ và commit.
- Duplicate event ID không tạo side effect lần hai.
- Lỗi dependency tạm thời được propagate để retry.
- Lỗi schema vĩnh viễn được quarantine hoặc chuyển DLQ theo policy.
- Error handler không ACK trước khi lưu bền vững.

### 10.2. Test channel adapter

Mock `OrderService` và `BasicAcknowledgeablePubsubMessage` để xác minh:

- `MANUAL` + success: handler gọi `ack()` sau khi business commit.
- `MANUAL` + lỗi: handler gọi `nack()` hoặc ghi quarantine rồi ACK theo policy.
- `AUTO` + exception propagate: adapter NACK.
- `AUTO` + error handler swallow exception: adapter có thể ACK; test này giúp phát hiện lỗi cấu hình.
- `AUTO_ACK` + exception: không NACK ngay, message chờ redelivery theo deadline.

### 10.3. Dùng Pub/Sub emulator

Khởi động emulator:

```bash
gcloud beta emulators pubsub start \
  --project=local-pubsub \
  --host-port=127.0.0.1:8085
```

Cấu hình ứng dụng:

```yaml
spring:
  cloud:
    gcp:
      project-id: local-pubsub
      pubsub:
        emulator-host: 127.0.0.1:8085
```

Test có thể tạo topic/subscription, publish, consume qua inbound adapter/binder, kiểm tra payload conversion, headers, ack/nack và idempotency. Emulator không thay thế kiểm thử IAM, quota, retry timing, DLQ forwarding, exactly-once hoặc ordering behavior trên Pub/Sub thật.

### 10.4. Test binder với functional binding

Trong test profile:

1. Đặt `spring.cloud.function.definition` trỏ tới function đang test.
2. Cấu hình destination và group tách biệt cho test.
3. Dùng emulator host để tránh kết nối project production.
4. Tạo topic/subscription fixture hoặc bật auto-create chỉ trong test.
5. Publish event và xác minh consumer nhận DTO đúng.
6. Kiểm tra retry/ACK behavior theo binder version đã pin.
7. Dọn tài nguyên test sau khi chạy.

Không dùng anonymous subscription test để xác minh durability của production group; phải test với group name ổn định.

### 10.5. Cloud sandbox test

Trên project sandbox, kiểm tra:

- Runtime service account chỉ có publish/subscribe role cần thiết.
- Topic/subscription đã được provision đúng.
- DLQ service agent IAM có đủ quyền.
- `AUTO`, `AUTO_ACK`, `MANUAL` có hành vi như mong muốn.
- Restart/scale out không tạo subscription ngoài dự kiến.
- Consumer group chia tải giữa các instance; group khác nhận bản copy riêng.
- `PubSubMessageHandler` success/failure callback hoạt động.
- Ordering key và header mapping được chuyển đúng.

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Inbound adapter không nhận message | Sai subscription, IAM thiếu hoặc subscriber chưa start | Kiểm tra resource name, runtime role và lifecycle |
| Payload là `byte[]` thay vì DTO | Chưa đặt `payloadType` hoặc converter không phù hợp | Cấu hình `setPayloadType()` và `PubSubMessageConverter` |
| Message lỗi nhưng bị ACK | Error handler bắt exception rồi return trong `AUTO`/`AUTO_ACK` | Propagate exception hoặc dùng `MANUAL` để ACK/NACK tường minh |
| Message redelivery liên tục | NACK, exception hoặc ack deadline hết | Kiểm tra retry policy, DLQ, ack extension và lỗi business |
| `ORIGINAL_MESSAGE` header bị null | Header bị filter hoặc handler không nhận đúng message | Kiểm tra adapter, header mapper và `allowedHeaders` |
| Publish thành công ở channel nhưng không thấy topic | Send channel không đồng nghĩa publish đã thành công; sai topic/IAM | Kiểm tra callback, topic và publisher permission |
| Stream binder tạo subscription lạ | Không khai báo group, binder tạo anonymous subscription | Đặt group ổn định và tắt auto-create trong production nếu dùng IaC |
| Mỗi instance nhận message trùng | Mỗi instance dùng group/anonymous subscription khác nhau | Dùng cùng group name cho các instance của cùng consumer |
| Group khác nhau không nhận bản copy | Nhầm group thành instance ID | Tạo subscription riêng cho mỗi nhóm nghiệp vụ cần bản copy |
| Binder không hỗ trợ partitioned consumer | Pub/Sub binder chưa hỗ trợ Stream partitioning | Dùng ordering key hoặc chọn binder khác có partitioning |
| Không có ACK response `SUCCESSFUL` | Spring GCP wrapper không expose `AckReplyConsumerWithResponse` | Dùng Java Pub/Sub client trực tiếp nếu cần exactly-once ACK response |
| Header nghiệp vụ biến mất | `allowedHeaders` hoặc header mapper lọc header | Thêm allowlist/header pattern và test contract |

### 11.1. Quy trình kiểm tra

1. Xác minh topic/subscription thực tế trên Google Cloud.
2. Kiểm tra IAM của runtime service account.
3. Kiểm tra `AckMode` hoặc binder `consumer.ack-mode`.
4. Kiểm tra error channel có swallow exception hay không.
5. Kiểm tra payload type, converter và header mapper.
6. Kiểm tra group và tên subscription.
7. Kiểm tra Pub/Sub backlog, oldest unacked age, expired ack deadlines và DLQ.
8. Kiểm tra BOM và phiên bản binder/Integration adapter đang chạy.

## 12. Chọn giải pháp theo yêu cầu

### 12.1. Bảng quyết định

| Yêu cầu | Lựa chọn khuyến nghị | Lý do |
| --- | --- | --- |
| Consumer đơn giản, xử lý một DTO | `PubSubTemplate.subscribe()` hoặc Stream `Consumer<T>` | Ít thành phần, code tập trung vào nghiệp vụ |
| Luồng có router/filter/transformer/error channel | Spring Integration | Có sẵn Enterprise Integration Patterns và channel composition |
| Publish từ nhiều service qua channel | `PubSubMessageHandler` | Outbound adapter và callback publish |
| Poll theo nhịp hoặc fetch batch | `PubSubMessageSource` | Kiểm soát poll interval, block và fetch size |
| Nhiều microservice dùng functional bindings | Spring Cloud Stream binder | Tách function code khỏi destination và consumer group |
| Cần exactly-once ACK response | Java Pub/Sub client trực tiếp | Spring Cloud GCP không expose `AckReplyConsumerWithResponse` |
| Cần partitioning của Spring Cloud Stream | Binder có hỗ trợ partitioning | Pub/Sub binder hiện không hỗ trợ Stream partitioning |
| Cần IAM, retention, DLQ và ordering được review trước deploy | IaC + adapter/binder với auto-create tắt | Tách provisioning khỏi runtime |

### 12.2. Nguyên tắc lựa chọn

- Bắt đầu với abstraction nhỏ nhất đáp ứng yêu cầu hiện tại.
- Dùng Spring Integration khi cần điều phối nhiều bước message flow.
- Dùng Stream binder khi muốn chuẩn hóa producer/consumer theo function và group.
- Dùng Java client trực tiếp khi cần tính năng Pub/Sub mà wrapper chưa expose.
- Không trộn nhiều consumer abstraction trên cùng subscription.
- Dù chọn abstraction nào, vẫn cần idempotency, schema contract, retry policy, DLQ và observability.

## 13. Bài tập thực hành tổng hợp

Một hệ thống thương mại điện tử có topic `orders` và subscription `orders-sub`. Service `order-worker` nhận `OrderCreated`, kiểm tra tồn kho, ghi đơn hàng vào database và phát `OrderAccepted`. Một luồng khác chỉ cần ghi audit event vào topic `order-audit`.

### Yêu cầu A — Spring Integration

1. Thêm Pub/Sub starter và `spring-integration-core` qua BOM tương thích.
2. Tạo `PubSubInboundChannelAdapter` dùng Streaming Pull.
3. Đặt payload type là DTO hoặc `String` qua converter.
4. Dùng `AckMode.MANUAL`; ACK sau transaction commit.
5. NACK lỗi dependency tạm thời; quarantine lỗi schema vĩnh viễn.
6. Tạo error channel và kiểm tra behavior khi handler propagate hoặc swallow exception.
7. Tạo outbound `PubSubMessageHandler` cho `order-audit`.
8. Thêm success/failure callback và mapping `eventId`, `eventType` headers.
9. Thử `GcpPubSubHeaders.ORDERING_KEY` theo `orderId` nếu nghiệp vụ cần thứ tự.
10. So sánh Streaming Pull với `PubSubMessageSource` khi publish batch nhiều message nhỏ và xử lý chậm.

### Yêu cầu B — Spring Cloud Stream

1. Thêm `spring-cloud-gcp-pubsub-stream-binder`.
2. Viết `Function<OrderCreated, OrderAccepted>`.
3. Cấu hình `acceptOrder-in-0` tới destination `orders`, group `order-worker`.
4. Cấu hình `acceptOrder-out-0` tới destination `accepted-orders`.
5. Provision topic/subscription trước bằng IaC và đặt `auto-create-resources: false`.
6. Thử `AUTO`, `AUTO_ACK` và `MANUAL` trong sandbox.
7. Tạo hai instance cùng group và quan sát chúng chia message.
8. Tạo group thứ hai và xác minh group đó nhận bản copy riêng.
9. Thử bỏ group để quan sát anonymous subscription và cleanup khi binder shutdown.
10. Kiểm tra binder không hỗ trợ partitioning và mô tả cách dùng ordering key nếu cần thứ tự theo key.

### Ma trận đánh giá

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Adapter nhận message hợp lệ | Payload chuyển đúng DTO và handler xử lý được |
| Transaction thành công | ACK chỉ sau commit |
| Dependency lỗi | NACK/retry theo policy đã chọn |
| Error handler nuốt exception ở AUTO | Test phát hiện message có thể bị ACK |
| Publish qua outbound adapter | Success/failure callback nhận kết quả |
| Header nghiệp vụ | Chỉ header được allowlist được publish |
| Cùng Stream group, nhiều instance | Message được phân phối trong cùng subscription |
| Group khác nhau | Mỗi group nhận bản copy riêng |
| Không có group | Anonymous subscription được tạo/cleanup theo binder behavior |
| Pub/Sub partitioning | Không bật Stream partitioning vì binder chưa hỗ trợ |
| Duplicate event | Inbox/idempotency ngăn side effect lặp |

### Tiêu chí hoàn thành

- Giải thích được khác nhau giữa Spring Integration adapter và Stream binder.
- Có inbound/outbound adapter chạy được trên emulator hoặc sandbox.
- Chọn ACK mode phù hợp và xử lý error channel đúng semantics.
- Có functional binding, destination và consumer group ổn định.
- Quản lý resource creation và IAM có kiểm soát.
- Có test retry, duplicate, header mapping và graceful shutdown.
- Nêu được giới hạn partitioning và exactly-once ACK response.

## 14. So sánh với AWS và Azure

| Nhu cầu tích hợp | Google Cloud Pub/Sub | AWS | Azure |
| --- | --- | --- | --- |
| Spring Integration | Pub/Sub channel adapters trong Spring Framework on Google Cloud | Spring Integration AWS adapters cho SQS/SNS/S3 và dịch vụ hỗ trợ | Spring Integration adapters cho Azure Service Bus/Storage tùy module |
| Spring Cloud Stream | Pub/Sub binder riêng, dựa trên channel adapters | Binder cho Kinesis; SQS/SNS thường dùng adapter/connector phù hợp | Binder cho Azure Event Hubs/Service Bus tùy dự án và phiên bản |
| Consumer group | Pub/Sub subscription; Stream group ánh xạ subscription | SQS queue consumer hoặc Kinesis shard/consumer semantics | Service Bus subscription/session hoặc Event Hubs consumer group |
| ACK | Pub/Sub ACK/NACK qua message wrapper | SQS `DeleteMessage` hoặc visibility timeout; Kinesis checkpoint | Service Bus `Complete`/`Abandon`; Event Hubs checkpoint |
| Partitioning/order | Pub/Sub ordering key; Stream binder chưa hỗ trợ partitioning | Kinesis shard/partition key; SQS FIFO MessageGroupId | Event Hubs partition key; Service Bus SessionId |
| Retry/DLQ | Subscription retry policy và dead-letter topic | SQS redrive policy/DLQ hoặc retry strategy của dịch vụ | Service Bus DLQ hoặc Event Hubs checkpoint/retry strategy |

Các adapter và binder không đồng nhất semantics giữa broker. Khi chuyển cloud, ánh xạ lại destination, group/subscription, ACK, retry, DLQ, ordering và partitioning theo dịch vụ đích. Không giả định `consumer group` trong Spring Cloud Stream có hành vi giống hệt trên mọi binder.

## Tổng kết

Spring Integration và Spring Cloud Stream đều giúp Spring Boot tích hợp Google Cloud Pub/Sub, nhưng giải quyết hai mức abstraction khác nhau. Spring Integration dùng `PubSubInboundChannelAdapter`, `PubSubMessageSource` và `PubSubMessageHandler` để kết nối `MessageChannel`, hỗ trợ routing, error channel, pollable source, header mapping và ACK mode. Spring Cloud Stream binder dùng `Supplier`/`Function`/`Consumer`, destination và consumer group để xây dựng microservice event-driven theo functional model.

Với Integration, hiểu rõ `AUTO`, `AUTO_ACK` và `MANUAL`; đặc biệt, error handler hoàn tất bình thường có thể khiến adapter ACK message dù flow nghiệp vụ đã gặp lỗi. Với Stream binder, khai báo group ổn định để có subscription bền vững, quản lý auto-create resource có kiểm soát và nhớ rằng Pub/Sub binder hiện chưa hỗ trợ Stream partitioning. Nếu cần exactly-once ACK response, dùng Java Pub/Sub client trực tiếp vì Spring Cloud GCP không expose `AckReplyConsumerWithResponse`.

Dù chọn hướng nào, consumer vẫn cần idempotency, commit trước ACK, retry có giới hạn, DLQ bền vững, header/schema contract và monitoring. Chọn abstraction theo yêu cầu xử lý và khả năng kiểm soát cần thiết, không chỉ theo số dòng code.

## Tài liệu tham khảo

- [Spring Framework on Google Cloud — Spring Integration](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html) — inbound/outbound channel adapter, pollable source, ACK mode, error handling và header mapping.
- [Spring Framework on Google Cloud — Spring Cloud Stream binder](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html) — Pub/Sub binder, binding configuration, consumer group, resource creation và function model.
- [Google Cloud — Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring) — lựa chọn Pub/Sub starter, Spring Integration adapters và Stream binder; giới hạn exactly-once ACK response.
- [Spring Framework on Google Cloud — Pub/Sub API](https://googleapis.dev/java/spring-cloud-gcp/latest/index.html) — `PubSubInboundChannelAdapter`, `PubSubMessageSource`, `PubSubMessageHandler` và các API hỗ trợ.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — quy ước `<functionName>-in-0` và `<functionName>-out-0`.
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — destination, group và consumer/producer properties.
- [Spring Cloud Stream — Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) — semantics group và competing consumers.
- [Spring Guides — Messaging with Google Cloud Pub/Sub](https://github.com/spring-guides/gs-messaging-gcp-pubsub) — ví dụ Spring Integration inbound/outbound channel adapters.
