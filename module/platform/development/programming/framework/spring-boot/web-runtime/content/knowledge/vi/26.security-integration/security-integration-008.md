# Header bảo mật, HTTPS và tránh làm lộ dữ liệu qua phản hồi lỗi

> **Ngữ cảnh:** Spring Boot web-runtime → **Tích hợp bảo mật**. Bài học sử dụng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x**, giải thích các **HTTP security response headers**, HTTPS/TLS ở máy chủ nhúng hoặc reverse proxy, và thiết kế **phản hồi lỗi không làm lộ chi tiết nội bộ**. Trọng tâm là biện pháp phối hợp, không phải công thức “thêm vài header là hệ thống an toàn”. Ví dụ MVC dùng Tomcat mặc định; WebFlux/Reactor Netty có ghi chú riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **HTTP header bảo mật**, **HTTPS/TLS**, **authentication/authorization**, **CORS**, **CSRF**, **input validation** và **error handling**; hiểu mỗi lớp giải quyết vấn đề khác nhau.
2. Giải thích đúng vai trò của `Strict-Transport-Security` (HSTS), `Content-Security-Policy` (CSP), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` và `Cache-Control`.
3. Nhận biết **những header Spring Security tự thêm** trong cấu hình mặc định, header phải tự đặt và khác biệt giữa HTTP request với HTTPS request.
4. Cấu hình HTTPS bằng **PEM SSL bundle** cho embedded Spring Boot server hoặc đặt TLS termination tại ingress, hiểu rủi ro của `Forwarded`/`X-Forwarded-Proto` từ proxy không tin cậy.
5. Thiết kế response lỗi có **HTTP status chính xác**, schema ổn định, thông điệp an toàn, `requestId` để điều tra, không xuất stack trace, tên class, SQL, URL nội bộ, token hay PII.
6. Chạy ứng dụng Spring Boot MVC có SecurityFilterChain, CSP và các security headers, ba loại lỗi 400/404/500 với `ProblemDetail`; kiểm chứng bằng curl và MockMvc.
7. Phân biệt sự khác nhau của lỗi từ controller, Spring MVC exception resolver, Spring Security authentication/authorization entry points, Servlet container và reverse proxy.
8. Kiểm thử HTTP→HTTPS, HSTS, browser CSP enforcement, header consistency trên 2xx/4xx/5xx, ngăn cache dữ liệu nhạy cảm và không làm gián đoạn chức năng hợp lệ.

## 2. Bức tranh tổng thể về phòng thủ nhiều lớp

Một ứng dụng có thể trả response qua nhiều thành phần:

~~~text
Browser / Mobile Client / API Client
          |
          | HTTPS/TLS
          v
CDN / WAF / Ingress / Reverse Proxy
          |                 |
          | headers?        | TLS termination?
          v                 v
Embedded Tomcat / Reactor Netty
          |
          v
Spring Security Filter Chain
          |    authn/authz, CSRF, security headers
          v
Spring MVC / WebFlux Request Handling
          |    validation, exception resolution, ProblemDetail
          v
Service / Database / Downstream
          |
          v
Response 2xx / 4xx / 5xx
          |
          +--> headers + status + body + cookies
          |
          v
Browser enforces supported headers / Client sees error
~~~

Ba nhóm công cụ chính của bài này:

- **HTTPS/TLS** bảo vệ kết nối khỏi nghe lén và sửa đổi, xác minh danh tính server dựa trên certificate chain và hostname khi client kiểm tra đúng. Nó **không** tự loại bỏ SQL injection, dữ liệu dư thừa trong JSON hoặc lỗ hổng authorization.
- **Security response headers** cho trình duyệt biết các hạn chế khi tải/chạy/nhúng tài nguyên, sử dụng cache, truyền referrer, hoặc bắt buộc chuyển HTTP thành HTTPS. Tác động phụ thuộc header, browser, context và các proxy ở giữa.
- **Error response hygiene** giới hạn thông tin được phép đưa ra ngoài khi có lỗi, trong khi phía server giữ dữ liệu chẩn đoán cần thiết ở kênh logs/traces có quyền truy cập và retention phù hợp.

**Điểm cốt lõi:** TLS mã hóa một error response; nếu chính body đó chứa chuỗi kết nối database hay access token, TLS vẫn vận chuyển **chính xác dữ liệu nhạy cảm ấy đến client**. Ngược lại, response lỗi đã được làm sạch nhưng gửi qua HTTP plaintext vẫn có thể bị nghe lén trên đường truyền. Cần cả hai.

## 3. Header bảo mật là gì và áp dụng ở đâu?

HTTP response có status line, headers và body. Ví dụ minh họa, không phải mọi header đều được Spring tự cung cấp:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; object-src 'none'
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()

{"status":"ok"}
~~~

Header có thể được viết bởi Spring Security, controller, servlet filter, web server, ingress hoặc CDN. Nếu nhiều tầng cùng ghi một header với giá trị khác nhau, kết quả có thể khó đoán hoặc bị trình duyệt bỏ qua. Hãy xác định **header owner** và kiểm tra response qua URL public thực tế.

### Header bảo mật không giống request header

| Nhóm | Ví dụ | Ai thường đặt | Dùng làm gì |
|---|---|---|---|
| Response security | CSP, HSTS, X-Frame-Options | Server/ingress | Chính sách bảo vệ trình duyệt khi xử lý response |
| Response caching | Cache-Control, Vary | Server/CDN | Điều khiển bộ nhớ đệm và representation |
| Request context | Origin, Authorization, Cookie | Browser/client | Thông tin cho server ra quyết định, không tự là quyền truy cập |
| Proxy forwarding | Forwarded, X-Forwarded-Proto | Trusted proxy | Truyền thông tin scheme/host/client gốc qua các hop |
| Error body fields | title, status, detail, requestId | API error handler | Cung cấp lỗi có kiểm soát, không phải HTTP headers bắt buộc |

Không nhét stack trace vào `X-Error-Detail` rồi coi body đã sạch. **Header cũng là dữ liệu client thấy được**, có thể bị log ở client/proxy. Cần kiểm tra cả header values, redirects, cookies, body, filenames, caching và trailers.

## 4. Header nào Spring Security mặc định cung cấp?

Với Spring Security servlet/web security configuration còn giữ header defaults, tài liệu Security trình bày nhóm mặc định tiêu biểu:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
~~~

**HSTS chỉ được thêm khi request được nhận diện là HTTPS/secure.** Nếu dùng HTTP plaintext ở localhost, không thấy HSTS có thể là hành vi đúng. Nếu request đến Spring từ ingress qua HTTP nhưng người dùng truy cập HTTPS ngoài internet, cần thiết kế TLS termination và forwarded-header trust đúng; nếu không, ứng dụng có thể không coi request là secure.

Một số điểm cần nhớ:

- **CSP không được Spring Security tự tạo mặc định**, vì một chính sách phù hợp phụ thuộc tài nguyên thực của từng ứng dụng.
- **Referrer-Policy không tự được bổ sung theo một giá trị phù hợp cho mọi app**; ứng dụng có thể đặt rõ theo rủi ro.
- **Permissions-Policy** thường cần cấu hình chủ động nếu muốn hạn chế browser features.
- Các mặc định có thể bị thay đổi khi tự viết `SecurityFilterChain`, tắt header writers, thêm filter khác hoặc qua proxy. **Kiểm tra effective response**, đừng dựa duy nhất vào danh sách dependency.
- Spring Security có thể không ghi `Cache-Control` của mình nếu response đã có chính sách cache do ứng dụng cung cấp; nhờ vậy tài nguyên tĩnh công khai có thể được cache phù hợp. Đây là lý do cần kiểm tra header thực thay vì nghĩ Security “ghi đè tất cả”.
- `X-XSS-Protection: 0` không phải lỗi bảo mật: bộ lọc XSS kiểu cũ của trình duyệt đã lỗi thời và có thể gây vấn đề; phòng chống XSS hiện đại ưu tiên **output encoding, CSP, sanitization**, không bật lại XSS auditor cũ.

**Đừng làm mất defaults chỉ vì muốn thêm một header.** Trong DSL, có thể thêm CSP và Referrer-Policy, giữ các writers còn lại, thay vì `headers.disable()` hoặc tắt cả security filter.

## 5. HSTS: yêu cầu trình duyệt ưu tiên HTTPS cho hostname

`Strict-Transport-Security` là chính sách trình duyệt ghi nhớ rằng một hostname phải được truy cập qua HTTPS trong khoảng thời gian nhất định, sau khi nhận policy trong bối cảnh HTTPS hợp lệ.

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Ý nghĩa:

- `max-age=31536000`: policy có tuổi thọ một năm tính theo giây, theo semantics của HSTS.
- `includeSubDomains`: mở phạm vi HSTS sang subdomains; chỉ bật khi **toàn bộ subdomain liên quan** đã hỗ trợ HTTPS đáng tin.
- `preload`: tín hiệu đăng ký preload với chương trình/browser có hỗ trợ; đây là cam kết quản trị domain, **không** tự động khiến mọi browser đưa domain vào preload list.

### Vì sao HSTS quan trọng nếu đã redirect HTTP→HTTPS?

Nếu client lần đầu truy cập `http://example.test`, bước HTTP ban đầu có thể bị kẻ tấn công trên mạng thao túng **trước khi** client nhận redirect 301/308 sang HTTPS. Khi trình duyệt đã biết HSTS hoặc domain được preload, nó có thể chủ động nâng request lên HTTPS ngay từ đầu, giảm cơ hội downgrade/SSL stripping.

Nhưng HSTS **không thay thế**:

- Cấp certificate đúng hostname/SAN và chain CA đáng tin.
- Redirect HTTP→HTTPS cho những clients chưa có HSTS policy.
- Bảo vệ proxy hop nếu TLS terminate trước backend.
- Cookies `Secure`, `HttpOnly` và `SameSite` theo nhu cầu.
- Kiểm tra mixed content/CSP, vì trang HTTPS vẫn có thể cố tải tài nguyên không an toàn.

### HSTS không được công nhận từ HTTP

Nếu server trả `Strict-Transport-Security` trong một HTTP plaintext response, browser tuân chuẩn không coi đó là nguồn đáng tin để thiết lập HSTS. Spring Security mặc định chỉ thêm HSTS cho **HTTPS request**; thêm một filter ép HSTS lên HTTP không tạo hiệu lực mong đợi.

### Chiến lược rollout production

Trước khi bật `includeSubDomains` và nhất là `preload`, kiểm kê các subdomains, certificate expiry, custom ports, cổng admin cũ và môi trường legacy. Một chính sách quá rộng có thể khóa đường truy cập hợp lệ khi các host chưa sẵn sàng HTTPS. Có thể rollout một `max-age` ngắn trước để đánh giá, tăng dần sau khi đã bảo đảm mọi host tương thích. Thay đổi HSTS đã được browser nhớ **không thể thu hồi tức thì trên mọi client**.

## 6. Content-Security-Policy (CSP): hạn chế nguồn và hành vi tài nguyên

CSP cho browser biết tài nguyên script/style/image/connect/frame được phép tới từ đâu, và có thể hạn chế iframe embedding, form submission, base URI cùng một số hành vi liên quan. Nó hỗ trợ giảm tác động XSS, nhưng **không thay thế việc encode output hay validate input**.

Ví dụ một chính sách tương đối chặt cho trang chỉ dùng tài nguyên same-origin:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Diễn giải:

| Directive | Ý nghĩa | Lưu ý |
|---|---|---|
| `default-src 'self'` | Fallback source list cho những loại tài nguyên dùng default-src | Không tự giới hạn mọi loại directive; một số phải khai báo riêng |
| `script-src 'self'` | Chỉ tải/chạy scripts từ nguồn được liệt kê trong những tình huống thông thường | Inline scripts có thể bị chặn nếu không dùng nonce/hash phù hợp |
| `object-src 'none'` | Không cho plugin-style object/embed được chỉ định | Thường hữu ích vì kiểu nội dung cũ tiềm ẩn rủi ro |
| `base-uri 'self'` | Hạn chế URI trong thẻ `<base>` của HTML | Giảm khả năng thay URL resolution không mong đợi |
| `frame-ancestors 'none'` | Không cho trang bị nhúng bởi bất kỳ ancestor frame nào | Chính sách chống clickjacking hiện đại; không được thay bởi default-src |
| `form-action 'self'` | Hạn chế đích form submission | Không phải same-origin policy chung cho mọi fetch |
| `connect-src 'self'` | Hạn chế nơi `fetch`/WebSocket/XHR kết nối | Có thể cần allowlist cho API khác origin; **không thay thế CORS** |
| `img-src 'self' data:` | Hạn chế nguồn ảnh, có thể cho phép data URL khi cần | Đừng cấp rộng hơn ứng dụng dùng |
| `upgrade-insecure-requests` | Gợi ý browser nâng URL resource không an toàn theo CSP semantics | Không thay thế TLS config hoặc HSTS cho toàn hostname |

**Mỗi ứng dụng phải thiết kế CSP theo thực tế.** Một SPA tải scripts từ CDN, styles inline và gửi API tới origin khác có thể bị hỏng nếu copy nguyên `default-src 'self'`. Cần kiểm kê asset endpoints, fonts, web sockets, analytics, third-party widgets trước khi bật enforcing policy.

### Vì sao không nên tùy tiện dùng unsafe-inline?

Cho phép `'unsafe-inline'` trong `script-src` làm yếu một phần phòng thủ XSS. Nếu phải dùng inline scripts, xem xét CSP nonces/hashes theo từng response, không tạo nonce cố định dùng cho mọi request. Dynamic CSP với nonce phải phối hợp chặt với HTML renderer và cache policy; một giá trị static nonce không đem lại lợi ích của nonce ngẫu nhiên được quản lý đúng.

### Thử với Content-Security-Policy-Report-Only

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

Report-only giúp quan sát vi phạm mà không chặn theo policy đó, phù hợp giai đoạn migration. Một request có thể nhận đồng thời **enforcing CSP** và **report-only CSP**; không phải hai header tự triệt tiêu nhau. Đường report endpoint phải có auth/rate-limit/privacy/retention thích hợp vì các báo cáo có thể chứa URL hoặc chi tiết có tính nhạy cảm.

Đặc biệt với API thuần JSON, một CSP trên JSON response thường **không thay thế** CSP của trang HTML frontend đang chạy scripts. Cần đặt CSP ở **response document thực sự được browser render**, thường là HTML của frontend, và kiểm thử trong browser. Một CSP trên controller trả JSON không chứng minh UI đã có CSP.

## 7. X-Frame-Options và frame-ancestors chống clickjacking

**Clickjacking** là kiểu dẫn dụ người dùng click một thành phần giao diện thật bị che hoặc đặt trong frame của trang khác. Hai lựa chọn cơ bản:

~~~http
X-Frame-Options: DENY
~~~

Browser không nên cho trang hiển thị trong frame. `SAMEORIGIN` cho phép các frame cùng origin theo semantics của header. Đối với nhiều ứng dụng admin, `DENY` là mặc định an toàn; Spring Security đặt giá trị này theo mặc định.

CSP `frame-ancestors 'none'` hoặc allowlist tương ứng là cách biểu đạt hiện đại và linh hoạt hơn. Không coi `X-Frame-Options` là cách cho phép danh sách hostname tùy ý: cơ chế cũ có giới hạn. Nếu ứng dụng thật sự cần embed trong portal hợp pháp, thiết kế `frame-ancestors` allowlist và cân nhắc fallback `SAMEORIGIN`/container behavior; không tắt bảo vệ cho tất cả chỉ để sửa một iframe.

**Không nhầm `frame-ancestors` với `frame-src`:** một cái kiểm soát ai được nhúng *trang hiện tại*, cái kia kiểm soát những frame mà *trang hiện tại* được tải.

## 8. X-Content-Type-Options: nosniff

Header này yêu cầu browser không suy đoán MIME type cho một số loại request theo cách có thể tạo lỗ hổng từ file có nội dung đa nghĩa:

~~~http
X-Content-Type-Options: nosniff
~~~

Điều kiện quan trọng: **server cũng phải trả Content-Type chính xác.** Nếu trả JavaScript như `text/plain` rồi bật nosniff, browser có thể từ chối thực thi script; đó là tác dụng chính sách chứ không phải lỗi cache ngẫu nhiên. Với nội dung user upload, tránh trả file không đáng tin trên cùng origin có quyền cookie/JS mà không có policy, đúng MIME, Content-Disposition và validation phù hợp.

`nosniff` không thay thế quét malware, file type validation, CSP, output encoding hoặc origin isolation cho user-generated content.

## 9. Referrer-Policy và Permissions-Policy

### Referrer-Policy

Header điều khiển lượng thông tin từ URL hiện tại mà browser có thể gửi trong `Referer` header khi điều hướng hoặc tải tài nguyên, tùy context.

~~~http
Referrer-Policy: no-referrer
~~~

Chọn `no-referrer` khi muốn hạn chế tối đa thông tin URL được gửi đi. Trong nhiều ứng dụng, `strict-origin-when-cross-origin` là chính sách cân bằng: không gửi path/query đầy đủ tới nguồn cross-origin, trong khi có thể cung cấp referrer phù hợp cho same-origin. Hãy chọn theo privacy requirement và analytics thực tế; không tự nhét API key/access token vào URL query kể cả đã đặt no-referrer.

### Permissions-Policy

Header hạn chế các browser features cụ thể trong document/iframe, ví dụ:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

Cú pháp `()` tương ứng không cho phép feature; hỗ trợ của browser có thể khác nhau theo feature và version. **Đừng tưởng Permissions-Policy cấp hoặc từ chối authorization của API backend.** Nó là một cơ chế quản lý browser capabilities; user consent và permission prompts vẫn áp dụng theo giao thức riêng.

Khi cần dùng camera để quét QR hoặc geolocation cho map, đừng copy policy cấm toàn bộ vào trang đó mà không đánh giá. Có thể áp chính sách theo đường/ứng dụng và iframe allow policies đúng mức, đồng thời kiểm tra quyền trước khi truy cập dữ liệu người dùng.

## 10. Cache-Control: tránh lưu response nhạy cảm

Đối với response chứa thông tin cá nhân hoặc session-bound data:

~~~http
Cache-Control: no-store
~~~

`no-store` yêu cầu HTTP caches tuân chuẩn không lưu response theo giao thức, hữu ích cho dữ liệu nhạy cảm. `no-cache` **không** đồng nghĩa cấm lưu; nó cho phép lưu nhưng yêu cầu revalidate trước khi dùng. `private` tránh shared cache lưu response theo ý nghĩa chuẩn, nhưng browser private cache vẫn có thể lưu nếu đủ điều kiện.

Spring Security default thường bao gồm:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Đây là các compatibility/default headers để bảo vệ private content. Tuy nhiên:

- Không phải mọi response đều là dữ liệu cá nhân; tài nguyên JS/CSS có tên content-hash thường nên được cache lâu khi immutable.
- Controller, static resource handling hoặc proxy có thể đặt `Cache-Control` riêng.
- `no-store` **không xóa bản dữ liệu đã phát tán tới người dùng**, không ngăn screen capture, logs hoặc browser extension, và không phải quyền truy cập.
- Một error response có thể chứa requestId, thông tin path hoặc metadata nhạy cảm; cân nhắc `no-store` cho lỗi API riêng tư.
- CDN có thể áp custom caching policy; kiểm tra behavior end-to-end, không chỉ origin header.

## 11. HTTPS: mã hóa truyền tải trước khi request vào Spring

### Luồng TLS đơn giản

~~~text
Client opens https://api.example.test
  |
  | DNS + TCP + TLS ClientHello (SNI/ALPN)
  v
Server/proxy presents X.509 certificate chain
  |
  | Client checks trust chain, SAN/hostname, validity
  | Key exchange establishes protected channel
  v
Encrypted HTTP request/response
  |
  v
Spring controller and filters
~~~

HTTPS bảo vệ trong phạm vi **mỗi TLS hop**. Nếu CDN/ingress terminate TLS rồi gửi plaintext HTTP tới Spring Boot, client-facing hop là HTTPS nhưng hop ingress→app không được mã hóa. Mô hình này có thể chấp nhận trong mạng tin cậy với chính sách rõ, hoặc phải dùng HTTPS/mTLS nội bộ theo security requirements.

### Cách 1: TLS terminate tại ingress

~~~text
Browser --HTTPS:443--> Trusted ingress --HTTP:8080--> Spring Boot
                            |
                            +-- có thể đặt HSTS ở public edge
~~~

Ứng dụng không nhất thiết có private key của domain public. HSTS và redirect policy có thể do ingress sở hữu, nhưng phải kiểm tra header trên **đúng response tới browser**, cả 200, 302 và 4xx/5xx. Với request scheme ở Spring, chỉ tin forwarded headers đã được trusted proxy quản lý.

### Cách 2: TLS trực tiếp trên embedded server

~~~text
Browser --HTTPS:8443--> Embedded Tomcat / Netty
                            |
                            v
                        Spring Security
~~~

Spring Boot 3.3 hỗ trợ PEM SSL bundles và key-store bundles. Có thể cấu hình:

~~~properties
server.port=8443
spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key
server.ssl.bundle=webserver
~~~

Trong lab, key nằm ở classpath cho dễ thử; **production không nên đóng gói private key vào JAR**. Nên dùng file/secret mount, quyền đọc tối thiểu, cấp/renew certificate tự động và kiểm soát vòng đời. Đừng trộn `server.ssl.bundle` với các thuộc tính `server.ssl.key-store` hoặc `server.ssl.certificate-private-key` trực tiếp.

## 12. HSTS và forwarded headers khi có reverse proxy

Giả sử browser truy cập `https://shop.example.test` nhưng ingress forwarding tới `http://internal-app:8080`. Từ góc nhìn socket của Tomcat, request có thể là HTTP. Nếu Spring Security không được cấu hình nhận diện external HTTPS đáng tin, HSTS header có thể không được viết ở backend vì request bị xem là không secure.

Spring Boot hỗ trợ:

~~~properties
# Chỉ áp dụng khi có trusted reverse proxy xử lý và kiểm soát headers
server.forward-headers-strategy=framework
~~~

Lựa chọn khác là `native` khi phù hợp web server/container. `framework` dùng cơ chế forwarded-header của Spring Framework; lựa chọn phù hợp tùy ingress, container và network. **Không bật việc tin tất cả X-Forwarded-* do client trực tiếp gửi**. Nếu attacker tự đặt `X-Forwarded-Proto: https`, `X-Forwarded-Host` hay `Forwarded: host=...` mà app tin không kiểm soát, có thể gây URL poisoning, redirect sai, cookie/security decisions sai hoặc logs đánh lừa.

Cách triển khai đúng là ingress **xóa/ghi đè** forwarded headers từ client, chỉ chuyển nội dung do trusted hop tạo, giới hạn backend chỉ nhận traffic từ ingress và cấu hình trusted proxies đúng.

### Không trộn redirect và HSTS

- **Redirect** `http://...` → `https://...` giúp điều hướng khi client bắt đầu bằng HTTP.
- **HSTS** là policy của browser áp dụng cho những lần truy cập tương lai sau khi nhận trên HTTPS.
- **server.ssl.bundle** bật TLS listener của Spring Boot khi áp dụng cho embedded server.
- **Forwarded headers** giúp backend hiểu external scheme/host của request qua trusted proxy.
- **CSP** kiểm soát tài nguyên/iframe của document, không bật TLS.
- **Cookie Secure** yêu cầu cookie được gửi trong kết nối secure theo browser rules, nhưng không tự thêm TLS listener.

Mỗi khái niệm là một mảnh khác nhau; không dùng một property như thuốc chữa tất cả.

## 13. Vấn đề lộ dữ liệu qua phản hồi lỗi

Lỗi không chỉ là status code. Response khi thất bại có thể vô tình chứa:

- **Stack trace**, fully-qualified Java class names, package nội bộ, đường dẫn file source/line number.
- **SQL query/SQLSTATE**, tên bảng/cột, JDBC URL, hostname và database cluster.
- **Token, API key, JWT**, password, session ID, private header values và cookies.
- **PII**: email, số điện thoại, địa chỉ, mã khách hàng, thông tin sức khỏe/tài chính.
- **Filesystem paths**, hostname nội bộ, port service, infrastructure topology, tenant IDs.
- **Exception message** trực tiếp từ thư viện: `e.getMessage()` có thể chứa user input, URL, secrets hoặc downstream response.
- **Full request body**, đặc biệt các endpoint login, upload, card/payment, password reset.
- **Debug headers** hoặc error pages từ reverse proxy, WAF, servlet container, database gateway.

Ví dụ thiết kế không an toàn:

~~~java
// MÃ MINH HỌA KHÔNG AN TOÀN - KHÔNG ÁP DỤNG
@ExceptionHandler(Exception.class)
ResponseEntity<String> leak(Exception ex) {
    return ResponseEntity.internalServerError()
            .body(ex.toString() + " | " +
                  java.util.Arrays.toString(ex.getStackTrace()));
}
~~~

Mã trên trả exception type/message/stack cho client. Dùng `ex.getMessage()` làm `detail` của ProblemDetail **cũng có thể là lỗi tương tự**. Không chuyển exception nội bộ thành HTTP 200 với body `{"success":false}` chỉ để tránh trả 500; điều đó gây sai semantics, làm lệch monitoring và khiến caches/clients xử lý sai.

### Thiết kế phản hồi lỗi đúng mục đích

Một error response dành cho client cần:

1. **Status code** đúng lớp: 400 bad input, 401 unauthenticated, 403 forbidden, 404 missing, 409 conflict, 429 rate limit, 500 unexpected fault, 503 dependency temporarily unavailable.
2. **Thông điệp công khai ổn định**, không nhắc secret/SQL/implementation. Ví dụ “Không thể xử lý yêu cầu lúc này.”
3. **Mã lỗi domain** nếu client cần xử lý có điều kiện, ví dụ `INVALID_QUANTITY`; không gán trực tiếp exception class thành public code.
4. **requestId/correlationId** để người vận hành tìm logs/traces ở kênh nội bộ.
5. **Content-Type rõ ràng**, ví dụ `application/problem+json` theo RFC 9457 khi dùng `ProblemDetail`.
6. **Cache policy** như `Cache-Control: no-store` khi nội dung lỗi mang thông tin người dùng/session.
7. **Chính sách log an toàn**: logs nội bộ có quyền truy cập/retention/redaction, tránh ghi raw secrets/PII. Không cần đẩy hết diagnostics ra client.

## 14. Spring Boot error properties: cẩn thận với debug flags

Spring Boot 3.3 có các property quan trọng cho Servlet error handling:

~~~properties
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

Những giá trị trên tương ứng mặc định bảo thủ trong Boot 3.3, nhưng **ghi rõ trong production profile** giúp người vận hành thấy chủ đích. Các lựa chọn `on_param`/`always` có thể khiến client kiểm soát việc nhận thêm thông tin nếu cấu hình không phù hợp. Đặc biệt:

~~~properties
# Không dùng trong production để debug từ client:
server.error.include-stacktrace=on_param
server.error.include-message=always
~~~

Khi lộ stacktrace hoặc exception message qua `/error`, chỉ cần một yêu cầu bị lỗi hoặc thêm query parameter thích hợp là client có thể thấy chi tiết. Không chạy một bản production với debug-oriented error flags rồi trông chờ firewall/người dùng không phát hiện.

### server.error.* có giải quyết mọi lỗi không?

Không. Các property này chủ yếu điều khiển cách **Boot error attributes/default error handling** xuất thông tin. Chúng **không tự sanitise**:

- `@ExceptionHandler` do ứng dụng tự viết trả `exception.getMessage()`;
- Spring Security custom `AuthenticationEntryPoint` / `AccessDeniedHandler`;
- Errors được trả nguyên từ downstream hoặc REST gateway;
- Reverse proxy/gateway error pages;
- Filters viết body trước khi error resolver chạy;
- Response serialization lỗi sau khi đã commit headers/body;
- SSE, streaming uploads hoặc WebSocket frames.

Cần khảo sát **mọi đường tạo response lỗi** và test end-to-end. Không thể chỉ dùng một property để đảm bảo mọi thư viện không lộ thông tin nhạy cảm.

### ProblemDetail và RFC 9457

Spring Framework 6.x có `org.springframework.http.ProblemDetail` để biểu diễn lỗi HTTP theo format chuẩn. Một response ví dụ:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Lỗi máy chủ",
  "status": 500,
  "detail": "Không thể xử lý yêu cầu lúc này.",
  "requestId": "mã ngẫu nhiên"
}
~~~

Các key title/status/detail có semantics rõ, còn `requestId` là extension property do ứng dụng cung cấp. `ProblemDetail` **không tự xóa secrets** nếu bạn tự đặt `detail` bằng exception message; schema đúng nhưng nội dung sai vẫn nguy hiểm.

Spring Boot 3.3 có `spring.mvc.problemdetails.enabled` để tích hợp xử lý Problem Details cho các built-in MVC exceptions. Khi bật tính năng này đồng thời thêm `@ControllerAdvice` custom, cần hiểu thứ tự/resolver và tránh tình trạng built-in handler do Boot đăng ký cạnh tranh với handler của ứng dụng. Lab phía dưới chủ động tạo ProblemDetail cho domain errors, không phụ thuộc property này để chuyển tất cả exception.

## 15. Ví dụ chạy được: Spring MVC + Spring Security + lỗi an toàn

Ta dựng một ứng dụng lab có:

- `GET /api/health` trả dữ liệu công khai 200.
- `GET /api/items/1` trả item công khai; `/api/items/2` tạo lỗi 404 domain-specific.
- `GET /api/quantity?value=0` tạo lỗi 400, nhưng không trả raw validation/exception message.
- `GET /api/failure` mô phỏng lỗi internal database và trả ProblemDetail 500 **không chứa thông tin backend**.
- Spring Security giữ headers mặc định; app bổ sung CSP, Referrer-Policy và Permissions-Policy.
- HTTPS hoạt động bằng SSL bundle trong profile `https` để kiểm HSTS trên HTTPS.

**Quan trọng:** demo cho phép request `permitAll()` để tập trung vào header/error behavior, không phải cấu hình authorization production. Tất cả endpoint chỉ dùng GET; demo giữ mặc định CSRF của Spring Security (không vô hiệu hóa). Trong sản phẩm thực, mọi endpoint dữ liệu riêng phải có authn/authz.

### 15.1. Cấu trúc project

~~~text
security-headers-demo/
  pom.xml
  src/main/java/example/securityheaders/SecurityHeadersApplication.java
  src/main/resources/application.properties
  src/main/resources/application-https.properties
  src/main/resources/tls/localhost.crt
  src/main/resources/tls/localhost.key
  src/test/java/example/securityheaders/SecurityHeadersTests.java
~~~

Các file dưới `tls/` chỉ cần tạo khi thử HTTPS profile. Không commit/đóng gói private key production theo cách dùng trong lab.

### 15.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-headers-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>security-headers-demo</name>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven parent Spring Boot 3.3.13 quản lý các dependency versions phù hợp. Spring Boot plugin giúp chạy bằng `mvn spring-boot:run` và đóng executable JAR. Dependency `spring-boot-starter-web` dùng embedded Tomcat mặc định; Spring Security được kích hoạt qua starter và custom `SecurityFilterChain` trong code.

### 15.3. File Java hoàn chỉnh

Đặt tại `src/main/java/example/securityheaders/SecurityHeadersApplication.java`:

~~~java
package example.securityheaders;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.header.writers.StaticHeadersWriter;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class SecurityHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityHeadersApplication.class, args);
    }

    public record Item(long id, String name) { }

    @Configuration
    static class SecurityConfiguration {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {

            // permitAll chỉ phục vụ lab: không có dữ liệu riêng.
            // Không copy policy này vào API production.
            http.authorizeHttpRequests(auth ->
                    auth.anyRequest().permitAll());

            // Giữ default security headers; chỉ BỔ SUNG policy.
            http.headers(headers -> headers
                    .contentSecurityPolicy(csp -> csp
                            .policyDirectives(
                                    "default-src 'self'; " +
                                    "script-src 'self'; " +
                                    "base-uri 'self'; " +
                                    "object-src 'none'; " +
                                    "frame-ancestors 'none'"))
                    .referrerPolicy(ref -> ref.policy(
                            ReferrerPolicyHeaderWriter
                                    .ReferrerPolicy.NO_REFERRER))
                    .addHeaderWriter(new StaticHeadersWriter(
                            "Permissions-Policy",
                            "camera=(), microphone=(), " +
                            "geolocation=()")));

            return http.build();
        }
    }

    @RestController
    static class DemoApi {
        @GetMapping("/api/health")
        public Map<String, String> health() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/items/{id}")
        public Item item(@PathVariable long id) {
            if (id != 1L) {
                throw new NoSuchElementException(
                        "Internal catalog key=" + id);
            }
            return new Item(1L, "Demo public item");
        }

        @GetMapping("/api/quantity")
        public Map<String, Integer> quantity(
                @RequestParam int value) {
            if (value < 1 || value > 100) {
                throw new IllegalArgumentException(
                        "Private business rule: value=" + value);
            }
            return Map.of("accepted", value);
        }

        @GetMapping("/api/failure")
        public Map<String, String> failure() {
            // Dữ liệu minh họa CHỈ nằm trong exception nội bộ;
            // khách hàng không được nhận nội dung này.
            throw new IllegalStateException(
                    "INTERNAL_DB_HOST=db.private.lan");
        }
    }

    @RestControllerAdvice
    static class ApiErrors {
        private static final Logger LOG =
                LoggerFactory.getLogger(ApiErrors.class);

        @ExceptionHandler(NoSuchElementException.class)
        public ResponseEntity<ProblemDetail> notFound(
                NoSuchElementException ex) {
            return response(HttpStatus.NOT_FOUND,
                    "Không tìm thấy tài nguyên",
                    "Tài nguyên được yêu cầu không tồn tại.",
                    UUID.randomUUID().toString());
        }

        @ExceptionHandler(IllegalArgumentException.class)
        public ResponseEntity<ProblemDetail> badInput(
                IllegalArgumentException ex) {
            return response(HttpStatus.BAD_REQUEST,
                    "Yêu cầu không hợp lệ",
                    "Giá trị yêu cầu không hợp lệ.",
                    UUID.randomUUID().toString());
        }

        @ExceptionHandler(IllegalStateException.class)
        public ResponseEntity<ProblemDetail> internalFailure(
                IllegalStateException ex) {
            String requestId = UUID.randomUUID().toString();

            // Log ở đây KHÔNG ghi ex.getMessage(), raw headers,
            // request body hoặc các giá trị bí mật.
            LOG.error("Simulated internal error, requestId={}",
                    requestId);

            return response(HttpStatus.INTERNAL_SERVER_ERROR,
                    "Lỗi máy chủ",
                    "Không thể xử lý yêu cầu lúc này.",
                    requestId);
        }

        private ResponseEntity<ProblemDetail> response(
                HttpStatus status, String title,
                String detail, String requestId) {

            ProblemDetail body =
                    ProblemDetail.forStatusAndDetail(status, detail);
            body.setTitle(title);
            body.setProperty("requestId", requestId);

            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                    .cacheControl(CacheControl.noStore())
                    .body(body);
        }
    }
}
~~~

**Nhận xét về khả năng chạy:** đây là **một file Java đầy đủ** trong package đúng path, sử dụng APIs có trong Spring Boot 3.3/Spring Security 6.x và Java records của Java 17. Các nested configuration/controller/advice đều là static types được component scan của Spring nhận diện. Không cần tạo database hay định nghĩa record ở file khác.

### 15.4. Vì sao không dùng @ExceptionHandler(Exception.class) đại trà?

Một catch-all handler viết ẩu có thể biến 400, 404, lỗi chuyển đổi tham số, method-not-allowed hoặc exception của framework thành 500, làm sai HTTP semantics. Demo chỉ xử lý **ba nhóm exception đã xác định** để minh họa error mapping. Những exception khác được xử lý bởi Spring MVC/Boot mặc định, cùng các `server.error.*` flags đã cấu hình.

Trong sản phẩm lớn, nếu cần catch-all thật, nên hiểu rõ `ResponseEntityExceptionHandler`, `ErrorResponse`, độ ưu tiên `@ControllerAdvice` và cơ chế xử lý của framework, giữ nguyên statuses của built-in exceptions thay vì mặc định coi mọi thứ là 500.

Vì sao không trả `ex.getMessage()`? Trong mã demo, các exception cố ý chứa chuỗi `Internal catalog key=...`, `Private business rule: ...` hoặc `INTERNAL_DB_HOST=db.private.lan` để chứng minh không rò rỉ. Dòng `detail` được viết **cố định theo domain error**, không lấy từ throwable. `requestId` giúp người vận hành kết nối response với logs/traces mà không cần tiết lộ nội dung stack.

Trong ứng dụng production, logs có thể cần stack trace để debug nhưng phải có redaction, access control, retention và secure logging pipeline. Không nên chỉ bỏ hết logs vì sợ lộ: quan trọng là **không cho client nhìn thấy**, đồng thời bảo vệ dữ liệu trong logs nội bộ.

### 15.5. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Cố tình nêu rõ policy hạn chế lộ lỗi ở Boot 3.3
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false

# Không cần vô hiệu hóa SSL/headers ở HTTP profile:
# default Spring Security headers vẫn được trả,
# ngoại trừ HSTS chỉ xuất hiện trên HTTPS/secure request.
~~~

Khi profile `https` không hoạt động, server chạy HTTP local trên cổng 8080. Đừng khẳng định test HTTP đã kiểm chứng HSTS/TLS. Việc tách hai profile giúp nhìn rõ HSTS khác các header còn lại ra sao.

### 15.6. Chạy local HTTP và thử các status

Trong thư mục dự án có Maven và JDK 17:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/items/1
curl -i http://localhost:8080/api/items/2
curl -i "http://localhost:8080/api/quantity?value=0"
curl -i http://localhost:8080/api/failure
~~~

Kỳ vọng **theo semantics**:

| URL | Status | Body chính | Điều cần quan sát |
|---|---|---|---|
| `/api/health` | 200 | JSON `{"status":"ok"}` | nosniff, X-Frame-Options, CSP, Referrer-Policy và Permissions-Policy |
| `/api/items/1` | 200 | Item JSON id 1 | Không cần login vì permitAll chỉ ở lab |
| `/api/items/2` | 404 | ProblemDetail công khai | Không chứa `Internal catalog key` |
| `/api/quantity?value=0` | 400 | ProblemDetail công khai | Không chứa `Private business rule` |
| `/api/failure` | 500 | ProblemDetail công khai | Không chứa `db.private.lan` |
 
Error response mẫu 500 (minh họa, ID thực thay đổi):

~~~json
{
  "type": "about:blank",
  "title": "Lỗi máy chủ",
  "status": 500,
  "detail": "Không thể xử lý yêu cầu lúc này.",
  "requestId": "6fb8a742-62d2-4b77-99ec-3e64a0c1b019"
}
~~~

Không khẳng định thứ tự JSON fields hoặc header order giống y hệt, vì serializer/container có thể thay đổi. `requestId` được random hóa từng lỗi; không dùng nó như secret hoặc access token. Khi code được chạy trên profile HTTP, **không nên thấy HSTS** là một policy đáng tin; hãy kiểm profile HTTPS ở mục sau.

### 15.7. Có thấy lỗi 404/400 từ framework giống advice không?

Các lỗi domain cụ thể đã được `@ExceptionHandler` map. Nhưng URL không có route, thiếu request parameter hoặc không convert được kiểu dữ liệu có thể đi qua default MVC/Boot error handling, không nhất thiết cùng JSON với handler demo. **Phân biệt**:

- **Domain exception**: ứng dụng chủ động tạo và map status/detail.
- **MVC framework exception**: mapping/argument binding/validation/content negotiation.
- **Security exception**: authentication/authorization filter, có thể trả 401/403 trước controller.
- **Container/proxy error**: 400/413/502/503/504 do một tầng khác tạo; advice không chạy.

Hợp đồng lỗi nhất quán cho sản phẩm cần chuẩn hóa **tất cả các nguồn** này một cách chủ động, không mặc định một advice xử lý được tất cả.

## 16. Chạy HTTPS bằng PEM SSL bundle

### 16.1. Tạo self-signed cert cho localhost

Trong thư mục project, tạo thư mục:

~~~bash
mkdir -p src/main/resources/tls
~~~

Trên PowerShell có thể dùng `New-Item -ItemType Directory -Force src/main/resources/tls`. Cần OpenSSL 1.1.1+ hỗ trợ `-addext`.

Tạo private key PKCS#8 và certificate có SAN:

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out src/main/resources/tls/localhost.key

openssl req -new -x509 -sha256 -days 7 \
  -key src/main/resources/tls/localhost.key \
  -out src/main/resources/tls/localhost.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
~~~

Trên Windows, chạy command trên một dòng thay cho dấu nối dòng của shell Unix hoặc dùng cú pháp PowerShell tương đương. Certificate tự ký này **không được browser tin theo mặc định**; không dùng nó làm certificate production. Trong lab, private key nằm dưới resources để dễ chạy nhưng **không commit file private key lên repository** hoặc phân phối JAR chứa secret thật.

### 16.2. application-https.properties

Tạo `src/main/resources/application-https.properties`:

~~~properties
server.port=8443

spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key
server.ssl.bundle=webserver

# Chỉ bật HTTP/2 khi runtime/client hỗ trợ và cần kiểm thử riêng:
# server.http2.enabled=true
~~~

Lưu ý hai tầng:

- `spring.ssl.bundle.pem.webserver...` **định nghĩa bundle** tên webserver.
- `server.ssl.bundle=webserver` **áp dụng bundle** cho máy chủ nhúng.

Không trộn bundle với `server.ssl.key-store` / `server.ssl.certificate-private-key` rời ở cùng cấu hình. Spring Security headers trong ví dụ vẫn được xử lý ở filter chain; chỉ khác request đã là HTTPS, nên HSTS mặc định có thể xuất hiện.

Chạy riêng profile HTTPS:

~~~bash
mvn -Dspring-boot.run.profiles=https spring-boot:run
~~~

Khi active `https`, vẫn load `application.properties` rồi override `server.port` thành 8443 và bổ sung bundle. Nếu HTTP app còn chạy trên 8080, bạn có thể chạy đồng thời trên hai cổng **nếu là hai process riêng biệt**, nhưng lab đơn giản nhất là dừng process HTTP trước để tránh nhầm quan sát. HTTPS profile **không tự tạo listener redirect HTTP 8080 → HTTPS 8443**; redirect cần cấu hình riêng ở proxy/container nếu mong muốn.

### 16.3. Kiểm tra HTTPS mà không bỏ verification

~~~bash
curl --cacert src/main/resources/tls/localhost.crt \
  -i https://localhost:8443/api/health

curl --cacert src/main/resources/tls/localhost.crt \
  -i https://localhost:8443/api/failure
~~~

Kỳ vọng request thành công, status 200/500 theo endpoint, response headers bảo mật và trên HTTPS có `Strict-Transport-Security` nếu Spring Security nhận diện kết nối secure. `--cacert` chủ động tin cert self-signed dành riêng lab; nó khác `curl -k` / `--insecure` vì không tắt xác minh certificate.

Để kiểm certificate SAN/chain:

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

Để kiểm TLS handshake:

~~~bash
openssl s_client -connect localhost:8443 \
  -servername localhost \
  -CAfile src/main/resources/tls/localhost.crt \
  -verify_hostname localhost
~~~

Output cụ thể có thể thay đổi theo OpenSSL, JDK, server và certificate; kiểm tra return code/verify, hostname và kết nối. Đừng lấy `curl -k` thành bằng chứng HTTPS đã được **xác minh danh tính**.

### 16.4. So sánh header ở HTTP và HTTPS

Chạy:

~~~bash
curl -s -D - -o /dev/null http://localhost:8080/api/health
~~~

và khi chạy HTTPS profile:

~~~bash
curl --cacert src/main/resources/tls/localhost.crt \
  -s -D - -o /dev/null https://localhost:8443/api/health
~~~

Lệnh `-o /dev/null` mang tính Unix; trên Windows có thể dùng `curl.exe -I` để xem HEAD khi endpoint hỗ trợ semantics thích hợp hoặc dùng `-o NUL`. Nên dùng `curl -i` nếu muốn kiểm cả status và body.

Thông thường bạn sẽ thấy CSP/nosniff/frame options/referrer/permissions cả hai môi trường, còn HSTS chỉ ở request HTTPS/secure. Nếu đang qua proxy, hãy kiểm tra URL public vì header do edge/backend có thể khác.

## 17. Integration tests với MockMvc và Spring Security

### 17.1. Tạo test dependencies

POM ở mục 15 đã có `spring-boot-starter-test` và `spring-security-test` trong scope test. Không cần thêm version thủ công nhờ Spring Boot BOM.

Tạo `src/test/java/example/securityheaders/SecurityHeadersTests.java`:

~~~java
package example.securityheaders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTests {
    @Autowired
    MockMvc mvc;

    @Test
    void defaultHeadersAndCspExist() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                        "X-Frame-Options", "DENY"))
                .andExpect(header().exists(
                        "Content-Security-Policy"))
                .andExpect(header().string(
                        "Referrer-Policy", "no-referrer"))
                .andExpect(header().exists(
                        "Permissions-Policy"));
    }

    @Test
    void hstsAppliesToSecureRequests() throws Exception {
        mvc.perform(get("/api/health").secure(true))
                .andExpect(status().isOk())
                .andExpect(header().exists(
                        "Strict-Transport-Security"));
    }

    @Test
    void internalFailureIsSanitized() throws Exception {
        mvc.perform(get("/api/failure"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.detail").value(
                        "Không thể xử lý yêu cầu lúc này."))
                .andExpect(jsonPath("$.requestId").exists())
                .andExpect(content().string(
                        not(containsString("db.private.lan"))))
                .andExpect(header().string(
                        "Cache-Control", "no-store"));
    }

    @Test
    void validationErrorIsSanitized() throws Exception {
        mvc.perform(get("/api/quantity")
                    .param("value", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(
                        not(containsString("Private business rule"))));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

`MockMvc` tạo request giả lập trong JVM; `secure(true)` khiến request được đánh dấu secure để kiểm behavior của HSTS header writer, **không phải TLS handshake thật**. Test HSTS ở đây chỉ kiểm Security filter cho request secure; vẫn phải dùng HTTPS endpoint thực với `curl --cacert` để xác minh certificate và TLS. Khi có reverse proxy, cần thêm kiểm thử end-to-end qua ingress thực tế.

### 17.2. Tại sao test cả lỗi?

Một số security headers được thêm qua filter ở success response nhưng bị mất khi:

- Exception được xử lý bởi filter trước/lúc commit response.
- Error dispatcher tạo body riêng hoặc reset response.
- Reverse proxy phát sinh 502/503 thay vì Spring.
- Downstream API gateway thay Content-Type hoặc cache policy.
- Một filter custom gửi redirect/error trực tiếp.

Vì vậy tích hợp test nên bao gồm **2xx, 3xx, 4xx, 5xx** trong phạm vi có thể, không chỉ kiểm `/api/health`. Kiểm tra body/cookies/headers và cả error routes thực của sản phẩm.

## 18. Spring Security: xác thực và phân quyền có đường lỗi riêng

`@RestControllerAdvice` xử lý exception trong luồng Spring MVC controller/resolvers. Nhưng Spring Security thường từ chối request **trước controller**, ví dụ:

- **401 Unauthorized**: client chưa xác thực/credentials không hợp lệ, tùy authentication scheme.
- **403 Forbidden**: đã xác thực nhưng không đủ quyền, hoặc một số trường hợp CSRF/access denied.
- **Redirect 302 tới login**: hành vi hợp lệ cho form login nhưng không phải contract phù hợp cho mọi REST API.
- **429 Too Many Requests**: có thể do rate-limit filter/gateway, không nhất thiết do controller.

Khi dùng REST API với Bearer tokens, Spring Security Resource Server có integration riêng cho bearer authentication entry points và `WWW-Authenticate` header theo chuẩn. **Không xóa header giao thức hợp lệ** chỉ để giấu toàn bộ chi tiết; nhưng cũng không đặt raw exception/stacktraces/tokens vào header.

Một đoạn cấu hình **minh họa**, không phải extension tự biên dịch độc lập:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

Nếu bật auth thật, phải bổ sung provider/resource-server config, token validation và quyền. Khi custom error handler:

- `AuthenticationEntryPoint` xử lý unauthenticated requests.
- `AccessDeniedHandler` xử lý denied authenticated requests hoặc access-denied cases theo chain.
- Controller advice cho domain/service exceptions.
- Default Boot MVC error handling cho route/binding/framework exceptions nếu không có handler cụ thể.

Một ErrorHandler bắt `Exception.class` rồi trả 500 cho mọi lỗi không thay thế được hệ thống này và có thể làm 401/403 biến thành lỗi khác. Với Spring WebFlux, names tương ứng là reactive `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` và `SecurityWebFilterChain`, không dùng Servlet types.

## 19. WebFlux: security headers và error body có khác không?

Spring Security WebFlux cũng có security headers và cơ chế tùy chỉnh qua `ServerHttpSecurity` / `SecurityWebFilterChain`. Spring WebFlux cung cấp `ProblemDetail`, `ErrorResponse`, `@RestControllerAdvice`, cùng cơ chế xử lý lỗi reactive riêng.

Mảnh cấu hình chỉ dành cho ứng dụng WebFlux đã có `spring-boot-starter-webflux` và `spring-boot-starter-security`:

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; object-src 'none'")))
        .build();
}
~~~

Đoạn này cần imports từ `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `@Bean` và application class trong dự án reactive. Nó **không phải** một Spring Boot app hoàn chỉnh; cần cấu hình identity/auth thích hợp cho protected endpoints. Không copy class Servlet `SecurityFilterChain`/`HttpSecurity` vào WebFlux rồi kỳ vọng áp dụng.

Điểm khác biệt quan trọng: WebFlux có request pipeline reactive và có thể trả `Mono<ProblemDetail>` hoặc `Mono<ResponseEntity<ProblemDetail>>`. Nhưng điều này **không làm dữ liệu lỗi tự an toàn**; không publish `Throwable.toString()` hoặc remote stack trace trong body. Khi exception xảy ra sau khi reactive response stream đã gửi một phần dữ liệu, headers/status có thể **đã được commit**, nên không thể luôn đổi thành 500 ProblemDetail đầy đủ. Cần thiết kế streaming error handling phù hợp và quan sát client disconnect.

Với cả Servlet và reactive runtime, proxy/WAF có thể tạo error responses ngoài Spring. Test điểm ingress/public URL là bắt buộc khi cần cam kết về header security và không rò rỉ thông tin.

## 20. Lộ dữ liệu qua logs, traces, headers và frontend UI

Chỉ làm sạch error JSON vẫn chưa đủ nếu:

- **Access logs** ghi nguyên query string có email/reset token.
- **Request logging filter** chụp body chứa password/card number.
- **Tracing spans** lưu headers Authorization/Cookie hoặc SQL đầy đủ với PII.
- **APM dashboard** mở cho người không có quyền, hoặc retention kéo dài.
- **Proxy error page** hiển thị upstream hostname/IP/stack/nginx debug.
- **Frontend UI** hiển thị raw `response.text()` của 500 error cho người dùng.
- **Debug actuator endpoints** như env/configprops/heapdump được mở công khai.
- **Support ticket** chứa raw curl transcript kèm JWT/token, cookie, private endpoints.

Thiết kế log dùng **allowlist fields**, redaction các giá trị bí mật và trace correlation ID. Đừng dựa chỉ vào tìm/replace pattern như `password=` vì secret có thể xuất hiện dưới nhiều tên và encoding. Bảo vệ quyền truy cập, phân cấp dữ liệu, mã hóa lúc lưu và chính sách xóa là các phần của solution.

### Ví dụ hợp đồng frontend an toàn

Nếu nhận 500 ProblemDetail:

~~~javascript
async function fetchItem(id) {
  const response = await fetch("/api/items/" + encodeURIComponent(id));
  if (!response.ok) {
    let requestId = null;
    try {
      const problem = await response.json();
      if (typeof problem.requestId === "string") {
        requestId = problem.requestId;
      }
    } catch (_) {
      // Có thể lỗi không trả JSON do proxy/network.
    }
    throw new Error(
      "Không thể hoàn thành yêu cầu."
      + (requestId ? " Mã hỗ trợ: " + requestId : "")
    );
  }
  return response.json();
}
~~~

Đây là mảnh JavaScript dùng trong frontend thực đã có API phù hợp; không phải file chạy độc lập trong browser nếu chưa gọi function. Nó không render raw HTML từ error body bằng innerHTML và không tự ý hiển thị stacktrace/message nội bộ. Với status 401/403, frontend nên phân biệt login/permission flow thay vì biến tất cả thành “vui lòng thử lại” nếu điều đó làm sai trải nghiệm.

Không log toàn bộ error response vào console production cùng token/user context, đặc biệt khi trang có bên thứ ba đọc console hoặc telemetry tự thu thập dữ liệu.

## 21. Chẩn đoán các lỗi bảo mật/header thường gặp

| Triệu chứng | Nguyên nhân có thể | Hành động |
|---|---|---|
| HTTPS hoạt động nhưng không thấy HSTS | Header writer bị tắt, request backend bị coi là HTTP, proxy bỏ header | So trực tiếp backend/ingress, kiểm `isSecure` và trusted forwarded headers |
| HSTS trên HTTP response nhưng browser không lưu | HSTS phải nhận qua HTTPS hợp lệ | Kiểm certificate/HTTPS, không ép bằng header HTTP |
| Sau bật CSP giao diện mất JS/CSS | `script-src`/`style-src` quá chặt, inline script bị chặn | Quan sát CSP violation, dùng nonce/hash/allowlist đúng mức |
| CSP trên API JSON nhưng frontend vẫn chạy script không an toàn | Policy không đặt ở HTML document/other relevant responses | Đặt CSP đúng origin/document và encode output |
| Trang không hiển thị trong iframe | `X-Frame-Options: DENY` hoặc `frame-ancestors 'none'` | Thiết kế embed allowlist, không tắt toàn cục |
| JS bị từ chối MIME type | `nosniff` + Content-Type trả sai | Sửa MIME, không bỏ nosniff chỉ để chạy được |
| Response lỗi chứa stacktrace | `server.error.include-stacktrace` quá rộng hoặc handler tự trả stack | Đặt never, sửa advice/error body |
| Lỗi 500 body lộ JDBC URL | `ex.getMessage()` được dùng làm detail | Public message cố định, requestId; log nội bộ redacted |
| API dùng no-store nhưng CDN vẫn cache | Proxy caching policy override, test sai endpoint | Kiểm response tại edge và cấu hình cache thực |
| Error response 403 không có CSP | Security entrypoint/filter/gateway tạo body khác controller | Cấu hình security/error handlers và test 4xx |
| Người dùng truy cập HTTP rồi redirect bị can thiệp | HSTS chưa được thiết lập, TLS policy thiếu | HTTPS, redirect, HSTS rollout/preload nếu đủ điều kiện |
| Cookies bị gửi qua connection không phù hợp | Thiếu `Secure`/`HttpOnly`/`SameSite` hoặc proxy scheme sai | Sửa cookie policy, TLS termination và trusted forwards |
| Chạy local HTTP test kỳ vọng có HSTS | Môi trường không có HTTPS secure request | Test `.secure(true)` ở MockMvc và HTTPS thật |
| Header CSP bị lặp hoặc khác nhau | App + nginx/CDN cùng viết policy | Chọn owner, kiểm browser hiệu lực nhiều policies |
| CORS lỗi bị hiểu thành CSP | Browser Console báo connect-src vs Access-Control-Allow-Origin | Đọc chính xác lỗi và đối chiếu cả hai policy |
| HTTP 200 cho lỗi internal | Exception bị nuốt, API dùng body failure nhưng status success | Map 4xx/5xx phù hợp, tránh che lỗi quan sát |

### Một lưu ý về Security headers trên error responses

HSTS, CSP và X-Frame-Options thường có ý nghĩa ở browser response security context, nhưng không phải mọi kết nối/response đều đi qua cùng filter. Ví dụ một lỗi 502 do nginx sinh không hề chạm Spring Security. Khi tuyên bố “tất cả errors đều có headers”, cần test **một tập representative error cases qua public ingress**, không chỉ qua MockMvc.

## 22. Khung quyết định và checklist production

Trước khi deploy một API web runtime, trả lời:

1. **TLS termination ở đâu?** Client→CDN→ingress→app, hop nào có HTTPS/mTLS, ai giữ private key?
2. **Chứng thư hợp lệ không?** CA chain, SAN, expiry, rotation, TLS versions/ciphers, private key permissions.
3. **HSTS áp ở đâu?** Header từ trusted HTTPS response, rollout max-age, includeSubDomains/preload với sự chuẩn bị.
4. **Security headers có owner không?** Spring Security hay ingress? Có duplicate/conflicting headers không?
5. **CSP của HTML frontend có đúng?** Scripts/styles/fonts/API/WebSockets được allow vừa đủ, không lạm dụng unsafe-inline.
6. **Content-Type + nosniff đúng không?** Tránh user-uploaded content cùng origin có quyền và không được kiểm soát.
7. **Error response có contract không?** Status, ProblemDetail hoặc DTO ổn định, requestId, message an toàn, no-store khi cần.
8. **Built-in errors đã được xem xét?** Binding, invalid JSON, no handler, method mismatch, serialization errors.
9. **Security errors đã được xem xét?** 401/403/CSRF/token failure, entrypoints và redirects không lộ user existence/secrets.
10. **Proxy error pages đã được xem xét?** 413/429/502/503/504, WAF blocks, timeout, CDN cache.
11. **Logging/tracing có privacy review không?** Authorization/Cookie/PII/SQL secrets redaction, access control và retention.
12. **Cookie/session policy đúng không?** Secure, HttpOnly, SameSite, CSRF và permissions.
13. **Static resources có cache policy khác JSON private không?** Hash/versioned assets được cache phù hợp; dữ liệu riêng no-store.
14. **Kiểm thử có cover HTTP và HTTPS không?** HTTP chỉ chứng minh một phần header; HSTS cần secure request và TLS acceptance thực.
15. **Có giám sát sự cố không?** Security headers drift, certificate expiry, TLS failure, error rate, 401/403/5xx, stack leak regression và WAF events.

### Một chiến lược rollout an toàn

- **Development:** baseline defaults, CSP Report-Only khi có frontend phức tạp, unit/integration tests cho response errors.
- **Staging:** HTTPS đáng tin, bật enforcing CSP dần theo tài nguyên thực, kiểm behavior với CDN/proxy và browsers mục tiêu; test bad inputs và fault injection.
- **Production:** certificate automation, private key secret mount, HSTS sau kiểm kê subdomains, header ownership rõ ràng, redaction logs và alerts.
- **Sau release:** chạy kiểm tra headers có định kỳ, theo dõi expiry, quan sát policy violations và kiểm response 4xx/5xx của từng tầng. Cập nhật baseline khi library/browser standards thay đổi.

**Không bật HPKP (HTTP Public Key Pinning) cho hệ mới.** Cơ chế này đã bị nhiều trình duyệt bỏ và có nguy cơ tự khóa người dùng nếu xoay khóa sai. Không coi header cũ như `X-XSS-Protection: 1; mode=block` là giải pháp XSS hiện đại.

## 23. Câu hỏi tự kiểm tra có đáp án

**1. HTTPS đã bật thì có cần sanitize error response nữa không?**  
Có. HTTPS bảo vệ dữ liệu khi truyền, nhưng nếu server gửi stacktrace/token/SQL trong body thì chính client vẫn nhận dữ liệu nhạy cảm đó.

**2. Spring Security có tự thêm CSP tối ưu cho ứng dụng không?**  
Không. CSP phụ thuộc nguồn JS/CSS/API/iframe thực tế, phải thiết kế và kiểm thử riêng.

**3. Tại sao trên HTTP localhost có CSP và nosniff nhưng không có HSTS?**  
Spring Security chỉ thêm HSTS cho request secure/HTTPS theo mặc định. Header HSTS do HTTP gửi cũng không được browser chấp nhận để thiết lập policy.

**4. HSTS và redirect HTTP→HTTPS có cùng tác dụng không?**  
Không. Redirect điều hướng một request, HSTS được browser ghi nhớ và áp dụng cho các truy cập sau theo policy.

**5. `X-Frame-Options: DENY` bảo vệ trước điều gì?**  
Chủ yếu trước clickjacking qua framing. Nó không thay thế authorization hoặc CSP toàn bộ.

**6. `X-Content-Type-Options: nosniff` có cứu được server trả MIME sai không?**  
Không. Nó có thể khiến browser từ chối tài nguyên vì MIME sai; cần sửa Content-Type.

**7. `Cache-Control: no-cache` có giống `no-store` không?**  
Không. no-cache có thể lưu nhưng cần revalidate trước khi sử dụng; no-store chỉ thị không lưu theo HTTP caching semantics.

**8. Một API trả 500 với `detail=exception.getMessage()` có an toàn nếu exception từ JDBC không?**  
Không mặc định. Exception message có thể chứa host, SQL, credentials, key hoặc PII. Trả public detail cố định và requestId.

**9. `server.error.include-stacktrace=never` có ngăn custom advice trả stacktrace không?**  
Không. Property chủ yếu điều khiển Boot error handling; mã ứng dụng phải tự sanitize output.

**10. `ProblemDetail` có tự bảo vệ mọi thông tin nhạy cảm không?**  
Không. Nó chỉ định schema; nội dung fields do app tạo cần được kiểm tra riêng.

**11. Lỗi 401 từ Spring Security có chắc đi qua `@RestControllerAdvice` không?**  
Không. Security filter có thể từ chối trước controller, dùng AuthenticationEntryPoint/AccessDeniedHandler riêng.

**12. Sau khi TLS terminate ở nginx, Spring có tự biết request gốc là HTTPS không?**  
Không nhất thiết. Cần trusted forwarded headers/appropriate container config hoặc phát HSTS ở edge.

**13. Vì sao không cho phép mọi client điều khiển `X-Forwarded-Proto`?**  
Vì có thể gây spoof external scheme/host, tạo redirects/security decisions không đúng. Chỉ tin proxy được kiểm soát.

**14. `Referrer-Policy: no-referrer` có ngăn app log token trong URL không?**  
Không. Nó điều khiển referrer browser gửi trong ngữ cảnh nhất định; logging vẫn phải được kiểm soát riêng.

**15. CSP `frame-ancestors` và `frame-src` có giống nhau không?**  
Không. frame-ancestors kiểm ai được nhúng trang hiện tại; frame-src kiểm các frame trang hiện tại tải.

**16. MockMvc `secure(true)` có xác minh certificate chain như curl HTTPS không?**  
Không. Nó chỉ mô phỏng secure request để kiểm header logic; cần TLS handshake thật để xác minh certificate.

**17. Nếu proxy trả 502 với stacktrace, sửa `@ExceptionHandler` có đủ không?**  
Không. Phản hồi do proxy tạo, phải sửa proxy error page/logging/security headers ở tầng đó.

**18. Tại sao test 2xx chưa đủ?**  
Lỗi 4xx/5xx/redirect có thể đi qua đường xử lý khác, rò rỉ dữ liệu hoặc mất headers.

**19. Có nên bật includeSubDomains và preload ngay khi chuyển website sang HTTPS?**  
Không vội. Phải kiểm tất cả subdomains, certificate, hạ tầng và khả năng rollback vì HSTS đã lưu không được gỡ ngay.

**20. Nếu application dùng @RestController thuần JSON, CSP có thay thế CORS hay CSRF không?**  
Không. CSP chủ yếu điều khiển browser document resource behavior; CORS điều khiển quyền đọc response cross-origin và CSRF bảo vệ những mutation có thể dùng credentials tự động.

## 24. Tài liệu tham khảo chính thức

- [Spring Security – Default Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): headers mặc định, HSTS chỉ trên HTTPS, CSP không mặc định, các biện pháp phòng thủ và X-XSS-Protection.
- [Spring Security – Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): Java DSL cho Cache-Control, HSTS, CSP, Referrer-Policy, Frame Options và custom header writers.
- [Spring Security – Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): các cấu hình tương ứng trong WebFlux.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.error.include-*`, `server.forward-headers-strategy`, TLS và cấu hình web server.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): SSL bundle và cấu hình khi chạy sau front-end proxy.
- [Spring Boot 3.3 – SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): PEM SSL bundles và lifecycle TLS.
- [Spring Framework – Error Responses in MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler và xử lý ngoại lệ.
- [Spring Framework – Error Responses in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): cùng hợp đồng error responses ở reactive stack.
- [OWASP – HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): cách thiết kế security headers và pitfalls.
- [OWASP – Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): hạn chế information disclosure và logging.
- [MDN – Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): CSP directives, nonce/hash, report-only.
- [MDN – HTTP Strict Transport Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): chính sách HSTS và sự khác biệt với redirect.
- [RFC 6797 – HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797): semantics của HSTS.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status, headers và HTTP semantics.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): chuẩn current cho problem details.
