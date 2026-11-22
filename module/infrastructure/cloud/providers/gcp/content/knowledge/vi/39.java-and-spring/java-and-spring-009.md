# Tích hợp Spring Boot với Pub/Sub qua messaging adapters

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở chương **Java và Spring trên GCP**, bài này hướng dẫn ứng dụng Spring Boot phát và nhận sự kiện bằng **Google Cloud Pub/Sub** thông qua **Spring Integration messaging adapters**.

Ta xây một ứng dụng `orders-api`: HTTP request phát sự kiện `OrderCreated` lên topic `orders-created`; consumer nhận qua subscription `orders-worker-sub`, xử lý nghiệp vụ và quyết định `ack` hoặc `nack`. Mục tiêu không chỉ là gửi được một thông điệp mà còn hiểu hợp đồng dữ liệu, retry, xử lý trùng lặp, IAM, kiểm thử, quan sát và lựa chọn môi trường chạy phù hợp.

## 1. Mô hình Pub/Sub và Spring Integration

Pub/Sub truyền thông điệp bất đồng bộ theo mô hình publish/subscribe. **Topic** là nơi producer publish; **subscription** giữ luồng thông điệp được giao cho consumer. Hai subscription độc lập của cùng topic có thể nhận hai bản sao luồng sự kiện; các consumer cùng một subscription chia sẻ việc xử lý message của subscription đó.

Spring Integration cung cấp `Message`, `MessageChannel`, `@MessagingGateway`, `@ServiceActivator` cùng các Enterprise Integration Patterns. Channel adapter đóng vai trò cầu nối giữa Spring messages và Pub/Sub.

| Thành phần | Chức năng |
| --- | --- |
| `Message<T>` | Payload cùng headers của thông điệp trong Spring. |
| `MessageChannel` | Kênh nội bộ giữa các thành phần; ví dụ `DirectChannel`. |
| `@MessagingGateway` | Ánh xạ phương thức Java thành thao tác gửi message vào channel. |
| `PubSubMessageHandler` | Outbound adapter: nhận message từ channel, publish lên Pub/Sub topic. |
| `PubSubInboundChannelAdapter` | Inbound adapter: dùng Streaming Pull đọc Pub/Sub subscription, đẩy message vào channel. |
| `@ServiceActivator` | Xử lý message đến từ một channel. |
| `PubSubTemplate` | Abstraction publish/subscribe được Spring Framework on Google Cloud cấu hình. |
| `PubSubAdmin` | Quản lý tài nguyên topic và subscription khi bootstrap. |

~~~mermaid
flowchart LR
  HTTP[POST /orders/id/events] --> REST[OrderController]
  REST --> GW[OrderEventGateway]
  GW --> OUT[ordersOutboundChannel]
  OUT --> ADOUT[PubSubMessageHandler]
  ADOUT --> TOPIC[(orders-created topic)]
  TOPIC --> SUB[(orders-worker-sub)]
  SUB --> ADIN[PubSubInboundChannelAdapter]
  ADIN --> IN[ordersInboundChannel]
  IN --> PROC[OrderProcessor]
  PROC -->|ack/nack| SUB
~~~

Topic/subscription là tài nguyên của Pub/Sub trên Google Cloud; `MessageChannel` chỉ tồn tại trong process Spring Boot. Một message được publish vào topic; consumer subscribe vào subscription chứ không trực tiếp pull topic.

### 1.1. Khi nào chọn adapter?

| Lựa chọn | Trường hợp phù hợp |
| --- | --- |
| Dùng trực tiếp `PubSubTemplate` | Logic nhỏ, muốn gọi API publish/subscribe trong service. |
| Spring Integration channel adapters | Ứng dụng có message flows, gateways, filters, transformers, service activators; muốn dùng Enterprise Integration Patterns. |
| Spring Cloud Stream Pub/Sub Binder | Kiến trúc theo Spring Cloud Stream functions/bindings, muốn giảm mã liên quan đến middleware. |

Ví dụ tập trung vào **Spring Integration adapters**, không cần thêm Stream Binder cho cùng luồng.

## 2. Chuẩn bị Google Cloud và IAM

Bạn cần JDK 17 trở lên, một phiên bản Spring Boot tương thích với Spring Framework on Google Cloud, Google Cloud CLI, project có billing hợp lệ và quyền quản lý Pub/Sub để tạo tài nguyên ban đầu.

### 2.1. Bật API, tạo topic và pull subscription

~~~bash
gcloud config set project PROJECT_ID
gcloud services enable pubsub.googleapis.com --project=PROJECT_ID

gcloud pubsub topics create orders-created --project=PROJECT_ID

gcloud pubsub subscriptions create orders-worker-sub \
  --topic=orders-created \
  --ack-deadline=30 \
  --project=PROJECT_ID
~~~

Đây là **pull subscription**. `PubSubInboundChannelAdapter` sử dụng Streaming Pull nên không cần push endpoint. `--ack-deadline=30` đặt deadline ban đầu; Pub/Sub Java client có thể tự gia hạn ack deadline trong quá trình xử lý. Không suy luận rằng mọi message chưa ack đều sẽ được giao lại chính xác sau 30 giây.

Với producer và consumer khác project, adapter chấp nhận tên đầy đủ dạng `projects/PROJECT_ID/topics/TOPIC` hoặc `projects/PROJECT_ID/subscriptions/SUBSCRIPTION`; khi đó quyền IAM phải được cấp ở đúng project/tài nguyên.

### 2.2. Cấp quyền theo nguyên tắc tối thiểu

Tạo service account cho runtime minh họa:

~~~bash
gcloud iam service-accounts create orders-messaging \
  --display-name="Orders messaging runtime" \
  --project=PROJECT_ID
~~~

Cấp quyền publish ở topic và quyền subscribe ở subscription:

~~~bash
gcloud pubsub topics add-iam-policy-binding orders-created \
  --member="serviceAccount:orders-messaging@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project=PROJECT_ID

gcloud pubsub subscriptions add-iam-policy-binding orders-worker-sub \
  --member="serviceAccount:orders-messaging@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber" \
  --project=PROJECT_ID
~~~

Bài học gộp producer và consumer trong một process cho dễ chạy. Trong production, nên tách service account publisher và subscriber nếu hai workload độc lập. Dịch vụ xử lý message không cần quyền Pub/Sub Admin chỉ để đọc subscription.

Đối với phát triển local với dịch vụ thật, dùng `gcloud auth application-default login` và bảo đảm principal có quyền Pub/Sub tương ứng. Với Cloud Run, Compute Engine hoặc GKE, dùng service account gắn với workload/Workload Identity Federation. Tránh service account key JSON dài hạn trong source code, container image hoặc CI secrets.

## 3. Dependencies và cấu hình Spring Boot

### 3.1. Chọn phiên bản thư viện

Spring Framework on Google Cloud dùng BOM để quản lý phiên bản. Với Spring Boot **3.5.x**, dòng Spring Framework on Google Cloud **7.x** là lựa chọn tương thích theo bảng của dự án. Dự án Spring Boot 4.x có nhánh thư viện tương ứng khác; luôn đối chiếu bảng compatibility trước khi nâng version.

Ví dụ một phần `build.gradle` của ứng dụng Spring Boot 3.5.x:

~~~groovy
dependencies {
    implementation platform("com.google.cloud:spring-cloud-gcp-dependencies:7.5.2")
    implementation "com.google.cloud:spring-cloud-gcp-starter-pubsub"
    implementation "org.springframework.integration:spring-integration-core"
    implementation "org.springframework.boot:spring-boot-starter-web"
}
~~~

BOM 7.5.2 là phiên bản minh họa từ hướng dẫn của dự án; kiểm tra phiên bản đã được tổ chức kiểm thử khi dùng thật. Nếu dùng Maven, import `com.google.cloud:spring-cloud-gcp-dependencies` trong `dependencyManagement` rồi khai báo các dependency trên. Tránh trộn tọa độ `org.springframework.cloud:spring-cloud-gcp-...` của các thế hệ cũ với `com.google.cloud:spring-cloud-gcp-...` hiện hành.

### 3.2. Cấu hình project, topic, subscription

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: orders-api
  cloud:
    gcp:
      project-id: PROJECT_ID
      pubsub:
        enabled: true

app:
  pubsub:
    topic: orders-created
    subscription: orders-worker-sub
~~~

Thay `PROJECT_ID` bằng project của bài lab; khi triển khai có thể ghi đè bằng `SPRING_CLOUD_GCP_PROJECT_ID`. Pub/Sub starter cung cấp `PubSubTemplate` theo project và Application Default Credentials (ADC). Các khóa `app.pubsub.topic` và `app.pubsub.subscription` là cấu hình ứng dụng để tránh viết cứng resource name trong code.

## 4. Outbound adapter: gửi sự kiện OrderCreated

### 4.1. Định nghĩa event contract

`OrderCreated.java`:

~~~java
package com.example.orders;

public record OrderCreated(
    String eventId,
    String orderId,
    String occurredAt,
    int schemaVersion
) {}
~~~

Ví dụ JSON:

~~~json
{
  "eventId": "event-6e4158",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-19T09:00:00Z",
  "schemaVersion": 1
}
~~~

`eventId` là định danh logic của sự kiện, dùng khi xây idempotency. Pub/Sub có `messageId` riêng cho từng lần publish. Nếu producer retry bằng cách publish lại cùng event, message ID có thể khác, vì vậy cần giữ `eventId` ổn định theo giao dịch nghiệp vụ.

### 4.2. Messaging gateway

`OrderEventGateway.java`:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "ordersOutboundChannel")
public interface OrderEventGateway {
    void publish(String json);
}
~~~

Spring Integration tạo gateway implementation và gửi tham số `json` vào channel chỉ định. Controller gọi `gateway.publish(...)` như một phương thức Java bình thường.

### 4.3. Cấu hình inbound và outbound channels

`PubSubAdapters.java`:

~~~java
package com.example.orders;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.cloud.spring.pubsub.core.PubSubTemplate;
import com.google.cloud.spring.pubsub.integration.AckMode;
import com.google.cloud.spring.pubsub.integration.inbound.PubSubInboundChannelAdapter;
import com.google.cloud.spring.pubsub.integration.outbound.PubSubMessageHandler;
import com.google.cloud.spring.pubsub.support.BasicAcknowledgeablePubsubMessage;
import com.google.cloud.spring.pubsub.support.GcpPubSubHeaders;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;

@Configuration
@IntegrationComponentScan(basePackageClasses = OrderEventGateway.class)
public class PubSubAdapters {
    private static final Logger log =
        LoggerFactory.getLogger(PubSubAdapters.class);

    @Bean
    public MessageChannel ordersOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel ordersInboundChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "ordersOutboundChannel")
    public MessageHandler ordersPublisher(
            PubSubTemplate pubSubTemplate, Environment environment) {

        String topic = environment.getRequiredProperty("app.pubsub.topic");
        PubSubMessageHandler adapter =
            new PubSubMessageHandler(pubSubTemplate, topic);

        // Lab: trả kết quả khi Pub/Sub đã xác nhận publish.
        adapter.setSync(true);
        adapter.setPublishTimeout(10_000L);
        adapter.setSuccessCallback((messageId, original) ->
            log.info("publish confirmed messageId={}", messageId));
        adapter.setFailureCallback((error, original) ->
            log.error("publish failed", error));
        return adapter;
    }

    @Bean
    public PubSubInboundChannelAdapter ordersSubscriber(
            @Qualifier("ordersInboundChannel") MessageChannel input,
            PubSubTemplate pubSubTemplate,
            Environment environment) {

        String subscription =
            environment.getRequiredProperty("app.pubsub.subscription");
        PubSubInboundChannelAdapter adapter =
            new PubSubInboundChannelAdapter(pubSubTemplate, subscription);
        adapter.setOutputChannel(input);
        adapter.setAckMode(AckMode.MANUAL);
        return adapter;
    }

    @Bean
    @ServiceActivator(inputChannel = "ordersInboundChannel")
    public MessageHandler ordersReceiver(
            ObjectMapper mapper, OrderProcessor processor) {

        return springMessage -> {
            BasicAcknowledgeablePubsubMessage original =
                springMessage.getHeaders().get(
                    GcpPubSubHeaders.ORIGINAL_MESSAGE,
                    BasicAcknowledgeablePubsubMessage.class);

            if (original == null) {
                throw new IllegalStateException("Missing Pub/Sub ack header");
            }

            try {
                byte[] payload = (byte[]) springMessage.getPayload();
                OrderCreated event =
                    mapper.readValue(payload, OrderCreated.class);

                processor.handle(event);
                original.ack().whenComplete((done, error) -> {
                    if (error != null) {
                        log.error("Pub/Sub ack failed", error);
                    }
                });
            } catch (Exception error) {
                log.error("Processing failed; requesting redelivery", error);
                original.nack().whenComplete((done, nackError) -> {
                    if (nackError != null) {
                        log.error("Pub/Sub nack failed", nackError);
                    }
                });
            }
        };
    }
}
~~~

`DirectChannel` gọi handler trong cùng luồng dispatch, phù hợp khi muốn xử lý xong rồi ack. Nếu thay bằng `ExecutorChannel` hoặc pipeline bất đồng bộ, phải bảo đảm adapter/consumer không ack trước khi tác vụ nghiệp vụ thực sự hoàn tất.

Ở đoạn `ordersPublisher`, `PubSubMessageHandler` publish bất đồng bộ theo mặc định; `setSync(true)` kết hợp timeout 10 giây khiến việc gửi qua gateway chờ kết quả publish. Trong production, nếu dùng publish async, cần success/failure callback hoặc transactional outbox để kiểm soát sự kiện chưa được Pub/Sub xác nhận.

Ở đoạn inbound, `BasicAcknowledgeablePubsubMessage.ack()` và `nack()` trả `CompletableFuture<Void>`. Code theo dõi lỗi ack/nack để tránh nhầm việc gọi phương thức với xác nhận đã được xử lý thành công.

### 4.4. Business handler

`OrderProcessor.java`:

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderProcessor {
    private static final Logger log =
        LoggerFactory.getLogger(OrderProcessor.class);

    public void handle(OrderCreated event) {
        if (event.schemaVersion() != 1) {
            throw new IllegalArgumentException("Unsupported event version");
        }

        // Chỉ minh họa: production phải commit DB/idempotency trước ack.
        log.info("handled eventId={} orderId={}",
            event.eventId(), event.orderId());
    }
}
~~~

Handler này cố ý đơn giản để học luồng messaging. Khi dùng database, cần đặt unique constraint theo `eventId` hoặc khóa nghiệp vụ tương đương, áp dụng thay đổi trong một transaction và chỉ ack sau commit.

### 4.5. HTTP controller để thử publisher

`OrderController.java`:

~~~java
package com.example.orders;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderEventGateway gateway;
    private final ObjectMapper mapper;

    public OrderController(OrderEventGateway gateway, ObjectMapper mapper) {
        this.gateway = gateway;
        this.mapper = mapper;
    }

    @PostMapping("/{orderId}/events")
    public ResponseEntity<Map<String, String>> publish(
            @PathVariable String orderId) throws JsonProcessingException {

        OrderCreated event = new OrderCreated(
            UUID.randomUUID().toString(),
            orderId,
            Instant.now().toString(),
            1
        );

        gateway.publish(mapper.writeValueAsString(event));

        return ResponseEntity.accepted()
            .body(Map.of("eventId", event.eventId()));
    }
}
~~~

Với synchronous publisher trong ví dụ, trả `202 Accepted` sau khi Pub/Sub xác nhận publish. **Phản hồi HTTP không chứng minh consumer đã xử lý xong**. Nếu chuyển sang async publish, `202` có thể xuất hiện trước khi Pub/Sub chấp nhận message; cần có cơ chế bảo đảm publish phù hợp với cam kết của hệ thống.

### 4.6. Spring Boot entry point

`OrdersApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Các lớp thuộc cùng package hoặc package con của `com.example.orders` để component scan có thể tìm controller, service và adapter configuration.

## 5. ACK, NACK và điều kiện xử lý thành công

Với `PubSubInboundChannelAdapter`, ba chế độ acknowledgement có ý nghĩa khác nhau:

| Ack mode | Khi handler hoàn tất thành công | Khi exception đi ra khỏi adapter |
| --- | --- | --- |
| `AUTO` (mặc định) | Adapter ack | Adapter nack để redelivery |
| `AUTO_ACK` | Adapter ack | Không tự ack/nack; chờ theo deadline |
| `MANUAL` | Ứng dụng phải tự ack/nack | Ứng dụng vẫn phải tự quyết định ack/nack |

Ở `MANUAL`, calling `ack()` sau khi commit là ranh giới chịu trách nhiệm xử lý message. Nack có thể làm message được giao lại ngay hoặc gần ngay; chưa ack/nack thì Pub/Sub redelivery khi deadline hết hạn và các lần gia hạn ack kết thúc.

**Cẩn thận với error channel:** Nếu dùng `AUTO` và Spring Integration error handler bắt exception rồi kết thúc bình thường, adapter có thể coi flow thành công và ack message. Nếu muốn chế độ AUTO nack, exception phải được chuyển trở lại adapter. Chế độ MANUAL giúp quyết định rõ ngay trong consumer, nhưng cũng đòi hỏi xử lý đầy đủ mọi đường đi lỗi.

Không ack trước khi database commit. Nếu ứng dụng crash giữa lúc đã commit và chưa ack, message sẽ quay lại; vì thế consumer phải idempotent. Nếu crash trước commit, Pub/Sub có cơ hội giao lại để xử lý.

## 6. Chạy thử end-to-end trên Google Cloud

1. Bảo đảm topic/subscription tồn tại, application principal có IAM đã cấp và `application.yml` trỏ đúng project.
2. Khởi động app với Gradle hoặc Maven. Trên máy phát triển, trước đó có thể chạy `gcloud auth application-default login`.
3. Publish qua HTTP:

~~~bash
./gradlew bootRun

curl -X POST "http://localhost:8080/orders/ORD-1001/events"
~~~

Trên Windows dùng `gradlew.bat bootRun`. Quan sát log `publish confirmed messageId=...` và `handled eventId=... orderId=...` từ consumer.

Bạn cũng có thể publish trực tiếp bằng CLI để kiểm tra consumer độc lập với controller:

~~~bash
gcloud pubsub topics publish orders-created \
  --message='{"eventId":"lab-1002","orderId":"ORD-1002","occurredAt":"2026-11-19T09:00:00Z","schemaVersion":1}' \
  --project=PROJECT_ID
~~~

Tạm thay `OrderProcessor.handle` để ném exception khi `orderId` là `ORD-FAIL`, gửi một sự kiện lỗi và quan sát việc `nack` rồi redelivery. Sau đó khôi phục handler. Sự kiện Pub/Sub có thể được giao lại nhiều lần nên log không phải bằng chứng mỗi event chỉ được xử lý một lần.

## 7. Kiểm thử bằng Pub/Sub Emulator

Pub/Sub emulator giúp kiểm tra publish/subscribe mà không dùng tài nguyên production. Khởi chạy bằng Google Cloud CLI:

~~~bash
gcloud components install pubsub-emulator

gcloud beta emulators pubsub start \
  --project=local-pubsub \
  --host-port=127.0.0.1:8085
~~~

Thêm file cấu hình Spring profile `application-local.yml`:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-pubsub
      pubsub:
        emulator-host: 127.0.0.1:8085
~~~

Dùng profile `local` khi chạy ứng dụng với emulator. Emulator không sử dụng IAM thật; các resource/message trong một phiên local không đại diện cho độ tin cậy, quota hoặc chính sách của Pub/Sub production. Quan trọng: **`gcloud pubsub topics/subscriptions` không tạo tài nguyên trong emulator**. Các lệnh `gcloud pubsub` ở mục 2 chỉ dành cho dịch vụ thật.

Trước khi khởi động inbound adapter, tạo topic và subscription trên emulator qua `PubSubAdmin` trong một chương trình bootstrap hoặc test fixture riêng:

~~~java
// PubSubAdmin đã được kết nối với project local-pubsub và emulator.
pubSubAdmin.createTopic("orders-created");
pubSubAdmin.createSubscription("orders-worker-sub", "orders-created");
~~~

Không mặc định chạy hai lệnh tạo này bằng `ApplicationRunner` trong cùng app consumer: lifecycle của inbound adapter có thể bắt đầu trước runner, khiến subscription chưa tồn tại khi subscriber kết nối. Kiểm thử integration nên bootstrap resource trước khi context consumer startup.

## 8. Idempotency, retry và dead-letter topic

### 8.1. Xử lý message lặp

Pub/Sub mặc định có **at-least-once delivery**. Message có thể được giao lại do ack deadline, network, client restart hoặc crash. Nếu consumer thanh toán/ghi DB, xử lý lại không được gây hiệu ứng phụ lặp.

Mẫu triển khai production:

1. Producer gắn `eventId` ổn định cho cùng một sự kiện logic.
2. Consumer mở database transaction.
3. Insert `eventId` vào bảng `processed_events` với unique constraint; nếu đã có, coi là xử lý xong.
4. Áp dụng thay đổi nghiệp vụ trong **cùng transaction**.
5. Commit thành công rồi ack Pub/Sub.

Khi consumer crash sau commit nhưng trước ack, message có thể trở lại và unique constraint ngăn tác động trùng. Không dựa vào `Set` trong memory khi có nhiều replica; việc restart sẽ xóa danh sách và có race giữa các instance.

### 8.2. Phân biệt lỗi tạm thời và lỗi vĩnh viễn

| Lỗi | Xử lý gợi ý |
| --- | --- |
| Database timeout hoặc downstream 503 | Retry có backoff; theo dõi số lần nhận lại và giới hạn concurrency. |
| Quota 429 | Giảm tốc, hạn chế fan-out, điều chỉnh flow control. |
| JSON sai schema, event version không hỗ trợ | Đưa vào DLQ sau số lần thử phù hợp và xử lý ngoại tuyến. |
| Event trùng đã commit | Ack và bỏ qua side effect mới. |
| Permission denied / không có subscription | Sửa cấu hình/IAM; retry message không sửa được lỗi hệ thống. |

### 8.3. Cấu hình DLQ trên subscription

~~~bash
gcloud pubsub topics create orders-dlq --project=PROJECT_ID

gcloud pubsub subscriptions create orders-dlq-sub \
  --topic=orders-dlq \
  --project=PROJECT_ID

gcloud pubsub subscriptions update orders-worker-sub \
  --dead-letter-topic=orders-dlq \
  --max-delivery-attempts=5 \
  --project=PROJECT_ID
~~~

Dead-letter topic thuộc cấu hình **subscription nguồn**. Để forwarding hoạt động, Pub/Sub service agent của project (dạng `service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com`) cần được cấp quyền publish lên DLQ topic và quyền subscribe/ack trên source subscription. Tài liệu Pub/Sub quy định các role cụ thể và hướng dẫn cấp chúng.

`max-delivery-attempts` là mục tiêu xấp xỉ; Pub/Sub có thể thực hiện ít hoặc nhiều lần giao hơn. Cần một subscription trên DLQ topic, runbook, cảnh báo, xử lý dữ liệu nhạy cảm và quy trình replay có kiểm soát. Không tự động phát lại message lỗi schema vô hạn.

## 9. Pub/Sub headers, schema và ordering

Outbound adapter ánh xạ các headers của Spring `Message` sang Pub/Sub attributes (giá trị chuỗi), trừ một số headers nội bộ; inbound adapter ánh xạ attributes trở lại message headers.

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

Message<String> message = MessageBuilder
    .withPayload(json)
    .setHeader("eventType", "OrderCreated")
    .setHeader("schemaVersion", "1")
    .setHeader("correlationId", requestId)
    .build();

ordersOutboundChannel.send(message);
~~~

Đoạn này minh họa cách gửi headers khi đã có tham chiếu `MessageChannel` và payload JSON. Đừng đưa access token, mật khẩu, cookie, số thẻ hoặc thông tin cá nhân không cần thiết vào payload/headers. Trong production, dùng schema contract có version và kiểm soát tương thích trước/sau để producer, consumer phát hành độc lập.

Nếu cần giữ thứ tự theo `orderId`, Pub/Sub hỗ trợ ordering key. Spring adapter dùng `GcpPubSubHeaders.ORDERING_KEY`, và publisher phải bật `spring.cloud.gcp.pubsub.publisher.enable-message-ordering=true`. Subscription cũng cần bật ordering khi tạo. Message ordering áp dụng **theo từng key**, không bảo đảm thứ tự toàn bộ topic, và có tác động đến retry, concurrency.

## 10. Chọn môi trường chạy phù hợp

**GKE / Compute Engine:** Streaming Pull phù hợp cho ứng dụng hoặc worker chạy liên tục. Dùng Workload Identity Federation for GKE hoặc service account của VM; cấu hình subscriber flow control, concurrency và graceful shutdown. Nếu logic nghiệp vụ ghi database chậm, giới hạn outstanding messages để không làm cạn connection pool.

**Cloud Run:** Inbound Streaming Pull là công việc nền. Nếu Cloud Run service chỉ được cấp CPU trong lúc xử lý HTTP request, subscriber chạy nền có thể bị tạm dừng. Cần cân nhắc instance-based billing, minimum instances và vòng đời instance khi dùng Streaming Pull trên Cloud Run. Với kiến trúc request-driven, **Pub/Sub push subscription** gọi HTTP endpoint Cloud Run thường phù hợp hơn, nhưng đó là mô hình push HTTP, không phải inbound Streaming Pull adapter trong bài.

Producer và consumer chạy cùng một process rất tiện cho lab. Trong production có thể tách chúng thành hai deployment để scale theo HTTP traffic và subscription backlog riêng, tách danh tính IAM, quota và failure domain.

## 11. Observability và vận hành

Khi deploy, theo dõi cả client và Pub/Sub:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `subscription/num_undelivered_messages` | Backlog, mức độ consumer xử lý không kịp. |
| `subscription/oldest_unacked_message_age` | Message unacked lâu nhất, phản ánh độ trễ xử lý. |
| Publish latency/failure | Quyền, quota, network, timeout của publisher. |
| Consumer processing time/error | Chất lượng xử lý nghiệp vụ, database và downstream. |
| Ack/nack và redelivery | Lỗi lặp, deadline hoặc xử lý không thành công. |
| `subscription/dead_letter_message_count` | Số message chuyển sang DLQ. |

Nên log `eventId`, `messageId` nếu phù hợp, subscription, schema version, trạng thái xử lý và lỗi đã được làm sạch. Dùng OpenTelemetry tạo span producer/consumer và truyền trace context qua Pub/Sub attributes nếu cần theo dõi xuyên dịch vụ. Propagation qua message metadata không được bảo đảm nếu ứng dụng không cấu hình.

Thiết lập cảnh báo trên backlog, tuổi message, DLQ và failure rate; duy trì runbook để xử lý subscription bị kẹt. Theo dõi phí theo số message, retention, egress và lượng logs/metrics, không chỉ CPU của ứng dụng.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Inbound adapter không thấy subscription | Sai project, tên subscription hoặc subscription chưa tồn tại. | Đối chiếu project ID, `app.pubsub.subscription` và Pub/Sub Console. |
| Publish bị `PERMISSION_DENIED` | Runtime thiếu Pub/Sub Publisher trên topic. | Kiểm tra principal, cấp role trên đúng topic. |
| Pull bị `PERMISSION_DENIED` | Thiếu Pub/Sub Subscriber trên subscription. | Kiểm tra IAM và runtime identity. |
| Gateway không được tạo | Chưa bật scan cho `@MessagingGateway`. | Kiểm tra `@IntegrationComponentScan` và package. |
| Payload bị `ClassCastException` | Inbound mặc định dùng `byte[]`, handler lại ép thành String. | Decode UTF-8 hoặc cấu hình payload converter. |
| Consumer bị redelivery liên tục | Nack, lỗi parse, lỗi downstream, deadline hoặc ack thất bại. | Xem exception, subscriber metrics và DLQ. |
| Message mất khỏi subscription dù xử lý lỗi | Dùng AUTO và error handler đã nuốt exception. | Propagate lỗi hoặc dùng MANUAL ack/nack. |
| Dữ liệu bị tạo trùng | At-least-once delivery nhưng không có idempotency. | Unique constraint theo `eventId`, transaction và ack sau commit. |
| DLQ không nhận message | Service agent thiếu quyền forward hoặc cấu hình sai. | Kiểm tra publisher/subscriber role của service agent. |
| Emulator chạy nhưng app kết nối Pub/Sub thật | Chưa bật local profile hoặc chưa cấu hình emulator-host. | Kiểm tra profile/endpoint; bootstrap resource local trước khi chạy. |
| Streaming Pull trên Cloud Run thất thường | CPU bị suspend ngoài request hoặc scale-to-zero. | Điều chỉnh mô hình CPU/min instances hoặc dùng push HTTP. |

## 13. Checklist hoàn thành

- [ ] Chọn Spring Boot và Spring Framework on Google Cloud BOM tương thích.
- [ ] Tạo topic và pull subscription trong đúng project.
- [ ] Gắn runtime identity có Pub/Sub Publisher và Subscriber theo tài nguyên.
- [ ] Spring Boot có `PubSubTemplate`, application config và Spring Integration dependency.
- [ ] Gateway phát JSON qua outbound channel và `PubSubMessageHandler`.
- [ ] Inbound adapter dùng Streaming Pull đưa `byte[]` vào inbound channel.
- [ ] ServiceActivator parse event và xử lý nghiệp vụ trước khi ack.
- [ ] Chế độ MANUAL có đường ack/nack và quan sát lỗi của ack/nack.
- [ ] Publish thử qua HTTP và CLI; xác nhận message được xử lý.
- [ ] Có chiến lược idempotency và DLQ khi ứng dụng xử lý dữ liệu thật.
- [ ] Kiểm tra emulator theo profile riêng, tránh nhầm tài nguyên local với cloud thật.
- [ ] Theo dõi backlog, oldest unacked age, publish failure, retry và DLQ.
- [ ] Chọn mô hình Streaming Pull hoặc push phù hợp với Cloud Run/GKE/VM.

## Tài liệu tham khảo

- [Google Cloud: Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring) — phân biệt starter, Spring Integration adapters và Stream Binder.
- [Spring Framework on Google Cloud: Spring Integration](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/spring-integration.html) — inbound/outbound adapters, ack modes, headers và error handling.
- [Spring Framework on Google Cloud: Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/pubsub.html) — cấu hình, PubSubTemplate và PubSubAdmin.
- [Spring Framework on Google Cloud: Getting Started](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/getting-started.html) — BOM và ma trận tương thích.
- [Spring Guide: Messaging with Google Cloud Pub/Sub](https://github.com/spring-guides/gs-messaging-gcp-pubsub) — ví dụ Spring Integration channel adapters.
- [Pub/Sub: Dead-letter topics](https://docs.cloud.google.com/pubsub/docs/dead-letter-topics) — DLQ, service agent IAM và delivery attempts.
- [Pub/Sub: Testing apps locally with the emulator](https://docs.cloud.google.com/pubsub/docs/emulator) — chạy emulator, hạn chế và cách kết nối.
- [Pub/Sub: Subscriber overview](https://docs.cloud.google.com/pubsub/docs/subscriber) — Streaming Pull, ack deadline và redelivery.
- [Pub/Sub: Monitoring](https://docs.cloud.google.com/pubsub/docs/monitoring) — backlog, oldest unacked age và vận hành.

