# Storage key tách khỏi filename người dùng

## 1. Vì sao không dùng filename làm storage key?

Khi người dùng upload file, request multipart thường có một filename do client gửi, ví dụ `invoice.pdf`, `avatar.png` hoặc `../../config/application.yml`. Filename này hữu ích để hiển thị cho người dùng, nhưng nó là dữ liệu không tin cậy. Client có thể tự sửa filename, gửi ký tự phân cách đường dẫn, tên trùng, Unicode khó nhìn, phần mở rộng gây hiểu nhầm hoặc chuỗi rất dài.

Nếu dùng nguyên filename làm đường dẫn hoặc object key lưu trữ, ứng dụng có thể gặp:

- **Path traversal:** filename chứa `../`, `..\\` hoặc biến thể encoding để thoát khỏi thư mục dự kiến.
- **Overwrite/collision:** hai người dùng upload `report.pdf`; file sau ghi đè file trước hoặc vô tình được truy cập thay thế.
- **Cross-tenant collision:** tenant A và B có cùng filename, nhưng storage namespace không phân biệt tenant.
- **Name confusion:** Unicode normalization, ký tự điều khiển, dấu chấm cuối, tên thiết bị Windows hoặc double extension làm hệ thống và người vận hành hiểu khác nhau.
- **Unsafe content handling:** phần mở rộng do client chọn khiến ứng dụng hoặc browser đoán sai loại nội dung.
- **Information disclosure:** đường dẫn chứa tên khách hàng, số hợp đồng hoặc thông tin nhạy cảm xuất hiện trong log, URL và lỗi hệ thống.

Thiết kế an toàn là tách hai khái niệm:

- **Original filename:** tên do người dùng gửi, chỉ dùng như metadata để hiển thị hoặc gợi ý tên tải xuống sau khi xử lý an toàn.
- **Storage key:** định danh nội bộ do server tạo, duy nhất và không phụ thuộc filename. Dùng key này để lưu, đọc, xóa và quản lý object.

Ví dụ, người dùng upload `Bao cao thang 11.pdf`. Server có thể tạo storage key `uploads/7f/7f3a...c91d` và lưu mapping trong database. Khi tải xuống, ứng dụng tra metadata rồi trả tên thân thiện `Bao cao thang 11.pdf` qua `Content-Disposition`. Tên hiển thị không quyết định vị trí vật lý của file.

## 2. Phân biệt filename, storage key và file ID

Các hệ thống nên phân biệt rõ ít nhất ba giá trị:

| Giá trị | Ai tạo? | Mục đích | Có được dùng làm đường dẫn lưu trữ? |
|---|---|---|---|
| Original filename | Client/người dùng | Tên gốc được cung cấp trong multipart metadata. | Không. |
| Storage key | Server hoặc storage service | Định vị object/file trong filesystem hoặc object storage. | Có, sau khi được server tạo và kiểm soát. |
| File ID | Server | Định danh record nghiệp vụ/API, thường là UUID hoặc ID opaque. | Không nhất thiết; nên tra qua metadata để lấy storage key. |

Ví dụ một record metadata:

```json
{
  "fileId": "4f8e2f17-2b8a-4e50-9a9b-23e8a4c9c9a1",
  "tenantId": "tenant-42",
  "storageKey": "objects/7f/7f3a2b1c-9f4a-4a6a-8d17-7b31a7c3c91d",
  "originalFilename": "Bao cao thang 11.pdf",
  "mediaType": "application/pdf",
  "size": 248120,
  "status": "AVAILABLE"
}
```

Trong API công khai, thường chỉ trả `fileId` hoặc download endpoint, không cần để lộ storage key nội bộ. Storage key không phải credential và không thay thế authorization. Ngay cả khi key khó đoán, server vẫn phải kiểm tra user/tenant có quyền đọc file đó hay không.

## 3. Sinh storage key ở phía server

Storage key cần được tạo từ nguồn ngẫu nhiên an toàn hoặc cơ chế ID duy nhất do storage service cung cấp. Không tạo key bằng cách ghép filename, email, username, timestamp dễ đoán hoặc ID nghiệp vụ nhạy cảm.

Các lựa chọn thường gặp:

- UUID v4 hoặc random identifier có entropy đủ lớn.
- 128 bit trở lên từ cryptographically secure random generator.
- ID do object storage sinh, nếu API storage bảo đảm uniqueness và ứng dụng có thể quản lý mapping.
- Prefix phân vùng do server tạo (ví dụ theo shard hoặc tenant ID nội bộ đã xác minh) cộng với random suffix.

Ví dụ cấu trúc key:

```text
objects/7f/7f3a2b1c-9f4a-4a6a-8d17-7b31a7c3c91d
```

Prefix `7f` có thể được suy ra từ vài ký tự đầu của random ID để phân bố object theo thư mục. Nó không chứa filename. Với object storage, có thể dùng key phẳng hoặc prefix phân vùng tùy cách tổ chức bucket và lifecycle.

Không dùng storage key như cơ chế kiểm soát truy cập. UUID ngẫu nhiên làm giảm khả năng đoán, nhưng URL/key bị lộ vẫn có thể bị sử dụng nếu bucket công khai hoặc endpoint thiếu authorization. Bucket nên private; API kiểm tra quyền trước khi trả file hoặc tạo signed URL.

## 4. Lưu metadata mapping trong database

Database giữ thông tin nghiệp vụ và ánh xạ từ file ID tới storage key. Một schema ví dụ:

```sql
CREATE TABLE stored_file (
    file_id             UUID PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    owner_id            UUID NOT NULL,
    storage_provider    VARCHAR(30) NOT NULL,
    storage_bucket      VARCHAR(120),
    storage_key         VARCHAR(500) NOT NULL,
    original_filename   VARCHAR(255) NOT NULL,
    detected_media_type VARCHAR(120) NOT NULL,
    declared_media_type VARCHAR(120),
    byte_size           BIGINT NOT NULL,
    sha256              CHAR(64) NOT NULL,
    status              VARCHAR(24) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ,
    CONSTRAINT uq_storage_object
        UNIQUE (storage_provider, storage_bucket, storage_key)
);
```

Các trường `tenant_id`, `owner_id` giúp authorization và audit. `original_filename` là metadata không tin cậy đã được giới hạn/chuẩn hóa để hiển thị; `declared_media_type` là giá trị client khai báo; `detected_media_type` là kết quả server xác định từ nội dung. Không dùng declared MIME type hoặc extension làm bằng chứng file an toàn.

Unique constraint bảo đảm cùng một storage key không bị gắn cho nhiều record trong phạm vi provider/bucket. Khi dùng nhiều tenant, cần tenant isolation ở query và policy; chỉ có cột `tenant_id` không tự bảo vệ nếu truy vấn quên điều kiện.

## 5. Ngăn path traversal và filesystem abuse

Biện pháp tốt nhất là không đưa original filename vào đường dẫn filesystem. Server tạo storage key từ ký tự và cấu trúc do chính ứng dụng kiểm soát.

Ví dụ không an toàn:

```java
// Không dùng filename do client gửi làm path.
Path target = uploadRoot.resolve(file.getOriginalFilename());
file.transferTo(target);
```

Một filename như `../../application.yml` có thể khiến file được ghi ra ngoài upload directory nếu không có kiểm soát phù hợp. Việc chỉ loại `../` bằng regex cũng dễ bỏ sót separator khác, encoding hoặc cách filesystem chuẩn hóa đường dẫn.

Ví dụ tạo key ngẫu nhiên và ghi file mới:

```java
String storageKey = UUID.randomUUID().toString();
Path root = uploadRoot.toAbsolutePath().normalize();
Path target = root.resolve(storageKey).normalize();

if (!target.startsWith(root)) {
    throw new SecurityException("Invalid storage path");
}

try (InputStream input = multipartFile.getInputStream()) {
    Files.copy(input, target); // Không ghi đè file đã tồn tại.
}
```

Vì `storageKey` chỉ do server tạo và là UUID, nó không chứa separator. Kiểm tra `startsWith(root)` là defense-in-depth để đảm bảo path nằm dưới root; cần so sánh `Path` theo thành phần path, không so sánh chuỗi prefix. `Files.copy` mặc định thất bại nếu target đã tồn tại, tránh overwrite âm thầm.

Production còn cần:

- Tạo upload directory với quyền filesystem tối thiểu; chỉ process cần thiết được ghi.
- Không đặt upload directory bên trong webroot hoặc thư mục thực thi code.
- Bảo vệ root directory khỏi symlink/đổi mount bởi user không tin cậy.
- Dùng `CREATE_NEW` hoặc thao tác tương đương để tránh race khi tạo file.
- Giới hạn số file, dung lượng, thời gian và tổng quota.
- Không dùng storage key từ request để truy cập trực tiếp; tra metadata record do server quản lý.

Nếu phải hỗ trợ import file từ hệ thống cũ có path do người dùng cung cấp, hãy migration sang key mới; đừng duy trì việc dùng filename làm path chỉ vì tương thích.

## 6. Filename vẫn cần được xử lý an toàn

Tách storage key không có nghĩa là có thể lưu và hiển thị filename tùy ý. Original filename vẫn có thể gây lỗi log, giao diện, header hoặc thao tác vận hành.

Khi nhận filename:

- Giới hạn độ dài theo byte/ký tự và từ chối giá trị rỗng nếu nghiệp vụ yêu cầu tên.
- Loại hoặc thay thế ký tự điều khiển, NUL, CR/LF và ký tự không hợp lệ cho nơi hiển thị.
- Xử lý separator `/` và `\\`; nếu chỉ cần basename để hiển thị, loại phần path do client gửi nhưng không dùng basename đó làm storage key.
- Chuẩn hóa Unicode theo một quy tắc nhất quán cho tìm kiếm/so sánh, nhưng giữ metadata gốc nếu nghiệp vụ cần hiển thị chính xác.
- Tránh tên thiết bị/reserved name của hệ điều hành khi có export sang filesystem, ví dụ `CON`, `NUL`, `COM1` trên Windows.
- Xử lý dấu chấm hoặc khoảng trắng cuối tên theo hành vi của filesystem mục tiêu.
- Không cho filename chứa CR/LF để tránh header injection trong `Content-Disposition`.
- Encode theo đúng ngữ cảnh khi đưa vào HTML, JSON, log hoặc HTTP header.

Không cố biến filename thành “an toàn để làm path” bằng một regex tổng quát. Filename là metadata; storage key được tạo độc lập.

## 7. Extension, MIME type và nội dung file

Filename có thể kết thúc bằng `.pdf` nhưng nội dung thực tế là HTML, executable hoặc file khác. Header `Content-Type` do client gửi cũng có thể giả mạo. Vì vậy:

1. Có allowlist loại file theo nghiệp vụ, không cho phép mọi định dạng chỉ vì storage có thể lưu.
2. Kiểm tra extension như một tín hiệu bổ sung, không phải bằng chứng duy nhất.
3. Phát hiện định dạng dựa trên magic bytes/content signature bằng thư viện phù hợp.
4. Parse/scan file trong môi trường cách ly nếu định dạng phức tạp hoặc cần trích xuất nội dung.
5. Giới hạn kích thước giải nén, số entry, độ sâu archive và thời gian xử lý để chống archive/decompression bomb.
6. Lưu trạng thái `QUARANTINED`, `SCANNING`, `AVAILABLE` hoặc `REJECTED`; không cho tải xuống trước khi kiểm tra hoàn tất nếu use case yêu cầu.

Storage key không nhất thiết phải có extension. Có thể lưu nội dung theo key opaque và giữ `detected_media_type` trong metadata. Khi download, server đặt `Content-Type` dựa trên loại đã xác định và policy. Với file không tin cậy, cân nhắc `Content-Disposition: attachment` và `X-Content-Type-Options: nosniff`; không phục vụ HTML/SVG tùy ý inline trên origin có cookie nhạy cảm.

## 8. Upload an toàn với Spring Boot

Ví dụ service dưới đây tạo storage key ngẫu nhiên, lưu file trong vùng riêng và trả về metadata. Đây là minh họa phần key/path; production cần bổ sung streaming byte limit, file signature detection, malware scanning, transaction/outbox và xử lý lỗi storage/database.

```java
@Service
public class FileStorageService {
    private final Path uploadRoot;
    private final StoredFileRepository repository;

    public FileStorageService(
            @Value("${app.upload-root}") Path uploadRoot,
            StoredFileRepository repository) {
        this.uploadRoot = uploadRoot.toAbsolutePath().normalize();
        this.repository = repository;
    }

    public StoredFileMetadata store(
            MultipartFile file,
            UUID tenantId,
            UUID ownerId) throws IOException {

        String originalName = safeDisplayFilename(file.getOriginalFilename());
        String storageKey = UUID.randomUUID().toString();
        Path target = uploadRoot.resolve(storageKey).normalize();

        if (!target.startsWith(uploadRoot)) {
            throw new SecurityException("Storage path escaped upload root");
        }

        Files.createDirectories(uploadRoot);
        try (InputStream input = file.getInputStream()) {
            Files.copy(input, target); // Fails if target already exists.
        }

        try {
            String detectedType = detectMediaType(target);
            long size = Files.size(target);
            StoredFile record = new StoredFile(
                UUID.randomUUID(), tenantId, ownerId,
                storageKey, originalName, detectedType, size,
                "QUARANTINED"
            );
            repository.save(record);
            return StoredFileMetadata.from(record);
        } catch (RuntimeException | IOException ex) {
            Files.deleteIfExists(target);
            throw ex;
        }
    }
}
```

Các hàm `safeDisplayFilename` và `detectMediaType` là phần cần triển khai bằng thư viện/chính sách phù hợp, không nên tự viết parser bằng regex. Ví dụ cũng cần xử lý trường hợp database save thất bại sau khi object đã được tạo, process chết giữa hai bước và nhiều instance cùng xử lý. Với hệ thống production, nên có trạng thái upload tạm, background reconciliation để xóa object mồ côi và transaction/outbox cho các bước tiếp theo.

Không tin `tenantId` hoặc `ownerId` từ multipart form. Hai giá trị này phải được lấy từ principal/tenant context đã xác minh và policy. Nếu file được upload thay mặt một user khác, cần kiểm tra delegation rõ ràng.

## 9. Lưu trữ trên object storage

Với S3-compatible storage hoặc cloud object storage, key cũng phải do server tạo. Ví dụ:

```text
bucket: private-uploads
key: objects/7f/7f3a2b1c-9f4a-4a6a-8d17-7b31a7c3c91d
```

Nguyên tắc:

- Bucket/container private; không bật public-read chỉ để download thuận tiện.
- Dùng IAM/workload identity có quyền tối thiểu theo bucket/prefix và operation.
- Không cho client tự chọn bucket, account, prefix hoặc object key tùy ý.
- Nếu upload trực tiếp từ browser bằng pre-signed URL, server tạo key trước, giới hạn method, object, content length/type khi provider hỗ trợ và thời hạn URL ngắn.
- Không coi pre-signed URL là authorization lâu dài; URL là bearer capability, ai có URL trong thời hạn hiệu lực có thể dùng theo quyền đã ký.
- Sau upload trực tiếp, backend xác minh object tồn tại, size/checksum và trạng thái scan trước khi chuyển sang `AVAILABLE`.
- Bật encryption at rest, versioning/retention và audit theo yêu cầu dữ liệu.
- Không đưa original filename vào object key; dùng metadata riêng hoặc `Content-Disposition` khi tải.

Với multipart upload nhiều phần, upload ID của storage provider và part number là trạng thái kỹ thuật riêng. Chỉ hoàn tất multipart sau khi xác minh quyền, tổng kích thước, checksum và lifecycle. Hủy upload dang dở theo TTL để tránh chiếm storage.

## 10. Download: dùng metadata để tìm key, dùng filename cho hiển thị

Client nên yêu cầu file bằng `fileId`:

```http
GET /api/files/4f8e2f17-2b8a-4e50-9a9b-23e8a4c9c9a1/download
Authorization: Bearer <access-token>
```

Server thực hiện:

1. Xác thực principal.
2. Tra file record theo `fileId` và tenant context.
3. Kiểm tra quyền đọc file, trạng thái `AVAILABLE` và retention/deletion state.
4. Lấy storage key từ record nội bộ.
5. Đọc object từ bucket/filesystem private.
6. Trả nội dung với media type đã xác định và filename hiển thị đã encode an toàn.

Ví dụ response:

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="Bao-cao-thang-11.pdf"; filename*=UTF-8''Bao%20cao%20thang%2011.pdf
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

Framework HTTP thường có API để tạo `Content-Disposition` đúng chuẩn; ưu tiên dùng API đó thay vì nối header thủ công. `filename*` hỗ trợ UTF-8 theo RFC 5987/8187 trong các framework phù hợp. Không đưa raw filename có CR/LF vào header. Nếu tên hiển thị không an toàn hoặc quá dài, tạo tên download an toàn riêng mà vẫn giữ original metadata theo chính sách.

Không tạo filesystem path từ `fileId` hoặc filename client gửi. `fileId` chỉ dùng để tra record sau authorization; storage key lấy từ database đã kiểm soát. Không trả storage key nội bộ trong error message.

## 11. Tenant isolation và authorization cho file

Storage key tách khỏi filename giải quyết vấn đề định vị object, nhưng không tự ngăn truy cập chéo tenant. Mọi thao tác upload, list, download, replace, move và delete phải được ràng buộc với tenant context đã xác minh.

- Gắn `tenant_id` và owner/relationship vào metadata record.
- Query file bằng cả file ID và tenant scope, ví dụ `findByFileIdAndTenantId`.
- Kiểm tra permission chức năng và object-level authorization; user trong cùng tenant có thể có quyền khác nhau.
- Không cho client gửi storage key để đọc object trực tiếp.
- Nếu dùng prefix theo tenant trong bucket, tenant prefix phải do server tạo từ identity/policy; prefix không thay thế authorization.
- Với pre-signed download URL, xác minh quyền trước khi ký, giới hạn đúng object/method và thời gian sống ngắn.
- Audit các thao tác truy cập file nhạy cảm, nhưng không log URL ký có query chứa credential.

Ví dụ repository:

```java
Optional<StoredFile> findByFileIdAndTenantId(
    UUID fileId,
    UUID tenantId
);
```

Tránh repository method tổng quát `findByStorageKey` được gọi trực tiếp từ controller với key client gửi. Nếu service nội bộ cần lookup theo storage key, giới hạn method trong application boundary và kiểm tra quyền trước khi trả dữ liệu.

## 12. Cập nhật, replace và xóa file

Không nên ghi đè object đang tồn tại chỉ vì người dùng upload file mới có cùng filename. Một file mới nên nhận storage key mới; metadata có thể liên kết với cùng business record hoặc đánh dấu phiên bản mới.

Với replace:

- Tạo object mới với key mới và trạng thái quarantine.
- Kiểm tra nội dung, checksum, media type và quyền cập nhật.
- Trong transaction, cập nhật metadata/business reference sang object mới.
- Sau khi commit và hết retention/rollback window, xóa object cũ theo lifecycle.

Với delete:

- Kiểm tra quyền xóa và tenant/object scope.
- Đánh dấu trạng thái `DELETING` hoặc tombstone trước khi xóa object để tránh race với download.
- Xóa object và các bản sao/thumbnail theo policy.
- Ghi audit, xử lý retry nếu storage tạm thời lỗi và đánh dấu `DELETED` khi hoàn tất.
- Xem xét backup, versioning, replication và legal hold; xóa record metadata ngay lập tức có thể làm mất khả năng reconciliation.

Không tái sử dụng storage key đã xóa. Key không tái sử dụng giúp log, audit và tham chiếu cũ không vô tình trỏ sang nội dung mới.

## 13. Đồng bộ database và storage

Filesystem/object storage và database thường không cùng transaction ACID. Có thể xảy ra các trạng thái lệch:

- Object đã upload nhưng database insert thất bại: orphan object.
- Database record đã tạo nhưng upload thất bại: metadata trỏ tới object không tồn tại.
- Delete metadata thành công nhưng object xóa thất bại: object mồ côi và có thể vẫn chiếm storage.
- Replace object thành công nhưng cập nhật reference thất bại: user vẫn thấy phiên bản cũ.

Thiết kế lifecycle tường minh:

1. Tạo upload session/record `PENDING` cùng storage key do server sinh.
2. Upload object vào private/quarantine location.
3. Xác minh size/checksum/content và quét file.
4. Chuyển metadata sang `AVAILABLE` trong transaction; ghi outbox event nếu có downstream processing.
5. Job reconciliation tìm record `PENDING` quá hạn, object mồ côi và record trỏ tới object thiếu.
6. Xóa/khôi phục theo policy, có audit và retry.

Không cho download record `PENDING`, `QUARANTINED` hoặc `DELETING`. Định nghĩa TTL upload session và dọn multipart upload dang dở để tránh tích tụ chi phí.

## 14. Các anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách khắc phục |
|---|---|---|
| Dùng `getOriginalFilename()` làm path/object key | Path traversal, collision và overwrite. | Sinh storage key opaque ở server. |
| Chỉ xóa chuỗi `../` bằng regex | Bỏ sót separator, encoding, Unicode và parser behavior. | Không dùng filename làm path; tạo key độc lập. |
| Dùng filename làm primary key | Trùng tên và rename làm hỏng tham chiếu. | Dùng file ID riêng, unique constraint trên storage key. |
| Dùng UUID làm authorization | Key bị lộ vẫn có thể truy cập nếu endpoint/bucket mở. | Private storage và object-level authorization. |
| Tin extension hoặc Content-Type client gửi | File giả dạng định dạng an toàn. | Detect content, allowlist, scan và quarantine. |
| Trả raw filename trong HTTP header | CR/LF/header injection hoặc encoding lỗi. | Dùng API Content-Disposition và encode đúng chuẩn. |
| Dùng bucket public để download dễ hơn | Ai biết URL/key có thể truy cập file. | Private bucket, backend authorization hoặc signed URL ngắn hạn. |
| Dùng chung prefix cho mọi tenant mà query không filter | Rò file chéo tenant. | Tenant-aware metadata query và authorization. |
| Ghi đè object khi filename trùng | Mất dữ liệu hoặc thay nội dung ngoài ý muốn. | Key mới cho mỗi upload/version; cập nhật mapping. |
| Không có reconciliation | Orphan object và metadata hỏng tích tụ. | Lifecycle state, retry và reconciliation job. |
| Log signed URL hoặc storage key kèm secret | Rò capability/credential. | Redact URL query, log file ID và request ID phù hợp. |

## 15. Kiểm thử storage key và filename

Kiểm thử cần xác nhận filename không ảnh hưởng đến storage location, hai upload không ghi đè nhau và authorization vẫn được thực thi.

| Ca kiểm thử | Input/thao tác | Kết quả mong đợi |
|---|---|---|
| Filename bình thường | Upload `report.pdf`. | Storage key do server tạo; filename chỉ nằm trong metadata. |
| Path traversal | `../../secret.txt`, `..\\..\\secret.txt`. | Không thể thoát storage root; key không chứa input. |
| Absolute path | `C:\\Windows\\win.ini`, `/etc/passwd`. | Không ảnh hưởng vị trí lưu; không được dùng làm path. |
| Separator/encoding | `%2e%2e%2f`, Unicode separator hoặc encoded slash. | Storage key vẫn độc lập; filename được xử lý như metadata. |
| Filename trùng | Hai user upload `report.pdf`. | Hai storage key khác nhau; không overwrite. |
| Cross-tenant same name | Tenant A và B cùng upload `invoice.pdf`. | Hai record/object tách biệt; không đọc chéo tenant. |
| Unicode/control chars | CR/LF, NUL, bidi control, tên rất dài. | Bị giới hạn/chuẩn hóa cho hiển thị; không phá log/header. |
| Reserved filename | `CON`, `NUL`, dấu chấm/khoảng trắng cuối. | Không gây lỗi filesystem; storage key vẫn hợp lệ. |
| MIME spoofing | `.pdf` nhưng nội dung không phải PDF. | Bị phát hiện/reject hoặc quarantine; không tin extension. |
| Key collision | Giả lập generator trả key đã tồn tại. | Create-new/unique constraint từ chối; không overwrite. |
| Direct object access | Gọi bucket/object URL không có signed permission. | Bị từ chối bởi private storage policy. |
| File ID enumeration | User A yêu cầu file ID của tenant B. | Bị từ chối/che giấu theo policy; không lộ storage key. |
| DB/storage partial failure | DB insert hoặc object upload thất bại giữa chừng. | Không có file `AVAILABLE` sai trạng thái; reconciliation xử lý orphan. |
| Download filename | Filename chứa CR/LF, quote hoặc Unicode. | Content-Disposition được encode an toàn; không inject header. |
| Replace/delete race | Download đồng thời với replace/delete. | State transition nhất quán; không trả object sai phiên bản. |

Ngoài status code, kiểm tra filesystem/object key thực tế, nội dung object, database mapping, quyền tenant, số object được tạo/xóa và audit log. Test collision nên mock generator hoặc cố tình tạo key trùng trong môi trường test để xác minh thao tác create-new.

## 16. Giám sát và vận hành

Theo dõi các chỉ số:

- Upload success/failure, byte count, file count và quota theo tenant/user.
- Filename bị từ chối/chuẩn hóa, path traversal attempt và request có ký tự điều khiển.
- Storage key collision, unique constraint violation và object overwrite attempt.
- Object `PENDING`/`QUARANTINED` quá lâu, orphan object và metadata không khớp storage.
- Malware scan failure, file type mismatch, archive expansion và parser timeout.
- Download deny, cross-tenant access attempt, signed URL creation và expiration.
- Delete/replace retry, multipart upload chưa hoàn tất và storage cost bất thường.

Log nên dùng file ID, tenant ID đã xác minh, operation, storage provider, status và request ID. Không log nội dung file, credential, signed URL đầy đủ hoặc đường dẫn nội bộ nhạy cảm. Original filename chỉ log khi thật sự cần và phải encode/redact để tránh log injection.

Khi phát hiện object bị ghi đè hoặc truy cập chéo tenant, xác định file ID, storage key, tenant/owner, thời gian và consumer đã truy cập. Thu hồi signed URL/capability còn hiệu lực nếu có thể, khóa endpoint hoặc policy lỗi, bảo toàn audit evidence và đánh giá dữ liệu đã bị đọc/thay đổi. Không chỉ sửa metadata mà bỏ qua object storage, cache, thumbnail, backup hoặc bản sao downstream.

## 17. Checklist thiết kế storage key

- [ ] Storage key được tạo phía server bằng random/unique ID đủ mạnh?
- [ ] Original filename không được dùng làm filesystem path, bucket key hoặc object identifier?
- [ ] File ID và storage key được tách biệt; API chỉ trả ID cần thiết?
- [ ] Database lưu mapping cùng tenant, owner, media type, size, checksum và lifecycle status?
- [ ] Có unique constraint cho storage provider/bucket/key?
- [ ] Filesystem root/bucket private, quyền tối thiểu và không nằm trong webroot?
- [ ] Upload có byte/file/quota limits, content detection, quarantine và scan phù hợp?
- [ ] Download tra storage key từ metadata sau khi authorization thành công?
- [ ] Content-Disposition dùng filename đã xử lý/encode an toàn?
- [ ] Pre-signed URL giới hạn object, method và TTL; không log URL có credential?
- [ ] Tenant isolation áp dụng cho list/read/replace/delete và background job?
- [ ] Replace/delete dùng lifecycle state, không overwrite key cũ và có reconciliation?
- [ ] Có test path traversal, collision, Unicode, MIME spoofing, cross-tenant và partial failure?
- [ ] Có metric/alert cho orphan, mismatch, denied access và storage abuse?

Filename là thông tin do người dùng cung cấp và chỉ nên được dùng như metadata hiển thị sau khi xử lý phù hợp. Storage key phải do server tạo, duy nhất và tách khỏi tên file; file ID dùng để tra metadata sau khi kiểm tra quyền. Cách tách biệt này ngăn filename điều khiển vị trí lưu trữ, giảm path traversal và collision, đồng thời giúp hệ thống quản lý tenant, version, download, retention và audit một cách nhất quán.
