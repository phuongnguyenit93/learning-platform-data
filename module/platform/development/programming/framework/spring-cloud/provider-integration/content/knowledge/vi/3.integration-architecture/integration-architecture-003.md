# Chọn starter, template, repository hay SDK trực tiếp theo nhu cầu

Khi tích hợp Spring Boot với một dịch vụ managed, câu hỏi đầu tiên thường là: “Nên dùng Spring Cloud starter, template, Spring Data repository hay gọi SDK của AWS, Azure, Google Cloud trực tiếp?”. Bốn lựa chọn này **không nằm trên cùng một cấp độ**. **Starter** chủ yếu đưa dependency và cấu hình tự động vào ứng dụng; **template** và **repository** là hai kiểu API lập trình ở cấp cao; còn **SDK client** là API hướng tới dịch vụ do nhà cung cấp cloud phát hành. Một ứng dụng hoàn toàn có thể **cài starter nhưng vẫn gọi SDK trực tiếp**, hoặc dùng repository cho dữ liệu nghiệp vụ và template cho messaging trong cùng một use case.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun hướng đến thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud tương ứng: cấu hình danh tính và quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và so sánh khác biệt giữa các cloud provider. Bài này tập trung xây dựng **tiêu chí chọn lớp tích hợp theo nhu cầu**, thay vì mặc định sử dụng một kiểu API cho mọi dịch vụ.

## 1. Kết quả học tập

Sau khi học, bạn có thể:

- Giải thích mục đích và ranh giới của starter, template, repository và SDK client.
- Phân tích yêu cầu nghiệp vụ, tính năng cloud, số lượng provider, mô hình đồng bộ/bất đồng bộ và khả năng kiểm thử để chọn cách tích hợp.
- Chọn API hợp lý cho object storage, messaging, cơ sở dữ liệu managed và secret management.
- Tổ chức mã theo service, port và provider adapter khi cần giữ nghiệp vụ độc lập với nhà cung cấp.
- Nhận diện chi phí đánh đổi: lượng mã, khả năng truy cập tính năng chuyên biệt, vòng đời thư viện, quan sát, bảo mật và độ khó nâng cấp.
- Lập kế hoạch kiểm thử từ unit test đến integration test với cloud thật.

## 2. Bốn khái niệm: quan hệ giữa chúng là gì?

| Thành phần | Bản chất | Thường mang lại | Không tự giải quyết |
| --- | --- | --- | --- |
| **Starter** | Gói dependency và cấu hình Spring Boot/Spring Cloud | Đưa SDK/thư viện tích hợp vào classpath, đăng ký bean, bind properties, cấu hình listener/template khi có hỗ trợ | Không phải API nghiệp vụ; không tự bảo đảm quyền IAM/RBAC hay kết nối mạng |
| **Template** | API tác vụ do framework cung cấp | Rút gọn thao tác gửi/nhận, serialize, chuyển đổi message/resource, tích hợp Spring | Không bao phủ chắc chắn mọi API và tính năng riêng của provider |
| **Repository** | API hướng tới collection/aggregate dữ liệu, thường từ Spring Data | CRUD, derived query, paging/sorting và tích hợp persistence tùy datastore | Không phải abstraction mặc định cho object storage, queue hay secret |
| **SDK trực tiếp** | Client thư viện chính thức của provider | Truy cập API gần dịch vụ, model request/response, tùy chỉnh chi tiết, tính năng mới | Không tự tách phụ thuộc provider khỏi business logic |

Một số cách kết hợp hợp lệ:

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Application service]
    B --> C[Repository: dữ liệu nghiệp vụ]
    B --> D[Storage / Messaging port]
    D --> E[Provider adapter]
    E --> F[Template của Spring Cloud]
    E --> G[SDK client trực tiếp]
    F --> G
    H[Cloud starter] -. cung cấp dependency và auto-config .-> F
    H -. có thể tạo bean .-> G
    C --> I[(Managed database)]
    G --> J[Managed cloud API]
~~~

**Điểm then chốt:** Chọn starter và chọn API lập trình là **hai quyết định khác nhau**. Ví dụ, thêm **spring-cloud-aws-starter-s3** để Spring Cloud AWS cấu hình **S3Client**, rồi inject **S3Client** vào adapter và gọi **putObject** của AWS SDK. Không nhất thiết phải dùng **S3Template** chỉ vì đã dùng starter. Tương tự, Spring Data repository có thể sử dụng driver hoặc SDK bên dưới nhưng ứng dụng lập trình theo model dữ liệu.

## 3. Bắt đầu bằng đặc tính của use case

Trước khi chọn thư viện, hãy trả lời sáu câu hỏi:

1. **Thao tác chính là gì?** Ghi object, publish message, đọc/ghi aggregate, truy vấn dữ liệu, hay đọc secret?
2. **Cần tính năng phổ thông hay chuyên biệt?** CRUD đơn giản khác với multipart upload, batch write, điều khiển phiên bản object, session/lock của message hoặc thao tác admin.
3. **API đồng bộ, async hay reactive?** HTTP request chờ kết quả, xử lý nền theo message hay luồng reactive với backpressure?
4. **Ứng dụng gắn với một cloud hay cần chạy nhiều cloud?** Mức độ di động thực sự cần thiết là bao nhiêu và có các khác biệt dịch vụ nào phải giữ lại?
5. **Những bảo đảm quan trọng là gì?** Transaction, idempotency, thứ tự message, retry, giới hạn độ trễ, consistency, quyền truy cập, audit.
6. **Đội phát triển có thể kiểm thử và vận hành cách tích hợp đó không?** Có emulator, test resource, observability, kế hoạch nâng cấp BOM và SDK không?

Sơ đồ chọn hướng tiếp cận ở mức đầu tiên:

~~~mermaid
flowchart TD
    A[Use case cần dịch vụ managed] --> B{Lưu và truy vấn aggregate dữ liệu?}
    B -->|Có| C{Có Spring Data module phù hợp?}
    C -->|Có| D[Đánh giá Repository]
    C -->|Không| E[Đánh giá driver / SDK]
    B -->|Không| F{Có template hỗ trợ đúng chức năng?}
    F -->|Có| G{Cần tính năng API chuyên biệt?}
    G -->|Không| H[Đánh giá Template]
    G -->|Có| I[Đánh giá SDK client]
    F -->|Không| I
    D --> J[Kiểm tra giới hạn của abstraction]
    E --> J
    H --> J
    I --> J
    J --> K[Chọn starter / cấu hình client / identity / tests]
~~~

Đây là **heuristic**, không phải luật cố định. Ví dụ Cloud Storage là dịch vụ object storage nhưng không phải một database quan hệ để tự động áp dụng Spring Data JPA. Một SDK vẫn có thể phù hợp hơn template khi số lượng API được dùng nhỏ nhưng cần điều khiển chi tiết. Ngược lại, repository là lựa chọn tốt nếu model truy vấn của Spring Data trùng với nhu cầu và module tương thích.

## 4. Starter: nên thêm khi nào?

### 4.1. Vai trò

Spring Cloud starter thường gom dependency và bật auto-configuration có điều kiện cho các thành phần như client, properties, converter, template hoặc listener container. Nó giúp Spring quản lý cấu hình, dependency injection và lifecycle. Tên artifact, property và tính năng cụ thể phụ thuộc **provider và phiên bản**.

Ví dụ với **Spring Boot 3 và Spring Cloud AWS 3.x**, dependency Maven cho S3 có dạng:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Ứng dụng có thể khai báo region và bucket như sau:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${APP_STORAGE_BUCKET}
~~~

Trong ví dụ, **spring.cloud.aws.region.static** là property của Spring Cloud AWS; **app.storage.bucket** do ứng dụng tự định nghĩa. Không có cơ chế mặc định nào tự hiểu property ứng dụng nếu ta chưa bind hoặc inject nó. Phiên bản được quản lý qua **BOM tương thích**; một starter không bảo đảm Spring Boot, Spring Cloud và SDK hoạt động đúng nếu tùy tiện trộn phiên bản.

### 4.2. Khi nên dùng hoặc bỏ qua starter

**Ưu tiên starter** khi:

- Dự án đã dùng Spring Boot và thư viện Spring Cloud tương ứng hỗ trợ tốt dịch vụ cần tích hợp.
- Muốn có client bean, property binding, listener hoặc template sẵn có theo đúng phiên bản.
- Đội phát triển cần thống nhất cấu hình giữa local/test/production và giảm mã khởi tạo client lặp lại.

**Có thể chỉ dùng SDK/driver** khi:

- Starter không tồn tại hoặc không hỗ trợ phiên bản Boot/SDK và dịch vụ cần dùng.
- Muốn dùng một tập API rất nhỏ, cần cập nhật SDK sớm, hoặc không muốn thêm các integration layer không cần thiết.
- Cần cấu hình client chuyên biệt mà thư viện tích hợp không cho phép tùy chỉnh an toàn.

Tuy nhiên, tự tạo SDK client bằng **@Bean** cũng có thể kết hợp với starter: nhiều auto-configuration sử dụng **@ConditionalOnMissingBean** để nhường cho bean do ứng dụng khai báo. **Phải xác minh condition report và bean graph**; không nên giả định mọi starter đều có cùng hành vi back off.

## 5. Template: giảm mã cho thao tác tác vụ

**Template** thường biểu diễn hành động như **send**, **receive**, **upload** hoặc **download**, đồng thời gói một phần chuyển đổi dữ liệu và tích hợp với Spring. Đây là lựa chọn phù hợp khi thao tác ứng dụng nằm trong phạm vi API do template cung cấp.

Ví dụ với **Spring Cloud AWS SQS dòng 3.x**, một service có thể sử dụng **SqsTemplate** để gửi event:

~~~java
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.stereotype.Service;

record OrderPlaced(String orderId, long occurredAtEpochMs) {}

@Service
public class OrderEventPublisher {
    private final SqsTemplate sqsTemplate;

    public OrderEventPublisher(SqsTemplate sqsTemplate) {
        this.sqsTemplate = sqsTemplate;
    }

    public void publish(OrderPlaced event) {
        sqsTemplate.send("order-events", event);
    }
}
~~~

Dependency tương ứng trong family Spring Cloud AWS:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-sqs</artifactId>
</dependency>
~~~

Ví dụ giả định ứng dụng đã cấu hình tên queue, permission và message converter hỗ trợ payload **OrderPlaced** theo phiên bản dùng. **Gửi thành công** thường chỉ xác nhận queue/broker đã nhận message theo API; nó **không** xác nhận consumer đã xử lý xong. Các lựa chọn như FIFO, ordering, deduplication, visibility timeout, dead-letter và xác nhận xử lý cần được thiết kế riêng.

Template đặc biệt hữu ích khi:

- Phần lớn lời gọi là thao tác thông dụng mà template đã hỗ trợ.
- Cần tích hợp converter, listener, lifecycle hoặc convention Spring.
- Muốn giảm mã biến đổi request/response lặp lại.

Chuyển sang **SDK trực tiếp** ở một adapter cụ thể nếu cần tính năng provider mới, tham số điều khiển đặc biệt hoặc thao tác cấp thấp mà template chưa hỗ trợ. Đừng tự bọc một API template bằng nhiều lớp chỉ đổi tên phương thức nhưng không bổ sung hợp đồng nghiệp vụ hay lợi ích kiểm thử.

**Lưu ý:** Không có một interface **CloudTemplate** thống nhất giữa AWS, Azure và Google Cloud. Ví dụ SQS, Azure Service Bus và Google Pub/Sub khác nhau về mô hình queue/topic, ack, subscription, retry và ordering. Kiểm tra tên template/listener và khả năng tương ứng theo tài liệu chính thức của đúng phiên bản.

## 6. Repository: khi use case thực sự là dữ liệu có cấu trúc

**Spring Data repository** biểu diễn thao tác với aggregate và truy vấn dữ liệu. Nó có ý nghĩa khi datastore và module Spring Data cung cấp model phù hợp với ứng dụng. Ví dụ, nếu dùng **PostgreSQL managed** trên **Amazon RDS**, **Azure Database for PostgreSQL** hoặc **Google Cloud SQL**, ta có thể dùng **Spring Data JPA** và driver PostgreSQL; logic CRUD của ứng dụng gần như không cần biết database đang được host ở cloud nào.

Ví dụ entity và repository tối giản:

~~~java
// InvoiceEntity.java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "invoices")
public class InvoiceEntity {
    @Id
    private UUID id;

    @Column(nullable = false, unique = true)
    private String externalId;

    protected InvoiceEntity() {}

    public InvoiceEntity(UUID id, String externalId) {
        this.id = id;
        this.externalId = externalId;
    }

    public UUID getId() { return id; }
    public String getExternalId() { return externalId; }
}
~~~

~~~java
// InvoiceRepository.java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InvoiceRepository
        extends JpaRepository<InvoiceEntity, UUID> {
    Optional<InvoiceEntity> findByExternalId(String externalId);
}
~~~

~~~java
// InvoiceService.java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository invoices;

    public InvoiceService(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @Transactional
    public UUID register(String externalId) {
        return invoices.save(
            new InvoiceEntity(UUID.randomUUID(), externalId)).getId();
    }
}
~~~

Ví dụ giả định dự án đã có **spring-boot-starter-data-jpa**, PostgreSQL JDBC driver, datasource, migration cho bảng và quy tắc uniqueness/idempotency. Trong thực tế cần kiểm tra externalId trùng và xử lý unique constraint khi có race condition.

**Repository phù hợp** với truy vấn có cấu trúc, transaction database và entity lifecycle. Nó **không** tự biến upload S3 thành entity persist hoặc biến một queue thành cơ sở dữ liệu; cần xem bản chất service.

Với datastore mang tính provider như **Azure Cosmos DB**, **Google Cloud Firestore** hoặc **Google Cloud Spanner**, có thể tồn tại Spring Data module hoặc template tương ứng ở những phiên bản cụ thể. Khi cân nhắc, cần kiểm tra:

- Module còn được duy trì và tương thích với Spring Boot/JDK trong dự án không?
- Derived query/paging/transaction của module có đúng với khả năng datastore không?
- Có chức năng quan trọng nào chỉ SDK trực tiếp mới hỗ trợ không?
- Có chênh lệch về mô hình dữ liệu, indexing, consistency, chi phí query hoặc partition key không?

Không mặc định rằng annotation repository của JPA chạy tương đương trên Cosmos DB, Firestore hay Spanner. **Transaction của repository** cũng thường chỉ bao phủ phạm vi datastore đó; không tự bao gồm lời gọi object storage hoặc publish message.

## 7. SDK trực tiếp: kiểm soát rõ API của provider

SDK chính thức thường là lựa chọn phù hợp nếu cần tính năng chuyên biệt, model request/response đầy đủ, tối ưu hiệu năng hoặc tùy chỉnh timeout, HTTP client, credential, retry. **Trực tiếp** ở đây là adapter gọi SDK API; không có nghĩa phải bỏ Spring hay tự tạo client mới ở mỗi request.

Ví dụ adapter ghi object bằng **AWS SDK for Java v2** với client được Spring inject:

~~~java
// DocumentStorage.java
public interface DocumentStorage {
    void save(String objectKey, byte[] content, String contentType);
}
~~~

~~~java
// S3DocumentStorage.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3DocumentStorage implements DocumentStorage {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentStorage(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public void save(
            String objectKey, byte[] content, String contentType) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(objectKey)
            .contentType(contentType)
            .build();

        s3.putObject(request, RequestBody.fromBytes(content));
    }
}
~~~

**Điểm đáng chú ý:** Dù dùng **SDK trực tiếp**, bean **S3Client** vẫn có thể được Spring Cloud AWS starter auto-configure. Adapter sở hữu mapping giữa ngữ nghĩa ứng dụng và API của AWS; service nghiệp vụ chỉ biết **DocumentStorage**. Ví dụ sử dụng byte array cho đơn giản: file lớn nên xem xét streaming, multipart upload hoặc direct upload theo đặc tính từng cloud. Phải bổ sung validation, authorization và cách ánh xạ exception ở ứng dụng thật.

Trường hợp SDK trực tiếp thường có lợi thế rõ:

- **Object storage:** multipart/resumable upload, ký URL có thời hạn, xử lý versioning hoặc điều kiện ghi theo ETag/precondition.
- **Messaging:** cấu hình FIFO, message attributes đặc thù, batch operation, dead-letter/redrive API và yêu cầu thứ tự riêng.
- **Data:** query API, bulk/batch, consistency hoặc mô hình transaction chuyên biệt mà abstraction chưa biểu diễn đầy đủ.
- **Security/administration:** thao tác secret rotation, key management, chính sách hoặc thao tác quản trị khó biểu diễn bằng template.

Những trường hợp này làm tăng phụ thuộc vào provider. Nên đặt mã SDK ở **infrastructure adapter** và chỉ đưa khả năng cần thiết qua port. Nếu yêu cầu nghiệp vụ thật sự cần tính năng không có ở cloud khác, tốt hơn là biểu diễn tính năng đó rõ ràng thay vì che giấu khác biệt dẫn tới hành vi sai.

## 8. Áp dụng cho AWS, Azure và Google Cloud

### 8.1. Object storage

| Use case | AWS | Azure | Google Cloud | Hướng chọn |
| --- | --- | --- | --- | --- |
| Upload/download thông thường | Amazon S3 | Azure Blob Storage | Cloud Storage | Starter + template nếu API đủ; hoặc starter + SDK client |
| URL truy cập có thời hạn | S3 presigned URL | Blob SAS hoặc cơ chế cấp quyền phù hợp | Signed URL | SDK/client có hỗ trợ ký URL; xem quyền ký và thời hạn |
| Upload lớn/chia phần | Multipart upload | Block blob/chunk upload | Resumable upload | Dùng API/builder của provider phù hợp |
| Metadata, versioning, điều kiện ghi | Tính năng theo S3 | Tính năng theo Blob | Tính năng theo GCS | Kiểm tra request model và ngữ nghĩa thực tế trước khi trừu tượng hóa |

S3 dùng **bucket/key**, Azure Blob dùng **container/blob**, GCS dùng **bucket/object**. Đây là những mô hình gần nhau nhưng khác về authentication, ACL/IAM/RBAC, điều kiện ghi, tier lưu trữ và cách tính phí. Không nên chọn repository JPA cho thao tác object storage chỉ vì muốn một method **save**.

### 8.2. Messaging

| Nhu cầu | AWS | Azure | Google Cloud | Hướng chọn |
| --- | --- | --- | --- | --- |
| Gửi message phổ biến | SQS/SNS | Service Bus | Pub/Sub | Template/publisher abstraction nếu đáp ứng hợp đồng |
| Consumer do Spring quản lý | SQS listener | Service Bus consumer/integration | Pub/Sub subscriber/integration | Listener/container đúng phiên bản, có kiểm soát ack |
| Ordering/dedup/retry đặc thù | SQS FIFO, visibility, DLQ | Sessions/locks, dead-letter | Ordering keys, ack deadline, dead-letter | SDK hoặc cấu hình chuyên biệt khi template chưa đủ |

**Đừng dùng repository để giả lập queue** nếu use case cần delivery semantics của broker. Một lệnh **publish** thành công cũng không có nghĩa consumer đã xử lý xong. Handler cần cân nhắc giao lại nhiều lần, idempotency, poison message và quan sát retry/dead-letter. Nếu service vừa ghi database vừa phát event, hãy xem xét **transactional outbox** để tránh mất event giữa hai hệ thống; transaction của JPA không tự bao trùm queue.

### 8.3. Cơ sở dữ liệu managed

Với **PostgreSQL/MySQL managed** trên RDS, Azure Database hoặc Cloud SQL, **Spring Data JPA/JDBC** có thể phù hợp vì truy cập qua giao thức database tiêu chuẩn. Lựa chọn driver, pooling, network, TLS, IAM database authentication/identity (nếu dùng), schema migration và transaction phải cấu hình riêng.

Với **DynamoDB, Cosmos DB, Firestore hoặc Spanner**, trước tiên xác định module Spring Data/template đang được duy trì và giới hạn của nó. Nếu không có abstraction phù hợp, gọi client/SDK trực tiếp trong adapter được thiết kế cho partition/query model thực tế. Không ép các datastore khác nhau vào một kiểu **JpaRepository** giả.

### 8.4. Secret management

Đọc secret từ **AWS Secrets Manager**, **Azure Key Vault** hoặc **Google Secret Manager** thường sử dụng config integration có hỗ trợ, Spring Cloud integration hoặc SDK tương ứng. **Repository** thường không phải abstraction phù hợp cho secret. Chọn cách lấy secret dựa trên lúc cần đọc (startup hay runtime), cache/refresh, rotation, policy và audit. Tránh copy secret vào source code, file cấu hình commit lên git hoặc log; ưu tiên workload identity và quyền chỉ đọc đúng secret cần thiết.

### 8.5. Những gì giống và khác nhau

| Khía cạnh | Có thể thống nhất trong ứng dụng | Cần kiểm tra riêng theo provider |
| --- | --- | --- |
| Nghiệp vụ | Use case, port, dữ liệu đầu vào và kết quả | Tính năng mà cloud khác không hỗ trợ |
| Spring | Bean lifecycle, dependency injection, validation, conditional configuration | Starter, template/repository API, property namespace, tương thích phiên bản |
| Security | Nguyên tắc least privilege, tránh hard-code credential | IAM role, Managed Identity/RBAC, ADC/service account/workload identity |
| Độ tin cậy | Timeout budget, retry có giới hạn, idempotency, logging | Mã lỗi, quota, consistency, acknowledgment/locking |
| Kiểm thử | Unit test theo port, smoke test theo use case | Emulator, credentials, endpoint và hành vi dịch vụ thật |

## 9. Thiết kế ranh giới: nghiệp vụ ổn định, adapter thay đổi

Với yêu cầu “tạo hóa đơn, lưu PDF, phát sự kiện”, kiến trúc có thể kết hợp ba kiểu API khác nhau mà không làm nghiệp vụ biết tên dịch vụ cloud:

~~~mermaid
flowchart LR
    A[InvoiceApplicationService] --> B[InvoiceRepository]
    A --> C[DocumentStorage port]
    A --> D[EventPublisher port]
    B --> E[(Managed PostgreSQL)]
    C --> F[S3 / Blob / GCS adapter]
    F --> G[SDK client hoặc template]
    G --> H[Object storage]
    D --> I[SQS / Service Bus / PubSub adapter]
    I --> J[Messaging template / SDK]
    J --> K[Messaging service]
~~~

**InvoiceRepository** thể hiện thao tác persistence và transaction trên database. **DocumentStorage** biểu diễn nhu cầu ghi tài liệu, còn **EventPublisher** biểu diễn nhu cầu thông báo sự kiện. Phía sau mỗi port có thể dùng starter, template hoặc SDK tùy chức năng. Nếu chỉ dùng một cloud, port vẫn hữu ích cho unit test và giữ logic authorization/idempotency tại đúng lớp; nếu đa cloud, nó cung cấp điểm thay adapter.

Nhưng tách port **không tạo giao dịch phân tán**: ghi DB, upload object và publish event có thể thành công/thất bại độc lập. Cần xác định thứ tự thực hiện, trạng thái chờ, compensation, retry và transactional outbox khi yêu cầu nhất quán đòi hỏi. Với PDF có thể ghi lại được, một workflow lưu metadata trạng thái **PENDING** rồi upload và đánh dấu **READY** có thể phù hợp hơn giả định mọi bước luôn nguyên tử.

Một port tốt nên biểu diễn ngữ nghĩa thật của ứng dụng:

~~~java
public interface DocumentStorage {
    void save(String objectKey, byte[] content, String contentType);
}

public interface EventPublisher {
    void publishInvoiceCreated(String invoiceId);
}
~~~

Một port kém thường chỉ bê nguyên SDK request class ra ngoài, ví dụ buộc service nghiệp vụ nhận **PutObjectRequest** hoặc **BlobUploadOptions**. Cách đó làm việc thay provider khó hơn mà không mang lợi ích về rõ trách nhiệm.

## 10. Hiệu năng, đồng bộ, bất đồng bộ và reactive

Sự tiện lợi của template hoặc repository **không đồng nghĩa nhanh/chậm hơn** một cách tuyệt đối. Hiệu năng thường phụ thuộc mạng, payload, connection pooling, batching, serialization, pagination, retry và mô hình thực thi.

- Với **blocking SDK/JDBC**, lời gọi chờ I/O và chiếm thread trong lúc chờ. Cần giới hạn concurrency, connection pool, timeout và dung lượng hàng đợi xử lý.
- Với **async SDK** hoặc listener bất đồng bộ, throughput có thể tốt hơn khi khối lượng I/O lớn, nhưng cần quản lý backpressure, retry, shutdown và kết quả hoàn tất.
- Với **reactive repository/client**, lợi ích phụ thuộc khả năng non-blocking thực sự của toàn bộ pipeline; gọi blocking SDK bên trong reactive chain vẫn gây tắc nghẽn nếu không cách ly hợp lý.
- Template có thể dùng SDK sync hoặc async bên dưới tùy phiên bản. Đọc đúng contract của template trước khi mặc định một lời gọi là không chặn.
- Các tính năng upload streaming, batch write, bulk insert hoặc consumer concurrency nên chọn dựa trên tải thực tế và dịch vụ cụ thể.

Đối với messaging, cần phân biệt **độ trễ phát message** với **thời gian hoàn thành xử lý nghiệp vụ ở consumer**. Đối với repository, phân trang và truy vấn theo index thường quyết định chi phí hơn việc có dùng abstraction Spring Data hay không.

## 11. Bảo mật và quyền: abstraction không thay thế identity

Dù dùng starter, template, repository hay SDK, ứng dụng vẫn cần danh tính và quyền truy cập phù hợp:

| Provider | Identity thường ưu tiên trên cloud | Quyền cần kiểm tra |
| --- | --- | --- |
| AWS | IAM role của workload, credential chain phù hợp | IAM policy, resource policy/bucket policy và action cụ thể |
| Azure | Managed Identity hoặc identity phù hợp qua Azure SDK | Azure RBAC, policy và cấu hình network của tài nguyên |
| Google Cloud | Workload Identity / service account + ADC | IAM roles/permissions trên project, bucket, topic hoặc secret |

Với database managed còn có authentication/authorization của chính database, network/private endpoint, TLS và đôi khi cơ chế identity riêng. **Spring Boot khởi động thành công không chứng minh quyền cloud đúng**; nhiều SDK chỉ lấy token hoặc gọi endpoint khi có request đầu tiên.

Vẫn cần phân biệt hai lớp quyền: **người dùng cuối** có được phép thực hiện use case hay không và **workload identity** có được phép gọi tài nguyên cloud hay không. Client dùng role quyền cao không thể thay thế business authorization. Không lưu token, access key, connection string nhạy cảm vào log; sử dụng secret management và chính sách rotation thích hợp.

## 12. Kế hoạch kiểm thử theo mức abstraction

| Mức kiểm thử | Điều cần xác nhận | Kỹ thuật phù hợp |
| --- | --- | --- |
| **Unit test service** | Quy tắc nghiệp vụ, lựa chọn port, lỗi và idempotency | Mock/fake **DocumentStorage**, **EventPublisher**, repository |
| **Unit/adapter test** | Ánh xạ request/response/exception của template hoặc SDK | Mock client, kiểm tra bucket/key, queue, converter, mã lỗi |
| **Spring context test** | Starter, property, conditional bean, qualifier, bean wiring | ApplicationContextRunner hoặc context test có cấu hình |
| **Integration test emulator** | Giao tiếp thật qua SDK, serialization, listener và luồng đọc/ghi | LocalStack cho phần AWS được hỗ trợ, Azurite cho Azure Blob, emulator phù hợp nếu dịch vụ GCP cung cấp |
| **Cloud smoke test** | Danh tính/role, quyền, network, endpoint, quota, policy và đặc tính cloud | Tài nguyên test riêng, workload identity thật, dữ liệu thử được cleanup |

Ví dụ **DocumentUploadService** kiểm tra payload, tạo object key từ định danh hóa đơn và gọi port. Unit test kiểm tra chính hành vi đó mà không cần AWS credential:

~~~java
// DocumentUploadService.java
public class DocumentUploadService {
    private final DocumentStorage storage;

    public DocumentUploadService(DocumentStorage storage) {
        this.storage = storage;
    }

    public void uploadInvoice(String invoiceId, byte[] pdf) {
        if (pdf == null || pdf.length == 0) {
            throw new IllegalArgumentException("PDF is empty");
        }
        storage.save("invoices/" + invoiceId + ".pdf",
            pdf, "application/pdf");
    }
}
~~~

~~~java
// DocumentUploadServiceTest.java
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;

class DocumentUploadServiceTest {
    @Test
    void delegatesValidInvoiceToStoragePort() {
        DocumentStorage storage = mock(DocumentStorage.class);
        DocumentUploadService service = new DocumentUploadService(storage);
        byte[] bytes = {10, 20};

        service.uploadInvoice("123", bytes);

        verify(storage).save(
            eq("invoices/123.pdf"), same(bytes), eq("application/pdf"));
    }
}
~~~

Kiểm thử này xác nhận **service** chọn đúng khóa và content type rồi giao dữ liệu cho **DocumentStorage**. Có thể bổ sung test PDF rỗng để xác minh service ném lỗi mà không gọi port. Khi tích hợp, cần kiểm thử riêng adapter SDK, cấu hình Spring và quyền trên cloud; unit test không chứng minh object thực sự đã được lưu vào bucket.

Emulator có thể không hỗ trợ đầy đủ IAM/RBAC, rotation, consistency, dead-letter hay network/private endpoint. Kết hợp kiểm thử context, emulator và cloud smoke test sẽ cho bức tranh đáng tin cậy hơn chỉ chạy unit test hoặc chỉ thử bằng UI cloud.

## 13. Những lỗi chọn abstraction thường gặp

| Tình huống | Vì sao chưa hợp lý | Hướng điều chỉnh |
| --- | --- | --- |
| Dùng repository JPA để biểu diễn S3 object hoặc message queue | Không phản ánh ngữ nghĩa storage/messaging | Dùng storage port + template/SDK hoặc messaging adapter |
| Dùng SDK client trong controller và business service | Lộ kiểu request/exception SDK, khó kiểm thử và thay provider | Đưa SDK vào adapter, chỉ đưa hợp đồng cần thiết qua port |
| Thêm starter rồi vẫn khởi tạo SDK client ở mọi request | Lặp cấu hình, tốn tài nguyên kết nối, sai lifecycle | Inject client singleton do Spring quản lý |
| Dùng template cho API provider mà template chưa hỗ trợ | Không kiểm soát được tính năng chuyên biệt | Gọi SDK trực tiếp tại adapter cần tính năng đó |
| Tự khai báo bean client và không kiểm tra auto-config | Có thể bị back off ngoài dự kiến, trùng bean hoặc sai client | Xem condition report, bean type/name/qualifier |
| Tin rằng repository transaction bao gồm publish message | Database và queue không tự dùng một transaction | Outbox, idempotency hoặc workflow bù trừ |
| Muốn đa cloud nhưng đồng nhất mọi provider chỉ bằng tên method | Che mất khác biệt về bảo đảm và quyền | Chuẩn hóa phần chung, biểu diễn khác biệt thật trong adapter |
| Xem lỗi 403 như lỗi template/repository | Lỗi có thể đến từ danh tính, policy hoặc quyền tài nguyên | Lần theo SDK response, credential và IAM/RBAC |

Nếu gặp lỗi khi triển khai, hãy kiểm tra theo đúng ranh giới: **dependency/starter → điều kiện tạo bean → property → adapter/template/repository → SDK/driver → credential/network → service**. Thiếu bean ở startup khác bản chất với lỗi **PermissionDenied** trong request runtime; tăng retry không sửa được cấu hình IAM sai.

## 14. Bài tập ra quyết định

**Bài tập 1 — Lưu ảnh hồ sơ.** Một REST API cần upload ảnh tối đa 5 MB vào một bucket; ứng dụng chỉ chạy trên AWS trong năm đầu, có thể chuyển Azure về sau. Chọn **starter**, **template hay SDK**, có cần port không và phải kiểm thử những gì? Gợi ý: ưu tiên khả năng kiểm tra quyền tải lên, giới hạn file, object key và lifecycle; dùng port nếu muốn unit test và tránh lộ S3 request class.

**Bài tập 2 — Đồng bộ đơn hàng.** Sau khi ghi đơn hàng vào PostgreSQL managed, cần phát sự kiện tới SQS hoặc Pub/Sub; consumer có thể xử lý lại message. Chọn **Spring Data repository**, **messaging template/listener** hoặc **SDK**, rồi đề xuất transaction outbox và idempotency ở consumer. Giải thích tại sao gửi message thành công không đồng nghĩa với hoàn thành nghiệp vụ ở hệ thống nhận.

**Bài tập 3 — API đặc thù.** Một hệ thống cần multipart upload, điều kiện ghi, phân loại lỗi và retry tùy chỉnh. Một template chỉ hỗ trợ upload cơ bản. Nên bọc template bằng nhiều lớp hay dùng SDK? Hãy đề xuất adapter, metric và test case cho thao tác ghi trùng, timeout sau ghi thành công và lỗi bị từ chối quyền.

**Bài tập 4 — Chọn datastore.** Một ứng dụng có dữ liệu quan hệ, truy vấn join và transaction nhiều bảng; nhóm triển khai cân nhắc RDS PostgreSQL, Cloud SQL PostgreSQL và một NoSQL service. Khi nào có thể giữ cùng **JpaRepository**? Khi nào phải đổi model dữ liệu và dùng repository/SDK khác?

**Bài tập 5 — Secret.** Hệ thống chạy trên Azure có Managed Identity và đọc API key từ Key Vault. Lập quyết định dùng config integration hay SDK runtime dựa trên vòng đời secret và yêu cầu rotation; mô tả các permission cần kiểm tra và cách tránh lộ key trong log.

## 15. Ghi nhớ

- **Starter** giúp đưa dependency và auto-configuration vào Spring Boot; **template**, **repository** và **SDK trực tiếp** mới là các API dùng khi lập trình. Chúng có thể được kết hợp.
- **Repository** mạnh cho aggregate và truy vấn dữ liệu khi Spring Data module phù hợp; **template** tiện cho thao tác lặp lại đã được framework bao phủ; **SDK** thích hợp khi cần toàn bộ khả năng hoặc cấu hình chuyên biệt của provider.
- Chọn theo **hợp đồng nghiệp vụ, tính năng API, delivery/transaction semantics, sync/async, bảo mật, kiểm thử và độ khó vận hành**, không theo độ ngắn của ví dụ code.
- Với đa cloud, dùng **port và provider adapter** để giữ ranh giới nghiệp vụ rõ ràng; đừng giả định AWS, Azure và Google Cloud có quyền, lỗi và bảo đảm dữ liệu giống nhau.
- Tách biệt **quyết định chọn API** khỏi **cấu hình identity, IAM/RBAC, timeout/retry và quản lý kết nối**: abstraction tiện đến đâu vẫn cần kiểm tra các yếu tố này.
