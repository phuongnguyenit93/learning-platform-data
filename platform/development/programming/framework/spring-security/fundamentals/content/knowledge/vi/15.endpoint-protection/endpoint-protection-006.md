# anyRequest, anyExchange và chính sách cho đường dẫn còn lại

> **Spring Security fundamentals → Bảo vệ endpoint.** Trong một ứng dụng có nhiều tuyến API, các quy tắc cho `/public/**`, `/api/**` hoặc `/admin/**` thường chỉ bao phủ một phần request. Bài này giải thích cách chọn quy tắc **cuối cùng** cho những request chưa khớp, phân biệt `anyRequest()` ở Servlet với `anyExchange()` ở WebFlux, và tránh bỏ sót đường dẫn khi ứng dụng có nhiều security filter chain.

## 1. Câu hỏi xuất phát: request không khớp quy tắc cụ thể sẽ ra sao?

Giả sử ứng dụng có ba URL:

- `GET /public/ping`: cho phép mọi người.
- `GET /api/profile`: yêu cầu đăng nhập.
- `GET /api/admin/report`: yêu cầu role ADMIN.

Sau một lần triển khai, nhóm thêm `GET /internal/diagnostic` nhưng chưa quyết định ai được phép gọi. Điều đáng quan tâm là **chính sách áp dụng cho URL mới**, ngay cả khi controller đã tồn tại.

Với cách cấu hình phổ biến, có hai lựa chọn rõ ràng:

```java
// Servlet / Spring MVC
.anyRequest().authenticated()
```

Dòng này yêu cầu mọi request **còn lại trong chain đang được chọn** phải có danh tính đã xác thực. Người đã đăng nhập vẫn có thể đi qua tầng HTTP vào một endpoint mới nếu không có kiểm tra bổ sung.

```java
// Reactive / Spring WebFlux
.anyExchange().denyAll()
```

Dòng này từ chối tất cả exchange **còn lại trong chain đang được chọn**. Endpoint mới không tự mở ra khi nhóm quên thêm quy tắc cho nó.

Cả `anyRequest()` và `anyExchange()` đều là **catch-all authorization matcher**. Hai hàm không quyết định chain nào áp dụng, không tự xác thực người dùng, không thay thế kiểm tra CSRF, quyền nghiệp vụ hay quyền trên dữ liệu. Chúng trả lời một câu hỏi cụ thể: **“Khi các authorization matcher đứng trước không khớp, dùng chính sách nào?”**

## 2. Nắm vững ba lớp quyết định

Một request đi qua ba bước logic khác nhau:

```text
HTTP request / WebFlux exchange
           |
           v
[1] Chọn security filter chain phù hợp
    - Servlet: SecurityFilterChain + securityMatcher(...)
    - WebFlux: SecurityWebFilterChain + securityMatcher(...)
           |
           v
[2] Đánh giá các authorization rule theo thứ tự
    - requestMatchers(...) / pathMatchers(...)
    - Chỉ rule khớp đầu tiên quyết định tại đây
    - Cuối cùng: anyRequest(...) / anyExchange(...)
           |
           v
[3] Nếu được phép: controller → service → dữ liệu
    - Vẫn áp dụng method security và object/tenant scope
```

Đây là ba khái niệm dễ bị nhầm:

| Khái niệm | Servlet/MVC | WebFlux/reactive | Ý nghĩa |
|---|---|---|---|
| Chọn chain | `HttpSecurity.securityMatcher(...)` | `ServerHttpSecurity.securityMatcher(...)` | Chain này có xử lý request/exchange hay không? |
| Một rule authorization | `authorizeHttpRequests(...).requestMatchers(...)` | `authorizeExchange(...).pathMatchers(...)` | Với request trong chain, rule nào khớp? |
| Rule dự phòng cuối | `anyRequest()` | `anyExchange()` | Rule nào xử lý phần **chưa khớp** trong chain? |
| Cho phép tất cả | `permitAll()` | `permitAll()` | Rule này không yêu cầu quyền để qua bước authorization |
| Cần đăng nhập | `authenticated()` | `authenticated()` | Đòi hỏi principal được xác thực, chưa chứng minh quyền nghiệp vụ |
| Từ chối tất cả | `denyAll()` | `denyAll()` | Rule này từ chối bất kể quyền/role |

**Phạm vi rất quan trọng:** Một `anyRequest().denyAll()` nằm trong chain chỉ áp dụng `/api/**` **không** tự bảo vệ `/internal/**`. Nếu `/internal/**` không khớp bất kỳ chain nào, Spring Security có thể không tham gia bảo vệ request đó. Cần một chain fallback bao phủ tất cả request còn lại.

## 3. Servlet: `anyRequest()` trong `authorizeHttpRequests`

### 3.1. Cấu hình theo thứ tự từ cụ thể đến tổng quát

Đoạn Java minh họa sau nằm trong một Spring configuration/bean, chưa phải chương trình độc lập:

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/admin/report")
                .hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/profile")
                .authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Ý nghĩa khi một request đến:

1. Spring Security xét các cặp matcher → authorization theo **thứ tự khai báo**.
2. Nếu request khớp `GET /public/ping`, áp dụng `permitAll`; không tiếp tục thử `anyRequest`.
3. Nếu khớp `GET /api/admin/report`, yêu cầu `ROLE_ADMIN` theo tiền tố role mặc định.
4. Nếu khớp `GET /api/profile`, chỉ yêu cầu đăng nhập tại tầng HTTP.
5. Nếu không khớp các quy tắc trên, áp dụng `denyAll`.

`anyRequest()` nên đặt **sau cùng** trong chuỗi rule. Vì nó bắt tất cả phần còn lại, đặt trước quy tắc cụ thể làm quy tắc phía sau không còn cơ hội chạy, và API DSL có thể từ chối cấu hình đó.

Lưu ý `requestMatchers(HttpMethod.GET, ...)` phân biệt method: một request `POST /api/profile` **không khớp** rule GET và sẽ rơi vào fallback, dù path giống hệt. Nếu một matcher chỉ có path, nó có thể áp dụng cho nhiều HTTP method. Khi thiết kế API nhạy cảm, nên định nghĩa verb được hỗ trợ rõ ràng và test riêng hành vi này.

### 3.2. `anyRequest().authenticated()` có đủ an toàn không?

`authenticated()` phù hợp khi **mọi endpoint chưa có rule riêng đều dự kiến chỉ yêu cầu login**, ví dụ một intranet có thêm method-level security nghiêm ngặt. Tuy nhiên, nếu nhóm vô tình thêm `/internal/diagnostic` và quên ghi chính sách, một user thông thường đã đăng nhập có thể vào endpoint đó.

So sánh các catch-all:

| Catch-all | Người anonymous | Người đã login | Mục đích thường gặp |
|---|---|---|---|
| `anyRequest().permitAll()` | Qua bước authorization | Qua bước authorization | Ứng dụng thật sự cho phép public với tất cả URL còn lại; hiếm khi hợp lý cho API nhạy cảm |
| `anyRequest().authenticated()` | Bị yêu cầu xác thực | Qua bước HTTP authorization | Toàn bộ phần còn lại dự kiến dành cho user đã đăng nhập |
| `anyRequest().hasRole("ADMIN")` | Không đủ quyền | Chỉ ADMIN qua | Phần còn lại được thiết kế đồng nhất là khu vực ADMIN |
| `anyRequest().denyAll()` | Không được phép | Không được phép | **Allowlist / deny by default**: chỉ những route đã khai báo mới mở |

**Khuyến nghị chung cho API có nhiều độ nhạy khác nhau:** khai báo rõ endpoint public, endpoint authenticated và endpoint theo quyền; kết thúc với `anyRequest().denyAll()`. Đối với ứng dụng cố ý quy định “mọi route chưa khai báo vẫn dành cho user đăng nhập”, `authenticated()` là lựa chọn có chủ đích nhưng phải ghi nhận rủi ro mở rộng quyền khi bổ sung endpoint.

### 3.3. Quy tắc rộng có thể che quy tắc hẹp

**Cấu hình sai về mặt chính sách:**

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
```

`GET /api/admin/report` đã khớp `/api/**` ở dòng đầu, nên rule ADMIN bên dưới không được xét. Chỉ cần đăng nhập là đủ vượt **HTTP rule**. Dù service có thể còn chặn bằng method security, cấu hình này vẫn là lỗi cần sửa.

**Đúng theo thứ tự ưu tiên:**

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
```

Rule cụ thể đặt trước rule rộng. Tuy vậy, `/api/**` vẫn tự động bao phủ **mọi API mới trong namespace đó**. Nếu mục tiêu là chỉ cho phép các endpoint được duyệt, hãy chọn matcher cụ thể theo path + HTTP method và catch-all `denyAll`, thay vì dùng một wildcard quá rộng.

## 4. Reactive: `anyExchange()` trong `authorizeExchange`

Spring WebFlux sử dụng `SecurityWebFilterChain` và `ServerHttpSecurity`. Một HTTP exchange chứa request/response và ngữ cảnh reactive, còn `anyExchange()` đóng vai trò tương đương `anyRequest()` trong authorization rules.

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/admin/report")
                .hasRole("ADMIN")
            .pathMatchers(HttpMethod.GET, "/api/profile")
                .authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Các điểm cần nhớ:

- `authorizeHttpRequests` + `requestMatchers` + `anyRequest` thuộc **Servlet**; `authorizeExchange` + `pathMatchers` + `anyExchange` thuộc **WebFlux**. Không hoán đổi nguyên xi API giữa hai stack.
- Reactive authorization được tích hợp với WebFlux filter chain và bảo mật dựa trên Reactor Context; không dựa vào Servlet `HttpServletRequest`/`SecurityContextHolder` cho toàn bộ pipeline.
- Thứ tự từ rule cụ thể đến catch-all, ý nghĩa `permitAll/authenticated/denyAll` và yêu cầu authorization theo route vẫn tương tự.
- Đánh giá `anyExchange` cũng **chỉ diễn ra sau khi exchange đã được một `SecurityWebFilterChain` chọn**.
- Dùng `Mono`/`Flux` trong controller không tự quyết định security stack: cần xác định ứng dụng khởi chạy Spring MVC hay WebFlux. Khi project Boot có cả web MVC và webflux starter, Boot thường ưu tiên MVC trừ khi có cấu hình khác.

Phân biệt hai lần “match” rất hữu ích khi debug:

```text
WebFlux exchange GET /api/profile
  ├─ Có SecurityWebFilterChain khớp exchange?
  │    └─ Có → authorizeExchange
  │          ├─ GET /public/ping? Không
  │          ├─ GET /api/admin/report? Không
  │          ├─ GET /api/profile? Có → authenticated
  │          └─ anyExchange? Không cần xét nữa
  └─ Không → Không được chain này bảo vệ;
             cần xem chain khác/catch-all chain
```

## 5. Ví dụ chạy được: Servlet / Spring Boot 3.x / Java 17+

Ví dụ này cho thấy **endpoint đã được khai báo ở controller vẫn bị chặn** bởi `anyRequest().denyAll()` nếu không có authorization rule mở nó. Để chạy, tạo một project Spring Boot 3.x dùng Java 17+ từ Spring Initializr và chọn Gradle.

### 5.1. Dependencies

Trong `build.gradle` của project Spring Boot đã tạo, có khối:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đoạn này là **khối dependencies**, không phải toàn bộ `build.gradle`; giữ plugin, repository và Java toolchain do Spring Initializr cung cấp.

### 5.2. Lớp ứng dụng và security rules

Đặt `src/main/java/example/fallback/mvc/MvcFallbackApplication.java`:

```java
package example.fallback.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MvcFallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcFallbackApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "mvc public";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "mvc profile";
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "mvc admin report";
    }

    // Endpoint tồn tại thật nhưng KHÔNG có rule mở quyền.
    @GetMapping("/internal/diagnostic")
    public String diagnostic() {
        return "should not be exposed";
    }

    @Bean
    SecurityFilterChain httpSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo123")
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

`{noop}` là password encoder không hash, **chỉ dùng minh họa cục bộ**; production cần password hash, TLS và cơ chế quản lý identity phù hợp. Các user demo: `reader/demo123` có `ROLE_READER` và `admin/demo123` có `ROLE_ADMIN`.

### 5.3. Thực nghiệm từ terminal

Trong project, chạy:

```bash
./gradlew bootRun
```

Trên Windows chạy `gradlew.bat bootRun`. Để đơn giản, giả định mặc định ứng dụng dùng port 8080 và chưa có filter/route khác.

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo123 http://localhost:8080/api/profile
curl -i -u reader:demo123 http://localhost:8080/api/admin/report
curl -i -u admin:demo123 http://localhost:8080/api/admin/report
curl -i -u admin:demo123 http://localhost:8080/internal/diagnostic
```

| Request | Dự kiến | Lý do |
|---|---|---|
| Anonymous `GET /public/ping` | 200, `mvc public` | Rule `permitAll` |
| Anonymous `GET /api/profile` | 401 với HTTP Basic | Rule `authenticated` |
| Reader `GET /api/profile` | 200, `mvc profile` | Đã xác thực |
| Reader `GET /api/admin/report` | 403 | Thiếu `ROLE_ADMIN` |
| Admin `GET /api/admin/report` | 200, `mvc admin report` | Có `ROLE_ADMIN` |
| Admin `GET /internal/diagnostic` | 403 | Route có thật nhưng rơi vào `anyRequest().denyAll()` |

Ở đây cố tình test `/internal/diagnostic` là **route có controller**. Nếu chỉ gọi URL không tồn tại, response có thể bị ảnh hưởng bởi MVC routing, error dispatch hoặc trang lỗi và khó phân biệt “bị Security chặn” với “không tìm thấy handler”. Không dựa vào body mặc định hay tất cả header của `curl -i` vì chúng thay đổi theo phiên bản/cấu hình.

### 5.4. Kiểm thử hồi quy bằng MockMvc

Tạo `src/test/java/example/fallback/mvc/MvcFallbackTest.java`:

```java
package example.fallback.mvc;

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
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcFallbackTest {
    @Autowired MockMvc mvc;

    @Test
    void protectedAndFallbackRoutes() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("mvc public"));

        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/profile")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("reader", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin/report")
                .with(httpBasic("admin", "demo123")))
            .andExpect(status().isOk());

        // Âm tính quyết định: admin cũng bị chặn ở URL chưa khai báo.
        mvc.perform(get("/internal/diagnostic")
                .with(httpBasic("admin", "demo123")))
            .andExpect(status().isForbidden());
    }
}
```

Chạy `./gradlew test` hoặc `gradlew.bat test`. Test dùng Spring context và security filter thật, do đó có ý nghĩa hơn unit test chỉ gọi trực tiếp controller (bỏ qua filter chain). Test trên đây kiểm tra đường GET; với POST/PATCH/DELETE cần kiểm tra thêm CSRF, HTTP method và business authorization.

## 6. Ví dụ chạy được: Reactive / Spring WebFlux / Java 17+

Ví dụ thứ hai phải đặt trong **project Boot độc lập** với ví dụ Servlet. Nếu hai ứng dụng chạy cùng lúc, cấu hình port khác nhau. Tạo Spring Initializr project Boot 3.x, Java 17+, **chỉ chọn starter WebFlux** làm web stack.

### 6.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 6.2. Ứng dụng reactive và `anyExchange()`

Đặt `src/main/java/example/fallback/reactive/ReactiveFallbackApplication.java`:

```java
package example.fallback.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class ReactiveFallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveFallbackApplication.class, args);
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("reactive public");
    }

    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("reactive profile");
    }

    @GetMapping("/api/admin/report")
    public Mono<String> adminReport() {
        return Mono.just("reactive admin report");
    }

    @GetMapping("/internal/diagnostic")
    public Mono<String> diagnostic() {
        return Mono.just("should not be exposed");
    }

    @Bean
    SecurityWebFilterChain webfluxSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/profile")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}demo123")
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo123")
            .roles("ADMIN")
            .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }
}
```

Controller trả `Mono<String>` để minh họa kiểu return reactive; `Mono.just` ở đây không có I/O nên không dùng làm benchmark hiệu năng. Quan trọng là các HTTP rule nằm trong `SecurityWebFilterChain`, không phải Servlet `SecurityFilterChain`.

Lần lượt chạy `./gradlew bootRun` và gọi các URL tương tự mục 5.3 khi project WebFlux đang chiếm port 8080. Kết quả quyết định tương đương, body ở ba endpoint hợp lệ có tiền tố `reactive`. Đặc biệt admin truy cập `/internal/diagnostic` vẫn bị từ chối, do `anyExchange().denyAll()`.

### 6.3. Kiểm thử WebTestClient

Đặt `src/test/java/example/fallback/reactive/ReactiveFallbackTest.java`:

```java
package example.fallback.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveFallbackTest {
    @Autowired WebTestClient client;

    @Test
    void rulesAndCatchAll() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reactive public");

        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("admin", "demo123"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/internal/diagnostic")
            .headers(h -> h.setBasicAuth("admin", "demo123"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy `./gradlew test` (Windows: `gradlew.bat test`). Kiểm thử bằng HTTP client trên random port, có cơ chế authentication thật, tránh phụ thuộc vào việc giả định một method bị chặn chỉ vì cấu hình có vẻ đúng.

## 7. Nhiều security filter chain: catch-all trong chain chưa đủ

Đây là lỗ hổng kiến trúc dễ bị bỏ qua nhất.

### 7.1. Servlet: `securityMatcher` khác `requestMatchers`

Giả sử có hai chain: chain API dùng HTTP Basic, chain web dùng form login. Logic chọn:

```text
GET /api/reports
  → chain @Order(1) với securityMatcher("/api/**") → khớp
  → xét requestMatchers trong chain API
  → nếu không khớp rule cụ thể, anyRequest áp dụng cho API

GET /internal/diagnostic
  → chain @Order(1) với securityMatcher("/api/**") → không khớp
  → xét chain thứ hai nếu có
  → nếu không có chain thứ hai phù hợp, request có nguy cơ
    không được Spring Security bảo vệ.
```

Ví dụ **hai bean thay thế cho bean security đơn ở mục 5**, không được thêm đồng thời với bean đó:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/profile")
                .authenticated()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        // Không đặt securityMatcher: chain này có thể chọn
        // mọi request chưa khớp chain ưu tiên cao hơn.
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Cần import `org.springframework.core.annotation.Order` cùng các import Spring Security ở ví dụ MVC. Đoạn trên minh họa cấu trúc multi-chain và **không phải lớp Java chạy độc lập**. Trong dự án thật, hãy kiểm tra số bean, thứ tự `@Order`, chain matcher và cơ chế auth của từng chain.

Nếu viết `apiChain` chỉ với `securityMatcher("/api/**")` và `anyRequest().denyAll()`, nó chặn unknown **trong /api/**, nhưng không quyết định cho `/admin/**`, `/internal/**` hay `/actuator/**`. Chain fallback **không có `securityMatcher` giới hạn** là lớp bao phủ phần còn lại.

### 7.2. Reactive: `securityMatcher` cũng chọn chain trước `anyExchange()`

WebFlux hỗ trợ nhiều `SecurityWebFilterChain`, chọn dựa trên `securityMatcher` và precedence. Một cấu trúc minh họa tương đương:

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/profile").authenticated()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public/**").permitAll()
            .anyExchange().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Cần thêm imports `org.springframework.core.annotation.Order` và `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers` bên cạnh các import ở mục 6. Đây là **đoạn cấu hình minh họa**, thay thế chain đơn của ví dụ WebFlux; không chèn nguyên vào class đã có bean cùng mục đích.

**Mấu chốt:** `securityMatcher` là **điều kiện chọn chain**; `pathMatchers`/`requestMatchers` và catch-all là **quy tắc bên trong chain**. Nếu không có một chain nào khớp, `anyExchange` hay `anyRequest` của các chain không khớp sẽ không cứu được.

### 7.3. Khi fallback chain cần `denyAll` hay `authenticated`?

Nếu các chain cấp cao bao phủ hầu hết nghiệp vụ và phần còn lại phải được phê duyệt trước khi mở, chọn **`denyAll`**. Nếu một nhóm web riêng có nhiều trang động hợp lệ và mọi trang còn lại đều dự kiến yêu cầu login, **`authenticated`** có thể là chính sách chủ động. Dù dùng loại nào, hãy có **một chain cuối bao phủ toàn ứng dụng**, không giới hạn nhầm vào một prefix.

## 8. “Đường dẫn còn lại” không luôn đồng nghĩa với HTTP 404

Giữa HTTP authorization và request routing tồn tại hai câu hỏi:

- **Request được bảo vệ và được phép đi tiếp không?** Spring Security quyết định theo chain và rule.
- **Có controller/static resource/handler xử lý URL không?** Spring MVC hoặc WebFlux router mới quyết định việc đó.

Ví dụ `GET /does-not-exist` không có controller, nhưng catch-all `denyAll` có thể từ chối trước khi router xác định 404. Người chưa đăng nhập có thể thấy entry point 401, còn người đã đăng nhập thường nhận 403 khi bị từ chối. Status/body thực tế phụ thuộc authentication entry point, exception handling, dispatch, filter chain và framework version. Không dựa vào “URL chưa tồn tại nên chắc chắn 404” để khẳng định security đang đúng.

Nếu nghiệp vụ cần **404 cho route không tồn tại** và vẫn phải deny các route chưa cho phép, cần thiết kế rõ routing/error handling và cân nhắc nguy cơ lộ thông tin. Không mở wildcard `permitAll` chỉ để trang 404 trông đẹp hơn.

### 8.1. Servlet ERROR/FORWARD dispatch

Spring Security có thể authorize không chỉ request đầu tiên mà cả `ERROR`/`FORWARD` dispatch. Ví dụ lỗi controller khiến Spring Boot dispatch tới `/error`; nếu `anyRequest().denyAll()` chặn dispatch sau, một response 500 hoặc 404 có thể bị đổi thành 403 và khó debug.

Một lựa chọn **có điều kiện**, khi thực sự cần cho cơ chế render lỗi/forward của app:

```java
.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.ERROR,
        DispatcherType.FORWARD
    ).permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().denyAll())
```

Import `jakarta.servlet.DispatcherType`. Chỉ cho phép các dispatcher types cần thiết và test output; điều này không đồng nghĩa public tất cả `REQUEST` ban đầu, nhưng cũng phải đánh giá tác động với filter/forward custom. Đừng mở toàn `/error` theo mọi dispatcher nếu chưa hiểu kiến trúc.

### 8.2. CORS preflight, CSRF, login và static assets

- Browser có thể gửi `OPTIONS` preflight trước request thực tế. Cần cấu hình **CORS** đúng nguồn/headers/method và thứ tự tích hợp, không mặc định cho mọi `OPTIONS` đi qua chỉ vì catch-all gây lỗi. CORS không thay thế authentication/authorization.
- `POST`/`PUT`/`PATCH`/`DELETE` có thể bị kiểm tra **CSRF** khi dùng cookie/session, ngay cả khi HTTP authorization matcher có thể cho phép. Khi test từ chối, xác định nguyên nhân là rule hay CSRF. Không tắt CSRF chỉ để test dễ pass.
- Khi dùng form login, cần cho phép endpoint login và các đường hỗ trợ phù hợp. Khi có static CSS/JS, thường nên cho `permitAll` cho tài nguyên public **trong security chain**, thay vì bỏ qua toàn bộ chain bằng `web.ignoring()`, để giữ security headers.
- Actuator/health/metrics có thể dùng management context/port hoặc endpoint riêng. Đừng cho phép `/actuator/**` theo thói quen; chỉ mở mức health/public theo chính sách vận hành thực, bảo vệ metrics/config/heapdump nhạy cảm.
- WebSocket handshake, SSE, route management, forwarded path và proxy rewrite cần test riêng. Catch-all HTTP chỉ là một phần của hệ thống bảo vệ.

## 9. Làm sao thiết kế fallback mà không khóa nhầm ứng dụng?

Một chính sách `denyAll` không có lỗi logic nhưng có thể chặn legitimate features do nhóm chưa liệt kê đầy đủ: login, logout, error renderer, static assets, health probe hoặc OAuth2 callback. Không nên giải quyết bằng cách mở `anyRequest().permitAll()`, vì như vậy mọi endpoint chưa nghĩ tới cũng trở thành public.

Quy trình thực tế:

1. **Lập inventory**: danh sách URL/verb từ controller, tài nguyên tĩnh, authentication callbacks, actuator, management port, gateway routing và service khác.
2. **Phân cấp chính sách**: public chính xác; authenticated; role/authority; deny by default; object-level và method-level authorization khi cần.
3. **Sắp rule theo độ đặc hiệu**: endpoint admin trước wildcard API; path + method khi cần; các dispatcher/infra exceptions được review riêng.
4. **Chọn chain và fallback**: với nhiều chain, khai báo explicit precedence, bảo đảm có chain cuối bao phủ toàn app; mỗi chain có authorization catch-all phù hợp.
5. **Giữ private mặc định**: với URL mới chưa được phê duyệt, chọn từ chối; việc mở phải đi cùng policy và test.
6. **Kiểm tra cả happy path lẫn bị từ chối**: nếu test chỉ thấy 403 cho mọi request, app có thể đang bị khóa sai; nếu chỉ thấy 200, nguy cơ mở sai.
7. **Ghi owner của chính sách**: ai xét yêu cầu mở endpoint, ai review quyền admin và ai sở hữu regression tests.

### 9.1. Ma trận quyết định theo mục tiêu sản phẩm

| Tình huống | Chính sách dự phòng có thể phù hợp | Lưu ý |
|---|---|---|
| REST API xử lý dữ liệu nhạy cảm | `denyAll` | Chỉ mở endpoint theo allowlist được review |
| Portal nội bộ, tất cả route còn lại dành cho người đã login | `authenticated` | Phải có method/object authorization và inventory các route mới |
| Static website public độc lập | `permitAll` trong chain được chủ ý public | Không dùng chung blanket rule với API private |
| Quản trị không cho phép route ngoài danh sách | `denyAll` | Tránh wildcard `/admin/**` `authenticated` |
| Một chain chỉ xử lý `/api/**` | Catch-all trong chain + chain cuối phủ toàn hệ thống | Không nhầm `anyRequest` trong API chain thành fallback toàn ứng dụng |
| Hỗn hợp session browser + API bearer | Có thể dùng nhiều chain | Cần bảo toàn login/CSRF, session, stateless auth và fallback mỗi chain |

Không có catch-all “đúng tuyệt đối” cho mọi ứng dụng; chỉ có lựa chọn **được tuyên bố rõ, giải thích được và test đúng đường xử lý**.

## 10. Những lỗi hay gặp và cách nhận ra

| Lỗi/hiểu nhầm | Hậu quả | Cách sửa |
|---|---|---|
| Đặt `anyRequest`/`anyExchange` trước rule chi tiết | Rule sau không hoạt động hoặc cấu hình không hợp lệ | Đặt catch-all cuối |
| Đặt `/api/**` authenticated trước `/api/admin/**` ADMIN | User thường đi qua HTTP guard admin | Rule đặc hiệu đứng trước |
| Dùng `anyRequest().permitAll()` “cho tiện” | URL mới có thể public ngoài ý muốn | Chỉ `permitAll` cho route public, fallback `denyAll` |
| Dùng `anyRequest().authenticated()` và nghĩ mọi endpoint có phân quyền chặt | User đăng nhập có thể gọi endpoint nhạy cảm mới | Kiểm tra quyền hành động/dữ liệu, cân nhắc `denyAll` |
| Nghĩ `anyRequest` bảo vệ path ngoài `securityMatcher` | URL có thể rơi ngoài toàn bộ chain | Bổ sung chain fallback bao phủ toàn ứng dụng |
| Chỉ test URL không tồn tại | 404/401/403 từ router/dispatch gây hiểu nhầm | Test endpoint **tồn tại thật** nhưng chưa có authorization rule |
| Mở `/error` quá rộng | Lộ đường không dự kiến hoặc che lỗi auth | Xem dispatcher type, chỉ cho phép khi cần |
| Cho mọi `OPTIONS` public không xét CORS | Cấu hình CORS thiếu chặt chẽ | Thiết kế CORS policy, test preflight thực tế |
| Test POST nhận 403 rồi quy do fallback | Có thể là CSRF trước khi authorization | Dùng test với CSRF hợp lệ để phân lập rule |
| Trộn Servlet DSL với WebFlux DSL | Code không compile hoặc security stack sai | Xác minh stack trước khi chọn matcher/chain |
| Không xét path rewrite/context path | Rule không khớp deployment thực | Kiểm tra URL từ góc nhìn framework sau proxy |
| Chỉ bảo vệ HTTP, quên service/data | Đường gọi nội bộ hoặc ID khác vẫn truy cập sai | Kết hợp method security và object scope |

## 11. Bộ kiểm thử cần có khi thay đổi route

Khi thêm, đổi tên, di chuyển hoặc xóa endpoint, review nên chạy ma trận **route × HTTP method × anonymous/user/admin × chain × expected decision**. Ít nhất cần chứng minh:

- **Public endpoint**: `GET /public/ping` vẫn 200 không đăng nhập.
- **Authenticated endpoint**: anonymous bị chặn, reader/admin đăng nhập qua được ở `GET /api/profile`.
- **Privileged endpoint**: reader 403, admin 200 ở `GET /api/admin/report`.
- **Fallback endpoint có thật**: admin vẫn không được `GET /internal/diagnostic` nếu route chưa có rule; đây là negative test chống quên policy.
- **Unknown path**: kiểm tra hành vi mong đợi 401/403/404 theo hợp đồng và loại dispatch; không dùng unknown path thay cho fallback route test.
- **Method khác**: cùng path nhưng verb không được khai báo phải bị chặn theo chính sách, kể cả khi controller hỗ trợ verb đó.
- **Multiple chain**: request của mỗi prefix vào đúng chain; một URL không nằm trong prefix của chain trước vẫn được catch-all chain cuối xử lý.
- **Authentication mode**: HTTP Basic, form login, bearer JWT, session/cookie nếu có; không nhầm unauthorized với forbidden.
- **POST + CSRF**: có token hợp lệ thì check authorization đúng; thiếu/không hợp lệ thì bị chặn theo exploit protection.
- **Triển khai thực tế**: context path, proxy rewrite, actuator/management port, static assets, error/forward, CORS preflight.

Bổ sung test vào pipeline CI mỗi khi policy đổi. Negative tests thường phát hiện lỗi order matcher, chain scope và nhầm authenticated/authorized hiệu quả hơn việc nhìn cấu hình.

## 12. Checklist trước khi phê duyệt chính sách đường dẫn còn lại

- [ ] Xác định chính xác web stack: Spring MVC/Servlet hay WebFlux/reactive.
- [ ] Dùng đúng cặp DSL: `authorizeHttpRequests/anyRequest` hoặc `authorizeExchange/anyExchange`.
- [ ] Các matcher cụ thể được khai báo trước matcher rộng và catch-all.
- [ ] HTTP method có nằm trong matcher khi chính sách phụ thuộc method.
- [ ] Quy tắc cuối là `denyAll` / `authenticated` / `permitAll` có lý do và chủ sở hữu.
- [ ] `permitAll` chỉ áp dụng các endpoint thực sự public, không dùng wildcard vô tình mở dữ liệu.
- [ ] Với nhiều chain, `securityMatcher` và `@Order` được review; chain cuối bao phủ request còn lại.
- [ ] Không có controller/service mới nhạy cảm chỉ dựa vào `authenticated`.
- [ ] Quy tắc method/object/tenant-level authorization vẫn độc lập và đầy đủ.
- [ ] Error/forward dispatch, CORS, CSRF, static, actuator, login/logout đã được test theo thực tế.
- [ ] Có regression test cho fallback **route có thật** cùng role mạnh nhất.
- [ ] Có tài liệu ghi quyết định và cập nhật test mỗi khi thêm endpoint.

**Kết luận thực hành:** Ở Servlet, dùng `anyRequest()`; ở WebFlux, dùng `anyExchange()` để quyết định phần request/exchange còn lại **trong security filter chain đã được chọn**. Đặt chúng cuối danh sách rule; cân nhắc `denyAll()` khi muốn chủ động duyệt từng endpoint, và bảo đảm có **chain cuối không bị giới hạn matcher** để không bỏ lọt đường dẫn ngoài prefix. Một fallback tốt chỉ có giá trị khi được kiểm thử cả route hợp lệ, route có thật nhưng chưa cấp quyền, và phạm vi của tất cả chain.

## 13. Tài liệu chính thức

- [Spring Security — Authorize HTTP Requests, Servlet](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher order, `permitAll`, `denyAll`, `anyRequest`, dispatcher types.
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher` khác `requestMatchers` và fallback chain.
- [Spring Security — Authorize ServerHttpRequest, Reactive](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `anyExchange`.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): nhiều `SecurityWebFilterChain` và quy tắc chọn chain.
- [Spring Security — MockMvc Support](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): kiểm thử request với Spring Security.
- [Spring Security — WebTestClient Support](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): kiểm thử endpoint reactive và authentication.

Ví dụ dùng Spring Boot 3.x / Spring Security 6.x và Java 17+; đối chiếu API theo phiên bản dependency thực tế của ứng dụng.
