# Xây dựng REST API WebFlux với HTTP Basic và quyền theo vai trò

## 1. Yêu cầu bài thực hành và kết quả cuối

Bài thực hành tổng hợp này xây dựng REST API bằng **Spring Boot WebFlux** và bảo vệ API bằng **Spring Security Reactive**. Hai yêu cầu bảo mật là xác thực danh tính bằng **HTTP Basic** và phân quyền **Role-Based Access Control (RBAC)** cho từng HTTP method và đường dẫn. Sau khi hoàn thành, người học có thể chạy một ứng dụng Java 17+, gửi request bằng HTTP client, hiểu vì sao request được cho phép hoặc bị từ chối, và kiểm thử bằng `WebTestClient`.

Lab mô phỏng API quản lý bài viết `/api/articles`:

| Method và endpoint | Anonymous | READER | EDITOR | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/articles` | 401 | 200 | 200 | 200 |
| `GET /api/articles/{id}` | 401 | 200/404 | 200/404 | 200/404 |
| `POST /api/articles` | 401 | 403 | 201 | 201 |
| `DELETE /api/articles/{id}` | 401 | 403 | 403 | 204/404 |
| Method/endpoint chưa khai báo | Từ chối | Từ chối | Từ chối | Từ chối |

Ba tài khoản có username `reader`, `editor`, `admin` và authority tương ứng `ROLE_READER`, `ROLE_EDITOR`, `ROLE_ADMIN`. Password lấy từ biến môi trường lúc chạy lab, không hardcode giá trị thực vào repository.

Phạm vi minh họa: Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Reactor, JUnit 5. Lab sử dụng `ConcurrentHashMap` thay cho database để tập trung vào authentication/authorization; đây là kho dữ liệu tạm thời, mất dữ liệu sau restart. Trong production, cần thay bằng reactive persistence, quản lý user/secret chuyên dụng và bảo vệ TLS.

## 2. Kiến thức nền: HTTP Basic, role và chuỗi bảo mật reactive

HTTP Basic có header dạng:

~~~http
GET /api/articles HTTP/1.1
Host: localhost:8080
Authorization: Basic <base64(username:password)>
~~~

Chuỗi `<base64(username:password)>` là **ký pháp minh họa**. Base64 **không mã hóa bí mật**; server giải mã biểu diễn này để xác thực username/password, nên khi đi qua mạng phải dùng **HTTPS/TLS**. Trong browser, thông tin HTTP Basic có thể được cache và tự gửi lại; tuyệt đối không nhầm API HTTP Basic với OAuth2 Bearer token, JWT hoặc cơ chế session login.

Luồng Spring Security WebFlux:

~~~text
HTTP request
  -> WebFilterChainProxy / SecurityWebFilterChain
  -> HTTP Basic filter đọc Authorization
  -> ReactiveAuthenticationManager
  -> MapReactiveUserDetailsService tải UserDetails
  -> PasswordEncoder đối chiếu password với hash
  -> Authentication chứa principal + granted authorities
  -> authorizeExchange đối chiếu method/path và role
  -> controller Mono/Flux nếu được phép
  -> WebFlux subscribe Publisher và viết HTTP response
~~~

**Authentication** trả lời “ai đang gọi?”. Thiếu hoặc sai credential trên endpoint bảo vệ thường trả **401 Unauthorized** cùng `WWW-Authenticate: Basic...`. **Authorization** trả lời “người dùng đã xác thực có được làm thao tác này không?”. Thiếu quyền thường trả **403 Forbidden**. Khi đã vượt qua security nhưng tài nguyên không tồn tại, controller trả **404 Not Found**. Body POST sai dữ liệu trả **400 Bad Request**. Không biến các tình huống thành một loại lỗi duy nhất.

Trong Spring Security, `User.withUsername(...).roles("READER")` sinh authority `ROLE_READER`. Cấu hình `hasRole("READER")` kiểm authority đó; không truyền chuỗi `ROLE_READER` vào `hasRole`. Với `hasAuthority("SCOPE_read")` hay custom authority, cơ chế là khác: dùng đúng một mô hình và áp dụng nhất quán.

Ở WebFlux sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`; **không dùng** Servlet `HttpSecurity`, `SecurityFilterChain`, `UserDetailsService` blocking hoặc `MockMvc` để hiện thực bài reactive. SecurityContext trong luồng reactive gắn với Reactor Context.

## 3. Chuẩn bị dự án Gradle, package và cấu hình

Cấu trúc dự án:

~~~text
webflux-basic-rbac/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat
  src/main/java/example/webfluxbasic/
    BasicRbacApplication.java
    ApiSecurityConfig.java
    ArticleController.java
    PublicController.java
  src/main/resources/application.yml
  src/test/java/example/webfluxbasic/
    BasicRbacIntegrationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'webflux-basic-rbac'
~~~

File `build.gradle` cho một ứng dụng độc lập:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

Nếu dùng một repository Gradle đã có convention/plugin quản lý dependency, chỉ khai báo những dependency còn thiếu; không đè toàn bộ cấu hình build của module hiện hữu. Với Spring Boot 3.3.x, Java 17 là baseline tương thích; phiên bản plugin ở trên minh họa một bản 3.3 cụ thể.

File `src/main/java/example/webfluxbasic/BasicRbacApplication.java`:

~~~java
package example.webfluxbasic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicRbacApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicRbacApplication.class, args);
    }
}
~~~

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  users:
    reader-password: ${DEMO_READER_PASSWORD}
    editor-password: ${DEMO_EDITOR_PASSWORD}
    admin-password: ${DEMO_ADMIN_PASSWORD}
~~~

Các biến `DEMO_*` chỉ dành cho lab và phải được thiết lập khi chạy server. Không đặt default “password” công khai cho production. Khi chạy test ở mục 6, thuộc tính `demo.users.*` được test ghi đè, vì vậy không cần export các biến môi trường này để chạy test.

## 4. Cấu hình SecurityWebFilterChain và người dùng reactive

File `src/main/java/example/webfluxbasic/ApiSecurityConfig.java`:

~~~java
package example.webfluxbasic;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.users.reader-password}") String readerPassword,
            @Value("${demo.users.editor-password}") String editorPassword,
            @Value("${demo.users.admin-password}") String adminPassword) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode(readerPassword))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode(editorPassword))
            .roles("EDITOR")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(adminPassword))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, editor, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
            .authenticationManager(authenticationManager)
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/articles", "/api/articles/**")
                    .hasAnyRole("READER", "EDITOR", "ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/articles")
                    .hasAnyRole("EDITOR", "ADMIN")
                .pathMatchers(HttpMethod.DELETE, "/api/articles/**")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Diễn giải:

- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` mặc định dùng BCrypt và thêm prefix `{bcrypt}` khi tạo hash. Không so sánh password dạng plaintext; `ReactiveAuthenticationManager` sử dụng encoder để đối chiếu.
- `MapReactiveUserDetailsService` là nguồn user reactive ở lab, nhận ba `UserDetails` được gắn role thông qua `.roles(...)`. Không có “vai trò kế thừa” ngầm: admin được GET và POST vì matcher cho phép vai trò ADMIN, không phải tự được thừa hưởng READER/EDITOR.
- `httpBasic(...)` bật cơ chế xác thực header Basic; form login/logout mặc định bị tắt cho API. Không cần tự viết WebFilter parse `Authorization`.
- `NoOpServerSecurityContextRepository` không duy trì SecurityContext qua các request. Basic credentials vẫn phải xuất hiện trong request tiếp theo. Cấu hình này **không chứng minh** toàn bộ ứng dụng không bao giờ sử dụng WebSession từ các thành phần khác.
- Các `pathMatchers(HttpMethod,...)` ràng buộc vừa HTTP verb vừa URL. Quy tắc công khai được đặt rõ ràng; `anyExchange().denyAll()` chặn tất cả method/route chưa được cấp. Khi API mở rộng, cần cập nhật ma trận quyền và test.
- `csrf(...disable)` chỉ dành cho **lab dùng command-line/non-browser client**. Với trình duyệt, Basic credentials có thể được lưu và tự gửi, nên **không được mặc định tắt CSRF chỉ vì API không dùng cookie**. Hệ thống có browser cần đánh giá CSRF, Origin và cấu hình chain phù hợp.
- Basic được giữ qua TLS trong môi trường thực, không ghi access log chứa credential. Password tạo trong startup phục vụ demo; quản lý account production đòi kho xác thực an toàn, rotation và audit.

## 5. REST API reactive: controller và dữ liệu minh họa

File `src/main/java/example/webfluxbasic/ArticleController.java`:

~~~java
package example.webfluxbasic;

import java.net.URI;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {

    private final AtomicLong sequence = new AtomicLong(1);
    private final Map<Long, Article> articles = new ConcurrentHashMap<>();

    public ArticleController() {
        articles.put(1L, new Article(1L, "First article"));
    }

    @GetMapping
    public Flux<Article> all() {
        return Flux.defer(() -> Flux.fromIterable(articles.values())
            .sort(Comparator.comparingLong(Article::id)));
    }

    @GetMapping("/{id}")
    public Mono<Article> one(@PathVariable long id) {
        return Mono.defer(() -> Mono.justOrEmpty(articles.get(id)))
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Article not found")));
    }

    @PostMapping
    public Mono<ResponseEntity<Article>> create(
            @RequestBody Mono<ArticleInput> body) {

        return body.flatMap(input -> Mono.defer(() -> {
            if (input.title() == null || input.title().isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "title must not be blank"));
            }

            long id = sequence.incrementAndGet();
            Article article = new Article(id, input.title().trim());
            articles.put(id, article);

            return Mono.just(ResponseEntity
                .created(URI.create("/api/articles/" + id))
                .body(article));
        }));
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
        return Mono.fromSupplier(() -> {
            ResponseEntity<Void> response =
                articles.remove(id) == null
                    ? ResponseEntity.notFound().build()
                    : ResponseEntity.noContent().build();
            return response;
        });
    }

    public record Article(long id, String title) { }

    public record ArticleInput(String title) { }
}
~~~

Ví dụ tạo dữ liệu ban đầu ID 1 với tiêu đề `First article`. `GET /api/articles` trả mảng JSON; `GET /api/articles/1` trả object hoặc 404 nếu đã bị xóa. `POST` kiểm tra `title` không null/rỗng, tạo ID mới và trả `201 Created` cùng `Location: /api/articles/{id}`; DELETE trả 204 khi xóa được và 404 khi không có ID.

`Mono.defer` và `Mono.fromSupplier` làm cho thao tác đọc/ghi xảy ra vào lúc subscribe, thay vì tự thực thi trước khi Publisher được sử dụng. Dùng `ConcurrentHashMap` vì nhiều request WebFlux có thể chạy đồng thời; không mặc định phép cập nhật dữ liệu nghiệp vụ nhiều bước đã an toàn giao dịch chỉ vì Map thread-safe. Nếu dùng database thật, chọn R2DBC hoặc reactive driver phù hợp; tránh JDBC và `block()` trực tiếp trên event loop.

File `src/main/java/example/webfluxbasic/PublicController.java`:

~~~java
package example.webfluxbasic;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PublicController {

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

Không gắn `@PermitAll` hay phân quyền bổ sung chỉ để “lách” `SecurityWebFilterChain`; luật công khai đã thể hiện tại `GET /api/public/ping`. Mọi endpoint nhạy cảm nên được thử cả request hợp lệ và request thiếu role.

## 6. Kiểm thử xuyên suốt bằng WebTestClient

Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và `@AutoConfigureWebTestClient` để khởi động ứng dụng WebFlux với security chain thật và gửi Basic credentials qua HTTP test client. Việc dùng `mockUser()` hoặc `mockJwt()` chỉ kiểm phân quyền giả lập, **không kiểm chứng bước username/password Basic**; ở đây phải gửi `setBasicAuth` để đi qua `ReactiveAuthenticationManager`.

File `src/test/java/example/webfluxbasic/BasicRbacIntegrationTest.java`:

~~~java
package example.webfluxbasic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "demo.users.reader-password=reader-test-pass",
        "demo.users.editor-password=editor-test-pass",
        "demo.users.admin-password=admin-test-pass"
    })
@AutoConfigureWebTestClient
class BasicRbacIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsAccessibleWithoutCredentials() {
        client.get().uri("/api/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void protectedRouteWithoutCredentialsReturns401() {
        client.get().uri("/api/articles").exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void incorrectPasswordReturns401() {
        client.get().uri("/api/articles")
            .headers(h -> h.setBasicAuth("reader", "incorrect"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadSeedArticle() {
        client.get().uri("/api/articles/1")
            .headers(h -> h.setBasicAuth("reader", "reader-test-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("First article");
    }

    @Test
    void readerCannotCreate() {
        client.post().uri("/api/articles")
            .headers(h -> h.setBasicAuth("reader", "reader-test-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ArticleController.ArticleInput("Forbidden"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorCannotDelete() {
        client.delete().uri("/api/articles/1")
            .headers(h -> h.setBasicAuth("editor", "editor-test-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorCreatesAndAdminDeletes() {
        ArticleController.Article article = client.post()
            .uri("/api/articles")
            .headers(h -> h.setBasicAuth("editor", "editor-test-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ArticleController.ArticleInput("Temporary"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists(HttpHeaders.LOCATION)
            .expectBody(ArticleController.Article.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(article);

        client.delete().uri("/api/articles/" + article.id())
            .headers(h -> h.setBasicAuth("admin", "admin-test-pass"))
            .exchange()
            .expectStatus().isNoContent();
    }

    @Test
    void unknownMethodIsDeniedEvenForAdmin() {
        client.put().uri("/api/articles/1")
            .headers(h -> h.setBasicAuth("admin", "admin-test-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ArticleController.ArticleInput("Updated"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedReaderGets404ForMissingRecord() {
        client.get().uri("/api/articles/999999")
            .headers(h -> h.setBasicAuth("reader", "reader-test-pass"))
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

Test chỉ xóa record **do chính test tạo**, không xóa bản ghi mẫu ID 1. Điều đó tránh làm các test phụ thuộc thứ tự chạy. Bộ kiểm tra bao phủ public 200, anonymous/sai password 401, reader/editor thiếu quyền 403, editor tạo 201 và admin xóa 204, id không tồn tại 404, method chưa được cấp 403. Có thể thêm test POST title rỗng nhận 400 để chứng minh validation hoạt động sau authorization.

Trong REST API thực, 401 có thể kèm `WWW-Authenticate` challenge, 403 nghĩa là đã xác thực nhưng không có quyền, còn 404 là thiếu bản ghi sau khi được quyền thực hiện GET. Khi test thất bại, đọc request chính xác và kiểm `SecurityWebFilterChain` có thật sự được khởi tạo và áp đúng matcher hay không; đừng chỉ sửa kỳ vọng assertion cho test pass.

## 7. Chạy lab và kiểm tra bằng curl

Có thể chạy kiểm thử bằng Gradle Wrapper:

~~~text
Linux/macOS: ./gradlew test
Windows:     .\gradlew.bat test
~~~

Để chạy ứng dụng thực tế tại localhost, đặt mật khẩu trong terminal rồi chạy `bootRun`. Ví dụ trên **PowerShell**:

~~~powershell
$env:DEMO_READER_PASSWORD = 'reader-local-pass'
$env:DEMO_EDITOR_PASSWORD = 'editor-local-pass'
$env:DEMO_ADMIN_PASSWORD = 'admin-local-pass'
.\gradlew.bat bootRun
~~~

Mở một terminal khác, đặt lại các biến môi trường đó nếu muốn dùng biến trong lệnh `curl.exe`, rồi gửi lần lượt:

~~~powershell
curl.exe -i http://localhost:8080/api/public/ping
curl.exe -i http://localhost:8080/api/articles
curl.exe -i -u "reader:$env:DEMO_READER_PASSWORD" http://localhost:8080/api/articles
curl.exe -i -u "editor:$env:DEMO_EDITOR_PASSWORD" -X DELETE http://localhost:8080/api/articles/1
~~~

Trạng thái dự kiến theo thứ tự: `200`, `401`, `200`, `403`. Để thử POST trên PowerShell, tạo file `article.json` local chứa JSON:

~~~json
{"title":"Secured WebFlux"}
~~~

Sau đó chạy:

~~~powershell
curl.exe -i -u "editor:$env:DEMO_EDITOR_PASSWORD" -H "Content-Type: application/json" --data-binary "@article.json" http://localhost:8080/api/articles
~~~

Kết quả kỳ vọng: `201 Created`, có header `Location` chứa ID mới và body JSON có `id` cùng `title`. Dùng tài khoản admin để gọi `DELETE` với **ID vừa nhận được** sẽ trả `204` nếu bản ghi còn tồn tại. Không cố định ID khi đã gửi nhiều POST. Nếu dùng `curl` trong PowerShell 5.1, gọi `curl.exe` để tránh alias `Invoke-WebRequest`.

Những password trên là **giá trị giả dùng trong lab**. Không chạy HTTP Basic qua mạng thật mà không có TLS. Không lưu credential thực trong file lệnh, terminal history, source code, URL query hoặc log; với hệ thống sản xuất cần cơ chế cấp phát/rotation credential được quản lý.

## 8. Giải thích hành vi bảo mật và lỗi thường gặp

**Phân quyền theo method**: Security matcher phân biệt `GET /api/articles/1` và `DELETE /api/articles/1`; chỉ trùng URL không có nghĩa cùng quyền. `hasAnyRole("READER", "EDITOR", "ADMIN")` là allowlist cho GET, `hasAnyRole("EDITOR", "ADMIN")` cho POST, `hasRole("ADMIN")` cho DELETE. `ROLE_*` được gắn qua `User.roles`, nên các tên quyền trong matcher không kèm tiền tố.

**Deny by default**: `anyExchange().denyAll()` ở cuối khiến method chưa đăng ký bị chặn. Nếu thêm `PUT`, phải khai báo matcher rõ ràng và bổ sung negative tests cho reader. Không đặt một matcher `/api/**.permitAll()` trước luật bảo vệ hoặc cấu hình chain rộng vô tình bỏ qua kiểm tra.

**Password hashing**: không dùng `{noop}` cho mật khẩu thực. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` có thể tạo hash dạng `{bcrypt}...`; `UserDetailsRepositoryReactiveAuthenticationManager` được chỉ định encoder phù hợp. Nếu mọi password bị trả 401, kiểm tra thiếu prefix, cấu hình password, username, encoder và dấu cách trong biến môi trường.

**HTTP Basic không mã hóa**: Base64 bị đọc được khi dữ liệu bị nghe lén trên kết nối không TLS. Một browser còn có thể giữ Basic credentials và tự đính kèm, vì vậy việc **tắt CSRF không mặc nhiên an toàn**. Với API phục vụ browser và session/cookie hoặc browser Basic auth, phải đánh giá lại CSRF, CORS, Origin và các chain tương ứng. CORS không phải authentication/authorization và không thay thế CSRF.

**Không block event loop**: `Mono` và `Flux` không tự biến JDBC/blocking API thành non-blocking. Tránh `block()`, `Thread.sleep()`, thao tác file blocking trong handler WebFlux. Với DB thật, ưu tiên R2DBC/reactive driver hoặc cô lập blocking workload trên scheduler thích hợp; vẫn cần quản lý tài nguyên và latency.

**Chọn đúng security stack**: nếu thêm đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux`, ứng dụng Spring Boot có thể chọn MVC tùy cấu hình; lab yêu cầu chỉ dùng WebFlux. Nếu ứng dụng có nhiều `SecurityWebFilterChain`, phải kiểm `@Order` và `securityMatcher` để chắc request đi qua chain được thiết kế.

**Chính sách role không bằng quyền đối tượng**: Admin trong lab có quyền xóa mọi bài viết. Khi có tenant/ownership, cần thêm kiểm tra ở tầng service cho đúng dữ liệu và người sở hữu, không chỉ route. Các service phía sau gateway cũng phải tự bảo vệ trust boundary của mình.

**Dữ liệu in-memory và race**: `ConcurrentHashMap` chỉ phục vụ demo và không bền vững, không chia sẻ đa instance. `AtomicLong` sinh ID trong tiến trình, không thay thế database transaction. Test thật phải kiểm tra đồng thời, giới hạn quyền, phản hồi sau lỗi và tích hợp kho dữ liệu trong các bước mở rộng.

## 9. Ma trận nghiệm thu và bài tập mở rộng

| Ca kiểm thử | Caller | Request | Kỳ vọng |
| --- | --- | --- | --- |
| Public ping | Anonymous | GET `/api/public/ping` | 200 |
| Thiếu Basic | Anonymous | GET `/api/articles` | 401 |
| Sai password | reader / mật khẩu sai | GET `/api/articles` | 401 |
| Đọc đúng quyền | reader | GET `/api/articles/1` | 200 |
| Không đủ quyền tạo | reader | POST `/api/articles` | 403, không thêm record |
| Không đủ quyền xóa | editor | DELETE `/api/articles/1` | 403, không xóa record |
| Tạo đúng quyền | editor | POST body hợp lệ | 201, Location |
| Xóa đúng quyền | admin | DELETE id vừa tạo | 204 |
| Method chưa cấp | admin | PUT `/api/articles/1` | 403 |
| Tài nguyên không có | reader | GET `/api/articles/999999` | 404 |
| Body thiếu title | editor | POST body `{"title":""}` | 400 |

Tự mở rộng theo những bước có giá trị học tập:

1. Cài đặt `PATCH /api/articles/{id}` chỉ cho editor/admin; thêm test reader 403, editor thành công, admin thành công.
2. Thêm `ROLE_AUDITOR` chỉ được đọc và xác minh không bị cấp quyền POST/DELETE.
3. Kiểm tra quyền theo owner/tenant: editor chỉ sửa bài của mình, admin có quyền quản lý; không tin `ownerId` từ body do caller gửi.
4. Chuyển nguồn user sang `ReactiveUserDetailsService` lấy từ kho dữ liệu có hỗ trợ non-blocking; lưu hash mật khẩu đã tạo trước, không giữ password plaintext.
5. Bật reactive method security cho nghiệp vụ nhạy cảm và test cả bảo vệ HTTP lẫn bảo vệ service. Không dùng `@PreAuthorize` như cách thay thế tất cả kiểm tra quyền đối tượng.
6. Tách cấu hình cho API và UI nếu có browser session, đánh giá CSRF; test sự khác biệt của cookie/browser và Basic API.
7. Thêm audit tối thiểu gồm username, action, status, request ID nhưng không bao gồm Authorization header hay password. Bổ sung rate limiting và chống brute force theo yêu cầu triển khai.

## 10. Checklist kiến thức và triển khai an toàn

- [ ] WebFlux dùng `ServerHttpSecurity` và `SecurityWebFilterChain`, không lẫn Servlet security API.
- [ ] HTTP Basic hoạt động bằng `setBasicAuth` trong `WebTestClient`, có kiểm 401 khi thiếu/sai password.
- [ ] Mật khẩu được hash, username được tải qua `MapReactiveUserDetailsService` và xác minh bằng `ReactiveAuthenticationManager`.
- [ ] Role `READER`, `EDITOR`, `ADMIN` được ánh xạ rõ sang authority `ROLE_*`.
- [ ] Route GET/POST/DELETE áp đúng quyền, route công khai chỉ công khai phần đã phê duyệt.
- [ ] `anyExchange().denyAll()` giữ vai trò chặn mặc định.
- [ ] Có cả positive tests (200/201/204) và negative tests (401/403), thêm 400/404 theo hợp đồng API.
- [ ] Controller reactive trả `Mono`/`Flux`, không gọi blocking API trên event loop.
- [ ] Dữ liệu demo in-memory được phân biệt với hệ lưu trữ có giao dịch thực.
- [ ] Chỉ tắt CSRF trong lab/API đã đánh giá điều kiện sử dụng, không suy luận Basic stateless luôn an toàn trước CSRF.
- [ ] Không truyền HTTP Basic qua mạng không mã hóa; secret thực không nằm trong Git/log/test sample production.
- [ ] Quyền theo owner/tenant phải được kiểm tra ở tầng nghiệp vụ nếu có đối tượng dữ liệu.

**Thông điệp quan trọng:** Spring Security WebFlux giải quyết việc xác thực bằng HTTP Basic và phân quyền bằng `authorizeExchange` trước khi chuyển request tới controller. Một REST API chỉ an toàn khi **từng method và resource có policy rõ ràng**, người dùng thiếu quyền bị chặn, password được xử lý an toàn, và toàn bộ quyết định được chứng minh bằng cả test thành công lẫn test từ chối.

## Tài liệu tham khảo

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot — WebFlux Testing](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
