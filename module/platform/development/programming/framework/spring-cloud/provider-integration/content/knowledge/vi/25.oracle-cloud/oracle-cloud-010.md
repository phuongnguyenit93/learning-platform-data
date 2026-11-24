# Dùng OCI Java SDK cho chức năng ngoài phạm vi starter

Spring Cloud OCI cung cấp các starter để đưa dịch vụ managed của Oracle Cloud Infrastructure (OCI) vào Spring Boot bằng những API quen thuộc. Trong nhiều trường hợp, các abstraction như Storage, Queue, Streaming, VaultTemplate hoặc Spring Resource đã đủ cho nghiệp vụ. Tuy nhiên, có những yêu cầu cần operation, request option hoặc khả năng SDK chưa được starter bộc lộ.

OCI Java SDK là lớp client chính thức cho các OCI service API. Ứng dụng Spring có thể dùng SDK trực tiếp trong những trường hợp đó, đồng thời tiếp tục dùng cấu hình authentication, region và dependency management của Spring Cloud OCI. Mục tiêu là mở rộng đúng phần còn thiếu mà không làm rò rỉ OCI SDK vào toàn bộ business domain hoặc tạo thêm credential/client ngoài tầm quản lý.

Bài này trình bày khi nào cần dùng SDK trực tiếp, cách lấy client/credential từ Spring Cloud OCI, cách tạo SDK client riêng cho service chưa có starter, và các kỹ thuật quan trọng về pagination, waiter, multipart upload, async, retry, timeout, response stream, error handling và kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt Spring Cloud OCI starter, service abstraction và OCI Java SDK.
2. Nhận diện operation chưa được starter expose hoặc cần request option nâng cao.
3. Chọn đúng OCI SDK module theo service cần gọi.
4. Tái sử dụng authentication provider do Spring Cloud OCI cấu hình.
5. Lấy raw SDK client từ service bean khi starter có hỗ trợ.
6. Tạo SDK client bổ sung dưới dạng Spring bean khi chưa có client phù hợp.
7. Cấu hình region, endpoint, timeout và HTTP client.
8. Dùng request/response builder, paginator và waiter.
9. Xử lý object lớn bằng multipart upload.
10. Chọn synchronous hoặc asynchronous SDK client.
11. Quản lý retry, idempotency, request stream và unknown outcome.
12. Đóng response stream và client đúng vòng đời.
13. Xử lý BmcException và ghi nhận OCI request ID.
14. Đặt SDK phía sau adapter boundary và kiểm thử độc lập.
15. Bảo vệ IAM, credential, log và dữ liệu khi gọi API trực tiếp.

## 2. Starter và OCI Java SDK có vai trò khác nhau

Spring Cloud OCI là lớp tích hợp Spring Boot. Starter cung cấp auto-configuration, property binding, bean và abstraction để ứng dụng thao tác với dịch vụ theo idiom Spring.

OCI Java SDK cung cấp các client, request/response model và operation gần với OCI API hơn. Một số starter còn expose raw SDK client để ứng dụng dùng operation chưa có trong abstraction.

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Spring Cloud OCI starter | Cấu hình authentication, region và bean cho service | spring-cloud-oci-starter-storage |
| Spring abstraction/service bean | API đơn giản cho use case phổ biến | Storage, Queue, Streaming, VaultTemplate |
| OCI Java SDK | API đầy đủ hơn, request/response chi tiết | ObjectStorage, Identity, Compute, QueueClient |
| OCI REST API | Giao thức HTTP nền tảng | Dùng khi SDK chưa hỗ trợ operation hoặc cần endpoint đặc thù |

Không phải mọi chức năng nâng cao đều bắt buộc dùng SDK. Trước tiên xem abstraction hiện có đã đáp ứng chưa. Nếu service bean đã cung cấp raw SDK client, ưu tiên tái sử dụng client đó.

### 2.1. Khi nào nên giữ ở starter abstraction?

Dùng abstraction của starter khi:

- Operation đã có method rõ ràng.
- Không cần request option đặc biệt.
- Không cần API mới hơn SDK được starter quản lý.
- Muốn giữ code đơn giản và dễ mock.
- Không cần truy cập service-specific model hoặc response metadata.

Ví dụ, nếu Storage đã cung cấp upload/download theo nhu cầu, không cần viết lại cùng thao tác bằng PutObjectRequest và GetObjectRequest.

### 2.2. Khi nào nên dùng SDK trực tiếp?

Dùng OCI Java SDK khi:

- Starter chưa expose operation cần thiết.
- Cần lấy metadata hoặc response header đặc thù.
- Cần list object versions, retention rules, replication policies hoặc pre-authenticated requests.
- Cần điều khiển conditional request, ETag, request ID hoặc service option.
- Cần paginator, waiter hoặc async client.
- Cần multipart upload nâng cao.
- Cần gọi service OCI chưa có starter tương ứng.
- Cần dùng capability mới hơn abstraction Spring đang bọc, sau khi xác minh version compatibility.

### 2.3. Khi nào cần raw REST request?

Chỉ cân nhắc raw request khi API chưa được SDK expose hoặc cần gọi một endpoint đặc thù mà client SDK không expose. Nếu dùng raw request, vẫn nên dùng request signer của OCI SDK. Không tự xây chữ ký OCI bằng chuỗi thủ công.

## 3. Quy trình chọn lớp API

~~~mermaid
flowchart TD
    A[Use case cần gọi OCI] --> B{Starter có API phù hợp?}
    B -->|Có| C[Dùng Spring abstraction]
    B -->|Chưa đủ option| D{Starter expose raw SDK client?}
    D -->|Có| E[Tái sử dụng raw client]
    D -->|Không| F{OCI Java SDK có service client?}
    F -->|Có| G[Tạo SDK client Spring bean]
    F -->|Không| H[Đánh giá raw signed request]
    E --> I[Đặt sau adapter boundary]
    G --> I
    H --> I
    C --> I
    I --> J[Kiểm thử auth, IAM, retry và lifecycle]
~~~

Một quyết định tốt cần ghi lại operation nào thiếu trong starter, vì sao SDK trực tiếp cần thiết, module SDK nào được dùng và ai chịu trách nhiệm vận hành client đó.

## 4. Chọn OCI SDK module và dependency

OCI Java SDK được chia thành các module theo service. Ví dụ:

| Service | Artifact SDK thường dùng |
| --- | --- |
| Common/authentication | oci-java-sdk-common |
| Identity | oci-java-sdk-identity |
| Object Storage | oci-java-sdk-objectstorage |
| Compute | oci-java-sdk-compute |
| Vault/Secrets | oci-java-sdk-vault hoặc module service tương ứng theo SDK release |
| Streaming | oci-java-sdk-streaming |
| Queue | oci-java-sdk-queue |
| Logging | oci-java-sdk-logging |
| Notifications | oci-java-sdk-ons |

Tên module có thể thay đổi khi OCI bổ sung hoặc tách service. Kiểm tra Maven Central và Javadoc của đúng SDK release trước khi khai báo.

### 4.1. Dependency khi đã có service starter

Nếu ứng dụng đã khai báo service starter, SDK module tương ứng thường đã nằm trong dependency graph. Có thể dùng SDK types trong compile classpath mà không phải thêm một version SDK khác.

Ví dụ ứng dụng đã có Object Storage starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
</dependency>
~~~

Starter đã đưa các module cần thiết vào graph theo version mà release line của Spring Cloud OCI quản lý. Khi dùng trực tiếp ObjectStorage, không thêm một bản OCI SDK mới hơn chỉ để có classpath.

### 4.2. Dependency khi service chưa có starter

Nếu ứng dụng cần một service chưa được Spring Cloud OCI hỗ trợ, có thể khai báo SDK module tương ứng:

~~~xml
<dependency>
    <groupId>com.oracle.oci.sdk</groupId>
    <artifactId>oci-java-sdk-identity</artifactId>
</dependency>
~~~

Đoạn khai báo không ghi version để minh họa việc version cần được quản lý bằng dependency management phù hợp của project. Với OCI SDK, hãy chọn version tương thích với Spring Cloud OCI release đang dùng và các module SDK khác trong graph.

Nếu project không có starter nào quản lý OCI SDK, dùng OCI SDK BOM hoặc version catalog chính thức để giữ các module SDK đồng bộ.

### 4.3. Không trộn các version OCI SDK

Các module SDK dùng chung nhiều class trong common runtime, authentication, HTTP client và model. Trộn module 3.x ở các patch khác nhau có thể gây NoSuchMethodError, NoClassDefFoundError hoặc lỗi serialization khi chạy.

Kiểm tra graph:

~~~bash
mvn dependency:tree -Dincludes=com.oracle.oci.sdk
~~~

Hoặc Gradle:

~~~bash
./gradlew dependencyInsight --dependency oci-java-sdk-common --configuration runtimeClasspath
~~~

Không ép riêng một module SDK lên version mới nếu chưa kiểm tra tương thích với starter và những module SDK còn lại.

## 5. Tái sử dụng authentication từ Spring Cloud OCI

OCI Java SDK cần một authentication provider. Spring Cloud OCI core starter đã auto-configure authentication theo property đang dùng, ví dụ FILE, SIMPLE, INSTANCE_PRINCIPAL, RESOURCE_PRINCIPAL, SESSION_TOKEN hoặc WORKLOAD_IDENTITY.

Khi dùng SDK trực tiếp trong ứng dụng đã có core starter, hãy tái sử dụng provider được Spring Cloud OCI quản lý. Điều này giúp client trực tiếp dùng cùng identity với các service bean khác.

### 5.1. CredentialsProvider

Spring Cloud OCI có wrapper CredentialsProvider trong package:

~~~java
import com.oracle.cloud.spring.autoconfigure.core.CredentialsProvider;
~~~

Wrapper cung cấp AuthenticationDetailsProvider mà core starter đã tạo. Javadoc của Spring Cloud Oracle mô tả method getAuthenticationDetailsProvider() để lấy provider dùng với OCI SDK.

Ví dụ tạo một client cho service chưa có starter:

~~~java
@Configuration
public class OciAdvancedClientConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorageClient advancedObjectStorageClient(
            CredentialsProvider credentialsProvider,
            OciSdkProperties properties) {

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .build(credentialsProvider.getAuthenticationDetailsProvider());
    }
}
~~~

Ví dụ này giả định OciSdkProperties cung cấp region đã được đồng bộ với spring.cloud.oci.region.static. Nếu ứng dụng lấy region từ auth config file, hãy dùng cùng region resolution strategy của ứng dụng thay vì đặt một region khác.

### 5.2. Không tự tạo credential provider lần thứ hai

Tránh các cách sau trong ứng dụng đã có Spring Cloud OCI:

- Tự đọc ~/.oci/config lần nữa trong mỗi service.
- Tạo API key provider mới cho SDK trong khi starter đang dùng Instance Principal.
- Dùng FILE profile trong SDK nhưng production starter lại dùng Resource Principal.
- Nhúng private key vào code để tạo một client phụ.
- Tạo provider mới trong từng request.

Nếu starter dùng Instance Principal, SDK client bổ sung cũng phải dùng provider từ starter. Nếu starter dùng Workload Identity, không tự chuyển client phụ sang API key.

### 5.3. Khi cần cấu hình provider riêng

Chỉ tạo provider riêng khi có ranh giới identity được chủ đích, ví dụ một integration cần gọi tenancy khác bằng credential khác. Khi đó cần quản lý riêng:

- Nguồn credential.
- Rotation và refresh.
- IAM policy.
- Region/endpoint.
- Lifecycle provider.
- Audit identity.
- Cách kiểm thử và thu hồi.

Không dùng hai identity chỉ vì một ví dụ SDK trên Internet dùng profile DEFAULT.

## 6. Tái sử dụng raw client từ starter

Một số service bean của Spring Cloud OCI expose client OCI Java SDK trực tiếp. Điều này hữu ích khi abstraction không có method cần dùng nhưng starter đã tạo đúng authentication, region và client configuration.

Các ví dụ được công bố trong Javadoc Spring Cloud Oracle gồm:

| Spring bean | Raw SDK client |
| --- | --- |
| Storage | ObjectStorage |
| Streaming | Streaming |
| LogService | Logging |
| Queue | QueueClient và QueueAdminClient |
| Notification | NotificationDataPlane và NotificationControlPlane clients |
| Function | FunctionsInvokeClient |
| AutonomousDb | DatabaseClient |

Ví dụ dùng raw Object Storage client:

~~~java
@Service
public class ObjectVersionInspector {

    private final Storage storage;

    public ObjectVersionInspector(Storage storage) {
        this.storage = storage;
    }

    public String getObjectEtag(
            String namespace,
            String bucket,
            String objectName) {

        HeadObjectResponse response = storage.getClient().headObject(
                HeadObjectRequest.builder()
                        .namespaceName(namespace)
                        .bucketName(bucket)
                        .objectName(objectName)
                        .build());

        return response.getEtag();
    }
}
~~~

Storage vẫn chịu trách nhiệm abstraction thông thường; chỉ operation headObject dùng SDK trực tiếp. Không cần tạo ObjectStorageClient thứ hai.

Tên method raw client và return type phải khớp Javadoc của Spring Cloud OCI release đang dùng. Nếu một release thay đổi public API, cập nhật adapter ở một nơi duy nhất.

## 7. Tạo SDK client riêng như Spring bean

Khi không có service bean để lấy raw client, tạo client như một singleton bean. Client cần được cấu hình region, authentication và HTTP options trước khi đưa vào sử dụng.

### 7.1. Cấu hình timeout

Ví dụ cấu hình client:

~~~java
@Configuration
public class OciSdkHttpConfiguration {

    @Bean
    ClientConfiguration ociSdkClientConfiguration() {
        return ClientConfiguration.builder()
                .connectionTimeoutMillis(3000)
                .readTimeoutMillis(60000)
                .build();
    }
}
~~~

Các giá trị trên chỉ là điểm bắt đầu minh họa. Chọn timeout theo latency SLO, kích thước payload, thời gian xử lý của service và timeout của request phía trên.

### 7.2. Khởi tạo client

Ví dụ dùng một property riêng cho SDK client để thể hiện region được chọn rõ ràng. Giá trị này phải trùng với region mặc định của Spring Cloud OCI trong deployment:

~~~yaml
app:
  oci:
    sdk:
      region: ap-singapore-1
~~~

Khai báo properties class:

~~~java
@ConfigurationProperties(prefix = "app.oci.sdk")
public record OciSdkProperties(String region) {
}
~~~

Đăng ký properties class bằng @EnableConfigurationProperties hoặc @ConfigurationPropertiesScan.

~~~java
@Configuration
@EnableConfigurationProperties(OciSdkProperties.class)
public class OciIdentityClientConfiguration {

    @Bean(destroyMethod = "close")
    IdentityClient identityClient(
            CredentialsProvider credentialsProvider,
            ClientConfiguration clientConfiguration,
            OciSdkProperties properties) {

        return IdentityClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .configuration(clientConfiguration)
                .build(credentialsProvider.getAuthenticationDetailsProvider());
    }
}
~~~

Client được tạo một lần khi Spring context khởi động và được đóng khi context dừng. Không gọi builder trong mỗi method của service.

### 7.3. Region và endpoint

Một service client được gắn với một region/endpoint. Nếu ứng dụng cần gọi nhiều region, tạo client riêng cho từng region và đặt chúng dưới bean name/qualifier rõ ràng.

Không đổi region của cùng một client trong lúc nhiều request đang chạy. Điều đó có thể khiến request đi nhầm endpoint.

Ưu tiên region resolution từ Spring Cloud OCI. Nếu cần endpoint custom, chỉ cấu hình endpoint khi có yêu cầu rõ như realm/region mới, private endpoint hoặc API endpoint đặc thù.

### 7.4. Khi nào dùng client configurator?

OCI SDK cho phép cấu hình HTTP client, TLS, trust store, proxy, connection manager và các property khác thông qua builder/client configurator. Chỉ thay đổi các tùy chọn này khi có yêu cầu vận hành cụ thể.

Trước khi thêm custom HTTP client:

- Kiểm tra HTTP implementation mà SDK release đang dùng.
- Xác minh thread safety.
- Đo connection pooling và TLS handshake.
- Kiểm tra proxy/network route.
- Kiểm thử shutdown và resource cleanup.
- Tránh tạo hai connection pool độc lập nếu không cần.

## 8. Request và response builder

OCI SDK dùng request model và builder để tạo request. Mỗi operation trả về response model có dữ liệu và metadata như request ID, ETag hoặc pagination token.

Ví dụ đọc bucket:

~~~java
GetBucketResponse response = objectStorage.getBucket(
        GetBucketRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucketName)
                .build());

String requestId = response.getOpcRequestId();
Bucket bucket = response.getBucket();
~~~

Đọc object:

~~~java
GetObjectResponse response = objectStorage.getObject(
        GetObjectRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucketName)
                .objectName(objectName)
                .build());

try (InputStream input = response.getInputStream()) {
    Files.copy(input, targetPath, StandardCopyOption.REPLACE_EXISTING);
}
~~~

Phải đóng InputStream trả về từ GetObjectResponse. Nếu stream không được đóng, HTTP connection có thể không được trả lại pool và làm cạn connection/resource.

### 8.1. Dùng response metadata

Response có thể chứa:

- OPC request ID để tra cứu request trong OCI Support/Audit.
- ETag để kiểm tra object version/content state.
- Pagination token.
- Service-specific metadata.
- Work request ID khi operation chạy bất đồng bộ phía service.

Không bỏ metadata nếu workflow cần reconciliation hoặc hỗ trợ vận hành.

### 8.2. Conditional request

Một số operation hỗ trợ If-Match hoặc If-None-Match. Dùng điều kiện để tránh ghi đè object khi state đã thay đổi.

Ví dụ khái niệm:

~~~java
PutObjectRequest request = PutObjectRequest.builder()
        .namespaceName(namespace)
        .bucketName(bucket)
        .objectName(objectName)
        .ifMatch(expectedEtag)
        .putObjectBody(content)
        .build();
~~~

Xác minh operation cụ thể có hỗ trợ conditional header nào và semantics của HTTP 412/409. Không giả định mọi service API đều hỗ trợ cùng điều kiện.

## 9. Pagination: không giả định list trả về toàn bộ dữ liệu

Nhiều OCI list operation trả kết quả theo trang. Nếu chỉ đọc trang đầu, ứng dụng có thể bỏ sót resource mà không có exception.

Có hai cách:

1. Dùng paginator do service client cung cấp.
2. Tự đọc page token và gọi request tiếp theo.

Ví dụ tổng quát với ListBuckets:

~~~java
String pageToken = null;

do {
    ListBucketsResponse response = objectStorage.listBuckets(
            ListBucketsRequest.builder()
                    .namespaceName(namespace)
                    .compartmentId(compartmentId)
                    .page(pageToken)
                    .build());

    processBuckets(response.getItems());
    pageToken = response.getOpcNextPage();

} while (pageToken != null);
~~~

Với API khác, tên trường token có thể khác. Ví dụ Object Storage ListObjects sử dụng start/nextStartWith. Đọc Javadoc của operation, không sao chép pagination field của service khác.

### 9.1. Dùng paginator

Service client thường có getPaginators(). Paginator có thể cung cấp:

- Response iterator: lặp qua từng response page.
- Record iterator: lặp qua từng item trong các page.

Paginator giúp tránh tự viết page token loop, nhưng không làm cho danh sách lớn trở nên miễn phí. Vẫn cần kiểm soát tốc độ, memory và xử lý lỗi giữa chừng.

### 9.2. Pagination và thay đổi dữ liệu

Nếu resource thay đổi trong lúc lặp qua nhiều trang, kết quả có thể phản ánh trạng thái ở nhiều thời điểm. Không dùng pagination như một snapshot transaction nếu API không cam kết điều đó.

Nếu cần đồng bộ dữ liệu, lưu checkpoint/page token bền vững và thiết kế reconciliation cho resource thay đổi trong quá trình scan.

## 10. Waiter: chờ resource đạt trạng thái mong muốn

Một số operation OCI tạo resource hoặc khởi động công việc nhưng trả về trước khi resource đạt trạng thái cuối cùng.

Waiter trong SDK đóng gói polling:

- Gọi API kiểm tra trạng thái.
- Chờ theo delay strategy.
- Dừng khi đạt state mong muốn.
- Dừng khi timeout hoặc termination strategy kết thúc.

Ví dụ khái niệm:

~~~java
ComputeWaiters waiters = computeClient.getWaiters();

GetInstanceResponse response = waiters.forInstance(
        GetInstanceRequest.builder()
                .instanceId(instanceId)
                .build(),
        Instance.LifecycleState.Running)
    .execute();
~~~

Dùng waiter thay vì viết vòng lặp polling riêng khi SDK đã cung cấp waiter cho resource đó. Chọn termination timeout hợp lý và không chờ vô hạn trong HTTP request của người dùng.

Nếu waiter timeout, resource có thể vẫn đang provisioning. Ghi nhận OCID và trạng thái để tiếp tục reconciliation thay vì tạo resource trùng lặp.

## 11. Multipart upload cho object lớn

PutObject phù hợp với nhiều upload thông thường. Với file lớn, multipart upload chia object thành nhiều part, có thể upload song song và retry từng part.

OCI Java SDK cung cấp API multipart ở mức thấp và UploadManager ở mức cao. UploadManager có thể:

- Chia file thành nhiều part.
- Upload các part song song.
- Thu thập ETag/part metadata.
- Commit các part thành object hoàn chỉnh.
- Giảm chi phí retry toàn bộ file khi một part thất bại.

Oracle khuyến nghị dùng multipart upload cho object lớn hơn khoảng 100 MiB. Chọn part size và concurrency dựa trên băng thông, memory, CPU và quota của workload.

### 11.1. Raw multipart API

Dùng raw multipart API khi cần kiểm soát:

- Thời điểm tạo upload.
- Part number.
- Upload từng part.
- Lưu upload ID và ETag.
- Commit upload.
- Abort upload khi workflow thất bại.

Cách này phù hợp khi cần pause/resume hoặc phân phối upload qua nhiều worker. Đổi lại, ứng dụng phải quản lý state và cleanup đầy đủ.

### 11.2. UploadManager

Dùng UploadManager khi muốn SDK quản lý phần chia file và upload song song. Cần kiểm tra API constructor/builder theo đúng OCI SDK version và đặt giới hạn concurrency để tránh tạo quá nhiều request đồng thời.

### 11.3. Cleanup upload chưa commit

Multipart upload bị bỏ dở có thể giữ các part chưa commit và phát sinh chi phí lưu trữ. Thiết kế:

- Abort upload khi ứng dụng biết workflow đã thất bại.
- Có lifecycle rule để dọn uncommitted multipart uploads.
- Lưu upload ID nếu cần resume.
- Theo dõi upload tồn tại quá lâu.
- Không commit object trước khi đã xác minh đủ part và ETag.

## 12. Retry và idempotency

OCI Java SDK có retry configuration ở nhiều cấp:

- SDK/global.
- Client.
- Request.

Retry request-level có độ ưu tiên cao hơn client-level; client-level ghi đè global default cho client tương ứng.

SDK hiện hành có default retry cho một số operation/lỗi transient như throttling, một số 5xx, timeout và lỗi kết nối. Không phải mọi operation đều bật retry mặc định; kiểm tra Javadoc của operation và SDK release đang dùng.

### 12.1. Retry không có nghĩa exactly-once

Nếu client timeout sau khi server đã thực hiện operation, lần retry có thể lặp side effect. Cần xác định operation idempotent hay không.

| Operation | Rủi ro khi retry | Thiết kế |
| --- | --- | --- |
| GET metadata | Thấp | Retry transient theo SDK policy |
| List resources | Thấp, nhưng dữ liệu có thể thay đổi giữa page | Checkpoint/pagination |
| PutObject cùng object key | Có thể ghi đè | Conditional write, versioning hoặc object key idempotent |
| Create resource | Có thể tạo trùng hoặc nhận conflict | Dùng deterministic name/idempotency nếu API hỗ trợ; reconcile sau timeout |
| Delete resource | Có thể trả not found ở lần sau | Xem not found có phải trạng thái mong muốn |
| Publish message | Có thể publish duplicate | Business event ID và consumer deduplication |

### 12.2. Stream body và retry

PutObject tiêu thụ InputStream. Nếu stream hỗ trợ mark/reset, SDK có thể reset stream khi retry. Nếu không, SDK có thể wrap/buffer stream trong memory.

Với stream lớn hoặc không thể đọc lại:

- Không dựa vào retry mặc định mà chưa kiểm tra stream behavior.
- Dùng FileInputStream/nguồn có thể mở lại nếu phù hợp.
- Dùng multipart upload cho file lớn.
- Cân nhắc tắt retry cho request cụ thể nếu retry không an toàn.
- Kiểm tra unknown outcome bằng HeadObject hoặc metadata trước khi upload lại.

### 12.3. Retry budget

Tổng thời gian retry phải nằm trong timeout budget của caller. Nếu HTTP API có timeout 10 giây nhưng SDK retry 8 lần với read timeout dài, request có thể giữ thread quá lâu.

Đặt retry termination theo số lần hoặc tổng thời gian. Tránh retry đồng thời ở SDK, service adapter, queue worker và API gateway mà không có budget chung.

## 13. Timeout, circuit breaker và async client

### 13.1. Timeout

ClientConfiguration có thể cấu hình connect timeout và read timeout. Chọn timeout theo loại operation:

- Metadata request: thường cần timeout ngắn.
- Download file: timeout phụ thuộc kích thước và network throughput.
- Control-plane provisioning: dùng waiter với tổng thời gian chờ dài hơn.
- Streaming hoặc long-running operation: dùng API và timeout riêng theo service.

Không dùng một timeout cực lớn cho toàn bộ client chỉ để tránh lỗi timeout.

### 13.2. Circuit breaker

Một số OCI SDK service client hỗ trợ default circuit breaker. Circuit breaker ngăn ứng dụng tiếp tục gửi request dồn dập khi service đang lỗi.

Trước khi thêm Resilience4j hoặc circuit breaker riêng, kiểm tra client SDK có default breaker không. Nếu dùng nhiều lớp breaker, xác định rõ:

- Lỗi nào tính là failure.
- Timeout của từng lớp.
- Thời gian open/half-open.
- Retry có chạy trước hay sau breaker.
- Cách đo và cảnh báo.

### 13.3. Async client

OCI Java SDK có asynchronous client cho một số service. Async API thường nhận AsyncHandler hoặc trả Future. Chọn async khi:

- Có nhiều I/O operation độc lập.
- Không muốn block request thread.
- Ứng dụng có executor/backpressure rõ.
- Có thể xử lý callback và error path đúng cách.

Async không tự động làm ứng dụng nhanh hơn. Nếu callback gọi blocking database hoặc xử lý CPU nặng, vẫn cần executor phù hợp.

Tài liệu OCI Java SDK hiện hành lưu ý default retry và circuit breaker chưa được hỗ trợ cho asynchronous clients. Phải tự thiết kế retry/error handling tương ứng và kiểm tra behavior của version đang dùng.

### 13.4. InputStream với async Object Storage

Với getObject async dùng AsyncHandler, nếu response chứa InputStream thì phải xử lý stream bên trong callback. SDK có thể đóng stream ngay sau khi callback hoàn tất.

Nếu dùng Java Future, caller cần đọc và đóng stream sau khi lấy response. Không giữ response stream rồi dùng sau callback khi SDK đã đóng nó.

## 14. Raw signed request khi SDK chưa có operation

Raw request là phương án cuối khi OCI API chưa được SDK expose hoặc cần gọi endpoint đặc thù bằng HTTP client khác.

OCI Java SDK có DefaultRequestSigner để tạo RequestSigner cho request không theo service client chuẩn.

Quy trình tổng quát:

1. Dùng authentication provider đã được cấu hình.
2. Tạo request signer theo tài liệu SDK.
3. Tạo HTTP request đúng method, path, query và headers.
4. Ký request theo signing rules của OCI.
5. Gửi qua HTTP client đã cấu hình TLS/proxy.
6. Ghi request ID và xử lý response/error.

Không tự ghép Authorization header bằng string. Request signing phụ thuộc method, host, path, date, body và header được ký. Sai một thành phần có thể gây 401 hoặc chữ ký không hợp lệ.

Raw request cần test kỹ với endpoint thực tế và cần một adapter riêng. Khi SDK release mới hỗ trợ operation, ưu tiên chuyển lại sang service client.

## 15. Client lifecycle và thread safety

OCI SDK client là đối tượng có connection pool, HTTP client và executor/resource liên quan. Không tạo client mới mỗi lần gọi service.

Với default Jersey implementation, SDK client thread-safe sau khi khởi tạo và endpoint được thiết lập. Có thể tái sử dụng client giữa nhiều request/thread. Với HTTP implementation thay thế, cần kiểm tra thread safety riêng.

Trong Spring:

- Khai báo client dưới dạng singleton bean.
- Đặt destroyMethod close để đóng khi context dừng.
- Không close client sau mỗi request.
- Không thay region/endpoint trên client đang được nhiều thread sử dụng.
- Tạo client riêng nếu cần endpoint/region khác.
- Đóng provider/scheduler riêng nếu ứng dụng tự tạo và sở hữu chúng.

Ví dụ:

~~~java
@Bean(destroyMethod = "close")
ObjectStorageClient objectStorageClient(...) {
    // Tạo một client cho region/identity cố định
}
~~~

Nếu client được lấy từ service starter, không tự close client do starter sở hữu trừ khi API ownership nói rõ. Để Spring Cloud OCI quản lý vòng đời bean của nó.

## 16. Xử lý lỗi BmcException

OCI SDK ném BmcException dưới dạng unchecked exception. Exception có thể chứa:

- HTTP status code.
- Service error code.
- Message.
- OCI request ID.
- Cause/timeout details.

Ví dụ:

~~~java
try {
    objectStorage.headObject(request);
} catch (BmcException ex) {
    log.warn(
            "OCI request failed: status={}, serviceCode={}, requestId={}",
            ex.getStatusCode(),
            ex.getServiceCode(),
            ex.getOpcRequestId());

    throw new OciStorageException(
            "Unable to inspect object",
            ex);
}
~~~

Không log credential, Authorization header, secret content hoặc toàn bộ payload nhạy cảm.

### 16.1. Phân loại lỗi

| Nhóm | Hành vi |
| --- | --- |
| 400 validation | Sửa request, không retry vô hạn |
| 401 authentication | Kiểm tra provider, token, signature và clock |
| 403 authorization | Kiểm tra IAM policy, resource scope và principal |
| 404 not found | Kiểm tra OCID, region, namespace và lifecycle |
| 409 conflict | Đọc service error code; reconcile state |
| 429 throttling | Backoff, giảm concurrency và tôn trọng retry policy |
| 5xx | Retry có giới hạn nếu operation an toàn |
| Timeout | Xem operation có thể đã thành công trước khi retry |

Không phân loại chỉ bằng HTTP status. Một status 409 có thể là trạng thái đã tồn tại hoặc một conflict cần xử lý theo service error code.

### 16.2. Ghi nhận request ID

Khi gọi OCI Support hoặc điều tra Audit, request ID giúp truy tìm một request cụ thể. Ghi request ID cùng operation, service, region và correlation ID của ứng dụng.

## 17. Đặt SDK phía sau adapter boundary

Business domain không nên phụ thuộc trực tiếp vào OCI request/response classes.

Ví dụ interface:

~~~java
public interface ObjectVersionReader {
    List<StoredObjectVersion> listVersions(
            String bucketName,
            String objectNamePrefix);
}
~~~

Adapter OCI:

~~~java
@Component
public class OciObjectVersionReader implements ObjectVersionReader {

    private final ObjectStorage objectStorage;
    private final String namespace;

    public OciObjectVersionReader(
            Storage storage,
            ObjectStorageProperties properties) {
        this.objectStorage = storage.getClient();
        this.namespace = properties.namespace();
    }

    @Override
    public List<StoredObjectVersion> listVersions(
            String bucketName,
            String objectNamePrefix) {

        // Dùng ListObjectVersionsRequest của OCI SDK.
        // Map SDK response thành StoredObjectVersion của ứng dụng.
        return loadAndMapVersions(bucketName, objectNamePrefix);
    }
}
~~~

Đoạn adapter mô tả cấu trúc; phần loadAndMapVersions cần triển khai theo request/response model của SDK release đang dùng.

Lợi ích:

- Business code không phụ thuộc OCI SDK.
- Unit test có thể mock interface nội bộ.
- Có thể thay implementation hoặc service mà không sửa domain.
- OCI-specific error được map về lỗi ứng dụng.
- Quyền, retry và telemetry tập trung tại adapter.

## 18. Kiểm thử SDK trực tiếp

### 18.1. Unit test

Mock OCI SDK interface hoặc adapter interface để kiểm tra:

- Request được xây đúng.
- Response được map đúng.
- Error được chuyển thành application exception.
- Retry chỉ áp dụng với lỗi phù hợp.
- InputStream được đóng.
- Idempotency và unknown outcome được xử lý.

Không cần gọi OCI thật cho business logic thuần.

### 18.2. Context test

Kiểm tra Spring tạo được SDK client bean và đóng bean khi context dừng. Dùng test configuration cho provider/client khi không muốn truy cập OCI thật.

### 18.3. Integration test

Dùng test compartment và test identity riêng:

- Gọi một operation đọc resource.
- Gọi operation nâng cao mà starter không expose.
- Kiểm tra IAM positive/negative.
- Kiểm tra pagination.
- Kiểm tra retry/timeout có kiểm soát.
- Kiểm tra multipart upload và cleanup.
- Kiểm tra multi-region nếu use case cần.
- Xác minh Audit/request ID.

Không chạy integration test bằng tenancy production hoặc resource chứa dữ liệu thật.

### 18.4. Test client lifecycle

- Application context tạo client một lần.
- Nhiều request dùng cùng bean.
- Context shutdown gọi close.
- Không có thread/executor tồn tại sau shutdown ngoài dự kiến.
- Client của region A không bị dùng cho region B.

## 19. Bảo mật khi dùng SDK trực tiếp

Dùng SDK trực tiếp không làm thay đổi IAM requirement. Identity vẫn cần quyền cho operation cụ thể.

Nguyên tắc:

- Reuse workload identity đã cấu hình.
- Không hardcode API key/private key.
- Không log request signer hoặc token.
- Chỉ cấp quyền tối thiểu theo service operation.
- Giới hạn region/compartment.
- Không cho adapter có quyền quản trị tenancy nếu chỉ cần read object.
- Không tạo pre-authenticated request hoặc public endpoint nếu chưa có yêu cầu rõ.
- Giữ TLS validation bật.
- Quản lý proxy/trust store theo policy.
- Kiểm soát dữ liệu đưa vào log/trace.

Khi SDK direct thêm operation mới, IAM policy có thể phải bổ sung. Review policy cùng với code change; không giả định quyền của starter abstraction đã bao phủ mọi SDK operation.

## 20. Hiệu năng và chi phí

SDK trực tiếp có thể mở ra các tùy chọn hiệu năng nhưng cũng làm tăng trách nhiệm vận hành.

Đánh giá:

| Khu vực | Điều cần cân nhắc |
| --- | --- |
| Client reuse | Tránh tạo HTTP pool mới cho mỗi request |
| Connection timeout | Không chờ connect quá lâu |
| Read timeout | Phù hợp payload và latency |
| Pagination | Giới hạn số item xử lý và memory |
| Multipart | Chọn part size/concurrency theo bandwidth |
| Async | Có executor, backpressure và callback lifecycle |
| Retry | Không retry quá mức hoặc nhân bản side effect |
| Multi-region | Mỗi region có client/endpoint riêng |
| Logging | Không ghi payload lớn/secret |
| Cost | Request volume, transfer, storage và retry |

Không tối ưu trước khi đo. Ghi baseline latency, throughput, memory và error rate trước khi đổi HTTP client, concurrency hoặc retry.

## 21. Bài thực hành: dùng SDK để liệt kê object versions

**Bối cảnh:** Invoice Service dùng Spring Cloud OCI Storage starter để upload/download PDF. Một chức năng audit cần liệt kê các version của object trong bucket, nhưng abstraction Storage hiện tại không expose operation listObjectVersions theo nhu cầu.

### Phần A — Phân tích

1. Xác minh Storage starter đã được khai báo.
2. Kiểm tra Javadoc của Storage bean và xác định raw SDK client có thể truy cập.
3. Xác định request/response model của ListObjectVersions.
4. Xác định IAM permission cần cho operation.
5. Xác định pagination strategy.

### Phần B — Triển khai adapter

1. Inject Storage bean.
2. Lấy ObjectStorage SDK client từ bean.
3. Xây ListObjectVersionsRequest.
4. Đọc tất cả page.
5. Map SDK response thành StoredObjectVersion.
6. Ghi request ID cho mỗi operation.
7. Không đưa OCI model vào domain.

### Phần C — Mở rộng service SDK chưa có starter

1. Chọn một OCI service client khác chưa được starter expose.
2. Inject CredentialsProvider từ Spring Cloud OCI core.
3. Tạo client bằng SDK builder và region đã cấu hình.
4. Đặt client thành singleton Spring bean.
5. Cấu hình timeout.
6. Đóng client khi Spring context dừng.

### Phần D — Kiểm thử

1. Unit test adapter với mock SDK client.
2. Integration test trên bucket test có versioning.
3. Kiểm tra pagination qua nhiều trang.
4. Kiểm tra lỗi 403 và 404.
5. Kiểm tra timeout/unknown outcome.
6. Xác minh client được đóng khi shutdown.
7. Ghi lại dependency tree và OCI SDK version.

### Sản phẩm cần nộp

- Bảng so sánh starter abstraction và SDK operation.
- Dependency graph OCI SDK.
- Spring configuration tạo client.
- Adapter list object versions.
- Unit test và integration test.
- IAM policy cho workload.
- Bằng chứng pagination và request ID.
- Runbook xử lý 401/403, throttling và timeout.

## 22. Câu hỏi tự kiểm tra

1. Khi nào cần dùng OCI Java SDK trực tiếp?
2. Vì sao nên kiểm tra raw SDK client của starter trước khi tạo client mới?
3. CredentialsProvider trong Spring Cloud OCI có vai trò gì?
4. Vì sao client SDK nên là singleton bean?
5. Một service client có thể dùng đồng thời cho nhiều region không?
6. Pagination token được xử lý như thế nào?
7. Waiter giải quyết vấn đề gì?
8. Khi nào nên dùng multipart upload?
9. Vì sao cần abort/cleanup multipart upload chưa commit?
10. AsyncHandler và Future khác nhau thế nào khi response chứa InputStream?
11. Vì sao default retry của async client cần được kiểm tra riêng?
12. Vì sao retry PutObject có thể cần stream replayable?
13. BmcException cung cấp request ID ở đâu?
14. Vì sao không nên log toàn bộ request/response?
15. Vì sao SDK-specific types nên nằm sau adapter boundary?
16. Khi nào nên dùng raw signed request?
17. Cần kiểm thử gì trước khi triển khai SDK client trực tiếp?

## 23. Ghi nhớ

- Spring Cloud OCI starter cung cấp abstraction và auto-configuration; OCI Java SDK cung cấp service client/request/response đầy đủ hơn.
- Chỉ dùng SDK trực tiếp khi starter chưa expose operation hoặc option cần thiết.
- Ưu tiên raw SDK client đã được starter expose trước khi tạo client mới.
- Dùng CredentialsProvider của Spring Cloud OCI để tái sử dụng authentication đã cấu hình.
- Không tạo provider/client trong từng request; quản lý SDK client như Spring singleton bean.
- Mỗi service client gắn với một region/endpoint; dùng client riêng cho mỗi region cần truy cập.
- Dùng paginator, waiter và multipart upload thay vì tự viết lại cơ chế nếu SDK đã hỗ trợ.
- Đọc và đóng InputStream của GetObjectResponse; xử lý stream đúng lifecycle khi dùng async.
- Retry phải theo operation, request body replayability và idempotency; timeout không chứng minh operation chưa xảy ra.
- Ghi request ID, phân loại BmcException và không log secret/payload nhạy cảm.
- Đặt SDK sau adapter boundary, kiểm thử trong test compartment và cấp IAM least privilege.
- Kiểm tra dependency graph để giữ các OCI SDK module đồng bộ với starter release.

## Tài liệu tham khảo

- [Spring Cloud OCI 2.0.4 — Core starter and authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI 2.0.4 — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [Spring Cloud Oracle 2.0.0 Javadocs — API index](https://oracle.github.io/spring-cloud-oracle/2.0.0/javadocs/index-all.html)
- [OCI Java SDK — Concepts](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm)
- [OCI Java SDK — Getting started](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm)
- [OCI Java SDK — ObjectStorageClient Javadoc](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/ObjectStorageClient.html)
- [OCI Java SDK — Troubleshooting](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdktroubleshooting.htm)
- [OCI Object Storage — Multipart uploads](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingmultipartuploads.htm)
- [OCI Java SDK — GitHub repository](https://github.com/oracle/oci-java-sdk)
- [Maven Central — OCI Java SDK Object Storage module](https://central.sonatype.com/artifact/com.oracle.oci.sdk/oci-java-sdk-objectstorage)
