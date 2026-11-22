# Luồng truy cập tài nguyên được bảo vệ và chuyển tới trang đăng nhập

> **Ngữ cảnh:** Spring Security – Authentication → **Đăng nhập biểu mẫu** trên Servlet stack (Spring MVC). Bài học đi theo một lần truy cập thật: người dùng chưa đăng nhập mở trang cần bảo vệ, Spring Security chặn truy cập, lưu URL ban đầu (khi chính sách cho phép), chuyển tới form login, xác minh username/password, thiết lập phiên và đưa trình duyệt quay lại tài nguyên. Đồng thời phân biệt **302 redirect**, **401 Unauthorized**, **403 Forbidden**, `AuthenticationEntryPoint`, `ExceptionTranslationFilter`, `RequestCache` và `SavedRequestAwareAuthenticationSuccessHandler`. Ví dụ tích hợp dùng **Java 17+, Spring Boot 3.5.7, Spring Security Servlet 6.5.x, Gradle, MockMvc**.

## 1. Một câu chuyện request từ đầu đến cuối

Giả sử hệ thống có các đường dẫn:

- `GET /public`: công khai, không cần đăng nhập.
- `GET /reports/42`: người dùng có role `READER` mới được đọc.
- `GET /admin`: chỉ role `ADMIN` được xem.
- `GET /login`: trang đăng nhập.
- `POST /login`: gửi username, password và CSRF token để Spring Security xác minh.

Người dùng **chưa đăng nhập** gõ `http://localhost:8080/reports/42` vào trình duyệt. Với form login tiêu chuẩn, kết quả thường là:

```text
Browser                           Spring Security / App
   |                                       |
   | GET /reports/42                       |
   |-------------------------------------->|
   |                              AuthorizationFilter:
   |                              chưa có Authentication phù hợp
   |                              -> AccessDeniedException
   |                              ExceptionTranslationFilter:
   |                              lưu request bằng RequestCache
   |                              gọi AuthenticationEntryPoint
   | 302 Location: /login                  |
   |<--------------------------------------|
   |                                       |
   | GET /login                            |
   |-------------------------------------->|
   | 200 HTML login form (+ CSRF token)    |
   |<--------------------------------------|
   |                                       |
   | POST /login username/password/CSRF    |
   |-------------------------------------->|
   |                              UsernamePasswordAuthenticationFilter
   |                              -> AuthenticationManager
   |                              -> DaoAuthenticationProvider
   |                              -> PasswordEncoder.matches(...)
   |                              -> SecurityContext/session theo policy
   |                              -> AuthenticationSuccessHandler
   | 302 Location: /reports/42?continue    |
   |<--------------------------------------|
   |                                       |
   | GET /reports/42?continue              |
   |-------------------------------------->|
   |                              khôi phục SecurityContext
   |                              xác minh role READER
   |                              RequestCacheAwareFilter xử lý
   |                              saved request nếu phù hợp
   | 200 report content                    |
   |<--------------------------------------|
```

**Các điểm phải hiểu đúng:**

1. URL `/reports/42` chưa từng được trả nội dung trước khi user được phép. **Bộ lọc authorization** đã ngăn request đi tới controller.
2. `ExceptionTranslationFilter` **không tự xác minh password**. Nó điều phối phản hồi khi cần bắt đầu xác thực, thông qua `AuthenticationEntryPoint`.
3. `AuthenticationEntryPoint` cho browser form login thường là `LoginUrlAuthenticationEntryPoint`, phát HTTP redirect tới `/login`.
4. `RequestCache` có thể lưu yêu cầu ban đầu trước redirect, thường vào session thông qua `HttpSessionRequestCache`.
5. `GET /login` và `POST /login` là hai việc khác nhau: GET hiển thị form; POST được authentication filter xử lý.
6. Sau login thành công, `SavedRequestAwareAuthenticationSuccessHandler` có thể chọn **địa chỉ được lưu** làm đích redirect. Nó không tự thực thi endpoint báo cáo trong chính POST login.
7. **Browser tạo một GET mới** đến URL đã redirect; Spring Security kiểm tra lại phiên và quyền cho request mới đó.
8. `?continue` là chi tiết của request-cache optimization trong Spring Security 6 khi dùng mặc định `HttpSessionRequestCache`; URL chính xác phụ thuộc cấu hình/phiên bản.
9. Session cookie phải được browser gửi lại và policy session phải cho phép lưu/khôi phục `SecurityContext`. Không có cookie hoặc dùng chain stateless thì không thể suy ra kết quả như sơ đồ.
10. Đăng nhập thành công không mặc nhiên đồng nghĩa đủ mọi quyền. Role `READER` vẫn không được truy cập `/admin`.

## 2. Xác thực (authentication) và phân quyền (authorization) khác nhau thế nào?

- **Authentication:** “Bạn là ai?” Ví dụ `UsernamePasswordAuthenticationFilter` nhận username/password và `AuthenticationManager` xác minh, trả `Authentication` đã xác thực.
- **Authorization:** “Bạn có được đọc tài nguyên này không?” Ví dụ `AuthorizationFilter` áp dụng rule `hasRole("READER")` cho `/reports/**`.
- **Exception handling của security filter chain:** “Nếu chưa đủ điều kiện thì phản hồi HTTP gì?” Ví dụ anonymous user được đưa tới login, còn user đã đăng nhập nhưng thiếu role thường nhận 403.

Một số kết quả thông dụng:

| Tình huống | Với browser form login mặc định | Ý nghĩa |
| --- | --- | --- |
| Anonymous truy cập `/public` | 200 | Đường dẫn công khai |
| Anonymous truy cập `/reports/42` | **302 → /login** | Cần xác thực trước khi đọc |
| Anonymous GET `/login` | 200 | Trang login có thể truy cập công khai |
| Username/password sai khi POST `/login` | **302 → /login?error** | Authentication failure; chưa được cấp phiên mới |
| Login đúng, có saved request | **302 → URL ban đầu** | Success handler chọn đích |
| Login đúng, không có saved request | **302 → /home** theo ví dụ | Dùng default success URL đã cấu hình |
| User `ROLE_READER` truy cập `/reports/42` | 200 | Được phép |
| User `ROLE_READER` truy cập `/admin` | **403** | Đã xác thực nhưng không đủ quyền |
| Client API không có token với entry point 401 | **401** | API yêu cầu credentials; không redirect HTML |
| Request POST thiếu CSRF token | **403** trong flow CSRF bật | Có thể bị chặn trước authentication filter |

**Không đồng nhất HTTP 302 với authentication thành công.** Redirect từ `/reports/42` sang `/login` xảy ra vì **người dùng chưa xác thực**, còn redirect từ `POST /login` sang trang đích xảy ra sau một lần xác thực thành công. Cả hai đều dùng mã 3xx nhưng có ý nghĩa khác nhau.

**Không đồng nhất 403 với password sai.** Nếu account có `ROLE_READER` nhưng cần `ROLE_ADMIN`, lặp lại login bằng đúng password không tự cấp quyền mới. Muốn có quyền phải theo authorization policy do server kiểm soát.

## 3. Spring Security filter chain xử lý request như thế nào?

Trong Servlet application, `DelegatingFilterProxy` đưa request vào `FilterChainProxy`. `FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp request** và chạy các filter phù hợp.

Một đường xử lý đơn giản hóa:

```text
HTTP GET /reports/42
    |
    v
FilterChainProxy / SecurityFilterChain
    |
    +-- SecurityContextHolderFilter
    |       đọc SecurityContext từ SecurityContextRepository
    |
    +-- Authentication filters
    |       form-login filter chỉ xử lý URL/method phù hợp
    |
    +-- AnonymousAuthenticationFilter
    |       nếu không có identity, có thể thiết lập anonymous token
    |
    +-- ExceptionTranslationFilter
    |       bao quanh phần chain sau để bắt security exceptions
    |
    +-- AuthorizationFilter
            rule hasRole("READER")
            |
            +-- GRANTED -> controller /reports/42
            |
            +-- DENIED  -> AccessDeniedException
                             |
                             v
                         ExceptionTranslationFilter
                         -> entry point hoặc access denied handler
```

Sơ đồ mô tả vai trò, không cam kết mọi ứng dụng có đúng các filter hoặc thứ tự giống nhau. Custom filters, multiple chains và cách cấu hình Spring Security có thể làm pipeline khác. Khi debug, kiểm tra `FilterChainProxy` thực tế thay vì tự đoán.

### 3.1. AuthorizationFilter làm gì?

`AuthorizationFilter` có nhiệm vụ thực thi `AuthorizationManager`/authorization rules. Nếu request không đáp ứng yêu cầu, nó có thể ném `AccessDeniedException`.

Ví dụ:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .requestMatchers("/reports/**").hasRole("READER")
        .requestMatchers("/admin").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Đây là **snippet trong một `SecurityFilterChain`**, không phải cấu hình login đầy đủ. Quy tắc này mô tả quyền, không tự chọn trang login.

- `hasRole("READER")` tìm authority `ROLE_READER` theo convention mặc định của Spring Security.
- `hasAuthority("documents:read")` kiểm tra authority chính xác được yêu cầu.
- `permitAll()` cho phép truy cập mà không yêu cầu authentication.
- `authenticated()` yêu cầu principal đã xác thực nhưng **không mặc nhiên** cần role cụ thể.
- `denyAll()` chặn các request không được phép theo explicit allowlist.

### 3.2. ExceptionTranslationFilter là bộ phận chuyển “security exception → HTTP response”

`ExceptionTranslationFilter` bắt và xử lý các exception bảo mật phát sinh ở phần filter chain mà nó bao quanh. Hai hướng chính:

1. `AuthenticationException` hoặc user chưa được xác thực đầy đủ khi bị denied → **bắt đầu authentication** bằng `AuthenticationEntryPoint`.
2. User đã xác thực và bị `AccessDeniedException` do thiếu quyền → giao cho `AccessDeniedHandler`; mặc định thường trả **403 Forbidden**.

Pseudo-flow:

```text
Authorization/security exception
          |
          v
ExceptionTranslationFilter
          |
          +-- cần xác thực?
          |      |
          |      +-- clear context nếu thích hợp
          |      +-- RequestCache.saveRequest(...) theo policy
          |      +-- AuthenticationEntryPoint.commence(...)
          |             -> 302 /login (form)
          |             -> 401 (API/Basic/Bearer tùy entry point)
          |
          +-- đã xác thực nhưng thiếu quyền?
                 |
                 +-- AccessDeniedHandler.handle(...)
                        -> 403 hoặc response được custom hóa
```

`ExceptionTranslationFilter` không tự triển khai business authorization và cũng không cố biến mọi lỗi Java thành redirect. Nó xử lý **những exception bảo mật tương ứng trong security chain**. Exceptions do controller phát ra ngoài hợp đồng/security processing có thể qua error handling khác.

## 4. AuthenticationEntryPoint và LoginUrlAuthenticationEntryPoint

`AuthenticationEntryPoint` là interface đại diện cho **cách yêu cầu client bắt đầu xác thực**:

```java
public interface AuthenticationEntryPoint {
    void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException, ServletException;
}
```

Đây là **chữ ký mô tả API**; không cần khai báo lại interface này trong dự án.

Các entry point hay gặp:

| Entry point | Hành vi | Hợp với |
| --- | --- | --- |
| `LoginUrlAuthenticationEntryPoint` | HTTP redirect tới login page | Browser form login |
| `BasicAuthenticationEntryPoint` | 401 + `WWW-Authenticate: Basic ...` | HTTP Basic |
| `BearerTokenAuthenticationEntryPoint` | 401 và challenge theo Bearer | OAuth2 Resource Server |
| `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` | Trả status 401 | API client muốn JSON/status, không HTML redirect |
| `DelegatingAuthenticationEntryPoint` | Chọn entry point theo request matcher | Hệ thống có nhiều loại client |

### 4.1. Ai quyết định URL /login?

Cấu hình `formLogin(...)` chuẩn đăng ký entry point cho browser, thường dùng `LoginUrlAuthenticationEntryPoint`. Nếu không tự chỉ định trang login, Spring Security có thể sinh trang `GET /login` mặc định.

```java
http.formLogin(Customizer.withDefaults());
```

Đây là snippet, cần import `org.springframework.security.config.Customizer`. Khi chạy ứng dụng Spring Boot có web/security starter và chain phù hợp, Spring Security có thể tự sinh login page và xử lý `POST /login`.

**Không cần tự viết controller GET /login** nếu bạn dùng trang sinh tự động. Nhưng nếu khai báo trang login tùy chỉnh, **chính ứng dụng phải cung cấp controller/view trả HTML**.

### 4.2. Entry point không phải filter xử lý POST /login

`LoginUrlAuthenticationEntryPoint` chỉ **hướng client đi tới URL login**. Nó không kiểm tra form credentials.

`UsernamePasswordAuthenticationFilter` mới là nơi nhận `POST /login` theo cấu hình chuẩn, tạo `UsernamePasswordAuthenticationToken` chưa xác thực rồi gọi `AuthenticationManager`. Sau đó provider và password encoder xác minh credential.

Nếu bạn viết controller `@PostMapping("/login")` trong khi đã bật form login chuẩn, authentication filter thường **intercept POST /login trước controller**. Đừng lẫn hai cơ chế hoặc thêm hai filters cùng xử lý một path.

## 5. RequestCache giữ đích ban đầu ra sao?

### 5.1. Vì sao phải lưu original request?

Không lưu, người dùng mở `/reports/42`, bị chuyển tới login, đăng nhập xong có thể luôn bị đẩy về `/home`, mất ngữ cảnh ban đầu.

`RequestCache` giải quyết vấn đề UX này:

- Lưu thông tin về request cần authentication.
- Sau khi xác thực thành công, success handler có thể lấy `SavedRequest` để chọn đích.
- Khi browser quay lại URL đã lưu, `RequestCacheAwareFilter` có thể truy xuất wrapper/tái dựng những phần được hỗ trợ từ request đã lưu.

Các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `RequestCache` | Contract lưu, lấy, xóa và match request |
| `HttpSessionRequestCache` | Implementation phổ biến lưu `DefaultSavedRequest` trong session |
| `DefaultSavedRequest` | Snapshot metadata cần cho việc redirect/tái dựng request, không phải live `HttpServletRequest` vô hạn |
| `ExceptionTranslationFilter` | Gọi `saveRequest(...)` lúc bắt đầu authentication nếu policy cho phép |
| `SavedRequestAwareAuthenticationSuccessHandler` | Ưu tiên URL đã lưu khi login thành công, tùy các tùy chọn |
| `RequestCacheAwareFilter` | Đối chiếu HTTP request quay lại với saved request và wrapper |
| `NullRequestCache` | Không lưu request; hữu ích cho API stateless |

### 5.2. Session dùng cho RequestCache không giống session đã authenticated

Tại thời điểm anonymous truy cập `/reports/42`, `HttpSessionRequestCache` có thể tạo một session **chỉ để giữ saved request**. Khi đó user vẫn chưa authenticated.

```text
Session sau GET protected anonymous:
    SPRING_SECURITY_SAVED_REQUEST = DefaultSavedRequest(...)
    chưa có authenticated SecurityContext của "mai"

Session sau POST /login thành công:
    SecurityContext chứa authenticated principal "mai"
    saved request có thể vẫn tồn tại cho tới khi redirect request khớp
```

Do đó **có `JSESSIONID` trước khi đăng nhập không chứng minh đã đăng nhập**. Mục đích tạo session của request cache và của authenticated security context là hai việc khác nhau.

Tương tự, session fixation protection có thể thay đổi session ID khi login; hãy sử dụng cookie do browser nhận từ server và để framework quản lý session lifecycle.

### 5.3. Chi tiết Spring Security 6: tham số continue

Spring Security 6 tối ưu `HttpSessionRequestCache`: thay vì luôn tra cache trên mỗi request, mặc định cơ chế match có thể chỉ truy vấn request đã lưu khi request đến có tham số **`continue`**.

Ví dụ với request ban đầu không có query string:

```text
GET /reports/42 (anonymous)
  -> 302 /login
POST /login (valid credentials)
  -> 302 http://localhost:8080/reports/42?continue
GET /reports/42?continue (browser follows redirect)
  -> RequestCacheAwareFilter có điều kiện kiểm tra saved request
  -> controller trả báo cáo nếu user có quyền
```

Dấu `?continue` là **tín hiệu kỹ thuật cho request cache**, không phải token xác thực hay permission. Chỉ việc thêm `?continue` vào URL **không thể** làm bypass security; `AuthorizationFilter` vẫn cần session/authentication và quyền hợp lệ.

Với URL ban đầu đã có query, cache có thể ghép `&continue`. Khi viết test hoặc xử lý điều hướng, **đừng hardcode rằng Location sau login phải đúng bằng chuỗi `/reports/42` không có query** trên mọi phiên bản. Kiểm tra cấu hình cache và URL thực tế.

Tùy version/override, `HttpSessionRequestCache.setMatchingRequestParameterName(...)` có thể đổi behavior. Không tự bỏ tham số bằng JavaScript rồi trách Spring Security “không lấy lại request”. Tuy vậy application controller không nên phụ thuộc vào `continue` để quyết định authorization.

### 5.4. SavedRequest không phải “replay tùy ý mọi POST”

Request cache chủ yếu phù hợp trường hợp **trình duyệt điều hướng GET** đến tài nguyên cần login. Sau login, browser nhận 302 rồi tạo request mới đến đích. Đó **không phải** bảo đảm Spring Security tự tái chạy một POST/PUT đã gửi trước login với body, token, file upload và side effects y nguyên.

- Với write operations, thường nên trả lỗi cần login trước, sau đó client chủ động submit lại dưới quyền đã xác thực và CSRF token mới hợp lệ.
- Không tự động replay giao dịch thanh toán/xóa dữ liệu chỉ vì thấy `SavedRequest`.
- Có thể giới hạn request cache vào GET/safe navigation theo chính sách.
- Với các endpoint cực nhạy cảm, xác minh lại intent/action sau login thay vì mặc nhiên thực thi.
- Không lưu password, token, request body nhạy cảm vào custom request cache.

### 5.5. Một session có thể có nhiều lần bị chặn

Trong cấu hình cache session thông dụng, một saved-request slot có thể được **thay thế** bởi một request protected khác trước khi user đăng nhập. Vì vậy không cam kết luôn quay về “URL đầu tiên user từng mở”.

Ví dụ user lần lượt truy cập `/reports/42` rồi `/reports/99` khi anonymous: đích được lưu có thể là request sau theo chính sách. Nếu sản phẩm cần giỏ hàng hoặc multi-step workflow, nên quản lý workflow state riêng, không xem `RequestCache` là hệ thống lưu công việc dài hạn.

## 6. Form login: GET trang login, POST xác thực, success/failure handlers

### 6.1. GET /login

Khi anonymous bị redirect, trình duyệt gửi GET tới trang login. Nếu không khai báo custom page, Spring Security có thể sinh HTML mặc định qua filter tạo login page, bao gồm form và CSRF token phù hợp cấu hình.

Nếu tự dùng `.loginPage("/signin")`:

```java
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin")
        .failureUrl("/signin?error")
        .defaultSuccessUrl("/home", false)
        .permitAll());
```

Đây là **snippet cấu hình**, cần controller/view cho `GET /signin`, đảm bảo login page và assets được phép truy cập. Không viết custom page thì `/signin` có thể 404; không `permitAll` thì dễ tạo redirect loop.

### 6.2. POST /login

Form mặc định gửi tên parameter `username`, `password` (trừ khi cấu hình khác) tới login processing URL, thường là `POST /login`.

`UsernamePasswordAuthenticationFilter`:

1. Đọc username/password, tạo token unauthenticated.
2. Có thể gắn `WebAuthenticationDetails` vào token từ request.
3. Gọi `AuthenticationManager.authenticate(...)`.
4. Provider, ví dụ `DaoAuthenticationProvider`, tải `UserDetails` và kiểm tra `PasswordEncoder.matches(...)`.
5. Nếu authentication thành công, xử lý `SessionAuthenticationStrategy` phù hợp, đặt/lưu `SecurityContext` qua cơ chế framework và gọi success handler.
6. Nếu thất bại, xóa trạng thái bảo mật phù hợp và gọi failure handler; form login thường redirect `/login?error`.

**Với Spring Security 6, `SecurityContextHolderFilter` dùng explicit save.** Authentication filter chuẩn đã có cơ chế lưu context trong flow thành công. Nhưng nếu bạn viết manual login controller chỉ gọi `SecurityContextHolder.setContext(...)`, không thể mặc nhiên hy vọng request sau có session authenticated; phải lưu qua `SecurityContextRepository.saveContext(...)` và xử lý session strategy cần thiết.

### 6.3. SavedRequestAwareAuthenticationSuccessHandler

Mặc định form login thường dùng một success handler hỗ trợ saved request. Quy tắc quan trọng:

1. Nếu `alwaysUseDefaultTargetUrl == true`, dùng default target và bỏ saved request.
2. Nếu có `targetUrlParameter` được cấu hình và hiện diện, handler có thể dùng giá trị đó (phải đánh giá an toàn redirect).
3. Nếu có saved request, redirect về URL đã lưu.
4. Không có saved request, fallback sang default target URL đã cấu hình.

Ví dụ:

```java
http.formLogin(form -> form
        .defaultSuccessUrl("/home", false)
        .permitAll());
```

- `false`: **không ép** luôn dùng `/home`; saved request được ưu tiên khi có.
- `true`: luôn đưa về `/home` ngay cả khi trước login có protected URL được lưu.
- Trong ví dụ ở mục 8, dùng `false` để test redirect về `/reports/42`.
- Không tự xây `successHandler` nếu chỉ cần hành vi chuẩn, vì khi thay success handler không đúng bạn có thể vô tình bỏ saved-request logic.

### 6.4. AuthenticationFailureHandler

Sai mật khẩu hoặc account không được phép xác thực dẫn tới nhánh failure. Với form login mặc định, redirect `/login?error` là hành vi thường gặp.

**Phân biệt hai redirect:**

```text
Anonymous GET /reports/42:
    ExceptionTranslationFilter
    -> AuthenticationEntryPoint
    -> 302 /login

Wrong POST /login:
    UsernamePasswordAuthenticationFilter
    -> AuthenticationManager rejects
    -> AuthenticationFailureHandler
    -> 302 /login?error
```

`ExceptionTranslationFilter` không phải handler trực tiếp của mọi lần nhập sai password trong form login; lỗi đó thường được authentication filter bắt và chuyển sang `AuthenticationFailureHandler`.

Không log raw password trong failure handler; trả thông điệp đủ hữu ích nhưng tránh tiết lộ account existence/locked status trước khi có trust phù hợp.

## 7. Ví dụ Java 17+ chạy được bằng Spring Boot 3.5

Demo cố ý giữ **form login chuẩn**, không viết custom login filter/controller; vì trọng tâm là chuỗi redirect và saved request.

Các endpoints:

| Method/path | Rule | Đáp ứng khi hợp lệ |
| --- | --- | --- |
| `GET /public` | `permitAll()` | `public` |
| `GET /home` | `authenticated()` | `home:mai` |
| `GET /reports/{id}` | `hasRole("READER")` | `report=42;user=mai` |
| `GET /admin` | `hasRole("ADMIN")` | `admin:...` |
| `GET /login` | Form login mặc định | Login HTML |
| `POST /login` | Spring Security form filter | Redirect hoặc failure |

Có một demo account `mai / demo-pass-123` chỉ mang `ROLE_READER`. **Không dùng credential mẫu trong production**.

### 7.1. Cấu trúc project

```text
protected-page-login-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/loginflow/LoginFlowApplication.java
    └── test/java/demo/loginflow/LoginFlowApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'protected-page-login-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý phiên bản Spring Security phù hợp qua BOM. Khi kiểm tra lỗi version, xem dependency tree của project thật; không tự ép mọi `spring-security-*` dependency sang một patch number khác BOM.

### 7.2. Toàn bộ source code ứng dụng

Tạo `src/main/java/demo/loginflow/LoginFlowApplication.java`:

```java
package demo.loginflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFlowApplication.class, args);
    }
}

@Configuration
class LoginFlowSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("mai")
                        .password(encoder.encode("demo-pass-123"))
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/reports/**").hasRole("READER")
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/home").authenticated()
                .anyRequest().denyAll());

        // GET /login: trang form sinh bởi Spring Security.
        // POST /login: được UsernamePasswordAuthenticationFilter xử lý.
        // "false": không ép default URL nếu có saved request.
        http.formLogin(form -> form
                .defaultSuccessUrl("/home", false)
                .permitAll());

        // CSRF giữ bật theo mặc định; không tự tắt.
        // Session/request cache của Spring Security được sử dụng.
        return http.build();
    }
}

@RestController
class LoginFlowController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/home")
    String home(Authentication auth) {
        return "home:" + auth.getName();
    }

    @GetMapping("/reports/{id}")
    String report(
            @PathVariable("id") long id,
            Authentication auth) {
        return "report=" + id + ";user=" + auth.getName();
    }

    @GetMapping("/admin")
    String admin(Authentication auth) {
        return "admin:" + auth.getName();
    }
}
```

**Giải thích config:**

- `/reports/**` đòi `ROLE_READER`, được kiểm tra bởi authorization rules; `ROLE_READER` do nguồn user đáng tin cấp.
- `/admin` đòi `ROLE_ADMIN`; account mai không có role này.
- `/home` chỉ cần authenticated và là **default success target** nếu không có saved request.
- `.formLogin(...)` đăng ký entry point chuyển tới trang login, login filter, handler và trang mặc định theo cơ chế Spring Security.
- `.permitAll()` trong form-login config giúp login page, processing/failure URLs hoạt động công khai theo nhu cầu flow. Rule `/login` cũng được khai báo tường minh cho người đọc.
- Không có controller tự POST login, tránh đụng với `UsernamePasswordAuthenticationFilter`.
- Với unauthenticated browser, `GET /reports/42` không vào `LoginFlowController.report`. Chỉ sau authentication/authorization hợp lệ controller mới được gọi.
- Vì không tự định nghĩa `SecurityContextRepository` hay `RequestCache`, demo dùng behavior mặc định tương thích Spring Security 6.
- Không bắt đầu bằng `@WithMockUser` trong integration tests vì cần đi qua **redirect/login/request cache thật**.

### 7.3. MockMvc test: bốn nhánh quan trọng

Tạo `src/test/java/demo/loginflow/LoginFlowApplicationTests.java`:

```java
package demo.loginflow;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFlowApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousProtectedGetRedirectsToLoginAndIsSaved()
            throws Exception {

        MvcResult first = mvc.perform(get("/reports/42"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String loginRedirect = first.getResponse().getRedirectedUrl();
        assertNotNull(loginRedirect);
        assertTrue(loginRedirect.endsWith("/login"));

        HttpSession rawSession = first.getRequest().getSession(false);
        assertNotNull(rawSession);
        MockHttpSession session = (MockHttpSession) rawSession;

        SavedRequest saved = new HttpSessionRequestCache()
                .getRequest(first.getRequest(), first.getResponse());
        assertNotNull(saved);
        assertTrue(saved.getRedirectUrl().contains("/reports/42"));

        MvcResult login = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String target = login.getResponse().getRedirectedUrl();
        assertNotNull(target);
        assertTrue(target.contains("/reports/42"));

        // Trình duyệt GET lại URL đích với cùng session.
        // Với Spring Security 6, "continue" có thể xuất hiện
        // trong Location để request cache match.
        mvc.perform(get("/reports/42?continue").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("report=42;user=mai"));
    }

    @Test
    void loginWithoutSavedRequestUsesDefaultTarget()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String url = login.getResponse().getRedirectedUrl();
        assertNotNull(url);
        assertTrue(url.endsWith("/home"));

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("home:mai"));
    }

    @Test
    void authenticatedReaderGets403ForAdminOnly()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordReturnsToLoginError()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        MvcResult result = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String url = result.getResponse().getRedirectedUrl();
        assertNotNull(url);
        assertTrue(url.contains("/login?error"));

        // Password sai không tạo Authentication thành công.
        mvc.perform(get("/home").session(session))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicPageAndLoginPageAreReachable() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));

        mvc.perform(get("/login"))
                .andExpect(status().isOk());
    }

    @Test
    void loginPostRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
gradle test
```

Với Gradle Wrapper, dùng `./gradlew test` trên macOS/Linux hoặc `gradlew.bat test` trên Windows. Chạy web app:

```bash
gradle bootRun
```

Sau đó dùng browser mở `http://localhost:8080/reports/42`. Trình duyệt sẽ được chuyển đến login page; đăng nhập bằng tài khoản demo và quan sát browser chuyển về báo cáo.

**Các assertion này được xây dựng từ flow chính thức và cấu hình nêu trên; bài không tuyên bố đã chạy test thực tế.** Trong môi trường của dự án, nếu có security chain khác, reverse proxy, request cache override hoặc session cookie policy khác thì test cần phản ánh behavior tương ứng.

### 7.4. Đọc kết quả test

| Test | Kỳ vọng |
| --- | --- |
| `anonymousProtectedGetRedirectsToLoginAndIsSaved` | GET protected 302 /login; có saved request; login đúng redirect URL gốc; GET tiếp theo 200 |
| `loginWithoutSavedRequestUsesDefaultTarget` | Login đúng không có saved request → 302 /home; GET /home 200 |
| `authenticatedReaderGets403ForAdminOnly` | Mai đã xác thực nhưng thiếu ROLE_ADMIN → 403, **không** redirect login |
| `wrongPasswordReturnsToLoginError` | POST mật khẩu sai → 302 /login?error; không tạo authenticated session |
| `publicPageAndLoginPageAreReachable` | GET /public và GET /login đều 200 |
| `loginPostRequiresCsrf` | POST /login thiếu CSRF token → 403 |

**Vì sao dùng một `MockHttpSession` qua nhiều request?** Saved request và authenticated context có thể nằm trong session. Nếu mỗi lần `mvc.perform(...)` dùng một session mới, thành phần tiếp theo sẽ không tìm thấy trạng thái đã lưu. Trong browser thật, cookie `JSESSIONID` là cầu nối giữa các HTTP request; trong test, `.session(session)` mô phỏng điều đó.

**Vì sao kiểm tra URL với `contains("/reports/42")`?** Vì mặc định Spring Security 6 có thể thêm `?continue` và tạo redirect URL tuyệt đối theo server scheme/host. Assertion không nên coi mọi implementation redirect đều giữ nguyên chuỗi không có query.

## 8. Không có saved request thì điều gì xảy ra?

Nếu người dùng trực tiếp mở `/login` rồi đăng nhập mà không có một protected request đã được lưu, success handler cần một đích fallback. Với cấu hình:

```java
.formLogin(form -> form
        .defaultSuccessUrl("/home", false))
```

...đích fallback là `/home`. Nếu dùng `.defaultSuccessUrl("/home", true)`, đích mặc định luôn được ưu tiên và saved request có thể bị xóa.

**Những sai lầm gây khó chịu cho UX:**

- Dùng `alwaysUseDefaultTargetUrl(true)` rồi kỳ vọng người dùng trở lại URL gốc.
- Đặt custom `AuthenticationSuccessHandler` trả JSON nhưng không xử lý saved URL cho browser.
- Chỉ lưu đích trong một hidden field `returnUrl` do client gửi mà không validate, gây **open redirect**.
- Bỏ RequestCache vì muốn API stateless nhưng lại dùng cùng chain cho browser form login và mong có saved request.

Nếu cần một luồng điều hướng riêng theo role, phải xác định thứ tự ưu tiên giữa saved request, default URL và role-based landing page. Đừng cố tự động chuyển mọi user có role admin đến `/admin` nếu họ vừa mở một tài nguyên khác hợp lệ.

## 9. 401, 403, 302 và API clients: chọn entry point theo use case

Một browser tải HTML thường muốn **302 → trang login**. Nhưng SPA dùng fetch/AJAX, mobile client và backend API thường mong **401** hoặc JSON lỗi, không mong một trang HTML login được trả sau chuỗi redirect.

Ví dụ API token stateless:

```text
GET /api/reports/42
Authorization: (không có)

HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":"authentication_required"}
```

Đây là **ví dụ HTTP mang tính mô tả**; payload JSON phụ thuộc chính API của ứng dụng, Spring Security không tự sinh đúng JSON đó trong mọi cấu hình.

Một chain API có thể cấu hình riêng (snippet cần imports và thêm vào app có nhiều chains):

```java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
        .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
        .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

    // Chỉ quyết định CSRF theo cách cấp/đưa credential của API:
    // bearer-only stateless và browser cookie auth có threat model khác.
    return http.build();
}
```

Đây **không phải** một hệ thống API token đầy đủ: cần thêm bearer token authentication/configuration thực, xử lý 403 và response JSON nếu mong muốn. Nếu ứng dụng còn browser login, cần chain thứ hai cho web, matcher/`@Order` phù hợp. Không tắt CSRF toàn cục chỉ để tránh gửi token từ browser.

**Kết luận:** `ExceptionTranslationFilter` có thể gọi entry point trả 302 hoặc 401 tùy security chain/client. Không phải “mọi request chưa đăng nhập đều bị redirect /login”.

### Thiếu quyền sau login

Nếu đã có `Authentication` hợp lệ nhưng không đủ authority:

```text
GET /admin
Cookie: JSESSIONID=<hợp lệ>

AuthorizationFilter: hasRole("ADMIN") từ chối
ExceptionTranslationFilter: user đã xác thực
AccessDeniedHandler: HTTP 403 Forbidden
```

Trong hệ thống thật, không in cookie thật vào log hoặc tài liệu. Với user chưa authenticated cũng truy cập `/admin`, entry point form login có thể vẫn redirect /login, vì đây là nhu cầu **xác thực** trước khi xét quyền.

## 10. Custom login page, error page và redirect loop

Nếu cần giao diện riêng ở `/signin`:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/signin", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin")
        .failureUrl("/signin?error")
        .defaultSuccessUrl("/home", false)
        .permitAll());
```

Đây là snippet, cần **controller GET /signin** và template/page thật. `POST /signin` được Spring Security login filter xử lý theo cấu hình. Cần render CSRF token trong form và đặt `name="username"`/`name="password"`, hoặc thay parameter names trong config tương ứng.

### Những lỗi điển hình

**Lỗi A: /signin bị bảo vệ.** Anonymous gọi tài nguyên protected, redirect /signin, nhưng /signin cũng đòi authentication → redirect loop. Cần `permitAll()` cho login page và những tài nguyên cần để render.

**Lỗi B: form action khác loginProcessingUrl.** Form POST `/signin` nhưng filter chỉ chờ POST `/login` → request bị xử lý sai/no handler. Phải đồng bộ action và config.

**Lỗi C: custom form không có CSRF token.** Spring Security chặn POST với 403 trước khi kiểm tra password. Điều này không đồng nghĩa password sai.

**Lỗi D: matcher của security chain không bao phủ login URL.** Nếu chain chỉ match `/portal/**` nhưng trang login ở `/signin`, request login có thể không đi qua chain tưởng tượng. Xem `FilterChainProxy` và thứ tự chains.

**Lỗi E: custom success handler quên saved request.** Login đúng vẫn luôn về `/home`; đó là hệ quả logic handler, không phải RequestCache tự “hỏng”.

**Lỗi F: custom login page nằm sau redirect ngoài domain chưa validate.** Tránh dùng `returnUrl` tự do hoặc `Location` từ header do client cung cấp mà không có allowlist/local-path policy. Bảo vệ session/cookie và tránh open redirect.

## 11. Các ranh giới bảo mật cần kiểm tra

### 11.1. CSRF và form login

Với cookie/session-based browser authentication, CSRF protection là lớp phòng thủ quan trọng. Demo **giữ bật CSRF**:

- GET trang login thường có CSRF token trong form do framework render.
- POST `/login` trong MockMvc test dùng `.with(csrf())`.
- POST thiếu token bị 403.
- Không thêm `csrf(csrf -> csrf.disable())` vào browser chain chỉ để tự gửi form bằng cURL cho tiện.

Mặc dù login trước đó chưa có authenticated principal, **login CSRF** vẫn là rủi ro: kẻ tấn công có thể cố đưa nạn nhân đăng nhập vào một tài khoản do attacker kiểm soát, làm hành động của nạn nhân gắn sai account.

### 11.2. Session fixation protection

Spring Security có `SessionAuthenticationStrategy` phù hợp khi login thành công. Với Servlet session, chiến lược chống session fixation thường thay đổi session ID. Saved request và authenticated context phải tồn tại đúng qua việc thay ID/phiên theo cơ chế của framework.

**Không lưu session ID cũ trong JavaScript hoặc URL** rồi cố gửi lại. Để browser nhận cookie mới, cấu hình `Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path` đúng ranh giới HTTPS/proxy.

### 11.3. Open redirect và host/proxy headers

Saved request thường được tạo từ URL mà client yêu cầu tới ứng dụng. Nếu ứng dụng tự lấy giá trị `returnUrl` từ query/body/header hoặc tin các proxy headers không đáng tin, attacker có thể gây redirect ra domain bên ngoài.

Nên:

- Chấp nhận đích redirect thuộc cùng origin hoặc tập route nội bộ allowlisted.
- Không cho `javascript:`, `//evil.example`, domain ngoài và URL schema tùy ý trong return destination.
- Xác định trusted proxy chain, bảo vệ `Forwarded`/`X-Forwarded-Host` để host/scheme dựng URL redirect không bị giả mạo.
- Test login redirect với query, context path và HTTPS offload.
- Nếu flow có tham số `targetUrlParameter`, chỉ dùng với quy tắc validate/restrict phù hợp.

### 11.4. Không lưu dữ liệu nhạy cảm trong RequestCache

RequestCache dùng để **điều hướng**, không phải một nơi lưu form/password/OTP hoặc toàn bộ request body. Với request cần POST sau login, app nên thiết kế lại xác nhận hành động.

Nếu dùng custom `RequestCache`, cần giới hạn:

- Những method/path được lưu, ưu tiên safe navigation.
- Kích thước thông tin lưu, tránh giữ URL/headers cực lớn trong session.
- TTL và cleanup khi login/logout/session timeout.
- Không serialize secret hoặc PII thừa.
- Không tạo vô hạn session khi có lưu lượng bot anonymous, vì request cache tạo session cũng có chi phí.

### 11.5. Trạng thái session không bằng authorization

Sau login, session giúp framework nhận dạng user; **mỗi request** vẫn phải qua authorization policy tương ứng. Nếu role bị thay đổi giữa các request, cached `Authentication` có thể giữ authorities cũ; sản phẩm cần có chính sách revalidation/revocation/session invalidation nếu thay đổi quyền phải có hiệu lực ngay.

Đừng dùng “đã từng redirect qua /login” làm bằng chứng người dùng có quyền đọc báo cáo. Bộ lọc authorization và object-level policy mới quyết định.

## 12. Các phép thử quan trọng ngoài happy path

| Thử nghiệm | Điều cần kiểm chứng |
| --- | --- |
| Anonymous GET protected | 302 /login, không chạy controller protected |
| Anonymous GET public | 200 |
| GET login page | 200, không redirect loop |
| POST login mật khẩu đúng | Authentication thành công, session hợp lệ |
| POST login mật khẩu sai | Failure handler, không có full authenticated session |
| POST login thiếu CSRF | 403 trước khi auth |
| Login có saved request | Redirect về URL gốc hợp lệ |
| Login không có saved request | Dùng defaultSuccessUrl |
| Login với alwaysUseDefaultTargetUrl true | Saved request không được ưu tiên |
| Saved URL có query | Query được quản lý đúng, cân nhắc `continue` |
| Login từ một tab, mở protected URL khác | Policy saved-request slot đúng |
| Authenticated nhưng role thiếu | 403, không redirect login vòng lặp |
| Browser gửi sai/mất JSESSIONID | Request sau không nhận được authenticated context |
| API request không có token | 401 phù hợp entry point API, không trả HTML login |
| API user thiếu scope | 403 theo API authorization |
| Browser logout | Session/context được xóa; protected request sau lại đòi login |
| Session timeout | Không dùng cached authority cũ ngoài chính sách |
| Session fixation | Session ID thay đổi/được bảo vệ theo strategy |
| App sau reverse proxy | Redirect dùng đúng scheme/host/context path |
| Redirect return URL từ client | Không bị open redirect |
| Multi-chain matchers | Form-login filter/entrypoint ở đúng chain |
| Context path phụ như /portal | Redirect dùng đúng base path |
| GET vs POST protected | Không tự replay side-effect POST |
| RequestCache disabled | Không có saved URL, fallback có kiểm soát |

### 12.1. Tại sao @WithMockUser chưa đủ?

`@WithMockUser` có thể chuẩn bị một security context đã authenticated ngay trong test. Nó hữu ích khi test authorization, nhưng **không chứng minh**:

- Anonymous request tạo 302 sang login.
- `ExceptionTranslationFilter` có gọi RequestCache.
- `UsernamePasswordAuthenticationFilter` thực sự kiểm tra password.
- `AuthenticationSuccessHandler` chọn saved URL hay default URL.
- Browser gửi cùng session cookie và request sau khôi phục đúng authentication.

Muốn test bài này, phải mô phỏng **nhiều HTTP requests theo đúng thứ tự** và giữ cùng `MockHttpSession`, như mục 7.

### 12.2. Nếu debug thấy 401 thay vì 302

Kiểm tra:

1. Request đi vào chain web form login hay API stateless?
2. `AuthenticationEntryPoint` thực tế là `LoginUrlAuthenticationEntryPoint` hay `HttpStatusEntryPoint`/Basic/Bearer?
3. Có header `Accept`, AJAX request matcher hoặc config phân biệt browser/API không?
4. Có custom `exceptionHandling(...)` override form entrypoint không?
5. Login URL nằm trong đúng chain chưa?
6. Custom filter ném `AuthenticationException` ở vị trí mà `ExceptionTranslationFilter` có thể xử lý không?

**Không sửa bằng cách ép mọi 401 thành redirect /login**: API clients thường cần 401 thật để biết thiếu credentials.

### 12.3. Nếu debug thấy 403 thay vì 302

Kiểm tra:

1. User đã authenticated nhưng thiếu authority hay đang anonymous?
2. Request có phải POST/PUT/DELETE thiếu CSRF token không?
3. URL login có bị `denyAll`/mismatch bảo vệ không?
4. Custom `AccessDeniedHandler` hoặc authorization rules có thay đổi không?
5. Với API, trả 403 có đúng semantic “đã xác thực nhưng thiếu quyền” không?

### 12.4. Nếu login đúng nhưng không quay về URL gốc

Kiểm tra:

1. Trước login có request protected được lưu chưa?
2. `RequestCache` đang dùng HttpSession hay Null?
3. Browser giữ cùng session ID/cookie từ request anonymous đến POST login không?
4. `alwaysUseDefaultTargetUrl` có được bật `true` không?
5. Custom success handler có bỏ qua `SavedRequest` không?
6. Path/query/`continue` có được xây đúng không?
7. Một request protected khác có ghi đè saved request không?
8. Login có đi qua chain khác với protected page không?
9. Redirect của reverse proxy có bị đổi scheme/host sai không?
10. Session bị mất do load balancer, thiếu session store phân tán hoặc cấu hình cookie không đúng?

## 13. Những sai lầm phổ biến

1. **Cho rằng filter chặn protected page trực tiếp hiển thị form login.** Thường nó gửi **redirect**, browser mới GET login page.
2. **Nhầm `ExceptionTranslationFilter` với bộ kiểm tra password.** Provider/filter login mới kiểm tra credential.
3. **Nhầm `AuthenticationEntryPoint` với `AuthenticationSuccessHandler`.** Entry point khởi động xác thực; success handler chọn đích sau xác thực.
4. **Nhầm `AuthenticationFailureHandler` với entry point của anonymous protected request.**
5. **Coi HTTP 302 là luôn login success.** 302 đầu tiên có thể chỉ là yêu cầu vào /login.
6. **Coi HTTP 403 là password sai.** Thiếu role và thiếu CSRF cũng có thể gây 403.
7. **Coi mọi unauthenticated request là 401.** Form login browser thường redirect 302.
8. **Không permitAll trang custom login.** Dẫn đến redirect loop.
9. **Form POST không khớp `loginProcessingUrl`.** Authentication filter không nhận request.
10. **Chặn hoặc bỏ CSRF để form login tiện hơn.** Phá một lớp bảo vệ browser.
11. **Không dùng cùng session qua redirect/login.** Saved request/context không được khôi phục.
12. **Tưởng `HttpSessionRequestCache` có nghĩa đã authenticated.** Session anonymous cũng có thể lưu saved request.
13. **Quên tham số `continue` của Spring Security 6.** Test sai redirect URL hoặc không match request cache.
14. **Tưởng saved request sẽ tự chạy lại mọi POST.** Không được replay side effects tùy tiện.
15. **Bật `defaultSuccessUrl("/home", true)` rồi đòi quay về URL gốc.**
16. **Thay custom success handler nhưng bỏ qua saved request** mà không có chủ đích.
17. **Tin `returnUrl` từ client làm Location trực tiếp**, tạo open redirect.
18. **Dùng host/forwarded headers không đáng tin để dựng redirect**, tạo host-header injection.
19. **Dùng GET /login đồng thời như controller và filter không hiểu precedence**, gây xung đột hoặc login page lỗi.
20. **Tạo hai security chains nhưng login endpoint không thuộc chain nào phù hợp.**
21. **Coi có ROLE_READER đồng nghĩa có ROLE_ADMIN.** Authorization dựa trên authority chính xác.
22. **Chỉ kiểm tra redirect mà không GET lại resource**, bỏ qua vấn đề cookie/context.
23. **Dùng `@WithMockUser` làm test end-to-end login**, bỏ qua password, saved request và session.
24. **Custom manual login chỉ set context, không save** trong Spring Security 6, dẫn tới request sau mất authentication.
25. **Không kiểm thử expiry/logout/role revocation**, khiến phiên cũ giữ quyền ngoài chính sách.
26. **Log session ID/password/saved URL chứa secret** làm rò rỉ thông tin nhạy cảm.
27. **Dùng form login redirect cho mọi API**, khiến AJAX nhận HTML thay vì 401 JSON.
28. **Tự disable RequestCache mà không xác nhận UX fallback**, người dùng luôn quay về /home.
29. **Saved request lặp lại giữa nhiều tab mà không thiết kế policy**, nhầm destination.
30. **Tưởng URL được phép sau login nghĩa là user luôn có quyền với từng object.** Cần object-level authorization.

## 14. Bài tập thực hành

**Bài 1 – Vẽ lại request flow.** Với anonymous user GET `/reports/42`, nêu trách nhiệm `AuthorizationFilter`, `ExceptionTranslationFilter`, `LoginUrlAuthenticationEntryPoint`, `HttpSessionRequestCache`, `UsernamePasswordAuthenticationFilter`, `AuthenticationManager` và success handler. Chỉ rõ ở bước nào có 302, 200 và authentication thực sự thành công.

**Bài 2 – Chạy demo.** Chạy `gradle test` và `gradle bootRun`, truy cập `/reports/42` qua browser. Quan sát login page, session cookie, redirect URL có thể chứa `continue` và GET tiếp theo. Không chép giá trị session cookie vào tài liệu chia sẻ.

**Bài 3 – Thiếu quyền.** Đăng nhập user mai (`ROLE_READER`), GET `/admin`. Giải thích vì sao nhận 403 thay vì redirect về login. Thử anonymous GET `/admin` và so sánh.

**Bài 4 – Default URL.** Đổi `defaultSuccessUrl("/home", false)` thành `true`. Đăng nhập sau khi mở `/reports/42`, quan sát sự khác biệt. Giải thích saved request bị ưu tiên hoặc bị bỏ qua.

**Bài 5 – Login page tùy chỉnh.** Dựng `GET /signin`, config `loginPage("/signin")`, `loginProcessingUrl("/signin")` và `failureUrl("/signin?error")`. Kiểm tra CSS/images được phép truy cập, form có CSRF token và không tạo redirect loop.

**Bài 6 – API 401.** Tạo chain `/api/**` stateless với `HttpStatusEntryPoint(UNAUTHORIZED)` và `NullRequestCache`. So sánh cùng một yêu cầu anonymous ở browser chain (302) với API chain (401).

**Bài 7 – RequestCache.** Kiểm tra session sau anonymous GET protected. Xem object `SavedRequest` có destination nhưng chưa có authenticated context. Sau login, truy cập URL có `continue` và quan sát việc request cache match/remove theo chính sách.

**Bài 8 – POST trước login.** Giả định user cố POST `/payments/confirm` khi anonymous. Thiết kế UX cho phép họ login rồi **xác nhận lại** thao tác thay vì tự replay POST; kiểm tra CSRF, idempotency và double-submit.

**Bài 9 – Session lost.** Khi login đúng nhưng request sau trở về login, tìm lỗi `SameSite`/`Secure`/`Domain`, path, proxy, session store hoặc sai chain. Viết integration test giữ/làm mất session để chứng minh.

**Bài 10 – Redirect security.** Thử các `returnUrl` dạng local path, URL ngoài domain, `//evil.example` và URL với scheme không hợp lệ. Đặt rule chỉ cho phép destination đã validate. Không dùng input từ client làm `Location` nguyên văn.

**Bài 11 – Multi-tab.** Mở hai protected URLs khi anonymous trước khi login. Ghi nhận session có thể chỉ giữ một saved request gần nhất; đề xuất cơ chế workflow state riêng nếu sản phẩm cần phục hồi nhiều thao tác.

**Bài 12 – Migration.** Khi lên Spring Security 6, kiểm tra `HttpSessionRequestCache` với tham số `continue`, context persistence theo explicit-save và custom success handler. Viết test trên **đúng version** trước/sau nâng cấp để phát hiện khác biệt.

### Tiêu chí hoàn thành

Người học có thể giải thích:

- Tại sao anonymous GET protected thường thành **302 /login** chứ không phải 200/401 trong browser chain?
- `ExceptionTranslationFilter` và `AuthenticationEntryPoint` là gì, khác gì authorization và password authentication?
- Ai lưu `SavedRequest`, lưu ở đâu, và khi nào success handler sử dụng?
- Vì sao Spring Security 6 có thể thêm `?continue` vào URL trở lại?
- Login đúng nhưng thiếu role dẫn tới 403 thế nào?
- Khi nào GET login page là trang sinh tự động, khi nào phải viết controller riêng?
- Cách dùng MockMvc qua **nhiều request cùng session** để test flow thật?
- Vì sao không tự replay POST hay dùng untrusted returnUrl làm redirect?
- Những ranh giới CSRF, session fixation, cookie, open redirect và multi-chain cần bảo vệ?

## 15. Tài liệu chính thức

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): sơ đồ redirect từ protected page, `UsernamePasswordAuthenticationFilter`, success/failure handling.
- [Spring Security 6.5 – Servlet Architecture / Handling Security Exceptions](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và authorization filter chain.
- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, `AuthenticationEntryPoint` và authentication filter.
- [Spring Security 6.5 – Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): thay đổi RequestCache và `continue` giữa Spring Security 5 và 6.
- [Spring Security 6.5.11 – SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): chọn saved/default/target URL.
- [Spring Security 6.5.11 – HttpSessionRequestCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/HttpSessionRequestCache.html): lưu request trong session, matcher và tham số `continue`.
- [Spring Security – MockMvc Form Login Tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): `formLogin` request post processor và CSRF trong test.
- [Spring Security 6.5 – CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): bảo vệ form có cookie.
- [Spring Security 6.5 – Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html#servlet-securityfilterchain): chọn chain và matching.
- [OWASP – Unvalidated Redirects and Forwards Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): bảo vệ return URL và tránh open redirect.

**Phiên bản ví dụ:** Java 17 / Spring Boot 3.5.7 (Spring Security 6.5.x theo dependency management). Với Spring Security 7, WebFlux, custom authentication mechanism, API token hoặc request-cache implementation tùy chỉnh, phải đối chiếu Javadoc và security chain thực tế; không áp máy móc số status/URL của form login browser cho mọi loại client.