# Giới hạn địa chỉ chuyển hướng để ngăn Open Redirect khi đăng nhập biểu mẫu

## 1. Mục tiêu và bối cảnh

Trong cơ chế **form login** của Spring Security (ứng dụng Servlet), sau khi xác thực thành công, máy chủ thường trả HTTP `302 Found` với header `Location` để đưa người dùng tới trang tiếp theo. Địa chỉ này là một **quyết định bảo mật**: nếu máy chủ nhận nguyên xi địa chỉ do trình duyệt gửi lên, kẻ tấn công có thể biến tên miền đáng tin của ứng dụng thành điểm trung chuyển sang trang lừa đảo.

Sau bài này, bạn cần phân biệt được:
- **Địa chỉ do máy chủ ấn định** với **địa chỉ do người dùng/đối thủ cung cấp** qua `next`, `returnUrl`, `redirect`, `targetUrl`, `Referer` hoặc yêu cầu đã lưu.
- Khi nào `defaultSuccessUrl` và `SavedRequestAwareAuthenticationSuccessHandler` quyết định đích đến.
- Cách chỉ cho phép một nhóm đích hợp lệ và kiểm thử các URL giả mạo, URL tuyệt đối, URL bắt đầu bằng `//`, đường dẫn mã hóa hoặc đường dẫn vượt phạm vi.
- Giới hạn của biện pháp chống open redirect: nó **không thay thế** xác thực, phân quyền trên endpoint đích, CSRF hay cấu hình proxy đáng tin.

Phạm vi: chuyển hướng **sau khi đăng nhập bằng form** trên Spring Security Servlet; OAuth2/OIDC `redirect_uri` là luồng riêng với yêu cầu đăng ký và so khớp redirect URI riêng.

## 2. Open redirect xảy ra như thế nào?

Giả sử ứng dụng tại `https://app.example` cho phép đăng nhập rồi trở về địa chỉ chỉ định bởi `next`:

~~~http
POST /login?next=https://evil.example/phishing HTTP/1.1
Host: app.example
Content-Type: application/x-www-form-urlencoded

username=alice&password=...
~~~

Nếu code đăng nhập thành công gọi `response.sendRedirect(request.getParameter("next"))`, phản hồi có thể là:

~~~http
HTTP/1.1 302 Found
Location: https://evil.example/phishing
~~~

Người dùng bấm vào một liên kết bắt đầu bằng tên miền ứng dụng thật, đăng nhập thành công rồi bị chuyển sang trang giả. Đây là **CWE-601: URL Redirection to Untrusted Site**. Open redirect không tự động cấp quyền truy cập tài khoản; tác hại thường gồm phishing, vượt qua kiểm tra URL dựa trên tên miền, và phối hợp với lỗi xác thực/ủy quyền khác.

Các đầu vào nguy hiểm không chỉ có `https://evil.example`:

| Đầu vào không đáng tin | Vấn đề |
| --- | --- |
| `https://evil.example/login` | URL tuyệt đối tới host ngoài |
| `//evil.example/login` | URL tương đối giao thức; trình duyệt có thể chuyển sang host ngoài |
| `https://app.example.evil.example/` | Host có tiền tố giống tên miền thật, nhưng là tên miền khác |
| `https://app.example@evil.example/` | Phần trước `@` là userinfo; host thực tế là `evil.example` |
| `/admin`, `../private` | Có thể tới khu vực không được phép điều hướng, dù cùng ứng dụng |
| `%2F%2Fevil.example`, dấu `\` hoặc chuỗi mã hóa nhiều lần | Có thể bị các lớp URL decoder, proxy, framework hay browser diễn giải khác nhau |
| `javascript:...`, ký tự điều khiển, CR/LF | Những chuỗi bất thường phải bị bác bỏ, không làm đầu vào trực tiếp cho header/redirect |

Đừng dùng phép kiểm tra chuỗi như `url.startsWith("https://app.example")` hay `url.contains("app.example")`: chúng không chứng minh được host thực tế và dễ bị đánh lừa.

## 3. Spring Security chọn đích chuyển hướng ở đâu?

Luồng cơ bản:

1. Khách chưa đăng nhập yêu cầu một URL cần xác thực. `ExceptionTranslationFilter` có thể lưu yêu cầu ban đầu qua `RequestCache` rồi đưa khách tới form login.
2. `UsernamePasswordAuthenticationFilter` xử lý `POST /login`; nếu thông tin hợp lệ, `AuthenticationSuccessHandler` quyết định bước tiếp theo.
3. Bộ xử lý mặc định thông dụng là `SavedRequestAwareAuthenticationSuccessHandler`. Theo cấu hình, nó cân nhắc đích cố định, `targetUrlParameter` và `SavedRequest`.
4. Máy chủ gửi phản hồi chuyển hướng. Trình duyệt đọc `Location` và yêu cầu URL tiếp theo.

Thứ tự đáng nhớ của `SavedRequestAwareAuthenticationSuccessHandler`: `alwaysUseDefaultTargetUrl=true` ưu tiên đích mặc định; nếu không, `targetUrlParameter` đã được cấu hình có thể được dùng; sau đó tới URL của `SavedRequest`; cuối cùng là `defaultTargetUrl`. Với handler lớp cơ sở, tùy chọn `useReferer` có thể dùng header `Referer` nếu bật. Cả tham số yêu cầu lẫn `Referer` đều là dữ liệu không đáng tin.

### Hai cấu hình dễ nhầm

~~~java
// Chỉ là lựa chọn mặc định nếu trước đó không có SavedRequest phù hợp.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard"));
~~~

~~~java
// Luôn đưa đến /dashboard sau form login thành công;
// không quay về SavedRequest cũ.
http.formLogin(form -> form.defaultSuccessUrl("/dashboard", true));
~~~

Cách thứ hai phù hợp nếu sản phẩm **không cần chuyển hướng động** sau đăng nhập. Đây là lựa chọn đơn giản và ít rủi ro nhất. Không nên cấu hình `targetUrlParameter("next")` rồi tin rằng Spring Security sẽ tự kiểm tra danh sách URL hợp lệ cho ứng dụng: chính ứng dụng phải thực thi chính sách đích đến. Tương tự, đừng dựa vào `Referer` để quyết định nơi gửi người dùng.

## 4. Chọn chính sách redirect trước khi viết code

Ưu tiên theo mức độ đơn giản và an toàn:

1. **Đích cố định:** sau mọi lần đăng nhập thành công, chuyển đến `/dashboard` bằng `defaultSuccessUrl("/dashboard", true)`.
2. **Danh mục đích do máy chủ quản lý:** nếu phải tùy biến, client chỉ gửi khóa ngắn như `profile`, `orders`; server ánh xạ tới các đường dẫn đã được phê duyệt. **Không chấp nhận URL tùy ý.**
3. **Chỉ khi có yêu cầu thực sự phải trả về một đường dẫn động:** chuẩn hóa và kiểm tra bằng parser tương thích với API redirect và trình duyệt, chỉ nhận đường dẫn nội bộ hợp lệ hoặc một origin được phép rõ ràng; kiểm tra lại trước khi tạo `Location`.

Ví dụ chính sách:

| `next` trong yêu cầu đăng nhập | Đích do máy chủ lựa chọn |
| --- | --- |
| `profile` | `/profile` |
| `orders` | `/orders` |
| Không có, rỗng hoặc giá trị khác | `/dashboard` |
| `https://evil.example/` hoặc `//evil.example` | `/dashboard`, tuyệt đối không chuyển sang host ngoài |

Nếu ứng dụng triển khai dưới context path `/portal`, các đường dẫn ở cột phải phải được tạo thành `/portal/profile`, `/portal/orders`, v.v. Không tự dựng URL dựa trên `Host` hay `X-Forwarded-Host` không được kiểm soát.

## 5. Ví dụ Spring Boot + Spring Security: chỉ chuyển hướng tới đích đã duyệt

Ví dụ dưới đây dành cho **Java 17+, Spring Boot 3.x / Spring Security 6.x, ứng dụng Servlet**. Đặt file vào dự án Spring Boot có các dependency `spring-boot-starter-web` và `spring-boot-starter-security`. Đây là chương trình demo hoàn chỉnh trong **một file Java**; sử dụng tài khoản nội bộ chỉ để thực hành. Ứng dụng thực tế phải dùng kho người dùng/IdP và quản lý bí mật phù hợp.

File `src/main/java/com/example/redirectdemo/RedirectDemoApplication.java`:

~~~java
package com.example.redirectdemo;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RedirectDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedirectDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .anyRequest().authenticated()
            )
            // Demo luôn chọn đích theo whitelist, không khôi phục SavedRequest.
            .requestCache(cache -> cache.requestCache(new NullRequestCache()))
            .formLogin(form -> form
                // Spring Security tạo trang GET /login mặc định.
                .successHandler(this::onLoginSuccess)
                .permitAll()
            );

        return http.build();
    }

    private void onLoginSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) throws IOException {

        // "next" là dữ liệu không đáng tin; KHÔNG đưa trực tiếp vào sendRedirect.
        String next = request.getParameter("next");
        String safePath = approvedPath(next);

        // safePath chỉ có thể là hằng đường dẫn nội bộ do server định nghĩa.
        response.sendRedirect(request.getContextPath() + safePath);
    }

    private static String approvedPath(String next) {
        if ("profile".equals(next)) {
            return "/profile";
        }
        if ("orders".equals(next)) {
            return "/orders";
        }
        return "/dashboard";
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @RestController
    static class DemoPages {
        @GetMapping({"/dashboard", "/profile", "/orders"})
        String page(HttpServletRequest request) {
            return "OK " + request.getRequestURI();
        }
    }
}
~~~

**Tại sao ví dụ này chặn được open redirect?**

- `approvedPath` so sánh **bằng nhau chính xác** với hai khóa đã duyệt. Không có nhánh nào trả lại chuỗi `next` do client cung cấp.
- Đích `Location` được tạo từ context path do servlet container quản lý và một trong ba đường dẫn hằng số `/profile`, `/orders`, `/dashboard`; chuỗi độc hại không được tham gia tạo URL.
- `NullRequestCache` vô hiệu việc lưu/khôi phục đường dẫn trước đăng nhập trong riêng demo này, giúp một `SavedRequest` không vượt qua chính sách redirect mới. **Đổi lại**, người dùng mở URL bảo vệ trước khi đăng nhập sẽ không tự động quay về URL đó sau khi xác thực.
- `.permitAll()` cho phép truy cập trang/endpoint login; phần còn lại vẫn được bảo vệ bởi `.anyRequest().authenticated()`. Danh sách redirect hợp lệ không quyết định ai được phép truy cập nội dung trang đích.
- CSRF cho form login giữ nguyên cấu hình mặc định. **Không dùng `csrf.disable()` để làm cho thử nghiệm POST dễ hơn.**

Trang login mặc định tạo bởi Spring Security **không tự mang tham số `next` từ `GET /login?next=orders` sang POST**. Nếu sản phẩm cần tính năng này, hãy tạo form đăng nhập riêng (có CSRF token) và truyền **khóa** `next` dưới dạng hidden field trong `POST /login`. Trường hidden vẫn phải bị xem là đầu vào có thể bị sửa. Bài thực hành dùng MockMvc để gửi `next` trực tiếp trong request POST, giúp kiểm thử đúng nhánh xử lý mà không cần thêm template.

Chạy trong dự án Spring Boot có Maven wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`. Khi đăng nhập bằng tài khoản demo rồi vào `/orders`, controller trả nội dung `OK /orders`. Sau đăng nhập, đích mặc định là `/dashboard` nếu POST không chứa khóa được chấp nhận. Đây là ứng dụng Spring Boot, **không** biên dịch độc lập bằng `javac` khi thiếu dependency.

## 6. Kiểm thử redirect an toàn bằng MockMvc

Thêm dependency test `spring-boot-starter-test` và `spring-security-test` (scope `test`) vào dự án. Bài test này dành cho cùng dự án Spring Boot 3.x ở trên. File `src/test/java/com/example/redirectdemo/RedirectDemoApplicationTests.java`:

~~~java
package com.example.redirectdemo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RedirectDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        "profile, /profile",
        "orders, /orders",
        "https://evil.example/phish, /dashboard",
        "//evil.example/phish, /dashboard",
        "https://app.example.evil.example/, /dashboard",
        "https://app.example@evil.example/, /dashboard",
        "%2F%2Fevil.example, /dashboard",
        "../admin, /dashboard",
        "/admin, /dashboard",
        "javascript:alert(1), /dashboard",
        "unknown, /dashboard"
    })
    void choosesOnlyApprovedTargets(String next, String expected)
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-password")
                .param("next", next))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl(expected));
    }

    @Test
    void missingNextFallsBackToDashboard() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void invalidCredentialsDoNotReachSuccessHandler() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong")
                .param("next", "orders"))
            .andExpect(status().isFound())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void postWithoutCsrfTokenIsDenied() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "demo-password")
                .param("next", "orders"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Kỳ vọng: tất cả test qua; các giá trị `next` không thuộc whitelist đều chuyển đến `/dashboard`, không có header `Location` trỏ sang `evil.example`. MockMvc dùng `.with(csrf())` để mô phỏng form hợp lệ; chỉ riêng test CSRF âm tính cố ý không dùng. Nếu dự án dùng context path khác rỗng, hãy điều chỉnh URL kỳ vọng cho đúng và bổ sung test context path tương ứng.

Bộ thử nên được mở rộng theo chức năng thực tế: input rỗng; chữ hoa/chữ thường; tab/khoảng trắng; Unicode; `\evil.example`; ký tự xuống dòng; URL được mã hóa một hoặc nhiều lần; query string; redirect sau hết hạn phiên; login thất bại; đường dẫn đích bị giới hạn vai trò; các trường hợp qua reverse proxy. Với chính sách khóa cố định, mọi chuỗi không khớp chính xác đều rơi về fallback.

## 7. Nếu sản phẩm cần quay về trang được yêu cầu trước khi login

Không tự động bật cơ chế nhận URL tùy ý chỉ để giữ trải nghiệm “quay lại trang trước đó”. Có ba cách thiết kế:

**Cách A — dùng khóa do server quản lý:** ở thời điểm yêu cầu login, lưu trong session một ID đã kiểm chứng (ví dụ `orders`); sau đăng nhập server ánh xạ ID sang đích hằng. Nếu phải liên kết với một nghiệp vụ có tham số (mã đơn hàng), server cần kiểm tra định dạng ID và quyền truy cập đơn hàng trước/sau điều hướng. Có thể dùng token ngắn hạn gắn với session, chống sửa và hết hạn để tham chiếu tới đích đã xác minh.

**Cách B — kiểm tra đường dẫn nội bộ:** nếu business bắt buộc nhận một return path thay đổi, chỉ nhận các path đã qua parser và kiểm tra theo quy tắc chặt. Từ chối URL có scheme/authority, `//`, dấu gạch ngược, ký tự điều khiển, userinfo, path traversal, phần mã hóa không hợp lệ, và đường dẫn nằm ngoài prefix/route được phép. Cẩn thận với các lớp decode nhiều lần: kết quả sau cùng mà browser thực sự điều hướng mới là kết quả quan trọng. Tái kiểm tra đích **trước khi phát `Location`**. Không gộp các dạng bất thường bằng sửa chuỗi thủ công rồi mặc nhiên coi là hợp lệ.

**Cách C — thực sự cần redirect tới origin bên ngoài:** ưu tiên ánh xạ khóa cố định tới URL HTTPS đầy đủ ở server. Nếu không thể, parse URL bằng thư viện được duy trì, chỉ cho phép scheme `https`, so khớp **chính xác** host chuẩn hóa và effective port theo allowlist, loại bỏ userinfo và cấu trúc nhập nhằng, giới hạn path khi cần; không dùng so khớp chuỗi tiền tố/hậu tố. Cân nhắc trang xác nhận khi rời site.

Với `SavedRequestAwareAuthenticationSuccessHandler`, phải hiểu rằng URL đã lưu có thể được ưu tiên hơn `defaultSuccessUrl("/dashboard")`. Nếu muốn dùng `SavedRequest`, cần kiểm soát nguồn tạo request, host/public origin, cấu hình trusted proxy, và áp dụng chính sách an toàn cho đích đã lưu. Nếu không cần deep link, chọn đích cố định với cờ `true` hoặc handler riêng kèm `NullRequestCache` như ví dụ. Đừng cho rằng việc “URL nằm trong session” khiến nó tự nhiên đáng tin: nó có thể bắt nguồn từ một yêu cầu do client khởi tạo.

## 8. Những lỗi triển khai thường gặp

| Sai lầm | Vì sao không an toàn / dễ hiểu sai | Cách sửa |
| --- | --- | --- |
| `sendRedirect(request.getParameter("next"))` | Trình duyệt quyết định URL đích từ đầu vào bên ngoài | Chỉ dùng đích cố định hoặc ánh xạ khóa sang đích được duyệt |
| `url.startsWith("https://app.example")` | Chấp nhận `https://app.example.evil.example` | So sánh host/origin đã parse hoặc dùng khóa nội bộ |
| `url.endsWith("app.example")` | Chuỗi thô không biểu đạt host, scheme, userinfo, port | Dùng URL parser + whitelist chính xác |
| Cho phép URL bắt đầu bằng `/` | `//evil.example` cũng bắt đầu bằng `/` | Không dùng kiểm tra một ký tự; ưu tiên ánh xạ định danh |
| Bật `targetUrlParameter` để tiện form login | Tham số có thể bị đối thủ chỉnh sửa | Kiểm tra trước khi redirect hoặc thay bằng success handler có whitelist |
| Chỉ cài `defaultSuccessUrl("/dashboard")` rồi nghĩ luôn ở đó | SavedRequest có thể được chọn trước đích mặc định | Dùng overload `(..., true)` nếu muốn cố định |
| Tin `Referer`, `Host`, `X-Forwarded-Host` như nguồn origin an toàn | Header có thể bị thao túng khi triển khai proxy sai | Cấu hình trusted proxy/host rõ ràng; không lấy redirect đích từ header thô |
| Chặn host ngoài nhưng cho phép mọi path nội bộ | Có thể điều hướng tới endpoint không mong muốn hoặc gây lỗi logic | Giới hạn route hợp lệ và giữ nguyên authorization trên endpoint |
| Tắt CSRF để kiểm thử `POST /login` | Làm giảm an toàn form login và che giấu lỗi cấu hình | Dùng CSRF token thật hoặc `.with(csrf())` khi test |

**Lưu ý về kiểm soát truy cập:** chuyển hướng đến `/admin` không tự động cấp quyền truy cập `/admin`; Spring Security vẫn phải chặn người không có quyền. Tuy vậy, đích chuyển hướng không nên vượt ngoài chính sách sản phẩm. **Lưu ý về ghi log:** ghi nhận việc từ chối `next` bất thường theo mức độ phù hợp, nhưng tránh log mật khẩu, token đăng nhập hoặc toàn bộ query chứa thông tin nhạy cảm.

## 9. Checklist trước khi đưa vào production

- [ ] Đích đến sau login được xác định từ cấu hình server hoặc tập ID/path được phê duyệt; không chuyển thẳng dữ liệu người dùng vào `Location`.
- [ ] Không nhận URL có host ngoài dưới dạng `next`/`returnUrl`, trừ khi sản phẩm có yêu cầu cụ thể và allowlist origin rõ ràng.
- [ ] Kiểm tra cả `targetUrlParameter`, `SavedRequest`, `Referer` và các success handler tùy biến; mọi nhánh dẫn tới chuyển hướng phải theo cùng chính sách.
- [ ] Trang login truyền đúng khóa nghiệp vụ khi cần; hidden field được kiểm tra ở server; CSRF vẫn bật.
- [ ] Sau khi đăng nhập sai hoặc thiếu CSRF không xuất hiện redirect theo `next`.
- [ ] Test các trường hợp URL tuyệt đối, `//host`, host giả, userinfo, URL-encoding, path traversal và input rỗng.
- [ ] Có fallback xác định; xử lý context path/reverse proxy nhất quán và chỉ tin header forwarded từ proxy được phép.
- [ ] Từng route đích vẫn kiểm tra authentication/authorization độc lập.

## 10. Tài liệu chính thức

1. Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
2. Spring Security API — `SavedRequestAwareAuthenticationSuccessHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html
3. Spring Security API — `AbstractAuthenticationTargetUrlRequestHandler` (cảnh báo `targetUrlParameter` và `useReferer`): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationTargetUrlRequestHandler.html
4. Spring Security API — `RequestCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html
5. Spring Security — Testing Form Based Authentication: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
6. OWASP — Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Nguyên tắc phải nhớ:** chỉ chuyển hướng tới những đích **đã được server quyết định/kiểm chứng**, và kiểm thử header `Location` sau **đăng nhập thành công** chứ không chỉ kiểm tra biểu mẫu hay mã HTTP.