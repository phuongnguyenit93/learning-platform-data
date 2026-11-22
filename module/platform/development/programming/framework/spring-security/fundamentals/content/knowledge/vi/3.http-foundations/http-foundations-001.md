# Request, response, HTTP method và mã trạng thái liên quan tới bảo mật

HTTP là giao thức trao đổi request và response giữa client và server. Spring Security đưa ra quyết định xác thực, phân quyền và nhiều cơ chế phòng vệ dựa trên **thông tin trong HTTP request**, sau đó biểu đạt kết quả bằng **HTTP status, response headers và response body**. Hiểu chính xác lớp nền này giúp phân biệt lỗi truy cập, cấu hình đúng quyền cho từng method, tránh lộ thông tin và kiểm thử bảo mật có ý nghĩa.

Bài học tập trung vào ngữ nghĩa HTTP liên quan trực tiếp tới bảo mật trong ứng dụng Spring Boot/Spring Security. Các ví dụ minh họa dùng REST API; cách ứng dụng xử lý một request có thể phụ thuộc cấu hình xác thực, loại client, proxy/gateway và chính sách nghiệp vụ.

## 1. Vòng đời một HTTP request/response

Một client gửi request để yêu cầu tài nguyên hoặc hành động. Server trả response với status báo kết quả, các header mô tả cách xử lý response và có thể kèm body.

~~~text
Browser / mobile / API client
          |
          |  HTTP request
          |  method + target + headers + optional body
          v
     Reverse proxy / gateway (nếu có)
          |
          v
   Spring Security filter chain
       |                 |
       | bị từ chối      | được phép
       v                 v
  401 / 403 / ...     DispatcherServlet
                         |
                         v
                    Controller
                         |
                         v
                    Service / DB
                         |
                         v
                    HTTP response
          |
          v
Client nhận status + response headers + optional body
~~~

Trong HTTP/1.1, một request ví dụ trông như sau:

~~~http
GET /api/orders/42?includeItems=true HTTP/1.1
Host: shop.example.test
Accept: application/json
Authorization: Bearer <access-token>
X-Request-Id: req-123

~~~

Dòng đầu gồm **method**, **request target** và phiên bản giao thức. Các header cung cấp metadata như Host, Accept và Authorization; dòng trống kết thúc phần header. Ví dụ GET không có body. Cú pháp trên mang tính minh họa; chuỗi <access-token> là chỗ giữ chỗ, không phải một token hợp lệ.

Nếu request được chấp nhận, response có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{"id":42,"ownerId":"customer-17","status":"PAID"}
~~~

**Status 200** chỉ cho biết server đã xử lý request thành công theo ngữ nghĩa HTTP; nó không tự chứng minh người gọi **được cấp quyền đúng**, dữ liệu trả ra **đúng người sở hữu** hoặc response **an toàn để cache**. Những điều đó do hệ thống bảo mật và nghiệp vụ quyết định.

HTTP về cơ bản là giao thức không giữ trạng thái giữa các request. Việc duy trì đăng nhập xảy ra nhờ session cookie, token hoặc cơ chế khác; server cần kiểm tra credential và quyền cho từng request theo mô hình đã chọn. Không được suy ra rằng vì request trước được phép nên mọi request tiếp theo mặc nhiên được phép.

### 1.1. Những thành phần của request cần nhận diện

| Thành phần | Ví dụ | Ý nghĩa đối với bảo mật |
| --- | --- | --- |
| Scheme/transport | https:// | HTTPS/TLS bảo vệ dữ liệu khi truyền; HTTP thuần có nguy cơ bị nghe lén/sửa đổi trên đường truyền. |
| Method | GET, POST, DELETE | Diễn tả ngữ nghĩa thao tác và ảnh hưởng đến chính sách truy cập, CSRF, caching. |
| Path | /api/orders/42 | Là đầu vào cho routing và nhiều quy tắc phân quyền URL. |
| Query string | ?includeItems=true | Có thể xuất hiện trong history/log/analytics; tránh đặt password hoặc access token vào đây. |
| Headers | Authorization, Cookie, Origin | Có thể chứa credential, thông tin content negotiation hoặc metadata do client cung cấp. |
| Body | JSON, form, multipart file | Phải kiểm tra schema, kích thước, kiểu dữ liệu và quyền thực hiện nghiệp vụ. |
| Network context | Client IP, proxy chain | Chỉ tin thông tin IP được cung cấp theo cấu hình proxy tin cậy. |

Path, query, header, body và cookie **đều là đầu vào cần được kiểm soát**, kể cả khi client UI bình thường không cho người dùng sửa. Kẻ gọi API có thể sử dụng HTTP client riêng và tự tạo request.

### 1.2. Những thành phần của response cần nhận diện

| Thành phần | Ví dụ | Điều cần kiểm tra |
| --- | --- | --- |
| Status | 200, 401, 403, 404 | Phản ánh đúng kết quả xác thực, phân quyền, dữ liệu và lỗi. |
| Content-Type | application/json | Client hiểu đúng loại nội dung; kết hợp chống MIME sniffing khi phù hợp. |
| Cache-Control | no-store | Ngăn các cache tuân thủ chỉ thị lưu response nhạy cảm. |
| Set-Cookie | session=...; Secure; HttpOnly; SameSite=Lax | Quy định cách trình duyệt lưu/gửi cookie phiên; thuộc tính cần khớp mô hình sử dụng. |
| WWW-Authenticate | Bearer ... / Basic ... | Thông báo cơ chế/điều kiện xác thực khi server trả challenge. |
| Location | /api/orders/42 | Dùng trong response tạo resource/redirect; URL trả về phải được xây dựng an toàn. |
| Security headers | HSTS, CSP, nosniff ... | Hỗ trợ phòng vệ ở trình duyệt, tùy loại response và môi trường. |
| Body | JSON hoặc HTML lỗi | Không làm lộ stack trace, secret, nội dung đơn hàng hoặc chi tiết xác thực không cần thiết. |

Trong HTTP/2 và HTTP/3, biểu diễn trên dây khác HTTP/1.1, nhưng các khái niệm method, target, headers, status và body vẫn là nền tảng cho ứng dụng Spring.

## 2. HTTP methods: an toàn và idempotent có ý nghĩa gì?

Phân biệt hai tính chất quan trọng:

- **Safe:** method được định nghĩa nhằm mục đích đọc, không yêu cầu client gây thay đổi trạng thái nghiệp vụ trên server. Ví dụ GET và HEAD. Hệ thống vẫn có thể ghi log/metrics hoặc thực hiện các tác động phụ không được client yêu cầu.
- **Idempotent:** thực hiện cùng một request nhiều lần có **hiệu ứng dự định trên trạng thái server** giống như thực hiện một lần. GET, HEAD, PUT, DELETE và các method safe là idempotent theo ngữ nghĩa HTTP. POST và PATCH không mặc định idempotent.

Idempotent **không có nghĩa** là mọi response đều giống nhau, không có log được ghi thêm hoặc thao tác có thể gọi bao nhiêu lần cũng không tốn tài nguyên.

| Method | Safe? | Idempotent theo ngữ nghĩa? | Công dụng thường gặp | Câu hỏi bảo mật |
| --- | --- | --- | --- | --- |
| GET | Có | Có | Đọc resource | Có rò rỉ dữ liệu theo ID, query, role hoặc cache? |
| HEAD | Có | Có | Lấy metadata như GET nhưng không trả response body | Có để lộ metadata hoặc khác biệt phân quyền so với GET? |
| OPTIONS | Có | Có | Hỏi khả năng hỗ trợ, CORS preflight | CORS và quyền preflight đã cấu hình hợp lý? |
| POST | Không | Không mặc định | Tạo resource/chạy lệnh nghiệp vụ | Có CSRF, chống request lặp, giới hạn input, rate limit? |
| PUT | Không | Có | Tạo hoặc thay thế trạng thái resource theo URI | Có kiểm quyền cập nhật đúng ID/field và điều kiện đồng thời? |
| PATCH | Không | Không mặc định | Cập nhật một phần | Có mass assignment, cập nhật field cấm, xung đột dữ liệu? |
| DELETE | Không | Có | Yêu cầu xóa resource | Có kiểm quyền đối tượng, xác nhận điều kiện và audit? |
| TRACE | Có theo đặc tả HTTP | Có | Phản chiếu request phục vụ chẩn đoán | Thường không cần bật trên API công khai; xem xét chính sách server/proxy. |
| CONNECT | Không | Không mặc định | Yêu cầu thiết lập đường hầm qua proxy | Nếu bật sai ngữ cảnh có thể tạo đường truy cập tới đích ngoài ý muốn. |

Một số hệ thống có thể thiết kế POST idempotent bằng **idempotency key** và lưu kết quả xử lý, ví dụ tránh tạo hai giao dịch khi client retry. Đó là thiết kế ở tầng ứng dụng, không biến tất cả POST thành idempotent theo mặc định.

### 2.1. Vì sao GET không nên thực hiện hành động nhạy cảm?

GET thường được dùng bởi trình duyệt, crawler, prefetcher, link preview, monitoring và cache. Nếu **GET /api/payments/confirm?id=42** làm thay đổi trạng thái thanh toán, việc mở link hoặc một tác nhân tự động truy cập URL có thể gây tác động ngoài ý muốn.

GET cũng không phải nơi an toàn để đặt thông tin bí mật: URI và query có thể hiện trong history, log proxy, bookmark hoặc telemetry. Đừng dùng đường dẫn dạng **/reset-password?secret=...** mà không xét kỹ vòng đời secret, redaction log, thời hạn và cơ chế dùng một lần. Token trong link kích hoạt thường là một trường hợp đặc thù cần chính sách bảo vệ riêng.

**Safe method** không thay thế authorization: GET /api/orders/42 vẫn phải kiểm quyền chủ sở hữu và tenant.

### 2.2. Idempotency và tác động lặp lại

- PUT /api/profile/42 gửi cùng nội dung có thể đưa resource về cùng trạng thái cuối, nhưng cần quyền đúng chủ sở hữu. Lặp request không làm chủ thể sai có thêm quyền.
- DELETE /api/items/42 lần đầu có thể trả 204; lần sau có thể trả 404. Hai response khác status **không làm mất** tính idempotent của tác động xóa.
- POST /api/payments có thể tạo giao dịch mới nếu gửi lặp; cần thiết kế chống trùng, unique constraint và idempotency key khi nghiệp vụ yêu cầu.
- PATCH có thể idempotent nếu biểu diễn bằng “đặt giá trị = 5”, nhưng không idempotent nếu biểu diễn “tăng giá trị thêm 5”; không suy diễn tính chất chỉ từ tên method.

Với thao tác tạo/đổi dữ liệu, thường cần kiểm soát **authentication, authorization, CSRF khi phù hợp, input validation, concurrency, replay và audit**.

## 3. Các nhóm HTTP status và mối liên hệ bảo mật

Status code là ngữ nghĩa giao thức do server phát ra. Chọn mã đúng giúp client phân biệt việc cần đăng nhập lại, thiếu quyền, request sai, vượt giới hạn và lỗi backend.

| Nhóm | Ý nghĩa tổng quát | Điểm cần chú ý |
| --- | --- | --- |
| 1xx | Thông tin trung gian | Ví dụ 100 Continue; không đại diện kết quả phân quyền cuối cùng. |
| 2xx | Request được xử lý thành công | 200/201/204 vẫn phải đi kèm đúng quyền, đúng dữ liệu. |
| 3xx | Chuyển hướng hoặc dùng bản cache | Redirect có thể làm lộ/chuyển phương thức hoặc ảnh hưởng credential/cookie. |
| 4xx | Vấn đề từ phía request theo ngữ nghĩa HTTP | Thường gặp khi thiếu xác thực, thiếu quyền, sai method/format, bị rate limit. |
| 5xx | Server hoặc hệ thống phụ thuộc không đáp ứng được | Không trả stack trace/secret; cần giám sát và xử lý lỗi có kiểm soát. |

### 3.1. 2xx: Thành công không đồng nghĩa được cấp quyền đúng

| Status | Khi thường dùng | Lưu ý bảo mật |
| --- | --- | --- |
| **200 OK** | Đọc/cập nhật thành công và trả dữ liệu | Kiểm dữ liệu đúng principal, không rò rỉ trường nhạy cảm; đặt cache policy phù hợp. |
| **201 Created** | Đã tạo resource, có thể kèm Location | Chỉ trả ID/URL và dữ liệu người gọi được xem; tránh tạo resource nhân danh người khác. |
| **202 Accepted** | Chấp nhận xử lý bất đồng bộ, chưa hoàn tất | Không diễn giải là “đã thanh toán/đã xử lý”; task/queue vẫn cần quyền và chống lặp. |
| **204 No Content** | Thành công và không có body | Thích hợp xóa/cập nhật; response 204 không chứa body. |
| **206 Partial Content** | Trả một phần nội dung theo Range | Với file riêng tư, kiểm quyền trước khi cấp bất kỳ byte nào; không để Range làm lộ dữ liệu. |

Một endpoint trả 200 cho người không đủ quyền không chứng minh API “không gặp lỗi”; đó có thể là **lỗi phân quyền nghiêm trọng**. Test bảo mật cần kiểm cả **dữ liệu và side effects**, không chỉ status.

### 3.2. 3xx: Chuyển hướng cần được kiểm soát

| Status | Ngữ nghĩa | Nguy cơ/cần nhớ |
| --- | --- | --- |
| **301 Moved Permanently** | Resource được chuyển vĩnh viễn | Có thể được cache; cẩn thận với URL chứa dữ liệu nhạy cảm. |
| **302 Found** | Chuyển hướng tạm thời; user agent có thể chuyển POST thành GET | Trong web app dùng form login, client chưa đăng nhập có thể nhận 302 tới trang đăng nhập. |
| **303 See Other** | Hướng client thực hiện GET tới tài nguyên khác sau request | Hữu ích với luồng POST/Redirect/GET. |
| **307 Temporary Redirect** | Chuyển hướng tạm thời và giữ nguyên method/body | Không vô tình redirect POST chứa credentials hoặc body nhạy cảm tới đích không tin cậy. |
| **308 Permanent Redirect** | Chuyển hướng vĩnh viễn và giữ nguyên method/body | Cần rà kỹ target và chính sách client/cache. |
| **304 Not Modified** | Dùng bản đã cache theo conditional request | Không phải 3xx redirect; cần bảo vệ quyền truy cập và cơ chế cache với tài nguyên nhạy cảm. |

Khi ứng dụng tự nhận **returnUrl/redirectUri/next** từ client, phải kiểm tra allowlist/đích hợp lệ để tránh **open redirect** và rò rỉ dữ liệu qua URL. Với OAuth/OIDC, redirect URI phải được kiểm tra đúng theo quy định của luồng xác thực.

**HTTP → HTTPS redirect** giúp chuyển người dùng sang kết nối an toàn, nhưng request đầu tiên trên HTTP vẫn có thể phơi lộ dữ liệu nếu client đã gửi credential. Dùng HTTPS ngay từ đầu, cấu hình secure cookie và HSTS khi hệ thống đủ điều kiện; đừng dựa duy nhất vào redirect để bảo vệ secret.

### 3.3. 4xx: Mã lỗi liên quan trực tiếp tới bảo mật

| Status | Khi nào phù hợp | Điều cần phân biệt |
| --- | --- | --- |
| **400 Bad Request** | Request sai cú pháp hoặc không thể xử lý do client | Khác 401: request sai định dạng không nhất thiết thiếu đăng nhập. |
| **401 Unauthorized** | Thiếu hoặc không có bằng chứng xác thực hợp lệ cho tài nguyên cần bảo vệ | Tên mã gây nhầm lẫn: trọng tâm là **authentication**; có challenge WWW-Authenticate khi áp dụng. |
| **403 Forbidden** | Server hiểu request nhưng từ chối cho thực hiện | Có thể do thiếu quyền, CSRF hoặc chính sách khác; không luôn có nghĩa user đã đăng nhập. |
| **404 Not Found** | Không tìm thấy resource hoặc chủ động che giấu sự tồn tại | Có thể dùng cho resource không thuộc user nếu chính sách cố ý tránh lộ thông tin. |
| **405 Method Not Allowed** | URI tồn tại nhưng không hỗ trợ method đó | Response phải có header Allow nêu các method được hỗ trợ cho target. |
| **406 Not Acceptable** | Không thể tạo representation chấp nhận được theo Accept | Khác 415 về định dạng body gửi lên. |
| **408 Request Timeout** | Server không nhận đủ request trong thời gian chấp nhận | Không thay thế rate limit hoặc đánh giá xác thực. |
| **409 Conflict** | Request xung đột với trạng thái tài nguyên | Ví dụ optimistic locking hoặc chuyển trạng thái nghiệp vụ không hợp lệ. |
| **411 Length Required** | Server yêu cầu Content-Length | Có thể hữu ích ở luồng upload; không đồng nghĩa vượt dung lượng. |
| **413 Content Too Large** | Nội dung request quá lớn theo giới hạn server | Giới hạn body/file để tránh cạn tài nguyên. |
| **415 Unsupported Media Type** | Content-Type của request không được hỗ trợ | Không nhầm với 406 (Accept của response). |
| **422 Unprocessable Content** | Body có cú pháp hợp lệ nhưng nội dung không thể xử lý theo quy tắc | Ví dụ dữ liệu sai ngữ nghĩa; chọn 400/422 nhất quán theo API contract. |
| **429 Too Many Requests** | Vượt giới hạn số lượng request | Có thể kèm Retry-After; rate limiting là phòng vệ bổ sung, không thay thế quyền. |
| **431 Request Header Fields Too Large** | Header quá lớn | Có thể liên quan cookie/header bất thường; cần giới hạn tại proxy/server. |

**401 và 403 là cặp dễ nhầm nhất.** Cần hiểu cả ngữ nghĩa của hai mã và cấu hình cụ thể của server:

- **401:** client chưa cung cấp credential hợp lệ để xác thực. Với HTTP Basic, response có thể gồm **WWW-Authenticate: Basic realm="api"**; với Bearer, challenge và thông tin lỗi có thể tuân theo cơ chế Bearer token được cấu hình.
- **403:** request đã hiểu nhưng bị cấm. Thường xảy ra khi principal hợp lệ không có authority cần thiết hoặc POST bị chặn bởi CSRF. Server cũng có thể từ chối request vì chính sách khác khi chưa có principal đã xác thực.
- **404:** có thể được dùng thay vì phản hồi nói rõ resource của người khác tồn tại. Tuy nhiên phải tránh để thông tin rò qua khác biệt thời gian, body hoặc các endpoint liên quan nếu yêu cầu che giấu sự tồn tại.

Ví dụ kỳ vọng trong API dùng HTTP Basic và tài khoản được cấu hình đúng:

| Request | Điều kiện | Status điển hình |
| --- | --- | --- |
| GET /api/me | Không có credential | 401 |
| GET /api/me | Credential sai hoặc hết hiệu lực | 401 |
| GET /api/admin | Đăng nhập role USER nhưng chỉ ADMIN được truy cập | 403 |
| GET /api/admin | Đăng nhập ADMIN hợp lệ | 200 |
| GET /api/orders/42 | User A yêu cầu đơn của B; Service kiểm owner | 403 hoặc 404 theo policy |
| POST /api/orders | User có quyền nhưng thiếu CSRF token trong phiên dùng cookie | Có thể 403 |
| POST /api/orders | Body sai định dạng | 400 hoặc 415 tùy lỗi |
| GET /api/orders/42 | Không có resource và không có thông tin để lộ | 404 |

Bảng là ví dụ **phụ thuộc cấu hình**, không phải quy tắc cứng cho mọi hệ thống. Đặc biệt, ứng dụng trình duyệt dùng form login thường trả **302 redirect tới trang đăng nhập** cho một số request chưa xác thực, còn REST API dùng HTTP Basic/Bearer thường dùng 401.

### 3.4. 5xx: Lỗi server và cách tránh rò rỉ thông tin

| Status | Ý nghĩa điển hình | Cách xử lý an toàn |
| --- | --- | --- |
| **500 Internal Server Error** | Lỗi nội bộ bất ngờ | Trả thông tin lỗi tối thiểu; lưu chi tiết trong log có kiểm soát. |
| **502 Bad Gateway** | Gateway nhận response không hợp lệ từ upstream | Kiểm log/tracing theo request ID; không phơi endpoint nội bộ. |
| **503 Service Unavailable** | Quá tải/bảo trì/tạm thời không sẵn sàng | Có thể thêm Retry-After; bảo vệ khỏi retry bùng nổ. |
| **504 Gateway Timeout** | Gateway không nhận response kịp từ upstream | Thiết kế timeout, circuit breaker và retry có giới hạn. |

Đừng biến mọi lỗi quyền thành **500** để “giấu chi tiết”. Điều đó làm client retry sai, che khuất số liệu bảo mật và gây khó chẩn đoán. Đồng thời, đừng trả cho client stack trace, SQL, connection string, JWT, API key hoặc tên file nội bộ chỉ để dễ debug. Sử dụng message ngắn, mã lỗi ứng dụng và request/correlation ID.

## 4. Những HTTP headers tác động đến bảo mật

### 4.1. Request headers

**Authorization** mang credential cho một số cơ chế xác thực:

~~~http
Authorization: Bearer <access-token>
~~~

Bearer token là **credential mang quyền**: ai có token hợp lệ có thể dùng quyền gắn với token trong phạm vi được cấp, nên phải bảo vệ khi lưu/truyền, xác minh chữ ký hoặc phương thức xác thực phù hợp, issuer/audience/expiry theo cấu hình. Chỉ giải mã chuỗi JWT không đủ để tin claim.

HTTP Basic có dạng **Authorization: Basic ...**; phần credentials là Base64, **không phải mã hóa**. Không gửi Basic qua HTTP thuần; nên dùng TLS và quản lý mật khẩu đúng cách.

**Cookie** gửi các cookie phù hợp về domain/path/policy. Với session:

~~~http
Cookie: SESSION=<opaque-session-id>
~~~

Session ID là secret. Nếu bị đánh cắp, nó có thể bị sử dụng để chiếm phiên tùy thiết kế. Server cần quản lý session lifecycle, logout/invalidation, thời hạn và session fixation; client phải có HTTPS/Secure và các thuộc tính cookie phù hợp.

Các header còn lại:

- **Content-Type:** kiểu dữ liệu mà client thực sự gửi, ví dụ application/json hoặc multipart/form-data. Server phải validate nội dung thay vì chỉ tin header.
- **Accept:** kiểu response mà client có thể chấp nhận. Không dùng nó làm bằng chứng quyền truy cập.
- **Origin:** nguồn gốc trình duyệt của một số request; giúp xử lý CORS và có thể tham gia phòng vệ CSRF tùy ngữ cảnh, nhưng client không phải trình duyệt có thể tự đặt header này.
- **Host:** host đích của request; khi dùng tạo absolute URL hoặc reset link, phải tránh Host header injection bằng cấu hình trusted host/proxy.
- **X-Forwarded-For / Forwarded / X-Forwarded-Proto:** metadata proxy; **chỉ tin khi proxy tin cậy kiểm soát và chuẩn hóa chúng**. Client có thể tự gửi giá trị giả nếu server chấp nhận vô điều kiện.
- **Range / If-None-Match / If-Match:** điều khiển nội dung từng phần hoặc precondition/caching; không làm giảm yêu cầu kiểm tra quyền trước khi trả dữ liệu.
- **X-CSRF-TOKEN** hoặc header CSRF tương ứng: một cách truyền token khi client dùng cơ chế phòng vệ CSRF đã cấu hình; tên header có thể khác nhau.

### 4.2. Response headers

**WWW-Authenticate:** được dùng để gửi challenge cho client, đặc biệt khi nhận 401. Chọn đúng cơ chế xác thực thay vì tùy tiện trả 401 không có thông tin cần thiết cho giao thức.

**Set-Cookie** minh họa:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **Secure:** trình duyệt chỉ gửi cookie trên kết nối an toàn theo quy tắc áp dụng.
- **HttpOnly:** giảm nguy cơ JavaScript trực tiếp đọc cookie; không có nghĩa là chống mọi XSS hoặc CSRF.
- **SameSite:** ảnh hưởng việc trình duyệt gửi cookie trong bối cảnh cross-site; chọn Lax/Strict/None theo luồng thực tế. SameSite=None cần Secure trong trình duyệt hiện đại.
- **Path/Domain:** quyết định phạm vi cookie; cấu hình quá rộng có thể tăng vùng phơi lộ.

**Cache-Control** với dữ liệu nhạy cảm:

~~~http
Cache-Control: no-store
~~~

No-store yêu cầu cache tuân thủ không lưu response; không thay thế authorization, encryption hoặc chính sách lưu trữ dữ liệu trong chính ứng dụng. Thận trọng với cache chung, CDN, reverse proxy và các response có **Vary** theo nội dung/credential. Đừng dựa vào việc client luôn tuân thủ để bảo vệ dữ liệu tuyệt mật.

Một số header trình duyệt phổ biến:

| Header | Vai trò | Giới hạn |
| --- | --- | --- |
| **Strict-Transport-Security** | HSTS yêu cầu trình duyệt dùng HTTPS cho các lần truy cập sau theo policy | Phải gửi qua HTTPS và triển khai thận trọng trước khi áp dụng includeSubDomains/preload. |
| **Content-Security-Policy** | Hạn chế nguồn script/style/resource và một số hành vi trình duyệt | Không sửa XSS server-side hoặc làm mất nhu cầu escaping/input validation. |
| **X-Content-Type-Options: nosniff** | Hạn chế MIME sniffing ở các ngữ cảnh hỗ trợ | Không thay thế Content-Type đúng hoặc xác minh nội dung upload. |
| **Referrer-Policy** | Giảm dữ liệu URL được gửi làm referrer | Không cho phép nhét secret vào query vì còn các đường rò khác. |
| **Permissions-Policy** | Hạn chế một số tính năng trình duyệt | Không phải cơ chế xác thực hay phân quyền API. |
| **X-Frame-Options** hoặc CSP frame-ancestors | Giảm nguy cơ clickjacking khi nội dung bị nhúng | Không thay thế kiểm soát hành động nhạy cảm. |

Spring Security có hỗ trợ nhiều security headers mặc định hoặc qua cấu hình, nhưng chính sách cụ thể phải xem theo phiên bản Spring Security và dạng tài nguyên. Không giả định mặc định của thư viện đáp ứng toàn bộ chính sách frontend/browser cho mọi ứng dụng.

## 5. Authentication, authorization và HTTP status đi với nhau thế nào?

### 5.1. Authentication: yêu cầu danh tính hợp lệ

Ví dụ gọi API yêu cầu đăng nhập:

~~~http
GET /api/profile HTTP/1.1
Host: shop.example.test
Accept: application/json

~~~

Với API cấu hình HTTP Basic, response có thể có dạng:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Cache-Control: no-store

~~~

Client có thể gửi credential hợp lệ ở request sau. Với OAuth2 Resource Server/Bearer token, challenge thường là Bearer và có quy tắc riêng cho trường hợp token thiếu, sai hoặc không đủ scope. Với form login, thay vì 401, ứng dụng có thể **302** tới trang đăng nhập. Đây là lựa chọn entry point khác nhau, không phải mâu thuẫn của HTTP.

**Chưa đăng nhập** và **đã đăng nhập nhưng thiếu quyền** là hai trạng thái cần kiểm thử riêng.

### 5.2. Authorization: danh tính hợp lệ vẫn có thể không được phép

Giả sử principal đã xác thực là USER. Gọi API chỉ dành cho ADMIN:

~~~http
GET /api/admin/reports HTTP/1.1
Host: shop.example.test
Authorization: Bearer <valid-user-token>

~~~

Response có thể là:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"error":"forbidden"}
~~~

Điểm quan trọng: server cần xác minh credential đúng cách, xác định authorities/roles đáng tin cậy, kiểm tra chính sách trên method+path và **quyền đối với dữ liệu cụ thể** khi cần. Không đọc role từ header tùy ý do client tự gửi rồi tin đó là bằng chứng.

**Phân quyền ở URL không đủ cho IDOR/BOLA:** nếu GET /api/orders/{id} được phép với mọi user đã đăng nhập, Service vẫn cần kiểm tra đơn hàng đó có thuộc principal/tenant hiện tại hay không. Status 403/404 phải gắn với quyết định từ chối thực chất, tuyệt đối không để dữ liệu lộ ở body hoặc side effect trước khi trả lỗi.

### 5.3. Mã lỗi là hợp đồng API, không phải lớp bảo vệ duy nhất

Không thể “bảo mật” API chỉ bằng cách luôn trả 404 thay 403. Nếu endpoint đã đọc/ghi dữ liệu trái phép trước khi trả 404, rủi ro vẫn tồn tại. Một API dùng thông điệp lỗi thống nhất còn cần chống rò qua body, header, thời gian phản hồi và cache khi threat model yêu cầu.

Phân biệt status để client hành động đúng: 401 có thể yêu cầu đăng nhập/refresh theo chính sách; 403 thường cần cấp quyền hoặc thay đổi thao tác; 400/422 sửa dữ liệu; 429 chờ theo hạn mức; 503 tạm thời retry có giới hạn. Không retry vô hạn các request thay đổi dữ liệu.

## 6. CORS, CSRF, cookie và method OPTIONS

**CORS** (Cross-Origin Resource Sharing) kiểm soát liệu trình duyệt có được phép cho mã JavaScript ở một origin đọc response từ origin khác. Server trả các header CORS phù hợp, ví dụ **Access-Control-Allow-Origin**. Đối với một số cross-origin request, trình duyệt gửi **OPTIONS preflight** trước để hỏi method/header có được phép dùng hay không.

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type

~~~

Một preflight thành công có thể được đáp ứng:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization,content-type
Vary: Origin

~~~

Ví dụ chỉ minh họa header cần thiết cho tình huống cụ thể; nếu bật CORS credentials cần cấu hình thêm policy chính xác và không dùng wildcard origin cùng credentials. **CORS không chứng thực danh tính, không chặn curl hay công cụ gọi HTTP ngoài trình duyệt và không tự ngăn CSRF.** Server luôn phải kiểm tra quyền dù browser đã cho phép đọc response.

**CSRF** (Cross-Site Request Forgery) là nguy cơ trình duyệt bị dẫn dụ gửi request có side effect tới ứng dụng nơi người dùng đang có phiên xác thực, đặc biệt khi trình duyệt tự động gửi cookie/credential theo ngữ cảnh. Vì vậy:

- Các method thay đổi dữ liệu (POST, PUT, PATCH, DELETE) thường cần CSRF protection khi ứng dụng sử dụng cookie-session hoặc credential được browser tự gửi. Spring Security có cơ chế CSRF để cấu hình theo mô hình này.
- Nếu một API stateless thực sự chỉ nhận bearer token được client chủ động gắn trong Authorization và không chấp nhận cookie/credential tự gửi, thiết kế CSRF khác; vẫn cần xét XSS, token theft, CORS và các đường xác thực khác.
- **GET/HEAD/OPTIONS phải giữ ngữ nghĩa safe**. Nếu server dùng GET để xóa dữ liệu, CSRF protection theo phương thức mặc định có thể không chặn hành động đó vì GET được xem là safe.
- Preflight OPTIONS đôi khi đến **không kèm session cookie**, vì vậy cấu hình CORS và filter ordering phải hỗ trợ preflight hợp lệ trước khi yêu cầu authentication cho request nghiệp vụ.

**SameSite cookie**, CSRF token và Origin/Referer checks là những công cụ hỗ trợ khác nhau; không nên tuyên bố một cơ chế đơn lẻ giải quyết mọi trường hợp.

## 7. HTTPS/TLS, proxy và địa chỉ client

HTTPS bảo vệ tính bí mật/toàn vẹn khi dữ liệu đi qua kết nối TLS giữa các điểm kết thúc TLS. Trong hệ thống có reverse proxy, TLS có thể kết thúc tại gateway rồi đi tới backend bằng một kết nối khác; **đường gateway → backend vẫn phải được bảo vệ theo mô hình mạng và độ nhạy dữ liệu**.

Một số sai lầm thường gặp:

1. **Gửi mật khẩu/token qua HTTP rồi kỳ vọng redirect sang HTTPS sẽ bảo vệ chúng**: request đầu tiên có thể đã lộ.
2. **Tin trực tiếp X-Forwarded-For do client gửi** để áp dụng allowlist IP hoặc rate limit: header có thể bị giả nếu proxy không làm sạch/ghi đè.
3. **Tin Host/Forwarded để tạo link nhạy cảm** (reset password, OAuth redirect) mà không validate host được phép: có thể dẫn đến host-header injection.
4. **Cấu hình Secure cookie không phù hợp với việc TLS terminate tại proxy**, hoặc backend đánh giá sai scheme của request: phải cấu hình framework và trusted proxy đúng.
5. **Đánh đồng HTTPS với authorization**: TLS ngăn can thiệp trên đường truyền, nhưng user A có kết nối HTTPS hợp lệ vẫn không được đọc đơn của user B.

Các header request không phải bằng chứng “an toàn” chỉ vì do reverse proxy chuyển tiếp. Nguồn gốc của header và quyền của proxy phải được cấu hình rõ.

## 8. HTTP trong luồng Spring Security (Servlet)

Ở ứng dụng Spring MVC dùng Spring Security, Servlet filter chain xử lý request trước khi đến Controller. Một số phần chính:

- **SecurityFilterChain** xác định nhóm filter và quy tắc bảo mật được áp dụng.
- **Authentication** thể hiện danh tính và authorities sau khi cơ chế xác thực đã kiểm tra thành công.
- **Authorization** quyết định principal có được truy cập đường dẫn/method hay không; Spring Security hỗ trợ requestMatchers, authenticated, hasRole, hasAuthority và các quy tắc tùy biến.
- **AuthenticationEntryPoint** phụ trách bắt đầu quá trình xác thực khi cần, như trả 401/challenge hoặc redirect tới login tùy cơ chế.
- **AccessDeniedHandler** xử lý từ chối quyền khi luồng phù hợp, thường trả 403.
- **ExceptionTranslationFilter** giúp chuyển một số ngoại lệ authentication/authorization trong filter chain thành xử lý HTTP tương ứng.

Đây là bức tranh khái quát; thứ tự filter thực tế, exception handlers và kết quả cụ thể phụ thuộc cấu hình. Ngoài filter, Controller, Service, exception handler hoặc gateway vẫn có thể chủ động trả response.

Cấu hình minh họa cho ứng dụng Spring Security hiện đại, **đặt trong lớp @Configuration và có đủ dependency Spring Web/Spring Security**, không phải một file Java chạy độc lập:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/orders/**").authenticated()
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Trong đó HttpSecurity, SecurityFilterChain, Customizer và HttpMethod là các kiểu từ Spring Security/Spring Framework; cần import tương ứng. Cấu hình này chỉ mô tả một số **quy tắc truy cập URL** và chọn HTTP Basic. Nó không tự tạo user store, không xác định cách lưu mật khẩu, không kiểm quyền sở hữu từng order, và không cung cấp các quy tắc nghiệp vụ khác.

Chú ý **method + path**: GET /api/public/item được permitAll, nhưng POST /api/public/item không khớp matcher GET; với cấu hình trên, request có thể đi đến denyAll nếu không có quy tắc khác phù hợp. Thêm endpoint mới cũng cần policy rõ ràng, thay vì vô tình công khai do mẫu URL quá rộng.

Nếu dùng **nhiều SecurityFilterChain**, phải hiểu chain nào khớp request, thứ tự chain và có fallback chain phù hợp; một filter chain chỉ áp dụng cho /api/** không chứng minh mọi endpoint quản trị/actuator ở nơi khác đều đã được bảo vệ.

**Phân quyền theo role** không thay thế **phân quyền theo object/tenant**. Với một request đã đi qua authenticated(), Service vẫn phải xác minh principal được đọc/chỉnh sửa resource cụ thể. Với method security như @PreAuthorize, cần bật @EnableMethodSecurity và hiểu hành vi Spring proxy, bao gồm self-invocation.

## 9. Thực hành Java 17: chạy một HTTP server và quan sát status

Ví dụ sau **chạy độc lập với JDK 17+**, chỉ dùng thư viện chuẩn Java. Nó cố ý giả lập bốn tình huống: không có credential → 401; credential hợp lệ nhưng không phải admin → 403; admin → 200; sai HTTP method → 405. Đây là **mô phỏng HTTP semantics phục vụ học tập**, không phải cơ chế xác thực thực tế: token demo là hằng số so sánh chuỗi, không có chữ ký, expiry, user database, session hoặc HTTPS. Không đưa server minh họa này lên Internet.

Lưu thành **HttpSecuritySemanticsDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpSecuritySemanticsDemo {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );
        server.createContext("/api/admin", HttpSecuritySemanticsDemo::handle);
        server.start();

        try {
            URI uri = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort()
                + "/api/admin"
            );
            HttpClient client = HttpClient.newHttpClient();

            System.out.println(
                "anonymous GET: " + call(client, uri, "GET", null)
            );
            System.out.println(
                "user GET: " + call(client, uri, "GET", "user-demo")
            );
            System.out.println(
                "admin GET: " + call(client, uri, "GET", "admin-demo")
            );
            System.out.println(
                "admin POST: " + call(client, uri, "POST", "admin-demo")
            );
        } finally {
            server.stop(0);
        }
    }

    private static void handle(HttpExchange exchange) throws IOException {
        try {
            String method = exchange.getRequestMethod();

            if (!"GET".equals(method)) {
                exchange.getResponseHeaders().set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            String auth = exchange.getRequestHeaders()
                .getFirst("Authorization");

            boolean isUser = "Bearer user-demo".equals(auth);
            boolean isAdmin = "Bearer admin-demo".equals(auth);

            if (!isUser && !isAdmin) {
                exchange.getResponseHeaders().set(
                    "WWW-Authenticate", "Bearer realm=\"demo\""
                );
                exchange.sendResponseHeaders(401, -1);
                return;
            }

            if (!isAdmin) {
                exchange.sendResponseHeaders(403, -1);
                return;
            }

            byte[] bytes = "admin".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8"
            );
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        } finally {
            exchange.close();
        }
    }

    private static int call(
        HttpClient client, URI uri, String method, String token
    ) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri);

        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        if ("POST".equals(method)) {
            builder.POST(HttpRequest.BodyPublishers.noBody());
        } else {
            builder.GET();
        }

        return client.send(
            builder.build(),
            HttpResponse.BodyHandlers.discarding()
        ).statusCode();
    }
}
~~~

**Lệnh biên dịch và chạy:**

~~~bash
javac --add-modules jdk.httpserver HttpSecuritySemanticsDemo.java
java --add-modules jdk.httpserver HttpSecuritySemanticsDemo
~~~

**Stdout kỳ vọng chính xác:**

~~~text
anonymous GET: 401
user GET: 403
admin GET: 200
admin POST: 405
~~~

Giải thích:

1. Server bind **127.0.0.1**, port ngẫu nhiên do hệ điều hành cấp; client cùng chương trình tự lấy đúng port, vì vậy output không chứa số port không ổn định.
2. **GET không có Authorization** nhận 401 và header WWW-Authenticate, mô phỏng việc cần xác thực.
3. **GET với user-demo** được nhận diện là danh tính thử nghiệm nhưng thiếu quyền admin nên trả 403.
4. **GET với admin-demo** trả 200 cùng body admin, nhưng client trong ví dụ chỉ in status.
5. **POST** bị từ chối 405 vì endpoint minh họa chỉ hỗ trợ GET, có header Allow: GET. Ví dụ kiểm method **trước** credential để dạy semantics; Spring Security có thể trả mã khác nếu filter xác thực/phân quyền chặn request sớm hơn.

**Hạn chế cần nhớ:** việc so sánh chuỗi Bearer trong ví dụ không phải xác minh token. Khi xây dựng API thật, dùng cơ chế xác thực chuẩn của Spring Security (ví dụ HTTP Basic thích hợp cho demo hoặc OAuth2 Resource Server cho token) và HTTPS, rồi kiểm quyền theo chức năng và dữ liệu. Không áp dụng logic token hard-code vào Controller production.

## 10. Đọc HTTP bằng curl và DevTools

Đối với API đã có, dùng công cụ quan sát để nhìn **request thực tế** và **response thực tế**. Các lệnh ví dụ sau mang tính minh họa cho một server chạy ở localhost:8080 có endpoint tương ứng:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo-password http://localhost:8080/api/profile
curl -i -u reader:demo-password http://localhost:8080/api/admin
curl -I http://localhost:8080/api/public
curl -i -X OPTIONS http://localhost:8080/api/orders
~~~

- **-i** hiển thị status line và headers kèm body.
- **-I** yêu cầu HEAD (trong các trường hợp curl thông thường); HEAD trả metadata, không trả response body.
- **-u** giúp curl tạo HTTP Basic Authorization. Chỉ dùng credential demo trên môi trường được phép và kênh bảo vệ phù hợp; không nhập mật khẩu thật vào command history/chụp log.
- **-X OPTIONS** chỉ đổi method; nếu muốn kiểm **CORS preflight**, phải thêm Origin và Access-Control-Request-Method, có thể kèm Access-Control-Request-Headers.
- **curl -L** đi theo redirect. Khi debug 302/307/308, cần quan sát có redirect hay không và target/method nào được sử dụng; không tự động gửi credentials đến đích không tin cậy.

Với trình duyệt, tab **Network** hiển thị request URL/method, request headers, response status/headers, preflight, redirect và thời gian. Hạn chế chia sẻ bản ghi chứa Cookie, Authorization, query token hoặc nội dung riêng tư. Nếu ứng dụng dùng HTTPS ở giao diện công khai nhưng gọi API HTTP, trình duyệt có thể chặn hoặc tạo tình huống mixed content.

### 10.1. Kiểm tra bằng bốn chiều

Một bài kiểm thử bảo mật HTTP nên thay đổi đồng thời có kiểm soát:

1. **Danh tính:** ẩn danh, user thường, admin, token sai/hết hạn.
2. **Phương thức:** GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS theo hợp đồng API.
3. **Tài nguyên:** tài sản của chính mình, của người khác, khác tenant, ID không tồn tại.
4. **Payload và bối cảnh:** JSON sai, body lớn, token CSRF thiếu, Origin khác, request lặp, concurrent update.

Ví dụ ma trận:

| Tình huống | Kỳ vọng từ chính sách minh họa |
| --- | --- |
| Ẩn danh đọc /api/me | 401 với API challenge-based; 302 nếu form login được chọn |
| User thường gọi /api/admin | 403 |
| User A đọc đơn B | Không trả dữ liệu của B; 403/404 theo chính sách |
| User gửi POST vào API chỉ hỗ trợ GET | 405 nếu request đã tới handler của resource và không bị filter chặn trước |
| POST có content type sai | 415 khi chính sách xử lý media type từ chối |
| Request vượt quota | 429 hoặc cơ chế từ chối theo policy |
| Request file vượt giới hạn | 413 hoặc mã lỗi phù hợp từ gateway/app |
| Request dùng method thay đổi dữ liệu thiếu CSRF token khi CSRF áp dụng | 403 khi CSRF filter chặn |
| Request có quyền đầy đủ, hợp lệ | Status thành công và body/side effect đúng |

Khi test, **chỉ nhìn status là chưa đủ**: một API có thể trả 403 nhưng vẫn ghi DB, publish message hoặc lộ dữ liệu qua header/body. Cần xác minh dữ liệu **không bị thay đổi**, sự kiện không phát sai và response không chứa trường cấm.

## 11. Những lỗi HTTP bảo mật phổ biến

### 11.1. Chỉ kiểm URL, quên method

Cho phép **GET /api/resources/** để đọc không đồng nghĩa mọi POST/DELETE trên cùng URL an toàn. Bảo vệ theo method khi cần, đặt quy tắc rõ ràng và có fallback. Ngược lại, nếu dùng matcher quá hẹp mà endpoint khác không được bảo vệ, có thể mở nhầm bề mặt tấn công.

### 11.2. Dùng 401 và 403 lẫn lộn

Không có credential hoặc credential không hợp lệ thường là bài toán 401; đã có principal nhưng thiếu quyền thường là 403. Tuy nhiên do cơ chế login, filter order, exception handler và chính sách Resource Server, kết quả cần được xác minh với cấu hình thực tế.

### 11.3. Gọi API trả 200 rồi tự giấu lỗi trong JSON

Ví dụ mọi kết quả đều trả 200 với body {"error":"forbidden"} gây khó cho client, cache, monitoring và các kiểm thử HTTP. Với yêu cầu đã bị từ chối, dùng status phản ánh nguyên nhân phù hợp, body ngắn và thống nhất.

### 11.4. Tin dữ liệu từ header hoặc query để quyết định quyền

Header X-Role: ADMIN, tham số userId=..., Origin hay IP giả không tự chứng minh quyền. Quyền phải được rút ra từ identity đã xác thực và kiểm tra theo resource, tenant, operation. Metadata proxy chỉ tin theo chuỗi proxy được kiểm soát.

### 11.5. Cache dữ liệu riêng tư sai cách

Response GET thành công có thể bị browser/CDN/proxy lưu lại nếu policy không phù hợp. Xác định tài nguyên nào được cache, có phân biệt user không, có phải no-store không và liệu key cache có tách danh tính/tenant đúng hay không. Phản hồi 304 cũng cần được hiểu trong ngữ cảnh conditional request và authorization.

### 11.6. Nhầm CORS với bảo mật API

Trình duyệt có thể chặn JavaScript đọc response vì CORS; request vẫn có thể được gửi và công cụ ngoài trình duyệt vẫn gọi API. CORS không thay thế authentication, authorization, CSRF và kiểm soát side effects.

### 11.7. Vô tình lộ credentials qua URL, log và redirect

Không đặt access token hoặc password vào URL/query nếu có cách an toàn hơn. Log Authorization/Cookie phải được che/redact, và redirect target phải được kiểm soát. Cấu hình debug/HTTP tracing không nên ghi raw secret vào log production.

### 11.8. Để lỗi chi tiết hoặc security headers không hợp lý

Không trả stack trace, DB error, đường dẫn hệ thống, tài khoản nội bộ cho client. Cần security headers phù hợp cho HTML/UI và API, nhưng cũng tránh một cấu hình áp dụng máy móc phá luồng xác thực hoặc mở rộng quyền không kiểm soát.

## 12. Checklist khi thiết kế một endpoint

Trước khi đưa một endpoint vào sử dụng, có thể kiểm tra nhanh:

- **Method:** GET/HEAD chỉ đọc? POST/PUT/PATCH/DELETE có đúng ý nghĩa, xử lý lặp và concurrency? OPTIONS/CORS có cần hỗ trợ?
- **Danh tính:** xác thực bằng gì (cookie, Basic, Bearer)? Token/session được xác minh, truyền và hết hạn thế nào?
- **Quyền:** ai được gọi method/path, ai được thao tác resource/tenant cụ thể? Có test âm tính?
- **Request:** path/query/header/body/file có validation và giới hạn kích thước phù hợp? Có thể tin dữ liệu proxy nào?
- **CSRF/CORS:** client là trình duyệt hay máy khác; credential có tự được trình duyệt gửi không; preflight có đúng?
- **Response:** status phù hợp? Header cache/cookie/security đúng? Body không lộ dữ liệu khi lỗi?
- **Hạ tầng:** HTTPS từ đâu tới đâu; gateway có chỉnh URL/method/header; các endpoint quản trị có nằm ngoài chain không?
- **Quan sát:** log không lộ secret; request ID, audit, rate limit, timeout và retry phù hợp với mức độ rủi ro.

### Tự kiểm tra

1. Một user đăng nhập nhưng cố đọc đơn hàng của user khác nên được xử lý ở tầng nào và có thể nhận status nào? **Gợi ý:** Service/authorization theo object; 403 hoặc 404 tùy policy.
2. Tại sao DELETE có thể trả 204 lần đầu và 404 lần sau mà vẫn idempotent? **Gợi ý:** idempotency nói về hiệu ứng dự định, không đòi response giống nhau.
3. Vì sao GET làm thay đổi số dư tiền có thể nguy hiểm dù đã yêu cầu đăng nhập? **Gợi ý:** safe-method semantics, browser prefetch/link navigation và CSRF.
4. CORS chặn trình duyệt đọc response có nghĩa server không nhận request? **Gợi ý:** không; tách chính sách đọc response của browser với kiểm soát server.
5. Tại sao HTTP Basic trong header Authorization vẫn cần HTTPS? **Gợi ý:** Basic dùng Base64, không cung cấp mã hóa bí mật.
6. Một API trả 403 sau khi đã ghi dữ liệu trái phép có an toàn không? **Gợi ý:** không; kiểm tra side effects và đường xử lý quyền trước thao tác.
7. Khi nào 302 thường xuất hiện thay vì 401 ở Spring Security? **Gợi ý:** form login sử dụng AuthenticationEntryPoint chuyển tới trang đăng nhập.

## Kết luận

Đọc đúng **method, URL, headers, body, status và response headers** là nền tảng để hiểu Spring Security. **Authentication** xác định principal; **authorization** xác định principal được thực hiện hành động và truy cập dữ liệu nào; **HTTP status** báo kết quả cho client. Phương thức safe/idempotent, các nhóm 2xx/3xx/4xx/5xx, CORS/CSRF, cookie, caching và HTTPS đều ảnh hưởng trực tiếp tới thiết kế bảo mật. Một hệ thống an toàn phải thực thi quyền trước side effects, trả status nhất quán, bảo vệ credential và chứng minh các trường hợp bị từ chối bằng kiểm thử.
