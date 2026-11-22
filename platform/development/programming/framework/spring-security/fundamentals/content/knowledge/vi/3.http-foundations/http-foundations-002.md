# Header Authorization và các cách truyền thông tin xác thực trong HTTP

> **Phạm vi:** nền tảng HTTP trong Spring Security (Servlet/Spring MVC, Java 17+, Spring Boot 3.x). Bài học giải thích thông tin xác thực đi từ client đến server bằng cách nào, ý nghĩa chính xác của header **Authorization**, sự khác biệt giữa Basic, Bearer, cookie/session và những cách truyền credential khác. Không phải mọi cách truyền đều dùng cùng cơ chế xác thực hoặc có cùng mức độ an toàn.

## 1. Trước hết: credential được truyền đi, danh tính mới được xác minh

Khi gọi một API có bảo vệ, client cần đưa bằng chứng để server biết mình là ai hoặc đang đại diện cho ai. Bằng chứng đó có thể là **username/password**, **access token**, **session identifier**, **API key**, **chữ ký request** hoặc **chứng chỉ client**.

Có ba việc cần phân biệt:

1. **Credential transport:** bằng chứng được gửi ở đâu? Ví dụ HTTP request header, cookie, request body hoặc TLS handshake.
2. **Authentication:** hệ thống xác minh bằng chứng như thế nào? Ví dụ tra cứu tài khoản và kiểm tra mật khẩu, xác minh JWT, tra cứu session hoặc kiểm tra chữ ký.
3. **Authorization:** sau khi biết danh tính và authorities, hệ thống có cho phép truy cập endpoint/tài nguyên cụ thể không?

~~~text
Client
  |
  |  Request + credential (nếu có)
  v
HTTP / TLS transport
  |
  v
Spring Security: chọn SecurityFilterChain
  |
  +--> Bộ lọc nhận credential phù hợp (Basic / Bearer / session / ...)
  |        |
  |        v
  |    Xác minh -> Authentication -> SecurityContext
  |
  +--> Kiểm tra quyền (AuthorizationManager)
               |
               +--> ALLOW -> Controller / Service -> HTTP response
               |
               +--> DENY  -> AuthenticationEntryPoint / AccessDeniedHandler
~~~

**Authorization** là tên một HTTP header; **authorization** cũng là tên hoạt động *phân quyền*. Header **Authorization** chủ yếu dùng để **mang thông tin xác thực** đến server. Nó không tự quyết định người dùng có quyền hay không.

Một header nhìn có vẻ hợp lệ vẫn có thể mang mật khẩu sai, token hết hạn, token dành cho API khác hoặc token không đủ quyền. Server phải xác minh bằng chứng, rồi đánh giá quyền.

## 2. Cú pháp và vòng đời của header Authorization

HTTP cung cấp khuôn dạng tổng quát cho HTTP authentication:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: <scheme> <credentials>
~~~

Đoạn trên là **mẫu cú pháp**, không phải một credential sử dụng được. Phần **scheme** chỉ cách server nên diễn giải phần credential:

| Scheme | Ví dụ ý nghĩa | Bằng chứng chính |
| --- | --- | --- |
| **Basic** | Tài khoản và mật khẩu được mã hóa Base64 | Username/password |
| **Bearer** | Ai sở hữu token có thể dùng token theo phạm vi của nó | Access token |
| **Digest** | Cơ chế challenge/response dựa trên thông số của scheme | Giá trị băm tính từ credential/challenge |
| **Negotiate** | HTTP authentication có thể sử dụng SPNEGO/Kerberos | Token của giao thức |
| **AWS4-HMAC-SHA256** | Chữ ký request theo quy tắc của dịch vụ | Credential scope + chữ ký HMAC |

Một số lưu ý quan trọng:

- **Tên HTTP header không phân biệt chữ hoa/chữ thường**: **Authorization** và **authorization** biểu thị cùng trường header.
- **Tên authentication scheme cũng không phân biệt chữ hoa/chữ thường** theo HTTP, nhưng nội dung credential/token cần được giữ chính xác; **không chuyển token thành lowercase**.
- Cú pháp phần sau scheme **phụ thuộc scheme**. Không tự giả định mọi credential đều là JWT hoặc Base64.
- Header **Authorization** dùng cho server đích. Header **Proxy-Authorization** dành cho proxy yêu cầu xác thực và có challenge riêng **Proxy-Authenticate**.
- **Content-Type** và **Accept** nói về kiểu dữ liệu request/response, **không mang credential**. Một **X-CSRF-TOKEN** cũng không thay thế **Authorization**: CSRF token chứng minh tính hợp lệ của hành động trong cơ chế bảo vệ CSRF, không tự là danh tính đăng nhập.

### 2.1. Chu trình challenge/response

HTTP authentication có thể diễn ra như sau:

~~~http
GET /api/private HTTP/1.1
Host: api.example.test
~~~

Server có thể trả về:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="learning"
~~~

Client chọn scheme được hỗ trợ và gửi lại request kèm credential:

~~~http
GET /api/private HTTP/1.1
Host: api.example.test
Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l
~~~

Chuỗi Base64 minh họa tương ứng với **aladdin:opensesame**, không phải token cần lấy ở server thực. Sau khi kiểm tra credential, server có thể trả **200**, **403**, hoặc một response khác theo nghiệp vụ.

**Không phải client nào cũng chờ 401 mới gửi header**. API client thường gửi Authorization ngay ở request đầu tiên (*preemptive authentication*). Một ứng dụng dùng session cookie có thể không gửi Authorization header dù vẫn đang đăng nhập.

### 2.2. Phân biệt Authorization và WWW-Authenticate

| Header | Hướng | Vai trò |
| --- | --- | --- |
| **Authorization** | Client → server | Gửi credential của HTTP authentication |
| **WWW-Authenticate** | Server → client | Thông báo scheme/challenge để xác thực, thường đi cùng 401 |
| **Proxy-Authorization** | Client → proxy | Gửi credential cho proxy |
| **Proxy-Authenticate** | Proxy → client | Challenge của proxy, thường đi cùng 407 |
| **Cookie** | Browser/client → server | Gửi cookie, có thể chứa session identifier |
| **Set-Cookie** | Server → browser/client | Thiết lập cookie theo chính sách thuộc tính |

**401 Unauthorized** trong HTTP thường có nghĩa client cần cung cấp thông tin xác thực hợp lệ. Tên status dễ gây hiểu nhầm; thông thường đây là vấn đề *authentication*. **403 Forbidden** thường nghĩa server đã nhận diện client nhưng không cho phép hành động, hoặc request bị một cơ chế bảo vệ khác chặn. Với form login, request chưa đăng nhập có thể bị **302 Redirect** đến trang đăng nhập thay cho challenge 401. Các response cụ thể còn tùy cấu hình.

## 3. HTTP Basic: truyền username/password qua Authorization

**HTTP Basic** là cơ chế rất dễ hiểu và được nhiều HTTP client hỗ trợ:

~~~text
username + ":" + password
       |
       v
bytes (theo charset thống nhất)
       |
       v
Base64
       |
       v
Authorization: Basic <base64-string>
~~~

Ví dụ:

~~~text
username: aladdin
password: opensesame

Chuỗi ghép: aladdin:opensesame
Base64:    YWxhZGRpbjpvcGVuc2VzYW1l
~~~

Request tương ứng:

~~~http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l
~~~

**Base64 không phải mã hóa bảo mật**. Bất kỳ ai thấy chuỗi Base64 đều có thể giải mã lấy username/password. Với Basic, client thường có thể gửi credential lại ở nhiều request; vì vậy cần **HTTPS/TLS** cho mọi môi trường có lưu lượng mạng. Không gửi Basic qua HTTP plaintext.

### 3.1. Tự tạo Basic header bằng Java 17

File **BasicHeaderDemo.java** sau đây **độc lập**, chỉ dùng JDK:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {
    public static void main(String[] args) {
        String username = "aladdin";
        String password = "opensesame";
        String pair = username + ":" + password;

        String encoded = Base64.getEncoder()
            .encodeToString(pair.getBytes(StandardCharsets.UTF_8));

        System.out.println("Authorization: Basic " + encoded);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
~~~

**Stdout chính xác:**

~~~text
Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l
~~~

Ví dụ cố ý dùng credential giả để thấy được cách mã hóa; **đừng in credential thực hoặc ghi nó vào log**.

**Lưu ý charset:** với username/password chứa ký tự ngoài ASCII, client và server phải thống nhất cách biểu diễn; đặc tả Basic cho phép challenge thông báo **charset="UTF-8"**. Khi gặp lỗi đăng nhập với dấu tiếng Việt hoặc Unicode, đừng đoán server luôn diễn giải byte như UTF-8 nếu chưa xác nhận cấu hình hai phía. Dấu hai chấm đầu tiên phân cách username và password; username không nên chứa dấu hai chấm theo định dạng Basic.

### 3.2. Gửi Basic bằng curl

~~~bash
curl -i -u aladdin:opensesame https://api.example.test/api/me
~~~

Cú pháp này để **minh họa cách curl tạo Basic Authorization**; URL mẫu không phải một API chạy sẵn. Trong terminal thật, chuỗi mật khẩu trên command line có thể xuất hiện trong history hoặc thông tin tiến trình; có thể dùng **curl -u aladdin** và để curl hỏi mật khẩu, tùy môi trường chạy. Tránh dán mật khẩu thật vào script, log, ảnh chụp màn hình hoặc kho mã nguồn.

### 3.3. Basic có phải một lần đăng nhập rồi dùng session?

**Không bắt buộc.** HTTP Basic là cơ chế truyền username/password và xác thực theo request. Sau khi xác thực, Spring Security đặt đối tượng **Authentication** vào **SecurityContext** để các filter/controller dùng trong request đó; việc lưu context sang request kế tiếp phụ thuộc **SecurityContextRepository/session policy**. Đừng suy ra “Basic mặc định luôn có session” hoặc “Basic mặc định luôn stateless” khi chưa kiểm tra cấu hình ứng dụng.

Với API dùng Basic, có thể đặt **SessionCreationPolicy.STATELESS** để Spring Security không tạo/dùng HttpSession lưu SecurityContext. Điều này không thay đổi việc password phải được bảo vệ khi truyền.

## 4. Bearer token: truyền quyền truy cập bằng một token

Scheme **Bearer** thường xuất hiện khi client gọi OAuth2 Resource Server:

~~~http
GET /api/reports HTTP/1.1
Host: resource.example.test
Authorization: Bearer abc.def.ghi
~~~

Chuỗi **abc.def.ghi** chỉ minh họa cú pháp, **không phải một JWT hợp lệ**.

Từ “bearer” nhấn mạnh rằng **bên nào nắm giữ token thường có thể sử dụng token**, nếu server chấp nhận nó. Nếu token bị lộ, kẻ khác có thể dùng lại cho đến khi token hết hiệu lực hoặc bị thu hồi theo cơ chế của hệ thống. Cần bảo vệ token như một bí mật.

### 4.1. Bearer không đồng nghĩa JWT

Bearer mô tả **cách sử dụng token**; nội dung access token có thể là:

- **JWT**: token chứa claims trong các phần được mã hóa Base64URL; với JWS, server xác minh chữ ký, thuật toán cho phép và các claims liên quan.
- **Opaque token**: chuỗi không mang cấu trúc claims đọc được từ phía client; resource server có thể hỏi authorization server qua introspection hoặc cơ chế tương ứng.
- Một định dạng token khác mà hệ thống đã thống nhất.

Một JWT có thể được đọc phần payload sau khi Base64URL decode, nhưng **đọc được không có nghĩa token hợp lệ hoặc đã được xác minh chữ ký**. JWT ký (JWS) thông thường **không mã hóa bí mật dữ liệu trong claims**. Đừng đặt mật khẩu, private key hoặc thông tin riêng tư không cần thiết vào claims.

**Validation tối thiểu phù hợp loại token và hệ thống** có thể gồm: chữ ký/khóa tin cậy, thuật toán được phép, **issuer (iss)**, **audience (aud)**, **expiration (exp)**, thời điểm có hiệu lực **nbf**, trạng thái thu hồi/active nếu áp dụng, và quyền **scope/authorities**. Không tự coi việc decode JWT là bước đăng nhập. Đặc biệt, việc cấu hình issuer không có nghĩa mọi hệ thống đã tự kiểm tra đúng audience mong muốn; phải kiểm tra cấu hình decoder/validator.

### 4.2. Access token khác ID token và refresh token

| Token | Mục đích | Gửi đến API tài nguyên? |
| --- | --- | --- |
| **Access token** | Cho resource server kiểm tra quyền truy cập | **Có**, khi resource server dự kiến nhận nó |
| **ID token** (OpenID Connect) | Thông tin về phiên xác thực của user dành cho OAuth/OIDC client | **Không thay access token** để gọi API |
| **Refresh token** | Xin access token mới qua luồng được cấp phép | **Không gửi làm Bearer** đến resource API |

Lỗi phổ biến là đặt **ID token** vào Authorization header gọi API rồi tưởng đó là access token, hoặc gửi refresh token cho mọi endpoint. Cả hai đều sai mục đích và có thể làm lộ thông tin nhạy cảm.

### 4.3. Cách gửi Bearer bằng HTTP client

Với shell có biến môi trường **ACCESS_TOKEN** đã chứa access token thật cho đúng API:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://resource.example.test/api/reports
~~~

Dấu xuống dòng **\\** và cú pháp **$ACCESS_TOKEN** trong ví dụ phù hợp shell kiểu bash; với PowerShell, sử dụng cách đọc biến môi trường của PowerShell. **Không chạy thử trên endpoint không tin cậy** vì header đó mang credential có giá trị. Không đặt token vào URL hoặc commit token vào repository.

Ở Java dùng **Spring WebClient/RestClient**, hãy dùng API đặt Bearer header thay vì tự nối chuỗi thủ công khi thư viện đã hỗ trợ. Chỉ chuyển token xuống dịch vụ khác nếu token **đúng audience và scope** cho dịch vụ ấy; không tự động forward bearer token của người dùng đến mọi downstream host.

### 4.4. Các lỗi Bearer và response

Với một resource server tuân theo OAuth2 Bearer:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Khi token không hợp lệ, challenge có thể cho thêm thông tin như **error="invalid_token"**. Với token hợp lệ nhưng thiếu scope, response thường là **403** và có thể kèm **error="insufficient_scope"**.

Đừng dựa vào body lỗi cố định để xác định lý do; client nên nhìn **status**, challenge và cấu hình API. Không phản hồi token thô hoặc dữ liệu nội bộ qua message lỗi.

## 5. So sánh các cách chuyển credential qua HTTP/TLS

**Authorization header là cách phổ biến, nhưng không phải lựa chọn duy nhất.**

| Cách truyền | Ví dụ vị trí | Thường dùng cho | Rủi ro/điều cần biết |
| --- | --- | --- | --- |
| **Authorization: Basic** | Request header | Username/password | Base64 giải mã được; thường gửi lặp lại; phải dùng HTTPS |
| **Authorization: Bearer** | Request header | OAuth2 access token | Token bị đánh cắp có thể bị phát lại; cần audience/scope/hạn dùng |
| **Cookie: SESSION=...** | Request header Cookie | Session-based web app | Browser tự đính kèm; quản lý SameSite, CSRF và session |
| **X-API-Key: ...** | Custom request header | API key cho service/client | Key thường dài hạn; cần scope, rotation, rate limit |
| **Authorization: AWS4-HMAC-SHA256 ...** | Signed request header | API có xác thực bằng chữ ký | Phải canonicalize đúng method/path/query/headers/body, timestamp |
| **mTLS client certificate** | TLS handshake | Dịch vụ với danh tính bằng chứng chỉ | Quản lý CA, cấp phát/thu hồi chứng chỉ và ánh xạ danh tính |
| **Username/password trong login body** | HTTPS POST form hoặc JSON | Đăng nhập trước khi tạo session/token | Chỉ gửi đến endpoint đăng nhập tin cậy; không log body |
| **Access token trong URL query** | Query string | Trường hợp đặc biệt/legacy | **Không khuyến nghị**: rò qua log, history, URL được chia sẻ |
| **Access token trong form body** | application/x-www-form-urlencoded | Trường hợp hạn chế theo RFC 6750 | Có điều kiện chặt, không phải lựa chọn mặc định cho resource API |

**Hình thức truyền quyết định nguy cơ, nhưng không tự quyết định tính hợp lệ.** Dù credential đến từ header, cookie hay TLS, backend vẫn cần xác minh nó và kiểm tra quyền tại đúng điểm truy cập.

### 5.1. API key và custom header

Một API có thể tự định nghĩa:

~~~http
GET /api/jobs HTTP/1.1
Host: internal.example.test
X-API-Key: demo-key-for-explanation
~~~

**X-API-Key** là quy ước phổ biến, không phải scheme HTTP authentication mặc định mà Spring Security tự xác minh. Nếu dùng API key, phải triển khai/ghép cơ chế đọc header, đối chiếu key với bản ghi an toàn và sinh **Authentication** thích hợp. Có thể thay bằng một scheme Authorization được tài liệu API quy định, nhưng **không tự chế scheme khi OAuth2, mTLS hoặc công cụ có sẵn đã đáp ứng yêu cầu**.

API key thường chứng minh **danh tính ứng dụng/client**, không nhất thiết chứng minh người dùng cuối. Khi kiểm tra quyền, cần phân biệt “service A” với “user X đang dùng service A”. Chỉ cấp quyền cần thiết, có hạn dùng/rotation khi phù hợp, audit và giới hạn tốc độ.

### 5.2. Chữ ký request (HMAC)

Một số hệ thống không gửi mật khẩu thô mà ký một biểu diễn chuẩn hóa (*canonical request*) gồm method, path, query, một số headers, hash body và timestamp. Server tự dựng biểu diễn tương ứng, kiểm tra chữ ký, thời điểm và chính sách phát lại.

Đây là **cơ chế khác** với Basic/Bearer. Việc tự thêm header **Signature** không làm Spring Security tự hiểu hoặc kiểm tra chữ ký; cần dùng thư viện/triển khai của giao thức cụ thể và chính sách chống replay. Sai khác trong canonicalization có thể làm request hợp lệ bị từ chối hoặc gây lỗi an toàn.

### 5.3. mTLS

Với **mutual TLS**, client xuất trình **client certificate** trong quá trình bắt tay TLS; danh tính có thể được xác minh ở reverse proxy hoặc ứng dụng, rồi ánh xạ sang principal. Không nhất thiết có **Authorization** header. Nếu proxy chấm dứt TLS và truyền thông tin danh tính xuống backend qua header, chỉ tin header đó khi proxy được kiểm soát và backend không thể bị gọi trực tiếp để giả mạo header.

## 6. Cookie/session: đã đăng nhập nhưng không có Authorization header

Một ứng dụng web đăng nhập bằng form có thể dùng session cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Response trên là ví dụ chính sách cookie; thuộc tính thực tế phụ thuộc ứng dụng và servlet container. Browser lưu cookie rồi gửi trong các request tiếp theo nếu điều kiện Domain/Path/Secure/SameSite phù hợp:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<session-id>
~~~

**Session identifier là credential**: người giữ session ID hợp lệ có thể được server gắn với phiên của người dùng. Server tra cứu session (hoặc hệ thống quản lý session) rồi khôi phục thông tin liên quan đến authentication theo cấu hình. Cookie **không tự là role hoặc password**; nó thường chỉ mang một định danh phiên.

Các thuộc tính cần hiểu:

- **HttpOnly** hạn chế JavaScript truy cập cookie qua document.cookie, giúp giảm một số nguy cơ đánh cắp cookie do XSS; nó **không ngăn XSS gửi request nhân danh user**.
- **Secure** chỉ cho gửi cookie qua kênh phù hợp HTTPS (với một số khác biệt trên localhost); luôn thiết lập cho session cookie trên production.
- **SameSite=Lax/Strict/None** kiểm soát ngữ cảnh gửi cookie cross-site ở browser. **SameSite=None** yêu cầu **Secure** trong browser hiện đại.
- **Path/Domain** giới hạn phạm vi cookie; đặt hẹp hợp lý và cân nhắc prefix **__Host-** nếu điều kiện kỹ thuật phù hợp.
- **Max-Age/Expires** và thời hạn session phía server ảnh hưởng vòng đời. Xóa cookie ở browser không thay thế hoàn toàn việc vô hiệu hóa session phía server.

**Cookie và Authorization không loại trừ nhau trên cùng một HTTP request.** Một request có thể đồng thời mang session cookie và Bearer/Basic header. Hệ thống phải có chính sách rõ ràng về chain/filter và **nguồn danh tính nào được chấp nhận**, tránh xung đột hoặc hành vi không dự đoán được.

### 6.1. Cookie tự đính kèm và CSRF

Browser thường tự đính kèm cookie theo chính sách cookie. Trang độc hại có thể khiến browser gửi một request có tác động đến ứng dụng đã đăng nhập. Vì vậy ứng dụng dùng **cookie/session cho các thao tác thay đổi trạng thái** cần xem xét CSRF protection.

Spring Security Servlet bật bảo vệ **CSRF** theo mặc định cho các HTTP method không an toàn, ví dụ **POST**, nếu chưa thay cấu hình. Client phải cung cấp CSRF token hợp lệ theo cơ chế tương ứng khi endpoint yêu cầu. **Không tắt CSRF chỉ để một POST hết lỗi 403**.

API chỉ chấp nhận **Bearer token được client tự gắn trong Authorization header** và không phụ thuộc credential browser tự gửi có mô hình CSRF khác với session-cookie app. Tuy vậy, **nếu bearer token nằm trong cookie được browser tự gửi**, rủi ro CSRF vẫn tồn tại. Cả trình duyệt dùng HTTP Basic với credential được tự động gửi lại cũng cần được phân tích theo ngữ cảnh.

### 6.2. Có nên đặt access token trong cookie?

Với một **Backend for Frontend (BFF)**, browser có thể giữ session cookie HttpOnly, còn backend lưu/điều phối access token để gọi resource API. Đây là cách tránh đưa access token cho JavaScript của browser, nhưng cần quản lý CSRF, session, XSS và backend trust boundaries.

Đặt **access token trực tiếp trong cookie** không có nghĩa resource server tự đọc nó: Spring Security OAuth2 Resource Server **mặc định tìm Bearer token trong Authorization header**. Nếu muốn dùng cơ chế cookie, phải thiết kế rõ luồng xác thực; đừng bật một resolver tùy ý chỉ vì muốn “tự nhận token ở mọi nơi”.

## 7. Đặt credential trong request body và URL

### 7.1. POST /login có username/password trong body

~~~http
POST /login HTTP/1.1
Host: app.example.test
Content-Type: application/x-www-form-urlencoded

username=alice&password=example
~~~

Đây là ví dụ mô tả; cần **HTTPS** và endpoint login đã triển khai. Server xác minh credential rồi có thể **tạo session** hoặc **phát hành token** tùy kiến trúc. Việc username/password đi trong body **không tự làm chúng an toàn hơn header**, vì body vẫn có thể bị ghi log hoặc lộ khi TLS bị cấu hình sai. Login API và resource API có nhiệm vụ khác nhau; resource API thường **không nhận mật khẩu ở mỗi request**.

Trong OAuth2 Authorization Code + PKCE, **authorization code** có thể xuất hiện ở redirect callback URI rồi được client đổi lấy token qua token endpoint. **Authorization code không phải access token**; cần dùng state/PKCE và cấu hình redirect URI đúng quy trình. Không suy ra rằng vì authorization code từng xuất hiện trong query nên việc đưa **access token** vào URL là an toàn.

### 7.2. Tại sao không đưa access token vào URL?

Ví dụ cần tránh:

~~~http
GET /api/me?access_token=sample-secret HTTP/1.1
Host: resource.example.test
~~~

URL có thể bị ghi vào **access log, reverse proxy log, browser history, analytics, telemetry, ảnh chụp, liên kết được sao chép** và nhiều hệ thống trung gian. RFC 6750 có mô tả cách truyền token qua query nhưng **không khuyến nghị** vì rủi ro lộ token.

Tương tự, tránh **username/password** trong URL, ví dụ thông qua phần userinfo hoặc query parameter. Nếu có nhu cầu tương thích một hệ thống cũ, nên giới hạn chặt, đánh giá và chuyển sang chuẩn được hỗ trợ sớm nhất.

### 7.3. Form-encoded Bearer token cũng là ngoại lệ

RFC 6750 cho phép một phương thức truyền access token trong **request entity-body** có **Content-Type: application/x-www-form-urlencoded** khi thỏa các điều kiện nhất định. Đây **không phải phương thức mặc định**. Spring Security Resource Server mặc định không bật lấy token từ form body; việc mở hỗ trợ đòi hỏi cấu hình resolver riêng.

Một API mới nên ưu tiên **Authorization: Bearer** qua HTTPS, trừ khi giao thức/kiến trúc cụ thể buộc một lựa chọn khác.

## 8. Header Authorization trong Spring Security Servlet

Spring Security không “tự đăng nhập” mọi request có header Authorization. Filter phù hợp phải được bật và có cấu hình xác minh credential.

### 8.1. HTTP Basic filter

Với **httpBasic(...)**, chuỗi xử lý điển hình:

~~~text
Authorization: Basic <base64>
         |
         v
BasicAuthenticationFilter
         |
         v
UsernamePasswordAuthenticationToken (chưa xác thực)
         |
         v
AuthenticationManager
         |
         v
AuthenticationProvider (ví dụ DaoAuthenticationProvider)
         |
         +--> UserDetailsService + PasswordEncoder
         |
         v
Authentication đã xác thực
         |
         v
SecurityContextHolder -> AuthorizationFilter -> Controller
~~~

Nếu credential sai, cơ chế xác thực xử lý lỗi và có thể gọi **AuthenticationEntryPoint** để trả 401. Nếu thiếu credential, quy tắc yêu cầu authenticated có thể kích hoạt **ExceptionTranslationFilter** và Basic entry point. Với người dùng đã xác thực nhưng thiếu authority, thông thường trả **403**.

**httpBasic** không đọc Bearer token như JWT. Nếu gửi **Authorization: Bearer ...** vào ứng dụng chỉ cấu hình Basic thì request không vì thế được xác thực là Bearer. Cần bật đúng cơ chế Resource Server.

### 8.2. Bearer token filter

Với cấu hình **oauth2ResourceServer(...)**, flow điển hình:

~~~text
Authorization: Bearer <access-token>
         |
         v
BearerTokenAuthenticationFilter
         |
         v
BearerTokenResolver (mặc định đọc Authorization header)
         |
         v
AuthenticationManager / AuthenticationProvider phù hợp
         |
         +--> JWT: JwtDecoder, validators, authorities mapping
         |
         +--> Opaque: introspection / trạng thái token
         |
         v
Authentication trong SecurityContext
         |
         v
AuthorizationFilter -> Controller
~~~

**Một Authorization header không có token Bearer hợp lệ** không tạo ra danh tính hợp lệ. Resource Server phải có cấu hình khóa/tin cậy cần thiết để kiểm tra token. Sau khi xác thực vẫn phải áp dụng **scope/authority** và policy theo tài nguyên.

### 8.3. Session cookie

Với form login/session, các thành phần quản lý SecurityContext có thể khôi phục thông tin từ **SecurityContextRepository/HttpSession** khi bắt đầu request. Không cần BasicAuthenticationFilter hay BearerTokenAuthenticationFilter để mỗi lần đọc cookie lại kiểm tra password. Authentication có thể đã được lưu từ lần login trước, tùy cấu hình và trạng thái session.

Các flow trên **có thể kết hợp**, nhưng mỗi ứng dụng phải chủ động thiết kế matcher, filter chain, chính sách lưu context và nguồn authentication ưu tiên. Không nên nhận “bất kỳ credential nào có mặt” mà không có nguyên tắc rõ.

## 9. Ví dụ thực hành đầy đủ: Spring Boot 3 + HTTP Basic

Phần này là **một ứng dụng có thể chạy độc lập** với Java 17+ và Spring Boot 3.x. Nó minh họa request có/không có Authorization header và phản hồi authentication/authorization. Các endpoint chỉ dùng **GET** để không cần trộn logic demo với quy trình cấp CSRF token của các request thay đổi trạng thái.

Dùng dự án Spring Boot 3.x đã được cấu hình Gradle/Java, thêm **Spring Web**, **Spring Security** và dependencies kiểm thử:

**build.gradle** (đoạn dependencies thêm vào project đã có plugin và version management):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Tạo ba file trong **src/main/java/com/example/headerauth/**.

### 9.1. HeaderAuthApplication.java

~~~java
package com.example.headerauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeaderAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeaderAuthApplication.class, args);
    }
}
~~~

### 9.2. SecurityConfig.java

~~~java
package com.example.headerauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

Giải thích:

- **httpBasic(Customizer.withDefaults())** bật xử lý Basic Authorization header.
- **SessionCreationPolicy.STATELESS** chỉ rõ ví dụ không dựa vào HttpSession để lưu/đọc SecurityContext cho request kế tiếp; Basic credential được dùng mỗi khi gửi request cần xác thực.
- **/api/public** công khai, **/api/me** đòi đăng nhập, **/api/admin** đòi **ROLE_ADMIN**. Các URL khác bị deny.
- **BCryptPasswordEncoder** kiểm tra mật khẩu qua hash, thay vì so sánh plaintext. Mật khẩu demo đơn giản chỉ dùng cho **localhost**, không dùng trong production.
- **hasRole("ADMIN")** theo mặc định kiểm tra authority **ROLE_ADMIN**. Một username đã xác thực không tự có quyền ADMIN.

### 9.3. DemoController.java

~~~java
package com.example.headerauth;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        String roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + roles;
    }

    @GetMapping("/api/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

Spring MVC có thể cung cấp **Authentication** hiện hành cho tham số controller trên request đã xác thực. Endpoint **/api/me** cho thấy danh tính và authorities **sau khi** Spring Security đã xử lý header.

### 9.4. Chạy ứng dụng và quan sát header/status

Từ thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Dùng terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u alice:wrong http://localhost:8080/api/me
curl -i -H "Authorization: Bearer sample.invalid.token" \
  http://localhost:8080/api/me
~~~

**Dự kiến** với đúng config demo:

| Request | Status | Body khi thành công / nguyên nhân |
| --- | --- | --- |
| GET /api/public, không credential | **200** | **public** |
| GET /api/me, không credential | **401** | HTTP Basic yêu cầu xác thực |
| GET /api/me, Basic alice:alice123 | **200** | **alice ROLE_USER** |
| GET /api/admin, Basic alice:alice123 | **403** | Đã xác thực nhưng thiếu ROLE_ADMIN |
| GET /api/admin, Basic admin:admin123 | **200** | **admin-only** |
| GET /api/me, Basic password sai | **401** | Credential không hợp lệ |
| GET /api/me, Bearer mẫu | **401** | Ứng dụng chỉ bật HTTP Basic, không bật Resource Server |

Khi thử thiếu credential, hãy xem header **WWW-Authenticate** của 401. Ở HTTP Basic thông thường nó thông báo scheme Basic; một số cấu hình có thể tùy chỉnh challenge hoặc xử lý khác với request XHR. Các response lỗi không có body cố định để dựa vào.

**Lưu ý:** demo này không kiểm chứng Bearer token vì chưa cấu hình Resource Server. Không dùng kết quả 401 của một chuỗi Bearer giả để kết luận JWT thật hợp lệ hay không.

### 9.5. Kiểm thử Spring Security thông qua MockMvc

Tạo **src/test/java/com/example/headerauth/AuthorizationHeaderTest.java**:

~~~java
package com.example.headerauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationHeaderTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireAuthorization() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void missingCredentialsGetUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsCreateAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER"));
    }

    @Test
    void invalidPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserMayStillBeForbidden() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void bearerHeaderIsNotBasicAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer sample.invalid.token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**MockMvc** gửi request qua chuỗi filter do Spring Boot kiểm thử tích hợp; test này kiểm tra cách client trình bày Basic header cùng quyết định HTTP. **httpBasic(...)** trong Spring Security Test giúp xây dựng header đúng định dạng, không phải bypass authentication. Các test không cần hard-code chuỗi Base64.

## 10. Nếu dùng Bearer JWT thay Basic, cấu hình thế nào?

Đây là **một biến thể kiến trúc riêng** của ví dụ trên; không đặt thêm cùng SecurityFilterChain demo Basic nếu chưa thiết kế policy chấp nhận nhiều credential. Với **Spring Boot 3.x**, resource server JWT thường cần dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Ví dụ **application.yml** dưới đây dùng URL issuer tượng trưng; **phải thay bằng issuer thật, công khai metadata/JWK hợp lệ** để resource server chạy và xác minh token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
~~~

Bên trong một lớp **@Configuration**, có thể cấu hình chain riêng cho API dùng Bearer như sau (đoạn trích **không phải chương trình Java độc lập**):

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Cần các import tương ứng (**HttpSecurity**, **SecurityFilterChain**, **Bean**, **Customizer**) và cấu hình JWT decoder hợp lệ trong project. Với mapping scope mặc định thường gặp, token có scope **reports.read** được chuyển thành authority **SCOPE_reports.read**. Nếu hệ thống dùng claim hoặc prefix khác, phải cấu hình converter tương ứng. **Token hợp lệ vẫn phải có scope đủ và được intended audience chấp nhận**; cần cấu hình kiểm tra audience đúng API thay vì chỉ dựa vào việc token có chữ ký hợp lệ.

Spring Security Resource Server mặc định nhận Bearer từ **Authorization**. Nếu token ở custom header/form body, một **BearerTokenResolver** tùy chỉnh có thể hỗ trợ, nhưng đó là quyết định kiến trúc cần được đánh giá; cấu hình mặc định **không** tự đọc cookie hoặc query access_token như cách đăng nhập tương đương.

Đối với **opaque access token**, thay hướng xử lý JWT bằng cấu hình **opaqueToken/introspection** phù hợp authorization server. Đừng viết code tách chuỗi JWT để tự xác thực opaque token.

## 11. Browser: Authorization, CORS và credential mode

Khi JavaScript frontend gọi API khác origin:

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
    headers: {
        Authorization: "Bearer " + accessToken
    }
});
~~~

Đây là **đoạn minh họa**, biến **accessToken** phải đến từ cơ chế lấy token hợp lệ; không được hard-code secret trong mã nguồn frontend. Browser được phép để code set Authorization header, nhưng **cross-origin request có Authorization thường dẫn đến CORS preflight** (**OPTIONS**) trước actual request.

Server cần phản hồi preflight phù hợp, ví dụ cho phép origin và header **Authorization** theo CORS policy. **CORS là chính sách browser kiểm soát quyền đọc response cross-origin**, không phải bằng chứng đăng nhập hay authorization ở backend. Dùng Postman/curl chạy được không chứng minh frontend browser sẽ qua CORS.

Với session cookie và cross-origin **fetch**, client có thể cần:

~~~javascript
const response = await fetch("https://api.example.test/account", {
    credentials: "include"
});
~~~

Khi dùng credentialed CORS, server phải cấu hình **Access-Control-Allow-Credentials** và **Access-Control-Allow-Origin** đúng origin được phép; browser không chấp nhận wildcard **\*** cho Allow-Origin trong trường hợp credentialed request. Cookie còn phải phù hợp **SameSite**, **Secure**, Domain/Path và chính sách browser. **credentials: "include"** không tự tạo session hay cấp quyền nếu cookie không tồn tại.

**Khác biệt đáng nhớ:**

- Authorization Bearer được code JavaScript gắn thủ công thường **không được browser tự thêm vào mọi request**.
- Cookie/session có thể được browser **tự gửi** nếu đáp ứng điều kiện cookie, vì vậy phải chú ý CSRF.
- Khi browser giữ Basic credential, browser có thể tự gửi lại tùy cơ chế HTTP authentication; cũng cần đánh giá CSRF và hành vi browser thật.
- Thay đổi CORS không sửa được token sai, thiếu scope hoặc requestMatcher sai.

## 12. Checklist an toàn khi truyền credential

1. **Bắt buộc HTTPS/TLS** khi gửi password, token, cookie phiên hoặc API key qua mạng. Client phải kiểm tra chứng chỉ server; không dùng tùy chọn tắt kiểm tra TLS để “sửa lỗi” môi trường production.
2. **Không đưa bí mật vào URL**, log, query, browser history, analytics, stack trace, telemetry, screenshot hoặc thông báo lỗi. Đặt bộ lọc redaction cho **Authorization**, **Cookie**, **Set-Cookie**, **X-API-Key** và request body của login.
3. **Chọn đúng loại credential**: access token cho resource API, ID token cho OIDC client, refresh token cho token endpoint; password chỉ truyền nơi xác thực có chủ đích.
4. **Giới hạn lifetime, scope và audience**. Key/token bị lộ cần có khả năng thu hồi hoặc rotation tùy mô hình. Nếu resource server nhận nhiều issuer, cần thiết kế trust boundary rõ ràng.
5. **Không tùy tiện forward Authorization header qua redirect/call downstream**. Chỉ gửi token đến host tin cậy và đúng audience; khi HTTP client tự follow redirect cần kiểm tra hành vi chuyển header, đặc biệt qua domain khác.
6. **Kiểm soát proxy/gateway**: bảo đảm header cần thiết được chuyển đến đúng backend; không tin header “X-User” do Internet client tự tạo. TLS termination không đồng nghĩa client-to-backend luôn an toàn nếu kênh nội bộ bị nghe lén.
7. **Tách quyền authentication và authorization**: header đúng format chưa chứng minh được quyền; luôn kiểm tra action, resource, tenant và scope.
8. **Xem xét CSRF với browser credential tự gửi**, session fixation, XSS và logout/session invalidation. **HttpOnly** giảm nguy cơ đọc cookie bằng JavaScript nhưng không tự giải quyết mọi loại XSS hay CSRF.
9. **Không lưu access token lâu dài trong localStorage mà bỏ qua mô hình XSS**. Chọn cách lưu token/cookie/BFF dựa trên threat model và vòng đời token, tránh diễn đạt “cứ HttpOnly là đủ an toàn”.
10. **Test cả trạng thái thiếu/sai credential**. Ngoài 200, cần test 401, 403, token quá hạn, sai audience, sai quyền, đường dẫn chưa khai báo và hành vi proxy/CORS nếu client thực tế dùng browser.

## 13. Chẩn đoán một request bị 401 hoặc 403

Khi **curl** với Authorization header vẫn bị từ chối, kiểm tra theo thứ tự:

| Cần xác minh | Câu hỏi chẩn đoán |
| --- | --- |
| **Transport** | Request thực sự có Authorization/Cookie tới đúng host và qua HTTPS không? |
| **Scheme** | API chờ **Basic** hay **Bearer**? Có gửi ID token thay access token không? |
| **Filter chain** | Request khớp **SecurityFilterChain** nào? Có bật httpBasic/resource server đúng chain không? |
| **Credential validity** | Basic password đúng? JWT đúng signature/issuer/audience/exp? Opaque token còn active? |
| **SecurityContext** | Có Authentication hợp lệ được đặt vào context không? |
| **Authority/scope** | Có đúng ROLE_ADMIN hoặc SCOPE_reports.read như rule yêu cầu không? |
| **Resource policy** | Đã kiểm tra owner, tenant, action và trạng thái nghiệp vụ chưa? |
| **Other filters** | Có CSRF, CORS, reverse proxy, custom filter hoặc lỗi của app tác động response không? |

Trong môi trường phát triển có thể bật log Spring Security:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Chỉ dùng mức log phù hợp và **không ghi raw credential/token**. Với production, ưu tiên correlation ID, principal ID đã được xác minh, action, resource ID và quyết định access, tuân theo chính sách dữ liệu.

Các sai lầm điển hình:

- **Nhầm Authorization với quyền:** có header Bearer không chứng minh token hợp lệ hoặc được đọc tài liệu bất kỳ.
- **Nhầm Base64 với mã hóa:** Basic lộ mật khẩu khi credential bị đọc.
- **Nhầm JWT với mọi Bearer token:** opaque token không decode thành claims trên client.
- **Nhầm Cookie với Authorization:** session browser có thể hợp lệ dù Authorization vắng mặt.
- **Nhầm 401 với 403:** sai credential/thiếu xác thực khác với có danh tính nhưng thiếu quyền.
- **Nhầm CORS với authorization:** CORS là quy tắc truy cập của browser, không thay việc kiểm soát ở backend.
- **Đưa access token vào URL:** rất dễ bị hệ thống trung gian vô tình lưu lại.
- **Lấy token từ mọi vị trí để “tiện”:** mở rộng bề mặt tấn công và gây xung đột nguồn danh tính.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Request có **Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l**. Server đã có thể coi người gọi hợp lệ chưa?

**Trả lời:** Chưa. Đó là username/password sau mã hóa Base64; server còn phải kiểm tra credential, trạng thái tài khoản và các quy tắc truy cập.

**Câu 2.** Request không có Authorization header nhưng có session cookie hợp lệ. Spring Security có thể nhận diện người dùng không?

**Trả lời:** Có, nếu ứng dụng có cơ chế session/khôi phục SecurityContext được cấu hình phù hợp và phiên còn hợp lệ. Không phải mọi ứng dụng đều dùng session.

**Câu 3.** **Authorization: Bearer** có bắt buộc chứa JWT không?

**Trả lời:** Không. Bearer token có thể là JWT, opaque token hoặc định dạng phù hợp với hệ thống; phải xác minh theo cơ chế tương ứng.

**Câu 4.** Tại sao một trang web gọi API qua fetch gặp lỗi CORS trong khi curl gọi API được?

**Trả lời:** Browser áp dụng CORS (thường có preflight khi dùng Authorization cross-origin), còn curl không áp dụng chính sách CORS của browser. API vẫn phải kiểm tra authentication và authorization độc lập.

**Câu 5.** HTTP Basic hay Bearer có thể an toàn khi dùng HTTP plaintext không?

**Trả lời:** Không. Cần HTTPS/TLS để bảo vệ credential trên đường truyền; Base64 của Basic không có khả năng giữ bí mật, Bearer token bị lộ có thể bị sử dụng lại.

**Câu 6.** Vì sao nên tránh gửi access token trong query string?

**Trả lời:** URL có nhiều nơi lưu lại như history, access log, analytics hoặc liên kết chia sẻ; điều đó làm tăng khả năng credential bị lộ.

**Câu 7.** Một API đang cấu hình **httpBasic(...)** nhận **Authorization: Bearer**. Có tự xác thực token không?

**Trả lời:** Không. Cần cấu hình/filter xử lý Bearer thích hợp (thường OAuth2 Resource Server) và validation token hợp lệ.

**Câu 8.** Có thể dùng **HttpOnly cookie** rồi bỏ qua CSRF không?

**Trả lời:** Không. HttpOnly hạn chế truy cập cookie từ JavaScript; cookie vẫn có thể được browser tự gửi. Những request làm thay đổi trạng thái cần cơ chế chống CSRF phù hợp với kiến trúc.

## Tài liệu tham khảo chính thức

- HTTP Semantics — **Authorization / HTTP authentication**: https://www.rfc-editor.org/rfc/rfc9110.html
- HTTP Basic Authentication — **RFC 7617**: https://www.rfc-editor.org/rfc/rfc7617.html
- OAuth 2.0 Bearer Token Usage — **RFC 6750**: https://www.rfc-editor.org/rfc/rfc6750.html
- MDN — **Authorization header**: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Authorization
- MDN — **HTTP Authentication**: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication
- Spring Security — **HTTP Basic Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — **OAuth 2.0 Bearer Tokens**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html
- Spring Security — **CSRF**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — **Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html

**Điểm cốt lõi:** **Authorization** là đường truyền credential trong khuôn khổ HTTP authentication. Server chỉ xác lập danh tính sau khi đã kiểm tra credential bằng cơ chế phù hợp, rồi mới quyết định **có được phép làm hành động đó trên tài nguyên đó hay không**. Khi chọn cách gửi thông tin xác thực, hãy xét đồng thời **bảo mật đường truyền, quyền hạn, hạn dùng, khả năng rò rỉ và cách browser/client thực sự gửi request**.
