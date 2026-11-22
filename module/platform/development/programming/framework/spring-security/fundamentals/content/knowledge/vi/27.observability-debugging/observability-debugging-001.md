# Đọc log khởi động để hiểu cấu hình và chuỗi bộ lọc được tạo

## 1. Vì sao log khởi động quan trọng trong Spring Security?

Trong Spring Security, việc nhìn thấy một đoạn cấu hình Java như `.httpBasic(...)`, `.formLogin(...)` hay `.authorizeHttpRequests(...)` **chưa đủ** để biết request cuối cùng sẽ đi qua những bộ lọc nào. Mỗi `SecurityFilterChain` được xây dựng từ nhiều cấu hình, matcher, thứ tự và mặc định của framework. Từng chuỗi có thể được áp dụng cho một tập URL khác nhau.

Khi ứng dụng Spring Boot khởi động, Spring Security có thể ghi các dòng DEBUG mô tả các `SecurityFilterChain` đã được tạo, ví dụ các dòng bắt đầu bằng:

```text
DefaultSecurityFilterChain : Will secure ... with [...]
```

Dòng này là một **bằng chứng cấu hình lúc khởi động**: nó cho biết chuỗi bảo mật đã được xây dựng, có `RequestMatcher` nào và danh sách các `Filter` theo thứ tự được đặt trong chuỗi. Khi thấy 401, 403, redirect tới login sai hoặc một custom filter không chạy, đây là một trong những nơi nên xem đầu tiên.

Mục tiêu học tập là trả lời được năm câu hỏi:

1. Có bao nhiêu `SecurityFilterChain` được tạo cho ứng dụng Servlet?
2. Mỗi chuỗi có **matcher phạm vi** nào, ví dụ `/api/**` hay mọi request?
3. Bên trong mỗi chuỗi có những filter nào, đặc biệt là xác thực, CSRF và phân quyền?
4. Khi một URL được gọi, **chuỗi nào thực sự được chọn**, và những filter nào được gọi?
5. Thông tin nào **không thể kết luận chỉ từ log khởi động** mà phải kiểm tra cấu hình hoặc thử request?

**Phạm vi:** ví dụ chính dùng **Java 17+, Spring Boot 3.x / Spring Security 6.x, Spring MVC trên Servlet**. Với Spring Boot 4.x / Spring Security 7.x, tên, tập hợp hoặc cách in filter có thể khác. Với WebFlux reactive, chuỗi là `SecurityWebFilterChain` gồm `WebFilter`; không dùng danh sách Servlet filter trong bài này để suy đoán trực tiếp về reactive stack.

## 2. Bức tranh kiến trúc trước khi đọc log

Spring Security Servlet thường nằm giữa Servlet container và `DispatcherServlet`.

```text
HTTP client
   |
   v
Servlet container / Servlet FilterChain
   |
   v
DelegatingFilterProxy ("springSecurityFilterChain")
   |
   v
FilterChainProxy
   |---- SecurityFilterChain #1: matcher /api/**
   |        [security Filter A, security Filter B, ...]
   |
   |---- SecurityFilterChain #2: matcher any request
            [security Filter C, security Filter D, ...]
   |
   v
DispatcherServlet -> Controller -> Service
```

Các vai trò khác nhau cần được nhận diện:

| Thành phần | Vai trò | Khi xem log |
| --- | --- | --- |
| `DelegatingFilterProxy` | Cầu nối từ bộ lọc của Servlet container tới Spring Bean `springSecurityFilterChain` | Không phải mỗi dòng DEBUG về filter là một filter do container đăng ký độc lập |
| `FilterChainProxy` | Quản lý và chọn `SecurityFilterChain` cho từng request | Dòng `Securing GET /...` hoặc TRACE về việc gọi từng filter khi có request |
| `SecurityFilterChain` | Chứa một matcher phạm vi và danh sách security filter | Dòng DEBUG của `DefaultSecurityFilterChain` lúc tạo chuỗi |
| `RequestMatcher` | Kiểm tra request có thuộc phạm vi một chuỗi hay không | Chuỗi đầu tiên khớp sẽ được dùng |
| `HttpSecurity` | DSL Java dùng để xây các `SecurityFilterChain` trong Servlet | Các lệnh `.formLogin` / `.httpBasic` / `.csrf` dẫn tới những filter khác nhau |
| `AuthorizationFilter` | Kiểm tra quyết định phân quyền cho request | Sự hiện diện cho biết có filter phân quyền, **không cho biết toàn bộ luật role** |
| `ExceptionTranslationFilter` | Chuyển nhiều ngoại lệ xác thực/phân quyền sang entry point hoặc access-denied handler | Có thể giải thích vì sao lỗi bảo mật thành 401/403/redirect |
| `SecurityContextHolderFilter` | Quản lý ngữ cảnh bảo mật cho request trong pipeline được cấu hình | Không phải bằng chứng người gọi đã đăng nhập |

Một ứng dụng có thể có **nhiều** `SecurityFilterChain` trong cùng `FilterChainProxy`. Các chuỗi được thử theo thứ tự; **chuỗi đầu tiên có matcher khớp sẽ xử lý request**. Các chuỗi không tự động “chạy nối tiếp” chỉ vì nhiều bean cùng tồn tại.

### Hai loại thứ tự đừng nhầm lẫn

- **Thứ tự giữa các SecurityFilterChain:** do `@Order` và độ ưu tiên các bean quyết định. Nó ảnh hưởng chuỗi nào được chọn cho một URL.
- **Thứ tự filter bên trong một SecurityFilterChain:** do Spring Security và cách thêm custom filter định vị. Nó ảnh hưởng thời điểm khôi phục security context, CSRF, xác thực và phân quyền.

`@Order(1)` trên một bean `SecurityFilterChain` **không** có nghĩa filter đầu tiên trong chuỗi đó cũng mang thứ tự 1. Tương tự, `AuthorizationFilter` xuất hiện cuối danh sách không cho phép kết luận tất cả controller chắc chắn đã được bảo vệ đúng cách.

## 3. Bật đúng cấp độ log lúc khởi động

### 3.1. Cách đơn giản: DEBUG cho Spring Security

Trong `src/main/resources/application.properties` của dự án Spring Boot:

```properties
logging.level.org.springframework.security=DEBUG
```

Khởi động lại ứng dụng. Cấp `DEBUG` cho package này thường hiển thị các dòng xây dựng `DefaultSecurityFilterChain` cũng như một số log xử lý request. Đây là cách có chủ đích khi bạn muốn biết cấu hình bảo mật nào thực sự đã được tạo.

Nếu chỉ muốn thu hẹp việc in chuỗi filter lúc startup, có thể dùng:

```properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
```

Dòng thứ hai chỉ bật logger lớp xây dựng filter chain, **không tương đương** với việc bật toàn bộ `org.springframework.security` DEBUG. Nếu file logging khác có quy tắc chặn hoặc cấu hình appender, cần kiểm tra thêm logging system.

### 3.2. Lấy log sâu hơn khi có request: TRACE

Khi cần thấy từng filter được gọi cho một request Servlet:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Hoặc để điều tra rộng hơn trong môi trường **development/test**:

```properties
logging.level.org.springframework.security=TRACE
```

Ở TRACE, số lượng log tăng rất nhanh, có thể xuất hiện thông tin đường dẫn, principal, header hoặc bối cảnh bảo mật tùy cấu hình/version. **Không để DEBUG/TRACE rộng hoạt động kéo dài trong production** khi chưa đánh giá kiểm soát dữ liệu, quyền xem log, thời hạn lưu và chi phí vận hành. Tuyệt đối không chép mật khẩu, access token, cookie, session ID hay body nhạy cảm vào log bằng custom filter để “dễ debug”.

### 3.3. Vì sao `--debug` của Spring Boot chưa chắc đủ?

Lệnh:

```bash
./gradlew bootRun --args='--debug'
```

bật **debug mode** của Spring Boot, tập trung vào một số logger lõi và có thể hiển thị **Condition Evaluation Report**. Đây không phải cam kết bật DEBUG cho **mọi** logger trong `org.springframework.security`. Muốn kiểm tra danh sách filter, hãy đặt logger `DefaultSecurityFilterChain` hoặc `org.springframework.security` tường minh. Condition report trả lời “tại sao cấu hình auto-configuration được áp dụng/không áp dụng”, khác với câu hỏi “chuỗi security filter nào đã được tạo”.

Có thể bật logging bằng đối số ứng dụng thay vì sửa file:

```bash
./gradlew bootRun --args='--logging.level.org.springframework.security=DEBUG'
```

Với ứng dụng đã đóng gói:

```bash
java -jar build/libs/security-chain-lab.jar \
  --logging.level.org.springframework.security=DEBUG
```

Tên JAR ở đây là **ví dụ tên artefact**, phụ thuộc cấu hình build của dự án. Để chạy dự án vừa sinh bằng Gradle Wrapper, cách `./gradlew bootRun` là đơn giản nhất.

## 4. Ví dụ đầy đủ: tạo hai chuỗi bảo mật có phạm vi khác nhau

Ta tạo một ứng dụng Spring Boot có:

- `/api/**`: dùng **HTTP Basic**, `GET /api/ping` công khai, `GET /api/admin` yêu cầu role `ADMIN`. Không dùng form login trong chuỗi API.
- Phần web còn lại: dùng **form login**, `GET /web/public` công khai, `GET /web/admin` yêu cầu role `ADMIN`, các URL khác yêu cầu đăng nhập.
- Hai tài khoản trong bộ nhớ để thử luồng: `reader` với role USER và `admin` với role ADMIN.

Điểm cần quan sát là **sự khác nhau trong danh sách filter lúc ứng dụng khởi động**, không phải xây dựng một ứng dụng web phức tạp.

### 4.1. Khởi tạo dự án

Tạo dự án bằng Spring Initializr với **Java 17+**, **Spring Boot 3.x**, dependencies **Spring Web** và **Spring Security**, chọn Gradle.

Sắp xếp tệp Java:

```text
src/main/java/demo/filterlogs/SecurityChainLogApplication.java
```

Toàn bộ mã dưới đây nằm trong **một tệp Java**; biên dịch/chạy trong dự án có các dependency Spring Boot 3.x/Security 6.x. Không thể dùng `javac` độc lập nếu không có classpath Spring.

```java
package demo.filterlogs;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityChainLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainLogApplication.class, args);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/ping").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/web/public", "/login", "/error"
                ).permitAll()
                .requestMatchers("/web/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class DemoEndpoints {

        @GetMapping("/api/ping")
        public Map<String, String> ping() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/admin")
        public Map<String, String> apiAdmin() {
            return Map.of("message", "api-admin-ok");
        }

        @GetMapping(
            value = "/web/public",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String webPublic() {
            return "<!doctype html><html><meta charset=\"UTF-8\">"
                + "<body><h1>Trang cong khai</h1></body></html>";
        }

        @GetMapping(
            value = "/web/admin",
            produces = MediaType.TEXT_HTML_VALUE
        )
        public String webAdmin() {
            return "<!doctype html><html><meta charset=\"UTF-8\">"
                + "<body><h1>Trang quan tri</h1></body></html>";
        }
    }
}
```

**Giải thích những lựa chọn quan trọng:**

1. `@Order(1)` đưa chuỗi API lên trước. `securityMatcher("/api/**")` giới hạn **toàn bộ chuỗi**, không chỉ một rule phân quyền.
2. `@Order(2)` đưa chuỗi web sau. Chuỗi web không khai báo `securityMatcher(...)`, nên matcher mặc định của nó là **mọi request chưa bị chuỗi trước chọn**.
3. `requestMatchers(...)` **bên trong `authorizeHttpRequests(...)`** chọn rule phân quyền sau khi chuỗi đã được chọn. Nó **không** làm `FilterChainProxy` tạo thêm chuỗi độc lập.
4. `httpBasic(...)` trên API thêm cơ chế xác thực Basic; `formLogin(...)` trên web thêm cơ chế form login. Vì vậy log filter của hai chuỗi có dấu hiệu khác nhau.
5. `SessionCreationPolicy.STATELESS` và `NullRequestCache` làm ví dụ API không dựa vào HTTP session/request cache; điều đó **không tự động tắt CSRF**. Ở đây mọi lệnh kiểm tra API đều là GET.
6. `hasRole("ADMIN")` theo quy ước mặc định yêu cầu authority `ROLE_ADMIN`, còn `reader` chỉ có `ROLE_USER`.
7. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` sinh mật khẩu được mã hóa đúng chuẩn cấu hình ví dụ. Tài khoản chỉ dùng cho `localhost`. Trong mạng thật, HTTP Basic phải đi qua HTTPS vì Base64 không mã hóa credentials.

### 4.2. Bật log và khởi động

Trong `src/main/resources/application.properties` thêm:

```properties
spring.application.name=security-chain-lab
logging.level.org.springframework.security=DEBUG
```

Khởi động từ thư mục dự án:

```bash
./gradlew bootRun
# Trên Windows PowerShell:
# .\gradlew.bat bootRun
```

Bản dựng Spring Initializr có thể sử dụng Maven thay vì Gradle; khi đó dùng wrapper tương ứng. Không chạy `javac SecurityChainLogApplication.java` nếu không đưa đầy đủ dependency Spring vào classpath.

Sau khi startup, tìm logger `DefaultSecurityFilterChain` hoặc cụm **`Will secure`** trong console. Bạn cần thấy **hai thông báo cấu hình chuỗi filter**, một cho `/api/**`, một cho matcher mặc định.

### 4.3. Đọc log mẫu cho hai chuỗi

Tài liệu Spring Security minh họa dòng DEBUG thuộc `org.springframework.security.web.DefaultSecurityFilterChain` với cấu trúc:

```text
DEBUG o.s.s.web.DefaultSecurityFilterChain :
Will secure any request with [DisableEncodeUrlFilter, WebAsyncManagerIntegrationFilter, SecurityContextHolderFilter, HeaderWriterFilter, CsrfFilter, LogoutFilter, UsernamePasswordAuthenticationFilter, DefaultLoginPageGeneratingFilter, DefaultLogoutPageGeneratingFilter, BasicAuthenticationFilter, RequestCacheAwareFilter, SecurityContextHolderAwareRequestFilter, AnonymousAuthenticationFilter, ExceptionTranslationFilter, AuthorizationFilter]
```

Đây là **dòng ví dụ minh họa từ tài liệu kiến trúc Spring Security**, không phải stdout dự đoán nguyên văn cho mã ở mục 4. Trong chương trình của chúng ta, thường xuất hiện **hai dòng riêng**, có thể mô tả như sau:

```text
[API chain] WEB matcher: /api/**
  Authentication: HTTP Basic
  Authorization: AuthorizationFilter
  CSRF: can contain CsrfFilter under defaults

[Web chain] WEB matcher: any request
  Authentication: form login
  Authorization: AuthorizationFilter
  CSRF: can contain CsrfFilter under defaults
```

Đoạn thứ hai là **bảng ghi chú cách đọc**, không phải định dạng text mà framework cam kết in. Danh sách filter cụ thể khác nhau tùy phiên bản Spring Security, thành phần auto-configuration, những tính năng được bật, cách builder được sử dụng và custom filter được cài. **Không so sánh log bằng một danh sách tên filter cố định lấy từ một bài viết khác.**

### 4.4. Cách phân tích từng phần của dòng Will secure

Một dòng startup DEBUG có thể được tách thành:

```text
DEBUG | DefaultSecurityFilterChain | Will secure | matcher | with | [filters...]
```

- **DEBUG**: cấp log. Nếu chỉ để INFO, dòng chi tiết này có thể không xuất hiện dù Security vẫn đang bảo vệ request.
- **DefaultSecurityFilterChain**: lớp báo rằng một chuỗi filter đã được xây dựng; nó không phải tên của controller hay URL.
- **Will secure**: chuỗi này dự kiến được dùng cho những request mà matcher của nó nhận.
- **Matcher**: có thể được hiển thị như `any request`, một mẫu `/api/**` hoặc biểu diễn kiểu `Mvc [pattern='...']` / một tổ hợp matcher. Cú pháp `toString()` của matcher có thể khác theo phiên bản.
- **with [filters]**: danh sách các security filter trong thứ tự cấu hình. Đây là phần cần đọc để biết những bước xác thực/CSRF/phân quyền nào hiện diện.
- **Tên filter**: cho biết loại cơ chế được cài trong chuỗi, **không** in hết mọi tham số, biểu thức role, policy hoặc trạng thái của một request cụ thể.

Một dòng `Will secure any request` của **chuỗi fallback** **không** đồng nghĩa nó luôn xử lý mọi URL. Nếu `/api/**` đã khớp chuỗi đầu, chuỗi fallback không chạy cho request đó. Muốn biết một URL cụ thể đang chọn chuỗi nào, xem `@Order`, `securityMatcher` và log **runtime** khi phát request.

## 5. Nhận diện vai trò của các filter thường gặp

Dưới đây là “từ điển đọc log” để giải thích nhanh các tên filter **khi chúng thực sự có mặt** trong chuỗi:

| Filter | Ý nghĩa quan sát | Điều không nên suy ra |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Thiết lập/quản lý security context cho request | Không chứng minh người gọi đã được xác thực |
| `CsrfFilter` | Có bước kiểm tra CSRF tương ứng cấu hình | Không chứng minh mọi endpoint đều bị yêu cầu token CSRF; cần xét method/ignoring matcher |
| `HeaderWriterFilter` | Có cơ chế thêm security response headers | Không bảo đảm mọi header đều luôn xuất hiện (ví dụ HSTS phụ thuộc kết nối an toàn/cấu hình) |
| `CorsFilter` | Có cơ chế xử lý CORS trong chuỗi này khi được cấu hình | Không khẳng định mọi origin đều được phép |
| `LogoutFilter` | Có chức năng logout filter | Không chứng minh endpoint/logout URL của mọi chuỗi đều giống nhau |
| `UsernamePasswordAuthenticationFilter` | Cơ chế nhận xác thực username/password qua form | Không cho biết login page/custom failure handler nào đã được cấu hình |
| `DefaultLoginPageGeneratingFilter` | Có thể có trang login mặc định của Spring Security | Không chứng minh login form custom đang hoạt động |
| `BasicAuthenticationFilter` | Có xử lý HTTP Basic credentials | Không có nghĩa mọi URL trong chuỗi bắt buộc phải đăng nhập |
| `BearerTokenAuthenticationFilter` | Có đường xác thực Bearer token khi cấu hình resource server Servlet phù hợp | Không chứng minh chữ ký, issuer, audience và từng scope đã được kiểm thử |
| `AnonymousAuthenticationFilter` | Có thể thiết lập principal anonymous khi chưa xác thực | Không được coi anonymous là một người dùng đã xác minh |
| `RequestCacheAwareFilter` | Có logic liên quan saved request/request cache | Không tự chứng minh chuỗi đang tạo session hoặc request cache có dữ liệu |
| `ExceptionTranslationFilter` | Có cơ chế chuyển ngoại lệ bảo mật sang authentication entry point/access-denied handler | Không cho biết tất cả trường hợp sẽ trả 401, 403 hay 302 |
| `AuthorizationFilter` | Có kiểm tra quyết định phân quyền request | Không cho biết rule `permitAll`, `hasRole`, owner/tenant đã đúng hay không |

Danh sách chỉ mô tả **những filter điển hình**; chuỗi thực tế có thể có nhiều filter khác, filter bị bỏ qua hoặc những filter mới của phiên bản/framework khác. Tên filter phải được hiểu trong **đúng chuỗi** đã chọn, không gom danh sách của nhiều chuỗi thành một.

### Vì sao có filter mà endpoint vẫn trả 200 cho anonymous?

Sự có mặt của `AuthorizationFilter` không ngăn các rule như:

```java
.requestMatchers("/api/ping").permitAll()
```

Tương tự, `BasicAuthenticationFilter` có mặt không buộc mọi request phải có Authorization header: endpoint công khai vẫn có thể hoạt động khi không có credentials. **Filter được cài** và **chính sách áp dụng cho URL** là hai câu hỏi khác nhau.

### Vì sao thấy CsrfFilter nhưng GET vẫn thành công?

CSRF mặc định thường tập trung vào các HTTP method thay đổi trạng thái. Với GET thông thường, thiếu token không nhất thiết gây 403. Khi thêm POST/PUT/DELETE, phải kiểm tra riêng xử lý CSRF. Không tắt CSRF chỉ vì nhìn thấy `CsrfFilter` trong danh sách hoặc vì request POST thiếu token bị 403; cần đánh giá mô hình xác thực và nguồn credential có tự đính kèm hay không.

## 6. Dùng request thực để xác minh suy luận từ log

Sau khi ứng dụng chạy, thử các request. Trên PowerShell dùng `curl.exe` thay vì alias `curl` của một số phiên bản PowerShell.

```bash
# API công khai, không Basic auth
curl -i http://localhost:8080/api/ping

# API quản trị, thiếu Basic credentials
curl -i http://localhost:8080/api/admin

# API quản trị, đã xác thực nhưng chỉ có USER
curl -i -u reader:reader123 \
  http://localhost:8080/api/admin

# API quản trị, người có ROLE_ADMIN
curl -i -u admin:admin123 \
  http://localhost:8080/api/admin

# URL web quản trị, chưa có form-login session
curl -i http://localhost:8080/web/admin

# URL web công khai
curl -i http://localhost:8080/web/public
```

Dấu `\` nối dòng ở đây là cú pháp Bash. Với PowerShell, đặt mỗi lệnh trên một dòng; nếu dùng `curl.exe` sẽ giữ cú pháp curl.

Kết quả cần đối chiếu:

| Yêu cầu | Chuỗi được chọn | Status điển hình | Ý nghĩa |
| --- | --- | --- | --- |
| `GET /api/ping` không auth | `/api/**` (Order 1) | **200** | `permitAll` trong chuỗi API |
| `GET /api/admin` không auth | `/api/**` | **401** + `WWW-Authenticate` | Cơ chế HTTP Basic cần xác thực |
| `GET /api/admin` với `reader` | `/api/**` | **403** | Đã xác thực, thiếu role ADMIN |
| `GET /api/admin` với `admin` | `/api/**` | **200** | Có role ADMIN |
| `GET /web/admin` không session | Fallback web (Order 2) | **302** tới `/login` | Form login yêu cầu đăng nhập |
| `GET /web/public` không session | Fallback web | **200** | URL web công khai |

Khi dùng `curl -i` không kèm `-L`, ta nhìn được **status đầu tiên**. Nếu dùng `curl -L` hoặc trình duyệt tự theo redirect, có thể thấy trang `/login` trả 200 và tưởng tài nguyên quản trị được phép, trong khi request gốc đã nhận 302.

Mở `http://localhost:8080/web/admin` trong trình duyệt ẩn danh; trình duyệt sẽ được chuyển tới form login mặc định. Sau khi đăng nhập bằng `reader`, vì thiếu ADMIN, tài nguyên `/web/admin` sẽ bị từ chối 403. Với tài khoản `admin` trong phiên mới, tài nguyên được cho phép. Lần đăng nhập form thật có thể cần cookie session và CSRF token; không cố gửi POST `/login` bằng curl không token rồi suy rằng tài khoản sai.

## 7. Đọc log khi request chạy: DEBUG khác TRACE thế nào?

**Log startup** cho biết **danh sách filter của chuỗi đã tạo**. **Log runtime** cho biết **đang xử lý request nào, filter nào đã được gọi và tại đâu request bị chặn**. Hai loại này bổ sung cho nhau.

Với cấu hình:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

khi có request, bạn có thể thấy dạng log:

```text
DEBUG o.s.security.web.FilterChainProxy : Securing GET /api/admin
TRACE o.s.security.web.FilterChainProxy : Invoking DisableEncodeUrlFilter (1/...)
TRACE o.s.security.web.FilterChainProxy : Invoking SecurityContextHolderFilter (.../...)
TRACE o.s.security.web.FilterChainProxy : Invoking BasicAuthenticationFilter (.../...)
TRACE o.s.security.web.FilterChainProxy : Invoking AuthorizationFilter (.../...)
```

**Các dòng trên được rút gọn có chủ đích để minh họa cấu trúc**, không phải log thực tế đã chạy, không phải danh sách filter đầy đủ và không cam kết đúng số `(n/N)` của một phiên bản. Nếu cần đếm chính xác, đọc TRACE do phiên bản ứng dụng của bạn thực sự in ra.

Khi bật TRACE toàn package `org.springframework.security`, log có thể thể hiện cả điểm phát sinh lỗi, ví dụ:

```text
DEBUG FilterChainProxy : Securing POST /...
TRACE FilterChainProxy : Invoking CsrfFilter (n/N)
DEBUG CsrfFilter : Invalid CSRF token found for ...
DEBUG AccessDeniedHandlerImpl : Responding with 403 status code
```

Đoạn thứ hai cũng là **dạng minh họa được lược bỏ**, không phải bằng chứng ứng dụng ví dụ nhận POST theo URL đó. Nguyên tắc điều tra là theo dõi request cụ thể qua `FilterChainProxy`, xem filter cuối cùng đã được gọi, rồi đọc logger sở hữu quyết định 401/403. Nếu `CsrfFilter` chặn trước, đừng quy trách nhiệm ngay cho `hasRole`.

### Quy trình đọc một request lỗi

1. Ghi **method + path + status** thực tế từ `curl -i`/DevTools.
2. Kiểm tra **SecurityFilterChain** khớp URL theo thứ tự, không chỉ tìm bean có tên gần giống.
3. Xem log `FilterChainProxy` có bắt đầu bảo vệ request bằng `Securing ...` không.
4. Ở TRACE, đọc **filter được gọi tới điểm dừng** và thông điệp lỗi liên quan.
5. Nếu là 401, xem authentication entry point, credentials và filter xác thực tương ứng.
6. Nếu là 403, phân biệt CSRF, authorization hoặc rule trong service.
7. Nếu là 302, kiểm tra form login, request cache và HTTP redirect đến trang nào.
8. Sửa **quy tắc nguồn** (matcher, role, CSRF, chain order), khởi động lại nếu cần và kiểm tra status lẫn log mới.

**Cảnh báo:** một log `Secured GET /...`, nếu xuất hiện, có ý nghĩa request đã đi qua một đoạn bảo mật theo thông điệp logger; nó không tự chứng minh dữ liệu trả về không lộ tài nguyên của người khác. BOLA/IDOR và phân quyền ở service vẫn phải kiểm thử riêng.

## 8. Đọc nhiều chain: ưu tiên, matcher và những lỗi cấu hình thường gặp

### 8.1. Có hai dòng Will secure nhưng request vẫn đi sai chain

Giả sử bạn viết một chain tổng quát ở `@Order(1)`:

```java
@Bean
@Order(1)
SecurityFilterChain broadChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đây là **ví dụ sai về thứ tự ưu tiên nếu bạn định đặt thêm chuỗi API riêng sau nó**. Vì chuỗi trên mặc định khớp mọi request và được xét trước, request `/api/admin` sẽ không đi tới một chain API ở `@Order(2)`. Log startup có thể vẫn in **cả hai chuỗi**, nhưng điều đó không có nghĩa cả hai đều được chọn cho request.

Cách sửa: đặt `securityMatcher("/api/**")` ở chain API và cho nó `@Order(1)`; đặt fallback `any request` phía sau. Đừng nhìn mỗi số lượng dòng `Will secure` rồi kết luận matcher đã đúng.

### 8.2. Nhầm securityMatcher và requestMatchers

```java
// Đây chỉ là các luật bên trong một chain:
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

Đoạn này **không tự tạo SecurityFilterChain riêng cho API** và không biến cơ chế form login thành Basic chỉ cho `/api/**`. Muốn hai bộ filter khác nhau, phải có hai bean `SecurityFilterChain` và định nghĩa `securityMatcher(...)` phù hợp cho chain API.

### 8.3. Không có fallback, một số URL không đi qua Spring Security

Giả sử ứng dụng chỉ đăng ký:

```java
http.securityMatcher("/api/**");
```

và không có SecurityFilterChain nào khác khớp `/admin`. `FilterChainProxy` có thể **không áp dụng các security filter Spring Security** cho `/admin`. Đó là rủi ro nghiêm trọng nếu ứng dụng còn có các endpoint khác. Dòng startup `Will secure /api/**` **không chứng minh** mọi request của server được bảo vệ. Khi thiết kế nhiều chain, nên có fallback không đặt `securityMatcher(...)` (hoặc một phạm vi fallback bao quát có chủ đích) để kiểm soát những URL còn lại.

Không nhầm việc **Spring Security bỏ qua** với việc **rule `permitAll()` cho phép**: `permitAll` vẫn chạy trong một chain và các security filter khác có thể áp dụng; bỏ qua toàn bộ filter khiến các tính năng bảo vệ của chuỗi đó không được chạy.

### 8.4. Có BasicAuthenticationFilter nhưng API vẫn chuyển tới login

Nếu startup log của **chuỗi API đã chọn** lại cho thấy form login và custom entry point, kết quả có thể là 302 thay vì 401. Cũng có thể request bị chain web xử lý do matcher sai. Hãy kiểm tra đồng thời:

- `@Order` và `securityMatcher(...)` của từng bean;
- `FilterChainProxy` chọn chain nào khi request thật chạy;
- `AuthenticationEntryPoint` nào được kích hoạt ở endpoint;
- có filter/exception handling tùy chỉnh hay không.

Không nên giải quyết bằng cách luôn trả 401 cho **trang web dùng form login**, vì hành vi 302 tới trang đăng nhập là chủ đích hợp lệ cho trình duyệt.

### 8.5. Không thấy custom filter trong danh sách

Nếu bạn dùng:

```java
http.addFilterBefore(
    myAuditFilter,
    org.springframework.security.web.authentication
        .UsernamePasswordAuthenticationFilter.class
);
```

đây là đoạn **minh họa cách gắn filter**, không phải phần của chương trình mục 4; `myAuditFilter` phải là một filter instance thực tế được tạo trong ứng dụng. Nếu khởi động với DEBUG nhưng không thấy custom filter trong chuỗi mong muốn, kiểm tra:

- Lệnh `addFilterBefore/After/At` có được gọi **trên HttpSecurity của đúng bean chain** không?
- Custom filter có nằm trong bean SecurityFilterChain được `http.build()` trả về không?
- Có đặt thứ tự filter so với lớp tham chiếu phù hợp không?
- Có dùng một filter vừa là Servlet `@Component`, vừa add vào Spring Security chain gây **đăng ký hai lần** không?
- Có hai chain và bạn đang xem dòng của chain còn lại không?

Tên custom filter hiển thị trong log có thể là lớp cụ thể hoặc proxy, nên đừng tìm một chuỗi chữ quá cứng nhắc. Nếu có mặt lúc startup mà không được gọi khi request chạy, cần xem matcher/chain selection hoặc điểm xử lý sớm dừng pipeline.

## 9. Khi nào log khởi động KHÔNG đủ để khẳng định cấu hình đúng?

Một danh sách filter là **ảnh chụp cấu trúc tại thời điểm khởi động**, không phải bản mô tả hoàn chỉnh mọi chính sách. Ví dụ:

| Muốn xác minh | Startup DEBUG có đủ? | Cần thêm gì? |
| --- | --- | --- |
| Có bao nhiêu SecurityFilterChain được xây | **Có thể** thấy qua các dòng Will secure | Đối chiếu bean configuration và logging filter chain |
| Chain nào mang HTTP Basic | **Gợi ý mạnh** khi có BasicAuthenticationFilter | Kiểm tra `httpBasic` và gửi request credentials |
| URL nào là public | **Không** | Kiểm tra `authorizeHttpRequests` và thử anonymous |
| `hasRole("ADMIN")` áp dụng đúng đường dẫn | **Không** | Kiểm tra rule, matcher, thứ tự, test USER/ADMIN |
| JWT có chữ ký/issuer/audience hợp lệ | **Không** | Kiểm thử token decoder/validation |
| CSRF có chặn POST đúng | **Không** | Gửi POST có/không có token trong test |
| Custom filter có được **gọi** khi có request | **Không** | TRACE request hoặc test có instrumentation |
| Người dùng có quyền đọc đúng bản ghi | **Không** | Kiểm tra phân quyền theo owner/tenant ở service |
| Có một endpoint nào không được bảo vệ | **Không chỉ dựa vào số dòng** | Kiểm tra toàn bộ matcher và test các path ngoại lệ |
| Logging có thể dùng lâu dài trong production | **Không** | Đánh giá dữ liệu nhạy cảm, ACL log, retention, hiệu năng |

Đừng nhầm **có filter** với **mọi quyết định trong filter đều đúng**. Ví dụ `AuthorizationFilter` được tạo nhưng một matcher `permitAll` đặt sai vị trí có thể mở URL nhạy cảm. Khi rule cụ thể nằm sau `anyRequest()`, cấu hình còn có thể bị từ chối ngay lúc xây dựng; đọc chính xác exception startup thay vì chỉ tìm dòng `Will secure`.

## 10. Phân biệt các log khởi động dễ bị đọc nhầm

### 10.1. Generated security password

Nếu Spring Boot tạo một tài khoản mặc định để phát triển, startup có thể in thông báo về mật khẩu ngẫu nhiên được tạo. Đây là **dấu hiệu auto-configuration về người dùng mặc định**, không chứng minh rằng các `SecurityFilterChain` đã được thiết lập đúng như ý. Nếu đã khai báo `UserDetailsService` riêng như ví dụ, Boot thường không tạo tài khoản mặc định đó.

Mật khẩu được sinh vẫn là **credential**, không chụp màn hình hoặc đưa vào hệ thống ticket/chat công khai. Khi thấy thông báo này ngoài môi trường development, hãy kiểm tra ngay cách quản lý người dùng và bí mật của ứng dụng.

### 10.2. Condition Evaluation Report

Khi chạy với `--debug`, Spring Boot có thể in các điều kiện auto-configuration “matched/did not match”. Điều này giúp giải thích vì sao một bean/configuration được kích hoạt, nhưng **không thay thế** log `DefaultSecurityFilterChain` liệt kê filter cụ thể. Một ứng dụng có thể “matched” một cấu hình bảo mật nhưng người phát triển vẫn thay đổi chi tiết bean `SecurityFilterChain` bằng cấu hình riêng.

### 10.3. Servlet container startup

Dòng “Tomcat started on port 8080” hoặc “Started ...Application” nói ứng dụng đã khởi động và server nhận request; nó **không** cho biết security matcher, role hay CSRF. Một controller còn tồn tại mà SecurityFilterChain không khớp có thể vẫn trả HTTP 200 khi server chạy.

### 10.4. Logger DEBUG thiếu vì cấu hình ghi log, không hẳn thiếu filter

Nếu không có dòng `Will secure`, trước khi kết luận security không hoạt động, kiểm tra:

1. Bạn đã bật DEBUG **trước khi application context khởi tạo** chưa?
2. Đúng logger `org.springframework.security.web.DefaultSecurityFilterChain` chưa?
3. Có file `logback-spring.xml`/logger policy/appender chặn DEBUG không?
4. Log có bị đẩy sang collector/file thay vì console không?
5. Ứng dụng đang chạy **Servlet hay WebFlux**? WebFlux không dùng lớp DefaultSecurityFilterChain Servlet tương đương để in đúng định dạng trên.
6. Bản ứng dụng đang chạy có đúng JAR/build đang xem code không?

Ngoài ra, nếu ứng dụng **không dùng Servlet** mà đang chạy reactive, hãy tìm cơ chế và logger dành cho `SecurityWebFilterChain` / `WebFilterChainProxy`, không lấy sự vắng mặt của Servlet log làm bằng chứng thiếu bảo mật.

## 11. Gỡ lỗi 401, 403, 302 bằng cách phối hợp startup và request logs

### 11.1. HTTP 401 từ API

Dấu hiệu:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Đây là ví dụ **dạng header HTTP Basic**, giá trị realm/header thật có thể khác theo cấu hình/version. Hướng điều tra:

1. Startup có chain `/api/**` chứa `BasicAuthenticationFilter` không?
2. Request `/api/admin` có được chain API nhận không?
3. Header `Authorization` có tồn tại và đúng scheme Basic không? **Không đưa giá trị header vào log**.
4. Credentials có được user details service kiểm chứng không?
5. Nếu credentials đúng mà 401, kiểm tra password encoder/lock/disabled account và authentication provider.

### 11.2. HTTP 403 khi đã đăng nhập

Một kết quả 403 có thể do:

- Tài khoản có `ROLE_USER` nhưng endpoint yêu cầu `ROLE_ADMIN`.
- CSRF token thiếu/sai ở request thay đổi trạng thái.
- Method security hoặc một `AuthorizationManager` riêng từ chối.
- Custom filter/handler tạo response 403.

Log startup cho biết **bộ phận nào đã được cài**, nhưng cần TRACE runtime và bài test mới phân biệt nguyên nhân. Với `POST` bị 403, kiểm tra `CsrfFilter` trước khi sửa role hoặc vô hiệu hóa CSRF.

### 11.3. HTTP 302 chuyển hướng tới login

Với form login cho web, 302 thường là hành vi đúng khi chưa có phiên đăng nhập. Nếu API trả redirect ngoài ý muốn, kiểm tra matcher và entry point. Lưu ý client HTTP có thể tự theo 302 rồi nhận 200 HTML từ `/login`; đừng nhìn chỉ status sau cùng và cho rằng API đã trả dữ liệu.

### 11.4. HTTP 404 ở /login dù formLogin đã bật

Trong cấu hình chain hẹp, một filter có thể cung cấp endpoint **chỉ trong phạm vi matcher của chính chain**. Nếu cấu hình `formLogin` trong chain chỉ khớp `/secured/**` nhưng để login endpoint mặc định `/login` nằm ngoài đó, request `/login` có thể không được chain chứa filter login xử lý và trả 404. Phải đặt login endpoint phù hợp phạm vi và cấu hình URL chính xác; startup log cho biết form-login filter tồn tại nhưng **không chứng minh mọi login URL đều reachable**.

Trong ví dụ mục 4, chain web là fallback nên `/login` được chain đó xử lý.

## 12. Cách kiểm thử tự động để tránh “đọc log rồi đoán”

Log là công cụ **quan sát**, còn test HTTP là bằng chứng **hành vi**. Với Spring Boot 3.x và `spring-security-test`, ta có thể dùng `MockMvc` để tạo ma trận không phụ thuộc câu chữ log. Thêm dependency test vào `build.gradle` của dự án Initializr:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Sau đây là lớp test riêng cho ứng dụng mẫu (Java 17+, Spring Boot 3.x), đặt tại:

```text
src/test/java/demo/filterlogs/SecurityChainLogApplicationTests.java
```

```java
package demo.filterlogs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrlPattern;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainLogApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void apiPingIsPublic() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousApiAdminRequiresBasicAuth() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotAccessApiAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessApiAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousWebAdminRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/admin"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void webPublicIsAccessible() throws Exception {
        mvc.perform(get("/web/public"))
            .andExpect(status().isOk());
    }
}
```

**Để tạo tệp Java thật, cần viết bốn static import thành một dòng mỗi import** (không copy các dòng bị ngắt chỉ để trình bày trong README):

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
```

Khi soạn tệp test, dùng các import này **thay** cho những import bị ngắt dòng ở trên, không nhập trùng. Các test xác nhận **hành vi** của những URL tiêu biểu trong hai chuỗi, đặc biệt phân biệt API trả 401 với web trả 302. Chúng không kiểm tra đầy đủ BOLA, CSRF POST, policy ở service hay security của mọi URL; cần mở rộng theo ứng dụng thực.

Chạy bằng:

```bash
./gradlew test
# Windows:
# .\gradlew.bat test
```

Kỳ vọng các test PASS khi chạy đúng dự án đã khai báo. Đây không phải stdout đã đo trong tài liệu. Muốn xác minh **filter cụ thể**, kết hợp DEBUG startup/TRACE runtime hoặc introspection/test cấu hình có kiểm soát, thay vì dùng một assertion “có chữ `BasicAuthenticationFilter` trong toàn bộ stdout” (dễ vỡ theo logger và phiên bản).

## 13. Không dùng logging để lộ dữ liệu nhạy cảm

Bật DEBUG/TRACE là **công cụ chẩn đoán có giới hạn thời gian**:

- Dùng profile dev/test hoặc cấu hình logging chỉ mở cho môi trường điều tra được phân quyền.
- Không ghi `Authorization`, `Cookie`, credentials, access token, refresh token, session ID, request body chứa dữ liệu cá nhân, hoặc giá trị `password` vào log.
- Khi chuyển log vào collector, kiểm soát quyền đọc, truyền/lưu mã hóa khi thích hợp, retention, bản sao và cơ chế hạn chế/xóa dữ liệu.
- Thận trọng với URL/query chứa email, token, thông tin cá nhân; log `Securing GET /...` có thể làm lộ đường dẫn nếu ứng dụng nhét dữ liệu nhạy cảm vào URL.
- Không đưa log chứa thông tin nhạy cảm vào issue công khai. Khi cần chia sẻ để sửa lỗi, chỉ gửi các dòng mô tả **matcher/filter class** sau khi rà soát dữ liệu.
- Khi điều tra xong, hạ cấp logging về mức vận hành phù hợp; TRACE toàn package có thể gây quá tải log và che mất tín hiệu quan trọng.

Một nguyên tắc hỗ trợ sự cố: **chỉ cần biết filter và quyết định**, không cần biết giá trị mật khẩu/token. Ví dụ log “Basic authentication failed” có thể đủ để khoanh vùng; muốn phân tích sâu thì dùng test credential giả và trace có kiểm soát thay vì log bí mật thật.

## 14. Quy trình kiểm tra nhanh khi nhận một dự án Spring Security

1. **Xác định stack**: Servlet/MVC dùng `HttpSecurity`, `SecurityFilterChain`, `FilterChainProxy`; WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`.
2. **Bật DEBUG đúng logger**: `org.springframework.security.web.DefaultSecurityFilterChain` hoặc package `org.springframework.security`, khởi động lại.
3. **Tìm mọi dòng `Will secure`**: đếm chuỗi, đọc matcher và filter list từng chuỗi; đừng trộn filter của các chuỗi.
4. **Vẽ sơ đồ matcher–order**: `/api/**` Order 1, fallback Order 2, v.v.; xem có URL nào không khớp chuỗi nào không.
5. **Đánh dấu cơ chế trong từng chain**: Basic/form login/Bearer, CSRF, AuthorizationFilter, custom filter.
6. **Kiểm tra chính sách source**: `requestMatchers`, `hasRole`, `permitAll`, `access`, CORS/CSRF; log startup không chứa đầy đủ thông tin này.
7. **Gửi request đại diện**: anonymous, user thường, admin, GET và POST khi có nghiệp vụ ghi.
8. **Bật TRACE FilterChainProxy có chủ đích** nếu kết quả trái dự đoán; đọc filter thật sự được gọi và điểm bị từ chối.
9. **Kiểm thử tự động** cho từng phạm vi quyền và URL đặc biệt, cả trường hợp âm tính.
10. **Giảm logging sau chẩn đoán**, rà soát dữ liệu có thể bị ghi và bảo vệ quyền xem log.

**Kết luận:** dòng `DefaultSecurityFilterChain : Will secure ... with [...]` cho biết **các chuỗi security filter đã được tạo lúc khởi động**. Nó là bản đồ cấu trúc, không phải bằng chứng mọi request đều an toàn. Để hiểu hành vi thực tế, luôn đối chiếu **matcher + @Order + filter list + rule phân quyền + log request + test HTTP**.

### Tài liệu chính thức

- [Spring Security 6.5 — Servlet Architecture, Printing the Security Filters & Logging](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration: Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
