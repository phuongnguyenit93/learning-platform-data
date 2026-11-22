# Thứ tự các nhóm bộ lọc: ngữ cảnh, xác thực, bảo vệ và phân quyền

> **Thông điệp chính:** Trong Spring Security **Servlet**, một request không đi trực tiếp đến controller rồi mới được kiểm tra bảo mật. Nó đi qua một **chuỗi các Servlet Filter có thứ tự xác định**. Về logic, Spring Security cần (1) chuẩn bị/khôi phục `SecurityContext`; (2) áp các biện pháp bảo vệ request như CORS, CSRF và headers; (3) xác thực credential từ Basic, form login, Bearer token hoặc cơ chế khác; (4) thiết lập danh tính anonymous khi chưa có principal và chuẩn bị xử lý exception; (5) áp luật phân quyền tại `AuthorizationFilter` rồi mới cho request vào `DispatcherServlet`. Thứ tự quan trọng bởi **một filter chỉ thấy trạng thái mà các filter trước nó đã chuẩn bị**, và **một filter từ chối request có thể ngăn mọi filter phía sau chạy**.

Bài này thuộc nhóm **Kiến trúc Servlet** của module **Spring Security – fundamentals**. Ví dụ dùng **Java 17+, Spring Boot 3.5.16, Spring Security 6.5.x, Spring MVC/Servlet**. Danh sách filter thực tế phụ thuộc cấu hình và phiên bản, không có một thứ tự đầy đủ bất biến cho mọi project. Với **WebFlux**, phải dùng `SecurityWebFilterChain` và mô hình reactive khác.

## 1. Kết quả học tập

Học xong, bạn có thể:

1. Giải thích đường đi `Servlet FilterChain` → `DelegatingFilterProxy` → `FilterChainProxy` → một `SecurityFilterChain` → `DispatcherServlet`.
2. Phân biệt **thứ tự chọn SecurityFilterChain** và **thứ tự Filter bên trong chain đã chọn**.
3. Chỉ ra nhiệm vụ và quan hệ của `SecurityContextHolderFilter`, `HeaderWriterFilter`, `CorsFilter`, `CsrfFilter`, `LogoutFilter`, `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, `AnonymousAuthenticationFilter`, `ExceptionTranslationFilter` và `AuthorizationFilter`.
4. Giải thích vì sao `CsrfFilter` có thể chặn POST trước khi HTTP Basic authentication được xử lý.
5. Mô tả sự khác nhau giữa 401 vì thiếu/sai credential và 403 vì thiếu quyền/CSRF.
6. Hiểu `ExceptionTranslationFilter` **chỉ bắt exception thuộc phạm vi downstream mà nó bao bọc**, không phải mọi lỗi từ cả chuỗi.
7. Chọn vị trí custom filter bằng `addFilterBefore`/`addFilterAfter` theo điều kiện tiên quyết; không nhầm `addFilterAt` với việc tự loại bỏ filter cũ.
8. Tránh đăng ký custom filter hai lần qua Spring Boot servlet filter auto-registration và `HttpSecurity`.
9. Phân biệt `securityMatcher`, `requestMatchers`, `@Order` và `permitAll`; không để URL nằm ngoài mọi chain.
10. Quan sát filter list bằng DEBUG/TRACE và viết MockMvc tests kiểm thứ tự thật cùng các trường hợp 200/401/403/500.
11. Hiểu giới hạn với session form login, JWT, multi-chain, ASYNC/ERROR dispatch và quyền trên tài nguyên nghiệp vụ.

## 2. Servlet Filter: thứ tự không chỉ là cách trình bày

`Filter` có thể đọc/sửa request, response, từ chối request sớm, hoặc gọi `chain.doFilter` để chuyển cho thành phần tiếp theo. Khi response quay lại, đoạn code sau `chain.doFilter` được thực thi theo thứ tự ngược, giống một stack:

```text
Request vào:
  Filter A.before
    Filter B.before
      Filter C.before
        DispatcherServlet -> Controller
      Filter C.after
    Filter B.after
  Filter A.after
Response ra.
```

Với exception, câu lệnh sau `chain.doFilter` không nhất thiết chạy nếu filter không dùng `finally`. Vì vậy lifecycle của `SecurityContext`, response headers và exception handling đều cần được thiết kế theo thứ tự.

Snippet cơ bản:

```java
@Override
public void doFilter(ServletRequest request,
        ServletResponse response, FilterChain chain)
        throws IOException, ServletException {

    prepareRequest(request);
    try {
        chain.doFilter(request, response);
    } finally {
        finishRequest(response);
    }
}
```

Đây là **snippet giải thích**, không phải file độc lập vì `prepareRequest`/`finishRequest` là method do ứng dụng định nghĩa. Trong thực tế không phải filter nào cũng bắt buộc tiếp tục: `CsrfFilter` từ chối POST thiếu token sẽ dừng xử lý, và controller sẽ không chạy.

**Quy tắc:** Đừng suy luận “mọi filter trong log khởi động đều đã chạy trên request này”. Danh sách đăng ký nói các filter có thể chạy; **short-circuit** và request matcher quyết định filter nào thực sự được gọi.

## 3. Tầng bên ngoài: container, DelegatingFilterProxy và FilterChainProxy

### 3.1. Sơ đồ đầy đủ

```text
HTTP request
    |
    v
Servlet container (Tomcat/Jetty/Undertow)
    |
    v
Container FilterChain
    |
    +-- các Servlet Filter khác (nếu được đăng ký)
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy (Spring-managed Filter)
    |
    +-- HttpFirewall và request matching
    |
    +-- chọn SecurityFilterChain ĐẦU TIÊN phù hợp
          |
          +-- SecurityContextHolderFilter
          +-- protection filters (headers/CORS/CSRF...)
          +-- LogoutFilter
          +-- authentication filters (Basic/form/Bearer...)
          +-- AnonymousAuthenticationFilter
          +-- ExceptionTranslationFilter
          +-- AuthorizationFilter
          |
          v
DispatcherServlet -> Controller -> Service
    |
    v
Response quay ngược qua filters
```

`DelegatingFilterProxy` là adapter giữa lifecycle Servlet container và một filter bean do Spring quản lý. `FilterChainProxy` là filter bean đứng sau adapter, có nhiệm vụ giữ các `SecurityFilterChain` và chọn chain phù hợp. Trong Spring Boot có `spring-boot-starter-security`, đăng ký proxy thường được Boot xử lý; bạn thường khai báo bean `SecurityFilterChain` chứ không tự tạo `web.xml`.

`FilterChainProxy` còn tích hợp `HttpFirewall` khi xử lý request và đảm bảo các lifecycle bảo mật quan trọng như cleanup security context. Không tự đăng ký thủ công từng Spring Security Filter trực tiếp với container để “tối ưu” rồi vô tình bỏ qua bảo vệ của proxy.

### 3.2. Chain selection là bước đầu tiên

Mỗi `SecurityFilterChain` có một `RequestMatcher`, và `FilterChainProxy` thử theo thứ tự. **Chỉ chain phù hợp đầu tiên chạy**; các chain còn lại không được ghép thêm filter vào request đó.

```text
Chains theo thứ tự:
  @Order(1)  matcher /api/**   -> Basic + stateless API
  @Order(2)  matcher /admin/** -> chính sách admin
  mặc định   matcher any       -> giao diện web còn lại

GET /api/tasks:
  chọn chain #1, KHÔNG chạy tiếp chain #2 hoặc default.

GET /home:
  thử #1 không match, #2 không match,
  chọn default.
```

Nếu request **không match chain nào**, Spring Security có thể không bảo vệ request đó; đây là lỗ hổng cấu hình rất nghiêm trọng, đặc biệt khi khai báo một chain có `securityMatcher("/api/**")` mà quên catch-all chain cho các đường còn lại.

### 3.3. Hai thứ tự độc lập

| Cấu hình | Nó sắp xếp cái gì? | Không có nghĩa gì? |
| --- | --- | --- |
| `@Order(1)` của bean `SecurityFilterChain` | Chain nào được thử matcher trước | Không thay vị trí `BasicAuthenticationFilter` bên trong chain |
| `http.securityMatcher("/api/**")` | Chọn request được chain này bảo vệ | Không thay authorization rule ở các chain khác |
| `http.authorizeHttpRequests().requestMatchers(...)` | Chọn rule phân quyền **sau khi chain đã match** | Không làm chain match thêm đường dẫn mới |
| `http.addFilterAfter(...)` | Vị trí một filter **trong chain đã chọn** | Không thay thứ tự container-level filter |
| Servlet `FilterRegistrationBean`/`@Order` | Thứ tự Filter ở cấp container | Không tương đương `HttpSecurity` filter order |

Thứ tự gọi các DSL methods trong Java cũng **không** là thứ tự thực thi: viết `.authorizeHttpRequests(...)` trước `.httpBasic(...)` trong source không làm `AuthorizationFilter` chạy trước `BasicAuthenticationFilter`. `HttpSecurity.build()` dùng ordering rules của framework.

## 4. Thứ tự nhóm filter trong một chain

Spring Security 6.5 reference khuyến nghị học theo các **mốc chức năng**:

```text
┌──────────────────────────────────────────────┐
│ SecurityContext được load/chuẩn bị            │
│ SecurityContextHolderFilter                   │
├──────────────────────────────────────────────┤
│ Bảo vệ request: headers, CORS, CSRF           │
│ HeaderWriterFilter / CorsFilter / CsrfFilter  │
├──────────────────────────────────────────────┤
│ LogoutFilter (nếu request là logout)           │
├──────────────────────────────────────────────┤
│ Xác thực credential theo mechanism           │
│ Form / Basic / Bearer / OAuth2 / X.509 ...    │
├──────────────────────────────────────────────┤
│ AnonymousAuthenticationFilter và hỗ trợ       │
│ RequestCacheAwareFilter, request wrappers ... │
├──────────────────────────────────────────────┤
│ ExceptionTranslationFilter                    │
│ Bao downstream và xử lý security exceptions  │
├──────────────────────────────────────────────┤
│ AuthorizationFilter                           │
│ Cho qua/từ chối theo luật HTTP authorization │
└──────────────────────────────────────────────┘
                      |
                      v
             DispatcherServlet / Controller
```

Đây là **các nhóm** chứ không phải danh sách đầy đủ. Tùy app có thể có `DisableEncodeUrlFilter`, `WebAsyncManagerIntegrationFilter`, `SessionManagementFilter`, `ConcurrentSessionFilter`, `RememberMeAuthenticationFilter`, `DefaultLoginPageGeneratingFilter` và nhiều authentication filters khác.

### 4.1. Một filter list minh họa từ tài liệu chính thức

Một cấu hình có form login + HTTP Basic có thể in:

```text
DisableEncodeUrlFilter
WebAsyncManagerIntegrationFilter
SecurityContextHolderFilter
HeaderWriterFilter
CsrfFilter
LogoutFilter
UsernamePasswordAuthenticationFilter
DefaultLoginPageGeneratingFilter
DefaultLogoutPageGeneratingFilter
BasicAuthenticationFilter
RequestCacheAwareFilter
SecurityContextHolderAwareRequestFilter
AnonymousAuthenticationFilter
ExceptionTranslationFilter
AuthorizationFilter
```

**Không học thuộc danh sách này như chân lý tuyệt đối.** Bật/tắt form login, OAuth2 Resource Server, CORS, request cache, session hoặc thay đổi version làm danh sách khác. Xem DEBUG log `DefaultSecurityFilterChain` và danh sách filter của **đúng chain đã match request**, không lấy chuỗi được copy từ blog khác.

## 5. Nhóm ngữ cảnh: SecurityContextHolderFilter

`SecurityContextHolderFilter` hỗ trợ lấy `SecurityContext` từ `SecurityContextRepository` và làm context có thể truy cập qua `SecurityContextHolder` trong phạm vi request. Holder mặc định dùng `ThreadLocal` cho ứng dụng Servlet, còn filter/framework phải dọn đúng khi request kết thúc.

```text
Request A: có session authentication Alice
  SecurityContextHolderFilter -> có thể khôi phục Alice.

Request B: stateless, mang Basic Authorization header
  SecurityContextHolderFilter -> ban đầu thường trống.
  BasicAuthenticationFilter -> xác thực Alice sau đó.

Request C: anonymous
  SecurityContextHolderFilter -> context ban đầu trống.
  AnonymousAuthenticationFilter -> có thể đặt anonymous.
```

Không được kết luận rằng sau khi `SecurityContextHolderFilter` chạy là “đã xác thực xong” — nó chuẩn bị/khôi phục context, **không tự kiểm username/password**. Ngược lại, cũng không được khẳng định “luôn null trước Basic”: một `HttpSession` hợp lệ có thể cung cấp authentication từ request trước.

**Load / save / clear là ba việc khác nhau:**

- **Load:** cung cấp context cho request hiện tại.
- **Save:** lưu context ở repository/session theo chính sách để request sau có thể khôi phục. Với custom authentication trong Spring Security 6 có thể cần explicit `SecurityContextRepository.saveContext(context, request, response)`.
- **Clear:** dọn context của thread sau request; **không đồng nghĩa logout** hoặc xóa session/refresh token.

Với `SessionCreationPolicy.STATELESS`, ứng dụng thường xác thực từ credential/token ở request mới thay vì server session. Với form login, repository/session và saved-request behavior có thể khác. Đừng tự `clearContext()` ở giữa controller rồi làm phần còn lại mất principal.

## 6. Nhóm bảo vệ: headers, CORS, CSRF và Logout

### 6.1. HeaderWriterFilter

`HeaderWriterFilter` tạo những browser security headers được cấu hình, ví dụ `X-Content-Type-Options: nosniff`. Tùy implementation, header được xử lý ở chiều response hoặc khi commit, không có nghĩa nó chỉ chạy mã “trước” controller.

`permitAll()` trên một URL **không bỏ qua** HeaderWriterFilter nếu URL vẫn đi qua chain. Trái lại, `web.ignoring()` hoặc URL không match bất kỳ chain nào có thể bỏ luôn các security filters cần thiết.

### 6.2. CorsFilter phải xử lý preflight trước yêu cầu login

Một browser có thể gửi:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://frontend.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Preflight thường không mang cookie `JSESSIONID` và không có thông tin authentication như request chính. Nếu hệ thống kiểm login trước khi xử lý CORS, preflight có thể bị từ chối sai. Spring Security có tích hợp:

```java
http.cors(Customizer.withDefaults());
```

Nhưng cấu hình này cần có `CorsConfigurationSource` hoặc Spring MVC CORS configuration thích hợp. **CORS không phải authentication và cũng không thay CSRF**. Không chữa preflight bằng `anyRequest().permitAll()` hoặc mở Origin toàn cục mà không hiểu trust boundary.

### 6.3. CsrfFilter có thể chặn POST trước Basic authentication

`CsrfFilter` kiểm CSRF token ở những request cần bảo vệ; mặc định GET/HEAD/OPTIONS/TRACE thường được xem là safe methods, còn POST/PUT/PATCH/DELETE thường cần token khi CSRF enabled.

**Luồng quan trọng:**

```text
POST /notes
Authorization: Basic writer:demo-pass
CSRF token: KHÔNG CÓ

SecurityContextHolderFilter
  -> HeaderWriterFilter
  -> CsrfFilter: token thiếu -> AccessDeniedHandler -> 403
  -> DỪNG

BasicAuthenticationFilter: có thể CHƯA chạy.
AuthorizationFilter:      có thể CHƯA chạy.
Controller:               không chạy.
```

Vì vậy **403 CSRF không chứng minh password đúng**. Khi muốn kiểm quyền `NOTE_WRITE` trên POST, trước hết test với CSRF token hợp lệ. Đừng tắt CSRF toàn app để làm bài test xanh; phải xét browser cookie/Basic tự gắn và threat model thực tế. Một Bearer API chỉ dùng explicit Authorization header trong non-browser clients có thể có chính sách khác, nhưng cần thiết kế rõ.

### 6.4. LogoutFilter không phải một authentication filter thông thường

`LogoutFilter` đứng ở giai đoạn sớm trước nhiều authentication filters và có thể xử lý logout request: gọi logout handlers, xóa context/session theo chính sách, chuyển hướng hoặc trả response. Nó không chứng minh mọi request đã authenticate, không tự revoke JWT ở issuer hoặc toàn bộ refresh token trong một hệ thống phân tán. Khi filter quyết định logout thành công, downstream có thể không chạy.

## 7. Nhóm xác thực: từ credential đến Authentication

| Loại login | Filter điển hình | Nguồn credential |
| --- | --- | --- |
| HTTP Basic | `BasicAuthenticationFilter` | `Authorization: Basic ...` |
| Form login | `UsernamePasswordAuthenticationFilter` | POST login form |
| Bearer JWT/OAuth2 Resource Server | `BearerTokenAuthenticationFilter` | `Authorization: Bearer ...` |
| OAuth2 Login | `OAuth2LoginAuthenticationFilter` + filters khác | Redirect/callback/code |
| X.509 | `X509AuthenticationFilter` | Client certificate đã kiểm tra từ TLS |
| Pre-auth | `AbstractPreAuthenticatedProcessingFilter` hoặc implementation | Principal đã được upstream tin cậy |

Chỉ những filter được cấu hình mới xuất hiện. Authentication filter thường trích credential, tạo `Authentication` chưa xác thực, gọi `AuthenticationManager`/`AuthenticationProvider`, rồi đặt `Authentication` đã xác minh vào `SecurityContext` và xử lý success/failure.

**Password hợp lệ không đồng nghĩa có đủ quyền.** Alice có `ROLE_USER` vẫn không tự được vào URL cần `ROLE_ADMIN`. Authentication trả lời *ai đang gọi*; authorization trả lời *được làm gì*; object-level policy còn phải xét *trên tài nguyên nào, của tenant nào*.

### 7.1. BasicAuthenticationFilter và lỗi 401

Khi `BasicAuthenticationFilter` nhận credential sai, nó có thể tự dùng `AuthenticationEntryPoint`/failure handling để trả `401` và dừng filter chain **trước khi đến `AuthorizationFilter`**. Với anonymous GET protected không có Basic header, Basic filter thường cho đi tiếp, `AnonymousAuthenticationFilter` đặt anonymous, rồi authorization từ chối và `ExceptionTranslationFilter` kích hoạt entry point. Cả hai có thể trả 401 nhưng **đường đi khác nhau**.

### 7.2. RequestCacheAwareFilter và anonymous

`RequestCacheAwareFilter` hỗ trợ khôi phục saved request ở các flow redirect/form login. Nó không phải password provider. `AnonymousAuthenticationFilter` điền một `AnonymousAuthenticationToken` khi chưa có Authentication, giúp các thành phần xử lý anonymous thống nhất.

Một bẫy:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // KHÔNG đủ để coi là user đã đăng nhập hợp lệ.
}
```

Với anonymous token, cờ `isAuthenticated()` có thể true. Dùng `authenticated()`/`hasAuthority`/`AuthenticationTrustResolver` hoặc method security thay vì tự cấp phép bằng cờ này.

## 8. Nhóm phân quyền và dịch exception

`AuthorizationFilter` đánh giá các rule `authorizeHttpRequests(...)`. `ExceptionTranslationFilter` thường đứng ngay trước vùng authorization, gọi downstream bên trong `try/catch` để xử lý `AuthenticationException` hoặc `AccessDeniedException` thích hợp.

```text
ExceptionTranslationFilter
  try {
      AuthorizationFilter
        -> granted: DispatcherServlet
        -> denied: AccessDeniedException
  } catch (AuthenticationException | AccessDeniedException) {
      nếu cần login: AuthenticationEntryPoint
      nếu đã authenticated nhưng không đủ quyền: AccessDeniedHandler
  }
```

Trường hợp điển hình:

| Request | Điểm chặn | Response trong HTTP Basic lab |
| --- | --- | --- |
| GET /me anonymous | AuthorizationFilter → ExceptionTranslationFilter | 401 |
| GET /me credential sai | BasicAuthenticationFilter failure | 401 |
| GET /admin Alice đúng password | AuthorizationFilter → ExceptionTranslationFilter | 403 |
| POST /notes writer đúng nhưng thiếu CSRF | CsrfFilter (upstream) | 403 |
| POST /notes Alice đúng + CSRF hợp lệ nhưng thiếu NOTE_WRITE | AuthorizationFilter | 403 |
| POST /notes writer đúng + CSRF hợp lệ | Cho vào controller | 200 |

**Giới hạn quan trọng:** `ExceptionTranslationFilter` **không bắt mọi lỗi** ở filter đứng trước nó. Một exception do custom filter đặt trước `ExceptionTranslationFilter` ném ra có thể không được xử lý bởi nó. `CsrfFilter` có handler lỗi riêng; Basic authentication filter cũng có cơ chế failure riêng. Lỗi nghiệp vụ không phải security exception không tự đổi thành HTTP 401/403.

Nếu cần custom access checks, ưu tiên `AuthorizationManager`, `authorizeHttpRequests`, method security hoặc kiểm owner/tenant ở service; không vội viết custom filter ném `AccessDeniedException` ở một vị trí chưa được wrapper bảo vệ.

## 9. Ví dụ ba request đi qua filter chain

### 9.1. Basic GET /me đúng mật khẩu

```text
GET /me, Authorization Basic của Alice

FilterChainProxy chọn matching chain
  -> SecurityContextHolderFilter: context khả dụng
  -> CsrfFilter: GET thường không cần CSRF
  -> LogoutFilter: không phải logout
  -> BasicAuthenticationFilter: xác thực Alice
  -> AnonymousAuthenticationFilter: không thay Alice
  -> ExceptionTranslationFilter: bao downstream
  -> AuthorizationFilter: authenticated() = PASS
  -> Controller: "me:alice"
  -> Cleanup context ở cuối request
```

### 9.2. Anonymous GET /me

```text
GET /me không Authorization header
  -> BasicAuthenticationFilter: không có credential, tiếp tục
  -> AnonymousAuthenticationFilter: anonymous
  -> AuthorizationFilter: cần authenticated, từ chối
  -> ExceptionTranslationFilter: kích hoạt Basic entry point, 401
  -> Controller không chạy
```

### 9.3. GET /admin của Alice

```text
GET /admin, password Alice đúng
  -> BasicAuthenticationFilter: Alice authenticated, ROLE_USER
  -> AuthorizationFilter: yêu cầu ROLE_ADMIN, từ chối
  -> ExceptionTranslationFilter: AccessDeniedHandler, 403
  -> Controller không chạy
```

### 9.4. POST /notes thiếu CSRF

```text
POST /notes, Basic của writer đúng nhưng token CSRF thiếu
  -> CsrfFilter: 403, dừng
  -> Không thể kết luận Basic filter đã kiểm password
```

### 9.5. POST /notes có CSRF nhưng thiếu quyền

```text
POST /notes, Basic Alice đúng, CSRF hợp lệ
  -> CsrfFilter pass
  -> BasicAuthenticationFilter xác thực Alice
  -> AuthorizationFilter cần NOTE_WRITE nhưng Alice thiếu
  -> ExceptionTranslationFilter chuyển thành 403
```

Hai request cùng status **403** có thể có nguyên nhân khác nhau. Test/filter trace phải phân biệt được nơi request dừng.

## 10. Mẫu ứng dụng chạy được: thấy trước/sau Basic authentication

**Cách làm:** tạo một Spring Security chain HTTP Basic stateless với ba user in-memory/BCrypt. Chèn **hai custom probe filters** chỉ ghi request attributes:
- `ContextProbeFilter` đứng sau `SecurityContextHolderFilter`, trước `BasicAuthenticationFilter`.
- `AfterAuthenticationProbeFilter` đứng sau `AnonymousAuthenticationFilter`, trước `ExceptionTranslationFilter`/`AuthorizationFilter`.
- Endpoint `GET /flow` đọc ba mốc `before`, `after` và `controller`.
- Kiểm thử thứ tự thực tế bằng `FilterChainProxy.getFilters(...)` và hành vi qua MockMvc.

**Không biến probe thành auth mechanism:** chúng không sửa principal/roles hoặc trả response nhạy cảm ra Internet. Mọi user/password mẫu trong bài chỉ dùng localhost.

### 10.1. Cấu trúc

```text
servlet-filter-order-demo/
├── pom.xml
└── src/
    ├── main/java/demo/filterorder/FilterOrderApplication.java
    └── test/java/demo/filterorder/FilterOrderTests.java
```

Java 17, Spring Boot `3.5.16`, Spring Security 6.5.x theo Boot BOM. Bản 3.5.16 phát hành ngày 25/06/2026 và là bản OSS cuối của nhánh 3.5; khi làm sản phẩm mới, chọn dòng Boot được hỗ trợ và cập nhật code/test phù hợp.

### 10.2. pom.xml đầy đủ

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>servlet-filter-order-demo</artifactId>
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
```

### 10.3. Ứng dụng Java đầy đủ

Tạo `src/main/java/demo/filterorder/FilterOrderApplication.java`:

```java
package demo.filterorder;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class FilterOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterOrderApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class LabSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTE_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/me", "/flow", "/boom")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTE_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(Customizer.withDefaults())
            // Probe 1: context được chuẩn bị; Basic chưa chạy.
            .addFilterAfter(
                new ContextProbeFilter(),
                SecurityContextHolderFilter.class)
            // Probe 2: sau các auth filters và anonymous fallback.
            .addFilterAfter(
                new AfterAuthenticationProbeFilter(),
                AnonymousAuthenticationFilter.class)
            .build();
    }
}

// Không @Component / @Bean: chỉ register bên trong SecurityFilterChain.
class ContextProbeFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        request.setAttribute("phase.before", PhaseNames.current());
        chain.doFilter(request, response);
    }
}

class AfterAuthenticationProbeFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        request.setAttribute("phase.after", PhaseNames.current());
        chain.doFilter(request, response);
    }
}

final class PhaseNames {
    private PhaseNames() { }

    static String current() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "none" : auth.getName();
    }
}

@RestController
class LabRoutes {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication auth) {
        return "me:" + auth.getName();
    }

    @GetMapping("/flow")
    String flow(HttpServletRequest request, Authentication auth) {
        return "before=" + request.getAttribute("phase.before")
            + ";after=" + request.getAttribute("phase.after")
            + ";controller=" + auth.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/notes")
    String createNote(Authentication auth) {
        return "created:" + auth.getName();
    }

    @GetMapping("/boom")
    String boom() {
        throw new ResponseStatusException(
            HttpStatus.INTERNAL_SERVER_ERROR, "lab error");
    }
}
```

### 10.4. Đọc code theo thứ tự

- `UserDetailsService` cung cấp users/password hashes; `PasswordEncoder` bcrypt giúp provider kiểm credential.
- `SecurityFilterChain` tạo URL rules. `HttpSecurity` vẫn đặt filter đúng order dù source gọi `authorizeHttpRequests` trước `httpBasic`.
- `ContextProbeFilter` sau `SecurityContextHolderFilter`: trong demo stateless Basic, thường đọc `none` vì chưa xác thực.
- `BasicAuthenticationFilter` chạy sau CSRF và logout groups, kiểm password.
- `AfterAuthenticationProbeFilter` sau `AnonymousAuthenticationFilter`: với Basic hợp lệ nó đọc username đã xác thực.
- `AuthorizationFilter` sau probe quyết định role/authority, có thể từ chối trước controller.
- Hai probe không là bean, tránh Boot auto-register thêm một lần ở container ngoài Spring Security.
- `/boom` được phép vào với user authenticated để kiểm filter cleanup sau response lỗi.
- User mẫu `demo-pass` có trong source công khai: **không bao giờ deploy app demo ra mạng public**.
- CSRF vẫn bật. Muốn POST thành công qua MockMvc phải đính token hợp lệ; curl đơn giản không có token sẽ bị 403.

```text
GET /flow với alice đúng password:
    ContextProbeFilter        -> "none"
    BasicAuthenticationFilter -> Alice
    AfterAuthenticationProbe  -> "alice"
    AuthorizationFilter       -> Alice được phép
    Controller                -> "alice"

Body kỳ vọng:
before=none;after=alice;controller=alice
```

Nếu dùng session-based form login với authentication được khôi phục trước Basic, giá trị `before` có thể là user đã login. Đây là **tính chất của demo stateless**, không phải định luật mọi chain.

## 11. MockMvc test: kiểm thứ tự bằng FilterChainProxy và request thật

Tạo `src/test/java/demo/filterorder/FilterOrderTests.java`:

```java
package demo.filterorder;

import java.util.List;

import jakarta.servlet.Filter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.access.ExceptionTranslationFilter;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterOrderTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy proxy;

    private int indexOf(Class<? extends Filter> type) {
        // Convenience method kiểm path.
        // Với RequestMatcher phụ thuộc method/header,
        // kiểm thêm request thực qua MockMvc.
        List<Filter> filters = proxy.getFilters("/flow");
        assertNotNull(filters);

        for (int i = 0; i < filters.size(); i++) {
            if (type.isInstance(filters.get(i))) {
                return i;
            }
        }
        throw new AssertionError("Missing: " + type.getName());
    }

    @Test
    void filtersAreOrderedByDependenciesNotJavaDslOrder() {
        int context = indexOf(SecurityContextHolderFilter.class);
        int early = indexOf(ContextProbeFilter.class);
        int csrfFilter = indexOf(CsrfFilter.class);
        int logout = indexOf(LogoutFilter.class);
        int basic = indexOf(BasicAuthenticationFilter.class);
        int anon = indexOf(AnonymousAuthenticationFilter.class);
        int late = indexOf(AfterAuthenticationProbeFilter.class);
        int translator = indexOf(ExceptionTranslationFilter.class);
        int authorization = indexOf(AuthorizationFilter.class);

        assertTrue(context < early);
        assertTrue(early < csrfFilter);
        assertTrue(csrfFilter < logout);
        assertTrue(logout < basic);
        assertTrue(basic < anon);
        assertTrue(anon < late);
        assertTrue(late < translator);
        assertTrue(translator < authorization);
    }

    @Test
    void showsBeforeAndAfterBasicAuthentication() throws Exception {
        mvc.perform(get("/flow")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "before=none;after=alice;controller=alice"));

        mvc.perform(get("/flow")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "before=none;after=writer;controller=writer"));

        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());
    }

    @Test
    void distinguishesAuthenticationFromAuthorization()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("alice", "bad")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void csrfCanDenyBeforeAuthenticationAndAuthorization()
            throws Exception {
        // Writer có NOTE_WRITE, nhưng CSRF thiếu.
        mvc.perform(post("/notes")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        // CSRF hợp lệ, nhưng Alice thiếu NOTE_WRITE.
        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Writer đúng credential + CSRF + NOTE_WRITE.
        mvc.perform(post("/notes")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:writer"));
    }

    @Test
    void errorAndNextRequestDoNotKeepPreviousIdentity()
            throws Exception {
        mvc.perform(get("/boom")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isInternalServerError());

        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Ý nghĩa test:**

- `indexOf(...)` lấy danh sách filter thật của Spring Security và khẳng định quan hệ thứ tự: context → CSRF → logout → Basic → anonymous → exception translator → authorization.
- `getFilters(String)` chỉ là tiện ích test URL. Với matcher phụ thuộc HTTP method/headers/dispatcher, nó không thay được MockMvc request.
- `/flow` với Alice/Writer chứng minh danh tính xuất hiện sau `BasicAuthenticationFilter`, không phải từ biến global trong controller.
- `httpBasic(...)` đi qua đường password authentication thật. `@WithMockUser` chỉ tiêm user giả, không đủ để test provider/encoder.
- `CsrfFilter` và `AuthorizationFilter` có thể cùng tạo HTTP 403 vì nguyên nhân khác; test cả thiếu token, thiếu authority và thành công.
- Test `/boom` với HTTP 500 cho thấy request sau không tự nhận authentication của Alice, và context trong thread test được dọn.
- `/public` có status 200 nhưng vẫn nhận security header `nosniff`, chứng minh `permitAll` khác việc bỏ security chain.
- Password demo không có ý nghĩa bảo mật; toàn bộ lab chỉ phục vụ học tập.

## 12. Chạy Maven và quan sát

Ở thư mục dự án:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Các kết quả kỳ vọng**, không phải kết quả đã thực thi lúc soạn bài:

| Request | User/token | HTTP/body kỳ vọng |
| --- | --- | --- |
| GET /public | Anonymous | 200, `public` |
| GET /me | Anonymous | 401 |
| GET /me | Alice sai password | 401 |
| GET /flow | Alice đúng password | 200, `before=none;after=alice;controller=alice` |
| GET /flow | Writer đúng password | 200, `before=none;after=writer;controller=writer` |
| GET /admin | Alice đúng password | 403 |
| GET /admin | Admin đúng password | 200, `admin` |
| POST /notes | Writer, thiếu CSRF | 403 |
| POST /notes | Writer, CSRF sai | 403 |
| POST /notes | Alice, CSRF đúng | 403 |
| POST /notes | Writer, CSRF đúng | 200, `created:writer` |
| GET /boom | Alice đúng password | 500 |
| GET /me ngay sau /boom | Anonymous | 401 |
| GET /unknown | Alice đúng password | 403 |

Thử bằng curl **chỉ trên localhost** (curl sẽ hỏi mật khẩu `demo-pass` khi dùng `-u`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/flow
curl -i -u writer http://localhost:8080/flow
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Không lưu raw Basic header/password trong log hoặc shell history. Base64 của Basic authentication **không mã hóa** password; môi trường thật bắt buộc HTTPS. Để test POST với CSRF token hợp lệ, dùng MockMvc như ví dụ.

## 13. Cách thêm custom filter đúng vị trí

### 13.1. Câu hỏi trước khi thêm filter

1. Filter cần `SecurityContext` đã được chuẩn bị chưa?
2. Nó cần **authenticated user** hay có thể xử lý anonymous?
3. Nó kiểm credential hay kiểm permission/tenant?
4. Nó phải chạy trước hoặc sau `CsrfFilter`/`LogoutFilter`?
5. Nếu nó ném `AccessDeniedException`, có đứng trong phạm vi `ExceptionTranslationFilter` bao bọc không?
6. Nó có bị Boot auto-register với Servlet container không?

| Nhiệm vụ | Vị trí/hướng giải quyết thường phù hợp | Cảnh báo |
| --- | --- | --- |
| Khởi tạo metadata/trace khi context sẵn | Sau `SecurityContextHolderFilter` | Auth có thể chưa xuất hiện |
| Custom authentication mechanism | Spring docs gợi ý sau `LogoutFilter` | Tự thiết kế provider/success/failure/context save |
| Cần đọc principal sau các auth mechanisms | Sau `AnonymousAuthenticationFilter` | Anonymous vẫn có principal; exception từ đây có thể đứng trước translator |
| Tự ném AccessDeniedException muốn translator bắt | Downstream của `ExceptionTranslationFilter` và trước nơi cần chặn | Cẩn thận order/anchor, tốt hơn dùng `AuthorizationManager` |
| URL/method permission | `authorizeHttpRequests` | Không nhất thiết viết filter riêng |
| Object owner/tenant permission | Service/method security | Không chỉ phụ thuộc path hoặc username |
| CORS | `http.cors(...)` | Preflight cần xử lý sớm |
| Security headers | `http.headers(...)` | Tránh custom filter không cần thiết |

### 13.2. Ba API sắp filter

```java
http.addFilterBefore(customFilter, AnchorFilter.class);
http.addFilterAfter(customFilter, AnchorFilter.class);
http.addFilterAt(customFilter, AnchorFilter.class);
```

Đây là **snippet**: các class `customFilter`/`AnchorFilter` chưa định nghĩa nên không phải chương trình độc lập. `addFilterBefore/After` xác định thứ tự tương đối với một filter đã biết. `addFilterAt` đặt ở cùng order slot; **đừng giả định nó xóa filter mặc định đã được DSL khác đăng ký**. Nếu cả DSL `httpBasic(...)` và một `BasicAuthenticationFilter` tùy chỉnh cùng tồn tại, bạn có thể gặp hành vi trùng/khó xác định. Khi cần thay một filter built-in, xem DSL configurer tương ứng để thay/disable đúng cơ chế.

### 13.3. Vì sao addFilterBefore(BasicAuthenticationFilter.class) có thể sai?

Nếu custom filter cần kiểm `ROLE_ADMIN` của user Basic, đặt **trước `BasicAuthenticationFilter`** trong API stateless có thể khiến nó đọc được context rỗng. Chỉ dùng vị trí này khi filter thực sự muốn **tự thực hiện authentication** hoặc logic trước Basic, không phải kiểm quyền đã xác minh.

### 13.4. Custom Filter bị đăng ký hai lần

Nếu viết:

```java
@Component
class MySecurityFilter extends OncePerRequestFilter {
    // Implementation.
}

// Sau đó lại:
http.addFilterAfter(mySecurityFilter, BasicAuthenticationFilter.class);
```

Spring Boot có thể auto-register `@Component Filter` ở **container-level**, trong khi `HttpSecurity` đăng ký thêm bên trong Spring Security chain. Có thể bị chạy hai lần hoặc chạy ngoài thứ tự tưởng tượng.

Giải pháp:
- Không khai báo bean khi có thể tạo filter trực tiếp với `new` trong `HttpSecurity`.
- Nếu cần DI/bean, dùng `FilterRegistrationBean<MySecurityFilter>` với `setEnabled(false)` để chặn container registration; vẫn add bean vào chain.
- Test đếm invocation trong môi trường có filter thực, kể cả khi request lỗi.

Snippet:

```java
@Bean
FilterRegistrationBean<MySecurityFilter> disableContainerRegistration(
        MySecurityFilter filter) {
    FilterRegistrationBean<MySecurityFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

## 14. Nhiều SecurityFilterChain: first match wins

Một cấu hình riêng **để hiểu chain selection**, không dùng cùng lúc với app demo mục 10:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("API_USER"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

`/api/orders` chỉ dùng filter của chain API; không tự nhận filter form login từ fallback chain. `/home` dùng fallback. `anyRequest` trong API chain chỉ áp dụng URL đã match `/api/**`. Nếu bỏ fallback, một URL ngoài `/api/**` có thể không qua Spring Security.

**Endpoint do filter cung cấp:** Khi dùng `formLogin()`, filter có thể tạo `GET /login` và `POST /login`. Nếu chain có `securityMatcher("/secured/**")` mà login URL lại là `/login`, đường login nằm ngoài matcher và có thể không hoạt động. Định nghĩa `loginPage/loginProcessingUrl` phù hợp phạm vi chain.

`permitAll` vẫn đi qua security filters; `web.ignoring` và “không match chain nào” là bỏ qua filters. Với URL public nên ưu tiên chính sách cho phép tường minh, giữ headers/CSRF nơi phù hợp.

## 15. Đọc logs thay vì đoán

Trong cấu hình **chỉ dành cho local/test**:

```properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

DEBUG lúc startup thường in dạng:

```text
Will secure any request with [
  SecurityContextHolderFilter, HeaderWriterFilter,
  CsrfFilter, LogoutFilter, BasicAuthenticationFilter,
  AnonymousAuthenticationFilter,
  ExceptionTranslationFilter, AuthorizationFilter
]
```

List trên là **dạng rút gọn minh họa**, không phải output chính xác của một lần chạy hoặc danh sách đầy đủ. Ứng dụng demo còn có hai probe filters và một số hỗ trợ khác. TRACE trong runtime có thể in:

```text
Securing GET /me
Invoking SecurityContextHolderFilter (index/total)
Invoking CsrfFilter (index/total)
Invoking BasicAuthenticationFilter (index/total)
...
Invoking AuthorizationFilter (index/total)
Secured GET /me
```

`index/total` là ký hiệu chú thích, không phải chỉ số thực. Nếu request bị chặn sớm thì không có log invocation của filters sau đó. Đừng bật TRACE dài hạn trên production hoặc log password, Basic/Bearer headers, cookies, token và raw `Authentication`.

Một quy trình debug hiệu quả:

1. Xem URL/method/dispatcher và reverse-proxy rewrite.
2. Xác định **chain được chọn** và thứ tự `@Order`/`securityMatcher`.
3. Kiểm filter list bằng startup DEBUG hoặc `FilterChainProxy.getFilters(...)`.
4. Với POST 403, kiểm CSRF trước; với 401, kiểm authentication filter/entry point; với GET 403, kiểm authorities/authorization.
5. Với custom filter, kiểm anchor, exception scope, double registration và việc có gọi `chain.doFilter`.
6. Với session, kiểm context repository/save/load/clear.
7. Với ERROR/ASYNC dispatch, kiểm Servlet dispatcher types và `OncePerRequestFilter` behavior theo phiên bản.
8. Test lại bằng MockMvc với real credential + CSRF và kiểm route ngoài matcher.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Dựa vào thứ tự DSL lines | Tưởng authorize chạy trước Basic | Xem order của filter thật |
| Nghĩ mọi chain matching đều chạy | Dựa sai vào filter của chain khác | First matching SecurityFilterChain wins |
| Chỉ có chain `/api/**` nhưng còn /admin | URL ngoài matcher có thể không protected | Catch-all chain |
| Dùng `permitAll` như cách “bypass toàn bộ security” | Hiểu sai headers/CSRF | PermitAll chỉ là authorization rule |
| Dùng `web.ignoring` bừa bãi | Bỏ security headers và exploit protection | Ưu tiên permitAll |
| Bật CORS sau authentication | Preflight bị 401 | CORS xử lý trước |
| POST 403 thì chắc chắn user thiếu role | Có thể bị CSRF chặn | Test CSRF hợp lệ rồi kiểm quyền |
| Bad Basic password nên chờ AuthorizationFilter | Basic filter có thể tự 401 | Kiểm provider/entrypoint |
| Filter custom cần identity nhưng đặt trước Basic | Context có thể chưa có user | Đặt sau auth hoặc dùng AuthorizationManager |
| Custom filter ném AccessDeniedException trước translator | Lỗi không được dịch như mong đợi | Error handler riêng/đưa vào downstream/phương án authz |
| `addFilterAt` nghĩa là xóa built-in filter | Có thể duplicate | Disable/cấu hình DSL đúng |
| `@Component Filter` đồng thời addFilterAfter | Chạy hai lần hoặc sai order | Chỉ một registration path |
| Quên `chain.doFilter` trên happy path | Controller không bao giờ chạy | Chỉ short-circuit có chủ đích |
| Quên clear context ở custom thread | Rò danh tính khi reuse worker | Framework lifecycle/try-finally đúng phạm vi |
| Nghĩ logout = clear ThreadLocal | Session/JWT có thể còn hợp lệ | Logout/revoke policy riêng |
| Basic dùng HTTP ngoài localhost | Credential lộ trên mạng | HTTPS |
| Tự dùng `auth.isAuthenticated()` cho anonymous | Có thể cấp quyền sai | Spring authorization/trust resolver |
| Chỉ test với `@WithMockUser` | Không kiểm password/provider | MockMvc + httpBasic real |
| Chỉ có HTTP path role | IDOR/BOLA ở resource | Service owner/tenant checks |
| Copy Servlet filters sang WebFlux | Sai execution/context model | Reactive SecurityWebFilterChain |

## 17. Checklist review Pull Request

- [ ] Có xác nhận đúng Spring MVC/Servlet thay vì WebFlux?
- [ ] Có hiểu container FilterChain, DelegatingFilterProxy, FilterChainProxy và SecurityFilterChain?
- [ ] Có phân biệt filter ordering với chain selection order?
- [ ] Mọi URL cần bảo vệ đều match ít nhất một chain?
- [ ] Có default catch-all chain hoặc policy explicit deny cho URL khác?
- [ ] `SecurityContextHolderFilter` đặt context scope trước nơi cần đọc?
- [ ] CSRF/CORS/headers phù hợp threat model, preflight xử lý đúng?
- [ ] Authentication filters tồn tại khi config mechanism tương ứng?
- [ ] Anonymous principal không bị coi là login thật?
- [ ] ExceptionTranslationFilter bao authorization failures cần dịch?
- [ ] Không giả định nó xử lý mọi lỗi từ upstream filters?
- [ ] Custom filter đặt theo prerequisites, không theo vị trí dòng Java DSL?
- [ ] Có tránh double registration filter bean với Boot?
- [ ] Không dùng `addFilterAt` thay built-in một cách mơ hồ?
- [ ] Có test POST thiếu CSRF, token sai/đúng, thiếu authority?
- [ ] Có test GET anonymous 401, Basic sai 401, thiếu role 403, thành công 200?
- [ ] Có kiểm exception path, cleanup và request sau không thừa hưởng identity?
- [ ] Public route vẫn nhận headers phù hợp nếu `permitAll`?
- [ ] Có trace filter order ở đúng chain và gỡ TRACE trước production?
- [ ] Có kiểm method security và object/tenant authorization?
- [ ] Với session login, có kiểm SecurityContextRepository, saved request và logout?
- [ ] Với Bearer API, có kiểm JWT signature/issuer/audience/scope và policy CSRF phù hợp?
- [ ] Không đưa mật khẩu demo và debug endpoints lên production?

## 18. Tự đánh giá

**1.** Thứ tự `.authorizeHttpRequests(...)` trước `.httpBasic(...)` trong source làm authorization filter chạy trước Basic không?

**Đáp án:** Không. Spring Security sắp các filter theo order đăng ký trong `HttpSecurity`. Test list thật hoặc DEBUG logs.

**2.** Tại sao CSRF thiếu có thể trả 403 ngay cả khi Basic password đúng?

**Đáp án:** CsrfFilter đứng trước nhiều authentication filters và có thể chặn POST, nên Basic chưa chắc chạy.

**3.** Hai SecurityFilterChain cùng match URL có được ghép lại không?

**Đáp án:** Không. FilterChainProxy chỉ chọn chain đầu tiên match request.

**4.** `securityMatcher("/api/**")` cùng `anyRequest().authenticated()` có bảo vệ /admin không?

**Đáp án:** Chỉ nếu còn chain khác match /admin. `anyRequest` trong API chain chỉ áp dụng request đã match /api/**.

**5.** Vì sao `ExceptionTranslationFilter` đứng trước `AuthorizationFilter`?

**Đáp án:** Nó bao downstream và chuyển `AuthenticationException`/`AccessDeniedException` do authorization phát ra thành entrypoint/denied response.

**6.** Có thể đặt filter tự ném `AccessDeniedException` trước `ExceptionTranslationFilter` rồi trông chờ translator bắt không?

**Đáp án:** Không. Translator chỉ bắt exceptions của downstream nằm trong lời gọi `chain.doFilter` nó bao bọc.

**7.** `permitAll()` có làm `HeaderWriterFilter` biến mất không?

**Đáp án:** Không. Nó chỉ là authorization rule. Bypass chain là cơ chế khác và có thể mất headers/CSRF.

**8.** Tại sao `@Component` filter thêm bởi `addFilterAfter` có thể chạy hai lần?

**Đáp án:** Boot có thể auto-register Filter bean ở servlet container, còn HttpSecurity đăng ký trong Spring Security chain.

**9.** HTTP 401 Basic password sai và HTTP 401 anonymous cần login có cùng đường xử lý không?

**Đáp án:** Không nhất thiết. BasicAuthenticationFilter xử lý credential lỗi; anonymous authorization failure thường được ExceptionTranslationFilter chuyển sang AuthenticationEntryPoint.

**10.** Vì sao không chỉ test `@WithMockUser` để khẳng định thứ tự Basic authentication?

**Đáp án:** Mock principal bỏ qua credential provider. Test qua `httpBasic(...)` với user store/encoder thật.

## 19. Ghi nhớ cuối bài

1. **Thứ tự của filter là một phần của mô hình bảo mật**, không phải thứ tự dòng Java DSL.
2. **SecurityContext** được chuẩn bị trước, **CSRF/CORS/headers** bảo vệ request, **authentication filters** xác minh credential, **AuthorizationFilter** quyết định quyền.
3. **ExceptionTranslationFilter** bao downstream để dịch lỗi authz; không bao hết upstream failures.
4. **CSRF 403 không chứng minh password đúng**; phải phân biệt với 403 thiếu authority.
5. **FilterChainProxy chọn chain đầu tiên match**; `securityMatcher` khác `requestMatchers` và nên có catch-all policy.
6. **Custom filter đặt theo prerequisites**; tránh double registration và dùng đúng error-handling scope.
7. **Kiểm bằng evidence**: DEBUG/TRACE, actual filter list, MockMvc với 200/401/403/500 và CSRF.
8. **Bảo mật HTTP không thay domain authorization**: sau khi filter cho qua, service vẫn cần kiểm actor/tenant/resource.

## Tài liệu chính thức

- [Spring Security 6.5 — Servlet Architecture, Filters, Order, Custom Filters và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity, securityMatcher](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Authentication Persistence/SecurityContextHolderFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — HTTP Security Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — FilterChainProxy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
