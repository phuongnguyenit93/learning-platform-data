# Thứ tự xử lý CORS, security filter và gateway

## 1. Bài toán và mục tiêu học tập

Trong module **INTEGRATION_API_REST**, thiết kế một API đúng theo resource, URI, phương thức và mã trạng thái HTTP là cần thiết nhưng chưa đủ để JavaScript trong trình duyệt gọi API từ origin khác. Request có thể bị chặn ở **CORS**, bị **security filter** từ chối hoặc bị **API gateway** xử lý trước khi tới controller. Ba lớp này có mục đích khác nhau, và thứ tự sai thường tạo lỗi khó hiểu: API gọi bằng curl thành công nhưng fetch báo CORS, hoặc OPTIONS bị trả 401 dù access token hoàn toàn hợp lệ.

Bối cảnh xuyên suốt:

- Giao diện SPA chạy tại **https://app.example.test**.
- REST API chạy tại **https://api.example.test** qua gateway; backend là **Spring Boot 3 / Spring Security 6**.
- Người dùng lấy danh sách đơn hàng bằng **GET /api/v1/orders** hoặc tạo đơn bằng **POST /api/v1/orders**.
- Request cần header **Authorization: Bearer ...**; API có chính sách quyền theo tenant và chủ sở hữu.

**Mục tiêu:**

1. Phân biệt **same-origin**, **cross-origin**, CORS và xác thực.
2. Mô tả chính xác đường đi của **preflight OPTIONS** và request thực qua browser, gateway, security filter và controller.
3. Cấu hình Spring Security/Spring MVC để CORS chạy trước authentication/authorization mà **không mở quyền trái phép**.
4. Phân tích tác động của cookie, credentials, CSRF, CORS response headers, cache và gateway errors.
5. Kiểm thử bằng HTTP, MockMvc và trình duyệt thật; đọc Network/console để tìm tầng gây lỗi.
6. Vận dụng cho REST API có OpenAPI, phân trang, ETag, xử lý lỗi và bảo mật đa tenant.

**Nguyên tắc chính:** **CORS không phải authentication hay authorization.** Nó là cơ chế để **trình duyệt** quyết định JavaScript từ origin nào được đọc response. Server vẫn phải kiểm token và quyền đối với resource ở **request thực**, kể cả khi response có CORS headers hợp lệ.

## 2. Origin, site và CORS khác nhau như thế nào?

**Origin = scheme + host + port**. Hai URL khác một thành phần là hai origin khác nhau:

| Giao diện | API đích | Cross-origin? |
| --- | --- | --- |
| https://app.example.test | https://app.example.test/api | Không |
| https://app.example.test | https://api.example.test/api | **Có**: khác host |
| http://localhost:3000 | http://localhost:8080 | **Có**: khác port |
| http://app.example.test | https://app.example.test | **Có**: khác scheme |
| https://app.example.test | https://app.example.test:8443 | **Có**: khác port |

**Same-site** (liên quan cookie/SameSite) và **same-origin** không đồng nghĩa. Hai subdomain app.example.test và api.example.test là **khác origin**, nhưng trong cấu hình thông thường có thể cùng site. Chính sách cookie, schemeful same-site, third-party cookie blocking và CORS phải được đánh giá riêng.

Một request cross-origin từ JavaScript thường có:

~~~http
Origin: https://app.example.test
~~~

Server có thể cho phép origin này bằng response header:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

**Access-Control-Allow-Origin không tạo phiên đăng nhập và không cấp permission documents:read.** Nếu request không có quyền, API vẫn phải trả 401/403, chỉ khác ở chỗ browser được phép cho JavaScript **nhìn thấy** nội dung/status của lỗi khi CORS được cấu hình đúng.

### 2.1. CORS chỉ áp dụng theo mô hình client phù hợp

- **Browser fetch/XHR** thực thi kiểm tra CORS; browser có thể không gửi request thực nếu preflight thất bại, hoặc gửi request rồi không cho JavaScript đọc response.
- **curl, Postman, Java HttpClient** không bị trình duyệt áp chính sách CORS. Chúng vẫn cần token và quyền API.
- **Origin** là một header do client gửi, có thể bị giả từ client không phải trình duyệt. Vì vậy **không coi Origin hợp lệ là bằng chứng caller đáng tin**.
- CORS không thay chống **CSRF**, chống **SSRF**, CSRF token, validation, kiểm quyền trên từng ID hoặc giới hạn rate/quota.

## 3. Khi nào trình duyệt gửi preflight?

Một số cross-origin requests được phép đi thẳng theo quy tắc **CORS-safelisted request**. Các request khác cần gửi **OPTIONS preflight** trước khi request thực được phát đi.

Ví dụ GET đơn giản không kèm header không thuộc safelist có thể không cần preflight:

~~~http
GET /api/v1/catalog HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

Nhưng request có **Authorization** hoặc POST gửi **Content-Type: application/json** thường kích hoạt preflight:

~~~http
OPTIONS /api/v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Đặc điểm của request preflight:

- Method thực tế của request kiểm tra là **OPTIONS**, không phải POST.
- **Access-Control-Request-Method** khai báo method browser muốn gửi tiếp.
- **Access-Control-Request-Headers** liệt kê các header không thuộc safelist mà browser dự định gửi; giá trị và thứ tự có thể được chuẩn hóa.
- Browser **không đính kèm access token Authorization vào preflight** chỉ vì request thực sẽ có token. Preflight cũng thường **không mang cookie phiên**.
- URL preflight thường cùng resource path với request thực; preflight không được tạo đơn hoặc chạy logic nghiệp vụ POST.

Phản hồi cho preflight hợp lệ có thể là **200** hoặc **204** tùy CORS processor:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PATCH,DELETE
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

**Chỉ dùng status 2xx chưa đủ.** Browser phải kiểm tra origin, method và requested headers có được cho phép không. Nếu thiếu/mismatch bất kỳ header cần thiết, browser chặn request thực.

### 3.1. Không phải request cross-origin nào cũng preflight

Cùng một API, nếu GET không có Authorization và chỉ dùng safelisted headers, browser có thể gửi ngay request thực. **Không có OPTIONS** trong Network panel không chứng minh CORS đã tắt hoặc cấu hình sai. Preflight cũng có cache riêng theo browser/network partition và max-age, khiến OPTIONS xuất hiện ở lần đầu nhưng không ở lần sau.

Một **simple request** vẫn chịu CORS trên **response thực**. Server trả 200 nhưng không có Access-Control-Allow-Origin hợp lệ thì browser vẫn chặn JavaScript đọc body.

## 4. Luồng chính xác: preflight khác request thực

~~~mermaid
sequenceDiagram
    participant B as Browser SPA
    participant G as Gateway
    participant C as CORS policy
    participant S as Security filters
    participant A as REST Controller

    B->>G: OPTIONS + Origin + ACR-Method/Headers
    G->>C: Route tới CORS processor hoặc tự xử lý
    C-->>G: 2xx + allow-origin/methods/headers
    G-->>B: Preflight response (không auth user)
    Note over B: Browser kiểm CORS và quyết định gửi request thực
    B->>G: POST + Authorization + JSON + Origin
    G->>C: Kiểm policy cross-origin
    C->>S: Validate JWT, CSRF nếu áp dụng
    S->>A: Chỉ khi request đã xác thực/được phép
    A-->>S: HTTP 201/400/403...
    S-->>C: Response
    C-->>G: Response có CORS headers nếu Origin hợp lệ
    G-->>B: Response thực, browser kiểm CORS
~~~

**Đây là luồng khái niệm:** gateway có thể tự xử lý preflight mà **không chuyển OPTIONS vào backend**; hoặc forward OPTIONS cho CORS filter trong backend. Cần xác định rõ **tầng nào là chủ sở hữu chính sách CORS** cho route, tránh gateway và backend cùng tự viết headers đối nghịch.

Hai điểm rất quan trọng:

1. **Preflight không phải request nghiệp vụ.** Nó cần được xử lý **trước authentication bắt buộc của request thực**. Nếu SecurityFilterChain đòi JWT cho mọi OPTIONS preflight, browser sẽ nhận 401/403 và **không gửi POST/GET thực**.
2. **Request thực vẫn qua authentication và authorization.** CORS cho phép origin không có nghĩa tenant/user được phép đọc hoặc ghi một đơn hàng cụ thể.

### 4.1. Gateway nên xử lý gì?

Gateway thường chịu trách nhiệm **routing, TLS termination, origin allowlist hoặc forward preflight, rate limiting và error translation**. Nếu gateway là điểm CORS chính:

- Với preflight hợp lệ: trả 2xx và các Access-Control-Allow-* thích hợp **trước kiểm bearer token người dùng**.
- Với request thực: kiểm CORS origin (nếu gateway quản lý), rồi chuyển qua authentication/authorization theo kiến trúc.
- Không tự chèn **Authorization** vào preflight; không mặc định preflight cần cookie.
- Route phải cho phép OPTIONS đến đúng handler CORS, kể cả khi route downstream chỉ khai báo GET/POST.
- Khi gateway từ chối 401/403/429 hoặc sinh 502/503/504, **response lỗi vẫn cần CORS headers phù hợp cho origin được phép**, nếu client cần đọc lỗi.
- Nếu forward OPTIONS tới Spring, không để gateway chặn trước vì thiếu token, API key hay CSRF token.
- Không copy Origin thành Access-Control-Allow-Origin một cách mù quáng; phải so allowlist chặt.

**Preflight từ origin bị từ chối** có thể được gateway trả 403/4xx hoặc response không chứa allow headers. Browser sẽ chặn; đó **không phải** lý do loại bỏ xác thực của request thực.

## 5. CORS được đặt trước security filter vì sao?

Ví dụ cấu hình sai:

~~~text
Browser OPTIONS /api/v1/orders
        |
        v
Gateway yêu cầu bearer token
        |
        +--> 401 Unauthorized
        |
        v
Không đến CORS processor -> Browser hủy POST
~~~

Hoặc gateway forward preflight nhưng Spring Security từ chối vì request OPTIONS **không có cookie/session hoặc Authorization**.

Cấu hình đúng có hai nhánh rõ:

~~~mermaid
flowchart TD
    A[HTTP request đến gateway] --> B{CORS preflight hợp lệ?}
    B -- Có --> C[CORS processor kiểm origin / method / headers]
    C --> D[Trả 2xx và CORS headers]
    B -- Không --> E[Route thực hoặc lỗi CORS]
    E --> F[Security filter / authentication]
    F --> G{Đã xác thực và có quyền?}
    G -- Không --> H[401/403 theo policy]
    G -- Có --> I[Controller / service / data ACL]
    I --> J[2xx hoặc 4xx/5xx nghiệp vụ]
    H --> K[Áp CORS response headers nếu origin được phép]
    J --> K
~~~

Trong backend Spring có **CorsFilter/CORS integration trước security authentication filters**. Bộ xử lý này sẽ kết thúc request preflight hợp lệ tại chỗ; với request thực, nó cho request đi tiếp và áp CORS headers lên response theo policy.

**Chỉ thêm permitAll cho OPTIONS chưa đủ.** Điều đó có thể tránh 401, nhưng browser vẫn không nhận được Access-Control-Allow-Origin/Methods/Headers đúng. Ngược lại, mở mọi OPTIONS không kiểm soát cũng không tạo ra API an toàn. Phải cấu hình **CORS processor thực sự** và xử lý preflight theo route.

### 5.1. Đừng tưởng CORS header là quyền truy cập

Tưởng tượng request GET của user A tới **/api/v1/orders/B**. Origin được phép và JWT của A hợp lệ, nhưng order B thuộc tenant khác. API phải từ chối **403 hoặc 404** theo chính sách privacy. Trả Access-Control-Allow-Origin không thể thay kiểm tra owner/tenant trong repository/service.

Tương tự, kiểm Origin ở gateway không có khả năng ngăn Java HttpClient độc hại gọi API từ máy chủ khác; đó là lý do cần xác thực, phân quyền, rate limits và auditing độc lập.

## 6. Spring Boot 3 + Spring Security 6: cấu hình tham chiếu

Ví dụ API **Bearer JWT thuần** không dùng cookie phiên để xác thực /api. Cấu hình CORS dựa trên **CorsConfigurationSource** cho route API, chính xác từng origin và từng method. Đoạn code dưới đây dùng các class Spring Framework/Security 6 và giả định dự án có OAuth2 Resource Server/JWT setup phù hợp.

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
            List.of("https://app.example.test"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type",
            "If-Match", "Idempotency-Key"));
        cors.setExposedHeaders(List.of(
            "ETag", "Location", "Retry-After"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf.disable()) // Chỉ đúng cho bearer-only API
            .sessionManagement(sm -> sm.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/v1/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Các import thường dùng: **CorsConfiguration**, **UrlBasedCorsConfigurationSource**, **CorsConfigurationSource**, **HttpSecurity**, **SecurityFilterChain**, **Customizer**, **SessionCreationPolicy**, **HttpMethod**, các annotation Spring; đoạn ví dụ không phải project độc lập. **JWT decoder/issuer/audience và policy role/tenant** vẫn phải cấu hình đúng ở ứng dụng.

**Giải thích các quyết định:**

- **.cors(withDefaults())** để Spring Security tích hợp CORS processing trước các security filters yêu cầu principal, dựa trên CorsConfigurationSource được cung cấp.
- **AllowedOrigins** là danh sách origin chính xác; không tự động cho mọi subdomain.
- **AllowedMethods/AllowedHeaders** phải bao những phương thức và header request thực sự dùng. Với request **Authorization + application/json**, preflight sẽ hỏi **authorization,content-type**.
- **setAllowCredentials(false)** phù hợp mô hình bearer header với fetch credentials không bao gồm cookie. **Authorization tự đặt bằng fetch header vẫn có thể được dùng khi credentials mode là omit**; credentials mode chủ yếu điều khiển ambient credentials như cookie.
- **ExposedHeaders** cho phép JavaScript đọc các response headers không CORS-safelisted như **ETag, Location, Retry-After**.
- **MaxAge** là thời gian browser có thể cache **kết quả preflight** theo giới hạn trình duyệt; không phải TTL dữ liệu GET.
- **CSRF disable chỉ hợp lý cho chain thật sự stateless, không dựa cookie tự gửi để xác thực.** Nếu bất kỳ API endpoint nào xác thực bằng session/cookie, cần thiết kế CSRF protection thích hợp thay vì copy cấu hình disable.

Nếu app có **nhiều SecurityFilterChain** (web login + API JWT), kiểm thứ tự **@Order**, securityMatcher và CORS config của từng chain. Một fallback chain bắt OPTIONS hoặc một proxy filter chạy trước Spring Security có thể làm hỏng preflight.

### 6.1. Spring MVC và @CrossOrigin

Spring MVC có thể khai báo **@CrossOrigin** hoặc cấu hình **WebMvcConfigurer#addCorsMappings**, nhưng nếu ứng dụng dùng Spring Security, CORS phải được **tích hợp với security filter chain** để preflight được xử lý trước authentication. Đừng mặc định controller annotation sẽ có cơ hội chạy nếu security filter chặn OPTIONS từ trước.

Khi vừa cấu hình **@CrossOrigin**, **global MVC**, **CorsFilter** và **gateway**, hãy xác định policy nào được kết hợp/ưu tiên. Đừng gửi hai header Access-Control-Allow-Origin có giá trị khác nhau hoặc thay đổi allowCredentials tùy tầng; một response với nhiều giá trị ACAO không hợp lệ cho browser.

## 7. Phân biệt request thực và lỗi authn/authz

Sau preflight thành công, browser gửi request thực:

~~~http
POST /api/v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{"items":[{"sku":"SKU-001","quantity":1}]}
~~~

Nếu token hợp lệ và caller đủ quyền:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/orders/33333333-3333-4333-8333-333333333333
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

{"id":"33333333-3333-4333-8333-333333333333","state":"CREATED"}
~~~

Nếu token hết hạn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

{"type":"about:blank","title":"Unauthorized",
 "status":401,"code":"TOKEN_INVALID"}
~~~

**Điểm mấu chốt:** API có thể trả **401 đúng** và đồng thời **CORS đúng**. Nếu 401 thiếu allow-origin, fetch có thể chỉ hiển thị lỗi CORS/TypeError và frontend không đọc được status/code để điều hướng login. Không vì muốn sửa CORS mà bỏ kiểm JWT hay đổi 401 thành 200.

Nếu user đã xác thực nhưng không được xem tài nguyên, service trả **403** hoặc **404** theo privacy policy. CORS chỉ làm frontend đọc được mã lỗi, không biến 403 thành 200.

### 7.1. Những status thường dễ bị nhầm

| Trường hợp | Tầng xử lý | Kết quả mong đợi |
| --- | --- | --- |
| Origin không được cho phép | CORS browser/gateway | Browser chặn, không đọc body |
| Preflight không được route | Gateway/CORS | 404/405 hoặc thiếu CORS headers, request thực không được gửi |
| Preflight bị yêu cầu token | Gateway/security | 401/403 trước CORS, request thực không được gửi |
| Request thực thiếu JWT | Security filter | **401**, có CORS headers cho origin được phép |
| JWT đủ nhưng thiếu object permission | Service/authorization | **403/404**, có CORS headers |
| Request body sai | MVC validation | **400/422** theo hợp đồng, có CORS headers |
| Upstream không trả kịp | Gateway | **504**, nếu origin được phép nên có CORS headers |
| Backend làm hỏng response | Gateway/app | **502/5xx**, lỗi an toàn và CORS nhất quán |

**Gateway và Spring Security có thể trả response trước khi controller chạy**, nên chỉ viết @RestControllerAdvice không bảo đảm mọi lỗi có cùng CORS/Problem Details.

## 8. Credentials, cookies, SameSite và CSRF

Có hai mô hình đăng nhập web thường gặp; thứ tự CORS/security giống về nguyên tắc nhưng khác yêu cầu credentials và phòng vệ CSRF.

| Mô hình | Client gửi gì? | CORS | CSRF |
| --- | --- | --- | --- |
| **Bearer token trong Authorization header** | JS gắn token trực tiếp vào từng request | AllowedHeaders phải cho Authorization; có thể dùng credentials: omit | Khi không có credential tự động gửi, API bearer-only có thể không cần CSRF token; phải kiểm mọi cơ chế auth khác |
| **Session/cookie authentication** | Browser tự gửi Cookie nếu cookie policy và fetch cho phép | credentials: include; ACAO phải là origin cụ thể và ACAC: true | **Cần CSRF protection** cho unsafe methods khi phụ thuộc cookie/session |
| **Hỗn hợp cookie + bearer** | Có cả token gắn tay và cookie tự gửi | Áp quy tắc credentials cho cookie | Không tắt CSRF chung vì một phần app dùng JWT |

Ví dụ request cross-origin gửi cookie:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/v1/profile",
  {
    method: "GET",
    mode: "cors",
    credentials: "include"
  }
);
~~~

Để JavaScript đọc response khi **credentials mode = include**, browser yêu cầu:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không dùng Access-Control-Allow-Origin: \*** với request có credentials. **Access-Control-Allow-Credentials** có giá trị đúng là **true**; không có ý nghĩa đặt false như một permission. Với phản hồi credentialed, Access-Control-Allow-Origin phải là **một origin cụ thể được phép**, không phải danh sách phân tách dấu phẩy hoặc phản chiếu Origin vô điều kiện.

Cookie cross-site có thể yêu cầu **SameSite=None; Secure** và HTTPS; nhưng chính sách cookie của browser, third-party blocking/partitioning và cùng-site hay khác-site vẫn quyết định cookie có được gửi hay không. **CORS allow credentials không buộc browser phải gửi cookie**.

### 8.1. CORS không chặn tấn công CSRF

Nếu user đang đăng nhập bằng session cookie, một trang độc hại có thể kích hoạt các loại request mà browser cho phép gửi, ví dụ form POST. Dù trang đó **không đọc được response vì CORS**, server vẫn có thể xử lý side effect nếu thiếu kiểm soát CSRF.

Biện pháp cho cookie-based API: CSRF token được kiểm server-side, SameSite cookie hợp lý, kiểm Origin/Referer như lớp bổ sung khi phù hợp, và authorization cho từng thao tác. Nếu dùng custom header **X-CSRF-Token**, preflight có thể cần **Access-Control-Allow-Headers: X-CSRF-Token**; cho phép header đi qua CORS **không thay việc xác minh token**.

**Không sao chép .csrf(disable()) từ bearer-only chain sang website dùng session cookie.** Tách SecurityFilterChain hoặc điều chỉnh CSRF matcher đúng cơ chế xác thực. Với app cross-origin, cân nhắc cách frontend đọc/lấy CSRF token an toàn và cookie attributes nhất quán.

### 8.2. Origin null, wildcard và allowlist

**Origin: null** có thể xuất hiện từ sandboxed documents, file:// hoặc các opaque origins; đừng cho phép mặc định trong API có dữ liệu nhạy cảm. Cũng đừng xác thực origin bằng cách kiểm chuỗi **endsWith("example.test")** vì dễ chấp nhận sai domain tương tự. Dùng danh sách chính xác hoặc pattern có kiểm soát được review.

**Access-Control-Allow-Origin: \*** chỉ thích hợp khi API thực sự công khai với chính sách tương ứng và không dùng browser credentials. Đối với REST API có JWT/tenant data, origin allowlist chặt giúp giảm bề mặt tương tác từ trình duyệt, nhưng **không thay kiểm JWT/quyền** vì client ngoài trình duyệt có thể giả Origin.

## 9. Gateway, backend và CORS header: tránh hai nơi mâu thuẫn

Có hai kiến trúc thường dùng:

**Phương án A – Gateway sở hữu CORS public:** gateway kiểm origin, xử lý preflight và thêm allow headers vào mọi response cho origin hợp lệ, gồm error gateway. Backend không ghi duplicate ACAO cho chính public route ấy; vẫn kiểm authentication, role, tenant và resource.

**Phương án B – Backend sở hữu CORS:** gateway chuyển Origin, Access-Control-Request-* và OPTIONS tới backend, không yêu cầu bearer token trên preflight; Spring CorsFilter xử lý, response qua gateway không bị strip/replace CORS headers. Gateway vẫn cần chính sách cho error do nó tự phát trước backend.

Không có một thứ tự vật lý duy nhất bắt buộc cho mọi gateway/framework, nhưng phải đạt bất biến: **preflight có thể được xử lý mà không cần user token, actual request luôn được bảo vệ và lỗi có CORS headers đúng khi origin được phép**.

### 9.1. Lỗi do nhiều tầng cùng thêm header

Một số kết quả sai:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Origin: *
~~~

Hoặc:

~~~http
Access-Control-Allow-Origin: https://app.example.test, https://other.example.test
~~~

Browser không chấp nhận nhiều origin trong ACAO. Nếu gateway vừa thêm ACAO vừa backend thêm ACAO, cần **chọn một nơi chịu trách nhiệm** hoặc có cơ chế override/strip bảo đảm đúng **một giá trị**. CORS policy của gateway và backend cũng phải nhất quán về **allowed methods, headers, credentials và route**.

### 9.2. Gateway redirect, authentication và OPTIONS route

Các trường hợp thường xảy ra:

- Gateway chuyển **OPTIONS /api/v1/orders** tới trang login bằng **302/307** vì không có session: browser có thể thất bại ở preflight/redirect handling.
- API gateway áp **API key/JWT authentication trước CORS**; OPTIONS thiếu token → **401**.
- Ingress chỉ route GET/POST, không route OPTIONS → **404 hoặc 405**.
- Gateway thêm ACAO vào response 200 nhưng quên **429/502/504** → frontend chỉ thấy CORS error khi hệ thống gặp sự cố.
- Proxy rewrites path từ **/api/v1** sang **/v1** nhưng CORS config backend match nhầm **/api/** → preflight không có policy.
- WAF/rate-limiter coi mọi OPTIONS là traffic nguy hiểm và chặn → CORS lỗi theo tải.

Cần kiểm **path thực gateway nhận**, path downstream, thứ tự CORS/auth filters và nơi phát response; không “chữa” bằng cách bỏ kiểm JWT trên mọi method.

### 9.3. CORS error response có thể che lỗi thực

Khi gateway trả **502** mà không có ACAO, JavaScript thường chỉ thấy lỗi CORS/TypeError chứ không đọc được 502. DevTools **Network** có thể cho thấy response và headers; server/gateway logs theo request ID mới xác định nguyên nhân. Không kết luận từ console “CORS policy blocked” rằng backend có lỗi phân quyền.

## 10. Vary, CDN cache và expose response headers

CORS thường cần **Vary: Origin** nếu server trả ACAO động theo Origin. Với preflight, cache phải xét cả **Access-Control-Request-Method** và **Access-Control-Request-Headers**, vì request tới cùng URL có thể hỏi method/header khác nhau.

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Proxy/cache phải **giữ các thành phần Vary** khi thêm/ghép headers. Nếu cache preflight của origin A được tái dùng sai cho origin B hoặc cho một method không được phép, browser có thể nhận thông tin CORS không chính xác. Browser còn có **preflight cache riêng**, không đồng nhất với HTTP CDN cache.

**Access-Control-Max-Age** chỉ mô tả thời gian cache kết quả preflight, **không** có nghĩa cho phép cache dữ liệu đơn hàng. Response đơn hàng cá nhân nên theo **Cache-Control: private, no-store** khi phù hợp. CDN không được cache user-specific JSON chỉ bằng URL mà bỏ qua Authorization, tenant và quyền.

### 10.1. Headers JavaScript có thể đọc

Browser tự cho JavaScript đọc một số **CORS-safelisted response headers**, nhưng những header như **ETag, Location, Retry-After, X-Request-Id** thường cần được khai báo:

~~~http
Access-Control-Expose-Headers: ETag, Location, Retry-After, X-Request-Id
~~~

Ví dụ frontend tạo đơn và đọc Location:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/v1/orders",
  {
    method: "POST",
    mode: "cors",
    credentials: "omit",
    headers: {
      "Authorization": "Bearer " + accessToken,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      items: [{ sku: "SKU-001", quantity: 1 }]
    })
  }
);

if (!response.ok) {
  const problem = await response.json();
  throw new Error(problem.code || "ORDER_REQUEST_FAILED");
}
const location = response.headers.get("Location");
~~~

Request này thường tạo preflight vì có Authorization và JSON Content-Type. **credentials: omit không xóa Authorization mà ứng dụng tự gắn vào headers**; nó ngăn browser tự gửi ambient credentials như cookie. Nếu response có Location nhưng thiếu **Access-Control-Expose-Headers: Location**, frontend có thể nhận **null** khi đọc header dù request thành công. Location vẫn phải được server tạo an toàn, tránh tin unvalidated Host/Forwarded từ client.

**ExposedHeaders không cấp quyền lấy resource ở Location**. Request GET tiếp theo tới Location vẫn phải qua JWT và authorization của tài nguyên mới.

## 11. Kiểm thử với curl: tách preflight và actual

curl không thực thi CORS, nhưng có thể mô phỏng preflight để kiểm chính xác gateway và Spring đã trả headers nào.

~~~bash
curl -i -X OPTIONS \
  'https://api.example.test/api/v1/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

**Kỳ vọng:** 2xx; đúng **Access-Control-Allow-Origin**, cho phép **POST** và các headers đã hỏi; **không cần Bearer token**. Không bắt buộc là 204: Spring CORS processor có thể trả 200.

Thử origin lạ:

~~~bash
curl -i -X OPTIONS \
  'https://api.example.test/api/v1/orders' \
  -H 'Origin: https://attacker.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type'
~~~

**Kỳ vọng:** không có ACAO cho origin lạ; server có thể trả 403 theo policy. Không trả origin phản chiếu chỉ vì client gửi header.

Thử request thực không có token:

~~~bash
curl -i 'https://api.example.test/api/v1/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Accept: application/json'
~~~

**Kỳ vọng:** **401** từ security filter (nếu endpoint yêu cầu auth), **và** ACAO hợp lệ để JS thấy 401. Khi cung cấp token đúng nhưng tenant không có quyền, phải có **403/404**, không phải 200 chỉ vì origin được phép.

**Phải thử qua cả public gateway endpoint và backend test endpoint** khi điều tra: nếu backend OPTIONS đúng mà gateway OPTIONS 401, lỗi ở gateway. Tuy nhiên chỉ truy cập backend trực tiếp để test trong môi trường được phép, không mở port nội bộ ra Internet để debug.

## 12. MockMvc kiểm thứ tự CORS và Spring Security

Với project có **spring-security-test**, tạo integration test bật SecurityFilterChain:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CorsSecurityIntegrationTest {
    @Autowired MockMvc mvc;

    private static final String APP =
        "https://app.example.test";

    @Test
    void preflightDoesNotRequireBearerToken() throws Exception {
        mvc.perform(options("/api/v1/orders")
                .header(HttpHeaders.ORIGIN, APP)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type"))
            .andExpect(status().is2xxSuccessful())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, APP))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")));
    }

    @Test
    void actualRequestNeedsAuthEvenWithAllowedOrigin()
            throws Exception {
        mvc.perform(get("/api/v1/orders")
                .header(HttpHeaders.ORIGIN, APP))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, APP));
    }

    @Test
    void untrustedOriginIsNotAllowed() throws Exception {
        mvc.perform(options("/api/v1/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://attacker.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

Cần imports JUnit, MockMvc, HttpHeaders và Hamcrest **containsString**. Ví dụ giả định JWT resource server và **/api/v1/orders** đã được match bởi chain ở mục 6; filter phải thực sự được đưa vào test. Đừng chỉ test controller với security filters bị tắt, vì như vậy không đo được thứ tự preflight/security.

Bộ test cần thêm **actual request với JWT đúng nhưng thiếu quyền object** (403/404) và **actual request với JWT đủ quyền** (2xx). Kiểm response header CORS ở cả 401/403 và error 5xx của gateway bằng test ngoài MockMvc.

## 13. Kiểm thử trên trình duyệt thật và ma trận lỗi

MockMvc chứng minh Spring xử lý headers; nó không thể thay việc browser tự quyết định **có gửi request thực và có cho JS đọc response hay không**. Dùng Playwright hoặc browser integration test với hai origin thực và gateway/ingress gần production, quan sát DevTools Network.

| ID | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| C01 | GET cross-origin đơn giản | Response có ACAO; có thể không preflight |
| C02 | POST JSON + Authorization | OPTIONS trước POST khi chưa cache |
| C03 | OPTIONS không có token | 2xx và allow headers |
| C04 | OPTIONS origin lạ | Không được allow; browser không gửi POST |
| C05 | OPTIONS hỏi PATCH/If-Match | Chỉ method/header trong allowlist được cho phép |
| C06 | Actual request thiếu JWT | 401, JS đọc được status |
| C07 | JWT hợp lệ nhưng sai tenant/order ID | 403/404, không rò data |
| C08 | POST đúng token | 201 + Location, JS đọc được Location khi expose |
| C09 | Cookie credentials include | ACAO cụ thể, ACAC true, CSRF bảo vệ unsafe requests |
| C10 | ACAO wildcard + include | Browser chặn, test không chấp nhận cấu hình này |
| C11 | Gateway chặn OPTIONS | CI phát hiện 401/403/404/405 ở gateway |
| C12 | Gateway trả 429/502/504 | Error có CORS headers đúng origin |
| C13 | Gateway/backend cùng thêm ACAO | Không có duplicate/multiple ACAO |
| C14 | CDN cache preflight nhiều origins/methods | Vary đầy đủ, không reuse sai |
| C15 | Request Origin null/file sandbox | Không được mở quyền ngoài policy |
| C16 | Preflight cache hết hạn | Browser gửi OPTIONS lại và áp policy mới |
| C17 | GET ETag/304 cross-origin | Client đọc được ETag và 304 path phù hợp |
| C18 | CORS response đúng nhưng thiếu object ACL | Không coi CORS là authorization |
| C19 | Proxy rewrite và path /api | CORS policy match đúng URL tới service |
| C20 | Browser thiếu cookie do SameSite | Không nhầm cookie policy với CORS |

**Lưu ý test 304:** browser/fetch xử lý cache revalidation theo Fetch/HTTP caching; không được tự khẳng định script luôn nhận status 304 trong mọi chế độ cache. Kiểm ETag/expose và hành vi revalidation ở wire, gateway, cache tương ứng.

## 14. Chẩn đoán nhanh theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Điểm kiểm đầu tiên |
| --- | --- | --- |
| curl 200, browser báo CORS | Response không có ACAO/ACAC đúng | Origin và response headers |
| OPTIONS 401 nhưng POST không xuất hiện | Gateway/security filter chạy trước CORS | Preflight auth bypass đúng route |
| OPTIONS 200 nhưng POST vẫn không gửi | Thiếu allowed method/header/origin | ACR-Method/Headers so với allowlist |
| POST gửi rồi JS nhận TypeError | Actual response/error thiếu CORS | Network response và gateway errors |
| Chỉ lỗi khi token hết hạn | 401 thiếu CORS headers | Security entry point/response filter |
| Chỉ lỗi khi DB down | 5xx do gateway/app không có CORS | Gateway error path |
| Request với cookie không hoạt động | ACAC, credentials, SameSite/Secure/third-party blocking | Browser cookie policy và CSRF |
| ETag/Location header đọc thành null | Thiếu Access-Control-Expose-Headers | ExposeHeaders |
| Có hai ACAO | Gateway và Spring cùng gắn | Một nguồn chính sách và strip/override |
| Origin A được, origin B không | Policy, wildcard/pattern và cache Vary | Allowlist và Vary |
| Preflight phát lại bất thường | Max-Age/cache partition/browser limits | Không đánh đồng CDN vs browser preflight cache |
| Bypass bằng curl dù browser không được | CORS không phải kiểm quyền API | JWT, tenant/object ACL |

**Quy trình gỡ lỗi:** xem browser có gửi OPTIONS không → status/headers của OPTIONS tại gateway → có request thực không → status thực từ security/controller → CORS headers trên response thực/error → cookie/CSRF/cache nếu có. Đừng vô hiệu hóa bảo mật để “sửa CORS”.

## 15. Bài thực hành: SPA gọi Order API qua gateway

**Bối cảnh:** SPA tại **https://app.example.test** gọi Order API tại **https://api.example.test**. Gateway forward **/api/v1/orders** đến Spring Boot 3. API dùng bearer JWT, dữ liệu phân tách theo tenant; frontend cần tạo đơn, đọc **Location** và bắt lỗi token hết hạn.

**Đề bài (100 điểm):**

1. **CORS và thứ tự – 30 điểm.** Vẽ luồng OPTIONS preflight, request POST thực, gateway và Spring Security. Giải thích vì sao OPTIONS không có token nhưng POST phải có, sự khác nhau giữa CORS allowlist và JWT/tenant authorization. Cấu hình chỉ chấp nhận origin app, methods GET/POST/PATCH và headers Authorization/Content-Type/If-Match.
2. **Spring/gateway – 25 điểm.** Viết CorsConfigurationSource và SecurityFilterChain với cors integration; bảo đảm JWT + quyền theo order ID ở request thực. Chọn gateway hoặc backend làm điểm chịu trách nhiệm CORS, xử lý preflight và mọi error path, không phát hai ACAO.
3. **Browser và HTTP contract – 20 điểm.** Viết fetch POST JSON với Bearer token, khai báo expose Location/ETag/Retry-After. Giải thích lỗi browser khi Origin không được phép và tại sao curl vẫn gọi được API nếu có token. Nêu khác biệt nếu chuyển sang session cookie, credentials include và CSRF.
4. **Kiểm thử – 25 điểm.** Ít nhất tám ca gồm OPTIONS không token, unknown origin, actual 401, actual 403 do tenant, POST 201/Location, gateway 502/504, duplicate ACAO, cookie/CSRF và Vary preflight cache.

**Gợi ý triển khai:**

- Chọn **một chính sách origin allowlist chính**; gateway có thể xử lý OPTIONS hoặc forward đến Spring CorsFilter, nhưng không được bắt user JWT ở preflight.
- Ở Spring Security, cấu hình **cors(Customizer.withDefaults())** trước xác thực theo cơ chế tích hợp, chính sách REST chỉ cho đúng origins/methods/headers.
- Request POST phải qua Bearer validation, tenant-aware repository, validation và business rules. Trả **201 Created** với Location khi tạo thành công; **401/403/404** khi không đủ quyền.
- Frontend dùng fetch **mode: cors**, gửi Authorization trong request thực, đọc Location nhờ **Access-Control-Expose-Headers**; xử lý lỗi Problem Details an toàn.
- Tự động hóa kiểm thử ở cả **MockMvc** và **gateway/browser**. Không coi OPTIONS 2xx là đủ: assert cả preflight headers và thực tế JavaScript đọc được 401 hoặc 201.

**Tiêu chí hoàn thành:** trang không cần vô hiệu hóa bảo mật hay proxy tạm để hoạt động; preflight thành công với origin được phép nhưng request thực của user khác tenant vẫn bị từ chối; response thành công và thất bại đều có CORS headers phù hợp; origin lạ không đọc được response qua browser.

## 16. Checklist production và nguồn chuẩn

- [ ] Nêu rõ **origin** theo scheme/host/port; không nhầm same-site với same-origin.
- [ ] Phân biệt simple cross-origin request, preflight OPTIONS và actual request.
- [ ] Preflight được CORS xử lý **trước yêu cầu JWT/session của request thực**.
- [ ] Gateway định tuyến hoặc tự trả OPTIONS có chủ đích, không redirect sang login.
- [ ] Spring Security tích hợp CORS processor với chain tương ứng; không chỉ permitAll(OPTIONS).
- [ ] Request thực luôn được xác thực/phân quyền ở gateway/service theo policy, kể cả khi origin hợp lệ.
- [ ] Origin allowlist rõ, không wildcard hoặc reflected Origin nguy hiểm.
- [ ] Credentialed requests dùng ACAO cụ thể, ACAC true, cookie policy đúng; CSRF được bảo vệ.
- [ ] ACAO chỉ có **một giá trị** nhất quán giữa gateway/backend.
- [ ] CORS headers xuất hiện ở actual response 2xx và các lỗi 401/403/429/5xx từ các tầng liên quan.
- [ ] Vary Origin và Access-Control-Request-Method/Headers được giữ khi cache; không rò cache theo tenant.
- [ ] Expose ETag/Location/Retry-After khi JavaScript cần đọc, không lộ dữ liệu qua exposed headers.
- [ ] Đã test curl, MockMvc, gateway, browser thực và các tình huống token hết hạn, cookie, OPTIONS bị chặn.
- [ ] Có request ID/tracing để phân biệt lỗi CORS, auth, gateway và controller.

**Ghi nhớ:** **CORS quyết định JavaScript ở origin nào có thể đọc response; authentication xác định người gọi; authorization xác định người đó được làm gì; gateway quyết định request đi qua những tầng nào.** Với request preflight, CORS phải được phép trả lời trước khi đòi credentials của user. Với request thực, không tầng nào được bỏ qua JWT, quyền tenant hoặc validation chỉ để tránh một lỗi trình duyệt.

### Nguồn học tập

- **Fetch Standard / CORS protocol** (WHATWG): preflight, request credentials mode, response header exposure và CORS checks.
- **MDN Web Docs**: Cross-Origin Resource Sharing, HTTP access control, Fetch API và cookie credentials.
- **Spring Security Reference**: CORS integration, SecurityFilterChain, CSRF protection và OAuth2 Resource Server.
- **Spring Framework Reference**: Web MVC CORS, CorsConfigurationSource, CorsFilter và WebMvcConfigurer.
- **RFC 9110 – HTTP Semantics**, **RFC 9457 – Problem Details** và **OpenAPI Specification 3.1**.
