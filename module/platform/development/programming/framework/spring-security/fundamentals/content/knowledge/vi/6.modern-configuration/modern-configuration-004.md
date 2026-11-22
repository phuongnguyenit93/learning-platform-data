# Phân biệt cấu hình xác thực, phân quyền và cơ chế bảo vệ trong Spring Security

Trong ứng dụng Spring Security, nhiều cấu hình nằm chung một phương thức `SecurityFilterChain` nên người mới học rất dễ nhầm rằng chúng đều đang “kiểm tra đăng nhập”. Thực tế, bạn đang khai báo ít nhất **ba nhóm trách nhiệm độc lập nhưng phối hợp với nhau**:

1. **Xác thực (authentication):** xác minh *ai đang thực hiện yêu cầu*, dựa trên bằng chứng nào; tạo ra danh tính `Authentication` đáng tin cậy.
2. **Phân quyền (authorization):** quyết định *danh tính đó được phép làm gì* với một URL, phương thức hoặc tài nguyên cụ thể.
3. **Cơ chế bảo vệ (exploit protections / security hardening):** giảm khả năng request, response, phiên hoặc trình duyệt bị lợi dụng, như CSRF, security headers, quản lý session và các cấu hình an toàn liên quan.

Ba nhóm cùng phục vụ bảo mật nhưng trả lời ba câu hỏi khác nhau. **Đăng nhập hợp lệ không tự động cấp quyền quản trị; có quyền quản trị cũng không làm một POST thiếu CSRF token trở thành hợp lệ.** Một request chỉ đến được logic nghiệp vụ khi các lớp kiểm tra phù hợp đã chấp nhận nó.

Bài sử dụng **Spring Boot 3, Spring Security 6, Spring MVC/Servlet, Java 17+** để minh họa API cấu hình hiện đại với `SecurityFilterChain` và `HttpSecurity`. Một số API thay đổi giữa các dòng phiên bản; nếu bạn đang dùng Spring Boot 4/Spring Security 7 hoặc Spring WebFlux thì phải chọn tài liệu đúng phiên bản và mô hình ứng dụng.

## 1. Nhìn một cấu hình để nhận ra ba nhóm trách nhiệm

Đoạn dưới đây là *hình minh họa* trong một lớp Spring `@Configuration`:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        // Authorization: ai được vào đường dẫn nào?
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        // Authentication: xử lý Basic credentials.
        .httpBasic(Customizer.withDefaults())
        // Exploit protection: xác minh CSRF khi áp dụng.
        .csrf(Customizer.withDefaults())
        .build();
}
```

Ở đây:

- `.httpBasic(...)` bật cơ chế đọc username/password từ HTTP Basic, đưa cho các thành phần xác thực.
- `.authorizeHttpRequests(...)` đặt điều kiện **phải được phép truy cập** cho URL; `authenticated()`, `hasRole(...)`, `permitAll()` là *rule phân quyền*.
- `.csrf(...)` bật/giữ chính sách CSRF cho request làm thay đổi trạng thái. Spring Security Servlet thường bật CSRF mặc định; viết tường minh để người học dễ quan sát.
- `.build()` tạo một `SecurityFilterChain` gồm các security filter tương ứng.
- Những cấu hình này không tự định nghĩa ai là USER/ADMIN, password của ai đúng, ai sở hữu bản ghi hoặc CSRF token lấy từ đâu. Chúng cần phối hợp với các bean và lớp nghiệp vụ khác.

**Không suy ra thứ tự filter trực tiếp từ thứ tự gọi các DSL trong code.** Spring Security lắp filter theo kiến trúc riêng; request có thể bị CSRF chặn trước khi controller hoặc kiểm tra quyền ứng dụng được gọi. Hãy đọc kết quả, rule và filter chain thực tế thay vì xem ba lời gọi DSL là ba câu lệnh thực thi tuần tự.

### 1.1. Bảng phân biệt nhanh

| Mục đích | Câu hỏi | Thành phần thường gặp | Kết quả khi không đạt |
| --- | --- | --- | --- |
| **Authentication** | “Người gọi là ai? Credentials hợp lệ không?” | `httpBasic`, `formLogin`, `UserDetailsService`, `PasswordEncoder`, `AuthenticationManager`, `AuthenticationProvider`, `oauth2ResourceServer` | Không tạo identity tin cậy; HTTP API thường 401 hoặc web redirect login |
| **Authorization** | “Identity này có được truy cập/chạy hành động này không?” | `authorizeHttpRequests`, `requestMatchers`, `hasRole`, `hasAuthority`, `@EnableMethodSecurity`, `@PreAuthorize`, `AuthorizationManager` | Thường 403 nếu đã xác thực nhưng thiếu quyền |
| **Exploit protection** | “Request/response/phiên có vượt qua điều kiện an toàn không?” | `csrf`, `headers`, `cors`, `sessionManagement` và cấu hình cookie/TLS phù hợp | Ví dụ POST thiếu CSRF token thường 403; header/cookie policy có thể không biểu diễn bằng một status riêng |

**Lưu ý về CORS và session:** CORS là cơ chế trình duyệt kiểm soát truy cập xuyên origin, không phải authentication/authorization. Session management quản lý vòng đời và cách lưu authentication; nó nằm ở ranh giới nhiều nhóm, nhưng không tự quyết định quyền trên một bản ghi. Bảo mật toàn hệ thống còn đòi hỏi validation, truy vấn tham số, output encoding, rate limiting, quản lý secret và kiểm soát nghiệp vụ.

## 2. Hiểu quyết định bảo mật trên một request

Giả sử Alice đã đăng nhập, có authority `ROLE_USER` và `note:write`, nhưng không có `ROLE_ADMIN`. Một request có thể gặp những kiểm tra sau:

```text
HTTP request
     |
     v
FilterChainProxy -> chọn SecurityFilterChain phù hợp
     |
     +-- Các kiểm tra bảo vệ request phù hợp (ví dụ CSRF trên POST)
     |
     +-- Authentication: kiểm tra Basic/form/token/session nếu cần
     |       |
     |       +-- thành công -> SecurityContext chứa Authentication
     |       +-- thất bại -> xử lý login challenge/401/redirect
     |
     +-- Request authorization: có quyền truy cập URL này không?
     |       |
     |       +-- thiếu quyền -> 403/handler phù hợp
     |
     v
Controller -> Service
                 |
                 +-- Method/domain authorization:
                 |     đúng thao tác? owner? tenant? trạng thái?
                 |
                 v
           Thực hiện nghiệp vụ và trả response
     |
     +-- Response headers và các lớp bảo vệ trình duyệt phù hợp
```

Sơ đồ mô tả **trách nhiệm** chứ không cam kết thứ tự filter cụ thể. Các thành phần như `CsrfFilter`, `BasicAuthenticationFilter`, `AuthorizationFilter` và `ExceptionTranslationFilter` hoạt động theo cách Spring Security lắp chain. Không phải request nào cũng đi qua mọi bước: public GET có thể không cần xác thực, còn request sai CSRF có thể bị chặn rất sớm.

### 2.1. Bảng request thực tế

| Request | Authentication | Authorization | Protection | Kết quả mẫu |
| --- | --- | --- | --- | --- |
| Anonymous GET `/api/public` | Không bắt buộc | `permitAll()` | Filters/headers thích hợp vẫn hoạt động | 200 |
| Anonymous GET `/api/me` | Chưa có credentials | Endpoint cần login | Không yêu cầu CSRF vì GET an toàn | 401 với HTTP Basic |
| Alice GET `/api/me` | Basic hợp lệ | `authenticated()` đạt | Các bảo vệ phù hợp áp dụng | 200 |
| Alice GET `/api/admin` | Basic hợp lệ | Thiếu `ROLE_ADMIN` | CSRF không phải nguyên nhân | 403 |
| Admin GET `/api/admin` | Basic hợp lệ | Có `ROLE_ADMIN` | Bảo vệ phù hợp | 200 |
| Alice POST `/api/notes` thiếu CSRF | Basic hợp lệ | Có thể có quyền tạo ghi chú | CSRF từ chối | 403 |
| Alice POST `/api/notes` có CSRF | Basic hợp lệ | Rule URL và method policy đạt | CSRF hợp lệ | 200 trong demo |
| Viewer POST `/api/notes` có CSRF | Basic hợp lệ | Method policy thiếu `note:write` | CSRF đạt | 403 |

Đặc biệt, **hai response cùng status 403 có thể xuất phát từ những lớp khác nhau**: thiếu authority, thiếu quyền trên object, hoặc CSRF token sai. Chỉ nhìn 403 không đủ để kết luận phải sửa rule nào.

## 3. Cấu hình xác thực: thiết lập danh tính tin cậy

### 3.1. Cấu hình cơ chế nhận bằng chứng

Một ứng dụng có thể nhận credentials theo những cơ chế khác nhau:

| Cơ chế | Cấu hình thường gặp | Client gửi gì? | Kết quả/đặc trưng |
| --- | --- | --- | --- |
| HTTP Basic | `http.httpBasic(Customizer.withDefaults())` | Header `Authorization: Basic ...` | Provider kiểm tra username/password; API chưa xác thực thường 401 + Basic challenge |
| Form login | `http.formLogin(Customizer.withDefaults())` | Username/password qua form `POST /login` | Web chưa login thường redirect `/login`; session có thể giữ context |
| OAuth2 Resource Server JWT | `http.oauth2ResourceServer(oauth -> oauth.jwt(...))` | `Authorization: Bearer ...` | Phải xác minh token, chữ ký, issuer/audience, thời hạn và ánh xạ scope phù hợp |
| OAuth2/OIDC login | `http.oauth2Login(Customizer.withDefaults())` | Luồng chuyển hướng tới identity provider | Ứng dụng tạo/khôi phục danh tính theo flow login |
| Custom provider | `AuthenticationProvider` hoặc cơ chế tương ứng | Credentials riêng | Phải kiểm tra nguồn và bằng chứng đáng tin cậy |

Các mục trên là **lựa chọn authentication**, không phải danh sách cần bật tất cả. Bật nhiều cơ chế trên cùng chain có thể yêu cầu thiết kế `AuthenticationEntryPoint`, session policy, request matcher và ranh giới client rõ ràng.

### 3.2. UserDetailsService và PasswordEncoder làm gì?

`UserDetailsService` giúp tìm thông tin người dùng theo username cho những cơ chế phù hợp. Nó có thể trả `UserDetails` với username, password hash, trạng thái tài khoản và authorities. `PasswordEncoder` chịu trách nhiệm kiểm tra raw password với hash đã lưu; ví dụ BCrypt.

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("demo-alice-pass"))
        .authorities("ROLE_USER", "note:write")
        .build();
    return new InMemoryUserDetailsManager(alice);
}
```

Đây là đoạn cấu hình trong Spring Boot, cần import các class `User`, `UserDetails`, `UserDetailsService`, `PasswordEncoder`, `BCryptPasswordEncoder` và `InMemoryUserDetailsManager`. Password được hash để lưu; provider so sánh bằng `matches`. Không lưu plaintext password hay hardcode mật khẩu thật trong production. Các password demo chỉ dùng trên localhost để học.

**Không nhầm:**

- `UserDetailsService` giúp lấy người dùng; bản thân nó không định nghĩa mọi URL được vào.
- `PasswordEncoder` xử lý mật khẩu; nó không quyết định quyền đọc đơn hàng.
- `AuthenticationManager` / `AuthenticationProvider` thực hiện xác minh; `Authentication` kết quả chứa danh tính và `GrantedAuthority` đáng tin cậy khi xác thực thành công.
- `SecurityContextHolder` cho phép truy cập `Authentication` hiện tại theo mô hình phù hợp. Không nên tự tạo `Authentication` với cờ authenticated=true từ JSON body do client gửi.

### 3.3. AuthenticationEntryPoint xử lý người chưa đăng nhập

Khi cần yêu cầu client xác thực, Spring Security có thể sử dụng `AuthenticationEntryPoint`:

- HTTP Basic: thường trả **401 Unauthorized**, kèm header `WWW-Authenticate`.
- Form login: thường trả **302 Redirect** tới trang `/login`.
- Bearer token: thường trả 401 với challenge Bearer tương ứng khi token thiếu/sai.

Ví dụ HTTP:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
```

Có thể nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Tên realm và các header khác phụ thuộc cấu hình. Không được cố định chuỗi realm trong mọi bài test. **Basic chỉ Base64-encode username/password**, vì thế cần HTTPS khi triển khai thực tế; Base64 không phải encryption.

### 3.4. Cấu hình authentication không tạo policy truy cập

Nếu một user login thành công bằng Basic, điều được chứng minh là credentials được chấp nhận theo provider. Người đó **chưa mặc nhiên** có quyền gọi `/api/admin` hoặc xem báo cáo của user khác. Bước authorization phải dựa trên authority/role và cả tài nguyên cụ thể khi cần.

## 4. Cấu hình phân quyền: xác định được làm gì

### 4.1. Quy tắc theo HTTP request

`authorizeHttpRequests` định nghĩa điều kiện truy cập dựa trên request matcher:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
    .requestMatchers(HttpMethod.POST, "/api/notes").authenticated()
    .anyRequest().denyAll()
)
```

Phân tích:

- `permitAll()` cho phép endpoint công khai về **quyền truy cập**, không loại request khỏi toàn bộ security filter chain.
- `authenticated()` yêu cầu người dùng được xác thực theo ngữ nghĩa Spring Security, nhưng không yêu cầu role riêng.
- `hasRole("ADMIN")` theo mặc định tìm authority **`ROLE_ADMIN`**. `hasAuthority("ROLE_ADMIN")` kiểm tra chính xác chuỗi ấy, còn `hasAuthority("ADMIN")` kiểm tra chuỗi `ADMIN`.
- `anyRequest().denyAll()` từ chối những request chưa có rule; phù hợp khi muốn danh sách endpoint được mở phải tường minh.
- Rule được xét theo **thứ tự khai báo**. Matcher cụ thể phải đứng trước matcher bao quát.
- Matcher có thể giới hạn theo HTTP method; GET thường dùng đọc, POST thường gây tác dụng phụ. Không tự cho rằng GET luôn an toàn nếu controller vi phạm semantics và thay đổi dữ liệu.

**`securityMatcher` khác `requestMatchers`:** khi có nhiều `SecurityFilterChain`, `securityMatcher` quyết định **toàn chain nào** xử lý request; `requestMatchers` trong `authorizeHttpRequests` quyết định **rule** cho request nằm trong chain đó. Nếu không chain nào khớp, request có thể không được Spring Security bảo vệ. Nên có fallback chain phù hợp.

### 4.2. Method security và chính sách nghiệp vụ

Không phải mọi lời gọi nghiệp vụ đều đi qua đúng một controller. Một service có thể được gọi từ API, message consumer hoặc job. Vì thế, Spring Security hỗ trợ method security:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
    // Bean configuration khác nếu cần
}

@Service
class NoteService {
    @PreAuthorize("hasAuthority('note:write')")
    public String create(Authentication authentication) {
        return "created by " + authentication.getName();
    }
}
```

Đây là hai **fragment**, cần imports, bean và cơ chế gọi service qua Spring proxy. `@EnableMethodSecurity` bật xử lý annotation phù hợp; nếu method bị gọi nội bộ bằng **self-invocation** trong cùng object, Spring AOP proxy có thể không áp dụng annotation như mong đợi. Phải test service qua ranh giới thực tế.

`@PreAuthorize` đặt **authorization** ở phương thức, khác với `httpBasic` là **authentication** ở ranh giới HTTP. Khi method security từ chối, request đã xác thực có thể nhận 403 qua cơ chế exception handling phù hợp.

### 4.3. Quyền trên một đối tượng cụ thể

Giả sử Alice và Bob đều có `ROLE_USER` và `order:read`. Hai người được vào endpoint đọc đơn nhưng chưa chắc có quyền trên **cùng một order ID**. Backend còn cần kiểm tra:

```text
authenticatedPrincipal
AND hasAuthority("order:read")
AND sameTenant(principal, order)
AND (isOwner(principal, order) OR hasAuthority("order:read:any"))
AND businessStateAllowsOperation(order)
```

Việc chỉ ẩn nút trên giao diện, chỉ dùng `hasRole("USER")` hoặc dùng ID ngẫu nhiên không thay thế kiểm tra quyền trên object. Domain policy phải lấy owner/tenant từ server và principal đã xác minh. Đây cũng là cách tránh lỗi IDOR/Broken Object Level Authorization.

### 4.4. Phân quyền thiếu quyền và không thể xác định quyền

- Có bằng chứng xác thực, policy kết luận không đủ role/permission → **DENY**, thường 403.
- Dịch vụ cấp quyền ngoài timeout hoặc policy bắt buộc bị thiếu → **UNAVAILABLE**; không tự chuyển thành ALLOW.
- Thiếu rule cho endpoint nhạy cảm → dùng mặc định deny hoặc fail fast khi thiếu cấu hình, không fallback `permitAll()`.
- Truy vấn owner/tenant không có kết quả đáng tin → không cấp quyền đối với tài nguyên cần kiểm tra.

**Fail closed** mô tả việc không cho hành động đi tiếp khi không có quyết định ALLOW đáng tin cậy, không đồng nghĩa mọi lỗi phải trả đúng 403. Lỗi dependency có thể cần phản hồi 503 tùy hợp đồng API.

## 5. Cơ chế bảo vệ: giảm nguy cơ khai thác request, response và phiên

### 5.1. CSRF: kiểm tra ý định của request trong bối cảnh phù hợp

**Cross-Site Request Forgery** xảy ra khi trang khác lợi dụng việc trình duyệt tự đính kèm credentials (ví dụ cookie phiên) để khiến nạn nhân gửi request làm thay đổi trạng thái. Đăng nhập đúng và có quyền ghi không đủ để bảo đảm POST thực sự do người dùng muốn thực hiện.

Trong Spring Security Servlet, **CSRF protection mặc định bật** đối với các HTTP method không an toàn như POST, PUT, PATCH và DELETE. Có thể viết tường minh:

```java
.csrf(Customizer.withDefaults())
```

Một request POST thiếu/sai CSRF token theo cơ chế đang dùng thường bị chặn với **403**, kể cả khi đã gửi credentials hợp lệ. Test nên dùng `with(csrf())` để tạo token đúng khi muốn kiểm tra các lớp tiếp theo.

**Điểm cần nhớ:**

- `permitAll()` chỉ là quyết định authorization; một POST công khai vẫn có thể bị CSRF từ chối.
- `hasRole("ADMIN")` không tự tắt CSRF cho admin.
- `SessionCreationPolicy.STATELESS` không tự chứng minh CSRF không cần thiết. Rủi ro phụ thuộc việc client có gửi credentials tự động hay không.
- Với API thực sự chỉ nhận bearer token do client chủ động thêm vào header, không sử dụng cookie/session hoặc Basic credentials tự đính kèm, có thể đánh giá việc không dùng CSRF cho đúng phạm vi. Quyết định phải đến từ threat model và cơ chế xác thực thực tế.
- CORS **không thay thế** CSRF. Một số request có thể được gửi từ trang ngoài ngay cả khi JavaScript không thể đọc response.
- CSRF không chữa XSS. Nếu script độc hại chạy trong chính origin đáng tin, nó có thể gây hành động khác dưới quyền người dùng.

Không tắt CSRF toàn ứng dụng để “sửa” một POST trả 403. Kiểm tra request method, cơ chế cấp token, cách gửi token và loại client trước khi chỉnh policy.

### 5.2. Security headers: bảo vệ phía trình duyệt

Spring Security có cơ chế viết nhiều HTTP response header theo mặc định, chẳng hạn:

| Header / chính sách | Mục đích | Giới hạn |
| --- | --- | --- |
| `X-Content-Type-Options: nosniff` | Giảm suy đoán MIME type nguy hiểm | Không chữa XSS hoặc authorization sai |
| `X-Frame-Options: DENY` theo cấu hình mặc định thường gặp | Hạn chế clickjacking qua frame | Cần xem yêu cầu nhúng/iframe của ứng dụng |
| `Strict-Transport-Security` (HSTS) khi HTTPS | Khuyến khích browser chỉ dùng HTTPS cho origin theo chính sách | Không bảo vệ HTTP ban đầu khi chưa có HSTS/preload, không kiểm tra quyền |
| Cache-control headers | Hạn chế lưu cache phản hồi nhạy cảm theo mặc định | Ứng dụng có thể ghi đè chính sách cache |
| `Content-Security-Policy` (CSP) khi **ứng dụng cấu hình** | Giảm một số nguy cơ script/content injection | Không tự bật với một policy phù hợp cho mọi ứng dụng, không thay thế output encoding |

Ví dụ cấu hình CSP cho một ứng dụng tự quản lý tài nguyên frontend (chỉ minh họa, cần tự đánh giá script/style được phép):

```java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; object-src 'none'")
    )
)
```

Không copy một CSP bất kỳ vào production rồi giả định giao diện hoạt động đúng; phải test report-only/violation, tài nguyên của chính ứng dụng và tác động lên browser. Spring Security không tự sửa SQL injection, output escaping, lỗi owner/tenant hoặc dependency lỗ hổng.

### 5.3. CORS: chính sách browser cross-origin, không phải user permission

`cors(...)` giúp cấu hình tích hợp CORS với Spring Security khi browser client chạy origin khác. CORS quyết định theo mô hình trình duyệt một origin có thể gửi/đọc các request cross-origin và preflight ra sao; nó không xác minh danh tính của người dùng hay cấp quyền trên dữ liệu.

Ví dụ nhận thức:

- Origin `https://app.example` được phép gọi API thì **user Alice vẫn phải login** nếu API private.
- Alice có token hợp lệ nhưng không có quyền xem `order/123` thì **authorization vẫn phải từ chối**.
- Một command-line client không chịu chính sách CORS như browser; backend vẫn cần authentication/authorization.
- CORS cho phép credentials chỉ khi chính sách có origin rõ ràng và cấu hình tương thích, không tùy tiện dùng wildcard với cookie.

Việc đặt `cors(Customizer.withDefaults())` một mình không thay thế một `CorsConfigurationSource` hoặc cấu hình CORS hợp lệ cho nhu cầu ứng dụng. Phải xác định origin, methods, headers và credential policy. Preflight OPTIONS thường cần được xử lý trước security flow đòi credentials, vì preflight không mang thông tin đăng nhập theo cùng cách request thực.

### 5.4. SessionManagement, cookies và trạng thái

`sessionManagement(...)` quản lý chính sách session như tạo, hạn chế hoặc không sử dụng HTTP session cho security context. Với form login, session có thể giữ đăng nhập qua nhiều request. Với resource server API, authentication thường đến từ bearer token mỗi request.

Những lựa chọn này liên quan **cách lưu/khôi phục identity**, nhưng không tự quyết định `hasRole` hoặc owner/tenant. Các cookie phiên của ứng dụng browser nên áp dụng `Secure` khi HTTPS, `HttpOnly`, `SameSite` theo threat model và quản lý vòng đời/đăng xuất đúng. Không dùng sự tồn tại của cookie làm bằng chứng đã login thành công.

### 5.5. HTTPS, password hashing và những biện pháp ngoài framework

Một SecurityFilterChain đầy đủ vẫn chưa tự bảo đảm:

- Dữ liệu gửi qua HTTPS/TLS trên đường truyền và kết nối tới các dependency tin cậy;
- Input validation (ví dụ `@Valid`), query tham số hóa chống SQL injection;
- Context-aware output encoding/template escaping chống XSS;
- Rate limiting, quota, kiểm soát kích thước request và chống lạm dụng tài nguyên;
- Phân quyền trên object, tenant isolation và trạng thái nghiệp vụ;
- Logging/audit hữu ích nhưng không rò rỉ password, token, session ID;
- Giao dịch nhất quán, idempotency cho tác vụ có side effect và quy trình thu hồi quyền.

**Authentication, authorization và exploit protection không cạnh tranh nhau; chúng bảo vệ các loại tài sản và ranh giới khác nhau.**

## 6. Ví dụ ứng dụng Spring Boot 3 hoàn chỉnh

Ví dụ minh họa cả ba nhóm ngay trong một ứng dụng **Servlet/Spring MVC**. Sử dụng hai tài khoản:

- `writer` có `ROLE_USER` và `note:write`;
- `viewer` chỉ có `ROLE_USER`;
- `admin` có `ROLE_ADMIN`.

Chính sách:

| Endpoint | Rule request | Rule method | CSRF |
| --- | --- | --- | --- |
| `GET /api/public` | Công khai | Không có | GET không cần token |
| `GET /api/me` | Đã xác thực | Không có | GET không cần token |
| `GET /api/admin` | `ROLE_ADMIN` | Không có | GET không cần token |
| `POST /api/notes` | Đã xác thực | `note:write` tại service | POST yêu cầu token hợp lệ trong demo |

### 6.1. Dependency

Tạo một dự án **Spring Boot 3 + Java 17+**, dùng Spring Web và Spring Security. Trong `build.gradle` (Groovy DSL) đã có Spring Boot plugin, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là phần `dependencies`, không phải toàn bộ Gradle build script. Với Maven, dùng `spring-boot-starter-parent` hoặc BOM tương ứng và cùng các dependency ở test scope. Không khai báo phiên bản Spring Security độc lập nếu Boot dependency management đã quản lý.

### 6.2. Main application

Tạo `src/main/java/example/securitylayers/SecurityLayersApplication.java`:

```java
package example.securitylayers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLayersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLayersApplication.class, args);
    }
}
```

### 6.3. SecurityConfig: authentication + authorization + protection

Tạo `src/main/java/example/securitylayers/SecurityConfig.java`:

```java
package example.securitylayers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails writer = User.withUsername("writer")
            .password(encoder.encode("demo-writer-pass"))
            .authorities("ROLE_USER", "note:write")
            .build();

        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("demo-viewer-pass"))
            .authorities("ROLE_USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .authorities("ROLE_ADMIN")
            .build();

        return new InMemoryUserDetailsManager(writer, viewer, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Ba phần dễ nhầm cần đánh dấu:

1. **Authentication**: `userDetailsService(...)` định nghĩa các user mẫu và authorities được lưu; `passwordEncoder(...)` tạo BCrypt; `httpBasic(...)` bật việc nhận header Basic để Spring Security xác thực. Các user chỉ là ví dụ học tập, không dùng password hardcode ở production.
2. **Request authorization**: `authorizeHttpRequests(...)` kiểm tra GET admin có `ROLE_ADMIN`; GET me và POST notes yêu cầu user đã đăng nhập; những method/endpoint không khai báo bị từ chối.
3. **Method authorization**: `@EnableMethodSecurity` bật `@PreAuthorize` ở service; riêng POST notes được kiểm tra thêm `note:write`.
4. **Exploit protection**: `csrf(Customizer.withDefaults())` giữ bảo vệ CSRF đối với POST; các security headers mặc định phù hợp vẫn được Spring Security ghi ra nếu không bị ghi đè.
5. **Không suy luận authz từ thông tin do client tự khai**: username trong request body, `X-Role` header hoặc trường `isAdmin` không được tự biến thành authority đã xác minh.

Lưu ý: `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`. `User.withUsername(...).authorities("ROLE_ADMIN")` cấp đúng chuỗi. `hasAuthority("ROLE_ADMIN")` cũng khớp, còn `hasAuthority("ADMIN")` sẽ không khớp với user admin này.

### 6.4. Controller và service: phân biệt URL rule với method rule

Tạo `src/main/java/example/securitylayers/ApiController.java`:

```java
package example.securitylayers;

import java.util.Map;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
class ApiController {

    private final NoteService noteService;

    ApiController(NoteService noteService) {
        this.noteService = noteService;
    }

    @GetMapping("/public")
    Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin only");
    }

    @PostMapping("/notes")
    Map<String, String> createNote(Authentication authentication) {
        return Map.of(
            "result",
            noteService.create(authentication)
        );
    }
}

@Service
class NoteService {

    @PreAuthorize("hasAuthority('note:write')")
    public String create(Authentication authentication) {
        // Demo chỉ trả chuỗi; ứng dụng thực tế mới ghi DB.
        return "created by " + authentication.getName();
    }
}
```

Ở đây:

- `GET /api/admin` được bảo vệ ở HTTP layer: `hasRole("ADMIN")`.
- `POST /api/notes` chỉ yêu cầu login ở HTTP layer, nhưng khi controller gọi bean `NoteService`, `@PreAuthorize` còn kiểm tra authority `note:write`.
- Các kiểm tra CSRF vẫn xảy ra ở web filter chain; ngay cả writer có `note:write` vẫn có thể bị từ chối nếu POST thiếu token.
- `NoteService` là bean riêng và được controller gọi qua dependency injection, cho phép Spring method security áp dụng trên phương thức. Không tự gọi một phương thức `@PreAuthorize` qua `this.method()` trong cùng bean rồi giả định proxy đã chặn.
- Logic demo chưa có owner/tenant/data persistence. Với API có dữ liệu thật, phải bổ sung domain authorization và kiểm tra không có side effect trái phép.

### 6.5. Chạy ứng dụng và quan sát bằng curl

Từ dự án Spring Boot có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Giả sử app chạy trên `http://localhost:8080`. Các password dưới đây chỉ dùng local:

```bash
# Public GET: 200, body {"message":"public"}
curl -i http://localhost:8080/api/public

# GET private chưa có credentials: 401, Basic challenge
curl -i http://localhost:8080/api/me

# Writer được xác thực: 200, body {"user":"writer"}
curl -i -u writer:demo-writer-pass http://localhost:8080/api/me

# Writer không có ROLE_ADMIN: 403
curl -i -u writer:demo-writer-pass http://localhost:8080/api/admin

# Admin đúng role: 200, body {"message":"admin only"}
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin

# Writer có note:write nhưng POST thiếu CSRF token: 403
curl -i -X POST -u writer:demo-writer-pass \
  http://localhost:8080/api/notes
```

Lệnh Bash cuối có dấu nối dòng `\`. Trong PowerShell, đưa URL lên cùng dòng hoặc dùng cú pháp riêng của shell; không copy dấu nối dòng Bash vào PowerShell.

Để kiểm tra **POST thành công với CSRF**, ở bài này sử dụng MockMvc `with(csrf())` nhằm tránh phải giải quyết vòng đời session/token bằng curl. Trong browser/session app thực, client phải lấy token từ repository/handler đúng cấu hình rồi gửi lại theo header hoặc form parameter phù hợp.

HTTP Basic thực tế phải được sử dụng qua HTTPS; `curl -u` có thể làm lộ password trong history/process list, nên password cố định trên đây chỉ là giá trị demo. Không ghi header Authorization chứa credentials hoặc session ID thật vào tài liệu công khai.

## 7. Kiểm thử đầy đủ ba nhóm bằng Spring Security Test

Thêm `spring-security-test` trong test scope để sử dụng `httpBasic()` và `csrf()`. Tạo `src/test/java/example/securitylayers/SecurityLayersTest.java`:

```java
package example.securitylayers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityLayersTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validCredentialsProduceIdentity() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("writer", "demo-writer-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("writer"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("writer", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void roleDecidesAdminAccess() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("writer", "demo-writer-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void missingCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("writer", "demo-writer-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndAuthorityAllowPost() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("writer", "demo-writer-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result")
                .value("created by writer"));
    }

    @Test
    void validCsrfButMissingMethodAuthorityIsDenied()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("viewer", "demo-viewer-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.securitylayers.SecurityLayersTest
```

Trong PowerShell:

```powershell
.\gradlew.bat test --tests example.securitylayers.SecurityLayersTest
```

**Kỳ vọng:** cả **8 phương thức test** đều pass với mã/config/controller đúng như ví dụ, khi môi trường Boot 3 và dependency test được thiết lập. Đây là kết quả **dự kiến theo mã**, không phải log từ một lần chạy công cụ trong bài này; số lượng task và output Gradle thực tế có thể khác.

Các test lần lượt chứng minh:

| Test | Nhóm được kiểm tra | Điều nó chứng minh |
| --- | --- | --- |
| Public GET | Request authorization | `permitAll()` vẫn cho anonymous vào |
| Anonymous private GET | Authentication + entry point | Chưa có credentials được yêu cầu xác thực |
| Basic đúng | Authentication | Provider nhận credentials và tạo identity |
| Basic sai | Authentication | Credentials không hợp lệ bị từ chối |
| Admin role | Request authorization | Người đã login nhưng thiếu role vẫn bị từ chối |
| POST thiếu CSRF | Exploit protection | Quyền ghi đúng vẫn chưa đủ nếu request thiếu token |
| POST CSRF hợp lệ + writer | Protection + method authorization | Đủ điều kiện thì đi tới service |
| POST CSRF hợp lệ + viewer | Method authorization | Token hợp lệ không cấp thêm `note:write` |

### 7.1. Vì sao test thiếu CSRF và thiếu authority đều có thể ra 403?

`status().isForbidden()` chỉ xác nhận **kết quả HTTP**, chưa chỉ rõ filter nào gây ra. Để xác định nguyên nhân trong bài học, chúng ta tạo hai request khác nhau:

- Writer có `note:write` nhưng **không cung cấp CSRF** → 403 ở lớp bảo vệ request.
- Viewer **có CSRF hợp lệ** nhưng không có `note:write` → 403 ở method security.

Cách so sánh này tốt hơn việc luôn bỏ `with(csrf())` rồi thắc mắc sao test authority nào cũng nhận 403 vì CSRF chặn trước.

### 7.2. @WithMockUser khác với httpBasic()

`@WithMockUser` hoặc `with(user("..."))` đặt người dùng giả lập vào security context để test authorization; nó **không chứng minh username/password thực được provider xác thực**. `httpBasic(...)` thêm Basic header để request đi qua cơ chế HTTP Basic đã cấu hình, phù hợp khi muốn kiểm tra phần authentication và authorization kết hợp.

Đừng coi một test `@WithMockUser(roles = "ADMIN")` pass là bằng chứng user có thể đăng nhập thật hoặc JWT issuer/scope được verify đúng.

### 7.3. Test không có side effect trái phép

Ví dụ controller trả chuỗi nên không ghi dữ liệu. Trong sản phẩm thật, các test 401/403/CSRF phải xác minh thêm:

- Không có bản ghi đơn hàng hoặc ghi chú nào được thêm/sửa/xóa;
- Không phát sự kiện vào queue hay gọi payment provider;
- Không ghi dữ liệu tenant khác;
- Không chạy logic nghiệp vụ nếu policy đã từ chối;
- Không rò rỉ password/token hoặc dữ liệu nhạy cảm qua error response/log.

Một HTTP 403 không đủ để chứng minh an toàn nếu side effect đã xảy ra trước khi exception được trả.

## 8. Ví dụ Java 17 độc lập: mô hình tư duy về ba lớp

Nếu chưa có môi trường Spring Boot, chương trình Java dưới đây **không sử dụng Spring Security thật** mà mô phỏng ba cổng kiểm tra. Nó giúp nhìn rõ sự khác biệt giữa việc chưa xác thực, bị từ chối quyền và request không vượt qua bảo vệ.

Tạo tệp **`ThreeLayersModel.java`**:

```java
import java.util.Set;

public class ThreeLayersModel {

    enum Decision {
        ALLOW,
        UNAUTHENTICATED,
        FORBIDDEN,
        CSRF_REJECTED,
        DENY_UNKNOWN
    }

    record Actor(
        String name,
        boolean authenticated,
        Set<String> authorities
    ) {}

    record Request(
        String method,
        String path,
        boolean csrfValid
    ) {}

    static Decision decide(Actor actor, Request request) {
        if (request == null || request.method() == null
                || request.path() == null) {
            return Decision.DENY_UNKNOWN;
        }

        if ("GET".equals(request.method())
                && "/api/public".equals(request.path())) {
            return Decision.ALLOW;
        }

        boolean knownGet = "GET".equals(request.method())
                && ("/api/me".equals(request.path())
                    || "/api/admin".equals(request.path()));
        boolean knownPost = "POST".equals(request.method())
                && "/api/notes".equals(request.path());

        if (!knownGet && !knownPost) {
            return Decision.DENY_UNKNOWN;
        }

        // Mô phỏng một phần exploit protection cho POST.
        if (knownPost && !request.csrfValid()) {
            return Decision.CSRF_REJECTED;
        }

        // Mô phỏng authentication.
        if (actor == null || !actor.authenticated()) {
            return Decision.UNAUTHENTICATED;
        }

        // Mô phỏng authorization.
        Set<String> rights = actor.authorities();
        if (rights == null) {
            return Decision.FORBIDDEN;
        }

        if ("/api/admin".equals(request.path())
                && !rights.contains("ROLE_ADMIN")) {
            return Decision.FORBIDDEN;
        }

        if (knownPost && !rights.contains("note:write")) {
            return Decision.FORBIDDEN;
        }

        return Decision.ALLOW;
    }

    static void print(String label, Actor actor, Request request) {
        System.out.println(label + ": " + decide(actor, request));
    }

    public static void main(String[] args) {
        Actor writer = new Actor(
            "writer", true, Set.of("ROLE_USER", "note:write")
        );
        Actor viewer = new Actor(
            "viewer", true, Set.of("ROLE_USER")
        );

        print("Public GET", null,
            new Request("GET", "/api/public", false));
        print("Anonymous private GET", null,
            new Request("GET", "/api/me", false));
        print("Writer admin GET", writer,
            new Request("GET", "/api/admin", false));
        print("Writer POST without CSRF", writer,
            new Request("POST", "/api/notes", false));
        print("Viewer POST with CSRF", viewer,
            new Request("POST", "/api/notes", true));
        print("Writer POST with CSRF", writer,
            new Request("POST", "/api/notes", true));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ThreeLayersModel.java
java ThreeLayersModel
```

**Stdout chính xác theo logic chương trình:**

```text
Public GET: ALLOW
Anonymous private GET: UNAUTHENTICATED
Writer admin GET: FORBIDDEN
Writer POST without CSRF: CSRF_REJECTED
Viewer POST with CSRF: FORBIDDEN
Writer POST with CSRF: ALLOW
```

Mô hình dùng record `Actor` có cờ authenticated/authority do code tạo, **không tự xác minh password, token, session hay CSRF token**. Vì vậy nó chỉ dùng để học luồng quyết định, **không được thay thế Spring Security trong production**. Đặc biệt, `csrfValid` là cờ giả lập trong chương trình; không bao giờ tin một trường `csrfValid=true` do client gửi mà coi nó là bằng chứng CSRF hợp lệ.

Trong ứng dụng thật, Spring Security nhận request, xác thực credentials, kiểm tra CSRF theo token repository/handler và đánh giá authorization; domain service còn phải xử lý quyền trên object. Thứ tự thực thi có thể khác mô phỏng nhưng điều kiện bắt buộc phải được đáp ứng.

## 9. Những thay đổi cấu hình nào tác động tới nhóm nào?

### 9.1. Bật form login thay HTTP Basic

```java
// Authentication policy cho web browser:
.formLogin(Customizer.withDefaults())
```

So với `httpBasic`, hành vi khi chưa login thay đổi: với form login, browser thường chuyển hướng tới `/login`, còn Basic thường trả 401 challenge. **Role và URL permission không tự thay đổi** chỉ vì chọn cơ chế xác thực khác. Cần cấu hình đúng security chain và client type; không mặc định mọi browser luôn 302 khi có cả hai entry point.

### 9.2. Đổi từ authenticated() sang hasRole("ADMIN")

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Đây là **thay đổi authorization**: user đã login nhưng thiếu `ROLE_ADMIN` sẽ bị từ chối. Nó không đổi cách password được kiểm tra, không bật/tắt CSRF và không thay đổi password hashing.

### 9.3. Thêm CSRF cho POST

```java
.csrf(Customizer.withDefaults())
```

Đây là cơ chế bảo vệ request; người đã xác thực hợp lệ vẫn có thể bị chặn vì token thiếu/sai. Chỉ khi threat model giải thích rõ nguồn credentials, client type và phạm vi request mới cân nhắc tùy chỉnh exception hoặc ignore matcher. Không dùng disable toàn cục để né lỗi test.

### 9.4. Cấu hình security headers

```java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; object-src 'none'")
    )
)
```

Đây là cấu hình browser protection. Nó không tạo user, không cấp `ROLE_ADMIN`, không thay method policy, và không đảm bảo output của ứng dụng đã an toàn khỏi XSS. Cần kiểm tra phù hợp frontend.

### 9.5. Mở CORS nhưng vẫn yêu cầu login

Một origin được CORS cho phép chỉ có nghĩa trình duyệt được sử dụng tài nguyên cross-origin theo chính sách. API riêng tư vẫn phải kiểm tra credentials và quyền của principal. Nếu frontend gọi API có cookie từ origin khác, cần đánh giá cả `SameSite`, CORS credentials, CSRF và trust boundary.

### 9.6. Cấu hình stateless API

`SessionCreationPolicy.STATELESS` định hướng Spring Security không tạo/dùng HTTP session để lưu/khôi phục SecurityContext cho các request trong chain. Nhưng nếu frontend/browser vẫn có credential tự đính kèm, chỉ thêm chữ “stateless” không loại bỏ mọi nguy cơ CSRF. Và stateless không tự giới hạn role/scope hoặc tenant.

## 10. Phân tích các sai lầm cấu hình thường gặp

| Lỗi | Nhóm bị hiểu nhầm | Hậu quả | Cách sửa |
| --- | --- | --- | --- |
| Coi `httpBasic()` như cho phép mọi user | Authentication vs authorization | User hợp lệ truy cập nhầm endpoint nhạy cảm | Thêm `authorizeHttpRequests` và object policy rõ ràng |
| Coi `hasRole("ADMIN")` là cách xác minh mật khẩu admin | Authorization vs authentication | Nhầm vai trò rule và provider | Cấu hình provider/user store/token verifier riêng |
| Gọi `hasRole("ROLE_ADMIN")` khi prefix mặc định | Authorization | Role bị thêm prefix sai hoặc rule không khớp | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Đặt `anyRequest().permitAll()` quá rộng | Authorization | Endpoint ngoài ý muốn thành public | Rule cụ thể và `anyRequest().denyAll()` khi cần |
| Tắt CSRF vì POST test trả 403 | Exploit protection | Request giả mạo có thể thành công trong app cookie | Thử `with(csrf())`, cấp token đúng cơ chế, đánh giá threat model |
| Coi CORS là hệ thống cấp quyền | Browser protection vs authorization | Non-browser client hoặc same-origin request vẫn vượt chính sách sai | Luôn kiểm tra identity/permission tại server |
| Tin `X-User-Id`, `roles` hoặc `isAdmin` từ client | Authentication/authorization | Giả mạo danh tính, leo thang quyền | Dùng principal đã xác minh và nguồn authority tin cậy |
| Dùng `web.ignoring` cho route công khai không cần thiết | Chain protection | Bỏ qua security headers/filter trên route | Ưu tiên `permitAll()` cho public resource |
| Chỉ bảo vệ URL, quên service/object | Authorization | IDOR/BOLA, đọc nhầm tenant | Method/domain authorization và scoped queries |
| Tưởng CSP tự bật/giải quyết mọi XSS | Exploit protection | Cảm giác an toàn giả | Chọn CSP phù hợp, escape output theo ngữ cảnh |
| Tưởng một 403 luôn do role thiếu | Lỗi chẩn đoán | Sửa sai lớp, có thể tắt protection cần thiết | Phân tích request, filter chain, CSRF, permission và log |
| Để thiếu policy thì fallback `permitAll()` | Authorization/config | Vượt quyền khi configuration lỗi | Fail fast hoặc deny theo chính sách |
| Hai chain có matcher/`@Order` sai | Chain selection | Request đi qua cơ chế khác hoặc không được bảo vệ | Kiểm thử chain matching, thêm fallback phù hợp |
| Copy cấu hình `WebSecurityConfigurerAdapter` cũ | API version | Không biên dịch với Boot 3/Security 6 | Dùng bean `SecurityFilterChain` và tài liệu đúng phiên bản |

### 10.1. Vì sao permitAll() không giống bỏ qua Spring Security?

`permitAll()` là **authorization decision** cho một request đi qua `SecurityFilterChain`. Các filter và header writer phù hợp vẫn có thể tham gia. Trong khi đó, việc cấu hình Spring Security bỏ qua hẳn request có thể khiến nó không đi qua các security protections của chain. Với public endpoint hoặc static resource, nên ưu tiên `permitAll()` trừ khi có lý do kỹ thuật rõ ràng và đã hiểu tác động.

### 10.2. Vì sao không thể chỉ kiểm tra role trong controller?

Một admin endpoint có thể được gọi qua REST, job hoặc asynchronous flow. Nếu policy chỉ nằm ở controller, những đường gọi khác có thể bypass. Tùy kiến trúc, dùng HTTP authorization, method security và domain policy phù hợp ở nơi thực hiện nghiệp vụ để bảo vệ đầy đủ.

### 10.3. Vì sao sai CSRF có thể che mất lỗi permission?

Ví dụ viewer không có `note:write` và gửi POST không CSRF token. Request có thể bị `CsrfFilter` chặn trước khi thực thi `@PreAuthorize`, nên test chỉ thấy 403 mà **chưa chứng minh** method security đã từ chối thiếu quyền. Để kiểm tra authorization riêng, thêm CSRF token hợp lệ trong test và giữ viewer thiếu authority.

### 10.4. Vì sao Spring Security không tự hoàn thành threat model?

Framework cung cấp nhiều thành phần bảo mật nhưng không biết tất cả tài sản và quy tắc nghiệp vụ của bạn. Một Spring Security config hợp lệ vẫn có thể chứa lỗi logic, ví dụ tài khoản A đọc đơn của B vì repository chỉ lọc theo ID. Cần xác định subject, action, resource, owner, tenant, chính sách trạng thái và điều kiện kinh doanh, rồi kiểm thử đúng những trường hợp bị từ chối.

## 11. Cách đọc một SecurityConfig chưa từng gặp

Khi mở lớp cấu hình của dự án, hãy làm theo trình tự:

1. **Xác định ứng dụng Servlet hay reactive**: đoạn `HttpSecurity` thuộc Servlet, trong khi WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`.
2. **Xác định số chain**: có bao nhiêu bean `SecurityFilterChain`? `securityMatcher` và `@Order` phân vùng URL thế nào? Có fallback không?
3. **Tìm authentication mechanisms**: `httpBasic`, `formLogin`, `oauth2ResourceServer`, `oauth2Login` hoặc custom filter/provider. Identity/credential lấy từ đâu?
4. **Tìm user store/token verifier**: `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder`, `JwtDecoder`, issuer/audience và cách ánh xạ authority.
5. **Tìm request authorization**: `authorizeHttpRequests`, matchers, thứ tự rule, `permitAll`, `authenticated`, `hasRole`, `hasAuthority` và fallback.
6. **Tìm method/domain authorization**: `@EnableMethodSecurity`, `@PreAuthorize`, service policies và checks owner/tenant.
7. **Tìm exploit protections**: `csrf`, `headers`, `cors`, `sessionManagement`, cookie policy, HTTPS và các config browser.
8. **Tìm exception handling**: `AuthenticationEntryPoint` khi chưa đăng nhập; `AccessDeniedHandler` khi bị từ chối; cấu hình form redirect khác API JSON.
9. **Đối chiếu bằng tests**: anonymous, credentials sai, user thiếu authority, POST thiếu CSRF, khác owner/tenant, side effect bị chặn.
10. **Xem runtime evidence**: chọn chain thật, headers/status thật, log được làm sạch; không suy luận chỉ từ một annotation hay status code.

### 11.1. Bảng kiểm cấu hình trước khi release

- Có định nghĩa rõ authentication provider/identity source, credential policy và cách lưu secret hay chưa?
- Có phân quyền mọi endpoint và method quan trọng, với mặc định deny phù hợp?
- Có tách quyền đăng nhập và quyền thao tác nghiệp vụ, tránh role quá rộng?
- Các request thay đổi trạng thái có CSRF protection phù hợp cơ chế cookie/credentials không?
- CORS chỉ cho phép origin cần thiết và không bị hiểu nhầm là authorization?
- Security headers được kiểm tra trên phản hồi thực; CSP đã thiết kế riêng nếu cần?
- Cookie/session/token có vòng đời, timeout, thu hồi và các thuộc tính an toàn hợp lý?
- Có kiểm tra owner, tenant, trạng thái đối tượng và dữ liệu đúng phạm vi tại service/repository?
- Có regression tests cho 401/403, form login nếu dùng, CSRF đúng/sai, quyền object và side effect?
- Khi cấu hình hoặc dịch vụ cấp quyền bị lỗi, có ngăn hành động nhạy cảm thay vì tự động cho qua?
- Test dùng đúng version, dependency và có môi trường integration phù hợp?
- Có kế hoạch giám sát và tránh log raw credentials/token/session ID?

## 12. Tự kiểm tra

**Câu 1.** Một request `GET /api/admin` gửi Basic username/password đúng nhưng user chỉ có `ROLE_USER`. Nó thất bại ở nhóm nào? HTTP status dự kiến?

**Câu 2.** Vì sao thay `httpBasic` bằng `formLogin` thường làm phản hồi của browser chưa đăng nhập đổi từ Basic challenge sang redirect mà không cần thay các rule `hasRole`?

**Câu 3.** Vì sao một POST của writer, dù đã được xác thực và có `note:write`, vẫn có thể bị từ chối khi không có CSRF token?

**Câu 4.** Tại sao một origin được CORS cho phép không có nghĩa user từ origin đó được xem mọi bản ghi?

**Câu 5.** Khác biệt giữa `securityMatcher` và `requestMatchers` khi có nhiều `SecurityFilterChain`?

**Câu 6.** Lệnh `@PreAuthorize("hasAuthority('note:write')")` bảo vệ thành phần nào? Nó có kiểm tra password người dùng không?

**Câu 7.** Nếu Alice có `order:read`, điều gì ngăn cô ấy đọc order của Bob trong cùng tenant?

**Câu 8.** Vì sao test POST không có CSRF token có thể không chứng minh được rule `@PreAuthorize` đúng?

**Câu 9.** `permitAll()` có tắt toàn bộ security filters và headers của request không?

**Câu 10.** Để bảo vệ user trước XSS/SQL injection, có thể chỉ viết `authorizeHttpRequests` và `csrf` mà không kiểm tra input/output hoặc truy vấn database không?

**Đáp án gợi ý:**

1. Authentication thành công nhưng authorization từ chối vì thiếu `ROLE_ADMIN`; thường 403.
2. Vì đây là thay đổi **cơ chế authentication entry point**, không phải thay đổi rule quyền.
3. CSRF bảo vệ request làm thay đổi trạng thái trong bối cảnh thích hợp, độc lập với việc danh tính/authority đúng.
4. CORS là chính sách cross-origin của browser; backend vẫn phải xác thực, kiểm tra quyền và object ownership.
5. `securityMatcher` chọn toàn chain, `requestMatchers` đặt rule bên trong chain đã chọn.
6. Nó bảo vệ method của Spring bean, kiểm tra authority trong Authentication hiện tại; không tự xác minh password.
7. Domain/object authorization dựa trên owner/tenant và policy tại service/repository.
8. Request có thể bị CSRF chặn trước khi tới method; muốn test authorization riêng cần CSRF hợp lệ.
9. Không; `permitAll()` chỉ là quyết định cho phép trong chain.
10. Không; exploit protections của Spring Security là những lớp bổ sung, cần validation, query tham số, output encoding và domain policy.

### Tài liệu tham khảo chính thức

- [Spring Security – Java Configuration / SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security – Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security – MockMvc Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
