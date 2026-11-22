# If-Range và tránh nối các phần từ nhiều phiên bản

## 1. Bài toán: tải tiếp một tệp đã thay đổi

Một client đang tải tệp video 800 MB từ REST API. Sau khi nhận 200 MB đầu tiên, kết nối bị ngắt. Để tiết kiệm băng thông, client gửi yêu cầu lấy tiếp từ byte thứ 200 MB bằng **Range**. Nhưng trong lúc ngắt kết nối, chủ sở hữu đã thay tệp bằng bản dựng mới có **cùng URL**.

Nếu client đơn giản nối dữ liệu mới vào 200 MB cũ, kết quả có thể gồm **đầu tệp phiên bản A + cuối tệp phiên bản B**. Tệp có thể hỏng, vượt kiểm tra checksum, hoặc nguy hiểm hơn: vẫn có cấu trúc đọc được nhưng nội dung không tương ứng với bất kỳ phiên bản hợp lệ nào.

**If-Range** giúp client nói: *“Chỉ gửi phần byte tôi yêu cầu nếu representation vẫn là phiên bản mà tôi đang tải. Nếu không, hãy gửi lại toàn bộ representation để tôi bắt đầu lại.”*

Bài thuộc chương **Tệp và dữ liệu lớn** của module **INTEGRATION_API_REST**. Trong thực hành REST API với resource, URI, phương thức, HTTP status, cache, hợp đồng OpenAPI, xác thực, phân quyền và kiểm thử Java/Spring, If-Range là mảnh ghép đặc thù giúp **resume download an toàn theo phiên bản**. Trọng tâm ở đây là điều kiện HTTP đối với **byte-range download**, không phải kiến trúc upload phân mảnh.

Sau bài này, bạn có thể:

- Phân biệt **Range**, **Content-Range**, **If-Range** và validator **ETag/Last-Modified**.
- Giải thích vì sao **If-Range khớp → có thể 206**, **không khớp → trả 200 toàn bộ**, chứ không phải 412.
- Chỉ dùng validator đủ mạnh để tránh ghép phần byte từ nhiều phiên bản.
- Xây downloader kiểm tra response/status/validator trước khi nối dữ liệu.
- Nhận diện rủi ro với content coding, CDN, concurrency, bảo mật, giới hạn range.
- Triển khai ví dụ HTTP, Spring MVC, kiểm thử tích hợp và bài tập tình huống.

## 2. Những khái niệm cần phân biệt

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Range** (request) | **Range: bytes=1000-1999** | Client yêu cầu một hoặc nhiều khoảng của representation. |
| **Content-Range** (response) | **Content-Range: bytes 1000-1999/5000** | Server xác nhận khoảng byte đang trả và tổng độ dài representation. |
| **Accept-Ranges** (response) | **Accept-Ranges: bytes** | Server quảng bá hỗ trợ byte ranges; không tự ràng buộc phiên bản. |
| **ETag** (response) | **ETag: "sha256-abcd..."** | Validator của representation; cần strong validator phù hợp để resume an toàn. |
| **Last-Modified** (response) | **Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT** | Thời điểm sửa theo HTTP-date, đôi khi dùng làm validator nhưng có giới hạn độ chính xác. |
| **If-Range** (request) | **If-Range: "sha256-abcd..."** | Điều kiện riêng của Range: tiếp tục lấy một phần chỉ khi validator còn khớp. |
| **206 Partial Content** | HTTP response có đoạn byte | Range được đáp ứng, body là phần được chọn chứ không phải toàn tệp. |
| **200 OK** | HTTP response toàn representation | Server trả bản đầy đủ; client **không được append** vào phần đã tải. |
| **416 Range Not Satisfiable** | **Content-Range: bytes */5000** | Các khoảng yêu cầu không thể đáp ứng trên representation hiện hành. |

Range áp dụng cho **HTTP representation**, kể cả video/ảnh nếu server hỗ trợ. Offset bắt đầu từ **0**, hai đầu đều bao gồm: **bytes=1000-1999** là 1.000 byte; **bytes=1000-** lấy từ 1000 đến hết; **bytes=-1000** lấy 1.000 byte cuối.

## 3. Cách hoạt động của một lần tải tiếp hợp lệ

### 3.1. Bước đầu: lấy toàn tệp hoặc metadata

Giả sử tài nguyên **/files/f-42/content** có 10 byte, nội dung **0123456789**, validator strong **"file-v1"**:

~~~http
GET /files/f-42/content HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept-Encoding: identity

HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10
Accept-Ranges: bytes
ETag: "file-v1"
Cache-Control: private, no-store

0123456789
~~~

Giả sử client chỉ lưu được **01234** (5 byte). Nó giữ cả **strong ETag "file-v1"**; production phải sinh ETag đúng theo representation thực tế.

### 3.2. Bước tiếp: gửi Range kèm If-Range

~~~http
GET /files/f-42/content HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept-Encoding: identity
Range: bytes=5-
If-Range: "file-v1"
~~~

Nếu tài nguyên **vẫn là representation cũ**, server đáp ứng phần còn lại:

~~~http
HTTP/1.1 206 Partial Content
Content-Type: application/octet-stream
Content-Range: bytes 5-9/10
Content-Length: 5
Accept-Ranges: bytes
ETag: "file-v1"

56789
~~~

Client chỉ **append 56789** sau khi xác minh 206, start=5, total=10 và validator/biểu diễn khớp. Tệp cuối là **0123456789**.

### 3.3. Nếu server đã thay phiên bản

Giả sử representation mới có nội dung **abcdefghij** với strong ETag **"file-v2"**. Client vẫn thử:

~~~http
GET /files/f-42/content HTTP/1.1
Range: bytes=5-
If-Range: "file-v1"
Accept-Encoding: identity
~~~

Vì validator không khớp, server **bỏ qua Range** và gửi toàn bộ representation mới:

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10
ETag: "file-v2"

abcdefghij
~~~

**200 sau Range là toàn bộ representation, không phải phần còn thiếu.** Client phải **thay tệp tạm**, không append thành **01234abcdefghij**. If-Range giúp tránh ghép nhầm phiên bản, nhưng **không bảo đảm server luôn trả 206**.

## 4. Ngữ nghĩa If-Range: so sánh nào, mã nào?

Theo **RFC 9110 – HTTP Semantics**, **If-Range** được dùng cùng **Range** trên GET. Giá trị là **một entity-tag hoặc một HTTP-date**, không phải danh sách entity tag như một số conditional header khác.

### 4.1. If-Range với ETag

~~~http
Range: bytes=1048576-
If-Range: "sha256-strong-v3"
~~~

Origin server đánh giá validator theo **strong comparison**. Nếu validator hiện hành strong và **khớp**, server có thể xử lý Range; nếu **không khớp**, server phải bỏ qua Range và xử lý như một GET không yêu cầu đoạn byte (thường là **200** toàn representation).

**Client không được tạo If-Range bằng weak ETag**, ví dụ:

~~~http
If-Range: W/"file-v3"
~~~

Weak ETag biểu đạt tương đương yếu, **không đủ chứng minh các byte của representation giống nhau**. Server không được đối xử weak tag đó như một strong match để cho phép nối tệp.

### 4.2. If-Range với HTTP-date

~~~http
Range: bytes=1048576-
If-Range: Wed, 18 Nov 2026 10:00:00 GMT
~~~

HTTP cho phép dùng HTTP-date khi client **không có entity-tag** và Last-Modified đủ mạnh để làm validator. Tuy nhiên, độ phân giải thời gian thường là **giây**: nhiều thay đổi trong một giây có thể khiến Last-Modified không đổi dù byte đã khác. Với tệp có thể ghi đè nhanh, **strong ETag đáng tin cậy là lựa chọn ưu tiên**.

Không so ngày “gần đúng”. Khi không thể xác minh validator ngày đủ mạnh và khớp theo HTTP, hãy **trả full representation**, không cho client nối byte.

### 4.3. Không nhầm If-Range với If-Match

| Điều kiện | Mục đích | Nếu không khớp |
| --- | --- | --- |
| **If-Range** cùng **Range** | Tiếp tục **GET một phần** nếu representation chưa đổi. | **Bỏ qua Range**, thông thường **200 toàn bộ**, **không phải 412**. |
| **If-Match** trên PATCH/PUT | Chỉ thực hiện thay đổi khi strong validator khớp. | **412 Precondition Failed** nếu điều kiện được đánh giá là false. |
| **If-None-Match** trên GET | Chỉ gửi representation khi cache client chưa có bản phù hợp. | **304 Not Modified** nếu validator khớp và điều kiện GET đúng. |
| **If-None-Match: \*** trên PUT create-only | Chỉ tạo nếu chưa có representation hiện hành. | **412** khi điều kiện không thỏa. |

**If-Range không phải “một If-Match khác để trả 412”**. Nó đặc biệt hữu ích vì phản hồi 200 tự cung cấp con đường khôi phục: tải lại toàn bộ khi dữ liệu đã thay đổi.

**Phạm vi:** If-Range không có tác dụng nếu thiếu Range; server có thể bỏ qua Range và trả 200. HTTP đánh giá precondition thông thường trước Range; không bỏ qua xác thực/phân quyền. Range dùng cho GET, không dùng HEAD để resume. Accept-Ranges chỉ quảng bá hỗ trợ, không thay kiểm tra status.

## 5. Content-Range và xử lý 206, 200, 416

### 5.1. 206 Partial Content

~~~http
HTTP/1.1 206 Partial Content
Content-Range: bytes 1000-1999/5000
Content-Length: 1000
ETag: "v3"
Content-Type: application/octet-stream
~~~

Đây là phản hồi **một khoảng liên tục**. Client cần kiểm tra:

1. Đơn vị **bytes** và cú pháp **start-end/total**.
2. **start** đúng vị trí dự kiến; **end >= start** và nhỏ hơn total.
3. Số byte thực nhận bằng **end - start + 1**.
4. Representation và validator khớp phiên bản đang ghép.
5. Content coding/media type có tương thích với các phần đã lưu không.

Không nên chỉ kiểm tra “HTTP 206 là thành công” rồi append. Một server hoặc proxy lỗi có thể trả Content-Range không khớp yêu cầu, hoặc dữ liệu bị cắt giữa chừng.

### 5.2. 200 OK sau request Range

**200** nghĩa là phản hồi đầy đủ theo phương thức GET thông thường. Với downloader đang resume, điều này là tín hiệu **không append**:

~~~text
IF response.status == 200:
    truncate_or_replace_temporary_file()
    write_full_response_from_offset_zero()
    remember_new_validator()
~~~

Chỉ publish tệp sau khi kiểm tra dữ liệu đầy đủ. Nếu body 200 cũng bị ngắt, lưu phần mới cùng validator mới để có thể thử resume ở lần sau.

### 5.3. 416 Range Not Satisfiable

Nếu tệp hiện hành có 5.000 byte nhưng client yêu cầu:

~~~http
Range: bytes=6000-
~~~

server có thể trả:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */5000
~~~

**bytes */5000** công bố độ dài hiện hành cho một representation. Nó không có nghĩa client chắc chắn đã tải xong. Nếu client đang có 6.000 byte trong tệp tạm, metadata rõ ràng đã không còn nhất quán; cần kiểm tra lại validator/độ dài và thường **khởi động lại**.

Nếu client đã có chính xác tổng byte và hash hợp lệ, có thể xác nhận hoàn tất theo chính sách. Nhưng **416 không phải response thành công cho việc lấy phần tiếp theo**, và không được append hay mặc định coi nội dung tạm là chính xác.

**Multi-range** (ví dụ **Range: bytes=0-99,200-299**) có thể trả **206 multipart/byteranges**, mỗi phần có Content-Range riêng. Client không hỗ trợ multipart phải tránh yêu cầu dạng này, không nối các phần như một dải liên tục.

## 6. Tình huống nguy hiểm: nhiều request song song

Download manager có thể chia file 100 MB thành bốn khoảng và tải đồng thời. Điều này cải thiện tốc độ nhưng tạo ra race nếu tệp bị thay giữa những request.

~~~text
T0: GET/HEAD lấy strong ETag A, total = 100 MB
T1: Worker 1 GET bytes=0-24MB     -> 206, ETag A
T2: Server publish phiên bản B tại cùng URI
T3: Worker 2 GET bytes=25-49MB   -> Nếu không có If-Range: 206 của B
T4: Ghép A + B                   -> TỆP HỎNG
~~~

Đối với **mọi request phân đoạn**, gắn cùng validator strong A:

~~~http
GET /files/f-42/content HTTP/1.1
Range: bytes=26214400-52428799
If-Range: "strong-A"
~~~

Nếu server đã chuyển sang B, nó trả **200 toàn bộ B** thay vì cung cấp đoạn B dưới giả định A còn đúng. Client phải **hủy bộ phần tải A**, không được ghi response 200 vào vị trí offset 25 MB.

### 6.1. Quy tắc downloader song song

- Chọn **một phiên bản mục tiêu** trước khi tải; lưu strong ETag và tổng độ dài.
- Mỗi segment request mang **If-Range cùng ETag** và Range chính xác.
- Khi nhận 206, kiểm tra **Content-Range** không chồng/thiếu và validator phù hợp. Chỉ ghi phần vào đúng offset trong tệp tạm gắn với phiên bản đó.
- Nếu bất kỳ request nào trả **200** vì phiên bản đổi, **đánh dấu toàn bộ phiên tải A không còn hợp lệ**, hủy các segment còn lại và bắt đầu tải B.
- Nếu có 416, timeout, response sai range, weak/missing validator hoặc encoding khác: dừng ghép, xác minh trạng thái và phục hồi theo chính sách; không cố “chắp vá”.
- Đến cuối, kiểm tra độ dài, coverage không có lỗ hổng và **checksum toàn tệp từ nguồn tin cậy** nếu có; sau đó **đổi tên tệp tạm thành tệp cuối một cách nguyên tử** trên filesystem phù hợp.

**Strong ETag là validator, không phải chữ ký xác thực nội dung.** Nếu cần bảo đảm chống hư hỏng, nên có SHA-256/digest đáng tin từ metadata có kiểm soát hoặc manifest đã xác thực, nhất là khi tải qua nhiều hop/cache.

### 6.2. URI bất biến theo phiên bản

Nếu có thể, dùng **/files/f-42/versions/v17/content** cho bản bất biến. Resume dễ hơn vì URI giữ một snapshot, nhưng vẫn phải kiểm tra Range/integrity, TTL và quyền sau khi người dùng bị thu hồi truy cập.

## 7. Representation và Content-Encoding: byte nào đang được đếm?

**Byte ranges áp dụng cho selected representation**, kể cả content coding như **gzip**. Offset khi đó tính trên **byte đã nén**, không phải byte file gốc.

Ví dụ nguy hiểm:

~~~text
Request 1: Accept-Encoding: gzip     -> lưu 1 MB byte đã nén
Request 2: Accept-Encoding: identity -> lấy phần byte chưa nén
Nối hai phần                           -> dữ liệu không đồng nhất
~~~

Để đơn giản hóa resume, client có thể yêu cầu **identity representation**:

~~~http
Accept-Encoding: identity
~~~

Vẫn phải kiểm tra **Content-Encoding**, ETag, tổng byte sau proxy/CDN. **Không dùng cùng strong ETag cho các representation có byte khác nhau** như gzip và identity. Nếu hỗ trợ nhiều coding, cấu hình **Vary/cache key** và validator theo từng biến thể. Với ZIP/MP4 đã nén sẵn, identity thường thuận tiện cho resume.

## 8. Java/Spring MVC: xử lý If-Range với một range đơn

Mẫu **Spring Boot 3 / Spring Framework 6** dùng byte[] để kiểm tra HTTP thuận tiện trên **tệp nhỏ**. Với file lớn, phải stream từ **snapshot bất biến** có thể seek, không đọc hết vào RAM.

### 8.1. Service trả snapshot nhất quán

~~~java
import java.util.UUID;

// Dữ liệu và strong ETag phải cùng thuộc MỘT phiên bản bất biến.
record BlobSnapshot(byte[] bytes, String strongEtag) {}

interface BlobService {
    BlobSnapshot loadAuthorizedSnapshot(String actor, UUID id);
}
~~~

Service phải **phân quyền trước** và bảo đảm byte[] không bị mutate; record không tự làm mảng bất biến. ETag và nội dung phải thuộc **cùng object/version**.

### 8.2. Controller hỗ trợ bytes=start-end và bytes=start-

~~~java
import java.security.Principal;
import java.util.Arrays;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class FileDownloadController {
    private static final Pattern ONE_RANGE =
            Pattern.compile("bytes=(\\d+)-(\\d*)");
    private final BlobService storage;

    FileDownloadController(BlobService storage) {
        this.storage = storage;
    }

    @GetMapping("/files/{id}/content")
    ResponseEntity<byte[]> download(
            @PathVariable UUID id,
            Principal principal,
            @RequestHeader(value = "Range", required = false)
            String range,
            @RequestHeader(value = "If-Range", required = false)
            String ifRange) {

        // Xác thực/phân quyền trước khi tiết lộ cả độ dài lẫn ETag.
        BlobSnapshot blob =
                storage.loadAuthorizedSnapshot(principal.getName(), id);
        byte[] data = blob.bytes();
        String tag = blob.strongEtag(); // Ví dụ: "\"file-v1\""

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        headers.setETag(tag);
        headers.set("Accept-Ranges", "bytes");
        headers.setCacheControl("private, no-store");

        // Chỉ cho phép partial nếu If-Range vắng mặt hoặc
        // khớp CHÍNH XÁC strong ETag của snapshot hiện tại.
        boolean rangeAllowed = range != null
                && (ifRange == null
                    || (!ifRange.startsWith("W/") && ifRange.equals(tag)));

        if (rangeAllowed) {
            Matcher m = ONE_RANGE.matcher(range);
            if (m.matches()) {
                try {
                    long from = Long.parseLong(m.group(1));
                    long requestedTo = m.group(2).isEmpty()
                            ? data.length - 1L
                            : Long.parseLong(m.group(2));

                    if (requestedTo >= from) {
                        if (from >= data.length) {
                            headers.set("Content-Range",
                                    "bytes */" + data.length);
                            headers.setContentLength(0);
                            return new ResponseEntity<>(
                                    new byte[0], headers,
                                    HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE);
                        }

                        long to = Math.min(
                                requestedTo, data.length - 1L);
                        byte[] part = Arrays.copyOfRange(
                                data, (int) from, (int) to + 1);
                        headers.set("Content-Range",
                                "bytes " + from + "-" + to
                                        + "/" + data.length);
                        headers.setContentLength(part.length);
                        return new ResponseEntity<>(
                                part, headers, HttpStatus.PARTIAL_CONTENT);
                    }
                } catch (NumberFormatException invalidNumber) {
                    // Range quá lớn hoặc sai định dạng: bỏ qua Range.
                }
            }
        }

        // If-Range không khớp, không có Range, hoặc biến thể
        // Range mà ví dụ không hỗ trợ: trả TOÀN BỘ, không nối.
        headers.setContentLength(data.length);
        return new ResponseEntity<>(data, headers, HttpStatus.OK);
    }
}
~~~

**Giới hạn mẫu:** chỉ xử lý **bytes=start-end/start-**; suffix và multi-range trở về **200**. If-Range dạng ngày cũng về 200; production có thể hỗ trợ ngày với validator đủ mạnh. Số không parse được bị bỏ qua, còn request/header cần giới hạn kích thước ở gateway. **Arrays.copyOfRange** tốn RAM, phải thay bằng streaming seekable trên file lớn. Hệ thống thật cần chống nén/chuyển mã qua proxy, 401/403/404 đúng và bảo vệ dữ liệu theo tenant.

### 8.3. Một lỗi thiết kế dễ bị bỏ qua

Nếu service đọc **ETag từ DB rồi mở file path có thể bị overwrite**, validator và byte có thể thuộc hai bản khác nhau. Hãy cố định **immutable version/generation ID** cho cả metadata và stream; chỉ đổi con trỏ phiên bản hiện hành nguyên tử. Một lần HEAD riêng lẻ không bảo đảm file không đổi trong lúc GET.

## 9. Thiết kế downloader có thể resume một cách an toàn

Server đúng giao thức chỉ giải quyết một nửa bài toán. Client cũng phải lưu trạng thái và quyết định **append hay replace** theo response thật.

### 9.1. Metadata của tệp tạm

Lưu **URI, strong ETag, totalBytes, receivedBytes, content coding và vị trí tempFile**. Với tải song song, lưu các đoạn đã hoàn tất và kiểm tra coverage; **không tin receivedBytes nếu kích thước tệp tạm không khớp**.

### 9.2. Quyết định theo status

~~~text
resume(resource, tempFile, state):
    n = actual_size(tempFile)
    require n == state.receivedBytes
    require state.etag is a strong ETag

    response = GET(resource, headers={
        "Range": "bytes=" + n + "-",
        "If-Range": state.etag,
        "Accept-Encoding": "identity"
    })

    if response.status == 206:
        require Content-Range unit == "bytes"
        require Content-Range.start == n
        require Content-Range.total == state.totalBytes
        require response ETag == state.etag
        require content coding matches stored representation
        append_exact_range(response.body)

    else if response.status == 200:
        # KHÔNG APPEND: bản đã đổi hoặc server bỏ qua Range.
        replace_temp_with_full_response(response.body)
        replace_metadata_with_response_validator_and_length()

    else if response.status == 416:
        verify_current_version_length_and_optional_checksum()
        if verification fails: restart_from_byte_zero()

    else:
        handle_auth_limit_timeout_or_http_error(response)

    if full_coverage_and_integrity_valid():
        atomic_publish_temp_file()
~~~

Đây là **giả mã**. Production cần stream xuống đĩa, kiểm tra body bị cắt, đồng bộ metadata và phục hồi sau crash. Nếu không có strong validator, ưu tiên tải lại hoặc dùng URI phiên bản bất biến.

### 9.3. Không phụ thuộc vào Content-Length đơn lẻ

Ở **206**, Content-Length (nếu có) là độ dài **đoạn body**, còn tổng file nằm sau dấu **/** của Content-Range. Ở **200**, Content-Length phản ánh full body. Với chunked/HTTP2 vẫn phải đếm byte thật, kiểm tra EOF và checksum; không suy ra hoàn tất chỉ từ việc đóng kết nối.

## 10. Bảo mật, cache và phòng lạm dụng Range

### 10.1. Phân quyền mỗi request phân đoạn

Mỗi Range GET phải kiểm tra **authentication, tenant/owner và quyền hiện hành**, kể cả khi client đã tải phần đầu. **Không tiết lộ ETag/độ dài/416 trước phân quyền**; UUID khó đoán không đủ bảo mật.

### 10.2. Range amplification và từ chối dịch vụ

Nhiều range chồng lặp, header cực lớn hoặc request song song có thể gây DoS. Giới hạn **header, số range, kích thước response, connection, I/O, bandwidth, timeout và rate**; kiểm tra overflow ở phép tính start/end/length. Có thể **bỏ qua Range** không hỗ trợ thay vì tạo multipart tốn kém.

### 10.3. CDN có thể ghép các phản hồi 206

Cache/CDN chỉ được kết hợp các partial response khi thỏa semantics HTTP và **cùng strong validator/representation**, đồng thời xét Content-Encoding, Vary và quyền. File riêng có thể dùng **Cache-Control: private, no-store**; file công khai với URI bất biến có thể cache hiệu quả nếu validator/Range chuẩn. Cùng URL **không chứng minh cùng byte**.

### 10.4. Download URL và thông tin nhạy cảm

Không log token, cookie hay URL ký sẵn. Signed URL là **credential có TTL và scope**; tránh redirect sang host lạ và sanitize tên file Content-Disposition ở client.

## 11. OpenAPI 3.1: ghi rõ contract của Range và If-Range

~~~yaml
openapi: 3.1.0
info:
  title: Files API
  version: 1.0.0
paths:
  /files/{id}/content:
    get:
      summary: Tải tệp với byte Range và If-Range
      description: >
        If-Range khớp có thể trả 206; nếu không khớp
        hoặc Range bị bỏ qua, trả 200 toàn bộ.
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string, format: uuid}
        - in: header
          name: Range
          required: false
          description: "Ví dụ: bytes=1048576-"
          schema: {type: string}
        - in: header
          name: If-Range
          required: false
          description: Strong ETag đã lưu; ví dụ chỉ nhận strong ETag.
          schema: {type: string}
      responses:
        '200':
          description: Toàn bộ representation; KHÔNG append vào phần cũ
          headers:
            ETag:
              schema: {type: string}
          content:
            application/octet-stream:
              schema: {type: string, format: binary}
        '206':
          description: Một phần byte của cùng representation
          headers:
            Content-Range:
              required: true
              schema: {type: string}
            ETag:
              schema: {type: string}
          content:
            application/octet-stream:
              schema: {type: string, format: binary}
        '416':
          description: Range không thể đáp ứng với representation hiện tại
          headers:
            Content-Range:
              description: "Ví dụ: bytes */5000"
              schema: {type: string}
~~~

Trích đoạn này cần bổ sung **securitySchemes**, lỗi 401/403/404/429, Problem Details và multipart/byteranges nếu hỗ trợ. Khai báo OpenAPI **không tự cài đặt xử lý If-Range** trong Spring/proxy.

## 12. Kiểm thử HTTP và tính nhất quán dữ liệu

### 12.1. Ma trận test trọng tâm

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| R01 | GET không Range | **200**, full body, strong ETag và độ dài đúng. |
| R02 | Range hợp lệ, không If-Range | **206** nếu server chọn đáp ứng Range; Content-Range chính xác. |
| R03 | Range + strong If-Range **khớp** | **206**, đúng start/end/total, nội dung đúng version. |
| R04 | Range + If-Range **cũ** | **200 full**, không Content-Range partial; client phải replace, không append. |
| R05 | If-Range yếu hoặc dạng date không được hỗ trợ | **200 full** theo policy ví dụ; không giả strong match. |
| R07 | Range bắt đầu từ vị trí ngoài tệp | **416** cùng **Content-Range: bytes */total**. |
| R08 | Range đầu/cuối một byte hoặc dạng suffix/multi-range không hỗ trợ | Không off-by-one; phần không hỗ trợ trả 200 full. |
| R10 | Tệp đổi giữa hai phân đoạn | Request sau với If-Range cũ nhận 200, downloader hủy mọi segment cũ. |
| R11 | Content coding khác hoặc CDN đổi version giữa stream | Không ghép gzip/identity; không phát ETag A cùng byte B. |
| R12 | Tenant khác, Range cực lớn, body bị cắt | Không lộ metadata, overflow hay publish file không đủ byte. |

### 12.2. Test Spring MockMvc cho 206

Giả sử **BlobService** đã được mock trả một snapshot có **0123456789** và strong ETag **"file-v1"** cho một UUID được phép truy cập:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.nio.charset.StandardCharsets;

mockMvc.perform(get("/files/{id}/content", fileId)
        .principal(() -> "user-17")
        .header("Range", "bytes=5-")
        .header("If-Range", "\"file-v1\""))
    .andExpect(status().isPartialContent())
    .andExpect(header().string("Content-Range", "bytes 5-9/10"))
    .andExpect(header().string("ETag", "\"file-v1\""))
    .andExpect(content().bytes(
            "56789".getBytes(StandardCharsets.US_ASCII)));
~~~

Test **không khớp validator**:

~~~java
mockMvc.perform(get("/files/{id}/content", fileId)
        .principal(() -> "user-17")
        .header("Range", "bytes=5-")
        .header("If-Range", "\"file-older\""))
    .andExpect(status().isOk())
    .andExpect(header().doesNotExist("Content-Range"))
    .andExpect(content().bytes(
            "0123456789".getBytes(StandardCharsets.US_ASCII)));
~~~

**Lưu ý:** Principal trong MockMvc không thay thế test Spring Security thực với authentication/tenant/scope.

### 12.3. Integration test để bắt race thật

Integration test phải publish A, tải một phần, rồi publish B cùng URI: **If-Range A phải trả 200 full B**. Khi tải 3–4 đoạn song song và thay version giữa các request, downloader **không được tạo tệp A+B**. Test qua gateway/CDN với gzip/identity, mô phỏng mất điện giữa ghi tệp tạm và đối chiếu **byte cuối** với snapshot nguồn. Thử thêm 416, file rỗng, offset cuối/ngoài biên, số cực lớn và quyền bị thu hồi.

## 13. Bài tập: video đổi phiên bản giữa lúc resume

Một ứng dụng tải video **10.000 byte** ở URI **/videos/v-42/content**. Lần GET đầu nhận **ETag: "v1"**, nhưng chỉ ghi được **4.000 byte** đầu. Sau đó server publish **"v2"** tại cùng URI. Client gửi:

~~~http
GET /videos/v-42/content HTTP/1.1
Range: bytes=4000-
If-Range: "v1"
~~~

Server đúng giao thức trả:

~~~http
HTTP/1.1 200 OK
ETag: "v2"
Content-Length: 12000
Content-Type: video/mp4

<toàn bộ 12.000 byte phiên bản v2>
~~~

**Câu hỏi:** Vì sao trả 200, không phải 206/412? Nếu append vào 4.000 byte cũ thì thành bao nhiêu byte? Cùng độ dài có chứng minh cùng nội dung không? If-Range dạng **W/"v1"** có hợp lệ để ghép byte không? Khi tải bốn phần song song và qua CDN, phải kiểm tra gì?

**Đáp án gợi ý:** If-Range không khớp nên server trả full v2; append sai thành **16.000 byte**. Cùng độ dài vẫn có thể khác byte, weak validator không đủ. Tất cả phần song song phải cùng strong ETag/content coding, Content-Range đúng; một response 200 buộc bỏ bộ phần cũ.

## 14. Checklist trước khi phát hành download resume

- [ ] Server hỗ trợ Range đúng scope đã công bố; hiểu **206/200/416** và Content-Range.
- [ ] **If-Range** được đánh giá bằng **strong ETag** hoặc HTTP-date đủ mạnh khi hỗ trợ.
- [ ] If-Range **không khớp** dẫn tới **full 200**, không trả 206 của phiên bản mới dưới validator cũ.
- [ ] Không coi If-Range như If-Match/412; không dùng weak ETag làm strong match.
- [ ] Byte representation và validator cùng một **snapshot bất biến** trong thời gian streaming.
- [ ] Client chỉ append khi response **206**, Content-Range và validator hợp lệ.
- [ ] Khi nhận **200** sau Range, client **replace/restart**, tuyệt đối không append.
- [ ] Khi nhận **416**, kiểm tra metadata/độ dài và checksum trước khi quyết định hoàn tất hay tải lại.
- [ ] Các phần tải song song phải cùng một representation, không chồng/lỗ hổng và có checksum nếu cần.
- [ ] Content-Encoding, ETag, Content-Length và Content-Range thống nhất qua origin, proxy, CDN.
- [ ] Xác thực/phân quyền trên **mọi** Range GET, không lộ độ dài/ETag của tài nguyên ngoài quyền.
- [ ] Chống range amplification, số cực lớn, nhiều connection, storage I/O, timeout và hỏng tệp tạm.
- [ ] OpenAPI mô tả Range/If-Range và các status/header thực tế; Spring xử lý đúng hoặc cấu hình hỗ trợ có kiểm chứng.
- [ ] Integration test mô phỏng publish v2 giữa các lần GET và tải song song; file cuối phải bằng **một phiên bản duy nhất**.

**Kết luận:** **Range** cho phép yêu cầu một đoạn dữ liệu; **If-Range** bảo đảm client chỉ dùng đoạn đó khi representation vẫn phù hợp validator đã lưu. Nếu validator đã đổi, **200 toàn bộ là tín hiệu bắt đầu lại**, không phải một phần để nối. Thiết kế đúng cần phối hợp strong validator, snapshot byte ổn định, Content-Range, content coding, phân quyền và kiểm thử race — nhờ đó file cuối không bị ghép từ nhiều phiên bản khác nhau.
