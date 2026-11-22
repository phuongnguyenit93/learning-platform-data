# defaultSuccessUrl và xử lý chuyển hướng thành công

## 1. Bài toán chuyển hướng sau đăng nhập biểu mẫu

Khi người dùng gửi `POST /login`, Spring Security có hai việc tách biệt: **xác thực danh tính** và **quyết định trang sẽ mở sau khi xác thực thành công**. `AuthenticationManager`/`AuthenticationProvider` chịu trách nhiệm kiểm tra username, password và trạng thái tài khoản; còn `AuthenticationSuccessHandler` quyết định HTTP response tiếp theo, thông thường là redirect tới một URL.

`defaultSuccessUrl(...)` nằm trong cấu hình `formLogin(...)` và chỉ thiết lập **đích chuyển hướng khi đăng nhập thành công**. Nó không tạo tài khoản, không kiểm tra password, không tự cấp `ROLE_ADMIN` và không thay cho authorization tại trang đích.

Hãy phân biệt hai trường hợp:

- **Đăng nhập trực tiếp:** người dùng chủ động vào `/login` từ thanh điều hướng, gửi form đúng và muốn vào trang chính `/dashboard`.
- **Đăng nhập sau khi bị chặn:** người dùng cố xem `/orders/42` trong trạng thái anonymous, Spring Security mời họ đăng nhập, sau đó họ muốn quay lại đúng `/orders/42`.

Nếu cả hai trường hợp đều bị ép về dashboard, trải nghiệm của trường hợp thứ hai bị gián đoạn. Nếu luôn quay về URL cũ, một số sản phẩm lại không thể thực thi bước onboarding/đồng ý điều khoản bắt buộc. **`defaultSuccessUrl` có hai overload để giúp chọn chính sách.**

### Mục tiêu học tập

Sau bài này bạn phải phân biệt được:

1. `defaultSuccessUrl("/dashboard")` và `defaultSuccessUrl("/dashboard", true)`.
2. `defaultTargetUrl`, `alwaysUseDefaultTargetUrl`, `SavedRequest`, `RequestCache` và `AuthenticationSuccessHandler`.
3. Đường chuyển hướng thành công so với `loginPage`, `loginProcessingUrl`, `failureUrl` và logout.
4. Luồng Browser → URL protected → login → redirect URL cũ, và lý do một số lần đăng nhập về dashboard.
5. Nguy cơ **open redirect** khi dùng `next`/`returnUrl`/`Referer` không được kiểm tra.
6. Cách viết cấu hình Spring Security 6.5.x, ví dụ Java 17+ chạy được, dự đoán stdout, và chiến lược kiểm thử integration thật.

Bài học tập trung vào **Đăng nhập biểu mẫu** trong module **Spring Security - authentication**, không biến điều hướng thành cơ chế xác thực hay phân quyền mới.

## 2. Ý nghĩa chính xác của hai overload

Cấu hình thường gặp:

```java
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard"));
```

Tương đương về chính sách với:

```java
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", false));
```

Nếu một request bị chặn đã được lưu trong `RequestCache`, handler mặc định thường **ưu tiên URL của request ấy**. Chỉ khi không có saved request được ưu tiên mới chuyển về `/dashboard`.

Ngược lại:

```java
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", true));
```

`true` có nghĩa là **luôn dùng `/dashboard` sau thành công**, ngay cả khi session đang giữ một request cũ. Handler `SavedRequestAwareAuthenticationSuccessHandler` cũng loại bỏ saved request liên quan khi dùng nhánh bắt buộc này.

| Tùy chọn | Có saved request `/reports/annual` | Không có saved request |
| --- | --- | --- |
| `defaultSuccessUrl("/dashboard")` | Redirect `/reports/annual`. | Redirect `/dashboard`. |
| `defaultSuccessUrl("/dashboard", false)` | Redirect `/reports/annual`. | Redirect `/dashboard`. |
| `defaultSuccessUrl("/dashboard", true)` | Redirect `/dashboard` và bỏ saved request. | Redirect `/dashboard`. |

**Không hiểu `false` thành không chuyển hướng.** `false` là “không bắt buộc sử dụng default URL”; không phải “không chạy success handler”.

**Không hiểu `true` thành tự động cho phép truy cập dashboard.** Dashboard vẫn phải có controller/view và một policy authorization đúng cho những user sẽ được đưa tới đó.

### Default khi không cấu hình

Theo `AbstractAuthenticationTargetUrlRequestHandler` trong Spring Security 6.5, đích mặc định ban đầu thường là **`/`**. Với form login, handler thông dụng là `SavedRequestAwareAuthenticationSuccessHandler`: nếu có request cũ hợp lệ thì ưu tiên URL cũ, nếu không sẽ dùng logic default target. `/` là root của ứng dụng, **không phải** URL `/login`.

## 3. Vì sao có SavedRequest và RequestCache?

Xem một request tới trang bảo vệ:

```text
GET /orders/42 (người dùng chưa đăng nhập)
     |
     v
AuthorizationFilter: không đủ authentication
     |
     v
ExceptionTranslationFilter:
   - chuyển sang bắt đầu xác thực
   - có thể yêu cầu RequestCache lưu request ban đầu
     |
     v
302 Location: /login
     |
     v
GET /login -> HTML form
     |
     v
POST /login (username/password)
     |
     v
UsernamePasswordAuthenticationFilter
     |
     v
AuthenticationManager -> kết quả đã xác thực
     |
     v
SessionAuthenticationStrategy + SecurityContext
     |
     v
AuthenticationSuccessHandler
     |
     +-- có saved request và alwaysUse=false:
     |        302 Location: /orders/42
     |
     +-- không có saved request:
     |        302 Location: /dashboard
     |
     +-- alwaysUse=true:
              302 Location: /dashboard
```

`RequestCache` quản lý mô tả request đang chờ khôi phục. Triển khai phổ biến là `HttpSessionRequestCache`, lưu `DefaultSavedRequest` trong `HttpSession`. Nó không giống `SecurityContextRepository`, nơi lưu `SecurityContext`/`Authentication` để những request kế tiếp biết ai đang đăng nhập.

| Thành phần | Lưu trữ điều gì? | Tác dụng |
| --- | --- | --- |
| `SecurityContextHolder` | Authentication hiện hành theo context holder strategy | Code trong quá trình xử lý đọc danh tính. |
| `SecurityContextRepository` | SecurityContext vào request/session hoặc kho thích hợp | Khôi phục authentication qua các request theo policy. |
| `RequestCache` | Request trước khi yêu cầu authentication | Chọn URL trang cần quay lại sau login. |
| `SavedRequest` | Thông tin về request đã lưu | Cung cấp `getRedirectUrl()` và dữ liệu cần cho request matching. |
| `AuthenticationSuccessHandler` | Không phải kho dữ liệu; nhận kết quả authentication | Quyết định redirect, forward hoặc response khác. |

**Lưu ý:** không phải mọi response 401 hoặc redirect tới login đều tạo saved request. Nó còn phụ thuộc `ExceptionTranslationFilter`, request matcher, cache configuration và session. Một `NullRequestCache` không giữ request gốc.

### Những request nào nên được lưu?

Những yêu cầu **GET** tới tài nguyên protected thường là ứng viên hữu ích để phục hồi điều hướng. Việc lưu một POST có side effects không có nghĩa toàn bộ body được replay an toàn sau login; đặc biệt không thể dùng request cache làm hàng đợi chuyển tiền, tạo đơn hàng hoặc thay trạng thái nghiệp vụ. Các API như vậy cần cơ chế idempotency, CSRF, xác nhận lại thao tác và authorization riêng.

Không để các request favicon, CSS, XHR phụ hoặc endpoint health vô tình lấn át URL đích thực sự quan trọng. Có thể cấu hình `HttpSessionRequestCache.setRequestMatcher(...)` khi cần chọn request được lưu theo chính sách.

## 4. `SavedRequestAwareAuthenticationSuccessHandler` chọn URL theo thứ tự nào?

Spring Security 6.5.11 dùng handler này trong kịch bản browser form login điển hình. Nó kế thừa `SimpleUrlAuthenticationSuccessHandler` và có `RequestCache` để kiểm tra URL cần quay lại.

Các nhánh quan trọng:

1. **`alwaysUseDefaultTargetUrl=true`:** dùng `defaultTargetUrl`, bỏ saved request nếu có.
2. **`targetUrlParameter` đã được bật và request có giá trị tương ứng:** dùng parameter để quyết định đích, đồng thời bỏ saved request. Việc cho client chỉ định đích phải được xem xét bảo mật.
3. **Có saved request:** redirect đến `savedRequest.getRedirectUrl()`. Request đã lưu thường **được giữ trong cache ở bước này** để cơ chế `getMatchingRequest(...)`/wrapper tiếp tục xử lý request browser gửi sau redirect.
4. **Không có saved request:** chuyển đến logic base handler, có thể dựa vào URL mặc định, target parameter hoặc tùy chọn Referer theo cấu hình.

| `alwaysUse` | Có `targetUrlParameter` hợp lệ | Có saved request | Đích được chọn |
| --- | --- | --- | --- |
| `true` | Bất kỳ | Bất kỳ | **Default URL**, nhánh ưu tiên cao nhất. |
| `false` | Có giá trị | Có/không | Target parameter theo handler. |
| `false` | Không | Có | Saved request URL. |
| `false` | Không | Không | Default URL hoặc Referer nếu được bật. |

`targetUrlParameter` **không tự bật** khi bạn chỉ khai báo `defaultSuccessUrl`. Đây là một tùy chọn của lớp handler, và có thể tạo lỗ hổng open redirect nếu được bật mà thiếu validation.

### Saved request có luôn bị xóa khi redirect thành công?

**Không.** Khi redirect tới original saved URL, handler có thể giữ đối tượng trong cache để request tiếp theo được xử lý bằng matching wrapper. Khi buộc về default URL hoặc dùng target parameter, request cũ bị xóa. Vì vậy một unit test đòi `RequestCache` luôn rỗng ngay sau mọi login thành công có thể sai so với hợp đồng.

### API của HttpSessionRequestCache

```java
HttpSessionRequestCache cache = new HttpSessionRequestCache();

cache.saveRequest(request, response); // lưu khi policy yêu cầu

SavedRequest saved = cache.getRequest(request, response); // đọc, không xóa

cache.removeRequest(request, response); // bỏ request đang lưu

HttpServletRequest matched =
        cache.getMatchingRequest(request, response); // request wrapper hoặc null
```

Đây là **đoạn trích** cần request/response thật và imports `SavedRequest`, `HttpServletRequest`. Trong flow do Spring Security quản lý, bạn thường không cần tự gọi `saveRequest` ở controller. Nếu đang debug, có thể kiểm tra attribute `SPRING_SECURITY_SAVED_REQUEST` trong session **bằng công cụ an toàn**, không đưa nội dung URL nhạy cảm hoặc session ID vào log công khai.

## 5. SimpleUrl, SavedRequestAware và AuthenticationSuccessHandler tùy biến

| Handler | Cách chọn response | Khi dùng |
| --- | --- | --- |
| `SavedRequestAwareAuthenticationSuccessHandler` | Saved request được ưu tiên trừ khi có override phù hợp. | Form login truyền thống muốn quay lại trang trước login. |
| `SimpleUrlAuthenticationSuccessHandler` | Dựa vào default URL, `alwaysUseDefaultTargetUrl`, target parameter, tùy chọn Referer. | Điều hướng đơn giản không cần phục hồi RequestCache. |
| `ForwardAuthenticationSuccessHandler` | Forward server-side tới một đường trong ứng dụng. | Khi thực sự cần forward cùng request thay vì browser redirect. |
| Custom `AuthenticationSuccessHandler` | Code ứng dụng tự quyết định redirect/JSON/status/forward. | API login, onboarding, role-specific landing hoặc quy trình đặc thù. |

`defaultSuccessUrl(...)` là một **shortcut để cấu hình success handler**. Nếu dùng `successHandler(custom)`, không được mặc định đích từ `defaultSuccessUrl` trước đó vẫn chạy sau custom handler. Hãy chọn một contract rõ ràng cho response và kiểm thử handler thực sự được cài vào filter.

### `setUseReferer(true)`

Handler base có thể dùng HTTP `Referer` nếu không có URL ưu tiên khác và tùy chọn đã bật. Nhưng `Referer` do browser/client gửi, có thể thiếu, bị sửa, chứa URL ngoài site hoặc mang thông tin không mong muốn. **Không dùng Referer làm chứng cứ đáng tin để chọn redirect về domain bên ngoài**. Nếu không có nhu cầu đặc biệt, ưu tiên saved request/framework hoặc đích cố định.

### `setTargetUrlParameter("next")`

Một form có thể gửi `next=/inbox`. Khi cấu hình parameter, handler có thể dùng URL đó để điều hướng. Cơ chế này đòi **kiểm tra nghiêm ngặt nguồn đích**. Nếu attacker tạo link `/login?next=https://evil.example/phishing` và ứng dụng redirect sau login mà không validate, họ có thể lợi dụng **open redirect** để phishing. Đừng bật vì thấy tiện mà không có threat model.

## 6. Cấu hình form login Java trong Spring Security 6.5

### 6.1. Dùng saved request nếu có, fallback về dashboard

```java
@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/dashboard")
                .failureUrl("/login?error")
                .permitAll());

        return http.build();
    }
}
```

Đây là **trích đoạn Spring Boot/Spring Security Servlet**, chưa phải project chạy độc lập: còn cần imports, nguồn `UserDetailsService`/`AuthenticationManager`, `PasswordEncoder`, form template, MVC controller và trang dashboard. `GET /login` hiển thị form; `POST /login` được filter xử lý.

### 6.2. Luôn về dashboard

```java
.formLogin(form -> form
    .loginPage("/login")
    .defaultSuccessUrl("/dashboard", true)
    .permitAll())
```

Sử dụng khi sản phẩm bắt buộc đi qua dashboard/onboarding/đồng ý điều khoản. Không dùng để thay authorization: sau login, user vẫn có thể tự gửi request tới URL protected khác.

### 6.3. Cấu hình với login form sẵn có

```java
.formLogin(form -> form
    .defaultSuccessUrl("/dashboard"))
```

Khi không chỉ định login page custom và filter chain phù hợp, Spring Security có thể hiển thị form đăng nhập mặc định. Nếu bạn đã chỉ định `loginPage("/login")`, ứng dụng chịu trách nhiệm tạo trang GET và đảm bảo form gửi POST tới `loginProcessingUrl` với CSRF đúng.

Một mẫu HTML tĩnh minh họa:

```html
<form action="/login" method="post">
  <label for="username">Username</label>
  <input id="username" name="username" autocomplete="username">
  <label for="password">Password</label>
  <input id="password" type="password"
         name="password" autocomplete="current-password">
  <!-- Ứng dụng thật PHẢI thêm CSRF token do framework phát hành -->
  <button type="submit">Sign in</button>
</form>
```

Mẫu HTML trên **chưa chứa CSRF token nên không phải form đầy đủ để triển khai**. Với Thymeleaf được tích hợp đúng và `th:action`, Spring Security có thể hỗ trợ thêm trường token tự động; với JS/AJAX form, phải lấy và gửi token theo cấu hình thực. Không tắt CSRF toàn cục chỉ để redirect hoạt động.

### 6.4. Đổi hoàn toàn success handler

Ví dụ ứng dụng API muốn trả HTTP 204 thay vì redirect:

```java
.formLogin(form -> form
    .successHandler((request, response, authentication) -> {
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }))
```

Đoạn này không tạo redirect tự động. Client phải hiểu contract success và tự chuyển màn hình nếu cần. Tránh vừa ghi JSON/204 vừa gọi `sendRedirect` sau khi response đã commit. Custom handler cần quyết định request cache cleanup, error handling và tránh serialize `Authentication.credentials` ra response.

## 7. `loginPage`, `loginProcessingUrl`, `failureUrl` không phải URL thành công

| API | Phạm vi | Ví dụ |
| --- | --- | --- |
| `loginPage("/login")` | Trang GET để user thấy form. | Controller/view render HTML. |
| `loginProcessingUrl("/login")` | Endpoint POST nhận username/password. | `UsernamePasswordAuthenticationFilter` xử lý. |
| `defaultSuccessUrl("/dashboard")` | Đích sau xác thực thành công, với quy tắc saved request. | Redirect 3xx. |
| `failureUrl("/login?error")` | Đích khi login thất bại. | Failure handler redirect. |
| `logoutSuccessUrl("/login?logout")` | Đích sau logout nếu được cấu hình. | Logout success handler. |

Đừng tạo `@PostMapping("/login")` ở controller để xử lý credentials trong khi `UsernamePasswordAuthenticationFilter` đang sở hữu cùng URL. Nếu muốn custom JSON login, chọn một chiến lược có filter, request parsing, CSRF và persistence được thiết kế rõ.

**Sai password không đi qua `defaultSuccessUrl`**. Một `BadCredentialsException` ở form filter thường dẫn đến `AuthenticationFailureHandler`. Nếu user gặp `/login?error`, phải kiểm tra login failure (credential, account status, CSRF, filter chain) chứ không sửa default success target.

### Đích mặc định phải tồn tại và đúng quyền

Nếu app đặt `defaultSuccessUrl("/dashboard")` nhưng không có controller/trang ấy, redirect thành công rồi GET mới có thể 404. Nếu `/dashboard` chỉ cho phép `ROLE_ADMIN` mà user thường đăng nhập hợp lệ, redirect có thể dẫn đến 403. Lỗi đích/authorization khác với đăng nhập sai. Hãy chọn landing page mà mọi user đã authenticated có quyền xem hoặc xử lý role theo chính sách đáng tin cậy.

## 8. Java 17 runnable: kiểm tra handler thật mà không cần web server

Chương trình console dưới đây dùng **Spring Security Web 6.5.11**, **Spring Framework Test 6.2.12**, **Jakarta Servlet API 6.0**, Java 17+ và Gradle. Nó gọi `SavedRequestAwareAuthenticationSuccessHandler` thật với `MockHttpServletRequest`/`MockHttpServletResponse` để so sánh sáu trường hợp.

Ví dụ dùng `UsernamePasswordAuthenticationToken.authenticated(...)` chỉ để tạo một **fixture đã được xác minh giả lập** cho handler. Trong ứng dụng thật, chỉ `AuthenticationManager`/provider tin cậy mới được xác minh credentials; không bao giờ nhận username/authorities từ request rồi tự gán `authenticated=true`.

### 8.1. Cấu trúc thư mục

```text
login-success-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SuccessRedirectDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'login-success-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.SuccessRedirectDemo'
}
```

### 8.2. `src/main/java/demo/SuccessRedirectDemo.java`

```java
package demo;

import jakarta.servlet.http.HttpSession;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;

public final class SuccessRedirectDemo {

    private static Authentication trustedFixture() {
        // Chỉ dùng cho demo handler: không lấy user/role từ client.
        return UsernamePasswordAuthenticationToken.authenticated(
                "lan",
                null,
                AuthorityUtils.createAuthorityList("ROLE_READER"));
    }

    private static SavedRequestAwareAuthenticationSuccessHandler handler(
            HttpSessionRequestCache cache) {

        SavedRequestAwareAuthenticationSuccessHandler result =
                new SavedRequestAwareAuthenticationSuccessHandler();

        result.setDefaultTargetUrl("/dashboard");
        result.setRequestCache(cache);
        return result;
    }

    private static HttpSession saveOriginal(
            HttpSessionRequestCache cache) {

        MockHttpServletRequest original =
                new MockHttpServletRequest("GET", "/reports/2026");

        original.setScheme("https");
        original.setServerName("app.example.test");
        original.setServerPort(443);

        cache.saveRequest(original, new MockHttpServletResponse());
        return original.getSession(false);
    }

    private static MockHttpServletRequest loginRequest(
            HttpSession previousSession) {

        MockHttpServletRequest login =
                new MockHttpServletRequest("POST", "/login");

        if (previousSession != null) {
            login.setSession(previousSession);
        }

        return login;
    }

    public static void main(String[] args) throws Exception {
        Authentication authenticated = trustedFixture();

        // A: saved request thắng khi alwaysUse=false.
        HttpSessionRequestCache savedCache = new HttpSessionRequestCache();
        MockHttpServletRequest savedLogin =
                loginRequest(saveOriginal(savedCache));
        MockHttpServletResponse savedResponse =
                new MockHttpServletResponse();

        handler(savedCache).onAuthenticationSuccess(
                savedLogin, savedResponse, authenticated);

        String location = savedResponse.getRedirectedUrl();

        System.out.println("saved.status302="
                + (savedResponse.getStatus() == 302));
        System.out.println("saved.original="
                + (location != null
                && location.contains("/reports/2026")));
        System.out.println("saved.stillCached="
                + (savedCache.getRequest(
                        savedLogin, savedResponse) != null));

        // B: không có saved request -> dashboard.
        HttpSessionRequestCache emptyCache = new HttpSessionRequestCache();
        MockHttpServletRequest directLogin = loginRequest(null);
        MockHttpServletResponse directResponse =
                new MockHttpServletResponse();

        handler(emptyCache).onAuthenticationSuccess(
                directLogin, directResponse, authenticated);

        System.out.println("direct.dashboard="
                + directResponse.getRedirectedUrl()
                        .endsWith("/dashboard"));

        // C: alwaysUseDefaultTargetUrl=true -> dashboard và xóa cache.
        HttpSessionRequestCache forcedCache = new HttpSessionRequestCache();
        MockHttpServletRequest forcedLogin =
                loginRequest(saveOriginal(forcedCache));
        MockHttpServletResponse forcedResponse =
                new MockHttpServletResponse();

        SavedRequestAwareAuthenticationSuccessHandler forced =
                handler(forcedCache);
        forced.setAlwaysUseDefaultTargetUrl(true);
        forced.onAuthenticationSuccess(
                forcedLogin, forcedResponse, authenticated);

        System.out.println("always.dashboard="
                + forcedResponse.getRedirectedUrl()
                        .endsWith("/dashboard"));
        System.out.println("always.cacheGone="
                + (forcedCache.getRequest(
                        forcedLogin, forcedResponse) == null));

        // D: param "next" được ưu tiên nếu handler được cấu hình.
        // /inbox là route nội bộ cố định, không phải user input bất kỳ.
        HttpSessionRequestCache parameterCache =
                new HttpSessionRequestCache();
        MockHttpServletRequest parameterLogin =
                loginRequest(saveOriginal(parameterCache));
        parameterLogin.setParameter("next", "/inbox");
        MockHttpServletResponse parameterResponse =
                new MockHttpServletResponse();

        SavedRequestAwareAuthenticationSuccessHandler parameter =
                handler(parameterCache);
        parameter.setTargetUrlParameter("next");
        parameter.onAuthenticationSuccess(
                parameterLogin, parameterResponse, authenticated);

        System.out.println("parameter.inbox="
                + parameterResponse.getRedirectedUrl()
                        .endsWith("/inbox"));
        System.out.println("parameter.cacheGone="
                + (parameterCache.getRequest(
                        parameterLogin, parameterResponse) == null));

        // E: Referer chỉ minh họa API, không phải nguồn đáng tin cậy.
        HttpSessionRequestCache refererCache =
                new HttpSessionRequestCache();
        MockHttpServletRequest refererLogin = loginRequest(null);
        refererLogin.addHeader("Referer", "/from-page");
        MockHttpServletResponse refererResponse =
                new MockHttpServletResponse();

        SavedRequestAwareAuthenticationSuccessHandler referer =
                handler(refererCache);
        referer.setUseReferer(true);
        referer.onAuthenticationSuccess(
                refererLogin, refererResponse, authenticated);

        System.out.println("referer.fromPage="
                + refererResponse.getRedirectedUrl()
                        .endsWith("/from-page"));

        // F: successHandler tùy biến có thể trả HTTP 204.
        AuthenticationSuccessHandler custom =
                (request, response, auth) -> response.setStatus(204);

        MockHttpServletResponse customResponse =
                new MockHttpServletResponse();

        custom.onAuthenticationSuccess(
                loginRequest(null), customResponse, authenticated);

        System.out.println("custom.status204="
                + (customResponse.getStatus() == 204));
        System.out.println("custom.noRedirect="
                + (customResponse.getRedirectedUrl() == null));
    }
}
```

### 8.3. Chạy chương trình

Với Java 17+ và Gradle (hoặc Gradle Wrapper tương thích) trong thư mục có `build.gradle`:

```bash
gradle run --quiet
```

**Stdout từ chương trình** (bỏ qua thông báo của Gradle/log runtime) theo các API/fixture trên:

```text
saved.status302=true
saved.original=true
saved.stillCached=true
direct.dashboard=true
always.dashboard=true
always.cacheGone=true
parameter.inbox=true
parameter.cacheGone=true
referer.fromPage=true
custom.status204=true
custom.noRedirect=true
```

Demo dùng kiểm tra boolean thay vì in nguyên URL vì representation của `Location` có thể bao gồm host/scheme/context path tùy redirect strategy và Servlet environment. Tuy vậy, các nhánh được kiểm tra bằng thuộc tính ổn định: đích có URL gốc, dashboard hay inbox; cache còn hay đã xóa; status 302 hay 204.

### 8.4. Giải thích lần lượt

- **`saved.status302=true`:** success handler mặc định dùng redirect HTTP (mã 302 trong cấu hình này).
- **`saved.original=true`:** `HttpSessionRequestCache` giữ request `/reports/2026`, và `alwaysUse=false` không buộc dashboard.
- **`saved.stillCached=true`:** khi redirect tới saved URL, request còn được lưu cho matching wrapper ở request sau; đừng tự xóa trong test quá sớm.
- **`direct.dashboard=true`:** không có URL cũ, nên sử dụng `defaultTargetUrl`.
- **`always.dashboard=true` + `always.cacheGone=true`:** override bắt buộc dùng URL mặc định và bỏ request cũ.
- **`parameter.inbox=true` + `parameter.cacheGone=true`:** parameter được cấu hình thắng saved request; đây cũng là nơi phải kiểm soát open redirect.
- **`referer.fromPage=true`:** khi không có saved URL, base handler có thể dùng Referer nếu bật. API có thể làm điều này, nhưng client không cung cấp một “nguồn sự thật” tin cậy.
- **`custom.status204=true` và `custom.noRedirect=true`:** custom handler có thể chọn response khác redirect; client phải được thiết kế theo contract đó.

**Điều demo không kiểm tra:** password hashing, CSRF, filter order, session fixation, redirect do proxy thực, `SecurityContextRepository` persistence, authorization trang đích, HTTP cookie. Những điều đó cần integration tests với full filter chain.

## 9. Redirect sau login liên quan gì tới SecurityContext và session?

Một `302` khiến browser **tạo request HTTP mới** tới đích. Để GET tiếp theo được nhận diện là authenticated, cần có cơ chế lưu/ngữ cảnh đáng tin:

```text
POST /login
  |
  +--> AuthenticationManager xác minh đúng
  +--> SecurityContextHolder nhận Authentication
  +--> SecurityContextRepository lưu vào session/request theo cấu hình
  +--> success handler gửi 302 Location: /dashboard
          |
          v
GET /dashboard (request mới)
  |
  +--> browser gửi session cookie nếu phù hợp
  +--> SecurityContextRepository phục hồi Authentication
  +--> AuthorizationFilter kiểm tra quyền
  +--> controller render trang
```

Nếu custom login filter chỉ `SecurityContextHolder.setContext(...)` mà **không lưu** vào repository có persistence, browser có thể theo redirect đúng nhưng request mới thành anonymous. Trong Spring Security 6, cơ chế `SecurityContextHolderFilter` nhấn mạnh **explicit save** cho các luồng authentication tự tạo.

**Đừng đổi `defaultSuccessUrl` để chữa sự cố session.** Kiểm tra repository (thường HttpSession/Delegating cho form login), `saveContext`, cookie, session fixation, path/domain, reverse proxy và session store.

### Session fixation protection

Spring Security thường chạy `SessionAuthenticationStrategy` sau khi manager xác thực thành công; nó có thể đổi session ID nhằm chống session fixation. Custom login cơ chế riêng không được bỏ session strategy. SavedRequest, SecurityContext và session data phải được bảo toàn qua chuyển trạng thái phù hợp. Nếu session đổi hoặc mất dữ liệu sai, redirect có thể về dashboard thay vì URL gốc hoặc GET sau login bị anonymous.

### Session cookie

Các thuộc tính `Secure`, `HttpOnly`, `SameSite`, `Path`, domain và timeout của session cookie ảnh hưởng việc trình duyệt có gửi cookie vào request mới không. Nếu response redirect từ HTTPS sang HTTP hay sai host do reverse proxy, persistence có thể thất bại hoặc gây rủi ro bảo mật. Không xây URL bằng cách tin mù quáng `Host`/`X-Forwarded-*` do client tự gửi.

## 10. Tại sao không dùng `defaultSuccessUrl` làm authorization?

Một saved request có thể dẫn về `/admin`. Nếu user vừa đăng nhập thành công nhưng chỉ có `ROLE_READER`, handler vẫn có thể redirect về `/admin`. Authorization tiếp theo phải trả **403** (hoặc error policy khác phù hợp) nếu không đủ quyền.

Đây không phải một “lỗi” của saved request. **Saved request là ý định điều hướng**, không phải giấy phép truy cập. Dù handler luôn dùng `/dashboard`, user vẫn có thể tự mở `/admin`. Controller, method security, URL policy và domain authorization mới quyết định quyền.

Tương tự, trang đích `/dashboard` phải tồn tại và có role policy hợp lý. Nếu nó yêu cầu một role không được cấp cho tất cả user sau login, browser có thể redirect xong rồi lại gặp 403. Không “khắc phục” bằng cách `permitAll()` một trang chứa dữ liệu nhạy cảm chỉ để tránh lỗi UX.

## 11. Tùy biến redirect theo role hoặc onboarding

Một ứng dụng có thể có chính sách:

- User chưa đồng ý điều khoản → bắt buộc `/terms`.
- Admin → `/admin/home`.
- User thường → `/dashboard`.
- User có saved request hợp lệ và không bắt buộc onboarding → quay lại URL cũ.

`defaultSuccessUrl` cố định không mô tả hết các nhánh này. Khi cần, dùng `AuthenticationSuccessHandler` custom và lấy role/trạng thái từ **nguồn server tin cậy**.

Trích đoạn handler tối giản:

```java
AuthenticationSuccessHandler roleLanding =
        (request, response, authentication) -> {

    boolean admin = authentication.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    String target = admin ? "/admin/home" : "/dashboard";
    response.sendRedirect(request.getContextPath() + target);
};
```

**Đây không phải một success handler production hoàn chỉnh.** Nó bỏ qua saved request và giả định role đã được manager/provider thiết lập đúng. Khi chạy sau reverse proxy hoặc có context path phức tạp, phải dùng URL building đúng và kiểm thử. Nếu sản phẩm muốn khôi phục saved request ưu tiên role landing, phải đọc `RequestCache` phù hợp, xác minh route được phép và dọn cache đúng lúc.

Đừng tin field `role=admin` từ request login hoặc user profile chưa xác minh. Sau redirect, mỗi URL vẫn phải authorization.

### Cho phép một số URL đích nội bộ

Nếu thật sự cần parameter như `next`, ưu tiên một **allow-list route** thay vì raw URL bất kỳ:

```java
static boolean allowedRedirect(String path) {
    return "/dashboard".equals(path)
        || "/account".equals(path)
        || "/inbox".equals(path);
}
```

Đây là **mẫu ý tưởng giới hạn đích**, không phải thư viện validate mọi URL. Khi có path/query động, proxy và context path, cần parser/canonicalization/allow-list host/scheme/port chặt chẽ. Không dùng `startsWith("https://trusted.example")`; chuỗi `https://trusted.example.attacker.test` có thể vượt kiểm tra sai.

## 12. Open redirect: lỗ hổng phổ biến nhất khi dùng URL do client cung cấp

**Open redirect** xảy ra khi attacker kiểm soát URL mà application redirect tới, chẳng hạn:

```text
https://app.example.test/login?next=https://evil.example/phishing
```

Nếu handler copy `next` vào `Location` mà không kiểm tra, site thật có thể dẫn người dùng sang site phishing ngay sau đăng nhập. Những biến thể cần cân nhắc:

- `//evil.example/path`: network-path reference có thể chuyển host dù không có scheme.
- `https://trusted.example@evil.example/`: host thực là phần sau ký tự `@`.
- URL bắt đầu với scheme lạ hoặc có dấu backslash làm các parser hiểu không đồng nhất.
- Encoded `%2F%2F`, double encoding và canonicalization sai.
- Host suffix giống domain tin cậy nhưng không cùng origin.
- Redirect target đến trang nội bộ khác vốn tự thực hiện redirect ngoài site.
- `Referer` giả và `Host` header poisoning làm URL trong cache có domain không mong muốn.

**Phòng thủ:** dùng đích server-side cố định khi được; nếu cần đích động, chỉ cho phép route hoặc origin trong allow-list, normalize URI và kiểm tra scheme/host/port/context path sau parse, không lấy URL từ input chưa được tin cậy. Không đưa password, access token, reset token hoặc PII nhạy cảm vào query string/`Location`.

**`defaultSuccessUrl("/dashboard", true)` giảm độ phức tạp về điều hướng**, nhưng không tự bảo đảm không có open redirect ở những controller khác.

## 13. Redirect so với forward và mã 302/303/307/308

| Tiêu chí | Redirect sau login | Forward server-side |
| --- | --- | --- |
| HTTP | Response 3xx kèm `Location`. | Servlet chuyển tiếp nội bộ trong một request. |
| Thanh địa chỉ browser | Có thể đổi theo URL đích. | Thường vẫn hiển thị URL request gốc. |
| Request mới | Trình duyệt gửi request mới. | Không nhất thiết có request browser mới. |
| Auth/session | Cần context được khôi phục ở request mới. | Cùng request vẫn có thể đọc context tùy filter/dispatch. |
| Tránh form resubmission | Thường phù hợp POST/Redirect/GET. | Forward từ POST có thể giữ hệ quả resubmit. |

`DefaultRedirectStrategy` trong Spring Security thông thường dùng **302 Found**. Một số client chuyển từ POST sang GET khi theo redirect 302; nếu một API cần mô tả “đi tới GET sau POST” rõ hơn, có thể cân nhắc **303 See Other** qua custom strategy/handler phù hợp.

**Không dùng 307/308 một cách tùy tiện** cho redirect sau login POST: những status đó giữ method/body theo HTTP semantics, có thể làm gửi lại dữ liệu credential tới URL đích. Tùy chỉnh status redirect phải kiểm thử với browser/client tương ứng.

Đối với `ForwardAuthenticationSuccessHandler`, đừng coi đó là bản sao hoàn toàn của `defaultSuccessUrl`; forward cần xem xét dispatcher types, URL hiển thị, CSRF và filter chain của request chuyển tiếp.

## 14. Kiểm thử đúng: từ handler tới HTTP login thật

### 14.1. Test ở mức handler

Sử dụng mock Servlet request/response như mục 8 để kiểm tra:

| Case | Saved request | Handler | Kỳ vọng |
| --- | --- | --- | --- |
| Login trực tiếp | Không | Default handler có URL fallback | Dashboard. |
| Login sau protected GET | Có `/private` | `alwaysUse=false` | URL gốc. |
| Forced landing | Có `/private` | `alwaysUse=true` | Dashboard, xóa cache. |
| Target parameter được bật | Có | `targetUrlParameter("next")` | Parameter ưu tiên nếu hợp lệ, cache xóa. |
| Referer được bật | Không | `useReferer=true` | Referer nếu có, fallback nếu không. |
| Custom 204 | Không liên quan | Custom handler | Status 204, không redirect. |

**Đừng assert chỉ status 302**. Một redirect tới trang phishing cũng có thể là 302 hợp lệ về mặt HTTP nhưng sai bảo mật. Trong regression test, kiểm tra URL đầy đủ, scheme/host/context path, query và allow-list khi có dữ liệu client.

### 14.2. Integration test Spring Security + MockMvc

Một bài test login thật phải đi qua `UsernamePasswordAuthenticationFilter` và `AuthenticationManager`. Ví dụ trích đoạn (giả sử đã có user hợp lệ và `MockMvc` được cấu hình cùng Spring Security):

```java
@Test
void loginDirectlyGoesToDashboard() throws Exception {
    mockMvc.perform(formLogin()
            .user("demo")
            .password("correct-password"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/dashboard"));
}
```

Đây **không phải JUnit class độc lập**; nó cần `spring-security-test`, imports, fixture user và chính sách formLogin đúng. Nếu user không tồn tại hoặc hash trong fixture không tương thích encoder, request sẽ chạy failure handler chứ không redirect dashboard.

Để test saved request, hãy **giữ cùng `MockHttpSession`** giữa request bị chặn và POST login. Ví dụ mô tả trình tự:

```text
1. GET /private trong trạng thái anonymous.
2. Lấy HttpSession đã lưu SavedRequest (nếu có).
3. POST /login với session ấy, credentials đúng và CSRF token.
4. Assert HTTP redirect tới /private.
5. Theo redirect GET /private với session/cookie thích hợp.
6. Assert Authentication đã được duy trì và authorization hợp lệ.
```

Trong test có nhiều filter chain, xác minh request thực đi qua chain đúng, vì `defaultSuccessUrl` của web chain không nhất thiết quyết định login API chain.

### 14.3. Những test cần bổ sung

- Login thất bại → `failureUrl`/failure handler, không chạy success.
- Account locked/disabled → không cấp `Authentication`, không redirect như success.
- POST login thiếu CSRF token → từ chối theo policy; handler thành công chưa được gọi.
- User reader được saved `/admin` → có thể redirect tới `/admin` nhưng GET sau bị 403.
- Saved URL có query string được chấp nhận → query phải được giữ đúng, không chứa token bí mật.
- URL target parameter trỏ domain bên ngoài → bị deny hoặc fallback theo policy.
- Session cookie bị thiếu/hết hạn → không khôi phục saved request hoặc authentication như mong đợi.
- Context path `/app` và reverse proxy HTTPS → Location đúng scheme/host/path.
- `alwaysUse=true` → không dùng lại saved request cũ ở login sau.
- Logout rồi đăng nhập lại → không rò saved request/context của session đã invalidate.
- Custom handler trả JSON → response không đồng thời chứa `Location` redirect.
- Nếu sử dụng role-based landing → role lấy từ server; authorization vẫn áp dụng.

### Vì sao `@WithMockUser` không đủ?

`@WithMockUser` hữu ích để test authorization/controller vì có thể đặt security context trực tiếp. Nó **không chứng minh** login filter đã xử lý username/password, handler đã được gọi hoặc saved request được restore. Test thật phải đi qua login endpoint hoặc gọi success handler trực tiếp với đúng mô hình.

## 15. Khi nào nên dùng `NullRequestCache`?

Với một API stateless dùng bearer token/JWT, trình duyệt thường không cần quay về saved URL sau một form login. `NullRequestCache` phù hợp khi bạn **không muốn lưu request gốc** vào session. Một API authentication thành công có thể trả JSON hoặc HTTP 204 cho client thay vì redirect.

Điều này **không phải** lời khuyên chuyển tất cả form login sang stateless: browser form login dựa session thường dùng request cache để phục hồi trang và `SecurityContextRepository` để duy trì authentication. Hãy chọn theo kiến trúc endpoint, không theo việc muốn giảm vài HTTP redirects.

Nếu đã dùng `NullRequestCache` nhưng vẫn cần “quay lại trang trước” trong SPA, frontend có thể giữ route nội bộ trong state an toàn rồi điều hướng sau khi nhận kết quả login. Không đưa arbitrary external URL vào state mà không validate.

## 16. Các triệu chứng hay gặp và cách debug

### 16.1. Login đúng nhưng luôn về dashboard

Kiểm tra:

1. Có `defaultSuccessUrl("/dashboard", true)` hay custom success handler luôn redirect dashboard không?
2. Saved request có được tạo trong `RequestCache` khi bị chặn trước login không?
3. Có dùng `NullRequestCache` hoặc `requestCache().disable()` không?
4. Browser có giữ cùng HttpSession giữa GET protected và POST login không?
5. Request matcher cache có bỏ qua original URL hoặc bị các request phụ ghi đè không?
6. Handler có targetUrlParameter/Referer override không?
7. Multiple `SecurityFilterChain` có khiến request vào chain khác không?

### 16.2. Login đúng nhưng request sau lại anonymous

Kiểm tra **SecurityContextRepository**, không chỉ URL đích:

- Filter đã lưu SecurityContext theo mô hình explicit save chưa?
- Session fixation strategy có đổi session ID đúng không?
- Cookie `JSESSIONID` có được trả và gửi lại không?
- Cookie có `Secure`/`SameSite`/`Path`/domain đúng không?
- Proxy đang tạo Location sai scheme hoặc host?
- Session store có đồng bộ qua các node không?
- URL đích có thực sự thuộc security chain dùng cơ chế session không?

### 16.3. Redirect tới `/admin` rồi gặp 403

Saved URL có thể là `/admin`; nhưng user chỉ có `ROLE_USER`. Authorization phải từ chối. Có thể hiển thị trang 403 thân thiện hoặc điều chỉnh product navigation policy, **không** mở endpoint nhạy cảm bằng `permitAll`.

### 16.4. Form login POST trả 403 trước khi redirect

Thường kiểm tra CSRF: form thiếu token hoặc cookie/session không còn khớp, loginProcessingUrl/method sai, hoặc filter chain không như cấu hình. `defaultSuccessUrl` không được chạy khi authentication chưa thành công.

### 16.5. Redirect sang domain nội bộ hoặc HTTP

Kiểm tra forwarded headers và reverse proxy trust, context path, absolute default target URL, URL trong saved request và Host header. Không tin `X-Forwarded-Host` do client trực tiếp gửi. Dùng cấu hình proxy chuẩn và test với request HTTPS thực.

## 17. Những sai lầm cần tránh

1. **“`defaultSuccessUrl("/dashboard")` luôn đi dashboard.”** Sai: saved request được ưu tiên.
2. **“Tham số `true` nghĩa là không redirect.”** Sai: nó buộc dùng default target.
3. **“`SavedRequest` và `SecurityContext` là một.”** Sai: một cái lưu URL, cái kia lưu authentication.
4. **“Redirect đúng nghĩa là đã xác thực bền vững.”** Không; context/session có thể mất ở GET tiếp.
5. **“Cứ đổi `defaultSuccessUrl` là sửa được login loop.”** Sai nếu do cookie/repository/CSRF.
6. **“`failureUrl` là đích thành công.”** Sai: nó cho login thất bại.
7. **“Đưa `next` từ client vào Location là bình thường.”** Có thể tạo open redirect.
8. **“Referer luôn đáng tin.”** Không: có thể bị bỏ hoặc giả mạo.
9. **“`startsWith` đủ kiểm tra host.”** Không: cần parse/canonicalize/allow-list.
10. **“Saved request cho phép truy cập URL đã lưu.”** Authorization vẫn chạy.
11. **“Một POST có saved request được replay an toàn.”** Không dùng request cache làm transaction queue.
12. **“Mọi login thành công đều xóa saved request ngay.”** Không đúng khi redirect về URL gốc.
13. **“Bật `alwaysUse=true` không ảnh hưởng UX.”** Nó bỏ đường trở về trang user đang xem.
14. **“`successHandler` tùy biến sẽ tự gọi tiếp default success handler.”** Không; custom handler sở hữu response.
15. **“Return 204 rồi redirect tiếp cũng được.”** Sai contract và có thể commit response.
16. **“Cho role do browser gửi quyết định redirect.”** Nguy cơ giả mạo; dùng Authentication đáng tin.
17. **“Đi tới /admin sau login chứng minh đã là admin.”** Không; handler không thay authorization.
18. **“Chỉ test `@WithMockUser` là đủ.”** Không test login success flow.
19. **“Không cần test context path/proxy vì redirect luôn tương đối.”** Không bảo đảm với URL tuyệt đối hoặc host rewrite.
20. **“CSRF không liên quan tới login redirect.”** CSRF có thể chặn POST trước success.
21. **“Có thể lưu password/token trong query để giữ state.”** URL có thể rò qua history/logs/Referer.
22. **“`307` sau POST login giống `302`.”** 307 giữ method/body theo semantics, nguy cơ gửi lại credentials.
23. **“Cứ permitAll dashboard để sửa 403.”** Có thể mở dữ liệu nhạy cảm.
24. **“RequestCache bắt buộc phải tồn tại trong stateless API.”** Không; có thể dùng NullRequestCache.
25. **“Session cũ luôn được giữ qua session fixation protection.”** Phải test cấu hình thực.
26. **“Đặt GET và POST /login vào một controller cũng giống filter mặc định.”** Không nếu POST do authentication filter quản lý.
27. **“Mọi HTTP 302 từ login là thành công.”** Failure handler cũng có thể redirect, cần kiểm tra Location.
28. **“Saved request sẽ luôn được tìm thấy trên login POST không có cookie.”** Không: session không liên kết.
29. **“Đích động do user profile chưa được xác minh là an toàn.”** Phải kiểm tra quyền và nguồn dữ liệu.
30. **“Có một success URL cố định thì mọi user đều có quyền xem nó.”** Policy phải được kiểm chứng riêng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `defaultSuccessUrl("/home")` khác `defaultSuccessUrl("/home",true)` như thế nào?

**Trả lời:** Bản một tham số ưu tiên saved request nếu có. Bản `true` luôn dùng `/home` và bỏ saved request liên quan.

**Câu 2.** Người dùng anonymous cố xem `/orders/42`, bị yêu cầu login; sau login đúng sẽ tới đâu với `defaultSuccessUrl("/dashboard")`?

**Trả lời:** Nếu RequestCache còn saved request `/orders/42` thì thường về `/orders/42`; nếu không, fallback về `/dashboard`.

**Câu 3.** Một user tự mở `/login`, không có saved request thì sao?

**Trả lời:** Redirect về default target `/dashboard`.

**Câu 4.** `SavedRequestAwareAuthenticationSuccessHandler` có xóa cache ngay ở mọi login không?

**Trả lời:** Không. Khi redirect tới URL gốc, nó có thể giữ request cho matching wrapper. Với force default/target parameter ưu tiên thì xóa.

**Câu 5.** `defaultSuccessUrl` có xác minh password không?

**Trả lời:** Không. Password được manager/provider kiểm chứng; handler chỉ nhận kết quả thành công và điều hướng.

**Câu 6.** Vì sao `next=https://evil.example` có rủi ro?

**Trả lời:** Nếu redirect dựa vào URL client không được validate, nó tạo open redirect, hỗ trợ phishing và có thể làm lộ thông tin trong URL.

**Câu 7.** `RequestCache` và `SecurityContextRepository` khác nhau?

**Trả lời:** RequestCache lưu request/URL trước login; SecurityContextRepository lưu authentication context để khôi phục theo session/request scope.

**Câu 8.** Login đã redirect đúng dashboard nhưng GET tiếp theo anonymous là do đâu?

**Trả lời:** Có thể do repository không save, cookie/session mất, session fixation/proxy/path sai hoặc security chain khác; không nhất thiết do `defaultSuccessUrl`.

**Câu 9.** Vì sao một saved `/admin` vẫn có thể trả 403 sau login?

**Trả lời:** Saved request không cấp quyền. User chỉ có quyền tương ứng với Authentication đã được xác minh và authorization của URL.

**Câu 10.** Thế nào là test đáng tin cho redirect sau login?

**Trả lời:** Gửi POST login qua filter/provider thật với user fixture đúng, kiểm tra 302 + Location, giữ cùng session từ request protected trước login, thử `alwaysUse` true/false và kiểm tra GET sau redirect.

**Câu 11.** Khi dùng custom JSON success handler, còn cần `defaultSuccessUrl` không?

**Trả lời:** Thường không; custom handler quyết định response (200/204/JSON). Nó phải có contract và dọn RequestCache phù hợp.

**Câu 12.** `302` và `307` có giống nhau sau POST login?

**Trả lời:** Không. Với 302 nhiều client chuyển sang GET; 307 giữ method/body, có thể gửi lại password POST sang URL đích, nên không chọn tùy tiện.

**Câu 13.** `loginPage` và `loginProcessingUrl` khác nhau thế nào?

**Trả lời:** Một cái là trang GET hiển thị form, cái kia là endpoint POST do authentication filter nhận credentials.

**Câu 14.** Tham số `alwaysUse=true` có ngăn user tự truy cập URL bảo vệ khác không?

**Trả lời:** Không. Nó chỉ chọn URL sau login; authorization của mọi URL vẫn bắt buộc.

## 19. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): luồng filter nhận form, authentication success/failure, login page và POST.
- [Spring Security 6.5.11 — AbstractAuthenticationFilterConfigurer](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): `defaultSuccessUrl(String)` và `defaultSuccessUrl(String,boolean)`.
- [Spring Security 6.5.11 — SavedRequestAwareAuthenticationSuccessHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): thứ tự ưu tiên và lifecycle saved request.
- [Spring Security 6.5.11 — AbstractAuthenticationTargetUrlRequestHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html): URL mặc định, alwaysUse, target parameter và Referer.
- [Spring Security 6.5.11 — HttpSessionRequestCache](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/HttpSessionRequestCache.html): các API lưu, đọc, xóa và matching request.
- [Spring Security 6.5.11 — DefaultRedirectStrategy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/DefaultRedirectStrategy.html): tính `Location` và HTTP status redirect.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): lưu SecurityContext phục vụ request sau redirect.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explicit save và session fixation.
- [OWASP — Unvalidated Redirects and Forwards](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): chống open redirect và chỉ chấp nhận URL đáng tin.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): mã trạng thái 302, 303, 307 và 308.

**Kết luận:** `defaultSuccessUrl("/dashboard")` không có nghĩa tất cả user luôn về dashboard. Với `SavedRequestAwareAuthenticationSuccessHandler`, browser thường được chuyển về URL protected đã yêu cầu trước login; dashboard chỉ là fallback. Nếu sản phẩm bắt buộc về landing page, dùng `defaultSuccessUrl("/dashboard", true)` và chấp nhận bỏ saved request. Điều hướng sau login phải đi cùng **authentication thực**, session/context persistence, kiểm tra quyền trang đích, CSRF, validation URL và integration test trên chuỗi filter hoàn chỉnh.