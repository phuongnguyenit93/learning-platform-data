# Chẩn đoán chuỗi bảo mật không khớp hoặc quy tắc bị che bởi thứ tự trong Spring Security WebFlux

> **Ngữ cảnh:** Spring Boot 3.x, Spring Security 6.x, Java 17+ và **WebFlux/reactive**. Bài học tập trung vào `SecurityWebFilterChain`, `ServerHttpSecurity`, `ServerWebExchangeMatcher`, `authorizeExchange` và `WebTestClient`. Tránh nhầm với cấu hình Servlet (`HttpSecurity`, `SecurityFilterChain`, `requestMatchers`, `MockMvc`).

Một lỗi bảo mật phổ biến khi chuyển từ Servlet sang WebFlux hoặc tách cấu hình API và web là: code đã khai báo rule `/api/admin/**` nhưng người dùng thường vẫn gọi được API quản trị; hoặc đã `permitAll("/api/public")` nhưng endpoint lại trả 401; hoặc endpoint vẫn hoạt động khi không đăng nhập vì **không chuỗi bảo mật nào bao phủ URL đó**. Chỉ nhìn một câu `.hasRole(...)` trong mã chưa đủ: trước hết phải biết **request đã vào chuỗi nào và rule nào thực sự được chọn**.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả hai tầng matching: chọn `SecurityWebFilterChain` rồi chọn rule trong `authorizeExchange`.
2. Phát hiện chuỗi đầu tiên “nuốt” request của chuỗi ở thứ tự thấp hơn, chuỗi có `securityMatcher` quá hẹp và khoảng trống không có catch-all chain.
3. Phát hiện quy tắc cụ thể bị che bởi quy tắc rộng hơn, ví dụ `/api/**` đứng trước `/api/admin/**`.
4. Phân biệt lỗi matching với lỗi authentication, thiếu authority, CSRF, route không tồn tại, OAuth2 redirect và method security.
5. Dùng `WebTestClient` tạo ma trận request/identity/HTTP status và đọc log để xác nhận lỗi đã được sửa.
6. Chuyển cấu hình cũ sang WebFlux mà vẫn giữ nguyên chính sách quyền dự định.

## 2. Hai tầng matching: “chuỗi nào?” và “quy tắc nào?”

### 2.1. Mô hình ra quyết định

```text
HTTP request (method, path, headers, principal...)
                       |
                       v
          Spring Security WebFilterChainProxy
                       |
            Danh sách SecurityWebFilterChain
                đã sắp xếp theo @Order
                       |
                thử securityMatcher
                       |
            +----------+-----------+
            |                      |
       Không khớp              Khớp đầu tiên
            |                      |
     thử chain kế tiếp        Chọn DUY NHẤT chain này
            |                      |
      Không có chain?          auth filters, CSRF, ...
            |                      |
  Không được bảo vệ bởi         authorizeExchange:
  các chain này               thử rule theo THỨ TỰ
                                   |
                          rule đầu tiên khớp
                                   |
                        permitAll / authenticated /
                        hasRole / hasAuthority / denyAll
                                   |
                          WebFlux handler / controller
```

Hai tầng đó độc lập:

- **Tầng 1 – chọn chuỗi:** mỗi bean `SecurityWebFilterChain` có matcher riêng (khai báo bằng `http.securityMatcher(...)`). Spring Security duyệt các chain theo thứ tự ưu tiên và dùng **chain phù hợp đầu tiên**. Một request không “chạy qua mọi chain” để cộng dồn quyền. `@Order(1)` ưu tiên hơn `@Order(2)`; `Ordered.HIGHEST_PRECEDENCE` ưu tiên hơn các giá trị số thông thường.
- **Tầng 2 – chọn rule:** bên trong chain đã chọn, `.authorizeExchange(...)` duyệt các matcher/rule theo **thứ tự khai báo**. Rule đầu tiên phù hợp quyết định yêu cầu quyền; các rule đứng sau không có cơ hội xử lý request đó.
- **Tầng 3 – cơ chế thực thi:** authentication (`httpBasic`, OAuth2 Login, Bearer JWT/opaque), CSRF, headers và filter khác thuộc chính chain đã chọn. Controller và `@PreAuthorize` có thể bổ sung kiểm tra ở tầng ứng dụng sau đó.

Ví dụ, với `GET /api/admin/report`, nếu chain web catch-all đứng trước chain API, rule `hasRole("ADMIN")` bên trong chain API **không bao giờ được xét**. Nếu chain API được chọn nhưng rule `.pathMatchers("/api/**").authenticated()` đứng trước rule `.pathMatchers("/api/admin/**").hasRole("ADMIN")`, yêu cầu ADMIN cũng bị che.

### 2.2. Khác nhau giữa ba khái niệm dễ trùng tên

| Cơ chế | Nằm ở đâu? | Quyết định điều gì? | Thay đổi nào sửa lỗi? |
| --- | --- | --- | --- |
| `@Order` của bean `SecurityWebFilterChain` | Ngoài chain | Chain nào được kiểm tra trước | Đặt chain hẹp ưu tiên trước chain catch-all |
| `ServerHttpSecurity.securityMatcher(...)` | Định nghĩa chain | URL/method nào thuộc phạm vi chain | Sửa matcher để bao phủ chính xác endpoint |
| `.authorizeExchange().pathMatchers(...)` | Bên trong chain đã chọn | Request được phép, phải đăng nhập, cần quyền hay bị từ chối | Xếp rule cụ thể trước rule tổng quát; `anyExchange` cuối |
| `SecurityWebFiltersOrder` / `.addFilterAt(...)` | Bên trong filter pipeline | Thứ tự các WebFilter như authentication, authorization | Chỉ chỉnh khi thực sự xây custom filter, **không thay thế** sửa hai tầng matching |
| `@Order` của `WebFilter` tự tạo | Lớp WebFilter chung của WebFlux | Thứ tự custom WebFilter trong pipeline | Không dùng để chữa rule/chain bị che |

Với Java/WebFlux, **đừng** bê nguyên ví dụ `HttpSecurity.securityMatcher(...)`, `authorizeHttpRequests(...)` hoặc `FilterSecurityInterceptor` của Servlet sang. Tên class và cơ chế dùng cho WebFlux khác nhau, dù tư duy first-match tương tự.

## 3. Những lỗi “khớp sai chuỗi”

### 3.1. Catch-all chain đứng trước chain dành cho API

**Sai – mảnh code minh họa:**

```java
@Bean
@Order(1)
SecurityWebFilterChain website(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/admin/**").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    Customizer.withDefaults()))
            .build();
}
```

Ở đây chain `website` không khai báo `securityMatcher`: mặc định matcher của nó phù hợp với mọi request. Nó ở `@Order(1)` nên cả `/api/admin/report` đều đi vào website. Chain API ở `@Order(2)` không xử lý URL nào đã khớp chain website; Bearer JWT có thể không được giải mã dù JWT hợp lệ.

**Đúng:** đặt chain API với `securityMatcher("/api/**")` lên thứ tự ưu tiên cao, và để website catch-all ở cuối. Chỉ đảo thứ tự **không đủ** nếu chain API còn thiếu route cần bảo vệ.

### 3.2. Matcher của chain quá hẹp

**Sai:**

```java
.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/public/**"))
.authorizeExchange(ex -> ex
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().permitAll())
```

Rule `/api/admin/**` nằm ngoài phạm vi chain `/api/public/**`, nên không bao giờ chạy. Cấu hình này có thể làm người đọc tưởng các URL admin đều được bảo vệ khi thực tế chúng rơi vào một chain khác hoặc không thuộc chain nào.

**Đúng:** `securityMatcher` bao phủ **toàn bộ phạm vi** chain, chẳng hạn `/api/**`, rồi chia quyền `/api/public` và `/api/admin/**` ở bên trong.

### 3.3. Hai chain có phạm vi chồng lấn

Ví dụ:

```text
Chain A @Order(1): /api/**
Chain B @Order(2): /api/admin/**
Chain C @Order(3): match all
```

`/api/admin/report` khớp cả A và B, nhưng **A thắng**. Chain B có vẻ rất cụ thể nhưng không thể bắt được request đó.

Có hai cách thiết kế hợp lý:

1. Nếu admin chỉ khác **quy tắc phân quyền**, để một chain `/api/**`, xếp rule admin trước rule API tổng quát.
2. Nếu admin dùng **cơ chế xác thực khác**, tách chain `/api/admin/**` với ưu tiên cao hơn `/api/**` và tài liệu hóa ngoại lệ này.

Không tạo thêm chain chỉ để “làm rõ mỗi route”; số chain tăng khiến phạm vi và ưu tiên khó kiểm soát hơn.

### 3.4. Không có fallback chain

**Sai trong ứng dụng có nhiều route:**

```java
@Bean
SecurityWebFilterChain apiOnly(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Khi tự cung cấp chain này, **không được mặc định cho rằng Spring Boot vẫn tự sinh chain bảo vệ các route khác**. Một URL `/admin` không khớp `/api/**` có thể đi tiếp tới handler mà không được các chain Spring Security này bảo vệ.

**Đúng:** thêm fallback chain cuối, có chính sách mặc định rõ (`authenticated` hoặc `denyAll` tùy thiết kế), và test một route nằm ngoài nhóm API. Giữ một vùng public chỉ khi được khai báo có chủ đích.

## 4. Những lỗi “đã chọn đúng chain nhưng rule bị che”

### 4.1. Rule rộng nằm trước rule chặt

**Sai:**

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
```

`/api/admin/report` khớp `/api/**` trước, nên yêu cầu chỉ là **đã xác thực**, không cần `ROLE_ADMIN`. `hasRole("ADMIN")` phía dưới trở thành “dead rule” đối với admin path.

**Đúng:**

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/reports/**").hasAuthority("SCOPE_reports:read")
        .anyExchange().authenticated())
```

Duyệt từ **cụ thể → tổng quát**. Với endpoint không được dự tính, lựa chọn giữa `authenticated()` và `denyAll()` phải do hợp đồng API quyết định; trong vùng API đặc biệt nhạy cảm có thể chọn `denyAll()` rồi liệt kê các route được phép trước.

### 4.2. Rule public đứng sai vị trí

**Sai:**

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/public").permitAll())
```

`permitAll()` không có tác dụng với `/api/public`, vì đã bị `/api/**` khớp trước. Ngược lại, `permitAll("/api/**")` đặt trước `hasRole("/api/admin/**")` mở quyền rộng ngoài ý muốn.

Thêm các public endpoint có chủ đích **trước** rule rộng; tránh wildcard quá mức như `/**` hoặc `/api/**` để `permitAll()` khi chỉ muốn mở `/api/health`.

### 4.3. `anyExchange()` được dùng sai chỗ

`anyExchange()` là fallback cho các request chưa khớp rule trước, vì vậy đặt cuối chuỗi khai báo. Một số biến thể builder sẽ không cho đăng ký rule tiếp sau `anyExchange()` và báo lỗi cấu hình; dù sao cũng không nên mong rule phía sau có thể “ghi đè”.

Mỗi **chain** có thể có `anyExchange()` riêng. `anyExchange()` trong chain API chỉ áp dụng **sau khi** chain API đã được chọn; nó không thể bảo vệ request chưa từng lọt vào chain API.

### 4.4. Role khác authority

- `.hasRole("ADMIN")` yêu cầu authority tên `ROLE_ADMIN` theo tiền tố mặc định của Spring Security.
- `.hasAuthority("ADMIN")` đòi chính xác authority `ADMIN`.
- `.hasAuthority("SCOPE_reports:read")` thích hợp khi Resource Server ánh xạ scope OAuth2 `reports:read` thành `SCOPE_reports:read`.

Nếu chain và rule đã match đúng nhưng kết quả là **403**, hãy kiểm tra authority hiện có và yêu cầu của rule. Đừng “sửa” bằng cách hạ rule từ `hasRole` xuống `authenticated` khi chưa xác minh policy.

## 5. Ví dụ hoàn chỉnh Java 17+: hai chain với quyền khác nhau

Ví dụ ứng dụng chạy với Spring Boot 3.3.x + Spring Security 6.x. Mục tiêu là minh họa và kiểm thử **matching** bằng HTTP Basic để tránh phụ thuộc IdP bên ngoài. HTTP Basic trong ví dụ cần HTTPS khi triển khai thật; tài khoản và `{noop}` chỉ dành cho test/lab.

### 5.1. Dependencies

Trong Gradle Groovy DSL của một project Spring Boot có plugin và dependency management phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

### 5.2. Ứng dụng và cấu hình bảo mật

Lưu file: `src/main/java/example/chainorder/SecurityChainOrderApplication.java`.

```java
package example.chainorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecurityChainOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainOrderApplication.class, args);
    }

    // Chain 1 chỉ xử lý /api/**, trước catch-all.
    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Chain 2 không có securityMatcher => fallback cho URL khác.
    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/home").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    // Chỉ minh họa. {noop} + password cố định tuyệt đối không dùng production.
    @Bean
    MapReactiveUserDetailsService testUsers() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}password")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}password")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @RestController
    static class DemoRoutes {
        @GetMapping("/api/public")
        Mono<String> publicApi() {
            return Mono.just("API public");
        }

        @GetMapping("/api/private")
        Mono<String> privateApi() {
            return Mono.just("API authenticated");
        }

        @GetMapping("/api/admin/report")
        Mono<String> adminReport() {
            return Mono.just("API admin");
        }

        @GetMapping("/home")
        Mono<String> home() {
            return Mono.just("Web public");
        }

        @GetMapping("/account")
        Mono<String> account() {
            return Mono.just("Web authenticated");
        }
    }
}
```

Giải thích cơ chế trên năm route:

| Request | Chain được chọn | Rule đầu tiên khớp | Kết quả dự kiến |
| --- | --- | --- | --- |
| `GET /api/public` không credential | `apiChain` | `/api/public → permitAll` | 200 + `API public` |
| `GET /api/private` không credential | `apiChain` | `anyExchange → authenticated` | 401 với HTTP Basic |
| `GET /api/private` với `alice` | `apiChain` | `anyExchange → authenticated` | 200 + `API authenticated` |
| `GET /api/admin/report` với `alice` | `apiChain` | `/api/admin/** → hasRole("ADMIN")` | 403 |
| `GET /api/admin/report` với `admin` | `apiChain` | `/api/admin/** → hasRole("ADMIN")` | 200 + `API admin` |
| `GET /home` không credential | `fallbackChain` | `/home → permitAll` | 200 + `Web public` |
| `GET /account` không credential | `fallbackChain` | `anyExchange → authenticated` | 401 với HTTP Basic |

**Giới hạn cố ý:** ví dụ chỉ cung cấp GET nên không cần thay đổi CSRF mặc định. Không tắt `.csrf()` toàn cục để test thứ tự chain. Nếu thêm POST/PATCH/DELETE, kiểm tra CSRF riêng hoặc chọn policy stateless phù hợp với kiến trúc thật.

### 5.3. Integration test bằng `WebTestClient`

Lưu file: `src/test/java/example/chainorder/SecurityChainOrderApplicationTest.java`.

```java
package example.chainorder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        classes = SecurityChainOrderApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityChainOrderApplicationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicApiUsesFirstChain() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("API public");
    }

    @Test
    void privateApiNeedsAuthentication() {
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth("alice", "password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("API authenticated");
    }

    @Test
    void specificAdminRuleWinsOverGenericApiRule() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "password"))
                .exchange()
                .expectStatus().isForbidden();

        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("API admin");
    }

    @Test
    void fallbackChainCoversWebUrls() {
        client.get().uri("/home")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Web public");

        client.get().uri("/account")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Chạy từ project có Gradle Wrapper:

```bash
./gradlew test --tests 'example.chainorder.SecurityChainOrderApplicationTest'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests 'example.chainorder.SecurityChainOrderApplicationTest'
```

**Kỳ vọng:** bốn test pass khi project có đủ dependencies và không có cấu hình bổ sung làm thay đổi các chain. Không có stdout Java cố định vì test so sánh HTTP status/body. Nếu bạn sao chép class vào hệ thống đã có Security beans, cần tránh bean cùng chức năng hoặc test context mang thêm filter ngoài ví dụ; điều đó có thể đổi kết quả.

**Điều test này chứng minh:** đường HTTP thật đi qua `SecurityWebFilterChain`, Authentication và Authorization, thay vì chỉ kiểm tra phương thức controller. Ví dụ tạo người dùng test trong bộ nhớ, nên không phụ thuộc IdP. Ở môi trường thực dùng JWT, hãy thay HTTP Basic ở chain phù hợp bằng OAuth2 Resource Server và kiểm tra thêm token/authority; thứ tự chain vẫn có cùng ý nghĩa.

## 6. Thử gây lỗi có kiểm soát và quan sát sự khác biệt

Chỉ thực hiện các thí nghiệm này trên bản sao lab, không áp dụng trực tiếp vào production.

### Thí nghiệm A: Rule admin bị che

Trong `apiChain`, đổi thứ tự thành:

```java
.authorizeExchange(ex -> ex
        .pathMatchers("/api/public").permitAll()
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
```

Dự đoán: `specificAdminRuleWinsOverGenericApiRule` thất bại vì user `alice` đã xác thực có thể nhận **200** ở `/api/admin/report`. Đây là **lỗi phân quyền nghiêm trọng**: test 403 là bằng chứng phát hiện được regression. Sửa bằng cách đưa `/api/admin/**` lên trước `/api/**`, hoặc bỏ rule tổng quát khi `anyExchange().authenticated()` đã đủ.

### Thí nghiệm B: Catch-all đi trước

Đưa `fallbackChain` lên `@Order(1)`, `apiChain` xuống `@Order(2)`.

Dự đoán: `/api/public` không còn `permitAll` vì fallback dùng `anyExchange().authenticated()` → trả 401; `/api/admin/report` có thể bị fallback cho phép khi đã xác thực bất kỳ user nào → `alice` nhận 200. Chính xác **một sai lầm ưu tiên chain** gây đồng thời một lỗi chặn nhầm và một lỗi mở quyền.

### Thí nghiệm C: Chain thiếu phạm vi

Đổi matcher API thành `"/api/admin/**"` nhưng giữ `"/api/public"` và `"/api/private"` trong rule API. Request `/api/public` sẽ rơi về fallback, và đòi đăng nhập dù code API vẫn có `permitAll`. Đây là lỗi phạm vi chain, không phải bug của `permitAll()`.

### Thí nghiệm D: Thiếu fallback

Xóa bean `fallbackChain`. Nếu route `/account` vẫn tồn tại, test phải kiểm tra không xảy ra trường hợp request anonymous lấy được dữ liệu nhạy cảm. Trong ứng dụng có SecurityWebFilterChain tự định nghĩa, không giả định auto-configuration sẽ thêm một catch-all hộ. Bổ sung fallback và xác minh lại bằng HTTP test.

**Nguyên tắc học:** khi gây lỗi, thay **một biến** (thứ tự chain, matcher chain hoặc thứ tự rule), chạy cùng một ma trận. Nếu đồng thời sửa cả ba, khó chứng minh nguyên nhân.

## 7. Quy trình chẩn đoán production theo từng quyết định

### Bước 1 – Chốt request cụ thể đang sai

Ghi nhận đủ thông tin **không chứa credential**:

```text
Method:        GET
External URL:  https://app.example.com/api/admin/report
Upstream path: /api/admin/report
Expected:      alice (ROLE_USER) -> 403
Observed:      200
Auth mode:     HTTP Basic (lab) / Bearer JWT (production)
```

Phân biệt path **trước và sau** reverse proxy, API Gateway, `StripPrefix`, rewrite, `server.webflux.base-path` và đường dẫn thực nhìn từ `ServerWebExchange`. Security matchers làm việc với request mà WebFlux nhận được, không tự biết chuỗi URL công khai đã bị proxy sửa thế nào.

Giữ nguyên method (`GET` khác `POST`), URL encoding, slash cuối, case, header `Authorization`, content type và trạng thái session khi tái hiện. Không in toàn bộ token trong log hỗ trợ.

### Bước 2 – Liệt kê các `SecurityWebFilterChain` và ưu tiên của chúng

Đọc cấu hình Java thực tế, lập bảng:

| Ưu tiên | Bean | `securityMatcher` | Cơ chế xác thực | Fallback |
| --- | --- | --- | --- | --- |
| 1 | `apiChain` | `/api/**` | HTTP Basic (demo), JWT tùy hệ thống | Không |
| 2 | `fallbackChain` | Mặc định match all | HTTP Basic (demo) | Có |

Bắt đầu từ chain có ưu tiên cao nhất. Với từng chain, trả lời: **matcher có khớp method/path thực tế không?** Dừng ở chain đầu tiên khớp. Đừng đọc tiếp chain sau như thể chúng có thể tăng cường rule cho request đã được nhận.

Nếu tất cả chain đều có matcher giới hạn, kiểm tra có URL lọt ra ngoài không. Những endpoint ngoài API như `/actuator/**`, `/login/**`, `/oauth2/**`, `/callback`, `/error`, `/websocket` cũng cần chính sách rõ. Đừng mở toàn bộ Actuator chỉ vì endpoint health cần public.

### Bước 3 – Bên trong chain đã chọn, lần lượt đọc từng rule

Lập bảng theo thứ tự code, ví dụ:

| Rule | Pattern | Chính sách | `/api/admin/report` |
| --- | --- | --- | --- |
| 1 | `/api/public` | `permitAll` | Không khớp |
| 2 | `/api/admin/**` | `hasRole("ADMIN")` | **Khớp; dừng** |
| 3 | `anyExchange` | `authenticated` | Không xét nữa |

Nếu rule thứ 2 bị di chuyển dưới `/api/**` thì rule rộng khớp trước; test sẽ bắt được. Đừng đặt nhiều rule trùng phạm vi nhưng kỳ vọng framework tự chọn rule “cụ thể nhất”. Với `authorizeExchange`, **thứ tự khai báo là ưu tiên**, không phải điểm số độ cụ thể tự động.

### Bước 4 – Đối chiếu identity thực tế

Kiểm tra:

- Request có được authentication filter của **chain được chọn** xử lý không? `/api/**` JWT mà vào chain web chỉ có form login có thể nhận 302 tới login, không phải 401 Bearer.
- Principal có `ROLE_ADMIN` hay chỉ có `ADMIN`, `SCOPE_admin`? `hasRole("ADMIN")` khác `hasAuthority("SCOPE_admin")`.
- JWT còn hạn, issuer/audience hợp lệ, scope mapping đúng? Token lỗi thường tạo 401 trước khi tới authorization.
- Session/cookie/OAuth2 Login hay Basic/Bearer được dùng? Tránh đoán rằng HTTP status 302/401 đã chứng minh chain matcher sai.
- Có `@PreAuthorize`, `@PostAuthorize` hoặc custom reactive authorization manager từ chối ở tầng phương thức không? Security web permit vẫn có thể bị method security từ chối.

### Bước 5 – Phân biệt 401, 403, 302, 404 và 405

| HTTP status/triệu chứng | Khả năng thường gặp | Cần kiểm tra gì? |
| --- | --- | --- |
| **401 Unauthorized** | Chưa đăng nhập, Basic/Bearer thiếu hoặc token không hợp lệ | Authentication entry point của chain, credential và Bearer token decoder |
| **403 Forbidden** | Đã xác thực nhưng thiếu quyền; hoặc CSRF làm request ghi bị từ chối | Authority, rule đã khớp, CSRF, method security |
| **302/303 tới login** | Chain form login/OAuth2 Login được chọn thay vì chain API mong đợi | Chain order, default entry point, matcher của API |
| **404 Not Found** | HandlerMapping không có route hoặc upstream rewrite sai; cũng có thể security đã cho qua | Route thực, path đến app, handler mapping, rule chain |
| **405 Method Not Allowed** | Có route nhưng không hỗ trợ method đó | Controller mapping và request method |
| **200 dù thiếu quyền** | Rule rộng `permitAll`/`authenticated` đã che `hasRole` hoặc URL nằm ngoài mọi chain | Cả hai tầng matcher, fallback chain, test anonymous/role thấp |
| **CORS preflight OPTIONS thất bại** | CORS không được xử lý trước auth hoặc path/method matcher sai | CORS cấu hình WebFlux/Spring Security, OPTIONS request, origin/headers |
| **POST bị 403 nhưng GET được** | CSRF token thiếu hoặc rule theo HTTP method khác | CSRF policy, cookie/session, rule theo method |

Không thể kết luận chắc chắn chỉ từ một status. Ví dụ HTTP 403 **không luôn đồng nghĩa** người dùng thiếu role; CSRF và method security cũng có thể trả 403. Request được Security cho qua có thể bị controller trả 404; ngược lại 404 không bảo đảm endpoint không bị phơi bày.

### Bước 6 – Bật log bảo mật ngắn hạn và kiểm tra matcher một cách có chủ đích

Cho profile test/staging:

```yaml
logging:
  level:
    org.springframework.security: TRACE
    org.springframework.web.reactive: DEBUG
```

Khởi động với cấu hình test, tái hiện **một** request và xem các log liên quan đến security filters, authentication, authorization, request path. Mức TRACE có thể rất nhiều log, và tên dòng log cụ thể thay đổi theo phiên bản. **Không** coi có/không có một chuỗi log nhất định là bằng chứng tuyệt đối chain đã được chọn.

Khi cần chắc chắn hơn, viết test đối với `ServerWebExchangeMatcher` và integration test với request thực tế. Không thêm global WebFilter ghi raw `Authorization` header, JWT, session cookie hoặc client secret để “debug nhanh”. Tắt TRACE sau khi đã có bằng chứng.

Nếu cần quan sát policy trong nội bộ, có thể đặt tên bean theo vùng (`apiChain`, `fallbackChain`), tập trung cấu hình ở ít class và dùng request correlation ID an toàn. Log chỉ ra hiện tượng; HTTP test là bằng chứng không có regression.

## 8. Matcher test: cô lập lỗi path/method khỏi phần còn lại

Trong Spring WebFlux, `ServerWebExchangeMatcher` trả về `Mono<MatchResult>`. Cần **subscribe** thì matcher mới thực thi. Có thể kiểm tra riêng pattern như sau.

Ví dụ JUnit đặt trong cùng module test (đoạn class độc lập, dùng `spring-test` và `reactor-test`):

```java
package example.chainorder;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiPathMatcherTest {

    @Test
    void adminPathFallsInsideApiChain() {
        var matcher =
                new PathPatternParserServerWebExchangeMatcher("/api/**");

        var request = MockServerHttpRequest.get("/api/admin/report");
        var exchange = MockServerWebExchange.from(request);

        StepVerifier.create(matcher.matches(exchange))
                .assertNext(result -> assertTrue(result.isMatch()))
                .verifyComplete();
    }
}
```

Run test:

```bash
./gradlew test --tests 'example.chainorder.ApiPathMatcherTest'
```

**Kết quả kỳ vọng:** PASS khi path `/api/admin/report` thuộc matcher `/api/**`. Test này chỉ xác minh **một matcher**; nó không chứng minh toàn ứng dụng đã dùng chain API đầu tiên hay policy admin chặt. Để xác nhận chuỗi và rule hoạt động thật, kết hợp với `WebTestClient` ở mục 5.3.

Nếu matcher còn phụ thuộc method, dùng constructor/matcher hỗ trợ `HttpMethod` và tạo request theo method mong đợi. Nếu bạn dùng matcher tự viết (`ServerWebExchangeMatcher`), nhớ kiểm tra tình huống match/no-match/error riêng. Một reactive matcher có thể trả `Mono` bất đồng bộ; đừng dùng `.block()` trong production WebFilter.

## 9. Ứng dụng chuyển đổi từ Servlet sang WebFlux

| Servlet stack | WebFlux stack | Sai lầm hay gặp |
| --- | --- | --- |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Dùng bean Servlet cho reactive app |
| `HttpSecurity` | `ServerHttpSecurity` | Dùng DSL cấu hình sai stack |
| `RequestMatcher` | `ServerWebExchangeMatcher` | Custom matcher cũ không có tác dụng |
| `authorizeHttpRequests().requestMatchers(...)` | `authorizeExchange().pathMatchers(...)` | Trộn DSL hoặc hiểu sai thứ tự |
| `FilterChainProxy` | `WebFilterChainProxy` | Đọc log theo servlet filters |
| `Filter` / `OncePerRequestFilter` | `WebFilter` | Custom filter Servlet không được gọi |
| `MockMvc` | `WebTestClient` | Test không đi qua reactive filter chain cần thiết |
| `SecurityContextHolder` dựa trên ThreadLocal | `ReactiveSecurityContextHolder` / Reactor Context | Lấy auth sai khi reactive thread chuyển đổi |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Method authorization bị bỏ quên hoặc không áp đúng |

Một lỗi rất hay gặp sau migration: code cũ có hai bean `SecurityFilterChain`, nhưng sau khi đổi controller sang WebFlux, ứng dụng vẫn giữ cả thư viện servlet/webmvc và security servlet. Khi đó **loại ứng dụng web thực tế** (SERVLET/REACTIVE) cần được xác định bằng dependency, Boot auto-configuration và runtime đã khởi động. Không kết luận chỉ vì có `Mono` return type là đang chạy reactive security.

Khi dùng Spring Cloud Gateway, matcher path trong downstream không nhất thiết giống URL client nếu gateway đã rewrite prefix. Kiểm tra từng hop bằng test thật; không sao chép cấu hình URL của Gateway làm securityMatcher downstream khi path đã thay đổi.

### Nên dùng một chain hay nhiều chain?

**Một chain** thường đủ khi khác biệt chủ yếu là **authorization rule**: public, user, admin, scoped API. Sắp xếp rule cụ thể trước và fallback rõ ràng.

**Nhiều chain** phù hợp khi cần khác nhau về **authentication/filter behavior**: `/api/**` chỉ Bearer JWT stateless, còn `/web/**` dùng OAuth2 Login/session; endpoint đặc biệt dùng X.509/mTLS; hoặc cần tách CSRF behavior theo loại client. Khi tách, phải có matcher riêng, ưu tiên, fallback và test âm tính cho từng vùng.

Ví dụ định hướng (mảnh DSL, không phải class độc lập):

```java
@Order(1)
@Bean
SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex
                    .pathMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_admin")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    Customizer.withDefaults()))
            .build();
}

@Order(2)
@Bean
SecurityWebFilterChain browserLogin(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/", "/about").permitAll()
                    .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
```

Đoạn này cần project có OAuth2 Resource Server + OAuth2 Client và cấu hình issuer/client registration hợp lệ. `@Order(1)` giúp `/api/**` được chọn trước fallback. Đừng suy luận rằng chỉ bật Resource Server là mọi request có Bearer token đều được bảo vệ bởi JWT filter; chain chứa `.oauth2ResourceServer(...)` phải **match** request đó.

## 10. Chiến lược kiểm thử để chống rule shadowing khi thêm endpoint

Đối với mỗi nhóm đường dẫn, lập bảng tối thiểu:

| Request | Anonymous | Đã xác thực sai quyền | Đúng quyền | Lỗi cần chặn |
| --- | --- | --- | --- | --- |
| `/api/public` | 2xx | 2xx | 2xx | Không bị rule rộng chặn |
| `/api/private` | 401 | 2xx nếu policy chỉ authenticated | 2xx | Không có auth vẫn vào được |
| `/api/admin/report` | 401 | 403 | 2xx | User thường được trả 200 |
| `/home` | 2xx | 2xx | 2xx | Fallback chặn public |
| `/account` | 401/redirect theo scheme xác thực | 2xx | 2xx | Bỏ sót chain ngoài `/api/**` |
| URL API không tồn tại | 401/403 khi chưa đủ quyền, 404 sau khi được cho qua | Tùy policy | 404 | Mặc định vô tình `permitAll` |

Không chỉ test **happy path** với ADMIN; chính test **user role thấp hơn bị từ chối** phát hiện một rule `authenticated()` đã che `hasRole("ADMIN")`. Test anonymous cũng phát hiện thiếu fallback chain.

Nếu dùng `mockJwt()`/`mockUser()`/`mockOpaqueToken()`:

- Đảm bảo `WebTestClient` đã được cấu hình với Spring Security test support khi bind vào application context: `.apply(springSecurity())`.
- Test authorization với principal giả nhanh và đáng tin, nhưng **không** chứng minh decoder JWT/IdP hay HTTP Authorization header hoạt động. Dùng thêm integration test gửi token thật nếu cần kiểm tra authentication path.
- Khi test trực tiếp app qua cổng ngẫu nhiên, dùng Basic/Bearer credentials theo đúng mechanism thực tế của chain, như mục 5.
- Các điều kiện role/authority phải được test cả giá trị sai và đúng; tránh test dùng `@WithMockUser(roles="ADMIN")` cho mọi request, vì nó che lỗi cho quyền admin quá rộng.

Thử nghiệm mutation cực kỳ có giá trị: **cố ý** đưa `/api/**.authenticated()` lên trên `/api/admin/**.hasRole("ADMIN")` rồi chạy test. Nếu test vẫn xanh, bộ test chưa kiểm tra nguy cơ shadowing; cần bổ sung case ROLE_USER → 403.

### Bất biến nên duy trì khi mở rộng cấu hình

1. Mỗi URL nhạy cảm được ít nhất một chain bao phủ; không có khoảng trống do matcher.
2. Chain có phạm vi hẹp phải đứng trước chain rộng/catch-all khi overlap.
3. Rule chặt và cụ thể đứng trước rule rộng; `anyExchange` luôn cuối.
4. Phạm vi public được khai báo tối thiểu và test anonymous.
5. Cơ chế authentication của chain đúng kiểu request (Bearer API, login web, Basic test).
6. HTTP test được chạy sau mỗi lần thêm rule/endpoint, đổi route/gateway prefix hoặc nâng cấp Spring Security.
7. Các lỗi CSRF/method security/route được chẩn đoán riêng, không sửa bằng cách mở `permitAll` hàng loạt.

## 11. Những thao tác “chữa cháy” cần tránh

- **Đổi `@Order` ngẫu nhiên** cho đến khi endpoint hết 401 nhưng không hiểu chain nào thắng; có thể làm một vùng khác mất bảo vệ.
- **Dùng `.anyExchange().permitAll()`** trong chain catch-all để “mở tạm”; khi đó các URL không khớp chain hẹp có thể công khai toàn bộ.
- **Đổi `.hasRole("ADMIN")` thành `.authenticated()`** chỉ để user thường không còn 403; lỗi có thể là role mapping hoặc rule shadowing.
- **Thêm `.pathMatchers("/**").permitAll()` phía đầu** vì health check/login bị chặn; nó che mọi rule cụ thể.
- **Tắt CSRF toàn cục** vì POST nhận 403 khi nguyên nhân là thiếu CSRF token, không phải chain order.
- **Thêm một custom `WebFilter`** để override Authorization thay vì sửa matcher; cách này làm nhiều nguồn chính sách và khó test.
- **Nhìn duy nhất một HTTP status** rồi kết luận matching; cần method/path, auth mechanism, cookie, principal và route mapping.
- **Dùng `.block()` trong reactive WebFilter** để debug matcher hoặc quyền; có thể chặn event loop.
- **Log raw Bearer token/session cookie** ở TRACE; bảo vệ thông tin người dùng trong quá trình gỡ lỗi.

## 12. Bài tập tự đánh giá

### Câu A

Cho ba chain:

```text
@Order(1) matcher /api/**
@Order(2) matcher /api/admin/**
@Order(3) catch-all
```

`GET /api/admin/export` vào chain nào?

**Đáp án:** chain `@Order(1)` vì nó khớp `/api/**` trước; `@Order(2)` bị che. Nếu admin đòi mechanism riêng, đưa matcher `/api/admin/**` lên ưu tiên cao hơn. Nếu chỉ khác authority, đặt quy tắc admin vào chain `/api/**`.

### Câu B

Trong chain API:

```java
.pathMatchers("/api/**").authenticated()
.pathMatchers("/api/admin/**").hasRole("ADMIN")
.anyExchange().denyAll()
```

User có `ROLE_USER` gọi `/api/admin/export` sẽ ra sao, giả sử route tồn tại và không bị filter khác chặn?

**Đáp án:** qua rule `authenticated()` trước, nên authorization web **cho phép**; handler có thể trả 2xx. `hasRole("ADMIN")` không được áp dụng. Đây là lỗi policy dù code nhìn có rule ADMIN.

### Câu C

Có duy nhất chain `securityMatcher("/api/**")`. Một route `/reports/private` có thể phản hồi 200 cho anonymous dù bạn đã dùng `anyExchange().authenticated()` trong chain API không?

**Đáp án:** có thể. `anyExchange()` chỉ áp dụng **trong phạm vi chain đã chọn**. Nếu không có chain nào bao phủ `/reports/private`, các security filters từ chain API không được áp dụng. Phải thêm chain fallback hay mở rộng matcher theo policy.

### Câu D

POST `/api/admin/report` với `ROLE_ADMIN` bị 403 nhưng GET thành công. Có đủ căn cứ kết luận thứ tự rule sai không?

**Đáp án:** chưa. Kiểm tra CSRF (nếu browser/session), method-specific rules, request method, CORS preflight, handler và method security. 403 có thể đến từ CSRF trước khi handler chạy. Tái hiện bằng `WebTestClient` cho cả GET và POST, phân biệt authz và CSRF.

## 13. Checklist chốt lỗi và tài liệu tham khảo

Trước khi đóng một lỗi “chain không khớp/rule bị che”, cần có bằng chứng:

- [ ] Một request cụ thể với method, path thực tế vào WebFlux và identity đã biết.
- [ ] Bảng tất cả chain theo thứ tự cùng `securityMatcher`/authentication mechanism.
- [ ] Chỉ ra chain khớp **đầu tiên** và xác nhận không có chain catch-all đặt sai trước.
- [ ] Chỉ ra rule `authorizeExchange` khớp **đầu tiên** ở chain được chọn.
- [ ] So sánh authority `ROLE_` / `SCOPE_` / tên authority thực tế với yêu cầu.
- [ ] Có test anonymous, user không đủ quyền và user đúng quyền; kiểm tra status và body, không chỉ body.
- [ ] Nếu còn 403 sau khi role đúng, đã kiểm tra CSRF và method security; nếu 404, đã kiểm tra route/path rewrite.
- [ ] Bỏ hoặc khôi phục cấu hình TRACE sau gỡ lỗi; không lưu credentials trong logs.
- [ ] Thêm regression test cho bug shadowing cụ thể trước khi triển khai.

**Tài liệu chính thức:**

- Spring Security 6.5 — [WebFlux Security: Multiple Chains Support](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html#_multiple_chains_support): `@Order`, `securityMatcher` và chỉ chọn một chain.
- Spring Security 6.5 — [Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html): rule được xét theo thứ tự.
- Spring Security 6.5 — [WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html): tích hợp Spring Security test support.
- Spring Security 6.5 — [Testing Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html): 401/403 và mock user.
- Spring Framework — [Testing WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-test.html): `WebTestClient`, reactive mock request/exchange.

**Kết quả mong đợi:** khi một endpoint trả sai 401/403/200, bạn xác định được **chain được chọn**, **rule đầu tiên được áp dụng**, và **cơ chế authentication/authorization thực tế**; sửa đúng phạm vi/thứ tự với test chứng minh endpoint nhạy cảm không bị che rule hoặc lọt ngoài mọi chain.