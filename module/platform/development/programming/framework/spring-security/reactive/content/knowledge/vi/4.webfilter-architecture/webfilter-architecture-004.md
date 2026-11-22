# SecurityWebFiltersOrder và thứ tự các giai đoạn xử lý trong Spring Security WebFlux

## Mục tiêu bài học

Sau bài học này, bạn có thể:

1. Giải thích `SecurityWebFiltersOrder` điều khiển vị trí các `WebFilter` **bên trong** `SecurityWebFilterChain` như thế nào.
2. Đọc thứ tự các giai đoạn chính: header/HTTPS, CORS/CSRF, Reactor Context, authentication, anonymous, exception translation, authorization và phần xử lý HTTP.
3. Phân biệt **thứ tự chọn chain** với **thứ tự filter trong chain**, cũng như hướng đi vào request với hướng hoàn tất response.
4. Dùng `ServerHttpSecurity.addFilterBefore(...)`, `addFilterAfter(...)` và `addFilterAt(...)` đúng mục đích khi thêm custom WebFilter.
5. Kiểm chứng HTTP 200, 401, 403 và quan sát các giai đoạn bằng code Java/Spring WebFlux mà không vô tình bỏ qua cơ chế bảo mật.

> Phạm vi: **Spring Security dành cho WebFlux (reactive)**. Ở Spring MVC/Servlet, API tương ứng là `SecurityFilterChain`, `HttpSecurity` và `jakarta.servlet.Filter`; không dùng các API Servlet để suy luận trực tiếp thứ tự của `SecurityWebFilterChain`.

## 1. Ba lớp "thứ tự" rất dễ bị nhầm

Khi một HTTP request đến ứng dụng WebFlux, thứ tự được quyết định qua các lớp khác nhau:

```text
Client
  |
  v
WebFlux WebFilter chain (các filter của toàn ứng dụng)
  |
  v
Spring Security WebFilterChainProxy
  |
  +--> Chọn MỘT SecurityWebFilterChain phù hợp với request
  |    (thứ tự ưu tiên giữa các chain: @Order và securityMatcher)
  |
  +--> Chạy các WebFilter THỰC SỰ có trong chain đã chọn
  |    (vị trí tương đối: SecurityWebFiltersOrder)
  |
  v
WebHandler / RouterFunction / Controller
  |
  v
HTTP response được hoàn tất qua các lớp filter
```

- **Thứ tự filter toàn ứng dụng:** các `WebFilter` đăng ký với WebFlux có thể được sắp bởi `@Order` hoặc cơ chế Spring ordering. Đây là lớp bên ngoài Security chain.
- **Thứ tự chọn `SecurityWebFilterChain`:** nếu định nghĩa nhiều bean chain, `@Order` và `securityMatcher(...)` xác định chain nào được thử trước. Spring Security chọn **một chain phù hợp** cho request.
- **Thứ tự filter nội bộ:** `SecurityWebFiltersOrder` là enum mô tả các mốc vị trí chuẩn, được `ServerHttpSecurity` dùng khi lắp ráp filter trong chain đã chọn.

Vì vậy, `@Order(1)` trên một bean `SecurityWebFilterChain` **không có nghĩa** filter authentication ở vị trí số 1. Tương tự, `SecurityWebFiltersOrder.AUTHORIZATION` **không phải** một cấu hình phân quyền; nó là vị trí dành cho giai đoạn kiểm tra quyền.

### SecurityWebFiltersOrder là gì?

`org.springframework.security.config.web.server.SecurityWebFiltersOrder` là enum cung cấp các vị trí mặc định cho các WebFlux security filter. Mỗi giá trị có `getOrder()`; khi build `ServerHttpSecurity`, các filter được sắp theo giá trị order tương ứng.

Cần hiểu đúng:

- Enum nêu **mốc chèn**. Nó **không** có nghĩa mọi mốc đều chứa filter ở mọi request hoặc mọi cấu hình. Ví dụ, nếu ứng dụng chỉ dùng HTTP Basic thì không có lý do để đòi hỏi form login hay OAuth2 login filter cùng hiện diện.
- Thứ tự biểu thị **vị trí tương đối**, không phải cam kết một số nguyên cố định cho từng filter qua mọi phiên bản. Khi cần so sánh, dùng `getOrder()`, tránh hardcode số hoặc dựa vào `ordinal()`.
- Filter có thể **kết thúc request sớm** (CORS preflight, CSRF bị từ chối, xác thực lỗi, logout, quyền bị từ chối). Các filter ở phía sau có thể không được gọi.
- Các enum/feature có thể thay đổi giữa Spring Security 6.x và 7.x. Kiểm tra Javadoc đúng phiên bản thư viện của dự án trước khi dùng một hằng ít gặp.

## 2. Thứ tự các mốc SecurityWebFiltersOrder

Bảng dưới đây đặt các hằng theo **thứ tự khai báo trong Javadoc Spring Security 7.1**; những hằng chỉ xuất hiện ở phiên bản mới hoặc chỉ dùng cho tính năng bật thêm được ghi rõ. Khi dùng Spring Security 6.x, hãy đối chiếu API 6.x của chính dự án; đừng sao chép mặc định cấu hình 7.x.

| Vị trí | Hằng `SecurityWebFiltersOrder` | Ý nghĩa / filter điển hình |
| --- | --- | --- |
| 1 | `FIRST` | Mốc bắt đầu cho filter cần chạy rất sớm |
| 2 | `HTTP_HEADERS_WRITER` | Thiết lập các security response header theo cấu hình |
| 3 | `HTTPS_REDIRECT` | `HttpsRedirectWebFilter` nếu bật redirect sang HTTPS |
| 4 | `CORS` | `CorsWebFilter` khi có cấu hình CORS thích hợp |
| 5 | `CSRF` | `CsrfWebFilter` xử lý bảo vệ CSRF |
| 6 | `REACTOR_CONTEXT` | `ReactorContextWebFilter` tải `SecurityContext` từ repository vào Reactor Context |
| 7 | `HTTP_BASIC` | Vị trí xác thực qua HTTP Basic khi bật |
| 8 | `FORM_LOGIN` | Vị trí `AuthenticationWebFilter` cho form login khi bật |
| 9 | `AUTHENTICATION` | Vị trí tổng quát cho các cơ chế xác thực, ví dụ custom/Bearer trong cấu hình phù hợp |
| 10 | `ANONYMOUS_AUTHENTICATION` | `AnonymousAuthenticationWebFilter` cung cấp danh tính anonymous nếu cần |
| 11 | `OAUTH2_AUTHORIZATION_CODE` | Vị trí hỗ trợ quy trình OAuth2 authorization code khi bật |
| 12 | `LOGIN_PAGE_GENERATING` | Tạo trang đăng nhập mặc định nếu tính năng sử dụng |
| 13 | `LOGOUT_PAGE_GENERATING` | Tạo trang xác nhận logout nếu cấu hình áp dụng |
| 14 | `ONE_TIME_TOKEN` | Filter hỗ trợ one-time-token login ở phiên bản có tính năng này |
| 15 | `ONE_TIME_TOKEN_SUBMIT_PAGE_GENERATING` | Tạo trang nhập one-time token khi bật tính năng tương ứng |
| 16 | `SECURITY_CONTEXT_SERVER_WEB_EXCHANGE` | `SecurityContextServerWebExchangeWebFilter` giúp `exchange.getPrincipal()` sử dụng security context reactive |
| 17 | `SERVER_REQUEST_CACHE` | `ServerRequestCacheWebFilter` hỗ trợ lưu/khôi phục request trong một số luồng đăng nhập |
| 18 | `LOGOUT` | Xử lý yêu cầu logout nếu cấu hình |
| 19 | `EXCEPTION_TRANSLATION` | Chuyển lỗi authentication/authorization từ downstream thành phản hồi xử lý bởi security handler |
| 20 | `AUTHORIZATION` | Kiểm tra quy tắc truy cập exchange trước khi vào handler |
| 21 | `LAST` | Mốc cuối cho filter bổ sung |

**Đọc bảng như các vị trí, không như danh sách bắt buộc xuất hiện:** phần lớn dự án chỉ khởi tạo một tập con tùy `httpBasic`, `formLogin`, `oauth2Login`, `oauth2ResourceServer`, `csrf`, `cors`, v.v. Các mốc `FIRST`/`LAST` chủ yếu hữu ích khi chèn filter. Định dạng bảng cũng không biểu thị số nguyên mà `getOrder()` trả về.

Hãy để ý hai cặp vị trí quan trọng:

- `REACTOR_CONTEXT` ở **trước các vị trí xác thực**: hỗ trợ nạp thông tin xác thực sẵn có từ repository vào Reactor Context. Khi xác thực mới thành công, cơ chế authentication có thể cung cấp context cho chuỗi xử lý phía sau.
- `EXCEPTION_TRANSLATION` ở **trước `AUTHORIZATION`**: nó bao quanh phần xử lý downstream, nên có thể nhận lỗi thiếu xác thực/thiếu quyền phát sinh khi phân quyền và chọn entry point hoặc access-denied handler phù hợp.

### REACTOR_CONTEXT khác SECURITY_CONTEXT_SERVER_WEB_EXCHANGE

Hai tên gần giống nhưng nhiệm vụ khác nhau:

| Mốc | Trọng tâm |
| --- | --- |
| `REACTOR_CONTEXT` | Sử dụng `ServerSecurityContextRepository` để đưa `SecurityContext` vào `ReactiveSecurityContextHolder` trong luồng xử lý |
| `SECURITY_CONTEXT_SERVER_WEB_EXCHANGE` | Thích nghi `ServerWebExchange.getPrincipal()` để tra principal từ `ReactiveSecurityContextHolder` |

Cả hai không phải là bộ kiểm chứng password. Việc xác thực thuộc các filter/manager authentication. `ReactiveSecurityContextHolder` gắn với Reactor Context của subscription; không lấy `SecurityContextHolder.getContext()` kiểu thread-local trong service reactive để suy đoán danh tính.

## 3. Đọc các giai đoạn theo luồng xử lý một request

Một request HTTP Basic tới `GET /admin` có thể được nhìn theo trình tự khái niệm sau (chỉ các giai đoạn hiện diện trong cấu hình):

```text
Request vào
   |
   +--> Security headers / HTTPS / CORS / CSRF
   |
   +--> Tải SecurityContext vào Reactor Context nếu có
   |
   +--> HTTP Basic -> AuthenticationManager (nếu có Basic credentials)
   |
   +--> Các vị trí authentication khác / anonymous khi thích hợp
   |
   +--> Bọc exchange principal / request cache / logout khi phù hợp
   |
   +--> Exception translation chuẩn bị xử lý lỗi ở downstream
   |
   +--> Authorization: /admin có yêu cầu ROLE_ADMIN?
   |      |
   |      +-- Không: lỗi/denial -> security handler -> 401 hoặc 403
   |      |
   |      +-- Có: gọi WebFilterChain tiếp -> Controller
   |
   +--> Mono/Flux response hoàn tất hoặc lỗi
   |
Response đi ra qua các filter đã tham gia
```

Đây là bản đồ học tập, **không phải trace cam kết của mọi request**. Ví dụ:

- CORS preflight có thể được xử lý sớm mà không đi tới controller.
- CSRF chỉ cần chặn request nằm trong phạm vi quy tắc bảo vệ; GET/HEAD thường không cần token.
- Nếu có Basic credential sai, authentication có thể phát lỗi và một entry point sẽ xử lý, controller không được gọi.
- Một request đã đăng nhập nhưng thiếu role thường bị từ chối bằng 403; chưa đăng nhập vào tài nguyên được bảo vệ thường nhận 401 trong ví dụ HTTP Basic.
- Logout có thể xử lý request phù hợp và dừng phần còn lại của chain.
- `permitAll()` chỉ là một quy tắc tại authorization: các filter khác có thể vẫn chạy trước đó. "Public endpoint" không tự động làm cả Security chain biến mất.

### Vì sao EXCEPTION_TRANSLATION đứng trước AUTHORIZATION?

Trong `WebFilter.filter(exchange, chain)`, gọi `chain.filter(exchange)` sẽ nhận publisher của phần downstream. Filter phía trước có thể bọc publisher này để bắt lỗi. Vì vậy, **thứ tự request đi vào** khác **thứ tự các callback hoàn tất quay ra**.

Hình dung hai filter `A`, `B` và endpoint:

```text
A: before
  B: before
    Handler
  B: after
A: after
```

Điều này giống cặp dấu ngoặc. `EXCEPTION_TRANSLATION` đặt trước `AUTHORIZATION` để có cơ hội nhìn thấy `AccessDeniedException` hoặc các lỗi bảo mật phát sinh trong phần mà nó bọc. Không nên đặt mã `onErrorResume` chung ở custom filter để đổi tất cả `AccessDeniedException` thành thành công: cách đó có thể che giấu cơ chế trả 401/403.

### Mô phỏng thứ tự vào/ra bằng Reactor

File **`src/main/java/demo/FilterNestingDemo.java`**, chạy với Java 17+ và `reactor-core` trên classpath:

```java
package demo;

import reactor.core.publisher.Mono;

public class FilterNestingDemo {
    public static void main(String[] args) {
        Mono<Void> handler =
                Mono.fromRunnable(() -> System.out.println("handler")).then();

        Mono<Void> security = around("security", handler);
        Mono<Void> global = around("global", security);

        global.block(); // Chỉ trong chương trình console này
    }

    private static Mono<Void> around(String name, Mono<Void> next) {
        return Mono.defer(() -> {
            System.out.println(name + " before");
            return next.then(Mono.fromRunnable(
                    () -> System.out.println(name + " after")));
        });
    }
}
```

Stdout chính xác khi publisher hoàn tất thành công:

```text
global before
security before
handler
security after
global after
```

Chạy qua Gradle task/application phù hợp hoặc trong IDE với thư viện Reactor. Đây chỉ là mô hình cho thứ tự tín hiệu: mã thực tế trong Spring Security có nhánh lỗi, cancellation và những filter dừng chuỗi sớm. `then(...)` chỉ chạy hành động cuối khi upstream complete thành công; nếu cần quan sát cả lỗi/hủy, cân nhắc `doFinally(signalType -> ...)`. Trong WebFlux controller/filter **không gọi `block()`**.

## 4. Đặt custom WebFilter vào đâu?

Dùng API của `ServerHttpSecurity`:

```java
http.addFilterBefore(customWebFilter, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAfter(customWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
http.addFilterAt(customWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `addFilterBefore(filter, order)` | Chèn ngay trước **mốc order** được chọn | Phù hợp để xử lý/quan sát trước authorization |
| `addFilterAfter(filter, order)` | Chèn ngay sau **mốc order** được chọn | Không đồng nghĩa mọi phương thức authentication của cấu hình đều đã hoàn tất |
| `addFilterAt(filter, order)` | Đăng ký filter cùng vị trí order | **Không tự thay thế** filter có sẵn; trùng vị trí có thể không có thứ tự tương đối chắc chắn |

**Vị trí nên chọn từ mục đích:**

- Cần đọc danh tính đã xác thực và ghi audit chung của request: thường chèn `addFilterBefore(probe, AUTHORIZATION)`; vẫn phải xử lý trường hợp anonymous/không có context.
- Cần xử lý một credential type đặc biệt: tích hợp vào cơ chế `AuthenticationWebFilter` + `ServerAuthenticationConverter` + `ReactiveAuthenticationManager` rồi chèn ở mốc authentication thích hợp; đừng chỉ đọc header và tự coi như người dùng đã đăng nhập.
- Cần thêm quy tắc kiểm soát truy cập: ưu tiên DSL `authorizeExchange`, `ReactiveAuthorizationManager` hoặc reactive method security thay vì làm một WebFilter tùy ý trả 200/403.
- Cần CORS/CSRF/headers: ưu tiên các cấu hình chuẩn do `ServerHttpSecurity` cung cấp, tránh tái hiện các filter bảo vệ bằng code tự viết.

Không đăng ký custom security filter bằng `@Component` hoặc `@Bean WebFilter` toàn cục nếu mục đích là kiểm soát **vị trí trong riêng SecurityWebFilterChain**. Làm thế có thể khiến nó xuất hiện ở chuỗi WebFlux bên ngoài (hoặc chạy thêm lần nữa nếu cũng chèn vào security chain).

### "At" không có nghĩa "replace"

Trong WebFlux, `addFilterAt(filter, AUTHENTICATION)` **thêm** một WebFilter vào cùng order; không có hợp đồng đảm bảo việc xóa filter authentication đã có. Nếu thực sự muốn thay đổi cơ chế xác thực, hãy cấu hình/tắt cơ chế cũ rõ ràng, rồi đăng ký cơ chế mới. Không dựa vào tie-break của nhiều filter cùng order.

### Thứ tự source code cấu hình không phải thứ tự chạy

Hai lời gọi `addFilterBefore(...)` / `addFilterAfter(...)` có thể được thực hiện theo bất kỳ thứ tự trong đoạn Java cấu hình, nhưng filter được sắp theo order khi build chain. Nên tránh hai custom filter cùng slot vì không nên giả định thứ tự tie. Có thể quan sát bằng log/test thay vì đoán từ vị trí dòng code.

## 5. Ví dụ thực hành WebFlux có filter trước authorization

Ví dụ sau dùng **Java 17+**, Spring Boot với Spring Security WebFlux, một Security chain, HTTP Basic và một custom `WebFilter` chỉ ghi loại authentication đã thấy. Nó không thay thế kiểm tra quyền và không tự xác thực credential.

Trong project Gradle Spring Boot đã cấu hình plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

**`src/main/java/demo/orderdemo/OrderDemoApplication.java`**:

```java
package demo.orderdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebFilter;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class OrderDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderDemoApplication.class, args);
    }
}

@Configuration
@EnableWebFluxSecurity
class SecurityConfiguration {
    private static final Logger LOG =
            LoggerFactory.getLogger(SecurityConfiguration.class);

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        WebFilter stageProbe = (exchange, chain) ->
                ReactiveSecurityContextHolder.getContext()
                        .map(ctx -> ctx.getAuthentication())
                        .map(auth -> auth.getClass().getSimpleName())
                        .defaultIfEmpty("NoSecurityContext")
                        .doOnNext(type -> LOG.info(
                                "Before AUTHORIZATION path={} authType={}",
                                exchange.getRequest().getPath().value(),
                                type))
                        .then(Mono.defer(() -> chain.filter(exchange)))
                        .doFinally(signal -> LOG.info(
                                "Finished downstream path={} signal={}",
                                exchange.getRequest().getPath().value(),
                                signal));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .addFilterBefore(stageProbe, SecurityWebFiltersOrder.AUTHORIZATION)
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(reader, admin);
    }
}

@RestController
class ExampleApi {
    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(ctx -> "hello " + ctx.getAuthentication().getName());
    }

    @GetMapping("/admin")
    Mono<String> admin() {
        return Mono.just("admin only");
    }
}
```

**Vì sao vị trí và code như vậy?**

1. `stageProbe` chỉ được chèn bằng `ServerHttpSecurity` vào chain, không có `@Component` đăng ký WebFilter toàn cục.
2. `addFilterBefore(..., AUTHORIZATION)` đặt nó sau các vị trí authentication thông thường và trước bước kiểm tra quyền của exchange.
3. `ReactiveSecurityContextHolder.getContext()` lấy context từ pipeline. `defaultIfEmpty(...)` đảm bảo probe vẫn gọi `chain.filter(exchange)` khi không có context.
4. `then(Mono.defer(() -> chain.filter(exchange)))` cho downstream chạy sau khi việc ghi log phía trước hoàn tất. Không có `subscribe()` hay `block()` thủ công trong filter.
5. `doFinally` ghi tín hiệu kết thúc downstream trên cả complete/error/cancel. Với request bị từ chối, signal có thể là `onError` tại vị trí probe, dù HTTP response cuối được exception-translation filter phía ngoài chuyển thành 401/403. **Signal không phải mã HTTP.**
6. Probe chỉ log loại authentication, tránh in password, Basic credential, bearer token hay toàn bộ `SecurityContext`.

Chạy từ dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell có thể dùng `.\gradlew.bat bootRun`. Trên hệ thống cần có Java tương thích với phiên bản Spring Boot, thông thường Java 17+ cho Boot 3.x. Đoạn Java này cần Spring Boot và các dependency được quản lý bằng Gradle/Maven; `javac` đơn lẻ khi không có classpath Spring sẽ không biên dịch được.

Trong terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
```

| Request | HTTP status kỳ vọng | Body khi thành công | Nguyên nhân |
| --- | --- | --- | --- |
| `GET /public` không credential | `200` | `public` | `permitAll()` |
| `GET /admin` không credential | `401` | Phụ thuộc entry point | Cần đăng nhập |
| `GET /me` bằng `reader` | `200` | `hello reader` | Đã xác thực; controller đọc context |
| `GET /admin` bằng `reader` | `403` | Phụ thuộc handler | Đã đăng nhập nhưng thiếu `ROLE_ADMIN` |
| `GET /admin` bằng `admin` | `200` | `admin only` | Có `ROLE_ADMIN` |

Lưu ý: `roles("ADMIN")` tạo authority `ROLE_ADMIN`; cấu hình `hasRole("ADMIN")` tự áp dụng tiền tố `ROLE_`. Header, body lỗi và chi tiết log phụ thuộc phiên bản/cấu hình; đừng kiểm thử bằng cách so khớp **nguyên văn** toàn bộ log hoặc body lỗi. Tài khoản/password trên chỉ dành cho môi trường thực hành, không đưa credential ví dụ vào source production.

### Kiểm tra tự động trạng thái HTTP

Với Spring Boot 3.x có `spring-boot-starter-test`, thêm:

**`src/test/java/demo/orderdemo/OrderDemoHttpTest.java`**:

```java
package demo.orderdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderDemoHttpTest {
    @Autowired
    WebTestClient client;

    @Test
    void anonymousCannotReadAdmin() {
        client.get().uri("/admin").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotReadAdmin() {
        client.get().uri("/admin")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdmin() {
        client.get().uri("/admin")
                .headers(headers -> headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin only");
    }
}
```

Chạy `./gradlew test --tests demo.orderdemo.OrderDemoHttpTest` (PowerShell: `.\gradlew.bat test --tests demo.orderdemo.OrderDemoHttpTest`). Khi cấu hình hoạt động đúng, cả ba test PASS. Test này **kiểm tra hành vi truy cập**. Để chứng minh chính xác custom filter đã chạy trước authorization hoặc đo thứ tự log, cần thêm phép quan sát có kiểm soát như spy/metric trong test, thay vì chỉ nhìn status code.

## 6. Phân biệt thứ tự của nhiều chain với thứ tự filter

Một cấu hình nâng cao có thể dành `/api/**` cho JWT resource server, còn các URL khác dùng HTTP Basic. Mấu chốt là vị trí của **bean chain** và matcher, không phải `SecurityWebFiltersOrder`.

Ví dụ cấu trúc minh họa, không phải chương trình chạy độc lập (cần bean decoder JWT và các thành phần khác của resource server):

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
}

@Bean
SecurityWebFilterChain defaultChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Với request `/api/orders`, chain có `@Order(1)` được xét trước; nếu matcher đúng, Spring Security dùng chain API. Với request `/dashboard`, matcher API không khớp và chain mặc định xử lý. Mỗi chain tự có các filter của mình sắp theo `SecurityWebFiltersOrder`.

**Lỗi nghiêm trọng cần tránh:** để một chain đặc thù match mọi URL vì quên `securityMatcher`, khiến chain còn lại không có cơ hội xử lý; hoặc cấu hình matcher không phủ endpoint cần bảo vệ. Test đường đi qua từng chain, đặc biệt là public, protected, API, admin và request không khớp.

## 7. Những hiểu lầm và lỗi hay gặp

| Hiểu lầm / lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| "Enum có 21 hằng thì request chạy 21 filter" | Enum là các slot, nhiều tính năng không bật | Kiểm tra chain thực sự được build và cơ chế xác thực bật |
| "Chỉ cần đổi thứ tự khai báo Java là đổi thứ tự chạy" | Filter được sắp theo order | Chèn bằng `addFilterBefore/After/At` ở mốc rõ ràng |
| "`addFilterAt` thay filter có sẵn" | Thêm cùng order, có thể tạo tie | Tắt/thay cơ chế cũ bằng cấu hình và chọn vị trí phù hợp |
| "`@Order` trên chain giống `SecurityWebFiltersOrder`" | Một cái chọn chain, một cái sắp filter | Xác định đúng lớp thứ tự đang cấu hình |
| "HTTP Basic luôn chạy cho mọi request" | Chỉ xử lý khi cơ chế và matcher/credential phù hợp | Đọc thực tế cấu hình; test các loại request |
| "Authorization phải đứng trước authentication" | Không thể kiểm tra quyền theo danh tính khi chưa có context | Để các cơ chế authentication/context chạy ở giai đoạn thích hợp |
| "Không cần EXCEPTION_TRANSLATION vì có ControllerAdvice" | Lỗi bảo mật có thể phát sinh trước controller | Dùng entry point/access-denied handler của Spring Security |
| "`permitAll()` bỏ qua tất cả filter" | Chỉ cho phép ở bước authorization | Nếu cần khác biệt hành vi, cấu hình matcher/filter đúng mục đích |
| "Đặt @Component WebFilter và addFilterBefore cùng lúc là an toàn" | Có thể đăng ký cả global lẫn security chain | Chỉ đăng ký một đường thực sự cần |
| "Không có SecurityContext thì dừng Mono sẽ tự từ chối" | `Mono.empty()` chỉ là tín hiệu không có giá trị | Luôn xử lý rõ ràng nhánh trống và tiếp tục chain/ủy quyền đúng cách |
| "`doFinally(ON_ERROR)` chứng tỏ response chắc chắn HTTP 500" | Exception translation có thể chuyển lỗi thành 401/403 | Đo status riêng và hiểu phạm vi quan sát |
| "Log token và SecurityContext để debug dễ hơn" | Có thể lộ dữ liệu đăng nhập nhạy cảm | Log loại/trace ID đã kiểm soát, không ghi credential |

### Checklist thiết kế custom filter

- Xác định filter cần chạy **trước hay sau** authentication và authorization; nếu cần principal hãy đọc bằng `ReactiveSecurityContextHolder`, chấp nhận anonymous/empty.
- Không dùng `block()` hoặc `subscribe()` thủ công trong WebFilter; trả publisher của `chain.filter(exchange)` và bảo toàn đường đi lỗi/hủy.
- Không tự trả phản hồi thành công khi nhận `AuthenticationException` hoặc `AccessDeniedException` nếu không có chính sách rõ ràng; giữ exception translation hoạt động.
- Tránh đọc request body trong filter nếu không có kỹ thuật caching/đảm bảo replay; body reactive có thể bị consume và controller không đọc lại được.
- Khi cần đặt nhiều filter gần một mốc, có test thứ tự thực tế; tránh giả định hai filter cùng order tự sắp ổn định.
- Nếu chạy nhiều chain, kiểm tra mỗi `securityMatcher` và mức ưu tiên `@Order`; một request được chọn vào chain phù hợp, không tự nhận mọi rule từ chain khác.
- Không tắt CSRF, CORS hoặc security headers chỉ để test order; những bảo vệ này có ý nghĩa khác và cần quyết định riêng.

## 8. Bài tập vận dụng

1. Đổi filter demo sang `addFilterAfter(stageProbe, SecurityWebFiltersOrder.AUTHENTICATION)`. Dùng log/spy chứng minh vị trí và giải thích vì sao "sau slot AUTHENTICATION" không có nghĩa sau mọi phương thức xác thực tùy chọn.
2. Thêm một filter trước `EXCEPTION_TRANSLATION` và một filter trước `AUTHORIZATION`. Khi truy cập `/admin` không đủ role, so sánh tín hiệu lỗi quan sát được và mã HTTP cuối.
3. In kết quả so sánh `SecurityWebFiltersOrder.REATOR_CONTEXT` với `AUTHORIZATION` bằng `getOrder()`, sau khi sửa tên hằng cho đúng. Giải thích vì sao không hardcode số thứ tự.
4. Thêm `/api/**` với một chain riêng ưu tiên hơn; thử truy cập URL API, URL mặc định và URL chưa có rule. Tìm lỗi nếu chain API vô tình match tất cả.
5. Test một request OPTIONS preflight khi CORS được cấu hình thích hợp, rồi một POST thiếu CSRF token trong ứng dụng dùng session. Phân biệt giai đoạn nào từ chối, và vì sao không thể suy ra thứ tự chỉ qua status code.
6. Viết test cho custom filter bảo đảm `chain.filter(exchange)` được subscribe **chính xác một lần** cả khi có và khi không có security context.

**Điểm cốt lõi:** `SecurityWebFiltersOrder` chỉ định **vị trí tương đối** của các WebFlux security filter. Đọc request theo luồng đi vào, đọc response theo luồng publisher hoàn tất quay ra; chọn đúng chain trước khi nghĩ đến filter. Khi thêm filter, giữ nguyên hợp đồng reactive và để authentication/authorization/exception translation của Spring Security thực hiện công việc của chúng.

## Tài liệu chính thức

- [Spring Security — SecurityWebFiltersOrder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/SecurityWebFiltersOrder.html)
- [Spring Security — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — WebFlux Security và Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive SecurityContext và Spring Security](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
