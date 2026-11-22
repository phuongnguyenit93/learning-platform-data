# Cấu hình bằng lambda DSL và Customizer trong ServerHttpSecurity

> **Ngữ cảnh:** Spring Boot 3.3.x, Spring WebFlux, Spring Security 6.x và Java 17+. Bài này hướng dẫn cách khai báo chính sách bảo mật HTTP của **ứng dụng reactive** bằng `ServerHttpSecurity`, lambda DSL và `Customizer`; nhận biết khi nào giữ giá trị mặc định, khi nào tùy chỉnh, và cách kiểm chứng cấu hình thực sự có hiệu lực.

## 1. Đọc đúng ba thành phần của cấu hình

Trong ứng dụng WebFlux, `ServerHttpSecurity` là **builder** để định nghĩa chính sách bảo mật cho các `ServerWebExchange`. Sau khi cấu hình, gọi `build()` để tạo `SecurityWebFilterChain`. Spring Security sử dụng chain này để xử lý request trước khi vào controller.

```text
Client HTTP request
    |
    v
ServerWebExchange (Spring WebFlux)
    |
    v
SecurityWebFilterChain
    |-- Kiểm tra CSRF/CORS/header theo cấu hình
    |-- Xác thực (ví dụ: HTTP Basic, form login, bearer token)
    |-- Phân quyền (authorizeExchange)
    v
@RestController -> Mono/Flux -> HTTP response
```

Ba tên rất dễ nhầm:

| Thành phần | Vai trò |
|---|---|
| `ServerHttpSecurity` | Builder cấu hình chính sách bảo mật HTTP **reactive** |
| `Customizer<T>` | Giao diện hàm nhận một đối tượng cấu hình kiểu `T` để thay đổi nó |
| `SecurityWebFilterChain` | Kết quả sau `http.build()`, được Spring Security áp dụng lên request |

Trong **Servlet/MVC** thường gặp `HttpSecurity` và `SecurityFilterChain`; ở **WebFlux** dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Đừng trộn kiểu của hai stack.

Cấu trúc tối thiểu:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Đây là **đoạn method đặt trong một lớp `@Configuration`**, chưa phải chương trình Java độc lập. Lambda ở `authorizeExchange` định nghĩa ai được truy cập request nào; `Customizer.withDefaults()` ở `httpBasic` và `formLogin` bật cách xác thực tương ứng với cấu hình mặc định của Spring Security. `build()` tạo chain.

## 2. Lambda DSL làm gì khác cú pháp chain cũ?

**Lambda DSL** truyền hàm vào mỗi phương thức cấu hình:

```java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public").permitAll()
        .anyExchange().authenticated())
    .httpBasic(Customizer.withDefaults());
```

Ở đây:

1. `authorizeExchange(...)` nhận một `Customizer<ServerHttpSecurity.AuthorizeExchangeSpec>`.
2. Biến `exchanges` đại diện cho phần cấu hình phân quyền. Phương thức `pathMatchers(...)` và `anyExchange()` dùng để đăng ký các điều kiện theo thứ tự.
3. Sau dấu `)` kết thúc lambda, bạn trở về builder `http` nên có thể tiếp tục gọi `httpBasic(...)`; **không cần `.and()`**.
4. Cuối cùng gọi `http.build()` một lần để tạo chain.

Cách viết cũ dựa nhiều vào các phương thức không có lambda và `.and()` đã trở thành lối viết cần tránh khi chuyển sang Spring Security mới. Lambda DSL giúp nhìn rõ ranh giới giữa cấu hình `authorizeExchange`, `httpBasic`, `formLogin`, `csrf` hoặc `headers`. Trong Spring Security 7, cấu hình lambda là hướng sử dụng cần thiết; bài ví dụ này dùng API của Spring Security 6.x.

**Điều lambda không tự làm:** nó không biến route thành public, không cấp role, không tạo user, không xác thực JWT và không tự vô hiệu hóa CSRF. Mọi tác động bảo mật đến từ các phương thức bên trong nó.

## 3. `Customizer<T>`, lambda và `Customizer.withDefaults()`

`Customizer<T>` là functional interface với ý tưởng:

```java
@FunctionalInterface
interface Customizer<T> {
    void customize(T target);
}
```

Đây là **minh họa khái niệm**, không phải mã thay thế `org.springframework.security.config.Customizer`. Spring Security cung cấp interface thật; khi triển khai, import:

```java
import org.springframework.security.config.Customizer;
```

Ba cách gọi cần phân biệt:

| Cách viết | Ý nghĩa |
|---|---|
| `.httpBasic(Customizer.withDefaults())` | Sử dụng HTTP Basic với lựa chọn mặc định của Spring Security |
| `.httpBasic(basic -> {})` | Lambda rỗng: tương đương ý nghĩa bật HTTP Basic bằng defaults |
| `.httpBasic(basic -> basic.authenticationManager(manager))` | Tùy chỉnh HTTP Basic bằng authentication manager do ứng dụng cung cấp; `manager` phải là `ReactiveAuthenticationManager` hợp lệ |

**`withDefaults()` không có nghĩa “mở quyền cho tất cả”**, cũng không phải “xóa hết mọi cấu hình trước đó”. Nó là một `Customizer` không thực hiện thêm chỉnh sửa đối với spec được truyền vào; phương thức nhận nó vẫn kích hoạt cơ chế tương ứng theo mặc định. Một `Customizer` tùy chỉnh là lambda có những lệnh cụ thể.

Tương đương về cú pháp khi **không cần option bổ sung**:

```java
// Hai cách dùng trong hai cấu hình thay thế nhau:
http.httpBasic(Customizer.withDefaults());

// Cách tương đương:
http.httpBasic(basic -> { });
```

Ví dụ customizer có thay đổi thật:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/health").permitAll()
    .anyExchange().authenticated());
```

Nếu bạn chỉ muốn bật cấu hình mặc định của cơ chế HTTP Basic, hãy chọn `withDefaults()` để người đọc biết không có tùy chỉnh ẩn. Nếu cần thay đổi một giá trị, sử dụng lambda có nội dung; đừng gọi thêm option không hiểu chỉ vì IDE gợi ý.

### `Customizer` có thể tách ra thành hàm tái sử dụng

Không bắt buộc phải dồn toàn bộ lambda vào method `@Bean`. Một cách viết rõ ràng, không phụ thuộc vào tự động phát hiện customizer bean, là khai báo **hàm trả về `Customizer` và truyền tường minh**:

```java
private static Customizer<ServerHttpSecurity.AuthorizeExchangeSpec> rules() {
    return exchanges -> exchanges
        .pathMatchers("/health").permitAll()
        .anyExchange().authenticated();
}

@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(rules())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đoạn này là **một phần cấu hình minh họa**, phải đặt trong lớp có imports và `@Configuration`; nó **thay thế** cấu hình `@Bean` tương ứng, không thêm cùng lúc với ví dụ hoàn chỉnh bên dưới. Lợi ích: nhóm quy tắc thành một customizer có tên, vẫn giữ nguyên thứ tự gọi và phạm vi của policy.

**Cẩn thận khi dùng các bean `Customizer` tự động:** cơ chế áp dụng và thứ tự các customizer cấp cao có thể phụ thuộc phiên bản Spring Security; đừng tạo nhiều bean có tác dụng lên cùng matcher rồi giả định thứ tự bất biến. Với ứng dụng nhỏ, cách truyền customizer tường minh vào đúng chain dễ đánh giá hơn.

## 4. Các phần của `ServerHttpSecurity` thường cấu hình bằng lambda

| API | Mục đích | Ví dụ |
|---|---|---|
| `authorizeExchange` | Cho phép/chặn/phân quyền từng request | `.authorizeExchange(ex -> ex.anyExchange().authenticated())` |
| `httpBasic` | Xác thực username/password qua HTTP Basic | `.httpBasic(Customizer.withDefaults())` |
| `formLogin` | Form login và cơ chế đăng nhập bằng form | `.formLogin(Customizer.withDefaults())` |
| `csrf` | Bảo vệ CSRF cho request phù hợp | `.csrf(Customizer.withDefaults())` |
| `cors` | Tích hợp xử lý CORS với nguồn chính sách CORS | `.cors(Customizer.withDefaults())` |
| `headers` | Cấu hình các response header bảo mật | `.headers(Customizer.withDefaults())` |
| `exceptionHandling` | Điều chỉnh cách ứng dụng đáp ứng lỗi authentication/access denied | `.exceptionHandling(handler -> { /* cấu hình khi cần */ })` |
| `oauth2ResourceServer` | Kiểm tra bearer access token với cấu hình resource server | `.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` |
| `securityMatcher` | Quy định **toàn bộ chain** áp dụng cho request nào | `.securityMatcher(matcher)` |
| `build` | Chốt builder thành `SecurityWebFilterChain` | `.build()` |

Chỉ bật những tính năng phù hợp. Ví dụ cấu hình JWT ở trên **đòi hỏi dependency và issuer/JWK/introspection tương ứng**; riêng một dòng `jwt(withDefaults())` không làm token tự hợp lệ. `cors(withDefaults())` cũng không có nghĩa mọi origin được phép; phải cung cấp chính sách CORS phù hợp.

Mỗi phương thức có default riêng. **Cấu hình mặc định của Spring Boot khi không có custom chain** và **những tính năng bạn gọi tường minh trên custom chain** là hai việc cần phân biệt. Việc tự khai báo `SecurityWebFilterChain` làm Spring Boot nhường cấu hình HTTP security mặc định để chain của bạn định nghĩa chính sách; không được giả định mọi đường dẫn vẫn được bảo vệ như trước nếu bạn thiếu rule.

## 5. Ví dụ Spring Boot WebFlux đầy đủ, chạy được

Mục tiêu học tập: cùng một ứng dụng có **GET public**, **GET yêu cầu USER**, **GET yêu cầu ADMIN** và fallback yêu cầu xác thực. HTTP Basic + form login dùng `Customizer.withDefaults()`; phân quyền được biểu đạt bằng lambda DSL. Chưa thêm datasource hay OAuth2 để dễ thấy chính sách chain.

Dùng **Spring Boot 3.3.13**, Java 17+ và Gradle tương thích. Tạo cấu trúc:

```text
security-lambda-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/security/
    │   ├── DemoApplication.java
    │   └── SecurityConfig.java
    └── test/java/example/security/
        └── SecurityDslTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'security-lambda-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.security'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/java/example/security/DemoApplication.java**

```java
package example.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/ping")
        Mono<String> ping() {
            return Mono.just("pong");
        }

        @GetMapping("/api/report")
        Mono<String> report() {
            return Mono.just("report for USER");
        }

        @GetMapping("/api/admin")
        Mono<String> admin() {
            return Mono.just("admin area");
        }
    }
}
```

**src/main/java/example/security/SecurityConfig.java**

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/report").hasRole("USER")
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

**Giải thích từng phần cấu hình:**

1. `@Bean SecurityWebFilterChain` cung cấp chain để Spring Security dùng cho WebFlux.
2. `ServerHttpSecurity http` do Spring cung cấp khi xây security configuration; khác `HttpSecurity` của MVC.
3. Ba `pathMatchers(HttpMethod.GET, ...)` xác định policy cụ thể cho **GET** của từng route. Các method khác không tự được miễn.
4. `permitAll()` cho phép truy cập `/api/ping` mà không cần login.
5. `hasRole("USER")` yêu cầu authority `ROLE_USER`; `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`.
6. `anyExchange().authenticated()` đặt fallback cho các request chưa khớp rule phía trước. Đây là **yêu cầu xác thực**, không đồng nghĩa phân quyền toàn bộ object của ứng dụng.
7. `httpBasic(Customizer.withDefaults())` bật hỗ trợ HTTP Basic; `formLogin(Customizer.withDefaults())` bật đăng nhập bằng form mặc định.
8. `build()` hoàn tất chain. Không cần gọi `.and()` giữa các lambda.

Ví dụ không khai báo `ReactiveUserDetailsService` riêng nên Spring Boot có thể cung cấp tài khoản phát triển `user` cùng mật khẩu ngẫu nhiên trong startup log, với role mặc định `USER`. Cần đổi cách xác thực trước khi triển khai production.

### Chạy ứng dụng và thử HTTP

Trong thư mục dự án:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle wrapper, dùng `./gradlew bootRun` hoặc `gradlew.bat bootRun` trên Windows. Quan sát log để lấy mật khẩu phát triển của đúng lần khởi động, sau đó thử:

```bash
# Public
curl -i -H "Accept: application/json" http://localhost:8080/api/ping

# Cần xác thực: không credential
curl -i -H "Accept: application/json" http://localhost:8080/api/report

# Thay GENERATED_PASSWORD bằng mật khẩu thấy ở startup log
curl -i -H "Accept: application/json" \
  -u "user:GENERATED_PASSWORD" \
  http://localhost:8080/api/report

# Cùng user, thiếu ROLE_ADMIN
curl -i -H "Accept: application/json" \
  -u "user:GENERATED_PASSWORD" \
  http://localhost:8080/api/admin
```

| Request | Kết quả chính kỳ vọng |
|---|---|
| `GET /api/ping` không credential | `200 OK`, body `pong` |
| `GET /api/report` không credential, `Accept: application/json` | `401 Unauthorized` |
| `GET /api/report` với `user` + mật khẩu đúng | `200 OK`, body `report for USER` |
| `GET /api/admin` với user mặc định `ROLE_USER` | `403 Forbidden` |

Với browser ưu tiên HTML, request chưa đăng nhập có thể nhận redirect đến trang form login thay vì phản hồi `401` kiểu API. Vì thế test ở trên ghi rõ `Accept: application/json` để đo hành vi HTTP Basic/API dễ quan sát. Không giả định body của mọi trang lỗi có một format cố định.

### Kiểm thử tự động bằng WebTestClient

Thêm file dưới đây để kiểm tra chính sách không vô tình bị thay khi sửa lambda. Test đặt mật khẩu **chỉ trong application context của test**, không viết đè giá trị production:

**src/test/java/example/security/SecurityDslTest.java**

```java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.security.user.password=test-password")
@AutoConfigureWebTestClient
class SecurityDslTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsAllowed() {
        client.get().uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void reportRequiresLogin() {
        client.get().uri("/api/report")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void userCanReadReport() {
        client.get().uri("/api/report")
            .headers(headers -> headers.setBasicAuth("user", "test-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report for USER");
    }

    @Test
    void ordinaryUserCannotReadAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("user", "test-password"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

Kỳ vọng **4 test PASS** khi dependency được tải thành công và app chạy trong test context. Đây là ví dụ đầy đủ có tên class, package, source path và dependency tương ứng; không cần tự tạo schema/database. Nếu thử trên dự án đã thay `ReactiveUserDetailsService` bằng bean riêng, hành vi user auto-generated sẽ khác: cần chỉnh fixture cho đúng nguồn xác thực của dự án đó.

## 6. Thứ tự matcher trong `authorizeExchange`

Quy tắc được đánh giá theo thứ tự đăng ký; **quy tắc rộng đặt trước có thể che mất quy tắc cụ thể phía sau**.

Đúng cho API có cả vùng public và admin:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll())
```

Đoạn trên chỉ là **mảnh lambda cấu hình minh họa**, không phải Java độc lập; nếu dùng `anyExchange().denyAll()` cùng form login, nhớ tính cả những đường dẫn đăng nhập, tài nguyên tĩnh và endpoint vận hành cần được phục vụ/cho phép theo thiết kế. Với ví dụ chạy được ở mục 5, fallback dùng `authenticated()` để tránh trộn hai mục tiêu.

Ví dụ cấu hình lỗi về **thứ tự**, không nên sử dụng:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()        // quá rộng
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated())
```

Request `/api/admin/users` đã khớp `/api/**`, nên rule ADMIN đặt phía sau không còn bảo vệ như mong muốn. Hãy đặt rule chặt/cụ thể trước rule rộng.

Ý nghĩa của các authorization action:

| Action | Kiểm tra |
|---|---|
| `permitAll()` | Cho phép mọi người, kể cả chưa xác thực |
| `authenticated()` | Yêu cầu danh tính hợp lệ |
| `hasRole("ADMIN")` | Yêu cầu `ROLE_ADMIN` (theo tiền tố role mặc định) |
| `hasAuthority("SCOPE_orders.read")` | Yêu cầu authority tên chính xác như tham số, hữu ích với scope khi hệ thống map scope thành authority tương ứng |
| `denyAll()` | Từ chối tất cả các request khớp rule |
| `access(...)` | Gọi bộ phân quyền reactive tùy chỉnh, thường cần khi quyền phụ thuộc ngữ cảnh |

**`hasRole("ADMIN")` không nên truyền `"ROLE_ADMIN"` làm tham số** theo mặc định, vì API sẽ tự thêm tiền tố role. Nếu làm phân quyền theo JWT scope, xác định chính xác authority mapping trước khi chọn `hasAuthority(...)`. Quy tắc HTTP không thay thế kiểm tra quyền **trên từng bản ghi/tenant** trong service.

## 7. `pathMatchers` và `securityMatcher` không giống nhau

- `pathMatchers(...)` **bên trong** `authorizeExchange` chỉ quyết định quyền của request đã đi vào chain.
- `securityMatcher(...)` **trên builder `ServerHttpSecurity`** quyết định request có đi vào **chain đó** hay không.

Nếu bạn chỉ có một chain bao phủ toàn bộ ứng dụng, có thể chưa cần `securityMatcher`. Khi có nhiều chain, đây là điểm bắt buộc cân nhắc để không để lộ những đường dẫn ngoài phạm vi match.

**Ví dụ thay thế cho cấu hình đơn ở mục 5** khi muốn tách route API và route web. Đặt hai method `@Bean` trong **một** lớp `@Configuration`, cùng các import theo bên dưới; không giữ thêm bean chain cũ của mục 5.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher
    .PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
class MultiChainSecurityConfig {

    @Bean
    @Order(0)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/ping").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

**Lưu ý cho code trên:** Java không cho phép tách một dòng `import` thành hai dòng như minh họa trình bày; khi sao chép, hãy viết đầy đủ thành một dòng:

```java
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
```

Ở đây `@Order(0)` chọn chain API trước khi thử chain web. Chain API chỉ áp dụng URL bắt đầu `/api/`. Chain web không có `securityMatcher` cụ thể nên có thể đóng vai trò fallback. **Nếu không có fallback và có URL không khớp bất kỳ chain nào, Spring Security sẽ không bảo vệ URL đó qua các chain đã khai báo.** Cần test route không khớp, cả method và prefix.

Phần nhiều chain dùng để minh họa phạm vi và thứ tự; nếu ứng dụng chỉ dùng HTTP API, một chain rõ ràng như mục 5 thường dễ bảo trì hơn.

## 8. Dùng lambda để bật/tắt hoặc cấu hình CSRF, CORS, form login

### 8.1 Bật mặc định khác với tắt tính năng

```java
// Giữ CSRF bằng cơ chế mặc định
.csrf(Customizer.withDefaults())

// Chỉ khi kiến trúc chứng minh không cần CSRF ở chain này
.csrf(csrf -> csrf.disable())
```

**CSRF** có ý nghĩa đặc biệt khi browser tự đính kèm cookie/session hoặc credential vào request ghi. Ví dụ mục 5 chỉ có GET nên không cần tắt CSRF để demo. Không sao chép `csrf.disable()` vào một web app dùng form login chỉ vì POST bị `403`. Trước hết xác định token CSRF được cấp và gửi thế nào. Với API bearer token thực sự không sử dụng credential tự động gửi từ browser, thiết kế CSRF có thể khác, nhưng nên ghi rõ giả định và kiểm thử.

### 8.2 Dùng `Customizer.withDefaults()` cho form/basic

```java
.httpBasic(Customizer.withDefaults())
.formLogin(Customizer.withDefaults())
```

Cả hai đều là **cơ chế xác thực**, không phải rule cho phép truy cập. Nếu muốn một API chỉ nhận bearer token, thường tắt form và Basic trong chain **của API đó**, đồng thời thiết lập cơ chế xác minh token, nhưng phải xem xét cookie/session/CSRF của ứng dụng:

```java
// Mảnh cấu hình thay thế, cần dependency resource-server,
// cấu hình issuer/JWK và policy phù hợp trong ứng dụng thực tế.
http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public").permitAll()
        .anyExchange().authenticated())
    .httpBasic(basic -> basic.disable())
    .formLogin(form -> form.disable())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
```

**Đoạn trên không phải một cấu hình JWT độc lập chạy được:** thiếu bean `SecurityWebFilterChain`, `build()`, dependency Spring Security resource server và thông tin tin cậy của issuer/JWK. Chỉ copy khi bạn đang triển khai chính xác mô hình resource server và đã cấu hình đầy đủ.

### 8.3 CORS không phải chính sách “allow all”

```java
.cors(Customizer.withDefaults())
```

Dòng này tích hợp CORS theo nguồn `CorsConfigurationSource` hoặc cấu hình CORS WebFlux tương ứng, tùy thiết kế. Nó không chứng minh mọi origin được phép và không thay cho authentication/authorization. Không dùng `allowedOrigins("*")` kết hợp credential chỉ vì tiện khi phát triển. Browser thực thi CORS nhưng curl/service client có thể tự gửi request mà không bị cơ chế trình duyệt chặn.

### 8.4 Tùy chỉnh login page

```java
.formLogin(form -> form.loginPage("/login"))
```

Đây là mảnh cấu hình: nếu chọn trang login tùy chỉnh, **ứng dụng phải thật sự phục vụ** `GET /login` và có policy cho phép truy cập phù hợp. Không đặt `loginPage("/login")` rồi kỳ vọng Spring tự tạo giao diện HTML của bạn. Nếu không cần thay login page, `formLogin(Customizer.withDefaults())` đơn giản hơn.

## 9. Chọn cấu trúc cấu hình phù hợp

**Một chain với lambda inline** phù hợp khi policy ngắn và chỉ có vài route: xem thứ tự matcher ngay trong `@Bean`.

**Tách `Customizer<AuthorizeExchangeSpec>` thành hàm** phù hợp khi nhiều policy logic có tên rõ và muốn tái sử dụng trong cấu hình chủ động; vẫn đảm bảo thứ tự gọi tường minh.

**Nhiều chain với `securityMatcher` và `@Order`** phù hợp khi cần cấu hình riêng cho API và giao diện web, hoặc vùng khác có authentication mechanism riêng. Phải có fallback để không vô tình bỏ lọt đường dẫn.

Cần phân biệt hai trục cấu hình:

| Trục | Các câu hỏi |
|---|---|
| Authentication | Ai là người gọi? Basic, form, JWT, OAuth2 hay custom manager? Credential được xác minh ở đâu? |
| Authorization | Người gọi có được vào URL/action hay dữ liệu cụ thể không? `permitAll`, `authenticated`, role, scope, access policy? |

Tùy chỉnh `SecurityWebFilterChain` không tự định nghĩa nguồn người dùng. Nếu Boot vẫn đủ điều kiện tạo user phát triển, tài khoản `user`/mật khẩu sinh tự động vẫn có thể xuất hiện ngay cả khi bạn đã viết lambda DSL.

## 10. Những lỗi phổ biến và cách nhận biết

| Lỗi | Tại sao sai | Cách sửa |
|---|---|---|
| Dùng `HttpSecurity`/`SecurityFilterChain` trong WebFlux | Đây là kiểu của Servlet stack | Dùng `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Nghĩ `Customizer.withDefaults()` cho phép anonymous | Nó bật tính năng với cấu hình mặc định | Đặt `permitAll()` ở đúng matcher nếu muốn public |
| Gọi `anyExchange()` trước rule cụ thể | Rule catch-all che hoặc làm các matcher sau không hợp lệ | Đặt rule cụ thể trước, fallback cuối |
| Viết `"/api/**".permitAll()` trước `"/api/admin/**"` | URL admin bị match rule public rộng | Đặt admin chặt hơn trước rule public/rule rộng |
| Quên fallback hoặc quên phạm vi chain | Có thể bỏ sót endpoint hoặc bỏ qua chain | `anyExchange()` và chain cuối rõ ràng; test URL không khớp |
| Dùng `.and()` theo hướng dẫn cũ | Dễ nhầm builder/spec và không theo lambda DSL hiện hành | Viết các lambda nối tiếp rồi gọi `build()` |
| Nhầm `hasRole("ADMIN")` với `hasAuthority("ADMIN")` | Thông thường role tự gắn tiền tố `ROLE_` | Xác nhận authority thực tế trong principal |
| Tắt CSRF để sửa lỗi `403` | Có thể mở đường CSRF với web dùng cookie/session | Kiểm tra cookie, CSRF token và flow theo loại client |
| Bật `cors(withDefaults())` rồi nghĩ mọi origin được phép | CORS cần chính sách nguồn cụ thể | Cấu hình allowed origin/method/header có chủ đích |
| Bật JWT nhưng quên issuer/audience | Token chưa được xác minh đủ điều kiện | Cấu hình resource server và validator phù hợp |
| Có nhiều `SecurityWebFilterChain` nhưng không quản thứ tự | Request có thể vào chain khác dự kiến | Dùng `securityMatcher`, `@Order` và test từng nhóm |
| Khai báo bean chain rồi nghĩ Boot vẫn tự áp policy ban đầu | Custom chain làm auto-config HTTP mặc định nhường quyền | Tự định nghĩa đầy đủ rule và fallback |
| Chỉ kiểm tra response `200` | Một endpoint có thể vô tình public | Test cả `401`, `403`, route trái phép và method khác |

Một cách debug có hệ thống:

1. Kiểm tra ứng dụng thực sự chạy **reactive** và starter Security có trên classpath.
2. Xác nhận có bao nhiêu `SecurityWebFilterChain` và chain nào có `securityMatcher` khớp request.
3. Đọc thứ tự `pathMatchers` trong `authorizeExchange` trước khi nhìn vào controller.
4. Xác định yêu cầu bị từ chối vì **chưa xác thực** (thường `401` hoặc redirect login) hay **không đủ quyền/CSRF** (thường `403`).
5. Kiểm tra role/scope của principal thực tế; không suy đoán từ username.
6. Dùng WebTestClient cho cả trường hợp cho phép và từ chối, với HTTP method và `Accept` phù hợp.

Khi cần log chẩn đoán bảo mật, chỉ bật mức log chi tiết trong môi trường kiểm thử kiểm soát được và không ghi hoặc chia sẻ bearer token, mật khẩu, cookie/session nhạy cảm.

## 11. Bài tập tự kiểm tra

1. Từ ví dụ mục 5, đổi `/api/ping` thành `authenticated()`; chứng minh test public thất bại và sửa test theo policy mới.
2. Đổi matcher của `/api/report` từ `hasRole("USER")` thành `hasAuthority("ROLE_USER")`; giải thích vì sao kết quả thường tương đương với user mặc định.
3. Thay `.httpBasic(Customizer.withDefaults())` bằng `.httpBasic(basic -> {})` và kiểm thử bốn trạng thái ở mục 5. Nêu điều gì đổi, điều gì không đổi.
4. Đặt `pathMatchers("/api/**").permitAll()` trước rule admin, chứng minh bằng test vì sao thứ tự rule là một kiểm soát bảo mật.
5. Thêm `@Order` và `securityMatcher` để tách API/web, rồi thử một URL không thuộc `/api/**` và giải thích chain nào tiếp nhận.
6. Cho biết vì sao thêm `.cors(Customizer.withDefaults())` không đồng nghĩa cho tất cả origin truy cập, và vì sao `.csrf(csrf -> csrf.disable())` không phải giải pháp mặc định cho web form login.

**Ghi nhớ:** `ServerHttpSecurity` xây security chain; **lambda DSL** giúp mô tả policy theo từng phần; **`Customizer.withDefaults()`** chỉ yêu cầu dùng cấu hình mặc định của tính năng đó. Sự an toàn đến từ việc định nghĩa đúng phạm vi chain, thứ tự matcher, cách xác thực và những điều kiện phân quyền, rồi kiểm chứng bằng request thực tế và test âm tính.

## Tài liệu chính thức để đối chiếu

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security — Authorize ServerHttpRequest (reactive): https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Security — Lambda DSL và `Customizer.withDefaults()`: https://spring.io/blog/2019/11/21/spring-security-lambda-dsl/
- Spring Boot 3.3 — Security (WebFlux): https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
