# Cookie phiên với Secure, HttpOnly, SameSite, Path và thời gian sống

> **Mục tiêu:** Hiểu cookie phiên của ứng dụng Spring Security (Servlet) là gì, mỗi thuộc tính **Secure**, **HttpOnly**, **SameSite**, **Path**, **Domain**, **Max-Age/Expires** bảo vệ điều gì, và vì sao **thời gian sống của cookie trong trình duyệt khác thời gian sống của session trên server**. Biết cấu hình Spring Boot, kiểm tra **Set-Cookie**, kiểm thử login/logout và chọn chính sách phù hợp cho production.

## 1. Cookie phiên và session phía server không phải một thứ

Trong mô hình **session-based authentication**, server lưu trạng thái phiên, bao gồm thông tin giúp Spring Security khôi phục **SecurityContext** sau khi người dùng đăng nhập. Trình duyệt giữ một cookie chứa **session ID** (mặc định với nhiều Servlet container là **JSESSIONID**). Khi URL, domain, path, SameSite và các điều kiện cookie cho phép, trình duyệt tự gắn ID vào header **Cookie** của request tiếp theo.

~~~text
1) GET /login --> server tạo session (nếu cần) --> Set-Cookie: JSESSIONID=opaque-id; ...
2) Người dùng POST /login với credentials + CSRF hợp lệ
3) Spring Security xác thực, quản lý/đổi session ID theo cấu hình và lưu SecurityContext
4) GET /api/me
   Cookie: JSESSIONID=opaque-id
             |
             v
   Server/SessionRepository tìm session theo ID
             |
             v
   Đọc SecurityContext --> xác thực/authorization --> response
5) Session hết hạn/bị thu hồi: cookie có thể còn, nhưng ID không dẫn đến session hợp lệ
~~~

**Session ID là một bí mật có thể dùng để mạo danh khi bị đánh cắp.** Nó phải đủ ngẫu nhiên, khó đoán và được bảo vệ khi truyền/lưu. Cookie **không nên chứa mật khẩu, access token tùy tiện, role do client quyết định hay toàn bộ đối tượng người dùng**. Với JSESSIONID thông thường, cookie là một tham chiếu tới dữ liệu server; bản thân giá trị không cung cấp quyền nếu server đã xóa hoặc thu hồi session.

Đừng nhầm:

- **Cookie**: dữ liệu trình duyệt lưu và quyết định lúc nào gửi lại dựa trên các thuộc tính cookie.
- **HTTP session**: trạng thái phía server, có ID, thời điểm truy cập và chính sách hết hạn.
- **SecurityContext**: kết quả xác thực mà Spring Security có thể lưu/khôi phục qua session repository.
- **Remember-me**: một cơ chế riêng, có thể tạo lần xác thực mới từ cookie/token dài hạn. Nó không đồng nghĩa kéo dài JSESSIONID.
- **JWT bearer**: một mô hình token khác; không thể dùng quy tắc về JSESSIONID thay cho kiểm tra chữ ký, expiry và revoke của JWT.

Bài này tập trung vào **Spring Boot 3.x + Spring Security 6.x, Servlet/MVC**. WebFlux/Reactive và các hệ thống dùng **Spring Session** có thêm cấu hình chuyên biệt, không nên lấy tên property Servlet để suy ra mọi trường hợp.

## 2. Đọc đúng header Set-Cookie

Ví dụ phản hồi của server sau khi tạo phiên:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: JSESSIONID=opaque-random-session-id; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax

{"status":"session created"}
~~~

Trong request tiếp theo, trình duyệt chỉ gửi **tên=giá trị**:

~~~http
GET /api/me HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=opaque-random-session-id
~~~

**Secure/HttpOnly/SameSite/Path/Max-Age không xuất hiện trong header Cookie gửi lại**; chúng là hướng dẫn của server trong **Set-Cookie** mà trình duyệt dùng khi lưu và gửi cookie. Nếu cookie bị từ chối do vi phạm quy tắc, request tiếp theo sẽ không có session ID và ứng dụng thường coi client chưa đăng nhập.

| Thuộc tính Set-Cookie | Tác dụng chính | Giới hạn cần hiểu |
| --- | --- | --- |
| **Secure** | Chỉ gửi cookie qua kết nối HTTPS bảo mật (có ngoại lệ trong một số browser cho localhost) | Không thay cho TLS đúng cấu hình và kiểm tra certificate; không tự mã hóa giá trị cookie |
| **HttpOnly** | Cản JavaScript đọc/ghi cookie qua **document.cookie** | JavaScript độc hại vẫn có thể kích hoạt request dùng cookie; không xóa được rủi ro XSS/CSRF |
| **SameSite=Strict/Lax/None** | Điều chỉnh cookie có được gửi trong request **cross-site** hay không | Không phải cơ chế phân quyền và không thay CSRF token trong mọi ứng dụng |
| **Path=...** | Giới hạn đường dẫn request mà browser gửi cookie | Không tạo ranh giới bảo mật mạnh giữa ứng dụng cùng host |
| **Domain=...** | Mở phạm vi host/subdomain được nhận cookie; nếu bỏ thường là host-only | Domain quá rộng làm tăng phạm vi bị lộ/cookie injection |
| **Max-Age=seconds** | Thời gian tồn tại của cookie tại client, tính tương đối | Không làm gia hạn hay xác thực session đã hết hạn phía server |
| **Expires=HTTP-date** | Ngày hết hạn tuyệt đối tại client | Khi có cả Max-Age và Expires, Max-Age được ưu tiên |
| **Không có Max-Age/Expires** | Cookie phiên trình duyệt (browser-session cookie) | “Đóng browser” không phải mốc tuyệt đối do khả năng restore session |
| **Name** | Phân biệt cookie; thường là JSESSIONID | Trùng tên ở nhiều Path/Domain dễ tạo nhầm lẫn |

**Các thuộc tính phối hợp với nhau.** Chỉ cấu hình HttpOnly nhưng thiếu Secure cho endpoint HTTPS có thể làm cookie rò qua một request HTTP ngoài ý muốn. Chỉ cấu hình Secure nhưng để cookie bị đọc bởi JavaScript có thể làm tăng tác động của XSS. Chỉ cấu hình SameSite mà không bảo vệ thao tác thay đổi trạng thái bằng CSRF token có thể bỏ sót các luồng phù hợp điều kiện gửi cookie.

## 3. Secure: bắt buộc bảo vệ session ID trên HTTPS

### 3.1. Hành vi trình duyệt

Cookie có **Secure** được gửi qua kết nối HTTPS. Khi ứng dụng cố dùng cookie đó trên HTTP thông thường, trình duyệt không gửi nó (một số trình duyệt áp dụng ngoại lệ cho **localhost**; không dựa vào ngoại lệ ấy trong production).

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu đăng nhập qua **https://app.example.com**, request đến **http://app.example.com** không được phép mang cookie Secure theo hành vi trình duyệt chuẩn. Tuy nhiên, **Secure không làm mã hóa cookie**; TLS mã hóa kênh vận chuyển, còn giá trị cookie vẫn hiện ở server, reverse proxy tại điểm kết thúc TLS, các công cụ phát triển và những nơi vô tình log header.

Triển khai đúng cần:

1. Cung cấp **HTTPS** và chứng chỉ server hợp lệ; không bỏ qua xác minh certificate.
2. Bắt đầu flow đăng nhập và đặt cookie trên HTTPS, tránh request HTTP đầu tiên mang credential.
3. Cấu hình **server.servlet.session.cookie.secure=true** rõ ràng.
4. Đảm bảo các chặng reverse proxy → backend được bảo vệ theo threat model; tránh log **Cookie** và **Set-Cookie**.
5. Cấu hình redirect HTTPS/HSTS cho website theo thiết kế; không coi redirect là biện pháp thay thế cho việc chỉ gửi bí mật trên TLS.

### 3.2. Reverse proxy và load balancer

Một triển khai phổ biến:

~~~text
Browser --HTTPS--> Load balancer / ingress --HTTP nội bộ--> Spring Boot
             TLS terminate
~~~

Spring Boot ở backend có thể nhìn request ở dạng HTTP vì TLS đã kết thúc tại ingress. Nếu chỉ dựa vào **request.isSecure()** hoặc suy đoán tự động, ứng dụng có thể phát cookie thiếu Secure. Đặt **server.servlet.session.cookie.secure=true** giúp yêu cầu thuộc tính này một cách tường minh.

Nếu Spring Boot cần biết scheme/host thật để tạo redirect hoặc URL, cấu hình cơ chế **Forwarded/X-Forwarded-Proto** qua proxy đáng tin và **server.forward-headers-strategy** theo kiến trúc. Không nhận tùy tiện header forwarded do client Internet gửi vì có thể giả mạo scheme/host. Kiểm tra header **Set-Cookie** ở biên public thực tế, không chỉ từ backend container.

## 4. HttpOnly: giảm nguy cơ đánh cắp cookie qua JavaScript

~~~http
Set-Cookie: JSESSIONID=abc123; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Với **HttpOnly**, JavaScript chạy trong trang không thể lấy cookie qua **document.cookie**. Điều này làm khó việc đánh cắp session ID qua lỗ hổng XSS.

Nhưng HttpOnly **không làm cookie “vô hình” ở mọi nơi**:

- Trình duyệt vẫn tự gửi cookie khi gọi **fetch/XHR** nếu request đủ điều kiện cookie và credentials mode/CORS.
- XSS vẫn có thể kích hoạt yêu cầu đã đăng nhập, đọc dữ liệu trả về trong cùng origin, hoặc làm hành động thay user.
- Session ID vẫn có thể lộ qua logs, reverse proxy, máy bị kiểm soát, extension trình duyệt có đặc quyền hoặc truy cập vật lý tùy tình huống.
- HttpOnly không ngăn CSRF: một trang độc hại có thể kích hoạt một số loại request khiến trình duyệt tự đính kèm cookie nếu SameSite và chính sách browser cho phép.

**Quy tắc:** đánh dấu HttpOnly cho cookie session; đồng thời áp dụng output encoding, CSP, chống XSS, CSRF protection, kiểm soát CORS và phân quyền đúng. Nếu frontend cần CSRF token, phát token qua cơ chế được thiết kế riêng, không buộc frontend phải đọc **JSESSIONID**.

## 5. SameSite: Strict, Lax và None khác nhau ở đâu?

**SameSite** giúp trình duyệt quyết định có đính kèm cookie khi request xuất phát từ **site khác** hay không. Site là khái niệm dựa trên **scheme + registrable domain** trong browser hiện đại, khác với **origin** vốn gồm scheme, host và port. Vì vậy **https://app.example.com** và **https://api.example.com** thường là **same-site** nhưng **cross-origin**; CORS vẫn có thể được yêu cầu cho JavaScript gọi API.

| SameSite | Hành vi chính | Dùng khi nào | Rủi ro/hạn chế |
| --- | --- | --- | --- |
| **Strict** | Không gửi cookie trên các request phát sinh từ site khác, kể cả top-level navigation | Khu vực nhạy cảm, ít cần điều hướng từ ngoài | Người dùng nhấp link từ site khác có thể bị coi là chưa đăng nhập ở request đầu |
| **Lax** | Gửi cookie trong request same-site; thường gửi trên **top-level cross-site navigation với phương thức an toàn** như GET | Website đăng nhập session thông thường | Không ngăn được mọi CSRF; GET phải không thay đổi trạng thái |
| **None** | Cho phép gửi trong ngữ cảnh cross-site, tùy chính sách trình duyệt | Tích hợp cần third-party/cross-site cookie và đã đánh giá đầy đủ | **Bắt buộc có Secure** trong browser hiện đại; third-party cookie có thể bị chặn |
| **Không khai báo** | Browser áp dụng mặc định riêng, nhiều browser coi gần giống Lax | Không khuyến khích dựa vào mặc định | Một số browser có ngoại lệ tạm thời, đặc biệt với cookie vừa cấp |

Với **SameSite=None**, dùng cấu hình **Secure=true**. Những browser hạn chế third-party cookies có thể chặn cookie bất chấp SameSite=None; không giả định thuộc tính này bảo đảm mọi iframe/SPA cross-site đều hoạt động.

**SameSite=Lax không thay cho CSRF token.** Cookie có thể được gửi trên top-level GET điều hướng từ site khác; ứng dụng không được thực hiện thao tác ghi dữ liệu qua GET. Ngoài ra same-site request từ subdomain khác có thể vẫn mang cookie theo cơ chế same-site. Nếu dùng session cookie để đăng nhập, nên duy trì CSRF protection cho các unsafe method như POST/PUT/PATCH/DELETE theo chính sách Spring Security.

### 5.1. Ví dụ cùng site, khác origin

Frontend tại **https://app.example.com** gọi backend **https://api.example.com**:

- Hai URL có thể **same-site** nên **SameSite=Lax** không tự ngăn request.
- Chúng là **cross-origin** nên JavaScript fetch phải tuân thủ **CORS**, chính sách **credentials** và header phản hồi server.
- Nếu cookie là **host-only** dành cho **api.example.com**, browser gửi cookie tới API host khi đủ điều kiện; frontend không cần và không nên đọc session ID.
- Nếu frontend và API nằm ở **hai registrable domain khác nhau**, đó là cross-site: lựa chọn SameSite=None + Secure có thể cần thiết, nhưng còn phụ thuộc chính sách third-party cookie và thiết kế xác thực.

Ví dụ frontend:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include",
});
const profile = await response.json();
~~~

Đối với cross-origin request dùng credentials, phía API phải phản hồi **Access-Control-Allow-Origin** với origin cụ thể được phép và **Access-Control-Allow-Credentials: true** theo chính sách; không kết hợp wildcard origin với credentials. CORS không thay xác thực hoặc CSRF và không nên dùng để cho mọi origin tùy ý truy cập API.

### 5.2. Khi có OAuth2/OIDC login callback

Một số luồng đăng nhập liên kết site bên ngoài dùng top-level redirect trở lại callback. **SameSite=Strict** có thể khiến cookie session không được gửi trên bước quay về, dẫn tới mất state/session; **Lax** có thể phù hợp với callback top-level GET. Nếu flow cần cross-site POST/iframe, có thể phải xét **None** và biện pháp bổ sung. Việc chọn SameSite phải được thử trên browser đích với đúng OAuth2/OIDC flow, không suy ra từ một request GET nội bộ.

## 6. Path và Domain: giới hạn phạm vi cookie, không phải authorization

### 6.1. Path

~~~http
Set-Cookie: JSESSIONID=...; Path=/app; Secure; HttpOnly; SameSite=Lax
~~~

Cookie **Path=/app** thường được gửi tới **/app** và các đường con phù hợp như **/app/profile**, không gửi tới **/other**. **Path=/** cho phép browser gửi cookie cho toàn bộ đường dẫn trong host thuộc phạm vi.

Một số quy tắc thực hành:

- Dùng **Path=/** khi ứng dụng cần session ở login/logout, API và các trang thuộc cùng host.
- Với ứng dụng nằm dưới **/portal**, cân nhắc **Path=/portal** nếu mọi endpoint liên quan đều nằm trong phạm vi đó.
- Không tùy tiện đặt **Path=/api** nếu form login ở **/login** và callback nằm ngoài **/api**; browser sẽ không gửi cookie đúng chỗ.
- Khi xóa cookie phải dùng **cùng name, Path và Domain** thích hợp với cookie gốc; khác Path có thể tạo thêm cookie cùng tên hoặc không xóa được cookie cũ.

**Path không phải cơ chế cô lập bảo mật giữa hai ứng dụng cùng origin.** Script cùng origin và các đường xử lý liên quan có thể tương tác theo những cách không tạo ranh giới tin cậy vững. Không dựa vào Path để bảo vệ dữ liệu bí mật khỏi một ứng dụng không đáng tin đang cùng host.

### 6.2. Domain: host-only thường tốt hơn

Nếu **không đặt Domain**, cookie thường là **host-only**: trình duyệt chỉ gửi tới host đã cấp. Nếu đặt **Domain=example.com**, cookie có thể được gửi tới host gốc và các subdomain phù hợp. Mở Domain rộng làm tăng nơi nhận cookie và các bề mặt tấn công từ subdomain; không đặt Domain trừ khi có yêu cầu thật.

~~~http
# Host-only: server app.example.com cấp, không có Domain
Set-Cookie: JSESSIONID=...; Secure; HttpOnly; Path=/; SameSite=Lax

# Domain cookie: scope rộng hơn, cần đánh giá rủi ro
Set-Cookie: JSESSIONID=...; Domain=example.com; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Dấu chấm đầu trong **Domain=.example.com** không còn mang nghĩa đặc biệt theo các quy tắc cookie hiện đại. Việc Domain mở rộng không làm server ở các subdomain tin cậy lẫn nhau; phân quyền vẫn phải diễn ra ở ứng dụng.

### 6.3. Cookie prefix `__Host-`

Với browser hỗ trợ cookie prefixes, tên bắt đầu **__Host-** phải có **Secure**, **Path=/**, **không có Domain** và được đặt qua một ngữ cảnh an toàn. Đây là cách làm mạnh hơn để hạn chế phạm vi cookie khi ứng dụng có thể tuân thủ các ràng buộc ấy.

~~~http
Set-Cookie: __Host-JSESSIONID=...; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Không tự đổi tên JSESSIONID thành **__Host-JSESSIONID** nếu ứng dụng đang chạy dưới Path khác / hoặc cần Domain cookie; browser có thể từ chối cookie vi phạm quy tắc prefix. Khi đổi tên cookie, cần sửa cả cấu hình logout/clear-cookie, monitoring và test. Prefix chỉ bổ sung ràng buộc trình duyệt, không thay xác minh phiên phía server.

## 7. Hai đồng hồ: tuổi thọ cookie ở client và timeout session ở server

Đây là phần dễ nhầm nhất khi cấu hình “thời gian sống”.

### 7.1. Cookie Max-Age / Expires

~~~http
Set-Cookie: JSESSIONID=...; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
~~~

**Max-Age=1800** nghĩa là browser có thể giữ cookie tối đa khoảng **1.800 giây (30 phút)** kể từ lúc nhận header. Đây là thời gian phía client, **không** đảm bảo session còn hợp lệ trên server trong suốt 30 phút. Nếu server tiếp tục phát Set-Cookie mới thì thời điểm hết hạn cookie có thể thay đổi theo header mới; không mặc định mỗi request đều làm mới Max-Age.

**Expires** biểu diễn ngày giờ tuyệt đối; **Max-Age** có ưu tiên nếu cả hai có mặt. **Max-Age=0** là yêu cầu xóa cookie khỏi browser. Nếu không có Max-Age/Expires thì là cookie phiên trình duyệt; browser có thể restore session sau khi khởi động lại, nên không coi việc đóng cửa sổ là đảm bảo đăng xuất.

### 7.2. Server session timeout (idle timeout)

Với Servlet:

~~~properties
server.servlet.session.timeout=15m
~~~

Đây là khoảng thời gian **session có thể không được truy cập trước khi hết hạn**, tùy session repository/container. Một request hợp lệ đến session thường làm cập nhật last-accessed time; session sẽ hết hạn sau một khoảng bất hoạt. Đây **không phải absolute lifetime** tính từ lúc đăng nhập.

Ví dụ cấu hình:

~~~properties
server.servlet.session.cookie.max-age=30m
server.servlet.session.timeout=15m
~~~

Giả sử:

- **10:00**: server tạo session S và phát cookie có Max-Age 30 phút.
- **10:10**: người dùng không gửi request trong 10 phút; session vẫn có thể hợp lệ.
- **10:16**: nếu không có request nào kể từ 10:00, server có thể đã coi S hết hạn sau 15 phút bất hoạt. Browser vẫn có thể giữ cookie tới 10:30 nhưng **server không chấp nhận ID cũ**.
- **10:31**: cookie hết tuổi theo Max-Age ngay cả nếu có hoạt động phía server; browser không gửi lại cookie cũ nếu không được phát lại/renew theo thiết kế.

**Tương quan hai đồng hồ:** truy cập lặp lại có thể gia hạn **idle timeout server**, nhưng không bảo đảm tự gia hạn **cookie Max-Age**. Đặt cùng giá trị không khiến hai cơ chế hoạt động giống hệt nhau. Nếu cần sliding session, absolute session limit hoặc “remember me”, phải thiết kế riêng và thử bằng browser thực tế.

### 7.3. Logout, session fixation và thay đổi quyền

Đăng xuất đúng cần:

1. **Invalidate** session phía server hoặc thu hồi liên kết xác thực theo session store.
2. **Clear SecurityContext** và ngăn sử dụng lại session cũ.
3. Gửi hướng dẫn xóa cookie nếu phù hợp, với **name/Path/Domain** trùng cookie gốc; kiểm tra ở browser.
4. Đảm bảo endpoint logout được bảo vệ CSRF phù hợp khi dùng session cookie.

Cookie có thể vẫn còn sau khi invalidate server session do khác biệt container/cấu hình xóa cookie. **Đó không phải bằng chứng logout thất bại nếu ID cũ đã vô hiệu**, nhưng nên dọn cookie để giảm nhầm lẫn trải nghiệm. Xóa cookie phía browser mà không invalidate session server thì ID bị sao chép trước đó vẫn có thể còn dùng được.

Spring Security mặc định có bảo vệ **session fixation** cho login qua các filter chuẩn, thường thay **session ID** trên Servlet container hiện đại. Không để kẻ tấn công cố định ID trước đăng nhập rồi tiếp tục sử dụng sau đăng nhập. Với controller tự xác thực bằng AuthenticationManager, phải xử lý session authentication strategy và lưu SecurityContext theo đúng cơ chế, thay vì giả định mọi bảo vệ filter tự chạy.

Khi tài khoản bị khóa, role bị thu hồi hoặc người dùng đổi mật khẩu, một session đang hoạt động không tự biến mất trong mọi thiết kế. Phải có chính sách **invalidate session / refresh authorities / session registry** đáp ứng yêu cầu bảo mật.

## 8. Cấu hình Spring Boot 3.x / Spring Security 6.x (Servlet)

### 8.1. Ví dụ cấu hình trực tiếp

Bắt đầu bằng dự án **Java 17+, Spring Boot 3.x, Spring Web, Spring Security** từ Spring Initializr. Tệp **src/main/resources/application.properties**:

~~~properties
# HTTPS cho môi trường thực hành localhost
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./localhost-demo.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localhost-demo

# Thuộc tính cookie phiên Servlet
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/

# Phân biệt lifetime client và idle timeout server
server.servlet.session.cookie.max-age=30m
server.servlet.session.timeout=15m

# Chỉ dùng cho tài khoản demo ở local
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Các property này thuộc namespace **server.servlet.session**. Không nhầm với **server.reactive.session** của WebFlux. **server.servlet.session.cookie.same-site** được Spring Boot hỗ trợ với Servlet container tự cấu hình phổ biến như Tomcat, Jetty, Undertow; trong ứng dụng thật vẫn phải kiểm tra Set-Cookie ở biên public.

**Cookie Max-Age 30 phút và server idle timeout 15 phút được chọn có chủ đích để chứng minh chúng khác nhau.** Khi xây production, chọn giá trị theo risk model: ứng dụng nhạy cảm có thể yêu cầu thời gian bất hoạt ngắn, absolute lifetime và re-authentication cho thao tác quan trọng. Tránh đặt cookie tồn tại quá lâu mà không có lý do.

Nếu muốn cookie chỉ tồn tại trong session trình duyệt, **bỏ thuộc tính cookie.max-age** (không đặt nó về 0 vì 0 mang nghĩa hết hạn ngay). Khi đó timeout server vẫn hoạt động độc lập.

### 8.2. Java tối thiểu để tạo và sử dụng session

Tệp **src/main/java/com/example/sessioncookie/SessionCookieApplication.java**:

~~~java
package com.example.sessioncookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCookieApplication.class, args);
    }
}
~~~

Tệp **src/main/java/com/example/sessioncookie/SecurityConfig.java**:

~~~java
package com.example.sessioncookie;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .logout(logout -> logout
                        .logoutSuccessUrl("/public/bye")
                        .permitAll())
                .build();
    }
}
~~~

**formLogin** sử dụng session sau khi đăng nhập. Theo cấu hình chuẩn Spring Security, **POST /login** cần CSRF token hợp lệ; không tắt CSRF để chạy demo. Mật khẩu được băm bằng BCrypt trong nguồn người dùng phía server. Class không trả password hoặc session ID qua endpoint.

Tệp **src/main/java/com/example/sessioncookie/SessionController.java**:

~~~java
package com.example.sessioncookie;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/public/session")
    public Map<String, String> prepareSession(
            HttpServletRequest request) {
        request.getSession(true);
        return Map.of("status", "session created");
    }

    @GetMapping("/api/me")
    public Map<String, String> currentUser(
            Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/public/bye")
    public Map<String, String> afterLogout() {
        return Map.of("status", "logged out");
    }
}
~~~

**GET /public/session** chủ động tạo session để dễ quan sát header Set-Cookie. Trong ứng dụng thật không nhất thiết phải tạo session cho mọi khách chưa đăng nhập; chỉ tạo khi cần thiết để tránh tốn tài nguyên và tránh tạo session ID không cần.

### 8.3. HTTPS localhost với chứng chỉ thực hành

Trong thư mục gốc dự án, dùng **keytool** đi kèm JDK để tạo file PKCS#12:

~~~bash
keytool -genkeypair -alias localhost-demo -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore localhost-demo.p12 -storepass local-only-pass -keypass local-only-pass -dname "CN=localhost" -ext "SAN=dns:localhost"
keytool -exportcert -rfc -alias localhost-demo -keystore localhost-demo.p12 -storepass local-only-pass -file localhost-demo.crt
~~~

Đây là chứng chỉ tự ký **chỉ dành cho localhost**. Trong môi trường production phải dùng chứng chỉ được tin cậy, quản lý private key an toàn và không commit **.p12**, mật khẩu hoặc secret. Tên file, alias và password phải khớp cấu hình.

Trên Linux/macOS:

~~~bash
export TLS_KEYSTORE_PASSWORD=local-only-pass
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
$env:TLS_KEYSTORE_PASSWORD = "local-only-pass"
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

Sau khi Spring Boot chạy, xác minh certificate bằng CA/certificate file ở local thay vì tắt TLS verification.

~~~bash
curl --cacert localhost-demo.crt -i -c cookies.txt https://localhost:8443/public/session
~~~

Response sẽ chứa một header **Set-Cookie** tương tự:

~~~http
Set-Cookie: JSESSIONID=<gia-tri-ngau-nhien>; Path=/; Max-Age=1800; Expires=<ngay-gio>; Secure; HttpOnly; SameSite=Lax
~~~

**Đây là dạng minh họa**, thứ tự/cách biểu diễn/Expires có thể khác tùy container và Spring Boot patch version; giá trị session ID và ngày hết hạn là động. Điều phải kiểm tra là **sự có mặt và ý nghĩa của các thuộc tính**, không hard-code toàn bộ chuỗi header.

Sau khi lưu cookie vào **cookies.txt**, thử gọi route cần login:

~~~bash
curl --cacert localhost-demo.crt -i -b cookies.txt https://localhost:8443/api/me
~~~

Do chưa đăng nhập, ứng dụng form login thường trả **302** tới **/login**. Browser có thể dùng biểu mẫu mặc định ở **https://localhost:8443/login**; để kiểm thử trong trình duyệt cần tin cậy chứng chỉ localhost bằng quy trình phát triển phù hợp. **Không** dùng `curl -k` hoặc tắt SSL validation cho đường thật.

Sau khi đăng nhập thành công bằng browser, gọi **/api/me** sẽ trả JSON:

~~~json
{"username":"alice"}
~~~

Lúc đó DevTools → Application/Storage → Cookies có thể cho biết cookie đang được lưu, thuộc tính Secure/HttpOnly/SameSite/Path, thời hạn và host. Không copy giá trị session ID vào ticket/log công khai. Tại tab Network, xem response login/Set-Cookie, request Cookie và redirect/CSRF.

### 8.4. Không copy cấu hình Servlet cho WebFlux hoặc Spring Session mà không kiểm tra

Với **Spring Boot reactive**, có các property như **server.reactive.session.cookie.same-site** và timeout WebSession riêng. Với **Spring Session** (Redis/JDBC), repository và cookie serializer có thể có cấu hình đặc biệt và TTL trong kho phân tán. Spring Boot có thể áp dụng một số property phiên cho auto-configured Spring Session Servlet, nhưng dự án tùy biến cần kiểm tra chính implementation đang phát Set-Cookie và lưu TTL.

Quan sát thực tế ở load balancer, container và browser là nguồn xác minh cuối cùng. Đừng nghĩ rằng đặt một property luôn đảm bảo proxy không ghi đè header.

## 9. Kiểm thử thuộc tính cookie và vòng đời session

### 9.1. Test ở cấp HTTP header với embedded container

**MockMvc** mô phỏng Servlet API và rất phù hợp kiểm tra flow Spring Security, nhưng nó không thay thế việc nhìn thấy **Set-Cookie thật của embedded container**. Khi kiểm tra Secure/HttpOnly/SameSite/Path/Max-Age, nên có ít nhất một bài test chạy server thực hoặc kiểm thử qua URL deployment.

Thêm **spring-boot-starter-test** vào project (nếu chưa có). Tệp **src/test/java/com/example/sessioncookie/SessionCookieHeaderTest.java**:

~~~java
package com.example.sessioncookie;

import java.util.List;
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.ssl.enabled=false",
        "demo.user.password=test-only"
    }
)
class SessionCookieHeaderTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void sessionCookieContainsSecurityAttributes() {
        ResponseEntity<String> response = client.getForEntity(
                "http://localhost:" + port + "/public/session",
                String.class);

        assertTrue(response.getStatusCode().is2xxSuccessful());
        List<String> headers =
                response.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertNotNull(headers);

        String rawCookie = headers.stream()
                .filter(h -> h.startsWith("JSESSIONID="))
                .findFirst()
                .orElseThrow();

        String lower = rawCookie.toLowerCase(Locale.ROOT);
        assertTrue(lower.contains("path=/"));
        assertTrue(lower.contains("secure"));
        assertTrue(lower.contains("httponly"));
        assertTrue(lower.contains("samesite=lax"));
        assertTrue(lower.contains("max-age=1800"));
    }
}
~~~

Test cố tình tắt TLS **chỉ trong embedded test server** để dễ truy cập bằng TestRestTemplate, vẫn xác minh rằng cấu hình buộc server **phát** header có Secure. Bài test này **không chứng minh trình duyệt gửi cookie qua HTTPS**; cần thêm kiểm thử E2E với certificate hợp lệ. Trong production, không dùng server HTTP với Secure cookie vì browser sẽ không gửi session một cách đáng tin cậy.

**Nếu test thất bại**, xem Set-Cookie thực tế và version/container trước khi thay đổi assertion; có thể Spring Session, reverse proxy hoặc custom cookie serializer đang quản lý header.

### 9.2. Test login và SecurityContext bằng MockMvc

Thêm dependency **spring-security-test** ở test scope. Tệp **src/test/java/com/example/sessioncookie/SessionFlowTest.java**:

~~~java
package com.example.sessioncookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "demo.user.password=test-only",
    "server.ssl.enabled=false"
})
@AutoConfigureMockMvc
class SessionFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginCreatesUsableAuthenticatedSession() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("test-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void unauthenticatedRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Test này chứng minh login bằng mật khẩu thực qua **UsernamePasswordAuthenticationFilter / AuthenticationManager** tạo session có thể dùng trong request sau. Nó **không đo thời gian 15/30 phút bằng cách chờ** và cũng không kiểm tra cookie do container phát. Khi cần test expiry ở server, hãy dùng session repository/test clock có thể điều khiển, hoặc test thời gian có tính toán hợp lý; tránh test chờ 15 phút làm CI chậm và không ổn định.

### 9.3. Ma trận các tình huống phải xác minh

| Kịch bản | Quan sát phía browser/HTTP | Quan sát phía server |
| --- | --- | --- |
| Cookie có Secure + HTTPS | Có cookie, request HTTPS gửi lại đúng scope | Session được tìm thấy |
| Truy cập HTTP thường | Browser không gửi Secure cookie | Request không được nhận diện từ cookie |
| Cookie HttpOnly | **document.cookie** không đọc được session ID | Request hợp lệ vẫn có thể mang cookie |
| SameSite=Strict khi link từ site khác | Cookie có thể vắng trong request điều hướng đầu | Có thể coi user chưa login ở bước đó |
| SameSite=Lax với top-level GET cross-site | Cookie có thể được gửi | GET không được thay đổi dữ liệu |
| SameSite=None + Secure | Cross-site có thể mang cookie nếu browser policy cho phép | Server vẫn phải xác thực và chống CSRF |
| Path=/app, request tới /other | Cookie không gửi theo Path | Không nhận session từ cookie đó |
| Host-only cookie | Không được gửi sang host sibling | Tránh mở rộng phạm vi subdomain |
| Cookie còn, server session hết idle timeout | Browser vẫn giữ cookie | Session lookup thất bại, cần đăng nhập lại |
| Cookie hết Max-Age, server session còn | Browser ngừng gửi cookie | Dù server còn record, client không truy cập qua cookie cũ |
| Login thành công | Session ID được thay đổi theo chính sách fixation | SecurityContext được lưu |
| Logout | Có thể nhận hướng dẫn xóa cookie | Session cũ phải bị invalidated |
| Cookie bị sao chép | Có thể thử replay nếu không có bảo vệ bổ sung | Phải có HTTPS, session invalidation, phát hiện bất thường |
| Reverse proxy TLS terminate | Set-Cookie công khai vẫn có Secure | Không tin forwarded headers từ client tùy ý |

**Không log nguyên header Cookie/Set-Cookie trong bài test production.** Khi cần evidence, chỉ lưu các thuộc tính (Secure/HttpOnly/SameSite/Path/Max-Age), status và thời điểm. Session ID là credential và phải được che.

## 10. Lỗi thường gặp và cách sửa

### 10.1. “Đã bật HTTPS nên không cần Secure”

Kết nối HTTPS hiện tại không bảo đảm mọi đường gửi cookie về sau đều bắt đầu bằng HTTPS, nhất là khi có redirect, cấu hình proxy sai hoặc HTTP endpoint phụ. **Sửa:** buộc **Secure=true**, enforce HTTPS và xác minh ở biên public.

### 10.2. “HttpOnly ngăn được XSS/CSRF”

HttpOnly chỉ giới hạn cách JavaScript đọc cookie. XSS vẫn có thể sử dụng browser để hành động thay user; CSRF dựa vào cookie được gửi tự động khi điều kiện phù hợp. **Sửa:** chống XSS, sử dụng CSRF token cho session auth, phân quyền, giới hạn CORS và áp dụng SameSite thích hợp.

### 10.3. “SameSite=Lax nghĩa là mọi cross-site request đều bị chặn”

Lax có ngoại lệ top-level navigation với phương thức an toàn; cùng site khác subdomain cũng không phải cross-site. **Sửa:** hiểu site vs origin, không dùng GET để mutate, giữ CSRF token cho request thay đổi trạng thái.

### 10.4. “Cookie Max-Age=30m đồng nghĩa user đăng nhập được 30m”

Không đúng nếu server timeout 15m hoặc account bị khóa/session bị revoke trước đó. **Sửa:** định nghĩa rõ idle timeout, cookie lifetime, absolute lifetime và re-authentication; test cả phía client và server.

### 10.5. “Đặt Path=/api sẽ làm /login an toàn hơn”

Nếu login/logout ở ngoài /api, cookie có thể không được gửi đến các endpoint cần session. Path không phải security sandbox. **Sửa:** chọn Path phủ đúng toàn bộ URL của một phiên và kiểm thử callback/login/logout.

### 10.6. “Domain=.example.com luôn tốt để chia sẻ đăng nhập”

Domain rộng khiến cookie có thể tới nhiều subdomain, tăng bề mặt nhận secret. **Sửa:** ưu tiên host-only; khi cần SSO đa host, thiết kế IdP/SSO chuẩn thay vì phát cùng JSESSIONID cho mọi subdomain.

### 10.7. “Logout chỉ cần xóa cookie trong browser”

Session server có thể vẫn tồn tại và bị dùng lại nếu ID từng bị đánh cắp. **Sửa:** server invalidate session và clear SecurityContext, sau đó xử lý xóa cookie đúng name/Path/Domain.

### 10.8. “Bật Secure=true rồi test trên http://localhost thấy không login”

Browser có thể không gửi Secure cookie trên HTTP; ngoại lệ localhost không thống nhất mọi browser và công cụ. **Sửa:** dùng HTTPS localhost với certificate tin cậy hoặc bài test chuyên kiểm tra header, không mang cấu hình HTTP dev vào production.

### 10.9. “Test MockMvc đã đủ chứng minh Set-Cookie production”

MockMvc không chạy toàn bộ hệ thống embedded container/proxy/browser. **Sửa:** test property/HTTP header ở container thực, thêm E2E ở domain HTTPS sau ingress và kiểm tra cookie store trong browser.

## 11. Checklist trước khi đưa vào production

- [ ] Website và mọi endpoint nhận cookie/credential dùng **HTTPS**; TLS certificate được kiểm tra.
- [ ] Session cookie có **Secure**, **HttpOnly** và **SameSite** theo nhu cầu thực.
- [ ] Cookie có **Path** đúng cho login/logout/API/callback; không chọn Path chỉ theo thói quen.
- [ ] Ưu tiên **host-only** (bỏ Domain) nếu không có nhu cầu chia sẻ subdomain thực sự.
- [ ] Dùng **__Host-** chỉ khi ứng dụng đáp ứng Secure + Path=/ + không Domain; kiểm tra browser và logout.
- [ ] **Cookie Max-Age/Expires** và **server session timeout** được lựa chọn, tài liệu hóa và kiểm thử riêng.
- [ ] Có chính sách **absolute session lifetime**, session fixation, session invalidation sau logout và khi revoke nếu yêu cầu bảo mật.
- [ ] Có cơ chế **CSRF** phù hợp khi browser gửi cookie tự động; không dựa riêng vào SameSite.
- [ ] Không để session ID, Cookie/Set-Cookie hay password trong logs, metrics, exception hoặc URL.
- [ ] Cấu hình reverse proxy, trusted forwarded headers và nội bộ TLS đúng mô hình triển khai.
- [ ] Test tại server thật và browser thật trên domain production/staging, kiểm tra **Set-Cookie** và request **Cookie**.
- [ ] Frontend cross-origin dùng CORS/credentials đúng; không mở wildcard origin cho credentialed requests.
- [ ] Phân biệt session cookie với remember-me, refresh token và các token dài hạn khác.
- [ ] Nếu dùng Spring Session, kiểm tra TTL của kho dữ liệu và serializer phát cookie; không đoán từ Servlet container mặc định.

## 12. Tài liệu tham khảo

- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): các property **server.servlet.session.cookie.*** và **server.servlet.session.timeout**.
- [Spring Boot 3.5 — Servlet Web Applications / SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): cấu hình SameSite trên Servlet container và Spring Session.
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContext, session fixation và quản lý session.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): bảo vệ các yêu cầu thay đổi trạng thái dùng xác thực dựa trên cookie.
- [Spring Security 6.5 — Handling Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): invalidation, clear authentication và xử lý cookie/logout.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, Domain, Path, SameSite, Max-Age, Expires, cookie prefixes.
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): các nguyên tắc giảm lộ cookie và phạm vi cookie.
