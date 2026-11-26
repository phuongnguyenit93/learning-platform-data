# bindToApplicationContext và cấu hình WebFlux kiểm thử

## 1. Dựng WebTestClient từ application context

Trong chương **Thiết lập WebTestClient** của module **SPRING_SECURITY_TESTING**, WebTestClient có thể được dựng trực tiếp từ **Reactive ApplicationContext** để kiểm tra controller, router và WebFilter trong cùng pipeline của ứng dụng. Cách này hữu ích khi cần kiểm tra Spring Security WebFlux mà không khởi động HTTP server hoặc mở cổng TCP.

Với **WebTestClient.bindToApplicationContext(context)**, Spring Test tìm WebHandler trong application context và dựng một mock web server trong bộ nhớ. Để các quy tắc bảo mật được áp dụng, cần tích hợp **SecurityWebFilterChain** vào mock client bằng **apply(springSecurity())** từ spring-security-test.

Bài này tập trung vào cấu hình WebFlux test theo application context và cách xác minh filter chain thực sự chạy. Sau bài học, bạn có thể:

- Dựng WebTestClient từ Reactive ApplicationContext.
- Tích hợp Spring Security WebFlux bằng springSecurity().
- Phân biệt bindToApplicationContext với bindToController và bindToServer.
- Kiểm tra endpoint công khai, endpoint yêu cầu xác thực và endpoint yêu cầu role.
- Dùng HTTP Basic credentials trong mock exchange và dùng mockUser() cho test authorization.
- Kiểm tra CSRF cho request thay đổi trạng thái.
- Nhận biết những gì mock application context test không chứng minh về HTTP connector và mạng.

## 2. ApplicationContext cần có những thành phần nào?

Một ứng dụng WebFlux có thể gồm các thành phần chính sau:

| Thành phần | Vai trò |
| --- | --- |
| **Reactive ApplicationContext** | Chứa bean, cấu hình WebFlux, controller/router và các thành phần bảo mật |
| **WebHandler** | Điểm vào xử lý request của WebFlux |
| **WebFilter** | Xử lý request/response trong pipeline Reactive |
| **SecurityWebFilterChain** | Chứa các WebFilter và quy tắc xác thực, phân quyền của Spring Security |
| **WebTestClient** | Gửi request kiểm thử và kiểm tra response |
| **springSecurity()** | Gắn cấu hình Spring Security vào WebTestClient mock được dựng từ context |

Với Spring Security WebFlux, cấu hình bảo mật thường được khai báo bằng **@EnableWebFluxSecurity** và một bean **SecurityWebFilterChain**. Khi dựng mock client từ application context, cần bảo đảm context test thực sự chứa bean này.

~~~mermaid
flowchart TD
    A["Reactive ApplicationContext"] --> B["WebHandler"]
    A --> C["SecurityWebFilterChain"]
    A --> D["Controller / RouterFunction"]
    E["WebTestClient.bindToApplicationContext(context)"] --> F["Mock Web server trong bộ nhớ"]
    F --> G["WebHandler"]
    G --> H["WebFilter pipeline"]
    H --> I["Spring Security WebFilter chain"]
    I --> J["Controller / RouterFunction"]
    J --> K["Response trả về test"]
    C -. "apply(springSecurity())" .-> I
~~~

**bindToApplicationContext không tự động có nghĩa mọi bean bảo mật đã được áp dụng đúng.** Hãy dùng springSecurity() khi dựng mock client và xác minh một request anonymous bị chặn. Nếu test vẫn trả 200 cho endpoint cần xác thực, kiểm tra xem SecurityWebFilterChain có trong context và đã được gắn vào client hay chưa.

## 3. Phân biệt ba cách bind thường dùng

| Cách dựng | Phạm vi | Có dùng toàn bộ ApplicationContext? | Có HTTP server/socket thật? |
| --- | --- | --- | --- |
| **bindToController(...)** | Controller được chỉ định | Không | Không |
| **bindToApplicationContext(...)** | WebHandler, WebFilter và handler từ context | Có | Không |
| **bindToServer()** | Kết nối tới server đang chạy | Server có context riêng | Có |

### bindToController

Cách này thích hợp cho kiểm thử controller hẹp. Nó không tự nạp toàn bộ cấu hình ứng dụng, nên không được mặc định rằng các WebFilter hoặc SecurityWebFilterChain production đã tham gia request. Nếu muốn kiểm tra security, cần tự cấu hình pipeline hoặc dùng application context.

### bindToApplicationContext

Cách này dựng mock WebFlux server từ context hiện có. Đây là lựa chọn phù hợp khi cần kiểm tra sự phối hợp giữa controller, WebFilter và Spring Security trong cấu hình ứng dụng. **apply(springSecurity())** kết nối SecurityWebFilterChain vào mock client.

### bindToServer

Cách này gửi request qua HTTP connector tới server đang chạy. Nó phù hợp để kiểm tra port, connector, serialization qua HTTP, TLS và hành vi cookie/header ở cấp vận chuyển. Nó không dùng apply(springSecurity()) vì filter chain đã chạy bên trong server.

Bài này dùng **bindToApplicationContext** để tập trung vào cấu hình WebFlux test. Mock server vẫn chạy pipeline ứng dụng trong bộ nhớ, nhưng không mở socket và không kiểm tra TLS hay reverse proxy.

## 4. Cấu hình WebFlux mẫu

Ví dụ dùng **Spring Boot 3.x**, **Spring Security 6.x**, Spring WebFlux, JUnit 5 và spring-security-test. Các dependency chính:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Nếu mục tiêu là ứng dụng WebFlux thuần, không thêm spring-boot-starter-web cùng lúc. Khi cả MVC và WebFlux starter cùng có mặt, Spring Boot có thể chọn MVC làm application type tùy cấu hình.

### 4.1. SecurityWebFilterChain

Cấu hình dưới đây cho phép truy cập /public, yêu cầu role USER cho /api/profile, role ADMIN cho /api/admin, và từ chối các route còn lại.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
                .pathMatchers(HttpMethod.GET, "/api/profile").hasRole("USER")
                .pathMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/action").hasRole("USER")
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

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin-secret")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }
}
~~~

Mật khẩu {noop} chỉ dùng cho ví dụ kiểm thử. Ứng dụng thực tế cần PasswordEncoder phù hợp và nguồn người dùng an toàn.

CSRF protection của WebFlux được bật theo mặc định. Các GET trong ví dụ không cần CSRF token; request POST /api/action cần token hợp lệ. Không tắt CSRF chỉ để làm test đơn giản hơn nếu ứng dụng sử dụng credentials mà trình duyệt tự động gửi.

### 4.2. Controller Reactive

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiController {

    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/profile")
    Mono<String> profile(Principal principal) {
        return Mono.just(principal.getName());
    }

    @GetMapping("/api/admin")
    Mono<String> admin(Principal principal) {
        return Mono.just("admin:" + principal.getName());
    }

    @PostMapping("/api/action")
    Mono<String> action(Principal principal) {
        return Mono.just("accepted:" + principal.getName());
    }
}
~~~

Các handler trả về **Mono** để phù hợp với mô hình Reactive. Principal được cung cấp theo SecurityContext của request. Nếu request chưa được xác thực, Spring Security chặn request trước khi controller được gọi.

## 5. Dựng WebTestClient bằng bindToApplicationContext

Đây là cấu hình trung tâm của bài học:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class WebTestClientContextTest {

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
}
~~~

Giải thích từng bước:

1. **@SpringBootTest(webEnvironment = MOCK)** nạp application context nhưng không khởi động HTTP server thật.
2. **@Autowired ApplicationContext** lấy context đã chứa controller, WebFlux infrastructure và SecurityWebFilterChain.
3. **bindToApplicationContext(applicationContext)** dựng mock WebTestClient dựa trên context.
4. **apply(springSecurity())** gắn WebFlux security chain vào mock exchange.
5. **configureClient().build()** hoàn tất client để các test dùng chung.

Với cách dựng thủ công này, không cần **@AutoConfigureWebTestClient** để Spring Boot tự inject một client. Test tự tạo client trong **@BeforeEach**. Nếu dùng **@WebFluxTest** thay vì **@SpringBootTest**, cần bảo đảm cấu hình bảo mật và các bean phụ thuộc được đưa vào slice bằng **@Import** hoặc cơ chế cấu hình phù hợp.

## 6. Kiểm thử anonymous và HTTP Basic

HTTP Basic trong ví dụ cho phép kiểm tra credentials được gửi qua request. Dù là mock server, request vẫn chạy qua AuthenticationWebFilter và ReactiveUserDetailsService đã cấu hình.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

@Test
void publicEndpointDoesNotRequireAuthentication() {
    client.get()
            .uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
}

@Test
void anonymousCannotReadProfile() {
    client.get()
            .uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
}

@Test
void validBasicCredentialsCanReadProfile() {
    client.get()
            .uri("/api/profile")
            .headers(headers -> headers.setBasicAuth("alice", "secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
}

@Test
void invalidBasicCredentialsAreRejected() {
    client.get()
            .uri("/api/profile")
            .headers(headers -> headers.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
}
~~~

Các phương thức test này nằm trong **WebTestClientContextTest** ở mục trước, nơi client được dựng trong setUp(). Có thể bỏ import không dùng; việc dựng client đã gọi bindToApplicationContext qua WebTestClient.

**Điểm quan trọng:** **setBasicAuth(...)** gửi credentials vào request. Spring Security vẫn phải xác minh username/password qua AuthenticationManager và ReactiveUserDetailsService. Đây là test xác thực bằng credentials trong mock pipeline, khác với việc gắn một Authentication giả lập bằng mockUser().

## 7. Dùng mockUser() cho kiểm thử authorization

Khi câu hỏi chỉ là “người dùng có role USER có truy cập được endpoint này không?”, có thể dùng **mockUser()**. Configurer này chuẩn bị SecurityContext cho mock exchange để test quy tắc authorization mà không cần lặp lại quá trình xác thực HTTP Basic.

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void mockUserWithUserRoleCanReadProfile() {
    client.mutateWith(mockUser("alice").roles("USER"))
            .get()
            .uri("/api/profile")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
}

@Test
void mockUserWithoutAdminRoleCannotReadAdminEndpoint() {
    client.mutateWith(mockUser().roles("USER"))
            .get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden();
}

@Test
void mockAdminCanReadAdminEndpoint() {
    client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin:admin");
}
~~~

**mockUser() không kiểm tra password, Basic header hoặc UserDetailsService.** Nó phù hợp với authorization test. Khi cần chứng minh credentials thực được xác minh, hãy dùng request HTTP Basic ở mục 6. Không dùng mockUser() để kết luận rằng login filter hoặc xác thực production đang hoạt động.

## 8. Kiểm thử CSRF cho request thay đổi trạng thái

WebFlux security bật CSRF protection mặc định. Request POST /api/action thiếu token hợp lệ bị từ chối trước khi handler thực thi. Có thể dùng configurer **csrf()** của spring-security-test để thêm token cho mock request.

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void postWithoutCsrfIsForbidden() {
    client.mutateWith(mockUser().roles("USER"))
            .post()
            .uri("/api/action")
            .exchange()
            .expectStatus().isForbidden();
}

@Test
void postWithCsrfAndAuthenticatedUserIsAccepted() {
    client.mutateWith(mockUser().roles("USER"))
            .mutateWith(csrf())
            .post()
            .uri("/api/action")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("accepted:user");
}
~~~

CSRF configurer tạo token test hợp lệ theo cơ chế Reactive. Trong ứng dụng thực tế, client cần gửi token theo cách mà ứng dụng cấu hình, thường là cookie/header hoặc form parameter. Nếu API dùng bearer token trong Authorization header do client chủ động đặt, chính sách CSRF có thể được cấu hình khác; hãy đánh giá dựa trên cách credentials được trình duyệt gửi.

## 9. Khi dùng bindToController hoặc WebFlux slice test

### bindToController không tự mang cấu hình security của context

Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new ApiController())
        .build();
~~~

Client này kiểm thử controller được chỉ định. Nó không tự động nạp bean SecurityWebFilterChain từ application context. Nếu mục tiêu là kiểm tra bảo mật của ứng dụng, dùng bindToApplicationContext(...).apply(springSecurity()) hoặc tự dựng đầy đủ filter chain cần thiết.

### @WebFluxTest cần import security configuration

**@WebFluxTest** chỉ nạp một phần cấu hình ứng dụng. Nếu cấu hình bảo mật không nằm trong slice, test có thể không thấy SecurityWebFilterChain hoặc UserDetailsService. Có thể đưa cấu hình cần thiết vào bằng **@Import(SecurityConfig.class)** và cung cấp mock/stub cho các bean ngoài phạm vi slice.

Không nên thêm một cấu hình test mở toàn bộ endpoint chỉ để test controller, rồi dùng kết quả đó làm bằng chứng endpoint production được bảo vệ. Hãy kiểm tra đúng security configuration mà ứng dụng dự định triển khai.

## 10. Những gì bindToApplicationContext không kiểm chứng

| Hạng mục | Có thể kiểm tra bằng mock context? | Cần HTTP server thật? |
| --- | --- | --- |
| Controller, RouterFunction | Có | Không bắt buộc |
| WebFilter và SecurityWebFilterChain | Có, khi cấu hình đầy đủ | Không bắt buộc |
| Authentication và authorization trong pipeline | Có | Không bắt buộc |
| HTTP Basic header trong mock exchange | Có thể kiểm tra cách ứng dụng xử lý header | Cần server thật nếu kiểm tra connector/wire |
| TCP socket và port binding | Không | Có |
| TLS handshake và certificate | Không | Có |
| Connector, compression và server-specific behavior | Không đầy đủ | Có |
| Cookie qua HTTP connector và client cookie jar | Kiểm tra response logic được | Có nếu cần xác minh vận chuyển thực |
| Reverse proxy/load balancer | Không | Có trong môi trường tích hợp tương ứng |

Mock context test là bằng chứng tốt cho WebFlux pipeline và security rules trong application context. Nó không chứng minh server thật đã khởi động, TLS đúng, cookie được browser xử lý đúng hay reverse proxy chuyển tiếp header chính xác. Khi cần những bằng chứng đó, bổ sung test bằng **@SpringBootTest(webEnvironment = RANDOM_PORT)** hoặc **bindToServer()**.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Anonymous vẫn truy cập endpoint cần xác thực | Chưa gọi apply(springSecurity()), context không có SecurityWebFilterChain hoặc matcher sai | Kiểm tra bean chain và mock client setup |
| springSecurity() không tìm thấy chain | Test slice không import cấu hình WebFlux security | Dùng @Import hoặc @SpringBootTest phù hợp |
| HTTP Basic luôn 401 | Sai username/password, UserDetailsService không được nạp hoặc password format không hợp lệ | Kiểm tra user bean và PasswordEncoder |
| mockUser test 200 nhưng Basic credentials sai | mockUser bỏ qua xác minh credentials | Dùng test HTTP Basic riêng |
| Role USER vẫn truy cập admin | Dùng nhầm authorities()/roles() hoặc matcher sai | Nhớ roles("ADMIN") tạo authority ROLE_ADMIN |
| POST trả 403 dù user có role | Thiếu CSRF token | Dùng mutateWith(csrf()) trong test |
| Controller không được tìm thấy | bindToController hoặc test slice không nạp handler mong muốn | Dùng đúng application context và mapping |
| Mock test qua nhưng HTTP thật lỗi | Connector, port, TLS, cookie hoặc serialization | Thêm test RANDOM_PORT/bindToServer |

## 12. Bài tập thực hành

1. Dựng client bằng bindToApplicationContext và springSecurity(). Gửi request anonymous tới /api/profile và xác minh 401.
2. Gửi HTTP Basic credentials hợp lệ và không hợp lệ. So sánh kết quả authentication.
3. Dùng mockUser().roles("USER") để đọc profile và gọi admin endpoint; xác minh lần lượt 200 và 403.
4. Gửi POST /api/action không có CSRF token rồi thêm csrf(). So sánh response.
5. Tạm bỏ apply(springSecurity()) trong một test riêng và quan sát vì sao kết quả không còn chứng minh SecurityWebFilterChain.
6. Chuyển test sang @WebFluxTest, import SecurityConfig và UserDetailsService cần thiết; kiểm tra filter chain vẫn được áp dụng.
7. Viết một test RANDOM_PORT riêng để so sánh cùng request qua HTTP connector thật.

Một WebTestClient được dựng từ application context có thể kiểm tra sâu controller, WebFilter và Spring Security WebFlux trong một pipeline thống nhất. Bằng chứng đáng tin cậy cần xác nhận **đúng context, đúng SecurityWebFilterChain, đúng cách gắn security vào client và đúng loại Authentication mà test muốn kiểm tra**. Khi phân biệt rõ mock principal với credentials thực, test sẽ cho biết chính xác ứng dụng đang bảo vệ endpoint ra sao.
