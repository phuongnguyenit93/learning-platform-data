# Xác định chuỗi bảo mật và quy tắc đã áp dụng cho yêu cầu

> **Phạm vi:** quan sát, giải thích và gỡ lỗi việc lựa chọn `SecurityFilterChain`, bộ lọc xác thực và quy tắc `authorizeHttpRequests` cho một HTTP request trong **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**. Bài viết dùng hai chain riêng cho API và web, log có kiểm soát và các kiểm thử tích hợp. Mục tiêu là trả lời bằng **bằng chứng**: “Request đã vào chain nào?”, “Matcher/rule nào thực sự khớp?”, “Yêu cầu bị từ chối ở bước nào?”, không đoán nguyên nhân chỉ dựa trên HTTP status.

## 1. Ba câu hỏi cần tách biệt khi một request bị chặn

Một request `GET /api/reports/weekly` có thể nhận 401, 403, 404 hoặc 200. Để giải thích đúng, cần trả lời **theo thứ tự**:

1. **Chain nào được chọn?** `FilterChainProxy` duyệt những `SecurityFilterChain` được đăng ký theo thứ tự ưu tiên và sử dụng **chain đầu tiên** có `RequestMatcher` khớp request. Mỗi request chỉ đi qua các security filters của chain đã chọn; các chain còn lại không được “gộp” hay tiếp tục áp dụng.
2. **Cơ chế xác thực/filters nào có trong chain đó?** Ví dụ API chain bật `httpBasic`, web chain bật `formLogin`. Cùng một user không mặc nhiên dùng được mọi cơ chế trên mọi đường dẫn; một API chỉ bật HTTP Basic có thể trả 401, trong khi browser chain chuyển hướng tới `/login`.
3. **Quy tắc phân quyền nào được áp dụng?** Sau khi request qua các bước liên quan, `AuthorizationFilter` xử lý những matcher/authorization rule đã đăng ký trong chain được chọn **theo thứ tự khai báo**; với cấu hình `authorizeHttpRequests` thông thường, **rule khớp đầu tiên** quyết định yêu cầu quyền. Nếu `.anyRequest()` đứng cuối, nó là fallback **bên trong chain ấy**, không phải fallback chọn `SecurityFilterChain` khác.

Có thể còn một câu hỏi thứ tư: **HTTP response bị quyết định trước hay sau authorization?** `CsrfFilter`, HTTP firewall, authentication filter, method security hay controller có thể chặn request ở những thời điểm khác nhau. Vì vậy “403” **không tự chứng minh** rằng `hasRole(...)` đã từ chối, và “404” **không tự chứng minh** rằng request không đi qua Spring Security.

### Hai tầng “first match” khác nhau

| Tầng | Thành phần điều phối | Cách chọn | Cấu hình liên quan |
| --- | --- | --- | --- |
| Chọn **SecurityFilterChain** | `FilterChainProxy` | Chọn chain **đầu tiên** có `chain.matches(request)==true` | `@Order` của các `SecurityFilterChain` và `http.securityMatcher(...)` |
| Chọn **authorization rule** bên trong chain | `AuthorizationFilter` với `AuthorizationManager` | Xét các `requestMatchers` theo thứ tự; dùng rule **đầu tiên** khớp | `http.authorizeHttpRequests(auth -> auth.requestMatchers(...).hasRole(...).anyRequest()...)` |
| Xác thực danh tính | Filter + `AuthenticationManager` | Theo cơ chế của **chain đã chọn**, ví dụ Basic/form | `httpBasic`, `formLogin`, resource server, custom filters |
| Xử lý hậu quả | Entry point/denied handler, exception handler | Tùy đã/chưa xác thực và loại lỗi | `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, MVC advice |

**Lưu ý:** `@Order` trên **SecurityFilterChain bean** quy định chain được xét trước/sau. Thứ tự `requestMatchers` **bên trong** `authorizeHttpRequests` là một thứ tự khác. Viết `@Order(1)` không làm cho `requestMatchers("/admin/**")` trở thành rule đầu tiên trong mọi chain.

## 2. Sơ đồ xác định chain và rule

```text
HTTP request
  method=GET, path=/api/reports/weekly, credentials=...
          |
          v
DelegatingFilterProxy -> FilterChainProxy
          |
          +-- SecurityFilterChain @Order(1)
          |      securityMatcher("/api/**")
          |      matches? YES -> CHỌN API CHAIN
          |                     |
          |                     +-- Security filters của API chain
          |                     |    (Basic auth, CSRF, ...)
          |                     |
          |                     +-- AuthorizationFilter
          |                          1. GET /api/public       -> không khớp
          |                          2. GET /api/reports/**   -> KHỚP
          |                                    hasRole("REPORT_VIEWER")
          |                          3. GET /api/me           -> không xét tiếp
          |                          4. anyRequest           -> không xét tiếp
          |
          +-- SecurityFilterChain @Order(2) ANY REQUEST
                 KHÔNG được xét tiếp vì chain đầu đã khớp

Nếu request là GET /dashboard:
  API chain /api/** -> NO
  WEB chain any request -> YES
  WEB authorization -> anyRequest().authenticated()
  WEB authentication -> formLogin, không phải HTTP Basic
```

Quy trình có thể viết thành một thuật toán điều tra:

```text
B1. Ghi method + path đã chuẩn hóa, context/servlet path nếu có.
B2. Liệt kê các SecurityFilterChain theo thứ tự; xác định first match.
B3. Kiểm tra filter list của chain đã chọn (Basic? form? CSRF? JWT?).
B4. Kiểm tra request có dừng ở filter trước AuthorizationFilter không.
B5. Nếu đã tới AuthorizationFilter, tìm rule khớp đầu tiên.
B6. Xem Authentication, authorities và lý do allow/deny.
B7. Nếu filter-level cho phép, xem method security và xử lý controller.
B8. Đối chiếu HTTP status, log, test để có kết luận có thể tái lập.
```

**Ví dụ phản trực giác:** Nếu API chain ưu tiên cao có `.securityMatcher("/api/**")` và rule cuối `.anyRequest().denyAll()`, request `GET /api/unknown` bị API chain xử lý và **không quay lại web chain** để thử `.anyRequest().authenticated()`. Không có khái niệm “không match rule API thì tự chuyển sang chain kế tiếp”: đã match chain thì chain đó chịu trách nhiệm.

## 3. Phân biệt securityMatcher, requestMatchers và @Order

### 3.1. securityMatcher chọn phạm vi của toàn chain

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Đây là **mảnh cấu hình minh họa**, không phải toàn bộ ứng dụng. `securityMatcher("/api/**")` giới hạn chain vào các request API. Trong chain này, `anyRequest()` nghĩa là mọi request **đã được chọn vào API chain**, không phải “mọi request toàn ứng dụng”.

### 3.2. requestMatchers chọn rule bên trong chain

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                .hasRole("REPORT_VIEWER")
        .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
        .anyRequest().denyAll())
```

Đây là **mảnh cấu hình thuộc API chain**. Quy tắc cụ thể đứng trước quy tắc tổng quát. Thứ tự kiểm tra:

- `GET /api/public`: khớp rule đầu, được `permitAll`.
- `GET /api/reports/weekly`: khớp rule thứ hai, cần `ROLE_REPORT_VIEWER`.
- `GET /api/me`: khớp rule thứ ba, chỉ cần đã xác thực.
- `GET /api/unknown`: không khớp ba rule đầu, rơi vào `denyAll`.
- `POST /api/reports/weekly`: các rule đầu giới hạn `HttpMethod.GET` nên **không** khớp, đi tới fallback `denyAll` **nếu request tới được AuthorizationFilter**. Trên POST, `CsrfFilter` có thể chặn sớm hơn vì thiếu token.

Nếu đổi thứ tự thành:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").permitAll()
        .requestMatchers("/api/reports/**").hasRole("REPORT_VIEWER")
        .anyRequest().denyAll())
```

thì rule `"/api/**"` đứng trước **nuốt toàn bộ request** vào `permitAll`, và rule báo cáo phía sau sẽ không được xét. Đây là lỗi cấu hình nghiêm trọng; test phải có tình huống người chưa có quyền gọi API báo cáo và bị từ chối, không chỉ test positive cases.

### 3.3. @Order chỉ có ý nghĩa giữa các SecurityFilterChain

`@Order(1)` thường được xét trước `@Order(2)`. Nếu một chain có matcher rộng `/**` hoặc matcher mặc định “any request” đứng trước chain `/api/**`, chain API phía sau có thể **không bao giờ được chọn**. Nên đặt chain có matcher hẹp/cụ thể hơn trước chain bao phủ rộng; đặt catch-all chain cuối cùng.

Nếu không cấu hình `securityMatcher(...)`, `HttpSecurity` thường có matcher mặc định nhận **mọi request**. Không được giả định “vì bean đặt tên apiChain nên chỉ xử lý API”; **bean name không quyết định URL matcher**.

Nếu **không có chain nào khớp**, request có thể **không được Spring Security bảo vệ** bởi `FilterChainProxy`. Đây là lỗ hổng nếu lập trình viên tưởng tất cả request đều được kiểm tra. Một chain fallback an toàn thường dùng `anyRequest().authenticated()` hoặc `denyAll()` theo yêu cầu, thay vì không có chain nào bao phủ phần còn lại.

## 4. Ví dụ đầy đủ: một API chain + một web chain

### 4.1. Mục tiêu quan sát

Tạo một ứng dụng demo có hai chain:

- **API chain `@Order(1)`:** chỉ xử lý `/api/**`; dùng HTTP Basic; `/api/public` công khai; `/api/reports/**` yêu cầu role `REPORT_VIEWER`; `/api/me` cần đăng nhập; những yêu cầu API còn lại bị từ chối.
- **Web chain `@Order(2)`:** xử lý mọi URL còn lại; dùng form login; `/public` công khai; `/admin/**` cần `ADMIN`; những URL web còn lại yêu cầu đã đăng nhập.

Ba tài khoản demo:

| Username | Password demo | Authorities |
| --- | --- | --- |
| `analyst` | `analyst-pass` | `ROLE_REPORT_VIEWER` |
| `member` | `member-pass` | `ROLE_MEMBER` |
| `admin` | `admin-pass` | `ROLE_ADMIN` |

Khi chưa có credential: `GET /api/reports/weekly` thường trả 401 do Basic entry point, còn `GET /dashboard` chuyển hướng 302 tới trang login. Chỉ từ hai phản hồi khác nhau đã có **dấu hiệu** về cơ chế đã áp dụng, nhưng cần log/kiểm thử để xác nhận chính xác chain và rule.

### 4.2. Khai báo dependencies

Tạo dự án Spring Boot 3.x và Java 17+ (Gradle hoặc Maven). Với một `build.gradle` đã có Spring Boot plugin và cấu hình repositories, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đoạn trên là **khối dependencies**, không phải toàn bộ Gradle build script. `spring-security-test` cung cấp các helper kiểm thử form login và HTTP Basic. Ví dụ không cần database vì dùng `InMemoryUserDetailsManager`.

### 4.3. Mã ứng dụng chạy được

Tạo file **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("analyst")
                        .password(encoder.encode("analyst-pass"))
                        .roles("REPORT_VIEWER")
                        .build(),
                User.withUsername("member")
                        .password(encoder.encode("member-pass"))
                        .roles("MEMBER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                HttpMethod.GET, "/api/public")
                                .permitAll()
                        .requestMatchers(
                                HttpMethod.GET, "/api/reports/**")
                                .hasRole("REPORT_VIEWER")
                        .requestMatchers(HttpMethod.GET, "/api/me")
                                .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/dashboard", true)
                        .permitAll())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/api/public")
    String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/reports/weekly")
    String weeklyReport() {
        return "report-weekly";
    }

    @GetMapping("/api/me")
    String apiMe(Authentication authentication) {
        return "api-user=" + authentication.getName();
    }

    @GetMapping("/public")
    String webPublic() {
        return "web-public";
    }

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication) {
        return "web-user=" + authentication.getName();
    }

    @GetMapping("/admin/panel")
    String adminPanel() {
        return "admin-panel";
    }
}
```

Đây là **một file Java hoàn chỉnh**, tên lớp public khớp tên file; các lớp `SecurityConfig` và `DemoController` là top-level package-private cùng package `demo`. Spring Boot quét các bean trong package này. Cấu hình dùng đúng các API Spring Security 6.x và cú pháp Java 17+.

**Điều quan trọng nhất trong mã** là `@Order(1)` + `.securityMatcher("/api/**")` ở chain API, và `@Order(2)` với matcher mặc định catch-all ở web chain. Dòng `.requestMatchers(HttpMethod.GET,"/api/reports/**").hasRole("REPORT_VIEWER")` chỉ chạy khi request đã được chọn vào API chain; role `REPORT_VIEWER` tương ứng authority `ROLE_REPORT_VIEWER` vì `hasRole` tự áp dụng tiền tố mặc định.

Trong ví dụ, `.formLogin(...)` chỉ được bật ở web chain. Do đó, **không** suy luận rằng `/api/reports/weekly` sẽ chuyển hướng tới trang `/login` khi chưa đăng nhập; request ấy nằm trong API chain và Basic entry point thường trả 401. Tương tự, request web không tự đọc HTTP Basic chỉ vì API chain có bật Basic.

**CSRF:** Cả hai chain giữ cấu hình CSRF mặc định. Các endpoint demo đều là GET để quan sát lựa chọn chain/rule mà không cần tắt CSRF. Đối với POST/PUT/DELETE trong ứng dụng thực, phải phân tích CSRF và mô hình xác thực trước khi chỉnh cấu hình; một HTTP 403 có thể phát sinh từ `CsrfFilter` trước khi authorization rule được kiểm tra.

### 4.4. Chạy và gửi request đối chiếu

Chạy dự án bằng Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa cấu hình cổng khác, ứng dụng nghe ở `http://localhost:8080`. Thử từng request bằng curl:

```bash
# API public -> 200.
curl -i http://localhost:8080/api/public

# API cần login -> 401 với Basic challenge.
curl -i http://localhost:8080/api/reports/weekly

# API credential sai -> 401.
curl -i -u analyst:wrong-pass \
  http://localhost:8080/api/reports/weekly

# API user có đúng role -> 200.
curl -i -u analyst:analyst-pass \
  http://localhost:8080/api/reports/weekly

# API user xác thực đúng nhưng thiếu role -> 403.
curl -i -u member:member-pass \
  http://localhost:8080/api/reports/weekly

# API /me chỉ cần authenticated -> 200.
curl -i -u member:member-pass \
  http://localhost:8080/api/me

# API path không thuộc rule cho phép -> 403 với user đã xác thực.
curl -i -u member:member-pass \
  http://localhost:8080/api/unknown

# Web public -> 200.
curl -i http://localhost:8080/public

# Web dashboard chưa login -> redirect đến /login (thường 302).
curl -i http://localhost:8080/dashboard

# Web admin chưa login -> chuyển hướng login, không phải 403 cho authenticated user.
curl -i http://localhost:8080/admin/panel
```

Các dòng kết thúc bằng `\` là cú pháp tiếp dòng của Bash. Với PowerShell, dùng `curl.exe` thay `curl` nếu `curl` là alias của `Invoke-WebRequest`; viết mỗi lời gọi `curl.exe` trên một dòng hoặc dùng dấu tiếp dòng phù hợp.

Kết quả kỳ vọng cho **chính cấu hình ví dụ**:

| Request | Chain được chọn | Rule trong chain | HTTP kỳ vọng |
| --- | --- | --- | --- |
| `GET /api/public`, anonymous | API | `GET /api/public -> permitAll` | 200, body `api-public` |
| `GET /api/reports/weekly`, anonymous | API | `GET /api/reports/** -> REPORT_VIEWER` | 401 và `WWW-Authenticate: Basic ...` |
| `GET /api/reports/weekly`, analyst đúng password | API | Cùng rule role báo cáo | 200, body `report-weekly` |
| `GET /api/reports/weekly`, member đúng password | API | Cùng rule role báo cáo | 403 vì thiếu `ROLE_REPORT_VIEWER` |
| `GET /api/me`, member đúng password | API | `GET /api/me -> authenticated` | 200, body `api-user=member` |
| `GET /api/unknown`, member đúng password | API | `anyRequest -> denyAll` | 403, không thử web chain |
| `GET /public`, anonymous | Web | `/public -> permitAll` | 200, body `web-public` |
| `GET /dashboard`, anonymous | Web | `anyRequest -> authenticated` | Redirect về `/login` (thường 302) |
| `GET /admin/panel`, member đã form-login | Web | `/admin/** -> ADMIN` | 403 |
| `GET /admin/panel`, admin đã form-login | Web | `/admin/** -> ADMIN` | 200, body `admin-panel` |

**Đừng lấy status làm bằng chứng duy nhất:** mặc dù 401 thường xuất hiện ở Basic API và 302 thường xuất hiện ở web form, handler/entry point có thể được tùy chỉnh. Luôn đối chiếu chain matching, rule matching và filter dừng request.

## 5. Bật log để thấy chain nào được cân nhắc

### 5.1. DEBUG và TRACE trong Spring Security

Dùng profile phát triển cục bộ (ví dụ file `src/main/resources/application-local.properties`) hoặc thêm trực tiếp vào `application.properties` chỉ khi phù hợp môi trường:

```properties
# Thấy cấu hình filters, request được Spring Security bảo vệ.
logging.level.org.springframework.security=DEBUG

# Theo dõi quá trình xét các SecurityFilterChain và thứ tự filter.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE

# Khi cần xem rõ hơn quyết định authorization, có thể tạm bật:
logging.level.org.springframework.security.web.access.intercept=TRACE
```

Nếu muốn quan sát chi tiết hơn ở môi trường lab, có thể dùng:

```properties
logging.level.org.springframework.security=TRACE
```

**Không để TRACE tràn lan ở production.** Log có thể tiết lộ URL, tham số, định danh, nội dung security context, thông tin điều tra nhạy cảm hoặc tạo lượng log lớn. Chỉ bật trong khoảng thời gian có kiểm soát, phạm vi logger cần thiết, với chính sách truy cập/lưu trữ log và redaction tương ứng; không in password, `Authorization` header, cookie, bearer token hay session ID.

Khi chạy với profile `local`:

```bash
./gradlew bootRun --args='--spring.profiles.active=local'
```

Nếu dùng `application.properties` chung thì không cần tham số profile. Giá trị logger cụ thể/chi tiết log có thể khác theo bản Spring Security; chú ý ý nghĩa thay vì phụ thuộc từng từ trong dòng log.

### 5.2. Những dòng nên tìm

Ở startup, `DefaultSecurityFilterChain` thường cho biết matcher của chain và danh sách security filters mà nó chứa. Khi xử lý request, `FilterChainProxy` có thể log các dạng sau (đây là **mẫu diễn giải**, không cam kết chuỗi chính xác từng phiên bản):

```text
DEBUG ... DefaultSecurityFilterChain : Will secure ... with [ ... ]
TRACE ... FilterChainProxy          : Trying to match request against ...
DEBUG ... FilterChainProxy          : Securing GET /api/reports/weekly
TRACE ... FilterChainProxy          : Invoking ...Filter (n/m)
TRACE ... [authorization logger]    : ... checking request matcher ...
DEBUG ... [entry point/handler]     : ... sending authentication challenge ...
```

**Cách đọc:** một dòng `Securing GET ...` chỉ nói request đi qua `FilterChainProxy` và đang được bảo vệ, **chưa đủ** kết luận matcher/rule nào đã cho phép hay từ chối. Tìm các dòng `Trying to match request against ...` và đối chiếu thứ tự chain; xem danh sách filter để biết chain có `BasicAuthenticationFilter` hoặc `UsernamePasswordAuthenticationFilter`. Sau đó xem log liên quan authorization, anonymous/authenticated principal, entry point và denied handler.

Nếu log ghi rằng request được xét lần lượt với các matcher và dừng ở `/api/**`, kết luận là API chain. Nếu first match là fallback web chain, cần xét liệu path thực tế có khác path bạn tưởng, cấu hình chain có bị thiếu `securityMatcher` hay thứ tự `@Order` có sai.

### 5.3. Không bật debug mode thiếu kiểm soát

`@EnableWebSecurity(debug = true)` là một chế độ debug bổ sung trong môi trường học tập, có thể in thông tin request/filters khá rộng. **Không khuyến khích bật trên production hoặc môi trường chứa secret**, và không xem đây là cách sửa lỗi. Ưu tiên scoped DEBUG/TRACE và kiểm thử trước; tắt debug sau khi thu đủ bằng chứng.

Cũng không nên sửa controller để trả công khai “chain nào đã xử lý” hoặc “user có những authority nào” chỉ nhằm gỡ lỗi. Dữ liệu này có thể hỗ trợ kẻ tấn công lập bản đồ chính sách bảo mật. Ghi nhận trong log nội bộ đã kiểm soát hoặc test code là phù hợp hơn.

## 6. Xác định chain bằng kiểm thử programmatic

Spring Security cung cấp `FilterChainProxy.getFilterChains()` để xem **danh sách chain đúng thứ tự sử dụng**. Mỗi `SecurityFilterChain` có `matches(HttpServletRequest)` và `getFilters()`. Để kiểm chứng trong bài test, có thể dùng request thực tế do `MockMvc` tạo thay vì chỉ truyền một URL string vì matcher có thể phụ thuộc HTTP method, servletPath, dispatcher type và thuộc tính request.

### 6.1. Kiểm thử tích hợp với MockMvc

Tạo file `src/test/java/demo/SecurityChainSelectionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityChainSelectionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy securityProxy;

    @Autowired
    @Qualifier("apiChain")
    SecurityFilterChain apiChain;

    @Autowired
    @Qualifier("webChain")
    SecurityFilterChain webChain;

    private SecurityFilterChain firstMatchingChain(
            MockHttpServletRequest request) {
        return securityProxy.getFilterChains().stream()
                .filter(chain -> chain.matches(request))
                .findFirst()
                .orElseThrow();
    }

    @Test
    void apiRequestSelectsFirstApiChain() throws Exception {
        MvcResult result = mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andReturn();

        assertSame(apiChain, firstMatchingChain(result.getRequest()));
    }

    @Test
    void webRequestSelectsFallbackWebChain() throws Exception {
        MvcResult result = mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andReturn();

        assertSame(webChain, firstMatchingChain(result.getRequest()));
    }

    @Test
    void publicApiIsAccessibleWithoutCredentials() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("api-public"));
    }

    @Test
    void anonymousApiReportTriggersBasicChallenge() throws Exception {
        mvc.perform(get("/api/reports/weekly"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "WWW-Authenticate", containsString("Basic")));
    }

    @Test
    void analystWithCorrectRoleCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/weekly")
                        .with(httpBasic("analyst", "analyst-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("report-weekly"));
    }

    @Test
    void validMemberWithoutReportRoleGets403() throws Exception {
        mvc.perform(get("/api/reports/weekly")
                        .with(httpBasic("member", "member-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongBasicCredentialsGet401() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("member", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void apiFallbackDeniesUnknownPath() throws Exception {
        mvc.perform(get("/api/unknown")
                        .with(httpBasic("member", "member-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousWebRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login")));
    }

    @Test
    void webFormLoginAllowsMemberDashboard() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("member")
                        .password("member-pass"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/dashboard"))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("web-user=member"));

        mvc.perform(get("/admin/panel").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void webAdminCanOpenAdminPage() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                        .user("admin")
                        .password("admin-pass"))
                .andExpect(status().isFound())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/admin/panel").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-panel"));
    }
}
```

**Kiểm thử trực tiếp đối tượng chain:** `apiRequestSelectsFirstApiChain` và `webRequestSelectsFallbackWebChain` dùng `MockMvc` tạo `MockHttpServletRequest`, rồi duyệt danh sách `getFilterChains()` và lấy **matcher đầu tiên**. `assertSame(...)` đối chiếu chính xác bean chain đã cấu hình. Cách này là công cụ chẩn đoán trong test, **không thay thế** việc chạy request thật qua `FilterChainProxy`; các test status/body đi kèm chứng minh hành vi có đúng như suy luận hay không.

**Lưu ý về request matcher phức tạp:** `matches(...)` có thể phụ thuộc request đã qua firewall, servlet mapping, method, dispatcher type hoặc request attributes. Kiểm thử trực tiếp trên một mock request tự tạo sơ sài có thể không giống request thật ở runtime. Đối với ứng dụng có context path, servlet path tùy chỉnh, reverse proxy hoặc nhiều servlet, ưu tiên test full `MockMvc` cùng cấu hình thật và đối chiếu log `FilterChainProxy`.

Chạy tất cả test:

```bash
./gradlew test
```

Chỉ chạy class này:

```bash
./gradlew test --tests demo.SecurityChainSelectionTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.SecurityChainSelectionTest
```

Kết quả kỳ vọng là các assertion pass với **đúng** mã ví dụ. Đây không phải stdout cố định; số lượng test và cách báo cáo của Gradle/JUnit có thể khác tùy công cụ. Nếu một assertion fail, giữ nguyên request gây lỗi và xác định sai ở chain, rule hay filter/handler; đừng sửa status kỳ vọng trước khi đọc trace.

### 6.2. Vì sao chỉ dùng @WithMockUser chưa đủ?

`@WithMockUser` hoặc `user(...)` hữu ích khi test *authorization* ở request đã có danh tính. Tuy nhiên, nó **không chứng minh** rằng HTTP Basic/form login được cấu hình trên chain đúng, rằng `PasswordEncoder` kiểm tra password hay rằng login entry point phản hồi đúng.

Trong bài này, `httpBasic(...)` trong MockMvc tạo credential đầu vào thật cho HTTP Basic filter; `formLogin()` đi qua form-login flow, có CSRF token hợp lệ. Những assertion đối chiếu **cơ chế thực tế của chain** hữu ích hơn việc chỉ đưa mock `Authentication` rồi thấy 200.

Cũng không nên dùng một test `@WithMockUser(roles = "REPORT_VIEWER")` để kết luận toàn bộ `/api/**` an toàn. Cần thêm **negative tests** cho member/anonymous, unknown path và các method khác.

## 7. Quy trình gỡ lỗi một request cụ thể

Giả sử một API production nhận `GET /api/reports/weekly` và bị từ chối ngoài dự kiến. Làm theo trình tự sau.

### Bước 1 — Ghi request thực sự mà server thấy

Thu thập an toàn: method, path, context path, servlet path, query keys quan trọng, dispatcher type, request ID, môi trường/profile, status và tên tài khoản/role ở dạng đã kiểm soát quyền truy cập. Không copy password, bearer token, cookie, Authorization header nguyên văn vào ticket/log.

Xác minh sự khác biệt như:

- `GET /api/reports/weekly` so với `POST /api/reports/weekly`: request method có thể khiến `requestMatchers(HttpMethod.GET,...)` không khớp.
- `/api/reports/weekly` so với `/reports/weekly`: nếu gateway strip prefix `/api`, chain API có thể **không** khớp.
- `/app/api/reports/weekly` khi `/app` là context path: matchers thường làm việc với đường dẫn trong ứng dụng, không đơn giản lấy toàn bộ URL từ browser.
- URL được encode, slash, trailing slash, servlet mapping đặc biệt: `HttpFirewall` và request matchers có thể xử lý khác với điều bạn nhìn thấy trên client.

### Bước 2 — Xem các chain thực sự đã được đăng ký

Tìm `@Bean SecurityFilterChain`, `@Order` và `securityMatcher` trong **cấu hình thuộc ứng dụng đang chạy**. Trên startup DEBUG, xem `DefaultSecurityFilterChain` và danh sách filter của từng chain. Không suy theo tên bean hoặc thứ tự lớp trong file Java.

Nếu có nhiều chain, tạo bảng:

| Ưu tiên | Matcher của chain | Cơ chế xác thực | Quy tắc trọng tâm |
| --- | --- | --- | --- |
| 1 | `/api/**` | HTTP Basic | API report cần role `REPORT_VIEWER` |
| 2 | Any request | Form login | `/admin/**` cần `ADMIN` |

Đây là bảng cho **ứng dụng demo**; trong ứng dụng thật cần ghi cấu hình thực tế, kể cả chain phát sinh từ cấu hình module khác.

### Bước 3 — Khớp với request, không khớp với URL “trong đầu”

Bật `FilterChainProxy=TRACE` cục bộ, theo dõi các lần thử matcher. Chain đầu tiên khớp là chain xử lý. Nếu không thấy chain mong đợi, xem `@Order`, `securityMatcher`, HTTP method, context/servlet path và matcher do MVC cung cấp. Nếu không có chain nào khớp, đây là tình huống cần rà soát bảo mật nghiêm túc, không phải “request mặc định được an toàn”.

Một request đi qua chain `/api/**` không thể dùng form login filter nằm **chỉ trong web chain**. Chú ý `/login` và `POST /login` trong ví dụ thuộc web chain vì URL không bắt đầu bằng `/api/`; nếu tự cấu hình form login endpoint nằm trong một chain chỉ match `/api/**`, endpoint cần được đưa vào phạm vi chain đó hoặc tách cấu hình phù hợp.

### Bước 4 — Xem request có dừng trước AuthorizationFilter không

Các trường hợp:

- `HttpFirewall` từ chối URL nguy hiểm: request có thể không tới danh sách filter mong đợi.
- `CsrfFilter` từ chối POST thiếu token: thường 403, dù rule `permitAll` phía sau có thể cho phép.
- HTTP Basic sai password: authentication filter thường chuyển sang entry point 401 trước khi authorization quyết định.
- Form login thất bại: failure handler redirect, không chứng minh rule URL nào đã từ chối.
- CORS preflight `OPTIONS` bị chặn: kiểm tra CORS/filter order, không chỉ xem role.
- Lỗi do custom filter hoặc exception handler riêng: status cuối cùng có thể khác mặc định.

Lệnh `curl -i` hỗ trợ xem status và các header như `Location` hoặc `WWW-Authenticate`. Nhưng log và test là bằng chứng mạnh hơn khi handler đã tùy chỉnh.

### Bước 5 — Nếu tới AuthorizationFilter, xác định rule đầu tiên

Đọc **theo thứ tự khai báo** trong **chain đã chọn**. Với `GET /api/reports/weekly` của demo:

1. `GET /api/public` → không khớp.
2. `GET /api/reports/**` → khớp → yêu cầu `ROLE_REPORT_VIEWER`.
3. Không xét `GET /api/me` hay `anyRequest` cho request đó.

Nếu user `member` có authority `ROLE_MEMBER`, request bị denied. Nếu `analyst` có `ROLE_REPORT_VIEWER`, được phép đi tới controller. Không “chạy tiếp” rule phía sau để tìm lựa chọn dễ hơn. Nếu rule `permitAll("/api/**")` nằm trước rule report, nó có thể làm cả report trở thành public.

**Rule match không phải cả câu chuyện:** `AuthorizationFilter` có thể cho qua, nhưng method security (`@PreAuthorize`), service hoặc controller vẫn có thể từ chối sau đó. Khi status khác dự tính, kiểm tra cả các lớp ở sau bộ lọc.

### Bước 6 — Kiểm tra ngữ cảnh xác thực và authorities

Điều tra danh tính dưới dạng đã được phép quan sát: anonymous hay authenticated? Username/principal nào? Authorities là `ROLE_ADMIN`, `ROLE_REPORT_VIEWER` hay `SCOPE_x`? `hasRole("ADMIN")` theo quy ước cần authority `ROLE_ADMIN`; `hasAuthority("SCOPE_reports.read")` cần chuỗi authority đúng nguyên văn. Đừng nhầm role `REPORT_VIEWER` với scope hay tự chèn `ROLE_` hai lần.

Với request từ browser, session/cookie có thể ảnh hưởng kết quả; với Basic, header được xét bởi filter tương ứng. Trong demo, không lấy `analyst:analyst-pass` làm bằng chứng “web chain cũng chấp nhận HTTP Basic”; web chain chỉ bật form login.

### Bước 7 — Kiểm tra kết luận bằng cặp test positive/negative

Một rule đúng phải có cả chứng cứ **cho phép** và **từ chối**:

- Analyst gọi report → 200; Member gọi cùng report → 403.
- Anonymous gọi API cần role → 401; Anonymous gọi API public → 200.
- Anonymous gọi web dashboard → redirect login; Member form-login → dashboard 200.
- Member vào `/admin/panel` → 403; Admin vào cùng endpoint → 200.
- Authenticated member gọi `/api/unknown` → 403; chứng tỏ fallback `denyAll` không chuyển sang web chain.

Nếu mọi test cùng trả 403, có thể lỗi CSRF/config/filter toàn cục chứ không phải mỗi rule đều chính xác. Nếu mọi test cùng trả 200, có thể rule chung quá rộng hoặc test vô tình bypass filter chain.

## 8. Các lỗi phổ biến khi suy ra chain/rule

### 8.1. Nhầm @Order của chain với thứ tự URL rules

**Sai:** “Đặt `@Order(1)` cho API chain nghĩa là rule `GET /api/reports/**` sẽ áp dụng trước mọi rule.”  
**Đúng:** Chọn chain bằng `@Order` + `securityMatcher`; sau đó **trong chain đã chọn** mới đọc thứ tự `requestMatchers`. Cần kiểm tra cả hai.

### 8.2. Nhầm securityMatcher với requestMatchers

**Sai:** “`requestMatchers("/api/**").authenticated()` khiến cả chain chỉ xử lý API.”  
**Đúng:** `requestMatchers` là rule authorization bên trong chain; `securityMatcher` là phạm vi của chính `SecurityFilterChain`. Một chain không có `securityMatcher` thường có thể match mọi request, gây chặn chain phía sau.

### 8.3. Đặt catch-all ở đầu

Một chain match-all đặt trước API chain sẽ “giành” request API. Một rule `anyRequest().permitAll()` hoặc `requestMatchers("/**").permitAll()` đặt trước rule cụ thể làm các rule phía sau không được áp dụng. Dùng chain matcher hẹp trước, fallback chain cuối và rule matcher hẹp trước `anyRequest`.

### 8.4. Cho rằng mỗi request chạy qua nhiều SecurityFilterChain

`FilterChainProxy` chọn chain khớp đầu tiên. Một request không liên tiếp đi qua API chain rồi web chain chỉ vì cả hai matcher có thể khớp; các filter của các chain không tự cộng dồn. Nếu muốn cơ chế nào đó cho cả API và web, cấu hình cơ chế ấy trong những chain cần nó hoặc thiết kế lại phạm vi chain.

### 8.5. Coi 403 luôn là thiếu role

Một POST thiếu CSRF có thể bị `CsrfFilter` chặn trước `AuthorizationFilter`. Method security cũng có thể ném `AccessDeniedException` sau khi filter-level authorization cho qua. Cần tìm filter/handler đầu tiên quyết định trả lỗi, không suy nguyên nhân chỉ từ số 403.

### 8.6. Coi 401 và 302 là dấu hiệu chắc chắn của chain

HTTP Basic thường trả 401, form login thường redirect 302; nhưng authentication entry point và handler có thể tùy chỉnh. Một ứng dụng có thể dùng cùng status cho nhiều chain. Test chain/rule thực tế và đọc log trước khi kết luận.

### 8.7. Không xét HTTP method

`requestMatchers(HttpMethod.GET, "/api/reports/**")` không cho phép POST. Một URL nhìn giống nhau nhưng khác method có thể rơi vào `denyAll`; CSRF cũng có thể chặn sớm. Đừng chỉ gửi GET khi đang điều tra POST/PUT/DELETE.

### 8.8. Đường dẫn từ reverse proxy khác đường dẫn tại ứng dụng

Ingress có thể strip hoặc add prefix, ứng dụng có context path hoặc DispatcherServlet mapping riêng. Trong log hãy xác định đường dẫn **mà server Spring thực sự dùng để match**, đồng thời tránh tin tưởng mọi `X-Forwarded-*` từ client ngoài trusted proxy. Cấu hình forward headers phải có ranh giới tin cậy rõ ràng.

### 8.9. Tắt Spring Security bằng web.ignoring() để chữa 404/403

`web.ignoring()` hoặc loại request khỏi tất cả chain có thể bỏ qua nhiều cơ chế bảo vệ, khác với `permitAll` bên trong một chain (vẫn qua các security filters). Ưu tiên cấu hình `permitAll` cho endpoint công khai cần security headers; chỉ bỏ qua security cho tài nguyên phù hợp khi đã hiểu hệ quả.

### 8.10. Dùng DebugFilter/TRACE và quên tắt

Logging chi tiết hữu ích để gỡ lỗi nhưng có thể sinh lượng log lớn và tiết lộ thông tin hoạt động. Tắt trace sau khi xác minh, hạn chế retention/access, không đưa credential vào output hoặc gửi nhật ký chứa token cho bên không có quyền.

## 9. Những trường hợp phức tạp hơn

### Matcher kết hợp method, header hoặc tenant

`RequestMatcher` không buộc chỉ dựa vào path. Có thể kết hợp method, servlet path, IP hoặc thuộc tính request khác tùy API được dùng. Vì vậy hãy tái tạo **toàn bộ request context**, không chỉ gửi một string URL rồi mong kết quả giống runtime.

### Nhiều servlet và path mapping

Nếu một ứng dụng có nhiều servlet hoặc mapping khác `/`, matcher tự suy luận có thể không như mong đợi. Trên Spring Security 6, các kiểu matcher như MVC, Ant và các lựa chọn khác có hành vi khác nhau theo môi trường/config; khi có nhiều servlet nên xác định rõ `RequestMatcher` phù hợp, servlet path và các điều kiện. Tài liệu hiện hành của phiên bản đang dùng luôn là nguồn chuẩn.

### Dispatch ERROR, FORWARD và ASYNC

Một request có thể dẫn tới ERROR/FORWARD/ASYNC dispatch. Tùy cách filter mapping và security configuration, có thể xuất hiện lần authorization/exception khác ngoài request gốc. Nếu controller trả lỗi và trang `/error` cũng bị bảo vệ, response cuối có thể gây nhầm. Kiểm tra dispatcher type và log; chỉ `permitAll` dispatcher types khi phù hợp với contract và threat model.

### Method security và principal-dependent rules

Ngay cả khi `authorizeHttpRequests` đã cho phép, `@PreAuthorize("hasRole('ADMIN')")` ở service có thể từ chối. Hãy chỉ ra rõ điểm nào quyết định: request-level authorization, method-level authorization hay business exception. Không sửa requestMatcher nếu nguyên nhân thật là policy của service.

### Profile và cấu hình test khác production

`@Profile`, `@ConditionalOnProperty`, bean cấu hình từ module khác hoặc thứ tự `@Order` có thể thay đổi danh sách chain. So sánh startup filter list ở môi trường lỗi với môi trường test; đừng lấy duy nhất mã của một module làm bằng chứng cho toàn application context.

## 10. Checklist quan sát và gỡ lỗi an toàn

1. Ghi đầy đủ method, URL/path tại server, context/servlet mapping, dispatcher type, status, request ID; **không lưu bí mật**.
2. Xác định thứ tự các `SecurityFilterChain`; xem `@Order` và `securityMatcher`. Có catch-all cuối không?
3. Chọn chain khớp **đầu tiên**, không gộp các chain.
4. Xem filter list chain: Basic/form/JWT/CSRF/CORS/exception handler có thật trong chain đó không?
5. Xem request bị chặn **trước** hay **trong** `AuthorizationFilter`.
6. Nếu tới authorization, duyệt `requestMatchers` **theo thứ tự**, ghi rule đầu tiên khớp và yêu cầu quyền của nó.
7. Đối chiếu principal, `isAuthenticated`, authorities; phân biệt `ROLE_` với `SCOPE_`.
8. Kiểm tra method-level security, controller mapping và business exceptions nếu filter-level đã cho qua.
9. Bật DEBUG/TRACE có giới hạn và kiểm tra log tương ứng; tắt sau khi thu bằng chứng.
10. Tạo test positive **và** negative cho URL, HTTP method, credential, role và fallback.
11. So sánh config thực tế ở môi trường lỗi với app/test; kiểm tra gateway, context path và servlet mapping.
12. Không “chữa” lỗi bằng cách tắt CSRF, bỏ security chain hoặc mở `permitAll` quá rộng.

## 11. Câu hỏi tự luyện

1. Vì sao `@Order(1)` và `.securityMatcher("/api/**")` trong API chain đóng hai vai trò khác nhau? Nếu bỏ `securityMatcher`, điều gì có thể xảy ra?
2. Nếu request đã khớp API chain nhưng không khớp các rule API cụ thể, Spring Security có thử web chain tiếp theo không?
3. Nếu đặt `.requestMatchers("/api/**").permitAll()` trước rule `/api/reports/**`, rule report sẽ còn hiệu lực không? Vì sao?
4. Một anonymous gọi `GET /api/reports/weekly` nhận 401; anonymous gọi `GET /dashboard` nhận 302. Những chi tiết nào cần kiểm tra trước khi kết luận hai request dùng Basic và form login?
5. `GET /api/unknown` với account đã xác thực nhận 403. Trường hợp này minh họa fallback của chain hay fallback authorization rule?
6. Nếu người dùng gửi `POST /api/reports/weekly` không CSRF token và nhận 403, có thể khẳng định `denyAll` đã chạy không?
7. Dùng `FilterChainProxy.getFilterChains()` và `chain.matches(request)` giúp kiểm tra điều gì? Vì sao chỉ truyền URL string có thể không đủ cho custom matcher?
8. Người dùng có authority `ROLE_REPORT_VIEWER` nhưng request bị 403. Liệt kê ba nguyên nhân ngoài trường hợp “role sai” cần kiểm tra.
9. Khi gateway bỏ tiền tố `/api`, chain nào có thể xử lý request và vì sao? Làm sao xác minh đường dẫn sau proxy?
10. Một endpoint `permitAll` vẫn bị chặn khi POST thiếu CSRF. Vì sao `permitAll` không có nghĩa “bỏ qua tất cả filter”?
11. Vì sao `@WithMockUser` không đủ chứng minh HTTP Basic entry point hoặc form login filter đã được cấu hình trên đúng chain?
12. Nếu log cho thấy `AuthorizationFilter` đã permit một request nhưng controller trả 403, bạn sẽ điều tra những lớp nào tiếp theo?

**Gợi ý:** (1) ưu tiên vs phạm vi match; (2) không, đã chọn chain thì dùng chain ấy; (3) không, rule đầu đã khớp; (4) xem matcher/filter list/entry point/log; (5) authorization fallback `denyAll`; (6) không, CSRF có thể chặn trước; (7) xem chain đầu tiên khớp request có đầy đủ method/path/context; (8) CSRF, method security, custom filter/handler; (9) tùy path thực tế, có thể rơi vào web chain; (10) permitAll chỉ là một quyết định authorization; (11) mock user bỏ qua xác thực thực; (12) method security, custom policy/filter, handler và controller/service.

## Tài liệu chính thức đối chiếu

- [Spring Security 6.5 — Servlet Architecture: FilterChainProxy, SecurityFilterChain, Logging](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration: Multiple SecurityFilterChain and Matching](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HTTP Requests and matcher order](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — FilterChainProxy API, getFilterChains](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security 6.5 — Servlet Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
- [Spring Security 6.5 — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)