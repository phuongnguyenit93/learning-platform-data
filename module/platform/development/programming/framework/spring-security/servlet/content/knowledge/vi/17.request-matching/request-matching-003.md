# Khớp chính xác, ký tự đại diện và biến đường dẫn

> **Phạm vi:** Spring Security 6.x trên **Servlet stack**, Spring Boot 3.x và Java 17+. Bài học giải thích cách một HTTP request được so khớp với các quy tắc bảo mật theo **đường dẫn chính xác**, **ký tự đại diện** (`*`, `**`) và **biến đường dẫn** (`{id}`, `{id:regex}`). Phân biệt `securityMatcher` (chọn `SecurityFilterChain`) với `requestMatchers` (chọn quy tắc cấp quyền trong chain); lưu ý khác biệt giữa `MvcRequestMatcher`, `AntPathRequestMatcher` và `PathPatternRequestMatcher`. Có dự án Spring Boot hoàn chỉnh với MockMvc tests, bảng đối chiếu và checklist lỗi phổ biến.

## 1. Matching là bước đầu của authorization

Ứng dụng có thể có các route:

```text
GET  /api/ping
GET  /api/books
GET  /api/books/42
GET  /api/books/42/chapters
POST /api/books
GET  /api/files/guide.json
GET  /api/admin/audit
GET  /external
```

Mỗi route cần một policy rõ ràng: route public, route bắt buộc đăng nhập, route chỉ dành cho role quản trị, hoặc route bị cấm. Matching có nghĩa **quyết định HTTP request hiện tại thuộc tập URL/method nào**. Authorization dựa trên kết quả đó để áp dụng yêu cầu quyền.

Một lỗi nhỏ trong pattern có thể trở thành lỗ hổng: nếu `/api/**` đã `permitAll()` nhưng nhánh `/api/admin/**` được bảo vệ ở phía sau, rule rộng có thể khiến rule admin không được áp dụng. Ngược lại, một matcher quá hẹp làm ứng dụng trả 401/403 dù controller có route.

### Những câu hỏi cần trả lời trước khi viết rule

1. URL thực tế của request có **path** và **HTTP method** nào?
2. Pattern là literal, wildcard, variable hay regex constrained variable?
3. Matcher sử dụng engine **Spring MVC/PathPattern** hay **Ant-style**?
4. Matcher chọn **cả filter chain** hay chỉ chọn một **authorization rule**?
5. Hai rules có chồng lấn không, và rule nào xuất hiện trước?
6. Nếu không có rule nào match, hệ thống có deny-by-default không?

## 2. Hai tầng request matching trong Spring Security Servlet

Spring Security nối vào Servlet qua `DelegatingFilterProxy`, thường ủy quyền cho `FilterChainProxy`. Nó có thể quản lý nhiều `SecurityFilterChain`; mỗi chain có filter và authorization rules riêng.

```text
HTTP request
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    +--> SecurityFilterChain @Order(1)
    |       securityMatcher("/api/**")?
    |             |
    |             +--> match: chọn chain này
    |                       |
    |                       +--> Security filters
    |                       +--> AuthorizationFilter
    |                                |
    |                                +--> requestMatchers(...) theo thứ tự
    |
    +--> SecurityFilterChain @Order(2)
            match-all fallback -> denyAll()
```

**Tầng 1: `securityMatcher(...)`** quyết định **request có đi vào SecurityFilterChain này hay không**. Nếu có nhiều chains, Spring Security chọn chain đầu tiên match theo thứ tự ưu tiên; nó không merge mọi chain cùng match.

**Tầng 2: `authorizeHttpRequests(...requestMatchers(...))`** quyết định **authorization rule nào áp dụng sau khi đã chọn chain**. Với cơ chế request matcher delegation, **rule đầu tiên match thường thắng**; đừng kỳ vọng rule cụ thể hơn tự vượt rule rộng đặt trước.

Ví dụ `GET /api/books/42`:

```text
securityMatcher("/api/**")             -> true
requestMatchers(GET, "/api/ping")       -> false
requestMatchers(GET, "/api/books")      -> false
requestMatchers(GET, "/api/books/{id}") -> true
                                         |
                                         v
                                    authenticated()
```

Nếu chain có `securityMatcher("/api/**")` thì rule `requestMatchers("/admin/**")` bên trong **không bảo vệ được `/admin/**`**, vì request đó không vào API chain. Cần chain khác hoặc điều chỉnh chain matcher.

## 3. Exact match: path literal

Exact match dùng path không có wildcard hay biến. Ví dụ trong cấu hình:

```java
// Fragment bên trong authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/ping").permitAll()
```

Đoạn này ràng buộc path `/api/ping` và HTTP method GET.

| Request | Có khớp rule GET `/api/ping`? |
| --- | --- |
| `GET /api/ping` | Có |
| `GET /api/ping?debug=true` | Có; query không phải path |
| `GET /api/ping/extra` | Không |
| `GET /api/pings` | Không |
| `POST /api/ping` | Không do method |
| `GET /API/ping` | Thông thường không vì case-sensitive trong cấu hình mặc định |

### Exact không đồng nghĩa prefix

`/api/ping` không match `/api/ping/extra`. Tương tự, `/api/user` không tự match `/api/users`. Nếu chỉ muốn một endpoint public, **dùng literal** thay vì nới `/api/**`.

### Path so với full URL

Đây **không** phải cách viết path matcher đúng:

```java
// Anti-pattern: Spring Security path matcher không tự so full URL.
.requestMatchers("https://example.com/api/ping").permitAll()
```

Cấu hình thường so path request theo ngữ cảnh Servlet/MVC; nó không kiểm tra host/port/scheme chỉ vì có chuỗi đó trong matcher. Nếu policy phụ thuộc host hoặc tenant, cần thiết kế `RequestMatcher` chuyên trách cùng trust boundary đối với proxy/forwarded headers.

### Query không làm thay path

`GET /api/books/42?lang=vi` và `GET /api/books/42?lang=en` có cùng path. Nếu permission phụ thuộc query parameter, cần logic riêng và phải xác minh parameter đó không phải dữ liệu client có thể tùy ý giả mạo để nâng quyền.

### Trailing slash

`/api/ping` và `/api/ping/` **không phải lúc nào cũng tương đương**. Với Spring MVC 6/PathPatternParser, optional trailing slash matching không còn được mặc định tự bật như một số cấu hình cũ. Luôn test thực tế, nhất là khi nâng Spring Boot hoặc reverse proxy rewrite đường dẫn.

## 4. Wildcards: `*`, `**`, `?` và hậu tố file

Cú pháp thông dụng trong Spring MVC PathPattern:

- `*`: khớp **các ký tự trong một path segment**; không đi qua dấu `/` sang segment tiếp theo.
- `?`: ký hiệu wildcard **một ký tự trong segment** theo engine hỗ trợ; không nhầm với dấu hỏi phân cách URL query.
- `**`: khớp **không hoặc nhiều segment** ở **cuối pattern** theo `PathPatternParser`.
- `*.json`: khớp file name có hậu tố `.json` trong **một segment**.
- `{*rest}`: kiểu capture nhiều segment còn lại ở cuối trong PathPatternParser.

### 4.1. Bảng khớp các path

Giả định `PathPatternParser` và không thay đổi cấu hình mặc định:

| Pattern | `/api/books` | `/api/books/42` | `/api/books/42/chapters` |
| --- | :---: | :---: | :---: |
| `/api/books` | Có | Không | Không |
| `/api/books/*` | Không | Có | Không |
| `/api/books/**` | Có | Có | Có |
| `/api/books/{id}` | Không | Có | Không |
| `/api/books/{id:[0-9]+}` | Không | Có | Không |
| `/api/books/*/chapters` | Không | Không | Có |

**Cần nắm đúng phạm vi:** `/api/books/**` bao phủ cả `/api/books/42/chapters/1` hoặc `/api/books/private/reports`. Nếu chỉ muốn một sách theo id, `/api/books/{id}` hẹp hơn và ít rủi ro mở nhầm subresources.

### 4.2. `*` chỉ một segment

```text
Pattern: /api/books/*

/api/books/42            -> match
/api/books/abc           -> match
/api/books/42/chapters   -> không match
/api/books               -> không match
```

`*` không kiểm tra id phải là số, không tự suy ra quyền người dùng, và không match qua dấu slash. Nếu hệ thống muốn một số nguyên, dùng regex constrained variable hoặc validate input tại tầng nghiệp vụ.

### 4.3. `**` có thể match nhiều segment

```text
Pattern: /api/books/**

/api/books                 -> match theo PathPattern
/api/books/42              -> match
/api/books/42/chapters     -> match
/api/books/42/chapters/1   -> match
```

Với `PathPatternParser`, `**` chỉ được hỗ trợ ở **cuối pattern** (tương tự `{*path}`). Một số matcher Ant lịch sử có cú pháp chấp nhận `/**/` ở giữa; **không copy nguyên pattern đó sang MVC/PathPattern** rồi tự cho là tương đương.

### 4.4. `*.json` không có nghĩa mở mọi tệp .json ở mọi cấp

`/api/files/*.json` có thể match `/api/files/guide.json` nhưng không match `/api/files/reports/guide.json` và không match `/api/files/guide.txt`.

Ngay cả khi route public chỉ cho .json, tầng đọc file vẫn cần chống path traversal, giới hạn file thực tế và kiểm tra quyền với đối tượng: Security matcher chỉ chọn URL, không tự làm filesystem authorization.

### 4.5. Wildcard `?` khác dấu query `?`

Trong path pattern, `?` biểu diễn một ký tự theo syntax của matcher hỗ trợ; trong HTTP URL, `?` phân cách query string. Ví dụ URL `/api/v1?debug=true` có path `/api/v1` và query `debug=true`. Không dùng dấu hỏi trong path pattern để trông chờ nó xử lý điều kiện query.

## 5. Biến đường dẫn `{id}` và regex `{id:regex}`

Route controller Spring MVC:

```java
@GetMapping("/api/books/{id}")
public String book(@PathVariable String id) {
    return "book-" + id;
}
```

Ở URL `/api/books/42`, biến `id` là `42`. Security có thể dùng matching pattern tương ứng:

```java
// Fragment khi đã có MvcRequestMatcher.Builder mvc:
.requestMatchers(mvc.pattern(
        HttpMethod.GET, "/api/books/{id}"))
.authenticated()
```

`{id}` chỉ mô tả **một path segment**, không kiểm tra kiểu dữ liệu, không truy vấn database và **không kiểm tra user sở hữu record**.

### 5.1. Regex constrained variable

`/api/books/{id:[0-9]+}` yêu cầu segment id gồm một hoặc nhiều chữ số:

```text
/api/books/42       -> match
/api/books/007      -> match
/api/books/abc      -> không match
/api/books/42/abc   -> không match
```

Cú pháp này tương thích `PathPatternParser` trong Spring MVC. Regex chỉ giúp phân loại request, không chứng minh id tồn tại hoặc được user truy cập. Với id số có leading zeros hay giới hạn độ dài, ứng dụng còn cần validation/service policy riêng.

### 5.2. Biến controller và biến security có thể khác nhau

Có thể controller định nghĩa `@GetMapping("/api/books/{id}")` nhưng security chỉ permit số `{id:[0-9]+}`. Khi đó `GET /api/books/abc` có **MVC handler nếu đến controller**, nhưng Security có thể chặn request **trước khi controller chạy** vì không match rule được phép.

Đây là lựa chọn có chủ ý nếu đúng nghiệp vụ. Ngược lại, một security pattern quá rộng so với controller có thể mở cả endpoint mới vô tình đặt cùng prefix.

### 5.3. Request path variables trong custom authorization

Khi `MvcRequestMatcher` trích xuất variables, `RequestAuthorizationContext.getVariables()` có thể cung cấp map đó cho `AuthorizationManager`. Điều này hữu ích để kiểm tra tài nguyên theo id/tenant hoặc tên principal.

Pseudocode minh họa contract, **không phải** logic bảo mật production:

```java
// requestMatchers(mvc.pattern(GET, "/api/users/{username}/profile"))
// .access((authenticationSupplier, context) -> {
//     String usernameFromUrl = context.getVariables().get("username");
//     Authentication current = authenticationSupplier.get();
//
//     // Phải check authenticated không anonymous, rồi xác minh
//     // username/tenant/ownership theo policy server-side trước khi grant.
//     return new AuthorizationDecision(/* allowed after validation */);
// });
```

Đừng chỉ kiểm tra `userId` client gửi bằng cách so với một header khác do client tự đặt. Với multi-tenant và delegated access, quyền cần dựa trên principal đã xác thực và dữ liệu server-side. Đây là điểm quan trọng để chống **IDOR/BOLA**.

## 6. Loại matcher quyết định semantics: MVC, Ant hay PathPattern

Các APIs quan trọng:

| API/class | Thường dùng | Lưu ý |
| --- | --- | --- |
| `MvcRequestMatcher` | Khi muốn matching tương thích Spring MVC | Dùng `HandlerMappingIntrospector`; hiểu context path và servlet path |
| `AntPathRequestMatcher` | Hệ thống cũ dùng pattern Ant | Cú pháp/normalization có thể khác MVC, đặc biệt `**` |
| `PathPatternRequestMatcher` | Phiên bản Spring Security hỗ trợ PathPattern matching trực tiếp | Parser cần nhất quán với app; `**` chỉ cuối |
| `RequestMatcher` tự viết | Host, tenant, header, query hoặc điều kiện khác | Phải review trust boundary/encoding/routing |

Trong ví dụ Boot 3.3.5 bên dưới, ta khởi tạo `MvcRequestMatcher.Builder` **tường minh** với `HandlerMappingIntrospector`. Việc này tránh đoán xem overload `requestMatchers(String...)` sẽ chọn engine nào dựa trên classpath/version.

### 6.1. String overload có thể phụ thuộc môi trường

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

Spring Security có thể chọn matcher phù hợp với Spring MVC nếu có MVC trên classpath, nhưng khi nhiều Servlet registrations hoặc custom MVC config, nên dùng matcher tường minh để thể hiện intent và giảm nhầm lẫn. Không áp đặt hành vi mặc định của một version cho mọi project.

### 6.2. Chớ trộn URL matching với MVC routing thiếu nhất quán

Nếu MVC xử lý một path theo `PathPatternParser` nhưng Security tự dùng `AntPathRequestMatcher` với quy tắc khác, có thể xảy ra trường hợp:

- MVC map request vào endpoint quản trị nhưng Security match một public rule khác;
- một dấu slash cuối được MVC chấp nhận nhưng Security không;
- encoded/semicolon path được tầng này xử lý khác tầng kia;
- pattern `/**/admin` hợp lệ ở engine này nhưng không hợp lệ ở engine kia;
- servlet path được tính hai lần hoặc bị bỏ qua.

**Mục tiêu:** đường dẫn được bảo vệ phải được hiểu tương đương ở mọi tầng có quyền quyết định identity/authorization. Kiểm thử các request biên và giữ firewall chính sách chặt.

### 6.3. Servlet path và context path

Context path là tiền tố khi app deploy vào một context, ví dụ browser gọi `/shop/api/books/42` nhưng ứng dụng có route `/api/books/42`. Matcher trong Servlet thường không tự cần thêm `/shop` vì container tách context path.

Nếu `DispatcherServlet` được mount ở servlet path `/app`, có thể cần:

```java
MvcRequestMatcher.Builder mvc =
        new MvcRequestMatcher.Builder(introspector)
                .servletPath("/app");

RequestMatcher matcher =
        mvc.pattern("/api/books/{id}");
```

Đây là fragment; cần imports `MvcRequestMatcher`, `HandlerMappingIntrospector`, `RequestMatcher`. Phải hiểu pattern tương đối với servlet path theo builder. Đừng lẫn `server.servlet.context-path` với `spring.mvc.servlet.path`.

## 7. Ràng buộc HTTP method

Hai policy này **không tương đương**:

```java
.requestMatchers("/api/books").permitAll()
```

```java
.requestMatchers(HttpMethod.GET, "/api/books").permitAll()
```

Dạng đầu có thể match nhiều methods trên path đó; dạng sau chỉ match GET. Nếu có `POST /api/books` tạo dữ liệu, một rule path-only `permitAll` có thể vô tình mở quyền nếu các lớp bảo vệ khác bị thay đổi.

Ví dụ:

```java
.requestMatchers(mvc.pattern(HttpMethod.GET, "/api/books"))
.permitAll()

.requestMatchers(mvc.pattern(HttpMethod.POST, "/api/books"))
.hasRole("EDITOR")
```

**HEAD và OPTIONS:** Spring MVC có thể hỗ trợ HEAD qua GET mapping, nhưng `HttpMethod.GET` matcher không tự match HEAD. CORS preflight thường là OPTIONS; cần cấu hình `http.cors(...)`/MVC CORS chính xác thay vì dùng broad `permitAll OPTIONS /**` mà không hiểu nguồn request.

**CSRF:** nếu API dùng session cookie hoặc browser credentials tự gửi, các request thay đổi trạng thái có thể cần CSRF token. CSRF 403 là cơ chế độc lập với hasRole. Khi test `POST` được phép, thêm `with(csrf())` để kiểm chứng rule role thay vì vô tình chỉ chứng minh CSRF đang chặn.

## 8. Thứ tự các quy tắc: match đầu tiên quyết định

Anti-pattern:

```java
// SAI: rule rộng làm rule admin bên dưới không có hiệu lực.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll());
```

Với `GET /api/admin/audit`, rule `/api/**` đã match trước và có thể cho phép **bất kỳ authenticated user** vào. Không có cơ chế tự chọn matcher cụ thể nhất thay cho thứ tự cấu hình.

Cách sắp xếp phù hợp hơn:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll());
```

### Literal vs variable overlap

`/api/users/me` cũng có thể match `/api/users/{id}` với `id="me"`. Nếu literal `/me` có policy khác với route biến `/{id}`, đặt literal trước hoặc dùng regex và authorization manager phù hợp.

### Fallback deny và chain coverage

`anyRequest().denyAll()` chỉ bảo vệ **trong chain đã được chọn**. Nếu chỉ định nghĩa chain `securityMatcher("/api/**")` mà không có chain bao phủ mọi request còn lại, các route bên ngoài API có thể **không được bảo vệ bởi Spring Security**.

Vì thế ví dụ hoàn chỉnh gồm một chain ưu tiên cho `/api/**` và một fallback chain match-all để deny-by-default. `@Order` của bean sắp thứ tự chains, **không** sắp thứ tự rule authorization bên trong.

## 9. Dự án Spring Boot: exact, wildcard, variable và method

Dùng **Java 17+**, Spring Boot **3.3.5** (Spring Security 6.x), Gradle **8.5**. Demo có hai user local:

- `reader / readerPass!` với `ROLE_READER`.
- `editor / editorPass!` với `ROLE_EDITOR`.

Tài khoản và mật khẩu này **chỉ dùng cho bài học**, không phải secret production. Mật khẩu được hash bằng BCrypt.

Chính sách URL:

| Request | Quyền |
| --- | --- |
| `GET /api/ping` | Public, literal exact |
| `GET /api/books` | Public, literal exact |
| `GET /api/files/*.json` | Public, wildcard tên file |
| `GET /api/books/{id:[0-9]+}` | Authenticated, id một segment gồm số |
| `GET /api/books/*/chapters` | `ROLE_EDITOR`, một segment |
| `GET /api/admin/**` | `ROLE_EDITOR`, mọi cấp con |
| `POST /api/books` | `ROLE_EDITOR` + CSRF |
| Mọi request còn lại | Deny |

### 9.1. File tree và Gradle

```text
request-matcher-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    ApiController.java
  src/test/java/demo/
    RequestMatcherTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'request-matcher-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
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

### 9.2. DemoApplication

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 9.3. SecurityConfig

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("readerPass!"))
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("editorPass!"))
                .roles("EDITOR")
                .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            HandlerMappingIntrospector introspector) throws Exception {

        MvcRequestMatcher.Builder mvc =
                new MvcRequestMatcher.Builder(introspector);

        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/ping")).permitAll()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/books")).permitAll()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/files/*.json")).permitAll()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/books/{id:[0-9]+}"))
                        .authenticated()
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/books/*/chapters"))
                        .hasRole("EDITOR")
                .requestMatchers(mvc.pattern(
                        HttpMethod.GET, "/api/admin/**"))
                        .hasRole("EDITOR")
                .requestMatchers(mvc.pattern(
                        HttpMethod.POST, "/api/books"))
                        .hasRole("EDITOR")
                .anyRequest().denyAll());

        http.httpBasic(Customizer.withDefaults());

        // Giữ CSRF bật; POST cần token CSRF hợp lệ.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Giải thích:**

1. `@Order(1)` chỉ áp dụng cho `/api/**`. `@Order(2)` là catch-all fallback không cho phép request nào ngoài API nếu chưa thiết kế policy riêng.
2. `MvcRequestMatcher.Builder` dùng `HandlerMappingIntrospector` nên authorization matching thống nhất với ngữ nghĩa Spring MVC trong project. Cách này tránh phụ thuộc lựa chọn động của String overload.
3. `HttpMethod.GET` và `POST` ngăn một public GET rule vô tình áp dụng cho POST.
4. `{id:[0-9]+}` dùng regex constraint; endpoint `GET /api/books/abc` bị rule cuối deny dù controller có thể map nó.
5. `/api/files/*.json` chỉ public tên file có hậu tố `.json` trong một segment.
6. `/api/admin/**` chỉ cho user có `ROLE_EDITOR`. `hasRole("EDITOR")` tự kiểm tra authority `ROLE_EDITOR`; `roles("EDITOR")` của account phù hợp.
7. `httpBasic` cho phép MockMvc thử authentication thật thay vì mock Principal sẵn có.
8. CSRF vẫn bật; `POST` phải có token. Với production API browser/cookie và CORS, cần phân tích threat model thay vì tắt CSRF tùy tiện.

### 9.4. ApiController

`src/main/java/demo/ApiController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/books")
    public String books() {
        return "books";
    }

    @GetMapping("/api/books/{id}")
    public String book(@PathVariable String id) {
        return "book-" + id;
    }

    @GetMapping("/api/books/{id}/chapters")
    public String chapters(@PathVariable String id) {
        return "chapters-" + id;
    }

    @PostMapping("/api/books")
    public String createBook() {
        return "created";
    }

    @GetMapping("/api/files/{name}")
    public String file(@PathVariable String name) {
        return "file-" + name;
    }

    @GetMapping("/api/admin/{action}")
    public String admin(@PathVariable String action) {
        return "admin-" + action;
    }

    @GetMapping("/external")
    public String external() {
        return "external";
    }
}
```

**Quan sát:** controller có mapping `GET /api/books/{id}` rộng hơn rule `GET /api/books/{id:[0-9]+}` ở Security. Điều đó có nghĩa request chứa id chữ có thể bị **Security deny trước** và không đến controller. Ở hệ thống thật, nên thống nhất policy và route, test đầy đủ thay vì chủ động tạo khác biệt không cần thiết.

### 9.5. MockMvc tests

`src/test/java/demo/RequestMatcherTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RequestMatcherTest {

    @Autowired
    MockMvc mvc;

    @Test
    void exactPublicEndpointsAreAccessible() throws Exception {
        mvc.perform(get("/api/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
        mvc.perform(get("/api/books"))
                .andExpect(status().isOk())
                .andExpect(content().string("books"));
    }

    @Test
    void exactMatchDoesNotOpenAChildPath() throws Exception {
        mvc.perform(get("/api/ping/extra")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void numericPathVariableRequiresLogin() throws Exception {
        mvc.perform(get("/api/books/42"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/books/42")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("book-42"));
    }

    @Test
    void nonNumericPathVariableIsDeniedBeforeMvc() throws Exception {
        mvc.perform(get("/api/books/abc")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void oneSegmentWildcardDoesNotOpenNestedRoutes() throws Exception {
        mvc.perform(get("/api/books/42/chapters")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/books/42/chapters")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("chapters-42"));
        mvc.perform(get("/api/books/42/chapters/extra")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void suffixWildcardOnlyAllowsJson() throws Exception {
        mvc.perform(get("/api/files/guide.json"))
                .andExpect(status().isOk())
                .andExpect(content().string("file-guide.json"));
        mvc.perform(get("/api/files/guide.txt")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminDoubleStarStillChecksRole() throws Exception {
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("reader", "readerPass!")))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/audit")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin-audit"));
    }

    @Test
    void postHasDifferentPolicyAndNeedsCsrf() throws Exception {
        mvc.perform(post("/api/books")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/books")
                        .with(httpBasic("reader", "readerPass!"))
                        .with(csrf()))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/books")
                        .with(httpBasic("editor", "editorPass!"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("created"));
    }

    @Test
    void fallbackChainBlocksOutsideApi() throws Exception {
        mvc.perform(get("/external")
                        .with(httpBasic("editor", "editorPass!")))
                .andExpect(status().isForbidden());
    }

    @Test
    void queryDoesNotAlterExactPath() throws Exception {
        mvc.perform(get("/api/ping").param("debug", "true"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
```

**Kết quả kỳ vọng:** 10 test PASS với project/cấu hình demo. Test cố ý dùng `httpBasic(...)` để request đi qua authentication logic thật. Đối với những URL `denyAll`, test gửi credentials hợp lệ để expected **403** (đã xác thực nhưng bị từ chối); nếu anonymous, HTTP Basic entry point có thể trả **401** thay vì 403. Điều đó khác với 403 do thiếu CSRF token.

**Các mặt được kiểm thử:**

- Literal exact không mở path con.
- Variable regex chỉ cho id có số và cần authentication.
- `*` chỉ một segment, không cho nested path.
- `*.json` không mở các đuôi file khác.
- `**` cover các URL admin nhưng vẫn yêu cầu role.
- `GET` và `POST` cùng path có policy khác, CSRF vẫn hoạt động.
- Fallback chain deny các route ngoài `/api/**`.
- Query string không làm exact path matcher đổi kết quả.

### 9.6. Chạy và thử với curl

```bash
gradle test
gradle bootRun
```

Nếu đã có Gradle Wrapper: dùng `./gradlew test`/`./gradlew bootRun` (macOS/Linux) hoặc `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows).

```bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/books/42
curl -i -u reader:readerPass! \
     http://localhost:8080/api/books/42
curl -i -u reader:readerPass! \
     http://localhost:8080/api/admin/audit
curl -i -u editor:editorPass! \
     http://localhost:8080/api/admin/audit
curl -i http://localhost:8080/api/files/guide.json
```

Kết quả dự kiến theo thứ tự: `200`, `401`, `200`, `403`, `200`, `200`. Không cần biết hash BCrypt thực tế để đối chiếu vì nó có salt ngẫu nhiên. HTTP localhost **chỉ dành cho thực hành**; Basic credentials trong production phải đi qua HTTPS.

Trong demo CSRF đang bật, lệnh POST trực tiếp không có CSRF token có thể trả **403**. `with(csrf())` ở MockMvc là công cụ tạo request kiểm thử, không phải lời khuyên tự hard-code token trong HTTP client thật.

## 10. Một số edge cases dễ gây security bypass

### 10.1. Dấu slash cuối

`/api/books/42` và `/api/books/42/` có thể khác nhau theo Spring MVC 6 default. Khi nâng phiên bản hoặc thêm redirect canonical URL, kiểm thử cả Security và MVC. Không mở một matcher quá rộng chỉ để “chữa” trailing slash.

### 10.2. URL encoding và firewall

`%2F`, `%2e`, `..`, double-slash, semicolon/matrix variables, Unicode normalization và encoded percent có thể được xử lý khác nhau bởi proxy, container, MVC và Security. `StrictHttpFirewall` có thể từ chối các request bất thường trước authorization.

Không nới firewall để cho request nguy hiểm đi qua nếu chưa hiểu cùng một đường dẫn được giải mã/chuẩn hóa thế nào ở **tất cả** tầng. Một mismatch giữa route và security pattern có thể mở dữ liệu không mong muốn.

### 10.3. Context path, servlet path, forwarded prefix

Một ứng dụng deploy ở `/myapp` có URL browser `/myapp/api/books`, nhưng matcher thường chỉ cần `/api/books` vì context path do container quản lý. Còn `spring.mvc.servlet.path` khác context path; `MvcRequestMatcher.Builder.servletPath(...)` có thể cần tùy trường hợp.

Reverse proxy có thể rewrite URI hoặc thêm `X-Forwarded-Prefix`. Hãy cấu hình forwarded header handling chỉ từ proxy đáng tin cậy và test đường dẫn **mà Servlet container thực sự nhận**, không chỉ URL browser hiển thị.

### 10.4. Controller mapping không phải quyền truy cập dữ liệu

Một path `/api/orders/{id}` có thể chỉ chọn endpoint, không kiểm tra order thuộc principal. Dùng object-level authorization và tenant binding đáng tin tại service/authorization manager; đừng nghĩ `hasRole("USER")` đủ chống IDOR/BOLA.

### 10.5. Không phải mọi request đều thuộc API chain

`/actuator/**`, `/error`, static files và các internal forwards có thể ở ngoài matcher `/api/**`. Cần fallback chain hoặc policy riêng cho endpoint thực sự dùng, kiểm tra dispatcher types và cách error handling tương tác Security. Đừng tự loại đường dẫn khỏi Spring Security bằng `web.ignoring()` khi chỉ cần `permitAll()` nhưng vẫn muốn các security filters/headers.

### 10.6. HTTP method và CORS

CORS preflight `OPTIONS` có thể đến trước request GET/POST thực. Một GET-only matcher không match OPTIONS. Cấu hình CORS ở Spring Security/MVC theo trusted origins và allowed methods, không mở “toàn bộ OPTIONS” không điều kiện rồi quên review. Với browser cookie/API token, CSRF và CORS là hai câu chuyện khác nhau: CORS quyết định JS cross-origin được đọc/gửi theo policy, CSRF bảo vệ state-changing requests.

## 11. Troubleshooting theo từng tầng

Nếu URL trả 401/403 khi tưởng phải 200 (hoặc ngược lại), kiểm tra theo trình tự:

1. Method + URI path trong request thực; không nhầm query.
2. Context path, servlet path và path proxy rewrite.
3. `SecurityFilterChain` nào được chọn, `securityMatcher` và `@Order` của chain.
4. Matcher type: `MvcRequestMatcher`, Ant hay PathPattern; có tương thích MVC?
5. Rule nào match đầu tiên trong `authorizeHttpRequests`; có broad rule che rule cụ thể?
6. `*` có match đúng một segment không; `**` đặt cuối pattern có hợp lệ?
7. `{id}`/`{id:regex}` có match dữ liệu URL thực tế không?
8. HTTP method GET/POST/PUT/DELETE/HEAD/OPTIONS có đúng?
9. `authenticated()`, `hasRole`/`hasAuthority`, object ownership và tenant policy.
10. CSRF có làm POST bị 403 không; có test với token hợp lệ để tách lỗi?
11. Security block trước MVC, hay MVC thực sự trả 404/405?
12. StrictHttpFirewall, encoded URI, dấu slash cuối và CORS/proxy headers.
13. Có fallback chain phủ mọi path cần được bảo vệ không?
14. Test regression: anonymous, reader, editor với positive và negative URLs.

Có thể tạm bật DEBUG cho môi trường phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

Không log Authorization header, token, cookie hay session ID. Một dòng “Securing GET...” chỉ cho biết filter chain đang chạy, không tự chứng minh đúng authorization rule được chọn.

## 12. Những lỗi triển khai phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `/api/**` authenticated trước `/api/admin/**` hasRole | Rule admin không chạy | Đặt rule cụ thể trước |
| `securityMatcher("/api/**")` nhưng định bảo vệ `/admin/**` bên trong | Request không vào API chain | Thêm chain/fallback phù hợp |
| `/api/books/**` thay `/api/books/{id}` | Mở cả subresources | Thu hẹp pattern |
| `*` được hiểu nhầm thành nhiều path segments | URL sâu bị match sai kỳ vọng | Phân biệt `*` và `**` |
| `requestMatchers("/api/books").permitAll()` cho GET/POST | Có thể mở cả POST | Ràng buộc `HttpMethod` |
| `{id}` được coi là kiểm tra numeric ID | Rule nhận cả chữ | Dùng regex constraint và validate |
| `{id}` được coi là kiểm tra quyền sở hữu | IDOR/BOLA | Authorization mức object/tenant |
| MVC dùng PathPattern còn Security dùng Ant tùy tiện | Mismatch routing/authorization | Đồng bộ matching semantics |
| Không có fallback chain | URL ngoài chain có thể không được bảo vệ | Bổ sung chain bắt tất cả |
| Chỉ test 200 không test 403/401 | Có thể bỏ sót rule quá rộng | Test cả role/anonymous/negative |
| Thấy 403 từ POST rồi tưởng hasRole hoạt động | Thực ra CSRF chặn | Test `with(csrf())` và role riêng |
| Dùng full URL trong path matcher | Pattern không match | Chỉ dùng path; host policy tách riêng |
| Trộn context path và servlet path | Pattern bị thừa/thiếu prefix | Test deployment thực |
| Nới StrictHttpFirewall để nhận encoded slash | Tăng nguy cơ bypass | Thống nhất canonical URI |
| Có regex route nhưng không kiểm tra dữ liệu service | Chưa có resource permission | Validate và check ownership |

## 13. Checklist thiết kế policy

- [ ] Xác định rõ path, HTTP method và những endpoint cần bảo vệ.
- [ ] Chọn exact path trước khi mở wildcard rộng.
- [ ] `*` một segment; `**` nhiều segment ở cuối theo PathPattern.
- [ ] `{id}` không đồng nghĩa numeric hoặc ownership; dùng regex/authorization tương ứng.
- [ ] Matcher type phù hợp Spring MVC parser và Servlet mapping thực tế.
- [ ] `securityMatcher` bao phủ đúng các route của chain.
- [ ] `requestMatchers` theo thứ tự từ rule chuyên biệt đến rule rộng.
- [ ] Có fallback `SecurityFilterChain` match-all khi cần.
- [ ] `anyRequest().denyAll()` trong chain muốn deny-by-default.
- [ ] Ràng buộc HTTP method; có kế hoạch HEAD/OPTIONS/CORS.
- [ ] Giữ CSRF khi threat model cần, test POST có CSRF hợp lệ.
- [ ] Test slash cuối, encoding, query, forwarded prefix và custom servlet path.
- [ ] Có object-level authorization cho resource theo id/tenant.
- [ ] Test cả anonymous và nhiều roles cho URL nhạy cảm.
- [ ] Không dựa vào happy path hay status 403 do CSRF để tuyên bố quyền đúng.

## 14. Bài tập và tự kiểm tra

**Bài tập:**

1. Chỉ cho `GET /api/ping` public, nhưng `GET /api/ping/extra` không public.
2. Cho user đã đăng nhập xem `GET /api/books/{id:[0-9]+}`; từ chối `/api/books/abc`.
3. Dùng `/api/files/*.json` để chỉ public một file segment có đuôi .json.
4. Dùng `/api/admin/**` cho role `ADMIN` và đặt nó trước `/api/**` rộng.
5. Phân biệt GET/POST trên `/api/books`; dùng CSRF token khi test POST.
6. Đặt chain `securityMatcher("/api/**")` rồi fallback deny cho `/external`.
7. Với `/api/users/{userId}/orders/{orderId}`, bổ sung kiểm tra owner/tenant ngoài URL matching.
8. Deploy app có context path `/myapp` và xác minh matcher route vẫn đúng.
9. So sánh một pattern Ant dùng `**` ở giữa với PathPatternParser và viết test migration.
10. Thêm regression test để chắc route mới ở `/api/admin/reports` không bị rule public khác mở quyền.

**Câu hỏi tự kiểm tra:**

1. `/api/books` có match `/api/books/42` không? **Không.**
2. `*` khác `**` thế nào? **Một segment** so với **nhiều segment còn lại** theo syntax PathPattern.
3. `{id}` có bắt buộc id là số không? **Không**; dùng regex như `{id:[0-9]+}` nếu cần.
4. `{id}` có đảm bảo user sở hữu record không? **Không**; cần kiểm tra dữ liệu/authorization.
5. Query `?lang=vi` có ảnh hưởng exact path matcher không? **Không**, nếu matcher chỉ kiểm tra path.
6. Hai rules overlap, ai thắng? **Rule đầu tiên match** trong cấu hình authorization.
7. `securityMatcher` khác `requestMatchers` ở đâu? **Chain selection** và **authorization rule selection**.
8. Nếu không match SecurityFilterChain nào? Request có thể **không được Spring Security bảo vệ**.
9. GET public có làm POST cùng path public không? **Không khi method được ràng buộc rõ**.
10. Một path không match rule có chắc trả 404? **Không**; Security có thể chặn trước MVC.
11. Tại sao cần đồng bộ MVC/Security path engine? Để tránh **mismatch routing và authorization**.
12. Có nên dùng broad `permitAll("/api/**")` rồi hy vọng mọi controller tự kiểm tra quyền? **Không nên**; dễ bỏ sót endpoint và mở dữ liệu.

**Ghi nhớ:** Matcher exact chỉ nhắm đúng route; `*` một segment; `**` nhiều segment ở cuối `PathPattern`; `{id}`/`{id:regex}` là cách mô tả URL chứ không cấp quyền sở hữu. **`securityMatcher` chọn `SecurityFilterChain`, `requestMatchers` chọn authorization rule**. Cả hai phải đúng thứ tự, đúng HTTP method, đúng matching engine và được kiểm thử với các URL hợp lệ/lệch chuẩn. Hãy deny-by-default và áp dụng object-level authorization khi cần.
