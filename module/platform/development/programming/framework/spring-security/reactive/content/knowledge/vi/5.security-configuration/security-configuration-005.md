# Tạo chuỗi dự phòng để tránh bỏ sót đường dẫn chưa được bảo vệ

**Module:** Spring Security – Reactive (Spring WebFlux)  
**Ngữ cảnh:** Cấu hình bảo mật nhiều `SecurityWebFilterChain`.  
**Mục tiêu:** Với mọi HTTP request đi qua ứng dụng WebFlux, luôn có một chính sách bảo mật được chọn. Các đường dẫn chưa được cho phép rõ ràng phải bị từ chối theo nguyên tắc **fail closed**.

Khi ứng dụng có các nhóm endpoint khác nhau như công khai, API người dùng, API quản trị và endpoint nội bộ, ta thường khai báo nhiều bean `SecurityWebFilterChain`. Mỗi bean có phạm vi khớp request riêng. Nếu chỉ tạo chuỗi cho `/api/**`, một endpoint nằm ngoài `/api/**` có thể **không khớp bất kỳ chuỗi Spring Security nào**. Việc có `@EnableWebFluxSecurity` không tự bảo đảm tất cả request đều được bảo vệ sau khi ta đã thay cấu hình mặc định bằng các chuỗi giới hạn phạm vi. Một chuỗi **dự phòng áp dụng cho mọi request còn lại**, đặt cuối danh sách, khép lỗ hổng này.

Bài học triển khai cấu hình Java 17+ bằng `ServerHttpSecurity`, giải thích thứ tự khớp và giới hạn bảo vệ, sau đó kiểm thử bằng `WebTestClient` và `curl`. Ví dụ sử dụng HTTP Basic với hai tài khoản *chỉ dành cho localhost* để tập trung vào cơ chế chọn chuỗi; khi dùng OAuth2/JWT, nguyên tắc chuỗi dự phòng vẫn giống nhau.

## 1. Hai tầng khớp request rất dễ nhầm

Trong Spring Security Reactive, cần phân biệt **chọn chuỗi** và **quyết định quyền bên trong chuỗi**:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `http.securityMatcher(...)` | Xác định **toàn bộ SecurityWebFilterChain** có phù hợp request không. | Chuỗi API chỉ nhận `/api/**`. |
| `http.authorizeExchange(ex -> ex.pathMatchers(...))` | Khi chuỗi đã được chọn, quyết định ai có quyền với một nhóm request trong chuỗi đó. | `GET /api/reports/**` đòi `ROLE_READER`. |
| `anyExchange().denyAll()` trong một chuỗi | Từ chối các request **đã chọn chuỗi này** nhưng không khớp quy tắc allow nào trước đó. | `/api/experimental` không tự được mở. |
| Chuỗi **fallback** không gọi `securityMatcher` | Dùng bộ khớp mặc định của `ServerHttpSecurity`, áp dụng với mọi request chưa rơi vào chuỗi ưu tiên hơn. | `/internal/diag`, `/new-feature` và đường không nằm dưới `/api/**`. |

**Quy tắc lựa chọn:** Spring Security kiểm tra các `SecurityWebFilterChain` theo thứ tự ưu tiên, lấy **chuỗi khớp đầu tiên** và thực thi các bộ lọc của chuỗi đó. Một request bị `denyAll()` trong chuỗi đầu tiên **không thử tiếp** chuỗi thứ hai. Đây là điểm then chốt: chuỗi dự phòng chỉ xử lý request **không khớp chuỗi trước**; nó không sửa được quy tắc quá rộng ở bên trong chuỗi trước.

Ví dụ nguy hiểm về **thiếu fallback**:

```java
@Bean
SecurityWebFilterChain onlyApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây chỉ là fragment: cần import, class cấu hình và các bean còn lại. Chuỗi trên chỉ xem xét `/api/**`. Nếu ứng dụng có controller `GET /internal/diag` thì request ấy **không được chuỗi này bảo vệ**. Khi không tồn tại chuỗi khác khớp, request không đi qua các bộ lọc Spring Security dự kiến; controller có thể được gọi nếu không có cơ chế độc lập chặn nó.

## 2. Thiết kế fail closed trước khi viết code

Ta xây ba chuỗi có thứ tự tường minh:

| Thứ tự | Tên chuỗi | Chọn request bằng `securityMatcher` | Quy tắc trong chuỗi |
| --- | --- | --- | --- |
| `@Order(1)` | `publicChain` | Chỉ `GET /public/ping` | Cho phép vô danh |
| `@Order(2)` | `apiChain` | `/api/**` với mọi HTTP method | Chỉ cấp quyền cho những method/path được liệt kê; cuối chuỗi `denyAll` |
| `@Order(Ordered.LOWEST_PRECEDENCE)` | `fallbackChain` | Không gọi `securityMatcher`: khớp mọi request còn lại | `anyExchange().denyAll()` |

Hai đặc điểm bảo vệ khác nhau:

1. **Fallback đóng các khoảng trống giữa các chuỗi:** `/internal/diag` không khớp `/public/ping` hay `/api/**` nên đi vào chuỗi cuối, bị từ chối.
2. **Deny mặc định đóng khoảng trống bên trong từng chuỗi:** `/api/experimental` khớp `apiChain`, nên fallback sẽ **không chạy**. Chính `apiChain` phải kết thúc bằng `anyExchange().denyAll()`.

Không nên sử dụng `anyExchange().permitAll()` trong fallback. `authenticated()` trong fallback an toàn hơn “không có kiểm soát”, nhưng vẫn có thể vô tình mở endpoint mới cho **mọi người đã đăng nhập**, ngay cả khi đường đó chưa được phân quyền. Đối với chính sách *không cho phép khi chưa khai báo*, `denyAll()` là lựa chọn chặt chẽ hơn; mở đường hợp lệ bằng thay đổi cấu hình và test rõ ràng.

### Luồng chọn chuỗi

```text
Request HTTP
    |
    v
Order(1) publicChain: GET /public/ping ?
    | YES -> permitAll -> controller công khai
    |
    NO
    v
Order(2) apiChain: /api/** ?
    | YES -> đối chiếu rule METHOD + PATH
    |        | được phép -> controller API
    |        | không khớp rule / thiếu quyền -> từ chối ngay
    |
    NO
    v
LOWEST_PRECEDENCE fallbackChain: match-all
    |
    v
anyExchange().denyAll() -> không cho gọi handler còn lại
```

Thứ tự số nhỏ chạy trước. Không đặt fallback trước chuỗi API; vì fallback khớp mọi request, nó sẽ “nuốt” hết lưu lượng và những chuỗi phía sau không còn cơ hội xử lý.

## 3. Dựng ví dụ Spring Boot WebFlux có chuỗi dự phòng

### 3.1. Cấu trúc và dependency

Ví dụ có thể chạy độc lập với **JDK 17+**, Maven 3.9+ và một cổng localhost còn trống. Dùng Spring Boot `3.5.7` là một phiên bản có trên Maven Central để minh họa tính tái lập; khi triển khai thật, chọn bản vá được hỗ trợ mới hơn theo chính sách dự án.

```text
reactive-security-fallback/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/fallback/
    │   │   ├── FallbackApplication.java
    │   │   ├── SecurityChains.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/fallback/
        └── FallbackSecurityTests.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-security-fallback</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-security-fallback
server.port=8080
```

Chỉ dùng WebFlux starter cho bài này; thêm cả Servlet MVC starter có thể thay đổi loại ứng dụng web mà Spring Boot chọn. Đừng dùng cấu hình `HttpSecurity`/`SecurityFilterChain` của Servlet để thay thế API tương ứng của WebFlux: ở đây phải dùng **`ServerHttpSecurity` và `SecurityWebFilterChain`**.

`src/main/java/demo/fallback/FallbackApplication.java`:

```java
package demo.fallback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(FallbackApplication.class, args);
    }
}
```

### 3.2. Cấu hình ba SecurityWebFilterChain

`src/main/java/demo/fallback/SecurityChains.java`:

```java
package demo.fallback;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SecurityChains {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain publicChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(new PathPatternParserServerWebExchangeMatcher(
                "/public/ping", HttpMethod.GET))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports/**").hasRole("READER")
                .pathMatchers(HttpMethod.GET, "/api/admin/dashboard")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }

    @Bean
    @Order(Ordered.LOWEST_PRECEDENCE)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            // Không gọi securityMatcher: dùng matcher mặc định (mọi request).
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(login -> login.disable())
            .build();
    }
}
```

Giải thích các lựa chọn quan trọng:

- `@Order(1)` cho một đường công khai **cụ thể** và đúng HTTP method. Nếu chọn mẫu quá rộng `/public/**` rồi `permitAll()`, mọi endpoint thêm về sau dưới `/public` có thể trở thành công khai ngoài ý muốn.
- `@Order(2)` chỉ áp dụng `/api/**`. Ba quy tắc allow đòi đúng GET, path và role; yêu cầu POST cùng đường sẽ không tự được cấp quyền. `anyExchange().denyAll()` ở cuối chặn mọi API khác dù chúng có controller.
- `@Order(Ordered.LOWEST_PRECEDENCE)` đặt chuỗi cuối sau chuỗi chuyên biệt. Vì không gọi `securityMatcher`, `ServerHttpSecurity` giữ matcher mặc định phù hợp mọi request. Đây mới là **fallback match-all**, không phải `securityMatcher("/misc/**")`.
- `httpBasic` được bật trong hai chuỗi bảo vệ để HTTP client có thể xác thực. `formLogin` tắt để tránh tự chuyển một request API thành trang login; hệ thống thực nên chọn cơ chế thích hợp (session, OAuth2 resource server, v.v.).
- `{noop}` chấp nhận mật khẩu rõ **chỉ cho demo localhost**. Không hard-code tài khoản production, không dùng `{noop}` trong cấu hình thực.
- Phần `.anyExchange().denyAll()` của fallback không tạo quyền ADMIN đặc biệt: **kể cả admin cũng bị từ chối** với route ngoài danh sách. “Admin” không đồng nghĩa với quyền truy cập mọi endpoint bất kỳ.

### 3.3. Controller để nhìn thấy hiệu quả của fallback

`src/main/java/demo/fallback/DemoController.java`:

```java
package demo.fallback;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/api/reports/{id}")
    public Mono<String> report(@PathVariable String id) {
        return Mono.just("report-" + id);
    }

    @GetMapping("/api/admin/dashboard")
    public Mono<String> adminDashboard() {
        return Mono.just("admin-ok");
    }

    @GetMapping("/api/experimental")
    public Mono<String> experimental() {
        // Có route thật nhưng chưa được cấp trong apiChain.
        return Mono.just("experimental-route");
    }

    @GetMapping("/internal/diag")
    public Mono<String> internalDiag() {
        // Có route thật nhưng không thuộc chuỗi public/api.
        return Mono.just("internal-route");
    }
}
```

Hai endpoint `/api/experimental` và `/internal/diag` được thêm **cố ý trong demo để kiểm chứng từ chối**; không nên công bố endpoint nội bộ thực rồi chỉ dựa vào một lớp bảo vệ duy nhất. `/api/me` đọc principal từ Reactor Context theo cách phù hợp reactive. Controller trả `Mono` cho WebFlux quản lý subscription; không gọi `subscribe()` trực tiếp.

## 4. Khi request chạy, Spring chọn chain nào?

| Request | Chuỗi được chọn | Quy tắc tác dụng | Kết quả với demo |
| --- | --- | --- | --- |
| `GET /public/ping`, không credential | `publicChain` | `permitAll` | `200`, `pong` |
| `GET /api/me`, không credential | `apiChain` | `authenticated` | Thông thường `401` (Basic challenge) |
| `GET /api/me`, reader hợp lệ | `apiChain` | `authenticated` | `200`, `reader` |
| `GET /api/reports/42`, reader hợp lệ | `apiChain` | `hasRole("READER")` | `200`, `report-42` |
| `GET /api/admin/dashboard`, reader hợp lệ | `apiChain` | `hasRole("ADMIN")` | `403` |
| `GET /api/admin/dashboard`, admin hợp lệ | `apiChain` | `hasRole("ADMIN")` | `200`, `admin-ok` |
| `GET /api/experimental`, admin hợp lệ | `apiChain` | `anyExchange().denyAll()` | `403`, dù controller tồn tại |
| `GET /internal/diag`, admin hợp lệ | **`fallbackChain`** | `anyExchange().denyAll()` | `403`, dù controller tồn tại |
| `GET /unknown`, admin hợp lệ | **`fallbackChain`** | `anyExchange().denyAll()` | `403` trước khi xem xét mapping |
| `POST /public/ping` | **`fallbackChain`** theo matcher có method | `denyAll` / có thể cả CSRF | `4xx` |

Tại sao có `403` cho `/unknown` thay vì `404`? Authorization filter có thể từ chối request **trước khi** bộ định tuyến tìm controller. Vì vậy `403` không chứng minh URL đó thực sự tồn tại. Ngược lại, một `404` cũng không chứng minh một route đang được bảo vệ đúng nếu request chưa từng đi qua chain phù hợp.

**401 so với 403:** Với HTTP Basic và cấu hình ví dụ, client chưa có hoặc dùng credential sai cho endpoint protected thường nhận `401 Unauthorized` kèm `WWW-Authenticate`, còn user đã xác thực nhưng thiếu quyền/đi vào `denyAll` nhận `403 Forbidden`. Cấu hình authentication entry point, access denied handler, login form, cơ chế token hoặc response đã commit có thể thay đổi response thực tế. Để chứng minh fallback, nên test **đăng nhập hợp lệ mà vẫn bị 403**, cùng với kiểm tra không đăng nhập không được 2xx.

## 5. Chạy và kiểm tra nhanh bằng curl

Chạy tại thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Để Maven chạy, cần JDK 17+, Maven và khả năng tải dependencies. Chờ log báo server Netty khởi chạy trên cổng 8080. Tại terminal khác:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user reader:reader123 http://localhost:8080/api/me
curl -i --user reader:reader123 http://localhost:8080/api/reports/42
curl -i --user reader:reader123 http://localhost:8080/api/admin/dashboard
curl -i --user admin:admin123 http://localhost:8080/api/admin/dashboard
curl -i --user admin:admin123 http://localhost:8080/api/experimental
curl -i --user admin:admin123 http://localhost:8080/internal/diag
curl -i --user admin:admin123 http://localhost:8080/unknown
```

Status mong đợi theo thứ tự: **200, 401, 200, 200, 403, 200, 403, 403, 403**. Body thành công lần lượt là `pong`, `reader`, `report-42`, `admin-ok`. Nếu dùng Windows PowerShell mà `curl` là alias, hãy gọi `curl.exe`. Lệnh `curl -i` cho thấy status và header; không chỉ nhìn body.

Đặc biệt, hai lệnh cuối xác nhận vai trò fallback: **admin đã xác thực đầy đủ vẫn không truy cập được** endpoint ngoài vùng cho phép. Lệnh `/api/experimental` xác nhận vai trò của `anyExchange().denyAll()` *trong apiChain*. Nếu bỏ fallback, `/internal/diag` có thể không còn đi qua Spring Security; nếu bỏ `denyAll` trong `apiChain` rồi thay bằng một quy tắc quá rộng, `/api/experimental` có thể vô tình mở.

Có thể kiểm tra HTTP code gọn trên shell kiểu Unix:

```bash
curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}\n' \
  --user admin:admin123 \
  http://localhost:8080/internal/diag
```

Kết quả:

```text
403
```

Không đánh đồng **curl exit code bằng 0** với HTTP status 200: mặc định `curl` vẫn có thể exit 0 khi server trả 403. Đọc `%{http_code}` hoặc phần status line. Không dùng mật khẩu demo làm mật khẩu thật; Basic chỉ dùng Base64, không thay thế mã hóa HTTPS trên đường truyền.

## 6. WebTestClient: khóa quy tắc bằng test tự động

Một cấu hình fallback chỉ đáng tin khi có kiểm thử chứng minh: đường công khai vẫn mở; endpoint được phép hoạt động; sai role bị chặn; **route có controller nhưng nằm ngoài chuỗi chuyên biệt bị chặn**; và route trong API nhưng chưa có rule vẫn bị chặn.

Với WebFlux và Spring Boot `RANDOM_PORT`, `@SpringBootTest` tạo server HTTP thật trên cổng ngẫu nhiên, rồi `WebTestClient` gửi request đến server đó. Không phải khởi động `mvn spring-boot:run` trước khi chạy test. Test dùng Basic headers để kiểm tra đường HTTP thực, không giả lập `SecurityContext` trong một session riêng.

`src/test/java/demo/fallback/FallbackSecurityTests.java`:

```java
package demo.fallback;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FallbackSecurityTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicGetIsAnonymous() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void apiNeedsAuthentication() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void readerCanReadOwnName() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void readerCanReadReport() {
        client.get().uri("/api/reports/42")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-42");
    }

    @Test
    void readerCannotAccessAdmin() {
        client.get().uri("/api/admin/dashboard")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/api/admin/dashboard")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void unknownApiPathIsDeniedWithinApiChain() {
        client.get().uri("/api/experimental")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void internalEndpointIsDeniedByFallback() {
        client.get().uri("/internal/diag")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownTopLevelPathIsDeniedByFallback() {
        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousCannotReachInternalEndpoint() {
        client.get().uri("/internal/diag")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
```

Chạy:

```bash
mvn test
```

Nếu dự án chỉ chứa class test này, kỳ vọng **10 test thành công**; không nên phụ thuộc một bản log Maven cố định. Các assertion `.isForbidden()` dành cho tài khoản đã xác thực, giúp phân biệt sự từ chối theo quyền với tình trạng không đăng nhập. Test `anonymousCannotReachInternalEndpoint` chỉ đòi `4xx` vì một số cấu hình cơ chế xử lý authentication khác sẽ chọn 401 hoặc 403; điều bắt buộc là **không trả 2xx/3xx dẫn tới nội dung được bảo vệ**.

Những phép thử có giá trị nhất là `unknownApiPathIsDeniedWithinApiChain` và `internalEndpointIsDeniedByFallback`: cùng một controller **có tồn tại**, nhưng bị chặn ở hai vị trí khác nhau. Nếu vô tình đổi fallback thành `permitAll()`, test `internalEndpointIsDeniedByFallback` báo lỗi. Nếu nới rộng API thành `anyExchange().authenticated()`, test `unknownApiPathIsDeniedWithinApiChain` phát hiện đường chưa phê duyệt được mở cho user.

### 6.1. Đảm bảo test thực sự dùng WebFilter bảo mật

- Với `@SpringBootTest(RANDOM_PORT)`, test chạy qua HTTP và toàn bộ filter được cấu hình trong application context. Không thay bằng unit test gọi trực tiếp `controller.internalDiag()`: cách đó bỏ qua SecurityWebFilterChain.
- Nếu dùng `@WebFluxTest` slice, phải kiểm tra các bean chuỗi đã được load và các dependency được mock/import đúng. Một test chạy qua WebFlux nhưng không nạp cấu hình bảo mật không chứng minh hệ thống đang fail closed.
- Với `WebTestClient.bindToController(...)` thuần túy, không mặc định có security filter; cần bind vào WebApplicationContext hoặc cấu hình thích hợp để test policy.
- Không dùng `mockUser` bên client khi kiểm tra server thật qua `RANDOM_PORT`; `mockUser` dành cho các test mock web context phù hợp. Qua HTTP thật phải gửi Basic, Bearer token hoặc cookie/session theo cơ chế server đang dùng.
- Chạy toàn bộ bộ test sau khi thêm đường dẫn hoặc đổi matcher. Một test đúng chỉ ở `/api/me` không đủ để phát hiện `/internal/diag` bị bỏ sót.

## 7. Chọn mặc định denyAll hay authenticated?

Một chuỗi fallback có thể dùng:

```java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated())
```

Điều này buộc có danh tính hợp lệ nhưng **có thể mở tất cả endpoint mới cho mọi người dùng đã đăng nhập**. Khi một endpoint nội bộ, quản trị hoặc chức năng đang thử nghiệm xuất hiện mà chưa được liệt kê, `authenticated()` không có role/domain permission tương ứng. Phương án fail-closed cho bài học là:

```java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().denyAll())
```

Đây là **hai fragment cấu hình**, không phải hai chương trình Java đầy đủ. `denyAll()` khiến việc thêm route mới trở thành sự kiện cần cập nhật rule có chủ đích và kiểm thử. Với app hướng người dùng, có thể cấu hình fallback `authenticated()` **nếu** yêu cầu sản phẩm thật sự là mọi route ngoài nhóm đặc biệt đều dành cho toàn bộ user đăng nhập; khi đó cần kiểm soát phạm vi qua review, test và quyền tại service. Chọn chính sách dựa trên mô hình quyền, không chọn theo kết quả 401/403 “dễ nhìn” hơn.

**Không mở rộng `permitAll` để xử lý lỗi 404.** Cách này có thể làm endpoint vô tình công khai. Việc response là 403 cho URL không tồn tại là hệ quả hợp lệ của fail-closed. Nếu sản phẩm yêu cầu trả 404 cho một nhóm URL, hãy thiết kế cụ thể tại routing/error handling và đánh giá tác động security; đừng làm yếu mặc định của toàn hệ thống.

## 8. Những sai lầm thực tế khi cấu hình fallback

### 8.1. Đặt chuỗi catch-all quá sớm

**Sai:**

```java
@Bean
@Order(1)
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex.anyExchange().denyAll())
        .build();
}
```

Nếu matcher mặc định của nó là match-all, request `/public/ping` lẫn `/api/me` đều khớp chuỗi này đầu tiên; chuỗi API/đường công khai phía sau không được chọn. Hãy đặt fallback ở thứ tự cuối (`Ordered.LOWEST_PRECEDENCE` hoặc không đặt `@Order` khi chắc chắn các chuỗi chuyên biệt có thứ tự cao hơn); tường minh thứ tự giúp dễ bảo trì.

### 8.2. Chỉ có một chain với securityMatcher hẹp

Đôi khi cấu hình chỉ định `securityMatcher("/api/**")` rồi tưởng `anyExchange()` bên trong có nghĩa “mọi request đến server”. Thực tế nó chỉ có nghĩa **mọi request đã khớp /api/** và được chọn vào chain đó**. Đường ngoài scope cần fallback match-all.

### 8.3. Nghĩ rằng fallback tiếp tục xử lý sau khi chuỗi trước deny

Spring Security không tìm “chuỗi cho phép tiếp theo” sau khi policy trong chuỗi đang chọn trả deny. Một request `/api/experimental` đã khớp `apiChain` không chạm fallback; do đó, **mỗi chuỗi chuyên biệt cũng phải có default cuối hợp lý**. Quy tắc cuối nên đặt sau các rule cụ thể vì thứ tự rule trong `authorizeExchange` quan trọng.

### 8.4. Matcher quá rộng hoặc bị chồng lên nhau

Ví dụ `/api/**` đặt trước `/api/admin/**` sẽ lấy luôn request admin nếu hai phần là hai chain có thứ tự như vậy. Chain admin riêng không chạy. Có hai cách đúng: đặt matcher admin trước matcher chung, hoặc dùng **một chain API** rồi khai báo `/api/admin/**` trước rule rộng hơn trong `authorizeExchange`. Không vô tình dùng `/public/**` + `permitAll` khi chỉ định cho một URL nhỏ. Với matcher phụ thuộc HTTP method, hãy kiểm tra cả GET/POST/PUT/DELETE/OPTIONS thực tế.

### 8.5. Dùng Sai stack Spring Security

Ở WebFlux dùng `SecurityWebFilterChain` + `ServerHttpSecurity` + `ServerWebExchangeMatcher`. Các ví dụ dùng `SecurityFilterChain` + `HttpSecurity` + `RequestMatcher` là API **Servlet**, không thể copy nguyên dạng sang app reactive.

### 8.6. Mở rộng quyền chỉ để “fix” 403

403 có thể do `denyAll` (mặc định), thiếu role hoặc CSRF ở phương thức thay đổi trạng thái; 401 có thể do thiếu Basic/Bearer token; CORS có thể làm browser chặn script ngay cả khi curl thành công. Cần xem request method, path, status, challenge headers, cấu hình chain và log trước khi sửa policy. Tuyệt đối không sửa `anyExchange().denyAll()` thành `permitAll()` chỉ để một bài test 403 chuyển xanh.

### 8.7. Tưởng có fallback là dữ liệu luôn được bảo vệ

Fallback hoạt động ở boundary HTTP của ứng dụng WebFlux tương ứng. Nó **không thay thế** kiểm tra quyền ở tầng service, quyền trên từng bản ghi, `@EnableReactiveMethodSecurity`/`@PreAuthorize`, multi-tenant isolation hoặc xác thực upstream. Ví dụ một route được phép `GET /api/reports/42` vẫn phải kiểm tra reader hiện tại có quyền với **report 42** hay không. `ROLE_READER` không tự chứng minh quyền trên mọi dữ liệu.

## 9. Ngoại lệ và phạm vi cần xem trước khi triển khai thật

**Health, readiness, metrics và actuator:** Đừng tự mở toàn bộ `/actuator/**` bằng `permitAll`. Chỉ cho phép endpoint thật sự cần public (ví dụ readiness), giữ metrics/env/heapdump và thông tin nhạy cảm được xác thực, giới hạn hoặc không expose. Nếu actuator chạy trên **management port/ApplicationContext khác**, phải kiểm tra cấu hình security của ngữ cảnh đó riêng; một fallback trong web context chính không tự bảo vệ mọi server/cổng khác.

**CORS và preflight:** Browser có thể gửi `OPTIONS` preflight trước khi gọi API có cross-origin; nếu `apiChain` chỉ cho phép GET và `anyExchange().denyAll`, preflight OPTIONS có thể bị chặn. Khi có client cross-origin hợp lệ, hãy định nghĩa CORS và chính sách OPTIONS rõ ràng, kiểm thử origin/header cụ thể; đừng `permitAll` mọi method/path chỉ để sửa CORS. Request `OPTIONS` và `GET` là hai request khác nhau.

**CSRF:** Spring Security WebFlux bật cơ chế CSRF theo cấu hình mặc định thường gặp; POST/PUT/PATCH/DELETE có thể nhận 403 do thiếu token trước cả khi đi đến authorization mong đợi. Ví dụ chỉ có GET nên không cần tắt CSRF. Với API token thuần túy có thể thiết kế CSRF riêng nếu phù hợp, nhưng phải hiểu mô hình credential/cookie trước khi disable.

**Login, logout và endpoints framework:** Nếu bật form login, OAuth2 login hoặc logout, cơ chế đó có thể tạo endpoint xử lý riêng. Matcher quá hẹp hoặc fallback deny-all có thể chặn flow login/callback trước khi filter dành cho flow đó thực thi. Phân bổ rõ các đường `/login`, `/logout`, `/oauth2/**`, callback và trang lỗi cho chuỗi phù hợp; không mở toàn bộ prefix một cách không giới hạn.

**Proxy, gateway và forwarding:** Test cả path bên ngoài và path thực tế ứng dụng WebFlux nhận sau khi proxy/gateway rewrite. Matcher chạy trên thông tin request **thực sự tới ứng dụng**, không trên giả định của tài liệu API gateway. Cấu hình context path, base path, forwarded headers, URL encoding và trailing slash có thể làm kết quả match khác dự tính. Tránh coi firewall URL normalization là khả năng thay thế security matcher.

**Functional routes và tài nguyên tĩnh:** `RouterFunction`, WebSocket handshake, static assets hoặc controller mới cũng đi qua boundary HTTP nếu cùng WebFlux context, nhưng phải test URL/method tương ứng. Nếu nhóm static assets được public, công khai **đúng những đường cần thiết**, tránh vô tình để API mới nằm trong vùng public rộng.

**Nhiều SecurityWebFilterChain khác:** Một plugin/cấu hình module khác có thể khai báo chain catch-all hoặc chain matcher rộng với `@Order` cao hơn và che khuất fallback của bạn. Rà soát bean chain của toàn ứng dụng theo đúng thứ tự hiệu lực khi tích hợp; không giả định chỉ có ba bean trong demo.

## 10. Quy trình áp dụng vào dự án có sẵn

1. **Liệt kê security chain hiện tại:** Mỗi bean `SecurityWebFilterChain`, `@Order`, `securityMatcher`, cơ chế xác thực, các rule `authorizeExchange` và vị trí `anyExchange`. Đây là công việc kiểm toán thiết kế khi tích hợp, không có nghĩa phải copy nội dung của app khác.
2. **Phân nhóm các URL thật:** Chỉ ra endpoint public, admin, API được phép và đường nội bộ. Ghi kèm HTTP method, quyền và cơ chế xác thực, thay vì chỉ liệt kê prefix.
3. **Đặt chain chuyên biệt trước:** Dùng matcher đủ cụ thể, tránh chồng chéo; cuối mỗi chain dùng fail-closed nếu route chưa liệt kê không được mở.
4. **Thêm fallback match-all cuối:** Không đặt `securityMatcher` trên fallback; `anyExchange().denyAll()` để từ chối mọi đường còn sót. Đảm bảo không có chuỗi ưu tiên cao hơn vô tình match-all.
5. **Viết test âm trước khi mở thêm route:** Một endpoint thật nằm ngoài matcher chuyên biệt phải bị chặn cả khi dùng user hợp lệ; một endpoint nằm trong prefix API nhưng chưa có rule phải bị chặn. Test role đúng/sai và phương thức khác nhau.
6. **Mở đường theo yêu cầu sản phẩm:** Thêm matcher/rule và test xác nhận đường được phép; sau đó chạy lại toàn bộ phép thử từ chối ngoài phạm vi.
7. **Kiểm tra lớp tiếp theo:** Bảo vệ quyền trên dữ liệu, service và luồng reactive; xử lý CORS/CSRF/login/logout, actuator và proxy riêng theo mô hình triển khai.

Có thể lưu bảng policy dùng để review:

| Phân loại | Method | Pattern | Chain | Kết quả mong muốn |
| --- | --- | --- | --- | --- |
| Public | GET | `/public/ping` | Public | Anonymous 200 |
| User | GET | `/api/me` | API | Anonymous 401; authenticated 200 |
| Report | GET | `/api/reports/**` | API | READER 200; thiếu role 403 |
| Admin | GET | `/api/admin/dashboard` | API | ADMIN 200; READER 403 |
| API chưa khai báo | Bất kỳ | `/api/experimental` | API default deny | Không cấp quyền |
| Đường ngoài nhóm | Bất kỳ | `/internal/diag` | Fallback | Không cấp quyền |
| URL mới | Bất kỳ | Ngoài các nhóm được phép | Fallback | Không cấp quyền |

## 11. Câu hỏi tự đánh giá

**Câu 1:** Một request `GET /api/experimental` đã khớp `apiChain`, nhưng không khớp rule allow. Có chuyển sang fallback không?  
**Không.** Chain được chọn theo matcher trước, rồi policy trong chain quyết định; `anyExchange().denyAll()` của API từ chối.

**Câu 2:** Fallback không khai báo `securityMatcher` có thật sự là match-all không?  
**Có, theo mặc định của `ServerHttpSecurity`** trong ví dụ. Nếu tự đặt matcher hẹp cho fallback, nó không còn bảo vệ mọi request còn lại.

**Câu 3:** Vì sao `@Order(1)` không thích hợp cho fallback?  
Vì fallback match-all chiếm mọi request trước các chain chuyên biệt, khiến public/API không được chọn.

**Câu 4:** Nếu fallback đổi thành `authenticated()`, user đã đăng nhập có thể gọi `/internal/diag` không?  
**Có thể**, vì người đó thỏa `authenticated()`, dù endpoint chưa hề được phân quyền cụ thể. Đó là lý do chọn `denyAll()` khi yêu cầu fail closed.

**Câu 5:** Test `/unknown` trả 403 có chứng minh controller tồn tại không?  
**Không.** Security có thể từ chối trước khi định tuyến; hãy dùng endpoint **thực sự tồn tại** như `/internal/diag` để chứng minh fallback ngăn controller.

**Câu 6:** Có chain fallback rồi, có thể bỏ test phân quyền từng bản ghi không?  
**Không.** Fallback bảo vệ boundary HTTP chưa được liệt kê; đường đã cấp phép còn cần authorization theo người dùng, tài nguyên và ngữ cảnh nghiệp vụ.

### Nguồn chính thức để đối chiếu

- Spring Security, *WebFlux Security — Multiple Chains Support*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security, `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security, `PathPatternParserServerWebExchangeMatcher` API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html
- Spring Boot, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html

**Điều phải nhớ:** Để không bỏ sót đường dẫn, cần **hai chốt**: (1) `anyExchange().denyAll()` bên trong mọi chuỗi chuyên biệt có rule chọn lọc, để chặn route mới *trong* phạm vi của chuỗi; (2) một `SecurityWebFilterChain` match-all, có thứ tự thấp nhất và `denyAll()`, để chặn route *ngoài* tất cả các chuỗi chuyên biệt. Đối chiếu bằng test có cả controller thật bị chặn và request được phép đi qua đúng đường.