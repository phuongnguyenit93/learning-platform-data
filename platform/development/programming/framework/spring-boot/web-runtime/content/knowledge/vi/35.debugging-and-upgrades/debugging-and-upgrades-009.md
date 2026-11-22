# Chẩn đoán mất phiên, cookie không được gửi và chuyển hướng sai giao thức

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Gỡ lỗi và nâng cấp

## 1. Bài toán: login thành công, sau đó lại bị đăng xuất

Một dịch vụ Spring Boot được chuyển từ HTTP trực tiếp sang Kubernetes Ingress với public URL **https://app.example.test/portal/**. Sau nâng cấp có người gặp các triệu chứng:

- POST login trả 200 hoặc 302, nhưng truy cập trang tiếp theo lại yêu cầu đăng nhập.
- Response login có **Set-Cookie: JSESSIONID=...**, nhưng request sau thiếu **Cookie: JSESSIONID=...**.
- Cookie được gửi đến backend, nhưng ứng dụng không tìm thấy **HttpSession**.
- Phiên HttpSession tồn tại nhưng Spring Security không khôi phục **Authentication**.
- Browser ở HTTPS nhận **Location: http://internal:8080/login**, hoặc lặp HTTPS → HTTP → HTTPS.
- Lỗi chỉ xảy ra khi request được cân bằng tải tới pod khác, hoặc sau restart/rolling upgrade.
- Frontend gửi fetch tới API khác origin, server có session nhưng browser không giữ credentials.

Đây không phải một lỗi duy nhất. Để sửa đúng, phải tìm ra **bước đầu tiên bị sai** trong luồng HTTP: server tạo session → response đặt cookie → browser lưu → browser gửi → backend tìm session → framework khôi phục authentication → redirect đúng public URL.

**Mục tiêu:** tự xác định root cause thay vì tắt CSRF, hạ Secure cookie hoặc bật SameSite=None một cách mù quáng.

Bài học dùng **Spring Boot 3.3**, Servlet/Spring MVC, Spring Security 6, Java 17+, cookie và reverse proxy. Ví dụ Java chính là một lab HttpSession không tích hợp login thật để tách transport bugs khỏi authentication. Các đoạn giải thích Security/Redis là hướng dẫn bổ sung, không giả vờ là các dependency đã có trong lab.

## 2. Chia hiện tượng thành sáu tầng để điều tra

~~~text
Browser GET/POST public HTTPS
       |
       v
[1] Response login có Set-Cookie?
       |
       v
[2] Browser có lưu cookie?
       |
       v
[3] Request kế có gửi Cookie theo URL/policy?
       |
       v
Ingress / proxy TLS termination, path rewrite
       |
       v
[4] Backend tìm được server-side HttpSession?
       |
       v
[5] SecurityContext/Authentication có được restore?
       |
       v
[6] Redirect Location có scheme/host/prefix đúng?
~~~

| Tầng | Cần kiểm | Nếu sai thì xem |
| --- | --- | --- |
| Response cookie | **Set-Cookie** có xuất hiện và hợp lệ? | Session chưa được tạo, policy stateless, headers bị proxy sửa. |
| Cookie storage | Cookie có được browser chấp nhận? | Domain sai, SameSite=None thiếu Secure, third-party blocking. |
| Cookie sending | Request có **Cookie** không? | Path, host/domain, Secure, SameSite, fetch credentials. |
| Session lookup | getSession(false) có null? | Expired, logout, pod khác, Redis/replication, ID rotation. |
| Authentication | Có session nhưng vẫn 401/302 login? | SecurityContextRepository, SecurityFilterChain, role, fixation. |
| Redirect URL | Location HTTP/internal/thiếu prefix? | Forwarded headers, context path, TLS termination, ingress rewrite. |

**Cần phân biệt hai tình huống:**

1. **Browser không gửi cookie:** đừng vội kiểm Redis hoặc Spring Session, vì request chưa mang khóa để tìm session.
2. **Browser có gửi cookie:** đừng đổi SameSite/Path trước khi xem session validity, storage và Spring Security auth.

Một HTTP status **302**, **401** hay **403** tự nó không chỉ ra nguyên nhân. 302 có thể là auth entry point hoặc redirect canonical URL; 401 có thể là xác thực thiếu; 403 có thể là CSRF hoặc authorization.

## 3. HttpSession, JSESSIONID và SecurityContext không giống nhau

**HttpSession** là state do Servlet/server lưu. **JSESSIONID** là một tên cookie thường được Servlet container dùng để mang session identifier opaque. Cookie thường chỉ chứa khóa để lookup, **không chứa mật khẩu**, và bản thân cookie còn tồn tại không bảo đảm server-side session vẫn tồn tại.

**Spring Security Authentication/SecurityContext** là trạng thái xác thực. Trong một app stateful, chúng có thể được lưu trong HttpSession qua **SecurityContextRepository**. Nhưng không phải mọi HttpSession đều có authenticated user; một client có session dùng cho shopping cart vẫn có thể anonymous.

**JWT/Bearer** hoặc một API **SessionCreationPolicy.STATELESS** có thể không dùng HttpSession để xác thực. Vì vậy cần xác nhận auth architecture trước khi điều tra JSESSIONID.

Servlet APIs:

~~~java
// Snippet minh hoa voi request kieu HttpServletRequest.
HttpSession current = request.getSession(false);
~~~

**getSession(false)** không tự tạo session mới; trả null nếu không có session hợp lệ. Ngược lại:

~~~java
HttpSession existingOrCreated = request.getSession(true);
~~~

có thể tạo session mới và phát cookie mới. **Dùng getSession(false) cho endpoint chẩn đoán**, vì việc vô tình tạo session khi kiểm có thể làm mất dấu lỗi gốc.

**Không log HttpSession.getId(), raw JSESSIONID hoặc request.getHeader("Cookie")**, dù ở DEBUG. Session ID là bearer-like credential: người khác có được nó có thể có cơ hội chiếm phiên nếu hệ thống không có biện pháp chống replay.

### Session fixation và SessionFixation

**SessionFixation** là nhóm tấn công cố định một session ID rồi dụ nạn nhân đăng nhập với ID đó. Spring Security thường bảo vệ bằng đổi session ID khi authentication thành công, ví dụ **changeSessionId()** trên Servlet hiện đại. Do đó **JSESSIONID thay đổi sau login có thể là đúng**, không phải một bug. Phải kiểm browser đã lưu ID mới chưa và request tiếp theo có gửi phiên mới.

Logout có thể invalidate session server-side, nhưng browser vẫn giữ cookie cũ một thời gian. Một stale JSESSIONID vẫn được gửi và bị server coi invalid. Nếu cần xóa cookie, expire nó với **Path và Domain chính xác**, hoặc dùng logout handler phù hợp; không giả định invalidate() tự xóa mọi cookie ở browser.

## 4. Set-Cookie là response; Cookie là request

Một response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=REDACTED; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Request tiếp theo:

~~~http
GET /portal/profile HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=REDACTED
~~~

**REDACTED** chỉ là giá trị minh họa. Khi browser gửi Cookie request, nó không gửi lại Path/SameSite/Secure/HttpOnly như thuộc tính; browser đã áp các quy tắc ấy trước khi chọn cookie.

Đừng đánh đồng:
- Server có gửi Set-Cookie.
- Browser đã **chấp nhận/lưu** cookie.
- Browser đã **gửi** cookie ở request tiếp.
- Backend đã **tìm đúng** server-side session.
- Spring Security đã phục hồi Authentication.

Đây là năm sự kiện độc lập cần chứng cứ riêng.

**HTTP redirect cũng có thể chứa Set-Cookie.** Với login form hoặc OAuth2 callback, phải xem từng response **302/303**, không chỉ response cuối cùng của redirect chain.

**HttpOnly:** document.cookie có thể không hiện JSESSIONID vì HttpOnly. Đó là cơ chế bảo vệ đúng; nó không chặn browser gửi cookie qua HTTP. **Set-Cookie** cũng là forbidden response header đối với browser Fetch APIs; **response.headers.get("set-cookie")** không phải cách tin cậy để kiểm nó. Dùng DevTools Network/Storage và subsequent requests.

## 5. Bảng cookie attributes và nguyên nhân thường gặp

| Thuộc tính | Kiểm soát | Triệu chứng khi sai |
| --- | --- | --- |
| **Name** | JSESSIONID hoặc tên custom | Client giữ tên cũ; nhiều cookies cùng tên. |
| **Domain** | Hostname nào nhận cookie | Cookie set ở internal host hoặc domain không match public. |
| **Path** | Public request path nào được gửi cookie | Public /portal nhưng cookie Path=/internal. |
| **Secure** | Chỉ gửi trên HTTPS, có ngoại lệ localhost theo browser | Redirect về HTTP khiến Secure cookie không đi. |
| **HttpOnly** | Chặn JavaScript đọc cookie | JS không thấy cookie dù browser vẫn gửi đúng. |
| **SameSite=Strict** | Hạn chế cross-site context mạnh | Callback/navigation từ external site có thể thiếu cookie. |
| **SameSite=Lax** | Cho phép same-site và một số top-level safe navigations | Cross-site fetch, iframe hoặc POST callback có thể bị chặn. |
| **SameSite=None** | Cho phép cross-site theo browser policy | Bắt buộc Secure; third-party policy vẫn có thể chặn. |
| **Max-Age/Expires** | Cookie persistence ở client | Cookie hết hạn trước server session hoặc tồn tại sau session. |
| **Partitioned** | Cookie partitioning theo browser support | Hành vi third-party contexts không giống unpartitioned cookie. |

**Cookie Path không phải ranh giới phân quyền mạnh**, và **Domain không bao gồm port**. SameSite là khái niệm **site** chứ không phải hoàn toàn tương đương **origin**; origin gồm scheme, host và port. Hai subdomains cùng registrable domain có thể same-site nhưng cross-origin.

### Domain: host-only thường đơn giản và an toàn hơn

Nếu app public ở **app.example.test** và không set Domain, cookie host-only thuộc app.example.test. Không đặt **Domain=internal-service** chỉ vì ứng dụng chạy sau proxy; browser không thấy hostname nội bộ ấy.

~~~http
Set-Cookie: JSESSIONID=REDACTED; Domain=example.test; Path=/; Secure
~~~

có thể áp dụng cho các subdomains phù hợp, tăng scope; chỉ dùng khi nghiệp vụ thực sự cần. Nếu app đổi hostname sau nâng cấp, cookie host-only ở hostname cũ không tự đi qua host mới.

**Không dùng Domain=app.example.test:8080** vì cookie domain không mang port. Đối với localhost và IP, để host-only mặc định cho lab thường ít gây nhầm hơn đặt Domain thủ công.

### Path: phải tính theo URL mà browser nhìn thấy

Ví dụ:

~~~text
Browser: https://app.example.test/portal/dashboard
Proxy:   strip /portal
Backend: http://service:8080/dashboard
~~~

Nếu backend phát **Path=/internal**, browser không gửi cookie cho **/portal/dashboard**. Có thể đặt:

~~~properties
server.servlet.session.cookie.path=/portal
~~~

nếu cookie chỉ nên theo public /portal, hoặc **Path=/** nếu chính sách của toàn host cần. **Đừng đặt Path theo upstream route /dashboard** khi browser truy cập /portal/dashboard.

Khi đổi Path, browser có thể còn cookie JSESSIONID cũ ở Path=/ hoặc /internal; nếu chúng trùng tên thì phải xử lý migration/cookie cleanup đúng Domain và Path, không xóa bừa toàn bộ cookies.

### Secure: đừng tắt để né lỗi HTTPS

Production public:

~~~text
Browser --HTTPS--> Ingress --HTTP--> Spring Boot
~~~

vẫn dùng được **Secure** cookie: browser chỉ thấy HTTPS public. Nếu backend lầm tưởng external request là HTTP và redirect browser sang http://, cookie Secure sẽ không đi. **Sửa forwarded scheme và public redirect**, không hạ Secure về false trên production.

**localhost exception:** browser có thể xử lý Secure khác trên localhost; curl và Java HttpClient không mô phỏng mọi ngoại lệ browser. Đừng coi localhost là bằng chứng cho môi trường HTTPS thực.

## 6. SameSite, fetch credentials và CORS là ba cơ chế khác nhau

Trong browser:

~~~javascript
const result = await fetch(
  "https://api.example.test/portal/api/me",
  { credentials: "include" }
);
console.log(result.status);
~~~

**Fetch credentials:**

- **omit**: không gửi credentials, không nhận/ghi Set-Cookie theo Fetch credential behavior.
- **same-origin**: mặc định; chỉ gửi credentials khi cùng origin.
- **include**: cho phép cross-origin credentials, nhưng **không vượt qua** Domain/Path/Secure/SameSite và browser privacy rules.

Nếu frontend là **https://app.example.test** còn API là **https://api.example.test**, hai origin khác nhau dù có thể same-site. Fetch mặc định same-origin vẫn có thể không gửi cookie đến API; phải dùng credentials include **nếu API contract cho phép**.

Server phải trả cho credentialed cross-origin fetch:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Access-Control-Allow-Origin: *** không được dùng cùng credentialed CORS. Server phải allowlist Origin, không phản chiếu Origin tùy ý. Preflight OPTIONS thường không mang credentials; phải kiểm cả preflight và actual response.

**SameSite=None; Secure** thường cần nếu app chủ đích gửi cookie trong cross-site requests, nhưng điều đó không bảo đảm third-party cookies được phép. Browser có thể chặn theo privacy policy, storage partitioning hoặc thiết lập người dùng. Luôn xem **Blocked Reason** trong DevTools.

**Đừng dùng SameSite=None thay cho CSRF defenses.** Cross-site cookie transport có thể mở thêm các đường CSRF; với cookie-based login cần bảo vệ CSRF hoặc thiết kế API phù hợp. Nếu cross-origin POST báo lỗi CORS, request có thể đã tới server; không retry một POST thanh toán chỉ vì JavaScript bị chặn đọc response.

### OAuth2/OIDC callback

Authorization-code flow có thể redirect top-level GET từ identity provider về app; SameSite=Lax thường hỗ trợ một số loại navigation này. Nhưng iframe hoặc **form_post** callback có rules khác. Ngoài JSESSIONID, kiểm state/correlation cookies, redirect URI, session và browser blocked reason. Không đổi tất cả cookies thành SameSite=None chỉ để làm một luồng đăng nhập xanh.

## 7. Khi Cookie đã tới server nhưng HttpSession vẫn mất

Nếu request có **Cookie: JSESSIONID=...** mà **request.getSession(false)==null**, xem:

- Server-side **idle timeout**; cookie có thể còn trong browser lâu hơn.
- Logout hoặc ứng dụng gọi **session.invalidate()**.
- Browser gửi cookie ID cũ trước khi ID rotation/login hoàn tất.
- Tên cookie hoặc session namespace đổi.
- Pod được scale down/restart làm mất in-memory sessions.
- Load balancer gửi request kế đến **pod B** nhưng session chỉ có ở RAM **pod A**.
- Shared session store (Redis/JDBC) bị outage, TTL hết hoặc không deserialize được.
- Server mới không tương thích session attributes của version trước trong rolling upgrade.
- Một container/app khác trên cùng domain/path đã ghi JSESSIONID trùng tên.
- Sticky-session configuration bị tắt khi thay Ingress Controller.

**server.servlet.session.timeout=30m** là server-side idle timeout, không giống cookie Max-Age. Session cookie không có Max-Age có thể còn trong browser, trong khi server đã expire state.

Trong Servlet, **request.isRequestedSessionIdValid()** giúp biết session ID trong request có hợp lệ không; không trả giá trị ID cho client. False có thể nghĩa là không gửi ID hoặc ID không được tìm thấy, nên cần kết hợp với evidence từ browser Network mà không log raw credentials.

**Đừng gọi getSession(true) trong endpoint chẩn đoán**, vì nó có thể lập tức tạo phiên mới, che mất chứng cứ phiên cũ không hợp lệ.

## 8. Mất session do nhiều replicas và Spring Session Redis

Mô hình lỗi:

~~~text
POST /login -> Ingress -> Pod A
  Pod A lưu HttpSession trong RAM.

GET /profile (cùng JSESSIONID) -> Ingress -> Pod B
  Pod B không có HttpSession đó.
  -> 302 /login hoặc 401.
~~~

**Sticky sessions** có thể giúp các requests của một client tới cùng pod, nhưng không phải giải pháp durable khi pod restart, HPA scale down hoặc failover.

**Spring Session** thay implementation HttpSession bằng repository chung. Với Redis, nhiều pods có thể tìm cùng session. Dependency Boot tương ứng:

~~~xml
<!-- Chi them khi deployment that su co Redis va security controls. -->
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Ví dụ hướng dẫn, **không phải một app chạy được nếu chưa có Redis server**:

~~~properties
spring.data.redis.host=redis.internal
spring.data.redis.port=6379
server.servlet.session.timeout=30m
~~~

Phải xem thêm TLS/auth, Redis network policy, compatible Spring Session versions, TTL, key namespace, serialization strategy và capacity. Không lưu mật khẩu/token plain-text trong HttpSession hoặc Redis; hạn chế session attributes lớn.

**Khi rolling upgrade**, thay đổi class names, serialVersionUID, JSON serialization hoặc session attribute structure có thể làm session cũ không đọc được. Bài toán này không sửa được bằng SameSite hoặc cookie Path. Cần migration policy, backward-compatible serialization hoặc cho phép re-login có chủ đích.

### Phân biệt session storage lỗi với authentication lỗi

Một **HttpSession** có thể tồn tại và chứa session attributes của ứng dụng nhưng Spring Security không phục hồi SecurityContext. Trong Spring Security 6, custom auth handlers có thể cần lưu context qua **SecurityContextRepository** theo behavior explicit-save. Kiểm đúng SecurityFilterChain và repository, không suy auth chỉ từ sessionPresent.

## 9. Spring Security 6 và những thay đổi lúc nâng cấp

Spring Boot 3.x dùng Servlet API namespace **jakarta.servlet.\*** thay cho **javax.servlet.\*** của các ứng dụng Boot 2.x, và Spring Security 6 thay đổi một số flow session management.

Những điều dễ bị hiểu nhầm:

1. Spring Security có thể đổi session ID sau login để chống SessionFixation. **ID đổi là expected security behavior**, không tự là mất phiên.
2. **SecurityContextHolderFilter** và **SecurityContextRepository** quản lý context giữa requests. Trong custom authentication code, chỉ set ThreadLocal context rồi bỏ qua lưu repository có thể khiến request kế không authenticated.
3. **SessionManagementFilter** không còn được dùng mặc định cho mọi authentication flow trong Spring Security 6; authentication mechanism thực hiện chiến lược phù hợp.
4. **SessionCreationPolicy.STATELESS** có thể khiến app không tạo session cho auth, dù ứng dụng có Servlet.
5. InvalidSessionStrategy hoặc invalidSessionUrl có thể redirect người dùng với stale cookie sau logout.
6. 403 sau POST có thể là CSRF, không phải cookie không được gửi; phải kiểm CSRF token và session/context.
7. Một cấu hình SecurityFilterChain mới có thể thay login URL, request matcher và logout behavior, gây 302/401 khác trước upgrade.

Minh họa **pseudocode không độc lập** cho custom auth handler:

~~~java
// Authentication auth = authenticationManager.authenticate(token);
// SecurityContext context = SecurityContextHolder.createEmptyContext();
// context.setAuthentication(auth);
// SecurityContextHolder.setContext(context);
// securityContextRepository.saveContext(context, request, response);
~~~

Đây không phải đoạn có thể biên dịch độc lập: cần các beans/imports và flow authentication cụ thể. Nó cho thấy **phải lưu context** khi policy của framework yêu cầu; không chỉ set ThreadLocal.

**Không tắt CSRF hoặc session fixation protection để sửa bug chưa xác minh.** Những thay đổi này làm giảm an toàn, có thể che lỗi khác. Với logout, expire session cookie với Name/Path/Domain đúng hoặc dùng cơ chế xóa do Spring Security hỗ trợ và test trên đúng Servlet container.

## 10. Reverse proxy tạo redirect sai scheme

Giả sử:

~~~text
Browser: https://app.example.test/portal/login
Ingress: HTTPS -> HTTP backend
Backend: http://session-service:8080/login
~~~

Nếu backend chỉ thấy HTTP và tự sinh link, response có thể là:

~~~http
HTTP/1.1 302 Found
Location: http://session-service:8080/login
~~~

Khi browser theo redirect, nó rời HTTPS, cookie Secure có thể không đi, host/path không match và có thể xuất hiện vòng lặp login.

Spring Boot 3.3 cho phép:

~~~properties
server.forward-headers-strategy=framework
~~~

Trusted reverse proxy truyền một bộ metadata nhất quán:

~~~http
Forwarded: proto=https;host=app.example.test
X-Forwarded-Host: app.example.test
X-Forwarded-Proto: https
X-Forwarded-Port: 443
X-Forwarded-Prefix: /portal
~~~

**Forwarded** là header chuẩn RFC 7239; X-Forwarded-* là de facto headers. Đừng để Forwarded và X-Forwarded-Host/Proto mâu thuẫn; proxy phải xác định policy viết/ghi đè.

| Strategy | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| **none** | Không xử lý forwarded metadata qua Boot strategy | Không có trusted proxy hoặc dùng canonical public URL riêng. |
| **native** | Dùng Tomcat/Jetty/Netty native forwarding support | Thường đủ cho X-Forwarded-For/Proto khi proxy phù hợp. |
| **framework** | Spring MVC ForwardedHeaderFilter; WebFlux ForwardedHeaderTransformer | Hữu ích khi cần X-Forwarded-Prefix và URI/redirect generation. |

Với **embedded Tomcat** sau TLS termination, Spring Boot docs còn nhắc:

~~~properties
server.tomcat.redirect-context-root=false
~~~

để X-Forwarded-Proto được xử lý trước redirect tại context root. Nó **không tự tạo HTTPS certificate** hoặc sửa URL rewrite ở ingress.

### Vòng lặp HTTP → HTTPS → HTTP

~~~text
1. Browser GET https://app.example.test/portal
2. Proxy gửi HTTP tới backend
3. Backend nghĩ client dùng HTTP, redirect http://app.example.test/portal
4. Proxy lại bắt buộc HTTPS
5. Browser vào HTTPS, tiếp tục lặp
~~~

Bắt redirect chain theo từng hop bằng DevTools Preserve log hoặc **curl -i** không tự follow. Đừng tắt HTTPS enforcement để dập loop; sửa **Forwarded Proto và redirect URL**.

### Trust boundary không được bỏ qua

Một attacker có thể tự gửi **X-Forwarded-Host: attacker.example**. Nếu backend tin nó và tạo Location/OAuth callback theo header ấy, có thể dẫn đến host-header poisoning hoặc open redirect. **ForwardedHeaderFilter không xác thực nguồn gốc header**.

Proxy ở ranh giới Internet phải **xóa/ghi đè Forwarded và X-Forwarded-*** từ client không tin cậy, rồi tự tạo giá trị theo virtual host/TLS/route đã allowlist. Backend phải bị cô lập khỏi direct public traffic bằng network policies/security groups/mTLS hoặc tương đương.

## 11. Context path, public Path và Nginx rewrite

Hai topology hay gặp:

| Topology | Public request | Backend request | server.servlet.context-path | Cookie Path phù hợp |
| --- | --- | --- | --- | --- |
| **Preserve /portal** | /portal/demo/session/status | /portal/demo/session/status | /portal | /portal hoặc / theo policy |
| **Strip /portal** | /portal/demo/session/status | /demo/session/status | root | /portal hoặc / theo policy |

Trong strip mode, header **X-Forwarded-Prefix: /portal** phục vụ generated public URLs, **không tự thêm Servlet context path**. Nếu đã strip /portal rồi còn đặt server.servlet.context-path=/portal, backend nhận /demo/... mà đòi /portal/demo/... và có thể trả 404.

Nginx lab minh họa strip prefix:

~~~nginx
server {
    listen 8088;
    server_name localhost;
    location /portal/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Prefix /portal;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
~~~

Với **location /portal/** và **proxy_pass http://127.0.0.1:8080/** có slash cuối, Nginx thay prefix bằng /, nên upstream nhận /demo/session/status. Nếu proxy_pass không có URI trailing slash ở dạng config tương ứng, path thường được preserve. Khi dùng regex locations/variables/rewrite, phải kiểm Nginx semantics riêng.

**Snippet này chỉ cho lab HTTP local**, không có TLS, host allowlist và reverse-proxy security production. Ở public HTTPS thực, forwarded proto phải là original HTTPS chứ không phải HTTP nội bộ.

Nếu không sửa được backend Set-Cookie Path, Nginx có **proxy_cookie_path** để rewrite Path, nhưng ưu tiên cấu hình tại app và test actual Set-Cookie. Không áp hai cơ chế rewrites chồng chéo; trong migration, browser có thể tồn tại cookie cùng tên ở path cũ và mới.

Kubernetes Ingress **pathType: Prefix** quyết định routing, không có nghĩa tự strip prefix. ingress-nginx **rewrite-target** là controller-specific, không portable sang mọi IngressClass/Gateway API implementation.

## 12. Cấu hình Spring Boot 3.3 theo môi trường

### Local lab — HTTP localhost, chưa có proxy

~~~properties
# application.properties
spring.application.name=session-diagnostics
server.port=8080

server.servlet.session.timeout=30m
server.servlet.session.tracking-modes=cookie
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.secure=false

server.forward-headers-strategy=none
server.error.include-message=never
server.error.include-stacktrace=never
~~~

**secure=false chỉ dành cho lab HTTP local**. Trên production HTTPS, giữ Secure=true. Dùng **server.servlet.session.tracking-modes=cookie** để tránh dựa vào URL rewriting như một cơ chế truyền session ID; không để lộ ;jsessionid trong links/logs.

### Production ví dụ — HTTPS ở edge, proxy strip /portal

~~~properties
# application-prod.properties
server.servlet.session.timeout=30m
server.servlet.session.tracking-modes=cookie
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/portal

# Backend root context vi proxy strip /portal.
server.forward-headers-strategy=framework
server.tomcat.redirect-context-root=false

server.error.include-message=never
server.error.include-stacktrace=never
~~~

**Không copy profile prod vào một dịch vụ chưa có TLS/ingress/authentication**. Đây chỉ là ví dụ cookie/forwarded config, không phải sản phẩm bảo mật hoàn chỉnh. SameSite phải theo frontend/OAuth flow, Path phải theo public URL, strategy chỉ bật khi proxy đã sanitize headers.

**Đừng dùng cookie Max-Age như biện pháp duy nhất giữ login.** Cookie còn trong browser nhưng HttpSession server đã hết timeout thì auth vẫn có thể mất.

## 13. Demo runnable Java 17+: HttpSession và redirect

Mục tiêu: chứng minh một client dùng cookie jar giữ được state, client không dùng cookie jar không giữ state; session invalidate làm state biến mất; redirect sinh public URL khi có trusted forwarded metadata.

Cấu trúc:

~~~text
session-diagnostics/
  pom.xml
  src/main/java/com/example/sessiondiag/
    SessionDiagnosticsApplication.java
    SessionState.java
    SessionController.java
    LocalRequestViewController.java
  src/main/resources/
    application.properties
    application-prod.properties
  src/test/java/com/example/sessiondiag/
    SessionHttpTests.java
    SessionMvcTests.java
~~~

Demo **không có Spring Security**, password, database hoặc Redis. Không dùng nó để thay login production. Spring Boot version minh họa **3.3.13**, Java 17+. Với dự án mới nên dùng nhánh Boot hiện còn được hỗ trợ và chạy lại contract tests khi nâng cấp.

### 13.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>session-diagnostics</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
      <artifactId>spring-boot-starter-test</artifactId>
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

### 13.2. Main class

File **src/main/java/com/example/sessiondiag/SessionDiagnosticsApplication.java**:

~~~java
package com.example.sessiondiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDiagnosticsApplication.class, args);
    }
}
~~~

### 13.3. DTO

File **src/main/java/com/example/sessiondiag/SessionState.java**:

~~~java
package com.example.sessiondiag;

public record SessionState(boolean present, int visits) {
}
~~~

Không đưa session ID vào response body. present chỉ nói **có HttpSession**, không chứng minh user đã được authenticated.

### 13.4. SessionController.java

~~~java
package com.example.sessiondiag;

import java.net.URI;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/demo")
public class SessionController {

    private static final String VISITS = "visits";

    @PostMapping(value = "/session/start",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public SessionState start(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute(VISITS, 1);
        return new SessionState(true, 1);
    }

    @GetMapping(value = "/session/status",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public SessionState status(HttpServletRequest request) {
        return view(request.getSession(false));
    }

    @PostMapping(value = "/session/visit",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public SessionState visit(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return new SessionState(false, 0);
        }
        Object previous = session.getAttribute(VISITS);
        int next = previous instanceof Integer n ? n + 1 : 1;
        session.setAttribute(VISITS, next);
        return new SessionState(true, next);
    }

    @PostMapping("/session/clear")
    public ResponseEntity<Void> clear(
            HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/redirect")
    public ResponseEntity<Void> redirect() {
        URI target = ServletUriComponentsBuilder
                .fromCurrentContextPath()
                .path("/demo/session/status")
                .build()
                .toUri();

        return ResponseEntity.status(HttpStatus.FOUND)
                .location(target)
                .build();
    }

    private SessionState view(HttpSession session) {
        if (session == null) {
            return new SessionState(false, 0);
        }
        Object stored = session.getAttribute(VISITS);
        int count = stored instanceof Integer n ? n : 0;
        return new SessionState(true, count);
    }
}
~~~

Giải thích:

- **POST /demo/session/start** chủ động tạo phiên, thường khiến container phát Set-Cookie JSESSIONID.
- **GET /demo/session/status** đọc bằng getSession(false), không tạo mới.
- **POST /demo/session/visit** tăng state nếu tìm được session. Ứng dụng thật dùng cookie auth cần bảo vệ CSRF cho state-changing requests.
- **POST /demo/session/clear** invalidate rồi trả **204 No Content**. Cookie cũ có thể vẫn ở browser.
- **GET /demo/redirect** trả **302 Found** và Location từ URI builder; khi forwarded headers được xử lý, URL phản ánh public scheme/host/prefix.
- Data nằm trong RAM JVM, nên restart hoặc chuyển sang pod khác không có shared store sẽ làm mất session.

### 13.5. Diagnostic controller chỉ có trong local profile

File **src/main/java/com/example/sessiondiag/LocalRequestViewController.java**:

~~~java
package com.example.sessiondiag;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("local")
@RestController
public class LocalRequestViewController {

    @GetMapping("/debug/request-view")
    public Map<String, Object> view(HttpServletRequest request) {
        return Map.of(
                "scheme", request.getScheme(),
                "secure", request.isSecure(),
                "host", request.getServerName(),
                "port", request.getServerPort(),
                "contextPath", request.getContextPath(),
                "requestedSessionIdValid",
                    request.isRequestedSessionIdValid(),
                "sessionPresent",
                    request.getSession(false) != null);
    }
}
~~~

Endpoint chỉ được đăng ký với **local** profile; không log/trả session ID. Tuy vậy nó phản ánh request host và thông tin proxy, nên không được expose ra Internet. Trong production hãy dùng instrumentation đã được review, metrics và management auth thay vì một debug endpoint công khai.

Cấu hình tạo hai files **application.properties** và **application-prod.properties** như mục 12. Có thể chạy profile local mà không cần application-local.properties: @Profile("local") sẽ kích hoạt controller diagnostic, còn base properties vẫn có hiệu lực.

## 14. Chạy lab với curl cookie jar

Với Java 17+ và Maven, tại thư mục project:

~~~bash
mvn clean test
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

Trên terminal khác, chưa có cookie:

~~~bash
curl -si http://127.0.0.1:8080/demo/session/status
~~~

Body kỳ vọng:

~~~json
{"present":false,"visits":0}
~~~

### Tạo session và lưu cookie

~~~bash
curl -si -X POST \
  -c session-cookies.txt \
  http://127.0.0.1:8080/demo/session/start
~~~

Body kỳ vọng:

~~~json
{"present":true,"visits":1}
~~~

Response còn có Set-Cookie JSESSIONID. Tệp **session-cookies.txt** lưu credential dùng trong demo; không commit lên Git hoặc gửi support ticket. Không sử dụng real user session trong bài thực nghiệm.

### Không gửi jar: session không được tìm thấy

~~~bash
curl -si http://127.0.0.1:8080/demo/session/status
~~~

Kỳ vọng **present=false**, vì lệnh curl không tự chia sẻ cookie giữa lần chạy nếu không dùng jar.

### Gửi cookie jar: session được nhận ra

~~~bash
curl -si -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/status
~~~

Kỳ vọng:

~~~json
{"present":true,"visits":1}
~~~

Tăng số lượt truy cập:

~~~bash
curl -si -X POST -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/visit
~~~

Kỳ vọng:

~~~json
{"present":true,"visits":2}
~~~

### Invalidate

~~~bash
curl -si -X POST -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/clear
~~~

Kỳ vọng **204 No Content**, body rỗng. Gọi status dùng cookie cũ:

~~~bash
curl -si -b session-cookies.txt \
  http://127.0.0.1:8080/demo/session/status
~~~

Kỳ vọng **present=false** vì server-side session đã bị invalidate; cookie jar có thể còn credential cũ nhưng server không nhận ID đó.

**Đừng mặc định curl -v an toàn trên production:** verbose output có thể in Cookie/Set-Cookie values thực. Nếu cần gửi logs cho team, redact token và path/query nhạy cảm trước.

## 15. Kiểm redirect với và không có forwarded headers

Local default strategy **none**:

~~~bash
curl -si http://127.0.0.1:8080/demo/redirect
~~~

Kỳ vọng **302 Found**, Location theo direct backend origin:

~~~http
Location: http://127.0.0.1:8080/demo/session/status
~~~

Dừng instance cũ. Chạy bản local cho phép framework xử lý synthetic forwarded headers:

~~~bash
mvn spring-boot:run \
  -Dspring-boot.run.arguments="--server.forward-headers-strategy=framework"
~~~

Gửi request test:

~~~bash
curl -si \
  -H 'X-Forwarded-Host: app.example.test' \
  -H 'X-Forwarded-Proto: https' \
  -H 'X-Forwarded-Port: 443' \
  -H 'X-Forwarded-Prefix: /portal' \
  http://127.0.0.1:8080/demo/redirect
~~~

Kỳ vọng **302 Location** có scheme=https, host=app.example.test, path=/portal/demo/session/status và port -1 hoặc 443. Một response minh họa:

~~~http
HTTP/1.1 302
Location: https://app.example.test/portal/demo/session/status
~~~

**Đây là test synthetic trong local lab**, không chứng minh ingress thực đã sanitize forwarded headers. Không dùng **curl -L** khi cần thấy response redirect đầu tiên, vì -L sẽ tự follow và có thể che Location sai.

Nếu public proxy strip **/portal** rồi backend root, X-Forwarded-Prefix giúp tạo external link đúng; **không đặt server.servlet.context-path=/portal** vì upstream đã không còn tiền tố này.

## 16. Integration test qua embedded HTTP server thật

Test này dùng **@SpringBootTest(RANDOM_PORT)**, Java 17 **HttpClient** và **CookieManager**. Nó kiểm vòng đời session ở HTTP connector, không giả làm Chrome/Firefox về SameSite/third-party cookie/CORS.

File **src/test/java/com/example/sessiondiag/SessionHttpTests.java**:

~~~java
package com.example.sessiondiag;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.forward-headers-strategy=framework",
        "server.servlet.session.cookie.secure=false",
        "server.servlet.session.cookie.path=/"
    })
class SessionHttpTests {

    @LocalServerPort
    int port;

    private final ObjectMapper mapper = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpRequest get(String path) {
        return HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(5))
                .GET().build();
    }

    private HttpRequest post(String path) {
        return HttpRequest.newBuilder(uri(path))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();
    }

    @Test
    void cookieStoreKeepsHttpSessionAcrossRequests()
            throws Exception {

        CookieManager cookies = new CookieManager();
        cookies.setCookiePolicy(CookiePolicy.ACCEPT_ALL);

        HttpClient withCookies = HttpClient.newBuilder()
                .cookieHandler(cookies).build();
        HttpClient withoutCookies = HttpClient.newHttpClient();

        HttpResponse<String> created = withCookies.send(
                post("/demo/session/start"),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, created.statusCode());
        assertTrue(created.headers()
                .firstValue("set-cookie").isPresent());
        assertTrue(mapper.readTree(created.body())
                .path("present").asBoolean());

        HttpResponse<String> absent = withoutCookies.send(
                get("/demo/session/status"),
                HttpResponse.BodyHandlers.ofString());
        assertFalse(mapper.readTree(absent.body())
                .path("present").asBoolean());

        HttpResponse<String> existing = withCookies.send(
                get("/demo/session/status"),
                HttpResponse.BodyHandlers.ofString());
        assertTrue(mapper.readTree(existing.body())
                .path("present").asBoolean());

        HttpResponse<String> visit = withCookies.send(
                post("/demo/session/visit"),
                HttpResponse.BodyHandlers.ofString());
        JsonNode visited = mapper.readTree(visit.body());
        assertEquals(2, visited.path("visits").asInt());

        HttpResponse<String> cleared = withCookies.send(
                post("/demo/session/clear"),
                HttpResponse.BodyHandlers.ofString());
        assertEquals(204, cleared.statusCode());

        HttpResponse<String> after = withCookies.send(
                get("/demo/session/status"),
                HttpResponse.BodyHandlers.ofString());
        assertFalse(mapper.readTree(after.body())
                .path("present").asBoolean());
    }

    @Test
    void forwardedHttpsAndPrefixAffectRedirectLocation()
            throws Exception {

        HttpClient noRedirect = HttpClient.newBuilder()
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                uri("/demo/redirect"))
                .timeout(Duration.ofSeconds(5))
                .header("X-Forwarded-Host", "app.example.test")
                .header("X-Forwarded-Proto", "https")
                .header("X-Forwarded-Port", "443")
                .header("X-Forwarded-Prefix", "/portal")
                .GET().build();

        HttpResponse<String> response = noRedirect.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(302, response.statusCode());
        URI location = URI.create(response.headers()
                .firstValue("Location").orElseThrow());

        assertEquals("https", location.getScheme());
        assertEquals("app.example.test", location.getHost());
        assertEquals("/portal/demo/session/status",
                location.getPath());
        assertTrue(location.getPort() == -1 ||
                location.getPort() == 443);
    }
}
~~~

**Điều test được:** cùng cookie jar có session, không cookie jar thì không; invalidate làm session không còn; 302 Location dùng forwarded origin/prefix trong test context framework.

**Điều test chưa được:** SameSite, browser cookie policy, CORS preflight, third-party blocking, real ingress path rewrite hoặc TLS certificate. Java HttpClient không có tất cả browser restrictions. Những thứ này phải test bằng DevTools và end-to-end public URL.

## 17. MockMvc test controller với mock HttpSession

File **src/test/java/com/example/sessiondiag/SessionMvcTests.java**:

~~~java
package com.example.sessiondiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SessionController.class)
class SessionMvcTests {

    @Autowired
    MockMvc mvc;

    @Test
    void missingSessionDoesNotCreateOneOnStatus()
            throws Exception {
        mvc.perform(get("/demo/session/status")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.present").value(false))
                .andExpect(jsonPath("$.visits").value(0));
    }

    @Test
    void readsExistingMockSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("visits", 7);

        mvc.perform(get("/demo/session/status")
                    .session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.present").value(true))
                .andExpect(jsonPath("$.visits").value(7));
    }

    @Test
    void clearReturns204() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("visits", 1);

        mvc.perform(post("/demo/session/clear")
                    .session(session))
                .andExpect(status().isNoContent());
    }
}
~~~

MockMvc không mở socket nên không kiểm browser cookie handling. Một app thực có Spring Security sẽ cần **spring-security-test**, principal/CSRF phù hợp trong các POST tests. Demo không thêm Security để cô lập vấn đề HttpSession.

Chạy từ thư mục project:

~~~bash
mvn clean test
~~~

Chỉ kết luận tests pass nếu Maven thật trả exit code 0 và các test classes đã thực thi. Code trong bài là tài liệu mẫu, không phải xác nhận đã build trên hệ thống của người đọc.

## 18. DevTools: đọc chứng cứ thay vì đoán

Từng bước trên Chrome/Edge/Firefox (tên menu có thể khác theo phiên bản):

1. Mở **Network** trước login, bật **Preserve log** để giữ 302 chain.
2. Chọn response login, xem **Set-Cookie**. Nếu có cookie values, đừng copy/screenshare chưa redact.
3. Xem browser **Application/Storage → Cookies**: Name, Domain, Path, Secure, HttpOnly, SameSite, Expires/Max-Age.
4. Xem browser **Issues/Blocked Reason** nếu cookie bị từ chối; ghi lý do, không chỉ ghi "cookie missing".
5. Chọn request ngay sau login, xem **Request Headers → Cookie**. Có gửi đúng tên cookie không?
6. Nếu có Cookie mà server không có session, xem **isRequestedSessionIdValid()** như boolean, session store TTL và pod routing.
7. Nếu session valid nhưng bị 401/302 login, điều tra **SecurityContextRepository**/authentication state.
8. Kiểm từng **Location** trong redirect chain: HTTPS có bị thành HTTP, host có thành internal, prefix /portal có mất không?
9. Nếu fetch cross-origin báo CORS, kiểm **credentials** trên request, ACAO/ACAC trên response và preflight; không suy cookie không gửi khi chỉ thấy JS error.
10. Dùng test account và traffic synthetic. Không gửi actual JSESSIONID, OAuth tokens, passwords hoặc session dumps cho issue tracker.

**Không dùng document.cookie để kết luận HttpOnly cookie vắng mặt.** JS không được đọc nó theo thiết kế.

**Không dùng response.headers.get("set-cookie")** để kết luận server không set cookie; Fetch browser che header này với JS.

## 19. Chẩn đoán phiên bị mất do rolling upgrade

Một kế hoạch migration cần kiểm:

| Thay đổi | Rủi ro |
| --- | --- |
| Boot 2.x → Boot 3.x | Namespace **javax.servlet → jakarta.servlet**, custom filters/listeners và dependencies phải đổi. |
| Security 5 → 6 | Context persistence/explicit-save, default filter behaviors, session management khác. |
| Đổi login hostname | Host-only cookie cũ không gửi tới hostname mới. |
| Đổi public prefix | Cookie Path cũ không match path mới. |
| Thêm HTTPS termination | Forwarded Proto/Host sai, redirect và Secure cookie bất nhất. |
| Ingress Nginx → gateway khác | Header sanitization, rewrite và proxy-cookie policies khác. |
| Một pod → nhiều pods | In-memory session không chia sẻ; cần routing/store strategy. |
| Thêm Spring Session Redis | TTL/serializer/namespace của session không tự giống container store. |
| Nâng Jackson/serialization | Old session attributes có thể không deserialize. |
| Đổi SameSite/browser | Cross-site callback/login và fetch behavior khác. |
| Thay cookie name | Client giữ JSESSIONID cũ, app mong một tên mới. |
| Đổi Servlet container | Set-Cookie defaults, session tracking, redirect behavior khác. |

Trước rollout, chạy compatibility tests qua public route; xác định có cần reauthentication người dùng theo kế hoạch. Không giả định existing in-memory sessions có thể chuyển sang Redis tự động.

Một rolling upgrade có hai app versions cùng đọc Redis có thể thất bại vì session attribute serialization không tương thích. Cần versioned schema hoặc deployment strategy để tránh mất phiên ngoài ý muốn.

## 20. Bảng phân loại lỗi nhanh

| Triệu chứng | Đừng nhầm với | Hướng xử lý |
| --- | --- | --- |
| Set-Cookie không có | Browser không gửi cookie | Kiểm app có tạo session, auth/save context, proxy không xóa header. |
| Set-Cookie có nhưng bị browser block | Session store lỗi | Đọc blocked reason, Domain/Secure/SameSite/third-party rules. |
| Cookie không đi ở /portal | Redis timeout | Xem public cookie Path và Domain. |
| Cookie Secure không đi sau redirect HTTP | Session fixation | Sửa X-Forwarded-Proto và HTTPS Location. |
| JS không thấy document.cookie | Cookie chưa được lưu | Có thể vì HttpOnly; kiểm Network/Storage. |
| JS không đọc được Set-Cookie | Server không set cookie | Header bị browser Fetch che; xem DevTools. |
| credentials include vẫn không có Cookie | Fetch không bật credentials | Kiểm SameSite/Domain/Path/Secure/browser privacy. |
| CORS wildcard và credentials | Cookie sai Path | ACAO phải exact allowlist, ACAC true. |
| Cookie tới server nhưng session invalid | Browser chặn cookie | Timeout/invalidate/pod khác/Redis/namespace. |
| JSESSIONID đổi ngay sau login | Mất phiên | Có thể là SessionFixation protection bình thường. |
| HttpSession có nhưng auth 401 | Cookie không gửi | Kiểm SecurityContextRepository, token/login policy. |
| POST 403 | Luôn do mất cookie | Có thể CSRF/authorization. |
| 302 về http://internal | SameSite | Kiểm reverse proxy Forwarded/Host/Proto và URI builder. |
| 302 login lặp sau logout | User chưa được xác thực | Cookie cũ chưa expire hoặc invalid-session strategy. |
| Chỉ một pod lỗi | Browser cookie policies | Kiểm session store/cluster deployment/version drift. |
| Session mất sau restart | Cookie Domain | In-memory state không persistent. |
| Redirect loop HTTPS ↔ HTTP | Cookie không được lưu | Sửa external scheme recognition, đừng tắt HTTPS. |

## 21. Monitoring và logging an toàn

Khi cần debug production, thu **metadata tối thiểu**:

~~~json
{
  "event": "session.lookup",
  "route": "/account",
  "request_id": "safe-correlation-id",
  "cookie_header_present": true,
  "requested_session_id_valid": false,
  "session_present": false,
  "authenticated": false,
  "pod": "api-2"
}
~~~

Đây là schema minh họa, không phải log Spring Boot tự phát. Các booleans giúp phân biệt cookie transport/session/auth mà không lộ token. Một request ID/trace ID nên được tạo riêng, **không bao giờ lấy nguyên session ID**.

Không log:
- JSESSIONID/SESSION/remember-me cookie values.
- Full Set-Cookie/Cookie/Authorization headers.
- OAuth authorization code/state, refresh tokens.
- Login body chứa username/password/OTP.
- Raw path/query có token hoặc personal data.
- Redis keys chứa session IDs nguyên văn.
- SecurityContext/principal objects được stringify.

Giữ **spring.mvc.log-request-details=false** ở production; tránh bật root TRACE, wire logging hoặc Tomcat access log có Cookie header. Nếu cần DEBUG hẹp, review nội dung, đặt owner/TTL, rollback, monitoring log volume và access controls.

Một số metrics hữu ích: count session created/expired (không label bằng session ID), auth failure codes, 302 login redirects, 401/403, session store errors, per-pod load, wrong-scheme redirects, 5xx và Redis latency. Khi dùng metrics tags, đừng thêm raw userId, cookie values hoặc request ID vào label.

## 22. Runbook xử lý incident

1. Ghi rõ frontend origin, public API URL, ingress/controller, backend URL, Spring Boot/Security versions và authentication mode.
2. Chọn một test account và một chuỗi login → request tiếp → logout trong DevTools Preserve log.
3. Xác định Set-Cookie được tạo, browser lưu hay block, request sau có gửi Cookie hay không.
4. Đối chiếu Domain/Path/Secure/HttpOnly/SameSite/Expires với **public URL**, không phải upstream URI.
5. Nếu không có Cookie, kiểm fetch credentials, CORS và cross-site browser policy.
6. Nếu có Cookie, kiểm session validity (không đọc ID thực), timeout/invalidate, session store và load balancing pod routing.
7. Nếu session tồn tại nhưng không authenticated, kiểm custom Spring Security persistence, SessionFixation, SecurityFilterChain và logout/invalid-session policy.
8. Kiểm redirect chain: Location scheme/host/port/prefix, TLS termination và forwarded headers.
9. Nếu URL sai, sửa strategy/proxy/header sanitation/context mapping thay vì tắt Secure.
10. Test cùng một luồng bằng **curl -c/-b** trên đúng public origin và **Java RANDOM_PORT** cho backend, rồi browser test cho SameSite/CORS.
11. Với nhiều replicas, kiểm sticky/session repository và timeout/TTL/serialization compatibility.
12. Có rollback cho ingress, cookie attributes hoặc login flow config khi canary tests lỗi.
13. Sau incident, thêm regression tests và sanitized telemetry để không cần log session IDs trong lần sau.

**Không làm:** hạ Secure trên HTTPS production, bật SameSite=None bất chấp CSRF, tắt CSRF hoặc expose /actuator/loggers chỉ để “hết lỗi”; các thay đổi này có thể mở lỗ hổng mà không giải quyết đúng tầng.

## 23. Checklist trước release và sau nâng cấp

- [ ] Biết auth mode: stateful HttpSession, Spring Session, JWT hay combination.
- [ ] Cookie Name, Domain, Path, Secure, HttpOnly, SameSite được quyết định theo public browser URL.
- [ ] Session timeout ở server/repository phù hợp với cookie persistence policy.
- [ ] HTTPS public không redirect về HTTP/internal host.
- [ ] Forwarded/X-Forwarded-* headers do trusted proxy tạo, backend không nhận untrusted direct traffic.
- [ ] Context path, Ingress strip/preserve và cookie Path nhất quán.
- [ ] Không dùng session ID trong URL/query/logs; session tracking uses cookie.
- [ ] Fetch cross-origin dùng credentials và exact-origin CORS khi thật sự cần.
- [ ] CSRF protection, SameSite và OAuth state/correlation được test.
- [ ] DevTools thử login, refresh, cross-site callback và logout.
- [ ] Spring Security context persistence, SessionFixation và invalid-session behavior được test.
- [ ] Trước/sau login session ID rotation được xử lý bình thường, không coi tự động là bug.
- [ ] Logout invalidate session và expire cookie đúng Name/Path/Domain khi cần.
- [ ] Multi-pod setup có shared session repository hoặc sticky strategy với giới hạn rõ.
- [ ] Redis TTL/serializer/namespace và upgrade compatibility được đánh giá.
- [ ] Redirects 302/303, Set-Cookie, Cookie request được kiểm qua **public ingress**.
- [ ] Có real HTTP RANDOM_PORT tests và browser policy tests; không chỉ MockMvc.
- [ ] Không log credentials, cookies, OAuth values hoặc raw SecurityContext.
- [ ] Có canary rollout/rollback và sanitized session metrics theo pod/version.
- [ ] Tài liệu/version-specific config được review khi nâng Spring Boot/Servlet/Ingress controller.

## 24. Câu hỏi tự kiểm tra

**1. Response có Set-Cookie thì request tiếp chắc chắn gửi Cookie không?**  
Không. Browser có thể block lưu hoặc không gửi vì Domain/Path/Secure/SameSite/credentials.

**2. Vì sao document.cookie không hiện JSESSIONID?**  
Có thể vì HttpOnly; browser vẫn gửi khi policies cho phép.

**3. getSession(false) có ưu điểm gì khi debug?**  
Không tạo session mới, giữ được chứng cứ nếu phiên cũ không hợp lệ.

**4. Vì sao Cookie đúng nhưng session vẫn mất ở Kubernetes?**  
Session ở RAM của pod khác, timeout/invalidate hoặc shared store lỗi.

**5. JSESSIONID đổi sau login có nhất thiết bất thường không?**  
Không. Session fixation protection có thể rotate ID.

**6. HttpSession còn tồn tại có bảo đảm đã authenticated không?**  
Không. Spring Security context có thể không được lưu hoặc khôi phục.

**7. Secure cookie có cần backend dùng HTTPS khi TLS terminate ở proxy?**  
Browser chỉ thấy public HTTPS; backend có thể HTTP trong trusted network.

**8. Vì sao redirect về HTTP khiến login thất bại?**  
Secure cookie không gửi qua HTTP và host/path có thể không match.

**9. SameSite=None có tự vượt browser third-party cookie blocking không?**  
Không. Nó còn đòi Secure và vẫn chịu browser privacy policies.

**10. app.example.test và api.example.test có thể same-site nhưng cross-origin không?**  
Có. Fetch cross-origin vẫn cần credentials/CORS nếu dùng cookie.

**11. Access-Control-Allow-Origin:* có hợp lệ với credentials không?**  
Không. Credentialed CORS cần explicit allowed origin và ACAC true.

**12. Cookie Path=/internal có đi tới public /portal không?**  
Không, vì Path matching theo URL public browser thấy.

**13. server.servlet.session.timeout=30m có tự đặt cookie Max-Age 30 phút không?**  
Không đồng nhất. Server idle timeout và client cookie lifetime khác nhau.

**14. invalidate() có tự xóa browser cookie trong mọi container không?**  
Không được bảo đảm; cần policy expire đúng cookie scope.

**15. Vì sao 403 POST không nhất thiết là session mất?**  
Có thể CSRF hoặc authorization bị từ chối.

**16. Vì sao chỉ có MockMvc chưa đủ debug cookie?**  
MockMvc không kiểm browser storage, SameSite, TLS/proxy hoặc network cookie jar.

**17. Property Boot nào giúp Spring MVC hiểu X-Forwarded-Prefix?**  
server.forward-headers-strategy=framework.

**18. ForwardedHeaderFilter có biết header nào do attacker tự gửi không?**  
Không. Proxy phải sanitize và backend phải được bảo vệ.

**19. Khi đổi from Boot 2 to Boot 3, Servlet imports đổi gì?**  
Từ javax.servlet sang jakarta.servlet.

**20. Nếu POST bị browser chặn đọc bởi CORS, có nên retry vô điều kiện?**  
Không. Server có thể đã xử lý request; retry cần biết idempotency contract.

## 25. Tài liệu tham khảo

- **Spring Boot 3.3 Servlet Web Applications / SameSite Cookies:** https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html — session cookies, SameSite support trên Tomcat/Jetty/Undertow.
- **Spring Boot 3.3 Common Application Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — server.servlet.session.cookie.*, session timeout, tracking modes và forwarded config.
- **Spring Boot 3.3 Behind a Front-end Proxy Server:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — forwarded headers strategy, Tomcat redirect-context-root.
- **Spring Security Authentication Persistence & Session Management:** https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html — SecurityContextRepository, invalid session, fixation và logout.
- **Spring Session HttpSession Integration:** https://docs.spring.io/spring-session/reference/http-session.html — clustered sessions và Spring Session integration.
- **Spring Session Spring Boot + Redis:** https://docs.spring.io/spring-session/reference/guides/boot-redis.html — Spring Session Redis starter và architecture.
- **Spring Framework Servlet Filters:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — forwarded metadata/ForwardedHeaderFilter.
- **MDN Set-Cookie:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie — Domain, Path, Secure, HttpOnly, SameSite, expiry.
- **MDN Request.credentials:** https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials — omit/same-origin/include.
- **MDN Fetch Credentials:** https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch — credentials, SameSite, cross-origin CORS.
- **MDN Access-Control-Allow-Credentials:** https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials — credentialed response rules.
- **NGINX proxy_pass:** https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass — URI rewriting and path handling.
