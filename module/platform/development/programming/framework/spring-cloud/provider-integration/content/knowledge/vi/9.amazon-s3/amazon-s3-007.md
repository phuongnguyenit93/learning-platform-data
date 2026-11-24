# Amazon S3: Mã hóa, versioning và vòng đời đối tượng

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, ứng dụng Spring Boot được tích hợp với các dịch vụ managed của AWS, Azure và Google Cloud để xử lý storage, messaging, dữ liệu, quản lý secret, danh tính và quyền. Với **Amazon S3**, lưu một object thành công mới chỉ là bước đầu: hệ thống còn phải biết object **được mã hóa bằng khóa nào**, **có thể khôi phục phiên bản cũ nếu ghi đè/xóa nhầm không**, và **bao lâu thì dữ liệu được chuyển lớp lưu trữ hoặc hết hạn**.

Bài học tập trung vào ba cơ chế:

1. **Encryption:** bảo vệ nội dung khi truyền và khi lưu, phân biệt SSE-S3, SSE-KMS, DSSE-KMS, SSE-C và mã hóa phía client.
2. **Versioning:** giữ các phiên bản của cùng object key, hiểu version ID, delete marker, khôi phục và xóa phiên bản.
3. **Lifecycle:** tự động chuyển storage class, expire object, quản lý noncurrent versions và dọn multipart upload chưa hoàn tất.

Kết thúc bài học, bạn có thể cấu hình Spring Boot + Spring Cloud AWS để PUT object với SSE-KMS, đọc thông tin mã hóa/phiên bản, thiết kế chính sách lifecycle có kiểm soát, giải thích quyền IAM/KMS và kiểm thử phục hồi trên AWS sandbox.

> **Phạm vi:** Ví dụ dùng AWS SDK for Java v2 (package `software.amazon.awssdk`) và Spring Cloud AWS hiện đại (namespace `io.awspring.cloud`). Chọn phiên bản tương thích với bản Spring Boot đang dùng. Bucket, object và KMS ARN trong tài liệu chỉ là dữ liệu minh họa.

## 1. Ba cơ chế giải quyết ba vấn đề khác nhau

Một object S3 được định danh bằng **bucket + key**, và có **version ID** nếu bucket bật Versioning. Encryption áp dụng cho byte dữ liệu, Versioning quản lý lịch sử còn Lifecycle xử lý dữ liệu theo thời gian.

~~~mermaid
flowchart TD
    API["Spring Boot API"] -->|"HTTPS, AWS SDK + IAM role"| S3["S3 bucket private"]
    KMS["SSE-S3 / AWS KMS key"] -->|"Mã hóa dữ liệu at rest"| S3
    S3 --> V1["reports/a.pdf · version v1"]
    S3 --> V2["reports/a.pdf · version v2"]
    S3 --> DM["reports/a.pdf · delete marker v3"]
    LIFE["Lifecycle rules"] -->|"Transition/expiration"| V1
    LIFE -->|"Transition/expiration"| V2
    LOCK["Object Lock/retention (nếu dùng)"] -->|"Hạn chế xóa version"| V1
~~~

| Nhu cầu | Cơ chế chính | Giới hạn |
| --- | --- | --- |
| Bảo vệ byte đang truyền | HTTPS/TLS | TLS không thay thế mã hóa khi lưu |
| Mã hóa khi lưu | SSE-S3, SSE-KMS, DSSE-KMS hoặc client-side encryption | Encryption không giữ lịch sử khi object bị xóa |
| Khôi phục bản cũ | S3 Versioning | Không tự ngăn sửa từ dữ liệu cũ hoặc xóa version vĩnh viễn |
| Tự chuyển lớp/xóa theo tuổi | S3 Lifecycle | Không bảo đảm hành động đúng từng giây; không thay thế retention pháp lý |
| Giữ version không thể xóa trong thời hạn | Object Lock/retention/legal hold | Cần chính sách quyền và cấu hình riêng |
| Quyết định ai được đọc/ghi | IAM, bucket policy, KMS policy và quyền nghiệp vụ | Không cơ chế mã hóa nào tự kiểm tra chủ sở hữu của tài liệu |

Ví dụ: một hệ thống hóa đơn yêu cầu **bucket private, SSE-KMS, Versioning, chính sách noncurrent retention và kiểm tra chủ sở hữu**. Những thành phần đó bổ trợ nhau; không có cơ chế đơn lẻ nào đảm bảo toàn bộ tính bảo mật, lịch sử và vòng đời dữ liệu.

## 2. Mã hóa trong khi truyền và lúc lưu

### 2.1. Encryption in transit

Ứng dụng Spring Boot sử dụng **HTTPS/TLS** khi gọi S3. Browser tải tệp qua presigned URL cũng nên dùng HTTPS; URL ký sẵn chứa chữ ký và có thể chứa session token, nên tránh để lộ trong log hay thông báo lỗi.

TLS bảo vệ đường truyền giữa các đầu cuối. Khi byte được S3 ghi vào storage, cơ chế **server-side encryption** bảo vệ nội dung at rest. Hai lớp này bổ sung cho nhau.

### 2.2. Encryption at rest: bảng so sánh

| Chế độ | Khóa do ai quản lý | Sử dụng khi | Lưu ý chính |
| --- | --- | --- | --- |
| **SSE-S3** | S3 quản lý key mã hóa phía server | Nhu cầu mã hóa at rest thông thường | S3 tự động áp dụng cho object mới theo mặc định |
| **SSE-KMS** | AWS KMS key do AWS hoặc khách hàng quản lý tùy lựa chọn | Cần key policy, audit và khả năng kiểm soát dùng khóa | Quyền S3 và quyền KMS có thể cùng cần thiết |
| **DSSE-KMS** | Hai lớp server-side encryption tích hợp KMS | Yêu cầu tuân thủ/kiểm soát cao hơn | Cần xác nhận hỗ trợ, quyền KMS và chi phí |
| **SSE-C** | Người gọi cung cấp key cho S3 trên các request liên quan | Trường hợp đặc biệt có quy trình quản lý khóa riêng | Client phải giữ khóa an toàn để giải mã sau này |
| **Client-side encryption** | Ứng dụng mã hóa trước khi truyền | Cần bảo vệ byte trước khi dữ liệu rời ứng dụng | Quản lý khóa, thuật toán, khả năng đọc/khôi phục tại ứng dụng |

Từ năm 2023, S3 tự động mã hóa phía server bằng **SSE-S3 (AES-256)** cho object mới nếu không yêu cầu chế độ khác. Vì vậy **không gửi header yêu cầu SSE-KMS** không đồng nghĩa dữ liệu mới mặc nhiên là plaintext trên storage. Tuy nhiên, yêu cầu bảo mật hoặc compliance có thể đòi khóa customer-managed trong KMS.

**SSE-KMS không đồng nghĩa dữ liệu đã được mã hóa ở phía Spring Boot trước khi upload.** S3 thực hiện mã hóa phía server; nếu cần mã hóa trước khi rời ứng dụng, phải thiết kế client-side encryption riêng.

### 2.3. SSE-KMS và quyền sử dụng khóa

Khi dùng SSE-KMS, một request PUT/GET phải vượt qua nhiều tầng:

~~~mermaid
flowchart LR
    APP["Spring Boot IAM role"] --> IAM["S3 identity/bucket policy"]
    IAM --> S3["S3 PutObject / GetObject"]
    S3 --> KMS["KMS key policy + IAM/grant"]
    KMS --> RESULT["Mã hóa / giải mã được phép"]
~~~

Các quyền thường cần:

- **PUT với SSE-KMS:** `s3:PutObject` và `kms:GenerateDataKey` trên KMS key tương ứng.
- **GET SSE-KMS:** `s3:GetObject` và `kms:Decrypt` khi cần giải mã.
- **Multipart upload, CopyObject hoặc một số trường hợp checksum:** có thể cần thêm `kms:Decrypt`/`kms:GenerateDataKey` tùy thao tác và cấu hình.
- **KMS key policy:** nếu dùng customer-managed KMS key, key policy hoặc grant phải cho phép principal sử dụng khóa; IAM allow riêng chưa chắc đủ.

Key dùng cho SSE-KMS cần phù hợp **Region** của bucket. Nếu KMS key bị vô hiệu hóa, bị lên lịch xóa hoặc chính sách bị sửa, object đã lưu có thể không đọc được dù phiên bản object vẫn còn.

**S3 Bucket Keys** có thể giảm request tới KMS và chi phí khi dùng SSE-KMS theo các điều kiện hỗ trợ, nhưng ảnh hưởng cách S3 sử dụng encryption context. Nếu dự án có policy phụ thuộc encryption context, cần kiểm tra khả năng tương thích trước khi bật.

### 2.4. Khi nào nên chọn SSE-S3, SSE-KMS hoặc client-side encryption?

- Chọn **SSE-S3** khi yêu cầu chính là mã hóa at rest tiêu chuẩn và muốn vận hành đơn giản.
- Chọn **SSE-KMS với customer-managed key** khi cần key policy, kiểm soát principal sử dụng key, audit hoặc tuân thủ riêng.
- Chọn **DSSE-KMS** chỉ khi có yêu cầu rõ ràng và đã xác nhận phí, quyền cùng giới hạn hỗ trợ.
- Chọn **client-side encryption** nếu dữ liệu phải được mã hóa **trước khi rời ranh giới ứng dụng**; cần quy trình quản lý/khôi phục khóa độc lập.
- Chỉ chọn **SSE-C** trong trường hợp đặc biệt đã có thiết kế giữ khóa an toàn; mất khóa có thể khiến dữ liệu không thể giải mã.

Không đưa secret, raw encryption key, session token hoặc dữ liệu nhạy cảm vào user metadata, object key hay log.

## 3. Tích hợp Spring Boot với SSE-KMS

### 3.1. Dependency và cấu hình

Spring Cloud AWS starter cho S3 giúp cấu hình AWS SDK v2 `S3Client` để inject vào Spring service. Với Maven:

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

`spring-cloud-aws.version` là property cần khai báo theo ma trận tương thích với Spring Boot thực tế, không có một phiên bản cố định dùng được cho mọi dự án.

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
    kms-key-arn: ${S3_KMS_KEY_ARN}
~~~

`app.storage.*` là property **do ứng dụng tự đặt tên**. Không hard-code access key/secret key: AWS SDK có default credentials provider chain (AWS profile/SSO khi local, IAM role hoặc workload identity trong môi trường triển khai).

### 3.2. Identity policy minh họa

Ví dụ role có quyền đọc/ghi tài liệu và sử dụng KMS key thử nghiệm:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadWriteDocuments",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:GetObjectVersion"
      ],
      "Resource": "arn:aws:s3:::training-private-files/documents/*"
    },
    {
      "Sid": "UseDocumentEncryptionKey",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/EXAMPLE-KEY-ID"
    }
  ]
}
~~~

Thay bucket, account, key ARN bằng giá trị của sandbox. Với **customer-managed KMS key**, key policy/grant cũng phải cho phép hành động. Role trên **không** có quyền quản trị bucket như `s3:PutBucketVersioning`, `s3:PutLifecycleConfiguration` hoặc quyền xóa vĩnh viễn version `s3:DeleteObjectVersion`; nên tách các quyền vận hành đó khỏi API upload/download.

### 3.3. Upload với SSE-KMS qua `S3Client`

~~~java
import java.io.InputStream;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;
import software.amazon.awssdk.services.s3.model.ServerSideEncryption;

@Service
public class EncryptedDocumentStorage {
    private final S3Client s3;
    private final String bucket;
    private final String kmsKeyArn;

    public EncryptedDocumentStorage(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket,
            @Value("${app.storage.kms-key-arn}") String kmsKeyArn) {
        this.s3 = s3;
        this.bucket = bucket;
        this.kmsKeyArn = kmsKeyArn;
    }

    public record StoredObject(
            String key, String versionId, String eTag) {}

    public StoredObject upload(
            InputStream source, long exactLength,
            String verifiedContentType) {

        if (exactLength < 0) {
            throw new IllegalArgumentException("Độ dài không hợp lệ");
        }

        String key = "documents/" + UUID.randomUUID();

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(verifiedContentType)
                .serverSideEncryption(ServerSideEncryption.AWS_KMS)
                .ssekmsKeyId(kmsKeyArn)
                .build();

        PutObjectResponse response = s3.putObject(
                request,
                RequestBody.fromInputStream(source, exactLength));

        return new StoredObject(
                key,
                response.versionId(),
                response.eTag());
    }
}
~~~

Đoạn code minh họa các đặc điểm:

1. **Key do backend phát sinh**; client không được chỉ định key tùy ý. Quan hệ user/tenant → documentId → key phải lưu ở database sau khi kiểm tra quyền.
2. `serverSideEncryption(AWS_KMS)` yêu cầu SSE-KMS, còn `ssekmsKeyId` chọn key.
3. `RequestBody.fromInputStream` đòi **số byte chính xác**. Caller phải giữ stream còn mở trong suốt PUT và đóng stream sau khi dùng.
4. `response.versionId()` có giá trị hữu ích khi S3 trả version ID. Với bucket chưa bật versioning, không giả định có version ID được sinh như bucket đã bật.
5. `ETag` không luôn là MD5 của nội dung (đặc biệt với multipart/mã hóa). Dùng checksum được hỗ trợ nếu cần kiểm tra toàn vẹn byte.

Với file lớn, hãy dùng streaming/multipart upload hay presigned URL phù hợp; tránh `getBytes()` để giữ toàn bộ file vào RAM.

### 3.4. Đọc metadata mã hóa bằng HEAD

~~~java
var info = s3.headObject(b -> b
        .bucket(bucket)
        .key("documents/example.pdf"));

System.out.println("Encryption: " + info.serverSideEncryptionAsString());
System.out.println("KMS key: " + info.ssekmsKeyId());
System.out.println("Version ID: " + info.versionId());
System.out.println("Content-Type: " + info.contentType());
~~~

`HeadObject` đọc metadata mà không tải body, nhưng vẫn là request mạng. Với object SSE-S3/SSE-KMS thông thường, **không gửi request header x-amz-server-side-encryption trên GET/HEAD**; header yêu cầu mã hóa này thường thuộc thao tác PUT/ghi.

### 3.5. Default encryption ở bucket và thay khóa

Một cách vận hành khác là cấu hình **default bucket encryption** bằng IaC/admin (ví dụ SSE-KMS với key tổ chức). Khi đó PUT không cần chỉ định mode trên mỗi request, miễn là bucket policy và quyền phù hợp.

Cần nhớ:

- Đổi default encryption của bucket chỉ định cách xử lý **những lần ghi tiếp theo**; object cũ **không tự động** được mã hóa lại bằng key mới.
- Muốn chuyển object đã lưu sang cấu hình khóa mới, cần copy/rewrite hoặc batch process phù hợp và xác minh sau khi hoàn tất.
- Nếu bucket policy bắt buộc request có **header SSE-KMS tường minh**, PUT không có header vẫn có thể bị **Deny**, ngay cả khi default encryption của bucket đã đặt SSE-KMS. Đừng nhầm giữa `có header` và `object cuối cùng được mã hóa`.
- Khi copy/multipart, phải xem xét quyền giải mã ở source key và quyền tạo data key ở destination KMS key.

## 4. S3 Versioning: ba trạng thái và ngữ nghĩa

### 4.1. Unversioned, Enabled, Suspended

| Trạng thái | Hành vi khi PUT cùng key | Hành vi khi DELETE key thông thường |
| --- | --- | --- |
| **Unversioned** (chưa bật) | Object hiện hành thường bị thay | Object bị xóa |
| **Enabled** | Tạo version ID mới; version cũ thường còn | Tạo **delete marker** làm object hiện hành bị che |
| **Suspended** | Có quy tắc riêng liên quan **null version**, không tiếp tục sinh version ID mới như Enabled | Có hành vi đặc biệt với null version/delete marker |

Khi bucket đã bật Versioning, có thể **suspend**, nhưng không trở lại hoàn toàn như bucket chưa từng bật. Các version trước đó vẫn tồn tại nếu chưa bị xóa hoặc lifecycle xử lý.

### 4.2. Dòng thời gian của một object

~~~text
T0 PUT documents/a.pdf  → version v1 (current)
T1 PUT documents/a.pdf  → version v2 (current), v1 cũ
T2 DELETE key           → delete marker v3 (current)

GET key                  → thông thường không thấy object current
GET key, versionId=v1    → nội dung cũ v1, nếu có quyền
GET key, versionId=v2    → nội dung v2, nếu có quyền
DELETE versionId=v3      → xóa marker, v2 có thể lại thành current
DELETE versionId=v1      → xóa phiên bản v1 thực sự
~~~

~~~mermaid
flowchart LR
    A["PUT v1"] --> B["v1: dữ liệu cũ"]
    C["PUT v2"] --> D["v2: dữ liệu mới"]
    E["DELETE key"] --> F["v3: delete marker"]
    F -->|"GET key mặc định"| G["Không thấy object hiện hành"]
    B -->|"GET versionId=v1"| H["Đọc được v1 nếu đủ quyền"]
    D -->|"GET versionId=v2"| I["Đọc được v2 nếu đủ quyền"]
~~~

**Delete marker không chứa lại nội dung object.** Nó che view hiện hành của key. Phiên bản v1/v2 vẫn có thể tiêu thụ lưu trữ và chi phí. **DELETE kèm version ID** lại là thao tác xóa phiên bản cụ thể, cần quyền riêng và có thể không khôi phục được nếu không có backup/replica.

### 4.3. Bật versioning trên bucket sandbox

~~~bash
aws s3api put-bucket-versioning \
  --bucket training-private-files \
  --versioning-configuration Status=Enabled

aws s3api get-bucket-versioning \
  --bucket training-private-files
~~~

Lệnh minh họa chỉ dùng trong **sandbox riêng** và cần quyền như `s3:PutBucketVersioning`. Không tự động bật/tắt versioning khi mỗi instance Spring Boot khởi động. Sau khi bật lần đầu, cần kiểm tra trạng thái đã ổn định trước những thao tác ghi/xóa nhạy cảm.

### 4.4. Version ID và ETag khác nhau thế nào?

| Thuộc tính | Mục đích | Không nên suy diễn |
| --- | --- | --- |
| `versionId` | Định danh version cụ thể trong bucket versioned | Không phải số thứ tự hay timestamp |
| `ETag` | Tham chiếu đến trạng thái object/điều kiện If-Match | Không luôn bằng MD5, không đồng nghĩa version ID |
| `Last-Modified` | Thông tin thời gian lưu/sửa | Không bảo đảm optimistic locking |
| `Checksum` | Kiểm tra toàn vẹn byte | Không thay thế quyền ứng dụng |

**Versioning không tự chống lost update.** Hai người cùng sửa bản A có thể lần lượt PUT B và C, khiến C trở thành current dù B vẫn được lưu ở lịch sử. Khi cần chống ghi đè logic, dùng conditional PUT (`If-Match`) hoặc optimistic locking ở database và cân nhắc key bất biến cho mỗi revision.

## 5. Đọc và khôi phục version trong AWS SDK v2

### 5.1. Liệt kê các version và delete marker

`ListObjectsV2` chủ yếu liệt kê object hiện hành. Muốn xem lịch sử, sử dụng **`ListObjectVersions`**:

~~~java
import software.amazon.awssdk.services.s3.model.ListObjectVersionsRequest;

String key = "documents/example.pdf";

var response = s3.listObjectVersions(
        ListObjectVersionsRequest.builder()
                .bucket(bucket)
                .prefix(key)
                .build());

response.versions().stream()
        .filter(v -> key.equals(v.key()))
        .forEach(v -> System.out.println(
                "version=" + v.versionId()
                + " latest=" + v.isLatest()
                + " eTag=" + v.eTag()));

response.deleteMarkers().stream()
        .filter(m -> key.equals(m.key()))
        .forEach(m -> System.out.println(
                "marker=" + m.versionId()
                + " latest=" + m.isLatest()));
~~~

Đây chỉ là **một trang** response. Nếu object có nhiều version, cần duyệt các trang bằng cặp marker `keyMarker`/`versionIdMarker` hoặc paginator hỗ trợ; không giả định trang đầu chứa toàn bộ lịch sử.

Các quyền thường liên quan:

- `s3:ListBucketVersions` trên **bucket ARN** khi LIST versions.
- `s3:GetObjectVersion` trên **object ARN** khi GET một version cụ thể.
- `s3:DeleteObjectVersion` trên **object ARN** khi xóa version cụ thể.
- `s3:GetObject` và `s3:DeleteObject` là quyền riêng cho thao tác thông thường.

### 5.2. Download phiên bản cũ theo version ID

~~~java
import java.io.IOException;
import java.io.OutputStream;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public void downloadVersion(
        S3Client s3,
        String bucket,
        String authorizedKey,
        String trustedVersionId,
        OutputStream target) throws IOException {

    // Tầng nghiệp vụ đã xác minh documentId, owner/tenant và version.
    var request = GetObjectRequest.builder()
            .bucket(bucket)
            .key(authorizedKey)
            .versionId(trustedVersionId)
            .build();

    try (var input = s3.getObject(request)) {
        input.transferTo(target);
    }
}
~~~

Với bucket SSE-KMS, còn cần quyền KMS phù hợp. Không cho người dùng tự gửi key/version ID của người khác dù IAM role backend có thể GET được.

### 5.3. Khôi phục một version cũ

Có thể **xóa delete marker hiện hành** để version trước hiện lại, nhưng thao tác xóa marker thay đổi lịch sử và đòi quyền xóa version. Một lựa chọn thuận tiện cho audit là **tạo một version mới từ nội dung version cũ**, giữ lại lịch sử trước đó.

Ví dụ minh họa cho tệp nhỏ:

~~~java
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

var oldContent = s3.getObjectAsBytes(
        GetObjectRequest.builder()
                .bucket(bucket)
                .key("documents/example.txt")
                .versionId(approvedOldVersionId)
                .build());

var result = s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key("documents/example.txt")
                .contentType("text/plain; charset=UTF-8")
                .build(),
        RequestBody.fromBytes(oldContent.asByteArray()));

System.out.println("New version ID = " + result.versionId());
~~~

Mẫu code tải hết nội dung vào RAM **chỉ dùng cho file nhỏ**. Với file lớn, dùng stream/copy phù hợp; cần giữ metadata, tags, Content-Type và cấu hình SSE-KMS theo yêu cầu. Nếu cần chống ghi đè một bản mới khác đang được sửa, dùng conditional write/optimistic locking thay vì PUT vô điều kiện.

## 6. S3 Lifecycle quản lý những hành động nào?

**S3 Lifecycle** cho phép thiết lập rule tại bucket để dịch vụ tự đánh giá tuổi object/phiên bản và quyết định chuyển storage class, expire hoặc dọn upload bỏ dở.

| Hành động | Tài nguyên mục tiêu | Kết quả |
| --- | --- | --- |
| **Transition** | Current object | Chuyển sang storage class khác khi đủ điều kiện |
| **Expiration** | Current object | Với bucket versioned thường thêm delete marker; với bucket unversioned có thể xóa object |
| **NoncurrentVersionTransition** | Các version không còn current | Chuyển lớp lưu trữ version cũ |
| **NoncurrentVersionExpiration** | Các version không còn current | Xóa version cũ khi đủ điều kiện; có thể mất khả năng restore |
| **AbortIncompleteMultipartUpload** | Multipart upload chưa Complete | Dọn các part dang dở, giảm chi phí |
| **ExpiredObjectDeleteMarker** | Delete marker hết ý nghĩa theo quy tắc | Dọn marker khi không còn version khác theo điều kiện dịch vụ |

Lifecycle filter có thể dựa vào **prefix**, tags hoặc kết hợp các điều kiện được API hỗ trợ. Không nhầm Lifecycle với job Java xóa chính xác từng giây; S3 xử lý các quy tắc bất đồng bộ.

### 6.1. Storage class: chi phí và thời gian khôi phục

| Storage class | Khi nào dùng | Cần cân nhắc |
| --- | --- | --- |
| **S3 Standard** | Truy cập thường xuyên | Giá lưu trữ cho mức truy cập đó |
| **S3 Standard-IA** | Ít truy cập, cần truy xuất nhanh | Phí retrieval và thời gian lưu tối thiểu |
| **S3 One Zone-IA** | Dữ liệu tái tạo được hoặc chấp nhận mô hình 1 AZ | Không phù hợp bản sao duy nhất cần bảo vệ nhiều AZ |
| **S3 Intelligent-Tiering** | Mẫu truy cập khó dự đoán | Phí giám sát/tier theo quy định |
| **S3 Glacier Instant Retrieval** | Archive ít truy cập nhưng vẫn cần đọc nhanh | Phí retrieval và thời gian tối thiểu |
| **S3 Glacier Flexible Retrieval** | Archive có thể chờ restore | Cần quy trình restore trước khi truy cập |
| **S3 Glacier Deep Archive** | Lưu dài hạn, hiếm đọc | Thời gian restore và chi phí theo tier |

Chuyển lớp **không luôn tiết kiệm cho mọi object nhỏ** vì có ràng buộc minimum duration, request fee và xử lý object dưới ngưỡng kích thước. Lựa chọn phải dựa trên thời gian giữ dữ liệu, khả năng phục hồi, chi phí đọc và phân loại dữ liệu.

### 6.2. Lifecycle không phải đồng hồ xóa chính xác

Rule `Expiration after 7 days` biểu thị khi object trở nên **đủ điều kiện** để expire theo cách S3 tính ngày/tuổi, không có nghĩa S3 hứa xóa đúng mili giây của ngày thứ 7. Vì vậy:

- Không dùng lifecycle để thực thi link hết hạn theo user/session chính xác một thời điểm.
- Nếu API cần chặn đọc ngay, kiểm tra quyền/thời gian tại tầng nghiệp vụ.
- Rule mới có thể áp dụng cho object **đã tồn tại** đủ điều kiện, không chỉ object upload về sau.
- Với Versioning, cần phân biệt **current expiration** và **noncurrent expiration** trước khi quyết định rule.

## 7. Ví dụ Lifecycle policy trong sandbox

Giả sử bucket có:

~~~text
incoming/      # File upload chưa được xác minh
documents/     # File nghiệp vụ đã được chấp nhận
reports/       # Báo cáo ít truy cập sau thời gian đầu
~~~

Cấu hình minh họa dạng JSON cho AWS CLI `put-bucket-lifecycle-configuration`:

~~~json
{
  "Rules": [
    {
      "ID": "AbortIncompleteIncoming",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "incoming/"
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    },
    {
      "ID": "ExpireTemporaryIncoming",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "incoming/"
      },
      "Expiration": {
        "Days": 14
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      }
    },
    {
      "ID": "MoveOldReportsToIA",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "reports/"
      },
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "STANDARD_IA"
        }
      ],
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 365
      }
    }
  ]
}
~~~

**Ý nghĩa:**

- Multipart upload trong `incoming/` chưa Complete sau 7 ngày có thể được abort.
- Current object thuộc `incoming/` đủ điều kiện expiration sau 14 ngày; noncurrent versions của chúng được xét xóa theo `NoncurrentDays = 30`.
- Current object thuộc `reports/` có thể chuyển Standard-IA sau 90 ngày; noncurrent versions được giữ theo rule 365 ngày.
- `documents/` chưa có rule expire trong ví dụ, để tránh vô tình xóa tài liệu nghiệp vụ cần giữ.

**Đây không phải policy áp dụng production ngay.** Lifecycle có thể tác động lên dữ liệu cũ đang nằm dưới prefix tương ứng. Phải kiểm kê dữ liệu, xác minh thời hạn pháp lý, quota, số noncurrent versions và thử nghiệm trên bucket sandbox.

### 7.1. Current Expiration với Versioning

Ví dụ bucket bật Versioning:

~~~text
PUT documents/a.pdf  → v1
PUT documents/a.pdf  → v2 (current)
Lifecycle Expiration đủ điều kiện
                     → delete marker (current)

v1 và v2 có thể vẫn được lưu dưới dạng noncurrent versions.
~~~

Để thực sự loại bỏ byte lịch sử, cần **NoncurrentVersionExpiration** hoặc thao tác xóa version riêng. Với bucket chưa bật Versioning, Expiration có thể xóa object hiện hành. Với trạng thái **Suspended**, cách xử lý null version/delete marker cần kiểm tra riêng.

### 7.2. Incomplete multipart upload

Multipart upload đi qua `CreateMultipartUpload → UploadPart → CompleteMultipartUpload`; nếu process chết trước Complete hoặc Abort, các part đã truyền chưa trở thành object hoàn chỉnh nhưng vẫn có thể tính phí. Rule `AbortIncompleteMultipartUpload` là lớp cleanup phía dịch vụ.

Điều này **không xóa object đã Complete**. Nếu ứng dụng hỗ trợ resume upload kéo dài nhiều ngày, thời hạn abort phải đủ dài để không làm mất phiên upload hợp lệ.

## 8. Object Lock, retention và legal hold

**Versioning không đồng nghĩa dữ liệu bất biến (immutable).** Một principal có quyền `s3:DeleteObjectVersion` vẫn có thể xóa version, trừ khi bị Object Lock, policy hoặc cơ chế bảo vệ khác ngăn.

**S3 Object Lock** cung cấp retention/legal hold cho **version cụ thể** và yêu cầu bucket có versioning phù hợp. Các chế độ:

- **Governance mode:** dữ liệu được bảo vệ nhưng principal có quyền đặc biệt và thao tác phù hợp có thể được phép bypass trong điều kiện xác định.
- **Compliance mode:** version được bảo vệ không thể giảm hoặc bỏ thời hạn retention bằng thao tác quản trị thông thường trước khi hết hạn.
- **Legal hold:** giữ version cho đến khi hold được gỡ bởi principal có quyền; độc lập với ngày retention.

Lifecycle không phải công cụ để vượt Object Lock. Một version có retention hoặc legal hold còn hiệu lực không thể đơn giản bị xóa chỉ vì rule NoncurrentVersionExpiration đã tới hạn.

Nếu dữ liệu chịu chính sách lưu trữ bắt buộc, cần xác nhận với nhóm phụ trách retention/compliance trước khi cấu hình expiration. Đặt nhầm rule xóa noncurrent versions có thể làm mất bản lưu cần giữ; đặt retention quá dài có thể làm chi phí tăng và hạn chế khả năng xóa hợp lệ.

## 9. Đánh giá chi phí, khôi phục và rủi ro vận hành

### 9.1. Versioning làm tăng dữ liệu lưu

~~~text
PUT reports/a.pdf 20 MiB → version v1
PUT reports/a.pdf 20 MiB → version v2
PUT reports/a.pdf 20 MiB → version v3

Khi cả ba version còn tồn tại, nội dung lưu có thể
xấp xỉ 60 MiB (chưa tính overhead/cấu hình riêng).
~~~

PUT phiên bản mới **không được hiểu** chỉ lưu phần chênh lệch với bản cũ. Noncurrent versions có thể tích lũy rất nhanh khi tài liệu bị thay thường xuyên.

### 9.2. Encryption có những chi phí và rủi ro riêng

- **KMS:** key charges và request usage, giới hạn throughput, quyền key policy; có thể dùng S3 Bucket Keys khi phù hợp.
- **Key rotation/change:** không đồng nghĩa toàn bộ object cũ tự được re-encrypt bằng key mới.
- **Khả năng khôi phục:** có version ID chưa đủ nếu KMS key bị vô hiệu hóa, key policy chặn hoặc không còn quyền decrypt.
- **Data transfer:** mã hóa không loại bỏ chi phí truyền dữ liệu giữa Region hoặc ra ngoài.

### 9.3. Lifecycle cần đối chiếu mục tiêu phục hồi

Khi chọn retention, hãy trả lời: “Nếu khách hàng phát hiện ghi đè/xóa nhầm sau **45 ngày**, có còn version để restore hay không?” Nếu NoncurrentVersionExpiration đang xóa version sau 30 ngày, mục tiêu phục hồi 45 ngày **không đạt**.

Versioning có ích cho recovery, nhưng **không thay thế backup/disaster recovery đầy đủ**. Cần cân nhắc Object Lock, replication/bản sao độc lập, quyền xóa tối thiểu, retention được kiểm thử và phương án phục hồi khi lỗi KMS, policy hoặc vùng lưu trữ.

## 10. Kiểm thử tích hợp Spring Boot với S3

### 10.1. Ba tầng kiểm thử

| Tầng | Nên xác minh | Giới hạn |
| --- | --- | --- |
| Unit test với mock SDK | Request có SSE-KMS/key ARN đúng; version ID được lưu; kiểm tra quyền trước GET version | Không chứng minh S3 mã hóa hoặc KMS policy thực |
| S3-compatible emulator | PUT/GET/HEAD, Versioning và delete marker nếu emulator hỗ trợ | KMS, Object Lock, lifecycle timing và IAM có thể khác AWS |
| AWS sandbox | SSE-KMS thật, IAM/KMS policy, versioning, lifecycle, restore và retention | Cần tài nguyên test riêng; lifecycle bất đồng bộ và có chi phí |

### 10.2. Lab từng bước

1. Tạo bucket sandbox private, bật Block Public Access và cấu hình default SSE-KMS bằng KMS key thử nghiệm.
2. Dùng IAM role test có quyền tối thiểu; gọi PUT một object và xác nhận `HeadObject.serverSideEncryption` cùng KMS key.
3. Bật Versioning; PUT hai lần vào cùng key với byte khác nhau, lưu `versionId` của từng PUT.
4. Gọi `ListObjectVersions` và GET từng version để so sánh byte.
5. DELETE key **không chỉ định version ID** trong sandbox để quan sát delete marker; sau đó khôi phục một version cũ thành version mới.
6. Thử đọc object SSE-KMS với principal thiếu `kms:Decrypt` để hiểu sự khác biệt giữa S3 permission và KMS permission.
7. Cấu hình Lifecycle rule chỉ dành cho một prefix thử nghiệm; quan sát trạng thái và điều kiện, **không kỳ vọng expire đúng ngay thời điểm đặt rule**.
8. Tạo multipart upload bỏ dở và thử Abort/cleanup trên bucket test; dọn mọi object/version và tài nguyên sau thực hành.
9. Thử thay đổi default encryption của bucket, rồi kiểm tra **object cũ** để chứng minh rằng việc thay default không tự re-encrypt dữ liệu tồn tại từ trước.

### 10.3. Negative cases cần đặt câu hỏi

- IAM role có `s3:GetObject` nhưng không có quyền KMS cần thiết: GET SSE-KMS sẽ thế nào?
- Customer-managed KMS key sai Region, key disabled hoặc key policy từ chối: biểu hiện khi PUT/GET ra sao?
- User A cung cấp version ID của tài liệu tenant B: tầng Spring Boot có chặn trước khi gọi S3 không?
- Expiration cho version hiện hành khác NoncurrentVersionExpiration thế nào sau khi có delete marker?
- Nếu Versioning Suspended, có null version hay hành vi khác cần lưu ý?
- Object Lock/legal hold có bảo vệ version khỏi xóa trong khoảng retention không?
- Khi thay encryption bucket, các object cũ được kiểm tra/migrate bằng cách nào?

## 11. So sánh Azure Blob Storage và Google Cloud Storage

Khi triển khai module **SPRING_CLOUD_PROVIDER_INTEGRATION** trên nhiều cloud, một số khái niệm tương đồng nhưng quyền, tên thuộc tính và semantics khác nhau.

| Nhu cầu | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Encryption at rest mặc định | SSE-S3 | Mã hóa phía dịch vụ theo cấu hình mặc định | Server-side encryption mặc định |
| Khóa khách hàng quản lý | SSE-KMS + AWS KMS | Customer-managed key qua Azure Key Vault/Managed HSM | CMEK qua Cloud KMS |
| Lịch sử object | S3 Versioning và version ID | Blob versioning/snapshots và soft delete theo cấu hình | Object Versioning, generation |
| Tự quản lý vòng đời | S3 Lifecycle | Blob lifecycle management | Cloud Storage Object Lifecycle Management |
| Bảo vệ retention/immutability | S3 Object Lock | Immutable Blob Storage/retention | Retention policies và các chế độ bảo vệ có hỗ trợ |
| Danh tính workload | IAM role, S3/KMS policy | Managed identity và Azure RBAC/Key Vault policy | Service account, IAM và Cloud KMS |

Một domain service có thể định nghĩa hợp đồng chung về upload, đọc revision và retention policy, nhưng adapter mỗi provider phải xử lý chi tiết **key, version ID/generation, role/RBAC, encryption và lifecycle**:

~~~java
public interface VersionedObjectStore {
    StoredVersion upload(
            String trustedKey, java.io.InputStream source,
            long size, String contentType) throws java.io.IOException;

    void downloadVersion(
            String trustedKey, String providerVersionId,
            java.io.OutputStream target) throws java.io.IOException;
}
~~~

`StoredVersion` là kiểu nghiệp vụ tự định nghĩa. Không cho controller tùy ý thay đổi lifecycle/retention trong mỗi HTTP request người dùng. Đây thường là cấu hình quản trị hạ tầng qua IaC hoặc quy trình vận hành được kiểm soát.

## 12. Bài tập thực hành

### Bài A — Chọn encryption phù hợp

Với ba nhóm dữ liệu gồm avatar công khai sau xét duyệt, hợp đồng nội bộ và hồ sơ yêu cầu kiểm soát key/audit riêng, hãy chọn SSE-S3 hay SSE-KMS. Giải thích quyền S3/KMS, TLS và cách ứng dụng phản ứng nếu KMS key không còn dùng được.

### Bài B — Versioning và delete marker

Upload ba phiên bản nội dung của `documents/lab.txt` trong sandbox. Liệt kê version ID, ETag và isLatest; GET từng version. DELETE không kèm version ID rồi mô tả object hiện hành, các version cũ và hai cách khôi phục.

### Bài C — Thiết kế Lifecycle

Một hệ thống muốn xóa file chờ xác minh sau 14 ngày, giữ noncurrent versions của tài liệu trong 180 ngày và chuyển báo cáo ít được đọc sang Standard-IA sau 90 ngày. Viết các rule theo prefix, giải thích current vs noncurrent và cách tránh rule xóa nhầm.

### Bài D — Kiểm thử quyền KMS

Tạo principal thử nghiệm chỉ có `s3:GetObject`, sau đó so sánh GET SSE-S3 và GET SSE-KMS trong sandbox. Chỉ ra các policy/permission cần thay để truy cập đúng object mà không mở rộng quyền không cần thiết.

### Bài E — Đánh giá retention và khôi phục

Khách hàng báo mất dữ liệu sau 45 ngày, nhưng hệ thống đặt `NoncurrentVersionExpiration = 30 days`. Phân tích có còn bản cũ để restore không và đề xuất retention, backup, Object Lock hoặc cảnh báo phù hợp.

### Bài F — Đối chiếu ba cloud

Lập bảng lưu trữ tài liệu trên AWS, Azure và GCP gồm encryption default, CMK/CMEK, versioning, lifecycle và bảo vệ retention. Đề xuất phần nào dùng chung trong Spring Boot và phần nào nằm ở adapter/infrastructure của provider.

### Câu hỏi tự kiểm tra

1. SSE-S3 mặc định cho object mới có thay thế TLS khi upload không?
2. SSE-KMS khác SSE-S3 ở quyền và quản trị khóa như thế nào?
3. Vì sao PUT SSE-KMS thường cần `kms:GenerateDataKey` và GET cần `kms:Decrypt`?
4. Thay bucket default encryption có mã hóa lại object cũ không?
5. Khi Versioning Enabled, PUT cùng key tạo ra điều gì?
6. DELETE key thông thường khi Versioning Enabled có xóa hết byte của version cũ không?
7. Làm thế nào đọc một version cụ thể và cần quyền IAM nào?
8. Vì sao ETag không nên mặc nhiên được dùng như MD5 hoặc version ID?
9. Current Expiration và NoncurrentVersionExpiration khác nhau ở điểm nào?
10. Incomplete multipart upload có thể tốn chi phí dù chưa có object hoàn chỉnh không?
11. Chuyển object sang storage class Glacier ảnh hưởng thời gian đọc/restore ra sao?
12. Object Lock khác với Versioning ở mục tiêu bảo vệ dữ liệu như thế nào?
13. Vì sao Lifecycle không nên dùng để vô hiệu hóa quyền truy cập chính xác từng giây?
14. Với yêu cầu khôi phục 90 ngày, retention noncurrent 30 ngày có phù hợp không?
15. Logic encryption, versioning và lifecycle nào có thể trừu tượng hóa giữa AWS/Azure/GCP, phần nào buộc phải theo provider?

**Kết quả mong đợi:** người học xây dựng được một dịch vụ Spring Boot truy cập Amazon S3 với mã hóa phù hợp, quyền IAM/KMS tối thiểu, hiểu hành vi version và delete marker, đặt lifecycle không làm mất dữ liệu cần giữ, đồng thời kiểm thử khả năng phục hồi và so sánh kiến trúc object storage managed giữa các cloud provider.

