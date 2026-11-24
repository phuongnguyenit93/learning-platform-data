# Tích hợp OCI Object Storage với tài nguyên Spring

Oracle Cloud Infrastructure (OCI) Object Storage lưu file và dữ liệu phi cấu trúc dưới dạng object trong bucket. Với Spring Boot, có thể thao tác qua API của Spring Cloud Oracle hoặc dùng Spring Resource abstraction để đọc/ghi object như một resource quen thuộc. Cả hai cách đều dùng OCI authentication và IAM policy đã cấu hình cho ứng dụng.

Spring Cloud Oracle 2.0.4 cung cấp starter Object Storage, tự động tạo bean Storage và đăng ký cơ chế phân giải URI Object Storage thành Spring Resource. Từ phiên bản 2.0.1, resource này còn triển khai WritableResource, vì vậy ứng dụng có thể upload bằng OutputStream. Khi cần chức năng chuyên biệt như liệt kê object có phân trang, multipart upload hoặc tạo pre-authenticated request (PAR), có thể dùng OCI Java SDK client được cung cấp từ Storage bean.

Bài học dùng document-service làm ví dụ. Service lưu hợp đồng PDF vào bucket contracts-prod, tạo metadata, đọc file để trả về cho người dùng, cấp URL upload/download có thời hạn cho đối tác và quản lý object theo IAM policy. Mục tiêu là để ứng dụng chỉ truy cập đúng bucket/object được giao, xử lý stream mà không nạp file lớn toàn bộ vào heap và giữ được khả năng retry, audit, kiểm thử.

## 1. Mục tiêu học tập và kiến trúc

Sau bài học, bạn có thể:

1. Mô tả namespace, bucket, object, compartment và region trong OCI Object Storage.
2. Chọn giữa Spring Cloud Oracle Storage API, Spring Resource và OCI Java SDK.
3. Thêm starter Object Storage và cấu hình authentication/region/compartment trong Spring Boot.
4. Dùng Storage bean để upload, download, lưu POJO JSON và xóa object.
5. Dùng ResourceLoader để resolve OCI object URL thành Resource hoặc WritableResource.
6. Xây REST endpoint stream file mà không tải toàn bộ object vào memory.
7. Dùng OCI SDK để liệt kê object, xử lý pagination và metadata.
8. Upload file lớn bằng UploadManager và multipart upload.
9. Tạo, phân phối và thu hồi pre-authenticated request theo quyền tối thiểu.
10. Cấu hình IAM policy cho workload và bucket.
11. Xử lý ETag, conditional write, versioning, retry, timeout và lỗi authorization.
12. Viết unit test và integration test cho luồng upload/download, quyền và URL chia sẻ.

~~~mermaid
flowchart TD
    A["Browser / API client"] --> B["Spring Boot document-service"]
    B --> C["Authentication provider"]
    C --> D["OCI IAM principal"]
    D --> E["IAM policy"]
    B --> F["Storage bean"]
    B --> G["Spring Resource / WritableResource"]
    F --> H["OCI Java SDK ObjectStorageClient"]
    G --> H
    H --> I["OCI Object Storage endpoint"]
    I --> J["Bucket contracts-prod"]
    J --> K["Objects: tenant/document/version"]
    B --> L["Audit + metadata database"]
~~~

Spring abstraction không thay thế OCI IAM. Resource URL giúp định vị object; identity provider ký request; IAM policy mới quyết định ứng dụng có được đọc/ghi object hay không.

## 2. Mô hình OCI Object Storage

### 2.1. Namespace, bucket và object

Object Storage có ba khái niệm chính:

- **Namespace:** vùng tên cấp tenancy, là top-level container cho bucket và object. OCI cấp một namespace duy nhất cho tenancy và không cho đổi tên.
- **Bucket:** container logic nằm trong một region và một compartment. Bucket chứa object, có policy, encryption, versioning, lifecycle và retention configuration.
- **Object:** nội dung dữ liệu cùng metadata. Object được định danh bằng bucket và object name.

Namespace giống nhau khi truy cập các region khác nhau trong cùng tenancy; endpoint và bucket resource vẫn gắn với region. Tên bucket phải duy nhất trong phạm vi namespace/region tương ứng. Bucket thuộc một compartment duy nhất.

Lấy namespace bằng OCI Console, CLI hoặc API GetNamespace. Spring Cloud Oracle Storage bean có phương thức getNamespaceName() để lấy namespace của tenancy hiện tại. Namespace không phải compartment OCID và cũng không phải tên bucket.

### 2.2. Object name và thư mục giả lập

Object Storage không có thư mục vật lý như filesystem. Object name là chuỗi khóa; dấu gạch chéo thường được dùng để mô phỏng prefix/hierarchy:

~~~text
contracts/
  tenant-001/
    2026/
      contract-1001.pdf
      contract-1002.pdf
  tenant-002/
    2026/
      contract-2001.pdf
~~~

Các tên trên thực chất là object key như contracts/tenant-001/2026/contract-1001.pdf. Prefix và delimiter giúp list theo nhóm, nhưng không tạo folder resource riêng.

Quy tắc đặt object key:

- Sinh key phía server, không tin đường dẫn tùy ý từ client.
- Dùng tenant ID đã xác thực, document ID hoặc UUID làm thành phần key.
- Tránh tên chứa dữ liệu cá nhân, số thẻ, email hoặc bí mật.
- Chuẩn hóa Unicode và ký tự phân cách theo quy ước của ứng dụng.
- Giới hạn độ dài và ký tự để URL/SDK xử lý nhất quán.
- Không nối trực tiếp tên file do người dùng cung cấp vào object key mà không kiểm tra.
- Dùng prefix riêng cho quarantine, temporary, processed và archive nếu nghiệp vụ cần.

### 2.3. Region và endpoint

Object Storage là regional service. Endpoint có dạng:

~~~text
https://objectstorage.<region>.oraclecloud.com
~~~

Ví dụ region identifier:

~~~text
ap-singapore-1
ap-tokyo-1
us-ashburn-1
eu-frankfurt-1
~~~

Region của bucket phải khớp region endpoint mà SDK client sử dụng. Khi client gửi request tới sai region, có thể gặp redirect, lỗi resource không tồn tại hoặc lỗi authorization khó hiểu.

Spring Cloud Oracle dùng spring.cloud.oci.region.static để đặt region cho API calls. Giá trị này ưu tiên hơn region trong OCI auth configuration file hoặc spring.cloud.oci.config.region.

### 2.4. Bucket và compartment

Bucket được tạo trong một compartment. IAM policy trên compartment quyết định workload nào có thể tạo bucket, đọc object, ghi object, liệt kê hoặc xóa dữ liệu.

Thiết kế thường gặp:

~~~text
Tenancy
└── Production
    ├── AppRuntime
    │   └── document-service
    ├── AppData
    │   └── contracts-prod
    └── Security
        └── audit and key resources
~~~

Runtime workload nằm trong AppRuntime; bucket nằm trong AppData. Dynamic group hoặc OKE workload identity được cấp quyền trên AppData. Việc service chạy trong AppRuntime không tự động cho nó quyền truy cập AppData.

### 2.5. Strong consistency

OCI Object Storage cung cấp strong consistency: sau khi một thao tác ghi thành công, request đọc tiếp theo trả về bản dữ liệu mới nhất. Điều này giúp luồng upload rồi download có thể kiểm chứng ngay.

Strong consistency không có nghĩa ứng dụng không cần xử lý concurrency. Hai request PUT đồng thời vẫn có thể ghi đè cùng object key nếu không dùng conditional request hoặc key riêng.

### 2.6. Object Storage và filesystem

| Đặc điểm | Filesystem | OCI Object Storage |
| --- | --- | --- |
| Định danh | Path | Bucket + object name |
| Folder | Directory resource | Prefix trong object name |
| Đọc/ghi | File handle | HTTP API/SDK stream |
| Rename | Thường là thao tác filesystem | Thường phải copy rồi delete hoặc dùng API rename theo khả năng |
| Lock | File lock | ETag, conditional request hoặc cơ chế nghiệp vụ |
| Metadata | File attributes | HTTP metadata và opc-meta |
| Location | Disk/mount | Bucket region |
| Access | OS permission | OCI IAM policy và credential |

Không gọi getFile() trên Resource từ Object Storage để mong có một file local. Dùng getInputStream() hoặc WritableResource.getOutputStream().

## 3. Chọn API phù hợp trong Spring

### 3.1. Spring Cloud Oracle Storage API

Storage API cung cấp các thao tác ở mức ứng dụng:

- createBucket(bucketName) hoặc createBucket(bucketName, compartmentId).
- upload(bucketName, key, inputStream, metadata).
- download(bucketName, key).
- download(bucketName, key, version).
- store(bucketName, key, object) để lưu POJO dưới dạng JSON.
- read(bucketName, key, clazz) để đọc JSON thành POJO.
- deleteObject(bucketName, key).
- deleteBucket(bucketName).
- getNamespaceName() và getClient().

Starter tự động đăng ký bean Storage trong Spring context. Đây là lựa chọn mặc định cho luồng upload/download phổ biến và thao tác file trong service.

### 3.2. Spring Resource abstraction

Spring Resource là abstraction thống nhất cho các nguồn như classpath, filesystem, URL và servlet context. Spring Cloud Oracle bổ sung protocol resolver để nhận diện URL Object Storage và tạo OracleStorageResource.

Resource phù hợp khi code cần một InputStreamSource/Resource để đọc object. Từ Spring Cloud Oracle 2.0.1, Object Storage Resource cũng triển khai WritableResource để ghi object.

Ưu điểm:

- Tái sử dụng API Spring quen thuộc.
- Dễ inject hoặc resolve theo URI.
- Có thể truyền Resource vào service khác đang làm việc với file/resource.
- Có thể dùng OutputStream để upload.

Giới hạn:

- Resource không phải filesystem file.
- Không thay thế API list bucket/object, quản lý PAR, multipart upload hoặc version management.
- Các thao tác quản trị object vẫn nên dùng Storage API hoặc OCI SDK.

### 3.3. OCI Java SDK trực tiếp

Storage bean có getClient() trả về OCI ObjectStorageClient. Dùng client này khi cần API chưa được bao phủ ở Storage abstraction:

- ListObjects và pagination.
- Create/DeletePreauthenticatedRequest.
- UploadManager/multipart.
- GetObject/HeadObject nâng cao.
- Versioning, retention, lifecycle, replication.
- Conditional request hoặc API operation chuyên biệt.

Không tạo ObjectStorageClient mới cho từng HTTP request. Dùng client đã được Spring starter cấu hình và quản lý vòng đời.

### 3.4. Bảng chọn nhanh

| Nhu cầu | API nên dùng |
| --- | --- |
| Upload file thông thường | Storage.upload |
| Download file thông thường | Storage.download hoặc Resource |
| Lưu POJO JSON | Storage.store / Storage.read |
| Dùng object như Spring dependency | ResourceLoader + Resource |
| Ghi qua OutputStream | WritableResource |
| Liệt kê object theo prefix | OCI SDK ListObjects |
| Upload file lớn | OCI SDK UploadManager |
| Tạo URL chia sẻ có thời hạn | OCI SDK Pre-Authenticated Request |
| Xóa object | Storage.deleteObject |
| Download object version cũ | Storage.download(bucket, key, version) |

## 4. Thêm dependency và cấu hình Spring Boot

### 4.1. Maven dependency

Spring Cloud Oracle 2.0.4 cung cấp starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
    <version>2.0.4</version>
</dependency>
~~~

Starter bao gồm module storage và các dependency cần thiết. Không thêm module nền tảng riêng nếu starter đã cung cấp transitive dependency.

Spring Cloud Oracle 2.0.4 đã nâng Spring Cloud OCI lên Spring Boot 4.1.1 và Spring Framework 7. Trước khi thêm starter vào dự án đang dùng Spring Boot khác, đối chiếu compatibility matrix/release notes và quản lý version nhất quán; không ép dependency Spring Framework hoặc OCI SDK khác version tùy tiện.

### 4.2. Gradle dependency

~~~kotlin
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter-storage:2.0.4")
}
~~~

### 4.3. Cấu hình local development

Khi phát triển trên máy cá nhân, dùng OCI config file profile:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: C:/Users/developer/.oci/config
      region:
        static: ap-singapore-1
      compartment:
        static: REPLACE_WITH_COMPARTMENT_OCID
      storage:
        enabled: true
~~~

OCI config file chứa user OCID, tenancy OCID, fingerprint, private key path và region. Bảo vệ private key bằng file permission/passphrase. Không commit file config hoặc PEM vào Git, không copy credential production vào laptop.

### 4.4. Cấu hình production trên Compute

Khi Spring Boot chạy trên OCI Compute, ưu tiên Instance Principal:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      compartment:
        static: REPLACE_WITH_APPDATA_COMPARTMENT_OCID
      storage:
        enabled: true
~~~

Compute instance phải thuộc dynamic group và dynamic group phải được cấp IAM policy trên compartment chứa bucket. Nếu principal không có quyền, thay API key profile không giải quyết đúng nguyên nhân; cần kiểm tra dynamic group, region, bucket và policy.

### 4.5. Cấu hình OKE workload identity

Với OKE enhanced cluster, có thể dùng Workload Identity:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: WORKLOAD_IDENTITY
      region:
        static: ap-singapore-1
      compartment:
        static: REPLACE_WITH_APPDATA_COMPARTMENT_OCID
      storage:
        enabled: true
~~~

Policy phải ràng buộc cluster OCID, namespace và Kubernetes service account. Không dùng API key của node hoặc một identity có quyền cho toàn bộ pod trong cluster nếu workload identity đã đáp ứng use case.

### 4.6. Các auth type được hỗ trợ

Spring Cloud Oracle 2.0.4 hỗ trợ:

| Config type | Trường hợp dùng |
| --- | --- |
| FILE | OCI config file profile, thường dùng local development |
| SIMPLE | Cấu hình user OCID, tenancy OCID, fingerprint và private key qua property |
| INSTANCE_PRINCIPAL | OCI Compute |
| RESOURCE_PRINCIPAL | OCI Functions/resource hỗ trợ resource principal |
| SESSION_TOKEN | Phiên CLI/SDK ngắn hạn |
| WORKLOAD_IDENTITY | OKE workload identity |

Tránh SIMPLE cho production nếu có workload identity. Nếu buộc dùng private key, lấy từ secret manager, giới hạn quyền đọc và lập lịch rotation.

### 4.7. Region và compartment mặc định

Các property quan trọng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.oci.config.type | Kiểu authentication |
| spring.cloud.oci.config.profile | Profile trong OCI config file |
| spring.cloud.oci.config.file | Đường dẫn config file |
| spring.cloud.oci.config.region | Region cho auth configuration |
| spring.cloud.oci.region.static | Region cho API call; ưu tiên hơn config file |
| spring.cloud.oci.compartment.static | Compartment OCID mặc định |
| spring.cloud.oci.storage.enabled | Bật/tắt module storage, mặc định true |

Compartment mặc định không có nghĩa mọi thao tác luôn được phép ở compartment đó. IAM policy vẫn quyết định quyền. Khi tạo bucket trong compartment khác, dùng overload có compartment OCID hoặc cấu hình phù hợp.

## 5. Cấu trúc Spring service và Storage bean

### 5.1. Inject Storage

~~~java
import com.oracle.cloud.spring.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class ContractStorageService {

    private final Storage storage;

    public ContractStorageService(Storage storage) {
        this.storage = storage;
    }
}
~~~

Không tự khởi tạo StorageImpl hoặc ObjectStorageClient trong controller. Starter auto-configures Storage bean và dùng OCI authentication provider đã cấu hình.

### 5.2. Lấy namespace

~~~java
public String namespace() {
    return storage.getNamespaceName();
}
~~~

Namespace được cấp ở cấp tenancy và không phải secret. Có thể lấy một lần lúc khởi tạo service hoặc gọi qua bean khi cần. Không hard-code namespace từ một tenancy khác vào production config.

### 5.3. Provision bucket

Bucket thường được tạo bằng IaC hoặc quy trình platform provisioning. Nếu ứng dụng có trách nhiệm tạo bucket trong một số môi trường:

~~~java
import com.oracle.bmc.objectstorage.responses.CreateBucketResponse;

public CreateBucketResponse createBucket(
        String bucketName,
        String compartmentOcid) {

    return storage.createBucket(bucketName, compartmentOcid);
}
~~~

Tạo bucket cần BUCKET_CREATE. Không chạy thao tác này mỗi request hoặc mỗi lần app restart. Nếu bucket đã tồn tại, xử lý conflict bằng cách kiểm tra bucket hiện tại và cấu hình mong đợi.

### 5.4. Tách bucket name và object key khỏi request

Controller nhận document ID hoặc business ID; service tra metadata và xác định bucket/key từ dữ liệu đã xác thực. Không cho client tự gửi bucket name tùy ý hoặc đọc object ở tenant khác.

Một object key có thể được sinh như sau:

~~~java
String objectKey(UUID tenantId, UUID documentId) {
    return "contracts/" + tenantId + "/" + documentId + ".pdf";
}
~~~

Đây là quy ước ví dụ. Tenant ID phải lấy từ security/business context đã xác minh. Nếu object key có version hoặc loại tài liệu, lưu mapping trong database thay vì suy luận từ tên file do client cung cấp.

## 6. Upload object với Storage API

### 6.1. Upload từ InputStream

~~~java
import com.oracle.cloud.spring.storage.StorageObjectMetadata;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class ContractUploader {

    private final Storage storage;

    public ContractUploader(Storage storage) {
        this.storage = storage;
    }

    public void uploadPdf(
            String bucketName,
            String objectKey,
            Path sourceFile) throws IOException {

        StorageObjectMetadata metadata =
                StorageObjectMetadata.builder()
                        .contentType("application/pdf")
                        .contentLength(Files.size(sourceFile))
                        .contentDisposition("attachment")
                        .cacheControl("private, no-store")
                        .metadata("document-type", "contract")
                        .build();

        try (InputStream input = Files.newInputStream(sourceFile)) {
            storage.upload(bucketName, objectKey, input, metadata);
        }
    }
}
~~~

Storage.upload đọc InputStream trong lời gọi đồng bộ. Đóng stream sau khi upload hoàn tất. Không dùng readAllBytes cho file lớn vì toàn bộ file sẽ được giữ trong heap.

Content-Type giúp client xử lý file đúng. Content-Disposition có thể yêu cầu tải xuống thay vì hiển thị inline. Cache-Control phù hợp với dữ liệu riêng tư giúp giảm nguy cơ cache ở intermediary/browser. Metadata tùy chỉnh chỉ nên chứa thông tin không nhạy cảm.

### 6.2. Upload từ MultipartFile

Trong Spring MVC, MultipartFile cung cấp InputStream:

~~~java
import java.io.InputStream;
import java.io.IOException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.multipart.MultipartFile;

@PostMapping(
        value = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Void> upload(
        @RequestPart("file") MultipartFile file,
        @AuthenticationPrincipal Jwt jwt) throws IOException {

    try (InputStream input = file.getInputStream()) {
        documentService.store(
                jwt.getSubject(),
                file.getOriginalFilename(),
                file.getContentType(),
                file.getSize(),
                input);
    }

    return ResponseEntity.accepted().build();
}
~~~

Ví dụ controller cần giới hạn kích thước ở Spring multipart configuration và reverse proxy. Trong service, kiểm tra tenant, loại file, kích thước, checksum và nội dung file trước khi lưu vào bucket chính thức.

Không tin Content-Type hoặc file extension từ client. Dùng content inspection/malware scanning nếu nghiệp vụ cần. File chưa được kiểm tra có thể upload vào quarantine bucket/prefix với quyền truy cập riêng.

### 6.3. Conditional upload để tránh ghi đè

Khi chỉ muốn tạo object mới:

~~~java
StorageObjectMetadata metadata =
        StorageObjectMetadata.builder()
                .contentType("application/pdf")
                .contentLength(fileSize)
                .ifNoneMatch("*")
                .build();
~~~

If-None-Match với dấu * yêu cầu thao tác chỉ thành công nếu object chưa tồn tại. Nếu object đã có, request bị từ chối thay vì ghi đè.

Khi cập nhật object theo ETag đã đọc trước đó, dùng If-Match để tránh ghi đè thay đổi của request khác. ETag dùng cho concurrency control; không coi ETag là SHA-256 của payload trong mọi trường hợp, đặc biệt với multipart upload.

### 6.4. Custom metadata

StorageObjectMetadata hỗ trợ:

- contentType.
- contentLength.
- contentDisposition.
- contentEncoding.
- contentLanguage.
- cacheControl.
- contentMD5.
- ifMatch và ifNoneMatch.
- custom metadata key/value.
- storageTier.
- opcSseKmsKeyId và các trường mã hóa phù hợp.

Không lưu PII, access token, secret hoặc nội dung hợp đồng trong custom metadata. Metadata thường xuất hiện trong API response/log/audit và có thể bị lộ rộng hơn nội dung object.

## 7. Download object với Storage API

### 7.1. Download thành Resource

Storage.download trả về OracleStorageResource, có thể dùng qua Spring Resource:

~~~java
import org.springframework.core.io.Resource;

public Resource download(
        String bucketName,
        String objectKey) {

    return storage.download(bucketName, objectKey);
}
~~~

Đọc nội dung qua InputStream:

~~~java
try (InputStream input = storage.download(bucket, key).getInputStream()) {
    input.transferTo(output);
}
~~~

Đóng InputStream sau khi sử dụng. Không giữ stream mở trong thời gian dài nếu không cần thiết.

### 7.2. Xóa object và download version cụ thể

~~~java
public void delete(String bucketName, String objectKey) {
    storage.deleteObject(bucketName, objectKey);
}

public Resource downloadVersion(
        String bucketName,
        String objectKey,
        String versionId) {
    return storage.download(bucketName, objectKey, versionId);
}
~~~

DeleteObject cần OBJECT_DELETE. Nếu bucket bật versioning, kiểm tra semantics delete marker và object versions trước khi xem thao tác xóa là xóa vĩnh viễn. Không expose delete endpoint nếu user chỉ cần xóa logical record.

### 7.3. Trả file bằng StreamingResponseBody

~~~java
import java.io.InputStream;
import java.util.UUID;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@GetMapping("/documents/{documentId}/content")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID documentId) {

    DocumentLocation location =
            documentService.authorizedLocation(documentId);

    Resource resource = storage.download(
            location.bucketName(),
            location.objectKey());

    StreamingResponseBody body = output -> {
        try (InputStream input = resource.getInputStream()) {
            input.transferTo(output);
        }
    };

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_PDF)
            .header(
                    HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                            .filename(location.safeDownloadName())
                            .build()
                            .toString())
            .body(body);
}
~~~

DocumentLocation phải được tạo sau khi kiểm tra quyền đọc tài liệu và tenant ownership. Không lấy bucket/key trực tiếp từ path/query của client. Dùng filename đã sanitize, tránh CRLF/header injection.

Streaming giúp tránh nạp toàn bộ file vào heap. Cần cấu hình giới hạn số request đồng thời, timeout và thread/executor phù hợp. Khi client ngắt kết nối, đóng stream và không tiếp tục truyền dữ liệu không cần thiết.

### 7.4. Đọc JSON thành POJO

Storage API có thể lưu và đọc Java object dưới dạng JSON:

~~~java
public void saveMetadata(
        String bucketName,
        String objectKey,
        DocumentMetadata metadata) throws IOException {

    storage.store(bucketName, objectKey, metadata);
}

public DocumentMetadata loadMetadata(
        String bucketName,
        String objectKey) {

    return storage.read(
            bucketName,
            objectKey,
            DocumentMetadata.class);
}
~~~

Dùng chức năng này cho JSON metadata hoặc document manifest nhỏ. Không dùng để lưu file binary lớn hoặc thay database cho dữ liệu có quan hệ, transaction và truy vấn phức tạp.

## 8. Spring Resource và WritableResource

### 8.1. URI của Object Storage

Spring Cloud Oracle nhận diện object URL theo cấu trúc:

~~~text
https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<object-name>
~~~

Ví dụ:

~~~text
https://objectstorage.ap-singapore-1.oraclecloud.com/n/exampleNamespace/b/contracts-prod/o/contracts/tenant-001/contract-1001.pdf
~~~

URL trên là địa chỉ định vị object. Khi được resolve bởi Spring Cloud Oracle Object Storage protocol resolver, Resource dùng OCI SDK và authentication provider của ứng dụng. URL này không tự trở thành public URL hoặc pre-authenticated URL.

### 8.2. Resolve Resource qua ResourceLoader

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriUtils;

@Component
public class OciResourceResolver {

    private final ResourceLoader resourceLoader;

    public OciResourceResolver(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource resolve(
            String region,
            String namespace,
            String bucket,
            String objectName) {

        String encodedObject =
                UriUtils.encodePath(objectName, StandardCharsets.UTF_8);

        String uri = "https://objectstorage." + region
                + ".oraclecloud.com/n/" + namespace
                + "/b/" + bucket + "/o/" + encodedObject;

        return resourceLoader.getResource(uri);
    }
}
~~~

UriUtils.encodePath mã hóa ký tự cần thiết trong object name nhưng giữ dấu slash dùng để biểu diễn prefix. Không nối chuỗi URL từ input chưa xác thực và không encode hai lần. Với object key có ký tự đặc biệt, kiểm thử URI trên đúng phiên bản Spring Cloud Oracle.

### 8.3. Đọc Resource

~~~java
Resource resource = resolver.resolve(
        region, namespace, bucket, objectKey);

if (!resource.exists() || !resource.isReadable()) {
    throw new DocumentNotFoundException();
}

try (InputStream input = resource.getInputStream()) {
    input.transferTo(outputStream);
}
~~~

exists() hoặc contentLength() có thể tạo request tới Object Storage. Tránh gọi lặp nhiều lần trong cùng request nếu không cần. Với remote Resource, isFile() thường không phải true và getFile() không phải cách lấy nội dung.

### 8.4. Ghi bằng WritableResource

~~~java
import java.io.OutputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.WritableResource;

Resource resource = resolver.resolve(
        region, namespace, bucket, objectKey);

if (!(resource instanceof WritableResource writable)) {
    throw new IllegalStateException(
            "OCI resource does not support writing");
}

try (OutputStream output = writable.getOutputStream()) {
    inputStream.transferTo(output);
}
~~~

Object Storage Resource của Spring Cloud Oracle 2.0.4 triển khai WritableResource. Dữ liệu được upload khi OutputStream đóng. Vì vậy try-with-resources không chỉ giải phóng stream mà còn kết thúc thao tác ghi.

Không trả WritableResource ra API công khai để client tự chọn bucket/key. Server cần quyết định object target sau khi xác thực và kiểm tra quyền.

### 8.5. URI resolver phải được starter đăng ký

Nếu spring-cloud-oci-starter-storage không nằm trên classpath hoặc auto-configuration bị tắt, Spring ResourceLoader có thể resolve HTTPS URL thành UrlResource thông thường. Khi đó request không đi qua OCI SDK authentication và có thể nhận 401/403 hoặc cố truy cập URL public.

Kiểm tra:

- Starter storage được khai báo.
- spring.cloud.oci.storage.enabled không bị đặt false.
- Auto-configuration được nạp.
- URI dùng đúng Object Storage host/path.
- Authentication provider hoạt động.
- IAM policy cấp quyền trên bucket/object.

### 8.6. Khi nào chọn Resource thay vì Storage API?

Dùng Resource khi service hoặc thư viện downstream đã nhận Resource/InputStreamSource/WritableResource. Dùng Storage API khi cần thao tác bucket, upload metadata, download version, delete hoặc lưu POJO. Dùng OCI SDK trực tiếp khi cần pagination, PAR, multipart hoặc operation chưa có trong Storage interface.

## 9. Liệt kê object và pagination bằng OCI SDK

### 9.1. Vì sao cần SDK trực tiếp?

Storage interface tập trung vào upload/download/store/read và bucket lifecycle. Để list object theo prefix, delimiter, fields và pagination, dùng ObjectStorageClient:

~~~java
import com.oracle.bmc.objectstorage.requests.ListObjectsRequest;
import com.oracle.cloud.spring.storage.Storage;

var client = storage.getClient();
String namespace = storage.getNamespaceName();

var response = client.listObjects(
        ListObjectsRequest.builder()
                .namespaceName(namespace)
                .bucketName(bucketName)
                .prefix("contracts/tenant-001/")
                .limit(1000)
                .build());

var objects = response.getListObjects().getObjects();
~~~

ListObjects trả tối đa 1.000 object mỗi response. Mặc định chỉ trả tên object; nếu cần size, ETag, timeCreated, timeModified hoặc storageTier, chỉ định fields theo API reference.

### 9.2. Xử lý trang tiếp theo

~~~java
String start = null;

do {
    var requestBuilder = ListObjectsRequest.builder()
            .namespaceName(namespace)
            .bucketName(bucketName)
            .prefix(prefix)
            .limit(1000);

    if (start != null) {
        requestBuilder.start(start);
    }

    var page = client.listObjects(requestBuilder.build())
            .getListObjects();

    page.getObjects().forEach(object -> {
        processSummary(object.getName(), object.getSize(), object.getEtag());
    });

    start = page.getNextStartWith();
} while (start != null);
~~~

Dùng nextStartWith từ response làm start cho request tiếp theo. Không tự tăng offset theo số object vì API dùng marker theo object name. Nếu danh sách lớn, xử lý từng trang thay vì gom toàn bộ tên object vào heap.

### 9.3. Prefix và delimiter

Prefix lọc object key bắt đầu bằng chuỗi chỉ định. Delimiter / có thể gom các phần còn lại thành common prefixes để mô phỏng folder. Không có nghĩa OCI tạo thư mục vật lý.

Dùng prefix có scope tenant hoặc document type để tránh list toàn bucket. IAM policy có thể giới hạn target.object.name theo pattern khi cần.

## 10. Metadata, ETag và versioning

### 10.1. System metadata và custom metadata

System metadata gồm Content-Type, Content-Length, ETag, Last-Modified, Cache-Control, Content-Disposition và thông tin lưu trữ. Custom metadata được gửi bằng key/value và có prefix opc-meta trong request header.

Metadata có thể dùng để:

- Ghi loại tài liệu hoặc mã nghiệp vụ không nhạy cảm.
- Đặt Content-Disposition cho download.
- Đặt Cache-Control phù hợp.
- Gắn correlation/reference ID.
- Lưu checksum do ứng dụng tính nếu có yêu cầu.

Metadata không nên thay database. Không dùng custom metadata làm nguồn chính cho trạng thái nghiệp vụ, ownership hoặc authorization.

### 10.2. ETag và conditional request

ETag đại diện phiên bản nội dung theo semantics của service. Có thể dùng If-Match để chỉ cập nhật nếu object vẫn có ETag như lần đọc trước, hoặc If-None-Match với * để chỉ tạo object khi chưa tồn tại.

Ví dụ tạo mới không ghi đè:

~~~java
StorageObjectMetadata metadata =
        StorageObjectMetadata.builder()
                .contentType("application/pdf")
                .ifNoneMatch("*")
                .build();

storage.upload(bucketName, objectKey, inputStream, metadata);
~~~

Nếu hai request cùng tạo một key, một request có thể thành công và request còn lại nhận precondition/conflict failure. Ứng dụng cần trả lỗi nghiệp vụ rõ ràng hoặc sinh object key khác.

### 10.3. Object versioning

Bucket có thể bật versioning để giữ các phiên bản object khi overwrite/delete. Storage API hỗ trợ:

~~~java
Resource olderVersion =
        storage.download(bucketName, objectKey, versionId);
~~~

Versioning giúp phục hồi thay đổi ngoài ý muốn nhưng làm tăng số object/version và chi phí lưu trữ. Kết hợp lifecycle/retention policy để quản lý noncurrent version. Không giả định xóa object key sẽ xóa vĩnh viễn mọi version nếu bucket versioning đang bật.

### 10.4. Strong consistency và concurrency

Strong consistency bảo đảm đọc thấy bản ghi mới nhất sau khi write thành công. ETag/conditional request vẫn cần thiết khi nhiều writer cập nhật cùng object. Với dữ liệu cần transaction nhiều object, nên lưu trạng thái nghiệp vụ trong database và dùng object storage cho blob; Object Storage không cung cấp transaction ACID nhiều object.

## 11. Upload file lớn và multipart upload

### 11.1. Khi nào dùng multipart?

OCI khuyến nghị multipart upload cho object lớn hơn 100 MiB. Multipart chia file thành parts, upload từng phần, sau đó commit thành một object.

Các giới hạn chính:

- Một object tối đa 10 TiB.
- Một part tối đa 50 GiB.
- Part number từ 1 đến 10.000.
- Các part có thể upload song song hoặc theo thứ tự bất kỳ.
- Khi commit, Object Storage ghép theo part number.
- Nếu một part lỗi, có thể upload lại part đó thay vì gửi lại toàn bộ file.

### 11.2. Dùng UploadManager

OCI Java SDK có UploadManager tự chọn PutObject hay multipart dựa trên UploadConfiguration. Nó có thể chia file thành parts, upload song song và retry từng part.

UploadConfiguration mặc định cho phép multipart và parallel upload; ngưỡng mặc định để chuyển sang multipart là 128 MiB, kích thước part mặc định 128 MiB và giới hạn 10.000 parts. Có thể điều chỉnh ngưỡng/part size theo băng thông, memory, số upload đồng thời và timeout, nhưng không nên tăng đồng loạt nếu chưa đo tải.

~~~java
import com.oracle.bmc.objectstorage.model.PutObjectRequest;
import com.oracle.bmc.objectstorage.transfer.UploadConfiguration;
import com.oracle.bmc.objectstorage.transfer.UploadManager;
import java.io.File;

File file = new File("/data/contracts/large-contract.pdf");

PutObjectRequest putRequest = PutObjectRequest.builder()
        .namespaceName(storage.getNamespaceName())
        .bucketName(bucketName)
        .objectName(objectKey)
        .contentType("application/pdf")
        .build();

UploadConfiguration configuration =
        UploadConfiguration.builder()
                .allowMultipartUploads(true)
                .allowParallelUploads(true)
                .build();

UploadManager uploadManager =
        new UploadManager(storage.getClient(), configuration);

UploadManager.UploadRequest uploadRequest =
        UploadManager.UploadRequest.builder(file)
                .allowOverwrite(false)
                .build(putRequest);

UploadManager.UploadResponse response =
        uploadManager.upload(uploadRequest);
~~~

UploadRequest.builder(file) lấy kích thước từ File và có thể đọc lại file cho multipart/parallel processing. Nếu dùng InputStream, phải cung cấp content length; để upload song song hiệu quả, nguồn stream cần hỗ trợ đọc lại/duplicate theo hướng dẫn SDK.

allowOverwrite(false) yêu cầu không ghi đè object đã tồn tại bằng If-None-Match. Nếu cần thay thế có chủ đích, bật overwrite và kiểm soát concurrency bằng ETag/version hoặc object key mới.

### 11.3. Multipart và IAM permissions

Multipart cần nhiều quyền hơn một PUT đơn giản. OCI yêu cầu OBJECT_CREATE và OBJECT_OVERWRITE cho CreateMultipartUpload/UploadPart; CommitMultipartUpload còn có thể cần BUCKET_READ, OBJECT_CREATE, OBJECT_READ và OBJECT_OVERWRITE theo permission mapping.

Policy chỉ cấp OBJECT_CREATE có thể làm upload nhỏ thành công nhưng multipart thất bại. Kiểm tra permission matrix và thử file vượt ngưỡng multipart trong môi trường test.

### 11.4. Dọn upload dở dang

Nếu process chết hoặc upload bị hủy, multipart có thể còn upload chưa commit. UploadManager mặc định cố gắng abort multipart khi thất bại. Nếu tự quản lý raw multipart API, cần có quy trình AbortMultipartUpload và lifecycle cleanup/monitoring phù hợp.

Không để upload dở dang tồn tại vô thời hạn vì parts đã upload có thể phát sinh storage cost.

### 11.5. Giới hạn tài nguyên phía Spring Boot

- Giới hạn multipart request size ở reverse proxy và Spring.
- Không giữ file lớn trong byte[].
- Dùng temporary disk/quarantine storage khi cần scan.
- Giới hạn upload đồng thời và executor parallel parts.
- Đặt timeout hợp lý nhưng đủ cho mạng chậm.
- Kiểm tra checksum trước/sau upload nếu yêu cầu integrity.
- Dùng unique object key để tránh hai upload ghi cùng object.
- Không cho client tự điều khiển part size hoặc thread count không giới hạn.

## 12. Pre-Authenticated Request (PAR)

### 12.1. PAR dùng để làm gì?

PAR tạo URL có quyền truy cập đã được cấp trước, cho phép người nhận đọc/ghi bucket hoặc object mà không cần OCI sign-in credentials. Đây là bearer URL: bất kỳ ai có URL đều có thể dùng đúng quyền và phạm vi được cấp.

Use case:

- Đối tác tải một hợp đồng.
- Browser upload một file trực tiếp vào object cụ thể.
- Người dùng nhận báo cáo mà không cần OCI account.

Không dùng PAR cho mọi truy cập nội bộ của service. Workload-to-workload nên dùng IAM principal và SDK authentication.

### 12.2. Giới hạn phạm vi PAR

Có thể tạo PAR cho:

- Một object cụ thể.
- Object có prefix.
- Tất cả object trong bucket.

Access type có thể là read, write hoặc read/write. Listing object bị từ chối mặc định; chỉ bật khi use case cần. PAR không cho phép người nhận xóa bucket hoặc object.

Expiration là bắt buộc nhưng OCI không đặt giới hạn tối đa chung cho thời gian hết hạn. Vì vậy ứng dụng nên tự áp dụng TTL ngắn theo use case và quản lý ngày hết hạn.

### 12.3. Tạo PAR bằng OCI SDK

Storage bean cho phép lấy ObjectStorageClient qua getClient(). Ví dụ tạo PAR chỉ đọc một object:

~~~java
import com.oracle.bmc.objectstorage.model.CreatePreauthenticatedRequestDetails;
import com.oracle.bmc.objectstorage.requests.CreatePreauthenticatedRequestRequest;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

public String createDownloadPar(
        String bucketName,
        String objectName,
        String region) {

    var details = CreatePreauthenticatedRequestDetails.builder()
            .name("document-download")
            .objectName(objectName)
            .accessType(
                    CreatePreauthenticatedRequestDetails.AccessType.ObjectRead)
            .timeExpires(Date.from(
                    Instant.now().plus(Duration.ofMinutes(15))))
            .build();

    var request = CreatePreauthenticatedRequestRequest.builder()
            .namespaceName(storage.getNamespaceName())
            .bucketName(bucketName)
            .createPreauthenticatedRequestDetails(details)
            .build();

    var par = storage.getClient()
            .createPreauthenticatedRequest(request)
            .getPreauthenticatedRequest();

    return "https://objectstorage." + region
            + ".oraclecloud.com" + par.getAccessUri();
}
~~~

Ví dụ minh họa cho download. Với upload, dùng access type ObjectWrite và cấp đúng permission. Tên PAR không nên chứa dữ liệu bí mật. Access URI chỉ xuất hiện khi tạo; OCI không lưu URL đầy đủ để lấy lại sau đó. Lưu URL ngay vào nơi bảo vệ phù hợp nếu nghiệp vụ cần phát lại cho người nhận.

### 12.4. Quyền để tạo PAR

Principal tạo PAR cần PAR_MANAGE trên bucket. Ngoài ra, principal phải có quyền phù hợp với access type đang cấp:

- Read: OBJECT_READ.
- Upload: OBJECT_CREATE và OBJECT_OVERWRITE.
- Read/write: OBJECT_READ, OBJECT_CREATE và OBJECT_OVERWRITE.

Nếu creator bị xóa hoặc mất quyền cần thiết, PAR cũng ngừng hoạt động. OCI kiểm tra quyền của creator mỗi lần PAR được sử dụng.

### 12.5. Thu hồi và bảo vệ PAR

- Xóa PAR bằng DeletePreauthenticatedRequest để thu hồi quyền.
- Đặt expiry ngắn.
- Scope vào một object cụ thể khi có thể.
- Không bật bucket listing nếu không cần.
- Gửi URL qua kênh đã xác minh người nhận.
- Không log URL, query/path token hoặc đưa vào analytics.
- Không lưu PAR URL trong database/log không mã hóa.
- Không đưa PAR vào browser referrer hoặc third-party analytics.
- Audit người tạo, target, access type, expiry và thời điểm revoke.

PAR URL là bearer credential. Nếu bị lộ, người khác có thể truy cập tới expiry hoặc cho tới khi PAR bị xóa/quyền creator bị thu hồi.

## 13. IAM policy cho document-service

### 13.1. Read-only policy

Nếu workload chỉ đọc object trong bucket hợp đồng:

~~~text
Allow dynamic-group DocumentService to read objects in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  target.object.name = 'contracts/*'
}
~~~

Nếu service cần liệt kê object, cần quyền inspect objects. Nếu cần liệt kê bucket, có thể cần BUCKET_INSPECT hoặc policy tương ứng. GetNamespace không cần permission khi lấy namespace của chính caller.

### 13.2. Policy cho upload

Ví dụ service chỉ tạo object mới trong bucket inbox và được list object cần thiết:

~~~text
Allow dynamic-group DocumentService to read buckets in compartment AppData
where target.bucket.name = 'contract-inbox'

Allow dynamic-group DocumentService to manage objects in compartment AppData
where all {
  target.bucket.name = 'contract-inbox',
  any {
    request.permission = 'OBJECT_CREATE',
    request.permission = 'OBJECT_INSPECT'
  }
}
~~~

Policy condition giới hạn manage objects vào OBJECT_CREATE và OBJECT_INSPECT. Nếu service cần overwrite object đã tồn tại, cần thêm OBJECT_OVERWRITE. Nếu dùng multipart upload, cần cả OBJECT_CREATE và OBJECT_OVERWRITE cùng các quyền commit operation được yêu cầu.

### 13.3. Policy cho upload và download trong một bucket

~~~text
Allow dynamic-group DocumentService to read buckets in compartment AppData
where target.bucket.name = 'contracts-prod'

Allow dynamic-group DocumentService to read objects in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  target.object.name = 'contracts/*'
}

Allow dynamic-group DocumentService to manage objects in compartment AppData
where all {
  target.bucket.name = 'contract-inbox',
  any {
    request.permission = 'OBJECT_CREATE',
    request.permission = 'OBJECT_OVERWRITE',
    request.permission = 'OBJECT_INSPECT'
  }
}
~~~

Tách bucket read-only và upload inbox giúp giảm phạm vi. Nếu service chỉ upload một lần và object key duy nhất, ưu tiên create-only và unique key để hạn chế overwrite.

### 13.4. Policy cho PAR

Principal tạo PAR cần PAR_MANAGE trên bucket và quyền object tương ứng với access type. Ví dụ nhóm chia sẻ hợp đồng chỉ tạo PAR đọc object trong prefix contracts:

~~~text
Allow dynamic-group DocumentShareService to manage buckets in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  request.permission = 'PAR_MANAGE'
}

Allow dynamic-group DocumentShareService to read objects in compartment AppData
where all {
  target.bucket.name = 'contracts-prod',
  target.object.name = 'contracts/*'
}
~~~

Nếu tạo PAR upload, cần thêm statement cấp OBJECT_CREATE và OBJECT_OVERWRITE trên bucket/object đích. Không cấp manage object-family hoặc tenancy-wide nếu chỉ tạo PAR cho một bucket.

### 13.5. KMS customer-managed key

Nếu bucket dùng customer-managed key, IAM còn cần quyền gắn key và service principal Object Storage cần quyền mã hóa/giải mã theo policy KMS. Với bucket đã mã hóa bằng KMS key, PutObject có thể cần KEY_ENCRYPT; GetObject có thể cần KEY_DECRYPT cho service principal Object Storage. Cấp đúng key compartment và key policy theo hướng dẫn OCI.

### 13.6. Policy không thay thế authorization nghiệp vụ

IAM policy cho phép workload truy cập bucket. Nó không biết user cuối cùng có quyền tải document ID đó hay không. Spring Boot vẫn phải xác minh tenant, owner, classification và business permission trước khi gọi Storage API hoặc tạo PAR.

## 14. Bảo mật dữ liệu và mạng

### 14.1. Bucket private

Giữ bucket private trừ khi có yêu cầu public access đã được đánh giá. Dùng OCI IAM policy cho workload nội bộ và PAR cho chia sẻ có kiểm soát. Không tạo public bucket để giải quyết lỗi 403.

### 14.2. Encryption at rest

OCI Object Storage mã hóa dữ liệu lưu trữ. Có thể dùng Oracle-managed keys mặc định hoặc customer-managed key theo yêu cầu kiểm soát khóa. Với customer-managed key:

- Chọn Vault/Key phù hợp region.
- Cấp KEY_ASSOCIATE cho thao tác gắn key.
- Cấp KEY_ENCRYPT/KEY_DECRYPT/KEY_READ cho service principal Object Storage theo yêu cầu.
- Kiểm thử upload/download sau khi đổi key policy.
- Không disable/destroy key còn bảo vệ object/version/backup.

### 14.3. TLS và private connectivity

Dùng HTTPS cho mọi request. Với workload trong private subnet, có thể dùng Service Gateway để truy cập Object Storage qua OCI network backbone mà không cần NAT/public internet egress cho đường đi đó.

Service Gateway không thay thế IAM policy. Network reachability và authorization là hai lớp riêng.

### 14.4. Bảo vệ object name và metadata

Không đặt PII hoặc secret trong object key vì key có thể xuất hiện trong audit/access log. Metadata cũng không nên chứa nội dung nhạy cảm. Dùng opaque ID, classification label và reference đã pseudonymize.

### 14.5. Kiểm soát file upload

Trước khi chuyển object sang vùng lưu chính thức:

- Xác minh tenant và quyền upload.
- Giới hạn kích thước và số file.
- Kiểm tra extension và MIME type thực tế.
- Quét malware nếu yêu cầu.
- Kiểm tra checksum.
- Sinh object key phía server.
- Lưu file vào quarantine prefix/bucket trước khi scan.
- Không cho upload ghi đè object đã được duyệt.
- Ghi audit event có actor, document ID, object key reference và outcome.

## 15. Retry, lỗi và tính đúng đắn

### 15.1. Strong consistency không loại bỏ retry

OCI Object Storage có strong consistency nhưng request có thể timeout sau khi server đã xử lý xong. Nếu client gửi lại PUT, có thể tạo/ghi đè object lần nữa. Dùng object key duy nhất, If-None-Match hoặc If-Match để làm rõ semantics.

### 15.2. SDK retry

OCI Java SDK có retry configuration cho các operation hỗ trợ. Các lỗi transient như timeout, connection error, 429 hoặc một số 5xx có thể được retry theo policy SDK. Không giả định mọi operation đều retry và không tự retry vô hạn.

Với upload:

- Dùng file/stream có thể đọc lại nếu retry hoặc multipart.
- Dùng unique object key hoặc conditional request.
- Kiểm tra object sau timeout trước khi gửi lại.
- Không retry lỗi 401/403 như lỗi mạng.
- Khi tự quản lý multipart, theo dõi upload ID và abort upload dở dang.

SDK asynchronous clients có khác biệt về retry support; kiểm tra tài liệu version đang dùng trước khi chuyển sync sang async.

### 15.3. Lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| 401 NotAuthenticated | Auth profile, key, token hoặc workload identity sai | Kiểm tra config type, credential và runtime |
| 403 NotAuthorizedOrNotFound | Thiếu IAM permission, sai compartment hoặc bucket scope | Kiểm tra principal, policy, target bucket và object |
| 404 object not found | Sai namespace, bucket, object key hoặc version | Kiểm tra key chính xác và region |
| 409 conflict | Bucket/object đã tồn tại hoặc state không phù hợp | Dùng unique key, conditional request và kiểm tra trạng thái |
| 412 precondition failed | ETag/If-None-Match không còn thỏa | Đọc lại metadata và xử lý concurrency |
| 429 Too Many Requests | Rate limit hoặc burst traffic | Backoff có jitter, giới hạn concurrency |
| 5xx/timeout | Network/service transient | Retry giới hạn và kiểm tra request ID |
| Upload multipart 403 | Thiếu OBJECT_CREATE/OBJECT_OVERWRITE hoặc BUCKET_READ | Kiểm tra permission matrix multipart |
| Resource mở bằng HTTP thường | Starter resolver chưa được đăng ký | Kiểm tra starter và URI format |
| WritableResource upload không hoàn tất | OutputStream chưa đóng | Dùng try-with-resources |
| File download bị heap OOM | readAllBytes hoặc buffer toàn bộ file | Stream qua InputStream/StreamingResponseBody |
| Object bị ghi đè | Object key dùng chung hoặc thiếu condition | Dùng UUID key/If-None-Match/If-Match |
| PAR URL bị từ chối | Expired, deleted, creator mất quyền hoặc URL bị cắt | Kiểm tra PAR metadata, creator policy và full URL |
| UploadManager multipart thất bại | Policy thiếu permission, stream không đọc lại được hoặc part error | Dùng File/repeatable stream, kiểm tra policy và abort |
| Không list được object | Thiếu OBJECT_INSPECT | Cấp inspect đúng bucket/prefix |

### 15.4. Ghi request ID

OCI SDK response có opc-request-id. Ghi request ID cùng timestamp, service, region, operation và object reference để điều tra. Không ghi Authorization header, PAR URL, nội dung object hoặc secret vào log.

### 15.5. ETag và checksum

ETag hữu ích cho conditional request và phát hiện object thay đổi. Không giả định ETag luôn là MD5 của toàn bộ object, đặc biệt với multipart. Nếu nghiệp vụ cần checksum bền vững, tính SHA-256 ở ứng dụng và lưu ở database/metadata đã kiểm soát.

## 16. Observability và vận hành

### 16.1. Metrics

Theo dõi:

- Số upload/download/delete theo bucket và service.
- Tổng byte upload/download.
- Upload duration và download latency.
- Error rate theo status/service code.
- Số multipart upload đang dở.
- PAR được tạo, hết hạn và thu hồi.
- Số request bị từ chối bởi IAM.
- Storage usage, object count và storage tier.
- Thời gian chờ connection/thread pool.

Không đưa object name có PII hoặc PAR URL vào metric label.

### 16.2. Audit

Bật Cloud Audit Logs/Data Access hoặc Object Storage logging phù hợp với nhu cầu. Ghi application audit ở Spring Boot để nối user cuối cùng với business document ID. Cloud audit có thể ghi OCI principal, API operation và resource nhưng không tự hiểu mục đích nghiệp vụ.

### 16.3. Lifecycle và version retention

Bucket có thể cấu hình lifecycle để chuyển storage tier hoặc xóa object/version hết hạn. Versioning giữ bản cũ nhưng tăng chi phí. Cần thiết kế retention, legal hold, lifecycle và backup theo data classification.

### 16.4. Disaster recovery

Object Storage là regional service và lưu dữ liệu dự phòng trong region. Nếu yêu cầu DR qua region, thiết kế replication policy và kiểm tra destination bucket/region. IAM policy, KMS key, lifecycle và PAR không tự được sao chép theo cách giống object; phải kiểm tra từng thành phần.

### 16.5. Cost awareness

Chi phí không chỉ là GB lưu trữ:

- Request API và số lần list.
- Data retrieval theo storage tier.
- Cross-region replication/transfer.
- Multipart parts chưa commit.
- Version cũ và backup.
- Logging/monitoring.
- PAR không dùng nhưng chưa xóa không trực tiếp tạo chi phí URL, nhưng làm tăng rủi ro bảo mật.

Tránh list toàn bucket trong mỗi request. Dùng prefix, pagination, cache metadata và database index để tìm object.

## 17. Kiểm thử tích hợp

### 17.1. Unit test Storage service

Mock Storage interface và xác minh:

- Upload dùng đúng bucket/key.
- Metadata chứa content type/length.
- Object key được tạo phía server.
- Download yêu cầu đúng object.
- Delete chỉ gọi sau authorization.
- Exception được chuyển thành lỗi nghiệp vụ phù hợp.
- Không log stream hoặc nội dung file.

### 17.2. Spring Resource test

Với integration test có OCI test environment:

- ResourceLoader resolve URL thành OracleStorageResource.
- Resource.isReadable() đúng.
- getInputStream() đọc đúng bytes.
- WritableResource.getOutputStream() ghi object khi close.
- Đọc lại object sau khi upload.
- Object key chứa prefix và ký tự đặc biệt được encode đúng.
- Không fallback sang UrlResource không xác thực.

### 17.3. OCI integration test

Dùng tenancy, compartment, bucket và workload identity riêng cho test. Tạo object key duy nhất cho mỗi test và cleanup sau khi hoàn tất.

Kiểm thử:

1. Upload object mới.
2. Download và so sánh checksum.
3. List theo prefix và đọc pagination.
4. Kiểm tra metadata/ETag.
5. Upload với If-None-Match để xác nhận không ghi đè.
6. Upload file lớn qua UploadManager.
7. Tạo PAR cho object và thử GET/PUT đúng access type.
8. Xóa PAR rồi xác nhận URL bị từ chối.
9. Thử truy cập bucket ngoài scope để xác nhận 403.
10. Kiểm tra request ID và audit event.

Không chạy test phá hủy trên bucket production. Dùng prefix riêng, bucket tạm và policy least privilege.

### 17.4. Test IAM negative cases

Test quyền bị từ chối quan trọng không kém test thành công:

- Principal đọc được contracts-prod nhưng không đọc bucket khác.
- Principal upload được contract-inbox nhưng không delete object.
- Principal không thể tạo bucket hoặc thay IAM policy.
- Người dùng tenant A không tải document tenant B.
- PAR chỉ đọc object được chỉ định, không list bucket.
- Object key khác prefix bị từ chối.

### 17.5. Test retry và concurrency

- Hai request cùng object key với If-None-Match chỉ có một request thành công.
- Update với ETag cũ bị từ chối.
- Timeout sau upload không tạo object ngoài ý muốn.
- Multipart part failure có thể retry và cuối cùng commit đúng object.
- Client disconnect đóng stream và giải phóng resource.
- Hai request download đồng thời không chia sẻ InputStream không an toàn.

## 18. Bài tập thực hành tổng hợp

Bạn được giao xây document-service trên OCI. Service lưu hợp đồng PDF vào bucket contracts-prod, metadata trong PostgreSQL và cung cấp REST API cho người dùng đã xác thực. Một đối tác ngoài OCI cần upload hồ sơ vào bucket contract-inbox và tải file đã được duyệt bằng URL có thời hạn.

**Nhiệm vụ:**

1. Tạo bucket contracts-prod và contract-inbox trong compartment AppData bằng IaC hoặc Console.
2. Cấu hình Spring Cloud Oracle 2.0.4 storage starter.
3. Dùng FILE profile local và Instance Principal/OKE Workload Identity ở production.
4. Cấu hình region.static và compartment.static đúng môi trường.
5. Viết Storage service upload PDF với content type, content length và custom metadata.
6. Viết download endpoint dùng StreamingResponseBody.
7. Resolve OCI object URL thành Resource và WritableResource.
8. Tạo object key từ tenant/document ID phía server.
9. Viết ListObjects pagination theo prefix.
10. Dùng UploadManager cho file vượt ngưỡng multipart.
11. Cấu hình IAM policy chỉ đọc contracts-prod và upload vào contract-inbox.
12. Tạo PAR ObjectRead cho đối tác với TTL 15 phút và revoke sau khi hoàn thành.
13. Viết unit/integration tests cho upload/download/list/PAR/denied access.
14. Ghi audit event cho upload, download, export và revoke.
15. Viết runbook xử lý 401/403/404/412, timeout và multipart upload dở dang.

**Câu hỏi tự đánh giá:**

- Namespace khác bucket và compartment như thế nào?
- Vì sao object key dùng dấu slash không tạo directory vật lý?
- Object Storage strong consistency có loại bỏ nhu cầu ETag không?
- Spring Cloud Oracle starter cung cấp bean nào?
- Resource và WritableResource khác nhau như thế nào?
- Vì sao URI Object Storage không mặc nhiên là public URL?
- Khi nào dùng Storage API và khi nào cần OCI Java SDK trực tiếp?
- Vì sao không dùng getFile() cho object storage Resource?
- UploadManager giải quyết vấn đề gì khi file lớn?
- Multipart upload cần những permission nào?
- Vì sao If-None-Match hữu ích khi upload?
- ETag có luôn là MD5 của object không?
- PAR là bearer URL và có thể thu hồi bằng cách nào?
- Vì sao PAR URL phải được lưu ngay khi tạo?
- Vì sao workload vẫn phải kiểm tra quyền user cuối trước khi gọi Storage?
- Vì sao service nên stream file thay vì readAllBytes?
- Vì sao cần test IAM denied cases?
- Vì sao versioning và lifecycle cần được thiết kế cùng nhau?

**Đáp án định hướng:** namespace là top-level container cấp tenancy; bucket là regional container thuộc một compartment; object key là tên phẳng có thể dùng prefix; strong consistency không ngăn concurrent overwrite; starter tạo Storage bean và protocol resolver; Resource đọc còn WritableResource ghi; URL Resource đi qua OCI SDK/auth khi resolver của starter được đăng ký; Storage API phù hợp CRUD thông thường còn SDK xử lý list/PAR/multipart; remote resource không phải file local; UploadManager tự chia parts và retry part; multipart cần OBJECT_CREATE và OBJECT_OVERWRITE cùng quyền commit cần thiết; If-None-Match ngăn overwrite; ETag không phải checksum MD5 phổ quát; PAR xóa bằng DeletePreauthenticatedRequest và hết hạn theo timeExpires; URL chỉ hiện khi tạo nên phải lưu an toàn; business authorization nằm ở Spring Boot; stream giảm heap; negative tests chứng minh least privilege; versioning giữ bản cũ và lifecycle quyết định thời hạn/xóa.

## 19. Tài liệu tham khảo chính thức

### Spring Cloud Oracle và Spring Framework

- [Spring Cloud Oracle 2.0.4 – OCI Object Storage](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/storage/): Storage bean, upload, Resource và WritableResource.
- [Spring Cloud Oracle – OCI Core](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/): authentication type, region và compartment properties.
- [Spring Cloud Oracle – Configuration Properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/): cấu hình auth, region, compartment và storage enabled.
- [Spring Cloud Oracle 2.0.4 – Storage Javadocs](https://oracle.github.io/spring-cloud-oracle/2.0.4/javadocs/com/oracle/cloud/spring/storage/Storage.html): Storage methods, upload/download, read/store và getClient.
- [Spring Cloud Oracle 2.0.4 – StorageObjectMetadata](https://oracle.github.io/spring-cloud-oracle/2.0.4/javadocs/com/oracle/cloud/spring/storage/StorageObjectMetadata.html): content metadata, conditional request và encryption fields.
- [Spring Framework – Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): Resource, ResourceLoader, WritableResource và stream contract.
- [Spring Cloud Oracle – Release Notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/): Spring Boot/Spring Framework compatibility và thay đổi WritableResource.

### OCI Object Storage

- [Overview of Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm): bucket, object, namespace, compartment, regional service và strong consistency.
- [Object Storage Namespaces](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/understandingnamespaces.htm): namespace của tenancy và cách lấy namespace.
- [Object Storage Objects](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm): object naming, metadata và conditional request.
- [Object Storage Multipart Uploads](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingmultipartuploads.htm): multipart workflow, part limits và required IAM permissions.
- [OCI Java SDK – UploadManager](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/transfer/UploadManager.html): upload tự chọn single PUT hoặc multipart.
- [OCI Java SDK – ListObjects](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/ObjectStorage.html): list, fields và pagination.
- [Object Storage Pre-Authenticated Requests](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests.htm): PAR scope, permissions, expiry và revoke.
- [Create Pre-Authenticated Request](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests_topic-To_create_a_preauthenticated_request_for_all_objects_in_a_bucket.htm): tạo PAR cho bucket/object/prefix.
- [Delete Pre-Authenticated Request](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests_topic-To_delete_a_preauthenticated_request.htm): thu hồi PAR.
- [Object Storage Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm): resource type, permission cho bucket/object/PAR/multipart và KMS.
- [OCI Common Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm): policy mẫu read/write Object Storage và condition theo bucket/object.
- [Object Storage Security](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm): least privilege, public bucket và IAM condition.
- [OCI Java SDK Concepts](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm): client reuse, retry, large object và SDK threading model.

**Ghi nhớ:** Storage API là lựa chọn thuận tiện cho CRUD object; Spring Resource giúp tích hợp object vào API stream của Spring; OCI Java SDK xử lý các tính năng chuyên biệt như pagination, multipart và PAR. Đặt đúng identity và IAM policy, giữ bucket private, tạo object key phía server, dùng conditional write khi cần và stream dữ liệu thay vì nạp toàn bộ file vào memory.
