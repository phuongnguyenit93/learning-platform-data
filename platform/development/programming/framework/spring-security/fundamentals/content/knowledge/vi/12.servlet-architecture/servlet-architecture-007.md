# ExceptionTranslationFilter và việc chuyển lỗi bảo mật thành phản hồi

Trong **Spring Security trên Servlet stack**, việc một request bị từ chối và việc **biến sự từ chối thành HTTP response** là hai trách nhiệm liên quan nhưng khác nhau. `AuthorizationFilter` và các cơ chế kiểm tra quyền có thể phát sinh `AccessDeniedException`; các thành phần xác thực có thể phát sinh `AuthenticationException`. **`ExceptionTranslationFilter`** là một thành phần chuyên chuyển **một số exception bảo mật phát sinh ở phần downstream của filter** thành hành động yêu cầu đăng nhập hoặc từ chối truy cập.

Khi hiểu đúng filter này, bạn giải thích được vì sao:

- Anonymous gọi `GET /api/me` có thể nhận **401 Unauthorized** trong REST API, hoặc **302 redirect đến /login** trong ứng dụng web form login.
- User đã đăng nhập, nhưng thiếu `ROLE_ADMIN` khi gọi `GET /api/admin` thường nhận **403 Forbidden**.
- User có remember-me authentication nhưng một tài nguyên yêu cầu xác thực mạnh hơn có thể được chuyển sang **`AuthenticationEntryPoint`** để đăng nhập đầy đủ, thay vì mặc nhiên bị xử lý như người đã xác thực hoàn toàn.
- Sai password ở `BasicAuthenticationFilter` vẫn cho 401, nhưng lỗi này **không nhất thiết được ExceptionTranslationFilter bắt**: Basic filter có luồng xử lý authentication failure riêng.
- Thiếu CSRF token có thể cho **403 từ CsrfFilter/AccessDeniedHandler**, không chứng minh mọi status 403 đều đi qua ExceptionTranslationFilter.
- `@ControllerAdvice` không mặc nhiên bắt exception xảy ra trong Servlet filters trước khi `DispatcherServlet` xử lý.

Bài này thuộc nhóm **Kiến trúc Servlet**, dựa trên **Java 17+, Spring Boot 3, Spring Security 6.x, Spring MVC/Servlet**. Chúng ta sẽ khảo sát luồng, nhánh quyết định, code cấu hình, cách kiểm thử bằng MockMvc, giới hạn phạm vi xử lý và mô phỏng Java 17 độc lập. Nếu dùng Spring Security 7, Spring WebFlux hoặc OAuth2 resource server tùy chỉnh, hãy đối chiếu API và filter chain theo version/stack tương ứng.

## 1. Bản đồ kiến trúc: lỗi xuất hiện ở đâu?

```text
Client
  |
  v
Servlet container FilterChain
  |
  +-- DelegatingFilterProxy("springSecurityFilterChain")
            |
            v
       FilterChainProxy
            |
            +-- SecurityContextHolderFilter / context
            +-- CsrfFilter / HTTP Basic / form login / bearer filter...
            +-- AnonymousAuthenticationFilter
            |
            +-- ExceptionTranslationFilter
            |       |
            |       | chain.doFilter(request, response)
            |       v
            |    AuthorizationFilter
            |       |
            |       +-- Nếu bị từ chối: throw AccessDeniedException
            |       |
            |       v
            |    DispatcherServlet
            |       |
            |       +-- HandlerMapping -> HandlerAdapter
            |       +-- Controller -> Service
            |       +-- @PreAuthorize / method security (nếu áp dụng)
            |
            +-- ExceptionTranslationFilter thấy exception phù hợp
                    |
                    +-- AuthenticationEntryPoint
                    |       401 / WWW-Authenticate / redirect...
                    |
                    +-- AccessDeniedHandler
                            403 / error page / JSON...
```

Đây là **sơ đồ khái niệm**, không phải danh sách tất cả filter của mọi cấu hình. Thứ tự và danh sách security filters thay đổi theo form login, HTTP Basic, JWT bearer, CSRF, session, nhiều `SecurityFilterChain` và các filters do bạn thêm.

Điểm quan trọng là `ExceptionTranslationFilter` gọi `chain.doFilter` để phần **sau** nó chạy. Nếu downstream ném exception thuộc những loại nó xử lý, nó chuyển sang một trong hai điểm mở rộng. Nếu một filter **chạy trước nó** đã tự bắt lỗi hoặc tự ghi response, ExceptionTranslationFilter có thể hoàn toàn không tham gia.

### 1.1. Ba nhóm trách nhiệm

| Thành phần | Làm việc gì? | Không làm gì? |
| --- | --- | --- |
| `AuthenticationManager`/`AuthenticationProvider` | Kiểm tra credentials, xác lập Authentication | Không phải HTTP error renderer dùng chung cho mọi request |
| `AuthorizationFilter`/`AuthorizationManager` | Quyết định có được truy cập request hay không; có thể từ chối bằng `AccessDeniedException` | Không tự chọn JSON body/redirect khi lỗi |
| `ExceptionTranslationFilter` | Bắt các exception bảo mật phù hợp từ downstream và điều phối response | **Không tự thực hiện kiểm tra quyền** |
| `AuthenticationEntryPoint` | Bắt đầu quá trình yêu cầu authentication, ví dụ 401 hoặc redirect | Không tự kiểm tra password đã nhập |
| `AccessDeniedHandler` | Tạo response khi access denied với người dùng đã xác thực theo branch phù hợp | Không nâng quyền hoặc sửa kết quả authorization |
| `DispatcherServlet` và `HandlerExceptionResolver` | Xử lý request/exception trong phạm vi Spring MVC | Không thay thế hoàn toàn Servlet/Spring Security filters |

Tên chứa “Translation” nói chính xác trách nhiệm: biến kết quả lỗi/exception ở security layer thành **giao diện phản hồi HTTP** thích hợp. Nó không phải “filter kiểm tra permission”.

## 2. Hai họ exception phải nhận diện

### 2.1. AuthenticationException

`AuthenticationException` là lớp gốc trong Spring Security dành cho **lỗi xác thực**, chẳng hạn:

- `BadCredentialsException`: thông tin đăng nhập không hợp lệ.
- `AuthenticationCredentialsNotFoundException`: thiếu authentication thích hợp ở một bước cần xác thực.
- `InsufficientAuthenticationException`: mức authentication không đủ cho hành động hiện tại.
- `DisabledException`/`LockedException`: trạng thái tài khoản, trong những flow/provider tương ứng.
- Các subclass từ authentication component khác.

Khi một `AuthenticationException` được **ném từ phạm vi downstream mà ExceptionTranslationFilter đang bao**, filter sẽ kích hoạt `AuthenticationEntryPoint.commence`. Tuy nhiên **không phải mọi BadCredentialsException đều phải đi qua filter này**: `BasicAuthenticationFilter` có thể xử lý failure và gọi entry point trực tiếp; `UsernamePasswordAuthenticationFilter` thường dùng authentication failure handler.

Không kết luận rằng “ExceptionTranslationFilter bắt mọi lỗi authentication trong ứng dụng”. Điều quan trọng là **filter order + nơi exception thực sự phát sinh + component đã xử lý lỗi hay chưa**.

### 2.2. AccessDeniedException

`AccessDeniedException` biểu thị **quyền truy cập bị từ chối**. `AuthorizationFilter` có thể ném exception này khi rule `hasRole`, `hasAuthority` hoặc `denyAll` không cho phép request. Method security cũng có thể tạo access-denied exception khi `@PreAuthorize` chặn một method và exception đi tới vùng được translation filter xử lý.

Một access-denied exception chưa cho biết response sẽ là 401 hay 403. Cần biết **identity hiện tại được coi là anonymous, remember-me, hay đã xác thực đầy đủ**.

### 2.3. Những lỗi không cùng loại

`ExceptionTranslationFilter` không phải global catcher cho mọi Java exception:

| Lỗi phát sinh | Thành phần xử lý điển hình | Có mặc nhiên được ExceptionTranslationFilter chuyển? |
| --- | --- | --- |
| `AuthenticationException` từ downstream | Entry point | **Có**, nếu exception thoát ra trong phần chain được filter bao |
| `AccessDeniedException` từ downstream | Entry point hoặc denied handler | **Có**, theo trạng thái auth |
| `BadCredentialsException` trong Basic filter | Basic authentication failure flow/entry point | Không bắt buộc qua ETF |
| `MissingCsrfTokenException`/`InvalidCsrfTokenException` tại CsrfFilter | CsrfFilter gọi AccessDeniedHandler theo cấu hình | Không nên mặc định quy cho ETF |
| `IllegalArgumentException` từ business service | MVC exception resolver hoặc container/error flow | Không, trừ khi có cơ chế khác chuyển thành security exception đúng |
| `MethodArgumentNotValidException` tại MVC binding | `@ControllerAdvice`/MVC error handler | Không phải security translation thông thường |
| `NoHandlerFoundException`/missing mapping | MVC/container 404 behavior | Không |
| `NullPointerException` hoặc DB failure | MVC/container error processing, có thể 500 | Không chuyển 401/403 chỉ vì nằm trong request |
| Exception từ filter chạy **trước** ETF | Filter đó/Servlet container hoặc handler tương ứng | ETF ở phía sau không bao trùm |

**Quy tắc:** Đừng biến mọi exception thành `AccessDeniedException` chỉ để trả HTTP 403. Điều đó che lỗi nghiệp vụ/hạ tầng, làm sai monitoring và có thể biến 500 thành phản hồi bảo mật gây khó debug.

## 3. Cây quyết định của ExceptionTranslationFilter

Mô hình hóa các nhánh phổ biến:

```text
ExceptionTranslationFilter gọi chain.doFilter(...)
         |
         +-- Không có exception phù hợp
         |       -> response bình thường
         |
         +-- AuthenticationException từ downstream
         |       -> startAuthentication(...)
         |             - clear SecurityContext
         |             - RequestCache.saveRequest(...) theo cấu hình
         |             - AuthenticationEntryPoint.commence(...)
         |
         +-- AccessDeniedException từ downstream
                 |
                 +-- Anonymous hoặc remember-me?
                 |       -> InsufficientAuthenticationException
                 |       -> startAuthentication(...) / entry point
                 |
                 +-- Đã authenticated đầy đủ?
                         -> AccessDeniedHandler.handle(...)
```

Trong phiên bản Spring Security được mô tả, `AuthenticationTrustResolver` giúp nhận diện anonymous/remember-me để quyết định **có nên yêu cầu authentication đầy đủ**. Lưu ý: các dạng authentication đặc biệt hoặc cấu hình custom có thể thay đổi kết quả; chỉ đọc `authentication != null` là không đủ để tự phân loại.

### 3.1. AuthenticationException → AuthenticationEntryPoint

Khi downstream ném `AuthenticationException`, filter khởi động authentication:

1. Clear `SecurityContextHolder` trong nhánh bắt đầu authentication.
2. Lưu request ban đầu bằng `RequestCache` **nếu chiến lược cache được cấu hình để lưu**.
3. Gọi `AuthenticationEntryPoint.commence(request, response, exception)`.
4. Entry point chọn phản hồi để client biết cần làm gì.

`AuthenticationEntryPoint` **không chỉ trả 401**:

- REST API/HTTP Basic: thường trả HTTP 401, có thể có header `WWW-Authenticate`.
- Browser form login: `LoginUrlAuthenticationEntryPoint` có thể redirect (302) tới trang đăng nhập.
- Bearer token resource server: response có thể có `WWW-Authenticate: Bearer ...` theo tiêu chuẩn phù hợp.
- API có entrypoint tùy biến: JSON error contract, trạng thái và headers do bạn chủ động quy định.

HTTP 401 nghĩa là **yêu cầu authentication hợp lệ** (hoặc authentication hiện tại không đủ). Không đồng nhất “401 luôn là password sai”: một request **không gửi credential** tới URL bảo vệ cũng có thể nhận 401.

### 3.2. AccessDeniedException + anonymous → EntryPoint

Ví dụ `GET /api/admin` của client chưa login:

```text
AuthorizationFilter: hasRole("ADMIN")
              |
              +-- Anonymous không có role -> AccessDeniedException
                        |
                        v
              ExceptionTranslationFilter
                        |
                        +-- AuthenticationTrustResolver.isAnonymous() == true
                        +-- AuthenticationEntryPoint.commence(...)
                        v
              401 trong API Basic / redirect trong form login
```

Dù exception là `AccessDeniedException`, kết quả **không nhất thiết là 403** vì hệ thống cần cho client cơ hội xác thực.

### 3.3. AccessDeniedException + remember-me

Remember-me authentication có thể được coi là mức xác thực chưa đầy đủ cho một tài nguyên nhạy cảm. Trong branch mà filter nhận diện remember-me, nó có thể yêu cầu authentication mạnh hơn bằng entry point thay vì gọi denied handler. Điều này giúp tránh nhầm “có một Authentication object” với “đã chứng minh danh tính ở mức đủ”.

Một số cấu hình không dùng remember-me hoặc có chính sách step-up riêng; khi đó cần kiểm tra actual `AuthenticationTrustResolver` và chain, không hardcode mọi trường hợp thành redirect.

### 3.4. AccessDeniedException + authenticated → AccessDeniedHandler

Ví dụ `reader` đăng nhập đúng, có `ROLE_USER` nhưng thiếu `ROLE_ADMIN`:

```text
AuthorizationFilter: hasRole("ADMIN")
              |
              +-- User đã xác thực, thiếu ROLE_ADMIN
                        |
                        v
              AccessDeniedException
                        |
                        v
              ExceptionTranslationFilter
                        |
                        +-- AuthenticationTrustResolver: không anonymous
                        +-- không phải remember-me branch
                        |
                        v
              AccessDeniedHandler.handle(...)
                        |
                        v
              403 Forbidden (trong config API mẫu)
```

**Authentication thành công không đồng nghĩa authorization thành công.** API có thể cho reader truy cập `/api/me` nhưng từ chối `/api/admin`.

### 3.5. Bảng quyết định

| Exception được ETF bắt | Trạng thái principal | Điểm xử lý | Ví dụ kết quả |
| --- | --- | --- | --- |
| `AuthenticationException` | Bất kỳ | `AuthenticationEntryPoint` | 401 Basic/Bearer, 302 form login |
| `AccessDeniedException` | Anonymous | `AuthenticationEntryPoint` | 401/302 |
| `AccessDeniedException` | Remember-me được coi chưa đủ | `AuthenticationEntryPoint` | Yêu cầu đăng nhập đầy đủ |
| `AccessDeniedException` | Fully authenticated | `AccessDeniedHandler` | 403 |
| Không có exception | Phù hợp policy | Tiếp tục chain | 200, 201, 204, hoặc lỗi MVC khác |
| Exception ngoài 2 họ trên | Bất kỳ | Component khác | 400/404/500/response khác |

Các status chỉ là **ví dụ từ entrypoint/handler phù hợp**, không phải hardcode trong bản thân hai lớp exception.

## 4. Phân biệt 401, 403, 302 và những kết quả khác

**401 Unauthorized** trong HTTP có nghĩa client cần cung cấp credentials hợp lệ cho tài nguyên được bảo vệ. Trong các authentication scheme như Basic hoặc Bearer, server thường dùng `WWW-Authenticate` để nêu challenge.

**403 Forbidden** nghĩa server hiểu request nhưng **không cấp quyền** trong chính sách hiện tại. Một user có thể đã login đúng nhưng vẫn không đủ role/scope/owner.

**302 Found/redirect tới /login** là một cách khởi động authentication trong website dựa vào form/session. Đừng tự xem 302 login là bằng chứng API đã cho quyền truy cập dữ liệu.

**404 Not Found** có thể do `DispatcherServlet` không tìm được handler; `permitAll` không tự tạo controller. Có sản phẩm cố tình dùng 404 thay 403 để hạn chế lộ sự tồn tại của resource; đó là quyết định riêng cần kiểm tra access policy, không phải behavior mặc định của ETF.

**400 Bad Request** cho validation/parsing error khác với 401/403. **500 Internal Server Error** báo lỗi xử lý bất ngờ; đừng nuốt mọi exception và biến thành 403 làm mất khả năng phát hiện sự cố.

### 4.1. Có nên luôn trả JSON với code riêng?

Với REST API thuần, JSON error contract giúp client phân biệt các trạng thái một cách có hệ thống:

```json
{"code":"AUTHENTICATION_REQUIRED"}
```

```json
{"code":"ACCESS_DENIED"}
```

Không trả mật khẩu, token, stack trace hoặc chi tiết user enumeration. Bổ sung correlation ID (từ hạ tầng tin cậy) và log server-side tương ứng. Nếu triển khai `application/problem+json`/RFC Problem Details, tuân thủ định dạng và media type; đừng tùy tiện tuyên bố JSON trên là Problem Details khi nó chưa đủ fields/contract.

### 4.2. WWW-Authenticate không phải dữ liệu nhạy cảm để bỏ mặc

Với Basic API, custom `AuthenticationEntryPoint` cần giữ behavior challenge phù hợp nếu client dựa vào nó. Một entrypoint trả status 401 nhưng mất `WWW-Authenticate` có thể khiến client hành xử khác mong đợi. Ngược lại, browser/SPA có thể muốn tránh pop-up Basic tùy request type; xem tài liệu Spring Security về `X-Requested-By: XMLHttpRequest` và cấu hình thực tế.

Đừng đưa password hoặc Authorization header vào error body, request cache log hoặc exception message phản hồi cho client.

## 5. RequestCache và saved request

Khi user anonymous yêu cầu một trang bảo vệ trong website, framework có thể lưu request ban đầu để sau login quay về đúng URL:

```text
GET /account/statement (chưa login)
     |
     +-- AccessDeniedException
     +-- EntryPoint redirect /login
     +-- RequestCache lưu target /account/statement (nếu bật)
     |
POST /login (đúng credential)
     |
     +-- SavedRequestAwareAuthenticationSuccessHandler
     +-- Redirect về /account/statement
```

`RequestCache` là abstraction, có các lựa chọn:

- `HttpSessionRequestCache` có thể lưu saved request trong HTTP session.
- `NullRequestCache` không lưu request; thường phù hợp API stateless/Basic clients có thể tự gửi lại request.
- Một implementation custom có thể kiểm soát cách lưu và khôi phục.

**Không khẳng định ETF luôn tạo session hoặc luôn lưu request.** Điều đó phụ thuộc cấu hình `RequestCache`. Trong ví dụ API bên dưới, chúng ta sử dụng `NullRequestCache` để không giữ saved request theo cơ chế form-login. Nếu bạn chuyển code sang browser session/form login, hãy thiết kế request cache phù hợp UX, session policy và an toàn redirect.

### 5.1. Bẫy open redirect và saved request

Khi redirect sau login, hãy cẩn thận với return URL do client cung cấp. Chỉ chấp nhận đích nội bộ đáng tin hoặc dùng saved request do cơ chế được cấu hình kiểm soát; tránh chuyển sang domain attacker bằng tham số `next=https://...` không xác minh.

Saved request không phải authorization grant. Sau login vẫn phải đánh giá **authorization lại** khi user quay về URL cũ.

## 6. ExceptionTranslationFilter và các filter khác: ranh giới rất quan trọng

### 6.1. BasicAuthenticationFilter có thể tự xử lý failure

Luồng Basic phổ biến:

```text
Authorization: Basic <base64(username:password)>
       |
       v
BasicAuthenticationFilter
       |
       +-- AuthenticationManager.authenticate(...)
       |
       +-- Sai password?
       |       +-- Clear context
       |       +-- RememberMeServices.loginFail(...)
       |       +-- Gọi AuthenticationEntryPoint theo flow Basic
       |       +-- Không tiếp tục controller
       |
       +-- Đúng password?
               +-- Lưu Authentication
               +-- chain.doFilter(...)
```

`BasicAuthenticationFilter` thường được bố trí **trước** `ExceptionTranslationFilter` trong chain. Vì thế `BadCredentialsException` do Basic filter xử lý **không phải bằng chứng ETF đã bắt nó**. Cả hai flow có thể dùng cùng `AuthenticationEntryPoint`, tạo ra response 401 tương tự nhưng xuất phát từ điểm xử lý khác nhau.

### 6.2. UsernamePasswordAuthenticationFilter có failure handler

Với form login, `UsernamePasswordAuthenticationFilter` (nền tảng từ `AbstractAuthenticationProcessingFilter`) xử lý form credentials. Khi authentication failure, nó thường gọi `AuthenticationFailureHandler` để redirect tới `/login?error` hoặc cơ chế được cấu hình.

Đừng mặc nhiên thay `exceptionHandling().authenticationEntryPoint(...)` rồi cho rằng mọi failure của `POST /login` sẽ trả JSON đó. Form authentication failure flow và unauthenticated request-to-protected-resource flow khác nhau.

### 6.3. CsrfFilter có AccessDeniedHandler riêng

Trong Spring Security 6.5, với HTTP method cần bảo vệ (ví dụ POST) mà CSRF token thiếu/sai, `CsrfFilter` có thể gọi `AccessDeniedHandler` **của chính nó** và dừng request. `CsrfFilter` thường nằm **trước** `ExceptionTranslationFilter`, nên lỗi 403 này có thể không đi qua handler được cấu hình tại `exceptionHandling`.

Hệ quả cho kiểm thử: `POST /public` có thể bị chặn **403** dù `/public` được `permitAll` nếu CSRF bật và thiếu token. Đừng debug nhầm 403 này thành `hasRole("ADMIN")`.

Nếu muốn thống nhất error JSON cho CSRF, phải xem điểm cấu hình `CsrfFilter.accessDeniedHandler`/handler tương ứng hoặc xử lý error ở tầng phù hợp; chỉ cấu hình ETF denied handler có thể không đủ.

### 6.4. @ControllerAdvice có thể thay đổi đường đi của exception MVC

Nếu một controller/service ném `AccessDeniedException`, đường exception đi qua Spring MVC. Nếu `HandlerExceptionResolver` hoặc `@ControllerAdvice` **đã xử lý** exception đó và ghi response, nó có thể không thoát ngược lên ETF. Nếu không được MVC xử lý, exception phù hợp có thể propagate ra security filter chain và được ETF chuyển.

Đây là lý do một global `@ExceptionHandler(Exception.class)` quá rộng có thể vô tình **nuốt security exceptions**, làm hỏng entrypoint/handler logic, khiến 401/403 trở thành 500/200 hoặc lộ nội dung không phù hợp. Khi dùng global exception handler, hãy xác định rõ loại exception mình sở hữu và để security layer xử lý những loại thuộc trách nhiệm security.

### 6.5. Exception từ Servlet Filter trước ETF

Nếu một custom `Servlet Filter` bên ngoài `DelegatingFilterProxy` ném lỗi, hoặc custom security filter chạy trước ETF ném exception chưa được bắt, ETF **không bao trùm nó**. Muốn convert thành security response, phải thiết kế handler/filter boundary đúng; không giả định ETF là một try/catch bao toàn bộ Servlet container.

### 6.6. Response đã commit

Sau khi `response.getWriter().flush()` hoặc body đã gửi, error handler có thể không thể đổi status/header/body hợp lệ. ETF có thể báo lỗi khi response đã committed thay vì cố viết một response mới. Trong custom entrypoint/denied handler, kiểm tra `response.isCommitted()` nếu flow có khả năng xảy ra tình huống đó; đừng viết thêm JSON thứ hai khi response đã được gửi.

Không tạo một filter cố “bắt tất cả Throwable rồi sendError(403)” vì có thể che lỗi nghiêm trọng, mất trạng thái đã commit và khiến incident/debugging khó khăn.

## 7. Cấu hình ExceptionHandling trong HttpSecurity

Điểm cấu hình thường thấy:

```java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(myAuthenticationEntryPoint)
    .accessDeniedHandler(myAccessDeniedHandler)
);
```

Đây là **fragment**, cần định nghĩa hai handler, import và security configuration. Spring Security lắp các thành phần này vào flow của `ExceptionTranslationFilter` trong `SecurityFilterChain` tương ứng.

Các handler có thể chọn:

- `BasicAuthenticationEntryPoint`: HTTP Basic challenge.
- `LoginUrlAuthenticationEntryPoint`: redirect vào login page.
- `BearerTokenAuthenticationEntryPoint`: challenge phù hợp OAuth2 Bearer.
- `HttpStatusEntryPoint`: gửi status HTTP đã chỉ định.
- Custom `AuthenticationEntryPoint`: JSON/body/headers theo contract API.
- `AccessDeniedHandlerImpl`: xử lý denied mặc định, thường 403.
- Custom `AccessDeniedHandler`: JSON, audit, response status 403.
- `DelegatingAuthenticationEntryPoint` hoặc request-matcher-based config: chọn entry point khác nhau theo loại request.

**Cần phân biệt config scope:** Với nhiều `SecurityFilterChain`, mỗi chain có matcher, filter list và exception handling có thể khác. Một API chain có thể dùng JSON 401/403; web chain dùng redirect login/error page. Đừng áp dụng global JSON handler vào form login rồi ngạc nhiên vì UX đổi hoặc xảy ra redirect loop.

### 7.1. Vì sao thứ tự SecurityFilterChain quan trọng?

`FilterChainProxy` chọn **SecurityFilterChain đầu tiên khớp request**. Giả sử có:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đây là fragment cấu hình nhiều chains, không dùng chung với project demo một-chain ở phần sau. `/api/**` dùng API chain; đường còn lại dùng web fallback chain. Nếu thiếu fallback, URL không match API chain có nguy cơ không được Spring Security bảo vệ. Nếu web chain đứng trước và match-all, API chain phía sau có thể không bao giờ được chọn.

### 7.2. Entry point cho API và web có thể khác status

| Client | Entry point phù hợp | Response dự kiến |
| --- | --- | --- |
| API dùng HTTP Basic | Basic hoặc JSON custom giữ challenge | 401 + WWW-Authenticate phù hợp |
| API dùng Bearer | BearerTokenAuthenticationEntryPoint | 401 + Bearer challenge phù hợp |
| Web form login | LoginUrlAuthenticationEntryPoint | Redirect login, thường 302 |
| Fully authenticated nhưng thiếu role | AccessDeniedHandler | 403 |
| AJAX/SPA | API JSON entry point/handler được định nghĩa rõ | 401/403 JSON, không redirect HTML vô ý |

Không gắn nhãn “403 = AuthenticationException”, “401 = AccessDeniedException”. Cùng một `AccessDeniedException` có thể dẫn đến **401** khi anonymous hoặc **403** khi đã authenticated đầy đủ.

## 8. Ví dụ Spring Boot 3: JSON 401/403 với filter minh họa

Bộ code sau cho một **Servlet REST API** dùng HTTP Basic cục bộ. Nó được thiết kế để chứng minh:

1. `AuthorizationFilter` từ chối anonymous ở `/api/me` và thiếu role ở `/api/admin`.
2. `ExceptionTranslationFilter` điều phối nhánh authentication/denied tương ứng.
3. Một filter minh họa đặt **ngay sau ExceptionTranslationFilter** có thể ném `AuthenticationException` hoặc `AccessDeniedException` để quan sát ETF bắt exceptions từ downstream.
4. Đăng nhập sai ở `BasicAuthenticationFilter` vẫn dùng entrypoint nhưng không nhất thiết qua ETF.
5. CSRF thiếu token có thể 403 từ `CsrfFilter` trước ETF, không nhất thiết có JSON body giống denied handler của ETF.
6. `permitAll` không tạo MVC handler; Spring MVC vẫn có thể trả 405 khi method không match.

**Giới hạn:** Dùng users/passwords hardcode chỉ để test local và `http://localhost`. Production phải dùng HTTPS, user store an toàn, password policy, rate limiting, monitoring và chỉ trả JSON error đã được kiểm tra không tiết lộ bí mật.

Cấu trúc project:

```text
src/main/java/example/translation/
    TranslationApplication.java
    SecurityConfig.java
    DemoFailureFilter.java
    DemoController.java

src/test/java/example/translation/
    ExceptionTranslationFlowTest.java
```

### 8.1. Dependencies

Trong `build.gradle` Groovy DSL của project Spring Boot 3 đã có plugins/repositories/toolchain Java 17:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là phần `dependencies`; với Maven dùng các starter tương ứng và `spring-security-test` test scope. Dùng BOM của Spring Boot để quản lý phiên bản Spring Security đồng bộ; không tự ghép Spring Boot 3 với Spring Framework/Security 7 mà chưa kiểm tra tương thích.

### 8.2. TranslationApplication.java

```java
package example.translation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TranslationApplication {
    public static void main(String[] args) {
        SpringApplication.run(TranslationApplication.class, args);
    }
}
```

### 8.3. DemoFailureFilter.java

Filter này nằm **trong Spring Security chain**, phía sau ETF, để buộc tạo hai loại security exception. Nó không có `@Component`, tránh việc Spring Boot tự đăng ký thêm filter vào Servlet container.

```java
package example.translation;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.web.filter.OncePerRequestFilter;

public class DemoFailureFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String path = request.getServletPath();

        if ("/demo/auth-failure".equals(path)) {
            throw new AuthenticationCredentialsNotFoundException(
                "demonstration authentication failure"
            );
        }

        if ("/demo/access-denied".equals(path)) {
            throw new AccessDeniedException(
                "demonstration access denied"
            );
        }

        chain.doFilter(request, response);
    }
}
```

Trong production, **không** tạo route công khai ném exceptions chỉ để thử; đây là test probe để người học tách nhánh. Khi gọi `/demo/access-denied`:

- Anonymous: ETF chuyển thành entrypoint.
- Reader đã authenticated: ETF chuyển thành denied handler.
- Bản thân filter chỉ **ném exception**; nó không đặt HTTP status.

### 8.4. SecurityConfig.java

```java
package example.translation;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.access.ExceptionTranslationFilter;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-local-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-local-password"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    AuthenticationEntryPoint apiEntryPoint() {
        return (request, response, failure) -> {
            response.setStatus(401);
            response.setHeader(
                "WWW-Authenticate", "Basic realm=\"demo\""
            );
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(
                StandardCharsets.UTF_8.name()
            );
            response.getWriter().write(
                "{\"code\":\"AUTHENTICATION_REQUIRED\"}"
            );
        };
    }

    @Bean
    AccessDeniedHandler apiDeniedHandler() {
        return (request, response, denial) -> {
            response.setStatus(403);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(
                StandardCharsets.UTF_8.name()
            );
            response.getWriter().write(
                "{\"code\":\"ACCESS_DENIED\"}"
            );
        };
    }

    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            AuthenticationEntryPoint entryPoint,
            AccessDeniedHandler deniedHandler) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/demo/auth-failure",
                    "/demo/access-denied"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/me"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/api/admin"
                ).hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(entryPoint)
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
            )
            .addFilterAfter(
                new DemoFailureFilter(),
                ExceptionTranslationFilter.class
            )
            .build();
    }
}
```

**Phân tích từng dòng quan trọng:**

1. `apiEntryPoint` có nhiệm vụ tạo JSON **401** và header Basic challenge. Khi ETF cần authentication, nó gọi handler này. Khi BasicAuthenticationFilter gặp password sai, chúng ta cũng cấu hình nó dùng **cùng** entry point qua `httpBasic`; vì vậy response giống nhau nhưng cơ chế khởi phát có thể khác.
2. `apiDeniedHandler` trả JSON **403** cho access denied thuộc nhánh handler này. Nó không tự cấp role hoặc sửa kết quả kiểm tra quyền.
3. `requestCache(new NullRequestCache())` tránh saved request kiểu browser session cho API Basic; client có thể tự thử lại request.
4. `/public` permitAll cho mọi HTTP methods về **authorization**; vì controller chỉ định `@GetMapping`, POST có CSRF token hợp lệ vẫn có thể dẫn tới MVC **405**.
5. `/demo/...` permitAll nhưng filter đặt sau ETF sẽ ném exception trước khi Servlet đích/controller chạy.
6. `/api/me` yêu cầu authenticated; `/api/admin` yêu cầu `ROLE_ADMIN`. User reader login đúng nhưng không có admin role.
7. `anyRequest().denyAll()` tránh vô tình mở endpoint không được khai báo.
8. `addFilterAfter(new DemoFailureFilter(), ExceptionTranslationFilter.class)` giữ custom filter **downstream** của ETF, để ETF có cơ hội catch. Custom filter không là bean riêng nên không bị Servlet container tự đăng ký thêm.
9. Cấu hình dùng `SecurityFilterChain` kiểu Spring Security 6.x, không dùng `WebSecurityConfigurerAdapter` đã bị loại bỏ.
10. `BCryptPasswordEncoder(10)` và password hardcode chỉ cho ví dụ localhost; không chọn cost production dựa trên con số demo.

**Lưu ý HTTP Basic và CSRF:** HTTP Basic chỉ mã hóa credentials bằng Base64, **không bảo vệ đường truyền**; bắt buộc dùng HTTPS trong production. `CsrfFilter` mặc định bật để bảo vệ các unsafe HTTP methods ở cookie/session browser; với API token stateless có thể có threat model khác, nhưng **không tắt CSRF theo thói quen để test pass**.

### 8.5. DemoController.java

```java
package example.translation;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("username", auth.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
```

Controller không có mappings cho `/demo/auth-failure` và `/demo/access-denied` vì filter sẽ ném exception từ trước. Khi test hai route đó, mục đích là kiểm tra **security error translation**, không kiểm tra handler MVC.

Controller cũng không biết password hash hoặc exception translation logic; nó chỉ nhận Authentication đã được Spring Security xác minh.

### 8.6. Chạy bằng Gradle

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giả sử app demo chạy tại `http://localhost:8080`:

```bash
# Public: 200
curl -i http://localhost:8080/public

# Anonymous vào tài nguyên có bảo vệ: 401 JSON
curl -i http://localhost:8080/api/me

# Login Basic đúng: 200
curl -i -u reader:reader-local-password \
  http://localhost:8080/api/me

# Basic sai: 401, do flow Basic xử lý failure
curl -i -u reader:wrong-password \
  http://localhost:8080/api/me

# Reader authenticated nhưng thiếu ROLE_ADMIN: 403
curl -i -u reader:reader-local-password \
  http://localhost:8080/api/admin

# Admin đầy đủ quyền: 200
curl -i -u admin:admin-local-password \
  http://localhost:8080/api/admin

# Lỗi AuthenticationException chủ động ném downstream: 401
curl -i http://localhost:8080/demo/auth-failure

# AccessDeniedException với anonymous -> entrypoint: 401
curl -i http://localhost:8080/demo/access-denied

# AccessDeniedException với reader -> denied handler: 403
curl -i -u reader:reader-local-password \
  http://localhost:8080/demo/access-denied

# POST public không có CSRF token -> 403 ở CsrfFilter
curl -i -X POST http://localhost:8080/public
```

Các status/body là **kỳ vọng từ code** chưa phải log máy chủ đã chạy trong bài viết. Đây là local HTTP demo; không gửi credentials thật qua HTTP hoặc đặt raw password thật trong shell history/process list.

**Response dự kiến cho `GET /api/me` không credential:**

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
Content-Type: application/json;charset=UTF-8

{"code":"AUTHENTICATION_REQUIRED"}
```

Tên/độ lớn chữ của `Content-Type` có thể khác theo Servlet container; phần contract cần kiểm tra là status 401, header challenge và JSON body do entrypoint viết.

**Response dự kiến cho reader gọi `GET /api/admin`:**

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json;charset=UTF-8

{"code":"ACCESS_DENIED"}
```

Không có stack trace, user password, JWT hoặc lý do phân quyền chi tiết trong response. Vận hành thật nên thêm correlation ID và audit server-side phù hợp, không để lộ thông tin nhạy cảm qua message của exception.

## 9. JUnit 5 và MockMvc: kiểm tra từng nhánh xử lý

Tạo `src/test/java/example/translation/ExceptionTranslationFlowTest.java`:

```java
package example.translation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExceptionTranslationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void anonymousMeUsesAuthenticationEntryPoint()
            throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                containsString("Basic")
            ))
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void correctBasicPasswordReachesController() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void incorrectBasicPasswordUsesBasicFailurePath()
            throws Exception {
        mvc.perform(get("/api/me").with(httpBasic(
                "reader", "incorrect")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void authenticatedReaderWithoutRoleIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void adminRoleIsAllowed() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic(
                "admin", "admin-local-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }

    @Test
    void thrownAuthenticationExceptionUsesEntryPoint()
            throws Exception {
        mvc.perform(get("/demo/auth-failure"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void thrownAuthenticationExceptionEvenForReaderUsesEntryPoint()
            throws Exception {
        mvc.perform(get("/demo/auth-failure").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void deniedForAnonymousUsesEntryPoint() throws Exception {
        mvc.perform(get("/demo/access-denied"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void deniedForAuthenticatedReaderUsesDeniedHandler()
            throws Exception {
        mvc.perform(get("/demo/access-denied").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void unsafeMethodWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/public"))
            .andExpect(status().isForbidden());
        // Không assert JSON từ ETF handler: CSRF có handler riêng.
    }

    @Test
    void validCsrfButWrongMvcMethodIsMethodNotAllowed()
            throws Exception {
        mvc.perform(post("/public").with(csrf()))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void unknownRouteDoesNotBecomePublicForReader()
            throws Exception {
        mvc.perform(get("/unmapped").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void unknownRouteAnonymousStillNeedsAuthentication()
            throws Exception {
        mvc.perform(get("/unmapped"))
            .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.translation.ExceptionTranslationFlowTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.translation.ExceptionTranslationFlowTest
```

**Kỳ vọng:** có **14 phương thức test**, được thiết kế để pass với project Spring Boot 3/Spring Security 6.x mô tả ở trên. Đây là kỳ vọng theo code đã rà soát; **không khẳng định đã chạy Gradle hoặc có log PASS thật**.

### 9.1. Các test tương ứng nhánh nào?

| Test | Tầng được kiểm tra | Diễn giải đúng |
| --- | --- | --- |
| `/public` | Authorization permitAll + MVC | Không có security error |
| Anonymous `/api/me` | AuthorizationFilter → ETF → EntryPoint | 401, request chưa xác thực |
| Basic password đúng | Basic authentication + MVC | 200, không phải exception translation |
| Basic password sai | BasicAuthenticationFilter failure handler/entrypoint | 401 nhưng không kết luận ETF đã bắt |
| Reader gọi admin | AuthorizationFilter → ETF → DeniedHandler | 403 vì thiếu role |
| Admin gọi admin | Authentication + authorization + MVC | 200 |
| `/demo/auth-failure` | Downstream AuthenticationException → ETF | EntryPoint, 401 |
| `/demo/access-denied` anonymous | Downstream AccessDeniedException → ETF | EntryPoint, 401 |
| `/demo/access-denied` reader | Downstream AccessDeniedException → ETF | DeniedHandler, 403 |
| POST thiếu CSRF | CsrfFilter/handler | 403 không mặc định JSON denied handler |
| POST có CSRF, sai method | MVC handler matching | 405 |
| Unknown path | `anyRequest().denyAll` | 401 anonymous / 403 authenticated |

Với `@WithMockUser`, bạn có thể test riêng nhánh authorization bằng một principal giả, nhưng **không chứng minh password provider thực sự đã xác thực**. Test `httpBasic(...)` với user store demo giúp bao phủ credential path.

### 9.2. Vì sao không assert toàn bộ FilterChainProxy internals trong MockMvc?

MockMvc mô phỏng Servlet requests/filters cho test; nó không chứng minh behavior mạng/TLS, browser redirect state, load balancer, error dispatch hay mỗi container-specific filter registration. Để kiểm tra filter ordering, committed response, multi-chain real deployment và status/headers thật, thêm integration test với embedded server/random port và công cụ HTTP client.

### 9.3. Cần thêm test cho ứng dụng thật

- Anonymous với nhiều entrypoints: JSON API vs redirect web login.
- Insufficient scope của OAuth2 Bearer: xác nhận RFC 6750 challenge và status theo resource server config.
- Remember-me đến endpoint yêu cầu fully authenticated: entrypoint phù hợp.
- AccessDeniedException từ `@PreAuthorize` không bị global `@ControllerAdvice` nuốt.
- CSRF missing/invalid: handler đúng, không lộ dữ liệu.
- Chỉ một SecurityFilterChain match request dự kiến; fallback chain bao phủ mọi URL.
- Servlet filter trước ETF ném lỗi: không giả định ETF xử lý.
- Error response đã commit: không viết JSON lần hai.
- Thông báo lỗi và log không có password, cookies, Authorization header, reset tokens.
- Regression test khi nâng Spring Security/Servlet container.

## 10. Java 17 độc lập: mô phỏng logic chuyển exception

Bài toán này thuộc Spring Security Servlet, nên **JDK thuần không thể tạo một `ExceptionTranslationFilter` thực** nếu không có dependency. Để thực hành tư duy nhánh 401/403, chương trình sau mô phỏng **decision tree** với kiểu dữ liệu Java 17. Nó không dùng HTTP thực, không có `AuthenticationManager` và không thay thế integration test framework ở trên.

Tạo file `ExceptionTranslationModel.java`:

```java
public class ExceptionTranslationModel {

    enum Identity {
        ANONYMOUS,
        REMEMBER_ME,
        FULLY_AUTHENTICATED
    }

    sealed interface Failure
        permits AuthFailure, AccessFailure {}

    record AuthFailure(String reason) implements Failure {}
    record AccessFailure(String reason) implements Failure {}

    static String translate(Identity identity, Failure failure) {
        if (failure instanceof AuthFailure) {
            return "ENTRY_POINT:401";
        }

        if (identity == Identity.ANONYMOUS
                || identity == Identity.REMEMBER_ME) {
            return "ENTRY_POINT:401";
        }

        return "ACCESS_DENIED_HANDLER:403";
    }

    public static void main(String[] args) {
        System.out.println(
            "authFailure:anonymous="
                + translate(
                    Identity.ANONYMOUS,
                    new AuthFailure("credential missing")
                )
        );

        System.out.println(
            "authFailure:authenticated="
                + translate(
                    Identity.FULLY_AUTHENTICATED,
                    new AuthFailure("re-auth required")
                )
        );

        System.out.println(
            "denied:anonymous="
                + translate(
                    Identity.ANONYMOUS,
                    new AccessFailure("admin only")
                )
        );

        System.out.println(
            "denied:rememberMe="
                + translate(
                    Identity.REMEMBER_ME,
                    new AccessFailure("step-up needed")
                )
        );

        System.out.println(
            "denied:authenticated="
                + translate(
                    Identity.FULLY_AUTHENTICATED,
                    new AccessFailure("admin only")
                )
        );
    }
}
```

Biên dịch/chạy với JDK 17:

```bash
javac ExceptionTranslationModel.java
java ExceptionTranslationModel
```

**Stdout chính xác theo logic mã trên:**

```text
authFailure:anonymous=ENTRY_POINT:401
authFailure:authenticated=ENTRY_POINT:401
denied:anonymous=ENTRY_POINT:401
denied:rememberMe=ENTRY_POINT:401
denied:authenticated=ACCESS_DENIED_HANDLER:403
```

Trong mô hình này, mọi entry point được giả định trả 401 giống API Basic; **trong Spring Security thật, entry point có thể redirect 302**. Mục tiêu là nhận diện **nhánh handler**, không mô phỏng hết Servlet lifecycle.

Các nhận xét quan trọng:

1. `AuthFailure` luôn vào entrypoint, không phụ thuộc enum identity.
2. `AccessFailure` với `ANONYMOUS` hoặc `REMEMBER_ME` vào entrypoint.
3. `AccessFailure` với `FULLY_AUTHENTICATED` vào denied handler.
4. Không có nhánh “bắt mọi exception”: kiểu `Failure` được giới hạn bởi `sealed interface` để nêu rõ phạm vi.
5. Mô hình không cho biết exception nằm ở vị trí nào trong filter chain; trong app thật, chỉ các exception **đi qua vùng ETF bao** mới do ETF xử lý.

## 11. Method security và exception propagation

`@EnableMethodSecurity` cho phép dùng annotations như `@PreAuthorize` ở service methods. Ví dụ:

```java
@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:export')")
    public byte[] exportReport(long reportId) {
        // Kiểm tra owner/tenant của reportId bằng logic domain phù hợp.
        return new byte[0];
    }
}
```

Đây là fragment: cần bật method security, dependencies và imports. `@PreAuthorize` có thể dẫn tới `AccessDeniedException` nếu quyền không đủ. Trong Servlet request đi qua ETF, exception có thể propagate qua Controller/DispatcherServlet rồi ra filter; **nhưng** `@ControllerAdvice`/MVC `HandlerExceptionResolver` có thể xử lý nó trước. Vì thế phải kiểm thử **đường truyền exception thực tế** để đảm bảo JSON/error/status đúng như chính sách.

Method security không thay kiểm tra resource owner/tenant; một người có quyền export report chưa chắc được export report của người khác. Đừng ghi 403 vì role rồi bỏ qua vấn đề BOLA/IDOR.

### 11.1. Không tự dịch exception một cách tùy tiện

Một anti-pattern:

```java
try {
    reportService.exportReport(id);
} catch (Exception ex) {
    return ResponseEntity.status(403).build();
}
```

Đoạn này sẽ biến cả lỗi database, NullPointerException, timeout và bug thành 403, đồng thời che tình trạng hệ thống. Tốt hơn là thiết kế exception handlers theo loại cụ thể, giữ security error handling trong security stack và ghi log/audit đã được redaction.

## 12. Debug vì sao một request nhận 401 hoặc 403

Khi gặp lỗi, đi theo thứ tự:

1. **Request thực:** URL, HTTP method, Content-Type, Accept, dispatcher type, Authorization/cookie có hay không (không log secret value).
2. **FilterChainProxy:** request match security chain nào? Có `securityMatcher` quá hẹp, thiếu fallback hoặc chain order sai không?
3. **Authentication state:** anonymous, remember-me, authenticated, authority/role/scope gì? Authentication trong SecurityContext có đúng không?
4. **Filter phát sinh lỗi:** BasicAuthenticationFilter, CsrfFilter, AuthorizationFilter, custom filter, method security hay MVC?
5. **Exception type:** AuthenticationException hay AccessDeniedException? Có wrapper/nested cause không?
6. **ETF nằm ở đâu:** exception phát sinh **trước hay sau** ETF? Nó có đi tới ETF chưa hay đã bị handler khác xử lý?
7. **Entry point/denied handler nào:** từ chain nào, custom config nào? HTTP Basic, Bearer, form login, REST JSON?
8. **Response đã commit chưa:** có filter/controller ghi body rồi mới throw exception không?
9. **RequestCache:** API dùng NullRequestCache hay web dùng HttpSessionRequestCache?
10. **CSRF:** nếu POST/PATCH/PUT/DELETE 403, kiểm tra CSRF token trước khi kết luận role bị thiếu.
11. **MVC error:** nếu 404/405/500, kiểm tra DispatcherServlet/ControllerAdvice và error dispatch.
12. **Tests:** tái hiện bằng MockMvc và test HTTP thật khi filter order/network behavior quan trọng.

### 12.1. Bật log có kiểm soát

Ví dụ trong `application.properties` cho môi trường dev:

```properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=TRACE
```

Đây là gợi ý phát hiện selected chain, security errors và cách response được điều phối. Đừng bật TRACE dài hạn trên production nếu chưa kiểm soát dữ liệu có thể lộ. Không log `Authorization` header, raw passwords, session cookies, bearer tokens, reset links hay dữ liệu cá nhân nhạy cảm.

### 12.2. Những breakpoint hữu ích

| Breakpoint | Câu hỏi được giải quyết |
| --- | --- |
| `FilterChainProxy.doFilter` | Security chain nào match? |
| `BasicAuthenticationFilter.doFilterInternal` | Credentials có đến từ Basic? Failure xử lý ở đâu? |
| `CsrfFilter.doFilterInternal` | Request có thiếu CSRF token không? |
| `ExceptionTranslationFilter.doFilter` | Có exception phù hợp từ downstream thoát lên không? |
| `ExceptionTranslationFilter.handleAccessDeniedException` | Anonymous/remember-me hay authenticated? |
| `AuthenticationEntryPoint.commence` | Ai tạo 401/redirect và challenge header? |
| `AccessDeniedHandler.handle` | Ai tạo 403 và error body? |
| `AuthorizationFilter.doFilter` | Authorization rule nào từ chối? |
| `DispatcherServlet.doDispatch` | Request đã vào MVC chưa? |
| `HandlerExceptionResolver.resolveException` | MVC có xử lý exception trước khi ETF nhìn thấy không? |

Tên method có thể đổi theo version; chọn breakpoint trong source của đúng dependency đã tải. Với một custom filter, đặt breakpoint trước/sau `chain.doFilter` và ghi nhận thứ tự thực tế.

## 13. Anti-patterns dễ mắc

### 13.1. “ExceptionTranslationFilter kiểm tra quyền”

Sai. Nó là **translator**. `AuthorizationFilter`/method security mới đánh giá quyền. Nếu không có cơ chế authorization và mọi request được cho đi tiếp, ETF không tự từ chối quyền để “bảo vệ tất cả”.

### 13.2. “AccessDeniedException luôn trả 403”

Sai. Nếu anonymous hoặc một remember-me được coi chưa đủ, ETF có thể đưa sang entrypoint. API Basic thường 401; web login thường redirect.

### 13.3. “AuthenticationException luôn là lỗi password sai”

Sai. Không có credentials, hết hạn authentication hoặc step-up chưa đủ cũng có thể là AuthenticationException. Đừng leak lý do chi tiết cho client.

### 13.4. “Mọi 401 đều do ExceptionTranslationFilter”

Sai. `BasicAuthenticationFilter` hoặc bearer authentication filter có thể tự xử lý authentication failure bằng entry point.

### 13.5. “Mọi 403 đều do AccessDeniedHandler cấu hình ở exceptionHandling”

Sai. `CsrfFilter` có thể dùng AccessDeniedHandler riêng. MVC/controller hoặc gateway cũng có thể tạo 403.

### 13.6. “permitAll bỏ qua toàn bộ security filters”

Sai. `permitAll` bỏ qua yêu cầu **authorization** với URL đó, không bỏ CsrfFilter/headers và các filter khác. `web.ignoring` khác permitAll và có hệ quả bỏ qua security chain.

### 13.7. “Global ControllerAdvice bắt mọi security exception”

Sai. Filter chạy trước MVC có thể viết response mà MVC hoàn toàn không được gọi; ngược lại ControllerAdvice catch-all có thể vô tình nuốt exception security từ controller.

### 13.8. “Đổi 401 thành 403 để khỏi lộ thông tin”

Không có một thay đổi status nào tự giải quyết information disclosure. Thiết kế authentication challenge, resource existence policy, API contract và error messages có kiểm soát. Thay sai 401/403 có thể phá hành vi client và làm sai monitoring.

### 13.9. “Lúc nào cũng cần saved request”

Không. Browser form login có thể cần khôi phục URL; stateless API thường chọn `NullRequestCache`. Tránh tạo session không cần thiết hoặc saved request không an toàn.

### 13.10. “Tạo AccessDeniedException cho mọi validation error”

Sai. JSON sai format hoặc field validation không hợp lệ thường là 400, không phải authorization failure. Giữ lỗi đúng lớp nghiệp vụ.

### 13.11. “Đã set 200 rồi exception handler ghi 401”

Nếu response đã commit, không thể an toàn ghi status/body mới. Đừng stream response trước khi có những kiểm tra security cần thiết.

### 13.12. “Để default handlers cho REST API, chắc chắn trả JSON”

Không. Default entry point có thể redirect HTML hoặc trả challenge không có body. API phải cấu hình và test response contract nếu cần JSON ổn định.

### 13.13. “Hai SecurityFilterChains luôn cộng dồn”

Không. FilterChainProxy chọn chain đầu tiên match. Error handling của chain không áp dụng cho request đi vào chain khác.

### 13.14. “@WithMockUser đủ để test login password”

Không. Nó bỏ qua credential authentication. Dùng `httpBasic(...)` hoặc form login test để chứng minh authentication provider thật hoạt động.

### 13.15. “Throw exception trực tiếp trong filter ở trước ETF sẽ được ETF catch”

Không. Bộ lọc phía sau không thể bắt exception đã phát sinh từ tầng ngoài trước khi nó được gọi.

### 13.16. “Lỗi CSRF 403 thì user thiếu ROLE_ADMIN”

Không. Một request authenticated với đúng role vẫn có thể thiếu CSRF token. Test rõ authentication, authorization và CSRF riêng.

### 13.17. “Cho 401 với role thiếu rồi gọi lại password”

Khi user đã fully authenticated mà thiếu role, entrypoint challenge thêm password không tự cấp role. Giữ 403 theo policy và sửa authorization/permission hợp lệ, không tạo vòng lặp login.

### 13.18. “Ghi exception.message vào JSON trả cho client”

Thông báo nội bộ có thể chứa username, token details, policy info hoặc stack trace. Dùng error code ổn định, chi tiết hạn chế, correlation ID và log đã redaction.

### 13.19. “Không có controller thì vẫn phải do ExceptionTranslationFilter xử lý”

Không. URL permitAll không có MVC handler thường trả 404/405; ETF không thay DispatcherServlet và handler mappings.

### 13.20. “Trong async dispatch, chỉ cần nghĩ đến một FilterChain duy nhất”

Async, FORWARD, ERROR dispatch có thể tạo thêm processing và security authorization theo DispatcherType/config. Đánh giá filter registration, SecurityContext propagation và error dispatch để tránh thay đổi status ngoài ý muốn.

## 14. Checklist kiểm tra thiết kế

**Authentication vs authorization**

- [ ] Liệt kê các authentication mechanisms được bật: HTTP Basic, form, bearer/JWT, OAuth2, SSO.
- [ ] Biết loại principal nào là anonymous/remember-me/fully-authenticated.
- [ ] Hiểu handler xác thực thất bại trực tiếp của từng authentication filter.
- [ ] Không map mọi AuthenticationException thành “bad password”.
- [ ] Không map mọi AccessDeniedException thành 403 mà bỏ qua trạng thái principal.

**ETF và error handlers**

- [ ] Xác định mỗi SecurityFilterChain đã cấu hình AuthenticationEntryPoint/AccessDeniedHandler thế nào.
- [ ] Entry point giữ đúng WWW-Authenticate challenge hoặc redirect behavior.
- [ ] AccessDeniedHandler trả 403/body phù hợp với API/browser.
- [ ] RequestCache phù hợp: NullRequestCache cho stateless/Basic khi cần, saved request cho web khi cần.
- [ ] Phân biệt exception ở phía trước và phía sau ExceptionTranslationFilter.
- [ ] CSRF filter errors được kiểm thử riêng, không nhầm handler.
- [ ] Không có ControllerAdvice catch-all làm hỏng security responses.
- [ ] Không viết response lần hai sau khi committed.
- [ ] Không lộ credentials, tokens, stack traces hoặc policy details.

**Servlet/MVC và QA**

- [ ] Kiểm tra SecurityFilterChain order, securityMatcher và fallback.
- [ ] Kiểm tra AuthorizationFilter/role/scope và method-level authorization.
- [ ] Kiểm tra owner/tenant/object-level permission tại service.
- [ ] Test anonymous 401/302, authenticated missing role 403, authentication success 200.
- [ ] Test Basic password sai do authentication filter xử lý.
- [ ] Test CSRF 403, MVC 404/405 và security 403 riêng.
- [ ] Test JSON/status/WWW-Authenticate headers bằng MockMvc.
- [ ] Test filter trước ETF và exception downstream khi có custom filters.
- [ ] Có monitoring và security audit với redaction, không chỉ dựa vào client status.
- [ ] Đối chiếu Spring Security API theo version BOM thực dùng, không copy cấu hình WebFlux.

## 15. Tự kiểm tra và đáp án

**1. ExceptionTranslationFilter có tự kiểm tra role/authority không?**  
Không. Nó chuyển các security exceptions phù hợp thành HTTP response; authorization ở filter/manager khác.

**2. Filter nào thường ném AccessDeniedException khi URL không đạt rule?**  
AuthorizationFilter (qua AuthorizationManager).

**3. Anonymous gọi URL yêu cầu authenticated, có thể nhận status nào trong API Basic?**  
401 từ AuthenticationEntryPoint được ETF kích hoạt sau AccessDeniedException.

**4. User login đúng nhưng thiếu ROLE_ADMIN, handler nào thường được gọi?**  
AccessDeniedHandler, thường trả 403.

**5. Vì sao AccessDeniedException đôi khi đi vào AuthenticationEntryPoint?**  
Vì AuthenticationTrustResolver nhận diện anonymous hoặc remember-me chưa đủ; cần yêu cầu authentication.

**6. AuthenticationException được ETF bắt sẽ tới đâu?**  
AuthenticationEntryPoint, với SecurityContext được clear và RequestCache theo cấu hình.

**7. AuthenticationEntryPoint có bắt buộc trả JSON 401 không?**  
Không. Form login thường redirect; Basic/Bearer thường dùng 401 challenge.

**8. AccessDeniedHandler có tự cấp role admin không?**  
Không. Nó phản hồi việc quyền bị từ chối.

**9. Vì sao HTTP Basic sai password có thể 401 mà không qua ETF?**  
BasicAuthenticationFilter có cơ chế xử lý authentication failure và gọi entrypoint trực tiếp.

**10. Vì sao POST thiếu CSRF token trả 403 dù endpoint permitAll?**  
CsrfFilter hoạt động độc lập trước authorization và có denied handling riêng.

**11. Vì sao @ControllerAdvice không chắc bắt exception từ Servlet filter?**  
Vì MVC exception resolver chỉ xử lý phạm vi MVC, còn filter có thể chạy trước DispatcherServlet.

**12. RequestCache có nhất thiết tạo session không?**  
Không; NullRequestCache không lưu request, HttpSessionRequestCache có thể lưu trong session.

**13. Nếu response đã committed rồi, có thể chắc chắn đổi status thành 401 không?**  
Không. Ghi response mới có thể thất bại và gây lỗi thứ cấp.

**14. Nếu nhiều SecurityFilterChain match cùng request, handler nào áp dụng?**  
Chain đầu tiên khớp được FilterChainProxy chọn, không cộng dồn tất cả.

**15. Cách test đúng một user reader thiếu quyền admin?**  
MockMvc GET /api/admin với credential reader hợp lệ, assert 403 và error contract.

**16. Vì sao không dùng @WithMockUser để khẳng định password hashing/login hoạt động?**  
Annotation tạo Authentication giả, bỏ qua đường xác minh credentials thật.

**17. Khi nhận 403, cần kiểm tra đầu tiên những nơi nào?**  
CsrfFilter, AuthorizationFilter, AccessDeniedHandler, principal authorities và route matcher.

**18. Spring WebFlux dùng cùng Servlet ExceptionTranslationFilter không?**  
Không. WebFlux có reactive security chain và các component tương ứng, không copy trực tiếp Servlet APIs.

## 16. Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Servlet Architecture và ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Authentication Architecture, EntryPoint](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security – ExceptionTranslationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security – AuthenticationEntryPoint Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html)
- [Spring Security – AccessDeniedHandler Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandler.html)
- [Spring Security – RequestCache Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html)
- [Spring Framework 6.2 – DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html)
- [Jakarta Servlet 6.0 – Servlet API specification](https://jakarta.ee/specifications/servlet/6.0/)
