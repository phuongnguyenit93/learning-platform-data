# Đặt giao diện nghiệp vụ và adapter nhà cung cấp ở ranh giới phù hợp

Một ứng dụng Spring Boot có thể gọi thẳng **S3Client**, **BlobServiceClient**, **Storage** hoặc client messaging từ service nghiệp vụ. Cách này nhanh ở giai đoạn đầu, nhưng nếu toàn bộ business service biết bucket, container, kiểu request SDK và mã lỗi provider, mỗi thay đổi về cloud sẽ lan sang logic nghiệp vụ. Ngược lại, tạo một interface cho mọi phương thức của SDK cũng không giúp kiến trúc tốt hơn: chỉ bổ sung các lớp chuyển tiếp, trong khi vẫn mang nguyên mô hình của nhà cung cấp vào ứng dụng.

Giải pháp là xác định **ranh giới trách nhiệm** trước khi đặt giao diện. Business layer mô tả **ứng dụng cần điều gì**; outbound port (giao diện do ứng dụng sở hữu) thể hiện một hợp đồng có ý nghĩa với use case; provider adapter giải quyết **làm điều đó bằng API cloud nào**. Những khác biệt thật về quyền, consistency, retry, idempotency và giao dịch phải được biểu diễn rõ, không thể xóa chỉ bằng cách đặt tên một interface chung.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua thư viện Spring Cloud tương ứng, bao gồm danh tính/quyền, storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh provider. Bài này tập trung vào **thiết kế port và adapter**, đặt từng quyết định tại đúng lớp và tổ chức Spring bean để các lớp phối hợp được trong ứng dụng thực tế.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt **inbound adapter**, **application service**, **outbound port**, **provider adapter**, **Spring Cloud integration** và **SDK client**.
- Xác định ai sở hữu interface và kiểu dữ liệu; giữ request/response/exception của SDK ở đúng ranh giới.
- Thiết kế port đủ hẹp, phản ánh ngữ nghĩa nghiệp vụ và bảo đảm mà use case thật sự cần.
- Viết một triển khai **DocumentStore** bằng Spring Boot, Spring Cloud AWS và S3; phác thảo adapter Azure Blob và Google Cloud Storage có cùng hợp đồng.
- Tổ chức cấu hình nhiều provider, identity, retry, logging và xử lý lỗi mà không để adapter quyết định quyền nghiệp vụ.
- Chỉ ra ranh giới transaction giữa database, storage và message broker; kiểm thử business service độc lập với cloud và kiểm thử adapter bằng contract.

## 2. Xác định ranh giới trước khi viết code

| Lớp / thành phần | Trả lời câu hỏi | Ví dụ trách nhiệm | Không nên chứa |
| --- | --- | --- | --- |
| **Inbound adapter** | Người dùng hoặc hệ thống ngoài gọi ứng dụng qua giao thức gì? | REST controller nhận PDF, kiểm tra format HTTP, ánh xạ kết quả thành status code | Lệnh S3 PutObject hoặc permission IAM |
| **Application service (use case)** | Khi nào thao tác được phép, cần phối hợp những bước nào? | Kiểm tra invoice được phép đính kèm PDF, quyết định object key và metadata cần lưu | Kiểu **PutObjectRequest**, **BlobClient**, endpoint hoặc token |
| **Outbound port** | Ứng dụng cần dịch vụ bên ngoài cam kết điều gì? | **DocumentStore.put(DocumentWrite)**, **DomainEventPublisher.publish(...)** | API đặc thù của S3/Service Bus nếu nghiệp vụ không cần |
| **Provider adapter** | Chuyển hợp đồng ứng dụng sang provider như thế nào? | Ánh xạ document thành bucket/key, gọi SDK, chuyển mã lỗi, giữ giới hạn API | Quyết định user nào được xem invoice hoặc tính tiền |
| **Spring Boot / Spring Cloud** | Ai tạo, cấu hình và inject bean? | Auto-configure SDK client, template, listener, properties và lifecycle tùy starter | Quy tắc nghiệp vụ của tài liệu/hóa đơn |
| **SDK + managed service** | Yêu cầu được gửi và thực thi thế nào? | Credential, HTTP/gRPC, Cloud Storage, IAM/RBAC, lỗi API | Quy tắc phân quyền giữa các người dùng cuối trong ứng dụng |

Trong mô hình **ports and adapters (hexagonal architecture)**, application service phụ thuộc vào outbound port; provider adapter **implements** port. Port là hợp đồng do phía ứng dụng cần dịch vụ quyết định, còn adapter phụ thuộc cả port lẫn SDK. Runtime thì lời gọi đi từ service qua bean adapter, sau đó tới client cloud.

~~~mermaid
flowchart LR
    U[Client HTTP] --> C[REST controller: inbound adapter]
    C --> A[InvoiceDocumentService: use case]
    A --> P[DocumentStore: outbound port]
    P --> D[S3DocumentStore: provider adapter]
    D --> SDK[S3Client: AWS SDK]
    SDK --> CLOUD[Amazon S3]
    AUTO[Spring Cloud AWS starter] -. auto-config / inject .-> SDK
    ID[Credential provider] -. cung cấp identity .-> SDK
~~~

Sơ đồ biểu diễn **luồng gọi lúc chạy**. Quan hệ phụ thuộc ở mức mã nguồn có chiều khác: **InvoiceDocumentService → DocumentStore ← S3DocumentStore → S3Client**. Điều này cho phép thay S3 adapter bằng Azure/GCP hoặc fake khi kiểm thử mà không sửa mã nghiệp vụ.

Một dự án nhỏ chỉ dùng một cloud vẫn có thể đặt trực tiếp SDK trong **infrastructure service** và inject service đó vào use case nếu chi phí abstraction chưa đáng. Port riêng trở nên hữu ích khi một hợp đồng đủ rõ giúp kiểm thử, thay đổi backend, cô lập lỗi provider hoặc tái sử dụng cùng use case. Không cần áp dụng port cho mọi utility method.

## 3. Đặt port ở đâu và ai sở hữu?

**Port thường nằm trong application/core package** hoặc trong module định nghĩa use case. Nó phải có thể được đọc và hiểu mà không cần import SDK. Ví dụ cấu trúc logic:

~~~text
com.example.invoice
├── application
│   ├── InvoiceDocumentService.java
│   ├── port
│   │   └── DocumentStore.java
│   └── model
│       ├── DocumentWrite.java
│       └── StoredDocument.java
├── adapter
│   ├── in
│   │   └── InvoiceDocumentController.java
│   └── out
│       ├── aws
│       │   └── S3DocumentStore.java
│       ├── azure
│       │   └── AzureBlobDocumentStore.java
│       └── gcp
│           └── GcsDocumentStore.java
└── configuration
    └── ProviderWiring.java
~~~

Các thư mục là **ví dụ tổ chức mã**, không phải quy tắc bắt buộc của Spring Boot. Trong Java multi-module, có thể đặt **application/core** ở module không phụ thuộc SDK, để module **infrastructure** import core và SDK. Với một Spring Boot module duy nhất, có thể dùng cùng cấu trúc package và kiểm tra dependency bằng review hoặc architecture tests.

**Điểm đặt đúng của port** là nơi một yêu cầu đã có ý nghĩa nghiệp vụ nhưng chưa biến thành thuật ngữ của provider:

- **Quá sớm:** tạo một **CloudClient** tổng quát có các method **execute**, **send**, **read** và tham số **Object**. Hợp đồng mơ hồ, không phản ánh trường hợp sử dụng.
- **Quá muộn:** định nghĩa **S3Port.putObject(PutObjectRequest)**. Cái tên có “port”, nhưng tầng nghiệp vụ vẫn phải import AWS SDK và biết bucket/key cụ thể.
- **Phù hợp:** **DocumentStore.put(DocumentWrite)** với document ID, key, content type và kết quả mà ứng dụng thật sự cần. Adapter quyết định chuyển những trường này sang **PutObjectRequest**, **BlobUploadOptions** hay **BlobInfo**.

Không biến port thành một bản sao của toàn bộ SDK. Số lượng phương thức và kiểu dữ liệu nên phát triển theo **use case**, không theo danh sách tính năng cloud có sẵn.

## 4. Bắt đầu từ hợp đồng và bảo đảm cần thiết

Giả sử use case: “Khi người dùng có quyền trên hóa đơn, ứng dụng nhận một file PDF và lưu ở object storage; sau đó lưu tham chiếu file để tải xuống về sau.” Trước khi viết port, xác định:

1. **Định danh:** tài liệu gắn với invoice ID nào? Object key có ổn định khi retry không?
2. **Input:** nội dung PDF, content type, dung lượng cho phép và tenant sở hữu.
3. **Output:** use case chỉ cần key hay còn cần version ID, checksum, URL có thời hạn?
4. **Ngữ nghĩa ghi:** cho phép ghi đè, tạo mới duy nhất, versioning hay conditional write?
5. **Lỗi:** lỗi từ chối quyền, không tìm thấy tài nguyên, lỗi tạm thời, lỗi dữ liệu được phân loại ra sao?
6. **Kỳ vọng hoàn tất:** khi method trả thành công, cloud đã xác nhận ghi chưa? Còn bước update database hoặc phát event nào sau đó?

Nếu ứng dụng chỉ cần lưu file và trả key, port có thể nhỏ:

~~~java
// DocumentWrite.java - application model
public record DocumentWrite(
    String objectKey,
    byte[] content,
    String contentType
) {}
~~~

~~~java
// StoredDocument.java - application model
public record StoredDocument(String objectKey) {}
~~~

~~~java
// DocumentStore.java - outbound port
public interface DocumentStore {
    StoredDocument put(DocumentWrite document);
}
~~~

Đây là mẫu **đồng bộ**, phù hợp cho use case đơn giản. Trường **byte[]** dùng để minh họa; trong hệ thống thật phải giới hạn dung lượng và tránh giả định record có mảng byte là bất biến (mảng có thể bị thay đổi từ ngoài). Với file lớn, hợp đồng streaming hay quy trình direct upload sẽ thích hợp hơn. Port này **không hứa** một transaction với database hoặc “exactly once”. Nếu cần tránh ghi đè, phải bổ sung chính xác cam kết create-if-absent/conditional write vào hợp đồng và triển khai bằng cơ chế từng provider hỗ trợ.

**Hợp đồng trả về nên chỉ chứa thông tin nghiệp vụ cần.** Không trả **PutObjectResponse**, **BlobProperties** hoặc cả đối tượng SDK vào service. Nếu thật sự cần version hoặc checksum, định nghĩa kiểu giá trị có ngữ nghĩa chung và giải thích rõ khả năng provider nào đáp ứng; không coi **ETag** của mọi cloud mặc nhiên là cùng một checksum.

## 5. Application service chỉ biết nghiệp vụ và port

Đoạn code sau cố tình loại bỏ tên AWS, Azure, GCP và thông tin cấu hình cloud khỏi application service. Ví dụ giả định bước kiểm tra quyền người dùng trên invoice đã được thực hiện bởi phần authorization của use case; triển khai thực tế phải thực hiện kiểm tra đó trước khi gọi **put**.

~~~java
// InvoiceDocumentService.java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InvoiceDocumentService {
    private final DocumentStore documentStore;

    public InvoiceDocumentService(DocumentStore documentStore) {
        this.documentStore = documentStore;
    }

    public StoredDocument saveInvoicePdf(UUID invoiceId, byte[] pdf) {
        if (invoiceId == null) {
            throw new IllegalArgumentException("Invoice ID is required");
        }
        if (pdf == null || pdf.length == 0) {
            throw new IllegalArgumentException("PDF cannot be empty");
        }

        String objectKey = "invoice-documents/" + invoiceId + ".pdf";
        return documentStore.put(
            new DocumentWrite(objectKey, pdf, "application/pdf"));
    }
}
~~~

Ở đây service quyết định **key có nghĩa với invoice**. Dùng UUID đã xác minh thay vì ghép trực tiếp một chuỗi đường dẫn do người dùng gửi vào key; trong ứng dụng multi-tenant cần đưa tenant ID vào mô hình và kiểm tra ownership trước khi tạo hoặc truy cập object. Chỉ phân vùng object theo tenant **không thay thế authorization**.

**Key ổn định giúp retry hướng tới cùng tài nguyên**; nó không tự bảo đảm request là idempotent hay tạo mới duy nhất. Nếu hai bản PDF khác nhau dùng cùng invoice ID, ghi lại có thể thay thế đối tượng cũ; phiên bản hóa, precondition hoặc định danh theo version phải được quyết định từ nghiệp vụ. Quy tắc “chỉ được nộp một PDF cuối cùng” là của use case, không phải của S3 adapter.

## 6. Adapter Spring Cloud AWS chuyển hợp đồng sang SDK

Với **Spring Boot 3 + Spring Cloud AWS 3.x** và AWS SDK for Java v2, một phương án là thêm starter S3 để Spring cung cấp bean **S3Client**. Adapter dùng client được inject và chuyển **DocumentWrite** thành yêu cầu AWS.

Dependency Maven minh họa, cần quản lý phiên bản bằng BOM tương thích:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Adapter:

~~~java
// S3DocumentStore.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.S3Exception;

@Component
@ConditionalOnProperty(
    prefix = "app.document-store",
    name = "provider",
    havingValue = "aws"
)
public class S3DocumentStore implements DocumentStore {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentStore(
            S3Client s3,
            @Value("${app.document-store.aws.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public StoredDocument put(DocumentWrite document) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(document.objectKey())
            .contentType(document.contentType())
            .build();

        try {
            s3.putObject(request, RequestBody.fromBytes(document.content()));
            return new StoredDocument(document.objectKey());
        } catch (S3Exception ex) {
            throw new DocumentStoreException(
                "Storage service rejected the request", ex);
        } catch (SdkClientException ex) {
            throw new DocumentStoreException(
                "Storage client could not complete the request", ex);
        }
    }
}
~~~

~~~java
// DocumentStoreException.java - exception ở ranh giới port
public class DocumentStoreException extends RuntimeException {
    public DocumentStoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  document-store:
    provider: aws
    aws:
      bucket: ${APP_DOCUMENT_BUCKET}
~~~

**spring.cloud.aws.region.static** là cấu hình cho client AWS trong Spring Cloud AWS. **app.document-store.provider** và **app.document-store.aws.bucket** là property **do ứng dụng định nghĩa** để chọn adapter và cung cấp bucket. **APP_DOCUMENT_BUCKET** là tên tài nguyên lấy từ environment; không đặt access key/secret key trong YAML. SDK nên nhận danh tính từ credential chain/role gắn với workload và được cấp quyền nhỏ nhất đủ ghi đúng bucket/prefix.

Trong ví dụ này adapter chỉ sử dụng **S3Client**; nếu ứng dụng ưu tiên API template có hỗ trợ tương ứng, adapter có thể gọi **S3Template** rồi template gọi SDK. Việc chọn template hay SDK là chi tiết của adapter, không buộc thay **DocumentStore** nếu hợp đồng vẫn được đáp ứng.

Ở production nên phân loại lỗi chi tiết hơn: **AccessDenied/403** thường không đáng retry, **throttling/5xx/timeout** có thể tạm thời, các lỗi **invalid request** cần trả thông tin phù hợp cho caller. Code đơn giản bên trên giữ nguyên cause để dễ chẩn đoán; việc retry, ánh xạ HTTP và thông điệp hiển thị cho người dùng cần chính sách riêng, tránh đưa chi tiết token/bucket nhạy cảm vào response.

## 7. Thay provider: giữ port, thay adapter và cấu hình

Với cùng một nhu cầu **DocumentStore.put**, hình dạng các adapter sẽ khác:

| Vai trò | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Dịch vụ | Amazon S3 | Azure Blob Storage | Cloud Storage |
| Client Java phổ biến | AWS SDK v2 **S3Client** | Azure SDK **BlobServiceClient/BlobClient** | Google Cloud Java **Storage** |
| Tài nguyên đích | Bucket + object key | Storage account + container + blob name | Project + bucket + object name |
| Lời gọi SDK tiêu biểu | **putObject** | **BlobClient.upload(...)** hoặc upload options phù hợp | **Storage.create(...)** / writer API |
| Identity runtime thường dùng | IAM role/default credentials chain | Managed Identity/DefaultAzureCredential | ADC/workload identity/service account |
| Kiểm soát quyền | IAM và bucket policy | Azure RBAC và chính sách storage | IAM trên project/bucket |
| Điểm cần chú ý | Versioning, precondition, object ownership | Block blob, ETag condition, SAS | Generation precondition, object versioning, signed URL |

Adapter Azure được thiết kế để nhận **BlobServiceClient** hoặc một client/template phù hợp qua Spring Cloud Azure, tìm đúng container/blob rồi upload bytes/content type theo Azure SDK. Adapter GCP dùng **Storage** client/template được cấu hình qua Spring Cloud GCP, tạo **BlobInfo** theo bucket/object và gọi API Cloud Storage. Cả hai đều trả **StoredDocument** và chuyển exception SDK thành lỗi của port.

~~~mermaid
flowchart TD
    A[InvoiceDocumentService] --> P[DocumentStore port]
    P -->|provider=aws| W[S3DocumentStore]
    P -->|provider=azure| Z[AzureBlobDocumentStore]
    P -->|provider=gcp| G[GcsDocumentStore]
    W --> C1[S3Client]
    Z --> C2[Azure Blob client]
    G --> C3[Google Cloud Storage client]
    C1 --> S1[Amazon S3]
    C2 --> S2[Azure Blob Storage]
    C3 --> S3[Google Cloud Storage]
~~~

Sơ đồ mô tả **các phương án triển khai**, không có nghĩa cả ba adapter đều phải được kích hoạt trong một environment. Khi dùng **@ConditionalOnProperty** để chọn provider, cần đảm bảo đúng một bean **DocumentStore**. Nếu không có provider hợp lệ, service có thể báo thiếu bean; nếu nhiều adapter cùng hoạt động, injection theo type có thể mơ hồ. Với hệ thống chủ động sử dụng nhiều provider trong cùng một lần chạy, hãy dùng **@Qualifier** hoặc một router rõ ràng theo yêu cầu nghiệp vụ thay vì dựa vào việc Spring tự chọn.

Không nên tuyên bố “thay provider chỉ cần đổi một property” khi bên dưới khác nhau về versioning, giới hạn kích thước, khả năng streaming, consistency, encryption, permission và cách tính phí. Port giữ được sự ổn định **chỉ trong phạm vi hợp đồng thực sự chung**; nếu use case cần chức năng riêng, phải mở rộng hợp đồng có chủ đích hoặc có capability cụ thể cho provider đó.

## 8. Thiết kế hợp đồng: đủ hẹp, không quá trừu tượng

### 8.1. Tránh interface sao chép SDK

Ví dụ không phù hợp:

~~~java
// KHÔNG nên đặt trong application layer:
public interface StoragePort {
    software.amazon.awssdk.services.s3.model.PutObjectResponse put(
        software.amazon.awssdk.services.s3.model.PutObjectRequest request);
}
~~~

Service nghiệp vụ vẫn phải tạo **PutObjectRequest**, hiểu bucket và xử lý **PutObjectResponse**; interface trên chỉ đổi vị trí lời gọi, **không tạo ranh giới phụ thuộc**. Khi chuyển Azure, API và kiểu dữ liệu service đều phải đổi.

Một abstraction quá rộng cũng khó giữ:

~~~java
// KHÔNG nên thiết kế chỉ để bao phủ mọi SDK:
public interface CloudEverything {
    Object execute(String provider, String operation, Object payload);
}
~~~

Code dùng nhiều ép kiểu runtime, khó kiểm chứng input/output và không nói rõ cam kết về side effect. Nếu thao tác chung chỉ là đọc/ghi PDF, **DocumentStore** đủ rõ hơn.

### 8.2. Đừng ẩn các khác biệt mà nghiệp vụ thực sự cần

Giả sử nghiệp vụ cần “chỉ tạo tài liệu một lần, không bao giờ ghi đè”. Port chỉ có **put** mà không định nghĩa ngữ nghĩa ghi sẽ không đủ: S3, Blob và GCS có cơ chế conditional write khác nhau. Có thể cần một thao tác rõ:

~~~java
public interface ImmutableDocumentStore {
    // Trả DocumentAlreadyExists nếu object đã tồn tại.
    StoredDocument createIfAbsent(DocumentWrite document);
}
~~~

**DocumentAlreadyExists** phải là lỗi chung do ứng dụng định nghĩa; mỗi adapter ánh xạ status/precondition tương ứng. Chỉ dùng thao tác “HEAD rồi PUT” tách rời có thể gặp race condition giữa hai request. Với việc tạo duy nhất, phải sử dụng cơ chế conditional request nguyên tử được provider hỗ trợ và test race condition thực tế; nếu không đáp ứng thì không được khẳng định contract đã được bảo đảm.

Tương tự, nếu ứng dụng cần giữ **version ID**, điều kiện **ETag**, một signed URL hoặc khả năng xóa sau TTL, hãy xác định xem đây là nhu cầu cốt lõi của mọi provider hay một capability riêng. Không gộp hàng chục tham số tùy chọn thành một request chung khiến mỗi adapter phải lặng lẽ bỏ qua những tham số không hỗ trợ.

### 8.3. Khi nào không cần tự tạo port?

Không có yêu cầu bắt buộc mọi service phải có interface. Ví dụ, một batch nội bộ chuyên dùng AWS S3, có ba lời gọi SDK và không có logic nghiệp vụ phức tạp, có thể dùng một Spring **S3ArchiveService** trong infrastructure module. Hoặc nếu **Spring Data JpaRepository** đã biểu diễn chính xác các thao tác dữ liệu, service có thể inject repository Spring Data ngay mà không phải tạo interface lặp lại mọi CRUD.

Nên thêm port khi nó **đặt tên rõ một khả năng của ứng dụng**, giúp cô lập dependency, tạo seam để kiểm thử hoặc biểu diễn một hợp đồng cần nhiều implementation. Không thêm chỉ vì quy tắc “mỗi class phải có interface”.

## 9. Tách port theo loại dịch vụ và ngữ nghĩa

Ứng dụng có thể dùng storage, messaging, dữ liệu và secret cùng lúc; không nên tạo một **CloudProviderPort** quản lý cả bốn:

| Nhu cầu use case | Port có thể phù hợp | Adapter provider |
| --- | --- | --- |
| Lưu PDF của invoice | **DocumentStore.put/get** theo document key | S3 / Azure Blob / GCS |
| Thông báo invoice đã phát hành | **InvoiceEventPublisher.publish** | SQS/SNS / Service Bus / Pub/Sub |
| Lưu dữ liệu invoice | **InvoiceRepository** hoặc Spring Data repository phù hợp | PostgreSQL trên RDS/Azure Database/Cloud SQL; datastore-specific repository/SDK khi cần |
| Đọc token của đối tác | **PartnerCredentialReader.get** nếu có nhu cầu runtime | AWS Secrets Manager / Azure Key Vault / Google Secret Manager |

**Port mô tả ý định nghiệp vụ**, không mô tả hành động kỹ thuật quá chung. **InvoiceEventPublisher** cụ thể và dễ kiểm thử hơn **CloudMessaging.execute(action)**. Nhưng nếu nhiều module cùng có nhu cầu publish sự kiện, một port mang ý nghĩa hạ tầng ổn định như **DomainEventPublisher** có thể hợp lý; giới hạn abstraction được quyết định bởi hợp đồng và ownership thực tế.

### 9.1. Messaging: ranh giới publication và consumer

~~~mermaid
flowchart LR
    A[Invoice service] --> P[InvoiceEventPublisher]
    P --> B[Messaging publisher adapter]
    B --> Q[SQS / Service Bus / PubSub]
    Q --> L[Listener / subscriber adapter]
    L --> U[InvoiceEventHandler]
~~~

**Publish thành công** thường chỉ nói broker đã chấp nhận message; không chứng minh consumer hoàn thành. Port có thể trả một kết quả publish hoặc async completion với ý nghĩa này, tránh hứa hẹn “đã xử lý” nếu broker không cung cấp bảo đảm đó.

Inbound listener adapter chịu trách nhiệm chuyển payload và metadata provider thành một command/event hợp lệ cho handler, xác nhận message theo quy tắc riêng của broker. Business handler chịu trách nhiệm idempotency, state transition và validation nghiệp vụ. SQS visibility timeout, Service Bus lock và Pub/Sub ack deadline khác nhau; adapter phải theo dõi completion của handler trước khi ack/complete nếu đó là hợp đồng được yêu cầu.

### 9.2. Data access: không ép mọi datastore thành JPA

Với managed PostgreSQL trên AWS RDS, Azure Database hay Google Cloud SQL, ứng dụng có thể dùng Spring Data JPA/JDBC và driver tiêu chuẩn; ranh giới repository tương đối ổn định. Với DynamoDB, Cosmos DB, Firestore hoặc Spanner, model partition/query, transaction và consistency khác đáng kể. Chỉ định nghĩa repository port chung khi **những truy vấn và bảo đảm cần thiết có thể được đáp ứng**; không sao chép **JpaRepository** sang mọi datastore bằng một tên mới.

### 9.3. Secret: ranh giới config và runtime

Secret chỉ cần lúc startup có thể được cấp qua cơ chế config integration; secret được đọc hoặc xoay vòng trong runtime có thể cần client/adapter riêng. Port ứng dụng không nên trả toàn bộ cloud SDK secret response hay log secret value. Cần quyết định cache, TTL, refresh, quyền đọc và giới hạn thời gian sống của secret. Một tên secret giống nhau ở ba cloud không có nghĩa quyền hoặc quá trình rotation giống nhau.

## 10. Vị trí thích hợp cho identity và authorization

Có **hai câu hỏi bảo mật độc lập**:

1. **Người dùng cuối có quyền làm use case này không?** Đây là trách nhiệm của application/domain authorization và inbound security. Ví dụ user A không được tải PDF của invoice thuộc user B, dù service backend có quyền đọc toàn bộ bucket.
2. **Workload có quyền gọi tài nguyên cloud không?** Đây là trách nhiệm cấu hình cloud identity và resource policy. AWS dùng IAM role/credentials chain, Azure thường dùng Managed Identity và RBAC, Google Cloud dùng ADC/workload identity/service account cùng IAM.

Adapter không nên tự đọc thông tin đăng nhập từ source code hoặc ghi credentials vào log. Spring Cloud starter và SDK client được cấu hình để lấy identity từ môi trường chạy; adapter nhận **client bean đã được cấu hình**, sau đó gọi dịch vụ. Credential hợp lệ không đồng nghĩa đã có quyền; lỗi **403/AccessDenied/PermissionDenied** thường cần kiểm tra identity thực tế, action, resource và policy.

| Vị trí | Điều cần làm | Ví dụ |
| --- | --- | --- |
| Controller / security boundary | Xác thực caller, kiểm tra kích thước/content type request | Chặn request không có token trước khi đọc body lớn |
| Application service | Kiểm tra ownership và use-case permission | Invoice ID thuộc tenant đang thao tác |
| Provider adapter | Chọn resource/key, tránh rò rỉ dữ liệu qua lỗi và log | Không đưa connection string hoặc secret vào exception public |
| Infrastructure/client config | Gắn workload identity, endpoint, region/project và timeout | Role chỉ được ghi bucket/prefix của ứng dụng |
| Managed service | Kiểm tra IAM/RBAC/resource policy của workload | Từ chối hành động khi thiếu quyền trên tài nguyên |

Không coi **prefix object key** là biện pháp phân quyền duy nhất: application phải xác thực/ủy quyền request, và IAM/RBAC phải giới hạn những tài nguyên workload thực sự được dùng.

## 11. Lỗi, retry và quyết định ở ranh giới nào?

Không phải mọi lỗi cloud nên đi thẳng tới controller dưới dạng SDK exception. Cần phân biệt **phân loại lỗi kỹ thuật** và **quyết định nghiệp vụ**:

| Tình huống | Adapter biết gì? | Application/controller cần quyết định gì? |
| --- | --- | --- |
| S3 trả **AccessDenied** | Mã provider, status 403, request ID | Báo lỗi vận hành phù hợp; không giả định caller cuối thiếu quyền invoice |
| Blob/GCS trả precondition failure | Điều kiện ghi bị vi phạm | Có phải conflict đã có tài liệu, cần version mới hoặc reject? |
| SDK timeout sau PUT | Không nhận được kết quả cuối; cloud **có thể đã ghi** | Kiểm tra trạng thái, dùng idempotency và chính sách retry |
| Throttling/429/5xx | Dịch vụ tạm thời không phục vụ hoặc chạm quota | Có retry không, số lần và deadline tổng, có báo request tạm thất bại không? |
| Sai dữ liệu input/business rule | Adapter không nên quyết định quyền user | Validation tại application/inbound; trả lỗi hợp lệ cho caller |

Adapter có thể ánh xạ exception thành **DocumentStoreUnavailable**, **DocumentAlreadyExists**, **DocumentStoreForbidden** hoặc một **DocumentStoreException** kèm category. Tên chính xác do ứng dụng lựa chọn. Giữ root cause nội bộ để có request ID/cloud error code khi cần debug, nhưng không để response HTTP lộ token, secret, connection string, tên tài nguyên nhạy cảm.

Retry ở SDK, Spring Retry, Reactor hoặc framework messaging **có thể chồng nhau**, dẫn đến nhiều lần gọi ngoài ý muốn. Giới hạn retry theo lỗi tạm thời, thêm exponential backoff/jitter, deadline, quota và idempotency. Đặc biệt, adapter chỉ nên tự động retry thao tác có side effect khi đã hiểu rõ hợp đồng idempotency của request.

**Application service** quyết định kết quả nghiệp vụ khi lưu PDF thất bại: giữ trạng thái chờ, báo lỗi, thử lại theo operation ID hay thực hiện cleanup. **Adapter** chỉ nên biết cách biến quyết định đó thành API provider an toàn.

## 12. Ranh giới giao dịch: một port không tạo transaction phân tán

Giả sử use case làm ba việc:

~~~text
InvoiceApplicationService
  1. InvoiceRepository.save(metadata)      -> managed PostgreSQL
  2. DocumentStore.put(pdf)                -> S3/Blob/GCS
  3. InvoiceEventPublisher.publish(event)  -> SQS/Service Bus/PubSub
~~~

**@Transactional** trên Spring Data JPA/JDBC thường chỉ quản lý transaction của database, không tự bao gồm object storage hoặc message broker. Nếu bước 2 đã thành công nhưng bước 3 thất bại, rollback database cũng không tự xóa PDF đã upload. Nếu publish đã thành công mà app mất kết nối trước khi nhận response, gửi lại có thể tạo event trùng.

Một thiết kế có thể:

- Ghi **invoice state** và bản ghi **outbox event** trong cùng transaction database.
- Có worker đọc outbox và publish message; khi consumer nhận, dùng event ID để xử lý idempotent.
- Lưu PDF theo key ổn định, theo dõi trạng thái **PENDING/READY/FAILED**; xác định cách retry/cleanup nếu một bước lỗi.
- Dùng precondition/version phù hợp khi hai request đồng thời lưu cùng tài liệu.

Giải pháp cụ thể tùy latency và yêu cầu nhất quán. **Transactional outbox** hỗ trợ đồng bộ hóa database với sự kiện theo mô hình eventual delivery; nó không tự khiến object storage tham gia cùng transaction SQL. Adapter không nên giả lập hai phase commit khi dịch vụ cloud không cung cấp bảo đảm đó.

## 13. Đồng bộ, bất đồng bộ và streaming có thay đổi port không?

**Có thể**, nếu mô hình hoàn tất là một phần của hợp đồng. Ví dụ một port đồng bộ:

~~~java
public interface DocumentStore {
    StoredDocument put(DocumentWrite document);
}
~~~

Khi ứng dụng thật sự cần non-blocking I/O, có thể định nghĩa:

~~~java
import java.util.concurrent.CompletionStage;

public interface AsyncDocumentStore {
    CompletionStage<StoredDocument> put(DocumentWrite document);
}
~~~

Hoặc với một ứng dụng dùng Reactor/WebFlux xuyên suốt:

~~~java
import reactor.core.publisher.Mono;

public interface ReactiveDocumentStore {
    Mono<StoredDocument> put(DocumentWrite document);
}
~~~

**CompletionStage** là abstraction Java, còn **Mono** đặt dependency lên Reactor trong application port. Cả hai có thể hợp lý, nhưng cần chọn một hợp đồng rõ về **khi nào request bắt đầu**, completion, cancellation và retry; không thay đổi signature chỉ vì provider có một client async. Bọc SDK blocking trong **Mono** không tự biến network I/O thành non-blocking. Với file lớn, **byte[]** vẫn làm tốn bộ nhớ; cần hợp đồng stream/chunk hoặc direct upload phù hợp, có backpressure và giới hạn buffer.

Một port không nên đồng thời cung cấp đủ các biến thể sync/async/reactive nếu use case chỉ dùng một kiểu. Lựa chọn mô hình dựa trên API inbound, tải dự kiến, khả năng SDK/driver, transaction và vận hành. Cũng không thay toàn bộ JPA/JDBC bằng Mono khi hệ thống vẫn dùng database blocking.

## 14. Chọn và wiring implementation trong Spring

Spring Boot có thể tự cấu hình SDK client thông qua starter, nhưng **DocumentStore** là bean của ứng dụng. Có các phương án:

| Bối cảnh | Wiring gợi ý | Điều cần kiểm tra |
| --- | --- | --- |
| Một provider ở mỗi environment | Mỗi adapter có **@ConditionalOnProperty(provider=...)** | Đúng một **DocumentStore** match; cấu hình hợp lệ |
| Nhiều provider cố định cùng chạy | Các bean có tên và **@Qualifier** rõ | Use case chọn đúng adapter, tránh **NoUniqueBeanDefinitionException** |
| Provider chọn theo tenant/request | Một router thực hiện **DocumentStore** và giữ map adapter đã cấu hình | Không tin trực tiếp provider do caller đưa vào, kiểm tra quyền và cô lập tenant |
| Chạy unit test | Fake/mock **DocumentStore** | Test không đòi SDK/cloud credentials |
| Integration test | Bean adapter thật với emulator/test resource | Client endpoint, bean graph và security config đúng |

Khi tạo **routing adapter**, business service vẫn gọi một port. Router dùng lựa chọn có nguồn gốc đáng tin cậy (ví dụ tenant config đã xác thực) để ủy thác tới adapter tương ứng. Nếu route có thể thay đổi giữa các lần retry, cần ghi lại **provider + resource + object ID** đã chọn để tránh một tài liệu bị lưu ở hai backend ngoài ý muốn.

**Không cần** định nghĩa ba bean client bằng tay chỉ để có ba adapter nếu starter đã hỗ trợ auto-configuration đúng nhu cầu. Khi có custom client, kiểm tra **@ConditionalOnMissingBean**, condition evaluation report và cách template/listener lấy client. Không bật tùy tiện **allow-bean-definition-overriding** để che xung đột wiring.

## 15. Kiểm thử theo ranh giới, tránh phụ thuộc cloud ở unit test

### 15.1. Unit test application service

Kiểm tra service tạo key đúng và gọi port với dữ liệu cần thiết. Ví dụ với Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class InvoiceDocumentServiceTest {
    @Test
    void savesPdfUsingBusinessKeyWithoutCloudSdk() {
        DocumentStore store = mock(DocumentStore.class);
        when(store.put(any(DocumentWrite.class))).thenAnswer(call -> {
            DocumentWrite request = call.getArgument(0);
            return new StoredDocument(request.objectKey());
        });

        InvoiceDocumentService service = new InvoiceDocumentService(store);
        UUID invoiceId = UUID.randomUUID();
        byte[] pdf = {1, 2, 3};

        StoredDocument result = service.saveInvoicePdf(invoiceId, pdf);

        ArgumentCaptor<DocumentWrite> captor =
            ArgumentCaptor.forClass(DocumentWrite.class);
        verify(store).put(captor.capture());
        DocumentWrite saved = captor.getValue();
        assertEquals("invoice-documents/" + invoiceId + ".pdf",
            saved.objectKey());
        assertArrayEquals(pdf, saved.content());
        assertEquals("application/pdf", saved.contentType());
        assertEquals(saved.objectKey(), result.objectKey());
    }
}
~~~

Test này xác minh **hành vi của service**, không chỉ tự gọi mock. Nên bổ sung test PDF rỗng/ID null, kiểm tra quyền, retry theo operation ID và validation trước khi port được gọi. Unit test không cần credentials và không chứng minh adapter đã upload thành công.

### 15.2. Unit/contract test provider adapter

Với S3, có thể mock **S3Client** để xác minh adapter tạo **PutObjectRequest** có bucket/key/content type đúng, và mô phỏng **S3Exception** để xác minh chuyển lỗi thành **DocumentStoreException**. Tương tự Azure adapter xác nhận chọn đúng container/blob và GCP adapter xác nhận bucket/object, metadata và mapping exception.

Một **contract test suite** hữu ích chạy các ca chung trên từng triển khai **DocumentStore**: put rồi get, cùng key ghi lại, permission denied, input không hợp lệ, object không tồn tại, timeout/ retry nếu contract định nghĩa, và race condition khi create-if-absent. Nếu adapter không thể đáp ứng một bảo đảm, sửa contract hoặc chỉ rõ capability; không giả kết quả như nhau chỉ vì method signature giống.

### 15.3. Integration test và cloud smoke test

| Mức | Công cụ/điều kiện | Điều xác minh |
| --- | --- | --- |
| Spring context | **ApplicationContextRunner**, context test | Đúng adapter theo provider property, bean dependency được inject |
| Emulator | LocalStack cho phần AWS tương ứng; Azurite cho Blob; emulator hoặc test project phù hợp cho GCP | Serialization, request/response, luồng đọc/ghi và lỗi cơ bản |
| Cloud test environment | Bucket/container/test project riêng, workload identity thật, quyền tối thiểu | IAM/RBAC, endpoint/region, TLS/network, quota và đặc tính provider |
| Resilience test | Timeout, throttling, trả lỗi sau khi side effect xảy ra | Idempotency, retry có giới hạn, cleanup và observability |

Emulator không mô phỏng đầy đủ IAM/RBAC, private endpoint, quota, retry, consistency và behavior của cloud thật. Dữ liệu test phải tách biệt, có cleanup và không chứa secret sản xuất. Không bật debug để log access key/token, request body hay file nhạy cảm.

## 16. Đánh giá một ranh giới có phù hợp hay chưa

Hãy tự hỏi:

1. Nếu thay **S3Client** bằng **BlobClient**, **InvoiceDocumentService** và unit test của use case có cần import SDK mới không?
2. Port có nói rõ **put** bảo đảm gì về ghi đè, completion và lỗi chưa?
3. Adapter có thể thay đổi cách xác thực, endpoint hoặc retry mà không phải sửa business rule không?
4. Permission của người dùng cuối có được kiểm tra trước khi gọi cloud và workload identity có bị giới hạn bằng IAM/RBAC không?
5. Một request timeout sau khi cloud đã nhận có thể được xử lý an toàn với key/operation ID ổn định không?
6. Unit test business chạy được khi không có mạng, credentials, bean Spring hoặc cloud emulator không?
7. Nếu use case cần một tính năng riêng của provider, hợp đồng có biểu diễn sự khác biệt rõ ràng hay adapter đang lặng lẽ bỏ qua nó?

Nếu không trả lời được, hãy xem lại **ownership của port**, ngữ nghĩa hợp đồng hoặc trách nhiệm adapter trước khi thêm một tầng wrapper mới.

## 17. Bài tập thực hành

**Bài tập 1 — Tìm ranh giới bị rò rỉ.** Một **InvoiceService** tạo **PutObjectRequest**, gọi **S3Client**, bắt **S3Exception** và trả **PutObjectResponse**. Hãy chuyển nó thành **InvoiceDocumentService → DocumentStore → S3DocumentStore**. Chỉ ra file nào được phép import AWS SDK và test nào không cần khởi động Spring.

**Bài tập 2 — Chuyển Azure/GCP.** Giữ **DocumentWrite**, **StoredDocument** và **DocumentStore**. Phác thảo hai adapter cho Azure Blob Storage và Google Cloud Storage. Nêu rõ cách ánh xạ container/bucket, key, content type, identity và lỗi provider; liệt kê ba đặc tính storage cần kiểm tra trước khi khẳng định chúng tương đương.

**Bài tập 3 — Ghi duy nhất.** Hai request đồng thời muốn lưu PDF cuối cùng cho một invoice. Port **put** hiện tại có thể ghi đè. Thiết kế **createIfAbsent** với kết quả **AlreadyExists** và giải thích tại sao bước **HEAD → PUT** không đủ để loại trừ race. Đề xuất kiểm thử contract cho từng provider.

**Bài tập 4 — Sự kiện sau upload.** Use case lưu invoice metadata trong PostgreSQL, upload PDF và publish event. Hãy đánh dấu ranh giới của **InvoiceRepository**, **DocumentStore**, **InvoiceEventPublisher**; mô tả ba cửa sổ lỗi và một workflow có trạng thái **PENDING/READY/FAILED**, outbox và idempotency.

**Bài tập 5 — Multi-tenant.** Một service dùng cùng bucket cho nhiều tenant, caller cung cấp invoice ID và tenant ID. Phân biệt nơi xác minh quyền tenant, nơi tạo object key, nơi cấp IAM quyền workload và nơi route giữa hai provider nếu một tenant ở Azure. Vì sao tự thêm tenant ID vào key chưa đủ an toàn?

**Bài tập 6 — Chọn abstraction phù hợp.** Một batch chuyên dùng AWS chỉ upload 10 file mỗi ngày; một sản phẩm SaaS có hàng nghìn khách hàng cần chuyển object storage giữa nhiều provider. Cân nhắc số adapter, độ ổn định hợp đồng, unit test và chi phí bảo trì. Khi nào một infrastructure service gọi SDK trực tiếp đủ tốt, khi nào port có giá trị rõ ràng?

## 18. Ghi nhớ

- **Application service phụ thuộc vào port do ứng dụng sở hữu; provider adapter triển khai port và phụ thuộc SDK.** Spring Cloud chủ yếu giúp cấu hình/wiring các bean và tích hợp với dịch vụ managed.
- **Port mô tả khả năng của use case** bằng kiểu dữ liệu và bảo đảm mà nghiệp vụ cần; không sao chép request/response/exception của SDK hoặc cố che khác biệt thật giữa AWS, Azure và Google Cloud.
- **Đặt authorization nghiệp vụ tại application/security boundary; đặt workload identity, endpoint và resource permission ở infrastructure/cloud.** Hai lớp kiểm tra quyền không thay thế nhau.
- Một lời gọi thành công đến object storage **không** tạo transaction với database hay message broker; cần thiết kế idempotency, trạng thái và outbox/compensation khi use case có nhiều side effect.
- Chọn abstraction ở mức đủ dùng: **service → port → adapter** khi mang lại hợp đồng rõ ràng và khả năng kiểm thử; SDK trực tiếp trong một infrastructure service vẫn có thể phù hợp với trường hợp nhỏ, ổn định và ít thay đổi.
- Kiểm thử đúng ranh giới: **unit test business không có cloud**, **adapter/contract test cho mapping và ngữ nghĩa**, **cloud smoke test cho identity, quyền, network và các bảo đảm thực tế**.
