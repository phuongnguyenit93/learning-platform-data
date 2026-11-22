# AuthenticationSuccessHandler và AuthenticationFailureHandler

**Module:** Spring Security – authentication. **Chủ đề cha:** Tích hợp bộ lọc. **Phạm vi:** Spring Security Servlet, đặc biệt form login và các authentication filters dựa trên `AbstractAuthenticationProcessingFilter`.

## 1. Bài toán: xác thực đã xong nhưng HTTP response sẽ đi đâu?

Khi người dùng gửi `POST /login`, ứng dụng phải giải quyết **hai việc khác nhau**:

1. **Xác thực**: username/password, tài khoản bị khóa, credential, MFA hay các điều kiện khác có hợp lệ không? Phần này thuộc `AuthenticationManager`, `AuthenticationProvider` và các cơ chế xác thực.
2. **Phản hồi sau nỗ lực xác thực**: nếu thành công thì chuyển người dùng về trang từng yêu cầu, về dashboard, hay trả JSON? Nếu thất bại thì redirect đến form login hay trả HTTP 401 với thông báo an toàn? Phần này thuộc **`AuthenticationSuccessHandler`** và **`AuthenticationFailureHandler`**.

Ví dụ:

~~~text
POST /login  [username/password]
      |
      v
UsernamePasswordAuthenticationFilter
      |
      v
AuthenticationManager.authenticate(...)
      |
      +--- THÀNH CÔNG ---> AuthenticationSuccessHandler
      |                       |
      |                       +--> 302 /dashboard
      |                       +--> 302 URL đã lưu trước login
      |                       +--> 200 JSON cho frontend tương ứng
      |
      +--- THẤT BẠI ----> AuthenticationFailureHandler
                              |
                              +--> 302 /login?error
                              +--> 401 JSON thông điệp chung
~~~

**Điểm cốt lõi:** Hai handler quyết định **cách hoàn tất phản hồi/điều hướng** sau khi một nỗ lực authentication đã được xử lý. Chúng **không xác minh mật khẩu thay provider**, **không trực tiếp cấp quyền** và **không tự bảo đảm SecurityContext được lưu vào HTTP session**.

Bài học áp dụng trực tiếp cho `UsernamePasswordAuthenticationFilter`/`formLogin`, đồng thời phân biệt với token bearer, HTTP Basic, OAuth2/OIDC, logout và lỗi authorization để tránh đặt handler sai chỗ.

## 2. Tách các giai đoạn của Servlet authentication flow

Một luồng form login thường bao gồm:

1. `UsernamePasswordAuthenticationFilter` thấy request phù hợp `loginProcessingUrl`, thường là `POST /login`.
2. Filter trích username/password từ request và tạo `UsernamePasswordAuthenticationToken` **chưa xác thực**.
3. Filter gọi `AuthenticationManager.authenticate(...)`.
4. `AuthenticationProvider` xử lý: đọc `UserDetails`, đối chiếu password, kiểm tra account flags, trả `Authentication` đã xác thực hoặc ném `AuthenticationException`.
5. Nếu thành công, cơ chế filter liên quan gọi `SessionAuthenticationStrategy`, chuẩn bị/lưu `SecurityContext`, phối hợp remember-me và phát sự kiện thích hợp rồi gọi **`AuthenticationSuccessHandler`**.
6. Nếu thất bại, cơ chế filter dọn `SecurityContextHolder`, gọi remember-me failure hook nếu có và gọi **`AuthenticationFailureHandler`**.
7. Handler tạo response thích hợp và kết thúc hoặc điều hướng request theo implementation.

~~~text
                   Servlet FilterChain
                          |
                          v
           AbstractAuthenticationProcessingFilter
                          |
             requiresAuthentication(request)?
                 |                   |
                no                  yes
                 |                   |
                 v                   v
          tiếp tục chain      attemptAuthentication(...)
                                     |
                              +------+------+
                              |             |
                             ok        AuthenticationException
                              |             |
                              v             v
                     Session strategy   Clear holder /
                     SecurityContext    remember-me fail
                     remember-me        |
                     success event      |
                              |             |
                              v             v
                     successful...    unsuccessful...
                              |             |
                              v             v
                    SuccessHandler    FailureHandler
                              |             |
                              v             v
                    Redirect/JSON     Redirect/JSON
~~~

Đây là **sơ đồ rút gọn**. Chương trình thực có thể có nhiều filters, session policies và cơ chế auth khác. `attemptAuthentication(...)` có thể trả `null` khi quy trình còn đang tiếp tục (ví dụ multi-step), nên không phải mọi request tới filter đều gọi ngay một trong hai handler.

### Ai chịu trách nhiệm cho điều gì?

| Thành phần | Việc chính | Không nên bắt nó làm |
| --- | --- | --- |
| `AuthenticationManager` | Điều phối xác thực credential | Tạo redirect/HTML/JSON của form login |
| `AuthenticationProvider` | Xác minh thông tin và account state | Đọc query `next` rồi quyết định điều hướng |
| `SecurityContextRepository` | Tải/lưu context theo request/session policy | Tự kiểm tra password hoặc tự chọn trang tiếp theo |
| `AuthenticationSuccessHandler` | Hoàn tất phản hồi HTTP sau xác thực thành công | Tự tạo role/admin từ input client |
| `AuthenticationFailureHandler` | Hoàn tất phản hồi HTTP khi authentication bị từ chối | Tiết lộ username có thật hoặc nguyên nhân account khóa |
| `AuthenticationEntryPoint` | Bắt đầu login/challenge khi truy cập tài nguyên mà **chưa được xác thực** | Xử lý mọi trường hợp form đã thử password sai |
| `AccessDeniedHandler` | Xử lý thiếu quyền khi đã xác thực, thường 403 | Chuyển lỗi authorization thành lỗi sai mật khẩu |
| `LogoutSuccessHandler` | Điều hướng/phản hồi sau logout | Nhầm với login success handler |

## 3. Hợp đồng AuthenticationSuccessHandler

Interface:

~~~java
package org.springframework.security.web.authentication;

// Rút gọn chữ ký; không phải Java file độc lập.
public interface AuthenticationSuccessHandler {

    void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException;

    default void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain,
            Authentication authentication)
            throws IOException, ServletException;
}
~~~

Trong Spring Security 6.5.11, đây là các chữ ký Servlet với `jakarta.servlet.*`, **không dùng `javax.servlet.*` của các thế hệ cũ**.

Tham số:

- `request`: request HTTP vừa thực hiện authentication.
- `response`: response HTTP để redirect, forward, thiết lập status, header hay body.
- `authentication`: kết quả do cơ chế đáng tin đã xác minh, chứa principal/authorities.
- `chain` ở overload thứ tư: có thể phục vụ cách tiếp tục filter chain trong một số loại authentication flow; không mặc định giả định mọi form login sẽ gọi overload này.

**Handler không nên gọi lại `authenticationManager.authenticate(...)` theo thói quen.** Nếu re-authenticate bên trong handler, có thể tạo thêm tác động phụ, tăng latency, vòng lặp hoặc sai session policy. Tại thời điểm được gọi, framework thông thường đã có kết quả xác thực.

### Điều handler thành công thường làm

- Quyết định URL hợp lệ để redirect, như trang trước login hoặc dashboard.
- Trả JSON/HTTP status phù hợp cho frontend dùng form-login endpoint kiểu AJAX.
- Ghi audit event **không chứa credential**; phát metric success có kiểm soát.
- Chọn bước tiếp theo **theo trạng thái server đáng tin** (ví dụ onboarding, setup bắt buộc), không dựa vào cờ role client gửi.
- Thực hiện công việc HTTP nhẹ và xác định rõ, tránh gọi dịch vụ chậm hoặc ghi dữ liệu quan trọng sau khi response đã commit.

### Không phải trách nhiệm mặc định

`AuthenticationSuccessHandler` không tự:

- Lưu database account hay thay đổi mật khẩu;
- Bảo vệ session fixation thay `SessionAuthenticationStrategy`;
- Tạo `SecurityContext`/cookie nếu một custom login controller đã bỏ qua các bước framework;
- Cập nhật quyền đã bị thu hồi trong một session cũ;
- Xác thực JWT trên mọi request resource server.

## 4. Hợp đồng AuthenticationFailureHandler

Interface:

~~~java
package org.springframework.security.web.authentication;

// Rút gọn chữ ký; không phải Java file độc lập.
public interface AuthenticationFailureHandler {

    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
~~~

`exception` thể hiện nguyên nhân nội bộ do hệ thống xác thực từ chối, ví dụ:

- `BadCredentialsException`;
- `LockedException`;
- `DisabledException`;
- `AccountExpiredException`;
- `CredentialsExpiredException`;
- Một số `AuthenticationServiceException`, tùy lỗi và provider.

**Dữ liệu exception là thông tin nội bộ**, không phải mặc nhiên là câu chữ giao diện. Đặc biệt, đừng làm:

~~~java
// KHÔNG AN TOÀN: lộ nguyên nhân/trạng thái/account information.
response.getWriter().write(exception.getMessage());
~~~

Với login công khai, nên chuẩn hóa những trường hợp password sai, username không tồn tại, account locked/disabled thành **phản hồi chung**, trong khi hệ thống vẫn giữ audit chi tiết bên trong theo quyền truy cập được kiểm soát.

`AuthenticationFailureHandler` nhận **`AuthenticationException`** của nỗ lực authentication. Một lỗi cơ sở dữ liệu, lỗi JSON, lỗi filter hoặc `RuntimeException` khác có thể không đi qua handler này, tùy implementation; cần có cơ chế xử lý lỗi hạ tầng an toàn riêng.

## 5. Điều gì xảy ra trước và sau handler?

### 5.1. Nhánh thành công

Trong luồng `AbstractAuthenticationProcessingFilter`:

~~~text
attemptAuthentication() -> Authentication result
                 |
                 v
        SessionAuthenticationStrategy
                 |
                 v
       successfulAuthentication(...)
                 |
          +------+-------+
          |              |
  SecurityContext      RememberMeServices
  được chuẩn bị/lưu    loginSuccess
          |              |
          +------+-------+
                 |
       InteractiveAuthenticationSuccessEvent
                 |
                 v
       AuthenticationSuccessHandler
                 |
                 v
         HTTP response/redirect
~~~

Luồng trên theo tài liệu Spring Security 6.5. Các chi tiết thứ tự, repository và session strategy phụ thuộc filter/configuration. **Không dời thao tác lưu context tới sau khi handler đã redirect**.

Nếu sử dụng `UsernamePasswordAuthenticationFilter` được cấu hình bởi `formLogin`, framework cung cấp quá trình chuẩn bị security context. Nếu tự viết `AbstractAuthenticationProcessingFilter` subclass/filter, phải cấu hình đúng `SecurityContextRepository` và session strategy; tài liệu API filter còn lưu ý default action của một instance tự khởi tạo có thể là **không lưu context** nếu chưa set repository.

### 5.2. Nhánh thất bại

~~~text
attemptAuthentication(...) ném AuthenticationException
                 |
                 v
       SecurityContextHolder cleared
                 |
                 v
       RememberMeServices.loginFail
                 |
                 v
       AuthenticationFailureHandler
                 |
                 v
    URL login chung / HTTP 401 chung
~~~

Handler thất bại không phải nơi “cấp quyền hạn chế” để cho user bị khóa vẫn đăng nhập. Khi auth thất bại, không được tùy tiện đưa `Authentication(isAuthenticated=true)` vào context hoặc cấp session authenticated để hoàn tất response.

### 5.3. Sự kiện và audit

`InteractiveAuthenticationSuccessEvent` do cơ chế filter phù hợp phát cho login thành công. Lỗi authentication có thể được ghi nhận bằng sự kiện từ `AuthenticationManager`/provider tùy cấu hình; không giả định có một sự kiện failure đối xứng phát từ `AbstractAuthenticationProcessingFilter`.

Có thể viết `ApplicationListener`, event publisher, audit service hoặc metrics độc lập. Khi ghi vào handler, dùng thông tin tối thiểu: user ID đã xác minh, request/correlation ID, result, category an toàn. Không log raw password, bearer token, cookie, toàn bộ principal hoặc full stack trace chứa dữ liệu nhạy cảm.

## 6. Bộ handler có sẵn: chọn trước khi tự viết

### Thành công

| Implementation | Hành vi chính | Dùng khi |
| --- | --- | --- |
| `SavedRequestAwareAuthenticationSuccessHandler` | Ưu tiên URL đã lưu trước khi yêu cầu login, nếu có; nếu không dùng target mặc định | Browser form login, quay lại trang người dùng định mở |
| `SimpleUrlAuthenticationSuccessHandler` | Redirect/forward tới target URL được xác định theo policy của base class | Luồng điều hướng cố định hoặc đơn giản |
| `ForwardAuthenticationSuccessHandler` | Server-side forward tới URL mong muốn | Muốn forward thay vì browser redirect, hiểu rõ request semantics |
| `HttpMessageConverterAuthenticationSuccessHandler` | Tạo phản hồi bằng HTTP message conversion theo cấu hình | Tích hợp API khi framework và converter phù hợp |

### Thất bại

| Implementation | Hành vi chính | Lưu ý |
| --- | --- | --- |
| `SimpleUrlAuthenticationFailureHandler` | Redirect tới `defaultFailureUrl` nếu đã cấu hình; nếu không có URL, gửi HTTP 401 | Tài liệu API nêu nhánh 401 mặc định có thể chứa message của exception; nên chuẩn hóa ở API công khai |
| `ForwardAuthenticationFailureHandler` | Forward tới URL xử lý thất bại | Không tự làm request thành authenticated |
| `ExceptionMappingAuthenticationFailureHandler` | Map exception type đến URL | Tránh làm lộ locked/disabled/not-found qua URL |
| `DelegatingAuthenticationFailureHandler` | Chọn sub-handler theo subclass của `AuthenticationException` | Hữu ích cho routing nội bộ nhưng public responses vẫn cần không thành oracle |
| `AuthenticationEntryPointFailureHandler` | Chuyển việc xử lý failure cho một `AuthenticationEntryPoint` | Dùng khi cùng một challenge/response policy thích hợp |

Các class trên là **công cụ điều hướng**, không phải security policy hoàn chỉnh. Một handler mặc định phù hợp với HTML có thể **không** phù hợp với frontend chỉ chấp nhận JSON.

## 7. SavedRequestAwareAuthenticationSuccessHandler và RequestCache

Đây là điểm khác nhau quan trọng giữa “login xong về dashboard” và “login xong trở lại trang đã yêu cầu”.

### 7.1. Một luồng browser điển hình

~~~text
1. GET /orders/42          [chưa đăng nhập]
            |
            v
2. Authorization yêu cầu authenticated
            |
            v
3. ExceptionTranslationFilter / AuthenticationEntryPoint
            |
            +--> RequestCache lưu yêu cầu gốc
            +--> redirect /login
            |
            v
4. POST /login             [password đúng]
            |
            v
5. SavedRequestAwareAuthenticationSuccessHandler
            |
            +--> lấy SavedRequest từ RequestCache
            +--> redirect /orders/42
            |
            v
6. GET /orders/42          [đã có session authenticated]
~~~

`ExceptionTranslationFilter` và `RequestCache` có vai trò lưu request ban đầu; `SavedRequestAwareAuthenticationSuccessHandler` đọc lại để quyết định target.

### 7.2. Thứ tự chọn target theo API 6.5

Theo Javadoc:

1. Nếu `alwaysUseDefaultTargetUrl=true`, dùng `defaultTargetUrl`, xóa saved request phù hợp.
2. Nếu đã cấu hình `targetUrlParameter` và request có giá trị cho tham số đó, handler có thể dùng URL tham số; saved request được xóa theo luồng này.
3. Nếu có `SavedRequest` trong `RequestCache`, redirect về URL đã lưu.
4. Nếu không có saved request, hành vi chuyển cho logic của superclass `SimpleUrlAuthenticationSuccessHandler` (thường target mặc định).

**Lưu ý bảo mật:** Tham số `targetUrlParameter` hay một query `next=/...` **không phải dữ liệu đáng tin**. Không dùng trực tiếp URL bên ngoài do user đưa vào làm redirect, nếu không có thể tạo **open redirect** phục vụ phishing.

### 7.3. Ví dụ cấu hình formLogin phổ biến

~~~java
// MÃ TÍCH HỢP Spring Security Servlet; không standalone.
http.formLogin(form -> form
        .loginPage("/login")
        .defaultSuccessUrl("/dashboard", false)
        .failureUrl("/login?error")
        .permitAll());
~~~

`defaultSuccessUrl("/dashboard", false)`: khi có saved request phù hợp, người dùng thường được đưa trở lại URL cũ; khi không có, dùng `/dashboard`.

~~~java
// MÃ TÍCH HỢP, không standalone:
http.formLogin(form -> form
        .defaultSuccessUrl("/dashboard", true));
~~~

`true` yêu cầu luôn dùng default target URL, bỏ qua nhu cầu quay lại trang đã yêu cầu trước login theo cách cấu hình này.

**Không** cấu hình thêm handler tùy biến chỉ để đạt một redirect đơn giản mà `defaultSuccessUrl`/`failureUrl` đã làm được.

### 7.4. Target URL sau login không được dùng để quyết định quyền

Một người có `ROLE_USER` bị redirect tới `/admin` vẫn phải chịu `AuthorizationManager`, `@PreAuthorize` hoặc policy server ở endpoint thật; handler không cấp `ROLE_ADMIN` chỉ vì chuyển URL.

Khi chọn trang theo role, lấy authorities từ **`Authentication` do provider đáng tin trả về** và chỉ chọn một URL nội bộ/đã allowlist. Không dùng `request.getParameter("role")` để quyết định quyền hoặc trang admin.

## 8. SimpleUrlAuthenticationFailureHandler: redirect và session-side exception

Javadoc `SimpleUrlAuthenticationFailureHandler` nêu:

- Nếu `defaultFailureUrl` được cấu hình, handler dùng redirect (hoặc forward nếu `useForward=true`).
- Nếu không cấu hình URL, implementation gửi 401; message có thể bắt nguồn từ `AuthenticationException`.
- Khi forward/redirect, nó có thể lưu exception ở request/session attribute để view sử dụng (phụ thuộc `allowSessionCreation`/`useForward`).

Điều này dẫn đến hai lưu ý:

**Lưu exception để view không đồng nghĩa được phép render exception.getMessage().** Một lỗi `LockedException` có thể chứa “account is locked”. Hãy hiển thị câu chung ở trang login, ví dụ “Tên đăng nhập hoặc mật khẩu không hợp lệ hoặc không thể đăng nhập lúc này”.

**Redirect thất bại có thể tạo session** nếu handler muốn lưu exception và `allowSessionCreation=true`. Nếu đang debug vì sao chưa login mà có `JSESSIONID`, hãy xét `RequestCache`, failure handler và các filter khác, không đổ hết cho `SecurityContextRepository`.

### Form login truyền thống

~~~java
http.formLogin(form -> form
        .loginPage("/login")
        .failureUrl("/login?error")
        .permitAll());
~~~

Trên trang login, dùng cùng một thông điệp công khai khi có tham số `error`. Không chuyển nguyên nhân thành `/login?locked=true`, `/login?userNotFound=true` hay `X-Account-Status`.

## 9. So sánh ba lựa chọn HTTP response

| Mô hình client | Khi login thành công | Khi login thất bại | Ghi nhớ |
| --- | --- | --- | --- |
| Browser form navigation | `302` về saved URL hoặc dashboard | `302` về `/login?error` | Browser thực hiện GET sau redirect; session cookie duy trì đăng nhập |
| AJAX gọi endpoint form-encoded | `200` JSON/status tùy API contract | `401` JSON chung | Vẫn là request form-urlencoded nếu dùng UsernamePasswordAuthenticationFilter mặc định |
| Stateless API login/token issuance tự thiết kế | `200`/`201` và token/session contract thích hợp | `401`/mã giao thức phù hợp | Cần filter/controller/provider và token handling riêng, không chỉ thay handler |

**Không dùng một response cho mọi giao thức một cách máy móc.** Với HTTP Basic, bearer token hoặc OAuth2/OIDC, các entry point/challenge/error semantics có thể yêu cầu header/status cụ thể. Hãy chọn response phù hợp cơ chế auth và không lộ account existence/state ngoài mức cần thiết.

### Redirect và forward khác nhau

- **Redirect**: server gửi 3xx với Location; browser thực hiện request mới tới URL đích.
- **Forward**: chuyển xử lý bên trong server cho cùng request/response qua `RequestDispatcher`; không tự tạo request mới ở browser.
- Forward sau POST có thể làm trang đích thấy method/body POST; cần hiểu CSRF, request-scoped values, URL hiển thị và tránh vô tình xử lý lại credential.

Đối với Post/Redirect/Get của HTML login, redirect thường dễ quản lý hơn.

## 10. Ví dụ Java 17 chạy được: hai handlers trả JSON an toàn

Ví dụ hoàn chỉnh này tạo **handler thực sự theo interface Spring Security 6.5.11**, nhưng gọi chúng trực tiếp bằng `MockHttpServletRequest`/`MockHttpServletResponse`. Nó **không cần Spring Boot, DB, server, TLS hay filter chain**. Mục đích là kiểm chứng chính xác **nội dung response** và việc hai nguyên nhân thất bại nội bộ nhận cùng phản hồi công khai.

**Ranh giới an toàn:** `Authentication` được tạo trực tiếp trong chương trình thử nghiệm để mô phỏng kết quả đã được xác minh. **Không được** tạo token authenticated từ username/role do client gửi trong production. Ở ứng dụng thật, `AuthenticationManager`/provider phải xác minh credential trước khi success handler được gọi.

### 10.1. Cấu trúc thư mục

~~~text
authentication-handlers-demo/
├── build.gradle
└── src/main/java/example/AuthenticationHandlersDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework:spring-test:6.2.15'
    implementation 'org.springframework:spring-web:6.2.15'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.AuthenticationHandlersDemo'
}
~~~

**File `src/main/java/example/AuthenticationHandlersDemo.java`:**

~~~java
package example;

import java.util.List;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public final class AuthenticationHandlersDemo {

    private static final String OK =
            "{\"code\":\"LOGIN_OK\"}";

    private static final String FAIL =
            "{\"code\":\"AUTHENTICATION_FAILED\"}";

    private static AuthenticationSuccessHandler successHandler() {
        return (request, response, authentication) -> {
            // Framework chỉ gọi success handler sau authentication thành công.
            // Check bổ sung này giúp demo thể hiện ranh giới tin cậy.
            if (authentication == null || !authentication.isAuthenticated()) {
                throw new IllegalStateException("Missing trusted authentication");
            }

            response.setStatus(200);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(OK);
        };
    }

    private static AuthenticationFailureHandler failureHandler() {
        return (request, response, exception) -> {
            // Có thể ghi audit nội bộ đã hạn chế quyền xem.
            // Không trả exception class/message/username ra client.
            response.setStatus(401);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(FAIL);
        };
    }

    private static MockHttpServletRequest newLoginRequest() {
        return new MockHttpServletRequest("POST", "/login");
    }

    public static void main(String[] args) throws Exception {
        // Chỉ tạo token authenticated trong demo đáng tin.
        Authentication trusted =
                UsernamePasswordAuthenticationToken.authenticated(
                        "linh", null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        MockHttpServletResponse success = new MockHttpServletResponse();
        successHandler().onAuthenticationSuccess(
                newLoginRequest(), success, trusted);

        System.out.println("success.status=" + success.getStatus());
        System.out.println("success.json="
                + success.getContentAsString());
        System.out.println("success.contentTypeIsJson="
                + success.getContentType().startsWith("application/json"));
        System.out.println("success.cacheControl="
                + success.getHeader("Cache-Control"));

        AuthenticationFailureHandler failureHandler = failureHandler();

        MockHttpServletResponse bad = new MockHttpServletResponse();
        failureHandler.onAuthenticationFailure(
                newLoginRequest(), bad,
                new BadCredentialsException("internal bad credentials"));

        MockHttpServletResponse locked = new MockHttpServletResponse();
        failureHandler.onAuthenticationFailure(
                newLoginRequest(), locked,
                new LockedException("internal account locked"));

        System.out.println("bad.status=" + bad.getStatus());
        System.out.println("locked.status=" + locked.getStatus());
        System.out.println("failure.sameBody="
                + bad.getContentAsString().equals(
                        locked.getContentAsString()));
        System.out.println("failure.publicJson="
                + locked.getContentAsString());
        System.out.println("failure.leaksInternal="
                + (locked.getContentAsString().contains("internal")
                   || bad.getContentAsString().contains("internal")));
        System.out.println("failure.cacheControl="
                + locked.getHeader("Cache-Control"));
    }
}
~~~

### 10.2. Chạy

Dùng **JDK 17+**, bản Gradle tương thích và kết nối Maven Central khi tải dependency lần đầu. Trong thư mục `authentication-handlers-demo`:

~~~bash
gradle -q run
~~~

Nếu dự án có Gradle Wrapper, dùng `./gradlew -q run`; Windows dùng `gradlew.bat -q run`.

**Stdout của chính chương trình** (không kể log từ Gradle/thư viện khi môi trường cấu hình thêm):

~~~text
success.status=200
success.json={"code":"LOGIN_OK"}
success.contentTypeIsJson=true
success.cacheControl=no-store
bad.status=401
locked.status=401
failure.sameBody=true
failure.publicJson={"code":"AUTHENTICATION_FAILED"}
failure.leaksInternal=false
failure.cacheControl=no-store
~~~

### 10.3. Giải thích đầu ra

- `success.status=200` và JSON `LOGIN_OK`: handler thành công đã hoàn tất response mà **không redirect**.
- `success.contentTypeIsJson=true`: response dùng JSON media type.
- `Cache-Control: no-store`: tránh cache response có liên quan đến phiên đăng nhập; trong production còn cần cookie/session flags, HTTPS và các headers chính sách.
- `bad.status=401`, `locked.status=401`: hai trường hợp bị từ chối đều nhận HTTP status chung.
- `failure.sameBody=true`, `failure.leaksInternal=false`: body không tiết lộ người dùng bị khóa hay mật khẩu sai.
- `failure.publicJson`: chỉ trả mã lỗi an toàn; frontend có thể hiển thị câu hướng dẫn chung.
- Demo **không** chứng minh timing/header/cookie khác biệt giữa account tồn tại và không tồn tại trong luồng xác thực thực tế. Muốn đánh giá account enumeration phải test HTTP/filter chain và kho tài khoản thật.

### 10.4. Vì sao ví dụ không kiểm tra mật khẩu?

`AuthenticationSuccessHandler` được thiết kế để chạy **sau xác thực**. Nếu demo gọi `AuthenticationManager`, ta đang học một khối khác. Ở production, handler **không được xem việc nhận một object `Authentication` bất kỳ từ client là xác thực thành công**; object đó phải được framework/provider cấp trong trusted flow.

Không có session cookie hoặc JWT nào được demo tạo ra. Muốn giữ login sang request sau cần Spring Security filter/repository/session strategy được cấu hình đúng.

## 11. Cấu hình Spring Boot Servlet: form login redirect

Mẫu điển hình nhất là không cần class custom:

~~~java
// Các import của ứng dụng Spring Security Servlet:
// @Bean, HttpSecurity, SecurityFilterChain;
// UserDetailsService/AuthenticationProvider được cấu hình riêng.
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .defaultSuccessUrl("/dashboard", false)
            .failureUrl("/login?error")
            .permitAll());

    return http.build();
}
~~~

**Đây là snippet tích hợp**, không tự biên dịch/chạy độc lập: ứng dụng cần bean users/password encoder hoặc provider, trang `GET /login` để render form và dependencies Spring Security/Servlet.

**Điểm cần test:**

- `GET /login` hiển thị form; có CSRF token phù hợp.
- `POST /login` thật sự được filter match, tham số mặc định `username` và `password` đúng.
- Sai credential tới `/login?error` với thông điệp chung.
- Đúng credential tới saved request nếu tồn tại, hoặc `/dashboard`.
- Session ID/CSRF/session fixation được xử lý bởi cơ chế framework.
- URL `/dashboard` chỉ là điều hướng, không cấp role; endpoint vẫn có authorization riêng.

### Form Login DSL và handler

~~~java
// Một lựa chọn khác: đăng ký handler tùy biến.
http.formLogin(form -> form
        .loginPage("/login")
        .successHandler(customSuccessHandler)
        .failureHandler(customFailureHandler));
~~~

`successHandler(...)`/`failureHandler(...)` gắn handler vào **filter login được DSL cấu hình**, không phải tất cả SecurityFilterChain khác hoặc mọi cơ chế auth của toàn ứng dụng.

## 12. Cấu hình cho frontend AJAX: JSON response nhưng vẫn form-encoded request

Nếu frontend gửi request dạng form-encoded và muốn tự quản lý UI sau login, có thể dùng các handler trả JSON giống demo:

~~~java
// MÃ PHÁC THẢO bên trong Spring Boot Servlet app.
// successHandler và failureHandler là các bean do ứng dụng định nghĩa.
@Bean
SecurityFilterChain ajaxLoginChain(
        HttpSecurity http,
        AuthenticationSuccessHandler successHandler,
        AuthenticationFailureHandler failureHandler) throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .loginProcessingUrl("/login")
            .successHandler(successHandler)
            .failureHandler(failureHandler));

    return http.build();
}
~~~

**Cảnh báo quan trọng:** `UsernamePasswordAuthenticationFilter` mặc định trích username/password từ **Servlet request parameters**, thường là `application/x-www-form-urlencoded`. Thay `successHandler`/`failureHandler` **không biến `POST /login` thành endpoint đọc JSON request body**.

Nếu frontend gửi:

~~~json
{
  "username": "linh",
  "password": "a-secret-value"
}
~~~

mà filter vẫn đọc `request.getParameter("username")`, request có thể không được xử lý đúng theo kỳ vọng. Muốn JSON login, phải có cơ chế filter/controller phù hợp để parse JSON, tạo unauthenticated token, authenticate qua manager, quản lý context, session strategy, CSRF, success/failure hooks. **Không chỉ đổi Content-Type của response.**

Với browser giữ session bằng cookie, fetch/AJAX phải dùng chế độ gửi cookie phù hợp, xử lý CSRF token và CORS chính xác. Tránh vô hiệu CSRF bừa bãi chỉ để request login chạy được.

## 13. Custom SuccessHandler với logic điều hướng theo quyền

Có thể muốn người dùng được đưa tới giao diện khác theo nhóm quyền. Một mẫu tối thiểu:

~~~java
// MÃ MINH HỌA trong ứng dụng Servlet, không standalone.
AuthenticationSuccessHandler handler = (request, response, auth) -> {
    boolean admin = auth.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    String target = admin ? "/admin" : "/dashboard";

    response.sendRedirect(
            request.getContextPath() + target);
};
~~~

Đây là logic **chọn trang**, không phải authorization. Hãy tiếp tục bảo vệ endpoint `/admin` bằng Spring Security server-side. Nếu muốn giữ saved request, cân nhắc kế thừa/delegate `SavedRequestAwareAuthenticationSuccessHandler` hoặc để config mặc định xử lý thay vì cứng nhắc chuyển mọi user tới dashboard.

**An toàn redirect:**

- Chỉ sử dụng local paths/allowlist; không phản chiếu một `next` URL bất kỳ.
- Tránh redirect tới `javascript:`, scheme/protocol-relative URL, host bên ngoài, path traversal và URL đã bị decode nhiều lớp.
- Nếu cần external redirect như OAuth2, dùng protocol-specific flows được framework hỗ trợ, kiểm tra `state`, redirect URI và nguồn tin cậy.
- Không đưa access token/raw password vào query string của redirect.
- Dùng response commit đúng một lần; không vừa `sendRedirect` vừa `write JSON` sau đó.

Nếu có impersonation/switch-user, lưu actor thực và audit theo chính sách, không chỉ dựa vào `ROLE_ADMIN` trong client.

## 14. Custom FailureHandler với error chung và audit riêng

Ví dụ production-style cho form/AJAX login:

~~~java
// MÃ MINH HỌA trong Spring application context; không standalone.
AuthenticationFailureHandler handler = (request, response, ex) -> {
    // Gửi audit nội bộ: loại lỗi đã chuẩn hóa, request/correlation ID.
    // Không log ex.getMessage() nếu có thể chứa dữ liệu nhạy cảm.
    // Không đặt chi tiết reason vào response.

    response.setStatus(401);
    response.setCharacterEncoding("UTF-8");
    response.setContentType("application/json");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write(
            "{\"code\":\"AUTHENTICATION_FAILED\","
          + "\"message\":\"Đăng nhập không thành công.\"}");
};
~~~

**Vì sao không chia chi tiết ở public response?** Một attacker có thể dùng khác biệt để dò danh sách tài khoản:

~~~text
Sai username      -> 404 UNKNOWN_USER
Sai password      -> 401 WRONG_PASSWORD
Account locked    -> 423 LOCKED
Account disabled  -> 403 DISABLED
~~~

Kể cả nội dung câu chữ được chuẩn hóa, HTTP status, response length, redirect query, headers, thời gian trả về và rate-limit behavior vẫn có thể tiết lộ trạng thái.

**Thiết kế tốt hơn:** phản hồi chung cho nhóm xác thực thất bại công khai; internal telemetry phân biệt `BAD_CREDENTIALS`, `LOCKED`, `DISABLED` và sự cố hạ tầng theo quyền truy cập phù hợp. Với người đã xác minh ownership qua kênh mạnh hơn, có thể đưa hướng dẫn mở khóa/reset cụ thể trong một flow khác.

### Một cảnh báo về default failure handler

Javadoc `SimpleUrlAuthenticationFailureHandler` ghi rõ khi **không có failure URL**, handler có thể gửi `401` kèm message bắt nguồn từ `AuthenticationException`. Không phụ thuộc vào behavior đó như chiến lược chống account enumeration; cấu hình generic redirect hoặc custom handler đã rà soát bảo mật.

## 15. AuthenticationFailureHandler khác AuthenticationEntryPoint và AccessDeniedHandler

Một request chưa xác thực truy cập `GET /admin` không giống một request đã thử password sai tại `POST /login`:

| Tình huống | Điểm xử lý phù hợp | Kết quả điển hình |
| --- | --- | --- |
| Chưa login, truy cập tài nguyên protected | `AuthenticationEntryPoint` do `ExceptionTranslationFilter` kích hoạt | Redirect login hoặc 401 challenge |
| Gửi form login, password sai | `AuthenticationFailureHandler` của authentication filter | Redirect `/login?error` hoặc 401 chung |
| Đã login, thiếu quyền đọc `/admin` | `AccessDeniedHandler` qua authorization/ExceptionTranslationFilter | 403 Forbidden |
| Login thành công | `AuthenticationSuccessHandler` | Redirect target/saved request hoặc JSON |
| Logout thành công | `LogoutSuccessHandler` | Redirect hoặc HTTP status cho logout |

**Không giải quyết lỗi authorization bằng cách giả lập login failure**. Ví dụ user đã xác thực nhưng thiếu `ROLE_ADMIN` nên nhận 403, không nên chuyển sang “mật khẩu sai” hoặc xóa authentication vô lý.

**Không có handler chung tự động cho toàn bộ resource server.** Bearer token chưa hợp lệ thường dùng `AuthenticationEntryPoint`/OAuth2 error response phù hợp; thiếu scope/authority có thể đi qua `AccessDeniedHandler`. Đừng lấy `formLogin.failureHandler` làm bằng chứng đã xử lý mọi 401 của API.

## 16. Filter chain, RequestMatcher và handler bị bỏ qua

Một lỗi rất thường gặp: đã khai báo bean handler và gắn vào `formLogin` nhưng khi gửi JSON login hoặc gọi endpoint khác, handler không được gọi.

Những nguyên nhân cần kiểm tra:

1. Request **không khớp filter**: `loginProcessingUrl`, HTTP method hoặc `securityMatcher`.
2. Request bị chặn **trước filter login**: CSRF thiếu, CORS preflight, request size/malformed body, filter custom khác.
3. Request được chain khác xử lý do nhiều `SecurityFilterChain` có `@Order`/matcher khác.
4. Cơ chế auth thực tế là HTTP Basic, bearer, oauth2Login hoặc một custom filter chưa đăng ký handler.
5. Lỗi không phải `AuthenticationException` trong `attemptAuthentication(...)`.
6. Endpoint là controller tự gọi `AuthenticationManager` chứ không đi qua `UsernamePasswordAuthenticationFilter`.
7. Một handler khác được cấu hình sau và ghi đè mục tiêu trên cùng filter/configurer.

**Mẹo:** kiểm thử bằng request thực qua Spring Security filter chain. Đừng chỉ unit-test `handler.onAuthenticationSuccess(...)` rồi kết luận login endpoint đã dùng nó.

### Ví dụ nhiều chains (minh họa)

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .formLogin(form -> form
            .successHandler(webSuccess)
            .failureHandler(webFailure));
    return http.build();
}
~~~

Đây là **mã tích hợp không độc lập**, yêu cầu imports, beans `webSuccess`/`webFailure` và cấu hình JWT decoder/issuer cùng dependencies phù hợp. Nó minh họa việc handler web **không quyết định response của `/api/**`**.

## 17. SecurityContextRepository, session fixation và response commit

Handler success chạy ở **cuối nỗ lực xác thực**, nhưng hiệu lực đăng nhập qua request kế tiếp phụ thuộc **context persistence**:

- `SecurityContextHolder` giữ context cho thread/request hiện tại.
- `SecurityContextRepository` định nghĩa cách lưu/tải context, có thể dùng `HttpSession`, request attribute hoặc null.
- Spring Security 6 dùng `SecurityContextHolderFilter`/explicit save trong cấu hình hiện đại.
- `AbstractAuthenticationProcessingFilter` khi được cấu hình đầy đủ có thể chủ động lưu context trong luồng success trước khi gọi handler.
- Custom login controller/filter không cấu hình đúng repository thì success handler trả 200 cũng **không đồng nghĩa browser đã đăng nhập ở request sau**.

Nếu tự gọi `AuthenticationManager.authenticate(...)` trong controller:

~~~java
// MÃ PHÁC THẢO custom login, không standalone.
// Cần xử lý đủ SessionAuthenticationStrategy, CSRF,
// success/failure handling và response lifecycle.

Authentication verified =
        authenticationManager.authenticate(unauthenticatedToken);

sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(verified);
securityContextHolderStrategy.setContext(context);

securityContextRepository.saveContext(context, request, response);

// Chỉ sau khi save mới hoàn tất redirect/JSON.
successHandler.onAuthenticationSuccess(
        request, response, verified);
~~~

**Không dùng code này như lời khuyên thay formLogin chuẩn**: framework còn xử lý session fixation, remember-me, exception mapping, event, concurrent session controls, request cache và các bước khác. Khi bắt buộc tự viết filter, hãy cấu hình chúng một cách có chủ đích.

**Save trước response commit**: `response.sendRedirect(...)` hoặc ghi body lớn có thể commit response trước lúc session cookie được thiết lập. Handler nên là điểm cuối cùng của luồng HTTP, không đợi handler redirect xong rồi mới persist context.

## 18. Điều hướng sau login và nguy cơ open redirect

Các tham số như:

~~~text
/login?next=https://attacker.example/
POST /login (targetUrlParameter=http://outside.example/)
~~~

không được mặc nhiên tin cậy. Một handler sử dụng `response.sendRedirect(request.getParameter("next"))` có thể biến domain hợp pháp thành điểm trung chuyển phishing.

### Chính sách target an toàn

- Ưu tiên URL nội bộ cố định như `/dashboard`.
- Nếu cần giữ URL gốc, dùng `RequestCache`/`SavedRequestAwareAuthenticationSuccessHandler` theo policy đã kiểm soát, thay vì tự lưu `next` chưa xác minh.
- Nếu cho phép tham số redirect, áp **allowlist thật** cho scheme/host/path; tốt hơn chỉ chấp nhận đường dẫn context-relative đã normalize.
- Không tin `Referer` làm bằng chứng quyền; nó có thể thiếu hoặc bị giả mạo.
- Không cho redirect vào endpoints thực hiện state-changing action chỉ bằng GET.
- Khi redirect có chứa tenant ID hoặc state, kiểm tra tenant membership/authorization từ server.
- Không đưa token, password, email nhạy cảm vào query string; URL dễ đi vào browser history, logs và Referer.

Ngay cả redirect hợp lệ cũng **không cấp quyền**. Tài nguyên đích phải tự áp policy server-side.

## 19. Failure handler không nên trở thành nơi quản lý brute force một cách tùy tiện

`AuthenticationFailureHandler` có thể phát audit event, cập nhật counter hoặc kích hoạt cảnh báo. Nhưng nếu tất cả việc chống brute-force chỉ nằm trong handler sau khi provider đã kiểm tra password, attacker có thể tiêu thụ tài nguyên BCrypt trước khi bị throttled.

Một thiết kế có nhiều lớp:

~~~text
Request /login
    |
    +--> Reverse proxy / WAF / IP + device throttling
    |
    +--> Application rate limit / risk check
    |
    +--> AuthenticationManager, PasswordEncoder
    |
    +--> Success/Failure handlers
                 |
                 +--> Audit event, metrics
                 +--> Public generic response
~~~

Cân nhắc:

- Rate limit theo IP/thiết bị/tài khoản đã chuẩn hóa và các tín hiệu rủi ro; không chỉ một IP nếu có NAT.
- Tránh counter hoặc `429` trở thành oracle chỉ kích hoạt với username tồn tại.
- Lockout không nên cho phép attacker khóa vĩnh viễn tài khoản người khác chỉ bằng nhiều lần thử sai.
- Dùng các kênh khôi phục có xác minh, không tiết lộ account status khi chưa được chứng minh quyền sở hữu.
- Event auditing nên idempotent/retry được nếu qua queue; không block login vô thời hạn bởi hệ thống log.
- Password hashing CPU-intensive cần capacity planning; không “cố tình sleep” làm hệ thống dễ DoS.

**Handler chỉ là nơi phản hồi sau thất bại**, không phải lớp phòng chống automation duy nhất.

## 20. Response một lần và tác dụng phụ trong handler

Một handler có thể gửi:

~~~java
response.sendRedirect("/dashboard");
~~~

hoặc:

~~~java
response.setStatus(200);
response.getWriter().write("{\"code\":\"LOGIN_OK\"}");
~~~

**Không làm cả hai cho cùng một response.** Sau `sendRedirect`/`sendError` hoặc khi response đã committed, việc ghi thêm body, đổi status, set cookie hoặc save context có thể gây `IllegalStateException` hoặc bị bỏ qua.

### Việc nên tránh trong success handler

- Gọi service bên ngoài chậm rồi mới trả browser.
- Ghi dữ liệu nghiệp vụ quan trọng **sau** khi redirect đã gửi.
- Gán `ROLE_ADMIN` chỉ vì trang đích là `/admin`.
- Log toàn bộ `Authentication`/password/hash.
- Gửi access/refresh token trong URL.
- Dùng mutable singleton field trong handler để giữ current user giữa requests.
- Ghi response rồi vẫn gọi filter chain ở một nhánh không được thiết kế.

### Việc nên tránh trong failure handler

- `ex.printStackTrace()` ra stdout/HTTP hoặc đưa `ex.getMessage()` vào JSON.
- Redirect khác nhau cho unknown, locked, disabled nếu tạo account enumeration.
- Ghi raw submitted password hoặc thông tin định danh nhạy cảm vào log.
- Tự set trusted `SecurityContext` sau khi authentication thất bại.
- Gửi thêm email/SMS trên mọi nỗ lực sai không rate limit.
- Che mọi lỗi infrastructure bằng 401 khiến đội vận hành không biết hệ thống đã hỏng.

**Lưu ý thêm:** Trong ứng dụng có phản hồi JSON, dùng `ObjectMapper` hoặc message converter khi có dữ liệu động thay vì ghép chuỗi từ input client. JSON constant trong demo chỉ là ví dụ tối giản; không nội suy trực tiếp username hoặc exception vào chuỗi.

## 21. Tách Servlet và WebFlux

Hai interface đang học là cho **Servlet stack**:

~~~text
AuthenticationSuccessHandler  (jakarta.servlet.http.HttpServletRequest,...)
AuthenticationFailureHandler  (jakarta.servlet.http.HttpServletRequest,...)
~~~

Trong **WebFlux**, dùng các interface reactive như `ServerAuthenticationSuccessHandler`/`ServerAuthenticationFailureHandler` với `WebFilterExchange`/`ServerWebExchange` và `Mono<Void>`, cùng `ServerSecurityContextRepository`. Không copy handler Servlet hoặc `ThreadLocal` pattern vào WebFlux.

Tương tự, nếu ứng dụng đăng nhập bằng OAuth2/OIDC:

- OAuth2 login Servlet có thể có success/failure handlers trên filter thích hợp.
- OIDC có thêm validation nonce/state, callback và session/client authorization flow; không tự triển khai logic redirect protocol từ đầu.
- Resource server bearer không mặc nhiên gọi cùng form login handler trên mỗi request.
- Logout dùng `LogoutSuccessHandler` khác với login success handler.

## 22. Kiểm thử chức năng đúng ranh giới

### 22.1. Unit test handler

Với `MockHttpServletRequest`/`MockHttpServletResponse`:

- Success handler nhận trusted Authentication, trả đúng status/Location/Content-Type/body.
- Failure handler gặp BadCredentials/Locked/Disabled đều trả phản hồi công khai chung theo policy.
- Không lộ exception message, username existence, password hash, authorities nhạy cảm hoặc stack trace.
- Response không cache dữ liệu nhạy cảm; không chứa URL ngoài allowlist.
- Không gửi redirect và JSON đồng thời.
- Việc gọi handler nhiều request không làm lẫn state vì singleton bean có mutable field.

### 22.2. Integration test filter chain

**Đây mới là bài kiểm tra end-to-end quan trọng.** Test các HTTP requests qua `SecurityFilterChain` với `MockMvc`/Spring Security Test:

~~~java
// PSEUDO-TEST: cần Spring Boot Test + spring-security-test,
// users giả lập, SecurityFilterChain thực và setup CSRF tương ứng.
// Không phải JUnit class standalone.

mvc.perform(formLogin().user("linh").password("correct"))
    .andExpect(authenticated());

mvc.perform(formLogin().user("linh").password("incorrect"))
    .andExpect(unauthenticated());

// Nếu custom failure handler trả JSON:
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "linh")
        .param("password", "incorrect"))
    .andExpect(status().isUnauthorized())
    .andExpect(content().json(
        "{\"code\":\"AUTHENTICATION_FAILED\"}"));
~~~

Test phải tương thích với handler đang cấu hình: nếu đang dùng `failureUrl` 302, không dùng assertion 401 cho cùng endpoint. Nếu custom login nhận JSON body, cần gửi JSON và chứng minh đúng filter/controller parse được.

### 22.3. Ma trận tích hợp đầy đủ

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Credential đúng | Success handler chạy **một lần**; context/session đúng ở request kế tiếp nếu stateful |
| Credential sai | Failure handler, status/body/redirect đúng, không có authenticated session |
| Unknown username | Public response không tiết lộ account existence |
| Locked/disabled/expired | Không cấp login; public contract phù hợp, audit internal phân biệt |
| Saved URL có trước login | SavedRequestAware đưa user về URL hợp lệ theo policy |
| Không có saved URL | Dùng default target chính xác |
| `alwaysUseDefaultTargetUrl=true` | Không phục hồi saved URL trái cấu hình |
| `targetUrlParameter`/`next` độc hại | Không open redirect tới domain ngoài |
| Redirect sau login | Session cookie được set đúng và request tiếp theo authenticated |
| CSRF token thiếu | Có thể bị từ chối trước form filter theo CSRF policy; handler không nhất thiết chạy |
| API stateless | Không cấp session dựa vào form flow và không gọi web handler ngoài dự kiến |
| AuthenticationManager lỗi backend | Không lộ stack trace, xử lý lỗi vận hành tách biệt |
| Concurrent login | Không rò context/principal qua requests |
| Multiple chains | Endpoint thật khớp chain/handler đúng |
| Session fixation | Session ID được bảo vệ theo strategy của framework |
| Logout | Logout handler riêng; handler login không được dùng thay thế |
| Rate-limit | Không lộ userExists qua 429/header/thời gian |
| Audit/metrics | Không ghi password/token/full principal; correlation ID an toàn |

### 22.4. Vì sao test handler trực tiếp chưa đủ?

Demo Java gọi `onAuthenticationSuccess`/`onAuthenticationFailure` thẳng trên mock response. Nó **không** kiểm tra rằng `UsernamePasswordAuthenticationFilter` của ứng dụng đã đăng ký đúng instance, không kiểm tra CSRF, `SecurityContextRepository` hoặc session cookie.

Một thành phần có thể unit-test PASS trong khi HTTP endpoint thực tế vẫn dùng handler mặc định. Vì vậy phải thử request qua chain và kiểm tra **cả request kế tiếp** sau login.

## 23. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| Login đúng nhưng luôn về `/` | Default success target; chưa có saved request hoặc handler khác | Kiểm tra SavedRequestAware và `defaultSuccessUrl` |
| Login về dashboard, không quay lại URL gốc | `alwaysUseDefaultTargetUrl=true` hoặc custom success không dùng RequestCache | Dùng `false`/SavedRequestAware đúng mục đích |
| Login sai hiển thị lỗi backend chi tiết | Render `exception.getMessage()` hoặc default 401 chưa chuẩn hóa | Generic failure response + audit riêng |
| Login API nhận JSON mà formLogin không thấy username | UsernamePasswordAuthenticationFilter đọc request parameters | Dùng form-urlencoded hoặc custom JSON auth flow hoàn chỉnh |
| Đã tạo handler bean nhưng không chạy | Chưa gắn vào `formLogin`/filter hoặc sai chain/matcher | Kiểm tra `SecurityFilterChain`, URL, method |
| Thiếu CSRF token nên failure handler không chạy | Request bị `CsrfFilter` chặn trước authentication | Cấp/kiểm tra CSRF đúng policy |
| Login 200 nhưng request sau 401 | Custom controller chưa save `SecurityContext`/session | Explicit save đúng repository và session strategy |
| `sendRedirect` rồi set JSON status | Response đã commit | Chọn đúng một loại response |
| `/login?next=https://...` dẫn đến external site | Open redirect | Chỉ local URL/allowlist đã normalize |
| User đã login nhưng thiếu quyền bị trả về login failure | Nhầm `AccessDeniedHandler` với auth failure | Authorization 403 theo policy |
| Endpoint API bearer không gọi handler web | Resource server có filter/entry point khác | Gắn policy tại đúng authentication mechanism |
| Login failure lưu exception trong session | `SimpleUrlAuthenticationFailureHandler` lưu để view render | Dùng generic view, điều chỉnh session policy khi cần |
| Handler thông báo tài khoản đang bị khóa | Public response rò account status | Same status/body/headers cho nhóm lỗi nhạy cảm |
| Session fixation do custom login | Bỏ qua `SessionAuthenticationStrategy` | Tích hợp strategy/framework login chuẩn |
| Hai người dùng bị lẫn redirect state | Singleton handler có mutable per-user field | Handler stateless; lấy dữ liệu từ request/auth |
| Login success chậm vì gọi API ngoài | Blocking I/O trong handler | Queue audit/notification hoặc xử lý async an toàn |
| Đổi handler mà remember-me vẫn không đúng | Auth flow/config/filter khác, remember-me hooks độc lập | Kiểm tra toàn bộ lifecycle |
| Test pass nhưng production lỗi | Chỉ unit-test handler, không qua chain/cookie/redirect | MockMvc + integration thực |

## 24. Checklist cho production

1. **Chọn cơ chế login:** browser form/session, AJAX form-encoded, JSON custom, SSO hay bearer; không mặc định tất cả dùng một handler.
2. **Xác định filter đúng:** `UsernamePasswordAuthenticationFilter`, OAuth2 filter hoặc custom filter, URL/method/chain matcher.
3. **Giữ provider làm authentication:** handler không tự xác minh raw password và không tự cấp quyền.
4. **Chọn response contract:** redirect/forward hoặc JSON, không kết hợp lẫn.
5. **Success target:** dùng SavedRequestAware nếu cần URL gốc, default target khi không có; bảo vệ chống open redirect.
6. **Failure public:** cùng response cho unknown/bad/locked/disabled theo threat model; không trả exception message.
7. **Nội bộ có audit:** lý do nguyên nhân và request ID tối thiểu, không lưu credential hoặc token.
8. **Session persistence:** custom login lưu `SecurityContext` đúng `SecurityContextRepository` trước response commit nếu stateful.
9. **Session fixation:** sử dụng `SessionAuthenticationStrategy` và session/cookie settings phù hợp.
10. **CSRF/CORS:** browser cookie-auth phải có CSRF protection; xử lý CORS và same-site đúng.
11. **Rate limiting:** giới hạn trước/ngoài PasswordEncoder phù hợp; tránh account enumeration qua 429/headers.
12. **Không re-auth trong handler:** sử dụng trusted authentication result đã có.
13. **Không giữ mutable per-user state trong bean:** Spring beans thường singleton, handler phải an toàn concurrent.
14. **Không block response bằng external I/O:** audit/notifications cần timeout, retry và queue nếu phù hợp.
15. **Logout là flow riêng:** `LogoutSuccessHandler` và session/token cleanup đúng.
16. **Multiple chains:** test xác thực và response cho từng matcher, không nhầm WebFlux với Servlet.
17. **Filter integration tests:** kiểm tra redirect/JSON, session cookie và request tiếp theo, không chỉ method handler.
18. **Security regression:** brute-force, account enumeration, open redirect, response leaks, CSRF và error paths.

## 25. Câu hỏi tự kiểm tra

**1.** `AuthenticationSuccessHandler` có chức năng kiểm tra password đúng hay sai không?  
**Đáp:** Không. Việc đó thuộc `AuthenticationManager`/`AuthenticationProvider`. Handler xử lý HTTP response sau khi thành công.

**2.** Khi dùng form login, user muốn quay lại `/orders/42` đã bị redirect về login. Nên dùng handler nào?  
**Đáp:** `SavedRequestAwareAuthenticationSuccessHandler` phối hợp `RequestCache`, hoặc để mặc định `formLogin` khi không cần tùy biến.

**3.** `defaultSuccessUrl("/dashboard", true)` khác gì `false`?  
**Đáp:** `true` luôn dùng dashboard; `false` giữ khả năng ưu tiên saved request khi có theo chính sách của success handler.

**4.** Một failure handler trả HTTP 423 khi locked, HTTP 401 khi password sai. Rủi ro?  
**Đáp:** Kẻ tấn công có thể dò tài khoản/trạng thái khóa qua status. Cần generic public response theo threat model.

**5.** Chỉ đặt bean `AuthenticationFailureHandler` là mọi nỗ lực login của app đều dùng nó?  
**Đáp:** Không. Phải gắn vào đúng filter/configurer/`SecurityFilterChain`; các auth mechanisms khác có entry point/failure logic riêng.

**6.** Tại sao success handler trả 200 JSON mà request sau vẫn 401?  
**Đáp:** Custom flow có thể chưa lưu context/session, cookie không được thiết lập hoặc request đi sai chain; handler không tự đảm bảo persistence.

**7.** Thay success/failure handler có làm UsernamePasswordAuthenticationFilter đọc JSON body không?  
**Đáp:** Không. Mặc định filter đọc servlet parameters; muốn login bằng JSON cần một cơ chế parse/authentication phù hợp.

**8.** Cách phân biệt `AuthenticationEntryPoint` với `AuthenticationFailureHandler`?  
**Đáp:** Entry point bắt đầu challenge/login khi truy cập resource mà chưa authenticated; failure handler xử lý nỗ lực authentication đã bị từ chối.

**9.** `AccessDeniedHandler` khác gì `AuthenticationFailureHandler`?  
**Đáp:** AccessDeniedHandler xử lý authorization không đủ (thường 403) khi đã authenticated; failure handler xử lý login/auth attempt thất bại.

**10.** Có được redirect thẳng tới query `next` của client?  
**Đáp:** Không. Phải validate/allowlist để tránh open redirect và rò token/secret.

**11.** Vì sao không dùng `exception.getMessage()` làm response login?  
**Đáp:** Message có thể lộ locked, disabled, unknown username, thông tin hạ tầng hoặc account state.

**12.** Muốn trả JSON cho frontend AJAX nhưng vẫn dùng formLogin, request gửi kiểu gì?  
**Đáp:** Mặc định username/password dưới dạng form parameters (thường form-urlencoded) và CSRF/cookies phù hợp; JSON body cần filter khác.

**13.** AuthenticationSuccessHandler có overload nhận `FilterChain` không?  
**Đáp:** Có, interface Servlet Spring Security 6.5 có một default overload bốn tham số; không phải mọi login filter nhất thiết dùng overload này.

**14.** Vì sao `SimpleUrlAuthenticationFailureHandler` có thể tạo session trong một request login sai?  
**Đáp:** Nó có thể lưu exception vào session để view dùng khi redirect, nếu được cấu hình cho phép tạo session.

**15.** Handler success/failure được kiểm chứng xong bằng unit-test, đã đủ production chưa?  
**Đáp:** Chưa. Cần test đúng filter chain, URL/method, redirects, session, CSRF, saved request, audit và security regressions.

## 26. Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): filter login, success/failure flow và cấu hình form.
- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, session strategy và kết quả xác thực.
- [AuthenticationSuccessHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationSuccessHandler.html): các overload của `onAuthenticationSuccess`.
- [AuthenticationFailureHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): `onAuthenticationFailure`.
- [AbstractAuthenticationProcessingFilter API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): `attemptAuthentication`, `successfulAuthentication`, `unsuccessfulAuthentication`, hooks, repository và filter lifecycle.
- [SavedRequestAwareAuthenticationSuccessHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): thứ tự chọn target URL.
- [SimpleUrlAuthenticationSuccessHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationSuccessHandler.html): target URL và session failure attributes cleanup.
- [SimpleUrlAuthenticationFailureHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html): default failure URL, 401 và lưu exception.
- [DelegatingAuthenticationFailureHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationFailureHandler.html): chọn handler theo exception type.
- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): lưu context cho custom authentication.
- [OWASP Authentication Cheat Sheet – Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages): chống account enumeration qua error responses, timing và flow.
- [OWASP Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): allowlist redirect targets.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session security, fixation và logout lifecycle.

**Ghi nhớ:** `AuthenticationSuccessHandler` trả lời **“đã đăng nhập thành công thì client đi đâu/nhận gì?”**; `AuthenticationFailureHandler` trả lời **“xác thực thất bại thì client nhận phản hồi an toàn nào?”**. Chúng đứng **sau quyết định của AuthenticationManager/provider**, không thay thế việc xác minh credential. Với form login ưu tiên cấu hình `defaultSuccessUrl`, `failureUrl` và `SavedRequestAwareAuthenticationSuccessHandler`; với AJAX trả JSON theo contract, còn session/CSRF/filter cần cấu hình đầy đủ. Khi tự tùy biến, tuyệt đối không lộ account state qua lỗi hoặc cho redirect tới URL không đáng tin.
