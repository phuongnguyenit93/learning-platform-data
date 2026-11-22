# Giới hạn kích thước, loại tệp và kiểm tra nội dung

## 1. Tại sao upload tệp cần hợp đồng chặt chẽ?

Một REST API cho phép nhân viên tải ảnh sản phẩm và tài liệu PDF lên hệ thống. Người dùng gửi tệp **12 MiB** tới endpoint chỉ chấp nhận tối đa **10 MiB**; một người khác đổi tên tệp thực thi thành **avatar.png**; một client khác gửi ZIP nhỏ nhưng giải nén thành hàng chục gigabyte. Nếu API chỉ kiểm tra đuôi tên tệp hoặc tin Content-Type do client khai báo, hệ thống có thể lưu nội dung nguy hiểm, lãng phí bộ nhớ, đầy ổ đĩa hoặc vô tình công khai tệp nhạy cảm.

Vấn đề gồm **ba quyết định độc lập**:

1. **Kích thước:** Có được tiếp nhận số byte này không, ở tầng nào và theo giới hạn nào?
2. **Loại tệp:** Hợp đồng cho phép định dạng nào, và có đủ bằng chứng để tin đây là định dạng đó không?
3. **Nội dung:** Tệp có thể được phân tích, lưu và phục vụ an toàn theo nghiệp vụ không?

Trong module **INTEGRATION_API_REST**, bài học gắn các quyết định trên với resource/URI, phương thức và mã trạng thái HTTP, hợp đồng OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử Java/Spring. Mục tiêu là thiết kế **đường nhận dữ liệu có giới hạn và có kiểm chứng**, không chỉ viết một controller nhận MultipartFile.

### Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt giới hạn **từng tệp**, **tổng multipart request**, **body HTTP**, **kích thước sau giải nén** và **quota lưu trữ**.
- Chọn đúng **413 Content Too Large**, **415 Unsupported Media Type**, **400 Bad Request**, **422 Unprocessable Content** và mã lỗi liên quan theo nguyên nhân.
- Hiểu vì sao **filename, phần mở rộng và Content-Type từ client đều không đáng tin**.
- Thiết kế các bước kiểm tra signature, cấu trúc định dạng, số chiều/entry, quét mã độc và xuất bản tệp.
- Cấu hình và triển khai ví dụ Spring MVC, bảo vệ streaming/temp storage và kiểm thử các biên giới hạn.
- Thiết kế API phản hồi lỗi có cấu trúc và quy trình upload lớn an toàn.

## 2. Đặt giới hạn ở đúng lớp

Một request có thể đi qua **CDN/WAF → gateway/reverse proxy → servlet container → multipart parser → ứng dụng → kho lưu trữ**. Không lớp nào tự thay thế toàn bộ các lớp còn lại.

| Giới hạn | Đếm cái gì? | Ví dụ và mục đích |
|---|---|---|
| **HTTP request body** | Byte truyền trong nội dung request theo cách lớp HTTP/server kiểm soát | Chặn body tổng quá lớn trước khi chiếm đường truyền và bộ nhớ |
| **Tổng multipart request** | Tất cả phần file/form và overhead multipart | Tổng request không vượt **12 MiB**, dù mỗi file nhỏ |
| **Một file part** | Số byte của file được gửi | Ảnh riêng lẻ không vượt **10 MiB** |
| **Định dạng/số lượng phần** | Số file, số form field, tên part, nested multipart | Chặn hàng nghìn file rỗng hoặc trường quá lớn |
| **Sau giải nén/giải mã** | Dữ liệu sau xử lý (pixel, entry ZIP, XML, PDF...) | Chặn decompression bomb và parser exhaustion |
| **Quota tài khoản/tenant** | Tổng dung lượng hoặc số object lưu | Chống một bên dùng hết tài nguyên được cấp |
| **Thời gian/tốc độ** | Upload duration, tốc độ đọc, số request song song | Chống giữ connection vô hạn hoặc chiếm temp disk |

**Ví dụ:** một tệp 9 MiB có thể vượt chính sách ảnh 8 MiB nhưng vẫn nằm dưới tổng multipart 12 MiB. Một file ZIP 1 MiB có thể vượt giới hạn dữ liệu sau giải nén 100 MiB. Hai điều kiện phải được kiểm tra độc lập.

### 2.1. MiB khác MB và multipart có overhead

**1 MiB = 1.048.576 byte**; **10 MiB = 10.485.760 byte**. Trong cấu hình Spring Boot, đơn vị **MB** của kiểu DataSize được diễn giải theo bội 1024; tuy nhiên khi tài liệu gửi cho client, nên công bố **giới hạn theo byte** để không phụ thuộc cách hiểu MB ở SDK/gateway khác.

Nếu cho mỗi file tối đa **10 MiB** nhưng đặt tổng request cũng đúng **10 MiB**, một file đúng ngưỡng có thể bị từ chối do **boundary, tên trường, MIME headers và metadata multipart**. Hãy đặt giới hạn tổng có khoảng dự phòng có chủ đích, nhưng không mở quá rộng.

### 2.2. Content-Length là tín hiệu sớm, không phải chứng cứ duy nhất

Một request có thể không có độ dài được biết trước hoặc được truyền dạng streaming. **Content-Length** nếu xuất hiện giúp chặn sớm, nhưng ứng dụng/proxy vẫn phải **đếm byte thực nhận**, kể cả dữ liệu đọc qua InputStream. Với nội dung nén, cần tính riêng kích thước sau giải nén.

**Không nên** đọc toàn bộ body vào byte[] rồi mới kiểm tra, vì memory exhaustion có thể xảy ra trước lúc logic giới hạn được thực thi.

## 3. HTTP semantics: phản hồi gì khi tệp không được chấp nhận?

Giả sử **POST /documents** nhận multipart/form-data và phần **file** chỉ cho phép PNG hoặc PDF, tối đa 10 MiB.

| Tình huống | Mã thường phù hợp | Vì sao |
|---|---|---|
| Request content vượt mức server chấp nhận | **413 Content Too Large** | Giới hạn byte của nội dung request; tên cũ là Payload Too Large |
| Request Content-Type không thuộc các media type endpoint hỗ trợ | **415 Unsupported Media Type** | Ví dụ gửi application/xml tới endpoint chỉ nhận multipart/form-data |
| File part khai loại media type không được API hỗ trợ | **415** theo hợp đồng upload đã công bố | Loại nội dung được gửi không được phép |
| Multipart thiếu boundary, hỏng cú pháp hoặc thiếu part bắt buộc | **400 Bad Request** | Request không thể diễn giải đúng |
| Media type được chấp nhận nhưng nội dung không đúng cấu trúc/quy tắc file | **422 Unprocessable Content** hoặc **400** theo hợp đồng | Cú pháp giao thức hợp lệ nhưng file không đạt kiểm tra |
| Quét nội dung không an toàn / từ chối theo chính sách nội dung | **422**, **403** hoặc mã domain được định nghĩa rõ | Không mặc định đây là lỗi kích thước |
| Quá nhiều lần upload trong một khoảng thời gian | **429 Too Many Requests** | Rate limiting; có thể kèm Retry-After |
| Header quá lớn (không phải body) | **431 Request Header Fields Too Large** khi stack hỗ trợ | Không nhầm với 413 |
| Tenant hết quota tổng dung lượng | Mã **403/409/422** theo quy tắc sản phẩm | Quota nghiệp vụ không đồng nghĩa file body quá lớn |
| Server không đủ lưu trữ để thực hiện yêu cầu | **507 Insufficient Storage** trong ngữ cảnh phù hợp hoặc 5xx khác theo lỗi | Sự cố khả năng lưu trữ, khác giới hạn upload chủ động |

**Phân biệt chủ đích:** 415 mô tả **loại media của request content** không được hỗ trợ. Khi endpoint nhận multipart nhưng chỉ một file part chứa loại bị cấm, sử dụng 415 là quy ước hợp lý nếu hợp đồng nói rõ. Với **Content-Type khai là image/png nhưng byte thực tế không tạo thành PNG hợp lệ**, 422/400 cho lỗi kiểm chứng nội dung thường rõ nghĩa hơn; không có một mã duy nhất bắt buộc cho mọi bộ lọc malware.

Ví dụ tệp quá lớn:

~~~http
POST /documents HTTP/1.1
Host: api.example.test
Content-Type: multipart/form-data; boundary=boundary123
Content-Length: 15728640

... nội dung multipart ...
~~~

~~~http
HTTP/1.1 413 Content Too Large
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/file-too-large",
  "title": "Content Too Large",
  "status": 413,
  "detail": "Tệp vượt giới hạn 10 MiB.",
  "code": "FILE_TOO_LARGE",
  "maxFileBytes": 10485760
}
~~~

Đây là **Problem Details** theo RFC 9457. **code** và **maxFileBytes** là extension members do API định nghĩa. Gateway có thể từ chối trước Spring Controller, thậm chí đóng connection khi chưa đọc hết body; do đó **không được bảo đảm mọi 413 đều có JSON body**. Client phải xử lý được cả status lẫn network interruption.

**Retry-After** trên 413 chỉ hữu ích nếu giới hạn có tính tạm thời. Với giới hạn cố định 10 MiB, chờ rồi gửi lại 15 MiB không giải quyết được gì.

## 4. Loại tệp: không tin những thông tin do client đặt

Một file upload có thể chứa:

~~~http
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png
~~~

Ba tín hiệu cần đánh giá:

| Dữ liệu | Ai kiểm soát? | Có đủ để tin tệp là PNG? |
|---|---|---|
| **filename / extension .png** | Client | **Không**: dễ đổi đuôi |
| **Content-Type: image/png** của part | Client | **Không**: có thể khai sai |
| **Magic bytes / signature** | Nội dung tệp | Giúp loại bỏ nhiều file giả, **chưa đủ** chứng minh toàn bộ file an toàn |
| **Parser/decoder theo định dạng** | Server | Phát hiện cấu trúc hỏng, nhưng phải giới hạn tài nguyên và dùng thư viện cập nhật |
| **Malware scan, kiểm tra chính sách** | Hệ thống kiểm soát nội dung | Giảm nguy cơ, không bảo đảm phát hiện 100% |

Chẳng hạn signature PNG bắt đầu bằng 8 byte **89 50 4E 47 0D 0A 1A 0A**. Một file có 8 byte đầu đó nhưng phần còn lại rác hoặc chứa payload ghép thêm **không tự động là ảnh PNG hợp lệ**.

### 4.1. Allowlist tốt hơn denylist

Đối với endpoint ảnh đại diện, có thể cho phép **image/png** và **image/jpeg** với các hạn mức riêng, thay vì chặn một danh sách đuôi như .exe, .bat, .sh. Danh sách định dạng cấm không bao giờ bao quát hết nội dung có khả năng thực thi, file đa định dạng (*polyglot*) hay biến thể encoding.

Với từng loại cho phép, xác định **media type, signature, validator, giới hạn riêng và cách phục vụ khi download**. Nếu chỉ cần PNG, không nên mở thêm PDF, SVG hoặc HTML để “tiện cho client”.

### 4.2. Trường hợp PDF, SVG, ZIP và ảnh

- **PDF:** chữ ký %PDF- chỉ là bước đầu; tài liệu có thể chứa cấu trúc hỏng, action, attachment hoặc nội dung nguy hiểm. Cần parser phù hợp, chính sách xử lý và scanner.
- **SVG:** là XML có khả năng chứa nội dung chủ động/liên kết; không coi nó tương đương ảnh raster an toàn khi phục vụ inline.
- **ZIP:** giới hạn số entry, tổng kích thước giải nén, tỉ lệ nén, độ sâu lồng nhau và đường dẫn entry; chặn **zip slip** (đường dẫn thoát thư mục).
- **Ảnh raster:** giới hạn chiều rộng/cao và tổng pixel **trước khi cấp phát ảnh giải mã**; file nén nhỏ có thể giải mã thành bitmap rất lớn.

**Không chạy hoặc render nội dung upload trong tiến trình API có quyền cao**. Dùng các thư viện cập nhật, sandbox/isolation khi thực thi parser hoặc quét file phức tạp, timeout và giới hạn CPU/memory.

## 5. Pipeline upload an toàn theo từng bước

~~~mermaid
flowchart TD
    C[Client POST multipart] --> G[Gateway: body/rate/timeout limit]
    G --> A[Auth và quota theo principal/tenant]
    A --> P[Parser: số part và từng file]
    P --> S[Staging cách ly, tên server sinh]
    S --> V[Kiểm tra signature và cấu trúc an toàn]
    V --> M[Scan và kiểm tra chính sách nội dung]
    M --> D{Đạt yêu cầu?}
    D -->|Có| PUB[Publish object + metadata trong phạm vi quyền]
    D -->|Không| DEL[Quarantine / xóa staging, trả lỗi phù hợp]
    PUB --> OK[201 Created hoặc hợp đồng kết quả khác]
~~~

**Thứ tự quan trọng:** không nên tạo một URL tải công khai trỏ tới file ngay khi vừa nhận byte đầu tiên. Hãy giữ tệp trong **kho staging không thể truy cập công khai** cho tới khi hoàn thành những bước kiểm tra bắt buộc. Với scan bất đồng bộ, trạng thái ban đầu là **PENDING_SCAN** và chỉ chuyển **READY** sau khi kiểm chứng; đừng trả “đã an toàn” trước khi scanner hoàn tất.

### 5.1. Điều kiện trước khi công bố

Hệ thống phải **xác thực/ủy quyền**, kiểm quota và kích thước, ghi tệp vào **staging private với tên server sinh**, kiểm chứng loại/cấu trúc/scan theo chính sách, rồi mới công bố resource READY. Khi bất kỳ bước nào thất bại phải cleanup file tạm, không làm quota bị chiếm mãi và không lộ thông tin nội bộ. **Signature không thay thế decoder hoặc malware scan**.

### 5.2. Phục vụ file tải xuống cũng là phần của kiểm chứng

Sau khi lưu, download endpoint nên:

- Kiểm tra quyền theo owner/tenant/resource, không mặc định bucket hoặc URL công khai.
- Gửi **Content-Type do server xác định**, không phản chiếu nguyên giá trị client khai.
- Dùng **Content-Disposition: attachment** cho loại tài liệu không nên render inline; nếu cần filename, encode/sanitize đúng chuẩn.
- Cân nhắc **X-Content-Type-Options: nosniff** trong những bối cảnh browser phù hợp.
- Không để SVG, HTML hoặc tệp script từ user hoạt động dưới origin có cookie/credential của ứng dụng mà không có thiết kế sandbox/origin cách ly.
- Gắn thời hạn cho URL tải trực tiếp được ký, quyền tối thiểu và cơ chế thu hồi theo yêu cầu.

**Đổi tên tệp không làm nội dung an toàn.** Điều quan trọng là định dạng thật, mức quyền, cách phục vụ và nguồn gốc của byte được sử dụng.

## 6. Cấu hình Java/Spring Boot và ranh giới của nó

Với **Spring Boot 3, Spring MVC/Servlet stack**, cấu hình multipart:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB
      file-size-threshold: 0B
~~~

- **max-file-size:** giới hạn một multipart file theo cơ chế multipart resolver.
- **max-request-size:** tổng kích thước multipart request (gồm cả trường form/overhead).
- **file-size-threshold:** ngưỡng trước khi lưu tạm xuống đĩa trong cơ chế Servlet multipart; không có nghĩa đĩa tạm vô hạn hoặc request hoàn toàn không cần RAM.

Cần giới hạn cả **temp storage path/capacity, số part, timeout, connection concurrency và upload rate** ở những tầng hỗ trợ. File tạm do container/multipart resolver tạo ra có vòng đời riêng; không nhầm nó với staging lâu hơn của ứng dụng.

**Chú ý:** các thuộc tính trên không đặt giới hạn chung cho mọi **raw application/octet-stream, JSON, XML** hoặc yêu cầu gửi trực tiếp vào object storage. Với các đường truyền đó cần chính sách tại gateway/container và logic đọc có giới hạn riêng.

### 6.1. Giới hạn ở gateway phải khớp hợp đồng

Nếu OpenAPI cho phép **10 MiB/file** và **12 MiB/request** nhưng reverse proxy chặn mọi request body ở **8 MiB**, người dùng sẽ không thể dùng đúng hợp đồng. Hãy đo qua **tuyến Internet → proxy → API**, kiểm tra cách mỗi tầng tính byte, và thiết kế độ lớn multipart đủ chỗ cho metadata.

Nếu ứng dụng cung cấp nhiều loại file với giới hạn khác nhau, cấu hình Spring có thể đặt **ngưỡng tổng thể** và application kiểm tra **ngưỡng theo loại**. Ví dụ chung cho ảnh tối đa 10 MiB nhưng CSV chỉ 2 MiB; không nên tăng giới hạn cho mọi endpoint để đáp ứng một luồng đặc biệt.

## 7. Ví dụ Spring MVC: chỉ nhận PNG dưới 10 MiB

Để tập trung vào nguyên tắc, ví dụ chỉ hỗ trợ **một part file có media type image/png**. Việc kiểm tra **8-byte PNG signature** được triển khai ở controller; xác minh **cấu trúc ảnh, giới hạn pixel, quét nội dung và publish** thuộc service staging được mô tả rõ bên dưới.

~~~java
import java.io.BufferedInputStream;
import java.io.IOException;
import java.net.URI;
import java.security.Principal;
import java.util.Arrays;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

record UploadedDocument(String id, String state) {}
record StoredDocument(String id) {}

@RestController
@RequestMapping("/documents")
class PngUploadController {
    private static final long MAX_BYTES = 10L * 1024 * 1024;
    private static final byte[] PNG_SIGNATURE = {
        (byte) 0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };

    private final DocumentStagingService staging;

    PngUploadController(DocumentStagingService staging) {
        this.staging = staging;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<UploadedDocument> upload(
            @RequestPart("file") MultipartFile file,
            Principal caller) throws IOException {

        // Security filter phải xác thực caller và kiểm soát
        // quyền upload. Service cũng kiểm tra quyền/tenant.
        if (caller == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "File is empty");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                HttpStatus.valueOf(413), "File too large");
        }
        if (!MediaType.IMAGE_PNG_VALUE.equalsIgnoreCase(
                file.getContentType())) {
            throw new ResponseStatusException(
                HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                "Only image/png is supported");
        }

        try (BufferedInputStream stream =
                 new BufferedInputStream(file.getInputStream())) {
            stream.mark(PNG_SIGNATURE.length);
            byte[] prefix = stream.readNBytes(PNG_SIGNATURE.length);
            stream.reset();

            if (!Arrays.equals(prefix, PNG_SIGNATURE)) {
                throw new ResponseStatusException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    "Invalid PNG content");
            }

            // Service bắt buộc:
            // 1) đọc/đếm byte với ngưỡng thực;
            // 2) ghi staging private, tên random;
            // 3) validate PNG dimensions/structure + scan;
            // 4) publish chỉ khi đạt, cleanup nếu lỗi;
            // 5) kiểm tra quyền/tenant từ caller đáng tin cậy.
            StoredDocument stored =
                staging.verifyAndPublishPng(stream, MAX_BYTES, caller);

            return ResponseEntity
                .created(URI.create("/documents/" + stored.id()))
                .cacheControl(CacheControl.noStore())
                .body(new UploadedDocument(stored.id(), "READY"));
        }
    }
}

// DocumentStagingService là abstraction CHƯA triển khai.
// Không dùng snippet như một pipeline an toàn hoàn chỉnh.
~~~

**Ý nghĩa của status:** API ví dụ chỉ trả **201 Created** sau khi file được xác thực, kiểm tra nội dung và công bố trạng thái READY. Nếu scanner chạy sau khi POST trả response, API có thể thiết kế **202 Accepted và monitor resource** hoặc một resource nhận upload đang chờ duyệt với contract rõ; **không dùng 201 READY khi chưa kiểm tra xong**.

### 7.1. Đếm byte khi ghi staging, không chỉ tin getSize()

Một helper đơn giản cho luồng sao chép có giới hạn:

~~~java
static long copyAtMost(
        java.io.InputStream in,
        java.io.OutputStream out,
        long maxBytes) throws IOException {

    long count = 0;
    byte[] buffer = new byte[8192];
    int read;

    while ((read = in.read(buffer)) != -1) {
        if (read > maxBytes - count) {
            throw new ResponseStatusException(
                HttpStatus.valueOf(413), "File too large");
        }
        out.write(buffer, 0, read);
        count += read;
    }
    return count;
}
~~~

Trong service thật, dùng phương thức trên khi ghi vào **file staging có quyền hạn hẹp**, xử lý **finally/try-with-resources để xóa staging khi bất kỳ bước nào thất bại**; chỉ publish sau khi decoder/scanner xác minh và quyền/metadata đã được ghi nhận. Đừng coi việc file có đúng signature hoặc copy không vượt 10 MiB là đã an toàn.

**Không dùng file.getBytes()** cho tệp lớn nếu không muốn nạp toàn bộ nội dung vào RAM; cũng không dùng **file.getOriginalFilename()** trực tiếp làm đường dẫn. Nếu cần lưu tên hiển thị, phải giới hạn độ dài, loại bỏ ký tự điều khiển và chuẩn hóa theo chính sách; object key nên do server sinh.

## 8. Chuẩn hóa lỗi upload thành Problem Details

Spring MVC có thể ném **MaxUploadSizeExceededException** khi multipart resolver nhận dữ liệu vượt giới hạn. Với Spring Framework 6+, có thể dùng **ProblemDetail**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
class UploadErrorHandler {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> tooLarge(
            MaxUploadSizeExceededException ignored) {

        ProblemDetail problem = ProblemDetail.forStatus(413);
        problem.setTitle("Content Too Large");
        problem.setDetail("Vượt giới hạn multipart request.");
        problem.setProperty("code", "UPLOAD_TOO_LARGE");

        return ResponseEntity.status(413)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .body(problem);
    }
}
~~~

Handler này **chỉ có tác dụng khi lỗi được chuyển đến tầng xử lý của Spring MVC**. Request bị gateway, reverse proxy hoặc servlet connector chặn trước đó không đi qua controller/advice. Với **ResponseStatusException** trong ví dụ, nếu muốn mọi lỗi 400/413/415/422 có **đúng schema Problem Details của sản phẩm**, cần cấu hình Spring ErrorResponse/ProblemDetail tương ứng hoặc thêm mapping có chủ đích, kiểm thử thực tế thay vì suy rằng mọi stack tự trả cùng JSON.

Thông điệp lỗi nên giúp client **giảm kích thước hoặc chọn định dạng hợp lệ**, nhưng không tiết lộ đường dẫn staging, tên bucket, thiết bị scanner hoặc stack trace. Có thể phát **X-Correlation-ID** để đội vận hành tra cứu. Không log toàn bộ file, token hoặc nội dung nhạy cảm để chẩn đoán lỗi upload.

## 9. Khi tệp rất lớn: upload session có kiểm chứng

Đối với video hoặc file lớn, không nhất thiết tăng body limit của mọi REST endpoint. Một luồng hợp lý: **POST /upload-sessions** kiểm tra quyền/quota và phát session có hạn; client upload theo part hoặc URL ký phạm vi hẹp vào **staging private**; **POST /upload-sessions/{id}/complete** xác minh byte thực, checksum, cấu trúc, scan và quyền trước khi publish document READY.

**Signed URL chỉ cấp quyền truyền byte**, không chứng minh tệp sạch hay thuộc đúng tenant. Không tin hoàn toàn kích thước và Content-Type do client khai, hoặc coi mọi object-storage ETag là SHA-256. Finalize nhiều lần phải được xử lý nguyên tử; staging lỗi/hết hạn cần cleanup. Nếu scan chưa xong, tài nguyên giữ **PENDING_SCAN**, không trả READY.

## 10. Bảo mật nội dung, quyền và cách phục vụ

| Rủi ro | Kiểm soát cần có |
|---|---|
| **Path traversal / overwrite** qua filename | Sinh storage key từ server; không dùng tên client làm đường dẫn |
| **MIME giả, polyglot, active content** | Allowlist, signature + parser, xử lý loại file chủ động trên origin cách ly |
| **Zip/image bomb, parser vulnerability** | Giới hạn expanded bytes, số entry/pixel, CPU/memory/time; cập nhật thư viện |
| **Quarantine bypass** | Object private cho tới khi kiểm chứng; scan không chạy thì giữ cách ly |
| **Cross-tenant leak** | Xác thực/phân quyền ở upload, finalize và download; quota theo tenant |
| **Upload flood** | Rate/concurrency limit, timeout, hạn mức file tạm và cleanup |

Khi tải xuống, dùng **Content-Type do server xác nhận**, **Content-Disposition: attachment** khi không muốn trình duyệt render inline, và cân nhắc **X-Content-Type-Options: nosniff**. Không lưu token, nội dung file hoặc đường dẫn nội bộ trong error/log. **Scan không đảm bảo phát hiện 100%**: chỉ publish khi tất cả bước bắt buộc đạt, và với lỗi scanner thì fail closed theo chính sách.

## 11. OpenAPI: công bố giới hạn và lỗi trước khi client upload

Đối với client, giới hạn phải nằm trong **hợp đồng rõ ràng**, không chỉ nằm trong cấu hình server. OpenAPI 3.0.3 minh họa endpoint **chỉ nhận PNG**:

~~~yaml
openapi: 3.0.3
info:
  title: Documents API
  version: 1.0.0
paths:
  /documents:
    post:
      summary: Tải lên một file PNG
      description: >
        Chỉ nhận phần file loại image/png; tối đa 10 MiB
        (10485760 byte) mỗi file, tổng multipart 12 MiB.
        Chỉ trả 201 khi file được duyệt và công bố READY.
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required: [file]
              properties:
                file:
                  type: string
                  format: binary
            encoding:
              file:
                contentType: image/png
      responses:
        "201":
          description: Tệp đã được duyệt và tạo resource
          headers:
            Location:
              description: URI của document mới
              schema: {type: string, format: uri-reference}
          content:
            application/json:
              schema:
                type: object
                required: [id, state]
                properties:
                  id: {type: string}
                  state: {type: string, enum: [READY]}
        "400":
          description: Multipart sai hoặc thiếu file
        "401":
          description: Chưa xác thực
        "403":
          description: Không có quyền upload
        "413":
          description: File hoặc tổng multipart quá lớn
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/ApiProblem"
        "415":
          description: Media type không được hỗ trợ
        "422":
          description: Nội dung file không hợp lệ
        "429":
          description: Vượt giới hạn tốc độ/đồng thời
components:
  schemas:
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
        maxFileBytes: {type: integer, format: int64}
~~~

Trong production, cần thêm **security schemes**, schema Problem Details cho 415/422, các điều kiện quota và chính sách upload nhiều file. OpenAPI **không tự thi hành** giới hạn multipart tại gateway/Spring; phải kiểm chứng cấu hình trên tuyến thực.

## 12. Kiểm thử HTTP, nội dung và tài nguyên sau lỗi

| Trường hợp | Kết quả phải xác nhận |
|---|---|
| PNG hợp lệ, đúng ngưỡng 10 MiB | Success theo contract, byte lưu đúng, chỉ READY sau validation |
| File **10 MiB + 1 byte** hoặc multipart quá 12 MiB | **413**, staging không bị bỏ quên |
| Sai request/part Content-Type | **415** đúng hợp đồng |
| image/png nhưng dữ liệu giả, PNG signature đúng nhưng cấu trúc hỏng | **422/400** theo contract; không publish |
| Thiếu boundary/part, file rỗng | **400** theo API |
| ZIP bomb/ảnh có số pixel khổng lồ | Bị chặn mà không OOM/đầy disk |
| Scanner lỗi, tên file traversal hoặc upload song song | Quarantine/cleanup, không ghi đè, không lộ nội dung |
| Caller khác tenant upload/download | **401/403/404** theo chính sách, không có data leak |

Ví dụ MockMvc kiểm tra **MIME khai là PNG nhưng byte không phải PNG** (giả định test đã cấu hình MockMvc, Spring Security Test và fixture):

~~~java
@Test
void rejectsFakePng() throws Exception {
    MockMultipartFile fake = new MockMultipartFile(
        "file", "avatar.png", "image/png",
        "not a PNG".getBytes(StandardCharsets.UTF_8));

    mockMvc.perform(multipart("/documents")
            .file(fake).with(user("alice")).with(csrf()))
        .andExpect(status().is(422));
}
~~~

Các class/helper test cần import theo dự án; **MockMvc có thể không đi qua giới hạn multipart của gateway/container**. Bổ sung integration test qua HTTP thật cho **10 MiB − 1 / đúng ngưỡng / +1 byte**, tổng multipart và request streaming không có độ dài biết trước. Dùng parser/scanner thực trong test định dạng (không mock kết quả “sạch” cho file giả). Sau mọi lỗi, assert **không có public object**, file tạm được dọn, quota đúng; thử GET bằng user khác để kiểm tra quyền. Kết quả 413 bị proxy chặn có thể không có JSON body.

## 13. Bài thực hành: tài liệu đính kèm đơn hàng

Thiết kế **POST /orders/{orderId}/attachments** nhận một PNG tối đa **8 MiB** hoặc PDF tối đa **20 MiB**; tổng multipart tối đa **22 MiB**. Chỉ người có quyền trên đơn hàng mới upload/download; file phải qua scan trước khi có thể tải.

**Yêu cầu:** (1) đề xuất limit ở gateway/Spring và limit riêng mỗi format; (2) phân loại HTTP status cho file quá lớn, media type bị cấm, PDF giả, thiếu quyền; (3) nêu pipeline staging → validate → scan → READY; (4) viết bốn phép thử biên và bảo mật.

**Gợi ý:** tổng request 22 MiB có chỗ cho multipart overhead; Spring file-limit chung đủ 20 MiB, application giới hạn PNG 8 MiB. Quá byte → **413**; loại không hỗ trợ → **415**; PDF khai đúng loại nhưng file hỏng → **422/400** theo contract; không có quyền → **403/404** theo chính sách. File chưa scan **không READY**; kiểm tra byte thực và quyền trước publish. Test kích thước +1 byte, PDF giả, scanner unavailable và truy cập khác tenant.

## 14. Checklist và tài liệu tham khảo

- [ ] Giới hạn **file, tổng multipart, decoded content, số part, quota** có giá trị byte rõ và được áp dụng xuyên gateway/Spring.
- [ ] **Content-Type/filename từ client không được tin**; dùng allowlist, signature, parser, scanner theo rủi ro.
- [ ] Có **bounded streaming**, giới hạn CPU/memory/temp disk, cleanup khi lỗi và staging private trước READY.
- [ ] Object key do server sinh, kiểm tra quyền ở **upload/finalize/download**, không rò dữ liệu giữa tenant.
- [ ] Response **413/415/400/422/401/403/429** và Problem Details được kiểm thử tại tầng xử lý thực.
- [ ] Upload session/signed URL có scope, expiry, kiểm tra nội dung sau upload và finalize chống đua.
- [ ] OpenAPI phù hợp runtime; có test biên byte, MIME giả, định dạng hỏng, scan lỗi và cross-tenant.

Tài liệu: [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110); [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html); [Spring Boot Multipart](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.multipart).

**Ghi nhớ:** Giới hạn byte bảo vệ tài nguyên; kiểm tra loại và nội dung bảo vệ pipeline xử lý; authorization và staging cách ly bảo vệ dữ liệu. Một upload **chỉ sẵn sàng để sử dụng sau khi đạt tất cả điều kiện bắt buộc**.

