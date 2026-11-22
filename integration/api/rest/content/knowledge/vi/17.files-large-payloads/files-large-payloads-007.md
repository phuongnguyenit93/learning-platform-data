# Range, Accept-Ranges, Content-Range và phản hồi 206

## 1. Bài toán: tải tiếp tệp lớn mà không lấy lại từ đầu

Client đang tải báo cáo 800 MiB, nhận được 300 MiB thì mất mạng. GET thông thường có thể phải tải lại từ đầu; HTTP **Range** cho phép yêu cầu phần còn lại của **selected representation** từ byte 314.572.800.

Đây là nội dung của chương **Tệp và dữ liệu lớn** trong học phần `INTEGRATION_API_REST`. Kiến thức liên hệ trực tiếp tới thiết kế URI/resource, HTTP methods/status, cache, conditional requests, xác thực/phân quyền, OpenAPI và kiểm thử bằng Java/Spring.

**Mục tiêu:** thiết kế `Range`, `Accept-Ranges`, `Content-Range`; tính vùng byte và `Content-Length`; phân biệt `200`/`206`/`416`; **resume an toàn qua `If-Range` và strong ETag**; xử lý multi-range, nén, streaming, cache và bảo mật.

> **Nguyên tắc:** Range chia nhỏ **các byte của một biểu diễn HTTP**, không phải phân trang JSON, chia bản ghi SQL hoặc “trả một phần object” theo ý nghĩa nghiệp vụ. Một API trả 20 đơn hàng trong một trang thông thường vẫn dùng `200 OK`, không tự động dùng `206 Partial Content`.

## 2. Ba header và một mã trạng thái cốt lõi

| Thành phần | Hướng | Ý nghĩa |
| --- | --- | --- |
| `Range: bytes=500-999` | Request | Client đề nghị lấy byte từ offset 500 đến 999 của biểu diễn |
| `Accept-Ranges: bytes` | Response | Server thông báo hỗ trợ range unit `bytes` cho tài nguyên |
| `Content-Range: bytes 500-999/1000` | Response | Body chứa đoạn 500–999, toàn bộ biểu diễn dài 1.000 byte |
| `206 Partial Content` | Response status | Server đã đáp ứng một range request, trả **một hoặc nhiều** phần của representation |

`Range` được định nghĩa trong HTTP Semantics (RFC 9110), thường dùng trên **GET**. Server phải **bỏ qua** Range đối với request method không phải GET. Client có thể gửi `Range` ngay cả khi trước đó không thấy `Accept-Ranges`; sự vắng mặt của header này **không chứng minh** server không hỗ trợ range. Server có thể công bố `Accept-Ranges: none` để cho biết không hỗ trợ, nhưng client vẫn phải xử lý response thực tế.

### HTTP exchange tối thiểu

```http
GET /files/f-42 HTTP/1.1
Host: api.example.test
Range: bytes=0-99

HTTP/1.1 206 Partial Content
Content-Type: application/octet-stream
Accept-Ranges: bytes
Content-Range: bytes 0-99/1000
Content-Length: 100
ETag: "sha256-asset-v7"

[100 byte nhị phân đầu tiên]
```

Các dòng trong ngoặc vuông minh họa body, **không phải 100 byte literal**. Trong một ứng dụng thật, body là các byte được truyền trên mạng.

**Offset đếm từ 0, và điểm cuối được tính bao gồm.** Đoạn `0-99` dài `99 - 0 + 1 = 100` byte. `Content-Range` của 206 mô tả **đoạn mà server thực sự trả**, không chỉ lặp lại chuỗi `Range` client yêu cầu.

## 3. Cú pháp byte range và công thức tính

Range unit thông dụng là `bytes`; ba dạng cần nhớ:

```http
Range: bytes=0-99
Range: bytes=500-
Range: bytes=-200
```

- **`bytes=a-b`:** từ byte `a` đến `b`, cả hai đầu đều tính. Nếu `b` vượt quá cuối tệp, server có thể giới hạn ở byte cuối.
- **`bytes=a-`:** từ vị trí `a` đến hết representation.
- **`bytes=-n`:** **n byte cuối cùng** (suffix range), *không phải* offset âm. Nếu `n` lớn hơn kích thước file, nó có thể bao phủ toàn bộ tệp.

Giả sử selected representation dài đúng **1.000 byte**. Các ví dụ:

| Request Range | Đoạn có thể trả | Số byte | Kết quả |
| --- | --- | ---: | --- |
| `bytes=0-0` | 0–0 | 1 | 206 |
| `bytes=0-99` | 0–99 | 100 | 206 |
| `bytes=500-999` | 500–999 | 500 | 206 |
| `bytes=500-` | 500–999 | 500 | 206 |
| `bytes=-200` | 800–999 | 200 | 206 |
| `bytes=-2000` | 0–999 | 1.000 | 206, dù trả đủ toàn bộ |
| `bytes=900-2000` | 900–999 | 100 | 206, điểm cuối được giới hạn |
| `bytes=1000-` | Không có byte nào | 0 | 416 nếu server từ chối vì không thỏa |
| `bytes=-0` | Không thỏa mãn trên tệp này | 0 | 416 nếu xử lý yêu cầu |

Với đoạn có đầu `start` và cuối `end`:

```text
0 <= start <= end < representationSize
returnedBytes = end - start + 1
```

Nếu tệp có kích thước **0 byte**, không có byte-range nào thỏa mãn. GET không có Range vẫn có thể trả `200 OK` với `Content-Length: 0`; GET yêu cầu vùng byte mà server xử lý thường nhận `416`.

**Đừng dùng kích thước ký tự** cho văn bản UTF-8: một ký tự tiếng Việt có thể được mã hóa thành nhiều byte. `bytes=0-99` không có nghĩa 100 ký tự, 100 dòng CSV hay 100 đối tượng JSON. Cắt tùy ý một đoạn JSON hoặc UTF-8 có thể tạo ra đoạn không parse được; client phải ghép đầy đủ mới xử lý được định dạng cần toàn vẹn.

## 4. Phân biệt 200, 206 và 416

### 4.1. Server chấp nhận một range: 206

```http
GET /files/f-42 HTTP/1.1
Range: bytes=800-1200

HTTP/1.1 206 Partial Content
Content-Type: application/octet-stream
Content-Range: bytes 800-999/1000
Content-Length: 200
Accept-Ranges: bytes
ETag: "asset-r7"
```

Server đã giới hạn điểm cuối là 999 vì tệp chỉ dài 1.000 byte. Với **một đoạn**, body chính là bytes 800–999. `Content-Length` là **độ dài phần body trả về (200)**, không phải kích thước tệp gốc (1.000). `Content-Range` xác nhận cả hai.

### 4.2. Server bỏ qua Range: 200

```http
GET /files/f-42 HTTP/1.1
Range: bytes=800-

HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 1000
ETag: "asset-r7"

[toàn bộ 1000 byte]
```

Server **được phép bỏ qua Range** (ví dụ không hỗ trợ, quyết định trả toàn bộ, không xử lý một yêu cầu có quá nhiều đoạn). Khi đó response đúng là **200 với toàn bộ biểu diễn**, không phải 206. **Client tải tiếp tuyệt đối không được append body 200 vào file đang có**, vì như vậy sẽ tạo file trùng dữ liệu. Nó phải bắt đầu lại hoặc xử lý thành một bản đầy đủ riêng.

### 4.3. Không có đoạn byte thỏa mãn: 416

```http
GET /files/f-42 HTTP/1.1
Range: bytes=1000-

HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */1000
Accept-Ranges: bytes
Content-Length: 0
```

Với `416`, server **nên gửi** `Content-Range: bytes */<kích thước>` khi biết kích thước. Dấu `*` ở đây nói không có đoạn được trả; con số là độ dài toàn bộ representation. Nó **không** phải `Content-Range: bytes 1000-.../1000`.

`416` thường được dùng khi không có vùng byte được yêu cầu nào có thể thỏa mãn, hoặc khi request chứa các vùng vô lý mà server lựa chọn từ chối theo ngữ nghĩa HTTP. **Không trả 416 chỉ vì server không triển khai multi-range**: với yêu cầu được phép bỏ qua, trả 200 toàn bộ là một lựa chọn phù hợp. Request sai cú pháp có thể bị bỏ qua hoặc xử lý lỗi theo hợp đồng; không mặc định mọi lỗi cú pháp là 416.

### Ma trận tóm tắt

| Phản hồi | Client hiểu gì? | Cách xử lý body |
| --- | --- | --- |
| `200 OK` | Nhận toàn bộ representation; Range có thể đã bị bỏ qua | **Thay thế** dữ liệu cũ, không append |
| `206 Partial Content` | Nhận đúng một/một số vùng byte được xác định | Kiểm tra `Content-Range` và ghép đúng vị trí |
| `416 Range Not Satisfiable` | Range không phục vụ được | Xem `Content-Range: bytes */size`; kiểm tra lại file/version |
| `304 Not Modified` | Conditional GET xác nhận cache, **không có body** | Dùng representation đã lưu tương ứng, không append |
| `412 Precondition Failed` | Một HTTP precondition như `If-Match` thất bại | Không ghép dữ liệu; xử lý điều kiện |

## 5. Nhiều vùng byte: `multipart/byteranges`

Một request có thể muốn hai vùng rời nhau:

```http
GET /files/f-42 HTTP/1.1
Range: bytes=0-2,7-9
```

Khi server đáp ứng **nhiều vùng**, response `206` dùng `multipart/byteranges`. Ví dụ tệp 10 byte chứa ASCII `0123456789`:

```http
HTTP/1.1 206 Partial Content
Content-Type: multipart/byteranges; boundary=part_example
Accept-Ranges: bytes
ETag: "asset-r7"

--part_example
Content-Type: application/octet-stream
Content-Range: bytes 0-2/10

012
--part_example
Content-Type: application/octet-stream
Content-Range: bytes 7-9/10

789
--part_example--
```

Đây là biểu diễn multipart để học cú pháp, không trình bày CRLF byte chính xác của framing. **Không đặt `Content-Range` ở cấp response ngoài cùng** khi body là multipart; mỗi part có `Content-Range` riêng. Nếu có `Content-Length` ở cấp ngoài, nó phải tính **toàn bộ multipart body, gồm boundary và headers**, không đơn giản là 3 + 3 = 6 byte.

Server được phép **gộp các vùng chồng lấp hoặc liền kề** và có thể bỏ qua một range request chứa nhiều đoạn nhỏ hoặc sắp xếp bất thường, để giảm nguy cơ lạm dụng tài nguyên. Một range set có cả phần thỏa và không thỏa không nhất thiết phải bị trả 416; server có thể trả những vùng thỏa mãn theo quy tắc HTTP.

Trong hệ thống tải tệp lớn thông thường, **một range mỗi request** là đủ. Nếu không hỗ trợ multipart, hãy công bố phạm vi hỗ trợ và thực hiện fallback 200 thay vì trả một response 206 không đúng định dạng.

## 6. Tải tiếp an toàn: giữ cùng một phiên bản tệp

Range chỉ xác định **vị trí byte**. Nếu nội dung tệp thay đổi giữa hai lần tải, ghép “300 MiB cũ + phần sau từ phiên bản mới” có thể tạo file hỏng mà không phát hiện ngay. Để tải tiếp đáng tin cậy, cần gắn range với **validator của cùng representation**.

Giả sử lần đầu client GET và nhận:

```http
HTTP/1.1 200 OK
Accept-Ranges: bytes
Content-Length: 1000
ETag: "asset-r7"
Content-Type: application/octet-stream
```

Client lưu 600 byte đầu **và strong ETag `"asset-r7"`**. Sau khi mất mạng:

```http
GET /files/f-42 HTTP/1.1
Range: bytes=600-
If-Range: "asset-r7"
Accept-Encoding: identity
```

Nếu selected representation còn trùng **strong ETag**:

```http
HTTP/1.1 206 Partial Content
Content-Range: bytes 600-999/1000
Content-Length: 400
ETag: "asset-r7"
Content-Type: application/octet-stream

[400 byte còn lại]
```

Client xác minh start=600, total=1000, cùng representation/validator, rồi ghi 400 byte vào offset 600. Kết quả cuối là 1.000 byte.

Nếu tệp đã đổi sang `"asset-r8"`, điều kiện `If-Range` không thỏa; server **bỏ qua Range** và gửi **200 với toàn bộ phiên bản mới**:

```http
HTTP/1.1 200 OK
Content-Length: 1050
ETag: "asset-r8"

[toàn bộ 1050 byte của phiên bản mới]
```

Client phải **bỏ hoặc thay thế bản tải dở**, không ghép thêm 450 byte vào dữ liệu r7.

### Thuật toán client gợi ý

1. Bắt đầu GET bình thường; lưu `ETag` mạnh, kích thước (nếu có) và bytes thật đã ghi bền.
2. Khi tiếp tục, tính offset từ **số byte thực đã lưu**, không phải phần trăm trong UI.
3. Gửi `Range: bytes=<offset>-` và `If-Range` với validator mạnh của bản đã lưu.
4. Nếu nhận **206**, parse `Content-Range`; xác minh range bắt đầu đúng offset và kích thước/validator nhất quán, rồi ghi vào vị trí tương ứng.
5. Nếu nhận **200**, server đã trả toàn bộ: **thay thế hoặc bắt đầu từ đầu**.
6. Nếu nhận **416**, so sánh kích thước hiện có với `bytes */size` và validator/hash; không tự kết luận “đã hoàn thành” chỉ vì offset bằng kích thước.
7. Khi ghép xong, kiểm tra tổng byte và checksum/hash được tin cậy nếu hợp đồng có; chỉ công bố tải hoàn tất sau kiểm chứng.

Nếu không có strong ETag, có thể dùng `If-Range` với một **HTTP-date** khi có `Last-Modified` đủ điều kiện làm strong validator theo quy tắc HTTP. Tuy nhiên timestamp thường không đủ độ phân giải cho dữ liệu đổi nhanh; trong sản phẩm mới, ưu tiên **artifact bất biến theo version** và strong ETag. **Không dùng weak ETag** (`W/"..."`) với `If-Range`.

## 7. `If-Range` khác `If-Match` và `If-None-Match`

Ba điều kiện dễ bị nhầm:

| Header | Ý nghĩa chính | Khi bản hiện tại không khớp |
| --- | --- | --- |
| `If-Range: "r7"` + `Range` | “Nếu vẫn là r7 thì trả đoạn; nếu đổi thì trả **toàn bộ**” | Thường **200 full**, không phải 412 |
| `If-Match: "r7"` | “Chỉ thực hiện request nếu ETag mạnh khớp r7” | **412 Precondition Failed** |
| `If-None-Match: "r7"` với GET | “Chỉ trả representation nếu không khớp r7” | **304 Not Modified**, không có body |

HTTP đánh giá **các precondition thông thường trước khi xét Range**. Ví dụ, GET với `If-None-Match` đã khớp selected representation sẽ có thể trả 304; server không cần tạo 206. `If-Range` không phải precondition chung kiểu `If-Match`; nó dùng để **quyết định trả một phần hay toàn bộ** khi có Range hợp lệ.

`If-Range` chỉ hữu ích với range request; không gửi nó như một cách “khóa phiên bản” cho một GET không có Range. Nếu client có một bản tải dở nhưng không thể chứng minh nó ứng với cùng representation, cách an toàn là bắt đầu tải mới.

## 8. Byte range và content coding: bẫy thường gặp

Theo HTTP, vùng byte được tính trên **representation data** được chọn. Nếu response dùng **content coding** như gzip, vùng byte liên quan tới **dạng đã mã hóa** của representation, không nhất thiết là byte của tệp gốc sau giải nén.

Ví dụ:

```http
GET /files/f-42 HTTP/1.1
Accept-Encoding: gzip
Range: bytes=1000-1999

HTTP/1.1 206 Partial Content
Content-Encoding: gzip
Content-Range: bytes 1000-1999/64000
Vary: Accept-Encoding
```

Trong trường hợp này, 64.000 byte là kích thước **biểu diễn đã gzip** được chọn. Client không thể tự lấy “1.000 byte thứ hai” của tệp giải nén rồi ghép vào dữ liệu gzip một cách tùy tiện.

**Chính sách đơn giản cho tải tiếp binary:** server lưu/tải một artifact bất biến, cố định media type và thường cung cấp đường tải **identity/no dynamic compression**. Client gửi `Accept-Encoding: identity` khi cần offset ổn định. Phải kiểm tra proxy/CDN có tự nén, giải nén hoặc biến đổi body không; có thể áp dụng `Cache-Control: no-transform` khi cần giữ representation qua các hop, song vẫn phải kiểm chứng cấu hình thực tế.

Nếu hỗ trợ nhiều biến thể identity/gzip/br:

- Công bố `Vary: Accept-Encoding` khi request header ảnh hưởng đến representation.
- Dùng validator mạnh **phù hợp từng dạng byte**; không xem cùng strong ETag là hợp lệ cho hai chuỗi bytes khác nhau.
- Client lưu đúng loại representation mà nó sẽ resume; tự động giải nén trong HTTP library có thể thay đổi byte offset thấy ở ứng dụng.
- Kiểm tra `Content-Encoding`, `Content-Length`, `Content-Range` sau khi qua CDN, không chỉ tại origin.

**Kết luận:** resume “từ byte N” chỉ an toàn khi N được đo trong **cùng dạng representation** mà server dùng để tính Range.

## 9. Streaming file lớn: bộ nhớ và tính bất biến

Một endpoint tải 4 GiB không nên gọi `Files.readAllBytes(...)` rồi trả toàn bộ trong một mảng byte. Thực hiện streaming, đọc theo khối và giới hạn thời gian/kết nối.

Các nguyên tắc quan trọng:

1. **Storage bất biến hoặc snapshot được giữ ổn định** trong suốt mỗi lần phát response. Nếu file thay đổi trong lúc gửi, `Content-Length`/`Content-Range` và bytes thực có thể không còn khớp.
2. **Dùng số 64-bit** cho offset/kích thước; file lớn hơn 2 GiB sẽ vượt phạm vi int.
3. **Không nạp toàn bộ file vào RAM**; dùng stream hoặc random-access file/channel theo offset.
4. **Tôn trọng backpressure/hủy kết nối**: khi client ngắt, dừng đọc/giải phóng handle; theo dõi timeout và bandwidth.
5. **Không xóa artifact đang có download hợp lệ** nếu storage/backend không hỗ trợ semantics cần thiết. Với object store versioned, cố định version ID khi phát các đoạn.
6. **Giới hạn song song/range quá nhỏ**: kẻ tấn công có thể mở hàng nghìn request chỉ lấy vài byte; chi phí connection, CPU, origin egress vẫn cao.

Một response tải file thường có thêm:

```http
Content-Disposition: attachment; filename="report.csv"
Content-Type: text/csv
Accept-Ranges: bytes
ETag: "sha256-report-v3"
Cache-Control: private, no-store
```

Tên file trong `Content-Disposition` phải được tạo/escape an toàn, không lấy nguyên chuỗi do user cung cấp để chèn CRLF hoặc đường dẫn. `Cache-Control` tùy loại dữ liệu: báo cáo riêng tư nên tránh shared cache, trong khi ảnh/binary công khai bất biến có thể cho phép CDN cache với TTL phù hợp.

## 10. Java/Spring: stream một byte range

Spring MVC hỗ trợ `Resource`/`ResourceRegion` và converter cho partial content; khi phù hợp, nên dùng framework hoặc range support của object storage/CDN. Ví dụ sau minh họa **một byte range** và phân biệt 200/206/416; chưa triển khai multi-range, mọi conditional headers hoặc `If-Range` dạng HTTP-date.

### 10.1. Parser với offset 64-bit

```java
// Java 17+, imports cho Optional, Pattern, Matcher.
record ByteWindow(long start, long end, long size) {
    long length() { return end - start + 1; }
    String contentRange() {
        return "bytes " + start + "-" + end + "/" + size;
    }
}
class UnsatisfiableRange extends RuntimeException {}

final class SingleRange {
    private static final Pattern P =
        Pattern.compile("^bytes=(\\d*)-(\\d*)$");

    static Optional<ByteWindow> parse(String header, long size) {
        if (header == null || header.contains(",")) return Optional.empty();
        var m = P.matcher(header.trim());
        if (!m.matches()) return Optional.empty();
        String a = m.group(1), b = m.group(2);
        if (a.isEmpty() && b.isEmpty()) return Optional.empty();

        try {
            if (size == 0) throw new UnsatisfiableRange();
            if (a.isEmpty()) {
                long suffix = Long.parseLong(b);
                if (suffix == 0) throw new UnsatisfiableRange();
                return Optional.of(new ByteWindow(
                    Math.max(0, size - suffix), size - 1, size));
            }
            long start = Long.parseLong(a);
            long end = b.isEmpty() ? size - 1 : Long.parseLong(b);
            if (end < start) return Optional.empty();
            if (start >= size) throw new UnsatisfiableRange();
            return Optional.of(new ByteWindow(
                start, Math.min(end, size - 1), size));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }
}
```

Ví dụ giả định kích thước không âm; header không được hỗ trợ hoặc sai cú pháp được **bỏ qua → 200**, còn vùng hợp lệ nhưng không thể thỏa mãn tạo **416**. Production nên dùng parser đầy đủ của framework khi hỗ trợ multipart và các dạng Range khác.

### 10.2. Controller giữ đúng length, range và validator

```java
// Spring MVC 6, Java 17+. DownloadStore/DownloadFile là abstraction.
@RestController
class FileController {
    private final DownloadStore store;
    FileController(DownloadStore store) { this.store = store; }

    @GetMapping("/files/{id}")
    ResponseEntity<StreamingResponseBody> get(
            @PathVariable String id,
            @RequestHeader(value="Range", required=false) String range,
            @RequestHeader(value="If-Range", required=false) String ifRange,
            Authentication caller) {

        DownloadFile f = store.requireAuthorizedImmutable(id, caller);
        long size = f.size();
        String etag = f.strongEtag(); // có dấu ngoặc kép
        HttpHeaders h = new HttpHeaders();
        h.setETag(etag);
        h.set(HttpHeaders.ACCEPT_RANGES, "bytes");
        h.setContentType(MediaType.APPLICATION_OCTET_STREAM);
        h.setCacheControl("private, no-store, no-transform");

        ByteWindow w = null;
        // Chỉ so strong ETag; If-Range cũ/không hỗ trợ -> 200 full.
        if (range != null && (ifRange == null || ifRange.equals(etag))) {
            try {
                w = SingleRange.parse(range, size).orElse(null);
            } catch (UnsatisfiableRange ex) {
                h.set(HttpHeaders.CONTENT_RANGE, "bytes */" + size);
                h.setContentLength(0);
                return new ResponseEntity<>(
                    out -> {}, h, HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE);
            }
        }
        long start = w == null ? 0 : w.start();
        long length = w == null ? size : w.length();
        if (w != null) h.set(HttpHeaders.CONTENT_RANGE, w.contentRange());
        h.setContentLength(length);

        StreamingResponseBody body = out -> {
            try (RandomAccessFile raf =
                     new RandomAccessFile(f.path().toFile(), "r")) {
                raf.seek(start);
                byte[] buffer = new byte[64 * 1024];
                long remaining = length;
                while (remaining > 0) {
                    int take = (int)Math.min(buffer.length, remaining);
                    int n = raf.read(buffer, 0, take);
                    if (n < 0) throw new EOFException("File đã đổi");
                    out.write(buffer, 0, n);
                    remaining -= n;
                }
            }
        };
        return new ResponseEntity<>(body, h,
            w == null ? HttpStatus.OK : HttpStatus.PARTIAL_CONTENT);
    }
}
```

`DownloadStore` phải kiểm tra quyền và trả **tệp bất biến/versioned**; không nối ID vào filesystem path từ request. Cấu hình executor/timeout cho `StreamingResponseBody`, tránh đọc cả file vào RAM, hỗ trợ HEAD đúng metadata và đóng stream khi client ngắt. ETag phải phù hợp **selected representation bytes**. API đầy đủ phải đánh giá các HTTP preconditions trước Range; mẫu chỉ nhận `If-Range` bằng strong ETag và fallback 200 khi khác. Nếu proxy nén body, cần kiểm tra lại content coding, `Vary`, validators và byte offsets.

## 11. Bảo mật endpoint tải theo byte

Range request **không làm giảm yêu cầu phân quyền**: mỗi request, kể cả chỉ tải một byte, phải kiểm tra tenant/owner/scope và điều kiện thời hạn tải. Client không được dùng ID file hoặc strong ETag như một credential.

| Nguy cơ | Kiểm soát |
| --- | --- |
| **IDOR**: đoán ID tệp người khác | Tra resource bằng ID rồi kiểm tra owner/tenant/permission; 403/404 theo chính sách |
| **Path traversal/symlink** | Server tra storage key từ metadata đã xác thực; không nối path theo input; giới hạn thư mục và xử lý symlink |
| **Range abuse** | Giới hạn số vùng, tổng byte mỗi request, request/concurrency và rate limit; có thể bỏ qua Range hoặc từ chối theo policy |
| **Tiết lộ dữ liệu qua shared cache** | `Cache-Control: private/no-store` cho file riêng; kiểm tra proxy/CDN cache key và auth |
| **Tải qua signed URL** | TTL ngắn, scope tối thiểu, không log chữ ký; cân nhắc khả năng resume khi URL hết hạn |
| **Filename/header injection** | Sinh `Content-Disposition` bằng API escaping an toàn; không đưa CRLF vào header |
| **File đang bị thay đổi hoặc xóa** | Immutable/versioned artifact, lease/retention; không dựa vào path mutable |
| **CORS cho web client** | Allowlist origin, credentials phù hợp; expose `Content-Range`/`ETag` khi JavaScript cần đọc |

Ví dụ response cho web client ở origin đã được cho phép:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Accept-Ranges, Content-Range, ETag, Content-Disposition
Vary: Origin
```

Chỉ phản chiếu `Origin` khi nó thuộc allowlist. CORS do browser thực thi, **không phải authorization**. Nếu tài nguyên có thông tin nhạy cảm, server vẫn phải xác thực và kiểm tra quyền cho mỗi byte-range request; không biến tệp riêng thành cache công khai.

## 12. Cache, CDN và validator khi tải từng đoạn

HTTP caches có thể lưu/ghép partial responses theo quy tắc riêng của caching (RFC 9111), nhưng **không được ghép những đoạn thuộc các representation khác nhau**. Một strong validator phù hợp là điều kiện quan trọng để tổng hợp byte ranges an toàn.

Những điều cần kiểm tra trên đường đi:

1. Edge có chuyển tiếp `Range`, `If-Range` và trả đúng `206` không, hay nó luôn trả 200?
2. `Content-Range`/`Content-Length` phản ánh **bytes thực trên wire** sau mọi biến đổi không?
3. CDN có gzip/br động, làm mất ổn định byte offset hoặc strong ETag không?
4. Cache có chia theo `Authorization`, Cookie, tenant và các header `Vary` cần thiết, hoặc bỏ cache file riêng không?
5. Các phần được ghép có cùng strong ETag và cùng selected representation không?
6. Khi object được thay phiên bản hoặc purge, có thể trả nhầm byte ranges của phiên bản cũ không?

Ngay cả 206 một byte cũng tốn tài nguyên. Theo dõi request rate, bandwidth, range lengths, 200 fallback, 416 và download completion; **không** dùng ID file/user hoặc ETag làm metric label.

## 13. OpenAPI: công bố đúng 200, 206 và 416

Ví dụ OpenAPI 3.0.3 mô tả một endpoint hỗ trợ **một byte range**:
 
```yaml
openapi: 3.0.3
info: {title: File API, version: 1.0.0}
paths:
  /files/{id}:
    get:
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string}
        - in: header
          name: Range
          schema: {type: string}
          description: 'Ví dụ bytes=500-999'
        - in: header
          name: If-Range
          schema: {type: string}
          description: Strong ETag để resume cùng một representation
      responses:
        '200':
          description: Toàn bộ file; Range có thể bị bỏ qua
          headers:
            Accept-Ranges: {schema: {type: string}}
            ETag: {schema: {type: string}}
          content:
            application/octet-stream:
              schema: {type: string, format: binary}
        '206':
          description: Một vùng byte đã được đáp ứng
          headers:
            Content-Range: {schema: {type: string}}
            ETag: {schema: {type: string}}
          content:
            application/octet-stream:
              schema: {type: string, format: binary}
        '416':
          description: Range không thỏa mãn
          headers:
            Content-Range:
              schema: {type: string}
              description: 'Ví dụ bytes */1000'
        '404': {description: Không tìm thấy/không được phép biết file}
```

Trong sản phẩm thật bổ sung `401`/`403`, `304`/`412`, security schemes, HEAD, media type thực, `Content-Disposition` và chính sách cache. **Không khai báo multipart/byteranges** nếu server chỉ trả một range. Nếu hỗ trợ multi-range, mô tả `multipart/byteranges` như một loại body riêng và `Content-Range` ở từng part, không phải ngoài cùng.

## 14. Kiểm thử byte range và resume

Tạo fixture 1.000 byte với nội dung xác định, strong ETag `"r7"`. **Kiểm cả body thực**, không chỉ HTTP status:

| Request/tình huống | Kỳ vọng |
| --- | --- |
| GET không Range | 200, toàn bộ 1.000 byte, không Content-Range |
| `bytes=0-0` | 206, `bytes 0-0/1000`, body 1 byte |
| `bytes=500-999` | 206, body đúng 500 byte |
| `bytes=750-` | 206, body 250 byte |
| `bytes=-200` / `-2000` | 206, 200 byte cuối / toàn bộ 1.000 byte |
| `bytes=900-2000` | 206, `900-999/1000` |
| `bytes=1000-` / tệp rỗng | 416, `bytes */1000` / `bytes */0` |
| Multi-range không hỗ trợ | 200 full, không giả 206 |
| If-Range strong ETag còn khớp | 206; bytes đúng cùng phiên bản |
| If-Range cũ hoặc yếu | 200 full, không append dữ liệu cũ |
| Tệp của tenant khác | 403/404 theo policy, không rò bytes |

```java
@Test
void rangeMathIsExact() {
    ByteWindow mid = SingleRange.parse("bytes=500-999", 1000)
        .orElseThrow();
    assertEquals(500, mid.start());
    assertEquals(500, mid.length());
    assertEquals("bytes 500-999/1000", mid.contentRange());

    assertEquals(800, SingleRange.parse("bytes=-200", 1000)
        .orElseThrow().start());
    assertThrows(UnsatisfiableRange.class,
        () -> SingleRange.parse("bytes=1000-", 1000));
    assertTrue(SingleRange.parse("bytes=0-2,7-9", 1000).isEmpty());
}
```

Với MockMvc, gửi `GET /files/f-42` cùng header `Range`, assert status/`Content-Range`/`Content-Length` rồi so sánh mảng bytes sau `asyncDispatch` cho `StreamingResponseBody`. Integration test qua proxy/CDN phải xen kẽ `identity`/gzip, phiên bản cũ/mới và nhiều range khác nhau. Test thêm HEAD không body, file lớn hơn 2 GiB, ngắt tải sớm không rò resource, và client **thay file** khi server trả 200 thay vì append.

## 15. Bài thực hành: tải tiếp một báo cáo 1 GiB

Thiết kế `GET /reports/{id}/download` cho báo cáo riêng của mỗi tenant. Báo cáo được ghi bất biến theo phiên bản, có strong ETag và tồn tại 48 giờ. Gateway có thể nén nội dung mặc định; client phải có khả năng resume sau timeout.

**Yêu cầu đầu ra:**

1. Viết response **200** cho lần GET đầu, có `Content-Length`, ETag, `Accept-Ranges` và cache policy phù hợp.
2. Client đã nhận bền **268.435.456 byte** (256 MiB); viết request `Range` và `If-Range` để lấy phần còn lại. Tính `Content-Range` và `Content-Length` nếu toàn bộ dài **1.073.741.824 byte** (1 GiB).
3. Đề xuất xử lý khi object được thay từ ETag v3 sang v4 giữa hai lần tải; giải thích vì sao response phù hợp là 200 full nếu `If-Range` không khớp.
4. Thiết kế chính sách identity encoding để offset ổn định, giới hạn số vùng/connection và streaming không đọc toàn bộ RAM.
5. Bổ sung kiểm tra tenant/owner, URL ký có TTL, retention, CORS và `Content-Disposition` an toàn.
6. Viết test cho các trường hợp: 0–0, suffix, offset đúng kích thước, multi-range fallback, If-Range cũ, người khác tenant, hai lượt tải cùng phiên bản và file rỗng.

**Gợi ý tính toán:** 1 GiB = 1.073.741.824 byte, phần đầu client đã có = 268.435.456 byte. Phần còn lại dài **805.306.368 byte**; range cần thiết là `bytes=268435456-`, response 206 có `Content-Range: bytes 268435456-1073741823/1073741824`. Không dùng con số 256 hoặc 1.024 làm offset byte trong HTTP.

### Thang đánh giá (100 điểm)

| Tiêu chí | Điểm |
| --- | ---: |
| Cú pháp, phép tính và 200/206/416 chính xác | 25 |
| Resume an toàn bằng If-Range/strong ETag | 25 |
| Streaming, content coding và cache/CDN | 20 |
| Bảo mật, phân quyền, tài nguyên lớn | 15 |
| OpenAPI, kiểm thử bytes/race và bài thực hành | 15 |

## 16. Câu hỏi tự kiểm tra

1. `Range: bytes=0-99` yêu cầu bao nhiêu byte? Vì sao?
2. `bytes=500-` và `bytes=-500` khác nhau thế nào?
3. Với tệp 1.000 byte, `bytes=900-2000` cho `Content-Range` nào?
4. `Accept-Ranges` vắng mặt có đồng nghĩa không hỗ trợ Range không?
5. Khi nào nhận 200 dù đã gửi Range, và vì sao không được append body 200?
6. `416` dùng khi nào? `Content-Range: bytes */1000` nghĩa gì?
7. Multipart 206 đặt `Content-Range` ở cấp nào?
8. `If-Range` khác `If-Match` như thế nào khi validator đã cũ?
9. Vì sao không dùng weak ETag để resume?
10. Gzip ảnh hưởng đến offset byte và validator ra sao?
11. Vì sao một range chỉ lấy 1 byte vẫn cần authorization?
12. Test nào chứng minh server thực sự trả đúng bytes, không chỉ đúng 206?

**Điểm cần nhớ:** `Range` yêu cầu **vùng byte**; `Accept-Ranges` công bố khả năng; `Content-Range` xác định đoạn và kích thước; `206` trả một phần, `200` có thể trả toàn bộ khi bỏ qua Range và `416` dùng khi vùng không thỏa. Resume an toàn cần **cùng một representation**, strong ETag + `If-Range`, kiểm tra offset/bytes và xử lý đúng nén, streaming, cache và phân quyền.
