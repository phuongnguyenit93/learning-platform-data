# AccessDeniedHandler xử lý quyết định từ chối quyền truy cập

> Phạm vi: Spring Security cho ứng dụng **Servlet / Spring MVC**. Bài học nằm trong nhóm “Lỗi bảo mật”, tập trung vào cách trả phản hồi an toàn khi một yêu cầu bị từ chối và cách tránh các cấu hình khiến lỗi 403 bị xử lý sai. Với WebFlux, cơ chế tương ứng sử dụng `ServerAccessDeniedHandler», không dùng trực tiếp interface Servlet trong bài này.

## 1. Hiểu đúng trách nhiệm

**`AccessDeniedHandler» không quyết định người dùng có quyền hay không.** Quyết định ủy quyền (authorization) thường được tạo bởi `AuthorizationManager» thông qua `AuthorizationFilter» hoặc bởi bảo vệ ở mức phương thức, ví dụ `@PreAuthorize». Khi truy cập bị từ chối, Spring Security có thể ném `AccessDeniedException». `ExceptionTranslationFilter» chuyển ngoại lệ bảo mật thành hành vi HTTP phù hợp; đối với một người dùng đã xác thực đầy đủ nhưng thiếu quyền, nó gọi `AccessDeniedHandler».

Handler chịu trách nhiệm **trả lời việc từ chối**: đặt HTTP status, cung cấp nội dung lỗi an toàn, chuyển tiếp đến trang 403 nếu phù hợp, và bảo toàn các header cần thiết của giao thức. Handler **không** được thay cho luật phân quyền, không tự cấp quyền và không tiếp tục xử lý tài nguyên đã bị từ chối.

Các khái niệm cần phân biệt:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| `Authentication» / cơ chế đăng nhập | Xác minh danh tính, tạo đối tượng xác thực |
| `AuthorizationManager» / `AuthorizationFilter» | Kiểm tra luật truy cập URL và đưa ra kết quả cấp/từ chối quyền |
| Method Security (`@PreAuthorize»…) | Kiểm tra quyền ở ranh giới lời gọi phương thức |
| `AccessDeniedException» | Tín hiệu rằng truy cập bị từ chối |
| `ExceptionTranslationFilter» | Điều phối ngoại lệ bảo mật sang luồng yêu cầu xác thực hoặc luồng từ chối quyền |
| `AuthenticationEntryPoint» | Khởi động cơ chế xác thực khi thiếu hoặc không đủ trạng thái xác thực |
| `AccessDeniedHandler» | Xây dựng phản hồi cho trường hợp từ chối quyền cần trả 403 |

## 2. Luồng xử lý và ý nghĩa của 401/403

Một luồng thường gặp với request HTTP:

```text
GET /reports
    |
    v
SecurityFilterChain
    |
    +--> Authentication filters: đọc credential, thiết lập Authentication
    |
    +--> AuthorizationFilter / AuthorizationManager
               |
               +--> Đủ quyền ----------> tiếp tục vào controller
               |
               +--> Bị từ chối: AccessDeniedException
                            |
                            v
                  ExceptionTranslationFilter
                            |
              +-------------+----------------+
              |                              |
       Chưa xác thực /                 Đã xác thực đủ,
       cần xác thực thêm               nhưng thiếu quyền
              |                              |
      AuthenticationEntryPoint        AccessDeniedHandler
              |                              |
      401 hoặc redirect login                 403
```

`ExceptionTranslationFilter» bao quanh phần tiếp theo của chuỗi filter, phát hiện các ngoại lệ bảo mật và chọn đường xử lý. Trường hợp anonymous, hoặc trạng thái xác thực chưa đủ tin cậy theo cấu hình, một `AccessDeniedException» có thể dẫn đến `AuthenticationEntryPoint». Trường hợp đã xác thực nhưng thiếu authority cần thiết, nó được giao cho `AccessDeniedHandler».

| Tình huống | Phản hồi thường gặp | Bên xử lý |
| --- | --- | --- |
| Chưa gửi credential, gọi API yêu cầu đăng nhập với HTTP Basic | `401 Unauthorized» và `WWW-Authenticate» | `AuthenticationEntryPoint» |
| Gửi password sai bằng HTTP Basic | `401 Unauthorized» | Cơ chế xác thực / entry point |
| Đăng nhập là `VIEWER» nhưng URL yêu cầu `ADMIN» | `403 Forbidden» | `AccessDeniedHandler» |
| Đăng nhập là `ADMIN» và được cho phép | `200 OK» trong ví dụ | Controller |
| Form login chưa đăng nhập, truy cập trang cần xác thực | Thường redirect đến trang login | Entry point của form login |
| POST thiếu CSRF token khi bảo vệ CSRF đang bật | Thường 403, nhưng nguyên nhân là CSRF | Cơ chế xử lý `AccessDeniedException» của CSRF |

**Không suy ra rằng mọi 403 đều do thiếu role.** `CsrfFilter» có thể từ chối POST vì token sai/thiếu; reverse proxy, CORS, code ứng dụng hoặc các lớp khác cũng có thể tạo phản hồi bị từ chối. Việc chẩn đoán phải dựa vào filter và ngoại lệ thực tế.

Cũng không nên viết “cứ `AccessDeniedException» là 403”: `ExceptionTranslationFilter» còn kiểm tra trạng thái xác thực trước khi chọn entry point hay access-denied handler. Một ngoại lệ bị ứng dụng bắt và xử lý trước đó sẽ không nhất thiết đi tới handler của Spring Security.

## 3. Hợp đồng `AccessDeniedHandler»

Interface Servlet khai báo phương thức:

```java
void handle(
    HttpServletRequest request,
    HttpServletResponse response,
    AccessDeniedException accessDeniedException
) throws IOException, ServletException;
```

Ba đối số lần lượt là request đang bị từ chối, response sẽ được trả về và nguyên nhân bảo mật. Từ exception có thể ghi log nội bộ đã lọc thông tin nhạy cảm, nhưng **không trả nguyên văn `exception.getMessage()» cho client** vì có thể tiết lộ tên tài nguyên, cấu trúc quyền hoặc chi tiết nội bộ.

Khi không tùy biến, Spring Security Servlet sử dụng `AccessDeniedHandlerImpl» như một implementation mặc định phổ biến: gửi lỗi HTTP 403. Nếu được cấu hình `errorPage», nó **forward nội bộ** tới trang lỗi; `SecurityContextHolder» vẫn tồn tại trong request đó và ngoại lệ được lưu dưới request attribute `WebAttributes.ACCESS_DENIED_403». `forward» không giống `redirect»: redirect tạo một request mới và dễ dẫn tới status 302 thay vì 403 nếu thiết kế không cẩn thận.

Cách áp dụng tùy ứng dụng:

- REST API: giữ HTTP 403 và trả body JSON ngắn, nhất quán, không lộ thông tin.
- Giao diện HTML: hiển thị trang từ chối quyền bằng forward/renderer có kiểm soát; vẫn giữ ngữ nghĩa 403.
- OAuth2 Resource Server: tôn trọng chuẩn Bearer, đặc biệt `WWW-Authenticate» và `insufficient_scope»; tránh tùy tiện ghi đè handler chuyên dụng.
- Hệ thống nhiều tenant: quyết định tenant nào được truy cập phải nằm trong kiểm tra quyền; handler chỉ định dạng lỗi, không tiết lộ tenant/tài nguyên có tồn tại hay không.

## 4. Ví dụ Spring Boot / Spring Security 6 — chạy được trên Java 17+

Tạo một dự án Spring Boot 3.x sử dụng Java 17 trở lên, có dependency `spring-boot-starter-web» và `spring-boot-starter-security». Trong dự án Maven có thể chạy bằng `./mvnw spring-boot:run» (Windows: `mvnw.cmd spring-boot:run»). Ví dụ là ứng dụng thực hành với người dùng lưu trong bộ nhớ; tên và password chỉ dành cho máy cục bộ.

Tạo file `src/main/java/com/example/denied/SecurityDeniedDemoApplication.java»:

```java
package com.example.denied;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDeniedDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDeniedDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccessDeniedHandler jsonAccessDeniedHandler)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                // Cho phép dispatch nội bộ để ứng dụng render lỗi chuẩn.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/public").permitAll()
                .requestMatchers("/reports").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(errors ->
                errors.accessDeniedHandler(jsonAccessDeniedHandler)
            );
        return http.build();
    }

    @Bean
    AccessDeniedHandler jsonAccessDeniedHandler() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(
                "{\"error\":\"access_denied\",\"message\":\"Forbidden\"}"
            );
        };
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}demo123").roles("VIEWER").build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo123").roles("ADMIN").build();
        return new InMemoryUserDetailsManager(viewer, admin);
    }

    @RestController
    static class ReportController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public ok";
        }

        @GetMapping("/reports")
        String reports() {
            return "reports ok";
        }
    }
}
```

**Vì sao ví dụ đúng trách nhiệm?**

1. `.requestMatchers("/reports").hasRole("ADMIN")» thực hiện luật quyền: `hasRole("ADMIN")» tìm authority `ROLE_ADMIN». Đây là nơi quyết định quyền truy cập, không phải handler.
2. HTTP Basic làm rõ sự khác nhau giữa anonymous và đã đăng nhập. Không ghi đè entry point nên Spring Security xử lý yêu cầu xác thực theo giao thức Basic.
3. `.exceptionHandling(...accessDeniedHandler(...))» chỉ quyết định **cách phản hồi** khi truy cập bị từ chối và luồng xử lý chọn `AccessDeniedHandler».
4. Handler trả đúng 403, header `Content-Type: application/json», mã lỗi ổn định và thông điệp chung. Nó không trả stack trace, username, danh sách vai trò thiếu hay thông tin tài nguyên.
5. `.dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()» cho phép luồng dispatch lỗi của Servlet container diễn ra; điều này không tự cho phép người dùng truy cập `/reports».
6. `.anyRequest().denyAll()» đóng các đường dẫn chưa được khai báo, tránh vô tình mở tài nguyên mới. Hãy bổ sung rule tương ứng khi thêm endpoint hợp lệ.

**Giới hạn của ví dụ:** `{noop}» lưu password dạng rõ để dễ thử tại máy cục bộ và **không dùng trong production**; triển khai thực tế cần password encoder an toàn và kho danh tính phù hợp. Ví dụ chỉ kiểm tra GET, không tắt bảo vệ CSRF để “sửa nhanh” lỗi 403 khi POST.

### Chạy thử và đối chiếu HTTP status

Khởi động ứng dụng, sau đó chạy từng lệnh:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports
curl -i -u viewer:demo123 http://localhost:8080/reports
curl -i -u admin:demo123 http://localhost:8080/reports
```

Kết quả mong đợi từ các endpoint trên (chỉ liệt kê status/body ổn định của ví dụ; header kỹ thuật như `Date» có thể khác nhau):

| Lệnh | Status | Phần body chính |
| --- | --- | --- |
| `GET /public» không credential | 200 | `public ok» |
| `GET /reports» không credential | 401 | Body tùy entry point; có thử thách `WWW-Authenticate: Basic ...» |
| `GET /reports» với `viewer» | 403 | `{"error":"access_denied","message":"Forbidden"}» |
| `GET /reports» với `admin» | 200 | `reports ok» |

Chú ý: **401 chưa đăng nhập** đi qua cơ chế yêu cầu xác thực; **403 đã đăng nhập nhưng không có `ROLE_ADMIN»** đi qua custom `AccessDeniedHandler». Việc đổi handler không khiến viewer trở thành admin và không được để controller chạy sau khi đã từ chối.

## 5. Trang lỗi HTML và cách chuyển tiếp an toàn

Khi ứng dụng có HTML view và muốn dùng handler dựng sẵn:

```java
@Bean
AccessDeniedHandler htmlAccessDeniedHandler() {
    AccessDeniedHandlerImpl handler = new AccessDeniedHandlerImpl();
    handler.setErrorPage("/access-denied");
    return handler;
}
```

Đoạn này là **fragment cấu hình**, không phải file Java độc lập: cần import `org.springframework.security.web.access.AccessDeniedHandlerImpl» và đăng ký handler trong `exceptionHandling» giống ví dụ trước. Đường dẫn `/access-denied» phải có controller/view hợp lệ và đủ quyền truy cập cho dispatch `FORWARD» nếu bộ lọc phân quyền dispatch đó. Kiểm tra rằng ứng dụng vẫn trả HTTP 403 và không lặp vòng lỗi.

Một redirect như `response.sendRedirect("/login")» trong handler thường là sai cho trường hợp **đã đăng nhập nhưng thiếu quyền**: nó gây nhầm với 401, dễ tạo vòng chuyển hướng, và có thể biến phản hồi bị từ chối thành 302. Nếu thiết kế sản phẩm thật sự yêu cầu chuyển trang, hãy xem xét rõ ngữ nghĩa của browser và API; không dùng redirect để che giấu việc từ chối quyền.

## 6. Các lỗi bảo mật và lỗi tích hợp thường gặp

### Lỗi A — Kiểm tra quyền ở handler

**Sai tư duy:** “Trong `AccessDeniedHandler», kiểm tra role rồi cho request đi tiếp nếu đạt.” Handler được gọi **sau** khi quyết định từ chối đã xảy ra; lúc này không nên thay thế `AuthorizationManager», sửa `SecurityContext» hoặc gọi controller. Quy tắc thực sự phải nằm trong `authorizeHttpRequests», method security hoặc lớp kiểm soát quyền của nghiệp vụ, đặc biệt khi quyền phụ thuộc chủ sở hữu tài nguyên.

**Đúng:** cấu hình luật `hasRole», `hasAuthority» hay authorization manager phù hợp; handler chỉ viết response từ chối.

### Lỗi B — Luôn trả 403 cho mọi lỗi đăng nhập

**Sai:** gán một trang JSON 403 cho cả credential thiếu, password sai và role thiếu. Khách hàng HTTP có thể hiểu sai rằng người dùng đã xác thực thành công. Với HTTP Basic/Bearer, lỗi xác thực còn cần header thử thách theo giao thức.

**Đúng:** để `AuthenticationEntryPoint» xử lý luồng thiếu hoặc sai authentication; chỉ tùy biến `AccessDeniedHandler» cho trường hợp bị từ chối quyền tương ứng. Ở ứng dụng form login, entry point có thể trả redirect thay vì 401.

### Lỗi C — Trả `200 OK» kèm `{"success":false}»

HTTP status 200 có thể làm frontend, cache, API gateway hoặc thiết bị giám sát tưởng request thành công, kể cả khi body ghi thất bại. Cần trả status 403 ở mức HTTP, body chỉ bổ sung thông tin dễ hiểu.

### Lỗi D — Rò rỉ dữ liệu trong phản hồi lỗi

Không ghép trực tiếp `accessDeniedException.getMessage()», `Authentication», toàn bộ danh sách role, tên tenant, đường dẫn file, stack trace hay dữ liệu truy vấn vào response. Một người không có quyền không nên dùng lỗi để dò danh tính hoặc sự tồn tại của tài nguyên. Hãy dùng mã lỗi chung; nếu cần thông tin chẩn đoán thì ghi log nội bộ, loại bỏ token, mật khẩu và dữ liệu cá nhân.

### Lỗi E — Ghi response hai lần hoặc tiếp tục filter chain

Sau khi set status và ghi body, handler phải kết thúc phương thức. Không gọi `filterChain.doFilter» sau khi bị từ chối; cũng không `sendError» sau khi body đã commit, hoặc cố forward/redirect khi response đã bị commit. Những hành vi này có thể gây exception, body sai hoặc lộ tài nguyên.

### Lỗi F — Mặc định “mọi 403 đều thiếu quyền”

Nếu POST/PUT/DELETE trả 403 nhưng GET thành công, hãy kiểm tra CSRF trước khi sửa role. Khi bật CSRF, `CsrfFilter» có thể gọi access-denied handler cho token không hợp lệ. Không tắt CSRF chỉ để chuyển 403 thành 200; hãy cấu hình cách cung cấp/kiểm tra token đúng với loại client và trạng thái cookie/session.

Nếu browser gặp lỗi CORS trước khi thấy response 403, cần kiểm tra CORS/preflight riêng. Mã lỗi ở tab Network cũng có thể do reverse proxy hoặc bộ lọc khác trả về, không nhất thiết do handler.

### Lỗi G — Sai authority `ROLE_» và thứ tự luật

`hasRole("ADMIN")» ánh xạ mặc định tới `ROLE_ADMIN», còn `hasAuthority("ADMIN")» kiểm tra chính xác chuỗi `ADMIN». Nhầm lẫn hai cách này thường gây 403 dù người dùng tưởng đã có quyền. Ngoài ra, các matcher được xét theo thứ tự; quy tắc bao quát đặt trước có thể che mất quy tắc cụ thể.

### Lỗi H — Quên đặc tính của OAuth2 Bearer

Với Resource Server, Spring Security có `BearerTokenAccessDeniedHandler» để tạo phản hồi theo RFC 6750; khi token hợp lệ nhưng thiếu scope, header `WWW-Authenticate» có thể thể hiện `insufficient_scope». Thay toàn bộ bằng JSON handler tùy ý có thể làm mất metadata giao thức mà client cần. Khi cần custom body, hãy lựa chọn cách bảo toàn status/header/giao thức và kiểm thử cả token sai, token hết hạn, token hợp lệ thiếu scope.

### Lỗi I — Bắt ngoại lệ quá sớm hoặc nhầm stack

Một `@ControllerAdvice» bắt `AccessDeniedException» rồi đổi thành 200/500 có thể làm mất semantics 403 và không đi vào handler của filter như mong đợi. Ngoại lệ xảy ra ngoài phạm vi mà `ExceptionTranslationFilter» bao quanh (ví dụ tác vụ bất đồng bộ độc lập) cũng không mặc nhiên đi qua nó. Spring WebFlux dùng `ServerAccessDeniedHandler» và các web filter reactive; ví dụ Servlet ở trên không áp dụng trực tiếp cho WebFlux.

## 7. Kiểm thử hành vi thay vì chỉ nhìn cấu hình

Trong ví dụ trên, kiểm thử tối thiểu cần chứng minh đủ **ba trạng thái**: anonymous 401, authenticated không đủ quyền 403, authenticated đủ quyền 200. Kiểm tra thêm body JSON ở nhánh 403, `Content-Type», và chứng minh controller không bị thực thi nếu bị từ chối. Khi thêm POST, viết trường hợp CSRF riêng; khi bật OAuth2, thêm kiểm thử header Bearer.

Nếu dự án có `spring-security-test» và `spring-boot-starter-test», có thể tạo `src/test/java/com/example/denied/AccessDeniedBehaviorTest.java»:

```java
package com.example.denied;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessDeniedBehaviorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousMustAuthenticate() throws Exception {
        mvc.perform(get("/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerReceives403Json() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("viewer", "demo123")))
            .andExpect(status().isForbidden())
            .andExpect(content().json(
                "{\"error\":\"access_denied\",\"message\":\"Forbidden\"}"
            ));
    }

    @Test
    void adminCanReadReports() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("admin", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports ok"));
    }
}
```

Chạy `./mvnw test» (Windows: `mvnw.cmd test»). Ba test đều phải xanh trong ứng dụng và cấu hình minh họa. Đừng chỉ test số 403: nếu handler trả JSON đúng nhưng URL đã bị mở nhầm cho một số trường hợp, lỗ hổng cấp quyền vẫn tồn tại.

Khi cần chẩn đoán ở môi trường phát triển, bật logging phù hợp cho `org.springframework.security» ở DEBUG/TRACE trong thời gian ngắn, kiểm tra security filter chain, matcher thực sự áp dụng, trạng thái xác thực và nguyên nhân `AccessDeniedException». Không ghi token hay credential vào log sản xuất.

## 8. Quy trình xử lý một lỗi 403 ngoài thực tế

1. **Xác minh request**: method, URL, security filter chain nào áp dụng, endpoint có bị proxy/gateway từ chối trước ứng dụng hay không.
2. **Xác minh authentication**: anonymous, HTTP Basic, session hay Bearer; user đã được xác thực chưa; có trạng thái remember-me hoặc credential lỗi không.
3. **Xác minh authorization**: matcher và thứ tự của nó, role/authority thật sự, quyền theo tenant/resource, method security nếu có. Không suy luận quyền từ việc client ẩn/hiện nút.
4. **Xác minh nguồn ngoại lệ**: `AuthorizationFilter», method security, CSRF hay lớp ứng dụng khác. Đặc biệt phân biệt 403 do CSRF với 403 do thiếu role.
5. **Xác minh phản hồi**: HTTP status, `Content-Type», body, `WWW-Authenticate» nếu dùng Basic/Bearer, không rò rỉ chi tiết và không có bước xử lý tiếp theo sau khi đã từ chối.
6. **Kiểm thử hồi quy**: anonymous, người dùng thiếu quyền, người dùng đủ quyền; bổ sung cả request state-changing và tenant khác nếu ứng dụng có.

## 9. Những điều cần nhớ

- **Authorization quyết định cho phép hay từ chối; `AccessDeniedHandler» trình bày kết quả từ chối.**
- **401/entry point** thường liên quan yêu cầu xác thực; **403/access-denied handler** thường là đã xác thực nhưng không có quyền. Trạng thái thực tế phụ thuộc cơ chế xác thực và loại exception.
- Handler phải giữ phản hồi an toàn, không để lộ dữ liệu, không biến 403 thành 200 và không tiếp tục xử lý tài nguyên sau khi deny.
- Phân biệt 403 do authority, CSRF, dispatch hoặc thành phần ngoài ứng dụng trước khi sửa cấu hình.
- Với Resource Server, giữ các semantics HTTP Bearer; không đánh mất `WWW-Authenticate» chỉ vì muốn một định dạng JSON chung.

## Tài liệu tham khảo chính thức

- Spring Security, Servlet Architecture — Handling Security Exceptions: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security, Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security, CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- `AccessDeniedHandlerImpl» Java API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandlerImpl.html
- Spring Security, OAuth2 Bearer Token Failure: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html