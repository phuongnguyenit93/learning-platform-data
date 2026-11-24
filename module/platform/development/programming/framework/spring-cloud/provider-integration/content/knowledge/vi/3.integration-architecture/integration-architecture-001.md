# Luồng xử lý từ mã nghiệp vụ qua Spring đến SDK và dịch vụ

Trong một ứng dụng Spring Boot, lệnh “lưu tệp lên cloud”, “gửi thông điệp” hay “đọc secret” thường chỉ xuất hiện dưới dạng một lời gọi phương thức. Phía sau lời gọi đó là nhiều thành phần cùng tham gia: mã nghiệp vụ, Spring Framework, thư viện tích hợp Spring Cloud, SDK của nhà cung cấp, cơ chế xác thực và dịch vụ managed trên cloud. Hiểu chính xác luồng này giúp thiết kế ứng dụng ít phụ thuộc nhà cung cấp, xác định đúng nơi xử lý lỗi và tìm được nguyên nhân khi triển khai thất bại.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Phạm vi là thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** thông qua những thư viện Spring Cloud tương ứng, từ cấu hình danh tính/quyền cho đến storage, messaging, dữ liệu, secret, kiểm thử và quan sát hệ thống.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Vẽ và giải thích được đường đi của một yêu cầu từ API hoặc tác vụ nền đến một dịch vụ cloud, rồi quay trở lại ứng dụng.
- Phân biệt chức năng của **Spring Boot**, **Spring Cloud integration**, **cloud SDK**, **credential provider** và **managed service**.
- Chỉ ra chỗ nên đặt luật nghiệp vụ, mã phụ thuộc nhà cung cấp, cấu hình quyền, xử lý lỗi và retry.
- Áp dụng cùng một mô hình cho AWS S3, Azure Blob Storage, Google Cloud Storage và mở rộng sang hàng đợi/thông điệp.
- Đọc triệu chứng lỗi để khoanh vùng: wiring của Spring, cấu hình endpoint/region, danh tính, quyền, kết nối mạng hay chính dịch vụ.

## 2. Các lớp tham gia và trách nhiệm

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| **Mã nghiệp vụ (domain/application)** | Quy định **khi nào** cần đọc/ghi dữ liệu, kiểm tra quy tắc nghiệp vụ và điều phối use case | Sau khi xác nhận hồ sơ hợp lệ, gọi cổng lưu tài liệu |
| **Spring Boot / Spring Framework** | Tạo và quản lý bean, dependency injection, cấu hình, vòng đời ứng dụng, web endpoint, transaction nội bộ | Tiêm một đối tượng triển khai giao diện lưu trữ vào service |
| **Spring Cloud integration** | Cung cấp starter, auto-configuration, template/abstraction, listener và tích hợp với hệ sinh thái Spring tùy thư viện | Spring Cloud AWS S3, Spring Cloud Azure Storage Blob, Spring Cloud GCP Storage |
| **SDK / client library của provider** | Tạo yêu cầu API, chuyển đổi dữ liệu, xác thực hoặc ký yêu cầu, thực hiện I/O và chuyển lỗi API thành exception | AWS SDK for Java v2, Azure SDK for Java, Google Cloud Java client libraries |
| **Credential provider / identity** | Tìm và làm mới danh tính dùng để gọi API; không tự cấp quyền cho danh tính đó | AWS IAM role, Azure Managed Identity, Google Cloud Application Default Credentials |
| **Managed service** | Xử lý yêu cầu ở phía cloud; kiểm tra quyền, lưu/đọc dữ liệu, nhận và phân phối thông điệp | Amazon S3/SQS, Azure Blob Storage/Service Bus, Google Cloud Storage/Pub/Sub |

Sơ đồ logic khi ứng dụng ghi một đối tượng vào object storage:

~~~mermaid
flowchart LR
    U[HTTP / scheduled job] --> C[Controller / job handler]
    C --> B[Business service]
    B --> P[Storage port]
    P --> A[Provider adapter]
    A --> T[Spring Cloud template, nếu dùng]
    T --> K[Cloud SDK client]
    A --> K
    K --> N[HTTPS / gRPC tùy API]
    N --> S[Managed cloud service]
    F[Spring Boot + Spring Cloud auto-config] -. tạo và tiêm bean .-> A
    F -. khởi tạo client .-> K
    I[Credential provider] -. cấp danh tính .-> K
~~~

**Đây là sơ đồ trách nhiệm, không phải một chuỗi lời gọi bắt buộc đi qua tất cả các hộp.** Spring Boot chủ yếu khởi tạo và ghép các đối tượng lúc startup. Tại runtime, adapter có thể gọi thẳng SDK đã được Spring tiêm vào; nếu dùng template của Spring Cloud thì adapter gọi template, rồi template dùng SDK. SDK gửi yêu cầu qua transport phù hợp với API. Với một số dịch vụ, Spring Cloud cung cấp listener hoặc abstraction riêng; mức hỗ trợ thay đổi theo provider và phiên bản.

Đặt một **port** (giao diện do ứng dụng sở hữu) giữa service nghiệp vụ và adapter là một lựa chọn kiến trúc hữu ích khi cần kiểm thử độc lập, đổi provider hoặc hỗ trợ nhiều backend. Với ứng dụng nhỏ chỉ dùng một dịch vụ, gọi client trực tiếp từ một infrastructure service vẫn có thể hợp lý; điều cần tránh là rải tên bucket, quyền IAM, mã lỗi và kiểu dữ liệu SDK vào toàn bộ nghiệp vụ.

## 3. Phân biệt luồng khởi động với luồng xử lý yêu cầu

### 3.1. Startup: Spring ghép các thành phần

Khi ứng dụng khởi động:

1. Dependency và BOM tương thích xác định phiên bản Spring Boot, thư viện Spring Cloud và SDK.
2. Spring Boot đọc cấu hình từ YAML, biến môi trường và các nguồn cấu hình đã bật.
3. Auto-configuration của starter phù hợp có thể tạo bean cho SDK client, template, converter hoặc listener container. Điều kiện tạo bean phụ thuộc classpath, cấu hình và phiên bản.
4. Credential chain được cấu hình hoặc phát hiện theo cơ chế của provider. Một số SDK chỉ lấy token thực tế khi thực hiện yêu cầu đầu tiên, vì vậy **khởi động thành công không chứng minh đã có quyền truy cập cloud**.
5. Spring tiêm bean vào adapter, service và controller; nếu cấu hình messaging, listener có thể đăng ký nơi nhận thông điệp.

Không cần khởi tạo SDK client mới ở từng HTTP request. Các client phổ biến được thiết kế để tái sử dụng, có quản lý kết nối và cấu hình retry/timeout. Cách tạo client cụ thể cần theo khuyến nghị của SDK và phiên bản thư viện đang dùng.

### 3.2. Runtime: một lệnh ghi object thực sự đi qua đâu?

Giả sử người dùng gửi nội dung tài liệu qua HTTP và ứng dụng ghi lên object storage:

1. **Controller** nhận request, xác thực người dùng ở tầng ứng dụng và kiểm tra các ràng buộc đầu vào (dung lượng, loại nội dung, quyền truy cập tài liệu).
2. **Business service** quyết định tên/định danh đối tượng và gọi một giao diện lưu trữ. Quy tắc “người này được tải lên tài liệu nào” nằm ở đây hoặc lớp authorization phù hợp, không nằm trong SDK.
3. **Provider adapter** ánh xạ thao tác chung thành API riêng của cloud, ví dụ bucket + object key đối với S3.
4. **SDK client** chuẩn bị request; credential provider cung cấp thông tin danh tính, SDK thêm xác thực/ký request theo giao thức tương ứng.
5. **Transport** gửi HTTP hoặc gRPC tới endpoint. DNS, TLS, proxy, firewall, private endpoint và timeout có thể ảnh hưởng tại bước này.
6. **Cloud service** kiểm tra danh tính và quyền trên tài nguyên, áp dụng chính sách dịch vụ rồi thực hiện ghi. Một danh tính hợp lệ vẫn có thể bị từ chối vì thiếu quyền.
7. **SDK** giải mã kết quả; thành công trả về response, thất bại thường phát sinh exception có thông tin mã lỗi/trạng thái.
8. **Adapter** chuyển lỗi mang tính provider sang lỗi có nghĩa với ứng dụng khi cần; **business service** hoàn tất use case, còn **controller** tạo HTTP response cho caller.

Luồng trả kết quả đi ngược về phía ứng dụng. Việc nhận HTTP 200/201 từ ứng dụng chỉ chứng minh điều mà ứng dụng đã thực sự chờ và kiểm tra: ví dụ adapter đã nhận phản hồi ghi thành công. Nó không tự đảm bảo mọi bước bất đồng bộ về sau hoặc một giao dịch ở hệ thống khác cũng đã hoàn thành.

## 4. Ví dụ xuyên suốt: lưu tài liệu qua Spring Cloud AWS và S3

Ví dụ sử dụng **Spring Boot với Spring Cloud AWS dòng 3.x và AWS SDK for Java v2**. Tên dependency, cách cấu hình và cơ chế auto-configuration cần được đối chiếu với phiên bản BOM tương thích trong dự án. Ta tách nghiệp vụ ra khỏi client S3, nhưng vẫn sử dụng Spring Cloud AWS để cấu hình/tạo client và Spring để inject dependency.

### 4.1. Định nghĩa giao diện do ứng dụng sở hữu

~~~java
// DocumentStorage.java
public interface DocumentStorage {
    void put(String objectKey, byte[] content, String contentType);
}
~~~

Giao diện này thể hiện nhu cầu **lưu nội dung theo một khóa**. Nó không buộc nghiệp vụ biết S3 bucket, Azure container hay GCS bucket. Các ứng dụng cần tải xuống, xóa, streaming hoặc quản lý phiên bản có thể thiết kế thêm method phù hợp; không nên cố gắng tạo một abstraction khổng lồ bao trùm mọi đặc tính provider.

~~~java
// DocumentService.java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStorage storage;

    public DocumentService(DocumentStorage storage) {
        this.storage = storage;
    }

    public String save(byte[] content, String contentType) {
        if (content == null || content.length == 0) {
            throw new IllegalArgumentException("Document must not be empty");
        }

        String objectKey = "documents/" + UUID.randomUUID();
        storage.put(objectKey, content, contentType);
        return objectKey;
    }
}
~~~

Service chỉ biết quy tắc tạo object key và cổng lưu dữ liệu. Trong hệ thống thực, cần thêm authorization, kiểm tra kích thước/MIME, giới hạn dung lượng, chống upload độc hại nếu phù hợp, và cơ chế idempotency ở cấp request. Ví dụ dùng mảng byte cho dễ theo dõi; tệp lớn nên cân nhắc streaming hoặc tải trực tiếp bằng URL có thời hạn với quyền được giới hạn.

### 4.2. Adapter chuyển lời gọi sang AWS SDK

~~~java
// S3DocumentStorage.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
@ConditionalOnProperty(
    prefix = "app.storage",
    name = "provider",
    havingValue = "aws"
)
public class S3DocumentStorage implements DocumentStorage {
    private final S3Client s3Client;
    private final String bucket;

    public S3DocumentStorage(
            S3Client s3Client,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    @Override
    public void put(String objectKey, byte[] content, String contentType) {
        PutObjectRequest request = PutObjectRequest.builder()
            .bucket(bucket)
            .key(objectKey)
            .contentType(contentType)
            .build();

        s3Client.putObject(request, RequestBody.fromBytes(content));
    }
}
~~~

Với starter S3 tương ứng, Spring Cloud AWS có thể auto-configure bean **S3Client** cho adapter; adapter vẫn gọi API **putObject** của AWS SDK. Spring làm nhiệm vụ tạo/tiêm client, còn SDK thực thi yêu cầu tới S3. Nếu chọn **S3Template** do Spring Cloud AWS cung cấp, adapter sẽ gọi API của template và luồng nội bộ sau đó mới tới SDK.

Dependency minh họa với Maven (phiên bản được quản lý qua BOM Spring Cloud AWS tương thích):

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Ví dụ cấu hình ứng dụng:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    provider: aws
    bucket: ${APP_STORAGE_BUCKET}
~~~

**APP_STORAGE_BUCKET** là tên tài nguyên do môi trường triển khai cung cấp, không phải credential. Ví dụ không đặt access key/secret key trong YAML. Ở máy phát triển, SDK có thể lấy credentials từ profile hoặc cơ chế đăng nhập được hỗ trợ; khi triển khai, ưu tiên IAM role/identity gắn với workload và cấp quyền ghi đúng bucket/prefix cần thiết. Thiết lập region phải phù hợp với tài nguyên và cấu hình client.

### 4.3. Controller và đường đi của một request

~~~java
// DocumentController.java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Map<String, String>> upload(@RequestBody byte[] body) {
        String key = documentService.save(
            body, MediaType.APPLICATION_OCTET_STREAM_VALUE);
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("key", key));
    }
}
~~~

Với request có Content-Type là **application/octet-stream**, trình tự là:

~~~text
POST /documents
  -> DocumentController.upload(...)
  -> DocumentService.save(...)
  -> DocumentStorage.put(...)
  -> S3DocumentStorage.put(...)
  -> S3Client.putObject(...)
  -> yêu cầu HTTPS đã ký -> Amazon S3
  <- kết quả từ S3 <- SDK <- adapter <- service
  <- HTTP 201 + object key
~~~

Đây là phiên bản tối giản để quan sát kiến trúc: cần thêm xác thực/ủy quyền của caller, kiểm soát kích thước body, ánh xạ exception và hạn mức trước khi triển khai production. Không nên coi object key trả về là một URL công khai; quyền tải xuống phải được kiểm tra ở luồng riêng.

## 5. Cùng một port, ba provider: cái gì thay đổi?

Trong kiến trúc dùng port, **DocumentService** không cần biết dữ liệu lưu ở đâu. Khi chuyển sang Azure hoặc Google Cloud, thường thay adapter, starter, client, cấu hình identity/endpoint và tài nguyên triển khai. Ngữ nghĩa dịch vụ vẫn phải được kiểm tra riêng; các cloud không hoàn toàn tương đương.

| Mối quan tâm | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object storage managed | Amazon S3 | Azure Blob Storage | Cloud Storage |
| Tích hợp Spring thường gặp | Spring Cloud AWS S3 starter/template | Spring Cloud Azure Storage Blob starter | Spring Cloud GCP Storage starter |
| Java client tiêu biểu | **S3Client** (AWS SDK v2) | **BlobServiceClient** (Azure SDK) | **Storage** (Google Cloud client library) |
| Danh tính ưu tiên ở runtime | IAM role/workload identity theo môi trường AWS | Managed Identity + Azure RBAC | Workload Identity hoặc service account phù hợp + IAM |
| Cách lấy thông tin đăng nhập thường gặp | AWS default credentials chain | DefaultAzureCredential hoặc cơ chế credential của starter | Application Default Credentials (ADC) |
| Ví dụ messaging tương ứng | SQS / SNS | Service Bus | Pub/Sub |

Luồng Azure Blob điển hình: **DocumentService → AzureBlobStorageAdapter → client/template được Spring Cloud Azure cấu hình → Azure SDK → HTTPS → Blob Storage**. Luồng Google Cloud Storage tương tự: **DocumentService → GcsStorageAdapter → client/template Spring Cloud GCP → Google Cloud Java client → API Cloud Storage**.

Khi chọn adapter qua cấu hình, phải bảo đảm ứng dụng có **đúng một bean DocumentStorage** phù hợp với môi trường; ví dụ adapter AWS được bật bởi thuộc tính **app.storage.provider=aws**. Nếu hai adapter cùng bật, constructor injection có thể trở nên mơ hồ; nếu không có adapter nào, ứng dụng không khởi động được. Tên artifact/namespace của Spring Cloud GCP, AWS và Azure thay đổi theo thế hệ thư viện, nên phải dùng tài liệu và BOM trùng với phiên bản trong dự án.

Không đồng nhất các khái niệm **bucket**, **container**, quyền truy cập, versioning, encryption, consistency, metadata và lỗi giữa ba nền tảng chỉ vì cùng có thao tác “put object”. Cổng chung chỉ nên chứa những cam kết thực sự cần cho nghiệp vụ; phần đặc thù nằm trong adapter hoặc được biểu diễn rõ bằng khả năng riêng.

## 6. Luồng messaging: chiều đi, chiều nhận và xử lý bất đồng bộ

Lệnh gửi message có đường đi gần giống lệnh ghi object nhưng kết quả có ý nghĩa khác:

~~~mermaid
flowchart LR
    A[Order service] --> P[EventPublisher port]
    P --> B[Provider publisher adapter]
    B --> K[Spring integration / SDK]
    K --> Q[SQS / Service Bus / Pub/Sub]
    Q --> L[Listener container / subscriber]
    L --> C[Consumer handler]
    C --> D[Use case xử lý sự kiện]
~~~

**Producer:** nghiệp vụ tạo sự kiện như **OrderCreated**, adapter dùng abstraction của Spring Cloud hoặc SDK để gửi tới queue/topic. Phản hồi gửi thành công thường xác nhận broker/dịch vụ đã nhận thông điệp theo hợp đồng API, **không** có nghĩa consumer đã xử lý thành công.

**Consumer:** Spring integration hoặc SDK polling/subscriber nhận message, chuyển payload sang dữ liệu ứng dụng và gọi handler. Sau khi xử lý, message được xác nhận, xóa, hoàn tất hoặc ack theo cơ chế dịch vụ. Các provider khác nhau về visibility timeout, lock, ack deadline, ordering, retry và dead-letter.

Với nhiều cấu hình messaging, một thông điệp **có thể được giao lại**: consumer xử lý xong nhưng chưa ack, timeout hoặc mất kết nối. Handler vì vậy cần idempotency, ví dụ kiểm tra **eventId** đã xử lý, đặt ràng buộc duy nhất trong database hoặc thiết kế phép cập nhật chịu được lặp lại. Không nên giả định mọi queue/topic mặc nhiên bảo đảm end-to-end exactly-once.

Nếu use case vừa ghi database vừa phát sự kiện, hai thao tác ở hai hệ thống không tự nằm trong cùng một transaction Spring. **Transactional outbox** là một cách phổ biến để ghi business state và bản ghi sự kiện trong cùng transaction database, rồi một thành phần khác phát sự kiện lên cloud. Cách triển khai và bảo đảm giao hàng phụ thuộc hệ thống thực tế.

## 7. Danh tính, quyền, mạng và secret đi vào luồng ở đâu?

Ba vấn đề thường bị nhầm lẫn:

1. **Danh tính (authentication):** SDK xác định “ứng dụng đang gọi với danh tính nào?”. Trên AWS có credential chain/role, Azure có Managed Identity/DefaultAzureCredential, Google Cloud có ADC/service account/workload identity. Token có thể được tự động làm mới bởi thư viện hỗ trợ.
2. **Quyền (authorization):** Cloud service xác định danh tính đó có được phép thực hiện hành động trên tài nguyên hay không. Ví dụ, có credential hợp lệ nhưng thiếu quyền ghi object vẫn nhận lỗi truy cập. Quyền phải giới hạn theo nguyên tắc **least privilege**.
3. **Kết nối:** client phải tới đúng endpoint/region/project/account qua DNS, TLS, proxy, firewall hoặc private network. Lỗi timeout hay không phân giải được DNS không được giải quyết chỉ bằng cách tăng quyền IAM/RBAC.

**Secret** là một nhánh tích hợp riêng: khi đọc giá trị từ AWS Secrets Manager, Azure Key Vault hoặc Google Secret Manager, code lại đi qua adapter/template/SDK với credential và quyền đọc secret tương ứng. Không hard-code secret hoặc ghi secret/token vào log; khi cần, dùng cơ chế identity của workload và quản lý secret theo khả năng từng cloud.

Một permission check trong **ứng dụng** (người dùng được upload hồ sơ nào) và một permission check tại **cloud** (workload được ghi vào bucket nào) giải quyết hai câu hỏi khác nhau. Cả hai đều cần thiết; cấp quyền cloud cho service không thay thế authorization của người dùng cuối.

## 8. Lỗi, retry và tính nhất quán: đường về không phải lúc nào cũng đơn giản

| Triệu chứng | Lớp cần xem đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Không tạo được bean client hoặc **DocumentStorage** | Spring dependency, BOM, điều kiện auto-configuration, cấu hình bean | Kiểm tra starter, phiên bản tương thích, profile/condition và dependency injection |
| Thiếu credential / không lấy được token | Credential chain, identity của môi trường | Xác định danh tính thực tế của workload; kiểm tra cấu hình đăng nhập/role/identity |
| **403 / AccessDenied / PermissionDenied** | Quyền trên tài nguyên, policy, RBAC/IAM | Kiểm tra action, resource scope, chính sách deny và identity; không mặc định coi là lỗi quyền của caller HTTP |
| Không tìm thấy bucket/container/topic hoặc sai region/project | Cấu hình tài nguyên và endpoint | Đối chiếu tên tài nguyên, account, project, vùng và môi trường |
| DNS/TLS/connection timeout | Network và transport | Kiểm tra outbound rule, proxy, TLS, private endpoint, endpoint URL và timeout |
| **429 / 503**, throttling, service unavailable | Giới hạn và tình trạng dịch vụ | Retry có backoff + jitter theo hướng dẫn SDK, giới hạn đồng thời, theo dõi quota |
| Upload hoặc publish được nhưng nghiệp vụ sau đó chưa hoàn tất | Workflow bất đồng bộ, consumer, transaction giữa hệ thống | Kiểm tra ack, retry, DLQ, outbox và idempotency |

Nguyên tắc xử lý lỗi:

- **Adapter** biết exception cụ thể của SDK và chuyển sang lỗi ứng dụng có ý nghĩa, ví dụ **StorageAccessException**, **StorageUnavailableException**, nhưng không làm mất nguyên nhân gốc trong log nội bộ an toàn.
- **Service nghiệp vụ** quyết định có được phép thử lại hoặc bù trừ hay không. **Controller** ánh xạ lỗi thành HTTP status phù hợp và thông báo không làm lộ bucket, token, connection string hoặc dữ liệu nhạy cảm.
- Retry ở SDK và retry ở Spring/application có thể **chồng nhau**, làm số lần gọi thực tế tăng mạnh. Chỉ retry lỗi có khả năng tạm thời, giới hạn tổng thời gian, thêm backoff/jitter và dự trù quota.
- Nếu mất phản hồi sau timeout, kết quả ghi hoặc gửi **có thể đã thành công** ở phía cloud. API ứng dụng cần idempotency key hoặc cơ chế chống trùng phù hợp để request gửi lại không tạo nghiệp vụ lặp.
- Ghi object vào cloud và ghi metadata vào database là **hai hệ thống khác nhau**; transaction database không tự rollback object đã upload. Cần thiết kế thứ tự thao tác, trạng thái tạm, cleanup/compensation hoặc workflow đồng bộ hóa tùy nghiệp vụ.

## 9. Quan sát và kiểm thử từng ranh giới

Nên theo dõi request từ đầu tới cuối bằng trace/correlation ID, tên thao tác nghiệp vụ, provider, loại tài nguyên, thời lượng, số lần retry và mã lỗi đã chuẩn hóa. Log không được chứa secret, access token, credential, payload nhạy cảm hoặc nội dung tài liệu. SDK instrumentation, trace propagation và metric support phụ thuộc SDK/thư viện đang sử dụng; không mặc định mọi lời gọi cloud đã xuất hiện đầy đủ trong distributed trace chỉ vì bật Spring actuator.

Chiến lược kiểm thử có thể chia theo ranh giới:

| Mức | Điều cần chứng minh | Ví dụ |
| --- | --- | --- |
| **Unit test nghiệp vụ** | Service tạo đúng yêu cầu và gọi port; không cần credential/cloud | Mock DocumentStorage, xác minh gọi put đúng object key và content type |
| **Adapter/contract test** | Ánh xạ kiểu dữ liệu, request, response, exception đúng theo provider | S3 adapter tạo đúng bucket, key, metadata; xử lý lỗi thiếu quyền |
| **Integration test** | Cấu hình Spring tạo bean thật, SDK có thể giao tiếp và lưu/đọc dữ liệu | LocalStack cho một số luồng AWS; Azurite cho Blob; emulator tương thích hoặc test project riêng cho Google Cloud |
| **Cloud smoke test có kiểm soát** | Identity, IAM/RBAC, region/project, network và quota hoạt động trên môi trường thật | Workload chạy bằng identity triển khai, ghi rồi đọc/xóa một object thử nghiệm |

Ví dụ unit test cho service không cần khởi động Spring context:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;

class DocumentServiceTest {
    @Test
    void delegatesSaveToStoragePort() {
        DocumentStorage storage = mock(DocumentStorage.class);
        DocumentService service = new DocumentService(storage);
        byte[] content = {1, 2, 3};

        String key = service.save(content, "application/octet-stream");

        assertTrue(key.startsWith("documents/"));
        verify(storage).put(
            eq(key), same(content), eq("application/octet-stream"));
    }
}
~~~

Emulator hữu ích cho phát triển và CI, nhưng thường không mô phỏng đầy đủ IAM, Managed Identity, workload identity, networking, quota hoặc mọi hành vi dịch vụ. Vì thế test tích hợp với emulator **không thay thế** kiểm thử quyền và kết nối ở cloud thật. Khi test trên cloud, dùng tài nguyên thử nghiệm tách biệt, quyền tối thiểu và quy trình dọn dữ liệu.

## 10. Tự luyện: lần vết một use case và tìm lỗi

**Bài tập 1 — Vẽ luồng.** Với yêu cầu “upload hóa đơn”, hãy đánh dấu nơi xác thực người dùng, nơi kiểm tra kích thước, nơi sinh object key, nơi chọn provider, nơi lấy credential và nơi dịch vụ cloud kiểm tra quyền. Giải thích đường trả kết quả khi thành công và khi bị **403**.

**Bài tập 2 — Thay adapter.** Giữ nguyên **DocumentService** và **DocumentStorage**. Phác thảo **AzureBlobDocumentStorage** hoặc **GcsDocumentStorage** với các trách nhiệm: chọn container/bucket, gọi SDK client được Spring quản lý, ánh xạ exception và dùng workload identity tương ứng. Liệt kê những cấu hình cần thay khi chuyển môi trường.

**Bài tập 3 — Lỗi ở production.** Ứng dụng khởi động bình thường nhưng khi ghi object nhận **AccessDenied**. Kiểm tra theo thứ tự: identity thực tế đang dùng, action/tài nguyên cần truy cập, IAM/RBAC và chính sách deny, tên tài nguyên và region/project. Vì sao chỉ đổi connection timeout không xử lý được lỗi này?

**Bài tập 4 — Ghi trùng.** Client timeout rồi tự gửi lại cùng yêu cầu upload; service hiện tại sinh **UUID mới cho mỗi lần**. Hãy đề xuất idempotency key ở tầng API và cách lưu kết quả theo key để tránh tạo hai tài liệu nghiệp vụ, đồng thời xử lý trường hợp object đã được ghi nhưng database chưa cập nhật.

## 11. Những điểm cần nhớ

- **Spring Boot** quản lý vòng đời và dependency; **Spring Cloud integration** giúp cấu hình và tích hợp; **SDK** thực hiện giao tiếp API; **cloud service** thực thi thao tác và quyết định quyền ở phía provider.
- Auto-configuration là công việc chủ yếu lúc **startup**; runtime có thể đi từ adapter **thẳng tới SDK** hoặc qua một template của Spring Cloud.
- Tách **business service → port → provider adapter** giúp khoanh vùng thay đổi và kiểm thử, nhưng không xóa khác biệt về ngữ nghĩa giữa AWS, Azure và Google Cloud.
- **Identity, quyền, mạng, retry và quan sát** nằm xuyên suốt luồng; một lần gửi thành công không đồng nghĩa toàn bộ workflow bất đồng bộ hoặc nhiều hệ thống đã hoàn tất.
- Khi sự cố xảy ra, đi theo từng ranh giới **Spring bean → adapter → SDK/credential → transport → managed service → response/exception** để tìm đúng lớp chịu trách nhiệm.
