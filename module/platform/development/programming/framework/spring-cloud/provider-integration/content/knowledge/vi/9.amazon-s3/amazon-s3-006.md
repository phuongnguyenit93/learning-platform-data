# Amazon S3: Phân trang, điều kiện ghi và kiểm soát ghi đè

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot được kết nối với các dịch vụ managed của AWS, Azure và Google Cloud để truy cập storage, messaging, dữ liệu và bảo vệ danh tính, quyền, secret. Với **Amazon S3**, hai bài toán quan trọng sau khi biết PUT/GET một object là:

- **Phân trang (pagination):** lấy một phần danh sách object tại một thời điểm, xử lý dữ liệu lớn mà không tải toàn bộ kết quả về RAM hoặc giữ request HTTP quá lâu.
- **Điều kiện ghi (conditional write):** chỉ tạo hoặc thay object khi trạng thái hiện tại của object đáp ứng một điều kiện, từ đó tránh ghi đè ngoài ý muốn khi nhiều client cập nhật cùng key.

Bài này giải thích `ListObjectsV2`, `continuationToken`, `prefix`, `delimiter`, paginator của AWS SDK for Java v2, `If-None-Match`, `If-Match`, `ETag`, hành vi S3 Versioning và những giới hạn khi phối hợp với database nghiệp vụ. Ví dụ dùng **Spring Cloud AWS** cùng **AWS SDK for Java v2** và bao gồm cách kiểm tra quyền, xử lý lỗi, kiểm thử tích hợp và đối chiếu với Azure/Google Cloud.

Sau khi hoàn thành, người học có thể:

1. Triển khai một API danh sách tài liệu có giới hạn trang và cursor tiếp nối.
2. Phân biệt `ListObjectsV2` với truy vấn cơ sở dữ liệu và giải thích vì sao phân trang không cung cấp một snapshot giao dịch.
3. Ghi object theo ngữ nghĩa **create-only** hoặc **replace-if-unchanged** bằng precondition.
4. Xử lý đúng lỗi **HTTP 412 Precondition Failed** và **HTTP 409 ConditionalRequestConflict**.
5. Biết khi nào cần versioning, key bất biến, idempotency và optimistic locking trong database.
6. Thiết kế test đồng thời để chứng minh hai request tranh chấp cùng một key không âm thầm ghi đè nhau.

> Ví dụ dùng namespace `io.awspring.cloud` của Spring Cloud AWS và `software.amazon.awssdk` của AWS SDK v2. Chọn phiên bản Spring Cloud AWS tương thích với phiên bản Spring Boot thực tế; một số tùy chọn điều kiện ghi phụ thuộc phiên bản AWS SDK/S3 API nên phải xác nhận khi triển khai.

## 1. Mô hình S3 cần nhớ trước khi phân trang và cập nhật

Một object S3 được định danh bởi **bucket + object key**. Ví dụ:

~~~text
s3://training-private-files/tenants/t-42/reports/2026/summary.pdf
     └────── bucket ─────┘└──────────── object key ─────────────┘
~~~

Bucket là nơi chứa object; key là một chuỗi **phân biệt chữ hoa/thường**. Các đoạn `tenants/`, `reports/`, `2026/` được hiển thị như thư mục trong S3 Console nhưng thực chất thường chỉ là **prefix** trong key. Khi cần liệt kê, ứng dụng lọc theo prefix; khi cần đọc/ghi, ứng dụng dùng chính xác bucket và key.

Trong bucket chưa bật versioning, một PUT mới vào cùng key có thể thay nội dung hiện tại. Trong bucket bật versioning, PUT tạo version hiện hành mới và có thể giữ lại version trước. **Versioning giữ lịch sử, nhưng không tự giải quyết tranh chấp hai người cùng sửa một tài liệu**: request đến sau vẫn có thể trở thành version hiện hành.

~~~mermaid
flowchart LR
    A["Tài liệu nghiệp vụ #42"] --> DB["Database: owner, tenant, key, version"]
    DB --> S["S3: bucket + object key"]
    S -->|"LIST theo prefix"| L["Trang object / continuationToken"]
    S -->|"PUT có If-Match hoặc If-None-Match"| W["Kiểm tra điều kiện tại S3"]
    W -->|"Đúng điều kiện"| OK["Tạo/thay object"]
    W -->|"Sai điều kiện"| ERR["HTTP 412 / xung đột 409"]
~~~

**Phân quyền là một bước riêng:** nếu backend có IAM role đọc mọi object dưới `tenants/*`, ứng dụng vẫn phải xác minh user được truy cập tenant tương ứng trước khi liệt kê hoặc cập nhật.

## 2. Vì sao LIST phải phân trang?

Một bucket có thể chứa hàng triệu object. Nếu API tải hết danh sách rồi mới trả response:

- Tốn nhiều request S3 và thời gian xử lý, khó đáp ứng timeout của web server.
- Có thể giữ quá nhiều metadata/key trong heap.
- Không thích hợp cho giao diện mà người dùng chỉ xem 20–100 mục mỗi lần.
- Một listing toàn bucket có thể tiết lộ tên object thuộc tenant hoặc nghiệp vụ khác nếu phân quyền kém.

S3 cung cấp API **`ListObjectsV2`** để đọc danh sách theo từng trang. Mỗi yêu cầu có thể đặt `maxKeys`, tối đa **1.000** cho general-purpose bucket; kết quả có thể ít hơn mức yêu cầu. Khi còn phần tiếp theo, response có `isTruncated` và một `nextContinuationToken` để chuyển sang trang kế tiếp.

### 2.1. Các tham số của `ListObjectsV2`

| Thuộc tính | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `bucket` | Bucket cần liệt kê | Phải nằm trong phạm vi IAM được cấp |
| `prefix` | Chỉ trả key bắt đầu bằng chuỗi này | Không phải điều kiện tìm kiếm SQL hay quyền tự thân |
| `delimiter` | Gom các key theo ký tự phân cách, thường là `/` | Tạo `CommonPrefixes`, không tạo folder thật |
| `maxKeys` | Giới hạn số mục của một response | API thông thường tối đa 1.000; không phải `offset` |
| `continuationToken` | Token tiếp tục từ response trước | Token opaque; không tự giải mã, chỉnh sửa hay tạo bằng key |
| `startAfter` | Bắt đầu phía sau key chỉ định (khi API hỗ trợ) | Không giống continuation token; không hỗ trợ cho directory buckets |
| `fetchOwner` | Yêu cầu một số thông tin owner | Thường không cần cho API người dùng thông thường |

Các trường trả về thường gặp:

- `contents()`: danh sách `S3Object` với key, size, thời điểm sửa đổi, ETag và một số thuộc tính tóm tắt.
- `commonPrefixes()`: nhóm prefix nếu dùng `delimiter`.
- `isTruncated()`: còn phần kết quả tiếp theo hay không.
- `nextContinuationToken()`: token dùng để tiếp tục.
- `keyCount()`: số mục đếm theo quy tắc API (có thể tính `CommonPrefixes` là một mục); **không phải tổng số object trong bucket**.

`ListObjectsV2` không trả body object và không phải cách truy vấn tùy ý trên `Content-Type`, user metadata, JSON content hay chủ sở hữu nghiệp vụ. Những điều kiện đó nên được lập chỉ mục trong **database ứng dụng** hoặc một hệ thống truy vấn phù hợp.

### 2.2. Prefix và delimiter tạo cảm giác “thư mục”

Giả sử bucket có:

~~~text
tenants/t-42/reports/2025/a.pdf
tenants/t-42/reports/2025/b.pdf
tenants/t-42/reports/2026/c.pdf
tenants/t-42/images/logo.png
tenants/t-99/reports/private.pdf
~~~

Với `prefix = tenants/t-42/reports/`, S3 chỉ liệt kê key của báo cáo tenant t-42 theo đúng tiền tố chuỗi. Nếu thêm `delimiter = "/"`, response có thể trả `commonPrefixes` là:

~~~text
tenants/t-42/reports/2025/
tenants/t-42/reports/2026/
~~~

Đó chỉ là **kết quả nhóm chuỗi key**. S3 không có thư mục vật lý tương ứng và không yêu cầu object riêng mang tên các prefix đó.

## 3. Cấu hình Spring Boot để gọi S3

### 3.1. Dependency và cấu hình ứng dụng

Dự án Maven có thể import BOM Spring Cloud AWS rồi thêm S3 starter:

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

Property `spring-cloud-aws.version` phải được dự án khai báo với bản phát hành tương thích Spring Boot. Starter hỗ trợ cấu hình bean `S3Client` của AWS SDK v2 để inject vào Spring service.

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
    list-page-size: 50
~~~

`app.storage.*` là **property do ứng dụng tự định nghĩa**, không phải tính năng tự động của S3 starter. Region phải phù hợp bucket. Cung cấp credentials qua AWS default provider chain (profile/SSO khi phát triển, IAM role hoặc workload identity khi triển khai), không hard-code access key/secret key vào cấu hình.

### 3.2. Quyền IAM cần thiết

Service vừa LIST vừa PUT các object dưới `tenants/` có thể dùng policy minh họa sau:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListTenantPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::training-private-files",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["tenants/", "tenants/*"]
        }
      }
    },
    {
      "Sid": "ReadWriteTenantObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::training-private-files/tenants/*"
    }
  ]
}
~~~

`s3:ListBucket` áp dụng lên **bucket ARN**; `s3:GetObject` và `s3:PutObject` áp dụng lên **object ARN**. `s3:prefix` chỉ giới hạn tham số của yêu cầu LIST, không giới hạn GET/PUT. Role ở ví dụ **không** có quyền xóa.

Policy này vẫn rộng hơn quyền của một người dùng ứng dụng: backend phải kiểm tra user/tenant trước khi tạo prefix hoặc key. Nếu dùng SSE-KMS, quyền KMS/key policy và explicit deny ở bucket policy cũng có thể ảnh hưởng. Trong production nên thu hẹp IAM theo dữ liệu và tác vụ thực tế, không dùng policy minh họa này để cấp toàn quyền tenant khi không cần thiết.

## 4. Triển khai LIST một trang bằng `S3Client`

### 4.1. Service giới hạn kích thước và prefix

Ví dụ sau trả về **một trang** object. `tenantId` phải được xác minh từ hệ thống xác thực hoặc database trước khi gọi service, tránh để người dùng tự chọn tenant khác.

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Response;
import software.amazon.awssdk.services.s3.model.S3Object;

@Service
public class S3TenantListingService {
    private final S3Client s3;
    private final String bucket;

    public S3TenantListingService(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public record ObjectSummary(
            String key, long size, Instant modifiedAt, String eTag) {}

    public record ObjectPage(
            List<ObjectSummary> items, String nextToken) {}

    public ObjectPage listOnePage(
            String authorizedTenantId,
            String continuationToken,
            int requestedSize) {

        if (authorizedTenantId == null ||
                !authorizedTenantId.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Tenant ID không hợp lệ");
        }
        if (requestedSize < 1 || requestedSize > 100) {
            throw new IllegalArgumentException("pageSize phải từ 1 đến 100");
        }

        String prefix = "tenants/" + authorizedTenantId + "/";
        ListObjectsV2Request.Builder builder =
                ListObjectsV2Request.builder()
                        .bucket(bucket)
                        .prefix(prefix)
                        .maxKeys(requestedSize);

        if (continuationToken != null &&
                !continuationToken.isBlank()) {
            builder.continuationToken(continuationToken);
        }

        ListObjectsV2Response response =
                s3.listObjectsV2(builder.build());

        List<ObjectSummary> items =
                response.contents().stream()
                        .map(this::toSummary)
                        .toList();

        String nextToken =
                Boolean.TRUE.equals(response.isTruncated())
                        ? response.nextContinuationToken() : null;

        return new ObjectPage(items, nextToken);
    }

    private ObjectSummary toSummary(S3Object object) {
        return new ObjectSummary(
                object.key(),
                object.size(),
                object.lastModified(),
                object.eTag());
    }
}
~~~

Đây là code minh họa cho Java phiên bản có `Stream.toList()` (Java 16+, phù hợp với nhiều dự án Spring Boot hiện đại). `ObjectSummary` không chứa body object; `size` tính bằng byte. `nextToken` là dữ liệu S3 trả về, không phải số trang hay giá trị có thể cộng `+1`.

**Quan trọng về an toàn cursor:** ví dụ chuyển tiếp trực tiếp token do S3 cấp để làm rõ API. Nếu xuất token ra client trong production, hãy coi nó là **dữ liệu không tin cậy**: giới hạn độ dài, xác minh tenant và bộ lọc ở mỗi request, không dùng token để vượt qua authorization. Nếu cần chống client sửa/mượn token giữa các truy vấn, có thể đóng gói token cùng `tenantId + prefix + pageSize/filters` và ký HMAC ở backend hoặc lưu cursor gắn với phiên; tránh log token tùy tiện.

### 4.2. Expose danh sách dạng cursor API

API nghiệp vụ có thể nhận:

~~~http
GET /api/documents?pageSize=50
Authorization: Bearer <application-token>
~~~

Và trả:

~~~json
{
  "items": [
    {
      "key": "tenants/t-42/reports/2026/a.pdf",
      "size": 8192,
      "modifiedAt": "2026-11-24T02:00:00Z",
      "eTag": "\"sample-etag\""
    }
  ],
  "nextToken": "<opaque-token>"
}
~~~

Các giá trị trong ví dụ là giả lập; token thực tế do S3 tạo và phải được dùng **nguyên vẹn** trong request sau. Một endpoint chuẩn có thể **không trả key S3 thô** mà trả `documentId` và metadata được lấy từ database, đặc biệt khi tên key chứa thông tin nội bộ.

Luồng controller nên là:

1. Xác thực user.
2. Xác định tenant/prefix từ dữ liệu ứng dụng tin cậy.
3. Chỉ cho phép `pageSize` trong khoảng hợp lý.
4. Gọi `listOnePage` với prefix đã ràng buộc.
5. Trả `items + nextToken`; trên trang cuối `nextToken = null`.

Không có nghĩa vụ đọc thêm trang ngay nếu người dùng chỉ muốn xem trang đầu.

## 5. Paginator: duyệt nhiều trang trong batch job

Khi cần quét toàn bộ key dưới prefix trong một **job có giới hạn**, AWS SDK v2 cung cấp paginator:

~~~java
ListObjectsV2Request request =
        ListObjectsV2Request.builder()
                .bucket(bucket)
                .prefix("tenants/t-42/reports/")
                .maxKeys(100)
                .build();

for (ListObjectsV2Response page :
        s3.listObjectsV2Paginator(request)) {
    for (S3Object object : page.contents()) {
        processOneKey(object.key());
    }
}
~~~

`processOneKey` là logic của batch job; ví dụ chỉ mô tả cách duyệt. Paginator tự xử lý token tiếp nối giữa các trang, nhưng **mỗi trang vẫn là một lời gọi S3**. Không nên chuyển tất cả kết quả paginator thành một `List` khổng lồ nếu bucket nhiều object.

Các lưu ý thiết kế batch:

- Đặt giới hạn tổng số key/trang, deadline, cơ chế hủy và retry có kiểm soát.
- `processOneKey` nên có **idempotency** hoặc trạng thái checkpoint vì job có thể bị dừng và chạy lại.
- LIST là thao tác đọc và có chi phí request; số lượng key lớn dẫn đến nhiều request.
- Một object được thêm/xóa trong lúc job duyệt có thể ảnh hưởng các trang; đừng xem toàn bộ các trang là cùng một ảnh chụp thời điểm.
- Nếu batch cần danh sách dữ liệu nghiệp vụ với thứ tự xác định, nên dùng database/query hoặc nguồn snapshot phù hợp thay vì giả định LIST có transaction isolation.

### 5.1. Khi nào dùng `StartAfter`?

Với **general-purpose bucket**, `StartAfter` có thể hỗ trợ bắt đầu liệt kê sau một key đã biết, ví dụ trong job xử lý tuần tự. Nhưng:

- `StartAfter` **không phải** `ContinuationToken`.
- `StartAfter` không được hỗ trợ trong **S3 directory buckets**.
- Khi bucket thay đổi đồng thời, một key checkpoint không tạo ra snapshot ổn định.
- Nếu code chỉ đang tải trang tiếp theo theo đúng `ListObjectsV2`, nên ưu tiên `NextContinuationToken` do S3 trả về.

Không tự dùng `lastKey` làm continuation token: token là chuỗi **opaque** do S3 tạo, không thể suy ra từ tên object.

### 5.2. Thứ tự và tính nhất quán

S3 cung cấp **strong read-after-write consistency** cho PUT/DELETE và GET/LIST sau thao tác thành công. Tuy nhiên, điều đó không đồng nghĩa với việc các trang LIST liên tiếp nhìn thấy một **snapshot nhất quán của cả bucket**.

Ví dụ:

~~~text
09:00 Trang 1: a.pdf, b.pdf, c.pdf
09:01 Ứng dụng khác tạo aa.pdf, xóa b.pdf
09:02 Trang 2: dùng continuationToken của trang 1
~~~

Trang 2 không có bảo đảm mang lại một danh sách phản ánh chính xác toàn bộ bucket tại 09:00. Đối với general-purpose buckets, kết quả LIST thường theo thứ tự từ điển của key; **directory buckets không bảo đảm thứ tự lexicographic** tương tự. Nếu UI cần sắp xếp theo thời gian, tên hiển thị hoặc trạng thái phê duyệt, hãy truy vấn một index/database có yêu cầu sắp xếp rõ ràng.

### 5.3. `Delimiter` có thể ảnh hưởng kích thước trang

Nếu truyền `delimiter("/")`, S3 có thể trả các nhóm `CommonPrefixes` bên cạnh `contents`. Khi phân trang kiểu mô phỏng thư mục, đừng chỉ đếm `contents().size()` và kết luận trang thiếu dữ liệu: mỗi `CommonPrefixes` được tính theo quy tắc số lượng mục trả về.

Nếu API cần liệt kê cả thư mục logic và object trực tiếp dưới một prefix, thiết kế response đủ hai loại mục:

~~~json
{
  "objects": [
    {"key": "tenants/t-42/reports/readme.txt"}
  ],
  "prefixes": [
    "tenants/t-42/reports/2025/",
    "tenants/t-42/reports/2026/"
  ],
  "nextToken": "<opaque-token>"
}
~~~

## 6. Vấn đề ghi đè khi nhiều client cùng PUT

Giả sử hai người cùng chỉnh một báo cáo:

~~~text
09:00 Object reports/status.json chứa phiên bản A
09:01 Client 1 đọc A
09:01 Client 2 đọc A
09:02 Client 1 ghi nội dung B
09:03 Client 2 ghi nội dung C từ bản A cũ

Kết quả nếu PUT vô điều kiện: C thành nội dung hiện hành;
thay đổi B bị ghi đè về mặt logic.
~~~

S3 Versioning có thể giữ bản B trong lịch sử, nhưng client 2 vẫn không biết mình đã sửa trên dữ liệu cũ. Đây là **lost update**. Các giải pháp phụ thuộc mục tiêu:

| Mục tiêu | Giải pháp |
| --- | --- |
| Mỗi upload phải tạo object mới | Key ngẫu nhiên/bất biến, có thể kết hợp `If-None-Match: *` |
| Chỉ tạo object nếu key chưa tồn tại | Conditional PUT với `If-None-Match: *` |
| Chỉ thay nội dung nếu object chưa thay đổi từ lúc đọc | Conditional PUT với `If-Match` của ETag đã đọc |
| Cần giữ lịch sử nội dung sau nhiều lần sửa | S3 Versioning và lưu version ID khi cần |
| Cần tính đúng quyền/chủ sở hữu/trạng thái nghiệp vụ | Optimistic locking/transaction tại database |
| Cần khôi phục sau retry/timeout | Idempotency key, kiểm tra trạng thái request và checksum phù hợp |

**Không dựa vào thao tác HEAD rồi PUT thông thường để bảo đảm key còn trống.** Giữa hai request đó, một client khác có thể tạo object. Phải đưa điều kiện đến **chính S3 trong request ghi** để được kiểm tra tại thời điểm xử lý.

## 7. `If-None-Match: *` — chỉ tạo khi chưa có object hiện hành

Header HTTP **`If-None-Match: *`** là một precondition cho PUT: yêu cầu chỉ thành công nếu S3 xác định chưa có object hiện hành đáp ứng key ở thời điểm kiểm tra. Với AWS SDK v2 có hỗ trợ conditional writes, sử dụng builder:

~~~java
import java.nio.charset.StandardCharsets;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

byte[] bytes = "Báo cáo mới".getBytes(StandardCharsets.UTF_8);

PutObjectRequest put = PutObjectRequest.builder()
        .bucket(bucket)
        .key("tenants/t-42/reports/new-report.txt")
        .contentType("text/plain; charset=UTF-8")
        .ifNoneMatch("*")
        .build();

s3.putObject(put, RequestBody.fromBytes(bytes));
~~~

Nếu key chưa có object hiện hành, request có thể tạo object; nếu key đã có object hiện hành, S3 từ chối điều kiện với **HTTP 412 Precondition Failed**. Khi xảy ra hoạt động đồng thời, S3 cũng có thể trả **HTTP 409 ConditionalRequestConflict**; xử lý retry sau khi xác minh tình trạng, không mặc định coi là lỗi mạng chung.

**Các điểm dễ nhầm:**

1. `If-None-Match` là điều kiện của **request PUT cụ thể**, không phải thuộc tính bucket được bật tự động.
2. Dấu `*` mang nghĩa kiểm tra sự tồn tại của object hiện hành, không phải wildcard của key hoặc prefix.
3. Nếu bucket bật versioning và **version hiện hành là delete marker**, một conditional create có thể thành công theo quy tắc kiểm tra object hiện hành; version cũ vẫn có thể tồn tại trong lịch sử.
4. Nếu request đầu đã tạo thành công nhưng client bị timeout trước khi nhận response, retry cùng key có thể nhận **412**. Trường hợp này cần tra **idempotency record/checksum** để phân biệt “đã hoàn tất trước đó” và “một object khác chiếm key”.
5. Không suy diễn từ một response 412 rằng principal đã có quyền GET object; quyền của PUT và GET độc lập.

### 7.1. Create-only với tên key UUID

Trong hệ thống lưu tài liệu, một kiểu key dễ kiểm soát là:

~~~text
tenants/{trustedTenantId}/documents/{serverGeneratedUuid}.pdf
~~~

Sinh UUID ở backend làm giảm nguy cơ va chạm; thêm `If-None-Match: *` biến quy ước “chắc sẽ mới” thành một **điều kiện được S3 kiểm tra**. Database lưu owner, tenant, documentId và key; API không cho người dùng tự chọn key ngoài quyền của họ.

## 8. `If-Match: ETag` — chỉ thay khi object chưa đổi

Với một tài liệu được phép sửa tại **cùng key**, backend có thể dùng optimistic concurrency control:

1. Đọc object và **ETag** hiện hành qua GET hoặc HEAD.
2. Cho phép user chỉnh sửa trên cơ sở trạng thái đó.
3. Gửi PUT kèm **`If-Match` bằng ETag đã đọc**.
4. Nếu object đã thay đổi và điều kiện không còn đúng, S3 trả **412** thay vì âm thầm ghi đè.

~~~mermaid
sequenceDiagram
    participant C1 as Client 1
    participant C2 as Client 2
    participant S3 as S3
    C1->>S3: HEAD key
    S3-->>C1: ETag = E1
    C2->>S3: HEAD key
    S3-->>C2: ETag = E1
    C1->>S3: PUT B, If-Match: E1
    S3-->>C1: Thành công; ETag mới E2
    C2->>S3: PUT C, If-Match: E1
    S3-->>C2: 412 Precondition Failed
~~~

Nếu cần sửa sau xung đột, client 2 phải tải bản mới, đối chiếu/merge thay đổi rồi gửi PUT với ETag mới. Không tự retry với điều kiện đã lỗi bằng cách bỏ hẳn `If-Match`.

### 8.1. Ví dụ Java: HEAD và conditional PUT

~~~java
import java.nio.charset.StandardCharsets;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

String key = "tenants/t-42/reports/status.json";

// Client/API đã kiểm tra quyền đọc và sửa tài liệu nghiệp vụ.
var head = s3.headObject(HeadObjectRequest.builder()
        .bucket(bucket)
        .key(key)
        .build());

String expectedEtag = head.eTag(); // Giữ nguyên giá trị SDK trả về.

byte[] replacement = """
        {"state":"approved"}
        """.getBytes(StandardCharsets.UTF_8);

var result = s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("application/json")
                .ifMatch(expectedEtag)
                .build(),
        RequestBody.fromBytes(replacement));

System.out.println("New ETag: " + result.eTag());
~~~

Trong sản phẩm thực, **expectedEtag phải đến từ lần đọc mà client đang chỉnh sửa**, không phải HEAD ngay trước PUT bất kể client đã sửa trên nội dung nào. Nếu backend luôn gọi HEAD lại trước PUT rồi dùng ETag mới nhất, một request chỉnh sửa từ nội dung cũ vẫn có thể ghi đè thay đổi của người khác. Vì vậy thường trả ETag cho client cùng bản dữ liệu, rồi nhận lại khi client yêu cầu cập nhật.

**ETag không phải lúc nào là MD5 nội dung.** Với multipart upload, mã hóa hoặc những cơ chế khác, ETag có thể không phải hash MD5 thuần. Dùng ETag làm **token điều kiện** theo ngữ nghĩa S3, đừng dùng nó làm checksum bảo mật hoặc kết luận rằng ETag luôn là số phiên bản đơn điệu. Nếu cần kiểm chứng toàn vẹn nội dung, dùng checksum phù hợp do SDK/S3 hỗ trợ.

### 8.2. Phân biệt ETag và Version ID

| Thuộc tính | Vai trò | Có thay thế nhau được không? |
| --- | --- | --- |
| `ETag` | Nhận diện trạng thái nội dung theo ngữ nghĩa của S3, dùng với HTTP `If-Match` | Không |
| `Version ID` | Định danh một version cụ thể trong bucket bật versioning | Không |
| `Content-Length` | Độ dài body object (byte) | Không |
| `Checksum` | Kiểm chứng toàn vẹn byte theo thuật toán được hỗ trợ | Không |
| `rowVersion` ở DB | Chống lost update đối với bản ghi nghiệp vụ | Không |

S3 Versioning **không tự sinh điều kiện `If-Match`** cho request PUT. Một hệ thống có thể lưu cả `versionId` và `ETag` nếu cần khôi phục phiên bản cụ thể và kiểm soát cập nhật. Nếu cần phân biệt các thay đổi logic ngay cả khi body có thể giống nhau, sử dụng **revision number ở database** hoặc key bất biến cho mỗi revision sẽ rõ ràng hơn là chỉ dựa vào ETag.

## 9. Xử lý HTTP 412 và 409 khi ghi có điều kiện

Conditional write cần cách xử lý lỗi khác với lỗi truy cập hoặc mạng.

| Kết quả | Ý nghĩa thực tế | Gợi ý xử lý |
| --- | --- | --- |
| 2xx | PUT/Complete thành công theo điều kiện | Lưu ETag/version ID mới; đánh dấu nghiệp vụ hoàn tất |
| **412 Precondition Failed** | Điều kiện không còn đúng với trạng thái object hiện hành | Trả **409 Conflict** ở API nghiệp vụ hoặc mã lỗi riêng; yêu cầu tải lại/merge |
| **409 ConditionalRequestConflict** | S3 phát hiện tranh chấp đồng thời trong conditional write | Đọc lại trạng thái, retry có kiểm soát khi thích hợp |
| 403 AccessDenied | Không có quyền S3/KMS hoặc bị policy từ chối | Kiểm IAM, bucket policy, KMS, explicit deny |
| 404/NoSuchKey trên HEAD/GET | Object không tồn tại hoặc không nhìn thấy ở trạng thái hiện hành | Đối chiếu key, quyền LIST và versioning |
| Timeout/5xx | Có thể là lỗi tạm thời; kết quả PUT đôi khi chưa rõ từ phía caller | Kiểm tra trạng thái/idempotency trước khi khởi tạo lại |

Ví dụ phân nhánh response:

~~~java
import software.amazon.awssdk.services.s3.model.S3Exception;

try {
    s3.putObject(putRequest, RequestBody.fromBytes(payload));
} catch (S3Exception ex) {
    if (ex.statusCode() == 412) {
        // Bản hiện tại không đáp ứng If-Match/If-None-Match.
        throw new DocumentConflictException(
                "Object đã tồn tại hoặc đã được thay đổi", ex);
    }
    if (ex.statusCode() == 409) {
        // Tranh chấp đồng thời: kiểm tra lại trạng thái trước khi retry.
        throw new ConcurrentObjectWriteException(
                "Xung đột khi ghi object", ex);
    }
    throw ex;
}
~~~

`DocumentConflictException` và `ConcurrentObjectWriteException` là **exception nghiệp vụ do ứng dụng tự định nghĩa**, không phải class có sẵn của AWS SDK. Ví dụ minh họa cách ánh xạ lỗi; trong code thực tế phải xác định đó là lỗi conditional write trước khi chuyển mọi 409/412 sang cùng một loại nghiệp vụ.

### 9.1. Có nên retry ngay khi gặp 412?

**Không retry vô điều kiện** với cùng payload mà bỏ precondition:

- Với **create-only**, 412 có thể nghĩa là một request khác đã tạo object. Cần kiểm idempotency session và đối chiếu object.
- Với **replace-if-unchanged**, 412 báo người khác đã sửa. Client cần tải bản mới và quyết định merge; tự ghi đè sẽ tái tạo lost update.
- Với **409**, có thể retry PUT sau khi đọc/đánh giá lại trạng thái theo hướng dẫn API; phải giới hạn số lần và dùng backoff.
- Với **CompleteMultipartUpload** gặp 409 do conditional conflict, thường cần **khởi tạo một multipart upload mới và upload lại các part** theo yêu cầu của S3, thay vì tái sử dụng trạng thái cũ một cách tùy tiện.

Nếu timeout xảy ra sau PUT thành công nhưng trước khi client nhận response, lần retry có thể gặp 412. Phải có **application request ID/idempotency record** để phân biệt request của chính mình đã hoàn tất với một request khác tranh chấp key.

## 10. Multipart upload có điều kiện và giới hạn ghi đè

Khi file lớn, một object có thể được đưa lên S3 bằng:

~~~text
CreateMultipartUpload
      ↓
UploadPart(1), UploadPart(2), ...
      ↓
CompleteMultipartUpload
      ↓
Object hiện hành xuất hiện ở bucket/key
~~~

**Điều kiện “chỉ tạo khi key chưa có” hoặc “chỉ thay khi ETag vẫn đúng” phải được kiểm tra tại lúc hoàn tất multipart**, không chỉ kiểm tra bằng HEAD trước khi khởi tạo upload. API `CompleteMultipartUpload` có hỗ trợ conditional headers trong các phiên bản S3/SDK tương ứng, như `If-None-Match` và `If-Match`.

Minh họa ý tưởng với AWS SDK v2 có hỗ trợ trường điều kiện:

~~~java
var completeRequest = CompleteMultipartUploadRequest.builder()
        .bucket(bucket)
        .key(key)
        .uploadId(uploadId)
        .multipartUpload(completedMultipartUpload)
        .ifNoneMatch("*")  // Chỉ hoàn tất nếu chưa có object hiện hành.
        .build();

s3.completeMultipartUpload(completeRequest);
~~~

Trong đoạn trên, `completedMultipartUpload` chứa các `CompletedPart` gồm **partNumber và ETag của từng UploadPart** theo thứ tự tăng dần; `uploadId` có được từ `CreateMultipartUpload`. Mẫu chỉ minh họa phần điều kiện ở **Complete**, không phải toàn bộ uploader.

Khi Complete thất bại:

1. Không kết luận ngay các part đã được xóa; multipart chưa hoàn tất có thể phát sinh chi phí.
2. Với 412, xác định object có tồn tại/đã thay đổi và quyết định xử lý xung đột.
3. Với 409 conditional conflict, làm theo quy trình khởi tạo multipart mới, upload lại nếu nghiệp vụ còn cần thiết.
4. Cố gắng `AbortMultipartUpload` đối với upload dang dở khi còn hợp lệ.
5. Đặt S3 Lifecycle rule **AbortIncompleteMultipartUpload** để dọn những phiên upload bị bỏ dở vì process bị kill hoặc client mất kết nối.

Không được nhầm việc `CreateMultipartUpload` thành công với việc một object mới đã sẵn sàng GET.

## 11. Thiết kế kiểm soát ghi đè ở tầng nghiệp vụ

S3 precondition rất hữu ích nhưng không tự tạo **transaction ACID chung giữa S3 và database**. Trong hệ thống quản lý hóa đơn hay báo cáo, người dùng thường tương tác bằng `documentId`, còn `objectKey` nằm trong bản ghi database.

### 11.1. Phương án A: một key bất biến cho mỗi revision

~~~text
Document ID = doc-42
Revision 1 → tenants/t-42/documents/doc-42/rev-001.json
Revision 2 → tenants/t-42/documents/doc-42/rev-002.json
Revision 3 → tenants/t-42/documents/doc-42/rev-003.json

Database:
documentId = doc-42
currentRevision = 3
currentObjectKey = .../rev-003.json
rowVersion = 3
~~~

Ưu điểm:

- Không ghi đè byte của revision cũ.
- PUT có thể dùng `If-None-Match: *` để bảo đảm key revision mới chưa tồn tại.
- Database cập nhật con trỏ current revision bằng **optimistic locking** (`UPDATE ... WHERE row_version = expectedVersion`).
- Dễ audit và rollback nghiệp vụ bằng cách chọn revision đã lưu.

Đánh đổi là nhiều object hơn và cần quy tắc lifecycle/retention. Nếu S3 PUT thành công nhưng cập nhật database thất bại, object mới có thể trở thành **orphan**; cần job đối soát/dọn dẹp hoặc quy trình upload có trạng thái.

### 11.2. Phương án B: một key có thể thay thế, kết hợp If-Match

Dùng cùng một key cho nội dung hiện hành và gửi `If-Match` với ETag từ lần đọc. Có thể bật versioning để giữ lịch sử. Cách này đơn giản ở tầng object, nhưng:

- Cần lưu/trả đúng ETag thuộc lần đọc mà client sửa.
- Cần xử lý 412 bằng UI tải lại/merge.
- Cần quản lý version cũ, delete marker và chi phí nếu bật versioning.
- Database vẫn phải chống lost update ở các trường nghiệp vụ độc lập như trạng thái duyệt, tên tài liệu hay owner.

### 11.3. Quy trình phối hợp S3 và database

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant API as Spring Boot
    participant DB as Database
    participant S3 as Amazon S3

    User->>API: Sửa documentId + expectedRevision
    API->>DB: Kiểm quyền + currentRevision
    DB-->>API: revision hiện hành phù hợp
    API->>S3: PUT key mới, If-None-Match: *
    S3-->>API: Thành công + ETag/version ID
    API->>DB: CAS update currentRevision
    alt CAS thành công
        DB-->>API: Đã cập nhật con trỏ
        API-->>User: 200 + revision mới
    else CAS thất bại
        DB-->>API: Người khác đã cập nhật trước
        API->>API: Ghi nhận orphan + lịch dọn/đối soát
        API-->>User: 409 Conflict
    end
~~~

**CAS (compare-and-swap)** tại database ở đây là một lệnh cập nhật có điều kiện theo revision/version, chẳng hạn:

~~~sql
UPDATE documents
SET current_object_key = :newKey,
    row_version = row_version + 1
WHERE id = :documentId
  AND row_version = :expectedRowVersion;
~~~

Nếu số dòng cập nhật bằng 0, đã có thay đổi cạnh tranh hoặc bản ghi không hợp lệ; không kết luận S3 PUT thất bại. Cần cleanup object vừa ghi theo chính sách. Quy trình này là ví dụ một hướng thiết kế, không phải transaction phân tán hoàn toàn tự động.

## 12. Liên hệ IAM và bucket policy để bắt buộc điều kiện ghi

Điều kiện trong Java giúp tránh ghi đè, nhưng **một caller khác có quyền PUT** vẫn có thể ghi vô điều kiện nếu policy không ràng buộc. Với bucket chứa dữ liệu quan trọng, AWS S3 có các **condition key** phục vụ việc thực thi conditional writes trong bucket policy, ví dụ `s3:if-none-match` hoặc `s3:if-match` ở các request được hỗ trợ.

Nguyên tắc triển khai:

- Tách vai trò chỉ upload object mới với vai trò được sửa hoặc xóa.
- Cân nhắc bucket policy **deny** PUT không gửi precondition phù hợp, theo API và tính năng bucket đang dùng.
- Kiểm tra riêng multipart, bởi `CreateMultipartUpload`, `UploadPart` và `CompleteMultipartUpload` có thời điểm đặt điều kiện khác nhau; policy áp dụng thiếu chính xác có thể chặn cả luồng hợp lệ.
- Test với role thực trong AWS sandbox, kể cả direct upload bằng presigned URL.
- Bật versioning/retention theo nhu cầu nhưng **không xem versioning thay thế quyền và điều kiện ghi**.

Ví dụ identity policy chỉ cho phép thao tác đọc và tạo object trong một prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::training-private-files/incoming/*"
    }
  ]
}
~~~

Policy này **chưa cưỡng chế `If-None-Match`**; nó chỉ cấp action và giới hạn object ARN. Nếu quy định bắt buộc create-only là yêu cầu bảo vệ dữ liệu, phải thiết kế bucket policy/role tương ứng và test chính sách ở AWS thật. Không tự suy rằng chỉ vì service Java đã truyền header là toàn bộ hệ thống được bảo vệ khỏi các caller khác.

## 13. Xử lý idempotency, retry và tính đúng đắn khi timeout

Các lỗi mạng có thể xảy ra tại thời điểm bất tiện:

~~~text
Client → PUT If-None-Match: * → S3 lưu thành công
                                 ↘ response bị mất do mạng
Client → retry cùng key      → S3 trả 412
~~~

Nếu xử lý 412 thành “upload thất bại”, ứng dụng có thể báo lỗi dù object đã được tạo. Nếu coi 412 là “thành công” vô điều kiện, ứng dụng có thể nhận nhầm dữ liệu do **caller khác** ghi.

Một quy trình tốt hơn là:

1. Backend tạo **operation ID/idempotency key** và key do backend phát sinh, gắn user/tenant.
2. Lưu trạng thái `PENDING` trước khi PUT.
3. Khi PUT thành công, lưu ETag/version ID, size, checksum nếu phù hợp, đánh dấu `READY`.
4. Khi timeout, tra operation ID và kiểm trạng thái object bằng HEAD/GET và thông tin đã biết; quyết định retry, hoàn tất hay báo xung đột.
5. Không làm mới `If-Match` rồi gửi lại payload cũ một cách âm thầm; client cần quyết định dựa trên bản hiện hành.
6. Dọn các object tạo thành công nhưng không được database tham chiếu, theo chính sách giữ dữ liệu.

Nếu ứng dụng có nhiều instance, idempotency record cần nằm trong nơi lưu bền vững chia sẻ, không dùng một `ConcurrentHashMap` cục bộ làm nguồn sự thật.

## 14. Kiểm thử chức năng và tình huống cạnh tranh

### 14.1. Ba tầng kiểm thử

| Tầng | Xác minh | Giới hạn |
| --- | --- | --- |
| Unit test với mock SDK | Prefix/size, token được truyền đúng, If-Match/If-None-Match có mặt, ánh xạ 412/409 | Không chứng minh S3 thực sự áp điều kiện |
| S3-compatible emulator (nếu hỗ trợ) | LIST, paginator, PUT có điều kiện, GET/HEAD, xung đột | Không chắc tái hiện concurrency, policy, directory bucket, KMS giống AWS |
| AWS sandbox | IAM thực, bucket policy, strong consistency, conditional PUT/Complete, versioning và retry | Cần quyền/tài nguyên test riêng, dọn dữ liệu sau kiểm thử |

### 14.2. Các trường hợp nên chạy

**Pagination:**

1. Tạo hơn 20 object test dưới prefix ngẫu nhiên `tenants/test-.../`.
2. Gọi `ListObjectsV2` với `maxKeys=5`; tiếp tục theo `nextContinuationToken` đến khi hết trang.
3. Kiểm tra không có key ngoài prefix, số mục đúng trong một bucket ổn định.
4. Thử prefix không có object, tên key có dấu `/` và `delimiter("/")`.
5. Chèn/xóa object **giữa các trang** để quan sát vì sao listing nhiều trang không phải một snapshot.
6. Giới hạn `pageSize` đầu vào API và thử token/tenant không hợp lệ.

**Conditional PUT:**

1. PUT cùng key mới với `If-None-Match: *`: lần đầu thành công; lần sau thường trả 412.
2. HEAD lấy ETag `E1`, PUT nội dung mới với `If-Match: E1`: thành công.
3. Gửi lại ETag cũ sau khi object đã đổi: mong đợi 412 khi điều kiện không còn đúng.
4. Chạy hai PUT đồng thời sử dụng cùng ETag cũ để quan sát một request thắng và request khác bị từ chối/xung đột (phân biệt 412/409).
5. Bật versioning ở bucket test riêng để xem lịch sử version khi PUT thành công.
6. Khi dùng multipart, thử conditional `CompleteMultipartUpload` và Abort/lifecycle cleanup sau thất bại.
7. Giả lập timeout sau PUT thành công để kiểm thử idempotency record và luồng đối soát.

### 14.3. Ví dụ minh họa create-only test

Đoạn sau mô tả phép thử bằng SDK (dùng key ngẫu nhiên trong bucket sandbox):

~~~java
String key = "incoming/test-" + java.util.UUID.randomUUID();

byte[] body = "hello".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

PutObjectRequest request = PutObjectRequest.builder()
        .bucket(testBucket)
        .key(key)
        .ifNoneMatch("*")
        .build();

s3.putObject(request, RequestBody.fromBytes(body));

try {
    s3.putObject(request, RequestBody.fromBytes(body));
    throw new AssertionError("Expected a conditional write conflict");
} catch (software.amazon.awssdk.services.s3.model.S3Exception ex) {
    if (ex.statusCode() != 412) {
        throw ex; // Không lẫn lỗi IAM/network với precondition.
    }
}
~~~

Trong test thực tế phải dọn object ở khối teardown/finally, không chạy với key có dữ liệu thật. Nếu bucket bật versioning, cần chính sách dọn version thích hợp; xóa current key không nhất thiết xóa lịch sử.

## 15. Liên hệ Azure Blob Storage và Google Cloud Storage

Module này hướng đến tích hợp Spring Boot với ba cloud provider. Cùng bài toán phân trang và ghi điều kiện tồn tại ở cả ba, nhưng **tham số và ngữ nghĩa khác nhau**:

| Bài toán | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| List theo prefix | `ListObjectsV2(prefix)` | List blobs theo prefix | List objects theo prefix |
| Phân trang | Opaque continuation token | Continuation token của Azure paging | Page token của Google Cloud Storage |
| Chỉ tạo khi chưa tồn tại | `If-None-Match: *` trên PUT hỗ trợ | `If-None-Match: *`/request conditions phù hợp | Preconditions như `ifGenerationMatch(0)` |
| Ghi nếu phiên bản chưa đổi | `If-Match` với ETag | `If-Match` với ETag | `ifGenerationMatch(generation)` |
| Lịch sử phiên bản | S3 Versioning + version ID | Blob versioning | Object version/generation |
| Danh tính workload | IAM role / AWS credentials | Managed identity / Azure RBAC | Service account / Google IAM |

Điểm cần giữ chung ở **domain service**: tenant authorization, page size, cursor contract, idempotency ID và lỗi `CONFLICT`. Phần adapter của từng cloud chịu trách nhiệm dịch sang API cụ thể, hiểu giới hạn provider và diễn giải ETag/generation/token.

Một interface nghiệp vụ có thể là:

~~~java
public interface ObjectCatalogPort {
    ObjectPage list(String trustedPrefix, String pageToken, int limit);

    CreatedObject createIfAbsent(
            String trustedKey, byte[] body, String contentType);

    UpdatedObject replaceIfUnchanged(
            String trustedKey, byte[] body,
            String contentType, String expectedRevision);
}
~~~

Trong interface trên, `ObjectPage`, `CreatedObject`, `UpdatedObject` là **kiểu miền tự định nghĩa**. `expectedRevision` có thể là ETag (S3/Azure) hoặc generation (GCP) ở tầng adapter nhưng API nghiệp vụ không nên tự phỏng đoán các chuỗi revision có thể so sánh giữa provider.

## 16. Bài tập thực hành và câu hỏi ôn tập

### Bài 1 — Xây API phân trang

Tạo endpoint `GET /api/documents?pageSize=10&cursor=...` trong Spring Boot. Backend xác thực user, lấy tenantId tin cậy, gọi `ListObjectsV2` với prefix tenant và trả trang kế tiếp. Với hơn 30 object test, xác minh cursor hoạt động, giới hạn pageSize và không lộ object tenant khác.

### Bài 2 — Tạo object đúng một lần

Tạo endpoint upload báo cáo mới: backend sinh UUID key và PUT `If-None-Match: *`. Gửi lại cùng key có chủ đích để quan sát 412. Thiết kế phản hồi nghiệp vụ sao cho request retry sau timeout không bị nhầm với request của người khác.

### Bài 3 — Sửa tài liệu không mất cập nhật

Hai client cùng đọc một object và ETag `E1`. Client A gửi PUT `If-Match: E1` với nội dung B; client B gửi PUT `If-Match: E1` với nội dung C. Quan sát kết quả và xây UI hiển thị xung đột, đề nghị tải lại/merge thay vì tự ghi đè.

### Bài 4 — Versioning và conditional write

Trong bucket sandbox bật versioning, tạo hai version cùng key, thử HEAD và tải từng version theo version ID. Sau đó thử `If-Match` với ETag cũ và `If-None-Match: *` khi object hiện hành tồn tại hoặc là delete marker. Ghi nhận khác biệt giữa **ETag, version ID và trạng thái current object**.

### Bài 5 — Multipart Complete có điều kiện

Upload nhiều part vào key mới; trước Complete, cho tác vụ khác tạo object ở cùng key. Gửi conditional Complete để quan sát phản hồi 412/409 tùy tranh chấp, rồi dọn multipart chưa hoàn thành. Trình bày lý do không chỉ HEAD trước khi bắt đầu multipart.

### Bài 6 — Thiết kế đa cloud

Đề xuất `ObjectCatalogPort` phục vụ S3, Azure Blob Storage và Google Cloud Storage. Chọn kiểu cursor và revision chung; diễn giải tại sao không thể cộng số trang hoặc dùng ETag AWS như generation của GCP. Mô tả cách kiểm thử cạnh tranh trên từng provider.

### Câu hỏi tự kiểm tra

1. `maxKeys` và `nextContinuationToken` khác nhau như thế nào?
2. Vì sao `continuationToken` không được suy ra từ key cuối của trang trước?
3. `prefix` và `delimiter` trả lời hai nhu cầu nào?
4. LIST nhiều trang có bảo đảm một snapshot transaction khi object thay đổi đồng thời không?
5. Khi nào dùng `StartAfter`, và vì sao cần cẩn thận với directory buckets?
6. Vì sao HEAD rồi PUT thông thường vẫn có race condition?
7. `If-None-Match: *` và `If-Match: ETag` biểu diễn hai ý định ghi khác nhau thế nào?
8. 412 và 409 trong conditional writes phải được xử lý ra sao?
9. Khi nào ETag không nên được dùng làm checksum MD5?
10. Versioning có tự chống việc cập nhật từ bản dữ liệu cũ không?
11. Vì sao conditional multipart cần được kiểm soát ở thời điểm Complete?
12. Idempotency record giúp giải quyết lỗi timeout sau PUT thành công thế nào?
13. Nếu S3 PUT thành công nhưng database optimistic update thất bại, cần xử lý object thừa ra sao?
14. IAM role có quyền `s3:PutObject` có bảo đảm mọi caller đều dùng điều kiện ghi không?
15. Azure và Google Cloud dùng cơ chế nào tương ứng cho cursor và conditional create/update?

Hoàn thành bài học này, người học phải triển khai được danh sách S3 có **cursor phân trang**, thao tác PUT có **precondition** để tránh ghi đè ngoài ý muốn, phân biệt lỗi tranh chấp với lỗi quyền/mạng và phối hợp **S3 Versioning + database optimistic locking** theo yêu cầu nghiệp vụ. Đây là nền tảng quan trọng khi triển khai Spring Boot với object storage managed trên nhiều cloud provider.

