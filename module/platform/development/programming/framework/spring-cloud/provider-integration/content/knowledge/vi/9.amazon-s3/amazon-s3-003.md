# Amazon S3: Thao tác tải lên, tải xuống, liệt kê và xóa đối tượng S3

## Mục tiêu bài học

Trong module `SPRING_CLOUD_PROVIDER_INTEGRATION`, ứng dụng Spring Boot sẽ kết nối các dịch vụ managed của AWS, Azure và Google Cloud để lưu dữ liệu, trao đổi thông điệp và xử lý nghiệp vụ. Đối với **Amazon S3**, bốn thao tác thường gặp nhất là **upload (PUT), download (GET), list (LIST) và delete (DELETE)**. Bài này hướng dẫn thực hiện các thao tác đó bằng **Spring Cloud AWS + AWS SDK for Java v2**, đồng thời giải thích phân trang, streaming, quyền IAM, versioning, lỗi thường gặp và cách kiểm thử tích hợp.

Sau bài học, bạn có thể:

- Chọn bucket và object key hợp lý cho dữ liệu của ứng dụng.
- Upload và tải về object mà không vô tình đọc hết file lớn vào bộ nhớ.
- Liệt kê object theo prefix, duyệt nhiều trang và hiểu giới hạn của LIST.
- Xóa object có chủ đích, phân biệt xóa ở bucket bật/tắt versioning.
- Thiết kế quy trình thao tác S3 có phân quyền, kiểm soát lỗi và kiểm thử.

> Các ví dụ dùng namespace `io.awspring.cloud` của Spring Cloud AWS hiện đại và `software.amazon.awssdk` của AWS SDK v2. Phần cấu hình cần phiên bản Spring Cloud AWS **tương thích với phiên bản Spring Boot thực tế** của dự án; đoạn tài liệu không cố định một số phiên bản cho mọi hệ thống.

## 1. Mô hình dữ liệu và bốn thao tác cơ bản

S3 là dịch vụ **object storage**. Mỗi object nằm trong một **bucket** và có **key** duy nhất trong bucket tại một thời điểm. Key là chuỗi ký tự có thể chứa dấu `/`, nhưng không đòi hỏi phải có thư mục thật trên máy chủ.

Ví dụ:

~~~text
s3://training-private-docs/documents/2026/invoice-42.pdf
     └────── bucket ──────┘└──────── object key ────────┘
~~~

Một đối tượng gồm dữ liệu (body), thông tin đi kèm như content type và user metadata, cùng trạng thái do S3 quản lý. Bảng ánh xạ nhu cầu nghiệp vụ sang AWS API:

| Nhu cầu | AWS SDK v2 | Quyền IAM thường dùng | Kết quả |
| --- | --- | --- | --- |
| Upload hoặc thay nội dung | `S3Client.putObject` | `s3:PutObject` | Object được lưu theo bucket/key |
| Tải nội dung | `S3Client.getObject` | `s3:GetObject` | Byte stream và metadata phản hồi |
| Xem thông tin không tải body | `S3Client.headObject` | `s3:GetObject` | Kích thước, content type, metadata, ETag... |
| Liệt kê theo prefix | `S3Client.listObjectsV2` | `s3:ListBucket` | Một trang danh sách key và metadata tóm tắt |
| Xóa theo key | `S3Client.deleteObject` | `s3:DeleteObject` | Thao tác xóa được S3 chấp nhận |

**Hai điểm cần nhớ từ đầu:** PUT trên **cùng bucket/key** không mặc nhiên tạo một tệp mới; nó có thể thay thế phiên bản hiện hành. DELETE cũng không luôn đồng nghĩa xóa sạch byte khỏi S3, nhất là khi bucket bật versioning.

### Luồng điển hình trong Spring Boot

~~~mermaid
flowchart LR
    C["Client"] -->|"Xác thực + yêu cầu upload/download"| A["Spring Boot API"]
    A -->|"Kiểm tra quyền tài liệu"| D["Database nghiệp vụ"]
    D -->|"Owner/tenant + object key"| A
    A --> S["Storage service"]
    S -->|"AWS SDK v2, IAM role"| B["S3 bucket private"]
    B -->|"Object / metadata"| S
~~~

Database thường lưu quan hệ `documentId → bucket/key, owner, tenant, trạng thái`. Key là định danh lưu trữ, còn **quyền truy cập người dùng** phải được xác minh tại ứng dụng trước khi service GET hoặc DELETE một object.

## 2. Chuẩn bị Spring Boot và quyền truy cập

### 2.1. Dependency và cấu hình

Với Maven, import BOM của Spring Cloud AWS rồi thêm S3 starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

Dự án phải khai báo `spring-cloud-aws.version` theo ma trận tương thích với Spring Boot đang chạy. Starter giúp cấu hình AWS SDK client thông qua Spring Boot auto-configuration; ví dụ dưới đây dùng trực tiếp bean `S3Client` để nhìn rõ từng request.

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    prefix: documents/
~~~

`app.storage.*` là cấu hình ứng dụng tự định nghĩa. Bucket ví dụ `training-private-docs` cần tồn tại tại Region phù hợp, và `S3_BUCKET_NAME` phải được cung cấp ở môi trường chạy. Không hard-code access key/secret key trong YAML: AWS SDK có **default credentials provider chain**, nên khi triển khai hãy dùng IAM role/workload identity; khi học tại máy cá nhân có thể dùng AWS profile hoặc credentials tạm thời hợp lệ.

### 2.2. Quyền IAM tối thiểu cho một prefix

Policy sau chỉ cho phép service liệt kê và đọc/ghi/xóa trong `documents/`. Thay bucket minh họa bằng bucket trong tài khoản thử nghiệm:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDocumentPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::training-private-docs",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["documents/", "documents/*"]
        }
      }
    },
    {
      "Sid": "ManageDocumentObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::training-private-docs/documents/*"
    }
  ]
}
~~~

`s3:ListBucket` áp dụng cho **bucket ARN**; GET/PUT/DELETE cần **object ARN**. Điều kiện `s3:prefix` điều khiển LIST, không kiểm soát GET/PUT/DELETE; giới hạn của ba thao tác đó nằm ở object ARN. Nếu thực tế service không có chức năng xóa, bỏ `s3:DeleteObject` khỏi role. Nếu dùng SSE-KMS, cần xét thêm quyền với KMS key. Bucket policy, SCP, explicit deny và các điều kiện bảo vệ khác vẫn có thể làm request bị từ chối.

## 3. Xây dựng service thao tác S3 bằng AWS SDK v2

Ví dụ dưới đây sử dụng **client đồng bộ** `S3Client`, key do backend tự tạo khi upload và prefix `documents/`. Bốn phương thức thao tác tương ứng với PUT/GET/LIST/DELETE; thêm `head` để đọc metadata.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Response;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class DocumentS3Service {
    private static final String PREFIX = "documents/";
    private final S3Client s3;
    private final String bucket;

    public DocumentS3Service(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    // Upload một object mới và trả key để lưu vào database nghiệp vụ.
    public String upload(
            InputStream content, long exactSize, String contentType) {
        if (exactSize < 0) {
            throw new IllegalArgumentException("Kích thước phải >= 0");
        }

        String key = PREFIX + UUID.randomUUID();
        String safeType = (contentType == null || contentType.isBlank())
                ? "application/octet-stream" : contentType;

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(safeType)
                .build();

        s3.putObject(request,
                RequestBody.fromInputStream(content, exactSize));
        return key;
    }

    // GET rồi ghi dần ra stream do mã gọi cung cấp.
    public void downloadTo(String trustedKey, OutputStream destination)
            throws IOException {
        ensureDocumentKey(trustedKey);

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build();

        try (ResponseInputStream<GetObjectResponse> source =
                     s3.getObject(request)) {
            source.transferTo(destination);
        }
    }

    // HEAD trả metadata mà không tải nội dung.
    public HeadObjectResponse head(String trustedKey) {
        ensureDocumentKey(trustedKey);
        return s3.headObject(HeadObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build());
    }

    // LIST đúng một trang. nextToken rỗng nghĩa là trang đầu.
    public ListObjectsV2Response listPage(
            String nextToken, int pageSize) {
        if (pageSize < 1 || pageSize > 1000) {
            throw new IllegalArgumentException(
                    "pageSize phải trong khoảng 1..1000");
        }

        ListObjectsV2Request.Builder request =
                ListObjectsV2Request.builder()
                        .bucket(bucket)
                        .prefix(PREFIX)
                        .maxKeys(pageSize);

        if (nextToken != null && !nextToken.isBlank()) {
            request.continuationToken(nextToken);
        }

        return s3.listObjectsV2(request.build());
    }

    // Xóa object hiện hành theo key.
    public void delete(String trustedKey) {
        ensureDocumentKey(trustedKey);
        s3.deleteObject(DeleteObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build());
    }

    private static void ensureDocumentKey(String key) {
        if (key == null || !key.startsWith(PREFIX)
                || key.length() <= PREFIX.length()) {
            throw new IllegalArgumentException("Key ngoài documents/");
        }
    }
}
~~~

**Điều kiện sử dụng code đúng cách:**

- `InputStream` upload phải còn mở khi gọi `putObject`. Caller sở hữu và đóng input stream; service đóng stream mà nó mở để đọc S3 trong `downloadTo`.
- `RequestBody.fromInputStream(content, exactSize)` cần **đúng kích thước byte**. Nếu cung cấp số byte sai, upload có thể bị cắt ngắn, bị chặn hoặc thất bại. Với stream không biết kích thước hoặc file lớn, chọn chiến lược upload phù hợp thay vì đoán số byte.
- `contentType` trong ví dụ là giá trị được truyền vào; production cần xác minh định dạng thật, tên file, kích thước, quyền và nội dung đáng ngờ trước khi chấp nhận upload.
- `trustedKey` chỉ được lấy sau bước **authorization** bằng dữ liệu nghiệp vụ. Kiểm tra prefix trong service là rào chắn cơ bản, không chứng minh một người dùng có quyền với object đó.
- `S3Client` được inject và tái sử dụng. Tránh tạo một client mới cho từng HTTP request.
- DELETE không trả nội dung object; muốn phản hồi 404 theo nghĩa nghiệp vụ, backend phải xác minh **bản ghi tài liệu và quyền truy cập** trong hệ thống của mình.

Các phần sau giải thích tại sao mỗi phương thức cần thiết kế như vậy.

## 4. Upload đối tượng: PUT

### 4.1. Gửi file lên S3 gồm những thông tin nào?

Một yêu cầu PUT thông dụng cần:

- **Bucket** đích, chẳng hạn `training-private-docs`.
- **Object key** bên trong bucket, chẳng hạn `documents/7c1d...`.
- **Nội dung byte** và kích thước byte chính xác nếu dùng input stream đồng bộ dạng `fromInputStream`.
- **Metadata** phù hợp như `Content-Type`, `Content-Disposition`, `Cache-Control` hoặc custom metadata.
- **Credentials và quyền IAM** cho `s3:PutObject`.

Ví dụ chỉ upload văn bản nhỏ trực tiếp từ byte array:

~~~java
byte[] payload = "Xin chào từ Spring Boot"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

var putResult = s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key("documents/demo.txt")
                .contentType("text/plain; charset=UTF-8")
                .metadata(java.util.Map.of("source", "lesson-003"))
                .build(),
        RequestBody.fromBytes(payload));

System.out.println(putResult.eTag());
~~~

`RequestBody.fromBytes` đơn giản nhưng phải giữ toàn bộ payload trong RAM; chỉ phù hợp file nhỏ. Nếu upload lần nữa lên **cùng key**, S3 cập nhật nội dung hiện hành; với bucket bật versioning, những phiên bản cũ có thể vẫn được giữ.

**Tạo key an toàn:** backend có thể dùng `documents/{opaqueId}/{UUID}` hoặc tạo UUID ngẫu nhiên. Không ghép trực tiếp `originalFilename` do client gửi vào key để làm cơ chế bảo mật, vì tên file có thể trùng, chứa dữ liệu nhạy cảm hoặc ký tự cần xử lý. Key S3 có giới hạn độ dài theo byte UTF-8; prefix là quy ước đặt tên chứ không phải folder vật lý.

### 4.2. Upload từ endpoint Spring MVC

Trong một ứng dụng đã có Spring Web, controller có thể chuyển `MultipartFile` sang service. Ví dụ này chỉ minh họa đường đi của file; ở hệ thống thật cần **authentication, authorization, giới hạn kích thước và kiểm tra nội dung** trước bước upload.

~~~java
import java.io.IOException;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentUploadController {
    private final DocumentS3Service storage;

    public DocumentUploadController(DocumentS3Service storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File trống");
        }

        try (var input = file.getInputStream()) {
            String key = storage.upload(
                    input, file.getSize(), file.getContentType());
            // Ở ứng dụng thật, lưu key cùng owner/tenant vào database.
            return Map.of("key", key);
        }
    }
}
~~~

`MultipartFile.getSize()` cung cấp số byte theo phần upload đã nhận; web server và Spring MVC cũng phải được cấu hình **max-file-size/max-request-size** phù hợp. Khi API nhận upload hoàn toàn từ bên ngoài, còn cần quyết định loại file cho phép, quét nội dung theo chính sách và cách xử lý upload thành công lên S3 nhưng transaction database thất bại.

### 4.3. Khi nào cần multipart upload?

Multipart upload của S3 chia object lớn thành các part, upload rồi hoàn tất bằng việc ghép part trên S3. Hãy cân nhắc khi:

- File lớn, upload qua đường truyền kém ổn định hoặc cần upload song song.
- Cần retry từng part thay vì truyền lại toàn bộ object.
- Cần tránh tải cả object vào RAM trong backend.

Trong AWS SDK v2 có thể dùng **S3 Transfer Manager** (kết hợp async/transfer client phù hợp) hoặc chủ động gọi các API multipart. Nếu tự điều phối multipart, ứng dụng cần xử lý **CompleteMultipartUpload** sau khi đủ part và **AbortMultipartUpload** khi từ bỏ phiên upload để tránh phát sinh chi phí cho các part chưa hoàn tất. Với browser/mobile, một hướng khác là backend kiểm tra quyền rồi cấp **presigned URL** PUT/multipart ngắn hạn; client tải trực tiếp lên S3.

### 4.4. Kiểm soát ghi đè

Nếu key đã tồn tại, PUT thông thường lên cùng key sẽ cập nhật nội dung hiện hành. Để tránh trường hợp hai request vô tình ghi đè, có thể:

1. Sinh key mới theo UUID và ghi key vào database cùng bản ghi tài liệu.
2. Dùng **conditional write** (ví dụ `If-None-Match: *` khi API/SDK hỗ trợ) nếu nghiệp vụ đòi hỏi chỉ tạo object khi key chưa tồn tại.
3. Bật S3 Versioning nếu cần giữ lịch sử nội dung.
4. Thiết kế **idempotency key** riêng cho request nghiệp vụ nếu client có thể retry sau timeout.

Không nên chỉ gọi HEAD rồi PUT và tin rằng object sẽ không bị tạo giữa hai thao tác; đây là dạng **race condition** nếu nhiều request hoạt động đồng thời.

## 5. Download đối tượng: GET và HEAD

### 5.1. GET dạng streaming

`getObject` cho phép nhận nội dung qua `ResponseInputStream<GetObjectResponse>`. Dùng try-with-resources để đóng stream, kể cả khi kết nối bị lỗi:

~~~java
GetObjectRequest request = GetObjectRequest.builder()
        .bucket(bucket)
        .key("documents/demo.txt")
        .build();

try (var source = s3.getObject(request);
     var destination = java.nio.file.Files.newOutputStream(
             java.nio.file.Path.of("downloaded-demo.txt"))) {
    source.transferTo(destination);
}
~~~

Ví dụ trên phù hợp với thao tác **tải xuống file local** của một chương trình thực hành. Trong một web API, thường stream nội dung đến HTTP response hoặc cấp presigned GET URL có thời hạn, không cần tạo file local.

Nếu cần trả file qua Spring MVC, đặt HTTP response headers thích hợp như `Content-Type`, `Content-Disposition` và kích thước từ metadata đáng tin cậy; tránh truyền trực tiếp header/filename nguy hiểm do client tự cung cấp. Nếu đối tượng rất lớn, API nên stream theo từng đoạn hoặc cho client tải từ S3 trực tiếp.

### 5.2. HEAD chỉ lấy metadata

~~~java
var info = s3.headObject(HeadObjectRequest.builder()
        .bucket(bucket)
        .key("documents/demo.txt")
        .build());

System.out.println("Type: " + info.contentType());
System.out.println("Size: " + info.contentLength());
System.out.println("ETag: " + info.eTag());
System.out.println("Version: " + info.versionId());
~~~

HEAD phù hợp khi cần xem kích thước, content type, version ID và một số metadata mà không tải body. Tuy nhiên HEAD vẫn là **request đến S3**, cần quyền phù hợp, có độ trễ và phát sinh chi phí request.

**Cẩn thận với HTTP 403/404:** khi truy cập key không tồn tại, S3 có thể trả **404** nếu caller có quyền `s3:ListBucket`, hoặc **403** nếu không có quyền liệt kê bucket. Lỗi 403 cũng có thể do policy chặn hoặc KMS. Vì vậy không thể kết luận object chắc chắn tồn tại chỉ vì nhận được 403.

### 5.3. Download một khoảng byte

Khi xử lý file lớn, media hoặc resume download, S3 hỗ trợ **HTTP Range**. Ví dụ yêu cầu 1.024 byte đầu tiên:

~~~java
var rangeRequest = GetObjectRequest.builder()
        .bucket(bucket)
        .key("documents/large-object.bin")
        .range("bytes=0-1023")
        .build();

try (var part = s3.getObject(rangeRequest)) {
    byte[] firstBytes = part.readAllBytes(); // Chỉ đọc phần được yêu cầu.
    System.out.println(firstBytes.length);
}
~~~

Một số trường hợp S3 có thể trả ít byte hơn yêu cầu do kích thước object, hoặc báo lỗi nếu range không hợp lệ; client cần kiểm tra response. `Range` là một tính năng của GET, khác với **part number** trong multipart upload.

### 5.4. Presigned GET URL

Thay vì để Spring Boot chuyển nhiều gigabyte qua server, backend có thể xác thực user, đối chiếu documentId với key rồi tạo **presigned GET URL** trong thời hạn ngắn. URL này cho phép ai có URL thực hiện request đã ký trong phạm vi hiệu lực; cần tránh ghi vào log và tránh chia sẻ ra ngoài.

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant A as Spring Boot API
    participant DB as Database nghiệp vụ
    participant S3 as S3 bucket private

    U->>A: Xin tải documentId=42
    A->>DB: Kiểm tra owner/tenant và lấy key
    DB-->>A: Quyền hợp lệ + key
    A-->>U: Presigned GET URL ngắn hạn
    U->>S3: GET bằng URL đã ký
    S3-->>U: Nội dung object
~~~

Presigned URL **không chuyển bucket thành public**. Nó đại diện cho quyền của danh tính ký và chỉ nên được cấp sau bước kiểm tra quyền nghiệp vụ; thời hạn URL còn chịu giới hạn bởi thời hạn của credentials dùng để ký.

## 6. Liệt kê đối tượng: LIST và phân trang

### 6.1. LIST hoạt động thế nào?

`ListObjectsV2` trả **danh sách object tóm tắt** trong bucket, có thể lọc theo prefix:

~~~text
documents/2026/invoice-001.pdf
documents/2026/invoice-002.pdf
documents/2025/invoice-100.pdf
images/avatar-101.png
~~~

Với prefix `documents/2026/`, LIST chỉ trả những key bắt đầu bằng chuỗi đó. Dấu `/` trong key chỉ là ký tự phân cách theo quy ước; bucket không có cấu trúc thư mục vật lý bắt buộc.

~~~java
var response = s3.listObjectsV2(
        ListObjectsV2Request.builder()
                .bucket(bucket)
                .prefix("documents/2026/")
                .maxKeys(100)
                .build());

for (var object : response.contents()) {
    System.out.println(object.key()
            + " | " + object.size()
            + " bytes");
}
~~~

Các phần tử `S3Object` được trả về chứa các thuộc tính tóm tắt như key, size, last modified và ETag; **không có body object** và không cung cấp đầy đủ user metadata như HEAD. Không dùng LIST để tìm kiếm theo nội dung văn bản hoặc tùy ý lọc trên custom metadata; ứng dụng nên dùng database/index riêng nếu có yêu cầu truy vấn nghiệp vụ.

### 6.2. Xử lý phân trang đúng

Mỗi trang LIST có giới hạn số key; request thường dùng `maxKeys` (tối đa 1.000 trong API `ListObjectsV2`). Nếu response còn dữ liệu, S3 trả `nextContinuationToken`. Đừng nhầm token này với **object key** hoặc giả định có thể tính ra token của trang sau.

Sử dụng `listPage` trong service:

~~~java
String token = null;

do {
    var page = storage.listPage(token, 100);

    for (var entry : page.contents()) {
        System.out.println(entry.key());
    }

    token = page.nextContinuationToken();
} while (token != null);
~~~

`nextContinuationToken()` là cursor để lấy phần tiếp theo. Trong một API thực tế, nên trả **một trang + nextToken** cho client và giới hạn `pageSize` thay vì cố đọc toàn bộ bucket ở một request HTTP.

AWS SDK v2 còn hỗ trợ paginator:

~~~java
var request = ListObjectsV2Request.builder()
        .bucket(bucket)
        .prefix("documents/")
        .maxKeys(100)
        .build();

for (var page : s3.listObjectsV2Paginator(request)) {
    for (var object : page.contents()) {
        System.out.println(object.key());
    }
}
~~~

Paginators tiện cho batch job, nhưng vẫn có **nhiều request mạng** và có thể mất lâu nếu bucket nhiều object. Giới hạn số trang, thời gian chạy hoặc số key cần xử lý theo use case.

### 6.3. Prefix và delimiter

Thêm `delimiter("/")` cho `ListObjectsV2` có thể nhóm các key vào `CommonPrefixes`, mô phỏng danh sách cấp thư mục:

~~~java
var response = s3.listObjectsV2(
        ListObjectsV2Request.builder()
                .bucket(bucket)
                .prefix("documents/")
                .delimiter("/")
                .build());

response.commonPrefixes().forEach(
        p -> System.out.println(p.prefix()));
~~~

`CommonPrefixes` chỉ là kết quả nhóm theo chuỗi key, không phải một loại thư mục thật. Khi dùng delimiter, số mục trả về có thể gồm cả key và nhóm prefix; hãy hiểu đúng `contents()`, `commonPrefixes()`, pagination và `keyCount()`.

### 6.4. Tính nhất quán, thứ tự và trải nghiệm người dùng

S3 cung cấp **strong read-after-write consistency** đối với PUT/DELETE và các lần GET/LIST liên quan sau khi thao tác thành công. Tuy nhiên, việc phân trang qua nhiều request **không phải một ảnh chụp transaction**: object có thể được thêm/xóa giữa các trang, nên ứng dụng cần thiết kế cách xử lý sự thay đổi đồng thời.

Đừng áp dụng thứ tự key dạng lexicographic cho tất cả loại bucket mà không kiểm tra tính năng bucket dùng; ví dụ directory buckets có khác biệt so với general-purpose buckets. Nếu giao diện cần danh sách được sắp theo ngày tạo, trạng thái thanh toán hoặc chủ sở hữu, nên lấy từ **database nghiệp vụ** thay vì dựa vào thứ tự LIST của S3.

## 7. Xóa đối tượng: DELETE và Versioning

### 7.1. DELETE không bật versioning

~~~java
s3.deleteObject(DeleteObjectRequest.builder()
        .bucket(bucket)
        .key("documents/demo.txt")
        .build());
~~~

Với bucket chưa bật versioning, thao tác xóa object hiện hành theo key là hành động cần được bảo vệ. `DeleteObject` thông thường có tính **idempotent theo nghĩa yêu cầu xóa key**: server có thể trả thành công kể cả khi key không còn tồn tại. Do đó không dùng riêng kết quả `deleteObject` để xác định rằng trước đó chắc chắn có dữ liệu.

### 7.2. DELETE khi bucket bật versioning

Nếu **Versioning** đang bật:

- PUT lên cùng key thường tạo thêm version mới.
- DELETE **không chỉ rõ version ID** thường tạo một **delete marker** và khiến object trông như đã bị xóa ở view mặc định.
- Dữ liệu của các version trước vẫn có thể tồn tại và phát sinh chi phí lưu trữ.
- Muốn xóa vĩnh viễn một version cụ thể phải chỉ rõ version ID và có quyền phù hợp (như `s3:DeleteObjectVersion`). Đây là thao tác riêng, cần quy trình kiểm soát.

~~~text
Bucket bật versioning:

PUT key=documents/a.txt   → version v1
PUT key=documents/a.txt   → version v2 (hiện hành)
DELETE documents/a.txt    → delete marker (hiện hành)
GET documents/a.txt       → thường không thấy object hiện hành
GET version v1/v2         → vẫn có thể truy cập nếu có quyền
~~~

Trong bucket đã **suspended versioning**, hành vi của null version và delete marker có quy tắc riêng; không nên mô tả mọi bucket có history giống hệt ví dụ trên. Các thiết lập như **Object Lock**, retention policy hoặc legal hold có thể ngăn xóa phiên bản ngay cả khi role có quyền trên S3.

### 7.3. Quy trình xóa an toàn trong ứng dụng

Khi người dùng muốn xóa chứng từ, một quy trình thường là:

1. Xác thực người dùng, tìm bản ghi theo `documentId` và kiểm tra quyền xóa.
2. Quyết định nghiệp vụ muốn **soft delete**, xóa object hiện hành hay xóa dữ liệu vĩnh viễn theo chính sách lưu giữ.
3. Ghi trạng thái nghiệp vụ (ví dụ `DELETING`) và thực hiện xóa bằng worker hoặc outbox nếu cần khả năng retry.
4. Cập nhật bản ghi khi thao tác S3 thành công; theo dõi và xử lý lỗi phần còn lại.
5. Với dữ liệu có versioning, quyết định xử lý version cũ, lifecycle, retention và chi phí.

**S3 và database không chia sẻ một transaction ACID.** Không thể mặc định rollback cả hai khi một bước thất bại. Nếu yêu cầu nhất quán nghiệp vụ cao, dùng state machine, outbox, retry có kiểm soát và idempotency, thay vì cố che giấu việc xóa có thể xảy ra ngoài transaction database.

### 7.4. Xóa nhiều object

AWS SDK hỗ trợ `DeleteObjects` để gửi nhiều key trong một request theo giới hạn API. Khi batch delete:

- Kiểm tra **từng phần tử lỗi** trong response; thành công ở mức HTTP không nhất thiết bảo đảm tất cả key đều được xóa.
- Với versioning, xác định rõ muốn xóa current view hay những version cụ thể.
- Chia batch đúng giới hạn, áp dụng retry có kiểm soát, tránh xóa theo prefix do client không tin cậy gửi vào.
- Ghi audit log nghiệp vụ cho các thao tác hàng loạt nếu hệ thống yêu cầu.

Không khuyến nghị minh họa batch delete bằng thao tác “xóa toàn bộ prefix” không có bước đối soát, đặc biệt trong môi trường dùng chung.

## 8. Xử lý lỗi và retry

Các API S3 có thể phát sinh lỗi từ SDK, HTTP, quyền IAM, cấu hình hoặc mạng.

| Hiện tượng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| 403 `AccessDenied` | Thiếu quyền IAM, bucket policy deny, SCP, KMS, policy endpoint | Đối chiếu action, ARN bucket/object và policy hiệu lực |
| 404 `NoSuchKey` với GET | Key không tồn tại hoặc bị che bởi delete marker hiện hành | Kiểm tra key và nghiệp vụ, không suy đoán từ LIST cũ |
| 403 khi HEAD key không tồn tại | Caller không có quyền LIST để phân biệt key không tồn tại | Không dùng 403 để khẳng định key tồn tại |
| Redirect/Region mismatch | Client nhắm sai Region của bucket | Kiểm tra bucket Region và SDK config |
| `SlowDown`/throttling hoặc lỗi 5xx | Tải lớn/tình trạng tạm thời phía dịch vụ | Backoff và retry có giới hạn |
| Upload sai kích thước | `Content-Length` không khớp stream thực | Cung cấp kích thước byte đúng, tránh tự đoán |
| Trình duyệt không tải file như mong đợi | `Content-Type`, `Content-Disposition` không đúng | Chỉnh metadata và HTTP headers |
| LIST tốn thời gian | Bucket nhiều object, đang duyệt hết các trang | Giới hạn prefix, maxKeys và dùng index nghiệp vụ |

Ví dụ tách lỗi S3 để log an toàn:

~~~java
try {
    storage.head(trustedKey);
} catch (software.amazon.awssdk.services.s3.model.S3Exception ex) {
    // Log operation, AWS requestId và mã lỗi; tránh log credential/URL ký.
    System.err.println("S3 HEAD failed, status=" + ex.statusCode()
            + ", requestId=" + ex.requestId());
    throw ex;
}
~~~

**Đừng retry vô điều kiện mọi thao tác:** retry GET/HEAD/LIST khi lỗi tạm thời thường đơn giản hơn; retry PUT với key cố định, DELETE hoặc nghiệp vụ có side effect cần xem xét idempotency và chính sách versioning. AWS SDK đã có chiến lược retry nhất định; cấu hình thêm retry tại tầng ứng dụng mà không hiểu hành vi SDK có thể khiến số lần gọi tăng ngoài dự kiến.

## 9. Kiểm thử tích hợp Spring Boot với S3

Để học cách tích hợp provider, nên kiểm thử cả **mã Java** lẫn **quyền và hành vi của dịch vụ managed**.

| Mức kiểm thử | Nội dung xác minh | Giới hạn |
| --- | --- | --- |
| Unit test với mock `S3Client` | Tạo key, truyền request, kiểm tra rule nghiệp vụ trước GET/DELETE | Không chứng minh API S3 hay IAM thật hoạt động |
| Integration test với S3 emulator | PUT → HEAD → GET → LIST → DELETE, streaming và pagination | Emulator không nhất thiết mô phỏng đúng IAM, KMS, versioning, consistency |
| Integration test trên AWS sandbox | Role thật, bucket private, Region, SSE-KMS, versioning và lỗi truy cập | Phát sinh tài nguyên/chi phí, cần dọn dữ liệu test |

### Kịch bản kiểm thử cho một object

~~~mermaid
flowchart TD
    A["Tạo key ngẫu nhiên dưới test/"] --> B["PUT nội dung mẫu"]
    B --> C["HEAD: size + Content-Type"]
    C --> D["GET: so sánh byte"]
    D --> E["LIST theo prefix + phân trang"]
    E --> F["DELETE key"]
    F --> G["Xác minh trạng thái hiện hành"]
    G --> H["Dọn dữ liệu/versions test"]
~~~

Ví dụ một phép kiểm tra logic của test:

~~~java
String key = storage.upload(
        new java.io.ByteArrayInputStream("abc".getBytes(
                java.nio.charset.StandardCharsets.UTF_8)),
        3L,
        "text/plain");

var metadata = storage.head(key);
if (metadata.contentLength() != 3L) {
    throw new AssertionError("Sai kích thước object");
}

var target = new java.io.ByteArrayOutputStream();
storage.downloadTo(key, target);

if (!java.util.Arrays.equals(
        target.toByteArray(),
        "abc".getBytes(java.nio.charset.StandardCharsets.UTF_8))) {
    throw new AssertionError("Nội dung tải về không khớp");
}

storage.delete(key);
~~~

Mẫu trên minh họa logic end-to-end; trong test thật hãy dùng framework assertion, tài nguyên sandbox riêng, dọn dữ liệu bằng `finally`/teardown và xử lý đúng trường hợp bật versioning. Tránh dùng bucket production cho integration test. Không chạy test xóa với key thực từ người dùng.

### Những trường hợp âm nên bổ sung

- PUT với stream có kích thước khai báo sai hoặc file vượt giới hạn ứng dụng.
- GET/DELETE với key không được ứng dụng cho phép, dù role backend có thể truy cập.
- LIST phân trang khi có trên 1.000 object và khi prefix rỗng.
- HEAD trên key không tồn tại với role có hoặc không có `s3:ListBucket`.
- PUT lại cùng key để hiểu ghi đè và cách versioning lưu lịch sử.
- Lỗi tạm thời và retry khi app mất mạng giữa upload/download.

## 10. Liên hệ với Azure Blob Storage và Google Cloud Storage

Khi xây dựng module tích hợp nhiều cloud provider, thao tác nghiệp vụ thường tương đương nhưng API, danh tính và mô hình quyền khác nhau.

| Nhu cầu | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Upload | `PutObject` | Upload blob | Upload/create object |
| Download | `GetObject` | Download blob | Read object |
| List | `ListObjectsV2` với prefix + continuation token | List blobs với continuation | List objects với paging |
| Delete | `DeleteObject` | Delete blob | Delete object |
| Định danh | Bucket + object key | Storage account + container + blob name | Bucket + object name |
| Danh tính | IAM role/SDK credentials | Managed identity/Azure RBAC | Service account/Google IAM |
| URL ngắn hạn | Presigned URL | SAS | Signed URL |

Các bước nghiệp vụ có thể dùng abstraction riêng của ứng dụng:

~~~java
public interface ObjectStoragePort {
    String upload(InputStream source, long length, String mediaType);

    void downloadTo(String objectKey, OutputStream destination)
            throws IOException;

    void delete(String objectKey);
}
~~~

Đây là hợp đồng minh họa; cách liệt kê, metadata, versioning và error mapping có thể cần interface riêng nếu các cloud khác nhau về ngữ nghĩa. Adapter AWS triển khai với `S3Client` hoặc `S3Template`, adapter Azure/GCP dùng SDK của provider tương ứng. **Không cố giả định** tất cả provider có chung policy model, token phân trang, semantics của delete hoặc tên các thuộc tính cấu hình Spring.

## 11. Bài tập thực hành

**Bài 1 — PUT/GET cơ bản.** Trong một bucket sandbox private, tạo endpoint nhận tệp văn bản nhỏ. Backend tạo UUID key, upload lên S3, lưu key vào bảng tài liệu thử nghiệm. Tải lại bằng ID nghiệp vụ (sau khi kiểm tra quyền) và so sánh hash nội dung. Giải thích vì sao không trả tùy ý một key do người dùng yêu cầu.

**Bài 2 — Metadata và streaming.** Upload tệp lớn hơn vài MB bằng stream, đặt `Content-Type` phù hợp; gọi HEAD để xác minh `Content-Length`. So sánh bộ nhớ khi dùng `RequestBody.fromBytes` với thiết kế streaming và trình bày khi nào nên dùng multipart.

**Bài 3 — Liệt kê qua nhiều trang.** Tạo nhiều object dưới `documents/lab-<uuid>/`, dùng `maxKeys=10` để duyệt nhiều trang. Kiểm tra `nextContinuationToken` và thử `delimiter("/")`. Giải thích tại sao LIST không phải API tìm kiếm theo metadata nghiệp vụ.

**Bài 4 — DELETE và Versioning.** Trong bucket test riêng, bật versioning, PUT hai lần cùng key rồi DELETE không kèm version ID. Quan sát delete marker và các version trước đó. Làm rõ điều kiện cấp quyền `s3:DeleteObjectVersion` nếu muốn dọn phiên bản test.

**Bài 5 — Giới hạn quyền.** Tạo role chỉ có `s3:GetObject`, thử LIST và DELETE. Ghi lại lỗi. Sau đó so sánh với role được cấp `s3:ListBucket` cho prefix và quyền GET/PUT/DELETE trên object ARN tương ứng.

### Câu hỏi tự kiểm tra

1. Phân biệt PUT mới và PUT lên cùng bucket/key đã tồn tại.
2. Tại sao `RequestBody.fromInputStream` cần kích thước byte chính xác?
3. Vì sao cần đóng `ResponseInputStream` sau GET?
4. `HEAD` khác `GET` và `LIST` ở dữ liệu trả về và quyền IAM như thế nào?
5. `nextContinuationToken` có phải object key hay số trang không?
6. DELETE không có version ID làm gì khi bucket đã bật Versioning?
7. Vì sao kết quả DELETE thành công không chứng minh object đã tồn tại trước đó?
8. Làm sao tránh xóa S3 thành công nhưng cập nhật database thất bại?
9. Tại sao ứng dụng nên kiểm tra quyền người dùng dù IAM role đã cho phép `s3:GetObject`?
10. Bài kiểm thử local emulator còn thiếu những xác minh nào nên làm trên AWS sandbox thật?

Kết thúc bài này, bạn có thể triển khai và giải thích luồng **PUT → HEAD/GET → LIST → DELETE** trong Spring Boot, hiểu ngữ nghĩa của từng thao tác S3 và thiết kế các giới hạn an toàn cần thiết khi đưa object storage vào hệ thống có dữ liệu thật.

