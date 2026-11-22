# Download response và Content-Disposition

Download API thường trông đơn giản: tìm file, trả bytes và đặt tên file trong response. Nhưng response download có thể làm lộ dữ liệu tenant khác, khiến browser render nội dung độc hại, ghi đè file của người dùng hoặc cache dữ liệu riêng tư ngoài ý muốn. Một endpoint tải file an toàn cần xác minh quyền trên từng file, xác định đúng representation, kiểm soát tên file và MIME type, giới hạn cache, xử lý Range/conditional request đúng HTTP semantics và stream dữ liệu có giới hạn tài nguyên.

`Content-Disposition` là HTTP response header hướng dẫn user agent cách trình bày nội dung, thường dùng `attachment` để đề nghị tải xuống và `inline` để đề nghị hiển thị trong trình duyệt nếu media type được hỗ trợ. Header này không phải cơ chế authorization, không bảo đảm browser luôn tải file và cũng không làm nội dung trở nên an toàn.

Trong module `SECURITY_API_SECURITY`, file download phải tuân theo quyền ở mức object, tenant và property. Server cần kiểm tra người gọi được tải file nào, ở trạng thái nào và trong phạm vi nào; sau đó mới phát response. Bài này tập trung vào download response, `Content-Disposition`, tên file Unicode, MIME type, cache, streaming, Range request và ví dụ triển khai với Spring.

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt `Content-Disposition: attachment` và `inline`.
- Tạo `filename` và `filename*` tương thích với tên file ASCII và Unicode.
- Tránh CRLF/header injection, path traversal và filename spoofing.
- Chọn `Content-Type`, `Content-Length`, `Cache-Control` và security header phù hợp.
- Bảo vệ download endpoint khỏi IDOR và cross-tenant access.
- Triển khai `HEAD`, conditional request, byte range, `206` và `416` đúng semantics.
- Stream file lớn mà không tải toàn bộ vào RAM.
- Đánh giá rủi ro của presigned URL, browser rendering và cross-origin download.
- Kiểm thử response headers, quyền truy cập, file content và lỗi giữa lúc stream.

## 1. Download response gồm những gì?

Một HTTP response tải file thường có dạng:

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-2026-001.pdf"
Content-Length: 48291
X-Content-Type-Options: nosniff
Cache-Control: private, no-store

<binary response body>
```

Các thành phần có vai trò khác nhau:

| Header/status | Vai trò | Điều cần chú ý |
|---|---|---|
| `Content-Type` | Kiểu media của representation được trả | Lấy từ metadata đáng tin hoặc server-side detection, không tin khai báo từ upload client |
| `Content-Disposition` | Gợi ý browser hiển thị inline hay tải attachment, cùng tên file đề xuất | Filename phải được sanitize và encode đúng chuẩn |
| `Content-Length` | Số byte của response body representation | Chỉ gửi khi biết chính xác độ dài của representation đang truyền |
| `Cache-Control` | Quy định cache | File riêng tư thường cần `private` và/hoặc `no-store` |
| `ETag`, `Last-Modified` | Validator cho conditional request | Không để validator làm lộ thông tin nhạy cảm hoặc bypass authorization |
| `Accept-Ranges`, `Content-Range` | Hỗ trợ tải một phần | Phải kiểm tra quyền trước khi trả `206` hoặc `416` |
| `X-Content-Type-Options` | Ngăn browser MIME sniffing trong các trường hợp áp dụng | Không thay thế content validation hoặc origin isolation |

Response body có thể là bytes từ local disk, object storage, generated report hoặc stream từ service khác. Cần xác định rõ nguồn dữ liệu, quyền truy cập, kích thước, lifecycle và cách xử lý khi client ngắt kết nối.

## 2. `Content-Disposition`: `attachment` và `inline`

### 2.1. `attachment`

`attachment` yêu cầu user agent xử lý nội dung như một file tải xuống thay vì hiển thị trực tiếp trong trang hiện tại. Ví dụ:

```http
Content-Disposition: attachment; filename="monthly-report.pdf"
```

Đây thường là lựa chọn phù hợp cho:

- Báo cáo PDF/CSV/XLSX được tạo từ dữ liệu tài khoản.
- File người dùng upload rồi tải lại.
- Archive, backup hoặc export package.
- File có nội dung không được phép render trong origin ứng dụng.

`attachment` là chỉ dẫn cho user agent, không phải cam kết tuyệt đối. Browser, extension, mobile WebView hoặc cấu hình người dùng có thể xử lý khác nhau. Server vẫn phải chọn MIME type chính xác, bảo vệ file và không dựa vào header này để ngăn mọi cách thực thi nội dung.

### 2.2. `inline`

`inline` gợi ý browser hiển thị nội dung trong cửa sổ/tab hiện tại nếu browser hỗ trợ media type đó:

```http
Content-Disposition: inline; filename="preview.pdf"
```

Chỉ dùng `inline` khi ứng dụng thực sự cần preview và nội dung đã được xem xét phù hợp để render. HTML, SVG, XML, PDF có JavaScript hoặc các định dạng active content có thể tạo rủi ro khi được phục vụ từ origin chứa session cookie hoặc quyền truy cập ứng dụng.

Với file do người dùng kiểm soát, cân nhắc phục vụ từ một origin riêng không chia sẻ cookie với ứng dụng chính, dùng `attachment` khi phù hợp và thêm sandbox/security policy cho nội dung cần preview. Không coi `inline` là an toàn chỉ vì file có đuôi `.pdf` hoặc `.png`.

### 2.3. Không dùng `Content-Disposition` thay authorization

Đổi `inline` thành `attachment` không ngăn người không có quyền tải bytes. Ngược lại, bỏ header này cũng không ngăn truy cập nếu endpoint trả nội dung mà không xác thực.

Authorization phải được kiểm tra trước khi đọc object hoặc phát bất kỳ byte nào. Nếu người dùng chỉ được xem preview đã redacted, không được trả file gốc chỉ bằng cách đổi query parameter hoặc `disposition=attachment`.

## 3. `filename` và `filename*`

### 3.1. `filename`

`filename` là parameter truyền tên file đề xuất trong `Content-Disposition`:

```http
Content-Disposition: attachment; filename="report.pdf"
```

Đây là dạng tương thích rộng cho tên ASCII. Giá trị có ký tự đặc biệt như dấu ngoặc kép, dấu gạch chéo ngược hoặc ký tự điều khiển cần được xử lý theo grammar của header; không nối trực tiếp chuỗi đầu vào vào response header.

Tên file trong header chỉ là gợi ý. Client có thể thay đổi tên khi lưu. Không dùng filename do browser gửi lại làm bằng chứng về đường dẫn lưu file hoặc danh tính object.

### 3.2. `filename*` cho Unicode

Tên file có dấu tiếng Việt hoặc ký tự Unicode nên được truyền bằng extended parameter `filename*`, dùng encoding theo RFC 8187. Ví dụ:

```http
Content-Disposition: attachment; filename="bao-cao-2026.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o-2026.pdf
```

Trong ví dụ:

- `filename` là fallback ASCII cho user agent cũ.
- `filename*` chỉ rõ charset UTF-8 và percent-encode các octet cần thiết.
- User agent hỗ trợ `filename*` thường ưu tiên giá trị này.

RFC 6266 định nghĩa `Content-Disposition` trong HTTP; RFC 8187 định nghĩa encoding extended parameter cho header HTTP. Khi cần tương thích, có thể gửi cả fallback `filename` và `filename*`, nhưng không gửi nhiều parameter cùng tên hoặc tự encode hai lần.

### 3.3. Quy tắc tạo filename fallback

Fallback nên:

- Chỉ chứa ký tự ASCII an toàn và phần mở rộng do server xác định.
- Thay dấu tiếng Việt hoặc ký tự không biểu diễn được bằng một dạng fallback dễ đọc.
- Không chứa CR, LF, NUL hoặc control character.
- Không chứa `/`, `\\` hoặc path segment.
- Có độ dài giới hạn.
- Không làm mất extension an toàn do server chọn.

Ví dụ:

```text
Tên hiển thị: báo-cáo-tháng-10.pdf
filename:     bao-cao-thang-10.pdf
filename*:    UTF-8''b%C3%A1o-c%C3%A1o-th%C3%A1ng-10.pdf
```

Không cần transliterate hoàn hảo; mục tiêu của fallback là tương thích. Tên Unicode đầy đủ nằm ở `filename*`.

## 4. Sanitize tên file và chống header injection

### 4.1. Không lấy raw filename từ request

Tên file do client upload có thể chứa:

- Path như `../../private/secret.txt` hoặc `C:\\Users\\...`.
- Dấu phân cách `/`, `\\`, ký tự null và control character.
- CR/LF để cố chèn header mới.
- Tên rất dài nhằm gây tốn tài nguyên hoặc làm hỏng log/UI.
- Ký tự Unicode vô hình, bidi control hoặc ký tự nhìn giống nhau.
- Extension giả như `invoice.pdf.exe` hoặc `image.png.html`.

Không dùng `MultipartFile.getOriginalFilename()` làm filesystem path, object storage key hoặc tên file tin cậy. Tạo storage key riêng bằng ID do server sinh. Nếu cần giữ tên hiển thị, lưu như metadata đã được validate và chỉ dùng sau khi sanitize ở output boundary.

### 4.2. CRLF/header injection

HTTP header được phân tách bằng CRLF. Nếu filename chứa `\r\n`, việc nối chuỗi trực tiếp có thể cho phép attacker tạo header ngoài ý muốn hoặc làm sai response framing ở thành phần xử lý lỗi.

Không làm như sau:

```java
response.setHeader(
    "Content-Disposition",
    "attachment; filename=\"" + userSuppliedFilename + "\"");
```

Hãy chuẩn hóa filename trước, từ chối control character và dùng API builder có xử lý quoting/encoding đúng chuẩn. Dù framework có từ chối CR/LF, ứng dụng vẫn nên validate để có hành vi rõ ràng và log an toàn.

### 4.3. Chống path traversal và tên file gây nhầm lẫn

Tên download không được quyết định đường dẫn object. Server nên:

1. Tra cứu file bằng object ID đã authorization.
2. Lấy storage key từ metadata server-side.
3. Lấy display filename từ metadata đã kiểm soát.
4. Loại bỏ path separator, control character và segment đặc biệt.
5. Áp extension dựa trên loại nội dung được phép.
6. Encode thành `filename`/`filename*`.

Không chỉ gọi `Path.normalize()` trên filename rồi dùng nó để truy cập storage. Cách đúng là tách hoàn toàn storage identifier khỏi tên hiển thị.

Với hệ điều hành đích khác nhau, có thể cần loại bỏ tên đặc biệt như `.`/`..`, tên thiết bị Windows, dấu chấm/khoảng trắng cuối tên và các ký tự không được filesystem hỗ trợ. Đây là vấn đề tên hiển thị/khả năng lưu file; nó không được phép tác động tới storage authorization.

### 4.4. Unicode bidi và extension spoofing

Ký tự điều khiển hướng chữ có thể làm tên file hiển thị khác thứ tự dự kiến. Một tên như `report[RIGHT-TO-LEFT OVERRIDE]gpj.exe` có thể đánh lừa người dùng khi nhìn extension. Với file nhạy cảm, nên loại bỏ hoặc hiển thị escaped các bidi control và control character; giữ extension do server xác định ở cuối tên.

Không tin extension để xác định `Content-Type`. File có tên `.pdf` vẫn có thể chứa HTML hoặc nội dung khác. Dùng metadata đã xác minh, magic bytes hoặc bộ phân tích định dạng phù hợp; với định dạng không tin cậy, cân nhắc chuyển đổi sang representation an toàn.

## 5. Chọn `Content-Type` và chống MIME sniffing

### 5.1. `Content-Type` phải phản ánh representation thực

Một số ví dụ:

| Nội dung | Content-Type thường dùng |
|---|---|
| PDF | `application/pdf` |
| CSV | `text/csv; charset=UTF-8` |
| JSON | `application/json` |
| ZIP | `application/zip` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| File không xác định/opaque binary | `application/octet-stream` |

Không lấy MIME type từ `Content-Type` do client khai báo khi upload mà không kiểm tra. Nếu không xác định chắc chắn, dùng `application/octet-stream` và thường trả dưới dạng attachment.

### 5.2. `X-Content-Type-Options: nosniff`

Có thể thêm:

```http
X-Content-Type-Options: nosniff
```

Header này yêu cầu browser không MIME-sniff trong các trường hợp được quy định, đặc biệt quan trọng với script/style resource. Nó không thay thế việc gán đúng `Content-Type`, không biến file HTML độc hại thành dữ liệu vô hại và không bảo đảm mọi browser xử lý mọi loại file giống nhau.

### 5.3. Phục vụ nội dung không tin cậy từ origin riêng

Nếu sản phẩm cần preview HTML, SVG hoặc định dạng có thể active, nên cân nhắc:

- Dùng origin riêng không gửi session cookie của ứng dụng chính.
- Không chia sẻ credential qua parent domain nếu không cần.
- Dùng `Content-Disposition: attachment` nếu preview không cần thiết.
- Áp CSP sandbox hoặc sandboxed viewer phù hợp với use case.
- Không cho file upload thực thi trong web root.
- Giới hạn CORS và không expose file riêng cho origin bất kỳ.

Subdomain riêng có thể vẫn chia sẻ cookie nếu cookie được đặt với `Domain` quá rộng. Khi cần cô lập mạnh, dùng một registrable domain riêng và không chia sẻ cookie.

## 6. Header thường dùng cho download

### 6.1. `Content-Length`

`Content-Length` là độ dài tính bằng byte của message body representation đang được gửi. Chỉ đặt khi biết chính xác độ dài sau các bước transform/content encoding áp dụng.

Không dùng file metadata cũ nếu object có thể đã thay đổi. Với response được nén, mã hóa hoặc chuyển đổi, độ dài cần phản ánh representation thực tế trên wire theo semantics HTTP. Nếu không biết trước, có thể stream mà không đặt `Content-Length` và để transport dùng framing phù hợp.

### 6.2. `Cache-Control`

File chứa dữ liệu cá nhân, hóa đơn, báo cáo hoặc thông tin tenant thường nên dùng:

```http
Cache-Control: private, no-store
```

`private` ngăn shared cache lưu response; `no-store` yêu cầu cache không lưu response. Đây là lựa chọn thận trọng cho dữ liệu nhạy cảm. Với tài nguyên công khai hoặc file có thể cache, có thể chọn policy khác như `public, max-age=...`, nhưng phải đánh giá CDN/shared cache key và khả năng thu hồi.

Không nghĩ rằng `Vary: Authorization` tự động làm mọi shared cache an toàn. Cách đơn giản hơn cho download riêng tư là không cho shared cache lưu response và xác minh quyền ở mỗi lần tải.

### 6.3. `ETag` và `Last-Modified`

Validator cho phép client gửi conditional request:

```http
If-None-Match: "file-v17"
If-Modified-Since: Tue, 17 Nov 2026 10:00:00 GMT
```

Server có thể trả `304 Not Modified` khi representation không đổi và điều kiện phù hợp. `ETag` nên đại diện cho version của representation; không dùng token hoặc thông tin nội bộ trong giá trị này.

Với dữ liệu riêng tư, authorization vẫn phải được thực hiện trước khi trả `304`. Nếu chỉ kiểm tra quyền khi trả body `200`, một `304` có thể xác nhận file tồn tại hoặc version của resource mà caller không được phép biết.

### 6.4. `Accept-Ranges`

Nếu server hỗ trợ byte range, có thể trả:

```http
Accept-Ranges: bytes
```

Không cần quảng bá header này nếu implementation không hỗ trợ hoặc không thể phục vụ range đúng. Range là byte offset của representation được chọn, không phải offset của file gốc sau khi server tùy ý transform.

## 7. Ví dụ Content-Disposition hoàn chỉnh

Response download PDF với tên tiếng Việt:

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="bao-cao-thang-10.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o-th%C3%A1ng-10.pdf
Content-Length: 48291
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
ETag: "report-v17"

<PDF bytes>
```

Response này đề nghị tải file với fallback ASCII và tên UTF-8. Browser vẫn có thể áp dụng hành vi riêng, nhưng server đã cung cấp metadata chuẩn và không phụ thuộc vào raw filename của client.

Với file công khai, cache policy có thể khác. Với file nhạy cảm, không bỏ authorization chỉ vì URL chứa UUID hoặc được ký.

## 8. Authorization cho download endpoint

### 8.1. Object-level authorization

Một route như:

```http
GET /api/files/{fileId}/download
```

cần kiểm tra file có tồn tại, thuộc tenant nào, owner hoặc principal nào, trạng thái có được tải không và caller có quyền download không.

Không chỉ kiểm tra `fileId` có tồn tại. UUID hoặc ID khó đoán chỉ làm giảm khả năng enumeration; nó không phải permission. Đây là lỗi IDOR/BOLA nếu user A thay ID của file mình bằng ID của file user B và nhận được bytes.

Có thể truy vấn theo cả object ID và tenant scope:

```sql
SELECT id, storage_key, display_name, media_type, size_bytes, version
FROM files
WHERE id = :file_id
  AND tenant_id = :authorized_tenant_id
  AND status = 'READY';
```

`:authorized_tenant_id` phải đến từ security context đã xác minh hoặc policy decision, không lấy nguyên từ query/body do client gửi. Nếu có sharing/delegation, kiểm tra quan hệ chia sẻ cụ thể.

### 8.2. Authorize trước khi mở stream

Thứ tự xử lý nên là:

1. Xác thực caller.
2. Tra cứu metadata theo object ID và scope phù hợp.
3. Kiểm tra quyền `file:download` trên file và tenant.
4. Kiểm tra trạng thái file, retention và legal hold nếu có.
5. Xác định media type, filename và version đã được server kiểm soát.
6. Mở stream hoặc tạo signed URL với phạm vi hẹp.
7. Ghi audit phù hợp và truyền response.

Không mở object storage stream trước khi authorization xong. Không trả `Content-Length`, filename hoặc ETag nhạy cảm cho object không được phép nếu các metadata đó làm lộ sự tồn tại hoặc kích thước.

### 8.3. Quyết định 403 hay 404

Nếu contract cần che sự tồn tại của file, có thể trả `404` cho cả file không tồn tại và file caller không được xem. Nếu contract cho phép phân biệt, trả `403` cho resource tồn tại nhưng caller thiếu quyền. Cần nhất quán giữa metadata endpoint, download endpoint, Range và conditional request để tránh enumeration oracle.

### 8.4. Audit download

Với file nhạy cảm, ghi audit event gồm actor, tenant, file ID, action, timestamp, request ID, kết quả và delivery mode (proxy hay signed URL). Không ghi raw bytes, token, cookie hoặc presigned URL đầy đủ vào log.

Audit nên phân biệt request được phép, request bị từ chối và việc tạo signed URL với lần URL đó được sử dụng nếu storage provider cung cấp access log. Tạo URL ký không đồng nghĩa file đã được tải hoàn tất.

## 9. Presigned URL và download qua object storage

### 9.1. Presigned URL là bearer capability

Presigned URL thường cho phép ai sở hữu URL thực hiện một hành động cụ thể với object trong một khoảng thời gian. Nó là bearer capability: người nhận URL có thể sử dụng mà không cần đăng nhập ứng dụng trong phạm vi chữ ký cho phép.

Khi cấp URL:

- Xác minh quyền trên file trước khi ký.
- Giới hạn object key, method và thời hạn.
- Không ký quyền rộng như list bucket hoặc prefix không cần thiết.
- Không để client tự chọn storage key tùy ý.
- Không log hoặc analytics URL đầy đủ vì query string thường chứa chữ ký.
- Dùng TTL ngắn phù hợp trải nghiệm và khả năng retry.
- Cân nhắc ký response header override như `Content-Disposition`/`Content-Type` nếu provider hỗ trợ và cần thiết.
- Thu hồi bằng cách xóa/rotate object, policy hoặc signing credential khi cần; không giả định mọi URL có thể thu hồi độc lập.

### 9.2. Metadata override trong signed URL

Một số object storage cho phép query parameter override `Content-Disposition` hoặc `Content-Type`. Các giá trị này phải do server tạo và được đưa vào chữ ký. Không để caller tự sửa response header sau khi URL được ký nếu provider không bảo vệ các parameter đó.

Nếu client có thể thay `response-content-disposition` thành `inline`, nội dung active có thể được browser render ngoài ý muốn. Kiểm tra chính xác behavior của provider, chữ ký và CORS trước khi dùng response override.

### 9.3. Proxy download hay redirect tới storage?

| Cách | Ưu điểm | Rủi ro/điểm cần kiểm soát |
|---|---|---|
| API proxy stream | Authorization tập trung; dễ áp response header và audit | Tiêu thụ bandwidth, connection và worker của API |
| Redirect/presigned URL | Giảm tải API, storage phục vụ file trực tiếp | URL là bearer secret; cần TTL, scope, response metadata và storage access log |
| CDN signed cookie/URL | Phân phối file lớn hiệu quả | Cache key, invalidation, tenant isolation và key rotation phức tạp |

Dù chọn cách nào, API phải authorize việc cấp quyền truy cập. Nếu redirect tới storage, response `302/303` cũng là một hành động cấp capability; không redirect chỉ vì client cung cấp object key.

## 10. Range request và tải file có thể tiếp tục

### 10.1. `Range: bytes=...`

Client có thể yêu cầu một phần representation:

```http
GET /api/files/file-123/download HTTP/1.1
Range: bytes=0-999
```

Nếu server hỗ trợ và range hợp lệ, response có thể là:

```http
HTTP/1.1 206 Partial Content
Content-Type: application/pdf
Content-Range: bytes 0-999/48291
Content-Length: 1000
Accept-Ranges: bytes
Content-Disposition: attachment; filename="report.pdf"

<first 1000 bytes>
```

`Content-Range` mô tả khoảng byte đã gửi và tổng độ dài representation. `Content-Length` là số byte của phần body trong response, không phải toàn bộ file.

### 10.2. Range không hợp lệ hoặc không thỏa mãn

Nếu range hợp lệ về cú pháp nhưng không có byte nào thỏa mãn, server có thể trả:

```http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */48291
```

Nếu server không hỗ trợ range, có thể bỏ qua Range và trả toàn bộ representation `200 OK` theo semantics HTTP. Không trả `206` nếu body không khớp `Content-Range`.

### 10.3. Multiple ranges

Request có thể chứa nhiều range. Server có thể hỗ trợ multipart/byteranges hoặc bỏ qua Range và trả `200`. Nếu policy không chấp nhận request quá phức tạp, có thể từ chối bằng lỗi request phù hợp; chỉ dùng `416` khi range byte không có phần nào thỏa mãn. Multiple ranges làm response phức tạp và có thể bị lạm dụng để tăng CPU/header overhead. Đặt giới hạn số range và xử lý overlap/coalescing theo chuẩn.

Không triển khai parser Range bằng cách tách chuỗi đơn giản rồi tin offset. Cần xử lý số âm, overflow, suffix range, open-ended range, nhiều range, whitespace và range vượt kích thước file theo HTTP semantics.

### 10.4. `If-Range`

Client có thể gửi `If-Range` cùng `Range`. Nếu validator khớp representation hiện tại, server trả phần byte được yêu cầu; nếu không khớp, server nên gửi toàn bộ representation hiện tại `200 OK` để client không ghép bytes từ hai version khác nhau.

Với ETag, `If-Range` cần strong validator; weak ETag không phù hợp cho mục đích này. Với date validator, chỉ dùng khi độ chính xác và semantics của Last-Modified phù hợp.

### 10.5. Authorization trước Range và conditional response

Thứ tự quan trọng:

1. Xác thực caller.
2. Xác minh quyền trên file hiện tại.
3. Xác định version/representation mà caller được tải.
4. Sau đó mới xử lý `If-None-Match`, `If-Modified-Since`, `Range` và `If-Range`.

Không để `304` hoặc `416` tiết lộ ETag, kích thước hoặc sự tồn tại của file mà caller không được truy cập. Không cho Range request bỏ qua kiểm tra tenant chỉ vì client đã biết URL.

## 11. Conditional requests và `HEAD`

### 11.1. `If-None-Match` và `304`

Với GET/HEAD, nếu `If-None-Match` khớp validator hiện tại, server có thể trả `304 Not Modified` và không gửi body. Với file riêng tư, vẫn cần xác minh authorization trước khi trả `304`.

Không dùng ETag dựa trực tiếp trên secret hoặc hash có thể tạo oracle cho dữ liệu có entropy thấp. Có thể dùng opaque version identifier hoặc HMAC của metadata nội bộ nếu cần validator không đoán được; lựa chọn phụ thuộc cache model.

### 11.2. `If-Modified-Since`

`Last-Modified` có độ chính xác theo giây trong HTTP-date. Nếu file thay đổi nhiều lần trong cùng một giây, date validator có thể không phân biệt được version. Với download quan trọng hoặc Range, ETag thường hữu ích hơn.

### 11.3. `HEAD`

`HEAD` trả headers tương tự GET nhưng không có response body. Có thể dùng để lấy kích thước hoặc metadata trước khi tải. Vì headers có thể tiết lộ tên file, kích thước, ETag và trạng thái, `HEAD` cũng phải qua cùng authentication và authorization như GET.

Không implement HEAD bằng cách tải toàn bộ file rồi bỏ body. Hãy lấy metadata từ storage/index và trả headers cần thiết. Nếu GET hỗ trợ conditional/range, xác định semantics HEAD nhất quán theo HTTP specification và framework.

## 12. Streaming file lớn

### 12.1. Tránh đọc toàn bộ file vào RAM

Không nên:

```java
byte[] bytes = storageClient.download(objectKey);
return ResponseEntity.ok().body(bytes);
```

cho file lớn hoặc traffic đồng thời cao nếu storage client đã buffer toàn bộ file. Bộ nhớ tiêu thụ xấp xỉ `file size × concurrent downloads`, chưa kể copy buffer và object overhead.

Thay vào đó, dùng stream có backpressure và buffer giới hạn. Khi client ngắt kết nối, hủy đọc upstream và đóng stream để giải phóng connection. Cần giới hạn concurrent download theo user/tenant và capacity của storage.

### 12.2. Content-Length và streaming

Nếu object storage cung cấp length đã xác minh cho đúng version, có thể gửi `Content-Length`. Nếu không biết độ dài, đừng đoán. HTTP server/container sẽ chọn framing phù hợp.

Nếu server nén hoặc transform nội dung, độ dài file gốc không còn là độ dài representation được truyền. Cần tính theo representation thực tế hoặc bỏ `Content-Length`.

### 12.3. Client disconnect và lỗi giữa stream

Sau khi headers hoặc một phần body đã gửi, server thường không thể đổi response thành JSON `500` một cách đúng đắn. Khi upstream storage lỗi giữa chừng:

- Đóng stream và connection phù hợp.
- Ghi log với request ID/file ID và byte count đã gửi.
- Hủy upstream request nếu client đã ngắt kết nối.
- Không ghi raw bytes hoặc signed URL vào log.
- Không tự động retry từ đầu sau khi đã gửi một phần body nếu client không hỗ trợ resume/Range.

Nếu cần retry/resume, dùng Range request với validator/version cố định. Tránh ghép bytes từ hai phiên bản file.

### 12.4. Timeout và concurrency

Đặt connect/read/idle timeout cho storage, tổng deadline phù hợp, giới hạn số download đồng thời và bandwidth/quota theo tenant. File export có thể cần queue thay vì giữ request HTTP lâu. Đối với file cực lớn, cân nhắc direct object storage hoặc CDN với signed capability.

## 13. Cross-origin download và JavaScript client

### 13.1. Browser navigation và Fetch khác nhau

Nếu người dùng điều hướng trực tiếp tới download URL hoặc click link, browser có thể xử lý `Content-Disposition` theo header. Nếu JavaScript dùng `fetch()` để nhận blob, code cần tự xử lý blob và tên file; `Content-Disposition` không tự tạo hành động download trong JavaScript.

Với cross-origin `fetch`, browser không cho JavaScript đọc mọi response header mặc định. Nếu client cần đọc `Content-Disposition`, server phải expose header qua CORS:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: Content-Disposition, ETag, X-Request-ID
```

Nếu response dùng credential, cần origin cụ thể và `Access-Control-Allow-Credentials: true`; wildcard không dùng được cho credentialed CORS. CORS chỉ cho browser đọc header, không cấp quyền tải file.

### 13.2. JavaScript download với Blob

Ví dụ đơn giản:

```javascript
const response = await fetch(downloadUrl, {
  credentials: "include"
});

if (!response.ok) {
  throw new Error("Download failed");
}

const blob = await response.blob();
const objectUrl = URL.createObjectURL(blob);
const link = document.createElement("a");
link.href = objectUrl;
link.download = safeClientFilename;
document.body.appendChild(link);
link.click();
link.remove();
setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
```

Đây là ví dụ cho file có kích thước vừa phải vì `response.blob()` có thể buffer nội dung trong browser memory. URL object được thu hồi trễ để browser có thời gian bắt đầu download; ứng dụng thực tế nên quản lý vòng đời URL và thu hồi sau khi không còn cần. Với file lớn, cân nhắc browser navigation tới URL được authorize hoặc cơ chế streaming/download phù hợp. `safeClientFilename` cần lấy từ metadata đáng tin và sanitize; không đưa raw header vào DOM hoặc attribute mà không parse/validate.

### 13.3. Parse Content-Disposition ở client

Nếu JavaScript cần tên từ response, nên dùng parser đã được kiểm chứng cho `Content-Disposition` thay vì split theo dấu `;` hoặc `=`. Quoting, escaped quote và `filename*` có thể khiến parser đơn giản xử lý sai. Server vẫn phải tạo header hợp lệ; client cần fallback tên an toàn nếu header thiếu hoặc malformed.

## 14. Spring Boot: xây dựng download response

### 14.1. Tạo Content-Disposition bằng builder

Với Spring Framework có `ContentDisposition` builder, có thể tạo header thay vì nối chuỗi:

```java
String downloadName = "báo-cáo-tháng-10.pdf";

ContentDisposition disposition = ContentDisposition.attachment()
    .filename(downloadName, StandardCharsets.UTF_8)
    .build();
```

Builder giúp encode/quote theo implementation của phiên bản Spring. Tùy phiên bản và overload, builder có thể phát `filename` hoặc `filename*`; không giả định một lời gọi sẽ luôn tạo cả hai parameter. Nếu contract cần fallback ASCII cùng tên UTF-8, hãy dùng helper/thư viện đã được kiểm chứng cho RFC 6266/8187 hoặc một formatter riêng có test parser/browser; không nối raw input vào header. Không tự encode trước rồi đưa chuỗi đã percent-encode vào builder nếu builder sẽ encode lần nữa.

### 14.2. ResponseEntity với Resource

Ví dụ file nhỏ hoặc resource có thể được quản lý an toàn:

```java
ResponseEntity<Resource> download(FileRecord file, Principal principal) {
    AuthorizedFile authorized = fileService.authorizeDownload(
        principal, file.id());

    Resource resource = storageService.openResource(authorized.storageKey());
    ContentDisposition disposition = ContentDisposition.attachment()
        .filename(authorized.safeDownloadName(), StandardCharsets.UTF_8)
        .build();

    return ResponseEntity.ok()
        .contentType(authorized.mediaType())
        .contentLength(authorized.sizeBytes())
        .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
        .header("X-Content-Type-Options", "nosniff")
        .cacheControl(CacheControl.noStore().cachePrivate())
        .body(resource);
}
```

Đây là ví dụ minh họa. `authorizeDownload` phải kiểm tra tenant/object permission và trạng thái file trước khi mở stream. `storageKey`, media type, length và safe filename phải lấy từ metadata server-side đã xác minh. `Resource` cần có lifecycle rõ; không trả một stream đã đóng trước khi framework ghi body.

Với `InputStreamResource`, việc framework xác định content length có thể tiêu thụ stream hoặc không khả thi tùy implementation. Chỉ đặt length nếu metadata đáng tin và response representation không bị transform. Không gọi `getInputStream()` nhiều lần trên resource one-shot.

### 14.3. StreamingResponseBody

Với file lớn, có thể dùng `StreamingResponseBody` để copy stream theo buffer:

```java
ResponseEntity<StreamingResponseBody> downloadLarge(
        UUID fileId, Principal principal) {

    AuthorizedFile file = fileService.authorizeDownload(principal, fileId);
    ContentDisposition disposition = ContentDisposition.attachment()
        .filename(file.safeDownloadName(), StandardCharsets.UTF_8)
        .build();

    StreamingResponseBody body = output -> {
        try (InputStream input = storageService.openStream(file.storageKey())) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
            output.flush();
        }
    };

    return ResponseEntity.ok()
        .contentType(file.mediaType())
        .contentLength(file.sizeBytes())
        .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
        .header("X-Content-Type-Options", "nosniff")
        .cacheControl(CacheControl.noStore().cachePrivate())
        .body(body);
}
```

Ví dụ cần bổ sung xử lý cancellation, timeout, exception logging và giới hạn concurrency theo hạ tầng thực tế. `StreamingResponseBody` chạy ở async executor; cấu hình executor có giới hạn thread/queue để không tạo unbounded work. Nếu client disconnect, write có thể ném IOException; cần để stream đóng qua try-with-resources và không retry tùy tiện.

Với object storage, nên dùng API streaming/download theo version hoặc generation cố định để metadata và bytes cùng trỏ tới một object version. Nếu object có thể thay đổi giữa lúc authorize và lúc mở stream, dùng immutable key/version hoặc conditional read để tránh TOCTOU.

### 14.4. Mapping lỗi

Các lỗi trước khi gửi body có thể được map theo contract:

| Tình huống | Status thường dùng |
|---|---|
| Chưa xác thực | `401 Unauthorized` |
| Không có quyền trên file | `403 Forbidden` hoặc `404` theo anti-enumeration policy |
| File không còn tồn tại/đã xóa | `404 Not Found` |
| File chưa sẵn sàng hoặc trạng thái không cho tải | `409 Conflict` hoặc status theo contract |
| Range không thỏa mãn | `416 Range Not Satisfiable` |
| Storage tạm thời không sẵn sàng trước khi stream | `503 Service Unavailable` |

Sau khi body bắt đầu gửi, không thể đảm bảo đổi sang Problem Details. Ghi log nội bộ và kết thúc stream an toàn. Không gửi exception message hoặc storage URL trong response.

## 15. Cấu trúc xử lý download khuyến nghị

Một service download dễ kiểm thử nên tách các trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| `FileAccessPolicy` | Kiểm tra actor, tenant, action và sharing rule |
| `FileMetadataService` | Trả version, length, media type và display name đáng tin |
| `FilenamePolicy` | Sanitize, fallback ASCII và Unicode extended parameter |
| `RepresentationResolver` | Chọn original, preview hoặc transformed representation |
| `RangeProcessor` | Parse range, If-Range và tạo byte interval đúng version |
| `StorageReader` | Mở stream theo immutable object key/version |
| `DownloadResponseFactory` | Tạo status/header nhất quán |
| `AuditService` | Ghi actor, file, tenant, result và delivery mode |

Flow tổng quát:

```mermaid
flowchart TD
    R[GET /files/{id}/download] --> A[Authenticate]
    A --> M[Load metadata by ID + authorized scope]
    M --> Z{Can download?}
    Z -- No --> D[Deny without leaking metadata]
    Z -- Yes --> V[Resolve immutable version and representation]
    V --> H[Build safe Content-Disposition and headers]
    H --> C[Evaluate conditional and Range headers]
    C --> S[Open bounded storage stream]
    S --> T[Stream with timeout/backpressure]
    T --> L[Audit outcome and release resources]
```

Authorization phải xảy ra trước khi xử lý các conditional/range response có thể tiết lộ metadata. `Open bounded storage stream` chỉ sau khi đã xác định object version và quyền hợp lệ.

## 16. Kiểm thử download response

### 16.1. Content-Disposition và filename

| Nhóm kiểm thử | Input/tình huống | Kết quả mong đợi |
|---|---|---|
| Attachment | Tải PDF/CSV bình thường | Có `attachment` và tên file an toàn |
| Inline | Preview loại file được phép | Chỉ inline theo policy và media type đã xác minh |
| Unicode | Tên file có dấu tiếng Việt | `filename*` UTF-8 hợp lệ; fallback ASCII có thể dùng |
| Quote/semicolon | Filename có dấu `"`, `;` | Header được encode/quote đúng, không phá grammar |
| CRLF | Filename chứa CR/LF/control | Bị từ chối hoặc loại bỏ trước khi tạo header; không xuất hiện header mới |
| Path traversal | `../../secret`, `C:\\temp\\x` | Không ảnh hưởng storage key; tên hiển thị được sanitize |
| Long name | Filename cực dài | Bị giới hạn theo policy |
| Bidi/control | Filename có bidi override hoặc ký tự vô hình | Được loại bỏ/hiển thị an toàn theo policy |
| Extension spoof | `report.pdf.exe` hoặc MIME mismatch | Media type và extension theo metadata đã xác minh |
| Duplicate parameter | Header có nhiều `filename`/`filename*` | Server không phát parameter trùng hoặc mơ hồ |

### 16.2. MIME và browser handling

- MIME type khớp nội dung đã xác minh.
- File không rõ định dạng dùng `application/octet-stream` và attachment theo policy.
- `X-Content-Type-Options: nosniff` có mặt ở response phù hợp.
- HTML/SVG/uploaded active content không render trên origin chứa session cookie nếu chưa có isolation.
- Preview endpoint không trả file gốc khi user chỉ có quyền xem bản redacted.
- `Cache-Control` phù hợp với dữ liệu nhạy cảm; CDN không cache chéo tenant.

### 16.3. Authorization và tenant isolation

| Principal | File của mình | File tenant khác | File đã xóa/expired |
|---|---|---|---|
| Anonymous | `401` | Không tiết lộ | Không tiết lộ |
| User A | Theo permission | `403` hoặc `404` theo policy | Từ chối |
| User B cùng tenant | Theo sharing/role | Theo sharing/role | Từ chối |
| User tenant khác | Không có quyền mặc định | Không có quyền | Không tiết lộ |
| Operator | Theo privileged policy/audit | Theo privileged policy/audit | Theo retention/legal hold |

Kiểm tra cả `GET`, `HEAD`, `Range`, `If-None-Match`, `If-Modified-Since`, presigned URL issuance và download thực tế. Không chỉ test GET 200.

### 16.4. Range và conditional requests

| Request | Kết quả mong đợi |
|---|---|
| Không có Range | `200` với toàn bộ representation |
| `Range: bytes=0-99` | `206`, `Content-Range: bytes 0-99/total`, body đúng 100 bytes |
| Suffix range hợp lệ | `206` với byte cuối theo semantics |
| Open-ended range | `206` tới cuối representation |
| Range ngoài kích thước | `416` và `Content-Range: bytes */total` nếu được phép tiết lộ |
| If-Range khớp strong ETag | Trả `206` theo range |
| If-Range không khớp | Trả full `200` |
| If-None-Match khớp | `304` sau khi authorization thành công |
| HEAD | Headers phù hợp, không có body |
| Multiple ranges | Xử lý đúng multipart/byteranges hoặc policy bỏ qua/từ chối |
| Object version thay đổi | Không ghép bytes từ hai version; validator/version được kiểm tra |

### 16.5. Streaming và failure

- File lớn được stream với bộ nhớ giới hạn.
- Client disconnect làm đóng upstream stream và giải phóng connection.
- Storage timeout và lỗi giữa stream được log, không lộ exception.
- Concurrency limit và tenant quota hoạt động.
- `Content-Length` khớp chính xác body representation.
- Nếu không biết length, response không phát length sai.
- File version được cố định giữa metadata lookup và stream open.
- Presigned URL có TTL, scope và response override đúng; URL không xuất hiện trong log.

## 17. Logging, monitoring và incident response

### 17.1. Log/audit

Ghi các trường cần cho điều tra:

- Request ID/trace ID.
- Actor, tenant và authorization result đã xác minh.
- File ID, version/generation và action.
- Response status, bytes sent, range/full response và delivery mode.
- Storage logical provider, latency và failure category.
- Presigned URL issuance event, TTL và scope — không ghi URL/signature đầy đủ.
- Client disconnect, timeout, cancellation và stream error.

Không ghi bearer token, cookie, signed URL query, raw file bytes hoặc nội dung nhạy cảm. Không dùng filename do client gửi làm log field không sanitize vì có thể tạo log injection.

### 17.2. Metrics

Theo dõi:

- Download count/bytes theo route, tenant tier và media type.
- Authorization deny và cross-tenant attempt.
- Range/206/416 ratio và conditional 304 ratio.
- Stream duration, throughput, active streams và disconnect rate.
- Storage latency/error, retry và connection pool saturation.
- Presigned URL issuance/expiry/access nếu provider có log.
- Cache hit/miss và cache policy mismatch.
- File preview/download theo loại nội dung.

Không gắn raw file ID, user ID hoặc filename vào metric label có cardinality không giới hạn. Dùng route template, media type và error category.

### 17.3. Khi phát hiện rò rỉ download

1. Xác định file/object version, tenant, actor và đường phân phối (proxy, CDN hay signed URL).
2. Thu hồi capability có thể thu hồi; rotate signing key hoặc thay policy nếu credential ký bị lộ.
3. Vô hiệu hóa URL hoặc object/version bị lộ theo khả năng provider.
4. Rà soát CDN/shared cache và purge representation đã cache sai scope.
5. Kiểm tra access logs để xác định phạm vi bytes đã được tải.
6. Nếu file chứa credential/secret, xử lý như secret compromise và rotate.
7. Sửa authorization/cache/response policy và thêm regression test.

## 18. Checklist trước khi phát hành

- [ ] Download endpoint xác thực caller và kiểm tra object/tenant permission trước khi mở stream.
- [ ] `GET`, `HEAD`, `Range`, conditional request và signed URL issuance có authorization nhất quán.
- [ ] Storage key được lấy từ metadata server-side, không từ filename hoặc path client gửi.
- [ ] `Content-Disposition` chọn `attachment`/`inline` theo loại nội dung và use case.
- [ ] Filename được sanitize, giới hạn độ dài và loại control/CRLF/path separator/bidi nguy hiểm.
- [ ] Tên Unicode dùng `filename*` UTF-8; fallback `filename` ASCII hợp lệ khi cần.
- [ ] Header được tạo bằng builder/thư viện phù hợp, không nối raw input.
- [ ] `Content-Type` dựa trên nội dung/metadata đã xác minh, không tin MIME khai báo khi upload.
- [ ] `X-Content-Type-Options: nosniff` và browser origin isolation phù hợp.
- [ ] File active/untrusted không render trên origin chứa session cookie nếu chưa có sandbox/isolation.
- [ ] `Content-Length` khớp representation; không đoán độ dài khi transform/stream.
- [ ] File riêng tư có `Cache-Control` phù hợp; shared cache không dùng chung response giữa tenant.
- [ ] ETag/Last-Modified không làm lộ metadata và authorization được kiểm tra trước 304/416.
- [ ] Range/If-Range được xử lý đúng; giới hạn multiple ranges và không trộn file versions.
- [ ] Streaming dùng buffer/concurrency/timeout giới hạn; client disconnect đóng upstream.
- [ ] Presigned URL là capability có TTL, scope hẹp và không bị log.
- [ ] Cross-origin JavaScript chỉ đọc `Content-Disposition` khi header được expose có chủ đích.
- [ ] Có test filename Unicode, CRLF, traversal, MIME, IDOR, tenant, Range, HEAD, 304 và streaming failure.
- [ ] Audit/metrics đủ điều tra nhưng không chứa token, signed URL hoặc file content.

## Kết luận

Download response an toàn cần kết hợp authorization trên object, metadata đáng tin, `Content-Disposition` được encode đúng chuẩn, MIME/cache policy phù hợp và streaming có giới hạn. `attachment`/`inline` chỉ hướng dẫn user agent; `filename`/`filename*` chỉ đề xuất tên file. Chúng không thay thế quyền truy cập, content validation hay origin isolation. Khi hỗ trợ Range, conditional request hoặc presigned URL, hãy giữ cùng một file version và kiểm tra quyền trước khi tiết lộ metadata hoặc gửi bytes. Cách tiếp cận này giúp download API tương thích browser mà vẫn bảo vệ dữ liệu và tài nguyên hệ thống.
