# WebTestClient với máy chủ giả lập khác với kết nối HTTP thật

## 1. Cùng một API kiểm thử được ở hai cấp độ

Trong chương **Thiết lập WebTestClient** của module **SPRING_SECURITY_TESTING**, WebTestClient là client kiểm thử HTTP dành cho Spring WebFlux. Nó có thể gửi request đến một web handler được dựng trong bộ nhớ hoặc kết nối tới một HTTP server đang chạy. Hai cách này đều dùng API fluent giống nhau, nhưng chúng kiểm chứng những lớp khác nhau của ứng dụng.

**Máy chủ giả lập (mock server)** chạy pipeline WebFlux trong cùng tiến trình test, không mở cổng TCP. Cách này nhanh, thuận tiện để kiểm tra controller, WebFilter, Spring Security và cách ứng dụng tạo response. **Kết nối HTTP thật** gửi request qua connector của server đang chạy, đi qua socket và HTTP stack thực tế; nó phù hợp để kiểm tra cấu hình server, giao tiếp mạng, cookie, header và tích hợp ở cấp HTTP.

Sau bài học, bạn có thể:

- Phân biệt bindToController, bindToApplicationContext và bindToServer.
- Dựng WebTestClient với Spring Security cho mock WebFlux server.
- Kết nối WebTestClient tới ứng dụng đang chạy bằng RANDOM_PORT hoặc một URL thật.
- Biết khi nào dùng mockUser/mockJwt và khi nào phải gửi credentials hoặc bearer token qua HTTP.
- Chọn cấp độ kiểm thử phù hợp với câu hỏi cần xác minh.
- Tránh kết luận về mạng, cookie hoặc TLS chỉ từ một mock server trong bộ nhớ.

## 2. Hai cách chạy WebTestClient

### Mock server: gọi WebFlux pipeline trong bộ nhớ

Với mock server, WebTestClient gửi request trực tiếp vào WebHandler hoặc controller đã được dựng cho test. Không có TCP socket và không cần khởi động HTTP connector như Reactor Netty hay Tomcat.

Các cách dựng thường gặp:

| Cách dựng | Phạm vi được kiểm thử | Điểm cần chú ý |
| --- | --- | --- |
| **bindToController(...)** | Một hoặc nhiều controller được chỉ định | Kiểu kiểm thử hẹp; không tự động nạp toàn bộ cấu hình ứng dụng |
| **bindToRouterFunction(...)** | RouterFunction và handler chức năng | Phù hợp với functional endpoints; filter và security cần được cấu hình đúng |
| **bindToApplicationContext(...)** | WebFlux application context, WebHandler và các WebFilter đã cấu hình | Thích hợp để kiểm tra Spring Security cùng controller trong context ứng dụng |
| **bindToServer()** | Kết nối tới HTTP server đang chạy | Cần URL/port của server; request đi qua HTTP connector thực |

Khi dùng **bindToApplicationContext**, nên áp dụng **springSecurity()** để tích hợp Spring Security WebFilterChainProxy vào mock WebTestClient setup:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.springframework.context.ApplicationContext;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

Cách này vẫn chạy WebFilter chain và các quy tắc bảo mật của ứng dụng, nhưng không đi qua TCP, TLS handshake, connector hay reverse proxy. Nếu chỉ dùng **bindToController**, không nên mặc định rằng security configuration của toàn application context đã được đưa vào client.

### Kết nối HTTP thật: gọi server đang chạy

Với **bindToServer()**, WebTestClient hoạt động như một HTTP client. Nó gửi request tới địa chỉ server, ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Server phải được khởi động trước. Trong test Spring Boot, cách thuận tiện là dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)** và **@AutoConfigureWebTestClient** để Spring Boot cung cấp WebTestClient trỏ tới server được khởi chạy cho test.

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RealHttpServerTest {

    @Autowired
    WebTestClient webTestClient;
}
~~~

Với cách này, request đi qua HTTP server thật của ứng dụng. Trong dự án WebFlux dùng Reactor Netty, nó đi qua Netty HTTP server; cấu hình connector, codec, cổng, header và cookie thực tế được tham gia vào quá trình xử lý.

## 3. Sơ đồ đường đi của request

~~~mermaid
flowchart TD
    A["Test gọi WebTestClient"] --> B{"Chọn cách bind"}
    B -->|"bindToApplicationContext"| C["Mock WebHandler trong bộ nhớ"]
    C --> D["WebFilter chain / Spring Security"]
    D --> E["Controller hoặc RouterFunction"]
    E --> F["Response trả trực tiếp cho test"]
    B -->|"bindToServer"| G["HTTP client connector"]
    G --> H["TCP / HTTP server connector"]
    H --> I["WebFilter chain / Spring Security"]
    I --> J["Controller hoặc RouterFunction"]
    J --> K["HTTP response qua mạng về test"]
~~~

Cả hai đường đi đều có thể kiểm tra logic controller và Spring Security. Điểm khác biệt là mock server bỏ qua lớp truyền tải mạng và HTTP connector. Vì vậy, kết quả mock server không chứng minh được server thật có bind đúng port, xử lý TLS đúng, nhận header/cookie qua mạng hoặc hoạt động đúng sau reverse proxy.

## 4. Chuẩn bị ứng dụng WebFlux mẫu

Ví dụ dùng **Spring Boot 3.x**, **Spring Security 6.x**, Spring WebFlux, JUnit 5 và spring-security-test. Các dependency chính:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Không thêm spring-boot-starter-web cùng lúc nếu mục tiêu là ứng dụng WebFlux thuần; Spring Boot có thể ưu tiên MVC khi cả hai web starter cùng có mặt.

### 4.1. Cấu hình bảo mật

Ứng dụng mẫu dùng HTTP Basic cho endpoint GET /api/me. HTTP Basic giúp ví dụ tập trung vào việc gửi credentials trên request, không phụ thuộc session đăng nhập.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService reactiveUsers() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}secret")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
~~~

Mật khẩu **{noop}secret** chỉ dùng trong ví dụ test để không làm phần cấu hình encoder che khuất chủ đề. Ứng dụng thực tế phải dùng PasswordEncoder phù hợp và quản lý credentials an toàn.

### 4.2. Controller Reactive

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiController {

    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    Mono<String> currentUser(Principal principal) {
        return Mono.just(principal.getName());
    }
}
~~~

Endpoint /api/me yêu cầu Authentication. Với HTTP Basic, request phải gửi Authorization header hợp lệ. Request không có credentials sẽ bị từ chối bằng 401 theo entry point mặc định của Basic authentication.

## 5. Dựng mock server từ application context

Mock server phù hợp khi muốn kiểm tra WebFlux filter chain và controller mà không cần mở cổng mạng. Ví dụ sau dùng application context và áp dụng Spring Security:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;


@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class MockWebTestClientTest {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void validBasicCredentialsReachProtectedEndpoint() {
        client.get()
                .uri("/api/me")
                .headers(headers -> headers.setBasicAuth("alice", "secret"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void missingCredentialsAreRejected() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void publicEndpointDoesNotRequireCredentials() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }
}
~~~

Trong test này:

- **@SpringBootTest(webEnvironment = MOCK)** nạp application context mà không khởi động HTTP server thật.
- **bindToApplicationContext(...)** dựng mock WebTestClient từ WebFlux context.
- **apply(springSecurity())** thêm cấu hình Spring Security cho mock exchange.
- Header Basic được gửi bằng **setBasicAuth(...)**, nên authentication filter vẫn kiểm tra username/password theo cấu hình ứng dụng.

Có thể dùng **mutateWith(mockUser())** hoặc **mutateWith(mockJwt())** trong các test authorization phù hợp. Các configurer đó tạo Authentication cho test để kiểm tra quy tắc truy cập. Chúng không thay thế việc kiểm tra credentials hoặc token được gửi qua HTTP và được server xác minh.

### 5.1. Khi dùng bindToController

Ví dụ hẹp:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ApiController())
        .build();
~~~

Cách này hữu ích cho kiểm thử controller độc lập, nhưng không tự nạp toàn bộ Spring application context. Nếu cần kiểm tra Spring Security, phải cấu hình các WebFilter/security chain tương ứng hoặc chuyển sang **bindToApplicationContext** để test theo cấu hình ứng dụng.

Đừng kết luận endpoint production được bảo vệ chỉ vì một test bindToController trả 401 hoặc 200; cần xác minh đúng filter chain đang chạy trong test.

## 6. Kết nối HTTP thật bằng Spring Boot RANDOM_PORT

Khi muốn kiểm tra server thật, để Spring Boot khởi động ứng dụng trên một cổng ngẫu nhiên và inject WebTestClient:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class RealWebTestClientTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void validCredentialsAreAcceptedByRunningServer() {
        webTestClient.get()
                .uri("/api/me")
                .headers(headers -> headers.setBasicAuth("alice", "secret"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void anonymousRequestIsRejectedByRunningServer() {
        webTestClient.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

WebTestClient được Spring Boot cấu hình để kết nối tới server đang chạy. Có thể dùng **bindToServer()** thủ công khi test cần một server ngoài application context:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Khi dùng bindToServer, test chịu trách nhiệm bảo đảm server đã sẵn sàng và URL đúng. Với RANDOM_PORT, Spring Boot quản lý việc chọn port và khởi động server trong vòng đời test.

**Không gọi apply(springSecurity()) trên client kết nối server thật.** Security WebFilter chain đã nằm trong ứng dụng đang chạy. Hãy gửi credentials hoặc token qua header/cookie như một client HTTP bình thường.

## 7. Những điều mock server và HTTP thật kiểm tra khác nhau

| Hạng mục | Mock server trong bộ nhớ | Kết nối HTTP thật |
| --- | --- | --- |
| Controller và handler | Có | Có |
| WebFilter và Spring Security chain | Có nếu setup đầy đủ | Có, từ server đang chạy |
| TCP socket và HTTP connector | Không | Có |
| Port binding và server startup | Không | Có |
| TLS handshake và certificate | Không | Có nếu server test bật HTTPS |
| Cookie và Set-Cookie | Kiểm tra response logic được | Kiểm tra qua HTTP stack thật; vẫn cần client gửi lại cookie |
| Header và body serialization | Kiểm tra trong pipeline mock | Kiểm tra qua HTTP connector thực |
| Reverse proxy/load balancer | Không | Chỉ có nếu môi trường test đưa các thành phần đó vào |
| Tốc độ và chi phí | Thường nhanh hơn | Thường chậm và cần quản lý server |
| Phạm vi lỗi được phát hiện | Logic WebFlux/security | Logic cùng lỗi tích hợp HTTP/server/network |

Mock server vẫn là một test có giá trị, không phải một mô phỏng controller giả đơn giản. Khi bindToApplicationContext, nó có thể chạy WebHandler, WebFilter và SecurityWebFilterChain của application context. Nhưng nó không thể chứng minh hành vi của lớp mạng vì lớp đó không được khởi động.

## 8. Mock authentication không giống credentials thật trên HTTP

Spring Security Test có các tiện ích Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockUser().roles("USER"))
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk();

client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("alice")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
~~~

Các configurer này rất hữu ích để kiểm tra authorization với một principal hoặc JWT đã dựng sẵn. Chúng tác động vào mock exchange/test security context; không xác minh rằng server thật đã đọc và xác minh Authorization header trên đường truyền.

Khi test **HTTP thật**, hãy gửi thông tin xác thực thực tế:

- HTTP Basic: dùng **headers.setBasicAuth(username, password)**.
- Bearer JWT: gửi **Authorization: Bearer <token>** bằng token test được ký bằng khóa phù hợp với JwtDecoder/JWK cấu hình.
- OAuth2 login: kiểm thử redirect/callback và session/cookie theo flow thực tế hoặc dùng test chuyên biệt cho mock authentication khi chỉ kiểm tra authorization.
- Cookie session: lấy Set-Cookie từ response login rồi gửi lại cookie ở request tiếp theo.

Với JWT, **mockJwt() không kiểm tra chữ ký, issuer, audience hoặc expiration của token thật**. Nếu cần kiểm tra decoder, hãy tạo token hợp lệ cho test hoặc cấu hình test JWK/decoder và gửi bearer token qua HTTP thật.

## 9. Cookie, session và nhiều request

WebTestClient không nên được xem như một trình duyệt luôn tự động lưu cookie giữa mọi lần exchange. Khi cần kiểm tra session persistence, lấy cookie từ response đăng nhập rồi gửi lại ở request tiếp theo.

Ví dụ ý tưởng cho một endpoint login trả Set-Cookie:

~~~java
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.web.reactive.function.BodyInserters;

EntityExchangeResult<String> login = client.post()
        .uri("/login")
        .body(BodyInserters.fromFormData("username", "alice")
                .with("password", "secret"))
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectBody(String.class)
        .returnResult();

String sessionCookie = login.getResponseCookies()
        .getFirst("SESSION")
        .getValue();

client.get()
        .uri("/api/me")
        .cookie("SESSION", sessionCookie)
        .exchange()
        .expectStatus().isOk();
~~~

Tên cookie trong ví dụ là **SESSION** minh họa. Tên thực tế phụ thuộc WebSessionIdResolver và cấu hình ứng dụng. Nếu ứng dụng dùng Spring Session hoặc cookie tên khác, hãy lấy đúng cookie từ response login. CSRF cũng cần được xử lý theo cấu hình của ứng dụng khi gửi request thay đổi trạng thái.

Đoạn login này giả định ứng dụng đã bật form login. Nếu CSRF đang bật, POST /login phải mang CSRF token hợp lệ; phần thân form ở trên chỉ rút gọn để làm rõ cách trích và gửi lại cookie. Ví dụ không chạy nguyên trạng với cấu hình HTTP Basic ở mục 4.

Ở mock server, cách này kiểm tra logic session/cookie trong WebFlux pipeline. Ở HTTP server thật, nó kiểm tra thêm cách cookie được phát và gửi qua HTTP connector. Muốn kiểm tra browser áp dụng Secure, SameSite và Domain theo đúng quy tắc, cần kiểm thử với browser hoặc HTTP client có hỗ trợ cookie jar và cấu hình tương ứng.

## 10. Chọn cấp độ test theo câu hỏi

| Câu hỏi | Cách phù hợp |
| --- | --- |
| Controller trả body đúng không? | bindToController hoặc bindToApplicationContext |
| Spring Security WebFilter chain có chặn anonymous không? | bindToApplicationContext + springSecurity() |
| Role hoặc authority có được xử lý đúng không? | Mock server + mockUser/mockJwt |
| HTTP Basic credentials có được xác minh bởi ứng dụng không? | Mock server với Authorization Basic; HTTP thật nếu cần xác minh connector |
| Server có bind port và khởi động đúng không? | RANDOM_PORT hoặc bindToServer |
| Header/cookie có đi qua HTTP connector đúng không? | Kết nối HTTP thật |
| TLS certificate và HTTPS hoạt động đúng không? | Server thật với HTTPS và client cấu hình trust phù hợp |
| Reverse proxy hoặc load balancer có chuyển tiếp header đúng không? | Test tích hợp trong môi trường có proxy |
| JWT signature và issuer được xác minh đúng không? | Gửi token thật qua resource server và kiểm tra decoder |

Không cần dùng HTTP server thật cho mọi test. Hãy dùng mock server cho nhiều test logic để phản hồi nhanh; thêm test HTTP thật cho những rủi ro nằm ở server, connector, cookie, TLS hoặc tích hợp mạng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mock server trả 200 dù thiếu security | Dùng bindToController mà không gắn filter chain | Dùng bindToApplicationContext + springSecurity() hoặc cấu hình filter rõ ràng |
| Mock server trả 404 cho endpoint đã có | Context test không nạp controller/router hoặc sai base path | Kiểm tra application context và mapping |
| Security config không có hiệu lực trong mock test | Chưa apply springSecurity() hoặc context không có SecurityWebFilterChain | Kiểm tra setup và bean security |
| Real server test không kết nối được | Server chưa khởi động, sai port hoặc WebTestClient không trỏ đúng base URL | Dùng RANDOM_PORT + AutoConfigureWebTestClient hoặc kiểm tra URL |
| mockJwt() pass nhưng token thật bị từ chối | Mock JWT bỏ qua việc xác minh chữ ký/token decoder | Gửi JWT test hợp lệ qua Authorization header |
| Cookie có trong response nhưng request sau không đăng nhập | Không gửi lại cookie, sai tên cookie hoặc session đã hết hạn | Trích cookie response và gắn vào request kế tiếp |
| Test pass mock nhưng fail HTTP thật | Lỗi connector, serialization, cookie, port, TLS hoặc cấu hình môi trường | Bổ sung test ở cấp HTTP thật để khoanh vùng |
| Dùng apply(springSecurity()) với bindToServer | Nhầm mock configurer với client HTTP thật | Chỉ áp dụng springSecurity() cho mock WebTestClient setup |

## 12. Bài tập thực hành

1. Dựng WebTestClient bằng bindToApplicationContext và apply(springSecurity()). Gửi GET /api/me không credentials và xác minh 401.
2. Gửi HTTP Basic credentials hợp lệ qua mock server; xác minh endpoint trả username alice.
3. Viết một test bindToController riêng và quan sát khác biệt khi chưa tích hợp SecurityWebFilterChain.
4. Chạy ứng dụng bằng RANDOM_PORT, inject WebTestClient và lặp lại hai ca anonymous/authenticated qua HTTP connector thật.
5. Với API JWT, so sánh mockJwt() trên mock server với request gửi Authorization Bearer token thật tới server đang chạy.
6. Nếu ứng dụng có session cookie, lấy Set-Cookie từ response login và gửi lại ở request sau; so sánh kết quả mock server và HTTP thật.
7. Nếu triển khai HTTPS, bổ sung test HTTP thật xác minh certificate và trust configuration.

Một bộ test WebTestClient tốt cần phân biệt rõ **logic của WebFlux/Spring Security** với **hành vi của HTTP server và mạng**. Mock server giúp kiểm tra nhanh pipeline trong application context; kết nối HTTP thật xác minh thêm connector, cookie, header, port và các thành phần vận chuyển. Chọn đúng cấp độ giúp kết quả test trả lời chính xác câu hỏi cần kiểm chứng.
