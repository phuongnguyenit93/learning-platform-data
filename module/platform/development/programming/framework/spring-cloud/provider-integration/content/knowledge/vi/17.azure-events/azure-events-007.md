# Phát và nhận Event Grid theo khả năng SDK hoặc starter

Azure Event Grid là dịch vụ định tuyến sự kiện theo mô hình publish/subscribe. Ứng dụng phát event lên topic hoặc domain; Event Grid áp dụng filter của event subscription rồi chuyển event tới event handler như webhook HTTP, Service Bus queue/topic, Event Hubs hoặc Storage Queue. Khi tích hợp Spring Boot, có thể dùng **Azure SDK for Java** trực tiếp hoặc **Spring Cloud Azure Event Grid starter** để phát event. Ở chiều nhận, ứng dụng làm việc với endpoint đích đã đăng ký; Event Grid Java SDK không cung cấp một receiver client để kéo event từ topic.

Bài này tập trung vào Event Grid topics/domains và push delivery bằng publisher SDK/starter. Event Grid namespaces với pull delivery có mô hình nhận và API riêng; không dùng ví dụ webhook/Service Bus dưới đây như cấu hình cho namespace pull consumer.

Bài học thuộc chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider. Bài này tập trung vào publish EventGridEvent/CloudEvent, dùng starter trong Spring Boot, nhận qua webhook hoặc Service Bus, xác thực endpoint, retry, dead-letter và vận hành an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả luồng publisher → topic/domain → event subscription → event handler.
- Phân biệt Event Grid với Event Hubs và Service Bus để chọn đúng dịch vụ.
- Chọn EventGridEvent, CloudEvent hoặc custom schema theo input schema của topic.
- Tạo publisher client bằng Azure SDK for Java và dùng Spring Cloud Azure Event Grid starter.
- Cấu hình Microsoft Entra ID, Managed Identity và role EventGrid Data Sender.
- Nhận event bằng HTTP webhook trong Spring Boot hoặc chuyển event tới Service Bus để consumer xử lý.
- Thực hiện subscription validation đúng với Event Grid schema và CloudEvents 1.0.
- Deserialize event, xử lý duplicate, xác nhận HTTP response và lưu công việc bền vững.
- Cấu hình retry/dead-letter, theo dõi delivery failure và kiểm thử tích hợp.

## 2. Luồng phát và nhận sự kiện

~~~mermaid
flowchart LR
    P["Spring Boot publisher"] --> SDK["EventGridPublisherClient"]
    SDK --> T["Event Grid topic / domain"]
    T --> F["Event subscription + filters"]
    F --> W["HTTP webhook"]
    F --> Q["Service Bus queue"]
    F --> H["Event Hubs"]
    W --> C1["Spring Boot webhook handler"]
    Q --> C2["Spring Boot Service Bus consumer"]
    H --> C3["EventProcessorClient"]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| Publisher | Tạo event theo contract và gửi đến endpoint |
| Topic/domain | Nhận event từ publisher; domain có thể chứa nhiều topic |
| Event subscription | Chọn event cần nhận bằng filter và cấu hình destination |
| Event handler | Nhận event qua webhook hoặc dịch vụ đích được hỗ trợ |
| Consumer application | Deserialize, validate, deduplicate và xử lý nghiệp vụ |
| Dead-letter destination | Lưu event không thể giao thành công để điều tra/replay |

**Event Grid là bộ định tuyến và giao event.** Topic/domain không phải event store để consumer đọc lại lịch sử tùy ý. Event được chuyển tới endpoint của subscription; nếu cần queue bền vững, dùng Service Bus; nếu cần stream và replay theo offset, dùng Event Hubs; nếu cần lưu dài hạn, dùng storage/archive.

## 3. Chọn schema trước khi tạo publisher

Topic hoặc domain được cấu hình một input schema. Publisher phải gửi đúng loại event tương ứng.

| Input schema của topic/domain | Kiểu Java khi dùng SDK | Đặc điểm |
|---|---|---|
| Event Grid schema | EventGridEvent | Envelope riêng của Azure: id, subject, eventType, eventTime, dataVersion, data |
| CloudEvents 1.0 | com.azure.core.models.CloudEvent | Envelope chuẩn hóa, có source, type, id, time, data |
| Custom schema | BinaryData | Ứng dụng tự định nghĩa cấu trúc JSON |

Không thể gửi EventGridEvent tới topic đang nhận CloudEvents hoặc ngược lại. Nếu publisher dùng sai generic type/schema, Event Grid trả lỗi Bad Request và không nhận event.

Có thể kiểm tra input schema bằng Azure CLI:

~~~bash
az eventgrid topic show \
  --name <topic-name> \
  --resource-group <resource-group> \
  --query inputSchema
~~~

Nên chọn CloudEvents khi muốn chia sẻ event contract giữa nhiều nền tảng hoặc cloud provider. Event Grid schema thuận tiện khi tích hợp các dịch vụ Azure và hệ sinh thái đã dùng envelope này. Custom schema chỉ nên dùng khi có contract riêng được quản lý chặt.

## 4. Dependency và BOM cho Spring Boot

### 4.1. Spring Cloud Azure Event Grid starter

Starter giúp Spring Boot tự cấu hình publisher client dựa trên endpoint và credential:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>SPRING_CLOUD_AZURE_BOM_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-eventgrid</artifactId>
    </dependency>
</dependencies>
~~~

Chọn SPRING_CLOUD_AZURE_BOM_VERSION theo phiên bản Spring Boot/Spring Cloud của dự án. Tại tài liệu hiện hành, Microsoft công bố các dòng BOM tương ứng với Spring Boot 4.x, 3.5.x và 2.x; hãy kiểm tra bảng version mapping trước khi nâng cấp. Dùng một BOM thống nhất để tránh trộn phiên bản Azure SDK và Spring Cloud Azure không tương thích.

### 4.2. Azure SDK for Java trực tiếp

Nếu cần tự tạo publisher client hoặc dùng CloudEvent/custom schema cụ thể, thêm SDK:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-eventgrid</artifactId>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
</dependency>
~~~

Có thể quản lý phiên bản bằng Azure SDK BOM (com.azure:azure-sdk-bom) hoặc dùng phiên bản SDK đã được BOM Spring Cloud Azure quản lý. Không tự thêm một phiên bản azure-messaging-eventgrid khác với phiên bản transitive của starter nếu chưa kiểm tra dependency tree.

### 4.3. Dependency cho consumer Service Bus

Nếu event subscription giao event tới Service Bus queue và Spring Boot nhận bằng Spring Cloud Stream binder, bổ sung:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-stream-binder-servicebus</artifactId>
</dependency>
~~~

Đây là dependency của **consumer Service Bus**. Event Grid starter chịu trách nhiệm publisher; Service Bus binder chịu trách nhiệm nhận message từ queue. Hai phần có thể chạy trong cùng ứng dụng hoặc tách thành hai service.

## 5. Danh tính và quyền truy cập

### 5.1. Publisher dùng Microsoft Entra ID

Ưu tiên Managed Identity hoặc workload identity để publisher không phải giữ access key trong cấu hình:

- Local development: dùng credential developer đã đăng nhập và được cấp quyền trên topic dev.
- App Service/VM: dùng system-assigned hoặc user-assigned Managed Identity.
- AKS: dùng Microsoft Entra Workload Identity.
- CI/CD: dùng workload identity federation với scope giới hạn.

Principal phát event cần role **EventGrid Data Sender** trên topic/domain hoặc scope phù hợp. Quyền Contributor/Owner quản lý resource không nên được cấp cho runtime chỉ để gửi event.

### 5.2. Quyền ở event handler là một luồng riêng

Publisher có quyền gửi tới topic không có nghĩa consumer tự động có quyền truy cập database, Service Bus hoặc webhook. Mỗi destination có cơ chế bảo vệ riêng:

| Luồng | Danh tính/quyền cần xem xét |
|---|---|
| Spring Boot → Event Grid topic | Publisher identity có EventGrid Data Sender |
| Event Grid → Service Bus queue | Managed identity của Event Grid subscription có Azure Service Bus Data Sender |
| Spring Boot consumer → Service Bus | Consumer identity có Azure Service Bus Data Receiver |
| Event Grid → webhook | TLS, endpoint authentication/authorization, validation handshake và network policy |
| Consumer → database/API | Identity và quyền của ứng dụng consumer trên hệ thống đích |

Nếu dùng access key hoặc SAS trong lab, lấy từ secret manager/biến môi trường, giới hạn phạm vi và thời hạn, rotate khi thay đổi nhân sự hoặc nghi ngờ lộ. Không commit key, token hay connection string vào Git.

## 6. Cấu hình Spring Boot với Event Grid starter

Ví dụ cấu hình endpoint và Managed Identity:

~~~yaml
spring:
  cloud:
    azure:
      eventgrid:
        endpoint: ${AZURE_EVENTGRID_ENDPOINT}
        event-schema: EVENT_GRID_EVENT
        credential:
          managed-identity-enabled: true
~~~

AZURE_EVENTGRID_ENDPOINT là endpoint của topic/domain. Với user-assigned identity, cấu hình client ID theo hướng dẫn credential của Spring Cloud Azure version đang dùng. Trong local development, dùng credential chain phù hợp; không giả định Managed Identity tồn tại trên máy lập trình.

Nếu môi trường lab dùng access key, starter cũng hỗ trợ cấu hình key theo tài liệu phiên bản tương ứng. Lưu key trong secret store và tránh đưa giá trị thật vào application.yml.

Starter hỗ trợ cấu hình schema qua property spring.cloud.azure.eventgrid.event-schema. Các giá trị gồm EVENT_GRID_EVENT (mặc định), CLOUD_EVENT và CUSTOM_EVENT. Chọn giá trị trùng với input schema của topic/domain; client được auto-configure tương ứng với EventGridEvent, CloudEvent hoặc BinaryData. Không chỉ đổi generic type trong code mà quên đổi event-schema trong cấu hình.

## 7. Phát EventGridEvent bằng starter

### 7.1. Inject publisher client

Với starter và topic dùng Event Grid schema, có thể inject publisher client vào service Spring:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridEvent;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import java.time.OffsetDateTime;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {
    private final EventGridPublisherClient<EventGridEvent> publisher;

    OrderEventPublisher(
            EventGridPublisherClient<EventGridEvent> publisher) {
        this.publisher = publisher;
    }

    public void publishOrderCreated(OrderCreatedPayload payload) {
        EventGridEvent event = new EventGridEvent(
                "/orders/" + payload.orderId(),
                "com.example.orders.created",
                BinaryData.fromObject(payload),
                "1.0")
                .setId(payload.eventId())
                .setEventTime(OffsetDateTime.now());

        publisher.sendEvent(event);
    }
}

record OrderCreatedPayload(
        String eventId,
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {}
~~~

Starter quản lý việc tạo client; service nghiệp vụ chỉ tạo event và gọi sendEvent. Trong ứng dụng thực tế, event ID nên được tạo từ outbox/business transaction và giữ nguyên khi retry, thay vì sinh ID mới cho mỗi lần gửi.

### 7.2. Gửi theo batch

SDK hỗ trợ gửi nhiều event trong một request:

~~~java
import java.util.List;

public void publishBatch(List<EventGridEvent> events) {
    if (events.isEmpty()) {
        return;
    }
    publisher.sendEvents(events);
}
~~~

Batch giảm overhead request khi publisher có nhiều event. Cần kiểm tra giới hạn payload/batch của loại topic và kích thước event; chia batch khi vượt giới hạn. Không gom event vô hạn trong bộ nhớ khi producer nhanh hơn dịch vụ.

### 7.3. Gửi là chưa đồng nghĩa xử lý xong

Khi sendEvent trả thành công, publisher đã nhận phản hồi thành công từ Event Grid. Điều đó không chứng minh event subscription đã giao tới endpoint hoặc consumer đã hoàn tất nghiệp vụ. Theo dõi delivery metrics và kết quả ở consumer riêng.

Nếu ứng dụng cập nhật database rồi phát event, cân nhắc transactional outbox để tránh trường hợp DB commit nhưng publish thất bại. Timeout khi publish có thể tạo kết quả không xác định; giữ event ID ổn định và thiết kế consumer idempotent.

## 8. Phát CloudEvent bằng Azure SDK

CloudEvents dùng com.azure.core.models.CloudEvent. Ví dụ tạo async publisher client bằng Microsoft Entra credential:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.core.models.CloudEvent;
import com.azure.core.models.CloudEventDataFormat;
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridPublisherAsyncClient;
import com.azure.messaging.eventgrid.EventGridPublisherClientBuilder;
import java.util.Map;

class CloudEventPublisher {
    private final EventGridPublisherAsyncClient<CloudEvent> publisher;

    CloudEventPublisher(String endpoint, TokenCredential credential) {
        this.publisher = new EventGridPublisherClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildCloudEventPublisherAsyncClient();
    }

    void publish(String eventId, String orderId) {
        CloudEvent event = new CloudEvent(
                "urn:example:orders-service",
                "com.example.orders.created",
                BinaryData.fromObject(Map.of(
                        "orderId", orderId,
                        "status", "CREATED")),
                CloudEventDataFormat.JSON,
                "application/json")
                .setId(eventId);

        publisher.sendEvent(event).block();
    }
}
~~~

DefaultAzureCredential có thể được tạo bằng new DefaultAzureCredentialBuilder().build() và truyền vào constructor. Trong Spring Boot, đăng ký credential và publisher client thành bean dùng lại theo lifecycle ứng dụng; không tạo client mới trên mỗi request. Với luồng reactive, không gọi block() trên event loop mà compose Mono trả về từ async client.

Không dùng publisher này nếu topic đang nhận Event Grid schema. Schema của topic/domain phải khớp kiểu CloudEvent.

## 9. Custom event schema

Khi topic được cấu hình custom schema, SDK dùng BinaryData làm generic type:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import java.util.Map;

class CustomEventPublisher {
    private final EventGridPublisherClient<BinaryData> publisher;

    CustomEventPublisher(
            EventGridPublisherClient<BinaryData> publisher) {
        this.publisher = publisher;
    }

    void publish(String orderId) {
        Map<String, Object> event = Map.of(
                "id", "order-" + orderId,
                "subject", "/orders/" + orderId,
                "eventType", "OrderCreated",
                "dataVersion", "1.0",
                "data", Map.of("orderId", orderId));

        publisher.sendEvent(BinaryData.fromObject(event));
    }
}
~~~

Custom schema yêu cầu producer và consumer thống nhất field, version và validation. Nếu nhiều service cùng dùng event, CloudEvents hoặc Event Grid schema thường dễ liên thông hơn custom envelope riêng.

## 10. Nhận event: chọn event handler

Event Grid không có receiver client trong Java SDK. Cách nhận phụ thuộc endpoint của event subscription:

| Destination | Cách Spring Boot nhận |
|---|---|
| Webhook HTTP | @RestController nhận POST và xác thực endpoint |
| Service Bus queue/topic | Azure Service Bus SDK hoặc Spring Cloud Stream Service Bus binder |
| Event Hubs | EventProcessorClient hoặc Spring Cloud Stream Event Hubs binder |
| Storage Queue | Azure Storage Queue SDK hoặc binder phù hợp |
| Azure Function/Logic App | Trigger/connector do nền tảng quản lý |

Chọn webhook khi muốn endpoint HTTP phản hồi trực tiếp với Event Grid. Chọn Service Bus khi cần queue bền vững, competing consumers, DLQ và khả năng tách delivery khỏi thời gian xử lý nghiệp vụ. Event Grid có thể giao event tới Service Bus, sau đó consumer xử lý độc lập.

## 11. Nhận Event Grid schema qua Spring Boot webhook

### 11.1. Subscription validation

Khi tạo event subscription trỏ tới webhook, Event Grid phải xác minh endpoint trước khi gửi event bình thường. Với **Event Grid schema**, Event Grid gửi một event có type:

Microsoft.EventGrid.SubscriptionValidationEvent

Payload chứa data.validationCode. Endpoint phải trả HTTP 200 cùng JSON:

~~~json
{
  "validationResponse": "<validationCode>"
}
~~~

Đây là handshake chứng minh endpoint chấp nhận đăng ký. Nó không thay thế authentication/authorization cho các request gửi tới webhook.

### 11.2. Controller nhận event và trả validation response

Azure SDK EventGridEvent.fromString có thể deserialize một event hoặc một JSON array thành danh sách event:

~~~java
import com.azure.messaging.eventgrid.EventGridEvent;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/event-grid")
class EventGridWebhookController {
    private final EventInbox eventInbox;

    EventGridWebhookController(EventInbox eventInbox) {
        this.eventInbox = eventInbox;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<?> receive(@RequestBody String body) {
        List<EventGridEvent> events = EventGridEvent.fromString(body);

        if (events.size() == 1
                && "Microsoft.EventGrid.SubscriptionValidationEvent"
                    .equals(events.get(0).getEventType())) {

            if (events.get(0).getData() == null) {
                return ResponseEntity.badRequest().build();
            }
            Map<?, ?> data = events.get(0).getData().toObject(Map.class);
            Object validationCode = data.get("validationCode");

            if (validationCode == null) {
                return ResponseEntity.badRequest().build();
            }

            return ResponseEntity.ok(
                    Map.of("validationResponse", validationCode));
        }

        for (EventGridEvent event : events) {
            // Lưu inbox bền vững và deduplicate theo event.getId().
            eventInbox.persistIfAbsent(
                    event.getId(),
                    event.getEventType(),
                    event.getData() == null
                            ? new byte[0]
                            : event.getData().toBytes());
        }

        // Chỉ ACK sau khi đã lưu công việc bền vững.
        return ResponseEntity.accepted().build();
    }
}
~~~

EventInbox là service ứng dụng cần triển khai với database/queue bền vững và unique constraint trên event ID. Không chỉ đưa event vào queue RAM rồi trả 202; process có thể dừng sau ACK và làm mất công việc. Nếu lưu inbox thất bại, để exception được chuyển thành response lỗi phù hợp để Event Grid thử giao lại.

Trong production, kiểm tra topic/source và event type mong đợi, giới hạn body size, validate schema và xác thực endpoint. Không log toàn bộ payload nếu có dữ liệu nhạy cảm.

### 11.3. Xử lý nhiều event trong một request

Event Grid thường gửi payload dưới dạng array, kể cả khi chỉ có một event. Controller nên xử lý tất cả phần tử trong body. Validation event được gửi riêng theo quy trình subscription validation; sau khi xác minh thành công, các event nghiệp vụ mới được giao.

Không giả định thứ tự event trong array là thứ tự toàn cục của hệ thống. Consumer phải dùng event ID, aggregate version và idempotency để bảo vệ trạng thái.

## 12. Nhận CloudEvents 1.0 qua webhook

CloudEvents 1.0 sử dụng cơ chế bảo vệ webhook khác Event Grid schema. Thay vì gửi SubscriptionValidationEvent, Event Grid gửi HTTP OPTIONS preflight với header WebHook-Request-Origin. Endpoint đồng ý nhận event bằng cách trả các header WebHook-Allowed-Origin và WebHook-Allowed-Rate.

~~~java
import com.azure.core.models.CloudEvent;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/webhooks/cloudevents")
class CloudEventWebhookController {
    private final CloudEventInbox inbox;
    private final String allowedOrigin;

    CloudEventWebhookController(
            CloudEventInbox inbox,
            @org.springframework.beans.factory.annotation.Value(
                    "${app.eventgrid.webhook.allowed-origin}") String allowedOrigin) {
        this.inbox = inbox;
        this.allowedOrigin = allowedOrigin;
    }

    @RequestMapping(method = RequestMethod.OPTIONS)
    ResponseEntity<Void> validate(
            @RequestHeader("WebHook-Request-Origin") String requestedOrigin) {

        if (!allowedOrigin.equals(requestedOrigin)) {
            return ResponseEntity.status(403).build();
        }

        return ResponseEntity.ok()
                .header("WebHook-Allowed-Origin", requestedOrigin)
                .header("WebHook-Allowed-Rate", "600")
                .allow(HttpMethod.POST)
                .build();
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> receive(
            @RequestBody String body,
            @RequestHeader(value = HttpHeaders.ORIGIN, required = false)
                    String origin) {

        if (!allowedOrigin.equals(origin)) {
            return ResponseEntity.status(403).build();
        }

        List<CloudEvent> events = CloudEvent.fromString(body);

        for (CloudEvent event : events) {
            inbox.persistIfAbsent(
                    event.getId(),
                    event.getType(),
                    event.getData() == null
                            ? new byte[0]
                            : event.getData().toBytes());
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

Giá trị WebHook-Allowed-Rate là số request mỗi phút mà endpoint chấp nhận theo hợp đồng webhook; chọn theo capacity thực tế, không copy giá trị minh họa vào production. Event Grid gửi Origin trong các request delivery sau handshake; endpoint nên kiểm tra origin đã thỏa thuận.

Ví dụ cấu hình origin sender được cho phép trong ứng dụng webhook:

~~~yaml
app:
  eventgrid:
    webhook:
      allowed-origin: eventgrid.azure.net
~~~

Thay giá trị minh họa bằng origin thực tế mà endpoint đã chấp thuận trong handshake. Nếu dùng nhiều sender, quản lý allow-list thay vì chấp nhận mọi origin.

CloudEvents abuse-protection handshake **không phải authentication**. Vẫn cần cơ chế xác thực/authorization cho webhook, giới hạn network, TLS và kiểm tra nguồn event.

## 13. Nhận event qua Service Bus queue

Nếu muốn tách thời gian giao event khỏi thời gian xử lý nghiệp vụ, cấu hình event subscription destination là **Service Bus queue**. Event Grid giao event vào queue; Spring Boot consumer nhận bằng Service Bus binder.

### 13.1. Cấu hình binding

Ví dụ cấu hình function binding:

~~~yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
      servicebus:
        namespace: ${AZURE_SERVICEBUS_NAMESPACE}
    function:
      definition: consume
    stream:
      bindings:
        consume-in-0:
          destination: ${AZURE_EVENTGRID_QUEUE_NAME}
~~~

Dependency cần spring-cloud-azure-stream-binder-servicebus và BOM tương thích. Consumer identity cần Azure Service Bus Data Receiver trên queue. Event Grid subscription identity cần Azure Service Bus Data Sender để gửi event vào queue.

### 13.2. Consumer function xử lý payload

Queue nhận JSON event do Event Grid giao. Ví dụ với Event Grid schema:

~~~java
import com.azure.messaging.eventgrid.EventGridEvent;
import java.util.List;
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class EventGridQueueConsumer {
    @Bean
    Consumer<Message<String>> consume(EventInbox eventInbox) {
        return message -> {
            List<EventGridEvent> events =
                    EventGridEvent.fromString(message.getPayload());

            for (EventGridEvent event : events) {
                eventInbox.persistIfAbsent(
                        event.getId(),
                        event.getEventType(),
                        event.getData() == null
                                ? new byte[0]
                                : event.getData().toBytes());
            }
        };
    }
}
~~~

Trong ứng dụng thực tế, chọn settlement/auto-complete phù hợp với Service Bus binder version. Chỉ complete message sau khi database transaction hoặc công việc bền vững đã hoàn tất. Nếu dùng inbox, lưu event ID và side effect trong cùng transaction; khi xử lý lỗi tạm thời, để message được giao lại theo policy của Service Bus.

### 13.3. Phân biệt retry của Event Grid và retry của Service Bus

Khi Event Grid giao thành công vào Service Bus queue, Event Grid coi delivery tới destination hoàn tất. Retry sau đó thuộc trách nhiệm Service Bus và consumer. Nếu dùng webhook trực tiếp, Event Grid theo dõi HTTP response của webhook. Hai tầng retry có cấu hình và DLQ riêng; cần theo dõi cả hai.

## 14. Delivery semantics, duplicate và ordering

Event Grid giao event theo mô hình **at-least-once**: một event có thể được gửi lại nếu endpoint timeout, trả lỗi hoặc phản hồi bị mất. Event Grid không bảo đảm thứ tự giao event toàn cục.

Consumer cần:
- Dùng event ID ổn định để deduplicate.
- Đặt unique constraint trong inbox/processed-event table.
- Ghi dedup record và thay đổi nghiệp vụ trong cùng transaction.
- Dùng aggregate version nếu trạng thái nghiệp vụ phải theo thứ tự.
- Trả response thành công sau khi đã nhận trách nhiệm xử lý bền vững.
- Không gửi email, thanh toán hoặc gọi API không idempotent trước khi có idempotency key ở hệ thống đích.

Event Grid không thay thế Event Hubs khi cần event log có partition/offset hoặc Service Bus khi cần lock/complete, session và DLQ queue semantics.

## 15. Retry, HTTP response và dead-letter

Event Grid dùng HTTP response để xác định delivery đã thành công hay cần thử lại. Với webhook, các response 200, 201, 202, 203 và 204 được xem là ACK thành công. Các response khác được xem là lỗi; hành vi retry phụ thuộc status code và loại endpoint.

| Response | Ý nghĩa vận hành |
|---|---|
| 200/201/202/203/204 | Endpoint đã nhận event; Event Grid coi delivery thành công |
| 5xx | Lỗi phía server, thường có thể được retry |
| 408/timeout | Event Grid có thể thử lại |
| 400 | Lỗi request không hợp lệ; webhook không được retry theo policy thông thường |
| 401/403 | Lỗi xác thực/phân quyền; webhook không được retry theo policy thông thường |
| 413 | Payload quá lớn; không được retry theo policy thông thường |

Mặc định, dead-letter không tự bật cho mọi event subscription. Cấu hình dead-letter destination (thường là Blob Storage) nếu không muốn event bị bỏ khi hết retry hoặc gặp lỗi cấu hình. Đặt TTL/max delivery attempts theo SLO và khả năng khôi phục.

Khi nhận event:
- Trả 202 sau khi lưu vào inbox/queue bền vững.
- Trả 5xx cho lỗi tạm thời khiến ứng dụng chưa thể nhận trách nhiệm xử lý.
- Không trả 400 chỉ vì downstream database đang tạm thời không khả dụng.
- Với event không hợp lệ vĩnh viễn, cân nhắc quarantine và ACK sau khi lưu quarantine thành công, hoặc cấu hình dead-letter phù hợp.
- Không ACK trước khi event được lưu bền vững.

Dead-letter destination cũng cần quyền, encryption, lifecycle, alert và runbook replay. Nếu dead-letter storage không tồn tại hoặc không truy cập được, event vẫn có thể bị mất theo policy dịch vụ.

## 16. Transactional outbox khi phát event

Nếu nghiệp vụ ghi database rồi gọi Event Grid trong cùng request, hai thao tác không atomic. Có thể xảy ra:
- Database commit thành công nhưng publish thất bại.
- Publish thành công nhưng database rollback.
- Publish thành công nhưng response bị mất và publisher retry gây duplicate.

Transactional outbox ghi event cần phát trong cùng transaction với dữ liệu nghiệp vụ:

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Database transaction"]
    TX --> ORDER["Update order"]
    TX --> OUTBOX["Insert outbox event"]
    OUTBOX --> WORKER["Outbox publisher"]
    WORKER --> EG["Event Grid topic"]
    EG --> SUB["Event subscription"]
    SUB --> CONSUMER["Idempotent consumer"]
~~~

Worker đọc outbox, gửi event và đánh dấu đã publish. Nếu worker chết sau send nhưng trước khi đánh dấu, event có thể được gửi lại; consumer vẫn cần dedup theo event ID. Outbox giúp không quên phát event sau commit, nhưng không tạo exactly-once xuyên database và Event Grid.

## 17. Monitoring và vận hành

Theo dõi cả publisher, Event Grid subscription và consumer:

| Nhóm | Chỉ số cần theo dõi |
|---|---|
| Publisher | Send success/failure, latency, throttling, 401/403, payload size |
| Event subscription | Delivery success/failure, attempts, matched/unmatched events, filter behavior |
| Webhook | Request count, 2xx/4xx/5xx, latency, validation failures |
| Service Bus destination | Active message count, oldest message age, DLQ count, lock/settlement failures |
| Consumer | Processing duration, duplicate suppressed, inbox backlog, business failure |
| Dead-letter | Event count, tuổi event, nguyên nhân và tỷ lệ replay |
| Security | Identity, RBAC changes, secret rotation, unauthorized request |

Dùng correlation ID, event ID và subscription name để nối publisher log với consumer log. Không ghi access key, SAS token, Authorization header hoặc payload chứa dữ liệu nhạy cảm.

Cảnh báo khi delivery failure tăng, webhook 401/403/5xx, DLQ có event mới, Service Bus backlog tăng hoặc consumer không tiến xử lý. Mỗi alert cần owner, dashboard và runbook xác minh endpoint, identity, RBAC, network và schema.

## 18. Kiểm thử tích hợp

Tạo topic, event subscription, Service Bus queue và dead-letter storage riêng cho test. Không dùng endpoint production để thử validation hoặc cố tình trả lỗi.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Publish EventGridEvent | Dùng starter/SDK gửi event | Topic nhận đúng schema |
| Publish CloudEvent | Dùng CloudEvent publisher | Topic CloudEvents nhận đúng envelope |
| Schema mismatch | Gửi EventGridEvent tới topic CloudEvents | Publisher nhận Bad Request |
| Batch publish | Gửi nhiều event trong một request | Event subscription nhận đủ event |
| Event Grid validation | Tạo webhook subscription Event Grid schema | Endpoint trả validationResponse đúng |
| CloudEvents preflight | Gửi OPTIONS với WebHook-Request-Origin | Endpoint trả Allowed-Origin và Allowed-Rate |
| Duplicate delivery | Gửi lại cùng event ID hoặc mô phỏng retry | Inbox ngăn side effect lặp |
| Webhook timeout | Làm handler chậm hơn deadline | Event Grid retry theo policy |
| HTTP 5xx | Trả lỗi tạm thời trong test | Event được retry hoặc dead-letter |
| HTTP 400/403 | Gửi lỗi cấu hình | Xác minh dead-letter và không giả định retry |
| Service Bus destination | Event subscription giao vào queue | Consumer binder nhận được event |
| Consumer lỗi | Làm database test tạm thời không khả dụng | Message không bị complete sớm |
| Dead-letter | Cố ý làm destination lỗi theo kịch bản test | Event được ghi vào dead-letter storage |
| Filter | Gửi event type/subject khác nhau | Chỉ event thỏa filter được giao |
| Cross-environment access | Dùng identity dev gửi tới topic prod | RBAC từ chối |

Unit test kiểm tra event contract, schema validation và idempotency. Cloud integration test mới xác minh được Entra ID, RBAC, subscription validation, delivery retry, dead-letter và Service Bus destination thật.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Publisher 401/403 | Sai credential hoặc thiếu EventGrid Data Sender | Kiểm tra runtime principal và role scope |
| Publisher 400 | Generic client không khớp input schema | Kiểm tra topic inputSchema |
| Event publish thành công nhưng không thấy consumer | Chưa tạo subscription, filter không match hoặc destination sai | Kiểm tra subscription và delivery metrics |
| Webhook subscription không tạo được | Validation handshake không hoàn tất | Kiểm tra response body/status, OPTIONS và WAF |
| Webhook nhận duplicate | At-least-once delivery hoặc response bị mất | Inbox/dedup theo event ID |
| Webhook trả 202 nhưng mất việc | ACK trước khi lưu bền vững | Persist vào inbox/queue trước response |
| Event bị drop khi endpoint trả 400/403 | Status code không được retry theo policy webhook | Sửa auth/schema và cấu hình dead-letter |
| Consumer Service Bus không nhận | Sai queue/binder hoặc thiếu Data Receiver | Kiểm tra destination, identity và role |
| Event Grid không ghi vào Service Bus | Event Grid identity thiếu Data Sender | Gán role cho identity của subscription |
| Event đến sai thứ tự | Event Grid không bảo đảm global ordering | Dùng aggregate version và state transition guard |

## 20. Checklist trước production

- **Schema:** Topic/domain input schema được xác định; publisher generic type khớp.
- **Dependency:** Spring Cloud Azure BOM tương thích Spring Boot; không trộn phiên bản SDK.
- **Publisher:** Client dùng lại theo lifecycle, timeout/retry được theo dõi, event ID ổn định.
- **Identity:** Publisher có EventGrid Data Sender; không hardcode key/SAS.
- **Subscription:** Filter, endpoint, retry policy và dead-letter được cấu hình rõ.
- **Receiver:** Webhook có validation/authentication; hoặc Service Bus queue có consumer identity và role phù hợp.
- **Acknowledgement:** Chỉ trả 2xx sau khi đã nhận trách nhiệm xử lý bền vững.
- **Reliability:** Consumer idempotent, duplicate-safe, không giả định event order.
- **Dead-letter:** Storage có quyền, encryption, lifecycle, alert và replay procedure.
- **Observability:** Delivery failures, webhook status, queue backlog, DLQ và business processing được theo dõi.
- **Testing:** Đã kiểm thử schema mismatch, validation, duplicate, timeout, retry, DLQ và RBAC denial.
- **Cost:** Số event, số delivery, retry/fan-out, storage dead-letter, network và monitoring đã được dự toán.

## 21. Tổng kết

Azure Event Grid publisher gửi event vào topic/domain bằng EventGridPublisherClient; Spring Cloud Azure Event Grid starter có thể auto-configure publisher cho Spring Boot. Event Grid Java SDK không có receiver client. Event được nhận tại event handler đã cấu hình: webhook HTTP, Service Bus, Event Hubs, Storage Queue hoặc dịch vụ hỗ trợ khác.

Khi phát event, phải chọn đúng EventGridEvent, CloudEvent hoặc custom schema và dùng Microsoft Entra ID với role EventGrid Data Sender khi có thể. Khi nhận event, phải hoàn tất validation handshake, lưu công việc bền vững trước ACK, xử lý duplicate và cấu hình dead-letter. Event Grid giao at-least-once và không bảo đảm thứ tự; consumer cần idempotency và correlation để hệ thống phục hồi an toàn.

## Tài liệu tham khảo

- [Azure Event Grid client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/messaging-eventgrid-readme?view=azure-java-stable)
- [CloudEvent class in Azure SDK for Java](https://learn.microsoft.com/en-us/java/api/com.azure.core.models.cloudevent?view=azure-java-stable)
- [Use Azure Event Grid in Spring Boot](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-initializer-java-app-with-event-grid)
- [Spring Cloud Azure developer guide](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
- [Spring Cloud Azure configuration properties](https://microsoft.github.io/spring-cloud-azure/current/reference/html/appendix.html)
- [Validate webhook endpoints with Event Grid schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-event-grid-events-schema)
- [Endpoint validation with CloudEvents schema](https://learn.microsoft.com/en-us/azure/event-grid/end-point-validation-cloud-events-schema)
- [Event Grid delivery and retry](https://learn.microsoft.com/en-us/azure/event-grid/delivery-and-retry)
- [Set dead-letter location and retry policy](https://learn.microsoft.com/en-us/azure/event-grid/manage-event-delivery)

