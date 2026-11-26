# API có client chủ động gửi bearer token

## Mục tiêu học tập

Sau bài học thuộc chương **Tích hợp ứng dụng**, người học có thể:

- Giải thích mô hình **API nhận bearer access token do client chủ động đưa vào header `Authorization`**, phân biệt nó với credential được trình duyệt tự gửi như session cookie.
- Xác định **điều kiện cụ thể** khiến CSRF truyền thống dựa trên cookie thường không áp dụng cho một endpoint **thực sự bearer-only**, và nhận diện ngoại lệ khi API vẫn nhận cookie, HTTP Basic, client certificate hoặc credential qua proxy/BFF.
- Phân biệt **access token**, **refresh token**, **ID token**, **CSRF token**, **OAuth `state`** và **Authorization Code + PKCE**; không dùng các loại token sai mục đích.
- Thiết kế client **SPA, mobile và CLI** đặt Bearer header, sử dụng HTTPS, kiểm soát nơi lưu token, hết hạn, làm mới, lỗi `401`/`403` và tránh ghi token vào log hoặc URL.
- Cấu hình **Spring Security OAuth2 Resource Server** trên **Servlet** và **Reactive/WebFlux** để xác thực JWT hoặc opaque token, kiểm tra issuer/audience/expiry và phân quyền dựa trên scopes.
- Cấu hình **CORS** cho SPA khác origin dùng Authorization header, cho phép preflight OPTIONS mà không cần access token, không nhầm CORS với authentication/CSRF.
- Chứng minh bằng kiểm thử rằng một nhóm API được miễn CSRF **không chấp nhận credential được browser tự gửi**, không có đường fallback cookie/session ngoài ý muốn.
- Kết hợp **CSP, HSTS, HTTP firewall, cookie/session security, bảo vệ XSS và quan sát log an toàn** trong module `SPRING_SECURITY_HTTP_PROTECTION`.
- Thiết kế regression suite bằng `MockMvc`, `WebTestClient` và kiểm thử HTTP/browser thật; giải thích vì sao mock JWT test chưa chứng minh decoder và security chain được cấu hình đúng.

## 1. Bearer token là gì, và “client chủ động gửi” nghĩa là gì?

**Bearer token** là token mà bên **sở hữu/đưa ra token** có thể dùng để truy cập tài nguyên theo quyền và điều kiện của token. Trong mô hình OAuth 2.0 Bearer Token Usage (RFC 6750), kiểu vận chuyển phổ biến và được ưu tiên là HTTP authorization header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
Accept: application/json
~~~

`Authorization: Bearer ...` thường được **mã client chủ động thêm** vào request: JavaScript của SPA, ứng dụng mobile, CLI, server-to-server client, SDK hoặc reverse proxy có chính sách xác thực riêng. Không phải browser tự lục `localStorage` rồi gắn `Authorization` cho mọi request đến API.

Ví dụ SPA:

~~~javascript
const token = getCurrentAccessToken(); // Hàm của ứng dụng, không phải browser API.

const response = await fetch("/api/orders", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + token,
    Accept: "application/json"
  }
});
~~~

Nếu một website bên ngoài ép browser của người dùng mở hoặc gửi form đến `/api/orders`, nó **không tự biết** `token` đang được giữ trong memory của SPA để điền vào `Authorization: Bearer ...`. Đây là khác biệt căn bản so với **cookie session mà browser tự gửi**.

Tuy nhiên, **“API dùng Bearer” chưa đủ để kết luận “không có CSRF”**. Phải chứng minh API **chỉ** nhận credential client chủ động đặt, và **không có đường xác thực phụ** dựa trên cookie/session/Basic hoặc gateway tự biến cookie thành header. Phần còn lại của bài tập trung vào việc chứng minh điều kiện đó bằng cấu hình và kiểm thử.

### 1.1. Ba request nhìn gần giống nhau nhưng mô hình khác nhau

**A. Session cookie tự gửi:**

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

displayName=Changed
~~~

Browser có thể tự gắn cookie dù attacker không biết session ID. Nếu endpoint chấp nhận cookie session mà thiếu anti-CSRF, một request được kích hoạt từ nơi không tin cậy có thể gây thay đổi.

**B. JWT trong cookie HttpOnly:**

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Cookie: ACCESS_TOKEN=eyJ...
Content-Type: application/x-www-form-urlencoded

displayName=Changed
~~~

JWT có chữ ký và backend không dùng `HttpSession` **không loại CSRF**: JWT vẫn được browser tự gửi trong cookie.

**C. Access token chỉ có trong Bearer header được client tự đặt:**

~~~http
POST /api/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...
Content-Type: application/json

{"displayName":"Alice"}
~~~

Nếu endpoint thực sự **chỉ** chấp nhận header này, một form HTML cross-site thông thường không biết bí mật để gửi header tương đương. Nguy cơ **CSRF cổ điển dựa trên ambient credential** giảm đáng kể. Nhưng kẻ tấn công có token bị đánh cắp vẫn có thể gọi API **trực tiếp**, không cần CSRF.

### 1.2. Sơ đồ luồng client chủ động đặt token

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as SPA / Mobile / CLI
    participant AS as Authorization Server
    participant API as Spring Resource Server
    participant D as Service / Database

    U->>B: Thao tác hoặc đăng nhập theo flow phù hợp
    B->>AS: Nhận access token qua flow được cấp phép
    AS-->>B: Access token với audience, scope, expiry
    B->>API: POST /api/orders + Authorization Bearer token
    API->>API: Kiểm chứng token và phân quyền
    alt Token hợp lệ, đủ scope
        API->>D: Kiểm tra quyền nghiệp vụ và cập nhật
        D-->>API: Kết quả
        API-->>B: 2xx + dữ liệu phù hợp
    else Không có/không hợp lệ/hết hạn
        API-->>B: 401 và WWW-Authenticate khi phù hợp
    else Đã xác thực nhưng không đủ quyền
        API-->>B: 403 và chi tiết lỗi an toàn
    end
~~~

Sơ đồ tách **Authorization Server** (cấp token) khỏi **Resource Server** (API kiểm tra token). Spring Security `oauth2ResourceServer()` bảo vệ API; nó **không tự triển khai một Authorization Server** để phát token.

## 2. Tách năm khái niệm credential và bằng chứng khác nhau

| Khái niệm | Mục đích | Nơi điển hình sử dụng | Không nên dùng thay |
|---|---|---|---|
| **Access token** | Cho phép client gọi tài nguyên theo quyền, audience và thời hạn | `Authorization: Bearer ...` | Không mặc nhiên là ID token hay CSRF token |
| **Refresh token** | Xin access token mới theo chính sách của Authorization Server | Token endpoint, có bảo vệ lưu trữ/rotation | Không nên gửi như access token tới mọi resource API |
| **ID token (OIDC)** | Chuyển thông tin về sự kiện xác thực/danh tính cho OIDC client | OIDC client xử lý login | Không dùng làm access token API trừ thiết kế giao thức riêng chính thức |
| **CSRF token** | Bằng chứng chống request giả mạo trong một luồng dùng credential tự gửi | Form parameter, custom header được server so | Không phải credential xác thực user |
| **OAuth `state`/PKCE** | Chống các lớp tấn công trong authorization redirect/code flow | Client và Authorization Server trong OAuth | Không thay token CSRF cho các POST nghiệp vụ dùng cookie |

Một API có thể dùng Bearer access token cho `/api/**` và **vẫn có** endpoint `/auth/refresh` dùng refresh cookie. Hai endpoint khi đó có **mô hình CSRF khác nhau**; không được coi toàn bộ hệ thống là một kiểu bearer-only.

### 2.1. JWT và opaque token là hai định dạng triển khai

**JWT** là một định dạng token chứa claims, thường được Resource Server xác minh chữ ký, thuật toán được phép và thông tin chuẩn như `iss`, `aud`, `exp`, `nbf`. Token có thể nhìn như ba phần Base64URL cách nhau bởi dấu chấm khi dùng JWT/JWS compact serialization. **JWT không tự có nghĩa là đã an toàn**; cần kiểm chứng toàn bộ claim và khóa tin cậy.

**Opaque token** là chuỗi không tự biểu diễn claims theo cách Resource Server đọc trực tiếp. API thường hỏi **introspection endpoint** được Authorization Server cung cấp để biết token có active và scope nào, cùng chính sách caching/revocation thích hợp.

Cả JWT lẫn opaque token đều có thể được gửi qua **Bearer header**. Nguy cơ CSRF của **cách vận chuyển** thường giống nhau nếu client là bên tự đặt header và server không chấp nhận credential tự gửi khác.

### 2.2. “Stateless” không phải chứng nhận bearer-only

Một security chain dùng `SessionCreationPolicy.STATELESS` thường không tạo/sử dụng `HttpSession` để lưu `SecurityContext` cho các request API. Đây là lớp kiến trúc quan trọng, nhưng **không chứng minh**:

- Custom authentication filter không đọc JWT từ cookie;
- API gateway không nhận session cookie rồi gắn `Authorization` vào upstream;
- Một security chain khác không được match trước API chain;
- HTTP Basic/Negotiate không được browser tự gửi;
- Một refresh/logout endpoint cookie-based không nằm trong `/api/**` đã miễn CSRF.

Phải kiểm tra **toàn bộ đường xác thực thực tế**, không chỉ một thuộc tính session policy.

## 3. Điều kiện để cân nhắc miễn CSRF truyền thống cho API

Một nhóm endpoint thường có thể được xem là **bearer-only** khi thỏa đồng thời các điều kiện:

1. **Resource Server chỉ xác thực bằng Bearer header** do client chủ động thêm, không nhận `JSESSIONID`, JWT cookie, Basic auth, mTLS auto-auth hoặc bất kỳ cơ chế ambient credential nào trên cùng route.
2. **Không có authentication fallback**: request thiếu `Authorization` không được xác thực dù browser vẫn có cookie của ứng dụng khác cùng host hoặc SSO proxy.
3. **Route và security chain tách rõ** khỏi browser/BFF session endpoints, form login, logout, refresh token cookie và các callback giao thức.
4. **Client ngoài origin hợp lệ không tự có token**. Website attacker không thể chỉ tạo HTML form hoặc điều hướng và có được header chứa access token của người dùng.
5. **Chứng minh bằng test**: cookie-only POST bị từ chối; Bearer token hợp lệ và đủ scope mới được chấp nhận; token thiếu/sai/hết hạn không được chấp nhận.
6. **Không bỏ các lớp bảo vệ khác**: XSS, token storage, scope/audience/issuer, resource authorization, HTTPS, CORS và logging.

~~~mermaid
flowchart TD
    A[Endpoint có thao tác ghi?] -->|Không| B[Kiểm tra authentication, authorization, GET chỉ đọc]
    A -->|Có| C[Liệt kê tất cả cơ chế xác thực]
    C --> D{Browser có tự gửi ít nhất một credential được chấp nhận?}
    D -->|Có| E[Đánh giá và áp CSRF cho đường browser này]
    D -->|Không| F{Chỉ Bearer do client chủ động gắn?}
    F -->|Đã chứng minh| G[Có thể miễn CSRF theo route và tiếp tục bảo vệ token]
    F -->|Chưa rõ| H[Giữ policy phòng vệ, điều tra fallback và test]
    E --> I[Giữ CSRF/Origin phù hợp và test thao tác ghi]
    G --> J[Test cookie-only thất bại, Bearer đúng thành công]
~~~

**Kết luận có điều kiện:** `csrf.disable()` có thể là quyết định đúng trong một **resource-server chain thuần Bearer**. Nhưng không nên đưa nó vào ví dụ cấu hình session web rồi áp cho mọi route chỉ vì client là SPA hoặc API dùng JWT.

### 3.1. Lưu ý không phải mọi Authorization header đều giống nhau

`Authorization: Basic ...` có thể được **browser ghi nhớ và tự gắn** trong một số điều kiện HTTP authentication. Client certificate cũng có thể được browser tự trình tại TLS handshake. Vì vậy câu “có Authorization thì không CSRF” **sai**.

Điểm cần chứng minh là **Bearer token được client tự lấy và chủ động đặt**, không phải **bất kỳ** header Authorization hoặc credential nào mà user agent có thể tự gửi.

### 3.2. API hybrid và BFF

~~~text
Browser -- Cookie BFF_SESSION --> BFF -- Authorization Bearer --> Resource API
~~~

Resource API phía sau BFF có thể thật sự Bearer-only. Nhưng điểm vào **browser → BFF** vẫn có ambient credential, phải đánh giá CSRF ở BFF. Nếu backend API cũng chấp nhận cookie fallback, cần bảo vệ đường đó hoặc loại bỏ fallback.

Một API khác nhận access token từ Bearer header nhưng refresh token từ cookie có thể cần **CSRF ở refresh endpoint**, dù các endpoint nghiệp vụ không dựa vào cookie.

## 4. Luồng nhận access token: OAuth2/OIDC cần dùng đúng chỗ

### 4.1. SPA/browser public client: Authorization Code với PKCE

Đối với ứng dụng SPA tương tác với Authorization Server, một luồng OAuth2/OIDC hiện đại thường dùng **Authorization Code flow + PKCE**:

1. SPA tạo code verifier ngẫu nhiên và code challenge tương ứng; tạo `state` để ràng buộc authorization response với request ban đầu.
2. Browser điều hướng người dùng tới Authorization Server; đăng nhập diễn ra tại môi trường được định nghĩa bởi provider.
3. Authorization Server redirect về redirect URI đã đăng ký với authorization code và `state`.
4. Client xác minh `state` và đổi code lấy token bằng code verifier phù hợp.
5. SPA giữ access token với vòng đời ngắn theo lựa chọn kiến trúc, rồi chủ động gắn Bearer header khi gọi Resource API.
6. Khi token hết hạn, client đi qua token refresh hoặc authorization flow phù hợp **với loại client và policy provider**, không tự suy đoán mọi browser đều có refresh token.

**Không tự viết một giao thức đăng nhập riêng** chỉ vì đã biết cú pháp Bearer. Dùng thư viện OAuth/OIDC phù hợp và cấu hình redirect URI, PKCE, state, token validation, scopes và trusted origins đúng.

### 4.2. Native mobile client

Mobile app dùng **system browser/external user-agent** và OAuth2 Authorization Code + PKCE theo thông lệ, nhận token qua redirect đã đăng ký rồi lưu trong cơ chế an toàn của nền tảng khi phù hợp (ví dụ Keychain/Keystore hoặc SDK được hỗ trợ).

Mobile client thường tự đặt `Authorization: Bearer` và không phụ thuộc browser cookie session cho Resource API. Tuy vậy vẫn phải đánh giá:

- Lộ token qua log/debug build, backup, clipboard, IPC hoặc thiết bị bị xâm nhập;
- Deep-link/app-link redirect URI spoofing hoặc sai kiểm chứng `state`/PKCE;
- TLS verification, thời hạn token, refresh rotation và thu hồi;
- Quyền theo từng tài nguyên ở server, không tin device/client tự khai.

### 4.3. CLI và server-to-server

CLI có thể dùng device authorization flow, Authorization Code + PKCE hoặc cơ chế provider hỗ trợ. Server-to-server có thể dùng **client credentials grant** nếu đúng mô hình quyền ứng dụng, không phải người dùng cuối.

Ví dụ lệnh gọi resource API:

~~~bash
# Giá trị token dùng trong biến môi trường của quy trình thử nghiệm.
curl --fail-with-body \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  https://api.example.com/api/orders
~~~

Không chép access token thật vào một lệnh shell được chia sẻ, commit vào repository hay đưa vào query parameter. Biến môi trường cũng cần chính sách bảo vệ phù hợp (process inspection, CI secret handling, logging).

### 4.4. Không nhầm access token với OIDC ID token

OIDC ID token thường hướng tới **client** để chứng minh sự kiện authentication, trong khi Resource Server cần **access token được phát cho resource đó**. Dùng ID token như API Bearer access token có thể gây sai audience và mô hình quyền.

**Yêu cầu bắt buộc:** API xác minh `aud` phù hợp với resource server, issuer tin cậy, chữ ký/active status, expiry và scope/quyền; không chỉ decode payload rồi tin claims.

## 5. Bearer token trên HTTP: yêu cầu an toàn tối thiểu

### 5.1. Dùng HTTPS và Authorization header

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"itemId":"book-1","quantity":2}
~~~

Sử dụng HTTPS với TLS certificate verification bình thường trên toàn đường client→API. Tránh gửi bearer token qua `http://` trong production; một token bị lộ trên đường truyền có thể bị dùng trực tiếp.

Không gửi token trong URL:

~~~http
GET /api/orders?access_token=eyJ... HTTP/1.1
~~~

Query string dễ lộ qua browser history, proxy logs, analytics, tracing và liên kết; Spring Security Resource Server thông thường nên nhận token từ header theo chính sách nhất quán. Hạn chế các cơ chế token transport fallback không cần thiết.

### 5.2. Khi token bị lộ, attacker không cần CSRF

Bearer token thường là credential dạng **proof of possession by presentation**: ai trình đúng chuỗi token hợp lệ có thể được xem là client có quyền trong phạm vi token. Vì vậy nguy cơ chủ yếu khi token bị lộ là **token theft/replay**, không nhất thiết CSRF.

Có thể giảm rủi ro bằng:

- Access token **short-lived**, scopes tối thiểu, audience đúng API;
- HTTPS, không log token, không đưa token vào URL, tránh rò qua error/reporting;
- Quy trình thu hồi/rotation phù hợp với opaque/JWT và provider;
- XSS hardening cho browser, hạn chế script không tin cậy;
- Với yêu cầu cao, cân nhắc **sender-constrained tokens** như DPoP hoặc mTLS-bound access tokens theo hỗ trợ end-to-end; không tự tuyên bố mọi bearer JWT được bảo vệ replay.

### 5.3. HTTP 401 và 403: đừng trộn CSRF với permission

Theo mô hình resource-server:

| Tình trạng | Kết quả API thường gặp | Ý nghĩa |
|---|---|---|
| Không có Bearer header trên route bắt buộc | `401 Unauthorized` | Chưa có credential hợp lệ |
| Header Bearer malformed | `401` | Credential không phù hợp |
| JWT signature/issuer/expiry không hợp lệ | `401` | Token không được chấp nhận |
| Opaque token không active | `401` | Token bị từ chối bởi introspection |
| Token hợp lệ nhưng thiếu scope/authority cần thiết | `403 Forbidden` | Đã xác thực nhưng không đủ quyền |
| Token hợp lệ và đủ scope nhưng resource thuộc user khác | `403`/`404` theo policy | Kiểm tra quyền theo tài nguyên phải chặn |
| Browser báo CORS error | Không nhất thiết có status JS đọc được | Kiểm tra preflight/response CORS và network |
| Cookie-web POST thiếu CSRF token | Thường `403` | CSRF filter chặn request dùng ambient credential |

Spring Security có thể trả header `WWW-Authenticate: Bearer ...` trên lỗi xác thực/quyền theo RFC 6750. Cần ghi nhận status/header theo policy mà **không đưa token thật hoặc dữ liệu nhạy cảm vào error body**.

## 6. Spring Security Servlet: một Resource Server thật sự Bearer-only

### 6.1. Phạm vi và dependency của ví dụ

Ví dụ sau dành cho **Spring MVC/Servlet** dùng Spring Security OAuth2 Resource Server để xác minh access token JWT trên nhóm `/api/**`. Một dự án Spring Boot điển hình có các thành phần tương ứng:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-oauth2-resource-server
spring-boot-starter-test              (test)
spring-security-test                  (test)
~~~

**Giả định quan trọng:** Access token do Authorization Server tin cậy phát và được client chủ động đặt vào header `Authorization`. API không tự đọc token từ cookie, không có form login/Basic trên nhóm API và không dựa vào HttpSession để khôi phục authentication.

Trong kiến trúc có thêm web quản trị dùng cookie session, nên **tách các security chains**. Không đặt cùng một ngoại lệ CSRF cho mọi endpoint chỉ vì phần lớn API dùng Bearer.

### 6.2. Chuỗi Resource Server tách biệt

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletResourceServerSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain bearerOnlyApi(HttpSecurity http)
            throws Exception {

        return http
            // Chain này chỉ áp dụng cho URL đã được đánh giá bearer-only.
            .securityMatcher("/api/**")

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().authenticated()
            )

            // Resource Server không dùng session để duy trì authentication.
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            // Không bật các cơ chế browser-auth phụ trong API chain.
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)

            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))

            // Chỉ hợp lệ sau khi xác minh không có ambient credential
            // hoặc endpoint dùng cookie trong /api/**.
            .csrf(AbstractHttpConfigurer::disable)

            // Chỉ cần khi SPA khác origin gọi API.
            .cors(Customizer.withDefaults())

            .build();
    }
}
~~~

**Giải thích từng ranh giới:**

- `securityMatcher("/api/**")` xác định **request nào chọn chain**. Không nhầm nó với `requestMatchers(...)` chỉ dùng để phân quyền **sau khi đã chọn chain**.
- `SessionCreationPolicy.STATELESS` có nghĩa Resource Server không dùng `HttpSession` để lưu/khôi phục `SecurityContext` qua các request. Nhưng phải kiểm tra thêm **custom filters**, proxy SSO, cookie token resolver hoặc các chain khác.
- `formLogin(...disable)` và `httpBasic(...disable)` tránh các cơ chế browser-managed authentication không chủ đích ở chain này.
- `oauth2ResourceServer(...jwt)` kích hoạt xử lý Bearer JWT, dựa trên `JwtDecoder` được cấu hình.
- `SCOPE_orders:write`/`SCOPE_reports:read` là ví dụ authority tương ứng scopes qua JWT authentication converter mặc định. Nếu issuer ghi scopes theo định dạng/claim riêng, cần map `GrantedAuthority` phù hợp thay vì giả định mọi token có claim `scope` chuẩn.
- `csrf(...disable)` là một **quyết định theo threat model của chain**, không phải lời khuyên tắt CSRF trên web-session application.
- `cors(...)` không làm token trở nên hợp lệ; nó chỉ xử lý browser cross-origin request/response. Với mobile/CLI thuần túy, CORS **không phải điều kiện server-side cho HTTP client**.

Nếu dự án thực tế có `/api/auth/refresh` dùng refresh cookie, `/api/logout` dùng session cookie hoặc API chấp nhận JWT-cookie fallback, **không được áp chain trên toàn `/api/**`**. Hãy tách matcher chặt hơn và bảo vệ endpoint cookie bằng anti-CSRF tương ứng hoặc thay đổi hợp đồng kiến trúc.

### 6.3. Khi ứng dụng cũng có trang web dùng session cookie

Một cấu hình **minh họa** chain web thứ hai:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

// Thêm vào class cấu hình nếu hệ thống có web session thực sự.
@Bean
@Order(2)
SecurityFilterChain browserPages(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/css/**", "/login").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

Đoạn code này **thuộc cấu hình thay thế có hai chains**, không phải file độc lập hoàn chỉnh. Route `/api/**` được chain `@Order(1)` xử lý trước; các route web còn lại sử dụng cookie session và **giữ CSRF**.

**Cần test thứ tự và phạm vi:** Nếu một endpoint `/api/profile` vô tình được chuyển sang chain web hoặc route mới được tạo dưới `/auth/**`, chính sách Bearer-only/CSRF có thể khác dự kiến. Không dựa vào tên file Java hay class config để suy ra matcher chạy ở production.

### 6.4. Cấu hình JWT issuer tin cậy

Spring Boot có thể cấu hình Resource Server JWT qua issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/training
~~~

`issuer-uri` là URI **minh họa**, phải thay bằng issuer thực sự do Authorization Server quản lý. Khi Resource Server được khởi tạo và cấu hình decoder phù hợp, nó có thể dùng metadata/JWKs từ issuer để xác minh chữ ký và các điều kiện token tiêu chuẩn.

**Không chỉ kiểm chữ ký**. Một Resource Server sản xuất cần xác minh:

| Kiểm tra | Ý nghĩa |
|---|---|
| **Signature** | Token thực sự được ký bằng khóa/thuật toán được tin cậy |
| `iss` | Token đến từ đúng issuer tin cậy |
| `aud` | Token được cấp để dùng cho **resource API này** |
| `exp`, `nbf` | Token chưa hết hạn và đủ điều kiện thời gian |
| `scope`/`scp` | Quyền được cấp cho hành động API |
| Quyền trên tài nguyên | User hoặc client có được thao tác với bản ghi cụ thể không |
| Token type/usage | Không nhận ID token hoặc token dành cho resource khác chỉ vì decode thành công |
| Key rotation/revocation | Chấp nhận khóa mới theo JWK policy và chiến lược thu hồi thực tế |

Mặc định các phiên bản Spring Security có thể tự kiểm chữ ký và một số claims như issuer/timestamps khi cấu hình `issuer-uri`, nhưng **audience của ứng dụng phải được cấu hình hoặc thêm validator rõ ràng theo phiên bản đang dùng**. Đừng ngầm coi mọi decoder đã kiểm tra audience đúng tài nguyên.

### 6.5. Ví dụ xác minh JWT audience bằng validator

Đây là một cách **minh họa kỹ thuật** dùng trusted JWK Set URI và validator rõ ràng cho issuer/audience. URI phải được cấu hình bằng metadata đáng tin cậy từ Authorization Server và quản lý theo từng môi trường.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfig {

    private static final String ISSUER =
        "https://auth.example.com/realms/training";

    private static final String JWK_SET_URI =
        "https://auth.example.com/realms/training/protocol/openid-connect/certs";

    private static final String EXPECTED_AUDIENCE =
        "orders-resource-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWK_SET_URI)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(EXPECTED_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token không dành cho resource API này",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

**Lưu ý:**

- Đây là một **lựa chọn thay thế cấu hình decoder tự động bằng properties**: khi đã tạo bean `JwtDecoder` tùy biến, cần hiểu nó thay cách auto-config lựa chọn decoder. Không áp dụng đồng thời nhiều cấu hình cạnh tranh rồi đoán bean nào được dùng.
- URI/issuer/audience ở đây là **dữ liệu ví dụ**; không dùng chúng trong production. Nên đưa các giá trị này vào cấu hình môi trường được kiểm soát, không viết cứng trong class thật.
- Bộ validator `JwtValidators.createDefaultWithIssuer(...)` kết hợp các điều kiện mặc định theo phiên bản cùng kiểm tra issuer; audience validator bổ sung kiểm tra resource API.
- Chỉ bật thuật toán ký đáng tin, khóa JWKS từ issuer tin cậy, chính sách clock skew và key rotation phù hợp. Không chấp nhận JWT có thuật toán `none` hay dùng thông tin khóa do request attacker tự quyết định.
- Với nhiều issuer hợp lệ, cần cơ chế multi-tenant trusted issuer rõ ràng, không lấy mọi `iss` trong token làm một URL để truy cập tùy tiện (nguy cơ SSRF/trust confusion).

### 6.6. Phân quyền scope và quyền trên từng tài nguyên

Khi Resource Server đọc `scope` chứa `orders:write`, mặc định JWT authentication converter thường map thành authority `SCOPE_orders:write`. Cấu hình `.hasAuthority("SCOPE_orders:write")` kiểm tra **quyền trên endpoint**.

Nhưng một token có `orders:write` **không mặc nhiên được chỉnh sửa mọi đơn hàng của mọi user**.

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
class OrderApi {

    private final OrderService orders;

    OrderApi(OrderService orders) {
        this.orders = orders;
    }

    record OrderUpdate(String note) {}

    @PatchMapping("/api/orders/{orderId}")
    ResponseEntity<Void> update(
            @PathVariable String orderId,
            @RequestBody OrderUpdate body,
            org.springframework.security.core.Authentication authentication) {

        // Phải xác định subject/client theo claims đáng tin
        // và kiểm tra ownership/tenant trong service.
        orders.updateIfAuthorized(
            authentication.getName(), orderId, body.note());

        return ResponseEntity.noContent().build();
    }
}
~~~

`OrderService` là **service của ứng dụng cần được triển khai**, không phải class Spring Security mặc định. Cần kiểm tra quyền trên resource, tenant isolation, input validation, audit và transaction; có thể dùng method security nhưng không chỉ tin route scope.

### 6.7. Opaque token introspection là phương án khác JWT

Nếu Authorization Server phát **opaque access tokens** và Resource Server phải introspect chúng, một cấu hình Spring Boot điển hình có thể như sau:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Và trong Resource Server chain thay cấu hình JWT bằng:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

**Hai cấu hình JWT và opaque token là các phương án cho những hợp đồng token khác nhau**, không đặt cùng hai cấu hình và tưởng Spring sẽ tự đọc mọi định dạng theo ý muốn. `Introspection client-secret` phải được lấy từ cơ chế secret management thật; biểu thức YAML ở đây là **placeholder cho cấu hình môi trường**, không phải secret thực.

Với introspection, phải xác minh response `active`, audience/resource, scopes, issuer/authorization server trust và khả năng chịu lỗi/caching khi token bị thu hồi. Việc introspection request từ Resource Server đến Authorization Server là **server-to-server**, không phải CORS browser.

## 7. CORS cho SPA khác origin khi chỉ dùng Bearer header

### 7.1. CORS vẫn cần khi frontend gọi API khác origin

Giả sử SPA ở `https://spa.example.com`, API ở `https://api.example.com`. SPA gửi:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "omit",
  headers: {
    Authorization: "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ itemId: "book-1" })
});
~~~

`credentials: "omit"` nói browser không tự thêm cookie/HTTP credentials theo credentials mode của fetch cho request này; **header `Authorization` mà client đã tự đặt vẫn được gửi nếu được browser/CORS cho phép**. Đây là lựa chọn minh họa rõ ràng cho API chỉ dùng Bearer.

Do request có header `Authorization` không thuộc CORS-safelisted request headers, browser thường gửi **preflight OPTIONS**:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://spa.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Preflight **không chứa access token** và **không cần authentication**. API phải cho phép origin/method/header hợp lệ trước khi browser gửi actual POST.

### 7.2. Servlet CorsConfigurationSource không dùng cookie

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletBearerCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://spa.example.com"));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));

        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type"));

        // Không cần credentialed CORS cookie cho bearer-only API.
        cors.setAllowCredentials(false);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Phạm vi:** `setAllowCredentials(false)` không hủy/chặn mọi `Authorization: Bearer` do JavaScript chủ động đặt. Mục tiêu là **không cấp quyền CORS cho browser tự dùng cookie/session**; Resource Server vẫn phải kiểm chứng Bearer token được gửi. Với browser/proxy phức tạp, cần test actual request để xác minh.

- Không phản chiếu mọi `Origin` hoặc dùng allowlist `allowedOriginPatterns("*")` chỉ để bỏ lỗi frontend.
- Chỉ allowlist origin frontend thật sự tin cậy và các phương thức/header cần dùng.
- Không xem **CORS allowlist** là authentication/authorization: một client non-browser hoặc token bị đánh cắp vẫn có thể gọi trực tiếp Resource API.
- Nếu SPA có thêm login/logout/refresh bằng cookie khác site, **phải tách chính sách cho các endpoint đó**, không mặc nhiên dùng policy bearer-only.
- Với frontend same-origin qua reverse proxy, thường không cần CORS cho fetch cùng origin; vẫn cần bảo vệ access token và authorization.

### 7.3. Preflight không có Bearer không nên trả 401

Spring Security CORS integration cần xử lý CORS **trước khi** chain yêu cầu Bearer authentication. Trong ví dụ `HttpSecurity` ở mục 6.2 đã có:

~~~java
.cors(Customizer.withDefaults())
~~~

và `CorsConfigurationSource` phù hợp.

Một preflight hợp lệ sẽ nhận chính sách CORS, ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://spa.example.com
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Access-Control-Max-Age: 1800
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Không bắt buộc `Access-Control-Allow-Credentials: true` vì ví dụ này **không dựa vào browser cookie credentials**. Nếu preflight bị `401`, kiểm tra security/CORS filter order và CORS source path trước khi thay đổi authorization rules. Đừng cho mọi `POST` permitAll để “sửa” OPTIONS.

### 7.4. Actual request vẫn chịu token và scope

Sau preflight, browser gửi request thực:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://spa.example.com
Authorization: Bearer ACCESS_TOKEN_VALID
Content-Type: application/json

{"itemId":"book-1"}
~~~

Resource Server phải:

1. Xác minh access token hợp lệ với issuer, audience, expiry, chữ ký/active status.
2. Kiểm tra authority/scope cho POST.
3. Kiểm tra permission trên resource và tenant theo nghiệp vụ.
4. Xác thực/validate payload và thực hiện transaction.
5. Trả status/bodies cần thiết cùng CORS headers cho trusted SPA origin.

**CORS thành công không phải bằng chứng Bearer token hợp lệ.** Nếu actual request không mang token, nó phải bị từ chối theo policy kể cả browser đã vượt preflight.

### 7.5. Khi SPA cùng origin nhưng vẫn muốn tách cookie auth

Cùng origin không bắt buộc browser phải gửi cookie cho Resource Server nếu SPA gọi API theo mô hình Bearer-only. Client có thể đặt `credentials:"omit"`, nhưng **server vẫn phải từ chối cookie-only request** để xác nhận không có session fallback.

Nếu SPA và web form dùng chung hostname, thứ tự security chain, cookie scope và login/logout routes cần được kiểm tra kỹ; đừng chỉ dựa vào frontend đã chọn omit để khẳng định API không bao giờ nhận cookie.

## 8. Client SPA: quản lý access token và gọi API

### 8.1. Token trong memory là một lựa chọn, không phải “miễn nhiễm XSS”

Ví dụ client đơn giản:

~~~javascript
// Token chỉ được cấp qua một luồng OAuth/OIDC đã được thiết kế và xác minh.
// Không tạo token phía frontend.
let accessToken = null;

function setAccessToken(token) {
  if (typeof token !== "string" || !token.trim()) {
    throw new Error("Access token không hợp lệ");
  }
  accessToken = token;
}

function clearAccessToken() {
  accessToken = null;
}

async function bearerFetch(path, options = {}) {
  if (typeof path !== "string" || !path.startsWith("/api/")) {
    throw new Error("Resource path phải thuộc /api/");
  }

  const url = new URL(path, "https://api.example.com");
  if (url.origin !== "https://api.example.com" ||
      !url.pathname.startsWith("/api/")) {
    throw new Error("Không được gửi token tới origin khác");
  }

  if (!accessToken) {
    throw new Error("Chưa có access token");
  }

  const headers = new Headers(options.headers ?? {});
  headers.set("Authorization", "Bearer " + accessToken);

  return fetch(url.toString(), {
    ...options,
    headers,
    credentials: "omit",
    mode: "cors",
    redirect: "error"
  });
}
~~~

**Mã chỉ minh họa vận chuyển token**. Trong ứng dụng production cần tích hợp thư viện OAuth2/OIDC cho token lifecycle, token refresh/rotation, lỗi login/logout và network; không tự phát token, không nhận token trực tiếp từ query string không đáng tin.

Những điểm an toàn:

- Chỉ gắn access token vào **đúng API origin**; không forward Bearer header theo redirect tới host khác.
- Không lưu token trong URL, analytics, console log, error-reporting payload.
- Không đặt header Authorization theo một URL do attacker tùy ý cung cấp.
- `redirect:"error"` giúp phát hiện/không tự theo redirect bất ngờ ở ví dụ này; nếu API có redirect chính đáng, thiết kế riêng và kiểm thử không rò token.
- `credentials:"omit"` hạn chế browser thêm cookie không cần thiết, nhưng **không chứng minh backend từ chối cookie fallback**.
- Script XSS cùng origin có thể đọc hoặc sử dụng token còn trong memory bằng cách gọi các code paths hợp lệ; memory-only không tự chống XSS.

### 8.2. Ví dụ API POST JSON

~~~javascript
async function createOrder(itemId) {
  const response = await bearerFetch("/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ itemId })
  });

  if (response.status === 401) {
    throw new Error("Access token thiếu, hết hạn hoặc bị từ chối");
  }

  if (response.status === 403) {
    throw new Error("Access token không đủ quyền cho hành động này");
  }

  if (!response.ok) {
    throw new Error("Tạo đơn không thành công: " + response.status);
  }

  return response.json();
}
~~~

Endpoint ở ví dụ cấu hình `/api/orders` cần quyền `SCOPE_orders:write`. Chúng ta **không gửi CSRF token** trong đường bearer-only đã được chứng minh; nhưng các kiểm tra access token, input, authorization và idempotency vẫn bắt buộc.

### 8.3. Không tự động retry POST khi token hết hạn

Một strategy refresh an toàn cần xét:

- Token sắp hết hạn và client có cơ chế refresh phù hợp;
- Có một lần retry có kiểm soát cho request **an toàn/idempotent** khi hợp lý;
- Với POST giao dịch, tránh retry mù quáng có thể tạo **đơn hàng trùng**, thanh toán lặp hoặc tác động kép;
- Sử dụng idempotency key **nếu nghiệp vụ yêu cầu**, do backend triển khai; key này **không phải CSRF token**;
- Khi refresh token nằm trong cookie của browser, **đường refresh có thể cần anti-CSRF** riêng.

Không bắt HTTP client tự lặp lại credential sau mọi `401`, đặc biệt khi token có thể đã bị thu hồi hoặc tài khoản bị khóa.

### 8.4. Nơi lưu token: đánh đổi có căn cứ

| Nơi lưu | Browser có tự gửi như cookie? | Điểm mạnh tương đối | Rủi ro cần quản lý |
|---|---|---|---|
| **Memory JavaScript** | Không | Hạn chế lưu lâu trên thiết bị/trang | XSS chạy tại origin vẫn có thể sử dụng token; mất token khi reload |
| `sessionStorage` | Không | Vòng đời thường gắn với tab/session browsing | Script cùng origin có thể đọc; không tự chống XSS |
| `localStorage` | Không | Dữ liệu tồn tại qua reload/browser restart | XSS và script dependency có thể đọc, token bị giữ lâu |
| `IndexedDB` | Không | Phù hợp một số lưu trữ có cấu trúc | Script có quyền cùng origin có thể truy cập |
| **Cookie HttpOnly chứa access token** | **Có** | Script khó đọc trực tiếp cookie | Trở lại mô hình CSRF/cookie auth; không tự tương đương Bearer-only |
| **BFF giữ access token phía server** | Browser dùng cookie BFF | Giảm lộ access token trực tiếp cho JS | Cần CSRF ở BFF, bảo vệ session và server-side token |
| **Mobile Keychain/Keystore** | Không phải browser cookie tự gửi | Cơ chế lưu an toàn theo nền tảng | Thiết bị compromise, backup, debugging, access policy |

Không có một vị trí lưu duy nhất tốt nhất cho mọi ứng dụng. Hãy chọn theo threat model, yêu cầu UX, loại client và hỗ trợ của Authorization Server.

### 8.5. CORS không bảo vệ token đã bị đánh cắp

Một kẻ tấn công có access token thật có thể gửi:

~~~bash
curl -H "Authorization: Bearer $STOLEN_TEST_TOKEN" \
  https://api.example.com/api/orders
~~~

HTTP client non-browser **không bị CORS của browser chặn**. Vì vậy CORS là chính sách bảo vệ dữ liệu cho script trong browser, **không phải cơ chế chặn người có token không được phép**. Bảo mật token và kiểm tra scope/authorization vẫn là lớp quyết định.

## 9. Spring Security Reactive/WebFlux: Resource Server Bearer-only

### 9.1. Từ Servlet sang Reactive: mô hình đe dọa không đổi

WebFlux xử lý request qua **`SecurityWebFilterChain`** và reactive pipelines thay vì Servlet filters, nhưng browser vẫn không tự lấy access token trong memory rồi thêm `Authorization: Bearer ...`.

| Vai trò | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Kiểm tra Bearer | OAuth2 Resource Server filter | OAuth2 Resource Server WebFilter |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Token opaque | Opaque Token Introspector | Reactive Opaque Token Introspector |
| CORS source | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` | `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| Stateful session | `HttpSession` | `WebSession` |
| Kiểm thử | `MockMvc` | `WebTestClient` |

**Quy tắc quan trọng:** Không dùng API `HttpSecurity`/`HttpSessionCsrfTokenRepository` trong WebFlux; không chuyển `ServerHttpSecurity`/`WebSession` sang Servlet một cách máy móc.

### 9.2. Reactive security chain chỉ nhận Bearer

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveResourceServerSecurity {

    @Bean
    SecurityWebFilterChain bearerApi(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))

            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyExchange().authenticated()
            )

            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())

            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)

            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))

            // Chỉ đúng cho Bearer-only API, không chứa cookie auth.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .cors(cors -> cors.configurationSource(corsSource))

            .build();
    }
}
~~~

**Giải thích:**

- `securityMatcher` giới hạn chain tới `/api/**`. Các endpoint web dùng cookie/session cần một **chain khác** có CSRF được bật.
- `NoOpServerSecurityContextRepository` ngăn việc lưu `SecurityContext` qua WebSession trong chuỗi này; access token vẫn được xác minh trên từng request.
- `formLogin`/`httpBasic` bị tắt để tránh cơ chế browser auth ngoài thiết kế.
- `oauth2ResourceServer(...jwt)` dùng `ReactiveJwtDecoder` có cấu hình tin cậy.
- `csrf(...disable)` chỉ được dùng vì **giả định Bearer-only đã được xác minh**, không phải vì WebFlux là reactive hay API trả JSON.
- `cors(...)` chỉ cần cho SPA cross-origin; nó xử lý preflight trước bước yêu cầu authentication ở chuỗi được tích hợp phù hợp.

**Yêu cầu khi triển khai:** Với ứng dụng nhiều `SecurityWebFilterChain`, cần đặt `@Order` thích hợp và kiểm thử đường request thực tế. Nếu default/fallback chain chưa được định nghĩa, các route ngoài matcher có thể không có policy mong muốn. Không phơi ra endpoint không được bảo vệ chỉ vì chain mẫu giới hạn `/api/**`.

### 9.3. Reactive CORS source

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveBearerCorsConfig {

    @Bean
    CorsConfigurationSource reactiveCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://spa.example.com"));
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type"));

        // Client cố ý dùng credentials: omit; không cần browser-cookie CORS.
        cors.setAllowCredentials(false);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return source;
    }
}
~~~

**Không** import nhầm `org.springframework.web.cors.UrlBasedCorsConfigurationSource` của Servlet. Cần kiểm tra CORS headers trên OPTIONS và actual request; không chỉ dựa vào việc browser JavaScript có nhận một lỗi mạng chung chung hay không.

### 9.4. Cấu hình JWT Reactive

Với Spring Boot Resource Server WebFlux, có thể dùng properties issuer URI tương đương:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/training
~~~

Resource Server Reactive cần kiểm chứng chữ ký/JWK, issuer, expiry, audience và scope theo policy như Servlet. **Audience có thể cần validator/cấu hình riêng**; không mặc nhiên chấp nhận mọi JWT từ cùng issuer cho mọi resource.

Nếu chuyển sang opaque token, cấu hình Resource Server bằng `.opaqueToken(...)` và Reactive introspector/credentials phù hợp với Authorization Server. Không dùng một JWT decoder để “giải mã” chuỗi opaque hoặc tự phân tích opaque token không có introspection policy.

### 9.5. Controller Reactive: xác thực ở web filter, phân quyền ở service

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class ReactiveOrderApi {

    private final ReactiveOrderService orders;

    ReactiveOrderApi(ReactiveOrderService orders) {
        this.orders = orders;
    }

    record NewOrder(String itemId) {}

    @PostMapping("/api/orders")
    Mono<ResponseEntity<Map<String, String>>> create(
            Mono<Authentication> authentication,
            @RequestBody Mono<NewOrder> body) {

        return Mono.zip(authentication, body)
            .flatMap(values -> {
                String itemId = values.getT2().itemId();

                if (itemId == null || itemId.isBlank()) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "itemId bắt buộc"));
                }

                return orders.createIfAuthorized(
                        values.getT1(), itemId)
                    .map(id -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(Map.of("id", id)));
            });
    }
}
~~~

`ReactiveOrderService` là **service giả định của ứng dụng**. Nó phải kiểm tra ownership/tenant/client type, validate dữ liệu và ghi trạng thái qua reactive/non-blocking data access phù hợp. Không gọi JDBC blocking trực tiếp trên event loop để triển khai một API WebFlux không chủ đích.

### 9.6. Khi một ứng dụng WebFlux có cả browser session

Có thể có hai chain:

- `/api/**`: Bearer-only, không lưu `SecurityContext` vào `WebSession`, CSRF không áp dụng theo threat model đã chứng minh.
- `/web/**` hoặc các đường browser login/refresh: Dùng WebSession cookie, **giữ `CsrfWebFilter`** và repository phù hợp.

Khi có BFF, bản thân BFF nhận cookie và cần CSRF ở đường browser→BFF, dù downstream Resource API dùng Bearer. Cần đặt `@Order`/matcher cho từng chain và kiểm thử cookie-only request không đi nhầm chain.

## 10. Chặn các đường vận chuyển Bearer token ngoài header

### 10.1. Tại sao không nhận access token qua query parameter?

Một số client muốn làm đơn giản:

~~~http
GET /api/orders?access_token=TEST_VALUE HTTP/1.1
Host: api.example.com
~~~

Đây là đường dễ gây rò token qua access logs, history, analytics, error reports hoặc URLs được chia sẻ. Theo thực hành ưu tiên RFC 6750, nên dùng header `Authorization`.

Spring Security Servlet cho phép cấu hình resolver chặt:

~~~java
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

// Định nghĩa bean hoặc tạo trong phần cấu hình resource-server chain.
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

resolver.setAllowUriQueryParameter(false);
resolver.setAllowFormEncodedBodyParameter(false);
~~~

Và có thể đưa vào chain:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults()))
~~~

**Chú ý:** Các dòng trên là **trích đoạn tích hợp**, không phải một class Java độc lập. Mặc định thông thường của `DefaultBearerTokenResolver` không cho token qua URI query/form-body nếu không được bật; viết rõ giúp ghi nhớ chính sách.

Bất kỳ khi nào hỗ trợ token từ nơi khác header, phải đánh giá rò rỉ, ambiguity, caching và security filters. Không tự thêm resolver đọc token từ `Cookie` nếu mục tiêu là API Bearer-only.

### 10.2. Kiểm thử header giả và nhiều Bearer credentials

Một Resource Server nên từ chối:

- `Authorization` không có token hoặc token malformed;
- `Authorization: Basic ...` trên chain không bật Basic;
- JWT sai chữ ký, sai `iss`, sai `aud`, hết hạn hoặc chưa đến `nbf`;
- Access token opaque không active;
- Credentials mơ hồ/đưa đồng thời nhiều nguồn token ngoài thiết kế;
- Request có session cookie nhưng **thiếu Bearer**.

**Không viết code tự parse header bằng `split(" ")` rồi bỏ qua mọi kiểm tra chữ ký/expiry/audience.** Dùng authentication filter/decoder/introspector của Spring Security, tùy chỉnh khi thực sự cần và có test.

### 10.3. API gateway có thể làm thay đổi ranh giới

Nếu gateway xác thực browser session cookie rồi tự tạo header `Authorization: Bearer ...` cho upstream Spring, **upstream** thấy Bearer nhưng request **browser→gateway** vẫn dựa vào ambient cookie.

Cần kiểm tra CSRF ở **gateway/BFF hoặc đường browser-entry** đó, không thể tuyên bố hệ thống không có CSRF chỉ vì Resource Server sâu bên trong nhìn thấy Bearer.

Nếu gateway chỉ forward token do client chủ động gửi, vẫn cần kiểm chứng proxy không chấp nhận header giả từ mạng không tin cậy hoặc không làm rò `Authorization` sang upstream ngoài allowlist.

## 11. Session, CSRF, CORS và bảo vệ trình duyệt phải đứng đúng chỗ

### 11.1. Bearer-only API không đồng nghĩa tất cả request của hệ thống đều bearer-only

Một hệ thống tổng thể có thể chứa:

~~~mermaid
flowchart TD
    B[Browser SPA] -->|Bearer header do JS gắn| API[Resource Server /api/**]
    B -->|Cookie phiên tự gửi| WEB[Web app /web/**]
    B -->|Refresh cookie tự gửi| REFRESH[POST /auth/refresh]
    API -->|Token claims và scopes| POLICY[Authorization nghiệp vụ]
    WEB -->|CSRF token + session auth| POLICY
    REFRESH -->|Origin/CSRF và rotation policy| POLICY
~~~

Quyết định phòng vệ theo **đúng ranh giới**:

| Endpoint | Credential được chấp nhận | CSRF truyền thống |
|---|---|---|
| `POST /api/orders` | Chỉ client Bearer header | Có thể miễn sau khi chứng minh không có ambient auth |
| `POST /web/profile` | Session cookie | Cần CSRF token |
| `POST /auth/refresh` | Refresh token HttpOnly cookie | Cần đánh giá CSRF/token abuse riêng |
| `POST /login` | Form login browser, tạo session | Cần đánh giá login CSRF dù chưa có phiên xác thực |
| `POST /logout` | Browser session cookie | Thường cần CSRF token |
| `GET /api/orders` | Bearer header | Không phải request thay đổi trạng thái; vẫn cần auth/quyền |
| `GET /account/delete` có side effect | Session cookie | Sai HTTP semantics; cần sửa sang phương thức ghi |

### 11.2. Cookie với JWT access token không phải mô hình này

Nếu một service đọc `ACCESS_TOKEN` từ cookie và xác thực JWT:

~~~http
Cookie: ACCESS_TOKEN=jwt...
~~~

đó là **cookie authentication**, không phải “client chủ động đặt Bearer header” theo thiết kế bài học. `HttpOnly` không ngăn browser gửi cookie; `SameSite` chỉ giảm các ngữ cảnh cross-site nhất định, nhất là khi có same-site cross-origin subdomains.

**Không** viện dẫn việc API “stateless” để miễn CSRF ở route dùng cookie JWT.

### 11.3. CORS và CSP là các lớp bổ trợ, không thay token validation

| Lớp | Bảo vệ điều gì | Không thay thế điều gì |
|---|---|---|
| **CORS** | Browser origin nào được JS đọc response/call với non-safelisted headers | Không xác thực người dùng, không ngăn cURL dùng stolen token |
| **CSP** | Hạn chế nguồn script/kết nối và một số hành vi ở SPA origin | Không tự chặn mọi XSS; không thay xác thực access token |
| **HTTPS/HSTS** | Hạn chế HTTP không an toàn và downgrade trong phạm vi chính sách | Không kiểm tra scope, audience hoặc quyền trên tài nguyên |
| **CSRF token** | Xác minh request ghi dùng ambient credential | Không thay token Bearer hoặc chống token theft |
| **HttpOnly/SameSite** | Bảo vệ cookie và điều kiện browser tự gửi | Không tự bảo vệ memory/localStorage Bearer token |
| **HTTP firewall** | Xử lý/loại URL và HTTP request bất thường theo chính sách | Không xác minh JWT claims/scope |
| **Authentication** | Xác minh danh tính token hoặc client | Không tự phân quyền mọi object/tenant |
| **Authorization** | Kiểm tra scope/role và quyền trên resource | Không thay bảo vệ credential khỏi lộ |

### 11.4. CSP trên HTML SPA

Nếu SPA được Nginx/CDN phục vụ, CSP phải có trên **response HTML của SPA**, không chỉ response JSON từ Spring API. Ví dụ một chính sách cơ sở cần được điều chỉnh theo build:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

- `connect-src` cho biết những origin JavaScript của SPA được phép kết nối; **API vẫn phải cấu hình CORS riêng**.
- `script-src` cần đủ chặt theo nơi phục vụ script; cân nhắc nonce/hash/Trusted Types và hạn chế script bên thứ ba.
- Không dùng `innerHTML` với dữ liệu không tin cậy; dùng DOM API như `textContent` và escaping/sanitization phù hợp.
- **Một script XSS cùng origin có thể dùng access token còn trong memory hoặc gọi API qua code hợp lệ**, dù CORS chỉ allowlist SPA.

### 11.5. HTTPS và HSTS

Spring Security và reverse proxy có thể thiết lập `Strict-Transport-Security` trên response HTTPS. Khi cấu hình HSTS, xác định rõ ai phát header (API, SPA static host, edge proxy) và phạm vi hostname/subdomains. `includeSubDomains`/preload chỉ dùng khi hạ tầng đáp ứng HTTPS lâu dài cho toàn phạm vi.

API Bearer header trên kết nối HTTP không an toàn gây nguy cơ lộ credential; hãy dùng HTTPS, xác minh chứng chỉ và không bỏ TLS verification để “fix dev”.

### 11.6. HTTP firewall và route matching

Spring Security Servlet có `StrictHttpFirewall`/HTTP firewall policy giúp từ chối một số request/path bất thường; WebFlux có cơ chế xử lý đường dẫn và security matching riêng. Các rule path normalization, encoded slash, semicolon, method và proxy rewriting cần được kiểm thử.

Nếu securityMatcher dựa trên `/api/**` nhưng proxy rewrite khiến endpoint được xử lý ở path khác, có thể chọn chain sai. **Không tắt HTTP firewall rộng** để khắc phục một đường dẫn frontend/proxy được thiết kế sai; sửa URI contract trước.

## 12. Kiểm thử Resource Server: đừng chỉ chứng minh JWT mock hợp lệ

### 12.1. Ma trận test bắt buộc

| ID | Tình huống | Credential request | Kết quả mong đợi |
|---|---|---|---|
| **BR-01** | API POST hợp lệ, đủ scope | Bearer token hợp lệ | Thành công theo hợp đồng API |
| **BR-02** | POST thiếu token | Không Bearer, không cookie | `401`, không side effect |
| **BR-03** | POST chỉ có session cookie | Cookie đã đăng nhập web, **không Bearer** | **Không** được xác thực qua cookie |
| **BR-04** | Token malformed/sai chữ ký | Bearer không hợp lệ | `401`, không side effect |
| **BR-05** | Token sai `iss` | Bearer issuer không tin cậy | `401` |
| **BR-06** | Token sai `aud` | Bearer dành cho API khác | `401` theo validator |
| **BR-07** | Token quá `exp` | Bearer hết hạn | `401` |
| **BR-08** | Token thiếu `SCOPE_orders:write` | Token hợp lệ nhưng không đủ scope | `403` |
| **BR-09** | Token đủ scope nhưng sai owner | Bearer user A sửa resource B | `403`/`404` theo policy, không side effect |
| **BR-10** | Preflight từ SPA được phép | `OPTIONS` không có Bearer | CORS permission trả đúng, không đòi login |
| **BR-11** | Preflight origin ngoài allowlist | `OPTIONS` từ untrusted origin | Không cấp CORS permission |
| **BR-12** | POST từ SPA origin đúng nhưng không Bearer | Origin được CORS allowlist, thiếu token | Vẫn `401` |
| **BR-13** | Cookie web route POST thiếu CSRF | Session cookie, không CSRF token | Bị CSRF filter từ chối |
| **BR-14** | Cookie web route POST đúng CSRF | Session cookie + token đúng | Qua CSRF; vẫn cần authorization |
| **BR-15** | Refresh cookie endpoint | Refresh cookie, không anti-CSRF | Phải theo chính sách bảo vệ refresh, không lọt vào bearer-only chain |
| **BR-16** | Query parameter token | `?access_token=...`, không header | Không chấp nhận nếu header-only |
| **BR-17** | Header Basic trên bearer chain | `Authorization: Basic ...` | Không xác thực theo Basic |
| **BR-18** | 401/403 response | Token thiếu/sai/quyền thiếu | Status/WWW-Authenticate hợp đồng, không lộ token |
| **BR-19** | CORS error path | Origin trusted, token sai | Actual response có CORS header phù hợp để SPA đọc lỗi |
| **BR-20** | GET API chỉ đọc | Bearer hợp lệ | Không có side effect nghiệp vụ |

**Nhóm BR-03 là quyết định:** Một API có cả bearer và cookie fallback không đáp ứng giả định miễn CSRF. Test chỉ với `jwt()` mà không gửi cookie thực không chứng minh điều này.

### 12.2. Positive test cần tách Scope và Object-level authorization

`SCOPE_orders:write` chứng minh client được cấp khả năng gọi một loại thao tác. Resource-owner check vẫn phải được service kiểm tra. Test cần có:

- User Alice sửa order của Alice: thành công.
- User Alice sửa order của Bob: bị từ chối.
- Token dành cho resource API khác: bị từ chối dù signature đúng.
- Token của client không có user subject: chỉ được dùng trên endpoint chính sách cho phép machine-to-machine.

Với mọi negative case, xác nhận **database, sự kiện nghiệp vụ và side effects không đổi**. Không dựa hoàn toàn vào HTTP status.

## 13. Servlet MockMvc: thử Bearer-only và đường cookie fallback

### 13.1. Test positive và negative bằng mock JWT

`spring-security-test` có `SecurityMockMvcRequestPostProcessors.jwt()` để gắn một `JwtAuthenticationToken` vào request test. Nó giúp kiểm tra **authorization rules và controller**, nhưng **không bắt BearerTokenAuthenticationFilter giải mã một access token thật**.

Giả định ứng dụng có `POST /api/orders` trả `201 Created` khi hợp lệ và service test cho phép Alice tạo đơn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerOnlyServletTests {

    @Autowired MockMvc mvc;

    @Test
    void bearerWithWriteScopeCanPostWithoutCsrfToken() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders:write")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"itemId\":\"book-1\"}"))
            .andExpect(status().isCreated());
    }

    @Test
    void missingBearerTokenIsUnauthorized() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"itemId\":\"book-1\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPrincipalWithoutWriteScopeIsForbidden() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"itemId\":\"book-1\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Đây là mẫu test logic Resource Server** với assumptions được ghi rõ, không phải một project tự chạy độc lập. Nếu API chưa có controller/service, cần triển khai fixture trước. Nếu controller trả status khác `201`, thay assertion theo hợp đồng API.

**Điểm cần phân biệt:**

- Bài test đầu tiên **không gửi CSRF token**, nhưng request có JWT principal và đúng scope; nó chứng minh route Bearer-only được cấu hình có thể thực hiện POST không cần CSRF.
- Bài test thiếu token không dùng `with(jwt())` và kỳ vọng `401` nếu chain đã thiết lập Bearer entry point đúng.
- Bài test không đủ scope dùng principal hợp lệ, kỳ vọng `403` do authorization.
- `jwt()` tạo authentication trong test, **không xác minh JWT chữ ký, issuer, audience, expiry hay actual Authorization header**.
- Không dùng test pass này để tự tuyên bố production Bearer decoder đã an toàn.

### 13.2. Test không nhận cookie-only authentication

Một test bước đầu:

~~~java
import jakarta.servlet.http.Cookie;

@Test
void sessionCookieWithoutBearerDoesNotAuthenticateApi() throws Exception {
    mvc.perform(post("/api/orders")
            .cookie(new Cookie("JSESSIONID", "dummy-session-id"))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"itemId\":\"book-1\"}"))
        .andExpect(status().isUnauthorized());
}
~~~

Đặt test method trong class đã có `MockMvc mvc`. Nó chứng minh một cookie **giả** không tự tạo authentication trên route; **chưa chứng minh** API không chấp nhận một **cookie session hợp lệ** đã login.

Để kiểm chứng fallback thực sự:

1. Khởi tạo **ứng dụng tích hợp** có cả web chain, đăng nhập bằng form/session web thật (và CSRF token khi cần).
2. Ghi nhận **session cookie được server phát hành** và trạng thái auth trên `/web/me`.
3. Gửi POST `/api/orders` với **chính cookie hợp lệ ấy** nhưng **không gửi `Authorization`**.
4. API phải **không thực hiện thao tác dưới danh tính phiên web**, thường `401`.
5. Gửi `Authorization: Bearer ...` hợp lệ cho Resource Server, không cookie, xác nhận xử lý theo token.
6. Nếu API lại chấp nhận cookie-only request, điều tra chain/matcher/filter/proxy trước khi miễn CSRF.

Test này là một trong những bằng chứng mạnh nhất cho quyết định “CSRF không áp dụng cho nhóm bearer-only”.

### 13.3. Test preflight từ SPA không cần bearer token

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerCorsServletTests {

    @Autowired MockMvc mvc;

    @Test
    void allowedSpaPreflightDoesNotNeedBearer() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://spa.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "authorization,content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://spa.example.com"));
    }

    @Test
    void untrustedOriginDoesNotReceiveCorsPermission()
            throws Exception {

        mvc.perform(options("/api/orders")
                .header("Origin", "https://untrusted.other.test")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "authorization,content-type"))
            .andExpect(status().isForbidden());
    }
}
~~~

`403` cho untrusted preflight là kết quả thường gặp của Spring CORS processor với cấu hình minh họa; nếu tổ chức có custom CORS error handler, kiểm tra theo hợp đồng đã chọn. Điều cốt lõi là **không cấp CORS permission cho untrusted origin**, không phải một status cố định trên mọi môi trường.

Một preflight hợp lệ **không mang Bearer header thật** và không cần JWT principal, vì browser chỉ hỏi liệu `authorization` là header được phép cho actual POST sau đó hay không.

### 13.4. Test header thật và decoder không dùng jwt() mock

Ở tầng tích hợp cao hơn, gửi header:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer TEST_ACCESS_TOKEN
Content-Type: application/json

{"itemId":"book-1"}
~~~

Có hai chiến lược:

- **HTTP integration với Authorization Server/test issuer** phát token JWT **được ký thật**, Resource Server dùng JWK tin cậy và validator production-like. Đây là bằng chứng tốt nhất về JWT decoder, issuer, audience, expiry và scope.
- **Test-only `JwtDecoder` mock/stub** nhận một token fixture xác định và trả `Jwt` tương ứng; sử dụng request HTTP thật để kiểm tra BearerTokenAuthenticationFilter gọi decoder và xử lý kết quả. Cách này kiểm tra wiring nhưng **không chứng minh cryptographic verification thật**.

Đối với token sai signature, sai `iss`/`aud`/`exp`, hãy dùng **JWT test issuer ký với khóa test** hoặc mock decoder trả lỗi có chủ đích để kiểm tra response path. Không gửi chuỗi JWT bất kỳ rồi kết luận toàn bộ cơ chế validation đã hoạt động.

### 13.5. Giữ riêng test web-cookie CSRF

Trong hệ thống có cả web chain:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;

@Test
void webSessionPostStillRejectsMissingCsrf() throws Exception {
    mvc.perform(post("/web/profile")
            .with(user("alice"))
            .param("displayName", "Changed"))
        .andExpect(status().isForbidden());
}

@Test
void webSessionPostWithCsrfMayProceed() throws Exception {
    mvc.perform(post("/web/profile")
            .with(user("alice"))
            .with(csrf())
            .param("displayName", "Changed"))
        .andExpect(status().isNoContent());
}
~~~

Các method nằm trong class test đã có `mvc`/imports phù hợp; `/web/profile` là **endpoint fixture giả định** trả `204` khi thành công. Mục tiêu là phát hiện việc developer vô tình disable CSRF ở **toàn bộ ứng dụng** khi chỉ muốn thay đổi nhóm API bearer-only.

## 14. Reactive WebTestClient: kiểm tra WebFlux Resource Server

### 14.1. Positive, missing token và thiếu scope

Dùng `SecurityMockServerConfigurers.mockJwt()` trong Spring Security Test cho WebFlux:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BearerOnlyReactiveTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void validJwtPrincipalWithScopePassesPostWithoutCsrf() {
        client().mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:write")))
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"itemId\":\"book-1\"}")
            .exchange()
            .expectStatus().isCreated();
    }

    @Test
    void missingBearerAuthenticationIsRejected() {
        client()
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"itemId\":\"book-1\"}")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void scopeReadCannotCreateOrder() {
        client().mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read")))
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"itemId\":\"book-1\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

`mockJwt()` hỗ trợ kiểm tra reactive authorization, tương tự `jwt()` với Servlet, nhưng nó **không xác minh token thật trên dây HTTP**. Không dùng kết quả này để khẳng định issuer/JWK/audience đã được Resource Server production cấu hình đúng.

### 14.2. Reactive preflight

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BearerCorsReactiveTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void allowedOriginPreflightRequiresNoBearer() {
        client().options().uri("/api/orders")
            .header("Origin", "https://spa.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers",
                "authorization,content-type")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "Access-Control-Allow-Origin",
                "https://spa.example.com");
    }

    @Test
    void otherOriginPreflightIsRejected() {
        client().options().uri("/api/orders")
            .header("Origin", "https://untrusted.other.test")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers",
                "authorization,content-type")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Nếu ứng dụng có custom CORS error handling, điều chỉnh status assertion, nhưng giữ chính sách **không cho untrusted origin đọc response**.

### 14.3. Reactive integration: xác minh Cookie không trở thành Bearer

Test `WebTestClient` với mockJwt **không đủ** chứng minh không có fallback qua WebSession. Cần có test HTTP integration:

~~~text
Client A: login thật vào web-session route -> nhận cookie SESSION=A.
Client A: POST /api/orders với Cookie: SESSION=A, không Bearer.
  Kỳ vọng: không authentication qua cookie, không có order mới.

Client B: POST /api/orders với Bearer access token thật, không cookie.
  Kỳ vọng: issuer/audience/scope đủ -> 201 Created.

Client B: POST /api/orders với token hết hạn hoặc sai audience.
  Kỳ vọng: 401, không ghi dữ liệu.

Client B: POST với token hợp lệ thiếu scope.
  Kỳ vọng: 403, không ghi dữ liệu.
~~~

Khi WebFlux có nhiều WebFilterChains, test matcher priority, CORS integration và nơi lưu `SecurityContext`/WebSession. Với BFF hoặc gateway biến cookie thành Bearer, phải kiểm thử **điểm vào browser** nữa.

## 15. Browser E2E và HTTP client integration

### 15.1. Kịch bản SPA khác origin

Môi trường thử nghiệm:

~~~text
SPA:          https://spa.example.test
Resource API: https://api.example.test
Issuer:       https://auth.example.test
~~~

Các host trên là **tên mô hình**, cần DNS/hosts và certificate test phù hợp; không đưa access token thật vào tài liệu hoặc log.

Quy trình:

1. **Mở SPA từ origin tin cậy** và kiểm tra CSP trên HTML thực sự cho phép `connect-src` tới API.
2. **Thực hiện OAuth/OIDC login** theo flow có PKCE/state. Không tự đọc password bằng form giả rồi tạo access token trong JavaScript.
3. **Nhận access token hợp lệ** từ provider test; kiểm tra client đã xin scope và audience phù hợp.
4. **Gọi GET /api/reports** với `Authorization: Bearer ...` và `credentials:"omit"`. Browser có thể gửi OPTIONS do Authorization header; kiểm tra preflight.
5. **Gọi POST /api/orders** với JSON và Bearer. Kiểm tra `201` và dữ liệu mới.
6. **Gửi cùng POST nhưng xóa Authorization header**; phải bị `401`, dù browser có cookie unrelated ở origin đích.
7. **Gửi Bearer token không đủ scope**; phải bị `403`, không có tác động.
8. **Thử token của resource khác** (audience không khớp); API phải từ chối.
9. **Thử token hết hạn**; API phải từ chối và client theo refresh/reauth policy.
10. **Kiểm tra untrusted Origin**; browser không được cấp CORS permission đọc response API, dù HTTP client non-browser vẫn có thể gửi request khi có token.
11. **Kiểm tra cookie-only fallback:** Nếu ứng dụng có web login session hợp lệ, gọi API với cookie đó nhưng **không Bearer**; phải bị từ chối.
12. **Kiểm tra URL/query:** API không chấp nhận token qua query/form nếu đã quy định chỉ nhận header.
13. **Thử logout ở OAuth client**: Dọn state, xác định rõ liệu refresh/access token đã thực sự bị thu hồi hay chỉ xóa trong browser, kiểm tra theo provider.
14. **Xác minh log/proxy**: Không lưu `Authorization` hoặc full JWT, response không cache nhầm dữ liệu riêng tư.

### 15.2. Đọc Network khi browser báo CORS error

Với request cross-origin có Bearer header, trình tự thường là:

~~~text
OPTIONS /api/orders
  Origin: https://spa.example.test
  Access-Control-Request-Method: POST
  Access-Control-Request-Headers: authorization,content-type

=> Preflight OK? Nếu không, browser có thể không gửi actual POST.

POST /api/orders
  Origin: https://spa.example.test
  Authorization: Bearer ...
  Content-Type: application/json

=> Resource Server mới xác minh Bearer và scope.
~~~

**Đừng sửa 401 Resource Server bằng cách mở CORS cho mọi origin.** Và đừng sửa OPTIONS 401 bằng cách permitAll toàn bộ POST. Hai lỗi nằm ở hai lớp khác nhau.

### 15.3. Test bằng curl khác browser E2E

Một HTTP client như cURL có thể gửi Authorization header mà **không tuân theo CORS của browser**:

~~~bash
curl --silent --show-error \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  https://api.example.test/api/reports
~~~

CURL test giúp kiểm tra decoder, status và API contract; nó không chứng minh CORS preflight sẽ cho SPA chạy. Browser test giúp kiểm tra CORS, CSP và cách client gắn Bearer header, nhưng muốn chứng minh JWT signature/audience validation cần thêm integration test với token thật.

### 15.4. Audit các credential đang được gửi

Một test bảo mật nên ghi nhận (không lộ token):

| Header/thuộc tính | Mong đợi cho Bearer-only resource API |
|---|---|
| `Authorization` | Có Bearer header trên request được phép |
| `Cookie` | Không cần cookie, server **không xác thực** dựa vào cookie-only request |
| `Origin` | Có trên cross-origin request phù hợp, khớp allowlist ở browser |
| Preflight `Access-Control-Request-Headers` | Liệt kê authorization và content-type nếu cần |
| `WWW-Authenticate` | Có giá trị theo Bearer auth policy khi lỗi phù hợp |
| `Cache-Control` | Không lưu response chứa dữ liệu cá nhân trên cache công khai |
| CSP trên SPA HTML | `connect-src` chỉ cho phép đích tin cậy |
| Logs | Không chứa access token, refresh token hay JWT payload riêng tư |

## 16. Chẩn đoán xung đột bảo mật khi triển khai

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
|---|---|---|
| `OPTIONS /api/orders` trả `401` | CORS xử lý sau Bearer authentication | Cấu hình `http.cors(...)`, CORS source đúng chain, preflight không auth |
| Browser báo CORS nhưng cURL thành công | CORS policy chỉ ảnh hưởng browser | Xem OPTIONS/ACAO/allowed headers, Origin chính xác |
| SPA GET thành công nhưng POST có Authorization trả CORS error | Preflight header `authorization` chưa được allow | Thêm header cần thiết vào trusted-origin CORS, không mở wildcard |
| API trả `401` cho JWT nhìn có vẻ đúng | Sai issuer, signature, audience, expiry, nbf, JWK, token type hoặc không có header | Kiểm tra decoder và claims ở server một cách không lộ token |
| API trả `403` với token hợp lệ | Thiếu `SCOPE_...` hoặc object-level permission | Kiểm tra authorities và resource authorization |
| API chấp nhận access token dành cho API khác | Chưa kiểm tra `aud` | Thêm audience validator và test sai audience |
| Access token JWT có scope nhưng bị `403` | Mapping scope/claim khác quy ước của converter | Kiểm tra JWT claims và `JwtAuthenticationConverter` |
| Cookie-only POST vẫn thành công dù không Bearer | Có authentication fallback qua session/gateway/filter khác | Loại bỏ fallback hoặc bảo vệ CSRF ở đường browser |
| `SessionCreationPolicy.STATELESS` nhưng có cookie auth | Custom filter/gateway vẫn đọc cookie | Audit toàn bộ authentication sources và request path |
| Spring Security tạo redirect login HTML ở API | FormLogin/default entry point/chain không phù hợp | Đặt Resource Server chain/entry point và matcher đúng |
| SPA gửi Bearer tới host không tin cậy | URL từ input/redirect làm lộ Authorization | Whitelist API origin, reject unexpected redirects, review code |
| Token nằm trong query string/log | Client transport sai hoặc logging quá rộng | Chỉ dùng header; che token trong logs/tracing |
| Token hết hạn mà client retry vô hạn | Refresh/reauth flow không có giới hạn | Dừng retry vòng lặp, làm mới có kiểm soát, phân biệt 401/403 |
| Refresh endpoint dùng cookie nhưng bị miễn CSRF | Matcher /api/** quá rộng | Tách route và áp CSRF/Origin/rotation policy cho cookie refresh |
| BFF downstream dùng Bearer nhưng browser POST bị CSRF | BFF nhận session cookie và thiếu CSRF token | Giữ anti-CSRF trên browser→BFF |
| CSP chặn `fetch` tới Resource API | HTML SPA thiếu `connect-src` cho API origin | Cập nhật CSP ở response **SPA HTML**, không chỉ API |
| Browser HTTPS gọi API HTTP bị chặn | Mixed content hoặc TLS endpoint sai | Dùng HTTPS và certificate tin cậy |
| API hoạt động local nhưng prod 404/401 | Reverse proxy rewrite/matcher sai | So public/upstream path, forwarded headers, filter chain |
| API route test `with(jwt())` pass nhưng header thật 401 | Test mock bỏ qua Bearer decoder/JWK | Thêm HTTP integration với JWT ký thật hoặc stub decoder |
| Request từ untrusted origin bị “CORS blocked” nhưng server vẫn ghi | CORS chỉ cản đọc; endpoint chấp nhận request/credential khác | Kiểm tra auth/CSRF/routing, xác minh no-side-effects |
| Header `WWW-Authenticate` thiếu hoặc bị proxy sửa | Error handler/proxy override | So response Spring và edge, giữ status/header auth an toàn |
| Mobile client nhận CORS error? | Native HTTP client thường không bị browser CORS; có thể là WebView hoặc lỗi khác | Xác định loại client thực, không áp browser policy máy móc |
| WebFlux logout/session behavior khác Servlet | WebSession handler khác hoặc authentication state tồn tại | Kiểm tra từng loại chain/handler, không suy diễn từ MVC |

### 16.1. Quy trình phân biệt 401, 403, CORS và CSRF

~~~text
Browser gọi API khác origin
    |
    +-- Browser gửi OPTIONS?
    |      |
    |      +-- Không qua: CORS/preflight/network/config source
    |      +-- Qua: browser gửi request thật
    |
    +-- Actual request có Authorization: Bearer ...?
           |
           +-- Không: thiếu access token/client không gắn header
           |         => Resource Server thường 401
           |
           +-- Có: Resource Server xác minh token
                     |
                     +-- Invalid/expired/wrong audience => 401
                     +-- Valid thiếu scope/permission => 403
                     +-- Valid đủ quyền => controller xử lý
           
    Nếu request dựa trên cookie:
        Đánh giá lại CSRF theo credential tự gửi,
        không dùng nhánh bearer-only.
~~~

Khi ghi log, chỉ dùng metadata cần thiết: request path/method, chain, loại authentication, JWT claim category đã fail, principal ID đã được khử nhạy cảm và exception type. **Không log raw token hoặc toàn bộ Authorization header**.

## 17. Các quyết định kiến trúc cần ghi thành tài liệu

### 17.1. Khi nào nên dùng Resource Server bearer-only?

| Ngữ cảnh | Bearer-only API có phù hợp không? | Cần chứng minh |
|---|---|---|
| **Native mobile app** gọi Resource API | Thường phù hợp | App tự đặt header, token được bảo vệ trên thiết bị, không có cookie auth fallback |
| **CLI** gọi API bằng token | Thường phù hợp | Token không lộ qua command history/log, scope/audience và expiry đúng |
| **Server-to-server** theo client credentials | Phù hợp nếu quyền machine-to-machine được thiết kế | Client credentials, TLS, scope/resource authorization, không trộn user ID |
| **SPA** dùng OAuth access token trong memory | Có thể phù hợp | Authorization Code + PKCE, XSS defense, CORS, token storage/lifecycle, API không nhận cookie |
| **SPA** lưu access token trong localStorage | Có thể về mặt transport | Token vẫn chịu rủi ro XSS; quyết định lưu token cần threat model riêng |
| **SPA dùng JWT cookie HttpOnly** | **Không phải bearer-only header** | Browser tự gửi cookie, cần đánh giá CSRF |
| **Web SSR/form login với JSESSIONID** | Không | Cookie session tự gửi; giữ CSRF cho POST |
| **BFF nhận cookie, gọi API Bearer** | Resource API phía sau có thể bearer-only | Browser→BFF phải chống CSRF riêng |
| **SPA Bearer access token + refresh cookie** | Chỉ áp cho route Bearer thực sự | Refresh route cookie phải được đánh giá CSRF riêng |
| **API vừa nhận JWT header vừa nhận cookie session** | Không đủ điều kiện miễn CSRF chung | Loại fallback hoặc bảo vệ đường cookie |

**Đừng chọn kiến trúc chỉ vì một từ khóa như “stateless”**. Một hệ thống có thể stateless đối với access token nhưng lại stateful ở BFF, refresh token store, rate-limit data hoặc login session.

### 17.2. Khi nào BFF là lựa chọn tốt hơn SPA trực tiếp cầm token?

BFF có thể phù hợp khi:

- Muốn giữ OAuth tokens **khỏi JavaScript browser**;
- Có thể cung cấp một frontend/backend origin hoặc một session cookie do BFF quản lý;
- Muốn tập trung OAuth client secrets/refresh token rotation/authorization trên server;
- Chấp nhận vận hành session store, CSRF cho browser→BFF và lớp proxy API.

BFF không **tự động** chống mọi XSS: script cùng origin vẫn có thể gọi BFF dưới phiên của user; cần CSP, output encoding, kiểm tra quyền và anti-abuse. Nó cũng không thay việc Resource API kiểm tra Bearer token do BFF gửi.

### 17.3. Khi nào yêu cầu sender-constrained access token?

Với hệ thống nhạy cảm, một token bị đánh cắp có thể bị dùng từ thiết bị/network khác. Có thể xem xét:

- **mTLS-bound access tokens**: Resource Server xác minh chứng chỉ client gắn với token, đòi mTLS end-to-end/thiết kế proxy đúng.
- **DPoP (Demonstrating Proof of Possession)**: Client chứng minh quyền giữ khóa riêng qua proof theo request, resource server xác minh ràng buộc DPoP/token theo giao thức; cần thiết kế chống replay/nonce phù hợp.

Đây là các cơ chế bổ sung phức tạp và đòi hỗ trợ của Authorization Server/Resource Server. **Không** chỉ thêm custom HTTP header tự đặt rồi tuyên bố bearer token đã thành proof-of-possession. Trong bài học này, mô hình nền tảng vẫn là **Bearer header**.

### 17.4. API cần bảo vệ gì ngoài JWT validation?

- **Scopes/roles:** Chỉ cho action khi có authority phù hợp.
- **Object-level authorization:** Kiểm tra user/client có được truy cập tài nguyên thuộc tenant/người khác hay không.
- **Input validation:** JSON schema/field constraints và dữ liệu độc hại.
- **Rate limiting/abuse detection:** Theo chủ thể thực tế, không chỉ IP; token không miễn kiểm soát lạm dụng.
- **Idempotency:** Với tạo đơn/thanh toán và retry do mạng, thiết kế idempotency key riêng.
- **HTTP firewall:** Giữ URL/method/path handling nhất quán với security matcher.
- **Cache policy:** Không cache dữ liệu riêng tư công khai, chú ý `Authorization` trong upstream/cache key.
- **Secret hygiene:** Không log `Authorization`, không hardcode access token, không xuất vào URL.
- **TLS và headers:** HTTPS, HSTS, CSP trên SPA HTML và những response headers cần thiết.
- **Logging/monitoring:** Báo lỗi theo loại, không đưa JWT nguyên văn vào trace/telemetry.

Đó là lý do nội dung Bearer-only thuộc module **SPRING_SECURITY_HTTP_PROTECTION** chứ không chỉ là một ví dụ bật OAuth Resource Server.

## 18. Quy trình triển khai và đánh giá thay đổi

### 18.1. Phiếu ghi nhận chính sách theo endpoint

Với mỗi nhóm route, nên có ít nhất các trường:

| Trường | Ví dụ |
|---|---|
| API | `POST /api/orders` |
| Client chính | SPA khác origin, mobile, CLI hoặc service-to-service |
| Credential duy nhất | `Authorization: Bearer access_token` |
| Token format | JWT đã ký / opaque introspection |
| Trusted issuer | URI chính xác của Authorization Server |
| Expected audience | Resource API identifier |
| Required scope/authority | `SCOPE_orders:write` |
| Object-level permission | User/client được tạo đơn cho account/tenant nào |
| Cookie/session fallback | **Không**; được test bằng cookie-only request |
| CORS policy | Origin nào được phép đọc response; allowed headers/methods |
| CSRF policy | Miễn **theo chain bearer-only** do không có ambient credential |
| Sensitive logging | Mask token và private claims |
| TLS/proxy | HTTPS public endpoint, forwarding/trust boundary |
| Security tests | 401/403/201, invalid audience/scope, preflight, cookie-only |
| Regression trigger | Thêm cookie SSO, refresh endpoint, BFF, auth provider hoặc proxy |

Một ngoại lệ CSRF không nên tồn tại vĩnh viễn ngoài bản thiết kế: **khi đường xác thực thay đổi, phải đánh giá lại ngay**.

### 18.2. Quy trình change review

~~~mermaid
flowchart TD
    A[Đề xuất route hoặc auth mới] --> B[Liệt kê mọi credential được chấp nhận]
    B --> C{Có credential browser tự gửi?}
    C -->|Có| D[Giữ/thiết kế anti-CSRF và test]
    C -->|Không| E[Thiết kế Bearer-only chain rõ matcher]
    E --> F[Issuer, audience, scopes, quyền tài nguyên]
    F --> G[CORS cho SPA nếu cross-origin]
    G --> H[Test invalid token, thiếu scope và cookie-only]
    D --> H
    H --> I[Kiểm tra HTTPS, headers, proxy, cache và logging]
    I --> J[Browser/HTTP integration và regression trước release]
~~~

Đặc biệt khi thêm **cookie-based refresh**, **gateway SSO** hoặc **form login** vào cùng host, phải kiểm tra xem route mới có bị match bởi chain với `csrf.disable()` không.

## 19. Checklist triển khai Resource Server bearer-only

| Hạng mục | Tiêu chí xác minh |
|---|---|
| **Route** | Bearer-only paths được định nghĩa rõ bằng `securityMatcher`; không bao trùm cookie endpoints |
| **Authentication** | Chỉ Bearer header; form login/Basic/cookie fallback không có trong chain |
| **Session** | Stateless/no-op SecurityContext persistence theo stack, không dùng web session để xác thực API |
| **JWT trust** | Chữ ký, JWK, issuer, expiry, nbf, audience được xác minh đúng |
| **Opaque trust** | Introspection qua TLS tin cậy; client credentials bảo mật và active status được kiểm tra |
| **Token transport** | Không chấp nhận bearer token trong query string/form nếu đã chọn header-only |
| **Token type** | Access token dành cho resource API, không dùng ID token thay thế |
| **Scopes** | Endpoint yêu cầu đúng `SCOPE_...` hoặc mapping authorities phù hợp |
| **Resource authorization** | Kiểm tra owner, tenant và quyền theo đối tượng |
| **CORS** | Trusted origins cụ thể; Authorization/Content-Type trong allowed headers |
| **Preflight** | OPTIONS từ trusted SPA không yêu cầu Bearer token; untrusted origin không có CORS permission |
| **Client SPA** | Token chủ động gắn trong Authorization; tránh gửi tới origin khác |
| **Credential mode** | Với bearer-only request có thể dùng `credentials: "omit"`, server vẫn từ chối cookie-only |
| **Token storage** | Có threat model XSS, token leakage, refresh và logout |
| **HTTPS/HSTS** | Không truyền token qua HTTP production; HSTS chính sách phù hợp |
| **CSP** | CSP đặt trên HTML SPA thật, `connect-src` cho API origin |
| **HTTP firewall/proxy** | Không rewrite path sai security matcher; không log Bearer |
| **Cache** | Không cache response private ở shared cache; xử lý Authorization đúng |
| **Tests** | JWT mock + JWT thật/test decoder; audience/scope; cookie-only; CORS/browser E2E |
| **No side effects** | Mọi 401/403/invalid token không thay đổi dữ liệu |
| **Change review** | Có trigger đánh giá lại khi thêm cookie, BFF, SSO hoặc refresh flow |

## 20. Câu hỏi tự đánh giá

**1.** Vì sao một API nhận Bearer token do client chủ động đặt thường có mô hình CSRF khác API nhận JWT từ cookie?

**Đáp án:** Browser có thể **tự gửi** JWT cookie khi request được kích hoạt từ site ngoài; nó **không tự lấy** Bearer token trong memory/localStorage của SPA để chèn vào header. Nếu API chỉ nhận Bearer header và không có ambient auth fallback, điều kiện credential tự gửi của CSRF truyền thống thường không có.

**2.** Nếu API đặt `SessionCreationPolicy.STATELESS`, đã đủ để tắt CSRF cho toàn bộ ứng dụng chưa?

**Đáp án:** Chưa. Custom filter/gateway có thể vẫn nhận cookie, BFF/refresh/login có thể dùng ambient credential, và các route có thể rơi vào security chain khác. Phải chứng minh điều kiện theo endpoint.

**3.** `Authorization: Basic ...` có được xem là “client chủ động gửi token” giống mọi Bearer header không?

**Đáp án:** Không. Browser có thể cache và tự gửi HTTP Basic credential trong những ngữ cảnh nhất định. Đánh giá CSRF dựa vào **ai đưa credential vào request**, không dựa vào tên header.

**4.** Vì sao JWT có chữ ký hợp lệ nhưng sai `aud` vẫn phải bị Resource Server từ chối?

**Đáp án:** Token có thể được phát cho **một resource khác**. Nếu API không kiểm tra audience, token không dành cho nó có thể bị dùng sai mục tiêu dù chữ ký do issuer tin cậy tạo.

**5.** SPA khác origin gửi `Authorization: Bearer ...` và `Content-Type: application/json`. OPTIONS có cần access token không?

**Đáp án:** Không. Browser gửi **CORS preflight** trước actual POST, thường không có credential. CORS xử lý preflight, còn POST sau đó mới được Resource Server kiểm chứng Bearer/scope.

**6.** CORS chỉ cho phép `spa.example.com` đọc API. Người có token đánh cắp có thể dùng cURL từ máy khác không?

**Đáp án:** Có thể. CORS là chính sách browser; cURL không bị CORS của browser cản. Cần bảo vệ token khỏi lộ, scope/audience, expiry, authorization và các cơ chế sender-constrained nếu phù hợp.

**7.** Vì sao `jwt()` helper trong MockMvc/WebTestClient không đủ để kiểm chứng cấu hình decoder?

**Đáp án:** Helper tạo authentication trực tiếp trong test, không gửi một Bearer token thật qua decoder để kiểm tra signature, issuer, audience, JWK, expiry. Cần test HTTP integration hoặc decoder riêng với token thật/issuer test.

**8.** Một request không có Bearer header nhưng có cookie web hợp lệ vẫn POST thành công lên `/api/orders`. Điều này nói gì về quyết định miễn CSRF?

**Đáp án:** API **không thực sự bearer-only**, vì có credential browser tự gửi được chấp nhận. Cần loại bỏ cookie fallback hoặc thiết kế CSRF cho đường cookie, kiểm tra lại chain/matcher/gateway.

**9.** Nếu SPA giữ access token trong memory thì XSS không thể chiếm quyền được nữa, đúng hay sai?

**Đáp án:** Sai. XSS cùng origin có thể sử dụng khả năng JS hợp lệ để gửi request dưới token đang có hoặc tiếp cận token tùy triển khai. Memory-only thay đổi vòng đời/lưu trữ, không tự chống XSS.

**10.** Một SPA có Bearer access token, còn `POST /auth/refresh` dựa trên refresh token cookie HttpOnly. Có thể miễn CSRF cho refresh vì API nghiệp vụ bearer-only không?

**Đáp án:** Không được suy ra như vậy. Refresh endpoint nhận **cookie tự gửi**, cần đánh giá CSRF/Origin/Fetch Metadata, token rotation/abuse và browser policy riêng.

**11.** Nếu client đưa token qua `?access_token=...`, vấn đề chính là gì?

**Đáp án:** Token có thể lộ qua URL history, proxy logs, analytics, caches hoặc liên kết được chia sẻ. Nên dùng header Authorization và không bật query resolver trừ khi có lý do/bảo vệ được đánh giá cụ thể.

**12.** API trả `403` với token hợp lệ; có phải do CSRF không?

**Đáp án:** Không nhất thiết. Với Bearer-only chain đã miễn CSRF, `403` thường có thể là thiếu authority/scope hoặc object-level authorization. Cần xem security chain và exception class, không suy đoán từ status.

**13.** Nên thêm CSP ở API JSON hay HTML SPA để giới hạn mã script của SPA?

**Đáp án:** Chính sách CSP chi phối **tài liệu mà browser tải và thực thi**; phải có trên HTML SPA ở origin frontend. API có các response headers riêng nhưng CSP trên JSON không tự bảo vệ HTML do CDN/Nginx cung cấp.

**14.** Có cần kiểm tra HTTP firewall và proxy khi một API dùng `securityMatcher("/api/**")` không?

**Đáp án:** Có. Request URI normalization, proxy rewriting và matcher quyết định chain nào được chọn. Nếu path bị viết lại sai, security policy có thể không áp dụng đúng route; cần test URL công khai và upstream.

**15.** Vì sao có thể chọn BFF thay vì SPA giữ access token?

**Đáp án:** BFF có thể giữ access/refresh tokens ở server và browser dùng cookie session cùng origin với BFF, giảm một số rủi ro token lộ trực tiếp cho JS. Nhưng browser→BFF **lại cần CSRF và session security**, cùng chống XSS/authorization.

## Kết luận

**API có client chủ động gửi bearer token** là mô hình bảo vệ tài nguyên trong đó client (SPA, mobile, CLI hoặc backend service) **tự đặt access token** trong header `Authorization: Bearer ...`. Với một **Resource Server thật sự bearer-only**, website attacker thông thường không thể khiến browser tự gắn Bearer token bí mật chỉ bằng form/điều hướng; vì vậy CSRF truyền thống dựa trên ambient credential thường **không phải lớp bảo vệ cần thiết ở chính nhóm endpoint đó**. Đây là một kết luận **có điều kiện**, không phải quy tắc “JWT/REST/SPA thì tắt CSRF”.

Spring Security **Servlet** sử dụng `SecurityFilterChain`, `HttpSecurity` và `oauth2ResourceServer()`; **Reactive/WebFlux** dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và reactive decoder. Với cả hai, phải xác minh issuer, signature/active status, audience, expiry, scopes và quyền theo tài nguyên, đồng thời tách chain web session/refresh cookie/BFF có cơ chế anti-CSRF riêng.

Nếu SPA khác origin gọi API, **CORS** cho phép browser thực hiện/read cross-origin requests và preflight phải được xử lý trước authentication. Nhưng CORS **không chặn người có token bị đánh cắp**, còn CSP/HSTS/HTTP firewall/cookie/session security đảm nhận các rủi ro khác. Giữ Bearer token khỏi log và URL, dùng HTTPS, chống XSS và quản lý vòng đời token là những yêu cầu cơ bản.

**Bằng chứng quan trọng nhất của quyết định miễn CSRF** không phải `csrf.disable()` có trong code, mà là **test request cookie-only không thể xác thực trên API**, cùng test Bearer token đúng/sai, scope, audience, preflight, session-web CSRF và **không có side effect trên request bị từ chối**. Đó là cách tích hợp các lớp phòng vệ của `SPRING_SECURITY_HTTP_PROTECTION` một cách kiểm chứng được.

## Tài liệu tham khảo

- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): bearer JWT validation, issuer, authorities và decoder.
- [Spring Security — OAuth2 Resource Server Opaque Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): token introspection.
- [Spring Security — OAuth2 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): Reactive JWT decoder và authentication.
- [Spring Security — OAuth2 Resource Server Opaque Tokens (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): Reactive opaque token introspection.
- [Spring Security — CORS Integration (Servlet)](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS filter order và allowlist.
- [Spring Security — CORS Integration (Reactive)](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS trên WebFlux.
- [Spring Security — Servlet OAuth2 Resource Server Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()` và kiểm thử Resource Server.
- [Spring Security — Reactive OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` với WebTestClient.
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): khi nào dùng CSRF, synchronizer token và cookie-based authentication.
- [Spring Security — CSRF Protection (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter` trên WebFlux.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, error response và bảo mật token.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE trong OAuth.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các lớp validation và tránh JWT confusion.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, Origin và credentialed requests.
- [MDN — Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `omit`, `same-origin` và `include`.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF threat model và token patterns.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): phòng vệ XSS bảo vệ token trong browser.
