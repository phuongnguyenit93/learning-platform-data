# Phân quyền theo đường dẫn kết hợp HTTP method trong Spring Security Servlet

## 1. Vì sao cần kết hợp cả URL lẫn HTTP method?

Một API có thể sử dụng **cùng một đường dẫn** để thực hiện các thao tác có mức độ nhạy cảm khác nhau. Ví dụ: đọc danh sách bài viết bằng `GET /api/articles`, tạo bài viết bằng `POST /api/articles`, sửa một bài bằng `PUT /api/articles/42` và xóa bài bằng `DELETE /api/articles/42`.

Nếu chính sách bảo mật chỉ nói “người dùng có quyền truy cập `/api/articles/**`”, nó rất dễ **cho phép nhầm thao tác ghi/xóa** đối với người chỉ nên có quyền đọc. Ngược lại, nếu yêu cầu vai trò ADMIN với toàn bộ prefix, các request đọc công khai hoặc của biên tập viên có thể bị chặn quá mức.

Trong **Spring Security Servlet**, cấu hình `authorizeHttpRequests` có thể kết hợp **`RequestMatcher` cho đường dẫn** và **`HttpMethod`** để mô tả đúng từng quyền:

- `GET`, `HEAD`: thường dùng đọc metadata/tài nguyên; vẫn có thể chứa dữ liệu nhạy cảm và không tự động công khai.
- `POST`: thường dùng tạo tài nguyên hoặc thực hiện thao tác có tác động.
- `PUT`: thường dùng thay thế/cập nhật tài nguyên.
- `PATCH`: thường dùng cập nhật một phần.
- `DELETE`: thường dùng xóa.
- `OPTIONS`: có thể phục vụ CORS preflight; cần được xử lý theo chính sách CORS, không đánh đồng với thao tác nghiệp vụ.

Điểm học chính: **quyết định phân quyền phải xét cả “request tới đâu?” và “request định làm gì?”**, sau đó áp dụng nguyên tắc *least privilege* và kết thúc bằng rule **deny-by-default**.

Bài tập này nhắm tới **Spring Security 6.x, Spring MVC / Servlet stack, `HttpSecurity` và `SecurityFilterChain`, Java 17+**. WebFlux sử dụng API reactive riêng và không lấy nguyên `HttpSecurity` sang `ServerHttpSecurity`. Ví dụ runnable cố định ở Spring Boot 3.3.5 như một mốc học tập, không hàm ý đó là bản hiện hành hoặc còn trong vòng hỗ trợ; ứng dụng mới cần chọn dependency phù hợp chính sách support.

## 2. Request authorization xảy ra ở đâu trong filter chain?

Sơ đồ rút gọn:

```text
HTTP request: PUT /api/articles/42
    |
Servlet container
    |
DelegatingFilterProxy -> FilterChainProxy
    |
Chọn SecurityFilterChain khớp với request
    |
Authentication filters (HTTP Basic / bearer / form session ...)
    |
SecurityContextHolder chứa Authentication (hoặc anonymous)
    |
AuthorizationFilter
    |
authorizeHttpRequests -> RequestMatcher + AuthorizationManager
    |
match path + method -> hasRole / hasAuthority / authenticated / denyAll
    |
ALLOW -> DispatcherServlet -> Controller/Service
DENY  -> Spring Security xử lý Authentication/AccessDenied
```

**Authentication** trả lời “ai đang gọi?”; **authorization** trả lời “người đó có được làm thao tác này không?”. `authorizeHttpRequests` không tự xác minh lại mật khẩu; nó dùng Authentication đã có trong `SecurityContextHolder` do một cơ chế xác thực cung cấp.

Tùy request và cấu hình, nếu không đủ authentication có thể trả **401 Unauthorized** (đối với API HTTP Basic) hoặc redirect về trang login (với form login). Nếu đã xác thực nhưng không có quyền, thường nhận **403 Forbidden**.

**Phân biệt:** `CsrfFilter` có thể trả 403 trước khi authorization dù role hoàn toàn đúng. Không suy luận “403 nghĩa là thiếu vai trò” khi chưa kiểm tra CSRF và chain thực tế.

### Hai tầng matcher rất dễ nhầm

- **`http.securityMatcher("/api/**")`**: quyết định **toàn bộ SecurityFilterChain** có được chọn cho request không.
- **`authorizeHttpRequests(...requestMatchers(...))`**: sau khi một chain đã được chọn, quyết định **quyền đối với request trong chain đó**.

Đặt `requestMatchers("/api/**")` vào một chain không khớp `securityMatcher` sẽ không làm request tự “nhảy” sang chain này. Và `FilterChainProxy` chọn **chain phù hợp đầu tiên theo thứ tự**, không lần lượt kết hợp rule của mọi chain cho một request.

## 3. RequestMatcher kết hợp HTTP method và đường dẫn

Cú pháp DSL tiêu biểu:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**")
        .hasAnyRole("READER", "EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.POST, "/api/articles")
        .hasAnyRole("EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
        .hasRole("ADMIN")
    .anyRequest().denyAll());
```

Đây là **mảnh cấu hình**, cần đặt trong một method cấu hình `HttpSecurity` và import `org.springframework.http.HttpMethod`. Khi Spring MVC có mặt, cơ chế lựa chọn matcher có thể dùng matcher theo MVC; khi không có MVC, cách khớp mẫu có thể khác. Luôn kiểm thử pattern thực tế với framework/version đang dùng.

Một `requestMatchers(HttpMethod.GET, "/api/articles/**")` chỉ phù hợp khi **method là GET** và path khớp pattern. Nó **không tự áp dụng** cho POST/PUT/DELETE tới cùng URL. `requestMatchers("/api/articles/**")` không chỉ rõ method nên có thể phù hợp nhiều method, tùy pattern.

### Đọc các dạng path

| Pattern | Ý định thông dụng | Cạm bẫy |
|---|---|---|
| `/api/articles` | Collection URL, ví dụ GET list / POST create | Không được giả định nó luôn được bao hàm đúng trong mọi matcher `/**` ở mọi công nghệ |
| `/api/articles/*` | Một segment cuối, ví dụ `/api/articles/42` | Không nhằm cho `/api/articles/42/comments` |
| `/api/articles/**` | Nhiều segment dưới prefix, tùy matcher | Rộng hơn mức cần nếu endpoint có các nhánh nhạy cảm |
| `/api/**` | Tất cả API URL dưới prefix | Nếu áp rule quá sớm có thể che các rule chi tiết |
| `/**` | Nhiều đường dẫn trong application | Chỉ nên dùng khi đã hiểu các endpoint hệ thống và default/fallback |

**Không đồng nhất Spring MVC pattern, Ant-style pattern và regular expression.** Cú pháp và khả năng match có khác biệt theo `MvcRequestMatcher`, `AntPathRequestMatcher` hay `PathPatternRequestMatcher`, phiên bản và cách cấu hình. Ví dụ chính ở mục 9 dùng các route đơn giản, một segment, để test chắc ranh giới.

Đường dẫn trong authorization thường **không bao gồm query string như một phần của pattern path**. Ví dụ `GET /api/articles/42?preview=true` vẫn là cùng route path tương ứng; nếu `preview=true` mở thêm dữ liệu nhạy cảm, cần policy nghiệp vụ riêng, không chỉ coi query parameter là đường dẫn khác.

### Method matching phải chính xác

`HttpMethod.GET` không phải “mọi phương thức an toàn”; `HttpMethod.HEAD` và `HttpMethod.OPTIONS` là những giá trị riêng. Framework có thể hỗ trợ HEAD tại MVC controller tương đương GET cho hành vi HTTP, nhưng một security matcher giới hạn GET **không nên được giả định tự cho HEAD**. Nếu muốn cho HEAD, khai báo policy và test rõ.

Với PATCH, PUT, DELETE, client có thể dùng cơ chế method override nếu ứng dụng cấu hình `HiddenHttpMethodFilter` hoặc proxy hỗ trợ. Vì vậy cần kiểm tra **effective method mà Spring Security nhìn thấy**, không chỉ HTML form hiển thị POST. Không tự bật method override hoặc tin untrusted header một cách tùy tiện.

## 4. Quy tắc quan trọng: thứ tự từ cụ thể đến tổng quát

`authorizeHttpRequests` xử lý các matcher đã khai báo theo **thứ tự**, dùng rule đầu tiên phù hợp để đưa ra quyết định. Vì vậy:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/articles/*")
        .hasAnyRole("READER", "EDITOR", "ADMIN")
    .requestMatchers("/api/articles/**")
        .authenticated()
    .anyRequest().denyAll())
```

Mẫu trên có một vấn đề: rule cuối cho mọi phương thức của `/api/articles/**` chỉ yêu cầu authenticated, nên những method chưa được liệt kê như PATCH hoặc POST một URL bất ngờ có thể bị cho qua tới MVC nếu có route khớp. Có thể cuối cùng MVC trả 404/405, nhưng **không nên dựa vào controller không tồn tại để làm security policy**; khi một route mới được thêm vào sau đó, quyền truy cập có thể vô tình quá rộng.

Một anti-pattern còn nguy hiểm hơn:

```java
// SAI nếu muốn DELETE chỉ dành cho ADMIN:
.requestMatchers("/api/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/articles/*").hasRole("ADMIN")
```

Rule tổng quát đứng trước đã match DELETE, nên rule ADMIN phía sau trở nên không thể được dùng cho request đó. Điều này thường xuất hiện khi đội phát triển thêm một rule “nhìn có vẻ bảo mật hơn” ở cuối config mà không nhận ra đã có matcher rộng chặn trước.

### Cấu hình chặt chẽ hơn

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/articles", "/api/articles/*")
        .hasAnyRole("READER", "EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.POST, "/api/articles")
        .hasAnyRole("EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.PUT, "/api/articles/*")
        .hasAnyRole("EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
        .hasRole("ADMIN")
    .requestMatchers("/api/articles", "/api/articles/*")
        .denyAll()
    .anyRequest().denyAll())
```

Khi tất cả method/path dự kiến đã có rule, phần còn lại **deny all**. Cách này giảm rủi ro một controller mới vô tình được lộ khi không ai cập nhật authorization config. Tuy nhiên, phải **cập nhật test** mỗi khi thêm endpoint hợp lệ, kể cả public health và actuator nếu được bật theo chính sách.

### Vì sao nên có cả fallback ở prefix và anyRequest?

`requestMatchers("/api/articles", "/api/articles/*").denyAll()` minh họa chủ đích “các method khác trên hai loại route này đều bị chặn”; `anyRequest().denyAll()` bảo vệ tất cả URL không được khai báo. Về hiệu lực trong project ví dụ, fallback `anyRequest().denyAll()` đã chặn các URL ngoài danh sách; rule prefix bổ sung giúp code review nhìn rõ rằng các method chưa cho phép ở bài viết đều bị từ chối.

## 5. hasRole, hasAuthority và permission

Spring Security có hai dạng rule thông dụng:

- `hasRole("ADMIN")` thường kiểm tra authority mang prefix `ROLE_ADMIN` theo cấu hình mặc định.
- `hasAnyRole("EDITOR", "ADMIN")` chấp nhận một trong các authority tương ứng.
- `hasAuthority("article:write")` kiểm tra chính xác chuỗi authority, không tự thêm prefix.
- `hasAnyAuthority("article:read", "article:write")` cho phép khi có một trong các quyền được chỉ định.
- `authenticated()` chỉ yêu cầu request có authentication đáp ứng điều kiện, **không bảo đảm user có quyền sửa/xóa**.
- `permitAll()` cho phép bước authorization đối với request phù hợp, **không bỏ qua CSRF, filter khác hoặc logic nghiệp vụ**.
- `denyAll()` từ chối mọi request khớp rule.

Ví dụ:

```java
.requestMatchers(HttpMethod.POST, "/api/articles")
    .hasAuthority("article:create")
.requestMatchers(HttpMethod.DELETE, "/api/articles/*")
    .hasAuthority("article:delete")
```

Rule authority chi tiết thường hợp với hệ thống có permissions theo chức năng. Role có thể là một **tập quyền** và có thể cần mapping/hierarchy theo nghiệp vụ. Không truyền `hasRole("ROLE_ADMIN")` theo thói quen nếu prefix mặc định đã tự thêm `ROLE_`, bởi có thể tạo cấu hình sai hoặc exception tùy API.

**Lưu ý tenant/ownership:** `DELETE /api/articles/42` với role EDITOR hoặc quyền `article:delete` vẫn chưa đủ để xác nhận đó là bài viết **thuộc tổ chức/người dùng mà requester được phép quản lý**. Cần kiểm tra resource-level authorization tại service, ví dụ một `@PreAuthorize` hoặc service policy query dữ liệu theo principal/tenant. HTTP rule chỉ là lớp bảo vệ ban đầu.

## 6. Quyết định 401, 403 và lỗi CSRF

Một bảng hành vi dễ dùng khi thiết kế integration tests:

| Request | Authentication | Rule | Kỳ vọng |
|---|---|---|---|
| GET private | Không có credential | requires auth/role | 401 với HTTP Basic API, hoặc redirect login với form-based |
| GET private | Có credential sai | Authentication thất bại | 401 với Basic challenge/entry point |
| GET private | Reader hợp lệ | hasRole(READER) | Cho phép, nếu controller tồn tại |
| POST create | Reader hợp lệ | hasAnyRole(EDITOR,ADMIN) | 403 sau khi CSRF hợp lệ |
| POST create | Editor hợp lệ, có CSRF | hasAnyRole(EDITOR,ADMIN) | Cho phép |
| POST create | Editor hợp lệ, thiếu CSRF | CsrfFilter có thể chặn trước authorization | Thường 403 |
| DELETE item | Editor hợp lệ | hasRole(ADMIN) | 403 dù đã có CSRF |
| DELETE item | Admin hợp lệ, có CSRF | hasRole(ADMIN) | Cho phép |
| PATCH không khai báo | Admin hợp lệ | denyAll | 403 |
| GET path lồng sâu chưa cấp quyền | Admin hợp lệ | denyAll | 403 |

**Quan trọng:** 403 không chỉ ra nguyên nhân duy nhất. Với test quyền role, hãy gửi **CSRF token hợp lệ** ở POST/PUT/PATCH/DELETE trước khi kết luận 403 đến từ authorization. Với test CSRF, cố tình bỏ token ở một request mà user đã có role cần thiết.

### Giữ CSRF khi credential được trình duyệt gửi tự động

Form login và nhiều website sử dụng cookie/session, nên cần CSRF protection theo trust boundary. Với HTTP Basic, browser có thể tự đính kèm Authorization header cho origin sau khi được challenge, nên **không mặc định Basic hoàn toàn không có CSRF risk**. Trong ví dụ runnable, CSRF **không bị tắt**, và MockMvc sử dụng `with(csrf())` cho request thay đổi trạng thái.

Nếu một API dùng bearer token chỉ do JavaScript/mobile client chủ động gửi trong Authorization header và không dùng credential tự gửi, có thể có chính sách CSRF khác, nhưng cần phân tích cụ thể. Không copy `csrf(AbstractHttpConfigurer::disable)` vô điều kiện chỉ để test POST trả 201.

## 7. Multiple SecurityFilterChains: cẩn thận ranh giới trước khi vào authorization

Một hệ thống có thể dùng hai chain:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/articles/**")
                .hasAuthority("SCOPE_articles.read")
            .requestMatchers(HttpMethod.POST, "/api/articles")
                .hasAuthority("SCOPE_articles.write")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đoạn trên là **minh họa hai bean trong project có imports và dependency OAuth2 Resource Server phù hợp**, không phải code độc lập chạy được chỉ bằng starter web/security. Bearer JWT cần cấu hình issuer/JWK, signature/audience/claims và mapping authorities đúng. Các scope string là tên policy minh họa.

Điểm cốt lõi là **thứ tự chain và matcher**: `/api/**` được xét theo chain API trước, còn các URL không khớp có thể được web chain xử lý. Một `securityMatcher("/api/v1/**")` đặt sai khiến `/api/v2/**` rơi vào fallback có chính sách khác; vì thế cần test đầy đủ các prefix.

Khi dùng nhiều chain, **requestMatchers trong một chain không cấp quyền cho request không vào chain đó**. Không có fallback chain cũng có thể làm một endpoint bị bỏ khỏi Spring Security nếu nó không khớp bất kỳ SecurityFilterChain nào. Trong môi trường thật nên kiểm thử cả “đường dẫn không dự kiến” thay vì chỉ các URL đã biết.

## 8. CORS preflight, HEAD/OPTIONS, lỗi path và forward

HTTP method authorization thường vướng những tình huống sau:

### CORS OPTIONS

Trình duyệt có thể gửi:

```text
OPTIONS /api/articles
Origin: https://frontend.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

Đây là **preflight**, không phải request thực hiện tạo bài viết. Nếu chain chặn OPTIONS trước khi CORS được cấu hình, frontend có thể báo “CORS error” dù POST với token thực ra có quyền.

Giải pháp ưu tiên là tích hợp CORS đúng cách qua `http.cors(...)` và cấu hình `CorsConfigurationSource` hoặc Spring MVC CORS, giới hạn origin/method/headers hợp lệ. **Không mặc định cho phép mọi OPTIONS từ mọi origin bằng một rule rộng** nếu ứng dụng có policy chặt chẽ. CORS là kiểm soát trình duyệt, **không thay thế authorization**, và việc preflight được thông qua không có nghĩa POST thực tế được phép.

### HEAD

Một endpoint MVC GET có thể phục vụ HEAD theo cơ chế MVC, nhưng security matcher GET không nên được mặc định bao gồm HEAD. Nếu API muốn hỗ trợ HEAD, khai báo thêm `requestMatchers(HttpMethod.HEAD, ...)` với chính sách rõ và test. Đừng vô tình cho HEAD tới endpoint tiết lộ metadata không phù hợp.

### URL encoding và path normalization

- Một đường dẫn có dấu `%2F`, nhiều slash, dấu `;`, segment `..`, khác chữ hoa/chữ thường hoặc servlet context path có thể được container, firewall hoặc MVC xử lý khác nhau.
- Không tự viết security check bằng `request.getRequestURI().startsWith("/admin")` rồi nghĩ nó tương đương `requestMatchers("/admin/**")` của framework.
- Khi có reverse proxy hoặc context path, nên kiểm thử URL ngoài thực tế và security path nội bộ được ứng dụng nhận.
- `HttpFirewall`/Servlet container có thể từ chối request bất thường trước khi vào authorization, và đó là kết quả phù hợp thay vì “bỏ qua rule”.

### ERROR và FORWARD dispatch

Một request sau authorization có thể đi qua `ERROR` hoặc `FORWARD` dispatch. Một số app cần policy cụ thể cho error handling hoặc view rendering; tránh cấp toàn quyền với `permitAll("/**")` để sửa trang lỗi 403. Tìm hiểu dispatcher type và cấu hình filter mapping/authorization phù hợp từng framework.

### Path variable và query parameter

Nếu URL là `GET /api/articles/42`, security matcher biết request nhắm vào route item; nó không tự biết bài 42 là bí mật, thuộc tenant nào hoặc trạng thái đã xuất bản hay chưa. Những kiểm tra như “chỉ tác giả và admin được sửa bản nháp” phải dựa vào dữ liệu hiện hành trong service/authorization logic, không chỉ path string.

## 9. Ví dụ hoàn chỉnh: Java 17, Spring Boot 3.3.5, Maven và MockMvc

Ví dụ này tạo một ứng dụng Spring MVC Servlet đơn giản có ba tài khoản `reader`, `editor` và `admin`. Phân quyền dựa trên **đúng HTTP method và URL**, không phụ thuộc vào việc có một controller chung cho các method. Demo chọn HTTP Basic để test thấy rõ 401 thay vì redirect của form login, nhưng **giữ CSRF mặc định** nhằm thể hiện 403 do CSRF khác 403 do role.

**Lưu ý:** Spring Boot 3.3.5 là mốc dependency minh họa cho cú pháp Spring Security 6 và Java 17; không hàm ý là bản mới nhất/được khuyến nghị cho production ở mọi thời điểm. Trong thực tế, dùng release có hỗ trợ bảo mật và kiểm tra release notes.

### 9.1. Cấu trúc project

```text
method-path-authorization/
├── pom.xml
└── src/
    ├── main/java/example/methodpath/
    │   ├── MethodPathApplication.java
    │   ├── SecurityConfig.java
    │   └── ArticleController.java
    └── test/java/example/methodpath/
        └── MethodPathAuthorizationTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>method-path-authorization</artifactId>
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

### 9.3. Spring Boot application

File `src/main/java/example/methodpath/MethodPathApplication.java`:

```java
package example.methodpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodPathApplication.class, args);
    }
}
```

### 9.4. SecurityConfig: khai báo rule theo method + path

File `src/main/java/example/methodpath/SecurityConfig.java`:

```java
package example.methodpath;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/api/articles", "/api/articles/*")
                    .hasAnyRole("READER", "EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/articles")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.PUT, "/api/articles/*")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
                    .hasRole("ADMIN")
                .requestMatchers("/api/articles", "/api/articles/*")
                    .denyAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

**Giải thích và biên giới:**

- Reader chỉ có `ROLE_READER`, Editor có `ROLE_EDITOR`, Admin có `ROLE_ADMIN`. Trong bài này, GET cho cả ba role; editor/admin được ghi; chỉ admin được DELETE. Đây là policy minh họa, không có role hierarchy ẩn.
- `formLogin(AbstractHttpConfigurer::disable)` giúp request thiếu authentication của API không bị chuyển về HTML login theo cơ chế form. `httpBasic(...)` cho phép test gửi Basic credential đơn giản và nhận HTTP 401 khi cần.
- CSRF **không bị disable**. POST/PUT/DELETE từ MockMvc cần `with(csrf())`, giúp tách lỗi CSRF khỏi lỗi role. Với API Basic sử dụng trong trình duyệt, việc giữ CSRF là lựa chọn thận trọng; production cần thiết kế CSRF token lifecycle theo client thực tế.
- Không thêm rule rộng `requestMatchers("/api/**").authenticated()` phía trước các rule role.
- `anyRequest().denyAll()` ngăn URL không nằm trong danh sách được cấp phép; khi thêm endpoint hợp lệ phải thêm rule và test.
- Password fixture được hash bằng BCrypt. Các mật khẩu cố định trong ví dụ chỉ phục vụ test, không dùng cho tài khoản thật.
- SecurityFilterChain đặt tại module Servlet; nếu có nhiều chains, cần chỉ rõ matcher và priority theo thiết kế.

### 9.5. Controller biểu thị các HTTP operations

File `src/main/java/example/methodpath/ArticleController.java`:

```java
package example.methodpath;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArticleController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/articles")
    public String allArticles() {
        return "ARTICLES";
    }

    @GetMapping("/api/articles/{id}")
    public String oneArticle(@PathVariable String id) {
        return "ARTICLE:" + id;
    }

    @PostMapping("/api/articles")
    @ResponseStatus(HttpStatus.CREATED)
    public String create(@RequestBody String title) {
        return "CREATED:" + title;
    }

    @PutMapping("/api/articles/{id}")
    public String update(@PathVariable String id, @RequestBody String title) {
        return "UPDATED:" + id + ":" + title;
    }

    @DeleteMapping("/api/articles/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        // Demo không lưu database; authorization được kiểm tra trước.
    }
}
```

Controller chỉ tạo chuỗi phản hồi để quan sát quyền. Nó **không cài đặt lưu/sửa/xóa thật** hoặc object-level authorization. Trong một ứng dụng thật, cần kiểm tra tenant, owner, trạng thái bài, validation input, business transaction và audit.

### 9.6. Test MockMvc phân biệt role, method, path, CSRF

File `src/test/java/example/methodpath/MethodPathAuthorizationTest.java`:

```java
package example.methodpath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodPathAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousReaderRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/articles"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicCredentialIsRejected() throws Exception {
        mvc.perform(get("/api/articles")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerMayReadCollectionAndIndividualArticle() throws Exception {
        mvc.perform(get("/api/articles")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("ARTICLES"));

        mvc.perform(get("/api/articles/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("ARTICLE:42"));
    }

    @Test
    void readerCannotCreateEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/articles")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Example"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorMayCreateAndUpdate() throws Exception {
        mvc.perform(post("/api/articles")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Example"))
            .andExpect(status().isCreated())
            .andExpect(content().string("CREATED:Example"));

        mvc.perform(put("/api/articles/42")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Revised"))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:42:Revised"));
    }

    @Test
    void editorCannotDeleteEvenWithCsrf() throws Exception {
        mvc.perform(delete("/api/articles/42")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanDelete() throws Exception {
        mvc.perform(delete("/api/articles/42")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingCsrfBlocksEvenAnAuthorizedEditor() throws Exception {
        mvc.perform(post("/api/articles")
                .with(httpBasic("editor", "editor-pass"))
                .contentType(MediaType.TEXT_PLAIN)
                .content("Example"))
            .andExpect(status().isForbidden());
    }

    @Test
    void undeclaredPatchMethodIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(patch("/api/articles/42")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Change"))
            .andExpect(status().isForbidden());
    }

    @Test
    void nestedPathIsNotCoveredBySingleSegmentRule() throws Exception {
        mvc.perform(get("/api/articles/42/comments")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void headIsNotGrantedByExplicitGetOnlyRule() throws Exception {
        mvc.perform(head("/api/articles/42")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Giải thích vì sao cần từng nhóm assertion:**

- Không có/credential sai: HTTP Basic entry point cho **401**, chứ không suy rằng controller trả lỗi.
- GET reader: xác nhận role thấp có quyền đọc collection và item.
- POST reader: có CSRF hợp lệ nhưng vẫn **403** do thiếu role Editor/Admin.
- POST/PUT editor: có CSRF và role, được phép đi vào MVC/controller; status/body khớp code.
- DELETE editor: CSRF hợp lệ nhưng vẫn bị từ chối bởi rule ADMIN.
- DELETE admin: có CSRF và role, controller trả 204.
- POST editor thiếu CSRF: bị từ chối bởi CSRF, **không** được dùng để chứng minh role bị sai.
- PATCH, path lồng sâu và HEAD không được cấp quyền: fallback **denyAll** ngăn các method/path chưa cho phép dù principal là admin.
- Test public cho thấy `permitAll()` cho phép request không cần authentication, còn các filter khác vẫn có thể chạy theo policy.

**Kỳ vọng:** 12 test pass trong môi trường phù hợp với dependency/mã minh họa. Đây là **kiểm tra tĩnh của bài học, chưa phải log test đã được chạy**. Nếu có khác biệt giữa matcher MVC trong phiên bản project, kết quả test là bằng chứng để sửa config ở bản thực tế, không nên tắt authorization/CSRF để “làm cho test xanh”.

### 9.7. Lệnh chạy

Tại thư mục project có `pom.xml`, cần JDK 17+ và Maven với dependencies resolve được:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Khi server chạy ở cổng 8080 mặc định (nếu cổng rảnh), có thể quan sát thao tác đọc:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/articles
curl -i -u reader:reader-pass http://localhost:8080/api/articles
curl -i -u reader:reader-pass http://localhost:8080/api/articles/42
```

Kết quả body/status dự kiến lần lượt:

```text
GET /public                           -> 200 PUBLIC_OK
GET /api/articles (anonymous)         -> 401
GET /api/articles (reader)            -> 200 ARTICLES
GET /api/articles/42 (reader)         -> 200 ARTICLE:42
```

**Không dùng ngay curl POST/PUT/DELETE trong ví dụ này mà bỏ qua CSRF token**, rồi kết luận các method bị security role chặn: khi không có CSRF token, bạn thường chỉ thấy 403 từ CsrfFilter. Dùng MockMvc `with(csrf())` như mục 9.6, hoặc triển khai một cơ chế CSRF token fetch/submit phù hợp cho client thật.

Thông tin đăng nhập `reader-pass`/`editor-pass`/`admin-pass` là fixture; không triển khai ra public Internet, và không ghi credential thật vào shell history hoặc log.

## 10. Hướng dẫn rà soát policy trước khi deploy

### Bước 1 — Liệt kê ma trận hành động theo resource

Ví dụ một tài nguyên article:

| Endpoint | Method | Reader | Editor | Admin |
|---|---|---|---|---|
| `/api/articles` | GET | Allow | Allow | Allow |
| `/api/articles/{id}` | GET | Allow | Allow | Allow |
| `/api/articles` | POST | Deny | Allow | Allow |
| `/api/articles/{id}` | PUT | Deny | Allow | Allow |
| `/api/articles/{id}` | DELETE | Deny | Deny | Allow |
| `/api/articles/{id}` | PATCH | Deny | Deny | Deny (chưa được triển khai) |
| `/api/articles/{id}/comments` | GET | Deny | Deny | Deny (chưa được triển khai) |

Ma trận nên được duy trì cùng API spec và integration tests. Khi thêm PATCH, cần bổ sung rule có method, route controller và test role cho phép/từ chối. Không tự dựa vào “admin có tất cả quyền” nếu chính sách đòi endpoint chỉ được phép khi khai báo tường minh.

### Bước 2 — Xem thứ tự matcher

- Rule công khai/đặc thù trước khi có rule tổng quát.
- Rule theo HTTP method cần nằm **trước** rule chỉ theo path trùng phạm vi.
- Rule `/api/**` hoặc `anyRequest()` thường ở cuối và phải có chủ đích.
- Kiểm tra cả các prefix tương tự như `/api/article`, `/api/articles-old`, `/api/admin`, servlet context path và lowercase/uppercase.

### Bước 3 — Kiểm tra response và điều kiện tiên quyết

- 401/redirect nếu thiếu authentication;
- 403 khi có authentication nhưng thiếu authority;
- 403 do CSRF nếu request nguy hiểm thiếu token;
- 404/405 chỉ khi request được phép đi đến MVC nhưng route/method không tồn tại — đừng xem 404/405 là security policy đủ mạnh;
- CORS preflight có cấu hình đúng, không vô tình lộ toàn bộ API;
- HEAD/OPTIONS có quyết định tường minh.

### Bước 4 — Kiểm tra quyền tại resource/service

HTTP path + method chỉ kiểm tra lớp bên ngoài. Hãy thêm logic cho owner, tenant, field-level access, article state hoặc điều kiện nghiệp vụ ngay nơi thao tác dữ liệu. Không xem `hasRole("EDITOR")` là đủ để cập nhật bài của người khác.

### Bước 5 — Test cả đường đi không dự kiến

Hãy dùng test cho các method chưa khai báo, path lồng sâu, path khác prefix, request thiếu role, credential sai, thiếu CSRF, filter chain khác và URL sau proxy. Để mặc định `denyAll` giúp lỗi cấu hình lộ rõ thành test fail thay vì âm thầm mở quyền.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Reader DELETE vẫn được xử lý | Rule `authenticated()` rộng đứng trước rule DELETE ADMIN | Đưa rule method+path cụ thể lên trước, giữ deny-by-default |
| Editor POST bị 403 dù role đúng | CSRF token thiếu hoặc security matcher khác với dự kiến | Gửi CSRF hợp lệ trong test, kiểm tra chain được chọn |
| GET vào endpoint cần đọc trả 401 | Thiếu credential, session hết hạn hoặc HTTP Basic sai | Phân biệt authentication vs authorization |
| Cùng URL GET 200 nhưng PUT 403 | Mỗi method có rule riêng hoặc CSRF | Đây có thể là policy đúng; xem quyền và CSRF |
| Tên role đúng nhưng rule vẫn 403 | Nhầm `ROLE_` prefix hoặc authorities khác thiết kế | Kiểm tra Authentication.getAuthorities và hasRole/hasAuthority |
| Có rule POST đúng nhưng không bao giờ được dùng | Rule path rộng trước nó đã match | Kiểm tra thứ tự requestMatchers |
| Endpoint mới vô tình bị công khai | Dùng fallback `authenticated()`/`permitAll()` quá rộng | Dùng `anyRequest().denyAll()` và thêm test khi mở endpoint |
| Endpoint mới liên tục 403 | Có fallback denyAll nhưng chưa khai báo rule hợp lệ | Thêm method+path tường minh và test |
| HEAD được xử lý khác GET | Security matcher match method khác nhau | Khai báo/test HEAD nếu cần |
| OPTIONS CORS bị từ chối | Không tích hợp CORS trước policy bảo mật phù hợp | Cấu hình CORS đúng, test preflight từ origin hợp lệ |
| Path encoded/forward khác dự kiến | Servlet firewall/PathPattern/proxy xử lý URL khác | Test URL thực tế, kiểm tra effective method/path |
| @WithMockUser pass nhưng production lỗi | Test mock principal bỏ qua authentication flow/cookie/token | Dùng MockMvc với Basic/form/bearer theo ứng dụng thực |
| User có role được phép nhưng sửa dữ liệu tenant khác | Thiếu object-level authorization | Kiểm tra ownership/tenant trong service và dữ liệu |
| Cùng URL bị policy khác khi di chuyển giữa /api và /web | SecurityFilterChains matcher/order sai | Test chain selection và fallback |

**Nguyên tắc debug:** trước tiên ghi nhận method thực, path thực, chain được chọn, Authentication và authorities, CSRF outcome và rule đầu tiên khớp. Không chỉ nhìn status code hay tên controller rồi sửa ngẫu nhiên.

## 12. Checklist cuối bài

- [ ] Có ma trận endpoint × HTTP method × quyền/ngữ cảnh truy cập rõ ràng.
- [ ] `requestMatchers(HttpMethod.X, "...")` dùng method cụ thể cho hành động nhạy cảm.
- [ ] Rule cụ thể đứng trước rule tổng quát; không có `authenticated()` rộng che role rule.
- [ ] `securityMatcher` của từng SecurityFilterChain đúng prefix và order.
- [ ] Những method/path không khai báo rơi vào `denyAll()`, không dựa vào 404/405.
- [ ] `hasRole` và `hasAuthority` được chọn đúng theo mapping của Authentication.
- [ ] API client và authentication entry point trả status phù hợp (401/403 hoặc redirect form login).
- [ ] CSRF được phân tích theo cơ chế credential của client; với cookie/form/Basic browser, không tắt tùy tiện.
- [ ] CORS preflight, HEAD, OPTIONS, encoded path, proxy/context path và forward/error dispatch đã được kiểm thử nếu hệ thống sử dụng.
- [ ] Authorization tại service kiểm tra ownership, tenant và các điều kiện nghiệp vụ.
- [ ] Integration tests có cả đường cho phép và từ chối cho mỗi method, cùng test unknown method/path.
- [ ] Không log credentials; có audit hợp lý đối với hành động ghi/xóa.

### Câu hỏi tự kiểm tra

**1.** Có `requestMatchers("/api/**").authenticated()` trước `requestMatchers(HttpMethod.DELETE, "/api/articles/*").hasRole("ADMIN")`. Reader được xác thực có thể tới DELETE route không?  
**Đáp án:** Rule rộng đứng trước có thể match và cấp qua bước authorization cho reader, khiến rule ADMIN không được sử dụng. Đó là cấu hình sai; cần sắp xếp đúng và dùng fallback denyAll.

**2.** Vì sao GET và DELETE cùng `/api/articles/42` có thể có quyền khác nhau?  
**Đáp án:** `RequestMatcher` có thể kiểm tra đồng thời HTTP method và path. Đọc một bài có rủi ro khác xóa bài.

**3.** Editor POST và thiếu CSRF nhận 403. Có thể kết luận Editor thiếu quyền tạo không?  
**Đáp án:** Không. Có thể `CsrfFilter` đã từ chối trước authorization. Cần gửi CSRF hợp lệ rồi kiểm chứng rule role.

**4.** Dùng `hasRole("ADMIN")` với authority có tên gì theo mặc định?  
**Đáp án:** Thường là `ROLE_ADMIN`, trừ khi hệ thống đã tùy biến cách dùng role prefix/authority mapping.

**5.** Khi nào `HEAD` hoặc `OPTIONS` cần rule riêng?  
**Đáp án:** Khi API/client/framework sử dụng chúng và có quyết định bảo mật cụ thể; đừng suy ra matcher GET tự cho phép HEAD hay CORS preflight tự được phép.

**6.** Tại sao `anyRequest().denyAll()` thường tốt cho tài nguyên nhạy cảm?  
**Đáp án:** Route/method mới sẽ bị chặn cho đến khi nhà phát triển khai báo quyền có chủ đích và bổ sung test.

**7.** `POST /api/articles` chỉ role Editor có đủ ngăn Editor tạo bài ở tenant khác không?  
**Đáp án:** Không. HTTP rule biết method/path/authorities nhưng không tự xác minh ownership/tenant của dữ liệu; cần kiểm tra nghiệp vụ.

**Kết luận:** thiết kế phân quyền HTTP trong Spring Security Servlet bằng **method + path** phải được viết như một ma trận hành động: **rule cụ thể trước, method rõ ràng, authority phù hợp, deny-by-default sau cùng**. Kết hợp với CSRF, CORS, authentication entry point và object-level authorization để policy vừa chính xác vừa không mở rộng quyền ngoài ý muốn.