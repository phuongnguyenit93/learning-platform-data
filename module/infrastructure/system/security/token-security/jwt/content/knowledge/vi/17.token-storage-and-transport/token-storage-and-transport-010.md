# Proxy, lịch sử trình duyệt, referrer và các điểm làm lộ token

> **Chương:** Lưu trữ và truyền  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung tập trung vào rò rỉ token trong quá trình truyền, chuyển hướng, ghi log và quan sát hệ thống; áp dụng cho HTTP, trình duyệt và hạ tầng trung gian nói chung, không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 1. Token có thể bị lộ ở đâu?

Một JWT thường được xem là bearer credential: ai sở hữu token và có thể gửi token đến resource server phù hợp có thể sử dụng quyền mà token đại diện, trong thời hạn và phạm vi được cấp. Vì vậy, bảo vệ chữ ký và mã hóa của JWT chưa đủ. Cần bảo vệ cả **đường đi của token** từ client đến resource server và mọi bản sao được tạo ra trong quá trình đó.

Token có thể xuất hiện ở nhiều nơi ngoài request mà ứng dụng dự định:

- URL, query string hoặc fragment.
- Browser history, bookmark, tab restore, clipboard và dữ liệu đồng bộ trình duyệt.
- HTTP `Referer` header khi điều hướng hoặc tải tài nguyên.
- Reverse proxy, load balancer, CDN, WAF và API gateway.
- Access log, application log, debug log, audit log và error report.
- APM, distributed tracing, crash reporting và analytics.
- Redirect response, trang lỗi, third-party script hoặc pixel.
- Cookie/header forwarding giữa các dịch vụ.
- Cache, message broker, support bundle, packet capture hoặc bản sao lưu.

Một token bị lộ ở bất kỳ điểm nào vẫn có thể bị sử dụng trong thời hạn còn hiệu lực. Kẻ tấn công không cần phá chữ ký JWT nếu có thể lấy được bearer token nguyên vẹn.

**Nguyên tắc:** truyền token trong kênh phù hợp, tránh đưa credential vào URL, giới hạn thành phần được nhìn thấy token, và loại bỏ hoặc che token khỏi log/trace/analytics.

## 2. Không đưa access token vào URL

### 2.1. Vì sao query string nguy hiểm?

Ví dụ không an toàn:

~~~text
https://api.example.test/invoices?access_token=eyJhbGciOi...
~~~

Query string thường được lưu hoặc quan sát ở nhiều tầng:

- Trình duyệt lưu URL trong history và có thể đồng bộ lịch sử.
- Proxy, gateway, WAF và web server thường ghi request target, bao gồm query string.
- Analytics, monitoring và error-reporting có thể thu thập URL đầy đủ.
- URL có thể được sao chép, gửi qua chat, đặt trong bookmark hoặc xuất hiện trong ảnh chụp màn hình.
- Khi trang điều hướng hoặc tải tài nguyên khác, URL nguồn có thể xuất hiện trong `Referer` tùy referrer policy.

RFC 6750 §2.3 mô tả cách truyền bearer token trong URI query parameter nhưng không khuyến nghị sử dụng vì URL có khả năng bị ghi lại. RFC 9700 §4.3.2 đưa ra yêu cầu rõ ràng hơn cho OAuth clients: **MUST NOT** truyền access token trong URI query parameter.

### 2.2. Dùng Authorization header

Với HTTP bearer token, phương thức thông thường là:

~~~http
GET /v1/invoices HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Header `Authorization` tránh đưa token vào URL và giảm nguy cơ token xuất hiện trong browser history hoặc referrer. Tuy nhiên, header vẫn có thể bị ghi lại bởi proxy, gateway, WAF, APM hoặc debug tooling nếu cấu hình thu thập request quá rộng.

Do đó:

- Chỉ gửi token đến origin dự kiến qua HTTPS.
- Không tự động chuyển tiếp `Authorization` sang origin khác.
- Redact header này tại mọi tầng ghi log và tracing.
- Không đưa giá trị token vào exception, metric label hoặc URL nội bộ.
- Giới hạn quyền đọc request headers ở các thành phần trung gian.

### 2.3. Fragment không phải giải pháp an toàn tuyệt đối

Ví dụ:

~~~text
https://client.example.test/callback#access_token=...
~~~

Phần fragment sau dấu `#` không được gửi trong HTTP request target đến web server. Tuy vậy, fragment vẫn có thể:

- Xuất hiện trong browser history.
- Được JavaScript đọc qua `window.location.hash`.
- Bị đọc bởi script bên thứ ba chạy trên cùng trang.
- Xuất hiện trong clipboard, screenshot, browser sync hoặc công cụ chẩn đoán phía client.
- Bị lưu trong telemetry phía trình duyệt nếu ứng dụng thu thập URL đầy đủ.

RFC 9700 §4.3.2 cũng lưu ý access token trả về qua implicit flow có thể xuất hiện trong browser history dưới dạng fragment. Không nên xem việc chuyển token từ query sang fragment là biện pháp thay thế cho một flow OAuth an toàn hơn.

Đối với OAuth, ưu tiên Authorization Code flow với PKCE và không chuyển access token qua URL. Khi nhận authorization response, tuân thủ chính xác response mode và biện pháp chống replay/mix-up theo profile đã chọn.

## 3. Browser history, bookmark và dữ liệu trình duyệt

### 3.1. URL nhạy cảm có thể tồn tại lâu hơn request

Nếu access token, authorization code hoặc credential khác xuất hiện trong URL, nó có thể được lưu ở:

- Lịch sử duyệt web.
- Danh sách tab gần đây và khôi phục phiên.
- Bookmark hoặc shortcut do người dùng tạo.
- Dữ liệu đồng bộ giữa nhiều thiết bị.
- Clipboard khi sao chép URL.
- Screenshot, screen recording hoặc công cụ hỗ trợ người dùng.
- Browser extension có quyền đọc tab/URL.
- Báo cáo crash hoặc telemetry của ứng dụng web.

Việc xóa token khỏi thanh địa chỉ sau khi trang tải không bảo đảm mọi bản sao đã biến mất. Browser history, log tại proxy hoặc telemetry có thể đã ghi nhận URL trước đó.

### 3.2. Redirect sang URL sạch chỉ là biện pháp giảm thiểu

Trong một số callback, ứng dụng có thể cần đọc authorization code hoặc tham số phản hồi trước khi chuyển người dùng đến URL sạch.

Ví dụ luồng khái niệm:

~~~text
GET /oauth/callback?code=<authorization-code>&state=<state>
    |
    | kiểm tra state, xử lý code theo giao thức
    v
302 Location: /account
~~~

Sau redirect, thanh địa chỉ hiển thị `/account`. Điều đó không xóa chắc chắn URL callback khỏi browser history hoặc các log đã được ghi trước redirect.

Nếu ứng dụng xử lý callback:

- Giữ callback page tối giản, không tải analytics, quảng cáo, pixel hoặc script không cần thiết.
- Đặt referrer policy nghiêm ngặt cho callback.
- Không render code/token vào HTML hoặc error message.
- Đổi URL hiện tại sang URL sạch sau khi xử lý thành công nếu phù hợp với ứng dụng.
- Bảo đảm authorization code dùng một lần, thời hạn ngắn và được ràng buộc với client/PKCE theo OAuth profile.
- Không ghi URL callback đầy đủ vào log.

Không dựa vào redirect hoặc thao tác thay URL ở client để thay thế việc ngăn credential xuất hiện trong URL ngay từ thiết kế flow.

### 3.3. Các biện pháp ở phía trình duyệt

- Không đặt access token hoặc refresh token trong query string.
- Hạn chế quyền của browser extension; không cài extension không đáng tin trên thiết bị xử lý tài khoản nhạy cảm.
- Tránh thu thập `location.href` đầy đủ trong analytics và error telemetry.
- Không đưa token vào nội dung hiển thị, link chia sẻ, QR code hoặc thông báo lỗi.
- Dùng trang callback tối giản, không tải tài nguyên từ bên thứ ba nếu không cần.
- Hướng dẫn người dùng không chia sẻ URL chứa authorization code hoặc credential.
- Với trang nhạy cảm, cân nhắc `Cache-Control: no-store`; lưu ý directive này không xóa browser history và không xóa log đã được tạo.

## 4. Referer và Referrer-Policy

### 4.1. Referer là gì?

`Referer` là HTTP request header cho biết URL nguồn đã dẫn đến request hiện tại. Tên header trong HTTP được viết là `Referer` (một chữ r), còn chính sách trình duyệt được gọi là `Referrer-Policy`.

Khi một trang điều hướng đến trang khác hoặc tải tài nguyên như ảnh, script, font hay iframe, trình duyệt có thể gửi thông tin referrer. Tùy chính sách, referrer có thể chứa origin, path và query string của trang nguồn.

Nếu URL nguồn có credential trong query string, một số cấu hình có thể làm credential xuất hiện trong request đến tài nguyên khác.

### 4.2. Các Referrer-Policy quan trọng

| Policy | Thông tin gửi đi | Nhận xét |
|---|---|---|
| `no-referrer` | Không gửi `Referer`. | Giảm tối đa rò rỉ referrer. |
| `same-origin` | Gửi full URL đã loại fragment và userinfo cho request cùng origin; không gửi sang origin khác. | Vẫn có thể lộ path/query trong cùng origin. |
| `strict-origin` | Chỉ gửi origin khi mức bảo mật đích phù hợp; không gửi khi HTTPS chuyển xuống đích không an toàn. | Không gửi path/query. |
| `strict-origin-when-cross-origin` | Cùng origin: có thể gửi full URL đã loại fragment/userinfo; khác origin: chỉ gửi origin khi phù hợp về bảo mật. | Đây là default phổ biến hiện nay, nhưng full URL vẫn có thể được gửi trong request cùng origin. |
| `unsafe-url` | Có thể gửi URL nguồn gồm path/query đến cả origin khác. | Không dùng cho trang nhạy cảm. |

Điểm dễ hiểu nhầm: `strict-origin-when-cross-origin` không có nghĩa là luôn loại bỏ query string. Với request cùng origin, policy này gửi URL đầy đủ đã loại fragment và thông tin user/password. Vì vậy, nếu trang có query chứa token, request cùng origin tới tài nguyên khác có thể mang query đó trong `Referer`.

W3C Referrer Policy định nghĩa chi tiết hành vi của từng policy. Với trang xử lý credential hoặc callback nhạy cảm, có thể đặt:

~~~http
Referrer-Policy: no-referrer
~~~

Nếu ứng dụng cần referrer để phân tích điều hướng, chọn policy hẹp nhất vẫn đáp ứng yêu cầu và tuyệt đối không đặt token trong URL.

### 4.3. Có thể đặt policy ở đâu?

Có thể áp dụng qua HTTP response header:

~~~http
HTTP/1.1 200 OK
Referrer-Policy: no-referrer
Content-Type: text/html
~~~

Hoặc dùng metadata trong HTML:

~~~html
<meta name="referrer" content="no-referrer">
~~~

Với một link cụ thể, có thể dùng:

~~~html
<a href="https://external.example.test/" rel="noreferrer">Mở trang bên ngoài</a>
~~~

Response header thường dễ áp dụng thống nhất cho toàn trang hơn. Cần kiểm tra policy thực tế trong browser và các request do script tạo ra; policy có thể được đặt ở cấp document hoặc điều chỉnh cho từng request.

### 4.4. Referrer-Policy không phải biện pháp thay thế cho URL sạch

Ngay cả khi dùng `no-referrer`, token trong URL vẫn có thể xuất hiện ở:

- Browser history và bookmark.
- Request URL đến server đầu tiên.
- Reverse proxy và access log.
- Analytics hoặc telemetry phía client.
- Screenshot, clipboard và browser sync.

Vì vậy, thứ tự ưu tiên là **không đưa token vào URL**, sau đó dùng Referrer-Policy như một lớp giảm thiểu bổ sung.

## 5. Redirect và third-party resources

### 5.1. Redirect chain

Một redirect có thể đưa browser đi qua nhiều origin:

~~~text
Client
  -> Authorization Server
  -> Redirect URI của ứng dụng
  -> Trang đích
  -> Third-party analytics
~~~

Các tham số trong URL callback có thể bị lưu ở history, log tại từng proxy hoặc được gửi làm referrer cho request tiếp theo tùy policy.

Rủi ro tăng khi:

- Redirect URI cho phép chuyển hướng đến URL tùy ý.
- Callback page tải script hoặc ảnh từ bên thứ ba.
- URL có authorization code hoặc token.
- Trang đích ghi lại URL đầy đủ vào analytics.
- Một redirect tiếp theo chuyển người dùng sang origin không được kiểm soát.

OAuth security BCP yêu cầu so khớp redirect URI chính xác theo quy tắc của RFC 9700 và cấm open redirector nhận URL đích tùy ý từ query parameter. Không để tham số redirect do client không tin cậy cung cấp quyết định nơi credential sẽ được chuyển đến.

### 5.2. Third-party JavaScript và tài nguyên nhúng

Một trang có thể tải:

- Analytics script.
- Tag manager.
- Advertising pixel.
- Chat widget.
- External font, image, video hoặc iframe.
- Error monitoring và session replay.

Nếu trang xử lý token hoặc authorization callback, mỗi script bên thứ ba là một thành phần có thể quan sát dữ liệu trang theo quyền thực thi của nó. Một script chạy cùng origin có thể đọc DOM và các giá trị JavaScript mà ứng dụng cung cấp; script có quyền truy cập location có thể đọc query/fragment tùy ngữ cảnh.

Biện pháp:

- Không tải third-party script trên trang callback hoặc trang hiển thị credential nếu không thật sự cần.
- Dùng Content Security Policy để giới hạn nguồn script, frame, connect và image.
- Kiểm soát thay đổi script bên thứ ba và dùng Subresource Integrity khi phù hợp.
- Không đưa token vào DOM, data attribute, analytics event hoặc session replay.
- Không truyền URL đầy đủ vào analytics.
- Dùng `Referrer-Policy: no-referrer` trên trang nhạy cảm.

CSP và SRI giúp giới hạn nguồn và tính toàn vẹn script, nhưng không thay thế việc tránh để token có thể truy cập từ JavaScript không cần thiết.

## 6. Reverse proxy, load balancer, CDN, WAF và API gateway

### 6.1. Vì sao hạ tầng trung gian có thể nhìn thấy token?

Trong kiến trúc phổ biến, request đi qua nhiều thành phần trước khi đến ứng dụng:

~~~mermaid
flowchart LR
    A["Browser / Client"] --> B["CDN / WAF"]
    B --> C["Load Balancer"]
    C --> D["Reverse Proxy / API Gateway"]
    D --> E["Application"]
    E --> F["JWT Validator"]
~~~

TLS bảo vệ dữ liệu trên đường truyền giữa các điểm kết thúc TLS. Tuy nhiên, tại mỗi thành phần terminate TLS, request có thể được đọc và xử lý ở dạng plaintext, bao gồm:

- URL và query string.
- `Authorization` header.
- `Cookie` và một số header tùy chỉnh.
- Request body nếu hệ thống ghi body hoặc kiểm tra nội dung.
- Response header như `Set-Cookie` hoặc response body nếu được capture.

Nếu một proxy terminate TLS rồi mở kết nối TLS mới đến upstream, proxy vẫn có thể nhìn thấy dữ liệu giữa hai chặng.

### 6.2. Những vị trí thường ghi token

| Thành phần | Dữ liệu có thể bị ghi | Kiểm soát cần có |
|---|---|---|
| CDN | URL, query, request headers, cache key, security event. | Không cache credential; redaction query/header; giới hạn quyền xem log. |
| WAF | Request URI, header, rule match, body sample. | Mask `Authorization`, `Cookie`, token parameters và dữ liệu nhạy cảm. |
| Load balancer | Request line, header, backend selection, trace metadata. | Tắt header logging nhạy cảm; chỉ log trường allowlist. |
| Reverse proxy | Request target, forwarded headers, upstream request/response. | Redact token và tránh dump request/response đầy đủ. |
| API gateway | Authorization context, policy decision, request/response. | Không lưu raw token; log kết quả xác minh và subject đã chuẩn hóa khi cần. |
| Application | Header, URL, exception, debug output. | Không log credential; không echo token trong lỗi. |
| Service mesh | Header capture, access log, trace span. | Cấu hình header allowlist/denylist; kiểm tra telemetry mặc định. |

### 6.3. Không tự động forward Authorization đến mọi upstream

Một proxy hoặc gateway có thể nhận token từ client rồi gọi dịch vụ khác. Không nên mặc định chuyển nguyên header `Authorization` đến mọi upstream.

- Chỉ forward đến dịch vụ cần token đó và được phép nhận token.
- Nếu dịch vụ downstream cần credential khác, dùng token exchange hoặc cơ chế service-to-service phù hợp.
- Xóa header nhạy cảm trước khi chuyển đến origin không liên quan.
- Không đưa token vào `X-Forwarded-*` hoặc custom header để “tiện debug”.
- Kiểm soát các header do client tự gửi để tránh giả mạo metadata tin cậy.
- Bảo đảm log ở cả gateway và upstream đều redacted.

Việc một proxy được phép nhìn thấy token không có nghĩa mọi thành phần phía sau cũng cần quyền đó.

## 7. Log, tracing, APM và analytics

### 7.1. Token có thể lọt vào log ở đâu?

Các hệ thống quan sát thường thu thập request để hỗ trợ điều tra và đo hiệu năng. Token có thể xuất hiện trong:

- Access log chứa request line và query.
- Debug log in toàn bộ request headers.
- Exception message chứa URL hoặc request object.
- Trace span attribute như `http.url`, `url.full`, `http.request.header.authorization`.
- APM transaction snapshot.
- WAF forensic sample.
- Crash report và browser telemetry.
- Analytics event chứa `location.href`.
- Support bundle hoặc bản dump khi điều tra sự cố.

Không chỉ application log mới cần redaction. Cần kiểm tra mọi collector, exporter, dashboard, archive, backup và nơi dữ liệu được gửi đến.

### 7.2. Trường cần loại bỏ hoặc che

Các trường nhạy cảm nên được loại bỏ, che hoặc thay bằng giá trị không thể sử dụng lại:

- `Authorization` và các header chứa bearer token.
- `Cookie`, `Set-Cookie` và session identifiers.
- Query parameter như `access_token`, `refresh_token`, `id_token`, `token`, `code`.
- OAuth `state`, `code_verifier` hoặc thông tin liên quan đến giao dịch xác thực.
- Request/response body có credential.
- URL callback đầy đủ nếu chứa mã hoặc dữ liệu nhạy cảm.

Ưu tiên cấu hình **allowlist trường được phép ghi** thay vì ghi tất cả rồi cố che các trường đã biết. Cách allowlist giảm rủi ro khi ứng dụng bổ sung một tham số mới mà pipeline redaction chưa nhận diện.

OWASP Logging Cheat Sheet khuyến nghị không ghi trực tiếp access token và session identification values; nếu cần theo dõi tương quan, dùng giá trị đã được mask, sanitize hoặc hash theo chính sách phù hợp.

### 7.3. Correlation ID thay cho token

Để liên kết log giữa các dịch vụ, dùng correlation ID hoặc trace ID ngẫu nhiên, không dùng bearer token làm request ID.

Ví dụ log an toàn:

~~~json
{
  "event": "jwt_validation_failed",
  "request_id": "req-8f19d3",
  "endpoint": "/v1/invoices",
  "reason": "INVALID_TOKEN",
  "issuer": "trusted-issuer-a",
  "duration_ms": 12
}
~~~

Không ghi nguyên token, authorization header hoặc plaintext. Nếu cần phân biệt các sự kiện của cùng một token trong điều tra, có thể tạo fingerprint bằng HMAC với khóa log riêng được bảo vệ. Fingerprint chỉ hỗ trợ tương quan, không phải bằng chứng xác minh token và không nên dùng làm metric label có cardinality cao.

### 7.4. Giới hạn truy cập log và trace

- Chỉ nhóm cần thiết mới được đọc log chứa metadata bảo mật.
- Áp dụng phân quyền, audit truy cập và thời hạn lưu trữ.
- Bảo vệ log khi truyền đến hệ thống tập trung.
- Kiểm soát nhà cung cấp APM/analytics và vị trí lưu trữ dữ liệu.
- Tắt capture request/response body nếu không cần.
- Kiểm tra export, backup và support bundle có giữ dữ liệu nhạy cảm hay không.
- Có quy trình xử lý nếu token đã lọt vào log: thu hồi token, giới hạn truy cập và xóa/expire bản sao theo chính sách lưu trữ.

## 8. Cookie và header forwarding

Token có thể được gửi trong header hoặc cookie tùy kiến trúc. Cả hai cách đều cần bảo vệ ở tầng proxy và application.

### 8.1. Authorization header

Nếu dùng bearer token trong `Authorization`:

- Chỉ gửi qua HTTPS.
- Không đưa header vào access log, trace hoặc analytics.
- Không forward qua domain/origin không tin cậy.
- Không copy header vào error report hoặc diagnostic dump.
- Hạn chế số thành phần terminate TLS có quyền đọc token.

### 8.2. Cookie

Nếu hệ thống đặt token hoặc session credential trong cookie, trình duyệt có thể tự động gửi cookie theo domain/path và thuộc tính cookie.

Các thuộc tính thường cần xem xét:

- `Secure`: chỉ gửi cookie qua kênh bảo mật.
- `HttpOnly`: ngăn JavaScript thông thường đọc cookie.
- `SameSite`: kiểm soát một phần việc gửi cookie trong ngữ cảnh cross-site.
- `Domain` và `Path`: thu hẹp phạm vi gửi cookie.
- `Max-Age`/`Expires`: giới hạn thời gian tồn tại.

Các thuộc tính này không ngăn proxy hoặc server nhận cookie ghi nó vào log. Vì vậy `Cookie` và `Set-Cookie` cũng phải được redaction. Cookie tự động gửi kèm request còn tạo rủi ro CSRF nếu thiết kế không có biện pháp phù hợp.

### 8.3. Header forwarding và trust boundary

Khi proxy chuyển request:

- Xác định header nào được giữ, xóa hoặc tạo lại.
- Không tin `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` do client tự gửi nếu chưa được proxy tin cậy chuẩn hóa.
- Không forward `Authorization` hoặc `Cookie` sang upstream không cần chúng.
- Xóa header chẩn đoán hoặc header nội bộ do client giả mạo.
- Dùng TLS giữa các chặng khi dữ liệu nhạy cảm đi qua mạng.
- Ghi rõ thành phần nào terminate TLS và thành phần nào được phép nhìn thấy token.

## 9. Cache và các điểm lưu tạm

Một token hoặc URL chứa token có thể bị lưu ngoài ý muốn trong cache hoặc kho trung gian.

Cần xem xét:

- Browser cache và history.
- CDN cache key có chứa query string.
- Reverse proxy cache.
- Shared cache giữa các người dùng.
- Service worker cache.
- Cache của ứng dụng hoặc thư viện HTTP.
- Message broker, retry queue và dead-letter queue.
- Database snapshot, backup và support export.

Với response chứa thông tin xác thực hoặc dữ liệu nhạy cảm, cân nhắc `Cache-Control: no-store` theo giao thức và threat model. Không cấu hình cache key dựa trên bearer token rồi lưu token trong metadata. Không đưa token vào message name, routing key hoặc dead-letter reason.

`no-store` là chỉ thị cho cache HTTP, không phải lệnh xóa mọi bản sao. Nó không xóa browser history, access log, trace hoặc dữ liệu đã được bên thứ ba thu thập.

## 10. Thiết kế một luồng truyền token ít rò rỉ

Ví dụ luồng API:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy/Gateway
    participant A as Application
    participant V as JWT Validator
    participant R as Resource

    C->>P: HTTPS request + Authorization: Bearer token
    Note over P: Redact Authorization trong access log
    P->>A: Forward chỉ đến upstream được phép
    Note over A: Không ghi token vào log/trace
    A->>V: Xác minh token trong memory
    V-->>A: Claims đã xác minh hoặc lỗi chung
    A->>R: Thực hiện policy/authorization
    R-->>C: Response không chứa token
~~~

Các nguyên tắc:

1. Client gửi token trong `Authorization` header qua HTTPS.
2. Proxy chỉ forward header đến upstream cần xác minh token.
3. Proxy và application redaction header trước khi ghi log hoặc trace.
4. Validator xác minh token trong memory, không lưu raw token vào cache/log.
5. Application kiểm tra authorization theo claims và policy hiện tại.
6. Response không echo token hoặc dữ liệu credential.
7. Monitoring dùng request ID/trace ID thay cho token.

Với OAuth browser flow, dùng Authorization Code với PKCE; không đặt access token trong URL. Trang callback không tải third-party resource không cần thiết và áp dụng Referrer-Policy phù hợp.

## 11. Xử lý khi phát hiện token đã bị lộ

Khi phát hiện token trong URL, log, trace hoặc hệ thống bên thứ ba:

1. **Xác định loại credential:** access token, refresh token, authorization code hay session cookie.
2. **Xác định phạm vi:** token nào, subject/client/issuer nào, thời gian bắt đầu và các hệ thống đã nhận dữ liệu.
3. **Đánh giá khả năng sử dụng:** thời hạn, audience, scope, sender constraint nếu có, và token còn active hay không.
4. **Thu hồi phù hợp:** revoke token/session/token family hoặc khóa liên quan theo phạm vi sự cố.
5. **Chặn rò rỉ tiếp diễn:** sửa cấu hình URL, proxy log, referrer policy, APM capture hoặc analytics.
6. **Giới hạn bản sao:** hạn chế quyền đọc log/trace, xóa hoặc expire dữ liệu theo chính sách và yêu cầu pháp lý.
7. **Kiểm tra dấu hiệu sử dụng trái phép:** xem xét request sử dụng token từ nguồn hoặc thời điểm bất thường.
8. **Cấp lại credential:** chỉ sau khi nguyên nhân lộ đã được khắc phục và trạng thái tài khoản được xác nhận.
9. **Xác minh:** thử lại end-to-end để bảo đảm token mới không xuất hiện ở URL, log hoặc trace.

Không chỉ xóa token khỏi URL hiện tại rồi coi sự cố đã kết thúc. Các bản sao có thể còn trong browser history, proxy log, telemetry, backup hoặc hệ thống của bên thứ ba.

## 12. Mã giả redaction trước khi ghi log

Mã giả sau minh họa nguyên tắc lọc dữ liệu nhạy cảm trước khi log. Đây không phải API của một thư viện cụ thể.

~~~text
function build_safe_request_log(request, correlation_id):
    safe_headers = allowlist_headers(
        request.headers,
        ["content-type", "accept", "user-agent", "x-request-id"]
    )

    return {
        "request_id": correlation_id,
        "method": request.method,
        "path": path_only(request.url),
        "headers": safe_headers,
        "authorization": "[REDACTED]",
        "cookie": "[REDACTED]"
    }

function log_validation_result(result, correlation_id):
    write_log({
        "event": "jwt_validation",
        "request_id": correlation_id,
        "outcome": result.safe_outcome,
        "reason_code": result.internal_reason_code
    })
~~~

Trong triển khai thực tế:

- Ưu tiên allowlist header và URL field cần thiết.
- Không chỉ redaction một danh sách query parameter cố định nếu ứng dụng có thể thêm tên credential khác.
- Không log raw request object hoặc exception chứa request URL.
- Đảm bảo redaction xảy ra trước khi dữ liệu được gửi đến collector.
- Kiểm thử redaction ở proxy, application, APM, WAF và analytics; không chỉ kiểm thử một logger.
- `reason_code` nội bộ không nên được trả nguyên vẹn cho client.

## 13. Ma trận kiểm thử các điểm làm lộ token

| Trường hợp | Kết quả mong đợi |
|---|---|
| Access token được truyền trong Authorization header qua HTTPS. | Được xử lý theo policy; header không xuất hiện trong log/trace. |
| Access token xuất hiện trong query string. | Client/endpoint không sử dụng cách truyền này; request bị từ chối hoặc xử lý theo policy bảo mật. |
| Trang callback chứa authorization code trong query. | Callback tối giản, không tải third-party script, log redacted và code được xử lý một lần. |
| URL nguồn có query nhạy cảm và trang dùng `strict-origin-when-cross-origin`. | Kiểm thử xác nhận request cùng origin có thể mang full referrer; không dựa vào policy này để bảo vệ token URL. |
| Trang nhạy cảm dùng `Referrer-Policy: no-referrer`. | Request phát sinh từ trang không gửi Referer. |
| Redirect từ callback sang URL sạch. | Token/code không xuất hiện trong log; kiểm tra browser history và callback handling riêng. |
| CDN/WAF ghi request URI. | Query nhạy cảm không được ghi hoặc đã được loại bỏ. |
| Reverse proxy ghi request headers. | Authorization/Cookie/Set-Cookie được redacted. |
| APM capture HTTP spans. | Không có bearer token, cookie hoặc URL query credential trong span attributes. |
| Analytics thu thập page URL. | Query/fragment nhạy cảm không được gửi. |
| Third-party script chạy trên callback page. | Không có script không cần thiết; CSP và referrer policy giới hạn rủi ro. |
| Cookie chứa session credential. | Cookie flags phù hợp và giá trị cookie không xuất hiện trong log. |
| Cache nhận response nhạy cảm. | Cache policy được cấu hình phù hợp; không lưu credential ngoài ý muốn. |
| Token đã lọt vào log. | Có quy trình revoke, giới hạn truy cập và xử lý bản sao. |
| Nhiều tầng proxy cùng ghi log. | Redaction được xác minh ở từng tầng, không chỉ ở application. |

## 14. Checklist thiết kế và vận hành

- [ ] Không truyền access token hoặc refresh token trong URI query parameter.
- [ ] Không dùng fragment như một nơi lưu token lâu dài.
- [ ] Dùng Authorization header qua HTTPS hoặc cơ chế truyền credential được profile cho phép.
- [ ] Callback page không tải third-party script/analytics không cần thiết.
- [ ] Referrer-Policy phù hợp; trang nhạy cảm cân nhắc `no-referrer`.
- [ ] Không dựa vào redirect hoặc `history.replaceState` để xóa mọi bản sao URL.
- [ ] CDN, WAF, load balancer, proxy và gateway đã redaction query/header nhạy cảm.
- [ ] Authorization, Cookie và Set-Cookie không xuất hiện trong log/trace.
- [ ] APM, analytics, crash reporting và session replay không thu thập credential.
- [ ] Không forward token đến upstream không cần hoặc không tin cậy.
- [ ] Cookie được cấu hình Secure, HttpOnly, SameSite và phạm vi Domain/Path phù hợp nếu sử dụng.
- [ ] Cache policy phù hợp cho response nhạy cảm.
- [ ] Log dùng correlation ID thay cho token.
- [ ] Có runbook xử lý token lộ và kiểm thử end-to-end trên toàn bộ đường truyền.

## 15. Câu hỏi tự kiểm tra

1. Vì sao access token trong query string có thể bị lộ dù request dùng HTTPS?
2. Browser history và fragment có thể giữ lại thông tin gì?
3. Fragment khác query string như thế nào về việc gửi trong HTTP request?
4. Vì sao `strict-origin-when-cross-origin` vẫn có thể gửi query trong Referer ở request cùng origin?
5. Khi nào nên dùng `Referrer-Policy: no-referrer`?
6. Vì sao redirect sang URL sạch không xóa chắc chắn browser history và proxy log?
7. Reverse proxy hoặc WAF có thể nhìn thấy token trong những trường hợp nào?
8. Vì sao APM và distributed tracing cần redaction riêng?
9. Vì sao không nên forward Authorization header đến mọi upstream?
10. `Cache-Control: no-store` có thể và không thể bảo vệ những nơi nào?
11. Khi token đã lọt vào log, vì sao cần xem xét revoke thay vì chỉ xóa log?
12. Cần kiểm thử những tầng nào để chứng minh token không xuất hiện trong URL, Referer, log và trace?

## 16. Tài liệu tham khảo

- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): phương thức truyền bearer token qua Authorization header và cảnh báo về URI query parameter (§2.1, §2.3).
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): credential leakage qua browser history (§4.3), access token không được truyền trong URI query parameter (§4.3.2), bảo vệ redirect-based flows và open redirectors.
- [W3C Referrer Policy](https://www.w3.org/TR/referrer-policy/): các chính sách `no-referrer`, `same-origin`, `strict-origin-when-cross-origin`, `unsafe-url` và thuật toán tạo Referer.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi trực tiếp vào log, bao gồm access token và session identifiers.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics của HTTP request headers, gồm Referer.
