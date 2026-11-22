# Phân biệt `securityMatcher` chọn chuỗi và `authorizeExchange` chọn quy tắc

## 1. Bài toán: một request được xét bảo mật như thế nào?

Trong Spring Security **reactive** (Spring WebFlux), khi ứng dụng có nhiều bean `SecurityWebFilterChain`, việc xử lý request diễn ra qua **hai tầng quyết định khác nhau**:

1. **Chọn chuỗi lọc bảo mật**: `securityMatcher(...)` quyết định một `SecurityWebFilterChain` có áp dụng cho request đó hay không. Các chain được xét theo thứ tự ưu tiên; Spring Security sử dụng **chain khớp đầu tiên**.
2. **Chọn quy tắc phân quyền bên trong chain đã chọn**: `authorizeExchange(...)` quyết định request nào được `permitAll()`, request nào cần `authenticated()`, `hasRole(...)`, `hasAuthority(...)` hoặc phải `denyAll()`.

Đây là hai cấp cấu hình, mặc dù cả hai đều có thể kiểm tra đường dẫn URL. Nếu nhầm chúng, ứng dụng có thể áp dụng nhầm cơ chế đăng nhập, vô tình bỏ qua kiểm tra quyền ADMIN, hoặc bỏ trống một nhóm endpoint không được Spring Security bảo vệ.

Mục tiêu bài học:
- Giải thích chính xác phạm vi, thứ tự đánh giá và trách nhiệm của hai API.
- Theo dõi cách một request đi qua nhiều `SecurityWebFilterChain` và nhiều luật `authorizeExchange`.
- Biết khi nào cần một chain, khi nào cần nhiều chain và tại sao catch-all chain thường cần thiết.
- Chạy thử ví dụ Java 17+ có endpoint public, user, admin ở cả nhánh API và nhánh web.
- Viết kiểm thử xác nhận HTTP 200, 401, 403 và phát hiện các cấu hình sai phổ biến.

## 2. Hai tầng matching: chain trước, rule sau

Sơ đồ logic:

~~~text
HTTP GET /api/admin/report
       |
       v
WebFilterChainProxy của Spring Security reactive
       |
       v
Xét SecurityWebFilterChain theo @Order:
  chain API: securityMatcher("/api/**")  => MATCH
  chain Web: mặc định any exchange       => không cần xét tiếp
       |
       v
Chọn đúng chain API
       |
       v
Các security filter đã cấu hình trong chain API
       |
       v
authorizeExchange:
  "/api/public/**" -> permitAll()       => không khớp
  "/api/admin/**"  -> hasRole("ADMIN")  => KHỚP
  anyExchange()    -> authenticated()   => không xét tiếp
       |
       v
Authentication + authorization quyết định kết quả
       |
       +-- người dùng có ROLE_ADMIN -> được đi tiếp tới handler
       +-- người dùng đã xác thực, thiếu quyền -> từ chối (thường 403)
       +-- chưa xác thực -> yêu cầu xác thực (thường 401 với HTTP Basic)
~~~

**Cần ghi nhớ:** `securityMatcher` không có phương thức `permitAll()` hay `hasRole()` vì nó không trực tiếp quyết định quyền. Ngược lại, `pathMatchers` bên trong `authorizeExchange` không chuyển sang chain khác; nó chỉ chọn một quy tắc **trong chain đã được chọn**.

### 2.1. `securityMatcher` — phạm vi áp dụng cho toàn bộ chain

Trong DSL reactive `ServerHttpSecurity`:

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/api/**")
);
~~~

Matcher thuộc kiểu `ServerWebExchangeMatcher`. Tại runtime, nó xét thông tin request và trả một kết quả khớp hoặc không khớp theo hợp đồng reactive. `PathPatternParserServerWebExchangeMatcher` là matcher theo mẫu đường dẫn; ngoài path còn có thể thiết kế matcher theo phương thức HTTP, header hoặc các điều kiện riêng khi cần.

Ở ví dụ trên:
- `/api/orders` khớp.
- `/api/public/info` khớp.
- `/api/admin/report` khớp.
- `/status` không khớp.

Một chain không có lời gọi `securityMatcher(...)` tường minh thường sử dụng matcher mặc định khớp mọi exchange. Đây là cơ chế thuận tiện cho **chain cuối bao phủ phần còn lại**.

### 2.2. `authorizeExchange` — quyền cần có trong chain được chọn

~~~java
http.authorizeExchange(exchange -> exchange
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
);
~~~

Đoạn này là **tập luật phân quyền HTTP**. Spring Security xét các luật theo thứ tự đã khai báo và áp dụng luật đầu tiên phù hợp. `anyExchange()` là quy tắc cuối cho những request chưa được luật trước bắt trúng.

- `permitAll()`: luật phân quyền cho phép truy cập mà không yêu cầu danh tính đăng nhập. Các filter khác của chain vẫn có thể chạy.
- `authenticated()`: yêu cầu danh tính đã được xác thực.
- `hasRole("ADMIN")`: theo quy ước mặc định, yêu cầu authority `ROLE_ADMIN`.
- `denyAll()`: từ chối quyền truy cập.
- `pathMatchers(...)`: chọn request theo path hoặc kết hợp HTTP method; không tạo một `SecurityWebFilterChain` mới.

Dấu hiệu nhận biết: `securityMatcher` là một điều kiện **ở cấp chain**; `pathMatchers` nằm trong DSL `authorizeExchange` là một điều kiện **ở cấp luật**.

## 3. So sánh trực tiếp

| Đặc điểm | `securityMatcher(...)` | `authorizeExchange(...)` |
| --- | --- | --- |
| Vai trò | Xác định chain bảo mật có áp dụng cho request hay không | Xác định yêu cầu phân quyền đối với request đã vào chain |
| Vị trí | Trên `ServerHttpSecurity` khi tạo từng `SecurityWebFilterChain` | Trên `ServerHttpSecurity` để đăng ký các quy tắc |
| Điều kiện | `ServerWebExchangeMatcher`, ví dụ `/api/**` | `pathMatchers`, `matchers`, `anyExchange` |
| Kết quả | Khớp/không khớp → chọn chain đầu tiên khớp | Quy tắc `permitAll`, `authenticated`, `hasRole`, ... |
| Thứ tự | Giữa các chain: `@Order` (giá trị nhỏ ưu tiên cao) | Giữa các rule: thứ tự khai báo trong `authorizeExchange` |
| Khi không khớp | Thử chain khác, nếu không có chain nào khớp thì không có web security chain xử lý request | Chuyển sang rule tiếp theo trong **cùng chain** |
| Lỗi hay gặp | Chain tổng quát đứng trước chain chuyên biệt, hoặc không có catch-all | Rule quá rộng che rule chặt chẽ, hoặc thiếu quy tắc cuối |

Đừng nhầm hai loại ưu tiên:
- `@Order(1)` và `@Order(2)` xác định **chain nào được xét trước**.
- Thứ tự `pathMatchers` trong `authorizeExchange` xác định **luật nào được xét trước trong chain đang dùng**.
- Thứ tự `WebFilter` bên trong chain là cơ chế khác; không tự ý đồng nhất nó với hai loại ưu tiên trên.

## 4. Khi nào dùng một chain, khi nào dùng nhiều chain?

### 4.1. Một chain thường đủ khi chỉ khác nhau về quyền truy cập

Nếu mọi endpoint dùng cùng cơ chế xác thực và các filter tương tự nhau, hãy mô tả các đường dẫn ngay trong một `authorizeExchange`:

~~~java
@Bean
SecurityWebFilterChain singleChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **đoạn cấu hình minh họa**, cần những import và bean xác thực tương ứng. Nó dùng một chain mặc định khớp mọi request; `pathMatchers` chỉ quyết định quyền. Không cần tạo ba `SecurityWebFilterChain` riêng cho ba mức quyền `public`, `admin` và `authenticated`.

### 4.2. Nhiều chain hữu ích khi các nhóm request khác cả cơ chế bảo mật

Ví dụ:
- `/api/**` có thể dùng OAuth2 Resource Server để kiểm tra Bearer JWT.
- Trang trình duyệt có thể dùng form login, cookie/session và cơ chế CSRF phù hợp.
- Một nhóm endpoint vận hành có thể dùng cấu hình xác thực đặc biệt.

Mỗi chain có thể có matcher, cơ chế xác thực, rule phân quyền và chính sách session/CSRF phù hợp. Hai chain không nên khác nhau chỉ vì mỗi chain có một endpoint cần `permitAll`; rule đơn giản giải quyết việc đó tốt hơn.

**Luôn nghĩ tới đường dẫn còn lại:** nếu chỉ khai báo một chain với `securityMatcher("/api/**")`, các request ngoài `/api/**` sẽ không khớp chain này. Nếu không có chain khác bắt chúng, chúng **không được bảo vệ bằng Spring Security web filter chain**. Điều này đặc biệt nguy hiểm với endpoint nội bộ vô tình công khai. Thêm chain catch-all cuối hoặc cố ý kiểm soát phạm vi bằng các biện pháp bảo vệ khác.

## 5. Ví dụ đầy đủ Java 17+ với hai chain

Ví dụ dùng Spring Boot 3.3.13, Spring Security WebFlux, Java 17+ và Gradle 8.x. Mọi endpoint đều là GET để tập trung vào hai tầng matcher. Hai chain cùng dùng **HTTP Basic** để dễ kiểm tra; trong hệ thống thực tế, API và web hoàn toàn có thể dùng cơ chế xác thực khác nhau.

### 5.1. Cấu trúc dự án

~~~text
reactive-chain-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── ReactiveChainDemoApplication.java
    │   ├── DemoController.java
    │   └── SecurityConfig.java
    └── test/java/demo/
        └── SecurityRoutingTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-chain-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/ReactiveChainDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveChainDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveChainDemoApplication.class, args);
    }
}
~~~

### 5.2. Các endpoint để quan sát lựa chọn chain và rule

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/api/public/info")
    Mono<String> publicApi() {
        return Mono.just("public-api");
    }

    @GetMapping("/api/orders")
    Mono<String> orders() {
        return Mono.just("orders");
    }

    @GetMapping("/api/admin/report")
    Mono<String> adminReport() {
        return Mono.just("admin-report");
    }

    @GetMapping("/status")
    Mono<String> status() {
        return Mono.just("healthy");
    }

    @GetMapping("/account")
    Mono<String> account() {
        return Mono.just("account");
    }
}
~~~

### 5.3. Cấu hình hai `SecurityWebFilterChain`

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // TẦNG 1: chain này chỉ được chọn cho /api/**.
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            // TẦNG 2: quyền bên trong chain API.
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            // Không khai báo securityMatcher:
            // chain cuối mặc định khớp mọi request còn lại.
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/status").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers(
            PasswordEncoder passwordEncoder) {
        UserDetails reader = User.withUsername("reader")
            .password(passwordEncoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(passwordEncoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Giải thích các lựa chọn:**
1. `@EnableWebFluxSecurity` bật cấu hình Spring Security reactive; trong Spring Boot có starter Security phù hợp, hạ tầng này thường cũng được tự cấu hình. Annotation không quyết định `/status` có public hay không.
2. `@Order(1)` khiến `apiSecurity` được xét trước `webSecurity` có `@Order(2)`. Con số nhỏ hơn có ưu tiên cao hơn.
3. `securityMatcher("/api/**")` ở chain API chỉ áp dụng với đường dẫn API. Điều kiện đó **không** tự cho phép truy cập API; việc cấp quyền nằm ở `authorizeExchange`.
4. `webSecurity` không ghi `securityMatcher`: mặc định khớp mọi request; nó trở thành chain cuối phục vụ `/status`, `/account` và các đường dẫn chưa khớp chain chuyên biệt.
5. `pathMatchers("/api/public/**").permitAll()` áp dụng cho endpoint API công khai, còn `pathMatchers("/api/admin/**").hasRole("ADMIN")` kiểm tra quyền ADMIN; `anyExchange().authenticated()` bảo vệ các endpoint API còn lại, ví dụ `/api/orders`.
6. Hai chain cùng bật HTTP Basic và tắt form login **chỉ để kết quả HTTP dễ quan sát trong demo**. `PasswordEncoder` sử dụng BCrypt; user trong memory là tài khoản demo, không phải nguồn danh tính cho production.
7. Không vô hiệu hóa CSRF ở đây; tất cả endpoint demo là GET. Với API ghi dữ liệu, phải phân tích cơ chế cookie/session, token và CSRF của từng chain trước khi thay đổi chính sách.

### 5.4. Tại sao thiếu `securityMatcher` ở chain cuối lại hợp lý?

Vì mọi request đi qua việc lựa chọn chain **theo thứ tự**:
- Request `/api/orders` khớp chain `apiSecurity` đầu tiên, nên dừng tìm chain; `webSecurity` không được áp dụng cho request đó.
- Request `/status` không khớp chain API, nên tiếp tục xét chain `webSecurity` và được kiểm tra `permitAll` tại đây.
- Request `/account` cũng vào `webSecurity` nhưng không khớp `/status`, nên áp dụng `anyExchange().authenticated()`.

Nếu đảo thứ tự `@Order` để chain catch-all được xét trước, mọi request có thể bị chain catch-all bắt trước. Khi đó `/api/public/info` có thể bị yêu cầu đăng nhập và `/api/admin/report` có thể chỉ đòi `authenticated()` thay vì `ROLE_ADMIN` — tức là sai chính sách. Không thể trông chờ Spring Security xét thêm chain API sau khi chain khác đã khớp.

## 6. Truy vết từng request: chọn chain rồi chọn rule

| Request | Chain được chọn | Rule được chọn | Kết quả với điều kiện nêu trong bảng |
| --- | --- | --- | --- |
| GET `/api/public/info`, không đăng nhập | API (khớp `/api/**`) | `/api/public/**` → `permitAll` | 200 |
| GET `/api/orders`, không đăng nhập | API | `anyExchange().authenticated()` | 401 |
| GET `/api/orders`, Basic `reader` đúng mật khẩu | API | `anyExchange().authenticated()` | 200 |
| GET `/api/admin/report`, Basic `reader` đúng mật khẩu | API | `/api/admin/**` → `hasRole("ADMIN")` | 403 |
| GET `/api/admin/report`, Basic `admin` đúng mật khẩu | API | `/api/admin/**` → `hasRole("ADMIN")` | 200 |
| GET `/status`, không đăng nhập | Web (catch-all) | `/status` → `permitAll` | 200 |
| GET `/account`, không đăng nhập | Web (catch-all) | `anyExchange().authenticated()` | 401 |
| GET `/account`, Basic `reader` đúng mật khẩu | Web (catch-all) | `anyExchange().authenticated()` | 200 |

Các mã HTTP trên là kết quả kỳ vọng của **cấu hình demo** với HTTP Basic, form login tắt, endpoint GET và không có security filter tùy biến khác. Trong ứng dụng dùng OAuth2, form login, CORS hoặc exception handling riêng, cách trả 401/403/redirect có thể khác. `securityMatcher` và `authorizeExchange` không tự phát mã HTTP; các filter xác thực, phân quyền và exception handling thực thi quyết định đó.

Một khác biệt thực hành: `permitAll` cho phép về mặt **phân quyền** nhưng không có nghĩa mọi filter trong chain đều bị tắt. Ví dụ request gửi header Basic với mật khẩu sai vào endpoint public vẫn có thể bị filter xác thực xử lý và trả lỗi. Đừng dùng `permitAll` như một cách loại bỏ toàn bộ security filter.

## 7. Chạy thử với Gradle và curl

Từ thư mục `reactive-chain-demo`, yêu cầu JDK 17+, Gradle 8.x và mạng để tải dependency lần đầu:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, chạy `./gradlew bootRun` trên Unix/macOS hoặc `gradlew.bat bootRun` trên Windows.

Giữ server ở `http://localhost:8080`. Các lệnh dưới đây in ra **chỉ HTTP status code** trong shell kiểu bash/Git Bash:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/public/info
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/orders
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/orders
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin/report
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin/report
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/status
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/account
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/account
~~~

Stdout kỳ vọng, theo thứ tự:

~~~text
200
401
200
403
200
200
401
200
~~~

Lưu ý: trên Windows PowerShell, gọi `curl.exe` để dùng chương trình curl thay vì alias; có thể cần thay `/dev/null` bằng `NUL`. Không dùng các thông tin đăng nhập demo trong môi trường thật, và với HTTP Basic ngoài localhost bắt buộc dùng HTTPS.

## 8. Kiểm thử tự động với `WebTestClient`

Tạo `src/test/java/demo/SecurityRoutingTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class SecurityRoutingTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicApiUsesApiChainButNeedsNoLogin() {
        client.get().uri("/api/public/info")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-api");
    }

    @Test
    void apiOrdersRequireAuthentication() {
        client.get().uri("/api/orders")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void apiAdminRequiresAdminRole() {
        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-report");
    }

    @Test
    void webFallbackHasItsOwnAuthorizationRules() {
        client.get().uri("/status")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/account")
            .exchange()
            .expectStatus().isUnauthorized();

        client.get().uri("/account")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("account");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc `./gradlew test` / `gradlew.bat test` nếu dự án có wrapper. Kỳ vọng là cả bốn phương thức test đều PASS và Gradle trả exit code 0. Không khẳng định một chuỗi log Gradle cố định vì kết quả hiển thị phụ thuộc môi trường.

Kiểm thử trên quan trọng vì nó kiểm tra **hậu quả quan sát được** của cả hai tầng:
- `/api/public/info`: API chain được chọn đúng và luật public được áp dụng.
- `/api/admin/report`: rule phân quyền ADMIN thực sự được áp dụng trong API chain.
- `/status`, `/account`: các request ngoài API được xử lý bởi chain cuối.
- Nếu nhầm thứ tự chain, ít nhất một kỳ vọng sẽ fail, giúp phát hiện hồi quy quyền truy cập.

Các test endpoint chỉ đo kết quả từ bên ngoài; trong trường hợp phức tạp, có thể kiểm tra thêm điều kiện match, bean chains và security logs để giải thích vì sao kết quả thay đổi.

## 9. Bốn tình huống sai thường gặp

### 9.1. Dùng `securityMatcher` để “mở” endpoint public

Ví dụ sai về tư duy:

~~~java
http.securityMatcher(
    new PathPatternParserServerWebExchangeMatcher("/public/**"))
    .authorizeExchange(ex -> ex.anyExchange().permitAll());
~~~

Chuỗi này chỉ áp dụng cho `/public/**`; nó **không đặt luật bảo vệ** các URL khác. Nếu đây là chain duy nhất, một endpoint `/private` có thể nằm ngoài Spring Security web filter chain. Để một endpoint public nhưng phần còn lại được bảo vệ, hãy dùng chain catch-all:

~~~java
http.authorizeExchange(ex -> ex
    .pathMatchers("/public/**").permitAll()
    .anyExchange().authenticated()
);
~~~

Hai khối code trên là **minh họa độc lập** về ý nghĩa matcher; không thêm chúng đồng thời với cấu hình hoàn chỉnh ở mục 5.

### 9.2. Chain tổng quát được ưu tiên quá sớm

Giả sử chain catch-all có `@Order(1)`, chain API có `@Order(2)`. Vì catch-all match mọi exchange, API chain không được chọn. Những luật trong chain API như `hasRole("ADMIN")` trở nên vô hiệu đối với các request bị chain catch-all bắt trước.

**Sửa:** đặt chain chuyên biệt ở mức ưu tiên cao hơn, và chain catch-all cuối:

~~~java
@Order(1) // /api/** chuyên biệt
@Order(2) // mọi URL còn lại
~~~

Đây chỉ là chú thích biểu diễn thứ tự; bản thân hai annotation cần gắn đúng vào các phương thức `@Bean` như ví dụ hoàn chỉnh.

### 9.3. Rule rộng nằm trước rule chặt

Trong một `authorizeExchange`, đoạn dưới có lỗ hổng phân quyền:

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

Vì `/api/admin/**` cũng thuộc `/api/**`, request admin đã khớp luật `permitAll` trước đó. Rule ADMIN phía dưới sẽ không được dùng cho trường hợp ấy. Cần đưa pattern chặt lên trước hoặc giới hạn pattern public thật cụ thể:

~~~java
.authorizeExchange(ex -> ex
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated()
)
~~~

**Sửa `@Order` không giúp được** lỗi này vì sai phạm ở thứ tự **rule trong một chain**, không phải thứ tự **giữa các chain**.

### 9.4. Quên catch-all chain hoặc catch-all rule

Hai lỗi khác nhau nhưng dễ bị đánh đồng:
- **Thiếu catch-all chain:** một số request không khớp bất kỳ `SecurityWebFilterChain` nào và có thể vượt qua các web security filter.
- **Thiếu catch-all rule trong chain đã chọn:** một số request có thể không được điều khiển bởi luật phân quyền tường minh mà bạn tưởng đã bao phủ. Hành vi cuối còn phụ thuộc cấu hình framework; không dựa vào một fallback “ngầm hiểu” để bảo vệ tài nguyên.

Cách xây dựng an toàn cho bài học là **chain cuối khớp mọi URL** và **mỗi chain có `anyExchange().authenticated()` hoặc `denyAll()` thích hợp**, sau các ngoại lệ được định nghĩa rõ.

## 10. Các lưu ý nâng cao trong Spring Security reactive

### 10.1. `ServerWebExchangeMatcher` và API tương ứng

`securityMatcher` nhận một `ServerWebExchangeMatcher` (ví dụ `PathPatternParserServerWebExchangeMatcher`). Đây là API WebFlux; đừng nhầm với `RequestMatcher` của Servlet. Tương tự, WebFlux cấu hình với `ServerHttpSecurity` và trả `SecurityWebFilterChain`; Spring MVC/Servlet dùng `HttpSecurity` và `SecurityFilterChain`.

Khi cần match theo HTTP method hoặc điều kiện khác, chọn matcher tương ứng và kiểm thử chính xác method/path. Đừng dùng một pattern quá rộng để bù cho việc chưa rõ phạm vi.

### 10.2. Authentication filter và authorization rule không phải một

`authorizeExchange` không tạo user, không xác minh mật khẩu và không giải mã JWT. Nó xác định **điều kiện phân quyền**. Các cơ chế như HTTP Basic, form login hoặc OAuth2 Resource Server thực hiện **xác thực**, rồi authorization dùng danh tính và authorities đã có.

Có thể có `securityMatcher("/api/**")` trên chain với `oauth2ResourceServer(...)`, trong khi chain Web có `formLogin(...)`. Khi đó chain đã chọn cũng quyết định **bộ authentication filters** được áp dụng. Đây là lý do quan trọng để dùng nhiều chain khi ứng dụng có nhiều kiểu client.

Trong demo, hai chain cùng dùng Basic để giữ cách kiểm thử đơn giản; việc khác biệt chain vẫn có ý nghĩa vì **quy tắc phân quyền khác nhau**.

### 10.3. CSRF, HTTP method và CORS

`permitAll` không đồng nghĩa với tắt CSRF. Một POST/PUT/DELETE dùng session hoặc cookie có thể bị từ chối 403 do thiếu CSRF token dù rule authorization cho phép. Các test GET của ví dụ không chứng minh POST hoạt động. Cấu hình CSRF, CORS và session cần xem xét theo nhóm endpoint và cơ chế xác thực, đặc biệt khi API stateless và website session-based dùng các chain khác nhau.

Nếu có proxy thay đổi path, context path hoặc URL rewrite, hãy kiểm tra giá trị path thực sự mà matcher nhận để tránh định nghĩa pattern không như mong muốn.

### 10.4. Phân quyền phương thức là một lớp bổ sung

`@PreAuthorize` được kích hoạt trong WebFlux bằng cấu hình reactive method security thích hợp (ví dụ `@EnableReactiveMethodSecurity`). Cơ chế này không thay thế `securityMatcher` hay `authorizeExchange`: nó bảo vệ lời gọi phương thức khi được thực thi. Endpoint nhạy cảm nên có cả kiểm thử HTTP và kiểm thử authorization nơi logic nghiệp vụ cần được bảo vệ.

### 10.5. Log và giám sát quyết định match

Khi một endpoint bất ngờ trả 200/401/403, hãy lần lượt kiểm tra:
1. Ứng dụng thực sự chạy reactive WebFlux, không vô tình chạy Servlet do dependency.
2. Những bean `SecurityWebFilterChain` nào được đăng ký, và `@Order` của chúng.
3. Matcher của chain nào khớp request **trước tiên**.
4. Trong chain được chọn, luật `authorizeExchange` nào khớp **trước tiên**.
5. Danh tính/authorities và các filter khác như CSRF, HTTP Basic, CORS/exception handling có ảnh hưởng gì.

Có thể bật log Spring Security tạm thời để xem quá trình xử lý, nhưng không đưa Authorization header, password, JWT hoặc session secret vào log có thể bị chia sẻ. Trong production, chỉ dùng mức quan sát phù hợp với bảo mật và quyền riêng tư.

## 11. Checklist thực hành

- [ ] Có giải thích rõ lý do tạo **một hay nhiều** `SecurityWebFilterChain`.
- [ ] Các chain chuyên biệt có `securityMatcher` đúng phạm vi.
- [ ] Thứ tự `@Order` đặt các chain chuyên biệt **trước** catch-all.
- [ ] Có chain cuối bao phủ tất cả request cần bảo vệ.
- [ ] Bên trong từng chain, rule hẹp đứng trước rule rộng.
- [ ] Quy tắc cuối `anyExchange().authenticated()`/`denyAll()` rõ ràng.
- [ ] Endpoint public dùng `permitAll` theo đúng yêu cầu; không đặt sai ở tầng chain.
- [ ] Test đủ anonymous, user thường, admin, URL API và URL ngoài API.
- [ ] Test thêm các HTTP method ghi dữ liệu cùng CSRF khi ứng dụng có chúng.
- [ ] Không dùng mật khẩu demo hoặc cơ chế Basic không mã hóa đường truyền trong production.

## 12. Câu hỏi tự kiểm tra

1. **`securityMatcher("/api/**")` có nghĩa là mọi API đều được phép truy cập không?** Không. Nó chỉ quyết định chain nào áp dụng; `authorizeExchange` mới đặt luật quyền.
2. **Nếu hai chain cùng khớp request, cả hai có chạy không?** Không theo cơ chế chọn chain Spring Security WebFlux: chọn chain khớp đầu tiên theo thứ tự.
3. **`@Order(1)` và `pathMatchers` khác nhau ở đâu?** `@Order` xếp thứ tự *giữa các chain*; `pathMatchers` xếp luật trong *chain đã chọn* thông qua thứ tự khai báo.
4. **`/api/admin/report` thuộc chain API nhưng chỉ có ROLE_USER: vì sao 403?** Vì rule `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`.
5. **Đưa chain catch-all lên trước API chain sẽ gây gì?** API chain có thể không bao giờ được xét và các luật API bị bỏ qua.
6. **Đặt `pathMatchers("/api/**").permitAll()` trước rule ADMIN có an toàn không?** Không, pattern quá rộng bắt luôn đường dẫn admin.
7. **Nếu chỉ khai báo chain cho `/api/**` mà có `/account` thì sao?** Nếu không còn chain khác khớp, `/account` không được bảo vệ bởi các Spring Security web filter chain ấy.
8. **`permitAll` có ngừng tất cả security filter và tắt CSRF không?** Không; nó chỉ là quyết định phân quyền.
9. **Có cần nhiều chain chỉ để `/public` không đăng nhập và `/private` có đăng nhập?** Thường không. Một chain và `authorizeExchange` là đủ.
10. **Trong WebFlux dùng `HttpSecurity` hay `ServerHttpSecurity`?** Dùng `ServerHttpSecurity` và `SecurityWebFilterChain`.

## 13. Tài liệu chính thức

- Spring Security — WebFlux Security, mục *Multiple Chains Support*: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Security — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/authorize-http-requests.html
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 — Gradle plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html

**Quy tắc ghi nhớ:** `securityMatcher` trả lời “**chain nào quản lý request này?**”; `authorizeExchange` trả lời “**trong chain ấy, request này cần quyền gì?**”. Sau khi trả lời hai câu hỏi, mới phân tích cơ chế xác thực, authorities, CSRF và cách trả lỗi HTTP.
