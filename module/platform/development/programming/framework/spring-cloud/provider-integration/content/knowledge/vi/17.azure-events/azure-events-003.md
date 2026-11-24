# Gửi sự kiện và vận hành Event Hubs processor

Azure Event Hubs không chỉ là một endpoint để gửi event. Một hệ thống production cần quản lý vòng đời producer, gom event thành batch phù hợp, chọn partition key, xác thực danh tính, xử lý kết quả gửi không xác định, vận hành consumer phân tán, lưu checkpoint và giám sát độ trễ. Nếu producer tạo client liên tục, consumer checkpoint sai thời điểm hoặc ứng dụng nuốt exception, hệ thống có thể tăng chi phí, mất tiến độ xử lý hoặc tạo side effect trùng lặp.

Trong chương **Sự kiện Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, bài học này hướng dẫn tích hợp Spring Boot với Azure Event Hubs qua Azure SDK for Java và Spring Cloud Azure phù hợp. Trọng tâm là **gửi event an toàn**, **vận hành EventProcessorClient**, cấu hình Managed Identity và Azure RBAC, quản lý checkpoint/ownership, xử lý lỗi, giám sát và kiểm thử trên môi trường riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả vòng đời producer và consumer khi làm việc với Event Hubs.
- Gửi event đơn lẻ hoặc theo batch bằng Azure SDK for Java.
- Chọn partition key và truyền metadata như event ID, schema version, correlation ID.
- Quản lý producer client dùng lại trong Spring Boot và đóng tài nguyên đúng lúc.
- Cấu hình EventProcessorClient với consumer group, Blob checkpoint store và workload identity.
- Hiểu cách processor start/stop, nhận ownership, xử lý event, cập nhật checkpoint và báo lỗi.
- Xử lý timeout, throttling, duplicate, poison event, checkpoint failure và graceful shutdown.
- Phân quyền Event Hubs Data Sender/Receiver và Storage Blob Data Contributor theo nguyên tắc tối thiểu.
- Kiểm thử producer/processor, theo dõi consumer lag, partition ownership và chi phí vận hành.

## 2. Kiến trúc producer và processor

Một ứng dụng có thể vừa phát event vừa tiêu thụ event, nhưng hai vai trò nên có cấu hình và quyền rõ ràng. Producer gửi dữ liệu vào event hub; processor đọc stream trong một consumer group, phối hợp ownership giữa các instance và lưu tiến độ vào checkpoint store.

~~~mermaid
flowchart LR
    API["Spring Boot API"] --> PR["EventHubProducerClient"]
    PR --> EH["Azure Event Hubs"]
    EH --> P0["Partition 0"]
    EH --> P1["Partition 1"]
    EH --> P2["Partition 2"]
    P0 --> EP["EventProcessorClient"]
    P1 --> EP
    P2 --> EP
    EP --> DB["Business database"]
    EP <--> CP["Blob checkpoint store"]
    EP --> OBS["Logs / metrics / tracing"]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Vòng đời |
|---|---|---|
| Producer client | Tạo batch, gửi event, áp dụng retry/timeout của SDK | Dùng lại trong thời gian sống của ứng dụng |
| Event Hub | Tiếp nhận và lưu event theo partition trong retention | Do Azure quản lý |
| Consumer group | Lưu vị trí đọc logic độc lập cho một workload | Tồn tại theo cấu hình Event Hubs |
| EventProcessorClient | Đọc event, phân phối partition ownership và gọi handler | Start khi ứng dụng sẵn sàng; stop khi shutdown |
| Blob checkpoint store | Lưu ownership và checkpoint của processor | Tài nguyên riêng, tồn tại lâu dài |
| Business handler | Validate, xử lý nghiệp vụ, deduplicate và ghi dữ liệu | Do ứng dụng quản lý |
| Observability | Đo throughput, lag, lỗi, checkpoint và sức khỏe worker | Vận hành liên tục |

**Event Hubs không lưu trạng thái nghiệp vụ đã xử lý.** Nó giữ event theo retention; ứng dụng phải quản lý kết quả xử lý, idempotency và checkpoint.

## 3. Chuẩn bị namespace, event hub và danh tính

Trước khi viết code, xác định rõ:

- **Namespace FQDN:** ví dụ `orders-dev.servicebus.windows.net`.
- **Event hub name:** ví dụ `order-events`.
- **Consumer group:** ví dụ `order-projection`; mỗi workload logic có group riêng.
- **Checkpoint container:** ví dụ container `eventhub-checkpoints` trong một storage account phù hợp.
- **Environment:** dev, test, staging hay production.
- **Region và tier/capacity:** phù hợp throughput, retention và yêu cầu vận hành.
- **Runtime principal:** Managed Identity hoặc workload identity mà Spring Boot thực sự sử dụng.

Tạo event hub và container checkpoint bằng IaC hoặc quy trình platform có kiểm soát. Không nên để mỗi lần Spring Boot khởi động tự tạo namespace, event hub hoặc container production; runtime chỉ nên có quyền sử dụng tài nguyên đã được provision.

### 3.1. Quyền cho producer và processor

| Vai trò | Tài nguyên | Azure role gợi ý |
|---|---|---|
| Producer | Event hub/namespace đích | **Azure Event Hubs Data Sender** |
| Consumer processor | Event hub/namespace nguồn | **Azure Event Hubs Data Receiver** |
| Processor checkpoint | Blob container lưu ownership/checkpoint | **Storage Blob Data Contributor** |
| Platform/IaC | Tạo namespace, hub, storage account, container và role assignment | Quyền quản lý ở scope triển khai, tách khỏi runtime |

Gán role ở scope nhỏ nhất mà dịch vụ và kiến trúc cho phép. Role quản lý namespace/resource không tự động thay thế quyền data-plane. Ngược lại, Data Sender không cần quyền tạo hoặc xóa event hub.

Checkpoint store là một tài nguyên độc lập: processor có thể đọc Event Hubs thành công nhưng không cân bằng ownership hoặc lưu checkpoint được nếu thiếu quyền Blob. Container nên được tạo trước bằng IaC; workload cần quyền đọc/ghi blob phù hợp.

### 3.2. Xác thực bằng Managed Identity

Ưu tiên Microsoft Entra ID và workload identity khi môi trường hỗ trợ:
- Local development: credential developer đã đăng nhập và được cấp quyền dev.
- Azure App Service/VM: Managed Identity theo cấu hình dịch vụ.
- AKS: Workload Identity cho Kubernetes workload.
- CI/CD: workload identity federation hoặc service connection được giới hạn.

Không commit SAS token, connection string hay secret vào repository. Nếu phải dùng SAS, giới hạn entity, quyền Send/Listen và thời hạn; lưu trong secret manager, rotate và audit. Không cấp quyền Manage cho workload chỉ cần gửi hoặc nhận event.

## 4. Chọn Azure SDK và Spring Cloud Azure

Có hai hướng tích hợp phổ biến:

**Azure SDK trực tiếp:** phù hợp khi cần kiểm soát chi tiết producer batch, EventProcessorClient, checkpoint store, callback, retry và lifecycle. Đây là hướng minh họa chính trong bài.

**Spring Cloud Azure:** cung cấp starter và auto-configuration để tích hợp dịch vụ Azure theo phong cách Spring Boot. Tên artifact, property, annotation và API có thể thay đổi theo major version. Trước khi dùng:
- Chọn BOM Spring Cloud Azure tương thích với Spring Boot đang chạy.
- Xác minh starter có expose các thao tác cần thiết như checkpoint, manual processing, partition context và lifecycle.
- Tránh tạo client thủ công trùng với bean auto-configured.
- Khi cần điều khiển partition ownership/checkpoint chi tiết, cân nhắc dùng EventProcessorClient trực tiếp như một Spring bean.

Các dependency Java thường cần cho ví dụ:
- `azure-messaging-eventhubs`
- `azure-messaging-eventhubs-checkpointstore-blob`
- `azure-storage-blob`
- `azure-identity`
- Spring Boot configuration và dependency injection

Dùng BOM hoặc dependency management để đồng bộ phiên bản Azure SDK; không tự chọn các phiên bản rời rạc mà chưa kiểm tra compatibility.

## 5. Cấu hình Spring Boot theo môi trường

Ví dụ cấu hình tự định nghĩa:

~~~yaml
app:
  event-hubs:
    namespace: orders-dev.servicebus.windows.net
    event-hub-name: order-events
    consumer-group: order-projection
    checkpoint-container-url: https://ordersdevstore.blob.core.windows.net/eventhub-checkpoints
    partition-key-field: orderId
~~~

Các khóa dưới `app.event-hubs.*` là property của ứng dụng trong ví dụ, **không phải property mặc định chung của mọi Spring Cloud Azure version**. Bind bằng `@ConfigurationProperties`, validate lúc startup và cấp giá trị từ deployment config.

Dev, test, staging và production cần namespace/hub, consumer group và checkpoint container phù hợp. Không để profile test vô tình dùng endpoint hoặc checkpoint production. Cần xác minh cả:
- Namespace và event hub name.
- Consumer group.
- Storage account/container checkpoint.
- Runtime principal và tenant.
- Region/environment manifest.
- Network endpoint, DNS và private access.

Profile chỉ chọn cấu hình; RBAC mới là lớp thực thi quyền. Nếu cấu hình sai trỏ tới resource production, identity dev vẫn cần bị từ chối tại resource đích.

## 6. Gửi event bằng EventHubProducerClient

### 6.1. Tạo producer client dùng lại

Azure SDK client nên được tạo một lần theo lifecycle ứng dụng và tái sử dụng. Không khởi tạo client mới cho từng HTTP request vì điều đó làm tăng chi phí thiết lập kết nối, tài nguyên mạng và độ trễ.

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@ConfigurationProperties(prefix = "app.event-hubs")
record EventHubProperties(
        String namespace,
        String eventHubName,
        String consumerGroup,
        String checkpointContainerUrl) {}

@Configuration
@EnableConfigurationProperties(EventHubProperties.class)
class EventHubProducerConfiguration {

    @Bean
    DefaultAzureCredential azureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    @Bean(destroyMethod = "close")
    EventHubProducerClient eventHubProducerClient(
            EventHubProperties properties,
            DefaultAzureCredential credential) {
        return new EventHubClientBuilder()
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .buildProducerClient();
    }
}
~~~

Đoạn code giả định namespace có dạng FQDN, event hub đã tồn tại và runtime principal có **Azure Event Hubs Data Sender**. DefaultAzureCredential chọn credential theo môi trường; hãy xác minh credential hiệu lực khi chạy trên cloud. Bean dùng `destroyMethod = "close"` để giải phóng client khi Spring context dừng.

### 6.2. Gửi một event

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import org.springframework.stereotype.Service;

@Service
class TelemetryPublisher {
    private final EventHubProducerClient producer;

    TelemetryPublisher(EventHubProducerClient producer) {
        this.producer = producer;
    }

    void publish(String jsonPayload) {
        EventData event = new EventData(jsonPayload);
        producer.send(java.util.List.of(event));
    }
}
~~~

Lệnh `send` hoàn tất có nghĩa producer đã nhận xác nhận theo semantics của SDK/service cho thao tác gửi; **không có nghĩa consumer đã đọc hoặc xử lý event**. Nếu cần theo dõi end-to-end, payload phải có event ID/correlation ID và consumer phát metric hoặc kết quả nghiệp vụ riêng.

Không gửi object Java tùy ý nếu chưa định nghĩa serialization. Nên dùng schema JSON/Avro/Protobuf có version, giới hạn kích thước và kiểm tra nội dung trước khi gửi.

### 6.3. Gửi theo batch

Batch giúp tận dụng dung lượng request và giảm overhead khi gửi nhiều event. Event Hubs có giới hạn kích thước batch/message theo tier và cấu hình; không nên hardcode một payload size tùy ý.

~~~java
import com.azure.messaging.eventhubs.CreateBatchOptions;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import java.util.List;

class BatchedEventPublisher {
    private final EventHubProducerClient producer;

    BatchedEventPublisher(EventHubProducerClient producer) {
        this.producer = producer;
    }

    void publishBatch(List<String> payloads, String partitionKey) {
        CreateBatchOptions options =
                new CreateBatchOptions().setPartitionKey(partitionKey);
        EventDataBatch batch = producer.createBatch(options);

        for (String payload : payloads) {
            EventData event = new EventData(payload);
            if (!batch.tryAdd(event)) {
                if (batch.getCount() == 0) {
                    throw new IllegalArgumentException(
                            "A single event exceeds the batch size limit");
                }

                producer.send(batch);
                batch = producer.createBatch(options);

                if (!batch.tryAdd(event)) {
                    throw new IllegalArgumentException(
                            "A single event exceeds the batch size limit");
                }
            }
        }

        if (batch.getCount() > 0) {
            producer.send(batch);
        }
    }
}
~~~

Đây là ví dụ đồng bộ minh họa cách chia batch. Trong production cần:
- Kiểm tra batch rỗng trước khi gửi và không bỏ sót event không thêm được.
- Giới hạn số event/byte trong bộ đệm ứng dụng.
- Xử lý lỗi gửi từng batch và xác định event nào cần retry.
- Không giữ một danh sách vô hạn trong heap khi producer nhanh hơn dịch vụ.
- Dùng client dùng lại và đo thời gian tạo batch/gửi batch.
- Khi dùng partition key, mọi event trong batch được định tuyến theo key đó; key có thể tạo hot partition nếu phân bố lệch.

Không chia một event quá lớn thành nhiều event tùy tiện nếu consumer không có contract ghép lại. Với payload lớn, cân nhắc lưu nội dung trong Blob Storage và gửi reference có quyền truy cập giới hạn.

### 6.4. Gắn metadata và event ID

Một event nên chứa:
- `eventId`: ID nghiệp vụ duy nhất, ổn định qua retry.
- `eventType` và `schemaVersion`: loại và phiên bản contract.
- `aggregateId`/partition key: entity cần giữ thứ tự.
- `occurredAt`: thời điểm nghiệp vụ xảy ra.
- `correlationId`/trace context: liên kết các bước xử lý.
- Payload tối thiểu cần cho consumer.

Ví dụ payload:

~~~json
{
  "eventId": "evt-1001-01",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "order-1001",
  "occurredAt": "2026-11-24T10:00:00Z",
  "correlationId": "req-abc-123",
  "data": {
    "orderId": "order-1001",
    "currency": "VND",
    "total": 450000
  }
}
~~~

Event ID nên được tạo từ nghiệp vụ trước lần gửi đầu tiên và giữ nguyên khi retry. Không sinh ID mới cho mỗi attempt, nếu không consumer không thể nhận biết cùng một ý định gửi bị lặp. Không đưa secret, access token, password hoặc dữ liệu nhạy cảm không cần thiết vào payload/properties.

### 6.5. Partition key và thứ tự

Dùng partition key theo entity cần xử lý có thứ tự, ví dụ `orderId`. Event của cùng order được định tuyến tới cùng partition theo cơ chế của Event Hubs; event của các order khác có thể chạy song song. Không có thứ tự tổng thể giữa partition.

Không chọn một key có phân bố lệch như một giá trị tenant lớn nếu nó khiến một partition nóng. Nếu nghiệp vụ yêu cầu thứ tự theo customer, nhưng một customer có lưu lượng vượt trội, phải thiết kế shard/sequence hoặc chấp nhận giới hạn song song. Partition key không phải khóa transaction và không tự bảo đảm thứ tự commit trong database.

## 7. Gửi event an toàn khi có lỗi

### 7.1. Phân loại lỗi producer

| Lỗi | Hướng xử lý |
|---|---|
| Authentication/authorization | Kiểm tra credential, tenant, role Data Sender và scope; không retry vô hạn |
| Namespace/event hub sai | Kiểm tra FQDN, tên hub, environment và resource tồn tại |
| DNS/network/TLS | Kiểm tra private endpoint, DNS, firewall, route và certificate |
| Payload/batch quá lớn | Giảm payload hoặc chia batch đúng contract; không retry cùng batch |
| Throttling/quota | Giảm tốc độ, tôn trọng retry policy, backoff và theo dõi metric |
| Timeout khi gửi | Kết quả có thể không xác định; event có thể đã được nhận |
| Service unavailable tạm thời | Retry có giới hạn nếu side effect được bảo vệ bằng event ID/idempotency |
| Schema không hợp lệ | Sửa dữ liệu; không retry cùng payload lỗi |

Azure SDK có retry policy riêng theo client/API và phiên bản. Trước khi thêm Spring Retry/Resilience4j, xác định SDK đã retry những trường hợp nào để tránh retry lồng nhau. Retry cần exponential backoff, jitter, giới hạn attempts và deadline tổng.

### 7.2. Timeout không chứng minh event chưa được nhận

Nếu producer gửi event nhưng response bị mất, ứng dụng không biết chắc event đã được Event Hubs nhận hay chưa. Retry có thể tạo event trùng. Cách xử lý:
- Giữ nguyên event ID qua mọi lần retry.
- Consumer deduplicate bằng event ID trong database hoặc inbox table.
- Ghi log attempt/request context đã lọc để điều tra.
- Nếu nghiệp vụ cần bảo đảm DB commit và publish event nhất quán, dùng transactional outbox thay vì gọi DB rồi gửi event trực tiếp trong cùng request.
- Không tuyên bố exactly-once chỉ vì SDK send trả thành công.

### 7.3. Transactional outbox

Nếu cập nhật đơn hàng trong database và publish event là hai thao tác riêng, có thể xảy ra:
- DB commit thành công nhưng publish thất bại.
- Event được publish nhưng transaction DB rollback.
- Publish thành công nhưng response mất, publisher retry và tạo duplicate.

Transactional outbox ghi trạng thái nghiệp vụ và event cần phát trong **cùng transaction database**. Worker riêng đọc outbox và gửi Event Hubs; sau khi gửi thành công mới đánh dấu đã publish. Nếu worker chết sau send nhưng trước khi đánh dấu, event có thể được gửi lại; consumer vẫn cần idempotency.

~~~mermaid
flowchart TD
    API["Spring Boot API"] --> TX["Database transaction"]
    TX --> O["Update order"]
    TX --> OB["Insert outbox event"]
    OB --> W["Outbox publisher"]
    W --> EH["Event Hubs"]
    EH --> C["Idempotent consumer"]
    W -. "Timeout / retry" .-> OB
~~~

Outbox không tạo exactly-once xuyên database và Event Hubs; nó bảo đảm event không bị quên giữa commit nghiệp vụ và việc phát event, với khả năng duplicate được xử lý ở consumer.

## 8. Vận hành EventProcessorClient

### 8.1. Processor làm những gì?

EventProcessorClient quản lý việc đọc event trong một consumer group và phối hợp partition ownership qua checkpoint store. Một processor instance:
1. Khởi động với namespace, event hub và consumer group.
2. Đọc ownership hiện tại từ checkpoint store.
3. Nhận ownership một hoặc nhiều partition theo cơ chế load balancing.
4. Đọc event từ checkpoint hoặc initial position nếu chưa có checkpoint.
5. Gọi callback xử lý event.
6. Cập nhật checkpoint khi ứng dụng yêu cầu.
7. Ghi lỗi vào callback xử lý lỗi khi có exception/transport/ownership problem.
8. Dừng khi ứng dụng shutdown.

Nhiều instance của cùng workload dùng **cùng consumer group và cùng checkpoint store** để phối hợp. Ứng dụng logic khác cần tiến độ độc lập phải dùng consumer group khác. Không dùng consumer group riêng cho từng pod nếu muốn các pod chia partition.

### 8.2. Blob checkpoint store

BlobCheckpointStore lưu hai nhóm trạng thái:
- **Ownership:** processor instance nào đang sở hữu partition trong consumer group.
- **Checkpoint:** vị trí đã xử lý gần nhất trên partition.

Container nên được tạo bằng IaC trước khi processor start. Runtime principal cần quyền Blob data phù hợp. Nếu Blob endpoint không truy cập được, processor có thể không ghi checkpoint hoặc không cân bằng ownership như mong muốn; đừng chỉ kiểm tra quyền Event Hubs.

Checkpoint store không lưu toàn bộ event. Event vẫn nằm trong Event Hubs theo retention; nếu cần archive dài hạn, xem Event Hubs Capture hoặc pipeline lưu sang Blob Storage/ADLS.

### 8.3. Tạo EventProcessorClient bean

Ví dụ Spring Boot dùng Azure SDK trực tiếp:

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerAsyncClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventProcessorConfiguration {

    @Bean(destroyMethod = "stop")
    EventProcessorClient eventProcessorClient(
            EventHubProperties properties,
            DefaultAzureCredential credential,
            BlobContainerAsyncClient checkpointContainer,
            OrderEventHandler handler) {

        return new EventProcessorClientBuilder()
                .consumerGroup(properties.consumerGroup())
                .credential(
                        properties.namespace(),
                        properties.eventHubName(),
                        credential)
                .checkpointStore(new BlobCheckpointStore(checkpointContainer))
                .processEvent(context -> {
                    handler.handle(context.getEventData());
                    // Chỉ checkpoint sau khi handler xử lý bền vững.
                    context.updateCheckpoint();
                })
                .processError(error -> {
                    // Dùng logger có cấu trúc trong ứng dụng thực tế.
                    // Ghi exception, partition và context đã lọc.
                    System.err.println(
                            "Event processor error: " + error.getThrowable());
                })
                .buildEventProcessorClient();
    }
}
~~~

Ví dụ giả định các bean `EventHubProperties`, `DefaultAzureCredential`, `BlobContainerAsyncClient` và `OrderEventHandler` đã được cấu hình. API callback cần đối chiếu phiên bản Azure SDK trong dự án. Trong code production, dùng logger thay `System.err`, thêm metrics và không ghi payload nhạy cảm.

### 8.4. Start và stop theo lifecycle Spring

EventProcessorClient cần được start sau khi application context đã tạo bean và dependency cần thiết. Có thể dùng ApplicationRunner:

~~~java
import com.azure.messaging.eventhubs.EventProcessorClient;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
class EventProcessorStarter implements ApplicationRunner {
    private final EventProcessorClient processor;

    EventProcessorStarter(EventProcessorClient processor) {
        this.processor = processor;
    }

    @Override
    public void run(ApplicationArguments args) {
        processor.start();
    }
}
~~~

Bean khai báo `destroyMethod = "stop"` để Spring gọi stop khi context đóng. Cần xác minh shutdown behavior và thời gian dừng phù hợp với phiên bản SDK; tránh kill process ngay lập tức khi đang xử lý event.

Một phương án khác là Spring lifecycle component để start/stop theo phase. Dù chọn cách nào, phải tránh:
- Gọi start nhiều lần cho cùng bean.
- Tạo processor client mới mỗi lần refresh request.
- Dừng processor trước khi hoàn tất các thao tác cần commit.
- Đóng Blob client/checkpoint store quá sớm.
- Nuốt lỗi shutdown khiến hệ thống tưởng đã dừng sạch.

### 8.5. Graceful shutdown

Khi container nhận SIGTERM trong rollout:
1. Ngừng nhận công việc mới từ các nguồn khác nếu cần.
2. Yêu cầu processor dừng và nhường ownership theo cơ chế SDK.
3. Cho callback đang chạy hoàn tất trong khoảng thời gian shutdown được cấp.
4. Đảm bảo side effect đã commit trước checkpoint.
5. Đóng client và datasource theo lifecycle.
6. Nếu không kịp hoàn tất, để event được đọc lại từ checkpoint gần nhất và bảo vệ duplicate bằng idempotency.

Không checkpoint event đang xử lý dở. Nếu orchestrator kill process trước khi callback hoàn thành, event có thể replay; đó là hành vi cần thiết để tránh mất dữ liệu.

## 9. Xử lý event trong processor

### 9.1. Validate, process, checkpoint

Một handler nên thực hiện theo thứ tự:
1. Đọc body và metadata.
2. Validate schema version, event ID, event type và partition context.
3. Ghi nhận correlation/trace.
4. Xử lý nghiệp vụ idempotent trong transaction.
5. Nếu event không hợp lệ, lưu quarantine bền vững theo policy.
6. Chỉ checkpoint sau khi xử lý hoặc quarantine đã hoàn tất.

Ví dụ DDL PostgreSQL cho bảng dedup:

~~~sql
CREATE TABLE processed_event (
    consumer_name varchar(100) NOT NULL,
    event_id varchar(200) NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id varchar(200) PRIMARY KEY,
    status varchar(50) NOT NULL
);
~~~

Ví dụ service handler dùng unique constraint để chống hai callback cạnh tranh cùng xử lý một event:

~~~java
import com.azure.messaging.eventhubs.EventData;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderEventHandler {
    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    OrderEventHandler(
            JdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public void handle(EventData event) {
        OrderCreated payload = parseAndValidate(event.getBodyAsString());
        if (payload.eventId() == null || payload.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }

        int inserted = jdbc.update(
                "INSERT INTO processed_event (consumer_name, event_id) " +
                "VALUES (?, ?) ON CONFLICT DO NOTHING",
                "order-projection",
                payload.eventId());
        if (inserted == 0) {
            return;
        }

        jdbc.update(
                "INSERT INTO order_projection (order_id, status) VALUES (?, ?)",
                payload.data().orderId(),
                payload.data().status());
    }

    private OrderCreated parseAndValidate(String body) {
        try {
            OrderCreated payload = objectMapper.readValue(body, OrderCreated.class);
            if (payload == null || payload.data() == null
                    || payload.data().orderId() == null
                    || payload.data().orderId().isBlank()) {
                throw new IllegalArgumentException("Missing order data");
            }
            return payload;
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Invalid event payload", exception);
        }
    }
}

record OrderCreated(String eventId, OrderCreatedData data) {}
record OrderCreatedData(String orderId, String status) {}
~~~

Đây là skeleton minh họa; trong triển khai thật, kiểm tra null/type của properties, dùng unique constraint để chống race condition thay vì chỉ `exists` rồi `record`, và bảo đảm repository cùng processed-event table tham gia một transaction. Không để exception giả trong production handler.

### 9.2. Duplicate và idempotency

EventProcessorClient có thể đọc lại event từ checkpoint gần nhất sau crash/rebalance. Consumer cần chịu được at-least-once processing:
- Dùng event ID ổn định do producer tạo.
- Đặt unique constraint trên event ID hoặc `(consumerName, eventId)`.
- Ghi processed event và thay đổi projection trong cùng transaction.
- Nếu cùng ID nhưng payload khác, báo conflict để điều tra.
- Giữ dedup record đủ lâu so với retention và thời gian replay.
- Không dùng offset làm ID nghiệp vụ duy nhất vì replay/consumer group khác có thể đọc lại event ở context khác.

### 9.3. Poison event và quarantine

Event sai schema hoặc vi phạm invariant có thể làm callback thất bại liên tục. Event Hubs không có DLQ tích hợp kiểu Service Bus. Ứng dụng có thể:
- Lưu event cùng metadata cần thiết vào quarantine store/queue riêng.
- Ghi partition ID, offset, sequence number, event ID và lý do đã lọc.
- Chỉ checkpoint qua event khi quarantine đã lưu bền vững và policy cho phép.
- Nếu quarantine thất bại, không checkpoint vượt event; báo lỗi và can thiệp theo runbook.
- Có quy trình sửa dữ liệu/handler rồi replay có kiểm soát.

Không log raw payload nếu có thông tin cá nhân hoặc bí mật. Quarantine cũng cần encryption, RBAC, retention và lifecycle.

## 10. Checkpoint đúng thời điểm

**Checkpoint là tiến độ đã xử lý**, không phải bằng chứng event đã được gửi tới processor. Quy tắc phổ biến là commit side effect trước, checkpoint sau.

| Thứ tự | Sự cố | Kết quả |
|---|---|---|
| Checkpoint trước DB commit | Process chết giữa hai bước | Có thể bỏ qua event chưa được ghi vào DB |
| DB commit trước checkpoint | Process chết giữa hai bước | Event có thể được đọc lại |
| DB commit + dedup trước checkpoint | Event được đọc lại | Dedup ngăn side effect lặp |
| Quarantine bền vững trước checkpoint | Event sai schema | Có thể bỏ qua theo policy và tiếp tục stream |

Checkpoint mỗi event giảm lượng replay nhưng tăng số lần ghi checkpoint. Checkpoint theo batch/interval giảm overhead nhưng có thể đọc lại nhiều event đã xử lý. Chọn tần suất theo throughput, chi phí Blob, khả năng replay và idempotency.

Nếu callback xử lý event bất đồng bộ, không checkpoint theo event cuối cùng chỉ vì nó được nhận sau cùng. Phải bảo đảm **mọi event trước checkpoint đã hoàn tất hoặc được quarantine bền vững**. Nếu không, một event xử lý chậm có thể bị bỏ qua sau khi checkpoint vượt qua nó.

## 11. Xử lý lỗi và retry

### 11.1. Producer và processor có loại lỗi khác nhau

| Lớp | Ví dụ lỗi | Cách phản ứng |
|---|---|---|
| Producer | 401/403 | Kiểm tra token, tenant, Data Sender và scope |
| Producer | Namespace/hub sai | Sửa endpoint/name; không retry vô hạn |
| Producer | Payload/batch quá lớn | Giảm/chia payload đúng contract |
| Producer | Throttling/temporary service error | Retry có giới hạn, backoff/jitter |
| Processor | Blob checkpoint access denied | Kiểm tra Storage Blob Data Contributor, scope và identity |
| Processor | Event Hubs receive denied | Kiểm tra Event Hubs Data Receiver |
| Processor | Network/DNS/AMQP failure | Kiểm tra private endpoint, DNS, firewall, TLS và retry |
| Handler | Database timeout | Phân biệt commit chưa rõ, transaction và idempotency |
| Handler | Schema/validation failure | Quarantine hoặc dừng theo policy; không retry vô hạn |
| Checkpoint | Blob write failure | Không giả định checkpoint đã lưu; theo dõi replay và ownership |

### 11.2. Error callback không phải nơi xử lý nghiệp vụ

`processError` nhận lỗi của processor/partition processing và là nơi ghi nhận exception, partition ID, operation và correlation. Không nên dùng callback này để nuốt lỗi handler hoặc đánh dấu event thành công. Handler phải quyết định xử lý, retry/quarantine và checkpoint; error callback hỗ trợ quan sát, cảnh báo và chẩn đoán.

Dùng logger có cấu trúc:
- Consumer group và event hub name.
- Partition ID.
- Exception class và mã lỗi đã lọc.
- Correlation/trace ID nếu có.
- Timestamp và trạng thái processor.
- Không log credential, SAS token hoặc payload nhạy cảm.

### 11.3. Backoff và retry lồng nhau

Azure SDK có retry policy cho các lỗi tạm thời. Nếu thêm retry ở tầng service, hãy xác định số attempts tổng, timeout mỗi lần và deadline toàn luồng. Không để SDK retry nhiều lần rồi Spring Retry lại retry cả operation nhiều vòng. Điều này có thể tạo retry storm và duplicate event.

Không retry vô hạn 401/403, invalid payload hoặc sai tên resource. Với send timeout, giữ nguyên event ID và để consumer deduplicate. Với database commit không rõ kết quả, kiểm tra trạng thái qua idempotency record thay vì phát event ID mới.

## 12. Monitoring và vận hành hằng ngày

### 12.1. Metrics producer

- Incoming messages và incoming bytes.
- Send operation count, success/failure, throttled requests.
- Batch size trung bình và tỷ lệ batch không đủ chỗ.
- Producer send latency p50/p95/p99.
- Retry count và lỗi cuối cùng sau retry.
- Số event theo event type/tenant/partition key (không đưa dữ liệu nhạy cảm vào label).

### 12.2. Metrics processor

- Outgoing messages/bytes và consumer lag.
- Tuổi event chưa xử lý.
- Partition ownership count và ownership changes.
- Số event processing success/failure, duration.
- Thời điểm checkpoint gần nhất trên mỗi partition.
- Checkpoint write failures và Blob latency.
- Duplicate suppressed, quarantine count, replay count.
- Processor active/stopped và thời gian rebalance.

Cần phân biệt **consumer lag** với **checkpoint lag**. Consumer có thể đã xử lý event nhưng checkpoint chưa được ghi; ngược lại checkpoint cũ có thể khiến replay dù side effect đã commit.

### 12.3. Alert và runbook

Ví dụ điều kiện cảnh báo:
- Consumer lag tăng liên tục vượt ngưỡng nghiệp vụ.
- Partition không có owner hoặc ownership thay đổi liên tục.
- Checkpoint không tiến trong khoảng thời gian bất thường.
- Throttling hoặc server error tăng đột biến.
- Poison/quarantine event tăng nhanh.
- Processor không start hoặc shutdown không hoàn tất.
- Blob checkpoint store bị 403/timeout.
- Incoming rate vượt năng lực xử lý trong thời gian dài.

Mỗi alert cần có owner, mức độ, link dashboard, cách xác minh principal/resource và bước xử lý. Không đặt một ngưỡng cố định áp dụng cho mọi event hub; baseline phụ thuộc throughput, tier, retention và SLO.

## 13. Kiểm thử tích hợp

Dùng namespace, event hub, consumer group và Blob checkpoint container riêng cho test. Không reset checkpoint hoặc đổi partition count production để kiểm thử.

| Kịch bản | Cách thử | Kết quả mong muốn |
|---|---|---|
| Producer gửi event đơn | Gửi event có event ID test | Event được nhận và consumer ghi nhận đúng |
| Batch đầy | Gửi nhiều event theo giới hạn batch | Không mất event khi phải chia batch |
| Một event vượt batch size | Tạo payload lớn trong test | Bị từ chối rõ ràng hoặc chuyển sang lưu object/reference |
| Partition key | Gửi nhiều event cùng aggregate key | Được định tuyến cùng partition trong topology ổn định |
| Send timeout | Mô phỏng response mất sau khi gửi | Retry giữ event ID; consumer dedup |
| Processor scale-out | Chạy nhiều instance cùng consumer group | Ownership phân phối lại, không đọc toàn bộ stream ở mọi instance |
| Crash trước checkpoint | Dừng processor sau DB commit | Event có thể replay; side effect không lặp |
| Checkpoint store 403 | Dùng identity thiếu Blob data role | Processor báo lỗi; không tiến checkpoint giả |
| Handler exception | Gửi payload lỗi schema | Quarantine hoặc dừng theo policy |
| Graceful shutdown | Gửi SIGTERM khi đang xử lý | Stop có kiểm soát; event chưa checkpoint có thể replay |
| Network partition | Chặn DNS/endpoint tạm thời | Processor phục hồi, checkpoint/ownership được kiểm tra |
| Retention/replay | Dùng consumer group test mới với initial position | Replay đúng phạm vi dữ liệu còn retention |
| Cross-environment access | Identity dev truy cập hub prod | Bị RBAC/network từ chối |
| Quota/throttling | Tải tăng dần trong giới hạn test | Retry/backpressure có kiểm soát, không retry storm |

Unit test kiểm tra logic serialization, partition key, idempotency và handler. Integration test trên Azure mới xác minh được RBAC, network, checkpoint store, processor ownership và behavior của dịch vụ thật. Giới hạn test theo quota/chi phí và cleanup resource sau run.

## 14. Tình huống vận hành thường gặp

### Tình huống A: producer gửi thành công nhưng consumer không thấy event

Kiểm tra:
- Producer và consumer đang trỏ cùng namespace/event hub/Region không?
- Consumer group có đúng không, initial position/checkpoint ở đâu?
- Event còn trong retention không?
- Processor có owner partition và có lỗi trong processError không?
- Filter/logic consumer có bỏ qua event không?
- Network và RBAC có đúng cho principal runtime không?

Không kết luận event mất chỉ từ dashboard một consumer group; nhóm có thể đang đọc từ offset cũ hoặc consumer chưa start.

### Tình huống B: processor restart và xử lý lại nhiều event

Đây có thể là replay từ checkpoint gần nhất. Kiểm tra checkpoint frequency, Blob store availability, shutdown, rebalance và handler duration. Xác nhận DB dedup hoạt động; nếu không, bổ sung inbox/unique event ID trước khi tăng checkpoint frequency.

### Tình huống C: processor chạy nhưng checkpoint không tiến

Kiểm tra quyền Storage Blob Data Contributor, container URL, DNS/private endpoint, Blob client credential và exception trong error callback. Kiểm tra code handler có bị block lâu hoặc callback không đến đoạn updateCheckpoint. Không tự tạo checkpoint container production bằng runtime role nếu quy trình yêu cầu IaC.

### Tình huống D: scale-out làm event xử lý chậm hơn

Nhiều instance có thể gây rebalance thường xuyên, tăng kết nối và cạnh tranh DB. Kiểm tra partition count, ownership churn, CPU/DB pool, Blob checkpoint latency và handler concurrency. Thêm pod vượt số partition không làm tăng parallelism hữu ích.

### Tình huống E: gửi event trùng sau timeout

Response của send có thể bị mất sau khi service nhận event. Kiểm tra producer retry và event ID. Giữ event ID ổn định qua attempts; consumer dedup. Nếu publish gắn với DB commit, dùng outbox để tránh khoảng trống giữa hai hệ thống.

## 15. Checklist đưa producer và processor lên production

- **Resource:** namespace/event hub/consumer group/checkpoint container đã được provision đúng môi trường và Region.
- **Identity:** producer có Event Hubs Data Sender; processor có Event Hubs Data Receiver; checkpoint có Blob Data Contributor ở scope nhỏ nhất.
- **Client lifecycle:** producer dùng lại một bean; processor start/stop theo lifecycle Spring; shutdown được thử nghiệm.
- **Producer:** event schema/version, event ID, partition key, batch size, retry/timeout và backpressure rõ ràng.
- **Consumer:** handler idempotent, validate schema, xử lý duplicate, quarantine poison event và checkpoint đúng thời điểm.
- **Checkpoint:** store có sẵn, quyền và network đúng, tần suất checkpoint theo replay budget.
- **Ordering:** chỉ giả định thứ tự trong partition; dùng aggregate version khi cần thứ tự nghiệp vụ.
- **Reliability:** timeout, retry, jitter, deadline, outbox/inbox và graceful shutdown.
- **Security:** Managed Identity/workload identity, không hardcode SAS/connection string, không log secret/payload nhạy cảm.
- **Observability:** send latency, retry, throttling, consumer lag, ownership, checkpoint age, quarantine và error callback.
- **Testing:** batch overflow, send timeout, duplicate, crash/replay, checkpoint 403, scale-out/in, cross-environment denial.
- **Cost:** tier/capacity, throughput, retention, Blob checkpoint operations, Capture, network và monitoring.
- **Runbook:** có owner và hướng xử lý cho producer failure, processor stopped, checkpoint failure, hot partition và lag tăng.

## 16. Tổng kết

Producer chịu trách nhiệm tạo event có contract rõ ràng, chọn partition key, gửi batch đúng giới hạn, giữ event ID ổn định và xử lý timeout/throttling an toàn. **EventProcessorClient** chịu trách nhiệm đọc stream và phối hợp partition ownership; ứng dụng chịu trách nhiệm xử lý nghiệp vụ, dedup, checkpoint sau side effect bền vững, quarantine và graceful shutdown. Blob checkpoint store là một phụ thuộc riêng cần danh tính, quyền, network và giám sát riêng.

Khi tích hợp Event Hubs với Spring Boot, hãy quản lý client theo lifecycle, dùng Managed Identity và RBAC tối thiểu, tách tài nguyên theo môi trường, kiểm thử lỗi sau send/commit/checkpoint và theo dõi lag cùng ownership. Cách vận hành này giúp producer không tạo tải bất ngờ, consumer phục hồi an toàn và hệ thống giữ được tính đúng đắn khi process, mạng hoặc dịch vụ gặp sự cố.

