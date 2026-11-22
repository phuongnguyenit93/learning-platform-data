# ServerWebExchangeMatcher: khớp đường dẫn và phương thức HTTP trong Spring Security reactive

## 1. Mục tiêu và tình huống sử dụng

Một ứng dụng Spring WebFlux thường có nhiều quy tắc HTTP: `GET /api/items` cho phép đọc công khai, `GET /api/items/{id}` yêu cầu tài khoản có quyền đọc, còn `POST /api/items` chỉ cho người có quyền ghi. Đồng thời, ứng dụng có thể dùng **security filter chain riêng** cho `/api/**` và chain khác cho các URL còn lại. Muốn cấu hình đúng, trước hết phải xác định **request nào khớp với điều kiện nào**.

`ServerWebExchangeMatcher` là giao diện Spring Security reactive dành cho câu hỏi đó. Matcher nhận `ServerWebExchange` (bao gồm request và response) và trả kết quả khớp ở dạng `Mono<MatchResult>`. Spring Security dùng các matcher để **chọn `SecurityWebFilterChain`** và **chọn quy tắc authorization** theo đường dẫn, HTTP method hoặc điều kiện khác.

Sau bài học, bạn có thể:
1. Mô tả `ServerWebExchangeMatcher`, `MatchResult` và kết quả reactive.
2. Dùng `ServerWebExchangeMatchers.pathMatchers(...)` để phân biệt đường dẫn và HTTP method.
3. Chọn đúng `securityMatcher(...)` hay `authorizeExchange(...).pathMatchers(...)`.
4. Hiểu thứ tự của nhiều filter chain và của các authorization rule.
5. Viết cấu hình WebFlux thực tế, kiểm thử `GET`, `POST`, `DELETE`, 200/401/403 và CSRF.
6. Nhận diện lỗi matcher quá rộng, lệch method, thiếu fallback hoặc nhầm stack Servlet.

Phạm vi bài: Spring Security **reactive/WebFlux** và việc match HTTP request. Cách xây dựng hệ thống user production, JWT, OAuth2 hay nghiệp vụ chi tiết là những chủ đề riêng.

## 2. `ServerWebExchangeMatcher` và `MatchResult`

Hợp đồng cốt lõi:

```java
public interface ServerWebExchangeMatcher {
    Mono<ServerWebExchangeMatcher.MatchResult> matches(
            ServerWebExchange exchange);
}
```

Đây là chữ ký rút gọn để **hiểu API**, không phải file class cần tự viết. Các kiểu chính:
- `ServerWebExchange` thuộc `org.springframework.web.server`: đại diện một lượt trao đổi HTTP đang được WebFlux xử lý.
- `Mono<MatchResult>`: phép đánh giá matcher được biểu diễn theo Reactor. Nó không phải `boolean` trả về trực tiếp.
- `MatchResult.isMatch()`: cho biết có khớp hay không.
- `MatchResult.getVariables()`: lấy biến được trích từ pattern nếu matcher cung cấp (ví dụ `id` trong `/api/items/{id}`). Không phải matcher nào cũng có biến.

Có hai factory thường dùng trong custom matcher:

```java
return ServerWebExchangeMatcher.MatchResult.match();    // Mono<MatchResult>, có khớp
// hoặc
return ServerWebExchangeMatcher.MatchResult.notMatch(); // Mono<MatchResult>, không khớp
```

Không nhầm `ServerWebExchangeMatcher` với `org.springframework.security.web.util.matcher.RequestMatcher` của Servlet. Cả hai cùng nói về matching HTTP request nhưng khác stack, kiểu request và cách trả kết quả.

### Vai trò trong pipeline

```text
                    HTTP request
                         |
                         v
          Chọn SecurityWebFilterChain
          (securityMatcher + @Order)
                         |
                         v
          WebFilter xử lý authentication
                         |
                         v
         authorizeExchange / matcher rules
          (path + method + thứ tự)
                         |
                         v
           permitAll / denyAll / role
                         |
                         v
             Controller / Handler
```

Sơ đồ mô tả **các quyết định chính**, không cam kết mọi WebFilter nội bộ chạy đúng thứ tự minh họa trong mọi cấu hình. Việc match route trong WebFlux controller cũng là một giai đoạn riêng: một request có thể vượt qua security nhưng vẫn nhận 404 hoặc 405 vì không có handler tương ứng.

## 3. Khớp đường dẫn với `ServerWebExchangeMatchers`

Class `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers` có các factory phổ biến:

```java
ServerWebExchangeMatcher any =
        ServerWebExchangeMatchers.anyExchange();

ServerWebExchangeMatcher exact =
        ServerWebExchangeMatchers.pathMatchers("/api/items");

ServerWebExchangeMatcher subtree =
        ServerWebExchangeMatchers.pathMatchers("/api/**");

ServerWebExchangeMatcher either =
        ServerWebExchangeMatchers.pathMatchers(
                "/health", "/public/**");
```

Những đoạn code trên có thể đặt trong một method/class Java đã import `ServerWebExchangeMatcher` và `ServerWebExchangeMatchers`. Factory nhận nhiều pattern như `pathMatchers("/health", "/public/**")` khớp **nếu một trong các pattern khớp**.

Với đường dẫn sử dụng Spring `PathPattern`:

| Pattern | Ví dụ khớp | Ghi chú |
| --- | --- | --- |
| `/api/items` | `/api/items` | Một đường dẫn cụ thể |
| `/api/items/{id}` | `/api/items/42` | Một path segment được gán biến `id` |
| `/api/items/*` | `/api/items/42` | `*` khớp phần trong một segment |
| `/api/items/**` | `/api/items/42/details` | `**` khớp phần đường dẫn còn lại; dùng ở cuối pattern |
| `/public/**` | `/public/docs/readme` | Một nhánh đường dẫn |
| `/**` | Rất nhiều đường dẫn | Quá rộng nếu đứng trước luật cụ thể |

`PathPattern` xử lý đường dẫn theo segment, không giống việc tùy ý tìm chuỗi con trong URL. Query string như `?page=2` **không làm thay đổi** kết quả khớp đường dẫn khi pattern chỉ quan tâm path. Hành vi liên quan slash cuối, case sensitivity, encoded path và context path nên được kiểm chứng theo cấu hình Spring Framework thực tế, thay vì suy đoán từ cách nhìn URL.

Với nhu cầu chỉ khớp path, `ServerWebExchangeMatchers.pathMatchers(...)` là lựa chọn ngắn gọn. Khi muốn biểu đạt rõ một pattern và có thể thêm điều kiện method bằng constructor, có thể dùng `PathPatternParserServerWebExchangeMatcher`:

```java
ServerWebExchangeMatcher oneItem =
        new PathPatternParserServerWebExchangeMatcher(
                "/api/items/{id}");
```

Import: `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher`.

## 4. Khớp cả HTTP method và đường dẫn

Một URL có thể cùng lúc hỗ trợ những hành động khác nhau:

- `GET /api/items`: đọc danh sách.
- `POST /api/items`: tạo item.
- `DELETE /api/items/42`: xóa item.

Quy tắc bảo mật theo mỗi method **khác nhau dù URL giống nhau**. Factory hỗ trợ overload sau:

```java
ServerWebExchangeMatcher canRead =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/api/items/**");

ServerWebExchangeMatcher canCreate =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.POST, "/api/items");

ServerWebExchangeMatcher canDelete =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.DELETE, "/api/items/{id}");
```

Import `org.springframework.http.HttpMethod`.

Điều kiện của `pathMatchers(HttpMethod.GET, "/api/items/**")` là **cùng lúc**:
1. Phương thức request là `GET`.
2. Path khớp `/api/items/**`.

Nếu path đúng nhưng method là `POST`, kết quả `isMatch()` là false. Nếu method là GET nhưng path nằm ngoài pattern, kết quả cũng false. Overload `pathMatchers(String... patterns)` không giới hạn HTTP method; tương tự, overload có `HttpMethod` nhận `null` nghĩa là không ràng buộc method theo hợp đồng API, nhưng nên gọi overload không có method khi muốn rõ ý.

Ví dụ constructor tương đương về mục đích:

```java
ServerWebExchangeMatcher getOneItem =
        new PathPatternParserServerWebExchangeMatcher(
                "/api/items/{id}", HttpMethod.GET);
```

**Không nhầm matcher với handler**: matcher cho biết URL/method có thuộc một quy tắc security, còn `@GetMapping`/`@PostMapping` quyết định controller nào xử lý request sau đó.

### GET, HEAD và OPTIONS

`GET`, `HEAD` và `OPTIONS` là các HTTP method khác nhau. Một quy tắc chỉ dùng `HttpMethod.GET` không tự động có nghĩa là mọi request `HEAD` hay `OPTIONS` cũng được quyền đó. WebFlux handler có thể hỗ trợ HEAD liên quan GET theo quy tắc framework, nhưng security matcher vẫn cần được xem xét riêng. CORS preflight thường dùng `OPTIONS`; nếu API phục vụ trình duyệt khác origin, phải xét cấu hình CORS và quy tắc security phù hợp, không mở toàn bộ API chỉ để chữa lỗi preflight.

## 5. Hai vị trí sử dụng matcher: chọn chain và phân quyền trong chain

Đây là khác biệt quan trọng nhất.

### 5.1. `http.securityMatcher(matcher)`: chọn **toàn bộ chain**

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **đoạn trích cấu hình**, cần các import và bean authentication đầy đủ ở ví dụ chạy được bên dưới. Chỉ những request khớp `/api/**` mới chọn chain này. Các request khác sẽ được Spring Security thử ở chain tiếp theo theo thứ tự, nếu tồn tại.

`@Order` quyết định thứ tự xét nhiều `SecurityWebFilterChain`. Spring Security chọn chain đầu tiên match request; các chain còn lại không cùng áp dụng theo kiểu cộng dồn cho request ấy. Nếu tất cả chain đều không match, request có thể **không được bảo vệ bởi các chain này**: cần kiểm tra phạm vi/fallback rất cẩn thận.

### 5.2. `http.authorizeExchange(...).pathMatchers(...)`: chọn **luật trong chain đã chọn**

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/items").permitAll()
    .pathMatchers(HttpMethod.POST, "/api/items").hasRole("EDITOR")
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

Tại đây, Spring Security xét các authorization rule **theo thứ tự khai báo** và áp dụng **quy tắc khớp đầu tiên** trong chain được chọn. Đưa quy tắc cụ thể trước, `anyExchange()` cuối.

Cũng có thể truyền một `ServerWebExchangeMatcher` tự dựng bằng `matchers(...)`:

```java
ServerWebExchangeMatcher getOrder =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/api/orders/{id}");

// Bên trong cấu hình ServerHttpSecurity:
http.authorizeExchange(exchanges -> exchanges
    .matchers(getOrder).hasRole("READER")
    .anyExchange().denyAll());
```

Đây là **đoạn minh họa trong method cấu hình**; `http` phải là đối tượng `ServerHttpSecurity`. Dùng `matchers(...)` khi đã có matcher tái sử dụng hoặc matcher phức tạp. Dùng `pathMatchers(...)` khi chỉ cần path/method đơn giản.

### 5.3. Bảng phân biệt

| Câu hỏi | `securityMatcher(...)` | `authorizeExchange(...).pathMatchers(...)` |
| --- | --- | --- |
| Đặt ở đâu? | Trực tiếp trên `ServerHttpSecurity` | Trong khối `authorizeExchange` |
| Chọn cái gì? | `SecurityWebFilterChain` áp dụng | Authorization rule của chain đang áp dụng |
| Khi nào xét thứ tự? | Giữa các chain, qua `@Order` | Giữa các rule, theo thứ tự khai báo |
| Nếu không khớp? | Thử chain kế tiếp | Thử rule kế tiếp |
| Nếu không có fallback? | Có nguy cơ request nằm ngoài các chain | Có nguy cơ cấu hình không bao phủ yêu cầu mong muốn |
| Khuyến nghị | Chain hẹp trước, chain bao phủ cuối | Rule cụ thể trước, `anyExchange().denyAll()` cuối |

**Lưu ý:** `permitAll()` nghĩa là không yêu cầu authorization cho rule đó, không đồng nghĩa với việc loại toàn bộ security filters khỏi request. Những concern khác như CSRF, headers, authentication có thể vẫn hoạt động theo cấu hình chain.

## 6. Dự án Java 17+ / Spring Boot 3.3 có thể chạy

Ví dụ này trình bày đầy đủ **hai filter chain**, match path+method, tài khoản mẫu và test. Chọn Spring Boot `3.3.5`, Java 17+, Gradle `8.5` (hoặc Gradle Wrapper tương thích) để có bộ dependency nhất quán. Spring Boot quản lý Spring Security qua BOM.

Cây dự án:

```text
reactive-matcher-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/matcher/
    │   ├── ReactiveMatcherApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/dev/example/matcher/
        ├── SecurityMatcherTests.java
        └── MatcherUnitTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-matcher-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chỉ dùng `spring-boot-starter-webflux` cho web runtime ở ví dụ này. Nếu thêm `spring-boot-starter-web`, Boot có thể tự chọn Servlet stack làm bạn hiểu sai tác dụng của `ServerWebExchangeMatcher`.

`src/main/java/dev/example/matcher/ReactiveMatcherApplication.java`:

```java
package dev.example.matcher;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveMatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveMatcherApplication.class, args);
    }
}
```

### 6.1. Cấu hình Security với hai chain

`src/main/java/dev/example/matcher/SecurityConfig.java`:

```java
package dev.example.matcher;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("READER", "EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("READER", "EDITOR", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, editor, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                    ServerWebExchangeMatchers.pathMatchers("/api/**"))
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.GET, "/api/items")
                        .permitAll()
                    .pathMatchers(HttpMethod.GET, "/api/items/{id}")
                        .hasRole("READER")
                    .pathMatchers(HttpMethod.POST, "/api/items")
                        .hasRole("EDITOR")
                    .pathMatchers(HttpMethod.DELETE, "/api/items/{id}")
                        .hasRole("ADMIN")
                    .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.GET, "/health").permitAll()
                    .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Giải thích:
- `@Order(1)`: chain `apiChain` được xét đầu tiên, chỉ dành cho `/api/**`.
- `@Order(2)`: `fallbackChain` không khai báo `securityMatcher` nên mặc định match mọi exchange còn lại; tránh để request ngoài phạm vi không được xét bởi bất kỳ chain nào.
- `GET /api/items` công khai; `GET /api/items/{id}` yêu cầu `ROLE_READER`; `POST /api/items` yêu cầu `ROLE_EDITOR`; `DELETE /api/items/{id}` yêu cầu `ROLE_ADMIN`.
- `anyExchange().denyAll()` trong từng chain chặn các request chưa có rule cho phép, kể cả method khác cho path quen thuộc.
- `GET /health` được fallback chain cho phép, không làm cho toàn bộ ứng dụng thành public.
- `MapReactiveUserDetailsService` cung cấp tài khoản ở RAM; `PasswordEncoder` lưu hash BCrypt. Vai trò từ `.roles("EDITOR")` được lưu thành authority `ROLE_EDITOR`.
- `httpBasic(...)` bật HTTP Basic để thử credential. Form login bị tắt để ví dụ API dễ quan sát 401/403.
- **CSRF vẫn được bật theo mặc định**. Ta cố ý giữ nguyên để bài kiểm thử phân biệt rõ lỗi role với lỗi thiếu CSRF token.

Các mật khẩu `reader-pass`, `editor-pass` và `admin-pass` được hard-code để làm **tài khoản thử nghiệm**, không dành cho triển khai công khai.

### 6.2. Controller chỉ mô phỏng xử lý

`src/main/java/dev/example/matcher/ApiController.java`:

```java
package dev.example.matcher;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("healthy");
    }

    @GetMapping("/api/items")
    public Mono<String> listItems() {
        return Mono.just("items");
    }

    @GetMapping("/api/items/{id}")
    public Mono<String> getItem(@PathVariable String id) {
        return Mono.just("item:" + id);
    }

    @PostMapping("/api/items")
    public Mono<String> createItem() {
        return Mono.just("created");
    }

    @DeleteMapping("/api/items/{id}")
    public Mono<String> deleteItem(@PathVariable String id) {
        return Mono.just("deleted:" + id);
    }
}
```

Các handler trả `Mono` và **không gọi `block()` hoặc `subscribe()`**. Ví dụ không thực sự sửa database; mục tiêu là kiểm chứng selection của matcher và kết quả authorization.

### 6.3. Bảng request và quy tắc được chọn

| Request | Chain | Authorization rule | Kết quả khi đủ điều kiện |
| --- | --- | --- | --- |
| `GET /health` | Fallback | `GET /health -> permitAll` | 200, `healthy` |
| `GET /api/items` | API | `GET /api/items -> permitAll` | 200, `items` |
| `GET /api/items/42` | API | `GET /api/items/{id} -> READER` | 200, `item:42` |
| `POST /api/items` | API | `POST /api/items -> EDITOR` | 200, `created` với CSRF hợp lệ |
| `DELETE /api/items/42` | API | `DELETE /api/items/{id} -> ADMIN` | 200, `deleted:42` với CSRF hợp lệ |
| `PUT /api/items/42` | API | `anyExchange -> denyAll` | Bị từ chối dù có quyền khác |
| `GET /other` | Fallback | `anyExchange -> denyAll` | Bị từ chối |

Bảng mô tả cấu hình khi handler tồn tại. Request không có handler có thể nhận 404/405 sau kiểm tra security; CSRF, authentication, method hoặc security entry point cũng ảnh hưởng status thực tế. Vì thế không suy luận toàn bộ HTTP status chỉ từ matcher.

## 7. Chạy ứng dụng và kiểm tra GET bằng curl

Từ thư mục `reactive-matcher-demo`:

```bash
gradle bootRun
```

Nếu dùng Gradle Wrapper thì chạy `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Sau khi server sẵn sàng ở port 8080, mở terminal thứ hai:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/items
curl -i http://localhost:8080/api/items/42
curl -i -u reader:reader-pass http://localhost:8080/api/items/42
curl -i -u reader:wrong http://localhost:8080/api/items/42
curl -i -u editor:editor-pass http://localhost:8080/api/items/42
```

Kết quả **dự kiến**:
1. `/health`: HTTP 200, body `healthy` (fallback chain).
2. `/api/items`: HTTP 200, body `items` (public API GET).
3. `/api/items/42` không có credential: HTTP 401 với HTTP Basic.
4. Cùng URL với `reader` đúng password: HTTP 200, body `item:42`.
5. Cùng URL với password sai: HTTP 401.
6. Cùng URL với `editor`: HTTP 200 vì editor cũng có role READER.

**Không dùng lệnh curl POST đơn giản để kết luận quyền EDITOR:** khi CSRF đang bật, `curl -u editor:editor-pass -X POST http://localhost:8080/api/items` thường nhận 403 do thiếu CSRF token. Đây không chứng minh rule `hasRole("EDITOR")` sai. Phần tiếp theo kiểm tra POST/DELETE bằng WebTestClient có CSRF hợp lệ.

## 8. Kiểm thử integration với `WebTestClient` và CSRF

`src/test/java/dev/example/matcher/SecurityMatcherTests.java`:

```java
package dev.example.matcher;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class SecurityMatcherTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void healthIsPublicThroughFallbackChain() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("healthy");
    }

    @Test
    void collectionGetIsPublic() {
        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("items");
    }

    @Test
    void itemGetNeedsAuthentication() {
        client.get().uri("/api/items/42")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanGetItem() {
        client.get().uri("/api/items/42")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("item:42");
    }

    @Test
    void readerCannotCreateEvenWithCsrf() {
        client.mutateWith(csrf())
                .post().uri("/api/items")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorCanCreateWithCsrf() {
        client.mutateWith(csrf())
                .post().uri("/api/items")
                .headers(h -> h.setBasicAuth("editor", "editor-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void editorCannotCreateWithoutCsrf() {
        client.post().uri("/api/items")
                .headers(h -> h.setBasicAuth("editor", "editor-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorCannotDeleteEvenWithCsrf() {
        client.mutateWith(csrf())
                .delete().uri("/api/items/42")
                .headers(h -> h.setBasicAuth("editor", "editor-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanDeleteWithCsrf() {
        client.mutateWith(csrf())
                .delete().uri("/api/items/42")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("deleted:42");
    }

    @Test
    void unlistedApiPathIsDenied() {
        client.get().uri("/api/unknown")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Tại `setup()`, `springSecurity()` áp dụng Spring Security test support lên client gắn với Spring `ApplicationContext`. `csrf()` cung cấp CSRF token hợp lệ cho request giả lập POST/DELETE; nó **không tắt** CSRF trong ứng dụng. `@SpringBootTest(...MOCK)` kiểm tra WebFlux bằng mock HTTP exchange, không cần khởi động server thật ở cổng 8080.

Chạy:

```bash
gradle test
```

Dự kiến: **10 test thành công** với cấu hình và dependency tương thích. Đây là dự kiến từ mã bài học, không phải tuyên bố đã chạy test trong hệ thống của bạn.

Phân tích ba kết quả dễ nhầm:
- Reader + CSRF hợp lệ nhưng POST bị **403**: sai *authorization role* (`READER` không có `EDITOR`).
- Editor + CSRF hợp lệ và POST **200**: vừa qua CSRF, vừa đủ `ROLE_EDITOR`.
- Editor + không CSRF và POST **403**: bị CSRF chặn, dù đã đủ role.

Đối với production, CSRF phải đánh giá theo cách ứng dụng xác thực và cách browser tự gửi thông tin đăng nhập. Không nên tắt CSRF đơn thuần để POST trả 200; nếu API thật sự dùng bearer token trong header và có mô hình threat riêng, hãy đánh giá cấu hình CSRF/CORS cùng kiến trúc xác thực.

## 9. Kiểm thử matcher độc lập: đúng path nhưng sai method

Matcher có thể được kiểm tra trực tiếp mà không cần chạy controller. Đây là chỗ phù hợp để sử dụng `block()` trong **JUnit test trên thread kiểm thử**, không phải trong WebFlux request handler.

`src/test/java/dev/example/matcher/MatcherUnitTests.java`:

```java
package dev.example.matcher;

import java.util.Objects;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MatcherUnitTests {

    private final ServerWebExchangeMatcher matcher =
            ServerWebExchangeMatchers.pathMatchers(
                    HttpMethod.GET, "/api/items/{id}");

    @Test
    void getMatchingPathSucceedsAndExtractsVariable() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/items/42"));

        ServerWebExchangeMatcher.MatchResult result =
                Objects.requireNonNull(matcher.matches(exchange).block());

        assertTrue(result.isMatch());
        assertEquals("42", result.getVariables().get("id"));
    }

    @Test
    void postSamePathDoesNotMatch() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.post("/api/items/42"));

        ServerWebExchangeMatcher.MatchResult result =
                Objects.requireNonNull(matcher.matches(exchange).block());

        assertFalse(result.isMatch());
    }

    @Test
    void getWrongPathDoesNotMatch() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/other/42"));

        ServerWebExchangeMatcher.MatchResult result =
                Objects.requireNonNull(matcher.matches(exchange).block());

        assertFalse(result.isMatch());
    }
}
```

Dự kiến **3 test thành công**: một request khớp và trích biến `id=42`, hai request không khớp do sai method hoặc path. Khi chạy toàn bộ bằng `gradle test` cùng file ở phần 8, dự kiến **13 test thành công**.

Nếu custom matcher không cung cấp path variables, `getVariables()` có thể rỗng; ở ví dụ này factory tạo path matcher hỗ trợ biến từ `{id}`.

## 10. Kết hợp nhiều matcher và viết custom matcher

Khi có nhiều điều kiện, cần xác định rõ quan hệ **OR** và **AND**:

```java
ServerWebExchangeMatcher healthOrDocs =
        ServerWebExchangeMatchers.matchers(
                ServerWebExchangeMatchers.pathMatchers("/health"),
                ServerWebExchangeMatchers.pathMatchers("/docs/**"));
```

Factory `matchers(...)` tạo matcher **khớp nếu bất kỳ matcher đầu vào nào khớp** (OR). Đừng nhầm nó là phép AND. Đối với cả path và method, overload `pathMatchers(HttpMethod.GET, "/docs/**")` đã cung cấp logic AND giữa hai điều kiện đó.

Spring Security cũng có `AndServerWebExchangeMatcher`, `OrServerWebExchangeMatcher` và `NegatedServerWebExchangeMatcher` để biểu đạt các điều kiện kết hợp khi cần. Chỉ nên thêm độ phức tạp này khi rule không còn đọc rõ bằng `pathMatchers(...)`.

### Custom matcher cho điều kiện không phải path

Ví dụ minh họa một matcher **chỉ nhận biết header** mà không tự cấp quyền:

```java
ServerWebExchangeMatcher version2 = exchange -> {
    String version = exchange.getRequest()
            .getHeaders().getFirst("X-API-Version");
    return "2".equals(version)
            ? ServerWebExchangeMatcher.MatchResult.match()
            : ServerWebExchangeMatcher.MatchResult.notMatch();
};
```

Đặt trong class/method đã import `ServerWebExchangeMatcher`. Kết quả là `Mono<MatchResult>`, không block thread. Đây là điều kiện để **phân loại request**; header do client gửi có thể sửa được, nên **không** lấy giá trị này làm bằng chứng danh tính/quyền hạn. Muốn cấp quyền, vẫn phải xác thực danh tính và kiểm tra authority/role phù hợp.

Đối với query parameter `?mode=preview`, path matcher thông thường không phân biệt nó. Nếu thật sự phải match query, có thể viết matcher riêng đọc `exchange.getRequest().getQueryParams()` và trả `MatchResult`. Tương tự, không dùng query string do client kiểm soát để thay thế authentication.

## 11. Thứ tự, fallback và các lỗ hổng hay gặp

### 11.1. Rule quá rộng đứng trước rule hẹp

```java
// SAI về ý định: rule đầu bắt mọi request trong /api,
// khiến rule /api/admin/** phía sau không được xét.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

Với request `GET /api/admin/report`, rule đầu đã cho phép; Spring Security không cộng dồn điều kiện `hasRole("ADMIN")` ở rule sau.

Sửa:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/public/**").permitAll()
    .anyExchange().denyAll())
```

### 11.2. Chain quá rộng đứng trước chain chuyên biệt

Nếu một chain `@Order(1)` match mọi URL, chain `@Order(2)` chỉ dành cho `/api/**` có thể **không được chọn**. Hãy gắn `securityMatcher("/api/**")` cho chain chuyên biệt và đặt nó trước fallback. Với nhiều chain, xét logic theo thứ tự **chain selection → authorization inside chosen chain**.

### 11.3. Chỉ khai báo chain cho `/api/**`, quên URL khác

Lúc này `/health`, `/admin` hoặc một endpoint mới có thể nằm ngoài các chain đã cấu hình. Tạo fallback match mọi request và áp dụng rule tường minh, thường `denyAll` cho URL chưa được thiết kế cho phép.

### 11.4. Chỉ xét path, quên method

`.pathMatchers("/api/items").permitAll()` mở cùng path cho **mọi method** trong phạm vi rule, kể cả `POST` nếu không có điều kiện khác khớp trước. Khi chính sách phân biệt đọc/ghi, phải ghi rõ `HttpMethod.GET`, `HttpMethod.POST`, `HttpMethod.DELETE` v.v.

### 11.5. Gặp 403 và kết luận matcher sai

403 còn có thể do:
- Đã đăng nhập nhưng thiếu role/authority.
- `anyExchange().denyAll()` được chọn.
- CSRF token thiếu/sai cho request thay đổi trạng thái.
- Cấu hình CORS, security exception handler hoặc logic authorization tùy chỉnh.

Xác minh request method, path, chain được chọn, rule đầu tiên match, authentication, CSRF và handler, theo đúng thứ tự. Test mỗi điều kiện độc lập để tìm đúng nguyên nhân.

### 11.6. Gặp 404/405 và tự sửa rule security

404/405 có thể xuất phát từ **handler mapping**, chẳng hạn `POST /api/items/42` không có `@PostMapping` tương ứng. Authorization không tạo controller. Nếu security từ chối trước, bạn cũng có thể thấy 401/403 thay vì 404/405. Test cả logic security lẫn route thực tế.

### 11.7. Nhầm WebFlux với Servlet

Cặp thành phần đúng:

| Reactive/WebFlux | Servlet/MVC |
| --- | --- |
| `ServerWebExchangeMatcher` | `RequestMatcher` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ServerHttpSecurity` | `HttpSecurity` |
| `authorizeExchange` | `authorizeHttpRequests` |
| `ServerWebExchange` | `HttpServletRequest` |

Đừng dùng ví dụ `AntPathRequestMatcher`/`MvcRequestMatcher` của Servlet để thay thế trực tiếp `ServerWebExchangeMatcher` trong WebFlux.

## 12. Checklist tự rà soát khi thiết kế quy tắc HTTP

1. Liệt kê toàn bộ endpoint, **cả path và method**: đọc/ghi/xóa/admin/health.
2. Chọn số lượng chain thật sự cần thiết. Một chain có nhiều authorization rule là đủ cho nhiều ứng dụng nhỏ; tách chain khi khác hẳn cơ chế xác thực hoặc phạm vi.
3. Với nhiều chain: đặt chain chuyên biệt trước, fallback cuối. Xem kết quả khi không chain nào match.
4. Trong từng chain: rule cụ thể trước, `anyExchange()` cuối. Chọn `denyAll()` cho các request không được khai báo nếu yêu cầu là allowlist.
5. Phân biệt `permitAll` với việc bỏ qua toàn bộ security filters.
6. Kiểm tra quyền bằng `hasRole`/`hasAuthority` trên danh tính đã được xác thực; không sử dụng path/query/header do client tự điền như bằng chứng quyền.
7. Kiểm thử status **200/401/403**, route tồn tại/không tồn tại, method sai, CSRF và CORS preflight khi có.
8. Không quên `HEAD`, `OPTIONS`, đường dẫn có biến, context path và slash cuối.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `ServerWebExchangeMatcher.matches(...)` trả kiểu gì?  
**Đáp án:** `Mono<ServerWebExchangeMatcher.MatchResult>`, không phải boolean.

**Câu 2.** Hai request `GET /api/items` và `POST /api/items` có cùng một rule nếu dùng `pathMatchers("/api/items")` không?  
**Đáp án:** Có thể cùng match vì overload này không giới hạn method. Muốn tách quyền, dùng `pathMatchers(HttpMethod.GET, ...)` và `pathMatchers(HttpMethod.POST, ...)`.

**Câu 3.** `securityMatcher(...)` khác gì `authorizeExchange().pathMatchers(...)`?  
**Đáp án:** Cái đầu chọn **filter chain** cho request; cái sau chọn **rule authorization** trong chain đã chọn.

**Câu 4.** Hai rule cùng match một request thì rule nào áp dụng?  
**Đáp án:** Rule đầu tiên theo thứ tự cấu hình trong chain, không cộng dồn mọi rule.

**Câu 5.** Hai chain cùng match một request thì chain nào được dùng?  
**Đáp án:** Chain đầu tiên khớp theo thứ tự `@Order`.

**Câu 6.** Vì sao `POST` với đúng role EDITOR vẫn nhận 403?  
**Đáp án:** Có thể thiếu CSRF token. Cần phân biệt CSRF với authorization.

**Câu 7.** Query `GET /api/items/42?view=full` có khiến pattern path `/api/items/{id}` tự động không match không?  
**Đáp án:** Không; query không thuộc phần path được so bởi path matcher thông thường.

**Câu 8.** `ServerWebExchangeMatchers.matchers(a, b)` mang nghĩa AND hay OR?  
**Đáp án:** OR, match nếu một trong các matcher khớp.

### Bài tập đề xuất

1. Tạo `GET /api/reports/{id}` chỉ cho role READER và `POST /api/reports` chỉ cho role EDITOR. Giữ `/api/reports/public` là trường hợp được đọc công khai nếu đó là yêu cầu sản phẩm.
2. Viết rule theo thứ tự tránh mở nhầm `/api/reports/{id}`. Hãy tự lý giải điều gì xảy ra với `GET /api/reports/public` khi một matcher public được đặt trước hoặc sau matcher `/api/reports/{id}`.
3. Thêm test cho `GET`/`POST`, đăng nhập thành công, thiếu role và thiếu CSRF. Đừng bỏ test `OPTIONS` nếu ứng dụng phục vụ browser đa origin.
4. Đưa `.pathMatchers("/api/**").permitAll()` lên đầu; chạy lại test và xác định yêu cầu bảo mật nào bị phá vỡ. Sau đó hoàn nguyên theo chính sách đúng.
5. Thử một custom `ServerWebExchangeMatcher` nhận `X-API-Version: 2` chỉ để **phân luồng** một rule, rồi giữ bước kiểm tra role riêng. Giải thích vì sao header client không đủ làm bằng chứng authorization.

## 14. Tài liệu chính thức

- [Spring Security — WebFlux Security, multiple chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — ServerWebExchangeMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatcher.html).
- [Spring Security — ServerWebExchangeMatchers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html).
- [Spring Security — PathPatternParserServerWebExchangeMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html).
- [Spring Security — Testing with CSRF in WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html).
- [Spring Framework — PathPattern](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html).

**Ghi nhớ:** `ServerWebExchangeMatcher` quyết định *request có khớp điều kiện không*; `securityMatcher` chọn *chain*; `authorizeExchange` chọn *rule*; path **và** method phải được diễn đạt đủ, rồi kiểm thử thứ tự, CSRF và fallback để tránh mở nhầm endpoint.