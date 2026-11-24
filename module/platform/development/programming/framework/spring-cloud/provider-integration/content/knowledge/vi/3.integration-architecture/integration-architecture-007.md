# Chuyển đổi dữ liệu, ngoại lệ và thông tin yêu cầu tại ranh giới tích hợp

Trong Spring Boot, một lời gọi **lưu tài liệu**, **phát sự kiện** hay **đọc secret** thường đi từ mã nghiệp vụ tới adapter, qua Spring Cloud integration/SDK rồi tới dịch vụ managed. Mỗi lớp có cách biểu diễn dữ liệu, lỗi và thông tin truy vết khác nhau. Ví dụ: application service nói “lưu PDF của hóa đơn”; AWS S3 nhận **PutObjectRequest** với bucket, key, content type và request body; Azure Blob Storage nhận tên container/blob và tùy chọn upload; Google Cloud Storage nhận thông tin bucket/object qua Java client. Nếu để request/response SDK và các exception của provider tràn vào nghiệp vụ, một thay đổi SDK hoặc provider có thể khiến nhiều service và test phải sửa theo.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** thông qua những thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và so sánh các cloud provider. Trọng tâm bài này là thiết kế ba phép chuyển đổi có chủ đích tại ranh giới tích hợp: **dữ liệu**, **ngoại lệ/kết quả**, và **ngữ cảnh yêu cầu**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt DTO của HTTP/message, kiểu dữ liệu ứng dụng, request/response SDK và resource của cloud.
- Thiết kế mapping hai chiều mà không khiến application service phụ thuộc kiểu dữ liệu provider.
- Phân loại lỗi **nghiệp vụ**, **cấu hình/xác thực cloud**, **lỗi tạm thời** và trường hợp **không rõ thao tác đã hoàn tất hay chưa**.
- Giải thích khác biệt giữa **business operation ID**, **correlation/trace ID**, **cloud request ID**, **idempotency key** và **message ID**.
- Ánh xạ một thao tác lưu object bằng Spring Boot + Spring Cloud AWS/S3, sau đó áp dụng cùng tư duy cho Azure và Google Cloud.
- Kiểm thử mapping, lỗi và metadata ở từng ranh giới mà không cần cloud thật cho unit test.

## 2. Ba luồng chuyển đổi trên cùng một request

~~~mermaid
flowchart LR
    H[HTTP DTO / message payload] --> A[Application command]
    A --> P[Outbound port]
    P --> AD[Provider adapter]
    AD --> S[SDK request + transport]
    S --> C[Managed service]
    C --> R[SDK response hoặc SDK exception]
    R --> AD
    AD --> O[Application result hoặc storage error]
    O --> H2[HTTP response / workflow result]
    X[Operation ID / correlation context] -. application .-> P
    X -. safe metadata .-> AD
    Y[Cloud request ID] -. diagnostics .-> AD
~~~

Có ba hướng thông tin cần thiết kế riêng:

1. **Dữ liệu:** controller/listener chuyển input thành command; application service chuyển nhu cầu thành một outbound port request; adapter chuyển sang mô hình của SDK. Khi nhận response, chỉ lấy phần có ý nghĩa với hợp đồng ứng dụng.
2. **Kết quả và lỗi:** SDK báo thành công, lỗi API, lỗi mạng hoặc timeout; adapter ánh xạ sang **lỗi có ý nghĩa ổn định**. Application/controller quyết định response, retry hay bước bù trừ dựa trên ý nghĩa đó.
3. **Ngữ cảnh yêu cầu:** operation ID, tenant hoặc principal đã xác thực, correlation/trace ID, timeout budget và cloud request ID phục vụ authorization, quan sát và khôi phục. Mỗi giá trị có nguồn tin cậy và vòng đời khác nhau.

Spring Cloud starter có thể cấu hình SDK client, template, converter hoặc listener cho ứng dụng. **Spring không tự biến ngữ nghĩa AWS, Azure, Google Cloud thành một hợp đồng thống nhất**; adapter vẫn phải hiểu những gì thực sự tương đương và những gì khác nhau.

## 3. Đặt dữ liệu ở đúng lớp

| Lớp | Dữ liệu thường thấy | Nên sở hữu | Không nên phụ thuộc vào |
| --- | --- | --- | --- |
| **Inbound adapter** | HTTP multipart, JSON DTO, HTTP headers; payload và attributes của queue | Kiểm tra cú pháp, kích thước, định dạng, ánh xạ transport | Request body dạng SDK cloud trong controller |
| **Application service** | Invoice ID, DocumentId, nội dung đã được kiểm tra, quyền use case, operation ID | Luật nghiệp vụ, đặt tên tài nguyên theo nghiệp vụ, điều phối | Bucket policy, **PutObjectRequest**, **BlobInfo** |
| **Outbound port** | **DocumentWrite**, **StoredDocument**, lỗi của ứng dụng | Hợp đồng kỹ thuật vừa đủ để phục vụ use case | Loại exception/metadata riêng của từng SDK |
| **Provider adapter** | Bucket/container, object key, SDK request/response, error code | Mapping, đặc tính provider, retry phù hợp, translation | Quyết định người dùng cuối có quyền xem invoice hay không |
| **SDK và cloud** | HTTP/gRPC, token/credential, API status và request ID | Truy cập dịch vụ và kiểm tra IAM/RBAC | Authorization theo business rule của ứng dụng |

Ví dụ một HTTP client gửi **Content-Type**, tên file và byte PDF. HTTP controller phải kiểm tra định dạng upload; application service quyết định hóa đơn nào nhận tài liệu và object key hợp lệ; adapter mới điền tên bucket/region và dựng SDK request. Không để caller chọn **bucket**, **storage account**, **project**, **service account** hoặc header nhạy cảm rồi chuyển thẳng vào SDK.

**Đơn vị sở hữu abstraction:** outbound port thường thuộc application/core; provider adapter phụ thuộc port và SDK. Ở mức mã nguồn, chiều phụ thuộc là **application → port ← adapter → SDK**, dù runtime request đi từ application qua adapter tới SDK.

## 4. Thiết kế hợp đồng dữ liệu trước khi mapping

Giả sử nghiệp vụ cần lưu một bản PDF vào object storage và nhận lại định danh để tham chiếu:

~~~java
// DocumentWrite.java - thuộc application model
import java.util.Objects;

public record DocumentWrite(
        String objectKey,
        byte[] content,
        String contentType,
        String operationId) {

    public DocumentWrite {
        Objects.requireNonNull(objectKey, "objectKey");
        Objects.requireNonNull(content, "content");
        Objects.requireNonNull(contentType, "contentType");
        Objects.requireNonNull(operationId, "operationId");
        if (objectKey.isBlank() || operationId.isBlank() ||
                content.length == 0) {
            throw new IllegalArgumentException("Invalid document write");
        }
    }
}
~~~

~~~java
// StoredDocument.java - kết quả mà application hiểu
public record StoredDocument(String objectKey) {}

// DocumentStore.java - outbound port
public interface DocumentStore {
    StoredDocument put(DocumentWrite request);
}
~~~

Các kiểu trên không import AWS, Azure hoặc Google Cloud SDK. **operationId** thể hiện định danh bền vững của thao tác nghiệp vụ; nó có thể phục vụ idempotency và truy vết. Một operation ID được đưa vào object metadata **không tự làm thao tác ghi trở thành idempotent**; bảo đảm đó cần được thiết kế riêng trong ứng dụng và/hoặc bằng conditional write của provider.

**Giới hạn ví dụ:** record chứa **byte[]** chỉ để dễ đọc. Mảng byte có thể bị code khác sửa và toàn bộ file nằm trong bộ nhớ; ứng dụng production cần giới hạn dung lượng, xác thực MIME/nội dung và cân nhắc stream hoặc direct upload có quyền giới hạn. Nếu dùng record chứa mảng trong một model yêu cầu bất biến, cần sao chép phòng vệ ở constructor và accessor hoặc chọn kiểu dữ liệu thích hợp khác.

### 4.1. Chỉ đưa dữ liệu thực sự cần qua port

| Cần cho use case? | Dữ liệu | Gợi ý thiết kế |
| --- | --- | --- |
| Có | Document key, content type, nội dung, operation ID | Đưa vào **DocumentWrite** |
| Có trong một số use case | Version ID, checksum, generation, điều kiện ghi | Định nghĩa capability/option có ngữ nghĩa chính xác |
| Thường không | AWS request ID, Azure response headers, địa chỉ endpoint | Giữ ở diagnostics hoặc hạ tầng quan sát |
| Không | AWS **PutObjectResponse**, Azure **BlobUploadOptions**, Google **BlobInfo** trong application service | Chỉ dùng trong provider adapter |
| Tuyệt đối không cần trong DTO công khai | Access key, OAuth token, SAS/connection string | Giữ trong credential/config infrastructure |

Nếu hệ thống có yêu cầu **ghi một lần, không được ghi đè**, port phải nói rõ điều kiện đó, ví dụ **createIfAbsent**. Một method **put** không khai báo semantics mà lại luôn ghi đè là lỗi hợp đồng, dù cả ba SDK đều có khả năng ghi object.

## 5. Mapping HTTP hoặc message payload vào application command

Ở inbound boundary, dữ liệu đến từ một nguồn bên ngoài và chưa thể được tin cậy:

~~~text
POST /invoices/{invoiceId}/document
  HTTP body / Content-Type / authenticated principal
    -> Controller: kiểm tra kích thước và định dạng
    -> Application service: kiểm tra ownership của invoice
    -> Tạo objectKey và operationId đáng tin cậy
    -> DocumentStore.put(DocumentWrite)
~~~

Cần tách **validation định dạng** khỏi **business authorization**. Controller có thể kiểm tra file không rỗng và tối đa bao nhiêu MB; application service xác minh invoice thuộc tenant/caller, quyết định key theo invoice và version, rồi gọi port. Không tin **X-Tenant-Id** hoặc tên bucket do client tùy ý gửi nếu các giá trị đó không được xác thực đối chiếu với identity và dữ liệu ứng dụng.

Với JSON/event payload, cần kiểm tra thêm:

- **Schema/version:** event thêm trường hoặc đổi ngữ nghĩa có thể phá consumer cũ; nên duy trì version và compatibility policy.
- **Thời gian:** dùng instant/UTC rõ ràng (ví dụ ISO 8601) và tránh lẫn time zone hoặc epoch milliseconds với seconds.
- **Kiểu số:** xử lý money bằng decimal hoặc đơn vị nguyên nhỏ nhất thay vì float; chú ý số lớn khi đi qua JavaScript/JSON.
- **Null/missing/empty:** phân biệt trường vắng mặt, null và rỗng theo contract; không để mapper tự biến mất dữ liệu quan trọng.
- **Encoding:** dùng UTF-8 và metadata/content type đúng; file nhị phân không được đưa qua String tùy tiện.
- **Kích thước:** payload JSON, metadata và message attributes có giới hạn riêng theo dịch vụ; không nhồi file lớn vào hàng đợi chỉ để đơn giản hóa lời gọi.

## 6. Ví dụ adapter Spring Cloud AWS S3: mapping request và response

Ví dụ dùng **Spring Boot 3, Spring Cloud AWS 3.x, AWS SDK for Java v2**. Với starter tương thích, Spring Cloud AWS có thể tạo bean **S3Client** để inject vào adapter; với cấu hình SDK riêng, ứng dụng có thể tự khai báo bean client. Tên artifact, BOM và property phải được kiểm tra theo đúng phiên bản dự án.

Dependency Maven minh họa:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Cấu hình:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  document-store:
    provider: aws
    bucket: ${APP_DOCUMENT_BUCKET}
~~~

**spring.cloud.aws.region.static** là property của tích hợp AWS; **app.document-store.provider** và **app.document-store.bucket** do ứng dụng định nghĩa. Tên bucket do môi trường cung cấp; credentials được SDK tìm theo cơ chế phù hợp với workload (ví dụ IAM role) và cần được cấp quyền tài nguyên cụ thể. Không hard-code access key/secret key trong YAML.

### 6.1. Định nghĩa lỗi chung để adapter sử dụng

~~~java
// StorageFailureCode.java
public enum StorageFailureCode {
    ACCESS_DENIED,
    CONFLICT,
    TEMPORARY_UNAVAILABLE,
    OUTCOME_UNKNOWN,
    PROVIDER_FAILURE
}
~~~

~~~java
// StorageFailure.java
public final class StorageFailure extends RuntimeException {
    private final StorageFailureCode code;
    private final String providerRequestId;

    public StorageFailure(
            StorageFailureCode code,
            String safeMessage,
            String providerRequestId,
            Throwable cause) {
        super(safeMessage, cause);
        this.code = code;
        this.providerRequestId = providerRequestId;
    }

    public StorageFailureCode code() {
        return code;
    }

    // Chỉ sử dụng nội bộ để đối chiếu với log/audit của cloud.
    public String providerRequestId() {
        return providerRequestId;
    }
}
~~~

Enum là **tập lỗi ứng dụng lựa chọn**, không có nghĩa AWS/Azure/GCP có cùng error code. Cần mở rộng theo use case (ví dụ NOT_FOUND, INVALID_REQUEST, QUOTA_EXCEEDED, PRECONDITION_FAILED) khi có lý do cụ thể. Thông điệp **safeMessage** không đưa token, connection string, tên bucket nhạy cảm hoặc body vào response công khai.

### 6.2. Adapter ánh xạ DocumentWrite sang PutObjectRequest

~~~java
// S3DocumentStore.java
import java.util.Map;
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
public final class S3DocumentStore implements DocumentStore {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentStore(
            S3Client s3,
            @Value("${app.document-store.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    @Override
    public StoredDocument put(DocumentWrite doc) {
        PutObjectRequest sdkRequest = PutObjectRequest.builder()
            .bucket(bucket)
            .key(doc.objectKey())
            .contentType(doc.contentType())
            .metadata(Map.of("operation-id", doc.operationId()))
            .build();

        try {
            s3.putObject(sdkRequest, RequestBody.fromBytes(doc.content()));
            return new StoredDocument(doc.objectKey());
        } catch (S3Exception ex) {
            throw translateServiceError(ex);
        } catch (SdkClientException ex) {
            throw new StorageFailure(
                StorageFailureCode.OUTCOME_UNKNOWN,
                "Cannot confirm object write",
                null,
                ex);
        }
    }

    private StorageFailure translateServiceError(S3Exception ex) {
        int status = ex.statusCode();
        StorageFailureCode code;
        if (status == 403) {
            code = StorageFailureCode.ACCESS_DENIED;
        } else if (status == 409 || status == 412) {
            code = StorageFailureCode.CONFLICT;
        } else if (status == 429 || status >= 500) {
            code = StorageFailureCode.TEMPORARY_UNAVAILABLE;
        } else {
            code = StorageFailureCode.PROVIDER_FAILURE;
        }

        return new StorageFailure(
            code,
            "Object storage request failed",
            ex.requestId(),
            ex);
    }
}
~~~

**Luồng dữ liệu:** **DocumentWrite.objectKey → PutObjectRequest.key**, **contentType → contentType**, **content → RequestBody**, **operationId → user metadata**. Trả về **StoredDocument** với key, vì hợp đồng hiện tại không cần expose toàn bộ **PutObjectResponse**. **S3Client** là bean dùng lại qua nhiều lời gọi; adapter không xây client mới trong mỗi request.

**Lưu ý về ngữ nghĩa của ví dụ:**

- Đây là mẫu mapping lỗi **tối giản**. HTTP **403** từ S3 thường là vấn đề identity/policy của workload, không tự suy ra người dùng cuối bị từ chối quyền invoice. **409/412** cần được diễn giải theo thao tác và precondition thực tế; mã **5xx/429** có thể là lỗi tạm thời.
- **SdkClientException** có thể xảy ra trước hoặc sau khi request được gửi. Với một thao tác ghi có side effect, nếu không có bằng chứng chắc chắn về trạng thái thì bảo thủ dùng **OUTCOME_UNKNOWN**. Không khẳng định mọi lỗi client đều đã ghi thành công hoặc chắc chắn chưa ghi.
- Metadata **operation-id** chỉ hỗ trợ truy vết và kiểm tra đối chiếu khi có quyền đọc object. Nó không thay thế idempotency key được bảo vệ ở application layer, conditional write hoặc cơ chế dedup của dịch vụ.
- SDK exception được giữ làm **cause nội bộ**. Không được serialize toàn bộ cause/stack trace thành HTTP body; chỉ log thuộc tính an toàn với cấu hình log bảo mật.
- Với tải file lớn, **RequestBody.fromBytes** cần toàn bộ nội dung trong RAM; hãy thiết kế streaming/multipart hay direct upload phù hợp.

### 6.3. Nếu cần phiên bản object hoặc checksum

S3 có thể cung cấp **versionId**, **ETag** hoặc thông tin checksum tùy cấu hình/tính năng. Azure Blob và Google Cloud Storage có **ETag/version/generation** với ý nghĩa và phạm vi khác. Không xem **ETag** là SHA-256 hoặc MD5 nhất quán trên mọi cloud; multipart upload, encryption hoặc cơ chế provider có thể làm ETag không phải digest đơn giản của nội dung.

Nếu use case thực sự cần **conditional write** hoặc optimistic concurrency, định nghĩa contract có trường điều kiện rõ (ví dụ **expectedVersion** hoặc **createIfAbsent**) rồi triển khai bằng precondition tương ứng và test race. Đừng thêm một field **String etag** vào port mà không nêu rõ nó được tạo, xác thực và sử dụng thế nào trên từng provider.

## 7. Chuyển ngoại lệ ở ranh giới nào?

Không phải mọi exception đều có cùng tầng chịu trách nhiệm:

| Loại lỗi | Nơi phát hiện | Cách biểu diễn ở ứng dụng |
| --- | --- | --- |
| PDF rỗng, sai loại dữ liệu, invoice không hợp lệ | Inbound/application validation | Lỗi input/validation của use case |
| Caller không được truy cập invoice của tenant khác | Business authorization | Lỗi authorization của **caller**, thường được map 403 ở HTTP |
| Workload thiếu quyền ghi bucket/container | Cloud SDK/managed service | Lỗi infrastructure **ACCESS_DENIED** cho người vận hành; không làm lộ cloud resource |
| Cấu hình sai endpoint, region, project | Client/config hoặc managed service | Lỗi cấu hình/hạ tầng, thường cần sửa deployment |
| Quota, throttling, 429/503, lỗi tạm thời | Cloud service/transport | **TEMPORARY_UNAVAILABLE** với retry giới hạn |
| Request bị timeout mà có thể đã được xử lý | SDK/transport | **OUTCOME_UNKNOWN**, kiểm tra trạng thái trước khi lặp side effect |
| Conditional write không đạt | Provider precondition | **CONFLICT** hoặc **ALREADY_EXISTS** theo hợp đồng use case |
| Object không tồn tại khi đọc/xóa | Provider response của thao tác cụ thể | **NOT_FOUND** nếu contract định nghĩa và được xác minh |

**Adapter** biết các mã như **S3Exception.statusCode()**, **BlobStorageException.getStatusCode()**, **StorageException.getCode()**. Nó có thể tạo lỗi hạ tầng trung lập. **Application service** biết có nên báo conflict, giữ trạng thái chờ hoặc thử lại. **HTTP exception handler** chuyển lỗi ứng dụng thành response an toàn.

Ví dụ HTTP **502/503** có thể phù hợp khi **workload cloud thiếu quyền** hoặc dịch vụ managed không phục vụ; HTTP **403** phù hợp khi **caller không được phép** làm use case. Hai nguồn lỗi có thể đều mang status 403 ở một lớp nào đó, nhưng ý nghĩa khác nhau; không sao chép máy móc status cloud sang caller.

### 7.1. Không bỏ mất nguyên nhân lỗi, không rò rỉ thông tin

Khi cần hỗ trợ chẩn đoán, lưu:

- Mã lỗi đã chuẩn hóa và operation ID.
- Provider, tên thao tác, region/project đã được cho phép log, status code và request ID từ cloud nếu có.
- **Cause** nội bộ đã được xử lý ở logging/telemetry phù hợp.

Không log credential, auth header, SAS token, connection string, secret value, nội dung PDF/message nhạy cảm hoặc toàn bộ HTTP request/response SDK. Request ID cloud có thể giúp support tra log provider nhưng không phải thông tin để một public API bắt buộc hiển thị.

## 8. Retry: phân loại lỗi không đủ, phải xét loại thao tác

Một lỗi có vẻ tạm thời chưa chắc được phép retry một cách mù quáng. Cần biết **thao tác có side effect gì** và **bảo đảm idempotency** nào đang có.

~~~mermaid
flowchart TD
    E[Lỗi từ SDK] --> A{Đã xác minh lỗi không thể phục hồi?}
    A -->|Có: ví dụ thiếu quyền| STOP[Trả lỗi cấu hình / authorization]
    A -->|Không| B{Có khả năng đã thực hiện side effect?}
    B -->|Có hoặc chưa rõ| C[Đối chiếu trạng thái / operation ID]
    B -->|Không chắc, có bằng chứng request chưa gửi| D{Thao tác retry an toàn?}
    C --> D
    D -->|Không| F[Báo trạng thái chưa xác định và xử lý bù trừ]
    D -->|Có| G[Retry có giới hạn, backoff, jitter, deadline]
~~~

Ví dụ **PUT object** timeout sau khi server đã ghi dữ liệu: một retry tạo key mới có thể tạo **hai object**. Dùng key ổn định theo document ID/operation ID giúp hướng các lần thử về cùng tài nguyên nhưng vẫn cần quyết định ghi đè hay create-if-absent. Với **publish message**, broker có thể đã chấp nhận message dù producer mất response; consumer phải thiết kế idempotency theo event ID.

SDK, Spring Retry, Reactor và message broker có thể cùng retry. Nếu mỗi lớp thử ba lần, số lần gọi thực tế có thể tăng mạnh. Hãy có **timeout budget và retry budget** toàn bộ, tránh lặp lại các lỗi permission hoặc validation, và ghi lại số retry ở mức observability.

## 9. Bốn loại định danh request dễ bị nhầm

| Giá trị | Tạo bởi ai? | Mục đích | Có đảm bảo duy nhất toàn hệ thống? |
| --- | --- | --- | --- |
| **Business operation ID / idempotency key** | Ứng dụng hoặc caller được xác thực rồi ứng dụng kiểm soát | Nhận diện một thao tác nghiệp vụ, chống lặp theo hợp đồng | Do thiết kế lưu trữ/ràng buộc của ứng dụng quyết định |
| **Correlation ID** | API gateway hoặc ứng dụng, có thể nhận từ upstream tin cậy | Gom log nhiều bước cùng request/workflow | Chỉ khi có quy tắc cấp phát/chuẩn hóa đáng tin cậy |
| **Trace ID / span ID** | Hệ thống distributed tracing/instrumentation | Theo dõi quan hệ thời gian và span qua hệ thống | Thuộc ngữ cảnh tracing, không thay thế business ID |
| **Provider request ID** | AWS/Azure/Google Cloud cho một API call cụ thể, nếu có | Điều tra một lời gọi cloud | Chỉ dùng theo semantics provider; mỗi retry có thể có ID khác |

Ví dụ một HTTP request có thể có **operationId=invoice-123-v2**, **traceId** của đường HTTP, và ba **cloud request IDs** khác nhau nếu SDK retry ba lần. Không dùng provider request ID làm khóa idempotency của nghiệp vụ; nó không tồn tại trước khi gọi cloud và có thể thay đổi theo lần thử.

**Khả năng tin cậy:** correlation header từ Internet có thể bị giả mạo hoặc quá dài. Tại boundary, cần kiểm tra định dạng/kích thước và quyết định dùng trace context từ upstream tin cậy hay phát ID mới. Tenant ID và principal phải đến từ security context đã xác thực/ủy quyền, không chỉ từ một HTTP header người dùng tự khai báo.

### 9.1. Trường nào có thể truyền vào provider?

Chỉ đưa những trường **an toàn và được API hỗ trợ**:

| Thông tin | S3 object metadata | Azure Blob metadata / headers | GCS object metadata | Lưu ý |
| --- | --- | --- | --- | --- |
| Content type | Request contentType | Blob HTTP headers/content type | BlobInfo/content type | Giúp client tải đúng loại, không thay validate nội dung |
| Operation ID ngắn, không nhạy cảm | User metadata phù hợp | Metadata key/value phù hợp | Custom metadata phù hợp | Giới hạn kích thước và định dạng tùy provider |
| Trace/correlation ID | Chỉ khi hữu ích và được phép | Tương tự | Tương tự | Không mặc định provider tiếp tục W3C trace qua SDK |
| Access token, cookie, PII | **Không** | **Không** | **Không** | Metadata có thể được đọc/xuất hiện trong log hoặc quyền object |

Với metadata, SDK tự map key/value sang header hoặc trường API theo provider. Không tự chèn header tùy ý có tên bắt đầu bằng **Authorization**, không gửi full request headers từ controller sang cloud và không cho caller tự quyết định endpoint/role.

## 10. Đối chiếu AWS, Azure và Google Cloud

| Khía cạnh | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Storage API Java tiêu biểu | **S3Client**, **PutObjectRequest** | **BlobClient/BlobServiceClient**, upload options | **Storage**, **BlobInfo** |
| Exception dịch vụ tiêu biểu | **S3Exception** / AWS service exceptions | **BlobStorageException** / Azure HTTP exceptions | **StorageException**, một số API GAX có **ApiException** |
| Exception phía transport/client | **SdkClientException** | HTTP/client exception theo Azure SDK | IOException/ApiException hoặc exception cụ thể theo thư viện |
| Mã HTTP ở lỗi dịch vụ | **statusCode()** trên service exception | **getStatusCode()** trên HTTP exception phù hợp | **getCode()** với StorageException; tùy API |
| Request ID để hỗ trợ | AWS request ID từ exception/response khi có | Ví dụ **x-ms-request-id** từ response metadata nếu có | HTTP/gRPC request identifiers khi API cung cấp |
| Metadata và conditional write | S3 user metadata + precondition của thao tác | Blob metadata/HTTP headers + ETag condition | GCS custom metadata + generation/metageneration precondition |
| Workload identity | IAM role/credential chain | Managed Identity/DefaultAzureCredential | ADC/workload identity/service account |

Các tên exception và accessor trong bảng mang tính **định hướng**; từng dịch vụ/SDK/version có API khác nhau. Không giả định một cơ chế mapping có thể chỉ dựa trên **HTTP status**. Ví dụ 404 trên thao tác đọc object có thể có nghĩa object không tồn tại; 404 trên thao tác khác có thể là sai account, container, endpoint hoặc resource. Một số API dựa trên gRPC trả canonical status thay vì HTTP response trực tiếp.

### 10.1. Azure Blob: adapter làm những gì?

Một **AzureBlobDocumentStore** sẽ dùng client/template do Spring Cloud Azure cấu hình (hoặc Azure SDK client tự tạo và được Spring quản lý), ánh xạ **DocumentWrite.objectKey** sang blob name, **contentType** sang blob HTTP headers hoặc upload options, rồi gọi upload trên container tương ứng. Khi lỗi, adapter đọc **BlobStorageException**, status/error code và request ID/headers phù hợp để chuyển thành **StorageFailure**. Không trả nguyên **BlobStorageException** cho application service.

Nếu dùng Managed Identity, Azure SDK lấy token từ credential chain phù hợp; **Azure RBAC/resource configuration** quyết định quyền ghi. Token hợp lệ nhưng không có quyền trên storage account/container vẫn dẫn tới lỗi authorization của workload. Retry và conditional write phải theo hợp đồng của Azure Blob, không sao chép một cách máy móc enum status AWS.

### 10.2. Google Cloud Storage: adapter làm những gì?

Một **GcsDocumentStore** dùng **Storage** client (hoặc abstraction phù hợp) để tạo **BlobInfo** từ bucket/object name/content type/metadata và đưa bytes/stream tới Cloud Storage API. Adapter chuyển **StorageException** thành lỗi chung theo operation và code phù hợp; nếu thư viện dùng gRPC/GAX ở một dịch vụ khác, phải kiểm tra **ApiException** và metadata của RPC. **ADC** xác định danh tính, IAM trên project/bucket xác định quyền.

Với GCS, **generation preconditions** quan trọng khi hợp đồng cần chống ghi đè; **generation** không tương đương tuyệt đối với **S3 version ID** hay ETag. Hợp đồng chung cần định nghĩa khả năng muốn đạt, rồi từng adapter dùng API provider đúng semantics.

## 11. Mapping message payload, headers và acknowledgment

Storage chỉ là một trường hợp. Với messaging (Amazon SQS/SNS, Azure Service Bus, Google Cloud Pub/Sub), có ít nhất **hai ranh giới**:

~~~mermaid
flowchart LR
    A[Business service] --> P[EventPublisher port]
    P --> B[Publisher adapter]
    B --> Q[SQS / Service Bus / PubSub]
    Q --> L[Listener / subscriber adapter]
    L --> H[Business event handler]
~~~

**Ở publisher**, ứng dụng tạo một sự kiện có ý nghĩa nghiệp vụ: **eventId**, **eventType**, **schemaVersion**, **occurredAt**, **aggregateId** và payload. Adapter serialize thành JSON/format phù hợp, gắn những message attributes được hỗ trợ và gọi template/SDK. Nếu publish thành công, kết quả thường chỉ xác nhận broker đã nhận/đồng ý xử lý lời gọi theo API; **không** xác nhận consumer đã hoàn tất nghiệp vụ.

**Ở consumer**, listener adapter chuyển message body và attributes thành event DTO đã được xác minh, kiểm tra schema version/nguồn phát tin cậy, sau đó gọi business handler. Handler dùng **eventId** hoặc một khóa nghiệp vụ phù hợp để xử lý lặp idempotent. Adapter/listener thực hiện **ack/delete/complete/nack** sau khi handler đạt trạng thái theo contract của broker.

Ví dụ một event model của ứng dụng:

~~~java
import java.time.Instant;

public record InvoiceIssuedEvent(
    String eventId,
    int schemaVersion,
    String invoiceId,
    Instant occurredAt
) {}
~~~

**Không đồng nhất message ID của broker với event ID của ứng dụng.** Broker có thể gán ID mới cho lần gửi, còn event ID cần ổn định qua lần publish lại để consumer khử trùng lặp. SQS visibility timeout, Service Bus lock/settlement, Pub/Sub ack deadline và dead-letter khác nhau; mapping lỗi/ack phải theo provider. Các header tracing được hỗ trợ phải truyền có chủ đích và không chứa token, thông tin tenant chưa xác minh hoặc PII nhạy cảm.

Nếu một use case vừa ghi database vừa publish event, **@Transactional** của JPA không tự gồm message broker. **Transactional outbox** là một lựa chọn để ghi trạng thái và bản ghi event trong cùng transaction database, rồi một worker phát event và đánh dấu kết quả theo operation ID.

## 12. Ranh giới dữ liệu với database và secret

### 12.1. Managed database

Với Spring Data JPA/JDBC trên PostgreSQL managed (AWS RDS, Azure Database hoặc Google Cloud SQL), entity/repository của ứng dụng không cần chứa tên cloud provider. Nhưng tầng persistence vẫn phải mapping giữa **domain entity** và **database row/entity**, bao gồm nullability, unique constraints, timezone, transaction, version để optimistic locking và mã lỗi SQL. 

Nếu dùng DynamoDB, Cosmos DB, Firestore hoặc Spanner, dữ liệu có partition key, consistency, index, transaction và query model đặc thù; adapter/repository phải thể hiện những khác biệt có ảnh hưởng đến bảo đảm nghiệp vụ. Đừng giả định mọi datastore đều hỗ trợ cùng semantics **save()** chỉ vì cùng triển khai một interface.

Lỗi **unique constraint violation** trong database có thể tương ứng với lỗi nghiệp vụ “đã tồn tại” nếu constraint bảo vệ một business invariant. Nhưng một lỗi kết nối database hoặc deadlock cần phân loại khác; không chuyển mọi exception persistence thành HTTP 409.

### 12.2. Secret management

Khi đọc AWS Secrets Manager, Azure Key Vault hoặc Google Secret Manager, application service thường chỉ cần giá trị secret theo một tên/capability rõ ràng. Adapter chuyển tên đó thành resource identifier của provider, gọi client, xử lý rotation/versioning và ánh xạ lỗi như missing secret, permission denied hoặc temporary unavailable.

**Không cho secret value đi vào generic exception, structured log, URL query string, message attributes hoặc object metadata.** Nếu secret được đưa vào Spring config tại startup, kiểm tra vòng đời refresh và cách hệ thống xử lý rotation. Nếu secret được đọc runtime, cân nhắc cache/TTL và identity của workload để tránh mỗi HTTP request lại gọi secret manager một lần.

## 13. Sử dụng thông tin yêu cầu để observability và hỗ trợ sự cố

Một log an toàn ở adapter nên có cấu trúc gần như:

~~~text
operation=object.put
provider=aws
operationId=invoice-123-revision-2
correlationId=7cde...         # ID đã được validate
providerRequestId=...          # chỉ khi SDK cung cấp
outcome=TEMPORARY_UNAVAILABLE
durationMs=217
attempt=2
~~~

Không ghi bucket/tenant/document key vào nhãn metric có cardinality cực lớn. Hãy chọn:

| Dữ liệu quan sát | Log/trace | Metric labels |
| --- | --- | --- |
| Provider, operation, result category | Có | Có, cardinality thấp |
| Duration, retry count, HTTP status/error category | Có | Histogram/counter phù hợp |
| Operation ID/correlation ID | Có, theo chính sách bảo mật | Thường **không** vì cardinality rất cao |
| Cloud request ID | Có, khi provider cung cấp | Không |
| Full object key, user email, payload | Chỉ khi đã có quy tắc bảo mật rõ ràng; mặc định tránh | Không |
| Token, secret, credential | Không | Không |

**Context propagation:** với Spring MVC, MDC/ThreadLocal có thể hữu dụng trong cùng thread, nhưng khi dùng **CompletableFuture**, executor, listener hoặc WebFlux/Reactor, context không tự di chuyển chính xác giữa các thread. Sử dụng cơ chế context propagation được Spring/Micrometer/Reactor và SDK hỗ trợ theo phiên bản, hoặc truyền một **OperationContext** đã được kiểm tra qua API của ứng dụng. Không ghi log theo nhầm tenant vì copy ThreadLocal không đúng.

**Traceparent/W3C Trace Context** giúp kết nối distributed traces khi client/server instrumentation hỗ trợ. Không giả định provider cloud bảo toàn toàn bộ trace qua mọi API. Một SDK request ID thuộc **provider call**, còn trace ID thuộc **hệ thống tracing**, và operation ID thuộc **nghiệp vụ**; chúng bổ sung nhau.

## 14. Async/reactive: ngoại lệ và metadata vẫn cần mapping

Khi đổi từ SDK đồng bộ sang bất đồng bộ, ứng dụng vẫn cần cùng một hợp đồng lỗi, nhưng error có thể được chuyển trong **future** hoặc **publisher** thay vì ném ngay trong phương thức:

| Execution model | Kết quả thành công | Lỗi |
| --- | --- | --- |
| SDK sync | Giá trị trả về từ method | Exception được throw trong lúc gọi |
| SDK async | **CompletableFuture** hoàn tất | Future hoàn tất **exceptionally**, có thể được bọc bởi CompletionException |
| Reactor | **Mono/Flux** phát tín hiệu | **onError**; adapter dùng onErrorMap/onErrorResume có điều kiện |

Ví dụ chuyển từ một future mà **AsyncDocumentStore** trả về sang Mono trong Spring WebFlux:

~~~java
import reactor.core.publisher.Mono;

public Mono<StoredDocument> saveReactive(
        AsyncDocumentStore asyncStore,
        DocumentWrite doc) {
    return Mono.defer(() ->
        Mono.fromFuture(asyncStore.put(doc)));
}
~~~

Ví dụ giả định **AsyncDocumentStore.put** trả **CompletableFuture<StoredDocument>**. **Mono.defer** giúp trì hoãn việc gọi async client cho tới lúc subscribe; một future đã được tạo trước đó có thể đã bắt đầu I/O. Nếu mapping exception xảy ra bên trong adapter, **Mono** nhận lỗi ứng dụng đã chuẩn hóa; nếu adapter trả raw SDK exception, cần **onErrorMap** có điều kiện, giữ root cause, không nuốt mọi lỗi bằng **onErrorResume**.

**Retry publisher** có thể subscribe lại và thực hiện ghi mới; cần operation ID/object key ổn định và hợp đồng idempotency. **Cancellation** không phải rollback của cloud. Nếu controller trả trước khi future/Mono hoàn tất, client HTTP có thể nhận phản hồi thành công sai nghĩa. Với messaging listener, phải bảo đảm xử lý/ack chờ completion theo API listener thực tế.

## 15. Kiểm thử mapping và lỗi theo từng ranh giới

| Mức | Điều xác minh | Kỹ thuật |
| --- | --- | --- |
| Unit test application service | Tạo **DocumentWrite** đúng, kiểm tra quyền, không dùng SDK | Mock/fake **DocumentStore** |
| Unit test adapter request | Bucket/key/content type/metadata được ánh xạ đúng | Mock SDK client, **ArgumentCaptor** |
| Unit test adapter error | S3 403/503, lỗi transport thành **StorageFailure** phù hợp | Mock SDK exception, assert error code |
| Context test | Chỉ đúng provider adapter được tạo, injection đúng client | Spring context / ApplicationContextRunner |
| Emulator integration | SDK thật upload/download, metadata đúng, serialization | LocalStack cho AWS, Azurite cho Blob, emulator/test environment thích hợp cho GCP |
| Cloud smoke test | Identity, IAM/RBAC, endpoint, request ID, timeout/retry | Tài nguyên thử nghiệm riêng với quyền tối thiểu |

### 15.1. Unit test adapter tạo request đúng

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;

class S3DocumentStoreTest {
    @Test
    void mapsApplicationDataToS3Request() {
        S3Client client = mock(S3Client.class);
        when(client.putObject(
                any(PutObjectRequest.class), any(RequestBody.class)))
            .thenReturn(PutObjectResponse.builder().build());

        S3DocumentStore adapter = new S3DocumentStore(client, "test-bucket");
        DocumentWrite doc = new DocumentWrite(
            "invoices/42.pdf",
            new byte[] {1, 2, 3},
            "application/pdf",
            "operation-42");

        StoredDocument receipt = adapter.put(doc);

        ArgumentCaptor<PutObjectRequest> captor =
            ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(client).putObject(captor.capture(), any(RequestBody.class));

        PutObjectRequest sdkRequest = captor.getValue();
        assertEquals("test-bucket", sdkRequest.bucket());
        assertEquals("invoices/42.pdf", sdkRequest.key());
        assertEquals("application/pdf", sdkRequest.contentType());
        assertEquals("operation-42",
            sdkRequest.metadata().get("operation-id"));
        assertEquals(doc.objectKey(), receipt.objectKey());
    }
}
~~~

Test này kiểm tra **adapter mapping**, không gọi S3. Thêm test mô phỏng **S3Exception.builder().statusCode(403).build()** để xác nhận **StorageFailure.code()==ACCESS_DENIED**, và test **503** thành **TEMPORARY_UNAVAILABLE**. Thêm test **SdkClientException** thành **OUTCOME_UNKNOWN** cho thao tác ghi. Để kiểm tra bytes thật và lifecycle stream, cần test riêng request body hoặc integration test; captor của **PutObjectRequest** không tự kiểm tra nội dung file.

### 15.2. Contract test đa provider

Một bộ contract test cho **DocumentStore** có thể gồm:

1. Ghi object và đọc lại nội dung/content type đúng; không lộ kiểu dữ liệu SDK.
2. Gửi cùng operation ID hai lần theo idempotency contract đã định nghĩa; kiểm tra có ghi đè, conflict hay trả cùng kết quả.
3. Truy cập resource sai quyền, resource không tồn tại, lỗi tạm thời, precondition failed; kiểm tra lỗi ứng dụng được map đúng.
4. Tạo key chứa Unicode/ký tự đặc biệt theo policy đã định nghĩa, kiểm tra encoding và không tự thay đổi key.
5. Thực hiện đồng thời hai thao tác create-if-absent để tìm race nếu contract có yêu cầu tạo duy nhất.
6. Kiểm tra provider request ID/trace thông tin an toàn xuất hiện trong log nội bộ, không trong public error body.

Emulator hỗ trợ kiểm thử kỹ thuật nhưng thường không mô phỏng đầy đủ IAM/RBAC, quota, network, encryption và mọi hành vi của cloud. Vì vậy cần cloud smoke test riêng cho các bảo đảm mà adapter tuyên bố hỗ trợ, dùng tài nguyên có cleanup và không chứa dữ liệu sản xuất.

## 16. Quy trình chẩn đoán lỗi tích hợp

Khi một use case thất bại, lần theo ranh giới theo thứ tự:

1. **Input:** HTTP/message payload có hợp lệ, content type và schema version đúng không?
2. **Use case:** identity/tenant đã được xác thực? Business authorization và object key đã đúng chưa?
3. **Port:** hợp đồng yêu cầu ghi đè hay create-if-absent? Có operation ID ổn định khi retry không?
4. **Adapter:** mapping bucket/container/project, content metadata, SDK request và timeout đã đúng chưa?
5. **SDK/client:** dùng credential chain, endpoint và region/project nào? Có lỗi transport trước/sau gửi không?
6. **Managed service:** IAM/RBAC, quota, precondition, mã lỗi và request ID provider cho biết điều gì?
7. **Đường về:** SDK exception có bị wrapper che mất? Adapter có ánh xạ đúng lỗi hay controller đã trả thông điệp sai nghĩa?
8. **Tái thực hiện:** cloud có thể đã xử lý thao tác chưa? Có cần reconcile trạng thái trước khi retry?

Ví dụ app nhận **S3 AccessDenied** trong lúc ghi PDF: xác nhận workload role, action **s3:PutObject**, resource ARN/bucket policy và các điều kiện deny. Không tự đổi HTTP response thành “người dùng không được xem hóa đơn” nếu application authorization đã cho phép. Ngược lại, một người dùng không có quyền với invoice phải bị từ chối **trước** khi adapter gọi S3, bất kể workload role có quyền rộng tới đâu.

## 17. Bài tập thực hành

**Bài tập 1 — Phân ranh giới dữ liệu.** Một controller nhận request JSON chứa invoiceId, tenantId, bucketName, accessToken và rawS3Request. Hãy thiết kế lại DTO để caller chỉ cung cấp thông tin cần thiết; chỉ ra lớp nào xác minh tenant, tạo object key và chọn bucket/credential theo cấu hình đáng tin cậy.

**Bài tập 2 — Mapping exception.** S3 adapter trả raw **S3Exception** cho REST controller. Viết enum lỗi ứng dụng và ánh xạ các trường hợp **403**, **409/412**, **503** và SDK timeout. Giải thích trường hợp nào có thể là **OUTCOME_UNKNOWN** và vì sao không thể retry mọi lỗi.

**Bài tập 3 — Ba provider.** Giữ **DocumentWrite** và **StoredDocument** rồi phác thảo adapter cho Azure Blob và Google Cloud Storage. Nêu cách map content type, object key, operation ID, precondition và mã lỗi; đề xuất ít nhất ba contract test chung.

**Bài tập 4 — Correlation và operation ID.** Một upload request thất bại hai lần rồi thành công ở lần thứ ba. Hãy phân biệt business operation ID, trace ID, correlation ID và ba cloud request ID; xác định trường nào xuất hiện trong audit log, metric labels và response công khai.

**Bài tập 5 — Schema evolution.** Publisher gửi **InvoiceIssuedEvent** qua SQS/Service Bus/Pub/Sub; consumer cũ chưa biết trường **currency** mới. Thiết kế schema versioning, validation và backward compatibility; giải thích eventId nào cần ổn định khi producer retry.

**Bài tập 6 — Ranh giới transaction.** Application ghi invoice vào PostgreSQL, upload PDF và publish event. Nếu upload timeout nhưng object đã được ghi, hãy đề xuất key ổn định, trạng thái **PENDING/READY**, outbox và cách reconcile mà không tạo document/event trùng.

**Bài tập 7 — Kiểm thử phân lớp.** Viết unit test của application service không import AWS SDK; viết adapter test dùng **ArgumentCaptor** với **PutObjectRequest**; cuối cùng thiết kế cloud smoke test xác minh quyền workload và nội dung đã lưu.

## 18. Ghi nhớ

- **Inbound DTO, application command, outbound port request và SDK request/response là các kiểu dữ liệu ở những ranh giới khác nhau.** Chỉ đưa thông tin nghiệp vụ cần thiết qua port; để chi tiết provider ở adapter.
- **Adapter chuyển ngoại lệ SDK thành lỗi ứng dụng có ngữ nghĩa rõ**, giữ nguyên nhân và provider request ID cho chẩn đoán nội bộ. Không sao chép máy móc status cloud vào HTTP response cho caller.
- **Business operation ID, correlation ID, trace ID và cloud request ID** có nguồn, phạm vi và mục đích khác nhau; chúng không thay thế cho nhau.
- **Metadata, Content-Type và message attributes** phải được validate, chuẩn hóa encoding và giới hạn dữ liệu nhạy cảm. Không chuyển token/header do caller đưa vào SDK một cách mù quáng.
- **Timeout/cancellation có thể để lại kết quả không rõ ràng**. Retry thao tác có side effect cần object key hoặc event ID ổn định, idempotency, precondition hoặc quy trình đối chiếu trạng thái.
- Cùng một tư duy áp dụng cho **AWS, Azure, Google Cloud**, nhưng status/error codes, versioning, metadata, IAM/RBAC và acknowledgment khác nhau; kiểm thử contract và cloud thật phải bảo vệ những cam kết đã đặt ra.
