# NoOpServerSecurityContextRepository: không lưu SecurityContext giữa các request trong Spring Security WebFlux

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Security **reactive (Spring WebFlux)**, một request có thể được xác thực thành công, nhưng ứng dụng không nhất thiết phải ghi kết quả xác thực vào session để dùng lại ở request sau. `NoOpServerSecurityContextRepository` là lựa chọn cho chính sách **không lưu/không khôi phục `SecurityContext` giữa các HTTP request**.

Sau bài này, bạn có thể:
- Giải thích trách nhiệm của `ServerSecurityContextRepository` và mối quan hệ với `ReactiveSecurityContextHolder`.
- Hiểu hành vi `load`/`save` của `NoOpServerSecurityContextRepository`.
- Cấu hình WebFlux HTTP Basic để mỗi request tự cung cấp thông tin xác thực, không tái sử dụng context từ request trước.
- Kiểm chứng bằng request thực tế và phân biệt việc không lưu context với việc không tồn tại mọi loại session/cookie.

**Phạm vi:** API reactive dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchange`. API servlet như `HttpSecurity`, `SecurityContextRepository` (không có tiền tố `Server`) hoặc `SessionCreationPolicy.STATELESS` là một nhánh cấu hình khác.

## 2. SecurityContext nằm ở đâu trong một luồng reactive?

- `Authentication` mô tả danh tính đã xác thực, principal và các authority; `SecurityContext` chứa `Authentication` hiện tại.
- `ReactiveSecurityContextHolder` cung cấp context cho chuỗi Reactor (`Mono`/`Flux`), thường được truy cập trong lúc xử lý **request hiện tại**. Không nên suy luận rằng context này là một biến `ThreadLocal` gắn cố định với một thread: một pipeline reactive có thể đổi thread.
- `ServerSecurityContextRepository` là chiến lược **lưu và khôi phục** `SecurityContext` qua các HTTP request. Hai phương thức quan trọng:
  - `Mono<SecurityContext> load(ServerWebExchange exchange)`: tìm context đã lưu cho request; `Mono.empty()` nghĩa là không tìm thấy.
  - `Mono<Void> save(ServerWebExchange exchange, SecurityContext context)`: lưu context và phát tín hiệu hoàn tất.
- `ReactorContextWebFilter` dùng repository để khôi phục context vào luồng xử lý. Một bộ lọc xác thực như `AuthenticationWebFilter` có thể tạo `Authentication` mới từ credential của chính request đó và đưa nó vào ngữ cảnh reactive, kể cả khi không có context nào được load trước.

**Hai khái niệm phải tách biệt:** context đang tồn tại **trong request hiện hành** và context được **ghi để tái sử dụng ở request kế tiếp**. NoOp loại bỏ hành vi thứ hai; nó không ngăn bộ lọc xác thực tạo context trong request hiện hành.

## 3. NoOp thực sự làm gì?

Lớp `org.springframework.security.web.server.context.NoOpServerSecurityContextRepository` triển khai `ServerSecurityContextRepository` theo kiểu “không làm gì”:

| Thao tác | Hành vi | Ý nghĩa |
| --- | --- | --- |
| `load(exchange)` | Trả `Mono.empty()` | Không có `SecurityContext` cũ được khôi phục từ repository. |
| `save(exchange, context)` | Trả một `Mono<Void>` hoàn tất mà không lưu gì | Xác thực thành công không được repository ghi để dùng lại sau. |
| `getInstance()` | Trả instance dùng chung | Dùng lại thay vì tự tạo repository cho từng request. |

Điều này thích hợp khi từng request mang thông tin xác thực như header `Authorization: Basic ...` hoặc `Authorization: Bearer ...`. Việc request thứ hai thành công vì **lại gửi credential/token** khác với thành công vì **được phục hồi từ session**.

Luồng minh họa:

~~~text
Request #1: Authorization: Basic ...
    -> repository.load(): empty
    -> HTTP Basic xác thực username/password của request #1
    -> Authentication có mặt trong Reactor Context của request #1
    -> endpoint được phép xử lý
    -> repository.save(): không ghi gì

Request #2: không có Authorization
    -> repository.load(): empty
    -> không có danh tính đã xác thực để tái sử dụng
    -> endpoint yêu cầu authenticated => HTTP 401
~~~

**Giới hạn chính xác:** NoOp chỉ chi phối nơi lưu/đọc `SecurityContext` tại các điểm được cấu hình dùng repository này. Nó không tự tắt cơ chế `WebSession` của những thành phần khác, không xóa mọi cookie, không vô hiệu hóa CSRF, không thay chính sách phân quyền, không xác thực token và cũng không tự thu hồi token đã cấp.

## 4. Ví dụ hoàn chỉnh: WebFlux + HTTP Basic không lưu context

Ví dụ dùng **Java 17+, Spring Boot 3.3.12 / Spring Security 6.x**, ứng dụng WebFlux thuần, một user thử nghiệm và endpoint `GET /me`. Để chạy riêng ví dụ, tạo project Gradle với các file sau; nếu đưa vào module đã có build thì chỉ cần các dependency tương đương.

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
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

**`src/main/java/demo/StatelessWebfluxApplication.java`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatelessWebfluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(StatelessWebfluxApplication.class, args);
    }
}
~~~

**`src/main/java/demo/SecurityConfig.java`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        var noOp = NoOpServerSecurityContextRepository.getInstance();

        return http
                // Chỉ định nơi ReactorContextWebFilter tìm context cũ.
                .securityContextRepository(noOp)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/me").authenticated()
                        .anyExchange().permitAll())
                // Chỉ định luôn repository cho bộ lọc HTTP Basic khi lưu.
                .httpBasic(basic -> basic.securityContextRepository(noOp))
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    public ReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .roles("READER")
                .build();
        return new MapReactiveUserDetailsService(reader);
    }
}
~~~

**`src/main/java/demo/MeController.java`**

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping(value = "/me", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> "Xin chào, " + authentication.getName());
    }
}
~~~

**Vì sao cấu hình có hai chỗ dùng `noOp`?** `ServerHttpSecurity.securityContextRepository(noOp)` định cấu hình repository cho `ReactorContextWebFilter` khi **đọc context**, còn `httpBasic(basic -> basic.securityContextRepository(noOp))` xác định nơi bộ lọc HTTP Basic **lưu kết quả xác thực**. Hai nơi này không được tự động liên kết với nhau trong mọi cấu hình; đặt rõ cả hai giúp mục tiêu của ví dụ dễ kiểm chứng. HTTP Basic mặc định cũng dùng NoOp để lưu trong các bản Spring Security tương ứng, nhưng viết tường minh làm rõ ý định.

`formLogin` được tắt vì ví dụ dùng credential trên mỗi HTTP request thay vì luồng login browser dựa trên session. `{noop}` trong mật khẩu chỉ để demo: đây là ký hiệu encoder chấp nhận mật khẩu **không băm**, tuyệt đối không dùng cho tài khoản thật. Ứng dụng thật dùng password encoder phù hợp (ví dụ BCrypt), nguồn user an toàn và kết nối HTTPS.

### Chạy và quan sát

Với Gradle Wrapper đã tạo cho project, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Không dùng kèm starter servlet/MVC cho ví dụ WebFlux thuần.

Mở terminal khác, gọi ba request **độc lập**:

~~~bash
# 1. Không có credential: endpoint được bảo vệ.
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me

# 2. Cung cấp Basic credential ở chính request này.
curl -s -u reader:demo123 -w '\n' http://localhost:8080/me

# 3. Bỏ Authorization: không được kế thừa request #2.
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
~~~

Kết quả tương ứng (mỗi lệnh một dòng):

~~~text
401
Xin chào, reader
401
~~~

Request #2 thành công vì Spring Security xác thực Basic header và đưa `Authentication` vào Reactor Context của **cùng request**; `MeController` đọc danh tính qua `ReactiveSecurityContextHolder`. Request #3 không có header và repository không thể khôi phục context nên trả 401. Nếu gọi request #2 hai lần, cả hai có thể trả 200: mỗi request lại tự gửi credential, **không chứng tỏ có session persistence**.

## 5. Kiểm thử tự động hành vi không ghi nhớ xác thực

Thêm file **`src/test/java/demo/NoOpSecurityContextTest.java`**; dùng dependency `spring-boot-starter-test` đã khai báo:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoOpSecurityContextTest {

    @Autowired
    WebTestClient client;

    @Test
    void previousAuthenticationIsNotReused() {
        client.get()
                .uri("/me")
                .headers(headers -> headers.setBasicAuth("reader", "demo123"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Xin chào, reader");

        client.get()
                .uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Chạy `./gradlew test` (hoặc `gradlew.bat test`). Phép thử xác minh khả năng truy cập ngay khi có Basic header và việc request kế tiếp không tự nhận lại xác thực. Nó không chứng minh “ứng dụng không tạo bất kỳ session/cookie nào”; để kiểm tra tuyên bố rộng hơn cần rà soát các thành phần và hành vi riêng.

## 6. Khi nào nên dùng và khi nào tránh?

| Tình huống | Đánh giá |
| --- | --- |
| WebFlux API xác thực độc lập trên mỗi request bằng HTTP Basic (trong kênh HTTPS) | Phù hợp; request mang credential mỗi lần. |
| Resource Server xác thực Bearer/JWT cho API | Thường phù hợp về nguyên tắc không lưu `SecurityContext`; xác thực/kiểm tra token là trách nhiệm riêng. |
| Trình duyệt đăng nhập bằng form, mong request sau vẫn được nhận diện chỉ nhờ session | Không phù hợp: context không được nhớ; nên xem xét `WebSessionServerSecurityContextRepository` và cấu hình đăng nhập nhất quán. |
| Tác vụ cần giữ trạng thái đăng nhập giữa các request mà client không gửi lại credential | Không phù hợp nếu chỉ dùng NoOp; cần chiến lược lưu/khôi phục khác. |

**So sánh với `WebSessionServerSecurityContextRepository`:** repository này dùng `WebSession` để lưu context và lấy lại ở request sau khi session tương ứng còn hợp lệ. NoOp không làm việc đó, giảm sự phụ thuộc vào session để phục hồi danh tính nhưng đổi lại client phải có cơ chế xác thực lại từng request. Việc dùng NoOp không tự giảm chi phí xác minh mật khẩu/token; mỗi lần xác thực vẫn có chi phí cần dự tính.

## 7. Lỗi hiểu nhầm và lưu ý bảo mật

1. **“NoOp là tắt authentication.”** Sai. Authentication và authorization vẫn chạy; NoOp chỉ không lưu/đọc `SecurityContext` giữa request tại các bộ lọc được cấu hình.
2. **“Đặt repository trên `ServerHttpSecurity` là đã điều khiển mọi thao tác save.”** Không nên giả định. `ReactorContextWebFilter` tải context qua repository cấu hình ở cấp HTTP, trong khi từng `AuthenticationWebFilter` có cấu hình repository để lưu riêng. Kiểm tra cơ chế xác thực thực tế (HTTP Basic, form login, OAuth2...) và đặt repository đúng chỗ.
3. **“Có context trong Reactor nên context được nhớ ở lần gọi sau.”** Sai. Reactor Context lưu thông tin cho chuỗi xử lý hiện tại; nó không phải kho bền vững giữa hai HTTP request.
4. **“NoOp bảo đảm tuyệt đối không có `WebSession`, `Set-Cookie` hoặc CSRF.”** Sai. Những thành phần khác vẫn có thể dùng session/cookie, và CSRF là chủ đề bảo vệ riêng. Chỉ vô hiệu hóa CSRF khi đã phân tích kiểu client, credential được browser tự gửi và bề mặt tấn công, không tắt theo thói quen.
5. **“HTTP 403 chứng tỏ repository không load được.”** Không nhất thiết. 401 thường phản ánh thiếu/không hợp lệ authentication; 403 thường liên quan quyền truy cập hoặc CSRF. Cần xem cấu hình và log thực tế.
6. **“Dùng Basic với mật khẩu plaintext là đủ cho API stateless.”** Sai. Ví dụ `{noop}` chỉ phục vụ demo. Dùng TLS, mật khẩu được băm ở nơi lưu trữ, kiểm soát quyền; nếu dùng Bearer/JWT cần xác minh issuer/audience/chữ ký/hạn sử dụng và thiết kế thu hồi khi cần.
7. **“NoOp làm logout hoặc thu hồi token tự động.”** Sai. Khi không có context session để xóa, logout ở client có thể là ngừng gửi token; làm token đã phát hành hết hiệu lực sớm cần cơ chế khác.

### Cách chọn nhanh

- Câu hỏi “request này có thể tự chứng minh danh tính không?” → Nếu **có**, chính sách không ghi nhớ `SecurityContext` giữa request thường phù hợp.
- Câu hỏi “người dùng cần được nhận diện ở request kế tiếp mà không gửi lại thông tin xác thực không?” → Nếu **có**, chỉ dùng NoOp sẽ không đáp ứng.
- Câu hỏi “có đảm bảo toàn bộ ứng dụng stateless không?” → Phải đánh giá riêng session, cookie, request cache, CSRF, login và các state store khác; không suy ra từ một repository.

## 8. Tự kiểm tra

**Tình huống A:** Gửi `GET /me` với Basic header hợp lệ, sau đó gửi lại mà không có header. Tại sao lần hai nhận 401? Vì NoOp không lưu context để load lại; request hai không mang credential mới.

**Tình huống B:** Hai request liên tiếp đều gửi Bearer token hợp lệ, cả hai đều thành công. Có phải NoOp không hoạt động? Không. Mỗi request có thể được xác thực độc lập bằng token của chính nó.

**Tình huống C:** Tự xây một `AuthenticationWebFilter` mới, gọi `setSecurityContextRepository` với một repository có lưu session, nhưng chỉ đặt NoOp ở `ServerHttpSecurity`. Có chắc toàn hệ thống không ghi context không? Không; phải kiểm tra repository của chính filter dùng lúc `save`, vì đọc và ghi có thể được cấu hình ở các vị trí khác nhau.

## 9. Tài liệu chính thức

- Spring Security API: [`NoOpServerSecurityContextRepository`](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html).
- Spring Security API: [`ServerSecurityContextRepository`](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/ServerSecurityContextRepository.html).
- Spring Security API: [`ServerHttpSecurity`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html), đặc biệt cấu hình `securityContextRepository` và `httpBasic`.
- Spring Security: [WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html).

**Điểm cần nhớ:** NoOp không ngăn authentication tạo ra `SecurityContext` trong request hiện tại; nó bảo đảm repository được cấu hình không lưu context để dùng lại qua request sau.