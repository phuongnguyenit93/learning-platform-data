# SPA: nhận, gửi và làm mới CSRF token sau đăng nhập hoặc đăng xuất

**Module:** Spring Security – Servlet  
**Nhóm kiến thức:** CSRF

## 1. Bài toán và phạm vi

Trong bài này, **token** là **CSRF token** (mã chống Cross-Site Request Forgery), không phải access token, ID token hay refresh token của OAuth 2.0/OIDC. Một SPA dùng **đăng nhập bằng phiên (session)** thường nhận cookie phiên như JSESSIONID; trình duyệt tự đính kèm cookie phù hợp vào request. Vì thế trang độc hại có thể tìm cách khiến trình duyệt gửi thao tác thay người dùng. CSRF token bổ sung bằng chứng rằng thao tác đổi trạng thái xuất phát từ ứng dụng hợp lệ.

Mục tiêu là làm đúng toàn bộ vòng đời:

1. Trước khi đăng nhập, SPA lấy một CSRF token từ server.
2. SPA đính kèm token vào header khi gửi POST đăng nhập hoặc các request thay đổi trạng thái.
3. Sau khi đăng nhập thành công, SPA **lấy token mới** vì Spring Security có thể xóa token cũ.
4. Trước khi đăng xuất, SPA gửi token hiện hành trong POST đăng xuất.
5. Sau khi đăng xuất thành công, SPA **lấy token mới** để lần đăng nhập tiếp theo có thể dùng ngay.

Nếu ứng dụng chỉ dùng bearer access token trong header Authorization do JavaScript chủ động thêm, mô hình CSRF có thể khác. Tuy nhiên, **mọi endpoint dựa vào cookie xác thực tự gửi** vẫn phải được đánh giá và bảo vệ khỏi CSRF. Không nhầm việc refresh CSRF token với làm mới access token OAuth.

## 2. Spring Security Servlet xử lý token như thế nào?

- **CsrfFilter** kiểm tra token đối với request thay đổi trạng thái; mặc định GET, HEAD, TRACE, OPTIONS không cần token, còn POST, PUT, PATCH, DELETE cần token. Endpoint GET không được thực hiện thao tác làm thay đổi dữ liệu.
- **CsrfTokenRepository** tạo, lưu và nạp token kỳ vọng. Mặc định phổ biến cho ứng dụng servlet dùng session là HttpSessionCsrfTokenRepository. Một lựa chọn khác là CookieCsrfTokenRepository.
- **CsrfTokenRequestHandler** quyết định cách đưa token lên request và cách đọc token client gửi. Spring Security 6 dùng xử lý token có che giấu XOR nhằm hạn chế rò rỉ qua nén phản hồi (BREACH).
- **Deferred token:** Spring Security có thể trì hoãn tạo/nạp token cho đến khi cần. Một endpoint bootstrap phải thật sự truy cập giá trị token, chẳng hạn gọi csrfToken.getToken(), để token được tạo và trả về.
- **Thay đổi trạng thái xác thực:** CsrfAuthenticationStrategy xóa token trước đó sau khi xác thực thành công; CsrfLogoutHandler xóa token lúc logout. Do đó SPA không được tiếp tục dùng token cũ sau hai sự kiện này.

CSRF token **không xác thực người dùng**, không quyết định vai trò và không thay thế kiểm tra authorization. Spring Security sẽ kiểm tra CSRF và quyền truy cập theo các bước riêng.

## 3. Trình tự request đúng

| Thời điểm | Request từ SPA | CSRF token gửi đi | Điều SPA cần làm |
| --- | --- | --- | --- |
| Mở trang, chưa đăng nhập | GET /api/csrf | Không cần | Lấy token và giữ tạm trong bộ nhớ |
| Đăng nhập | POST /api/login | Token vừa lấy trong header | Gửi kèm cookie phiên nếu có |
| Đăng nhập thành công | GET /api/csrf | Không cần | **Thay token cũ** bằng token mới |
| Thao tác nghiệp vụ | POST/PUT/PATCH/DELETE | Token đang hiệu lực | Gửi token trong header |
| Đăng xuất | POST /api/logout | Token đang hiệu lực | Server xóa phiên và CSRF token cũ |
| Đăng xuất thành công | GET /api/csrf | Không cần | **Lấy lại token** cho lần đăng nhập tiếp |
| Phiên hết hạn/token không hợp lệ | Thường nhận HTTP 403 khi CSRF sai | Token đã cũ | Tải lại token; quyết định có cần yêu cầu người dùng thao tác lại |

Luồng minh họa:

~~~text
SPA                       Spring Security (Servlet)
 |--- GET /api/csrf ------------------------>|
 |<-- 200 {headerName, token A} + session ---|
 |--- POST /api/login; CSRF: token A ------->|
 |<-- 204; token A bị vô hiệu hóa -----------|
 |--- GET /api/csrf ------------------------>|
 |<-- 200 {headerName, token B} -------------|
 |--- POST /api/data; CSRF: token B -------->|
 |<-- 200 -----------------------------------|
 |--- POST /api/logout; CSRF: token B ------>|
 |<-- 204; phiên/token B bị xóa -------------|
 |--- GET /api/csrf ------------------------>|
 |<-- 200 {headerName, token C} -------------|
~~~

A, B, C là ký hiệu logic cho các token hợp lệ ở từng giai đoạn. Do cơ chế XOR, **chuỗi token trả về có thể khác giữa hai lần GET** ngay cả khi token lưu trong repository chưa thay đổi; không dùng phép so sánh hai chuỗi phản hồi để khẳng định session đã đổi.

## 4. Ví dụ chạy được: Spring Boot 3 + Spring Security 6 + session

Ví dụ chạy với **Java 17+**, **Maven** và Spring Boot **3.3.5**. Đây là cấu hình học tập cùng origin (SPA và API cùng host). Khi dùng thực tế, chọn bản Spring Boot/Spring Security đã được cập nhật bản vá phù hợp. Để tái hiện kết quả, tạo các file sau.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>csrf-spa-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
~~~

**src/main/java/demo/DemoApplication.java**

~~~java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginProcessingUrl("/api/login")
                .successHandler((request, response, authentication) ->
                    response.setStatus(204))
                .failureHandler((request, response, exception) ->
                    response.sendError(401))
                .permitAll())
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(204))
                .permitAll())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint((request, response, exception) ->
                    response.sendError(401)))
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    // Chỉ để chạy thử trên máy cá nhân. Không hard-code tài khoản thật.
    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @RestController
    static class Api {
        // Cho phép gọi khi chưa đăng nhập và sau khi vừa đăng xuất.
        @GetMapping("/api/csrf")
        ResponseEntity<Map<String, String>> csrf(CsrfToken csrfToken) {
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                    "headerName", csrfToken.getHeaderName(),
                    "token", csrfToken.getToken()
                ));
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }

        @PostMapping("/api/data")
        Map<String, String> data(@RequestBody Map<String, String> body) {
            // Demo echo; không ghi cơ sở dữ liệu.
            return Map.of("echo", body.getOrDefault("value", ""));
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Giải thích cấu hình:

- GET /api/csrf được permitAll để SPA có thể bootstrap **trước login và sau logout**. Bằng cách gọi csrfToken.getToken(), endpoint buộc token deferred được tạo/nạp. Phản hồi no-store hạn chế cache token.
- Spring Security giữ session bằng cookie, xử lý POST /api/login với body form-urlencoded chứa username và password, trả 204 khi thành công, 401 nếu sai thông tin.
- POST /api/logout được LogoutFilter xử lý, trả 204. Endpoint này **vẫn chịu CSRF protection**.
- Phần bảo vệ CSRF được giữ bật bằng cấu hình mặc định; **không dùng csrf.disable()**, cũng không bỏ qua CSRF cho login/logout.
- /api/me và /api/data phải đăng nhập. /api/data chỉ phản hồi lại giá trị đã nhận; nó minh họa một POST cần CSRF token, không phải API lưu dữ liệu thật.

## 5. Mã SPA: nhận token, gửi header, làm mới sau hai sự kiện

Mở một trang cùng origin với server (ví dụ http://localhost:8080/login), rồi chạy đoạn JavaScript này trong DevTools Console; hoặc đưa vào module frontend cùng origin. Dùng fetch credentials: "same-origin" để browser gửi/nhận cookie phiên cho request cùng origin.

~~~javascript
let csrf = null;

async function loadCsrf() {
  const response = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Không lấy được CSRF token: " + response.status);
  }

  const data = await response.json();
  if (!data.headerName || !data.token) {
    throw new Error("Phản hồi CSRF thiếu headerName hoặc token");
  }
  csrf = { headerName: data.headerName, token: data.token };
  return csrf;
}

async function protectedPost(path, body, contentType) {
  if (!csrf) await loadCsrf();

  const headers = { [csrf.headerName]: csrf.token };
  if (contentType) headers["Content-Type"] = contentType;

  const response = await fetch(path, {
    method: "POST",
    headers,
    body,
    credentials: "same-origin"
  });

  if (response.status === 403) {
    csrf = null; // Token có thể cũ; không tự gửi lại POST.
    throw new Error("HTTP 403: cần tải CSRF token rồi thử lại có chủ đích");
  }
  return response;
}

async function login(username, password) {
  await loadCsrf(); // Có token ngay cả khi người dùng chưa có session.
  const form = new URLSearchParams({ username, password });
  const response = await protectedPost(
    "/api/login",
    form,
    "application/x-www-form-urlencoded;charset=UTF-8"
  );
  if (!response.ok) {
    throw new Error("Đăng nhập thất bại: " + response.status);
  }

  csrf = null;       // Spring Security có thể đã xóa token trước login.
  await loadCsrf();  // Bước bắt buộc trước POST nghiệp vụ tiếp theo.
}

async function postData(value) {
  const response = await protectedPost(
    "/api/data",
    JSON.stringify({ value }),
    "application/json"
  );
  if (!response.ok) {
    throw new Error("POST thất bại: " + response.status);
  }
  return response.json();
}

async function logout() {
  const response = await protectedPost("/api/logout");
  if (!response.ok) {
    throw new Error("Đăng xuất thất bại: " + response.status);
  }

  csrf = null;       // Token cũ đã bị xóa khi logout.
  await loadCsrf();  // Cần token mới để POST login lần sau.
}
~~~

Chạy lần lượt trong Console:

~~~javascript
await loadCsrf();
await login("learner", "local-demo-pass");
await postData("hello"); // {echo: "hello"}
await logout();
await login("learner", "local-demo-pass"); // Lần đăng nhập thứ hai vẫn hoạt động.
~~~

**Kỳ vọng:** GET /api/csrf trả 200; login đúng trả 204; POST /api/data trả 200 và JSON echo; logout trả 204. Không in hoặc hard-code token cụ thể vào ví dụ vì giá trị thay đổi theo request/session.

Trong ứng dụng thật, quản lý csrf trong một service dùng chung; sau khi login/logout thành công, chỉ cho phép các request thay đổi dữ liệu tiếp tục **sau khi** Promise loadCsrf() hoàn thành. Nếu mở nhiều tab, token của tab cũ có thể hết hiệu lực sau khi tab khác login/logout; khi gặp 403 hãy đồng bộ trạng thái và nạp lại token.

## 6. Phương án khác: SPA đọc cookie XSRF-TOKEN

Một số SPA (chẳng hạn các client có hỗ trợ XSRF cookie) nhận token bằng cookie **XSRF-TOKEN** và gửi giá trị cookie qua header **X-XSRF-TOKEN**. Ở Spring Security 6, token lấy trực tiếp từ cookie là **giá trị chưa che giấu**, trong khi handler XOR mặc định thường chờ dạng có che giấu; chỉ đổi sang CookieCsrfTokenRepository mà giữ nguyên handler có thể dẫn đến 403.

Nếu chọn kiểu cookie, **thay thế** cấu hình csrf của ví dụ trên bằng:

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
~~~

Đoạn trên cần import CookieCsrfTokenRepository và file handler sau:

**src/main/java/demo/SpaCsrfTokenRequestHandler.java**

~~~java
package demo;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);
        csrfToken.get(); // Buộc token/cookie sẵn sàng cho SPA.
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        return (StringUtils.hasText(header) ? plain : xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Trong **chế độ cookie**, SPA gọi GET /api/csrf để đảm bảo cookie XSRF-TOKEN đã được cấp (có thể bỏ qua nội dung JSON), sau đó **đọc cookie** và gửi chính giá trị đó trong header X-XSRF-TOKEN. Sau login/logout, gọi GET /api/csrf lại rồi đọc cookie mới. Không lấy token XOR trong JSON của ví dụ ở mục 4 để gửi qua nhánh header xử lý token thô của handler này; hai cách truyền phải được triển khai nhất quán.

Cookie XSRF-TOKEN dùng HttpOnly=false để JavaScript đọc được; cookie **phiên đăng nhập** vẫn nên HttpOnly, Secure trên HTTPS và được cấu hình SameSite phù hợp. Khả năng đọc cookie CSRF không cấp quyền đăng nhập cho JavaScript. Khi SPA và API khác origin, document.cookie của SPA không tự đọc được cookie thuộc origin của API; thường nên chọn luồng endpoint JSON hoặc thiết kế BFF thay vì giả định cookie có thể đọc chéo origin.

## 7. Vì sao phải refresh token sau login/logout?

**Sau login:** Spring Security thường thay đổi session identifier để chống session fixation và dùng CsrfAuthenticationStrategy để xóa CSRF token trước đó. Nếu SPA giữ token đã dùng trong POST /api/login rồi POST /api/data ngay, request sau có thể nhận **403 Forbidden** dù user đã đăng nhập thành công.

**Sau logout:** LogoutFilter thực hiện xóa ngữ cảnh xác thực/session và CsrfLogoutHandler xóa CSRF token. Nếu SPA tiếp tục gửi token trước logout để thực hiện POST login tiếp theo, request có thể bị 403. GET /api/csrf sau logout phải gọi được khi **anonymous**, vì lúc đó người dùng chưa xác thực.

Điểm cần phân biệt: **403 do CSRF token thiếu/sai/hết hiệu lực** khác với **401 vì chưa đăng nhập** và **403 vì không đủ quyền**. Đọc Network tab, response và log server trước khi kết luận nguyên nhân. Không sửa lỗi bằng cách tắt toàn bộ CSRF.

## 8. CORS, cookie và các môi trường triển khai

Ví dụ chính dùng **same origin** nên không cần bật CORS. Nếu SPA ở https://app.example.test và API ở https://api.example.test:

- Cần cấu hình CORS tại Spring Security/Web MVC với **origin cụ thể**, cho phép credentials, methods và header CSRF cần thiết; browser sẽ gửi preflight OPTIONS trong một số trường hợp.
- Dùng fetch credentials: "include" khi cần cookie xuyên origin; server phải trả Access-Control-Allow-Credentials: true cùng Access-Control-Allow-Origin là origin cụ thể, không phải ký tự *.
- CORS và SameSite giải quyết những phần khác nhau của bài toán: CORS kiểm soát JavaScript đọc phản hồi, SameSite ảnh hưởng việc browser gửi cookie, còn CSRF token chứng minh request thay đổi trạng thái hợp lệ.
- Cookie cross-site thường cần SameSite=None; Secure và HTTPS; chính sách chặn third-party cookies của browser có thể làm cách này không đáng tin. Cùng site khác origin cũng cần xem xét cookie, CORS và CSRF riêng.
- Giữ session cookie HttpOnly, dùng HTTPS, hạn chế XSS bằng escaping/CSP, kiểm soát redirect và không ghi CSRF token, password hoặc cookie xác thực vào log/analytics. CSRF token không thay thế phòng chống XSS.

## 9. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| POST /api/login trả 403 | Chưa GET /api/csrf; thiếu header hoặc cookie phiên không khớp | Bootstrap token, gửi đúng tên header và cùng cookie/session |
| Login trả 204, POST tiếp theo trả 403 | Vẫn dùng token trước login | GET /api/csrf và cập nhật token sau khi login thành công |
| Logout trả 403 | Gửi DELETE/GET theo giả định sai; thiếu CSRF ở POST logout | Dùng POST /api/logout với token hiện hành |
| Vừa logout xong không login lại được | Dùng token đã bị xóa lúc logout | GET /api/csrf sau logout và trước POST login |
| GET /api/csrf trả 401 | Endpoint bootstrap bị yêu cầu authenticated | Cho phép GET /api/csrf khi anonymous |
| Cookie XSRF-TOKEN có nhưng header X-XSRF-TOKEN bị 403 | Token thô từ cookie không khớp cơ chế XOR mặc định | Dùng handler SPA hỗ trợ cookie header hoặc chọn endpoint JSON nhất quán |
| Chỉ lỗi khi tách frontend và API | CORS, credentials, SameSite, cookie domain/path hoặc HTTPS | Kiểm tra Set-Cookie, Origin, preflight và Cookie request trong Network |
| 403 sau đổi tài khoản, hết phiên hoặc ở tab thứ hai | Session/token đã luân chuyển ở nơi khác | Làm mới token và trạng thái login; để người dùng quyết định gửi lại thao tác |

Không tự động gửi lại một POST có hiệu ứng nghiệp vụ sau lỗi 403: phản hồi lỗi có thể bị hiểu sai, hoặc request đã đi qua một phần hạ tầng. Với tác vụ có thể lặp, dùng idempotency key và quy tắc retry được thiết kế riêng.

## 10. Kiểm thử tối thiểu và checklist

Với ứng dụng chạy ở localhost:8080, kiểm tra bằng Network tab hoặc script ở mục 5:

1. GET /api/csrf khi chưa đăng nhập trả 200 và có headerName/token.
2. POST /api/login **không có CSRF header** phải bị từ chối (thường 403).
3. POST /api/login với CSRF token hợp lệ và đúng tài khoản trả 204.
4. Sau login gọi lại GET /api/csrf, rồi POST /api/data với token vừa nhận trả 200.
5. POST /api/logout với token hợp lệ trả 204; GET /api/me sau đó không còn là request đã xác thực (ở ví dụ này: 401).
6. GET /api/csrf khi đã logout trả 200; dùng token mới để POST /api/login được.
7. Thử bỏ cookie phiên, dùng token cũ, mở nhiều tab và hết session để xác nhận xử lý 403/401 đúng.
8. Xác nhận GET không đổi trạng thái, HTTPS/cookie policy/CORS đúng với môi trường thật.

**Quy tắc ghi nhớ:** SPA phải có CSRF token **trước mọi request đổi trạng thái**, bao gồm login và logout. Sau **login thành công** hoặc **logout thành công**, token trước sự kiện không còn đáng tin: **nạp lại CSRF token từ server rồi mới gửi thao tác tiếp theo**.