# Bearer token qua Authorization header trên kết nối HTTPS

Bearer access token là credential: bất kỳ bên nào sở hữu token hợp lệ đều có thể sử dụng nó trong phạm vi quyền và thời hạn được cấp, trừ khi token được ràng buộc thêm với người gửi. Vì vậy, cách truyền token ảnh hưởng trực tiếp đến an toàn của API. Với OAuth 2.0 Bearer Token Usage, cách khuyến nghị là gửi token trong HTTP request header **Authorization** với scheme **Bearer**, trên kết nối **HTTPS/TLS** đã được xác thực đúng.

Bài học thuộc chương **Lưu trữ và truyền** của module **Security – JSON Web Token (JWT)**. Nội dung tập trung vào cách gửi bearer token an toàn giữa client và resource server, các ranh giới TLS/proxy, nguy cơ rò rỉ header, cách xử lý lỗi và kiểm thử; áp dụng cho browser, mobile, backend và API ở mọi nền tảng.

## 1. Bearer token là credential mang quyền truy cập

Bearer token có nghĩa là bên trình token có thể được chấp nhận như bên được cấp quyền nếu token hợp lệ và request đáp ứng chính sách. Resource server thường không yêu cầu client chứng minh quyền sở hữu một khóa riêng cho mỗi request trong mô hình bearer.

Một request điển hình:

~~~http
GET /v1/invoices/42 HTTP/1.1
Host: billing.example.org
Authorization: Bearer eyJ...example-token
Accept: application/json
~~~

Resource server đọc header Authorization, trích xuất token và xác minh theo profile đã cấu hình. Với JWT, việc xác minh thường bao gồm chữ ký, issuer, audience, thời hạn, loại token và các claims bắt buộc; sau đó API tiếp tục kiểm tra scope và quyền trên tài nguyên.

**Ai lấy được bearer token có thể thử dùng token đó.** Chữ ký JWT hợp lệ không chứng minh người gửi request là chủ thể hợp pháp. Nếu token bị sao chép, kẻ tấn công có thể phát lại token trong thời gian token còn được chấp nhận.

### 1.1. Những thuộc tính cần có khi truyền bearer token

- **Confidentiality in transit:** người nghe lén trên đường truyền không đọc được token.
- **Server authentication:** client xác minh đang kết nối đúng máy chủ dự kiến, không gửi token tới endpoint giả mạo.
- **Integrity in transit:** dữ liệu request và response không bị sửa trái phép trên kết nối.
- **Audience restriction:** token chỉ được chấp nhận bởi resource server dự kiến.
- **Leakage prevention:** token không xuất hiện trong URL, log, trace, analytics hoặc thông báo lỗi.
- **Limited exposure:** giảm thời gian sống, scope và số nơi có thể truy cập token.

HTTPS/TLS bảo vệ kênh truyền giữa hai đầu TLS. Nó không tự bảo vệ token tại browser, thiết bị, process, proxy sau khi giải mã TLS, log hoặc hệ thống quan sát.

## 2. Dùng Authorization header với scheme Bearer

RFC 6750 định nghĩa cách sử dụng bearer access token trong OAuth 2.0. Phương pháp khuyến nghị là gửi token trong request header:

~~~http
Authorization: Bearer <access-token>
~~~

Trong đó:

- **Authorization** là HTTP request field mang thông tin xác thực/ủy quyền.
- **Bearer** là authentication scheme chỉ ra cách trình credential.
- **access-token** là giá trị token được cấp cho client.

Tên header và scheme cần được viết đúng theo giao thức. HTTP field names không phân biệt hoa thường theo HTTP, nhưng client nên dùng dạng chuẩn để dễ quan sát và tương thích.

### 2.1. Ví dụ request đầy đủ

~~~http
GET /api/orders?limit=20 HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
Accept: application/json
User-Agent: ExampleClient/1.0
~~~

Ví dụ response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "items": [
    {
      "id": "order-1001",
      "status": "processing"
    }
  ]
}
~~~

Header Authorization không phải dữ liệu nghiệp vụ. Không đưa token vào query parameter, path hoặc JSON body chỉ để thuận tiện cho một thành phần trung gian.

### 2.2. Ví dụ với curl

~~~bash
curl --fail-with-body \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  --header "Accept: application/json" \
  https://api.example.org/v1/profile
~~~

Đây là ví dụ shell minh họa. ACCESS_TOKEN phải được lấy từ một nguồn bí mật phù hợp trong môi trường thực tế; không ghi token trực tiếp vào script, lịch sử lệnh, tài liệu chia sẻ hoặc log CI/CD. Tránh bật chế độ verbose/trace khi request có credential nếu đầu ra có thể lưu hoặc chia sẻ.

### 2.3. Client phải gửi token tới đúng origin

Trước khi gắn token vào request, client cần biết endpoint đích là gì và endpoint đó có được phép nhận token hay không. Không gửi cùng một bearer token tới mọi host chỉ vì request được chuyển hướng hoặc URL được lấy từ dữ liệu bên ngoài.

Các nguyên tắc:

1. Dùng API origin đã cấu hình hoặc được xác minh theo quy trình đáng tin cậy.
2. Chỉ gửi token tới resource server phù hợp với audience của token.
3. Không tự động chuyển tiếp Authorization header tới host khác sau redirect.
4. Không gắn token vào URL do người dùng hoặc nội dung response tùy ý cung cấp.
5. Nếu API có nhiều origin, quản lý allowlist origin và audience rõ ràng.

## 3. HTTPS/TLS là bắt buộc với bearer token

Bearer token có thể bị sử dụng bởi bất kỳ bên nào sở hữu nó. Nếu truyền token qua HTTP thuần, người có khả năng quan sát đường truyền có thể đọc và sao chép token. RFC 6750 yêu cầu sử dụng TLS để bảo vệ bearer token khi truyền.

### 3.1. Điều gì xảy ra nếu dùng HTTP?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant N as Mạng trung gian
    participant API as Resource Server
    C->>N: HTTP request + Authorization: Bearer token
    Note over N: Có thể đọc và sao chép token
    N->>API: Chuyển tiếp request
    N-->>N: Lưu bản sao token
    N->>API: Có thể phát lại request khác
~~~

Khi dùng HTTP thuần, header Authorization không được mã hóa ở tầng truyền tải. Chỉ cần một điểm quan sát mạng không đáng tin, token có thể bị lấy cắp.

Với HTTPS, TLS mã hóa dữ liệu trên đường truyền và xác thực server bằng chứng chỉ. Người nghe lén trên mạng không thể đọc header nếu TLS được thiết lập và xác minh đúng. Tuy nhiên, TLS không bảo vệ khỏi endpoint bị xâm nhập hoặc proxy có quyền giải mã.

### 3.2. Client phải xác minh chứng chỉ máy chủ

Một client an toàn cần:

- Xác minh chuỗi chứng chỉ tới trust anchor được chấp nhận.
- Kiểm tra hostname của URL khớp với Subject Alternative Name phù hợp trên chứng chỉ.
- Kiểm tra thời hạn chứng chỉ và trạng thái tin cậy theo chính sách của nền tảng.
- Dùng bộ trust store được quản lý đúng; không tắt xác minh chứng chỉ để “sửa lỗi kết nối”.
- Cập nhật hệ điều hành, runtime và trust store để theo kịp thay đổi chứng chỉ/CA.

Không bỏ qua cảnh báo certificate, không chấp nhận mọi chứng chỉ, không dùng callback xác minh luôn trả về thành công và không hạ xuống HTTP khi TLS thất bại. Các cách làm đó có thể khiến token bị gửi tới máy chủ giả mạo.

### 3.3. Phiên bản TLS và cấu hình

Trong triển khai hiện đại, ưu tiên TLS 1.3; TLS 1.2 vẫn có thể được chấp nhận khi cấu hình cipher suite và thuật toán an toàn. Không dùng SSL hoặc các phiên bản TLS đã lỗi thời. Tắt giao thức và thuật toán yếu theo chính sách bảo mật hiện hành.

TLS cần được cấu hình ở tất cả đoạn kết nối mang token. Nếu client gọi gateway qua HTTPS nhưng gateway gọi service nội bộ qua HTTP, token hoặc security context có thể bị lộ trên đoạn mạng nội bộ đó.

### 3.4. HSTS trong ứng dụng web

HTTP Strict Transport Security (HSTS) cho phép website yêu cầu browser chỉ truy cập domain qua HTTPS trong thời gian chính sách còn hiệu lực. HSTS giúp giảm nguy cơ browser bị điều hướng xuống HTTP sau khi đã nhận chính sách.

HSTS:

- Có ích cho website và domain do tổ chức kiểm soát.
- Cần được gửi qua HTTPS; browser không tin HSTS nhận qua kết nối HTTP không an toàn.
- Không thay thế TLS certificate validation.
- Không tự bảo vệ mobile app, backend client hoặc mọi kết nối service-to-service.
- Không làm an toàn một endpoint HTTPS giả mạo hoặc token đã bị lấy từ storage/log.

## 4. Vì sao không truyền token trong URL?

Không đặt bearer token trong query string hoặc path. Ví dụ sau là cách truyền không an toàn:

~~~http
GET /v1/profile?access_token=<access-token> HTTP/1.1
Host: api.example.org
~~~

URL thường được ghi nhận ở nhiều nơi hơn header Authorization:

- Browser history, bookmark và đồng bộ lịch sử.
- Web server, reverse proxy, CDN, load balancer và WAF logs.
- Analytics, monitoring, request tracing và crash reports.
- Header Referer khi browser điều hướng sang trang khác, tùy chính sách.
- Link được gửi qua email, chat, ticket hoặc copy vào clipboard.
- Hệ thống cache và công cụ hỗ trợ vận hành.

HTTPS mã hóa URL trên đường truyền nhưng không ngăn các endpoint ghi URL vào log hoặc lưu trong browser history. Vì vậy, gửi token qua query string vẫn có rủi ro kể cả khi URL bắt đầu bằng HTTPS.

### 4.1. Fragment cũng không phải nơi lưu token để gọi API

Phần fragment sau dấu # thường không được gửi trong HTTP request tới server, nhưng có thể được đọc bởi script trong trang, lưu trong lịch sử hoặc xuất hiện khi liên kết bị chia sẻ. Không dùng fragment làm kênh truyền access token tới resource server.

Trong một số luồng OAuth cũ, fragment từng được sử dụng trong implicit flow. Với ứng dụng mới, áp dụng Authorization Code Flow với PKCE theo best current practice; token được xử lý theo hướng dẫn của client và không đưa vào URL.

### 4.2. Dùng header thay cho query string

| Cách truyền | Đánh giá | Lý do |
| --- | --- | --- |
| Authorization: Bearer trong HTTPS request | Khuyến nghị | Cách chuẩn của RFC 6750; dễ cấu hình redaction ở proxy/log |
| access_token trong query string | Tránh sử dụng | Dễ xuất hiện trong history, URL log, Referer và hệ thống quan sát |
| Token trong path | Tránh sử dụng | Path thường được ghi log, cache key và hiển thị trong URL |
| Token trong fragment | Không dùng để gọi API | Không được gửi trong HTTP request thông thường và vẫn có thể lộ phía client |
| Token trong body | Không phải cách truyền bearer chuẩn cho resource request | Có thể gây mơ hồ, bị lưu trong body logs và không tương thích middleware chuẩn |

RFC 6750 có mô tả các phương thức truyền khác trong điều kiện hạn chế, nhưng client nên dùng Authorization header và resource server nên tránh hỗ trợ query token. Nếu phải tương thích một hệ thống cũ, cần giới hạn rõ, đánh giá rủi ro và có kế hoạch loại bỏ.

## 5. Các ranh giới TLS: gateway, proxy và service nội bộ

Trong kiến trúc thực tế, TLS có thể kết thúc ở CDN, WAF, load balancer hoặc API gateway. Tại điểm kết thúc TLS, request được giải mã để xử lý. Vì vậy, thành phần này có thể nhìn thấy Authorization header.

~~~mermaid
flowchart LR
    C["Client"] -->|"HTTPS / TLS"| E["Edge / WAF / Load balancer"]
    E -->|"HTTPS nội bộ hoặc mTLS"| G["API Gateway"]
    G -->|"TLS / mTLS"| A["Resource API"]
    A --> D["Database"]
    E --> L["Logs / telemetry"]
    G --> L
    A --> L
~~~

### 5.1. TLS termination không phải ranh giới vô hình

Khi TLS kết thúc tại edge:

- Edge có thể đọc token và toàn bộ header request.
- Nếu edge chuyển tiếp request qua HTTP, token có thể bị lộ trên mạng nội bộ.
- Nếu edge ghi toàn bộ header vào log, token có thể bị lộ dù kết nối client-edge dùng HTTPS.
- Nếu edge thêm header nhận diện người dùng, service phía sau phải biết header đó đến từ edge đáng tin và không cho client giả mạo.

Các biện pháp:

1. Dùng TLS trên mọi đoạn mạng có credential hoặc dữ liệu nhạy cảm; cân nhắc mTLS giữa workload.
2. Chỉ cho phép gateway kết nối tới service nội bộ qua mạng và danh tính workload được kiểm soát.
3. Xóa header xác thực do client tự gửi mà gateway không tin cậy trước khi thêm header nội bộ.
4. Không để service tin header user/role từ Internet nếu chưa được gateway xác thực và bảo vệ đường truyền.
5. Redact Authorization và cookie tại mọi lớp log, bao gồm edge, gateway, service và tracing agent.
6. Giới hạn quyền truy cập cấu hình gateway, secret, log và dữ liệu capture.

### 5.2. Không chuyển tiếp token sang service không nằm trong audience

Một gateway nhận access token dành cho Billing API không nên tự động gửi nguyên token đó tới Payment API hoặc một dịch vụ bên thứ ba. Audience là ranh giới người nhận; token không dành cho service đích phải bị từ chối.

Nếu service cần gọi service khác thay mặt người dùng, hãy thiết kế delegation hoặc OAuth Token Exchange để lấy token phù hợp với audience và scope của service đích. Không chuyển tiếp token gốc chỉ vì các service nằm trong cùng mạng nội bộ.

### 5.3. Header forwarding và trust proxy

Các header như X-Forwarded-For, Forwarded hoặc header định danh nội bộ có thể được dùng để truyền ngữ cảnh qua proxy. Chúng không tự đáng tin chỉ vì tên header có vẻ nội bộ.

- Chỉ chấp nhận giá trị được thêm bởi proxy/gateway nằm trong chuỗi tin cậy.
- Proxy biên phải xóa các bản do client tự gửi nếu chúng có thể gây nhầm lẫn.
- Service chỉ tin proxy đã xác thực bằng cấu hình mạng/danh tính phù hợp.
- Không dùng forwarded header làm bằng chứng thay thế cho JWT validation.
- Không chuyển tiếp Authorization tới host hoặc upstream không được phép.

## 6. Redirect có thể làm lộ Authorization header

Một endpoint có thể trả response redirect với Location trỏ tới URL khác. Client cần xử lý redirect cẩn thận vì request ban đầu có bearer token.

Ví dụ:

~~~http
HTTP/1.1 302 Found
Location: https://other.example.net/collect
~~~

Nếu client tự động theo redirect và gửi lại Authorization header tới origin khác, token có thể bị lộ cho host không đáng tin. Nhiều HTTP client có chính sách loại bỏ Authorization khi đổi origin, nhưng hành vi phụ thuộc thư viện và cấu hình.

Nguyên tắc:

- Không mặc định rằng mọi client đều xử lý redirect an toàn.
- Tắt tự động chuyển tiếp Authorization qua redirect cross-origin nếu không có yêu cầu rõ ràng.
- Nếu cần redirect, chỉ cho phép đích đã cấu hình và kiểm tra scheme, host, port theo chính sách.
- Không theo redirect từ HTTPS xuống HTTP.
- Không gửi token tới domain rút gọn, domain do người dùng nhập hoặc URL trong response chưa được tin cậy.
- Kiểm thử redirect 301, 302, 303, 307 và 308 vì hành vi method/header có thể khác theo client.

## 7. CORS, CSRF và Authorization header

CORS và CSRF thường bị nhầm lẫn khi browser gửi bearer token.

### 7.1. CORS kiểm soát việc browser cho phép JavaScript đọc response

Cross-Origin Resource Sharing (CORS) là cơ chế browser áp dụng để kiểm soát JavaScript từ origin này có được phép đọc response từ origin khác hay không. CORS không phải cơ chế xác thực người dùng và không bảo vệ bearer token khỏi XSS trong cùng origin.

Một request có Authorization header thường kích hoạt CORS preflight vì đây không phải safelisted request header. Browser có thể gửi OPTIONS trước để hỏi server có cho phép origin, method và header tương ứng không.

Ví dụ response preflight:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.org
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type
Vary: Origin
~~~

Chỉ cho phép origin cụ thể cần thiết. Tránh phản chiếu tùy ý giá trị Origin vào Access-Control-Allow-Origin. Không dùng wildcard cho cấu hình có credentials theo quy tắc CORS của browser.

### 7.2. Authorization header không tự giải quyết mọi CSRF

Nếu browser chỉ gửi access token trong Authorization header do JavaScript chủ động gắn vào request, trình duyệt thường không tự động đính kèm header này cho mọi request cross-site như cookie. Điều này giảm một số dạng CSRF truyền thống.

Tuy nhiên:

- Nếu access token được lưu trong browser và XSS xảy ra, mã độc cùng origin có thể đọc token hoặc dùng token để gọi API.
- Nếu hệ thống dùng cookie phiên hoặc cookie chứa token, browser tự gửi cookie theo quy tắc cookie; cần biện pháp CSRF.
- Một số ứng dụng có endpoint chấp nhận nhiều phương thức credential; phải đánh giá toàn bộ.
- CORS không phải biện pháp chống XSS và không thay thế kiểm tra quyền ở API.

### 7.3. Khi dùng cookie

Nếu kiến trúc dùng cookie phiên hoặc BFF:

- Đặt Secure để chỉ gửi cookie qua HTTPS.
- Đặt HttpOnly để JavaScript không đọc trực tiếp cookie.
- Chọn SameSite phù hợp với luồng ứng dụng.
- Dùng CSRF token hoặc biện pháp tương đương khi cần.
- Xác minh Origin/Referer theo chính sách ở các thao tác thay đổi trạng thái.

HttpOnly không ngăn XSS thực hiện request thay người dùng trong trang đã bị chiếm quyền. Secure không bảo vệ cookie sau khi endpoint hợp lệ nhận được nó.

## 8. Không để Authorization header xuất hiện trong log

Header Authorization chứa credential. Nếu log nguyên header, mọi người hoặc hệ thống có quyền đọc log có thể sao chép token và sử dụng nó.

### 8.1. Những nơi cần redaction

- CDN, WAF, reverse proxy và load balancer.
- API gateway và service mesh.
- Web server access log và application log.
- Error report, exception trace và request dump.
- Distributed tracing, APM, telemetry và analytics.
- Công cụ debug, support portal, ticket và bản ghi test.

Redact cả các trường có thể chứa credential khác như Cookie, Set-Cookie, refresh token, authorization code và client secret.

### 8.2. Ghi sự kiện bảo mật mà không ghi token

Thay vì log token nguyên vẹn, ghi các thông tin cần thiết:

~~~json
{
  "event": "api.authorization",
  "request_id": "req-8f31",
  "issuer": "https://identity.example.org",
  "subject_ref": "user-42",
  "audience": "https://billing.example.org",
  "scope_decision": "invoice:read",
  "result": "allowed",
  "timestamp": "2026-11-16T10:30:00Z"
}
~~~

Đây là log minh họa; chỉ ghi subject hoặc định danh khi chính sách quyền riêng tư cho phép. Không ghi raw token, refresh token hoặc giá trị bí mật. Nếu cần liên kết token trong điều tra, có thể dùng fingerprint HMAC với khóa log riêng và kiểm soát truy cập thay vì lưu token gốc.

### 8.3. Hạn chế debug trong môi trường production

- Không bật HTTP wire logging có thể ghi Authorization header trên production.
- Không đưa token vào exception message hoặc response lỗi.
- Không dùng ảnh chụp màn hình có token thật trong tài liệu.
- Không chia sẻ request dump chưa được scrub.
- Đặt quyền truy cập và retention cho log theo độ nhạy dữ liệu.
- Khi token đã lọt vào log, xem đó là credential có khả năng bị lộ và đánh giá việc thu hồi.

## 9. Resource server xử lý bearer token và trả lỗi

Resource server nên phân biệt lỗi xác thực token và lỗi quyền truy cập.

### 9.1. Token thiếu hoặc không hợp lệ

Nếu request không có credential hoặc token không hợp lệ, API thường trả 401 Unauthorized và có thể dùng WWW-Authenticate để mô tả scheme:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="billing-api", error="invalid_token"
Cache-Control: no-store
~~~

Không phản hồi token đã nhận, chữ ký, khóa, claims nhạy cảm hoặc chi tiết nội bộ làm lộ cơ chế xác minh.

### 9.2. Token hợp lệ nhưng thiếu quyền

Nếu token hợp lệ nhưng không đủ scope để thực hiện thao tác, API thường trả 403 Forbidden và có thể chỉ ra scope cần thiết theo RFC 6750:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="invoice:write"
Cache-Control: no-store
~~~

401 cho biết request chưa có credential hợp lệ theo yêu cầu; 403 cho biết credential được chấp nhận nhưng quyền không đủ theo chính sách. Cần tránh tiết lộ quá nhiều thông tin về tài nguyên hoặc tài khoản cho người không có quyền.

### 9.3. Không yêu cầu client gửi token qua nhiều vị trí

Một resource server nên có chính sách rõ ràng về phương thức truyền credential. Nếu nhận cùng lúc Authorization header và query token, hoặc nhiều Authorization header, server có thể không biết giá trị nào có thẩm quyền.

Nên:

- Chỉ chấp nhận bearer token trong Authorization header.
- Từ chối request có nhiều giá trị Authorization mâu thuẫn.
- Không fallback sang query token khi header sai hoặc thiếu.
- Không ghép các giá trị header lặp lại để tạo token mới.
- Không ghi token vào response hoặc redirect.

## 10. Browser, mobile và backend có những lưu ý khác nhau

### 10.1. Browser SPA

Browser là môi trường có thể chạy script của bên thứ ba và chịu ảnh hưởng của XSS. Nếu SPA giữ bearer token, mọi mã độc chạy trong origin có thể có khả năng sử dụng token.

- Cân nhắc Backend-for-Frontend (BFF): browser giữ session cookie, access/refresh token được giữ ở backend.
- Nếu SPA trực tiếp gửi token, giữ token trong bộ nhớ khi phù hợp và giảm thời gian tồn tại.
- Tránh lưu token lâu dài trong localStorage nếu có phương án phù hợp.
- Áp dụng CSP, output encoding, API DOM an toàn, kiểm soát dependency và script bên thứ ba.
- Không gửi token tới origin không được phép.
- Không đưa token vào URL hoặc log phía browser.

### 10.2. Ứng dụng native/mobile

- Dùng Authorization Code Flow với PKCE qua system browser/external user-agent theo hướng dẫn OAuth cho native app.
- Không nhúng client secret hoặc khóa phát hành token dùng chung trong gói cài đặt.
- Dùng HTTPS và xác minh chứng chỉ theo nền tảng.
- Bảo vệ token khi lưu bằng vùng lưu trữ an toàn của hệ điều hành khi phù hợp.
- Không ghi token vào log, clipboard, file cấu hình hoặc bản sao lưu không cần thiết.
- Kiểm tra redirect về ứng dụng và không chuyển tiếp token qua deep link không an toàn.

### 10.3. Backend và service-to-service

- Lưu client credential và token trong secret manager hoặc kho bí mật được kiểm soát.
- Dùng TLS cho kết nối tới authorization server và resource server.
- Cân nhắc mTLS hoặc workload identity giữa service.
- Không dùng token của user cho mọi service nếu cần delegation/token exchange.
- Chỉ gửi token tới đúng audience và upstream được phép.
- Redact header tại proxy, service mesh, log và tracing.
- Không đưa token vào biến môi trường tồn tại lâu nếu có lựa chọn secret management tốt hơn.

## 11. Ví dụ thực tế

### Tình huống A — Gửi token qua HTTPS header

Client gọi Billing API bằng Authorization Bearer trên HTTPS. API xác minh token và audience, sau đó kiểm tra scope invoice:read và quyền trên hóa đơn.

**Bài học:** đây là mô hình truyền chuẩn; HTTPS bảo vệ kênh, còn resource server vẫn phải xác minh token và phân quyền.

### Tình huống B — Token bị lộ trong query string

Ứng dụng đặt access token trong URL để một service trung gian dễ đọc. URL được lưu trong browser history, CDN log và analytics.

**Bài học:** không truyền token trong URL kể cả qua HTTPS. Dùng Authorization header và redaction.

### Tình huống C — Gateway giải mã TLS rồi gửi HTTP nội bộ

Client gọi gateway qua HTTPS. Gateway kết thúc TLS nhưng gửi nguyên Authorization header tới service qua HTTP trên mạng dùng chung.

**Bài học:** TLS phải bao phủ mọi đoạn mạng mang credential; dùng HTTPS nội bộ hoặc mTLS theo mô hình triển khai.

### Tình huống D — Redirect sang host khác

API trả 302 tới một host bên ngoài. HTTP client tự động chuyển tiếp Authorization header và token bị gửi tới host đó.

**Bài học:** kiểm soát redirect cross-origin, không chuyển tiếp token tới origin không được phép và không downgrade HTTPS xuống HTTP.

### Tình huống E — Token bị ghi vào APM

Ứng dụng bật request tracing để chẩn đoán lỗi. APM thu thập tất cả header, bao gồm Authorization, rồi nhiều người có quyền truy cập trace.

**Bài học:** redaction phải được cấu hình ở mọi lớp observability; nếu token đã bị ghi, đánh giá và thu hồi credential.

### Tình huống F — CORS được cấu hình quá rộng

API phản chiếu mọi Origin và cho phép Authorization header. Một trang không đáng tin có thể thực hiện các request cross-origin theo điều kiện browser cho phép và đọc response.

**Bài học:** allowlist origin cụ thể, giới hạn method/header, không coi CORS là xác thực hoặc chống XSS; API vẫn kiểm tra token và quyền.

## 12. Checklist triển khai bearer token

### Client và request

- [ ] Gửi token bằng Authorization: Bearer trên HTTPS.
- [ ] Chỉ gửi token tới origin và audience được phép.
- [ ] Không truyền token trong query string, path hoặc fragment.
- [ ] Không tự động chuyển tiếp Authorization qua redirect cross-origin.
- [ ] Không downgrade kết nối từ HTTPS xuống HTTP.
- [ ] Không bật debug/trace có thể ghi token trong môi trường production.

### TLS và mạng

- [ ] Xác minh certificate chain và hostname.
- [ ] Không tắt certificate validation hoặc chấp nhận mọi certificate.
- [ ] Dùng phiên bản TLS và cấu hình mật mã còn được chấp nhận.
- [ ] Bảo vệ mọi đoạn mạng từ client tới edge, gateway và service.
- [ ] Dùng mTLS khi cần xác thực workload hai chiều.
- [ ] Quản lý trust proxy và header forwarding.

### Gateway, API và logging

- [ ] Resource server chỉ chấp nhận phương thức credential đã quy định.
- [ ] Từ chối Authorization header lặp hoặc mâu thuẫn.
- [ ] Xác minh chữ ký, issuer, audience, thời hạn, loại token và claims.
- [ ] Kiểm tra scope và quyền trên tài nguyên.
- [ ] Không chuyển token tới service không nằm trong audience.
- [ ] Redact Authorization, Cookie, Set-Cookie và token khỏi log/trace.
- [ ] Dùng 401 cho credential không hợp lệ và 403 cho quyền không đủ theo chính sách.

### Browser và ứng dụng

- [ ] Đánh giá XSS và nơi lưu token trong browser.
- [ ] Cân nhắc BFF cho ứng dụng browser.
- [ ] Cấu hình CORS với origin, method và header cụ thể.
- [ ] Nếu dùng cookie, có Secure, HttpOnly, SameSite và CSRF protection phù hợp.
- [ ] Native app dùng PKCE và system browser theo hướng dẫn OAuth.
- [ ] Bảo vệ token trong secure storage của thiết bị khi cần.

## 13. Kiểm thử bảo mật đường truyền

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Client gọi endpoint HTTP | Bị chặn hoặc chuyển hướng an toàn trước khi token được gửi; không gửi bearer token qua HTTP |
| Certificate không hợp lệ hoặc hostname không khớp | Client từ chối kết nối |
| Request HTTPS tới đúng API với token hợp lệ | API xác minh và xử lý theo quyền |
| Token đặt trong query string | API từ chối phương thức truyền không được hỗ trợ; không ghi token vào log |
| Authorization header bị lặp | Request bị từ chối hoặc xử lý theo chính sách rõ ràng, không chọn giá trị mơ hồ |
| Redirect cross-origin | Token không được chuyển tiếp tới origin mới |
| Redirect HTTPS xuống HTTP | Client không gửi lại token |
| Gateway chuyển request nội bộ | Đoạn mạng mang token vẫn được bảo vệ |
| Log/tracing thu thập request | Authorization và cookie được redacted |
| Token sai audience | Resource server từ chối |
| Token hợp lệ nhưng thiếu scope | API từ chối quyền theo chính sách |
| CORS từ origin không được phép | Browser không được cấp quyền đọc response; API vẫn xác minh request |
| Token bị lộ trong log thử nghiệm | Có thể thu hồi token và xác định phạm vi log đã lưu |

Kiểm thử cần bao gồm cấu hình client, gateway, CDN, service mesh, API và hệ thống quan sát. Chỉ kiểm tra request browser tới API là chưa đủ nếu token còn đi qua nhiều hop.

## 14. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Cách chuẩn để gửi OAuth bearer access token tới resource server là gì? | Authorization request header với scheme Bearer trên HTTPS/TLS. |
| HTTPS có làm token an toàn sau khi tới gateway không? | Không. Gateway kết thúc TLS có thể đọc token; log và kết nối nội bộ vẫn cần bảo vệ. |
| Có nên truyền access token trong query string nếu URL dùng HTTPS không? | Không. URL vẫn có thể bị lưu trong history, log, analytics hoặc Referer. |
| Chữ ký JWT có ngăn người khác phát lại bearer token bị sao chép không? | Không. Token nguyên vẹn vẫn có thể được dùng lại trong thời gian được chấp nhận. |
| CORS có phải cơ chế xác thực token không? | Không. CORS là chính sách browser về việc JavaScript đọc response cross-origin. |
| Authorization header có tự động được browser gửi như cookie không? | Không theo cách cookie tự động được đính kèm; JavaScript/client thường phải chủ động thiết lập header. |
| Có thể tắt xác minh chứng chỉ khi gặp lỗi TLS không? | Không. Điều đó có thể khiến token bị gửi tới endpoint giả mạo. |
| Gateway có thể chuyển nguyên token tới bất kỳ service nội bộ nào không? | Không. Phải tôn trọng audience và ranh giới tin cậy; dùng delegation/token exchange khi cần. |
| Có nên ghi Authorization header vào log để debug không? | Không. Redact token và ghi metadata an toàn phục vụ điều tra. |
| Khi token hợp lệ nhưng thiếu scope, API thường trả lỗi nào? | 403 Forbidden; 401 dành cho credential không hợp lệ hoặc thiếu theo yêu cầu xác thực. |

## 15. Ghi nhớ

- Bearer token là credential: ai sở hữu token hợp lệ có thể thử sử dụng nó.
- Gửi token bằng **Authorization: Bearer** trên **HTTPS/TLS** đã xác minh đúng.
- Không truyền token trong URL, query string, path hoặc fragment.
- TLS bảo vệ dữ liệu trên từng kết nối; endpoint, TLS termination, proxy, log và telemetry vẫn có thể nhìn thấy token.
- Xác minh certificate chain và hostname; không tắt kiểm tra chứng chỉ để bỏ qua lỗi.
- Kiểm soát redirect, header forwarding và audience; không chuyển tiếp token tới origin/service không được phép.
- CORS không phải cơ chế xác thực và không thay thế bảo vệ XSS hoặc phân quyền.
- Redact Authorization và cookie ở mọi lớp logging/observability.
- Resource server phải xác minh token và quyền; bearer token bị sao chép vẫn có thể bị replay.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 6750 – The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 8446 – The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 9325 – Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325)
- [RFC 6797 – HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797)
- [RFC 8705 – OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 – OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
