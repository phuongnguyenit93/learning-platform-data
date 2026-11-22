# Nhóm mã 2xx, 3xx, 4xx, 5xx và phân biệt với lỗi kết nối trong HTTP

**Chủ đề:** Java Advance - networking  
**Nhóm kiến thức:** Nền tảng HTTP

Khi client Java gọi một HTTP API, có **hai loại kết quả hoàn toàn khác nhau**:

1. **Nhận được HTTP response** với **status code** như **200**, **302**, **404**, **429** hoặc **503**. Nghĩa là ít nhất một thành phần HTTP (origin server, reverse proxy, API gateway, cache...) đã phát sinh response mà client nhận và xử lý được. Response có thể báo thành công, chuyển hướng hoặc thất bại ở tầng HTTP/ứng dụng.
2. **Không thu được một HTTP response hoàn chỉnh theo API client đang dùng**, do DNS, TCP connect, TLS handshake, timeout, kết nối bị đóng, protocol error, hủy request hoặc lỗi đọc body. Trường hợp này thường được báo bằng **exception** hoặc một future hoàn thành ngoại lệ, **không có status code HTTP đáng tin để phân loại**.

**HTTP 404 và TCP Connection refused không giống nhau**. **HTTP 504 Gateway Timeout và HttpTimeoutException cũng không giống nhau**. Đây là ranh giới quan trọng nhất khi thiết kế retry, quan sát vận hành, xử lý lỗi và hiển thị thông báo tới người dùng.

Bài học trình bày ý nghĩa của **2xx / 3xx / 4xx / 5xx**, các trường hợp dễ nhầm như **204**, **304**, **401/403**, **408/429**, **502/503/504**, và ví dụ Java 17 dùng **HttpClient** cùng một HTTP server chạy trên loopback để tự kiểm chứng.

## 1. Status code chỉ tồn tại khi có HTTP response

Một response HTTP/1.1 minh họa:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2
Content-Length: 26

{"error":"maintenance"}
~~~

Ở đây, **503** là **HTTP status code** (được gửi bởi một server/proxy/gateway). **Retry-After: 2** gợi ý đợi ít nhất 2 giây trước khi thử lại trong ngữ cảnh phù hợp; nó **không** có nghĩa TCP đã không kết nối được. HTTP/2 và HTTP/3 mã hóa phản hồi theo cơ chế khác HTTP/1.1 (ví dụ HTTP/2 có trường **:status**), nhưng ý nghĩa mã 2xx/3xx/4xx/5xx vẫn dựa trên HTTP semantics.

Đặt các lớp cạnh nhau:

~~~text
Client Java
   │
   ├── DNS lookup ── không resolve được ──> lỗi DNS/IOException
   │
   ├── TCP connect ── refused/timeout ────> lỗi kết nối/IOException
   │
   ├── TLS handshake (HTTPS)
   │       └── cert/hostname/protocol lỗi -> SSLException
   │
   ├── Gửi HTTP request
   │
   ├── Nhận HTTP response headers
   │       ├── status 2xx: thuộc nhóm Success
   │       ├── status 3xx: thuộc nhóm Redirection
   │       ├── status 4xx: thuộc nhóm Client Error
   │       └── status 5xx: thuộc nhóm Server Error
   │
   └── Nhận HTTP body
           └── connection đứt/đọc lỗi -> I/O exception có thể
                xảy ra dù đã thấy status ở tầng thấp
~~~

**Điểm tinh tế:** Một HTTP client gọi API đồng bộ **send(...)** có thể gặp **IOException trong quá trình nhận body**, dù bên dưới đã nhận được response headers. Khi **send(...)** ném exception, caller không nhận được đối tượng **HttpResponse** hoàn chỉnh từ lần gọi đó để chắc chắn xử lý status. Không nên kết luận “server không phản hồi gì” trong mọi trường hợp exception; việc request đã được server nhận/xử lý hay chưa có thể **không biết**.

### Năm nhóm status theo chữ số đầu

| Nhóm | Tên lớp HTTP | Diễn giải ở mức giao thức | Trường hợp ứng dụng |
| --- | --- | --- | --- |
| **1xx** | Informational | Phản hồi thông tin/trung gian; thường chưa phải response cuối | 100 Continue, 101 Switching Protocols, 103 Early Hints |
| **2xx** | Successful | HTTP request đã được nhận, hiểu và xử lý thành công theo ý nghĩa của mã | 200, 201, 202, 204, 206 |
| **3xx** | Redirection | Cần hoặc có thể thực hiện bước tiếp theo để hoàn thành yêu cầu/điều kiện | 301, 302, 303, 304, 307, 308 |
| **4xx** | Client Error | Request có vấn đề hoặc không thể được đáp ứng theo điều kiện của client/request | 400, 401, 403, 404, 409, 412, 429 |
| **5xx** | Server Error | Server/gateway không thực hiện được yêu cầu hợp lệ hoặc gặp vấn đề xử lý | 500, 501, 502, 503, 504 |

Status code là **số ba chữ số**. Ví dụ trong Java:

~~~java
int status = response.statusCode(); // response là HttpResponse<?> đã nhận.
int family = status / 100;           // 2, 3, 4, 5 (hoặc 1).
boolean httpSuccessClass = family == 2;
~~~

Đây là **snippet** cần biến **response**; nó **không chạy độc lập**. Phép chia cho 100 phân nhóm, không đánh giá liệu nghiệp vụ có hoàn tất. Danh sách status của HTTP có thể được mở rộng theo chuẩn và ứng dụng có thể dùng mã được đăng ký khác; đừng chỉ viết **switch** cho 200/404/500 rồi mặc định mọi mã còn lại là transport failure.

## 2. Nhóm 2xx: thành công ở tầng HTTP, nhưng nghĩa phụ thuộc từng mã

Đừng đồng nhất mọi **2xx** thành “mọi việc nghiệp vụ đã hoàn tất”. Hãy đọc **method, status, headers, body và API contract**.

| Mã | Tên | Ý nghĩa chính | Cách xử lý |
| --- | --- | --- | --- |
| **200 OK** | OK | Request đã thành công theo semantics của method; thường có representation/body | Parse nội dung theo Content-Type và contract; GET/POST có thể mang ý nghĩa khác nhau |
| **201 Created** | Created | Request đã tạo một hoặc nhiều tài nguyên | Xem **Location** nếu server cung cấp địa chỉ tài nguyên mới |
| **202 Accepted** | Accepted | Đã chấp nhận để xử lý, **chưa bảo đảm xử lý đã hoàn tất** | Theo dõi job/status URL hoặc callback theo contract |
| **204 No Content** | No Content | Request thành công, **không có response content** | Đừng ép parse JSON từ body rỗng |
| **206 Partial Content** | Partial Content | Server trả một phần representation theo range request phù hợp | Kiểm tra **Content-Range**, ghép theo protocol, không xem là toàn bộ file |
| **207 Multi-Status** | Multi-Status (WebDAV) | Có thể chứa trạng thái của nhiều thao tác/tài nguyên | Đọc cấu trúc body theo giao thức WebDAV; một 2xx không bảo đảm mọi phần thành công |

### 200 OK không phải luôn là “business success”

Một server có thể trả **200 OK** kèm JSON như:

~~~json
{
  "success": false,
  "errorCode": "OUT_OF_STOCK",
  "message": "Item cannot be reserved"
}
~~~

Đây vẫn là **HTTP 200** ở mức status. Ứng dụng muốn xác định có được đặt hàng hay không phải **đọc contract của body**. Có những API cố tình biểu diễn lỗi domain bằng 200; điều này có thể làm việc quan sát status khó hơn, nhưng client vẫn phải xử lý đúng contract thực tế.

Mặt khác, server có thể trả **201 Created** mà client phải dùng **Location** để tìm tài nguyên mới, hoặc trả **202 Accepted** khi một job mới chỉ vào queue. Không nên thông báo “xử lý hoàn tất” ngay khi thấy 202, trừ khi contract xác định rõ.

### 204: thành công không có body

Với **204 No Content**, response không chứa content, bất kể client đang chờ JSON. Một lỗi phổ biến:

~~~java
// Pseudocode lỗi: API trả 204 nhưng code vẫn bắt buộc parse JSON.
if (response.statusCode() == 204) {
    parseJson(response.body()); // Không có JSON để parse.
}
~~~

Thay vào đó, khi 204 là kết quả hợp lệ, xử lý nhánh **không body** rồi cập nhật state ứng dụng theo contract. **HEAD** cũng có trường hợp trả response headers mà không có response body; do đó “không có body” không đồng nghĩa exception.

### 206: thành công một phần

**206 Partial Content** thường gặp khi tải xuống theo **Range**. Nó khác với **200** trả toàn bộ representation. Khi tải file lớn theo từng phần, phải kiểm tra **Content-Range**, độ dài và identity của representation (ví dụ ETag/If-Range) để tránh ghép sai dữ liệu. 206 không phải một loại “lỗi kết nối xảy ra giữa chừng”; nó là HTTP response có chủ đích.

## 3. Nhóm 3xx: chuyển hướng hoặc xử lý điều kiện, không phải mọi mã đều “đi URL khác”

| Mã | Tên | Ý nghĩa và lưu ý |
| --- | --- | --- |
| **300 Multiple Choices** | Multiple Choices | Có nhiều representation/lựa chọn; client có thể cần chọn |
| **301 Moved Permanently** | Moved Permanently | Resource có địa chỉ lâu dài khác; nhiều client cache redirect |
| **302 Found** | Found | Resource tạm thời nằm ở URI khác; lịch sử client có thể đổi POST thành GET trong một số trường hợp |
| **303 See Other** | See Other | Yêu cầu client truy xuất tài nguyên khác, thường bằng GET (ngoại trừ HEAD theo quy tắc) |
| **304 Not Modified** | Not Modified | Trả lời conditional request: representation cache còn hợp lệ; **không có response body** và **không phải chỉ dẫn đi URL khác** |
| **307 Temporary Redirect** | Temporary Redirect | Redirect tạm thời, client **không được đổi method** khi tự động follow |
| **308 Permanent Redirect** | Permanent Redirect | Redirect lâu dài, client **không được đổi method** khi tự động follow |

### Location và redirect policy

Ví dụ:

~~~http
HTTP/1.1 302 Found
Location: /v2/catalog
Content-Length: 0
~~~

Client có thể:

1. Trả raw **302** cho ứng dụng để ứng dụng tự quyết.
2. Tự động follow redirect theo **redirect policy** rồi trả cho ứng dụng **response cuối**, ví dụ **200**.
3. Dừng vì quá nhiều redirect, scheme bị chặn, redirect loop, ràng buộc bảo mật hoặc lỗi mạng khi truy cập đích mới.

**Java HttpClient** cung cấp **HttpClient.Redirect.NEVER**, **NORMAL**, **ALWAYS**. Với **NEVER**, ứng dụng thấy status 302 nếu server trả 302; với **NORMAL**, client có thể tự follow những redirect cho phép và trả status cuối. **NORMAL** không tự động cho phép downgrade từ HTTPS sang HTTP. Không dùng **ALWAYS** mà bỏ qua chính sách credential/security; redirect qua domain khác cần đánh giá token, cookie và thông tin nhạy cảm.

**Không bảo đảm** mọi 301/302 redirect đều giữ nguyên method/body khi client tự follow: quy tắc lịch sử cho phép một số chuyển đổi POST → GET. **307/308** được tạo ra để giữ method khi follow. Đối với request có side effect, phải hiểu chính sách client và server, không gửi lại body tùy tiện.

### 304 Not Modified không phải lỗi và cũng không phải response có body

Một client dùng conditional GET:

~~~http
GET /logo.png HTTP/1.1
If-None-Match: "v7"
~~~

Server có thể trả **304 Not Modified**, nghĩa là representation cache đang giữ vẫn phù hợp. Client/browser có thể dùng lại nội dung cached theo quy tắc caching. **304 không phải “server ngừng hoạt động”**; một client không có cache hoặc không xử lý conditional requests đúng có thể gặp kết quả không mong đợi. Trong Java **HttpResponse**, nhận 304 không tự cung cấp representation đã cached trừ khi tầng cache tương ứng xử lý.

**Không** tự parse body JSON đối với 304; đây là mã không chứa response content theo HTTP semantics.

### Chuyển hướng thất bại trên đường đi vẫn là lỗi kết nối

Nếu server A trả 302 trỏ sang server B nhưng DNS của B thất bại, **client đang tự follow** có thể ném exception. Điều đó **khác** việc server A trả một HTTP 5xx. Để phân tích chính xác, cần log redirect chain/target và loại lỗi của request ở hop bị thất bại, không áp đặt một mã status duy nhất cho toàn bộ hành trình.

## 4. Nhóm 4xx: request/client có vấn đề hoặc không đáp ứng được điều kiện

“Client Error” trong tên nhóm **không** có nghĩa lúc nào cũng là lỗi lập trình ở phía client. Có thể là quyền truy cập, trạng thái tài nguyên, throttling, validation hoặc server áp dụng chính sách rõ ràng.

| Mã | Tên | Khi nào gặp | Hành động phù hợp |
| --- | --- | --- | --- |
| **400** | Bad Request | Request syntax, framing hoặc một số yêu cầu không hợp lệ | Sửa request, schema hoặc serialization |
| **401** | Unauthorized | Chưa có thông tin xác thực hợp lệ cho resource | Xem **WWW-Authenticate**, refresh/login đúng protocol |
| **403** | Forbidden | Server hiểu request nhưng từ chối thực hiện | Kiểm tra quyền, policy, tenant, không retry mù |
| **404** | Not Found | Resource không có ở URI này hoặc server không muốn tiết lộ nó | Kiểm tra path, ID, version; có API xem 404 là outcome hợp lệ |
| **405** | Method Not Allowed | Method không được hỗ trợ cho resource | Xem **Allow** header khi phù hợp; đổi method theo contract |
| **408** | Request Timeout | Server không nhận được complete request trong thời gian cho phép | Khác với timeout do client tự báo; đánh giá retry an toàn |
| **409** | Conflict | Trạng thái hiện tại xung đột thao tác | Refresh version/trạng thái rồi giải quyết conflict |
| **410** | Gone | Resource không còn, có chủ đích | Không lặp request vô hạn; cập nhật reference |
| **412** | Precondition Failed | Điều kiện như If-Match không thỏa | Đọc lại ETag/version, xử lý optimistic concurrency |
| **413** | Content Too Large | Request content vượt giới hạn được chấp nhận | Điều chỉnh payload/chunking nếu API hỗ trợ |
| **415** | Unsupported Media Type | Content-Type/representation không phù hợp | Gửi đúng định dạng được API hỗ trợ |
| **422** | Unprocessable Content | Syntax/content type hiểu được nhưng nội dung không xử lý được | Xem lỗi validation nghiệp vụ |
| **425** | Too Early | Server không muốn xử lý request có nguy cơ replay (ngữ cảnh TLS early data) | Thử lại sau handshake đầy đủ theo policy an toàn |
| **429** | Too Many Requests | Quá nhiều requests theo chính sách rate limit | Tôn trọng Retry-After nếu có, giảm tốc, backoff và quota |

### 401 khác 403

- **401**: thường là chưa có credential hợp lệ hoặc cần xác thực lại; response thường mang **WWW-Authenticate** theo HTTP authentication.
- **403**: server từ chối thực hiện ngay cả khi đã hiểu request; không đồng nghĩa gửi lại cùng credential nhiều lần sẽ thành công.

Một API có thể dùng 404 để **không tiết lộ tài nguyên mà caller không có quyền biết**. Vì vậy status chỉ nói được những gì server quyết định công bố qua HTTP; không phải bằng chứng về trạng thái nội bộ tuyệt đối.

### 409, 412 không giống kết nối hỏng

Ví dụ optimistic locking: client cập nhật tài nguyên với **If-Match: "v3"**, server đã ở version **v4** và trả **412**. TCP và TLS có thể hoàn toàn khỏe. **Retry ngay cùng payload/ETag** sẽ lặp lỗi. Phải đọc lại resource, merge hoặc báo conflict cho người dùng theo yêu cầu nghiệp vụ.

### 408 và 429 có liên quan timeout/rate limit nhưng vẫn là HTTP status

**408 Request Timeout** là response của server, phản ánh server không nhận complete request đủ nhanh theo điều kiện của nó. **429 Too Many Requests** phản ánh rate limiting. Cả hai là 4xx và đều có thể xử lý theo chính sách retry, nhưng **không** đồng nghĩa một **SocketTimeoutException** hoặc **HttpTimeoutException** đã xảy ra ở client.

**Retry-After** là header được thiết kế để truyền thời gian đợi; giá trị có thể là **số giây không âm** hoặc một **HTTP-date**. Nó thường xuất hiện ở 429/503 và có thể xuất hiện theo semantics khác. **Không** giả định header luôn có, luôn là số hoặc mang số mili giây.

## 5. Nhóm 5xx: server hoặc gateway gặp vấn đề khi xử lý

| Mã | Tên | Ý nghĩa gần đúng | Đừng nhầm với |
| --- | --- | --- | --- |
| **500** | Internal Server Error | Server gặp trạng thái lỗi không xử lý được yêu cầu | “TCP hỏng”: ở đây vẫn đã nhận HTTP response |
| **501** | Not Implemented | Server không hỗ trợ chức năng/method cần để thực hiện | 405 Method Not Allowed ở một resource cụ thể |
| **502** | Bad Gateway | Proxy/gateway nhận phản hồi không hợp lệ từ upstream | Client trực tiếp gặp Connection refused |
| **503** | Service Unavailable | Server tạm không phục vụ do quá tải, bảo trì hoặc nguyên nhân tương tự | 429 thường là throttling theo request/client policy |
| **504** | Gateway Timeout | Proxy/gateway không nhận kịp response cần thiết từ upstream | **HttpTimeoutException** do client tự phát hiện |
| **505** | HTTP Version Not Supported | Server không hỗ trợ phiên bản HTTP request | Lỗi TLS protocol version khi handshake |

**5xx không nhất thiết phát ra từ origin service.** Reverse proxy/API gateway/CDN có thể tạo **502**, **503** hoặc **504**, kể cả khi ứng dụng phía sau không gửi response. Khi debug cần phân biệt status do gateway phát sinh với status do backend trả, dựa trên log/trace IDs và metric ở từng hop, không chỉ nhìn body.

**5xx không chứng minh request chưa tạo side effect.** Ví dụ một POST tạo giao dịch đã commit vào database, nhưng server lỗi khi xây response và trả **500**; hoặc kết nối bị đứt sau commit. Nếu client retry không có idempotency key, có thể tạo giao dịch trùng. “Server Error” mô tả response HTTP, **không** là chứng nhận rollback.

### 502 và 504 dễ bị dùng sai khi phân loại

- **502 Bad Gateway**: gateway/proxy nhận response không hợp lệ từ upstream khi cần phục vụ request.
- **504 Gateway Timeout**: gateway/proxy không nhận kịp response thích hợp từ upstream.
- **Client HttpTimeoutException**: **chính HTTP client** vượt timeout của nó; có thể gateway chưa trả 504 hoặc request đã tới backend.
- **TCP connect timeout** từ client tới gateway: client chưa lập được kết nối; không tự biến thành 504.

Nếu có nhiều proxy/hop, một timeout ở tầng này có thể được tầng kia **chuyển thành một 504**. **Status 504 bạn nhận** là kết quả của hệ thống HTTP trung gian, còn exception timeout là đánh giá tại client theo chính deadline của nó.

### 503 và Retry-After

**503 Service Unavailable** thường có tính tạm thời. Nếu server có **Retry-After**, client có thể lên lịch thử lại **nếu** method/operation phù hợp và deadline cho phép. Nếu không có header, dùng backoff+jitter và giới hạn attempts. Không retry đồng thời tất cả clients ngay khi nhận 503, vì dễ làm hệ thống đang quá tải càng tệ.

## 6. Phân biệt trực tiếp: HTTP status và lỗi kết nối/I/O

Bảng này quyết định bạn phải ghi log và xử lý theo hai nhánh khác nhau:

| Hiện tượng | Có HTTP status code từ lần gọi này? | Ví dụ Java hoặc network | Ý nghĩa |
| --- | --- | --- | --- |
| HTTP 200 | Có: **200** | **response.statusCode() == 200** | HTTP success theo semantics |
| HTTP 404 | Có: **404** | **response.statusCode() == 404** | Server không cung cấp resource ở URI đó |
| HTTP 429 | Có: **429** | **response.statusCode() == 429** | Rate limit, có thể có Retry-After |
| HTTP 503 | Có: **503** | **response.statusCode() == 503** | Server/gateway đã trả Service Unavailable |
| HTTP 504 | Có: **504** | **response.statusCode() == 504** | Gateway báo upstream timeout |
| DNS thất bại | Không có status HTTP đáng tin từ request | **UnknownHostException** hoặc IOException có cause tương ứng | Chưa tìm được đích (hoặc lỗi DNS resolver) |
| TCP Connection refused | Không | **ConnectException** / IOException | Không kết nối được tới IP:port; listener không nhận hoặc bị policy từ chối |
| TCP connect timeout | Không | **HttpConnectTimeoutException** trên HttpClient tùy tình huống | Quá hạn khi thiết lập connection |
| TLS handshake/hostname failure | Không có response HTTP thông thường | **SSLHandshakeException**, **SSLException** | Không xây/xác minh được kênh TLS hợp lệ |
| HTTP request timeout phía client | Không có **HttpResponse** hoàn chỉnh do send trả về | **HttpTimeoutException** | Client chủ động hết hạn đợi theo request timeout |
| Server đóng kết nối giữa response | Có thể đã có headers ở tầng mạng, nhưng API send vẫn có thể ném exception | **IOException**, EOF/protocol exception | Không được suy ra server chưa xử lý request |
| Thread bị ngắt | Không có response trả về từ lần gọi send bị ngắt | **InterruptedException** | Client-side cancellation/interruption; cần khôi phục interrupt flag |
| Future async thất bại/hủy | Không có HttpResponse thành công từ future đó | **CompletionException**, **CancellationException**, cause liên quan | Phân loại theo cause, không theo status giả |

**Lưu ý về kiểu exception:** Java HTTP client có thể **wrap** nguyên nhân, đặc biệt trong asynchronous pipeline; các subclass/causes cụ thể phụ thuộc thời điểm lỗi, JDK và đường đi. Không dùng tên exception trong bảng như một cam kết rằng mọi failure trong loại đó sẽ luôn trả chính xác một class nhất định.

### Tại sao “status = 0” không phải cách tốt để biểu diễn network error?

Một số framework tự dùng số **0**, **-1** hoặc mã riêng để thể hiện “không có HTTP response”. Đây chỉ là **quy ước nội bộ của framework**, không phải một HTTP status code thuộc nhóm 2xx/3xx/4xx/5xx. Nếu biến mọi exception thành **status 500**, hệ thống quan sát mất khả năng phân biệt “server trả 500” với “client không connect được”.

Mô hình rõ hơn:

~~~text
HttpOutcome
 ├─ ResponseReceived
 │    ├─ status: 200 / 404 / 503 / ...
 │    ├─ headers, body, final URI
 │    └─ response timing
 └─ TransportOrClientFailure
      ├─ phase: dns/connect/tls/request/response/cancel (nếu xác định được)
      ├─ exception / cause
      └─ liệu request đã đến server? có thể UNKNOWN
~~~

Không phải lúc nào cũng phân biệt được phase chính xác từ exception. Những thông tin như hostname, request ID, redirect target, phase trace, timeout policy và network logs giúp kết luận vững hơn.

## 7. 408, 429, 503, 504 và timeout phía client: cùng “chậm” nhưng khác bản chất

| Kết quả | Ai báo vấn đề? | Cái gì thực sự đã xảy ra ở mức quan sát? | Retry? |
| --- | --- | --- | --- |
| **408 HTTP** | HTTP server | Server gửi status vì quá lâu để nhận request hoàn chỉnh | Xét tính idempotent và trạng thái request |
| **429 HTTP** | Server/gateway/rate limiter | Server trả status do quota/rate limit | Thường backoff và tôn trọng Retry-After |
| **503 HTTP** | Server/gateway | Server/gateway trả status tạm không phục vụ | Có thể retry có kiểm soát |
| **504 HTTP** | HTTP gateway | Gateway trả status không nhận kịp upstream | Có thể retry, nhưng kiểm tra nguy cơ duplicate |
| **HttpConnectTimeoutException** | Java client | Quá hạn thiết lập HTTP connection | Kiểm tra endpoint/network và retry có giới hạn |
| **HttpTimeoutException** | Java client | Request vượt timeout đã định; có thể ở nhiều giai đoạn | Không chắc server chưa xử lý |
| **SSLHandshakeException** | Java TLS layer | TLS handshake xác thực/thỏa thuận thất bại | Không retry mù khi cấu hình trust/hostname sai |

Ví dụ một request **POST /payments** có thể đã đến server và ghi database, nhưng client **HttpTimeoutException** khi chờ response. Retry ngay có thể tạo thanh toán thứ hai. Trong trường hợp này, **idempotency key + tra cứu trạng thái giao dịch** quan trọng hơn việc chỉ chọn backoff.

**Phân biệt timeout cấu hình Java:**

- **HttpClient.Builder.connectTimeout(Duration)** giới hạn thời gian kết nối khi cần tạo kết nối mới; không phải timeout tuyệt đối cho toàn bộ request/response và có thể không áp dụng khi dùng lại connection đã tồn tại.
- **HttpRequest.Builder.timeout(Duration)** đặt hạn cho request/response theo API; nếu vượt, **HttpTimeoutException** (hoặc subclass) có thể được ném.
- **Response Timeout** ở một số framework khác có thể là hạn đọc từng byte hoặc toàn body; **đừng** giả định semantics giống HttpClient Java chỉ vì cùng gọi là timeout.

Chỉ nhìn “elapsed 10s” không đủ để biết DNS, TCP, TLS, backend hay đọc body đang tốn thời gian. Muốn kết luận, cần telemetry theo phase và một request/trace ID để nối với log server.

## 8. Java HttpClient 17+: đọc status mà không biến 4xx/5xx thành exception

Với **java.net.http.HttpClient**, cách đồng bộ thường dùng:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items/42"))
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

int code = response.statusCode();
if (code >= 200 && code < 300) {
    // Thành công theo HTTP class; cần đánh giá method + API contract.
} else if (code >= 300 && code < 400) {
    // Redirect hoặc conditional semantics (ví dụ 304).
} else if (code >= 400 && code < 500) {
    // Client/request/permission/rate-limit outcome ở HTTP layer.
} else if (code >= 500 && code < 600) {
    // Server/gateway HTTP outcome.
}
~~~

Đây là **snippet** cần import **java.net.URI**, **java.net.http.HttpClient/HttpRequest/HttpResponse**, **java.time.Duration** và biến **client** tạo trước; nó **không** là chương trình độc lập. **send(...)** không tự ném exception chỉ vì status là 404 hoặc 503. Những status đó nằm trong **HttpResponse** nếu response được nhận/đọc thành công theo BodyHandler.

**Khác biệt với HttpURLConnection cũ:** **HttpURLConnection.getInputStream()** có thể ném IOException khi server trả HTTP error status, và code cần xử lý **getResponseCode() / getErrorStream()**. Không suy từ behavior của API cũ rằng **HttpClient.send(...)** cũng ném exception mặc định cho mọi 4xx/5xx. Khi dùng thư viện HTTP khác, phải đọc contract thư viện: có thư viện chuyển non-2xx thành exception do thiết kế.

### Bắt exception theo loại phù hợp

~~~java
// Snippet: client và request đã được tạo; catch theo thứ tự subclass trước.
try {
    HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    System.out.println("HTTP status: " + response.statusCode());
} catch (java.net.http.HttpConnectTimeoutException e) {
    // Connect timeout; không có response status từ lần send này.
} catch (java.net.http.HttpTimeoutException e) {
    // Request timeout; không khẳng định server chưa xử lý request.
} catch (javax.net.ssl.SSLHandshakeException e) {
    // TLS certificate, hostname, protocol hoặc trust failure...
} catch (java.io.IOException e) {
    // DNS/connect/reset/đứt stream/protocol... tùy cause.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Tôn trọng cancellation/shutdown.
}
~~~

Đây là đoạn **minh họa error handling**, không chạy độc lập nếu thiếu biến client/request. Một lỗi DNS có thể xuất hiện qua **IOException cause chain**, không cần ép mọi lỗi về **UnknownHostException** cấp ngoài. Khi dùng **sendAsync(...)**, exception thường được truyền qua **CompletableFuture** (ví dụ **CompletionException** khi join) và cần bóc cause; cách phân loại HTTP status vs network error vẫn không đổi.

### Redirects làm thay đổi status mà application nhìn thấy

~~~java
HttpClient noRedirect = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER).build();

HttpClient withRedirect = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL).build();
~~~

Cùng request tới endpoint trả 302: **noRedirect** có thể trả **302**; **withRedirect** có thể tự gọi URI trong Location và trả **200** của đích. Đây là khác biệt **policy**, không phải hai server có HTTP semantics khác nhau. Demo kiểm chứng chính xác điều này ở phần tiếp theo.

## 9. Ví dụ Java 17+ hoàn chỉnh: nhận các nhóm mã và một timeout thật

Ví dụ dưới đây chạy **HTTP server cục bộ trên 127.0.0.1, port do OS cấp**, không cần kết nối Internet. Server tạo các endpoint đại diện cho:

- **2xx:** 200 OK, 201 Created với Location, 204 No Content.
- **3xx:** 302 Found với Location và 304 Not Modified.
- **4xx:** 400 Bad Request, 404 Not Found, 409 Conflict, 429 Too Many Requests với Retry-After.
- **5xx:** 500 Internal Server Error, 503 Service Unavailable.
- **Redirect tự động:** cùng URI 302 nhưng policy NORMAL nhận status cuối 200.
- **Lỗi không có HTTP response:** endpoint **/slow** trì hoãn xử lý quá request timeout, khiến **HttpClient.send(...)** ném **HttpTimeoutException**, thay vì trả một status 408/504.

Mọi response đã dùng **HttpResponse.statusCode()** để phân nhóm. Status codes là số **cụ thể, ổn định do server demo tạo**; timeout có thể phụ thuộc scheduling/runtime, nhưng ví dụ dùng chênh lệch lớn giữa sleep 800ms và request timeout 150ms để kiểm chứng nhánh này trong điều kiện chạy bình thường.

### Mã nguồn: HttpStatusDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpStatusDemo {
    record Example(String path, int expected) {}

    private static String family(int code) {
        return switch (code / 100) {
            case 1 -> "1xx";
            case 2 -> "2xx";
            case 3 -> "3xx";
            case 4 -> "4xx";
            case 5 -> "5xx";
            default -> "other";
        };
    }

    private static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            String path = exchange.getRequestURI().getPath();
            int code = switch (path) {
                case "/ok" -> 200;
                case "/created" -> 201;
                case "/empty" -> 204;
                case "/redirect" -> 302;
                case "/unchanged" -> 304;
                case "/bad" -> 400;
                case "/missing" -> 404;
                case "/conflict" -> 409;
                case "/rate" -> 429;
                case "/error" -> 500;
                case "/busy" -> 503;
                case "/slow" -> 200;
                default -> 404;
            };

            if (code == 201) {
                exchange.getResponseHeaders().set("Location", "/resources/42");
            }
            if (code == 302) {
                exchange.getResponseHeaders().set("Location", "/ok");
            }
            if (code == 429) {
                exchange.getResponseHeaders().set("Retry-After", "2");
            }
            if (code == 503) {
                exchange.getResponseHeaders().set("Retry-After", "1");
            }

            if (path.equals("/slow")) {
                try {
                    Thread.sleep(800);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
            if (code == 204 || code == 304 || code == 302) {
                exchange.sendResponseHeaders(code, -1);
                return;
            }

            byte[] body = ("status=" + code).getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(code, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        }
    }

    private static HttpRequest request(URI base, String path) {
        return HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(2))
                .GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        server.createContext("/", HttpStatusDemo::handle);
        server.start();
        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/");
            HttpClient noFollow = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            Example[] cases = {
                new Example("/ok", 200),
                new Example("/created", 201),
                new Example("/empty", 204),
                new Example("/redirect", 302),
                new Example("/unchanged", 304),
                new Example("/bad", 400),
                new Example("/missing", 404),
                new Example("/conflict", 409),
                new Example("/rate", 429),
                new Example("/error", 500),
                new Example("/busy", 503)
            };
            for (Example sample : cases) {
                HttpResponse<String> response = noFollow.send(
                        request(base, sample.path()),
                        HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() != sample.expected()) {
                    throw new AssertionError("Unexpected HTTP status: " + sample.path());
                }
                System.out.println(sample.path() + "="
                        + response.statusCode() + " " + family(response.statusCode()));
                if (sample.path().equals("/rate")) {
                    System.out.println("retryAfter429=" +
                            response.headers().firstValue("Retry-After").orElse("absent"));
                }
            }

            HttpClient follow = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .build();
            HttpResponse<String> redirected = follow.send(
                    request(base, "/redirect"), HttpResponse.BodyHandlers.ofString());
            System.out.println("followedRedirectStatus=" + redirected.statusCode());

            HttpRequest slow = HttpRequest.newBuilder(base.resolve("/slow"))
                    .timeout(Duration.ofMillis(150)).GET().build();
            try {
                noFollow.send(slow, HttpResponse.BodyHandlers.ofString());
                throw new AssertionError("Expected timeout");
            } catch (HttpTimeoutException expected) {
                System.out.println("timeoutWasHttpResponse=false");
                System.out.println("timeoutWasException=true");
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Về môi trường:** **com.sun.net.httpserver.HttpServer** là HTTP server phục vụ demo/test nằm trong module JDK **jdk.httpserver**, không phải server production mặc định. Trong JDK đầy đủ thông thường, chương trình có thể biên dịch trực tiếp; nếu dùng JDK/runtime bị rút gọn không chứa **jdk.httpserver**, cần cung cấp module tương ứng. **java.net.http.HttpClient** là HTTP client chuẩn từ Java 11; cú pháp record và switch expression ở đây tương thích **Java 17**.

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 HttpStatusDemo.java
java HttpStatusDemo
~~~

**Stdout của lần chạy thành công** — đã biên dịch với **--release 17** và chạy kiểm thử trên **JDK 24**:

~~~text
/ok=200 2xx
/created=201 2xx
/empty=204 2xx
/redirect=302 3xx
/unchanged=304 3xx
/bad=400 4xx
/missing=404 4xx
/conflict=409 4xx
/rate=429 4xx
retryAfter429=2
/error=500 5xx
/busy=503 5xx
followedRedirectStatus=200
timeoutWasHttpResponse=false
timeoutWasException=true
~~~

### Phân tích ý nghĩa của demo

1. **HttpServer** bind vào loopback cổng **0**, hệ điều hành cấp một cổng hiện có; client được tạo URI từ **server.getAddress().getPort()**. Không có số port cố định gây xung đột test.
2. **noFollow** nhận chính status **302**, còn **follow** tự chuyển tới **/ok** và nhận **200**. Status mà ứng dụng nhìn thấy phụ thuộc redirect policy.
3. **/empty** trả **204** mà không gửi response body. **/unchanged** trả **304**; cả hai là HTTP responses hợp lệ, không phải lỗi I/O.
4. **/rate** trả **429** và **Retry-After: 2**; client vẫn nhận bình thường dưới dạng **HttpResponse**, đọc header qua **response.headers().firstValue(...)**.
5. **/error** và **/busy** lần lượt trả **500**, **503**. **HttpClient.send(...)** không ném exception chỉ vì HTTP class là 5xx.
6. **/slow** khiến request timeout ở client trước khi HTTP response hoàn tất. **catch(HttpTimeoutException)** chứng minh đây là **exception**, không phải HTTP **408** hay **504**. Server có thể vẫn thực hiện handler bên trong, nên không được suy ra request đã bị bỏ.
7. Ví dụ dùng **GET** và response bodies rất nhỏ để tập trung vào status semantics. Khi đưa vào ứng dụng thực, nên cấu hình HTTPS, trust policy, timeout, method/idempotency, log, limits và xử lý body theo API contract.

**Không suy diễn rằng toàn bộ mạng luôn có cùng timing:** nếu máy cực kỳ quá tải hoặc môi trường test bất thường, timeout có thể biểu hiện ở thời điểm khác; ví dụ này minh họa **phân biệt đúng kiểu kết quả**, không phải benchmark độ trễ. Nếu muốn test ConnectException, dùng môi trường/network fixture kiểm soát được endpoint không lắng nghe; không dùng cách “chọn cổng trống rồi đóng” như một giả định không có race trong test production.

## 10. Quy tắc retry: đừng dùng mỗi status hoặc mỗi exception

**Retry không phải cứ 5xx thì retry, cứ 4xx thì bỏ.** Quyết định dựa trên:

1. **Phương thức và semantics:** request có an toàn/idempotent theo HTTP và **hợp đồng nghiệp vụ thực tế** không?
2. **Kết quả đã biết:** nhận được response HTTP rõ ràng hay chỉ exception? Server có thể đã làm gì?
3. **Nguyên nhân:** 429/503 có Retry-After? 502/504 từ gateway? DNS/tls lỗi cấu hình hay temporary?
4. **Deadline/cadence:** còn bao nhiêu thời gian? Số lần retry tối đa? exponential backoff + jitter?
5. **Idempotency protection:** có idempotency key, unique business ID hoặc API status inquiry để tránh duplicate?
6. **Circuit breaker/rate limit:** retry hàng loạt có thể tạo retry storm không?

### HTTP method và idempotency

| Method phổ biến | Đặc tính cơ bản | Gợi ý retry |
| --- | --- | --- |
| **GET, HEAD, OPTIONS** | Được định nghĩa là **safe** theo HTTP semantics, nên không được yêu cầu tạo side effect nghiệp vụ | Thường có thể retry khi transient failure, vẫn phải có deadline và giới hạn |
| **PUT, DELETE** | Được định nghĩa là **idempotent** về hiệu ứng dự định của method | Có thể retry theo semantics, nhưng cần xét side effects phụ và contract cụ thể |
| **POST** | Không mặc định idempotent | Tránh retry tự động trừ khi contract cung cấp idempotency key hoặc bảo đảm tương đương |
| **PATCH** | Không mặc định idempotent | Phải xét operation cụ thể, version/ETag và contract |

**“Idempotent” không đồng nghĩa “không tạo ra thêm log/metrics nào”.** Theo HTTP semantics, việc gửi nhiều request có cùng hiệu ứng dự định lên tài nguyên, dù server có thể ghi log mỗi lần. Ứng dụng thực tế đôi khi triển khai sai semantics, vì thế client quan trọng vẫn cần kiểm soát ở tầng business.

### Ví dụ nguy hiểm: POST tạo đơn hàng

~~~text
Client: POST /orders (không có idempotency key)
    │
    ├── Server ghi orderId=42 vào database thành công
    ├── Kết nối đứt trước khi client đọc response
    ▼
Client: IOException / HttpTimeoutException
    │
    └── Nếu retry không kiểm soát → server có thể tạo orderId=43
~~~

Không thể quy exception thành “server chưa xử lý”, cũng không thể dựa vào **500** để chắc chắn rollback. Hãy dùng **idempotency key** do API định nghĩa, ví dụ một header có tên theo contract của hệ thống và giá trị unique cho một thao tác; hoặc tra cứu trạng thái dựa trên business request ID trước khi thử lại. Không tự phát minh rằng mọi server đều hỗ trợ một header idempotency chung.

### Kết hợp Retry-After và backoff

**Retry-After** có thể là:

~~~http
Retry-After: 3
~~~

hoặc:

~~~http
Retry-After: Wed, 21 Oct 2037 07:28:00 GMT
~~~

Giá trị đầu là **delay-seconds**, không phải milliseconds; giá trị sau là **HTTP-date**. Production code cần parse cả hai dạng, đối chiếu clock, áp dụng max wait/deadline, jitter nếu thích hợp và tôn trọng rate-limit policy. Đối với 429 hoặc 503 mà không có Retry-After, backoff có giới hạn vẫn tốt hơn retry ngay lập tức.

Đừng tự làm retry khi **certificate mismatch/SSLHandshakeException**, 401/403 do credential/policy sai hoặc 400/422 do validation chưa sửa: chúng thường **không biến mất chỉ vì lặp request**. Ngược lại, 404 có thể được coi là kết quả bình thường của API kiểm tra tồn tại tài nguyên; không nhất thiết phải báo lỗi hệ thống.

## 11. HTTP client quyết định thế nào khi nhận status?

Một cách tiếp cận là **đánh giá theo contract** trước, nhóm status chỉ để định tuyến xử lý mặc định:

~~~text
Gửi request
    │
    ├── ném exception / future exceptional
    │     └── ghi type + cause + phase/timing nếu có
    │           → retry/cancel/fail theo policy và idempotency
    │
    └── nhận HttpResponse
          │
          ├── 2xx → kiểm tra status cụ thể, body và business contract
          │           201: Location; 202: async job; 204: không body
          │
          ├── 3xx → redirect/conditional cache semantics
          │           302: Location; 304: dùng cached representation
          │
          ├── 4xx → auth, validation, conflict, quota...
          │           401: auth; 409: state; 429: backoff
          │
          └── 5xx → server/gateway error
                      503: capacity/maintenance, có thể Retry-After
                      504: gateway chờ upstream quá lâu
~~~

### Quy tắc đánh giá success ở nhiều tầng

Có ít nhất ba tầng:

- **Transport success:** đã kết nối và truyền/nhận đúng các byte cần thiết theo network protocol.
- **HTTP success:** server trả status phù hợp (thường 2xx) theo HTTP semantics.
- **Business success:** contract nghiệp vụ được hoàn tất, ví dụ giao dịch được xác nhận, dữ liệu đã commit hoặc job chuyển sang trạng thái completed.

Ví dụ: **202 Accepted** cho biết request HTTP được chấp nhận, **không** đảm bảo job hoàn tất. **200 OK** có thể chứa một domain error theo thiết kế API. **503** cho biết lỗi HTTP server/gateway, nhưng không chứng minh server chưa tạo side effect.

### Lưu ý logging/metrics

Nên tách các dimension:

~~~text
HTTP RESPONSE:
method=GET
route=/items/{id}
http_status=503
status_family=5xx
exception_type=none
retry_after=1
duration_ms=...

TRANSPORT / CLIENT FAILURE:
method=GET
route=/items/{id}
http_status=absent
error_type=HttpTimeoutException
phase=unknown_or_recorded_phase
duration_ms=...
request_effect=unknown
~~~

Không đưa token, password, cookie, query chứa thông tin cá nhân hoặc full response body nhạy cảm vào log. Nếu hệ thống dùng mã nội bộ như **HTTP_STATUS_UNAVAILABLE**, ghi rõ đó **không** phải mã HTTP trả về. Khi có distributed tracing, thêm request ID/trace ID và đối chiếu log gateway/backend theo chính sách.

## 12. Kiểm thử thực tế bằng HTTP client, curl và fault injection

### Khi có response: xem status và headers

~~~bash
curl -i http://127.0.0.1:8080/health
curl -v http://127.0.0.1:8080/missing
curl -i -L http://127.0.0.1:8080/redirect
~~~

Các URL là **ví dụ nếu bạn có server ở port 8080**, **không** phải URL của demo tự cấp port 0; hãy thay bằng port thật. **-i** hiển thị headers, **-v** hiển thị chi tiết tiến trình network, **-L** tự follow redirect. Với cURL, option **--fail** có thể làm lệnh trả exit code non-zero khi HTTP status >=400 (có ngoại lệ theo giao thức/tình huống); đây là hành vi của công cụ, **không biến 404/503 thành TCP error**.

### Khi không có response: kiểm tra network phase

Nếu chưa kết nối được, kiểm tra có lỗi DNS, sai hostname, proxy, firewall, port, TLS cert, DNS cache hoặc timeout hay không. **Không** lấy status code do application tự gán khi catch exception để suy ngược “server trả mã đó”.

Để phân tích vấn đề:

1. **DNS:** hostname resolve ra IP đúng không? Có IPv4/IPv6 mismatch không?
2. **TCP:** đúng host/port chưa? Có listener? Firewall/NAT và routing?
3. **TLS:** certificate chain được tin? SAN khớp hostname? TLS version/cipher compatible?
4. **HTTP:** request đã đến server/gateway chưa? Có status, Retry-After, Location, response body?
5. **Body/application:** có timeout đọc body, parse lỗi hoặc business validation failure không?

Một **HTTP 404** nên debug URL/path/API contract và quyền đọc; một **Connection refused** nên debug host/port/listener. Đây là hai bộ công cụ khác nhau.

## 13. Các lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “404 nghĩa là server không kết nối được.” | Điều tra sai network, mất thời gian | 404 là HTTP response; xem routing/resource/auth |
| “Mọi 5xx đều do backend gửi.” | Bỏ sót gateway/proxy/upstream | Correlate edge/backend logs và trace |
| “504 và HttpTimeoutException là một.” | Không biết ai thực sự timeout | Phân biệt response do gateway trả và deadline client |
| “500 chắc chắn là giao dịch rollback.” | Retry POST tạo side effect trùng | Idempotency key/business status inquiry |
| “Mọi 2xx đều chứa JSON.” | Parse body rỗng của 204/HEAD | Xem status, method và Content-Type |
| “304 là redirect cần follow Location.” | Hỏng caching/conditional requests | 304 là not-modified; sử dụng cache đúng |
| “401 và 403 giống nhau.” | Loop refresh token hoặc gây spam request | Xử lý xác thực vs phân quyền |
| “429 là 5xx vì service đang bận.” | Sai metrics, retry policy | 429 thuộc **4xx**, dùng Retry-After/quota |
| “send(...) luôn throw khi 404.” | Bỏ qua response.statusCode() | Đọc đúng behavior của java.net.http.HttpClient |
| “Bắt mọi IOException rồi đổi thành 500.” | Che mất lỗi DNS/TLS/network | Tách exception/transport khỏi HTTP status |
| “Bắt HttpTimeoutException nghĩa request chưa tới server.” | Lặp thao tác không idempotent | Giả định outcome unknown và thiết kế dedup |
| “Client luôn follow redirect.” | Surprise về method/URL/security | Cấu hình và test Redirect.NEVER/NORMAL |
| “Retry ngay mọi 503.” | Tạo retry storm | Backoff+jitter, Retry-After, max attempts |
| “Status family là đủ cho UI.” | Hiển thị thông báo sai với 409/422/429 | Phân loại theo mã và business contract |
| “Timeout càng dài càng an toàn.” | Người dùng đợi lâu, thread/connection cạn | Deadline có chủ đích và giới hạn tài nguyên |

## 14. Bài tập tự kiểm tra

1. Java **HttpClient.send(...)** nhận **HttpResponse** có status **404**. Có nên catch **ConnectException** để xử lý 404 không? Vì sao?
2. Một POST tạo đơn hàng trả **202 Accepted**, kèm status URL. Trạng thái nào cho phép báo “đơn hàng hoàn thành”? Cần polling/webhook như thế nào theo contract?
3. Server trả **204 No Content** cho DELETE. Một JSON parser tự chạy trên body rỗng sẽ báo lỗi. Đây có phải Connection Error không?
4. Client nhận **302 Found** từ **/login** rồi tự follow thành **200 OK**. Vì sao log application chỉ ghi 200 có thể làm mất thông tin redirect? Khi nào chọn Redirect.NEVER?
5. Với **304 Not Modified**, điều kiện nào giúp dùng cached representation? Vì sao 304 không phải HTTP server failure?
6. API trả **401**, **403**, **404**, **409**, **422**, **429**. Hãy viết xử lý riêng cho auth, permission, not-found, conflict, validation, rate limiting. Mã nào có thể retry mà không thay đổi request?
7. Một API gateway trả **504 Gateway Timeout**, còn một Java client khác ném **HttpTimeoutException** trước khi gateway kịp trả status. Ai tạo ra từng kết quả? Có nên đặt chung thành **statusCode=504**?
8. POST /payments đã commit, response bị mất giữa đường. Client nhận **IOException**. Vì sao câu hỏi “đã thực hiện thanh toán chưa?” không thể trả lời chỉ bằng exception? Thiết kế idempotency key và tra cứu trạng thái.
9. Chạy ví dụ và thay **HttpClient.Redirect.NEVER** bằng **NORMAL** trong các request. Quan sát mã status và đường đi nhận được. Làm sao log URI cuối để debug redirect?
10. Thay endpoint **/busy** trả 503 cùng **Retry-After: 1** bằng 429/503 không có header. Thiết kế retry policy có **deadline, exponential backoff, jitter** và giới hạn số lần thử.
11. Thay **/slow** từ 800ms thành 10ms và giữ timeout 150ms. Tại sao kết quả có thể là **200** thay vì HttpTimeoutException? Điều gì quyết định kết quả?
12. Đọc **RFC 9110** và giải thích: 301/302 khác 307/308 về method preservation, 408 khác timeout client, 429 khác 503, 206 có nghĩa gì khi tải file từng phần.

## 15. Checklist tổng hợp để code và vận hành

- [ ] Có phân biệt **HTTP response** với **exception khi chưa lấy được HttpResponse hoàn chỉnh**?
- [ ] Có phân loại 2xx/3xx/4xx/5xx nhưng vẫn xử lý mã cụ thể theo contract?
- [ ] Có xử lý **201 Location**, **202 async**, **204 no body**, **206 Partial Content**?
- [ ] Có xử lý **304 conditional/caching** riêng với redirect?
- [ ] Có biết redirect policy của HttpClient và tác động tới URL/method/credentials?
- [ ] Có phân biệt **401**, **403**, **404**, **409**, **412**, **422**, **429**?
- [ ] Có phân biệt **500/502/503/504** và lỗi từ gateway?
- [ ] Có nhận biết **408/429/503/504** là status, **HttpTimeoutException** là exception?
- [ ] Có giữ cause/exception và thông tin phase nếu không có status?
- [ ] Có tránh gán “500” hoặc “0” như thể đó là HTTP response thật?
- [ ] Có giới hạn timeout, retry attempts, backoff, jitter và cân nhắc Retry-After?
- [ ] Có cơ chế chống duplicate effect cho POST/payment khi outcome không chắc chắn?
- [ ] Có đọc **response body/headers** theo method/status và API contract?
- [ ] Có tách network, HTTP và business metrics, không log bí mật?

**Ghi nhớ:** **2xx/3xx/4xx/5xx là cách phân loại status của một HTTP response.** Status **404, 429, 503, 504** đều là **response HTTP thực sự**, không phải ngoại lệ kết nối. Ngược lại **DNS failure, Connection refused, TLS handshake failure, timeout do client và I/O failure** là các tình huống có thể khiến API Java không trả về **HttpResponse**, và chỉ có **exception/cause** để phân tích. Xác định trước “có response hay không” rồi mới quyết định thông báo, retry và logging; không dùng mỗi mã status để suy đoán nghiệp vụ hoặc side effect.

**Tài liệu tham khảo:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111), [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585), [HttpClient (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html), [HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html), [HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html), [HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html), [HttpServer (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).