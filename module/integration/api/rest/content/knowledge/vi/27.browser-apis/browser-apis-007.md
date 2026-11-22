# CORS là chính sách trình duyệt và phạm vi bảo vệ thực tế

Khi ứng dụng web gọi REST API ở một **origin khác**, trình duyệt phải áp dụng các quy tắc bảo vệ dữ liệu giữa những trang web. **CORS (Cross-Origin Resource Sharing)** là cơ chế để máy chủ chỉ định origin nào được phép đọc phản hồi của nó từ JavaScript chạy trong trình duyệt. Hiểu đúng CORS giúp xây dựng hợp đồng API HTTP, cấu hình Java/Spring Security và gỡ lỗi giữa frontend–backend mà không nhầm CORS với xác thực, phân quyền hay chống CSRF.

Điểm cốt lõi: **trình duyệt thực thi CORS; máy chủ công bố chính sách qua HTTP header**. Một phản hồi bị CORS từ chối vẫn có thể đã được máy chủ tạo ra. CORS chủ yếu kiểm soát khả năng **đọc phản hồi từ mã JavaScript ở origin khác**, không phải tường lửa bảo vệ endpoint trước mọi yêu cầu.

Sau bài học, người học có thể: phân biệt origin với site; dự đoán khi nào có preflight; cấu hình CORS an toàn cho REST API dùng Spring Security; nhận diện giới hạn của CORS trước CSRF, credential và client ngoài trình duyệt; thiết kế kiểm thử và quy trình chẩn đoán lỗi.

## 1. Nền tảng: same-origin policy và khái niệm origin

**Origin** gồm ba thành phần: **scheme + host + port**. Cổng mặc định được chuẩn hóa theo scheme; đường dẫn, query và fragment không thuộc origin.

Giả sử trang đang mở tại `https://app.example.com/dashboard`:

| URL đích | Cùng origin? | Lý do |
| --- | --- | --- |
| `https://app.example.com/api/orders` | Có | Cùng scheme, host và port mặc định 443 |
| `https://app.example.com:443/api/orders` | Có | Cổng 443 là mặc định của HTTPS |
| `https://api.example.com/v1/orders` | Không | Khác host |
| `http://app.example.com/api/orders` | Không | Khác scheme |
| `https://app.example.com:8443/api/orders` | Không | Khác port |
| `https://app.example.com/other?x=1` | Có | Khác path/query không làm thay origin |

**Same-origin policy (SOP)** là nhóm quy tắc của trình duyệt nhằm ngăn trang ở origin này tùy ý truy cập dữ liệu riêng ở origin khác. SOP không chặn mọi tương tác xuyên origin: trình duyệt từ lâu đã cho phép nhiều hoạt động như điều hướng liên kết, gửi form, tải ảnh hoặc nhúng một số tài nguyên theo quy tắc riêng. Trọng tâm của CORS là các **yêu cầu HTTP từ JavaScript như `fetch()`/`XMLHttpRequest` và quyền đọc phản hồi**.

**Origin khác site.** `https://app.example.com` và `https://api.example.com` là hai origin, dù thường được xem là *same-site* theo quy tắc cookie. Thuộc tính cookie `SameSite` xử lý *site*, không trực tiếp dùng khái niệm *origin* của CORS. Do đó không thể suy luận rằng “hai subdomain cùng công ty thì không cần CORS”.

## 2. CORS cho phép điều gì và không bảo vệ điều gì?

Hãy xét `https://app.example.com` gọi `https://api.example.com/api/v1/me`:

~~~mermaid
sequenceDiagram
    participant JS as JavaScript tại app.example.com
    participant B as Trình duyệt
    participant API as api.example.com
    JS->>B: fetch("https://api.example.com/api/v1/me")
    B->>API: GET /api/v1/me + Origin
    API-->>B: 200 JSON + Access-Control-Allow-Origin
    alt Origin được cho phép
        B-->>JS: Cho đọc status, headers được lộ và body
    else Origin bị từ chối
        B-->>JS: Lỗi CORS / fetch bị reject
        Note over API,B: Máy chủ có thể đã xử lý GET
    end
~~~

Máy chủ khai báo quyền đọc bằng `Access-Control-Allow-Origin` (ACAO). Ví dụ khi cho phép chính xác ứng dụng web:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin

{"id":"u-42","displayName":"Linh"}
~~~

Nếu phản hồi không có ACAO hợp lệ hoặc giá trị không khớp origin của trang, trình duyệt **không đưa nội dung phản hồi cho JavaScript**. Developer Tools vẫn có thể hiển thị request đã chạy, response có HTTP 200 hoặc 403 và thông báo CORS. Ở phía JavaScript, `fetch()` thường bị reject với lỗi mạng kiểu `TypeError: Failed to fetch`; ứng dụng không lấy được status/body của phản hồi bị CORS chặn.

Phạm vi thực tế:

- **CORS không xác thực người dùng:** ACAO không chứng minh ai đang gửi request. Origin được phép đọc chưa chắc người dùng có quyền đọc tài nguyên; API vẫn cần session hoặc access token và kiểm tra quyền trên từng resource/tenant.
- **CORS không phải giới hạn truy cập mạng:** `curl`, Postman, mobile app, server-to-server client hay script tự viết không chịu chính sách CORS của trình duyệt. Client như vậy có thể tự tạo header `Origin`; backend không được xem Origin là danh tính đáng tin.
- **CORS không tự chống CSRF:** một request đơn giản từ trang độc hại có thể được gửi đến server (ví dụ qua HTML form), dù trang độc hại không được đọc phản hồi. Nếu request làm thay đổi trạng thái và cookie được gửi kèm, tác dụng phụ có thể đã xảy ra.
- **CORS không thay TLS/CSP/authorization:** HTTPS bảo vệ kênh truyền; Content Security Policy (chẳng hạn `connect-src`) ràng buộc nơi *trang nguồn* được kết nối; authentication/authorization quyết định API trả dữ liệu cho ai.

Nói cách khác, **CORS là một lớp bảo vệ đọc dữ liệu giữa các origin trong trình duyệt**. Chính sách server-side như RBAC, kiểm tra chủ sở hữu dữ liệu, chống CSRF, rate limit và validation vẫn cần thiết.

## 3. Yêu cầu CORS không có preflight

Không phải mọi request xuyên origin đều có bước `OPTIONS`. Với các request thỏa điều kiện *CORS-safelisted* (thường gọi “simple request”), trình duyệt có thể gửi request chính ngay, sau đó kiểm tra header CORS của phản hồi.

Về cơ bản, phương thức phải là `GET`, `HEAD` hoặc `POST`; các request header do mã nguồn thiết lập phải nằm trong tập được phép cùng những hạn chế giá trị tương ứng. Với `POST`, ba MIME type thường gặp có thể thuộc nhóm cho phép là `application/x-www-form-urlencoded`, `multipart/form-data` và `text/plain`. **`Content-Type: application/json` không thuộc nhóm safelisted**, nên POST JSON thông thường có preflight. Quy tắc trình duyệt còn có các điều kiện khác về header và giá trị header; đừng chỉ nhìn HTTP method để kết luận.

Ví dụ một GET không dùng header tùy chỉnh:

~~~javascript
const response = await fetch("https://api.example.com/api/v1/catalog");
if (!response.ok) {
  throw new Error("API trả lỗi HTTP " + response.status);
}
const catalog = await response.json();
~~~

Request:

~~~http
GET /api/v1/catalog HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin

{"products":[{"id":"P-01","name":"Sách Java"}]}
~~~

Đối với API dữ liệu công khai không dùng credentials, ACAO có thể là `*`. Nhưng dữ liệu “công khai” phải được quyết định theo hợp đồng và chính sách truy cập, không dựa vào việc client có hay không gửi cookie ở một lần gọi cụ thể.

Lưu ý về request `no-cors`: đặt `mode: "no-cors"` **không phải cách sửa lỗi CORS**. Trình duyệt hạn chế method/header có thể gửi và trả về một *opaque response* mà JavaScript không đọc được body hay status thực. Cách này chỉ phù hợp khi không cần đọc phản hồi, chẳng hạn một số luồng tải tài nguyên.

## 4. Preflight: hỏi quyền trước khi gửi request chính

Khi request dùng phương thức hoặc header nằm ngoài nhóm safelisted, trình duyệt thường gửi **preflight** bằng `OPTIONS`. Preflight hỏi server có cho phép **origin, phương thức và danh sách request header dự kiến** hay không; nếu không hợp lệ, request chính sẽ không được trình duyệt gửi.

Ví dụ JavaScript tại `https://app.example.com` tạo đơn hàng bằng JSON, đồng thời gửi token CSRF mà ứng dụng đã cấp hợp lệ:

~~~javascript
const csrfToken = /* token do ứng dụng cấp */ "...";

const response = await fetch("https://api.example.com/api/v1/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({
    items: [{ sku: "BOOK-42", quantity: 1 }]
  })
});

if (!response.ok) {
  throw new Error("Tạo đơn hàng thất bại: " + response.status);
}
~~~

Trình duyệt gửi preflight, **chưa gửi JSON body**:

~~~http
OPTIONS /api/v1/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Server có thể phản hồi:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PATCH, DELETE
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN, Authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Khi được cho phép, trình duyệt mới gửi request chính:

~~~http
POST /api/v1/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token>
Cookie: SESSION=<session-id>

{"items":[{"sku":"BOOK-42","quantity":1}]}
~~~

Response cho phép trang đọc kết quả:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ORD-42
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: Location, ETag
Vary: Origin

{"id":"ORD-42","status":"CREATED"}
~~~

Chi tiết cần nhớ:

1. `Access-Control-Request-Method` và `Access-Control-Request-Headers` nằm ở **preflight request**; `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` nằm ở **response**. Danh sách allow không phải thứ client tự gán để vượt bảo vệ.
2. **Preflight CORS thông thường không kèm credentials như cookie/session**. Nếu backend đòi xác thực ngay ở `OPTIONS` và trả 401/403, request chính có thể không bao giờ được gửi. Cấu hình xử lý CORS ở trước kiểm tra xác thực của Spring Security.
3. `Access-Control-Max-Age` cho phép trình duyệt cache kết quả preflight trong thời gian hữu hạn; trình duyệt có thể áp giới hạn riêng. Giá trị này không biến thành cache authorization hoặc session.
4. **Preflight thành công chưa phải quyền truy cập dữ liệu.** API vẫn phải kiểm tra token, CSRF khi cần, quyền thao tác, schema và trạng thái tài nguyên của **request chính**.
5. Một preflight có thể không xuất hiện vì đã được cache. Thử lại trong profile riêng hoặc xóa cache liên quan để điều tra; không suy ra “không có CORS” chỉ vì tab Network không thấy OPTIONS.

Nếu request chính trả 401/403/422/500, phản hồi lỗi cũng nên có CORS header thích hợp cho origin được phép. Nếu không, frontend chỉ thấy lỗi CORS và mất thông tin lỗi HTTP hữu ích. Không tiết lộ nội dung lỗi nhạy cảm cho origin bị từ chối.

## 5. Credentials, cookie, dấu `*` và ranh giới bảo mật

`fetch()` dùng chế độ credentials mặc định `same-origin`: với yêu cầu xuyên origin, browser thường không gửi cookie của origin API. Để gửi cookie/session trong một request CORS, client dùng `credentials: "include"`; server cần phản hồi **đồng thời**:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

**Không dùng** `Access-Control-Allow-Origin: *` khi request có credentials mode `include`: browser sẽ chặn quyền đọc phản hồi dù server có trả 200. `Access-Control-Allow-Credentials` phải có giá trị chính xác `true` để trình duyệt cho JS đọc phản hồi của request credentialed. Không dùng các danh sách origin ngăn bằng dấu phẩy trong ACAO; mỗi phản hồi cho phép tối đa một origin hoặc `*` theo quy tắc tương ứng.

Cookie còn phải vượt qua *chính sách cookie* của trình duyệt: domain/path, `Secure`, `HttpOnly`, `SameSite` và các hạn chế cookie bên thứ ba. Với bối cảnh **cross-site** thực sự, cookie dùng xuyên site thường cần `SameSite=None; Secure` nếu trình duyệt cho phép; một số trình duyệt hoặc chế độ riêng tư có thể vẫn chặn cookie bên thứ ba. Thiết lập CORS đúng **không buộc trình duyệt gửi cookie** và không tự tạo phiên đăng nhập.

So sánh các cấu hình:

| Cấu hình phản hồi | Kết quả / rủi ro |
| --- | --- |
| `Access-Control-Allow-Origin: *`, không dùng credentials | Hợp lý cho API thực sự công khai; vẫn cần xử lý tải và validation |
| ACAO là một origin cụ thể và `Access-Control-Allow-Credentials: true` | Phù hợp ứng dụng web có session nếu origin được phép được chọn cẩn thận |
| ACAO `*` cùng `Access-Control-Allow-Credentials: true` | Không hợp lệ để JS đọc response khi credentials mode là `include` |
| Phản chiếu mọi `Origin` thành ACAO và bật credentials | **Nguy hiểm:** trang bên thứ ba có thể đọc dữ liệu người dùng khi browser gửi thông tin đăng nhập |
| Chỉ whitelist `https://app.example.com` nhưng API không kiểm tra quyền | Vẫn có lỗ hổng phân quyền; CORS không thay thế xác thực/authorization |

Với session hoặc cookie, tuyệt đối tránh cấu hình “lấy `Origin` của request và trả lại y hệt” cho mọi website. Chỉ phản hồi origin đã được cho phép bằng chính sách server-side; ưu tiên đối chiếu chính xác **scheme, host, port**. Origin có dạng `null` có thể xuất hiện trong một số ngữ cảnh sandboxed/file/data; không đưa `null` vào whitelist mặc định. `Origin` thiếu hoặc bị giả mạo bởi non-browser cũng không thể hiện quyền truy cập.

Khi dùng Bearer token trong header `Authorization`, header này thường làm request phát sinh preflight. Việc kiểm tra chữ ký token, scope và quyền truy cập resource vẫn là trách nhiệm của API. Lưu trữ token ở đâu và cách chống XSS là vấn đề riêng; CORS không bảo vệ token nếu origin hợp lệ của ứng dụng đã bị XSS.

## 6. Vì sao CORS không thay thế chống CSRF?

Giả sử người dùng đã đăng nhập tại `https://api.example.com` bằng session cookie. Trang độc hại ở `https://evil.example.net` có thể thử gửi form:

~~~html
<form action="https://api.example.com/api/v1/profile/email"
      method="POST">
  <input name="email" value="attacker@example.net">
</form>
<script>document.forms[0].submit();</script>
~~~

Nếu endpoint cho phép định dạng form và browser gửi cookie theo chính sách hiện hành, thao tác có thể thực sự đến server. CORS có thể ngăn trang độc hại **đọc phản hồi**, nhưng không bảo đảm form POST bị chặn. Việc cookie có được gửi còn phụ thuộc SameSite và chính sách trình duyệt; không được dựa hoàn toàn vào CORS để quyết định.

Đối với endpoint thay đổi trạng thái khi dùng cookie/session, thiết kế phòng thủ gồm:

- CSRF token được sinh, gắn với phiên/ngữ cảnh tin cậy và **được server xác minh** đối với request thay đổi trạng thái; có thể kết hợp kiểm tra `Origin` hoặc `Referer` phù hợp.
- Cookie được đặt `SameSite`, `Secure`, `HttpOnly` theo mục đích; có thêm chống XSS.
- Phương thức `GET`/`HEAD` không gây thay đổi trạng thái nghiệp vụ; không để việc chỉ tải ảnh hoặc mở liên kết kích hoạt chuyển tiền, xóa dữ liệu, v.v.
- CORS whitelist chính xác, không cho phép origin tùy ý; preflight là một lớp bổ sung nhưng không được xem như biện pháp CSRF duy nhất.

**Ví dụ phản chứng:** bật CORS chỉ cho `https://app.example.com` nhưng cấu hình Spring Security `csrf().disable()` cho ứng dụng dùng cookie session. Website lạ có thể không đọc kết quả nhưng vẫn có cơ hội tạo side effect qua đường request được browser cho phép. Ngược lại, API thuần Bearer token do client chủ động thêm vào header và không dùng cookie tự gửi có đặc tính CSRF khác; cần đánh giá cơ chế credential thực tế trước khi quyết định cấu hình CSRF.

## 7. Cấu hình CORS có kiểm soát trong Java/Spring Security

Ví dụ sử dụng **Spring Boot 3.x / Spring Security 6.x** với API `/api/**`. Ứng dụng web chạy tại `https://app.example.com`, có session cookie, chỉ cho đọc/ghi từ origin chính thức. Chúng ta cấu hình CORS qua `CorsConfigurationSource` và cho Spring Security xử lý CORS trước xác thực:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            // Giữ bảo vệ CSRF cho phiên dùng cookie.
            // Ứng dụng còn cần luồng cấp và kiểm tra CSRF token cho SPA.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/v1/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll());
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("Location", "ETag"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Vì sao từng thiết lập cần thiết:**

1. `http.cors(...)` tích hợp xử lý CORS vào filter chain của Spring Security. Preflight **không cần gửi cookie để được CORS đánh giá**, nên cần qua bước CORS trước khi cơ chế yêu cầu xác thực của ứng dụng chặn mọi `OPTIONS`.
2. `setAllowedOrigins` giới hạn đúng origin tin cậy; không dùng `"*"` khi `allowCredentials=true`. Phải cập nhật whitelist theo môi trường (dev/staging/prod), tránh vô tình cho phép toàn bộ origin trong production.
3. `setAllowedMethods` liệt kê **phương thức thực tế được gọi**, không phải cơ chế phân quyền đối với phương thức đó. Spring vẫn xử lý `OPTIONS` preflight; không cần coi OPTIONS là thao tác nghiệp vụ.
4. `setAllowedHeaders` kiểm soát những request header JavaScript được phép gửi trong request CORS có preflight. Nếu frontend thêm `X-Request-ID` hoặc `Idempotency-Key`, cần quyết định rõ việc có cho phép header tương ứng hay không.
5. `setExposedHeaders` làm `Location`/`ETag` đọc được từ JavaScript. Một số response header thông dụng được browser cho đọc sẵn, nhưng `Location` không mặc định thuộc nhóm đó. `Set-Cookie` là response header bị cấm đọc trực tiếp từ JS, kể cả khi thêm vào `Access-Control-Expose-Headers`.
6. `setAllowCredentials(true)` cho phép trình duyệt đọc response của request credentialed nếu các điều kiện khác hợp lệ. Nó **không** cấp session hoặc quyền của người dùng.
7. `registerCorsConfiguration("/api/**", ...)` gắn cấu hình theo đường dẫn. Nếu API còn endpoint ở `/actuator/**` hoặc đường dẫn khác, cần quyết định chính sách riêng, không mở rộng thiếu chủ đích.

Nếu hệ thống đã dùng `@CrossOrigin` hoặc `WebMvcConfigurer#addCorsMappings`, cần thống nhất nguồn cấu hình với Spring Security, tránh hai tầng trả header mâu thuẫn hay trùng lặp. Ở reverse proxy/gateway, tránh vừa trả ACAO cố định vừa để backend trả ACAO khác; browser thường từ chối phản hồi có nhiều giá trị ACAO không hợp lệ.

Với API auth dùng cookie, đoạn code chỉ là **cấu hình CORS và khung bảo mật**. Để SPA gửi `X-CSRF-TOKEN` thành công, ứng dụng phải cung cấp luồng cấp token hợp lệ và kiểm tra token theo cơ chế CSRF đang sử dụng. Nếu API dùng JWT Bearer hoàn toàn stateless, hãy thiết kế cấu hình authentication/CSRF riêng dựa trên threat model; không sao chép `csrf().disable()` chỉ để làm hết lỗi 403.

## 8. Cache, lỗi HTTP, redirect và vận hành

### 8.1. CORS header và cache dùng chung

Khi API phản hồi ACAO khác nhau theo `Origin`, cache trung gian phải biết response phụ thuộc vào Origin. Dùng:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
~~~

Nếu tạo phản hồi preflight phụ thuộc vào `Access-Control-Request-Method` hoặc `Access-Control-Request-Headers`, thêm các trường đó vào `Vary` khi phù hợp. Kiểm tra cách CDN/reverse proxy cache response; không để ACAO của một origin bị dùng nhầm cho origin khác. `Access-Control-Max-Age` là cache chính sách preflight ở browser, **không giống** `Cache-Control` của dữ liệu API.

### 8.2. Phân biệt lỗi CORS với lỗi API

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| `OPTIONS` nhận 401 | CORS filter có chạy trước authentication không? Gateway có chặn OPTIONS không? |
| `OPTIONS` nhận 403 | Origin, method, request header có khớp whitelist không? |
| Request chính 200 nhưng `fetch` báo lỗi CORS | Phản hồi có ACAO khớp Origin không? Credentials có dùng `*` không? Header có bị proxy thay? |
| POST trả 403 khi preflight thành công | Có thể do thiếu token CSRF, thiếu quyền, sai session hoặc policy nghiệp vụ |
| Chạy được qua Postman nhưng hỏng trên browser | Postman không thực thi CORS như browser; kiểm tra Origin/preflight/response headers |
| Có cookie trong trình duyệt nhưng request không mang cookie | `credentials` mode, domain/path, `SameSite`, `Secure`, chính sách third-party cookie |
| GET được nhưng POST JSON không được | POST JSON thường preflight; kiểm tra OPTIONS, method và Content-Type |
| Lỗi CORS chỉ khi API trả 4xx/5xx | Đường xử lý lỗi/gateway có trả CORS header cho origin được phép không? |

Một số redirect ở login, API gateway hoặc từ HTTP sang HTTPS làm quy trình preflight khó chẩn đoán. Đặt URL API đúng scheme và đường dẫn ngay từ client; không trông chờ redirect cho `OPTIONS`. Nếu route chỉ chấp nhận `POST` và vô tình chuyển `OPTIONS` sang trang login, cần sửa thứ tự middleware và xử lý route, không mở public endpoint nghiệp vụ để “sửa CORS”.

### 8.3. Các header bảo vệ khác

CORS không đồng nghĩa với `Cross-Origin-Resource-Policy (CORP)`, `Cross-Origin-Embedder-Policy (COEP)`, `Cross-Origin-Opener-Policy (COOP)` hay CSP. Chúng có mục đích khác nhau: quy định khả năng nạp/nhúng tài nguyên, cô lập ngữ cảnh duyệt web hoặc giới hạn hành vi của trang nguồn. Không bật các header tùy ý để sửa lỗi CORS; phải thiết kế cho đúng ứng dụng.

## 9. Kiểm thử CORS từ HTTP đến trình duyệt

**Bước 1 — Kiểm tra phản hồi preflight** bằng một HTTP client; đây là test cấu hình server, chưa chứng minh browser có thể đọc response:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/v1/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Kỳ vọng server cho phép đúng origin, POST, headers cần dùng và `Access-Control-Allow-Credentials: true`. Gửi lại preflight với `Origin: https://evil.example.net`: server không được cho origin đó quyền đọc. Một lệnh `curl` đặt `Origin` bất kỳ **không cho thấy** browser có chặn hay không.

**Bước 2 — Kiểm thử Spring MVC/Security** trên cấu hình đã tạo (minh họa với `MockMvc`):

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void approvedOriginCanPreflightPostJson() throws Exception {
    mockMvc.perform(options("/api/v1/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
        .andExpect(status().isOk())
        .andExpect(header().string("Access-Control-Allow-Origin",
                "https://app.example.com"))
        .andExpect(header().string("Access-Control-Allow-Credentials", "true"));
}

@Test
void rejectedOriginCannotPreflight() throws Exception {
    mockMvc.perform(options("/api/v1/orders")
            .header("Origin", "https://evil.example.net")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers", "content-type"))
        .andExpect(status().isForbidden());
}
~~~

Đoạn test giả sử `mockMvc` được inject từ test context có cấu hình Security/CORS ở trên, và `@Test` là JUnit Jupiter. Trên Spring Security/CORS processor mặc định, preflight được chấp nhận thường trả 200; nếu hệ thống chủ động trả 204, điều chỉnh assertion theo hợp đồng thực tế. Test từ chối origin thường nhận 403 từ CORS processor; bảo đảm phân biệt với 403 do authorization.

**Bước 3 — Kiểm thử trên hai origin thật** bằng browser automation hoặc trang frontend dev: mở trang từ `https://app.example.com` gọi sang `https://api.example.com`, quan sát Network, cookies, OPTIONS và Console. Các ca cần có:

| Ca | Kỳ vọng |
| --- | --- |
| GET công khai từ origin được phép | JavaScript đọc được JSON và status |
| POST JSON từ origin được phép | Preflight hợp lệ; request chính vẫn phải qua CSRF và authorization |
| POST từ origin không được phép | Preflight thất bại hoặc phản hồi bị chặn đọc; không suy luận rằng server chưa nhận request nếu đó là simple request |
| ACAO `*` trong request `credentials: "include"` | Browser không cho đọc phản hồi |
| Request credentialed không có session hợp lệ | 401/403 nghiệp vụ; với origin được phép, frontend đọc được phản hồi lỗi theo CORS |
| Request có session nhưng thiếu CSRF token | 403 từ cơ chế chống CSRF nếu endpoint cần token |
| Preflight đã cache | Có thể không xuất hiện OPTIONS mới, nhưng chính sách vẫn được thực thi |
| API hoặc gateway trả 4xx/5xx | Frontend từ origin được phép nhận status/error response; không bị che bởi lỗi CORS giả |

Khi điều tra một lỗi, hãy nhìn **từng request riêng**: `OPTIONS` có được gửi không, status/header của OPTIONS là gì, request chính có diễn ra không, response có ACAO/ACAC/Vary như mong đợi không, cookie có thực sự đi kèm và cuối cùng có lỗi authentication/CSRF/permission hay không. Không giải quyết lỗi 401 hoặc 403 bằng cách mở `Access-Control-Allow-Origin: *`.

## 10. Tình huống thiết kế và bài tập

**Tình huống A — Dashboard và API tách origin.** Giao diện tại `https://dashboard.example.com` đọc danh sách đơn hàng từ `https://orders.example.com`, người dùng dùng session cookie. Hãy vẽ luồng một GET và một PATCH JSON, ghi rõ request nào phải preflight, các header cần có, và nơi API thực thi authorization theo chủ sở hữu đơn hàng. Nếu frontend đọc `ETag` để dùng `If-Match` cho cập nhật có điều kiện, cần bổ sung những CORS header nào?

**Tình huống B — Phát hiện cấu hình nguy hiểm.** Reverse proxy phản hồi:

~~~http
Access-Control-Allow-Origin: https://evil.example.net
Access-Control-Allow-Credentials: true
~~~

vì tự động lặp lại bất kỳ `Origin` nào client gửi. Đánh giá rủi ro cho endpoint `GET /api/v1/me` dùng cookie. Đề xuất whitelist đúng origin và thiết kế test để xác nhận origin chưa đăng ký không đọc được thông tin người dùng.

**Tình huống C — Lỗi 403 bị gọi nhầm là CORS.** POST JSON từ SPA đã vượt qua preflight, request chính nhận 403 khi chưa gửi `X-CSRF-TOKEN`; Postman gọi được vì có bearer token. Hãy phân biệt cơ chế authentication giữa hai client, dự đoán lỗi CSRF và thiết kế sửa lỗi bảo đảm an toàn cho SPA dùng session. Không chọn giải pháp tắt CSRF chỉ vì frontend báo lỗi.

**Câu hỏi tự kiểm tra:**

1. Một HTML form của website khác có thể gửi POST dù không được CORS cho phép không? Nếu có, hệ quả đối với CSRF là gì?
2. Vì sao `Access-Control-Allow-Origin: *` không dùng được để cho JavaScript đọc response của request có `credentials: "include"`?
3. Preflight OPTIONS có phải mang cookie để API biết người dùng là ai không? Vì sao thứ tự CORS/Security filter quan trọng?
4. Vì sao chỉ kiểm tra `curl` hoặc Postman thành công chưa đủ chứng minh frontend gọi được API?
5. Nếu `https://app.example.com` và `https://api.example.com` cùng site nhưng khác origin, có cần CORS không? Thuộc tính cookie nào vẫn cần kiểm tra riêng?

**Đáp án định hướng:** (1) Có thể gửi request qua form/simple request; CORS không bảo vệ khỏi side effect, cần CSRF defense. (2) Browser cấm wildcard ACAO cho credentialed CORS response. (3) Preflight thông thường không có cookie, phải xử lý CORS trước authentication và kiểm tra quyền ở request chính. (4) Client ngoài trình duyệt không áp dụng CORS. (5) Có, vì khác host nên khác origin; vẫn cần xét `SameSite`, `Secure`, phạm vi cookie và chính sách trình duyệt. Với PATCH chứa `If-Match`, preflight cần cho phép request header `If-Match`; frontend muốn đọc `ETag` trong response thì server phải expose `ETag`.
