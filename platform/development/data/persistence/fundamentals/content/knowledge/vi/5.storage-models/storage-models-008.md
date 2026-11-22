# Lưu trữ đối tượng (object storage) và dữ liệu kích thước lớn

Trong chương **Mô hình lưu trữ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, không phải mọi dữ liệu cần được biểu diễn thành những hàng nhỏ trong bảng quan hệ. Ứng dụng Java có thể phải tiếp nhận ảnh sản phẩm, hóa đơn PDF, video, bản ghi âm, tệp log, dữ liệu nhập hàng loạt hoặc tập kết quả phân tích có kích thước hàng gigabyte. Với những dữ liệu đó, **object storage** là một mô hình quan trọng bên cạnh database giao dịch, hệ tệp và các kho chuyên dụng khác.

Chọn object storage đúng cách không chỉ là “đưa file lên đám mây”. Cần xác định nguồn dữ liệu có thẩm quyền, thiết kế khóa và metadata, giới hạn dung lượng, tính toàn vẹn, kiểm soát truy cập, cách xử lý lỗi kết nối và retry, đồng bộ với database, quản lý phiên bản, sao lưu, vòng đời và chi phí. Những quyết định này liên quan trực tiếp đến ranh giới persistence, giao dịch, mô hình dữ liệu, lược đồ, truy vấn, chỉ mục và bảo mật của ứng dụng Java.

**Sau bài học, người học có thể:**

- Giải thích object, bucket, key, metadata và version; phân biệt object storage với block storage, file storage và BLOB trong database.
- Nhận biết workload phù hợp: tệp lớn, nhiều đối tượng, dữ liệu ít cập nhật tại chỗ, tải về, lưu trữ lịch sử và xử lý bất đồng bộ.
- Thiết kế tải lên/tải xuống theo luồng, multipart upload, checksum, range request và URL truy cập ngắn hạn mà không nạp cả tệp vào heap Java.
- Kết hợp object storage với metadata database theo một quy trình có trạng thái, idempotency và đối soát lỗi từng phần.
- Đặt yêu cầu bảo mật, độ bền, khả dụng, RPO/RTO, lifecycle và chi phí có thể kiểm chứng.

## 1. Object storage lưu cái gì?

**Đối tượng (object)** thường bao gồm ba phần:

1. **Nội dung (body):** một chuỗi byte, ví dụ dữ liệu JPEG, PDF, ZIP hoặc Parquet.
2. **Định danh:** một **key** bên trong **bucket/container** (và có thể có version ID nếu bật quản lý phiên bản).
3. **Metadata:** thuộc tính kỹ thuật như kiểu nội dung, độ dài, thời điểm sửa đổi, checksum và một số metadata do ứng dụng đặt.

Một hệ có thể định danh đối tượng bằng `bucket + key`; nếu bật versioning, `bucket + key + versionId` có thể xác định một phiên bản cụ thể. Cách gọi container, giới hạn kích thước, thao tác API, cơ chế nhất quán và hỗ trợ versioning **tùy sản phẩm**.

Ví dụ một tệp ảnh hóa đơn:

~~~text
bucket: application-documents
key: tenants/7f4a/orders/2026/11/ab/c6f9f4a7-.../original.pdf
content-type: application/pdf
size: 18,420,113 bytes
checksum: SHA-256 của byte nội dung đã chốt
version-id: ID do kho cung cấp (nếu có)
~~~

Key ở trên mô phỏng cấu trúc thư mục, nhưng trong nhiều object store nó chỉ là **chuỗi định danh có tiền tố**. Việc liệt kê theo prefix không làm phát sinh một hệ tệp POSIX đầy đủ. Đừng mặc định có thao tác đổi tên thư mục nguyên tử, mở file để sửa byte ở giữa, append hoặc lock file giống đĩa cục bộ.

### 1.1. Các thao tác thông dụng

| Thao tác | Ý nghĩa | Điểm cần chú ý |
| --- | --- | --- |
| `PUT` / upload | Tạo hoặc thay thế nội dung object theo key | Cần giới hạn kích thước, kiểm tra dữ liệu, xử lý request lặp |
| `GET` | Trả nội dung object | Cần phân quyền; có thể tải theo luồng hoặc theo khoảng byte |
| `HEAD` | Đọc metadata mà không tải body | Hữu ích khi xác minh object tồn tại và kích thước |
| `LIST` | Liệt kê object theo bucket/prefix | Phải phân trang; không nên dùng thay hệ chỉ mục nghiệp vụ |
| `DELETE` | Xóa object hoặc tạo delete marker theo versioning | Kết quả và khả năng phục hồi tùy trạng thái phiên bản, retention |
| Copy / compose | Tạo object mới dựa trên object hiện có | Không suy ra có `rename` nguyên tử như file system |
| Multipart upload | Chuyển một object thành nhiều phần rồi hoàn tất | Cần hoàn tất hoặc hủy upload dở, kiểm tra toàn vẹn |

Các API thường được truy cập qua HTTP và SDK. Object store có thể là dịch vụ quản lý hoặc hệ tương thích API được triển khai nội bộ. “Tương thích S3” không bảo đảm mọi endpoint, header, semantics và chức năng nâng cao đều giống hệt nhau; phải kiểm tra phiên bản sản phẩm đang dùng.

## 2. So sánh object storage với các mô hình khác

| Mô hình | Đơn vị thao tác nổi bật | Thường phù hợp | Hạn chế cần đánh giá |
| --- | --- | --- | --- |
| **Block storage** | Khối dữ liệu/volume gắn với máy hoặc hệ điều hành | Đĩa cho database, hệ tệp, ứng dụng cần I/O block | Không tự cung cấp danh mục object, HTTP API hay cơ chế chia sẻ quy mô lớn |
| **File storage** | File và thư mục với đường dẫn | Ứng dụng cần mở, sửa, rename hoặc dùng semantics hệ tệp | Scale, lock, giao thức chia sẻ và quản trị phụ thuộc giải pháp |
| **BLOB trong database** | Cột nhị phân gắn với hàng và transaction | Dữ liệu nhị phân nhỏ-vừa cần ràng buộc và ghi nguyên tử cùng metadata | Tăng dung lượng DB, log giao dịch, backup và tải I/O khi file lớn |
| **Object storage** | Toàn bộ object định danh bởi key | Ảnh, video, tài liệu, backup, tệp dữ liệu lớn, tải lên/xuống song song | Không có transaction chung với database, truy vấn nghiệp vụ và sửa nội dung tại chỗ hạn chế |

Object storage không mặc nhiên nhanh hơn hay rẻ hơn trong mọi trường hợp. **File nhỏ được truy cập cực nhiều lần**, dữ liệu cần cập nhật nhiều byte nhỏ với độ trễ rất thấp hoặc dữ liệu cần commit nguyên tử cùng bản ghi giao dịch có thể hợp hơn với cache, database hoặc file/block storage. Ngược lại, tệp lớn, nội dung ít thay đổi, tăng trưởng nhanh và yêu cầu phân phối qua mạng thường là điểm mạnh của object storage.

**Nguyên tắc:** chọn theo *mẫu truy cập và cam kết nghiệp vụ*, không theo đuôi tệp. Một JSON 200 byte có thể là bản ghi giao dịch cần SQL; một JSON nhiều gigabyte có thể là tệp xuất dữ liệu nên lưu object.

## 3. Những trường hợp sử dụng điển hình

| Bài toán | Dữ liệu chính | Vai trò thường chọn |
| --- | --- | --- |
| Người dùng tải ảnh đại diện | JPEG/PNG/WebP | Object lưu byte; database lưu owner, trạng thái, key; CDN/cache phục vụ đọc |
| Hóa đơn và chứng từ | PDF được chốt theo giao dịch | Object lưu nội dung bất biến; database xác định hóa đơn, quyền, checksum, version |
| Video/bản ghi âm | Tệp lớn; có thể cần chuyển mã | Object chứa bản gốc và nhiều bản phái sinh; worker xử lý bất đồng bộ |
| Import dữ liệu | CSV/JSONL/Parquet lớn | Object làm vùng tiếp nhận, hàng đợi/job xử lý, database lưu kết quả và lỗi |
| Log/archive | Tệp ghi thành lô theo thời gian | Object phục vụ retention, truy vấn qua engine phù hợp khi cần |
| Backup | Snapshot, dữ liệu nền và nhật ký phục hồi | Object store có thể làm đích backup nếu đáp ứng tính toàn vẹn, tách biệt và quy trình restore |

Không nên xem object store là **cơ sở dữ liệu tìm kiếm nghiệp vụ**. Muốn tìm “tất cả hóa đơn của khách X trong tháng Y”, thông thường truy vấn bảng metadata có chỉ mục theo `customer_id`, `created_at`, `status`; sau đó mới dùng key để tải đúng object. Không liệt kê toàn bộ bucket rồi lọc tên file trong ứng dụng.

## 4. Thiết kế key và metadata từ đầu

### 4.1. Key là định danh kỹ thuật, không phải tên hiển thị

Nên tạo key ổn định, duy nhất và ít chứa thông tin nhạy cảm. Ví dụ:

~~~text
tenants/{tenantId}/assets/{yyyy}/{mm}/{objectId}/original
tenants/{tenantId}/assets/{yyyy}/{mm}/{objectId}/preview
imports/{jobId}/source
exports/{jobId}/result
~~~

Trong các mẫu này, các phần trong ngoặc nhọn là biến do server kiểm soát. Một `objectId` ngẫu nhiên giúp giảm va chạm; tên file gốc nên lưu như metadata đã chuẩn hóa, **không dùng trực tiếp làm key** nếu chứa thông tin cá nhân, ký tự nguy hiểm hoặc có thể gây ghi đè. Key có thể xuất hiện trong log, URL và sự kiện; không đặt token hay email riêng tư vào đó.

**Không được suy ra quyền truy cập từ việc biết key.** Key khó đoán chỉ là một thuộc tính phụ; truy cập phải dựa trên xác thực, phân quyền và chính sách bucket/object.

### 4.2. Metadata kỹ thuật và nghiệp vụ

Object storage thường có metadata cơ bản, nhưng ứng dụng cần bảng **catalog** để quản lý quyền sở hữu, tra cứu và trạng thái xử lý. Ví dụ lược đồ PostgreSQL:

~~~sql
CREATE TABLE stored_object (
    object_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    bucket_name TEXT NOT NULL,
    object_key TEXT NOT NULL,
    object_version TEXT,
    original_filename TEXT,
    content_type TEXT,
    byte_size BIGINT CHECK (byte_size >= 0),
    sha256_hex CHAR(64),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'VERIFYING', 'READY', 'REJECTED', 'DELETING')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMPTZ,
    UNIQUE (tenant_id, request_id),
    UNIQUE (bucket_name, object_key)
);

CREATE INDEX idx_stored_object_tenant_status_created
    ON stored_object (tenant_id, status, created_at DESC);
~~~

**Ý nghĩa của các trường:**

- `object_id` là định danh nghiệp vụ nội bộ; key là đường dẫn kỹ thuật có thể được đổi theo quy trình migration.
- `tenant_id` làm cơ sở kiểm tra quyền và lọc danh sách. Mọi truy vấn đa tenant phải kiểm soát tenant từ danh tính đã xác thực.
- `request_id` giúp nhận diện cùng một yêu cầu tải lên được thử lại; tái sử dụng ID với nội dung hoặc mục đích khác phải bị từ chối.
- `byte_size`, `content_type`, `sha256_hex` có thể để trống khi mới cấp phép, rồi được xác minh trước khi chuyển `READY`.
- `object_version` tùy chọn; nếu kho bật versioning, giữ ID của phiên bản cần tham chiếu để tránh vô tình đọc bản đã bị thay thế.
- `status` cho biết người dùng có được xem/tải object hay chưa. `PENDING` và `VERIFYING` không tự động đồng nghĩa nội dung đã an toàn.

Một bảng catalog **không chứa byte nội dung**. Database vẫn dùng transaction, khóa, chỉ mục và ràng buộc để bảo vệ danh tính, quyền sở hữu, phiên bản và trạng thái. Object store giữ nội dung lớn, có thể phục vụ tải xuống độc lập.

## 5. Vì sao cần tách database và object store?

Một quy trình upload có hai hệ thống lưu trữ:

~~~mermaid
flowchart TB
    U["Client / ứng dụng Java"] --> API["API xác thực, cấp objectId"]
    API --> DB[("Metadata DB: PENDING")]
    API --> URL["Quyền upload ngắn hạn / SDK"]
    URL --> OS[("Object storage: bytes")]
    OS --> V["Worker kiểm tra kích thước, checksum, loại nội dung"]
    V --> SC["Quét an toàn và xử lý theo chính sách"]
    SC --> DB2[("Metadata DB: READY hoặc REJECTED")]
    DB2 --> RD["API tra quyền rồi cho tải object"]
~~~

**Database và object storage thường không nằm trong một transaction ACID chung.** Không thể chỉ gọi `INSERT metadata`, `PUT object` rồi cho rằng hai thao tác luôn cùng commit hoặc cùng rollback. Cần **state machine**, idempotency và bước đối soát để xử lý lỗi giữa chừng.

### 5.1. Quy trình upload có trạng thái

1. **Khởi tạo:** API xác thực người dùng, kiểm tra quota và quyền upload, nhận `requestId` ổn định rồi tạo `objectId`, `objectKey` mới trong bảng catalog với `PENDING`.
2. **Cấp quyền truyền:** server upload bằng SDK hoặc cấp URL/credential ngắn hạn chỉ được ghi vào đúng object key và phạm vi cho phép. Không cấp quyền toàn bucket cho client.
3. **Truyền byte:** client gửi nội dung theo luồng hoặc nhiều phần. Theo dõi trạng thái multipart và hoàn tất theo API của kho.
4. **Xác minh:** server kiểm tra object có tồn tại, độ dài, checksum đáng tin cậy, loại dữ liệu thực, quyền sở hữu và kết quả quét nội dung độc hại nếu loại file yêu cầu.
5. **Công bố:** chỉ sau khi đạt điều kiện mới cập nhật bản ghi thành `READY` bằng một giao dịch database. Các đường đọc sản phẩm chỉ chọn object `READY`.
6. **Khắc phục lỗi:** bộ đối soát tìm bản ghi `PENDING` quá hạn, upload dở, object không có metadata hay bản ghi `READY` nhưng object mất; điều tra và sửa hoặc thu gom theo chính sách.

Ví dụ câu lệnh công bố có điều kiện:

~~~sql
UPDATE stored_object
SET status = 'READY',
    byte_size = :actual_size,
    sha256_hex = :verified_sha256,
    content_type = :verified_type,
    object_version = :confirmed_version,
    ready_at = CURRENT_TIMESTAMP
WHERE object_id = :object_id
  AND tenant_id = :tenant_id
  AND status = 'VERIFYING';
~~~

Trong JDBC dùng `PreparedStatement` với dấu `?` thay cho `:named_parameter`. Kiểm tra số dòng đã cập nhật bằng **1**; nếu bằng 0, trạng thái đã đổi hoặc không tìm thấy. Cần định nghĩa chuyển `PENDING → VERIFYING` bằng thao tác có điều kiện, và bảo đảm quá trình kiểm tra gắn với **đúng phiên bản nội dung**; không xác minh object A rồi vô tình cấp quyền tải object B vừa bị ghi đè.

### 5.2. Các trường hợp thất bại từng phần

| Thời điểm lỗi | Dữ liệu có thể còn | Cách xử lý |
| --- | --- | --- |
| Tạo `PENDING` xong nhưng client không upload | Chỉ còn hàng metadata | Hết hạn yêu cầu và chuyển trạng thái/thu gom |
| Upload xong nhưng API mất kết nối trước khi xác nhận | Object đã có, metadata còn `PENDING` | Tra theo `requestId`, `HEAD`/xác minh object rồi tiếp tục; tránh tạo object trùng |
| Ghi metadata `READY` thất bại | Object hợp lệ nhưng chưa được công bố | Retry cập nhật có điều kiện, giữ dấu vết; đối soát sau |
| Quét phát hiện file không hợp lệ | Object tạm có thể vẫn tồn tại | Đánh dấu `REJECTED`, cách ly và xóa theo chính sách |
| Object bị xóa ngoài quy trình | Metadata còn `READY` | Phát cảnh báo, chặn đường tải, khôi phục từ version/backup nếu có |
| Client dùng lại cùng request ID với nội dung khác | Trùng yêu cầu nhưng byte khác | Từ chối xung đột, không trả nhầm kết quả đã lưu |

**Không xóa ngay mọi object không tìm thấy metadata:** thao tác upload hoặc cập nhật catalog có thể vẫn đang diễn ra, đọc danh sách có thể khác semantics theo nhà cung cấp. Bộ dọn rác cần thời gian chờ, trạng thái, khóa/lease khi cần, log và thao tác xóa có thể lặp an toàn. Nếu upload dùng key cố định có nguy cơ ghi đè, dùng chính sách key bất biến hoặc conditional write/versioning theo khả năng của kho.

## 6. Truyền dữ liệu lớn mà không làm đầy heap Java

Với tệp 8 GiB, cách gọi `Files.readAllBytes(path)` hoặc `inputStream.readAllBytes()` không phù hợp: nó cố nạp cả nội dung vào bộ nhớ và có thể gây `OutOfMemoryError`. Hãy xử lý theo **luồng có bộ đệm giới hạn**, hoặc dùng API upload từ file và multipart upload khi cần.

### 6.1. Tính checksum theo luồng

Ví dụ Java 17+ tạo SHA-256 cho một tệp đã được ghi ổn định:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class FileChecksum {
    public static String sha256(Path file) throws IOException {
        final MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }

        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = input.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Bộ đệm chỉ 64 KiB dù tệp dài nhiều gigabyte. Với một tệp có thể bị thay đổi trong lúc đang băm rồi upload, checksum của bước kiểm tra có thể khác byte thực đã gửi. Vì vậy, cần **nguồn byte bất biến trong quá trình truyền** hoặc xác minh checksum ở phía object store/sau khi upload. Không coi checksum tính trước upload là bằng chứng duy nhất rằng đối tượng đã được lưu nguyên vẹn.

### 6.2. Upload từ file bằng SDK

Ví dụ dùng **AWS SDK for Java v2** (minh họa một API cụ thể, không phải yêu cầu bắt buộc của object storage):

~~~java
import java.nio.file.Path;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

public final class ObjectUploader {
    private final S3Client client;

    public ObjectUploader(S3Client client) {
        this.client = client;
    }

    public void uploadFile(
            String bucket, String key, Path stagedFile, String contentType) {
        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(contentType)
                .build();
        client.putObject(request, RequestBody.fromFile(stagedFile));
    }
}
~~~

SDK có thể đọc tệp từ disk mà không cần ứng dụng tạo một mảng byte bằng kích thước cả tệp. Ví dụ này phù hợp với **upload đơn lẻ trong giới hạn API của nhà cung cấp**, chưa có multipart, checksum đầu-cuối, idempotency, quota, phân quyền, xác minh version hay xử lý timeout. Mã production cần chọn loại upload dựa trên kích thước, chính sách retry và khả năng hỗ trợ của SDK; không suy ra mọi object kích thước lớn đều có thể gửi bằng một lệnh `PutObject`.

Nếu tải trực tiếp từ trình duyệt, có thể dùng URL đã ký trong thời gian ngắn (presigned URL) để tránh đi vòng byte qua server Java. Server vẫn phải xác thực quyền, cấp key duy nhất, giới hạn mục đích và sau upload **kiểm tra nội dung thực tế**. URL ký cho một PUT không tự động bảo đảm giới hạn dung lượng hoặc MIME chính xác trong mọi cấu hình; các giới hạn phải được thực thi bằng chính sách phù hợp và bước xác minh sau upload. Với object không được phép công khai, URL tải về cũng nên có TTL ngắn và quyền gắn với người dùng.

### 6.3. Multipart upload và truyền tiếp sau lỗi

Với tệp lớn, object store thường cung cấp **multipart upload**:

1. Khởi tạo một phiên upload, nhận `uploadId`.
2. Chia dữ liệu thành các part trong giới hạn kích thước/số lượng mà nhà cung cấp hỗ trợ.
3. Gửi từng part, có thể song song có giới hạn để tránh bão hòa mạng và bộ nhớ.
4. Lưu định danh part, trạng thái/checksum/ETag theo yêu cầu API của kho.
5. Hoàn tất (complete) khi đủ part; hoặc hủy (abort) nếu quyết định bỏ upload.
6. Xác minh object hoàn chỉnh trước khi công bố `READY`.

~~~mermaid
flowchart LR
    F["File lớn"] --> S["Chia part"]
    S --> P1["Part 1"]
    S --> P2["Part 2"]
    S --> PN["Part N"]
    P1 --> C["Complete multipart"]
    P2 --> C
    PN --> C
    C --> V["Verify size + checksum + version"]
    V --> D[("Catalog: READY")]
~~~

Upload dở có thể chiếm dung lượng hoặc phát sinh phí; cần chính sách hủy hoặc tự xóa multipart chưa hoàn tất. Với retry, giữ `uploadId`, thứ tự part và thông tin phiên; **không hoàn tất một object từ các part không cùng phiên hoặc không được xác minh**.

**ETag không phải lúc nào cũng là MD5 của nội dung.** Với multipart, mã hóa hoặc cấu hình cụ thể, ETag có thể mang ngữ nghĩa khác. Muốn xác minh toàn vẹn đầu-cuối, dùng cơ chế checksum chính thức của kho và/hoặc SHA-256 do ứng dụng tính trên cùng nội dung; xác định rõ byte gốc và byte đã biến đổi/nén được băm ở bước nào.

### 6.4. Download theo luồng và theo khoảng byte

Khi tải xuống, Java cũng không nên đọc toàn bộ body vào heap. Ví dụ dùng interface lưu trữ do ứng dụng tự định nghĩa:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

interface ObjectReader {
    InputStream open(String bucket, String key) throws IOException;
}

public final class ObjectDownloader {
    private final ObjectReader reader;

    public ObjectDownloader(ObjectReader reader) {
        this.reader = reader;
    }

    public void download(String bucket, String key, Path destination)
            throws IOException {
        try (InputStream source = reader.open(bucket, key);
             OutputStream target = Files.newOutputStream(
                     destination,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {
            byte[] buffer = new byte[64 * 1024];
            int size;
            while ((size = source.read(buffer)) != -1) {
                target.write(buffer, 0, size);
            }
        }
    }
}
~~~

Interface `ObjectReader` ở đây là **giả định để minh họa**, không phải API sẵn có của JDK. Mã sản phẩm cần có timeout, giới hạn kích thước, kiểm tra byte tải về, xử lý tệp dở, dọn file khi tải lỗi và kiểm soát đường dẫn đầu ra. Đường dẫn `destination` phải do server kiểm soát, không tạo trực tiếp từ tên file người dùng gửi.

Với video, PDF lớn hoặc tải tiếp, HTTP **Range request** có thể chỉ lấy khoảng byte:

~~~http
GET /assets/document HTTP/1.1
Range: bytes=0-1048575
~~~

Nếu server hỗ trợ và đáp ứng khoảng byte, nó có thể trả `206 Partial Content` và `Content-Range`. Client cần xác minh response và version/ETag theo hợp đồng tải tiếp; không ghép các mảnh từ hai phiên bản object khác nhau. Một số hệ xử lý nén, mã hóa, CDN hoặc proxy cần cấu hình thêm để phục vụ range nhất quán.

## 7. Tính nhất quán, tính bền vững và quyền ghi

Object storage có thể rất bền vững nhờ cơ chế sao chép hoặc mã sửa lỗi, nhưng cần phân biệt:

- **Durability:** nội dung object đã được xác nhận lưu có sống sót sau một phạm vi lỗi được mô tả không?
- **Availability:** có truy cập được object khi một máy hoặc vùng gặp sự cố không?
- **Consistency:** ngay sau PUT/DELETE, GET/HEAD/LIST trên các endpoint và vùng có nhìn thấy đúng kết quả mới nhất không?
- **Atomicity ở mức object:** việc thay một object được quan sát như thay toàn bộ nội dung có được bảo đảm không?
- **Transaction nhiều object:** có thể commit hoặc rollback đồng thời nhiều object và metadata database không?

**Không suy ra một câu trả lời chung cho mọi nhà cung cấp.** Một số dịch vụ có nhất quán mạnh cho thao tác trên object, một số sản phẩm hoặc cấu hình replication liên vùng có độ trễ. Phải đọc hợp đồng và kiểm thử cho các thao tác cụ thể: tạo, ghi đè, xóa, liệt kê, copy, versioning và failover.

Đối với dữ liệu nghiệp vụ có quyền ghi, nên định nghĩa **một nguồn có thẩm quyền** cho trạng thái catalog và tránh cho nhiều dịch vụ ghi đè cùng key tùy tiện. Một mẫu an toàn là **object key bất biến cho mỗi phiên bản**: bản mới dùng key mới, rồi cập nhật tham chiếu trong database bằng optimistic locking hoặc transaction. Cách này đơn giản hóa cache và tránh người đọc tải một nội dung bị thay thế ngoài ý muốn.

### 7.1. Ghi nhiều object có phải giao dịch không?

Giả sử ứng dụng tạo tài liệu và ảnh xem trước, lưu ở hai key khác nhau. Không nên giả định có thể commit cả hai object và một hàng database cùng lúc. Có thể dùng trạng thái:

`PENDING → UPLOADING → PROCESSING → READY`

Trong đó `READY` chỉ được công bố khi mọi object bắt buộc đã tồn tại, được xác minh và liên kết hợp lệ. Khi một bước lỗi, worker có thể thử lại hoặc bù/thu gom object tạm. Các bước phải **idempotent** và có deadline để không giữ trạng thái treo vô hạn.

## 8. Bảo mật dữ liệu lớn và đường tải lên

Một object có thể chứa thông tin định danh, tài liệu tài chính, hình ảnh cá nhân hoặc mã độc. Thiết kế cần bảo vệ cả API và kho nội dung:

1. **Phân quyền:** chỉ server hoặc credential giới hạn mới được tạo URL upload. Khi tải, kiểm tra quyền theo `tenant_id`, `object_id` và trạng thái `READY`; không mở toàn bộ bucket để “tiện tích hợp”.
2. **Mã hóa:** yêu cầu TLS khi truyền; mã hóa khi lưu theo chính sách; quản lý khóa và quyền giải mã riêng với quyền xem metadata khi cần.
3. **Kiểm tra loại nội dung:** `Content-Type` và phần mở rộng chỉ là khai báo, có thể bị giả mạo. Xác minh định dạng thực, giới hạn decompression/zip bomb, quét mã độc theo mức rủi ro trước khi công bố.
4. **Phòng lạm dụng:** giới hạn tổng dung lượng theo user/tenant, tốc độ upload, số lượng request, tuổi của URL đã ký và số upload chưa hoàn tất.
5. **Tải xuống an toàn:** đặt `Content-Disposition` phù hợp, kiểm soát cache của dữ liệu riêng tư, hạn chế loại nội dung có thể thực thi hoặc gây XSS trên cùng origin.
6. **Kiểm toán:** lưu ai tải lên, xác minh và tải xuống object nào; không ghi token, presigned URL đầy đủ hoặc dữ liệu nhạy cảm vào log.
7. **Nguyên tắc ít quyền nhất:** tài khoản worker xử lý preview chỉ được đọc nguồn và ghi prefix đầu ra cần thiết; job dọn rác có phạm vi riêng và được giám sát.

Nếu cần phát URL tải về cho người dùng, áp dụng **xác thực ở API cấp URL** trước, giới hạn thời hạn và mục đích. URL đã ký có thể được sử dụng bởi bất kỳ ai có URL trong thời gian còn hiệu lực; vì vậy tránh để lộ qua log, referrer hoặc hệ thống phân tích.

## 9. Versioning, lifecycle, backup và khôi phục

### 9.1. Versioning không giống backup

Bật versioning giúp giữ nhiều phiên bản object và có thể khôi phục khi ghi đè/xóa nhầm theo khả năng của kho. Nhưng nếu tài khoản bị xâm nhập có quyền xóa mọi version, bucket bị xóa hoặc cùng miền lỗi bị phá hủy, **versioning một mình không thay thế kế hoạch backup**.

Khi object chứa dữ liệu quan trọng, cần xác định:

- Có bật versioning, object lock/retention hay cơ chế bất biến phù hợp không?
- Backup hoặc replication sang vị trí/tài khoản tách biệt có bảo vệ trước xóa sai không?
- Quá trình restore lấy **đúng version**, checksum và catalog metadata có khớp nhau không?
- **RPO** (mức mất dữ liệu tối đa) và **RTO** (thời gian khôi phục mục tiêu) của object store và metadata database đã được thử chưa?
- Quy trình xóa dữ liệu cá nhân, retention bắt buộc và legal hold được giải quyết thế nào nếu có nhiều bản sao/version?

Metadata database cũng cần sao lưu phù hợp. Khôi phục một bucket đầy đủ nhưng mất bảng ánh xạ `objectId → key` có thể khiến ứng dụng không tìm được dữ liệu. Ngược lại, khôi phục catalog tới thời điểm cũ nhưng object store đã thay đổi có thể tạo tham chiếu mồ côi. Kế hoạch phục hồi cần **đối soát hai phía** với cùng mốc hoặc quy trình tái lập nhất quán.

### 9.2. Lifecycle và lưu trữ theo tầng

Object store thường có các tầng lưu trữ theo mức độ truy cập, ví dụ thường xuyên, ít truy cập và lưu trữ lạnh. Chuyển tầng có thể tiết kiệm phí lưu dữ liệu nhưng làm tăng phí truy xuất, thời gian khôi phục và/hoặc giới hạn tối thiểu thời gian lưu.

Một chính sách minh họa:

| Loại object | Mẫu truy cập | Chính sách cân nhắc |
| --- | --- | --- |
| Ảnh sản phẩm hiện hành | Đọc nhiều, yêu cầu thấp độ trễ | Tầng thường xuyên, CDN/cache nếu phù hợp |
| Video gốc đã chuyển mã | Ít đọc lại sau xử lý | Chuyển tầng sau thời gian quan sát |
| File import đã xử lý | Chỉ cần để đối soát ngắn hạn | TTL và xóa có kiểm soát theo chính sách |
| Báo cáo cuối năm | Hiếm đọc nhưng cần lưu lâu | Archive, có tính thời gian restore khi cần |
| Multipart dở | Không dùng được làm object hoàn chỉnh | Hủy/xóa sau ngưỡng an toàn |

Không đặt lifecycle xóa vĩnh viễn theo một quy tắc ngày chung nếu vẫn có nghĩa vụ lưu hoặc người dùng đang sở hữu dữ liệu. Cũng không mặc định “xóa catalog” là “đã xóa hết mọi phiên bản và backup”; cần quy trình xóa đồng bộ với chính sách retention.

## 10. Chi phí object storage gồm những gì?

Tổng chi phí có thể gồm:

- Dung lượng **GB/TB-tháng**, tính cả version cũ, object phái sinh và upload dở.
- Số lần PUT/GET/LIST/HEAD và những thao tác đặc thù của từng tầng.
- Lưu lượng truyền ra ngoài hệ thống, truyền qua vùng và chi phí CDN.
- Chi phí truy xuất/restore từ tầng lạnh và thời gian giữ tối thiểu.
- Replication, mã hóa/quản lý khóa, quan sát hệ thống, worker chuyển mã/quét file.
- Backup độc lập, log và cơ chế khôi phục.

Ví dụ, **500.000 tệp có kích thước trung bình 20 MB** tương đương khoảng **10 TB (đơn vị thập phân)** nội dung gốc trước khi cộng bản preview, version cũ, replication, backup và metadata. Nếu mỗi tệp có hai bản chuyển mã và tổng kích thước bằng 1,5 lần bản gốc, dung lượng nội dung có thể thành khoảng **25 TB** trước các lớp dự phòng khác. Đây chỉ là phép tính dung lượng, không phải báo giá.

Chi phí cũng ảnh hưởng thiết kế key và truy vấn. Liệt kê toàn bucket để tìm hồ sơ vừa chậm vừa phát sinh request; catalog có index giúp truy vấn nghiệp vụ nhanh và chỉ tải object cần thiết. Không nên tối ưu duy nhất giá mỗi GB nếu tải xuống và truy xuất chiếm phần lớn chi phí thực.

## 11. Thiết kế kiểm thử và các số đo

Một lựa chọn object storage cần được xác nhận bằng workload đại diện, không chỉ bởi việc upload một file nhỏ thành công.

| Kiểm thử | Điều phải xác minh |
| --- | --- |
| Upload tệp 1 KiB, vài MB và nhiều GB | Không nạp cả file lên heap; giới hạn tệp và multipart được xử lý |
| Mạng đứt ở giữa upload | Retry/tiếp tục có kiểm soát; không công bố object dở |
| Mạng đứt sau khi object store đã nhận PUT | Dùng request ID và HEAD/checksum để đối soát, không tạo hai bản nghiệp vụ |
| Hai client upload cùng một request ID | Một kết quả hợp lệ hoặc xung đột rõ ràng; không ghi đè ngoài ý muốn |
| Object bị thay giữa xác minh và tải | Phát hiện sai version/checksum, tránh cung cấp nội dung chưa được xác minh |
| Tệp giả MIME, tệp độc hại, tệp nén cực lớn | Bị chặn/cách ly theo chính sách, không công bố `READY` |
| Upload hoàn tất nhưng cập nhật DB lỗi | Có hàng `PENDING` và quy trình đối soát/khôi phục |
| Catalog `READY` nhưng object mất | Đường đọc báo lỗi có kiểm soát, cảnh báo và kế hoạch phục hồi |
| Bật versioning rồi xóa nhầm | Khôi phục đúng version và metadata theo RPO/RTO |
| File lớn tải nhiều người cùng lúc | p95/p99, throughput, chi phí egress, rate limit và tài nguyên Java |

Các chỉ số vận hành hữu ích: số object `PENDING` quá hạn, lỗi multipart, byte upload thành công/thất bại, tỷ lệ checksum mismatch, số tham chiếu mồ côi, độ trễ từ upload đến `READY`, tỷ lệ lỗi download, dung lượng theo tier, chi phí request/egress và thời gian restore đã thử.

## 12. Tình huống thực hành: quản lý tệp video

Một nền tảng học trực tuyến viết bằng Java nhận video gốc từ giảng viên, chuyển mã thành nhiều độ phân giải và cho học viên xem. Mỗi video có thể lớn 4–12 GiB. Hệ thống đang dùng:

- PostgreSQL cho khóa học, bài giảng, quyền truy cập và trạng thái công bố.
- Object storage chứa video gốc, bản chuyển mã và ảnh thumbnail.
- Worker xử lý bất đồng bộ, một dịch vụ CDN phục vụ video đã duyệt.

**Bài toán:**

1. Thiết kế `objectId`, key và các bảng metadata cho video gốc và các bản phái sinh.
2. Nêu luồng từ `PENDING` đến `READY`: ai upload, ai xác minh checksum, ai xử lý chuyển mã và khi nào học viên được xem.
3. Giảng viên upload xong nhưng mất mạng trước khi thấy kết quả. Làm sao để lần thử lại không tạo hai video trùng trong khóa học?
4. Worker chuyển mã hoàn tất ba độ phân giải nhưng cập nhật database thất bại. Cần giữ trạng thái gì và xử lý lại thế nào?
5. Một video bị báo cáo có nội dung không được phép. Làm sao tạm chặn tải mà vẫn giữ dữ liệu phục vụ điều tra theo chính sách?
6. Nếu object store vẫn còn video nhưng catalog PostgreSQL được phục hồi về trạng thái cũ, hệ thống tìm và khôi phục ánh xạ bằng cách nào?

**Hướng giải tham khảo:**

- Mỗi phiên bản nội dung có key mới, gắn vào `objectId` và bản ghi bài giảng có phiên bản/ownership. Bản gốc và bản chuyển mã có quan hệ nguồn–đầu ra được lưu rõ.
- Client upload theo multipart hoặc cơ chế SDK phù hợp; worker xác minh kích thước/checksum, định dạng và quét an toàn trước khi đưa file vào luồng xử lý.
- Lệnh tạo video nhận `requestId` từ client; hàng metadata có unique constraint theo tenant/request. Retry tra cứu kết quả cũ và đối soát object đã ghi.
- Nếu object đã chuyển mã nhưng metadata chưa commit, worker có thể retry cập nhật có điều kiện bằng job ID, hoặc đối soát rồi thu gom kết quả dư. Chỉ công bố bài giảng khi các tài nguyên bắt buộc ở trạng thái hợp lệ.
- Chặn truy cập từ API/catalog và vô hiệu hóa đường phân phối/cache phù hợp; xử lý object theo retention, bằng chứng và quyền đã định.
- Khôi phục catalog, đối chiếu danh sách/version, metadata nguồn, manifest và log xử lý; không mặc định chỉ dùng tên key để suy ra quyền sở hữu nếu thiếu nguồn kiểm chứng.

## 13. Checklist trước khi dùng object storage

- [ ] Đã xác định tệp nào thuộc object storage và dữ liệu nào vẫn cần database giao dịch.
- [ ] Có quy tắc bucket/key, version bất biến, metadata nghiệp vụ và quyền theo tenant.
- [ ] Upload/download theo luồng hoặc multipart, có timeout, checksum, giới hạn kích thước và xử lý file dở.
- [ ] Hệ thống không công bố tệp trước khi kiểm tra nội dung, quyền, trạng thái và tính toàn vẹn.
- [ ] Database và object storage được kết nối qua state machine/idempotency và cơ chế đối soát lỗi từng phần.
- [ ] Không dùng `LIST` toàn bucket làm truy vấn nghiệp vụ; metadata có index và phân trang phù hợp.
- [ ] Đã kiểm tra semantics consistency, versioning, conditional write, delete và failover của nhà cung cấp.
- [ ] Credential, URL ký, mã hóa, MIME, quét nội dung, audit và quyền đọc/ghi/xóa được kiểm soát.
- [ ] Có lifecycle, chính sách retention/xóa, xử lý multipart dở, backup và restore cả catalog lẫn object.
- [ ] Đã đo p95/p99, throughput, chi phí dung lượng/request/egress và thời gian phục hồi.

**Ghi nhớ:** object storage phù hợp để lưu **nội dung lớn được định danh bằng key và truy cập qua API**. Nó giúp ứng dụng Java mở rộng khả năng nhận và phân phối tệp, nhưng không tự thay thế database giao dịch, chỉ mục nghiệp vụ hoặc tính nguyên tử giữa nhiều hệ thống. Thiết kế tốt luôn đi kèm catalog metadata có thẩm quyền, truyền theo luồng, kiểm tra toàn vẹn, quy trình trạng thái có thể retry, phân quyền chặt chẽ và phương án đối soát/khôi phục đã được thử.
