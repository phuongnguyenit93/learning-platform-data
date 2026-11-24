# Phân biệt OCI Queue, Streaming và Notifications

OCI Queue, OCI Streaming và OCI Notifications đều tiếp nhận hoặc chuyển message, nhưng giải quyết ba bài toán khác nhau. Queue phân phối work item cho worker; Streaming tiếp nhận và cung cấp record theo partition/cursor để consumer xử lý và replay; Notifications phát thông báo từ topic tới nhiều subscription. Chọn nhầm service thường dẫn đến thiết kế sai về ownership, acknowledgement, checkpoint, ordering, replay và failure recovery.

Spring Cloud OCI cung cấp service-specific starter cho Queue, Streaming và Notifications, với các bean API riêng là Queue, Streaming và Notification. Những abstraction này không làm ba dịch vụ trở nên tương đương: application vẫn phải tuân theo semantics của từng backend. Bài học tập trung phân biệt ba dịch vụ này theo workload, message lifecycle, delivery model và cách viết consumer/producer; các starter OCI khác được đưa vào làm ví dụ đối chiếu khi chọn API.

Bài này đưa ra quy trình chọn theo workload, so sánh sâu Queue/Streaming/Notifications và thiết kế ranh giới giữa API Spring, OCI SDK, database transaction và managed service. Nội dung nằm trong chương Oracle Cloud của module SPRING_CLOUD_PROVIDER_INTEGRATION, nơi người học thực hành tích hợp Spring Boot với storage, messaging, dữ liệu, secret và các dịch vụ managed của cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt mục tiêu và message lifecycle của OCI Queue, OCI Streaming và OCI Notifications.
2. Chọn service dựa trên work distribution, event ingestion/replay hoặc pub/sub fan-out.
3. Chọn đúng Spring Cloud OCI starter và bean API Queue, Streaming hoặc Notification.
4. Thiết kế message identity, delivery, settlement, cursor, checkpoint và retry phù hợp từng service.
5. Phân biệt ba service OCI với Oracle TxEventQ và Spring Cloud Stream binder.
6. Đánh giá ordering, retention, consumer progress, fan-out và failure recovery.
7. Xác định transaction boundary, retry, idempotency và consistency khi ghép messaging với database.
8. Thiết kế authentication, IAM policy, region và compartment theo producer/consumer.
9. Đánh giá throughput, latency, partitioning, payload size và chi phí vận hành.
10. Kiểm thử redelivery, replay, subscription delivery và failure scenarios.
11. Nhận diện khi nào Oracle TxEventQ hoặc một OCI service khác phù hợp hơn.
12. Đặt provider-specific API sau adapter boundary để domain không phụ thuộc OCI-specific types.

## 2. Bắt đầu từ workload, không bắt đầu từ danh mục dịch vụ

Một workload mô tả công việc ứng dụng cần thực hiện, tần suất, dữ liệu và yêu cầu vận hành. Cùng một yêu cầu “gửi thông báo” có thể cần một dịch vụ khác nhau tùy đối tượng nhận, độ tin cậy và thời điểm gửi.

Ví dụ:

- Lưu hóa đơn PDF: cần object storage, truy cập theo object key, metadata, retention và download.
- Lưu database password: cần secret manager, IAM permission, rotation và cache.
- Xử lý đơn hàng nền: cần queue để phân phối work item, retry và dead-letter handling.
- Thu thập audit event số lượng lớn: cần stream, partition key, cursor và replay.
- Phát cảnh báo tới nhiều subscriber: cần pub/sub notification.
- Gửi email giao dịch: cần mail protocol và SMTP credential.
- Gọi tác vụ xử lý ảnh: cần invocation tới function hoặc queue-triggered worker.
- Quản lý database instance: cần control-plane API.
- Thực hiện query nghiệp vụ: cần DataSource, connection pool và transaction.
- Truy cập dữ liệu JSON/key-value: cần NoSQL repository hoặc API phù hợp.

### 2.1. Bốn câu hỏi chọn dịch vụ

**1. Workload đang làm gì?**

Lưu object, giữ secret, phân phối công việc, ingest event, phát thông báo, gửi email, ghi log, gọi function hay truy vấn dữ liệu?

**2. Workload cần programming model nào?**

- Spring Resource/WritableResource.
- Storage/Queue/Streaming service bean.
- Spring MailSender/JavaMailSender.
- Spring Data repository.
- Spring Cloud Stream function binding.
- OCI SDK/client API.
- Control-plane operation.

**3. Workload có semantics gì?**

- Request/response hay asynchronous.
- Work item hay event stream.
- Fan-out hay single-work processing.
- Transactional hay eventual consistency.
- Có cần ordering, replay, retention, deduplication hay checkpoint không?

**4. Ai vận hành và cấp quyền?**

- Workload identity nào gọi API?
- Resource nằm ở region/compartment nào?
- IAM policy nào được cấp?
- Ai tạo resource, ai dùng resource?
- Ai chịu trách nhiệm retry, retention, backup và alert?

Không chọn dịch vụ chỉ vì API của nó dễ gọi. Chọn theo semantics mà hệ thống cần bảo đảm.

## 3. Bản đồ Spring Cloud OCI starter

Danh mục Spring Cloud OCI 2.0.4 cung cấp các starter sau:

| Workload/capability | Starter | API hoặc abstraction chính |
| --- | --- | --- |
| Lưu file/object | spring-cloud-oci-starter-storage | Storage, Spring Resource, WritableResource |
| Secret/config bí mật | spring-cloud-oci-starter-vault | Spring property source, VaultTemplate |
| Queue work item | spring-cloud-oci-starter-queue | Queue |
| Stream event/data | spring-cloud-oci-starter-streaming | Streaming |
| Pub/sub notification | spring-cloud-oci-starter-notification | Notification |
| Application/service log | spring-cloud-oci-starter-logging | LogService |
| Email giao dịch | spring-cloud-oci-starter-email | MailSender, JavaMailSender |
| Gọi function | spring-cloud-oci-starter-function | Function |
| Quản lý Autonomous Database | spring-cloud-oci-starter-adb | AutonomousDb |
| Dữ liệu NoSQL | spring-cloud-oci-starter-nosql | NosqlDBConfig, NosqlRepository |
| Generative AI | spring-cloud-oci-starter-gen-ai | ChatModel, EmbeddingModel |

Ngoài các starter dịch vụ, core starter cung cấp OCI authentication và hạ tầng chung. Service starter thường kéo theo core cần thiết; hãy kiểm tra dependency graph trước khi khai báo core thêm lần nữa.

Danh sách trên là bản đồ tích hợp của Spring Cloud OCI. Oracle AI Database starters và TxEventQ binder là các nhánh khác trong hệ sinh thái Spring Cloud Oracle, sẽ được phân biệt ở phần messaging và database.

## 4. Chọn API Spring hay OCI SDK trực tiếp?

Một service starter có thể cung cấp abstraction Spring, bean chuyên biệt hoặc API gần với OCI SDK. Hãy chọn lớp API theo mức độ mà ứng dụng cần kiểm soát.

| Lớp API | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| Spring abstraction | Business code cần thao tác tài nguyên theo contract chung | Resource, WritableResource, MailSender |
| Service bean của starter | Cần operation đặc thù OCI nhưng muốn auto-configuration | Storage, Queue, Streaming, VaultTemplate |
| Spring Data abstraction | Cần repository/query theo mô hình dữ liệu | NosqlRepository |
| Spring Cloud Stream | Cần Supplier/Function/Consumer và binding | TxEventQ binder |
| OCI SDK trực tiếp | Starter chưa expose operation cần hoặc cần API mới/chuyên sâu | OCI Java SDK client |

### 4.1. Đặt provider API ở adapter boundary

Domain service nên nói về nghiệp vụ như InvoiceArchive, SecretProvider, OrderPublisher hoặc NotificationSender. Adapter mới phụ thuộc Storage, Queue, VaultTemplate hay OCI SDK.

Ví dụ:

~~~java
public interface InvoiceFileStore {
    String save(String invoiceId, InputStream content, String contentType);
    InputStream open(String objectKey);
}
~~~

Adapter OCI triển khai interface này bằng Storage API hoặc Spring Resource. Domain không cần biết namespace, bucket endpoint, OCI response class hoặc SDK request builder.

### 4.2. Khi nào dùng Spring Resource?

Dùng Resource khi thao tác đọc/ghi file là một phần của luồng xử lý và code cần một abstraction Spring. Dùng Storage khi cần thao tác bucket/object, metadata hoặc operation OCI-specific.

Không ép mọi operation vào Resource nếu business cần conditional write, metadata hoặc bucket lifecycle. Resource là abstraction truy cập nội dung, không phải contract đầy đủ của Object Storage.

### 4.3. Khi nào dùng OCI SDK trực tiếp?

Dùng SDK trực tiếp khi:

- Starter chưa expose một operation cần thiết.
- Cần một API option cụ thể của OCI.
- Cần điều khiển request/response chi tiết.
- Cần capability mới hơn version starter đang bọc.
- Cần tối ưu một luồng chuyên biệt sau khi đo đạc.

Nếu dùng SDK trực tiếp, reuse authentication provider, region, retry/timeout policy và client lifecycle của ứng dụng. Không tạo client mới cho mỗi request.

## 5. Object Storage: chọn Storage API hay Resource

OCI Object Storage lưu dữ liệu dạng object trong bucket. Spring Cloud OCI starter auto-configure bean Storage cho thao tác bucket/object và tích hợp object với Spring Resource.

Dependency:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
</dependency>
~~~

### 5.1. Dùng Storage API

Dùng Storage khi cần thao tác rõ ràng với bucket, object, metadata hoặc các operation của dịch vụ.

Ví dụ theo API của starter:

~~~java
@Service
public class InvoiceObjectService {

    private final Storage storage;

    public InvoiceObjectService(Storage storage) {
        this.storage = storage;
    }

    public void upload(
            String bucketName,
            String objectName,
            InputStream content) {

        storage.upload(
                bucketName,
                objectName,
                content,
                StorageObjectMetadata.builder()
                        .contentType("application/pdf")
                        .build());
    }
}
~~~

Đoạn code minh họa upload. Cần kiểm tra contract ownership/đóng InputStream theo API cụ thể và đóng stream do ứng dụng mở bằng try-with-resources.

### 5.2. Dùng Spring Resource

Object Storage resource có thể được resolve bằng URI theo endpoint Object Storage. Ví dụ:

~~~java
Resource resource = applicationContext.getResource(
    "https://objectstorage.REGION.oraclecloud.com/n/NAMESPACE/b/BUCKET/o/OBJECT_KEY"
);

try (InputStream input = resource.getInputStream()) {
    // Stream nội dung object
}
~~~

Object Storage resource cũng triển khai WritableResource. Khi ghi qua getOutputStream(), nội dung được upload khi stream đóng:

~~~java
WritableResource target = (WritableResource) applicationContext.getResource(
    "https://objectstorage.REGION.oraclecloud.com/n/NAMESPACE/b/BUCKET/o/OBJECT_KEY"
);

try (OutputStream output = target.getOutputStream()) {
    output.write(pdfBytes);
}
~~~

URI chỉ là cách định vị object qua resource abstraction. Không coi URI đó là URL công khai hoặc credential. Quyền đọc/ghi vẫn được kiểm tra qua OCI identity/IAM.

### 5.3. Chọn giữa hai cách

| Nhu cầu | Chọn |
| --- | --- |
| Đọc nội dung file trong API Spring nhận Resource | Resource |
| Ghi stream từ API Spring | WritableResource |
| Upload với metadata rõ ràng | Storage |
| Tạo bucket hoặc thao tác bucket/object | Storage |
| Kiểm soát operation OCI-specific | Storage hoặc SDK |
| Chỉ cần một abstraction file nội bộ | Interface ứng dụng + adapter OCI |

### 5.4. Thiết kế object key và upload

- Dùng object key ổn định theo business ID/version.
- Xác định chính sách overwrite và conditional write.
- Đặt content type, metadata và encryption theo yêu cầu.
- Stream file lớn thay vì luôn đọc toàn bộ vào heap.
- Thiết kế multipart upload và cleanup nếu dùng upload lớn.
- Không giả định object storage có directory/rename/locking giống filesystem.
- Dùng checksum/ETag/version metadata để kiểm tra kết quả.
- Xử lý timeout theo hướng unknown outcome: object có thể đã được ghi dù client không nhận response.

### 5.5. Khi không nên dùng Object Storage

Không dùng Object Storage để thay database cho record cần query/update nhiều thuộc tính hoặc transaction quan hệ. Không dùng Vault để thay Object Storage cho file lớn. Nếu cần truy vấn key-value hoặc JSON theo record, cân nhắc database/NoSQL.

## 6. Vault: chọn property source hay VaultTemplate

OCI Vault lưu secret và quản lý version. Spring Cloud OCI Vault starter có hai cách tích hợp chính:

- Property source: nạp secret vào Spring Environment theo tên secret.
- VaultTemplate: đọc hoặc quản lý secret qua bean API.

Dependency:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-vault</artifactId>
</dependency>
~~~

### 6.1. Property source cho cấu hình lúc khởi động

Chọn property source khi secret đóng vai trò cấu hình cho ứng dụng, ví dụ database password hoặc SMTP credential.

~~~yaml
spring:
  cloud:
    oci:
      vault:
        enabled: true
        compartment: ${OCI_COMPARTMENT_ID}
        property-refresh-interval: 10m
        property-sources:
          - vault-id: ${OCI_VAULT_ID}
~~~

Secret được đưa vào Spring Environment theo tên. Bean có thể resolve bằng @Value hoặc @ConfigurationProperties.

Refresh property source không có nghĩa mọi singleton bean hoặc connection pool đã inject secret cũ tự động thay đổi. Thiết kế refresh/recreate client riêng.

### 6.2. VaultTemplate cho truy xuất theo yêu cầu

Dùng VaultTemplate khi cần chọn secret theo tenant/workload hoặc muốn kiểm soát thời điểm đọc:

~~~java
GetSecretBundleByNameResponse bundle =
        vaultTemplate.getSecret(secretName);

String secretValue = vaultTemplate.decodeBundle(bundle);
~~~

Đặt VaultTemplate trong adapter SecretProvider. Business service không nên phụ thuộc OCI response type.

### 6.3. Quyết định

| Nhu cầu | Cách dùng |
| --- | --- |
| Password được nạp lúc startup | Property source |
| Secret theo tên động trong runtime | VaultTemplate qua adapter |
| Cần quản lý cache/TTL riêng | VaultTemplate + cache policy |
| Secret thay đổi định kỳ | Property refresh + refresh/recreate consumer |
| Tạo/promote/delete secret | Job quản trị riêng với quyền quản lý |

### 6.4. IAM và rotation

Workload runtime thường chỉ cần quyền đọc secret bundle. Tách quyền đọc khỏi quyền tạo, update, promote hoặc delete secret. Khi rotation:

1. Tạo credential mới trên target system.
2. Tạo secret version mới.
3. Kiểm tra credential mới.
4. Promote version mới thành CURRENT.
5. Refresh/recreate DataSource hoặc client.
6. Xác minh tất cả replica đã dùng credential mới.
7. Thu hồi credential cũ sau khi không còn consumer.

Không nhầm LATEST với CURRENT; version mới nhất có thể vẫn ở trạng thái PENDING.

## 7. Queue, Streaming, Notifications và TxEventQ không giống nhau

Đây là quyết định quan trọng nhất khi chọn messaging.

| Dịch vụ | Mô hình | Workload phù hợp | Tiến độ/đích nhận |
| --- | --- | --- | --- |
| OCI Queue | Work queue | Tác vụ độc lập, worker xử lý | Message receive/settlement theo Queue API |
| OCI Streaming | Stream/partition | Ingest event hoặc dữ liệu liên tục | Cursor/partition và checkpoint do consumer quản lý |
| OCI Notifications | Pub/sub fan-out | Phát alert/event tới nhiều loại subscriber | Topic và subscription |
| Oracle TxEventQ | Database-native transactional queue | Message gắn với Oracle AI Database | JMS, Kafka API hoặc Spring Cloud Stream binder |

Không chọn chỉ vì workload có từ “event” hoặc “message”. Xác định message có được phân phối cho một worker hay phát tới nhiều subscriber; cần replay hay không; có ordering; transaction gắn với database không; và ai quản lý acknowledgment/checkpoint.

### 7.1. So sánh theo vòng đời message

| Tiêu chí | OCI Queue | OCI Streaming | OCI Notifications |
| --- | --- | --- | --- |
| Đơn vị xử lý | Work item | Record/event trong stream | Notification gửi tới topic |
| Consumer model | Worker nhận message để xử lý | Consumer đọc record theo partition/cursor | Subscriber đăng ký topic/endpoint |
| Mục tiêu chính | Phân phối công việc | Ingest, lưu giữ và đọc luồng record | Fan-out một thông báo tới nhiều đích |
| Theo dõi tiến độ | Message delivery và settlement | Cursor/checkpoint | Trạng thái publish/subscription/delivery theo service |
| Replay | Dựa trên message lifecycle/retention của queue | Đọc lại từ cursor trong retention | Không dùng như event log để replay tùy ý |
| Ordering | Theo semantics và cấu hình queue | Theo thứ tự trong partition | Không nên dùng làm cơ chế ordering nghiệp vụ |
| Dead-letter | Queue có cấu hình dead-letter delivery count | Consumer tự thiết kế quarantine/error flow | Subscriber xử lý failure theo endpoint/delivery model |
| Fan-out | Không phải mục đích chính | Có thể có nhiều consumer group/consumer theo stream design | Mục đích cốt lõi |

### 7.2. Cây quyết định

~~~mermaid
flowchart TD
    A[Ứng dụng cần gửi message] --> B{Mỗi message là một work item?}
    B -->|Có| C[OCI Queue]
    B -->|Không| D{Cần giữ record và đọc theo cursor/partition?}
    D -->|Có| E[OCI Streaming]
    D -->|Không| F{Cần phát cùng thông báo tới nhiều subscriber?}
    F -->|Có| G[OCI Notifications]
    F -->|Không| H[Đánh giá TxEventQ hoặc API khác]
~~~

### 7.3. Những câu hỏi phải trả lời trước khi chọn

1. Ai sở hữu công việc sau khi publish: một worker hay nhiều subscriber?
2. Consumer cần acknowledge/settle từng message hay lưu checkpoint theo vị trí đọc?
3. Có cần replay dữ liệu cũ trong một retention window không?
4. Ordering cần ở toàn hệ thống, theo partition/key hay không cần?
5. Message lỗi cần redelivery, dead-letter hay subscriber retry riêng?
6. Producer cần biết consumer đã hoàn tất nghiệp vụ hay chỉ cần biết publish request được chấp nhận?
7. Có cần transaction chung với Oracle AI Database không? Nếu có, đánh giá TxEventQ.

### 7.4. Phân biệt publish success và business completion

Một API trả về publish success chỉ chứng minh service đã chấp nhận operation theo contract của API. Nó không tự chứng minh worker đã hoàn tất transaction hoặc tất cả subscriber đã xử lý xong. Nếu nghiệp vụ cần biết kết quả cuối, consumer/subscriber phải ghi trạng thái xử lý và phát kết quả hoặc cập nhật một workflow state riêng.

### 7.5. Thiết kế event contract dùng chung

Dù chọn Queue, Streaming hay Notifications, payload nên có:

- Event ID duy nhất.
- Event type và schema version.
- Aggregate/business ID.
- Occurred-at timestamp.
- Correlation/causation ID khi cần trace workflow.
- Payload vừa đủ cho consumer; tránh nhúng dữ liệu lớn hoặc secret.
- Quy tắc tương thích schema khi producer và consumer deploy khác thời điểm.

Không dùng transport message ID thay cho business event ID. Transport ID thuộc service; event ID thuộc contract nghiệp vụ và giúp deduplicate xuyên provider.

## 8. OCI Queue: phân phối work item

OCI Queue phù hợp với các message đại diện cho công việc có thể xử lý độc lập: tạo thumbnail, xử lý hóa đơn, gửi email, chạy tác vụ nền hoặc gọi một workflow.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-queue</artifactId>
</dependency>
~~~

Starter auto-configure bean Queue cho các operation queue/message. API có thể tạo queue với tên, compartment, dead-letter delivery count và retention.

Ví dụ tạo queue:

~~~java
String queueId = queue.createQueue(
        "invoice-processing",
        compartmentId,
        deadLetterDeliveryCount,
        retentionInSeconds);
~~~

### 8.1. Khi chọn Queue

- Một message thường đại diện một work item.
- Worker nhận công việc và thực hiện side effect.
- Cần retry khi lỗi tạm thời.
- Cần giới hạn số lần delivery.
- Cần dead-letter/quarantine cho message lỗi kéo dài.
- Cần quan sát queue depth và tuổi message cũ nhất.

### 8.2. Consumer cần idempotency

Message có thể được giao lại sau timeout, worker crash hoặc settlement không thành công. Consumer nên có idempotency key hoặc inbox record để side effect không bị lặp.

Ví dụ luồng:

~~~text
Receive message
  -> validate message
  -> check inbox/idempotency key
  -> execute business transaction
  -> commit result + inbox marker
  -> settle/ack message
~~~

Không settle message trước khi business effect đã được lưu bền vững. Nếu commit thành công nhưng settlement thất bại, message có thể được giao lại; inbox/deduplication xử lý lần giao lại.

### 8.3. Queue không phải event log

Queue thường được dùng để phân phối work item. Nếu cần giữ event theo partition và replay từ cursor, Streaming phù hợp hơn. Nếu cần fan-out tới nhiều subscriber độc lập, Notifications phù hợp hơn.

## 9. OCI Streaming: ingest và consume record

OCI Streaming phù hợp với dữ liệu/event liên tục có throughput lớn, ví dụ audit event, clickstream, telemetry hoặc sự kiện tích hợp từ nhiều hệ thống.

Dependency:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-streaming</artifactId>
</dependency>
~~~

Starter auto-configure bean Streaming để tạo stream và gửi/nhận message.

Ví dụ gửi record:

~~~java
PutMessagesResponse response =
        streaming.putMessages(
                streamId,
                "invoice-created".getBytes(StandardCharsets.UTF_8),
                eventPayload.getBytes(StandardCharsets.UTF_8));
~~~

Ví dụ đọc record theo cursor:

~~~java
GetMessagesResponse response =
        streaming.getMessages(streamId, cursor);
~~~

Đây là API-level illustration; cần kiểm tra cách tạo cursor, deserialize record, lấy cursor tiếp theo và checkpoint trong SDK/starter version đang dùng.

### 9.1. Partition key

Partition key quyết định cách record được phân phối vào partition. Chọn key theo ordering và throughput:

- Key theo customerId nếu cần ordering theo customer.
- Key theo aggregateId nếu cần giữ event của một aggregate cùng partition.
- Tránh một key nóng khiến mọi record dồn vào một partition.
- Nếu không cần ordering theo entity, chọn key phân tán để tận dụng partition.

Ordering không tự động là ordering toàn stream; phải xác định phạm vi partition.

### 9.2. Cursor và checkpoint

Consumer lưu tiến độ đọc. Sau restart, consumer có thể đọc lại record từ cursor an toàn. Cần:

- Commit business effect trước khi lưu checkpoint tương ứng.
- Không checkpoint vượt qua record chưa xử lý thành công nếu xử lý song song.
- Lưu checkpoint bền vững.
- Có chiến lược replay và deduplication.
- Theo dõi consumer lag và retention.

Nếu checkpoint đi trước business commit, ứng dụng có thể mất event. Nếu business commit rồi checkpoint chưa cập nhật, event có thể được đọc lại; idempotency xử lý duplicate.

### 9.3. Khi chọn Streaming thay Queue

Chọn Streaming khi cần ingest liên tục, partition, cursor, replay và xử lý record theo luồng. Chọn Queue khi message là work item cần worker xử lý và settle.

## 10. OCI Notifications: phát một thông báo tới nhiều subscriber

OCI Notifications là pub/sub service để gửi alert/message tới email, SMS, Functions, Slack, PagerDuty hoặc custom HTTPS endpoint.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-notification</artifactId>
</dependency>
~~~

Starter auto-configure bean Notification cho topic, subscription và publish operation.

Ví dụ tạo topic:

~~~java
CreateTopicResponse response =
        notification.createTopic("invoice-alerts", compartmentOcid);
~~~

### 10.1. Chọn Notifications khi nào?

- Cùng một thông báo cần fan-out tới nhiều subscriber.
- Đích nhận có thể là email, SMS, function hoặc HTTPS endpoint.
- Workload là alert/notification, không phải một task worker cần giữ ownership.
- Muốn tách producer khỏi subscriber.

### 10.2. Notifications không thay thế Queue

Nếu mỗi message cần một worker xử lý và settle theo work queue, dùng Queue. Notifications phục vụ pub/sub fan-out; không thiết kế nó như một durable work queue với consumer lock semantics.

Nếu cần event log để replay theo partition, dùng Streaming.

### 10.3. Payload và subscriber

- Giữ payload đủ ngắn và có schema/version.
- Không đưa secret hoặc dữ liệu nhạy cảm vào notification body.
- Subscriber nên xác thực nguồn và xử lý duplicate nếu downstream delivery có thể retry.
- Theo dõi trạng thái subscription và delivery failure.
- Không coi việc publish thành công là bằng chứng tất cả subscriber đã xử lý xong.

## 11. Oracle TxEventQ: messaging gắn với Oracle AI Database

TxEventQ là Oracle Database Transactional Event Queues. Nó khác OCI Queue và OCI Streaming vì backend nằm trong Oracle AI Database và có thể phối hợp với database transaction theo integration được hỗ trợ.

Chọn programming model theo codebase:

| API | Starter/project | Khi phù hợp |
| --- | --- | --- |
| Spring JMS | Oracle AQ/JMS starter | Ứng dụng đang dùng JmsTemplate/@JmsListener |
| Kafka Java API | OKafka starter | Ứng dụng dùng Kafka producer/consumer/admin concepts |
| Spring Cloud Stream | TxEventQ binder | Ứng dụng dùng Supplier/Function/Consumer bindings |

TxEventQ binder không phải binder của OCI Queue hoặc OCI Streaming. Nếu yêu cầu là managed OCI Queue, dùng Queue starter.

### 11.1. Transaction boundary

AQ/JMS starter có thể cấu hình DataSource và JMS Connection Factory chia sẻ database transaction. Khi cấu hình đúng, một transaction có thể đọc message, cập nhật database và commit/rollback cùng unit of work.

Không suy rộng điều này sang OCI Queue, OCI Streaming hoặc Notifications. Các dịch vụ đó có API và transaction boundary riêng. Khi ghép database với OCI managed service, cân nhắc outbox, inbox, saga hoặc reconciliation.

### 11.2. Khi nào nên chọn TxEventQ?

- Workload đã dùng Oracle AI Database.
- Cần database-native transactional messaging.
- Muốn giữ message flow trong cùng nền tảng database.
- Đội ngũ muốn dùng JMS, Kafka API hoặc Spring Cloud Stream theo lựa chọn.

Nếu không cần transaction gắn với Oracle Database, OCI Queue/Streaming có thể phù hợp hơn theo yêu cầu vận hành.

## 12. Chọn dịch vụ dữ liệu: Autonomous Database, JDBC/UCP hay Oracle NoSQL

Từ “Autonomous Database” có thể chỉ control plane quản lý instance hoặc data plane dùng để query dữ liệu. Hai việc cần API khác nhau.

### 12.1. Autonomous Database starter: quản lý vòng đời

Starter spring-cloud-oci-starter-adb auto-configure bean AutonomousDb. Bean này hỗ trợ operation như create, inspect, start, stop, delete Autonomous Database và generate wallet.

Chọn starter này khi ứng dụng/platform automation cần quản lý resource database qua OCI control-plane API.

Không dùng starter lifecycle để thay DataSource/JDBC trong business service.

### 12.2. JDBC/UCP/Wallet: kết nối để chạy query

Nếu workload cần đọc/ghi record, dùng Oracle JDBC driver và DataSource. UCP quản lý connection pool; Wallet hỗ trợ secure connectivity trong môi trường yêu cầu wallet/mTLS.

Một business service thường dùng:

- Spring JDBC hoặc Spring Data JPA.
- Oracle JDBC driver.
- UCP DataSource nếu phù hợp.
- Wallet/TNS config nếu endpoint yêu cầu.
- Transaction manager cho database transaction.

### 12.3. Oracle NoSQL Database

OCI NoSQL starter phù hợp với workload key-value, table hoặc JSON có access pattern rõ ràng và yêu cầu transaction semantics phù hợp.

Starter auto-configure NosqlDBConfig và hỗ trợ repository-based access. Cần enable repository theo hướng dẫn integration, ví dụ:

~~~java
@SpringBootApplication
@EnableNosqlRepositories
public class CatalogApplication extends AbstractNosqlConfiguration {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Repository:

~~~java
public interface BookRepository extends NosqlRepository<Book, Long> {
    Iterable<Book> findByAuthor(String author);
    Iterable<Book> findByTitle(String title);
}
~~~

Entity:

~~~java
@NosqlTable(tableName = "books")
public class Book {

    @NosqlId(generated = true)
    private long id;

    private String title;
    private String author;
    private double price;
}
~~~

Region phải được resolve từ spring.cloud.oci.region.static hoặc credential configuration trước khi NoSQL configuration được tạo.

### 12.4. Chọn mô hình dữ liệu

| Workload | Hướng chọn |
| --- | --- |
| Quan hệ, join, transaction nhiều bảng | Oracle AI Database + JDBC/JPA |
| Autonomous Database provisioning | AutonomousDb control-plane API |
| Key-value lookup, table, JSON theo access pattern | Oracle NoSQL |
| File/document binary lớn | Object Storage |
| Secret/config nhạy cảm | Vault |

Không chọn NoSQL chỉ vì dữ liệu có JSON. Hãy đánh giá access pattern, transaction, index, consistency và query requirements.

## 13. Email Delivery: chọn MailSender hay JavaMailSender

OCI Email Delivery tích hợp với Spring Mail. Starter spring-cloud-oci-starter-email cung cấp MailSender và JavaMailSender.

Dùng MailSender cho simple text email. Dùng JavaMailSender khi cần MIME, HTML, attachment hoặc cấu trúc message phức tạp.

Cấu hình SMTP dùng Spring Mail properties:

~~~yaml
spring:
  mail:
    host: ${OCI_SMTP_HOST}
    username: ${OCI_SMTP_USERNAME}
    password: ${OCI_SMTP_PASSWORD}
    port: 587
~~~

SMTP credentials phải được tạo theo OCI Email Delivery và bảo vệ như secret. Không dùng database password hoặc API key của developer làm SMTP credential.

Ví dụ gửi simple mail:

~~~java
@Service
public class InvoiceMailService {

    private final MailSender mailSender;

    public InvoiceMailService(
            @Qualifier("ociMailSender") MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String from, String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);
        mailSender.send(message);
    }
}
~~~

### Email đồng bộ hay bất đồng bộ?

Không nên gửi email ngay trong transaction tạo invoice nếu việc gửi email chậm hoặc thất bại có thể kéo dài request. Ghi event/outbox sau khi invoice commit rồi để worker gửi mail. Lưu trạng thái delivery, retry có giới hạn và idempotency theo business event.

## 14. Functions: gọi function hay xây worker riêng?

OCI Functions starter cung cấp client để invoke function đã triển khai. Nó không tự động biến ứng dụng Spring Boot hiện tại thành một OCI Function.

Starter spring-cloud-oci-starter-function auto-configure bean Function. API invocation nhận function OCID, endpoint, mode và request body theo contract của starter.

Chọn Functions khi:

- Công việc ngắn, có thể tách thành invocation độc lập.
- Muốn scale theo invocation và runtime serverless.
- Có ranh giới input/output rõ.
- Không cần giữ một consumer process liên tục.
- Có thể chấp nhận cold start/timeout/runtime limits của function.

Chọn Queue + worker khi:

- Work item cần backlog và điều tiết tốc độ.
- Xử lý dài hoặc cần concurrency ổn định.
- Cần kiểm soát retry và dead-letter.
- Muốn worker chạy liên tục hoặc cần local resource lâu dài.

Có thể kết hợp Queue với Function nếu kiến trúc trigger/service hỗ trợ. Không giả định mọi queue message tự động invoke function nếu chưa cấu hình integration.

## 15. Logging: gửi application log hay dùng observability stack?

OCI Logging starter cung cấp bean LogService để gửi log tới OCI Logging. Destination log được chọn bằng spring.cloud.oci.logging.logId.

Ví dụ:

~~~java
PutLogsResponse response = logService.putLog("invoice-created");
~~~

Chọn OCI Logging integration khi ứng dụng cần gửi log tới OCI Logging hoặc muốn gắn log với log resource đã provision.

Không nhầm application log với metrics và distributed tracing:

- Log ghi sự kiện chi tiết.
- Metric tổng hợp số liệu theo thời gian.
- Trace thể hiện đường đi của request qua nhiều service.
- OCI Logging không tự thay thế instrumentation Micrometer/OpenTelemetry.

Không gửi secret, password, token hoặc payload nhạy cảm vào log. Gắn correlation ID và request ID để đối soát; tránh đưa ID có cardinality cao vào metric label.

## 16. Generative AI: ChatModel và EmbeddingModel

OCI Generative AI starter cung cấp các model abstraction Spring-friendly. Starter hiện hành trong tài liệu OCI có thể auto-configure ChatModel và EmbeddingModel.

Chọn ChatModel khi workload cần sinh nội dung/hội thoại. Chọn EmbeddingModel khi cần chuyển văn bản thành vector cho semantic search hoặc retrieval workflow.

Không dùng embedding model thay database hoặc vector index; model chỉ tạo vector. Ứng dụng vẫn cần lưu và truy vấn vector trong một storage/index phù hợp.

Khi chọn model/API, xác định:

- Model ID hoặc dedicated cluster endpoint.
- Region và compartment.
- Input/output token limit.
- Latency và throughput.
- Data sensitivity và logging policy.
- Timeout, retry và quota.
- Cost per request/token.
- Model version và evaluation set.

Trong hệ sinh thái Oracle, cần kiểm tra release line của OCI Generative AI starter và Spring AI Oracle project. Không thêm cả hai integration chỉ vì cùng nói về Generative AI; chọn implementation được tài liệu đúng version khuyến nghị cho application baseline.

## 17. Bản đồ chọn nhanh theo tình huống

| Tình huống | Lựa chọn đầu tiên | API cần bắt đầu |
| --- | --- | --- |
| Lưu PDF, ảnh, archive | OCI Object Storage | Storage hoặc Resource |
| Nạp password/API token | OCI Vault | Property source hoặc VaultTemplate |
| Chạy tác vụ nền có retry | OCI Queue | Queue |
| Thu thập event/telemetry liên tục | OCI Streaming | Streaming |
| Phát alert tới nhiều subscriber | OCI Notifications | Notification |
| Gửi email giao dịch | OCI Email Delivery | MailSender/JavaMailSender |
| Gọi một xử lý serverless | OCI Functions | Function |
| Tạo/start/stop Autonomous DB | Autonomous Database | AutonomousDb |
| Query Oracle database | Oracle JDBC/UCP/Wallet | DataSource, JDBC/JPA |
| Dữ liệu key-value/table/JSON | Oracle NoSQL | NosqlRepository |
| Gửi log tới OCI Logging | OCI Logging | LogService |
| Chat/embedding | OCI Generative AI/Spring AI Oracle | ChatModel, EmbeddingModel |
| Transactional messaging trong Oracle DB | TxEventQ | JMS, OKafka hoặc Stream Binder |

Bảng là điểm bắt đầu. Quyết định cuối cùng phải dựa vào delivery semantics, data model, throughput, transaction và khả năng vận hành.

## 18. Thiết kế workload nhiều dịch vụ

Ví dụ Invoice Service:

~~~mermaid
flowchart TD
    A[Invoice API] --> B[Oracle AI Database]
    A --> C[OCI Object Storage]
    A --> D[OCI Vault]
    B --> E[Outbox event]
    E --> F[OCI Queue]
    F --> G[Invoice worker]
    G --> H[OCI Email Delivery]
    G --> I[OCI Notifications]
    G --> J[OCI Logging]
    G --> K[OCI Function]
~~~

Một luồng xử lý có thể:

1. Nhận request tạo invoice.
2. Ghi invoice metadata vào database.
3. Lưu file PDF vào Object Storage.
4. Ghi outbox event trong transaction database.
5. Publisher gửi event sang Queue.
6. Worker đọc event và kiểm tra idempotency.
7. Worker gửi email qua MailSender.
8. Worker phát notification tới subscriber nếu cần.
9. Worker ghi log operation và kết quả.
10. Một bước xử lý nặng có thể invoke Function.

### 18.1. Không có một transaction bao trùm mọi dịch vụ

Một @Transactional database không tự bao trùm Object Storage, Vault, Queue, Email Delivery và Functions.

Xác định failure boundary:

| Operation | Boundary |
| --- | --- |
| Insert invoice + outbox row | Database transaction |
| Upload PDF | Object Storage API operation |
| Read secret | Vault API operation |
| Publish Queue message | Queue API operation |
| Send email | SMTP operation |
| Publish notification | Notifications API operation |
| Invoke Function | Function invocation |
| Write log | Logging API operation |

Dùng outbox/inbox, idempotency, saga hoặc reconciliation để phối hợp các side effect. Không giữ database transaction mở trong lúc chờ email, function hoặc một external API chậm.

### 18.2. Chọn sync và async

Dùng synchronous API khi client cần kết quả ngay và operation ngắn, có timeout rõ. Dùng async queue/event khi operation kéo dài, có thể retry, cần điều tiết tải hoặc không cần response ngay.

Không biến mọi lời gọi thành async. Nếu operation chỉ là đọc một secret đã cache hoặc query database nhanh, queue sẽ tạo thêm complexity không cần thiết.

## 19. Identity, IAM, region và compartment theo workload

Mỗi service adapter cần identity phù hợp runtime. Ưu tiên Instance Principal cho OCI Compute, Resource Principal cho resource hỗ trợ và Workload Identity cho OKE đã cấu hình. Local development có thể dùng FILE/session token.

Tách policy theo service:

- Storage writer chỉ có quyền ghi object cần thiết.
- Vault reader chỉ đọc secret cần thiết.
- Queue producer chỉ publish.
- Queue consumer chỉ consume/settle theo API.
- Logging writer chỉ ghi log vào destination.
- Function invoker chỉ invoke function cần thiết.
- Autonomous Database provisioning identity có quyền control-plane rộng hơn runtime query identity.

Region phải khớp resource. Compartment là scope quản lý resource/policy. spring.cloud.oci.region.static có thể override region trong auth config file. Không cho rằng property compartment tự cấp quyền hoặc mọi operation đều dùng default compartment.

Không dùng một identity admin cho tất cả service chỉ để giảm số policy. Tách identity giúp giảm blast radius và làm audit rõ hơn.

## 20. Retry, timeout, idempotency và backpressure

Mỗi dịch vụ có semantics riêng. Thiết kế retry ở adapter theo operation và error class.

### Retry

- Retry lỗi transient và throttling theo backoff có jitter.
- Không retry validation, authentication hoặc authorization vô hạn.
- Giới hạn tổng retry budget.
- Tôn trọng retry-after nếu service/API cung cấp.
- Tránh retry đồng thời ở client, service và queue worker mà không có budget chung.

### Timeout

- Connect timeout và read/operation timeout phải phù hợp latency mục tiêu.
- Timeout không chứng minh operation chưa xảy ra.
- Với upload, publish hoặc invocation timeout, cần kiểm tra trạng thái hoặc idempotency key.
- Không để HTTP request chờ vô hạn một managed service.

### Idempotency

- Object Storage: object key/version và conditional write.
- Queue: business idempotency key/inbox.
- Streaming: event ID + checkpoint/replay deduplication.
- Notifications: event identity ở subscriber.
- Email: lưu trạng thái gửi và business event ID; không giả định SMTP retry luôn exactly-once.
- Function: idempotent input hoặc invocation key nếu application protocol hỗ trợ.
- Database: unique constraint/business key.

### Backpressure

- Giới hạn worker concurrency theo downstream capacity.
- Giới hạn in-flight request.
- Không nhận message nhanh hơn khả năng xử lý bền vững.
- Theo dõi queue depth, stream lag và retry backlog.
- Dùng circuit breaker cho dependency có thể outage nếu phù hợp.
- Tách bulkhead giữa email, storage, database và AI workload.

## 21. Bảo mật và data handling

- Không commit API key, private key, SMTP password hoặc secret.
- Dùng Vault/secret injection cho credential.
- Dùng TLS và IAM least privilege.
- Mã hóa dữ liệu theo policy của service.
- Không đưa PII hoặc secret vào notification/log nếu không cần.
- Xác định data residency và region trước khi tạo resource.
- Đặt retention/lifecycle cho object, queue, stream và log.
- Audit quyền truy cập và thay đổi resource.
- Tách quyền provisioning khỏi quyền runtime.
- Giới hạn quyền xóa và quyền quản trị.

Với dữ liệu nhạy cảm, quyết định service cần xét cả nơi dữ liệu được lưu, ai có thể đọc, thời gian lưu và cách xóa/retention.

## 22. Performance, quota và chi phí

Đánh giá service theo workload thực tế:

| Thành phần | Chỉ số cần đo |
| --- | --- |
| Object Storage | Số object, kích thước, throughput, request rate, download pattern |
| Vault | Số secret, read frequency, refresh interval, rotation |
| Queue | Queue depth, oldest message age, delivery attempts, worker throughput |
| Streaming | Partition count, ingest rate, consumer lag, retention |
| Notifications | Publish rate, subscriber count, delivery failures |
| Email | SMTP throughput, recipient volume, retry/bounce |
| Functions | Invocation count, duration, memory, cold start |
| Autonomous Database | Connection pool, CPU/storage, session count, query latency |
| NoSQL | Read/write units, key distribution, index/query pattern |
| Logging | Ingest volume, retention, query frequency |
| Generative AI | Input/output tokens, latency, model quota |

Không chọn theo giá mỗi request riêng lẻ. Tính tổng cost: request, storage, retention, network transfer, compute, retry, log ingest và vận hành.

## 23. Kiểm thử theo service boundary

### Unit test

Mock interface nội bộ như InvoiceFileStore, SecretProvider, OrderPublisher, NotificationSender. Unit test tập trung vào business rules, idempotency và error mapping.

### Context/auto-configuration test

Kiểm tra đúng starter đã tạo bean cần thiết và application context khởi động được. Test dùng fake property/identity phù hợp; không dùng credential production.

### Integration test

- Object Storage: upload/download/checksum/metadata.
- Vault: property source, VaultTemplate, secret rotation.
- Queue: publish/consume/redelivery/dead-letter.
- Streaming: partition/cursor/checkpoint/replay.
- Notifications: topic/subscription/publish.
- Email: SMTP authentication, delivery status và error handling.
- Functions: invoke deployed function và validate response.
- Autonomous DB: control-plane operation trong test compartment.
- JDBC/UCP: connection pool, transaction và query.
- NoSQL: repository CRUD/query theo access pattern.
- Logging: gửi log và kiểm tra destination.
- Generative AI: model config, timeout/quota và output validation.

### Failure injection

- OCI API timeout sau khi server đã nhận request.
- 401/403 do identity/policy.
- 404 do region/compartment/resource ID.
- 429 throttling.
- Queue message được giao lại.
- Stream consumer restart sau business commit trước checkpoint.
- Vault rotation khi nhiều replica đang chạy.
- Email timeout với trạng thái gửi chưa rõ.
- Function invocation timeout.
- Database pool cạn hoặc connection bị reset.

Test trong test compartment và dùng dữ liệu giả. Không thử failure injection phá hủy trên resource production.

## 24. Observability và runbook

Theo dõi metric/log theo service:

| Service | Tín hiệu |
| --- | --- |
| Storage | Upload/download latency, bytes, error, object not found |
| Vault | Read/refresh failure, cache age, version change |
| Queue | Depth, oldest message age, delivery count, DLQ |
| Streaming | Ingest rate, partition lag, cursor age, replay |
| Notifications | Publish failure, subscription status |
| Email | SMTP failure, send latency, bounce/retry |
| Functions | Invocation latency, timeout, error |
| Database | Pool active/wait, query latency, transaction rollback |
| NoSQL | Read/write latency, throttling, hot key |
| Logging | Ingest failure, log volume |
| Generative AI | Model latency, token usage, quota/timeout |

Runbook cần trả lời:

1. Workload đang dùng principal nào?
2. Resource nằm ở region/compartment nào?
3. API request ID là gì?
4. Lỗi là auth, IAM, network, quota hay service failure?
5. Operation có thể đã thành công dù client timeout không?
6. Có thể retry an toàn không?
7. Có cần reconciliation hoặc manual replay không?
8. Ai sở hữu policy/resource và ai được phép thay đổi?

## 25. Bài thực hành: thiết kế tích hợp cho Invoice Platform

**Bối cảnh:** Xây dựng Invoice Platform bằng Spring Boot. Hệ thống nhận invoice, lưu metadata và PDF, phát event để gửi email, đồng thời ghi audit log. Một số invoice cần xử lý ảnh hoặc OCR qua function.

### Phần A — Chọn dịch vụ

1. Dùng Oracle AI Database/JDBC cho invoice metadata.
2. Dùng OCI Object Storage cho PDF.
3. Dùng OCI Vault cho database/SMTP credential.
4. Dùng OCI Queue cho work item gửi email.
5. Dùng OCI Notifications cho alert fan-out nếu cần nhiều subscriber.
6. Dùng OCI Logging cho application/audit log.
7. Dùng OCI Functions cho xử lý ảnh/OCR nếu phù hợp execution limits.

### Phần B — Chọn API

1. Dùng Storage cho upload kèm metadata.
2. Dùng Resource cho luồng đọc file trong API Spring.
3. Dùng Vault property source hoặc VaultTemplate tùy vòng đời secret.
4. Dùng Queue bean để gửi/nhận work item.
5. Dùng MailSender cho email đơn giản.
6. Dùng Function bean để invoke function đã deploy.
7. Dùng JDBC/UCP cho database transaction.

### Phần C — Thiết kế consistency

1. Ghi invoice và outbox row trong cùng transaction.
2. Upload PDF bằng object key idempotent.
3. Publisher đọc outbox và gửi Queue message.
4. Worker dùng inbox/idempotency key.
5. Worker gửi email và lưu trạng thái.
6. Function xử lý ảnh theo invocation contract.
7. Ghi log operation ID và request ID.
8. Reconcile các operation timeout/unknown outcome.

### Phần D — IAM và vận hành

1. Tách identity API, worker và function.
2. Cấp quyền Storage/Vault/Queue/Logging/Functions tối thiểu.
3. Chọn region và compartment.
4. Đặt retry/timeout và DLQ policy.
5. Thiết kế alert cho queue backlog và error rate.
6. Kiểm thử restart, duplicate và throttling.

### Sản phẩm cần nộp

- Workload-to-service decision matrix.
- Sơ đồ kiến trúc và data flow.
- Bảng starter/API cho từng service.
- IAM policy matrix theo workload.
- Mẫu code adapter cho Storage, Vault, Queue và Email.
- Thiết kế outbox/inbox và idempotency.
- Test matrix cho success/failure/retry.
- Dashboard latency, backlog, error và cost drivers.
- Runbook xử lý timeout, 403, DLQ và replay.

## 26. Câu hỏi tự kiểm tra

1. Vì sao phải bắt đầu chọn dịch vụ từ workload?
2. Khi nào dùng Storage API và khi nào dùng Spring Resource?
3. Vì sao Object Storage không phải filesystem?
4. Property source khác VaultTemplate ở điểm nào?
5. Vì sao refresh secret không tự cập nhật DataSource?
6. OCI Queue và OCI Streaming khác nhau ở semantics nào?
7. Notifications phù hợp với fan-out hay work queue?
8. Vì sao TxEventQ khác OCI Queue?
9. Khi nào dùng AQ/JMS, OKafka hoặc TxEventQ binder?
10. AutonomousDb bean phục vụ control plane hay data plane?
11. Khi query Oracle database, cần DataSource/UCP hay AutonomousDb lifecycle API?
12. Oracle NoSQL phù hợp với access pattern nào?
13. Khi nào dùng MailSender và JavaMailSender?
14. Function starter invoke function hay deploy function?
15. OCI Logging có thay thế metrics/tracing không?
16. Vì sao một @Transactional không bao trùm Object Storage và Queue?
17. Khi Queue message được giao lại, consumer cần cơ chế nào?
18. Khi Streaming consumer restart, checkpoint nên được commit ở thời điểm nào?
19. Vì sao timeout không chứng minh operation chưa xảy ra?
20. Làm sao xác minh identity và IAM policy đúng theo từng workload?

## 27. Ghi nhớ

- Chọn service theo workload semantics, không chỉ theo tên dịch vụ.
- Spring Cloud OCI có core starter và service-specific starters; chọn đúng starter cho capability cần dùng.
- Storage phù hợp với operation bucket/object; Resource/WritableResource phù hợp với luồng đọc/ghi theo abstraction Spring.
- Vault property source phù hợp với cấu hình; VaultTemplate phù hợp với truy xuất secret theo yêu cầu.
- OCI Queue phân phối work item; OCI Streaming ingest/consume record theo partition/cursor; Notifications phát pub/sub tới nhiều subscriber.
- TxEventQ là database-native messaging và có API JMS, Kafka-style hoặc Spring Cloud Stream binder.
- AutonomousDb starter quản lý vòng đời Autonomous Database; JDBC/UCP/Wallet dùng để truy vấn dữ liệu.
- Oracle NoSQL repository phù hợp với mô hình key-value/table/JSON theo access pattern.
- Email Delivery tích hợp Spring Mail; Functions starter invoke function đã deploy; Logging starter gửi log qua LogService.
- Generative AI cần chọn đúng ChatModel/EmbeddingModel và version integration.
- Không giả định một transaction bao trùm nhiều managed services; dùng outbox, inbox, idempotency và reconciliation.
- IAM, region, compartment, retry, timeout, retention và observability phải được thiết kế theo từng workload.

## Tài liệu tham khảo

- [Spring Cloud Oracle — Project overview](https://oracle.github.io/spring-cloud-oracle/site/docs/intro/)
- [Spring Cloud OCI — Core starter and service catalog](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [OCI Object Storage integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/storage/)
- [OCI Vault integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/vault/)
- [OCI Queue integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/queues/)
- [OCI Streaming integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/streaming/)
- [OCI Notifications integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/notifications/)
- [OCI Logging integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/logging/)
- [OCI Email Delivery integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/email-delivery/)
- [OCI Functions integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/functions/)
- [OCI Autonomous Database integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/autonomous-database/)
- [Oracle NoSQL Database integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/nosql/)
- [OCI Generative AI integration](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/generative-ai/)
- [Spring Cloud Oracle — Oracle AI Database starters](https://oracle.github.io/spring-cloud-oracle/site/docs/category/oracle-ai-database-starters/)
- [Spring Cloud Oracle — TxEventQ Stream Binder](https://oracle.github.io/spring-cloud-oracle/site/docs/stream-binder/getting-started/)
- [OCI Queue documentation](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm)
- [OCI Streaming documentation](https://docs.oracle.com/en-us/iaas/Content/Streaming/Concepts/streamingoverview.htm)
- [OCI Notifications documentation](https://docs.oracle.com/en-us/iaas/Content/Notification/Concepts/notificationoverview.htm)
