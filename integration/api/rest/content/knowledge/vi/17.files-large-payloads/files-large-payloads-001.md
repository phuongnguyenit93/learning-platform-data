# Chọn dữ liệu nhị phân, multipart/form-data hoặc tài nguyên tệp

## 1. Bài toán: một tệp có thể là nội dung request hoặc một tài nguyên độc lập

REST API không nhất thiết truyền mọi thứ bằng JSON. Người dùng có thể tải ảnh đại diện, đính kèm hóa đơn PDF, gửi video, tải tài liệu xuống hoặc gửi một biểu mẫu vừa có mô tả vừa có tệp. Với các trường hợp ấy, cần chọn **hình thức biểu diễn trên HTTP** và **vòng đời tài nguyên** trước khi chọn thư viện Java.

Ba lựa chọn chính:

1. **Body nhị phân trực tiếp:** request hoặc response body chứa bytes của một tệp, với Content-Type thích hợp.
2. **multipart/form-data:** một request chứa nhiều part độc lập, ví dụ JSON metadata và một hoặc nhiều file.
3. **Tài nguyên tệp riêng:** tệp có ID, URI, metadata, trạng thái, quyền truy cập và vòng đời; dữ liệu có thể truyền bằng nhị phân hoặc multipart trong một thao tác tạo/cập nhật.

**Điểm quan trọng:** Lựa chọn thứ ba là **mô hình tài nguyên**, không phải một định dạng body cạnh tranh với hai lựa chọn đầu. Một API hoàn toàn có thể dùng POST multipart để tạo tài nguyên /api/files/{id}, rồi GET /api/files/{id}/content để tải bytes. Cần phân biệt **cách chuyển dữ liệu** với **cách quản lý tệp**.

Trong module **INTEGRATION_API_REST**, quyết định này liên hệ trực tiếp với URI, phương thức GET/POST/PUT, mã 201/202/206/413/415, hợp đồng OpenAPI, xác thực/phân quyền, cache, idempotency và kiểm thử Java/Spring.

## 2. Ma trận quyết định nhanh

| Nhu cầu | Thiết kế khởi đầu hợp lý | Vì sao |
|---|---|---|
| Thay nội dung ảnh đại diện tại URI cố định | **PUT body image/jpeg hoặc image/png** | Một representation nhị phân, URI đã biết |
| Tạo tệp có title, category và nội dung trong cùng request nhỏ/vừa | **POST multipart/form-data** | Metadata và bytes cùng được chuyển trong một request |
| Quản lý đính kèm có phân quyền, trạng thái scan, lịch sử hoặc xóa | **Tài nguyên /api/files/{id}** | Có identity, vòng đời, metadata và endpoint content |
| Tải PDF hoặc ảnh từ resource | **GET với media type thực** | Response là bytes, không cần JSON/base64 |
| Tệp lớn, kết nối chậm, cần upload tiếp tục hoặc lưu object storage | **Upload session/direct upload + tài nguyên tệp** | Giới hạn proxy, retry từng phần, giảm tải ứng dụng |
| Gửi danh sách nhiều tài liệu kèm thông tin riêng từng tài liệu | **Multipart hoặc nhiều tài nguyên riêng** | Phải định nghĩa atomic/partial success rõ |
| Client chỉ gửi metadata, tệp đã có trong object storage | **POST JSON metadata/link nội bộ** | Không cần truyền lại bytes nếu quyền và tính toàn vẹn đã xác minh |

Hãy tự hỏi: **một file hay nhiều file? Metadata có phức tạp không? Ai sở hữu tài nguyên? Dung lượng tối đa? Có cần scan, tải lại, retry, versioning hoặc link chia sẻ?** Nếu tài liệu có đời sống độc lập, nên cho nó một resource ID thay vì chỉ giữ một trường file trong request khác.

## 3. Truyền body nhị phân trực tiếp

### 3.1. Content-Type thể hiện loại bytes

Ví dụ thay ảnh đại diện:

~~~http
PUT /api/users/me/avatar/content HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: image/png
If-Match: "avatar-v3"
Content-Length: 123456

<123456 bytes PNG>
~~~

Nếu URI đại diện cho nội dung ảnh của chính người dùng và PUT được định nghĩa là **thay thế toàn bộ**, việc gửi lại cùng bytes thường không nhân đôi tài nguyên. Nếu cần chống lost update, dùng **If-Match** với ETag mạnh và kiểm tra phiên bản nguyên tử; mismatch trả **412 Precondition Failed**.

Phản hồi khi thay thành công:

~~~http
HTTP/1.1 204 No Content
ETag: "avatar-v4"
Cache-Control: no-store
~~~

Đây là **quy ước API minh họa**, không phải cứ PUT là phải trả 204. Nếu URI chưa có tài nguyên và PUT tạo mới thành công, **201 Created** thường phù hợp. Với PUT thay thế, phải đảm bảo phiên bản ETag mới tương ứng representation đã lưu; không tự phát validator sai với bytes bị biến đổi hoặc chuyển định dạng.

Nếu không nhận diện được loại nội dung chính xác, có thể dùng **application/octet-stream** cho bytes tổng quát. Tuy nhiên, khi biết tệp là PNG, PDF hay JPEG, media type thực tế (image/png, application/pdf, image/jpeg) hữu ích hơn. **Tên tệp .png hoặc Content-Type client khai báo không chứng minh bytes thực sự là PNG.**

### 3.2. Ưu, nhược điểm

**Ưu điểm:** ít overhead giao thức, thích hợp streaming, endpoint dễ mô tả bằng một media type, tải xuống theo cách HTTP thông thường. **Giới hạn:** khó gửi metadata có cấu trúc phức tạp cùng body; thường cần endpoint metadata riêng, query/header đã quy định hoặc một bước tạo resource trước.

Không nên dồn mọi metadata nghiệp vụ vào header tự đặt, ví dụ hàng chục trường địa chỉ, trạng thái duyệt, tags; khi dữ liệu phức tạp, POST multipart hoặc tạo metadata bằng JSON trước sẽ dễ bảo trì hơn.

### 3.3. Không mã hóa file bằng base64 trong JSON theo mặc định

~~~json
{"fileName":"scan.pdf","contentBase64":"JVBERi0xLjQK..."}
~~~

Phương án này đôi khi cần khi hệ thống chỉ hỗ trợ JSON, nhưng base64 thường tăng kích thước biểu diễn khoảng **33% trước overhead JSON**, đồng thời có thể tăng số bản sao dữ liệu trong bộ nhớ. Với upload thực tế, ưu tiên binary/multipart và streaming. Không tuyên bố JSON base64 bị cấm tuyệt đối: nó là trade-off cho tệp nhỏ và hợp đồng có ràng buộc.

## 4. multipart/form-data: một request có nhiều phần

### 4.1. Ví dụ một tệp và metadata JSON

~~~http
POST /api/files HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: multipart/form-data; boundary=example-boundary

--example-boundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Biên nhận tháng 11","category":"invoice"}
--example-boundary
Content-Disposition: form-data; name="file"; filename="receipt.pdf"
Content-Type: application/pdf

<bytes PDF>
--example-boundary--
~~~

Mỗi part có **Content-Disposition** với name riêng; part file có thể có filename và Content-Type. **Boundary là một phần bắt buộc của cách đóng gói multipart**; khi dùng browser FormData/curl/HTTP client library, hãy để thư viện tự tạo boundary và header tương ứng, không tự gõ Content-Type thiếu boundary.

Phản hồi nếu API đã lưu, xác minh cần thiết và hoàn thành tạo resource:

~~~http
HTTP/1.1 201 Created
Location: /api/files/f-742
Content-Type: application/json
Cache-Control: no-store

{
  "id": "f-742",
  "title": "Biên nhận tháng 11",
  "mediaType": "application/pdf",
  "size": 248310,
  "state": "READY",
  "contentUrl": "/api/files/f-742/content"
}
~~~

Nếu tệp chỉ mới được tiếp nhận để quét malware hoặc xử lý hậu kỳ, không trả **READY** sai sự thật. API có thể trả **202 Accepted** kèm URI trạng thái, hoặc tạo metadata resource bằng **201** với state PENDING_SCAN; phải giải thích rõ điều kiện để tải nội dung.

### 4.2. Gửi bằng curl

~~~bash
curl -i -X POST 'https://api.example.test/api/files' \
  -H 'Authorization: Bearer <test-token>' \
  -F 'metadata={"title":"Biên nhận","category":"invoice"};type=application/json' \
  -F 'file=@./receipt.pdf;type=application/pdf'
~~~

Với nhiều file, có thể dùng các part cùng name (ví dụ files) nếu API cho phép. **Thứ tự part, giới hạn số part, tổng size, kiểm tra metadata ứng với file nào và tính nguyên tử** phải nằm trong contract; không suy diễn mọi upload nhiều tệp là all-or-nothing.

### 4.3. Khi không nên dùng multipart

Không cần multipart nếu body chỉ là một file và URI đã có (raw PUT thường đơn giản hơn). Cũng không nên coi multipart là giải pháp mặc định cho video rất lớn cần resume theo chunk; có thể cần **upload session** riêng hoặc direct upload tới object storage.

## 5. Thiết kế tài nguyên tệp và vòng đời

Một file thường có hai representation khác nhau:

~~~http
GET /api/files/f-742 HTTP/1.1
Accept: application/json
~~~

~~~json
{
  "id": "f-742",
  "fileName": "receipt.pdf",
  "mediaType": "application/pdf",
  "size": 248310,
  "state": "READY",
  "sha256": "..."
}
~~~

Và bytes:

~~~http
GET /api/files/f-742/content HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 248310
Content-Disposition: attachment; filename="receipt.pdf"
X-Content-Type-Options: nosniff
Cache-Control: no-store

<bytes PDF>
~~~

Tách **metadata JSON** khỏi **content bytes** làm rõ schema, cache policy và lifecycle. ID nên do server cấp, không dùng filename như đường dẫn lưu trữ tin cậy. Có thể dùng URI khác; hai URI trên là thiết kế mẫu.

### 5.1. State machine của tài nguyên

~~~mermaid
stateDiagram-v2
    [*] --> INITIATED
    INITIATED --> UPLOADING
    UPLOADING --> PENDING_SCAN: Bytes đã nhận đủ và xác minh
    PENDING_SCAN --> READY: Scan/policy đạt
    PENDING_SCAN --> REJECTED: Scan/policy không đạt
    UPLOADING --> FAILED: Truyền không hoàn tất
    READY --> DELETED: Chủ thể có quyền xóa
    REJECTED --> DELETED
    FAILED --> DELETED
~~~

Các trạng thái **là mô hình ứng dụng**, không phải status HTTP. Ví dụ tài nguyên ở PENDING_SCAN có thể truy cập metadata bằng GET 200, nhưng GET content chưa được cho phép; API cần định nghĩa trả 409/423 hoặc mã phù hợp với tình trạng và quyền, không công bố nhầm bytes chưa quét.

### 5.2. Hợp đồng hành động gợi ý

| Endpoint | Ý nghĩa | Response điển hình |
|---|---|---|
| POST /api/files | Tạo tệp bằng multipart | 201 + Location khi hoàn tất; 202 nếu nhận để xử lý bất đồng bộ |
| GET /api/files/{id} | Xem metadata/trạng thái | 200 JSON |
| GET /api/files/{id}/content | Tải bytes khi READY, có quyền | 200 hoặc 206 nếu hỗ trợ Range |
| HEAD /api/files/{id}/content | Xem header mà không lấy body | 200 với metadata tương ứng |
| PUT /api/files/{id}/content | Thay toàn bộ bytes theo contract | 204 hoặc 200; 412 nếu If-Match sai |
| DELETE /api/files/{id} | Ngừng cung cấp/xóa theo chính sách | 204, 202 hoặc mã hợp đồng phù hợp |

**Xóa resource khỏi API không tự bảo đảm xóa tức thì khỏi backup/object-store versions**. Cần chính sách retention và xóa dữ liệu riêng. Link /content vẫn phải kiểm tra quyền tại thời điểm tải, dù caller từng đọc metadata.

## 6. Header, HTTP status và cache cần hiểu

| Thành phần | Ý nghĩa | Lưu ý |
|---|---|---|
| **Content-Type** | Media type của bytes hoặc multipart | Không tin MIME do client tự khai là đủ |
| **Content-Length** | Số byte trên HTTP message khi xác định được | Có thể vắng mặt khi truyền chunked; không bỏ giới hạn kích thước |
| **Content-Disposition** | inline hoặc attachment và tên tải về | Escape tên an toàn; không dùng trực tiếp làm đường dẫn server |
| **ETag** | Validator của selected representation | Phải thay đổi đúng khi nội dung thay đổi |
| **If-None-Match** | Revalidate GET/HEAD | Khớp có thể trả 304, không có body |
| **If-Match** | Điều kiện thay thế để tránh ghi đè | Mismatch: 412, cần kiểm tra nguyên tử |
| **Range** | Yêu cầu một phần bytes khi server hỗ trợ | Có thể trả 206; không phải cơ chế resumable upload |
| **Cache-Control** | Chính sách lưu/revalidate | Tệp riêng tư thường dùng private/no-store theo phân loại |
| **Location** | URI tài nguyên/operation liên quan | Gửi khi tạo resource hoặc theo dõi |

Các mã lỗi cần tài liệu hóa: **400** dữ liệu/multipart sai cú pháp; **401/403/404** xác thực, quyền và che giấu; **409** xung đột trạng thái; **412** điều kiện If-Match không đạt; **413 Content Too Large** khi vượt giới hạn; **415 Unsupported Media Type** khi loại content không được chấp nhận; **422 Unprocessable Content** khi cấu trúc hợp lệ nhưng nội dung không đạt quy tắc nghiệp vụ. **500/503** dành cho lỗi server/storage, không đổi thành 400 để đổ lỗi cho client.

### 6.1. Range download không đồng nghĩa upload từng đoạn

Client có thể gửi:

~~~http
GET /api/files/f-742/content HTTP/1.1
Range: bytes=0-1023
~~~

Nếu server hỗ trợ byte ranges và tệp đủ dài, phản hồi:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 0-1023/248310
Content-Length: 1024
Content-Type: application/pdf

<1024 bytes đầu>
~~~

Nếu range không thỏa mãn, server có thể trả **416 Range Not Satisfiable** với Content-Range dạng **bytes */248310**. Không tự tuyên bố hỗ trợ Range chỉ vì endpoint trả Resource; phải kiểm thử với storage/gateway thật. Resume upload là **một giao thức khác**, cần upload session, offset/part ID, kiểm tra chunk và hoàn tất có điều kiện.

## 7. Bảo mật: nội dung, filename, quyền và tài nguyên tiêu thụ

Upload file là một **bề mặt tấn công** chứ không chỉ là thao tác đọc stream. Kiểm tra đầy đủ cần nhiều lớp:

1. **Authentication/authorization:** người gọi có quyền tạo file trong tenant/folder/record cha không? GET/download/delete cũng phải kiểm tra ACL. ID không phải credential.
2. **Giới hạn:** kiểm tra request body, mỗi file, tổng số part, số file, thời gian truyền, số upload đồng thời và quota lưu trữ. Không chỉ tin Content-Length do client khai.
3. **Media type và nội dung thật:** allowlist loại được phép; kiểm tra signature/magic bytes hoặc parser chuyên dụng khi phù hợp. MIME do client khai và phần mở rộng chỉ là tín hiệu.
4. **Tên tệp không đáng tin:** filename trong Content-Disposition có thể chứa đường dẫn, ký tự điều khiển, Unicode bất thường hoặc ký tự dùng trong header. Sinh **storage key ngẫu nhiên phía server**, chuẩn hóa tên hiển thị và escape khi phản hồi.
5. **Malware và file nguy hiểm:** scan/kiểm tra policy trước khi công bố READY; dùng quarantine; kiểm tra archive bomb, zip-slip và decompression ratio khi giải nén.
6. **Nội dung thực thi trên trình duyệt:** không tùy tiện phục vụ HTML/SVG hoặc script người dùng tải lên cùng origin với ứng dụng; xét Content-Disposition: attachment, nosniff, origin tách biệt và CSP theo ngữ cảnh.
7. **Bảo vệ dữ liệu:** mã hóa khi truyền và lưu theo chính sách; không ghi body/token vào log; quy định retention, phân quyền cache và xóa/đối soát.

**Không có bước kiểm tra đơn lẻ nào bảo đảm tệp an toàn.** Ví dụ một tệp được khai image/png nhưng thực tế chứa nội dung không mong muốn vẫn có thể vượt qua kiểm tra tên đuôi; cần xác minh cả nội dung và cách phục vụ.

### 7.1. Filename không phải path

Không làm:

~~~java
// Không an toàn: tên tệp do client gửi quyết định đường dẫn lưu.
Path destination = uploadRoot.resolve(file.getOriginalFilename());
Files.copy(file.getInputStream(), destination);
~~~

Thay vào đó, lưu bytes dưới **opaque object key** do server phát sinh và chỉ lưu filename client như metadata hiển thị đã kiểm tra. Khi tải xuống, tạo Content-Disposition bằng bộ tạo header của framework; không nối raw filename vào header. Nếu app cho phép tải file đã lưu trên filesystem, phải xác thực canonical path và không cho ID/filename dẫn ra ngoài vùng lưu trữ.

### 7.2. Không tiết lộ tệp bằng URL dễ đoán

GET /api/files/{id}/content phải kiểm tra **owner/tenant/ACL tại thời điểm request**, kể cả khi trước đó caller đã upload. Nếu file được lưu ở object storage và truy cập qua signed URL:

- URL đã ký là **bearer capability** trong thời gian còn hiệu lực; ai có URL có thể dùng theo quyền của nó.
- Cấp URL **thời hạn ngắn, giới hạn method, object key, loại quyền và content type/size khi dịch vụ hỗ trợ**.
- Không đưa signed URL vào log, analytics, error detail hoặc tài liệu công khai.
- Kiểm tra quyền **trước khi phát URL**, và cân nhắc thu hồi/quarantine nếu trạng thái tệp đổi; URL còn hạn không tự bị vô hiệu trong mọi storage provider.
- Cấu hình CORS ở storage khi browser upload trực tiếp, nhưng **CORS không thay authentication/authorization**.

### 7.3. Tính toàn vẹn dữ liệu

Client có thể gửi checksum SHA-256 theo một trường metadata/header **được hợp đồng định nghĩa**. Server tính checksum từ bytes thực nhận và so sánh; với multipart/chunk phải quy định checksum áp dụng trên **toàn tệp hay từng part**. Không tin hash client khai là bằng chứng an toàn của file; checksum giúp phát hiện lỗi truyền/lưu, không thay antivirus hoặc ACL. Nếu tải lên qua signed URL, server cần xác nhận object thực có size, content type và checksum mong đợi trước khi chuyển READY.

## 8. Tệp lớn: streaming, session và timeout

### 8.1. Giới hạn bộ nhớ và reverse proxy

Một anti-pattern thường gặp là đọc toàn bộ file vào byte[] trước khi ghi:

~~~java
byte[] all = multipartFile.getBytes(); // có thể tốn RAM lớn
storage.save(all);
~~~

Với file lớn, nên xử lý bằng **InputStream/streaming** có giới hạn bytes và không giữ toàn bộ nội dung trong heap. Tuy nhiên, MultipartFile có thể được container lưu tạm trên disk hoặc memory theo cấu hình; streaming từ MultipartFile **không có nghĩa toàn bộ đường truyền HTTP→container hoàn toàn không buffer**. Hãy kiểm tra ngưỡng spool, multipart parser, reverse proxy buffering, JVM memory, disk tạm, connection timeout và object storage client.

Ví dụ Spring Boot application configuration (chỉ là ngưỡng minh họa):

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 20MB
      max-request-size: 22MB
~~~

Đây không phải giới hạn tuyệt đối của toàn hệ thống: proxy, web server, gateway và storage có thể áp dụng các ngưỡng khác. Khi xử lý raw binary, vẫn phải có **đếm bytes lúc đọc stream** và ngắt khi vượt giới hạn, kể cả khi Content-Length vắng mặt.

### 8.2. Direct upload theo session

Khi file nhiều GB, một mô hình thường dùng:

1. Client POST **/api/uploads** với size, media type và checksum; API kiểm tra quyền/quota rồi cấp session và hướng dẫn upload.
2. Client tải từng part lên storage bằng quyền giới hạn, giữ part receipts để retry.
3. Client POST **/api/uploads/{id}/complete**; API xác minh object, size, checksum và đưa vào scan, trả trạng thái **PENDING_SCAN**.
4. Khi kiểm tra đạt, tài nguyên chuyển **READY**; client GET metadata để biết khi nào có thể tải nội dung.

Client không được tự coi upload xong là tài nguyên READY: server phải **xác minh object và quyền** ở bước complete. Cần cơ chế dọn upload bỏ dở, giới hạn số session, expiration, quota và xử lý retry complete idempotent.

**Không nhầm resume download với resume upload.** HTTP Range áp dụng cho việc lấy một phần representation; upload từng đoạn cần quy ước offset/part number, checksum, commit/complete và xử lý trùng. Có thể chọn giao thức resumable đã được thống nhất với client hoặc API riêng; không tự nghĩ multipart/form-data sẽ cung cấp resumability.

### 8.3. Streaming vẫn cần kế hoạch lỗi

Nếu upload bị ngắt giữa chừng, xóa/quarantine object tạm, không phát tệp READY; nếu response 201 bị mất **sau khi server tạo tệp**, retry POST có thể tạo hai file. Với tạo resource có side effect, có thể yêu cầu **Idempotency-Key** hoặc một client upload ID duy nhất, scope/TTL/fingerprint rõ ràng. PUT thay thế một URI cố định thường dễ retry hơn, nhưng vẫn phải giải quyết điều kiện version và lỗi ghi giữa chừng.

Khi tải xuống đã bắt đầu, server có thể không đổi status HTTP sau khi gửi header nếu stream bị lỗi giữa chừng. Client phải kiểm tra số bytes/checksum khi quan trọng, có thể retry/range theo hỗ trợ của server. Metrics cần ghi **bytes thực truyền** và lỗi streaming, không chỉ request đã trả 200 lúc bắt đầu.

## 9. Java/Spring: hai đường upload và một đường download

Các ví dụ dưới dùng Spring MVC/Boot hiện đại. Các interface dịch vụ được mô tả rõ nhưng **cần implementation** cho persistence, object storage, antivirus, quota và policy; đây không phải một ứng dụng triển khai đầy đủ.

### 9.1. POST multipart: metadata JSON + file

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

record FileMetadata(
        @NotBlank String title,
        @NotBlank String category) {}

record CreatedFile(String id, String state) {}

interface FileUploadService {
    // Phải kiểm tra ACL/quota, loại nội dung, kích thước thực,
    // metadata và scan/policy trước khi cam kết state READY.
    CreatedFile create(
            Authentication caller,
            FileMetadata metadata,
            MultipartFile content);
}

@RestController
@RequestMapping("/api/files")
class FileUploadController {
    private final FileUploadService uploads;

    FileUploadController(FileUploadService uploads) {
        this.uploads = uploads;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<CreatedFile> create(
            @Valid @RequestPart("metadata") FileMetadata metadata,
            @RequestPart("file") MultipartFile file,
            Authentication caller) {

        CreatedFile created = uploads.create(caller, metadata, file);
        // Ví dụ chỉ trả 201 khi resource đã được tạo và phản hồi
        // phản ánh đúng trạng thái thực tế (READY hoặc PENDING_SCAN).
        return ResponseEntity.created(
                URI.create("/api/files/" + created.id()))
                .body(created);
    }
}
~~~

**Điểm kỹ thuật:** part metadata phải có Content-Type: application/json để converter giải mã JSON; file part nhận qua MultipartFile. **@Valid** áp dụng ràng buộc DTO metadata. File không rỗng, media type, số bytes thực, scan, quyền và quota phải được kiểm tra riêng — annotation của DTO không xử lý những điều đó.

Nếu service chỉ xếp hàng một request và **chưa tạo resource**, có thể chọn 202 với URI operation. Nếu đã tạo resource ở trạng thái PENDING_SCAN, 201 cùng state đó cũng hợp lệ khi được công bố rõ; client không được hiểu 201 đồng nghĩa bytes đã an toàn để tải xuống.

### 9.2. PUT bytes trực tiếp

~~~java
// Fragment trong controller đã inject FileContentWriter writer;
// dùng imports tương ứng của Spring MVC và jakarta.servlet.
@PutMapping(path = "/api/files/{id}/content",
        consumes = {"application/octet-stream", "image/png", "image/jpeg"})
ResponseEntity<Void> replace(
        @PathVariable String id,
        @RequestHeader(HttpHeaders.CONTENT_TYPE) String mediaType,
        @RequestHeader(name = HttpHeaders.IF_MATCH, required = false)
        String ifMatch,
        HttpServletRequest request, Authentication caller)
        throws IOException {
    writer.replace(id, caller, request.getInputStream(), mediaType,
            ifMatch, request.getContentLengthLong());
    return ResponseEntity.noContent().build();
}
~~~

FileContentWriter là dịch vụ của ứng dụng, phải kiểm tra quyền/tenant, loại nội dung, kích thước và strong ETag **nguyên tử với thao tác thay thế**, ghi staging rồi commit. Thiếu If-Match khi bắt buộc có thể trả 428; mismatch trả 412. **Content-Length có thể là -1**, nên phải đếm bytes lúc đọc; không công bố file đang ghi dở.

### 9.3. GET bytes bằng Resource

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

record DownloadFile(
        Resource resource,
        String mediaType,
        String displayFileName,
        long byteLength) {}

interface AuthorizedFileReader {
    // Phải kiểm tra resource READY và ACL/tenant hiện hành.
    DownloadFile open(String fileId, Authentication caller);
}

@RestController
class FileContentReadController {
    private final AuthorizedFileReader reader;

    FileContentReadController(AuthorizedFileReader reader) {
        this.reader = reader;
    }

    @GetMapping("/api/files/{id}/content")
    ResponseEntity<Resource> download(
            @PathVariable String id, Authentication caller) {

        DownloadFile file = reader.open(id, caller);
        String disposition = ContentDisposition.attachment()
                .filename(file.displayFileName(), StandardCharsets.UTF_8)
                .build().toString();

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(file.mediaType()))
                .contentLength(file.byteLength())
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .body(file.resource());
    }
}
~~~

Ứng dụng cần bảo đảm Resource phù hợp cơ chế streaming của Spring; **InputStreamResource một-lần-đọc** không có khả năng seek tùy ý và có thể có giới hạn khi xử lý contentLength/range. Ví dụ **không tự hỗ trợ Range/206**, ETag hoặc signed download: các tính năng ấy cần adapter/storage và kiểm thử riêng. MediaType phải đến từ **metadata đã xác minh**, không chuyển thẳng giá trị tùy ý của client; display filename cũng phải được chuẩn hóa.

## 10. Ghi hợp đồng trong OpenAPI

Ví dụ OpenAPI 3.0.3 rút gọn; schema binary dùng type: string, format: binary theo quy ước của phiên bản này:

~~~yaml
openapi: 3.0.3
info:
  title: Files API
  version: 1.0.0
paths:
  /api/files:
    post:
      summary: Create a file with JSON metadata
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required: [metadata, file]
              properties:
                metadata:
                  $ref: '#/components/schemas/FileMetadata'
                file:
                  type: string
                  format: binary
            encoding:
              metadata:
                contentType: application/json
      responses:
        '201':
          description: File resource created; check state before download
          headers:
            Location:
              schema:
                type: string
        '413':
          description: Content Too Large
        '415':
          description: Unsupported Media Type
  /api/files/{id}/content:
    get:
      summary: Download authorized file bytes
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Full file representation
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
        '404':
          description: Not found or deliberately hidden
components:
  schemas:
    FileMetadata:
      type: object
      required: [title, category]
      properties:
        title:
          type: string
        category:
          type: string
~~~

Trong API thật cần thêm PUT raw binary (requestBody application/octet-stream với schema format: binary; If-Match; response 204/412), securitySchemes, size limits, 401/403/202/409/422, metadata schema, Range/206 nếu hỗ trợ và idempotency. **OpenAPI diễn đạt hợp đồng, không tự chặn tệp độc hại hay thực thi ACL.**

## 11. Kiểm thử theo tình huống lỗi

| Kịch bản | Kiểm chứng |
|---|---|
| Multipart metadata JSON và file hợp lệ | 201, Location, đúng mediaType/size, có resource ID |
| Metadata sai hoặc thiếu part file | 400/422 theo contract, không tạo resource READY |
| MIME khai PNG nhưng nội dung không phải ảnh | Bị từ chối/quarantine theo policy, không phát tệp như ảnh tin cậy |
| File lớn hơn giới hạn; stream không có Content-Length | 413 và cleanup object tạm; không tràn RAM |
| Client ngắt kết nối giữa upload | Không publish file chưa đủ bytes; cleanup hoặc tiếp tục theo session |
| User tenant B đoán được file ID tenant A | 403/404 theo chính sách; không tải được bytes |
| Tệp đang PENDING_SCAN hoặc REJECTED | Không tải content trái policy |
| PUT cùng If-Match cũ sau update | 412; không ghi đè phiên bản mới |
| GET content với Range hợp lệ/không hợp lệ | 206/416 **chỉ nếu API công bố hỗ trợ** |
| Tải file có filename chứa dấu /, CRLF, Unicode | Không path traversal/header injection |
| Retry POST sau mất response 201 | Không tạo file trùng nếu contract có idempotency |
| Link đã ký hết hạn hoặc bị dùng sai object/method | Storage từ chối; không vượt ACL |

Ví dụ test controller multipart bằng MockMvc (giả định đã cấu hình service giả lập và security test phù hợp):

~~~java
MockMultipartFile metadata = new MockMultipartFile(
    "metadata", "", "application/json",
    "{\"title\":\"Biên nhận\",\"category\":\"invoice\"}"
        .getBytes(StandardCharsets.UTF_8));
MockMultipartFile file = new MockMultipartFile(
    "file", "receipt.pdf", "application/pdf", validPdfFixtureBytes());

mockMvc.perform(multipart("/api/files")
        .file(metadata)
        .file(file))
    .andExpect(status().isCreated())
    .andExpect(jsonPath("$.state").value("READY"));
~~~

Đoạn trên là **test fragment**: cần import MockMultipartFile, multipart, status/jsonPath, tạo fixture PDF hợp lệ và cấu hình authentication. Nếu service thực quét bất đồng bộ, expected state có thể là PENDING_SCAN thay vì READY. **Đừng chỉ test status:** kiểm tra quyền, bytes/hash, số lần ghi storage, cleanup sau lỗi, memory peak và gateway limits bằng integration test.

## 12. Bài tập và đáp án gợi ý

**Bài 1.** Một ứng dụng thay ảnh đại diện, không có metadata mới. Nên chọn gì? **Gợi ý:** PUT bytes trực tiếp đến URI đã biết, media type image/png hoặc image/jpeg, If-Match nếu cần bảo vệ cập nhật đồng thời; GET content là bytes.

**Bài 2.** Biểu mẫu gửi invoice PDF cùng title và category. Nên chọn gì? **Gợi ý:** POST multipart/form-data, một part metadata application/json và một part file application/pdf; tạo resource ID và Location.

**Bài 3.** Tệp video 5 GB phải tiếp tục upload sau mất mạng. Multipart một lần có đủ không? **Gợi ý:** Không tự có resumability; chọn upload session/multipart object storage có part IDs, checksum, complete và trạng thái scan trước READY.

**Bài 4.** Một PDF riêng tư được tải qua URL đoán được. Chỉ cần dùng UUID khó đoán? **Gợi ý:** Không; cần kiểm tra tenant/ACL cho GET, hạn chế link đã ký, cache policy, MIME/header an toàn và audit.

## 13. Checklist và kết luận

- [ ] Đã tách rõ **định dạng truyền bytes** khỏi **identity/vòng đời tài nguyên tệp**?
- [ ] Đã chọn raw body, multipart hay upload session theo metadata, kích thước và khả năng retry?
- [ ] Contract công bố method, Content-Type, response status, Location, error và size limits?
- [ ] Có auth/ACL, quota, MIME inspection, filename normalization, quarantine/scan và integrity check?
- [ ] Không giữ toàn bộ file lớn trong heap; đã kiểm tra proxy, parser, disk tạm và object storage?
- [ ] Tệp chưa đủ bytes/chưa scan không bị công bố READY?
- [ ] Download có Content-Disposition/nosniff/cache policy phù hợp; Range chỉ quảng bá khi thật sự hỗ trợ?
- [ ] PUT/POST retry có version/idempotency và cleanup cho các cửa sổ lỗi?
- [ ] OpenAPI và test bao phủ cả happy path, lỗi tải dở, vượt hạn mức và truy cập chéo tenant?

**Kết luận:** Chọn **body nhị phân** khi cần truyền một representation bytes đơn giản; chọn **multipart/form-data** khi cần gửi nhiều part trong cùng request; chọn **tài nguyên tệp có URI/ID riêng** khi file cần quyền, metadata, trạng thái, tải lại hoặc quản lý vòng đời. Với tệp lớn, hãy bổ sung streaming hoặc upload session theo nhu cầu, cùng kiểm soát bảo mật, khả năng phục hồi và kiểm thử sát hạ tầng thật.
