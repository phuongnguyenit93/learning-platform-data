# Sự khác nhau khi gọi API từ trình duyệt, curl và một dịch vụ khác

Cùng một API Spring Boot, cùng phương thức GET, cùng URL nhưng thử từ trình duyệt có thể gặp lỗi CORS, từ curl lại nhận JSON, còn một service Java có thể nhận 401 vì chưa đính kèm token. Để chẩn đoán đúng, phải phân biệt **quy tắc của HTTP và server** với **hành vi riêng của từng loại HTTP client**.

Bài học đặt trong ngữ cảnh Spring Security: request được xác thực và phân quyền trên server, còn trình duyệt có thêm chính sách về origin, cookie, JavaScript và việc đọc response. Công cụ curl và ứng dụng backend sử dụng HTTP mà không có các lớp bảo vệ trình duyệt tương đương. Chúng vẫn phải tuân theo chính sách bảo mật mà server thực thi.

## 1. Mục tiêu và nguyên tắc nền tảng

Sau bài này, bạn cần làm được bốn việc:

1. Giải thích vì sao cùng một endpoint có thể có kết quả khác nhau giữa browser, curl và service-to-service client.
2. Xác định request thực sự khác ở **method, URL, headers, cookie, Authorization, body, Origin, proxy hoặc TLS** hay không.
3. Phân biệt **CORS, CSRF, authentication, authorization** và nhận biết 200, 302, 401, 403, 404, 405 trong đúng bối cảnh.
4. Tái hiện một tình huống bằng curl, Java HttpClient và fetch; thu thập bằng chứng đủ để khoanh vùng lỗi ở browser, gateway, Spring Security hay nghiệp vụ.

**Quy tắc quan trọng:** Server nhận HTTP request, không nhận một “loại client” đáng tin chỉ vì User-Agent tự nhận là Chrome, curl hoặc Java. Hầu hết các header do client tạo đều có thể bị giả mạo ở ngoài trình duyệt. Server phải xác minh credential và quyền của principal, kiểm tra dữ liệu, và chỉ trao thông tin được phép xem.

## 2. Cả ba đều nói HTTP, khác nhau ở môi trường thực thi

Một request có thể có cấu trúc:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>

~~~

Response thành công có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"user":"alice"}
~~~

Các ví dụ HTTP/1.1 trên là biểu diễn minh họa. Trong thực tế trình duyệt hoặc HTTP client có thể dùng HTTP/2 hay HTTP/3; ngữ nghĩa method, URI, header, status và body vẫn tương ứng.

Về phía server, một API Spring MVC thường có luồng:

~~~text
Browser / curl / service client
             |
             | HTTP request
             v
     Reverse proxy / gateway
             |
             v
    Servlet Filter Chain
             |
             v
  Spring Security filters
     |             |
     | từ chối     | cho phép
     v             v
  401/403/...    Controller
                    |
                    v
               Service/DB
                    |
                    v
                Response
~~~

Đường đi là mô hình khái quát: gateway, middleware và các exception handler cũng có thể trả status trước hoặc sau filter. Trình duyệt còn áp dụng chính sách bảo mật **ở phía client** trước khi gửi một số request và trước khi cho JavaScript đọc response.

### 2.1. Bảng so sánh nhanh

| Khía cạnh | Trình duyệt (fetch/AJAX) | curl | Service backend (Java HttpClient, RestClient, WebClient...) |
| --- | --- | --- | --- |
| Ai phát request? | Trang web/script chạy trong trình duyệt, hoặc trình duyệt điều hướng tài liệu. | Người dùng/script dòng lệnh. | Mã chạy trên server hoặc worker. |
| Same-Origin Policy | Áp dụng cho quyền truy cập qua JavaScript; một số tài nguyên có quy tắc riêng. | Không có cơ chế trình duyệt này. | Không có cơ chế trình duyệt này. |
| CORS | Trình duyệt kiểm tra policy và có thể gửi OPTIONS preflight. | Không tự thực thi CORS; có thể chủ động gửi header Origin để thử. | Không tự thực thi CORS; thư viện có thể gửi Origin nếu được lập trình. |
| Cookie | Có cookie jar và quy tắc Domain, Path, Secure, HttpOnly, SameSite, credentials. | Không tự dùng cookie từ phiên trình duyệt; có thể chỉ định cookie hoặc cookie jar. | Thường không có cookie jar mặc định; tùy thư viện/cấu hình. |
| Authorization | Có thể do browser hoặc JavaScript đặt theo cơ chế đăng nhập. | Phải cung cấp rõ qua tham số/header hoặc cấu hình. | Phải lấy/đính kèm danh tính người dùng hoặc service theo chính sách. |
| CSRF | Browser có thể tự gửi cookie nên xuất hiện nguy cơ CSRF; server kiểm token khi áp dụng. | Không tự tạo CSRF token; vẫn bị server từ chối nếu thiếu token cần thiết. | Không tự tạo CSRF token; nếu gọi endpoint dùng session/cookie cũng phải đáp ứng policy. |
| Redirect | Trình duyệt điều hướng/fetch theo quy tắc redirect và policy bảo mật. | Mặc định không theo redirect; dùng -L khi cần. | Tùy thư viện; JDK HttpClient mặc định không theo redirect nếu chưa cấu hình. |
| TLS | Browser xác minh chứng chỉ theo trust store/policy trình duyệt. | curl xác minh chứng chỉ theo cấu hình và bộ CA; không nên dùng -k để né lỗi. | Java/HTTP stack xác minh TLS theo trust store/cấu hình. |
| Xem lỗi | Network panel, Console, fetch response hoặc lỗi bị policy chặn. | Thấy trực tiếp status/header/body nhận được từ server nếu không bị kết nối lỗi. | Log/exception/HTTP response theo code và policy client. |
| Vị trí mạng | Máy người dùng với DNS/proxy/VPN riêng. | Máy chạy curl; có thể là cùng hoặc khác mạng. | Máy chủ/pod; DNS, egress, firewall, proxy và quyền riêng. |

**Cần so sánh request thật, không chỉ URL được gõ.** Một GET từ browser có thể mang cookie session; lệnh curl không mang cookie, còn backend tự gắn service token khác. Vì vậy server có thể trả ba status khác nhau trong khi endpoint và method nhìn giống nhau.

## 3. Trình duyệt: origin, Same-Origin Policy và CORS

### 3.1. Origin là gì?

Một **origin** là bộ ba **scheme + host + port**:

- https://app.example.test và https://api.example.test: hai origin khác nhau vì host khác.
- http://localhost:3000 và http://localhost:8080: hai origin khác nhau vì port khác.
- http://localhost:8080 và https://localhost:8080: hai origin khác nhau vì scheme khác.

**Same-site** không đồng nghĩa **same-origin**. Hai subdomain cùng site có thể khác origin dù quy tắc SameSite cookie coi chúng là same-site theo mô hình áp dụng. CORS dùng origin, trong khi SameSite dùng khái niệm site.

**Same-Origin Policy (SOP)** hạn chế việc JavaScript thuộc một origin truy cập nội dung từ origin khác. Tuy nhiên, nó không có nghĩa rằng browser tuyệt đối không được gửi cross-origin request: điều hướng, form, ảnh hoặc một số fetch có thể gửi request; khả năng script **đọc response** còn phụ thuộc vào chính sách bảo mật và CORS.

### 3.2. Browser gọi fetch tới origin khác

Giả sử giao diện chạy tại http://localhost:3000 và API tại http://localhost:8080. Đoạn mã được chạy trong Console của trang ở origin giao diện:

~~~javascript
const response = await fetch("http://localhost:8080/api/public");
console.log(response.status);
console.log(await response.text());
~~~

Nếu API không cho phép origin http://localhost:3000 đọc response, trình duyệt có thể gửi GET và server **vẫn trả 200**, nhưng JavaScript nhận lỗi CORS hoặc TypeError: Failed to fetch. Trong DevTools Network đôi khi vẫn nhìn thấy response network. **Lỗi CORS không đồng nghĩa backend chưa xử lý request.**

Nếu server cho phép bằng policy phù hợp, response có thể chứa:

~~~http
Access-Control-Allow-Origin: http://localhost:3000
Vary: Origin
~~~

Khi server trả Access-Control-Allow-Origin phù hợp, browser cho JavaScript đọc response theo quy tắc CORS. Header này **không phải chứng cứ xác thực user** và không thay thế kiểm soát quyền trên server.

### 3.3. Khi nào có OPTIONS preflight?

Một số cross-origin request cần **CORS preflight**. Ví dụ script gắn Authorization hoặc gửi Content-Type: application/json cho POST, browser thường gửi OPTIONS trước:

~~~http
OPTIONS /api/private HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization

~~~

Server trả các header cho phép, ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Allow-Credentials: true
Vary: Origin

~~~

**Đây là response ví dụ**, status preflight thành công có thể khác tùy server. Sau khi preflight hợp lệ, browser mới gửi request nghiệp vụ tương ứng. Nếu preflight thất bại, browser không gửi request nghiệp vụ theo luồng fetch đó.

Lưu ý:

- Một cross-origin GET “đơn giản” có thể được gửi **không cần preflight**, dù việc đọc response vẫn chịu CORS.
- Không phải mọi OPTIONS đều là CORS preflight. Preflight có **Origin**, **Access-Control-Request-Method** và khi cần có **Access-Control-Request-Headers**.
- Preflight không phải login và thường không kèm credential như cookie; cần xử lý CORS phù hợp trước khi bắt xác thực cho request nghiệp vụ.
- Chấp nhận OPTIONS **không có nghĩa** sẽ cho phép GET/POST tương ứng: request thật vẫn phải trải qua authentication, authorization và các kiểm soát khác.
- Không dùng Access-Control-Allow-Origin: * cùng Access-Control-Allow-Credentials: true. Khi cần credential, server phải cho phép origin cụ thể và kiểm tra policy phù hợp.

### 3.4. Browser không cho JavaScript tùy tiện đặt mọi header

JavaScript fetch không thể tự đặt một số header do trình duyệt quản lý, ví dụ Host, Cookie và Origin theo cách tùy tiện. Browser quyết định các header đó dựa trên URL, cookie jar và policy. Trong khi đó, curl có thể tự tạo Origin giả và nhiều loại header request để thử nghiệm.

Vì thế **không bao giờ tin Origin, User-Agent hoặc X-Role chỉ vì “trình duyệt tự đặt”**. Ngoài browser, các header ấy có thể bị giả. Origin có giá trị trong CORS và có thể được dùng làm tín hiệu phòng vệ CSRF theo threat model, nhưng không chứng minh principal được cấp quyền.

### 3.5. Cookie và chế độ credentials của fetch

Khi ứng dụng đăng nhập bằng session cookie, browser có thể giữ cookie và tự gửi cho request phù hợp theo domain/path/SameSite/Secure. JavaScript không cần đọc cookie HttpOnly để trình duyệt gửi cookie đó.

Với fetch:

- Mặc định credentials: "same-origin": trình duyệt gửi credential trong bối cảnh same-origin theo policy.
- Cross-origin fetch muốn gửi cookie hợp lệ thường cần **credentials: "include"**, đồng thời cookie phải được phép theo Domain/Path/Secure/SameSite và chính sách browser.
- Server cũng cần CORS cho phép origin cụ thể và Access-Control-Allow-Credentials: true nếu browser được phép cho script nhận credentialed response.
- credentials: "include" **không tự tạo thông tin đăng nhập**; nó chỉ ảnh hưởng cách trình duyệt xử lý credential đã có.
- SameSite và CORS giải quyết những vấn đề khác nhau. Có thể một origin được CORS cho phép nhưng cookie vẫn không được gửi vì SameSite hoặc quy tắc third-party cookie.

Ví dụ cấu hình request từ giao diện (chỉ có ý nghĩa nếu server thật dùng cookie session):

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include",
  headers: { Accept: "application/json" }
});
console.log(response.status);
~~~

Nếu không có cookie hợp lệ, endpoint bảo vệ vẫn có thể trả 401 hoặc redirect tới login. Thêm credentials: "include" không giải quyết được sự thiếu session hợp lệ.

### 3.6. Browser, CORS và CSRF là ba lớp vấn đề khác nhau

**CORS** chủ yếu quản lý việc JavaScript của origin này có được đọc response từ origin khác hay không.

**CSRF** là nguy cơ kẻ tấn công khiến trình duyệt của người dùng gửi request có side effect tới ứng dụng mà browser tự đính kèm credential (đặc biệt session cookie). Một số request có thể được gửi ngay cả khi script không được đọc response. Vì vậy **CORS không thay thế CSRF protection**.

Với session/cookie, POST/PUT/PATCH/DELETE thường phải có CSRF token hoặc một cơ chế chống giả mạo tương đương được thiết kế đúng. Spring Security có cơ chế CSRF. Với API stateless chỉ nhận Bearer token do ứng dụng chủ động gắn trong Authorization và không chấp nhận credential tự gửi, nguy cơ CSRF thường khác, nhưng vẫn cần bảo vệ token và chống XSS.

Nếu API đổi trạng thái bằng GET, việc dựa vào quy tắc mặc định “GET là safe nên không cần CSRF token” có thể gây nguy hiểm. Thiết kế HTTP method đúng ngữ nghĩa trước khi chọn policy CSRF.

## 4. curl: gửi HTTP trực tiếp và chủ động kiểm soát request

curl là HTTP client dòng lệnh. Nó **không thực thi SOP/CORS của trình duyệt**, không có sẵn phiên đăng nhập trong Chrome/Edge và không tự lấy cookie của browser. Người dùng phải chủ động cung cấp credential và các header cần thiết.

Trên Windows PowerShell nên dùng **curl.exe** để tránh xung đột với alias curl của một số bản PowerShell. Trên Linux/macOS thông thường dùng curl.

### 4.1. Các lệnh cơ bản

~~~bash
curl.exe -i https://api.example.test/api/public
curl.exe -i -X GET https://api.example.test/api/profile
curl.exe -i -H "Accept: application/json" https://api.example.test/api/public
~~~

- **-i:** hiển thị cả response headers và body.
- **-I:** thường yêu cầu HEAD và chỉ hiển thị response headers, không thay thế một GET thực tế khi muốn kiểm tra body.
- **-X:** đặt method; không nên dùng -X GET/POST không cần thiết vì curl có cách chọn method phù hợp với body.
- **-v:** xem trao đổi HTTP/TLS để debug, nhưng có thể làm lộ credential hoặc dữ liệu nhạy cảm; che thông tin trước khi chia sẻ log.
- **--fail-with-body:** khiến curl trả exit code lỗi khi HTTP response báo lỗi từ server, đồng thời giữ body để chẩn đoán; khả dụng ở bản curl hỗ trợ.

HTTP 401/403 **không nhất thiết là lỗi thực thi dòng lệnh** đối với curl nếu không dùng các cờ coi status HTTP là lỗi. Phân biệt exit code của tiến trình curl với HTTP status do server trả về.

### 4.2. Gửi Authorization

Với Bearer token dùng trong môi trường thử nghiệm:

~~~bash
curl.exe -i -H "Authorization: Bearer DEMO_TOKEN" \
  https://api.example.test/api/profile
~~~

Cú pháp xuống dòng với ký tự \ ở cuối là dạng shell Unix. Trong PowerShell, nên viết trên **một dòng** hoặc dùng cú pháp nối dòng phù hợp:

~~~powershell
curl.exe -i -H "Authorization: Bearer DEMO_TOKEN" https://api.example.test/api/profile
~~~

HTTP Basic cho môi trường thử nghiệm:

~~~powershell
curl.exe -i -u reader:demo-password http://localhost:8080/api/private
~~~

Trong môi trường thật, tránh đặt secret thật vào command history, process arguments, màn hình chia sẻ hoặc log; ưu tiên quản lý credential bằng cơ chế phù hợp. HTTP Basic chỉ mã hóa Base64 credentials, **cần HTTPS** khi trao đổi qua mạng thực tế.

### 4.3. Cookie jar trong curl

Nếu server đăng nhập bằng cookie, chỉ gọi một URL API không đồng nghĩa curl đã có session giống trình duyệt. Có thể dùng cookie jar:

~~~bash
curl.exe -i -c cookies-demo.txt https://api.example.test/login
curl.exe -i -b cookies-demo.txt https://api.example.test/api/me
~~~

Hai lệnh chỉ minh họa cách **lưu/đọc cookie**; lệnh đầu không tự chứng minh đã đăng nhập vì login thật thường cần POST, form data hoặc luồng OAuth, và có thể cần CSRF token. File cookie jar chứa thông tin nhạy cảm, phải được bảo vệ và xóa đúng quy trình sau test.

Gửi thủ công cookie thử:

~~~powershell
curl.exe -i -b "SESSION=example-session" http://localhost:8080/api/me
~~~

Cookie phải hợp lệ phía server. Một chuỗi cookie tự đặt không tạo quyền truy cập. Nếu server yêu cầu CSRF token, curl phải gửi token tương ứng; việc dùng curl **không bỏ qua** kiểm tra CSRF trên server.

### 4.4. curl với CORS và redirect

Thử mô phỏng Origin của browser:

~~~powershell
curl.exe -i -H "Origin: http://localhost:3000" http://localhost:8080/api/public
~~~

Gửi một preflight đầy đủ:

~~~powershell
curl.exe -i -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" http://localhost:8080/api/private
~~~

curl in ra response ngay cả khi không có Access-Control-Allow-Origin. Nhưng **server vẫn có thể chủ động từ chối** request mang Origin không được phép, ví dụ bộ xử lý CORS của Spring trả 403. Điều này không biến Origin thành credential: curl có thể không gửi Origin, còn quyền truy cập thực sự phải do authentication/authorization quyết định.

Với redirect:

~~~powershell
curl.exe -i http://localhost:8080/api/private
curl.exe -i -L http://localhost:8080/api/private
~~~

Lệnh đầu không tự đi theo Location; lệnh thứ hai cho curl theo redirect. Nếu server dùng form login, response đầu có thể là 302 tới trang đăng nhập. Theo redirect có thể cho ra 200 **của trang login**, không phải 200 của tài nguyên API được bảo vệ. Kiểm tra URL cuối cùng và Content-Type trước khi kết luận thành công.

Trong TLS, curl xác minh chứng chỉ theo CA store/cấu hình. Không dùng tùy tiện **-k/--insecure** để làm mất kiểm tra certificate; sửa CA, hostname hoặc trust chain đúng với môi trường.

## 5. Service gọi service khác: HTTP client chạy trong backend

Một service khác có thể dùng Java HttpClient, Spring RestClient, WebClient, OpenFeign hoặc thư viện tương tự. Về mặt HTTP, nó vẫn gửi method, URL, headers và body. Khác với browser:

- Không có Same-Origin Policy của browser, vì vậy không cần “bật CORS để hai microservice nói chuyện”.
- Không tự có session của người dùng trên trình duyệt. Code cần quyết định **gọi với danh tính service** hay **đại diện user**; hai mô hình cấp quyền khác nhau.
- Có thể chạy trong cluster hoặc mạng nội bộ với DNS, firewall, service discovery, proxy, TLS và egress policy riêng.
- Phải cấu hình timeout, connection pooling, retry/idempotency, observability, token cache/refresh, certificate trust và giới hạn outbound data.
- Nếu service dùng cookie, vẫn phải chủ động quản lý cookie/session và đáp ứng chính sách CSRF của server khi áp dụng. Không có một đặc quyền “backend được miễn CSRF” trong giao thức.

### 5.1. Hai loại danh tính thường gặp

**Service identity:** Backend A gọi Backend B để thực hiện công việc của chính A. Có thể dùng OAuth2 Client Credentials, mTLS hoặc cơ chế machine-to-machine khác đã được thiết kế. Token/credential cần có scope, audience, thời hạn và quyền tối thiểu.

**User delegation:** Backend A gọi Backend B để hoàn thành thao tác thay mặt user. Backend B phải biết và xác minh ngữ cảnh người dùng theo cơ chế được cấp phép (ví dụ delegated token hoặc token exchange). **Không chuyển tiếp tùy tiện token nhận từ client** sang mọi dịch vụ: token có thể không được cấp cho audience của B và có thể làm lộ quyền rộng hơn dự kiến.

Ví dụ flow:

~~~text
Browser -> Service A -> Service B -> Database
         (user token) (service/delegated token)

Service B cần xác minh:
- Ai gọi? Service A hay người dùng nào được đại diện?
- Credential còn hợp lệ và cấp cho B hay không?
- Caller có scope/authority cho hành động không?
- Tài nguyên cụ thể có thuộc user/tenant hoặc quyền của caller không?
~~~

Dù A đã xác thực user, B vẫn cần **kiểm soát ranh giới tin cậy**. Không mặc nhiên coi request “đến từ nội bộ” là hợp lệ, không tin role do A đặt trong header tùy ý nếu thiếu bảo đảm xác thực giữa các service.

### 5.2. Các lỗi client backend thường gặp

- **401:** token không có, hết hạn, sai issuer/audience, hoặc credential bị cấu hình nhầm.
- **403:** service có danh tính hợp lệ nhưng thiếu scope/role/quyền đối tượng.
- **404:** URL nội bộ hoặc path rewrite sai, route không tồn tại, hoặc resource bị che giấu theo policy.
- **429:** vượt hạn mức; retry cần backoff và tôn trọng Retry-After khi có.
- **502/503/504:** gateway, upstream hoặc network gặp vấn đề; cấu hình timeout và retry hợp lý.
- **SSLHandshakeException:** chứng chỉ/trust store/hostname/mTLS không khớp; không sửa bằng cách tắt kiểm tra TLS.
- **Redirect bất ngờ:** service có thể nhận 302 tới HTML login thay vì JSON, đặc biệt khi endpoint dành cho browser được gọi bằng HTTP client backend.

Khi service cho phép nhập URL đích, cần quan tâm **SSRF** và giới hạn mạng outbound: allowlist các đích nghiệp vụ, kiểm tra scheme/host và xử lý DNS/redirect, không truyền credential tới hostname không tin cậy.

## 6. Cùng một API: ba request thực tế có thể khác nhau

Giả sử GET /api/profile yêu cầu đăng nhập. Đây là các request ví dụ, không giả định rằng ba client có cùng danh tính:

### 6.1. Browser đã có session cookie

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Cookie: SESSION=<session-id>
Origin: https://app.example.test

~~~

Cookie có thể tự được gửi nếu browser policy cho phép; Origin xuất hiện khi ngữ cảnh browser yêu cầu. Nếu là cross-origin fetch, response còn cần thỏa CORS để JavaScript đọc. Nếu cookie bị chặn hoặc chưa login, request có thể thành 401/302.

### 6.2. curl không có credential

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Accept: */*

~~~

Nếu server yêu cầu credential, curl có thể nhận 401 và WWW-Authenticate. Thiếu cookie trong curl khác với một browser đã đăng nhập. Muốn tái hiện chính xác, so sánh cookie/Authorization đã được che giá trị nhạy cảm.

### 6.3. Service gửi Bearer token riêng

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer <service-token>
Accept: application/json

~~~

Service token có thể xác thực thành công nhưng **không đại diện user** cần đọc profile. Endpoint có thể trả 403 hoặc kết quả khác tùy policy. Ngược lại, một token service được cấp đúng scope có thể hoạt động ở endpoint machine-to-machine riêng.

### 6.4. Tình huống HTTP status giống nhưng ý nghĩa khác

| Hiện tượng | Browser | curl | Backend service |
| --- | --- | --- | --- |
| API yêu cầu đăng nhập | Có thể 401, 302, hoặc lỗi CORS che response khỏi JavaScript. | Nhìn thấy 401/302 trực tiếp. | Nhận 401/302 hoặc exception nếu client cấu hình coi status là lỗi. |
| Server trả 403 do thiếu role | Có thể thấy 403 trong fetch response nếu CORS hợp lệ. | Nhận 403. | Nhận 403. |
| POST thiếu CSRF token | Có thể bị Spring Security trả 403. | Cũng bị 403 nếu endpoint áp dụng CSRF. | Cũng bị 403 nếu dùng cơ chế/endpoint yêu cầu token. |
| Origin không được phép đọc response | Browser ngăn JavaScript đọc; có thể preflight fail. | Không có browser enforcement; server có thể từ chối nếu nhận Origin. | Không có browser enforcement; server/gateway vẫn có thể có rule riêng. |
| Request được 200 nhưng chưa chắc đúng dữ liệu | Có thể bị hạn chế đọc bởi CORS, hoặc đọc được sau khi auth đúng. | In body 200. | Parse body 200 theo client; vẫn cần kiểm schema và quyền. |
| Server redirect tới /login | Browser thường đi theo redirect; fetch có thể gặp response HTML/CORS. | Cần -L để đi theo. | Tùy chính sách redirect của client. |

**Không suy luận “curl chạy được nên CORS đúng”, hoặc “browser lỗi CORS nên Spring Security sai”.** Phải phân tích cả request đã gửi, response thực sự, preflight và chính sách của từng thành phần.

## 7. Demo Spring Boot 3.3.x, Java 17+: cùng API cho ba client

Ví dụ dưới đây tạo API với ba endpoint, HTTP Basic dành cho học tập, CORS chỉ cho phép origin http://localhost:3000 và CSRF giữ cấu hình mặc định. Mục tiêu là **quan sát chính sách HTTP**, không phải xây dựng hệ thống đăng nhập production.

Yêu cầu: Java 17+, Maven 3.9+, cổng 8080 và 3000 chưa bị chiếm. Tài khoản reader/demo chỉ phục vụ thử nghiệm, không dùng trên Internet và không dùng cho dữ liệu thật.

Cấu trúc:

~~~text
demo-client-calls/
  pom.xml
  src/main/java/com/example/demo/ApiApplication.java
~~~

### 7.1. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>demo-client-calls</artifactId>
    <version>1.0.0</version>
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

### 7.2. Tệp src/main/java/com/example/demo/ApiApplication.java

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
@RestController
public class ApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/private")
    public String privateEndpoint(Authentication auth) {
        return "private:" + auth.getName();
    }

    @PostMapping("/api/actions")
    public String action() {
        return "changed";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers("/api/private", "/api/actions").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Giữ CSRF mặc định: POST thường cần CSRF token.
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("http://localhost:3000"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "X-CSRF-TOKEN")
        );
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Giải thích:

- GET /api/public công khai nhờ matcher GET cụ thể.
- GET /api/private yêu cầu danh tính hợp lệ; ở đây dùng HTTP Basic và user in-memory.
- POST /api/actions cũng yêu cầu danh tính; ngoài ra CSRF mặc định sẽ từ chối yêu cầu thay đổi trạng thái thiếu token khi rule CSRF áp dụng.
- http.cors() tích hợp CORS để xử lý preflight thích hợp trước authentication trong filter chain.
- CORS chỉ cho phép **http://localhost:3000**. Origin http://localhost:3001 hoặc file:// không tự được chấp nhận.
- anyRequest().denyAll() giúp đóng các route không thuộc phạm vi minh họa.
- Không có logic role/ownership trong demo. API thật còn phải bổ sung quyền đối tượng, quota, logging và cấu hình session/token phù hợp.

**Chạy ứng dụng** tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Vì ví dụ sử dụng HTTP Basic với tài khoản thử nghiệm và HTTP localhost, chỉ thử trên máy của mình; **không triển khai công khai**. Khi dùng credential thật qua mạng, cần HTTPS và cơ chế quản lý danh tính đúng.

### 7.3. Gọi bằng curl

Trên PowerShell, chạy:

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/private
curl.exe -i -u reader:demo http://localhost:8080/api/private
curl.exe -i -u reader:demo -X POST http://localhost:8080/api/actions
~~~

**Kết quả mong đợi:**

| Thử nghiệm | Status | Body/giải thích |
| --- | --- | --- |
| GET /api/public không credential | 200 | public |
| GET /api/private không credential | 401 | Có WWW-Authenticate: Basic ... |
| GET /api/private với reader/demo | 200 | private:reader |
| POST /api/actions với reader/demo, thiếu CSRF token | 403 | Spring Security từ chối trước khi gọi action() |

Các header phụ có thể thay đổi theo Spring Security/Servlet container. Response 403 không nói rằng user thiếu role: trong trường hợp POST trên là **CSRF protection**. Nếu để CSRF token hợp lệ hoặc điều chỉnh chính sách cho một API stateless theo threat model, kết quả có thể khác.

Thử preflight:

~~~powershell
curl.exe -i -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization" http://localhost:8080/api/private
~~~

Kết quả mong đợi là preflight được chấp nhận và có các header Access-Control-Allow-Origin, Access-Control-Allow-Methods và Access-Control-Allow-Headers phù hợp. **Preflight thành công không trả dữ liệu private:reader và không xác thực user.**

Sau đó gọi GET có Origin hợp lệ:

~~~powershell
curl.exe -i -u reader:demo -H "Origin: http://localhost:3000" http://localhost:8080/api/private
~~~

Server có thể trả 200 kèm Access-Control-Allow-Origin: http://localhost:3000. Nếu gửi Origin ngoài danh sách cho phép, bộ xử lý CORS có thể trả 403; nhưng gọi bằng curl **không gửi Origin** vẫn có thể tới API và được bảo vệ bằng HTTP Basic. Đó là lý do không dùng CORS làm hệ thống xác thực.

### 7.4. Gọi bằng trình duyệt

Tạo tệp **index.html** ở một thư mục riêng:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Browser API demo</title>
</head>
<body>
  <button id="call">Gọi API</button>
  <pre id="result"></pre>
  <script>
    document.getElementById("call").addEventListener("click", async () => {
      const result = document.getElementById("result");
      const basic = btoa("reader:demo"); // Chỉ dùng tài khoản demo.
      try {
        const response = await fetch(
          "http://localhost:8080/api/private",
          {
            method: "GET",
            credentials: "include",
            headers: {
              Authorization: "Basic " + basic,
              Accept: "text/plain"
            }
          }
        );
        result.textContent =
          "HTTP " + response.status + ": " + await response.text();
      } catch (error) {
        result.textContent = "Fetch failed: " + String(error);
      }
    });
  </script>
</body>
</html>
~~~

Dùng một static server để mở trang bằng **http://localhost:3000** (ví dụ, trong thư mục có index.html, nếu máy đã có Python):

~~~bash
python -m http.server 3000
~~~

Trong Windows cũng có thể dùng **py -m http.server 3000** nếu Python được cài với launcher. Mở http://localhost:3000/index.html và bấm nút.

**Kết quả mong đợi trên trang:** HTTP 200: private:reader. Trong DevTools Network sẽ có OPTIONS preflight vì request cross-origin có Authorization, sau đó là GET được xác thực. CORS trên backend cho phép đúng origin http://localhost:3000. Đoạn mã có mật khẩu demo lộ trong JavaScript **chỉ dùng cho bài học**; ứng dụng production không nhúng mật khẩu cố định hoặc secret service vào frontend.

Để xem kết quả khác, mở cùng file qua một origin khác, ví dụ http://127.0.0.1:3000 hoặc http://localhost:3001 sau khi host phù hợp. Trình duyệt sẽ phát sinh Origin khác với danh sách cho phép và có thể chặn request từ preflight. Thông báo trong Console là lỗi CORS; không phải thông báo “mật khẩu chắc chắn sai”.

Không mở index.html bằng file:// để so sánh origin trong ví dụ này: trang file:// thường tạo origin đặc biệt (có thể được biểu diễn là null) và không nằm trong danh sách allowlist.

### 7.5. Gọi bằng một dịch vụ Java 17

Tệp **ServiceClient.java** dưới đây là chương trình Java độc lập. API Spring Boot ở trên phải đang chạy.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

public class ServiceClient {

    public static void main(String[] args) throws Exception {
        String demo = "reader:demo";
        String basic = Base64.getEncoder().encodeToString(
            demo.getBytes(StandardCharsets.UTF_8)
        );

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:8080/api/private"))
            .timeout(Duration.ofSeconds(10))
            .header("Accept", "text/plain")
            .header("Authorization", "Basic " + basic)
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("HTTP " + response.statusCode());
        System.out.println("Body " + response.body());
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac ServiceClient.java
java ServiceClient
~~~

**Stdout kỳ vọng chính xác**, khi server demo đang chạy và không có interceptor/proxy khác:

~~~text
HTTP 200
Body private:reader
~~~

Chương trình **không gửi Origin**, vì đây không phải một script đang chạy trong browser. Spring Security vẫn kiểm tra HTTP Basic như với curl. Java HttpClient không cần CORS để đọc response. Trong dự án thật, không hard-code mật khẩu hay gửi Basic qua HTTP; dùng quản lý secret, OAuth2 client credentials/delegation hoặc mTLS theo thiết kế, HTTPS và timeout/retry đúng nghiệp vụ.

Các thư viện HTTP client có cách xử lý cookie, redirect và exception khác nhau. Với **JDK HttpClient** trong ví dụ, nếu không cài CookieHandler thì không có browser cookie jar; nếu không cấu hình followRedirects thì mặc định **NEVER**. Những điều này không tự động giống curl hoặc fetch.

## 8. Phân tích một loạt tình huống lỗi thường gặp

### 8.1. Browser báo CORS, curl nhận 200

Kiểm tra **Origin** thực sự trong DevTools, OPTIONS preflight, Access-Control-Allow-Origin và credentials mode. curl không áp dụng chính sách đọc cross-origin của browser; nó có thể lấy nội dung dù response không có CORS headers. Xem thêm server có thực sự từ chối request với Origin không, vì Spring CORS processor có thể trả 403 đối với origin bị cấm.

Giải pháp đúng là cấu hình origin được phép theo nghiệp vụ. Không tùy tiện mở wildcard, bật credentials cho mọi origin hoặc tắt bảo vệ API.

### 8.2. Browser chạy được sau login, curl 401

Browser có thể mang session cookie hoặc HTTP Basic credential đã được lưu theo chính sách. curl thường chưa có cookie/Authorization tương ứng. So sánh cookie jar, header Authorization, scope, expiry và cơ chế auth. Không copy token thật vào tài liệu hoặc log để đối chiếu.

### 8.3. curl nhận JSON 401, browser thấy trang đăng nhập

Form login có thể trả 302 redirect tới login page, browser theo redirect, rồi hiển thị HTML với status cuối 200. HTTP Basic/Bearer API thường có 401/challenge. Xác định **AuthenticationEntryPoint**, Accept, endpoint match và URL cuối sau redirect. HTTP status cuối 200 không chứng minh request ban đầu đã truy cập được tài nguyên bảo vệ.

### 8.4. GET thành công ở cả ba, POST bị 403

Có thể do **CSRF token thiếu** trong ứng dụng dùng cookie/session hoặc dùng HTTP Basic với CSRF đang bật; cũng có thể là thiếu role/quyền. Quan sát status, log bảo mật và cấu hình Spring Security. Đừng vội tắt CSRF chỉ vì POST từ curl hoặc Postman bị 403.

### 8.5. Service có token nhưng bị 403

Token của service có thể hợp lệ nhưng scope, audience, role hoặc quyền đối tượng không phù hợp. Mô hình “service được xác thực” khác “service được cấp quyền thực hiện mọi hành động”. Kiểm lại chính sách của API đích và loại token đang dùng.

### 8.6. curl trên máy cá nhân thành công, service trong cluster timeout

Đây có thể là khác biệt **DNS, proxy, egress firewall, service discovery, TLS/mTLS, certificate trust hoặc timeout**. CORS thường không liên quan. Cần quan sát request ở từng mạng, hostname được resolve, TLS handshake và dấu vết phía gateway.

### 8.7. API trả 200 trong Network, JavaScript vẫn báo Failed to fetch

Network thành công không có nghĩa JavaScript được đọc response. Browser có thể chặn vì CORS, mixed content, TLS, policy của extension hoặc vấn đề kết nối khác. Đọc **Console error**, nhìn request/preflight và response headers; đừng suy luận từ status đơn lẻ.

### 8.8. Endpoint thật trả 404 khi đổi token hoặc đổi user

Có thể do ẩn sự tồn tại của tài nguyên không thuộc chủ thể, do gateway route, do URL khác hoặc dữ liệu không tồn tại. Cần phân biệt 404 route với 404 theo chính sách truy cập object. Bất kể trả 403 hay 404, body không được lộ dữ liệu của người khác.

## 9. Authentication, authorization và CORS cần được đặt đúng tầng

| Cơ chế | Ai thực thi? | Quyết định điều gì? | Không thay thế được |
| --- | --- | --- | --- |
| **TLS/HTTPS** | Client và các TLS endpoint | Bảo vệ kết nối, kiểm tra chứng chỉ/peer theo cấu hình. | Quyền truy cập dữ liệu và logic nghiệp vụ. |
| **Authentication** | Backend/API/gateway đáng tin cậy | Credential có hợp lệ? Danh tính là ai? | Quyền trên từng thao tác/tài nguyên. |
| **Authorization** | Backend/Service/domain | Danh tính này được thực hiện hành động nào trên dữ liệu nào? | Kiểm soát request giả mạo hoặc đầu vào độc hại. |
| **CORS** | Browser thực thi policy nhận response; server cấu hình header/chấp nhận origin | Script từ origin nào được đọc cross-origin response? | Authentication, authorization, CSRF, API firewall. |
| **CSRF protection** | Chủ yếu server với browser client tương ứng | Request thay đổi trạng thái có phải hành động được phép trong ngữ cảnh phiên? | Authentication, kiểm role, chống XSS. |
| **Rate limiting/quota** | Gateway/API/infra | Giới hạn khối lượng request và tài nguyên bị tiêu thụ. | Xác thực/quyền và kiểm dữ liệu. |
| **Service identity/mTLS** | Các service và hạ tầng tin cậy | Máy/service nào đang gọi? Kênh giữa service được xác minh thế nào? | Quyền của người dùng/tenant và business rule. |

Một sai lầm phổ biến là nhìn Access-Control-Allow-Origin rồi nghĩ “API chỉ cho phép gọi từ website này”. Thực tế, browser chỉ hạn chế script đọc dữ liệu theo chính sách origin; curl/service thường không có hạn chế đó. Nếu dữ liệu cần bảo vệ, **server phải yêu cầu danh tính và quyền đúng** bất kể nguồn HTTP client.

Đồng thời, không xem mỗi request từ browser là đáng tin: input validation, object-level authorization, anti-CSRF, CSP/XSS prevention, file upload controls và audit vẫn cần thiết.

## 10. Quy trình debug cùng một API qua ba client

Để so sánh có căn cứ, thu thập thông tin theo thứ tự sau.

**Bước 1 — Xác nhận request đích.** So sánh scheme, host, port, path, query, method và environment. Một URL nhìn giống nhau có thể đi qua DNS/proxy khác nhau.

**Bước 2 — So sánh credential.** Header Authorization có tồn tại không (che giá trị), cookie có được gửi không, principal và scope/roles nào được xác thực ở server? Đừng dùng một session browser rồi mặc định curl có cùng quyền.

**Bước 3 — Phân biệt request chính và preflight.** Trong DevTools, xem OPTIONS và GET/POST là hai request khác nhau. Khi OPTIONS thất bại, có thể chưa có request nghiệp vụ để tra log.

**Bước 4 — Đọc cả status và headers.** Quan sát Location, WWW-Authenticate, Access-Control-Allow-Origin, Access-Control-Allow-Credentials, Set-Cookie, Content-Type, Cache-Control và các header gateway liên quan. Kiểm tra URL cuối nếu có redirect.

**Bước 5 — So khớp timestamp và correlation ID.** Dùng request ID để tìm trong log gateway/API; không ghi Authorization hoặc Cookie raw. Nếu browser báo lỗi nhưng backend không có log, kiểm preflight, TLS, DNS, proxy hoặc client policy.

**Bước 6 — Kiểm thử quyền theo object và side effects.** Request 200 nhưng body sai user vẫn là lỗi; POST trả 403 sau khi đã đổi DB vẫn là lỗi. Đảm bảo denied request không tạo tác động trái phép.

**Bước 7 — Kiểm tra policy theo môi trường.** So các biến thể localhost, staging, production, origin frontend, reverse proxy, trusted forwarded headers, port management và cấu hình Spring SecurityFilterChain nào đang khớp.

Dùng một bảng chẩn đoán ngắn:

| Đặc điểm | Browser | curl | Service |
| --- | --- | --- | --- |
| Actual method + URL | Ghi từ Network | Ghi từ -v/-i | Ghi từ HTTP client diagnostics |
| Origin/preflight | Có thể tự sinh | Chỉ có nếu tự gửi | Chỉ có nếu code/framework gửi |
| Credential | Cookie/Basic/Bearer theo policy | Header/cookie đã cung cấp | Service token/delegated token theo code |
| Response status | Phân biệt network status và fetch-access error | In trực tiếp | Status/exception tùy client |
| Dữ liệu & side effect | Kiểm Network và UI | Kiểm body | Kiểm body + downstream state |

Không nên chụp, dán hoặc chia sẻ raw token, password, session cookie, client secret hoặc dữ liệu khách hàng khi ghi bằng chứng.

## 11. Kiểm thử ba client và kỳ vọng bảo mật

Trong cùng API, dùng nhiều danh tính và loại HTTP client để xác minh các thuộc tính khác nhau:

| Bài kiểm thử | Cách gọi | Kỳ vọng cần kiểm |
| --- | --- | --- |
| Anonymous GET private | curl không credential | 401/challenge hoặc policy entry point tương ứng. |
| Browser fetch từ origin được phép | fetch + auth hợp lệ | Preflight (nếu cần) thành công, response đọc được. |
| Browser fetch từ origin không cho phép | fetch + origin khác | Script không đọc được response; actual request có thể không được gửi nếu preflight fail. |
| curl không có Origin nhưng auth hợp lệ | curl -u / Bearer | Được server xét authn/authz; CORS không phải “khóa API”. |
| User thường gọi chức năng admin | Bất kỳ client có credential USER | Bị từ chối theo authorization, không side effect. |
| POST thiếu CSRF token ở endpoint dùng session | Browser hoặc curl | Bị từ chối khi CSRF protection áp dụng. |
| Service token sai audience | Java HTTP client | Bị server từ chối; không chuyển tiếp token sai đích. |
| User A đọc tài nguyên User B | Browser, curl hoặc service được delegate cho A | Không nhận dữ liệu của B dù request hợp lệ về HTTP. |
| Retry request tạo giao dịch | Service client | Không tạo tác động trùng lặp nếu nghiệp vụ yêu cầu idempotency. |
| API lỗi qua gateway | curl trong pod / host riêng | Khoanh vùng DNS, TLS, proxy, timeout, upstream status. |

Bài kiểm thử về credential, URL, CSRF và CORS phải dùng **đúng cơ chế mà endpoint thực tế hỗ trợ**. Không tự suy đoán rằng mọi REST API dùng Bearer hoặc mọi trình duyệt đều dùng session cookie.

## 12. Những hiểu nhầm cần loại bỏ

1. **“curl gọi được nên CORS sai hoặc không có bảo mật.”** Curl không áp dụng CORS của browser; authn/authz vẫn phải kiểm trên server.
2. **“Chỉ website A mới gọi được API vì Allow-Origin là A.”** Allow-Origin giới hạn quyền JavaScript đọc response trong browser, không ngăn mọi client HTTP khác tự gửi request.
3. **“POST lỗi 403 chắc chắn là thiếu role.”** Có thể do CSRF, policy khác hoặc access control. Đọc log/filter và request thực tế.
4. **“Chỉ cần thêm credentials: include là đăng nhập được.”** Fetch không tự tạo session/token; cookie còn phụ thuộc policy, server và trạng thái đăng nhập.
5. **“Origin và User-Agent là bằng chứng nguồn request đáng tin.”** Ngoài browser chúng có thể bị giả mạo. Không dùng chúng làm danh tính người dùng.
6. **“Service nội bộ khỏi cần xác thực và phân quyền.”** Internal network không thay thế service identity, scope, audience và quyền dữ liệu.
7. **“HTTP Basic dùng Base64 nên mật khẩu được mã hóa.”** Base64 dễ giải mã; phải dùng HTTPS và secret management thích hợp.
8. **“Dùng curl thì server không kiểm tra CSRF.”** Nếu filter CSRF áp dụng cho request, curl thiếu token cũng có thể bị 403.
9. **“Network thấy 200 nghĩa là fetch đã thành công.”** Response có thể bị browser chặn đọc vì CORS hoặc policy khác.
10. **“302 rồi 200 nghĩa là gọi API thành công.”** Status 200 có thể thuộc trang login sau redirect, không phải resource yêu cầu.
11. **“X-Forwarded-For cho biết IP thật chắc chắn.”** Header chỉ đáng tin khi được proxy tin cậy quản lý theo kiến trúc.
12. **“Có JWT thì mọi service dùng chung token được.”** Token phải được cấp đúng audience/scope và truyền qua ranh giới tin cậy theo thiết kế.

## 13. Bài tập tự đánh giá

**Bài tập 1.** Một web frontend chạy trên http://localhost:3000, API trên http://localhost:8080. GET có Authorization hợp lệ trả 200 cho curl nhưng fetch báo lỗi CORS. Hãy ghi các bước để xác định browser có gửi OPTIONS không và response thiếu header nào. Giải thích vì sao không nên giải quyết bằng cách bỏ xác thực.

**Bài tập 2.** Browser đã đăng nhập và truy cập /api/me thành công. curl cùng URL trả 401. Hãy nêu ít nhất ba thông tin cần đối chiếu trong request (đáp án gợi ý: Cookie, Authorization, host/domain/path, redirect/login entry point).

**Bài tập 3.** Dùng API demo, chứng minh bằng curl rằng GET private cần credential, POST actions thiếu CSRF bị 403, và OPTIONS preflight không phải là hành động thay đổi dữ liệu. Quan sát status cùng các response headers cần thiết.

**Bài tập 4.** Viết một service client gửi token được cấp cho service B tới API của service C. Theo thiết kế bảo mật, điều gì cần được xác minh? (Gợi ý: audience, issuer, expiry, scope, chủ thể, quyền từng tài nguyên; đừng mặc nhiên chuyển tiếp token giữa các service.)

**Bài tập 5.** Một user A có session hợp lệ và dùng cả browser, curl, service delegation để đọc ID đơn của B. Dù cả ba client dùng HTTP khác nhau, thuộc tính bảo mật nào phải được bảo toàn? (Gợi ý: object-level authorization và không rò dữ liệu của B.)

### Checklist kết thúc

- Bạn có phân biệt **origin** với **site** và **CORS** với **authorization** chưa?
- Bạn có nhìn request **OPTIONS preflight** riêng với request nghiệp vụ chưa?
- Bạn có biết client nào tự gửi **cookie** và client nào phải tự gắn credential chưa?
- Bạn có thể giải thích vì sao 401/403/302 xuất hiện khác nhau khi **authentication entry point** hoặc cookie/session khác không?
- Bạn có biết một service cần token đúng **audience/scope**, TLS và giới hạn outbound không?
- Bạn có thể chứng minh bằng test rằng request thiếu quyền **không tạo side effect** và không lộ dữ liệu không?

## Kết luận

Browser, curl và backend service đều gọi HTTP nhưng khác nhau ở môi trường bảo mật, cách quản lý credential, cookie, preflight, redirect, TLS và đường đi mạng. Trình duyệt áp dụng SOP/CORS đối với JavaScript; curl chủ động tạo request; service backend cần quản lý danh tính và kết nối giữa các hệ thống. **Spring Security và tầng nghiệp vụ vẫn phải xác thực, phân quyền và bảo vệ dữ liệu cho mọi client.** Khi cùng một API hoạt động khác nhau, hãy so sánh request thực tế, phân biệt lỗi do browser policy với response của server, và kiểm tra quyết định bảo mật bằng test có thể tái hiện.
