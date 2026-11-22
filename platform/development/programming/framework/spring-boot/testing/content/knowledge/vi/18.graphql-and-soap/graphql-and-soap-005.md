# HttpGraphQlTester và kiểm chứng transport, authentication trong Spring Boot

Một GraphQL resolver có thể trả dữ liệu đúng khi gọi trực tiếp nhưng endpoint **POST /graphql** ngoài mạng vẫn sai: HTTP path không được map, Content-Type không được nhận, Authorization header bị mất, Spring Security trả 401/403 trước khi vào GraphQL, hoặc tài khoản đã đăng nhập lại được phép đọc field vượt quyền. Vì vậy, khi đề bài là **HttpGraphQlTester và kiểm chứng transport, authentication**, không thể chỉ assert giá trị do phương thức **@QueryMapping** trả về.

**HttpGraphQlTester** của Spring for GraphQL dùng **WebTestClient** để gửi GraphQL request qua **HTTP transport**. Điểm rất quan trọng: cùng một API HttpGraphQlTester có thể chạy với WebTestClient **bindToServer** (HTTP server thật) hoặc client gắn với mock web stack (không có socket thật). Muốn chứng minh routing, HTTP authentication và response trên port đang chạy, bài test phải chủ động cấu hình **bindToServer** cùng **@SpringBootTest(webEnvironment = RANDOM_PORT)**; khi cần assert HTTP 401, 403, 415 hoặc headers, nên giữ một WebTestClient thô để kiểm tra tầng transport.

Bài thực hành dùng **Java 17, Spring Boot 3.4.5, Spring for GraphQL được Spring Boot quản lý, Spring Security, JUnit Jupiter và Gradle**. Tất cả user/password đều là dữ liệu mẫu cục bộ; không dùng mẫu lưu mật khẩu này trong production.

## 1. Ba tầng kiểm chứng của một GraphQL HTTP request

Một request GraphQL qua HTTP thường trông như sau:

~~~http
POST /graphql HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Authorization: Basic <base64-of-test-credentials>

{
  "query": "query Greet($name: String!) { greeting(name: $name) }",
  "operationName": "Greet",
  "variables": { "name": "Lan" }
}
~~~

Dòng Authorization trong ví dụ là mô tả format, không phải credentials có thể dùng. Phía server xử lý theo các tầng:

~~~text
HTTP client / HttpGraphQlTester
         |
         v
TCP + HTTP: path, method, headers, Content-Type, JSON body
         |
         v
Servlet filters / Spring Security
  - Xác thực identity từ Authorization
  - Cho phép/chặn request vào /graphql
  - Có thể trả HTTP 401/403 trước GraphQL engine
         |
         v
Spring GraphQL HTTP handler
  - Đọc query, variables, operationName
  - Validation GraphQL document và execute resolver
  - Có thể trả HTTP 200 với "data" và "errors"
         |
         v
DataFetcher / @QueryMapping / service
  - Business result
  - Field-level method authorization (nếu cấu hình)
         |
         v
GraphQL response qua HTTP
~~~

Có ba loại bằng chứng khác nhau:

| Tầng | Câu hỏi | Công cụ thích hợp |
| --- | --- | --- |
| GraphQL execution | Query/variables/schema/resolver trả data và GraphQL errors đúng không? | **GraphQlTester** hoặc HttpGraphQlTester |
| HTTP transport | URL, method, Content-Type, HTTP status, response headers, security filters đúng không? | **WebTestClient** trực tiếp; HttpGraphQlTester cho request HTTP thành công |
| Authentication/authorization | Anonymous, wrong credentials, role sai, field bị giới hạn có bị chặn đúng chỗ không? | WebTestClient cho **HTTP 401/403**, HttpGraphQlTester hoặc WebTestClient cho **GraphQL errors** |

**Không nhầm HTTP 200 với thành công nghiệp vụ.** GraphQL có thể trả status HTTP 200 kèm trường **errors** khi một data fetcher không thực hiện được. Ngược lại, HTTP 401 hoặc 403 do Spring Security chặn request trước GraphQL thường không có cấu trúc GraphQL response đầy đủ.

## 2. HttpGraphQlTester khác GraphQlTester và WebTestClient như thế nào?

**GraphQlTester** là API chung để viết document, đặt variables, execute và assert GraphQL data/errors. **HttpGraphQlTester** là biến thể dùng WebTestClient để thực hiện GraphQL request bằng HTTP. **WebTestClient** là client HTTP tổng quát, dùng để assert status, headers, cookies và raw body.

| Công cụ | Có HTTP transport? | Có socket thật? | Ưu thế | Không thay thế được |
| --- | --- | --- | --- | --- |
| ExecutionGraphQlServiceTester | Không, gọi service GraphQL trong server | Không | Test schema/resolvers/data fetchers | HTTP security filter, network |
| WebGraphQlTester | Đi qua WebGraphQlHandler, không cần network client | Không | Test WebGraphQlInterceptor/headers và execution | Socket/real transport |
| HttpGraphQlTester với MockMvcWebTestClient | HTTP semantics qua mock MVC | **Không** | Web handler/filter trong mock context | Real TCP port/container |
| **HttpGraphQlTester với WebTestClient.bindToServer** | **Có HTTP** | **Có**, nếu server thật đang chạy | GraphQL documents/variables/data qua real HTTP | Kiểm tra tùy ý raw HTTP statuses như 401/403 một cách thuận tiện |
| **WebTestClient.bindToServer trực tiếp** | **Có HTTP** | **Có** | HTTP 401/403, content negotiation, raw JSON errors, headers | Cú pháp assertion chuyên biệt GraphQL |

Một số ví dụ dùng **@GraphQlTest**. Đây là **GraphQL test slice**, thường cấu hình GraphQlTester hoặc execution tester để kiểm tra GraphQL mà không mở server. Nó hợp với schema/resolver logic, **không chứng minh** endpoint thực tại /graphql đã qua Spring Security HTTP filter.

### Hai cách cấu hình HttpGraphQlTester đều hợp lệ

**Đưa WebTestClient đã tạo sẵn vào tester:**

~~~java
WebTestClient transport = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port + "/graphql")
        .build();

HttpGraphQlTester tester = HttpGraphQlTester.create(transport);
~~~

**Hoặc đưa WebTestClient.Builder vào builder của tester:**

~~~java
HttpGraphQlTester tester = HttpGraphQlTester.builder(
        WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port + "/graphql"))
        .headers(headers ->
                headers.setBasicAuth("reader", "reader-pass"))
        .build();
~~~

Hai đoạn trên là **trích đoạn**, cần import đúng WebTestClient và HttpGraphQlTester, và biến port từ @LocalServerPort. **create(WebTestClient)** và **builder(WebTestClient.Builder)** là API của HttpGraphQlTester 1.3.x, tương thích với dòng Spring Boot 3.4.x trong ví dụ.

**Không hard-code port 8080** trong test RANDOM_PORT: lấy port thật từ @LocalServerPort, rồi tạo URL. Đừng nhầm base URL là http://host:port và http://host:port/graphql; với tester chuyên dụng, base URL phải trỏ đúng endpoint GraphQL.

## 3. Quy tắc quan trọng của transport: HTTP errors và GraphQL errors

Cùng từ **“error”** nhưng có hai loại:

**A. HTTP-layer rejection**, thường trước khi GraphQL engine thực thi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="..."
~~~

Hoặc:

~~~http
HTTP/1.1 403 Forbidden
~~~

HTTP 401 thường có nghĩa chưa có identity hợp lệ/credentials sai; HTTP 403 thường có nghĩa identity đã được xác thực nhưng không được phép truy cập tài nguyên HTTP này. Content body có thể do Spring Security, Boot ErrorController, custom entry point hoặc reverse proxy định nghĩa. **Không giả định response 401/403 luôn là GraphQL JSON** có trường errors.

**B. GraphQL execution error sau HTTP request được chấp nhận:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": { "secret": null },
  "errors": [
    {
      "message": "generic execution error",
      "path": ["secret"]
    }
  ]
}
~~~

Đây là **minh họa cấu trúc**, không cam kết server/framework dùng message hoặc Content-Type y hệt. Khi data fetcher báo lỗi nhưng GraphQL execution hoàn tất theo protocol, HTTP 200 với errors có thể là response hoàn toàn hợp lệ. Với GraphQL-over-HTTP, HTTP status còn phụ thuộc giai đoạn lỗi và content negotiation; không áp dụng quy tắc “mọi lỗi GraphQL đều HTTP 200” cho request malformed, validation trước execution hoặc media types khác.

**Quy tắc chọn assertion:** nếu muốn chứng minh security filter từ chối request tới /graphql, dùng WebTestClient.expectStatus().isUnauthorized() hoặc isForbidden(). Nếu muốn chứng minh resolver/field bị chặn trong một GraphQL operation đã được HTTP cho phép, dùng HttpGraphQlTester.execute().errors() hoặc raw HTTP assert status+errors.

### GraphQlTester mặc định quan tâm tới errors

Khi assert **.path("greeting").entity(String.class).isEqualTo(...)**, GraphQlTester cũng có logic xác minh GraphQL errors; một payload có errors không nên bị coi là thành công chỉ vì một data path vẫn có giá trị.

Muốn **kỳ vọng có GraphQL errors**, dùng:

~~~java
tester.document("{ secret }")
        .execute()
        .errors()
        .satisfy(errors ->
                assertFalse(errors.isEmpty()));
~~~

**.errors().satisfy(...)** cho phép kiểm tra danh sách lỗi và thừa nhận lỗi ấy là kỳ vọng. Có thể dùng **.errors().expect(predicate).verify()** để kiểm tra một loại lỗi/thuộc tính theo contract. Nếu ứng dụng cần kiểm tra partial data cùng errors, xử lý errors tường minh rồi mới assert những data paths còn hợp lệ.

Không dùng **.errorFilter(error -> true)** toàn cục chỉ để bỏ qua tất cả errors; cách đó có thể biến lỗi không mong đợi thành test xanh.

## 4. Authentication qua HTTP và authorization ở field là hai tầng khác nhau

Spring Security có thể bảo vệ **POST /graphql** bằng **SecurityFilterChain**. Cấu hình URL-level matcher chỉ nhìn thấy HTTP method/path, nên nó thường không biết bên trong GraphQL document đang đọc **greeting** hay **secret**. Vì tất cả query có thể được gửi tới cùng một URL, chỉ dùng URL matcher không đủ để phân quyền theo field.

Ví dụ chính sách minh họa:

- **Anonymous**: POST /graphql không có Basic credentials -> HTTP **401**.
- **reader** với ROLE_READER: POST /graphql được HTTP chấp nhận; query greeting thành công.
- **guest** với ROLE_GUEST: POST /graphql bị filter chain từ chối -> HTTP **403**.
- **admin** với ROLE_ADMIN: POST /graphql được phép; có quyền đọc field secret.
- **reader** query field secret: HTTP request được chấp nhận, nhưng service method dùng **@PreAuthorize("hasRole('ADMIN')")** từ chối tại tầng data fetching. Kết quả có thể là **HTTP 200 với GraphQL errors**.
- **admin** query secret: trả **secret-for-admin**, không có GraphQL errors.

**@EnableMethodSecurity** là bắt buộc để kích hoạt các annotation @PreAuthorize trong ví dụ; chỉ thêm spring-boot-starter-security không tự bật method security. Đặt annotation ở **Spring-managed service method**, không chỉ là một private method trong cùng class hoặc self-invocation, để AOP proxy có thể chặn method call.

**CSRF:** với một ứng dụng browser có session/cookie, POST GraphQL có thể bị CSRF protection chặn (HTTP 403) trước khi authentication/authorization GraphQL diễn ra. Ví dụ dùng Basic Auth cho một API thử nghiệm và **chỉ bỏ qua CSRF với path /graphql** để tập trung vào authentication và roles. Quyết định này **không phải mặc định production**; nếu dùng cookie-based auth, phải xem kỹ rủi ro CSRF và kiểm thử CSRF token. Không tắt toàn bộ security chỉ để test pass.

## 5. Dự án runnable: Spring Boot 3.4.5 + GraphQL + Spring Security

Ví dụ dưới đây dùng Spring MVC servlet stack. Thêm **spring-boot-starter-webflux ở testImplementation** để có WebTestClient + HTTP client implementation cho test; ứng dụng **vẫn là MVC** vì spring-boot-starter-web có mặt và Spring Boot ưu tiên MVC khi cả MVC/WebFlux ở classpath. Không cần mở WebFlux server riêng.

Cây file:

~~~text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/resources/graphql/schema.graphqls
src/main/java/com/example/graphqlsecure/GraphQlSecureApplication.java
src/main/java/com/example/graphqlsecure/SecurityConfig.java
src/main/java/com/example/graphqlsecure/GreetingGraphQlController.java
src/main/java/com/example/graphqlsecure/SecretService.java
src/test/java/com/example/graphqlsecure/GraphQlHttpTransportTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'secure-graphql-http-testing'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Giải thích dependencies:**

- **spring-boot-starter-graphql** có Spring for GraphQL runtime; classpath có schema GraphQL.
- **spring-boot-starter-web** khiến ứng dụng dùng Spring MVC servlet HTTP endpoint.
- **spring-boot-starter-security** đưa servlet security filter chain/Basic Auth.
- **spring-graphql-test** mới chứa HttpGraphQlTester/GraphQlTester; starter-test **không bảo đảm** có tester chuyên GraphQL.
- **spring-boot-starter-webflux** chỉ ở test classpath để WebTestClient có transport implementation. Không cần đổi ứng dụng thành WebFlux, không dùng @WebFluxTest.
- Spring Boot BOM chọn các phiên bản Spring/Spring GraphQL/Spring Security tương thích; không gắn một reactor-netty/webflux version tùy tiện khác BOM.

**src/main/resources/application.yml**

~~~yaml
spring:
  graphql:
    path: /graphql
    graphiql:
      enabled: false
~~~

Đường endpoint GraphQL trong ví dụ là **POST /graphql**. Tắt GraphiQL UI để không sinh UI không cần thiết trong demo. GraphiQL là developer tool, không phải endpoint thực thi GraphQL; không mở nó trên production chỉ vì một bài test cần gọi query.

### 5.1. GraphQL schema

**src/main/resources/graphql/schema.graphqls**

~~~graphql
type Query {
  greeting(name: String!): String!
  secret: String
}
~~~

**greeting(name:)** bắt buộc truyền String không null. **secret** nullable để khi data fetcher bị từ chối, GraphQL có thể trả **data.secret = null** cùng một entry errors thay vì null-propagation của non-null field làm toàn bộ data trở thành null. Đây là lựa chọn có chủ đích để minh họa **GraphQL execution error**.

Không có schema field nào dùng HTTP response status; những thông tin đó thuộc tầng transport/security bên ngoài GraphQL. SOAP có XML envelope/SOAPAction và fault semantics riêng, không dùng HttpGraphQlTester để kiểm thử SOAP transport.

### 5.2. Application class

**src/main/java/com/example/graphqlsecure/GraphQlSecureApplication.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlSecureApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlSecureApplication.class, args);
    }
}
~~~

Đặt các class và schema đúng path để Spring Boot tự phát hiện GraphQL schema ở classpath:graphql/** và tự đăng ký GraphQL HTTP handler ở /graphql. Các đoạn Java compile dựa trên Java 17 và dependencies của build.gradle.

### 5.3. SecurityFilterChain và ba user demo

**src/main/java/com/example/graphqlsecure/SecurityConfig.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.ignoringRequestMatchers("/graphql"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/graphql")
                    .hasAnyRole("READER", "ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER").build(),
            User.withUsername("admin")
                .password("{noop}admin-pass")
                .roles("ADMIN").build(),
            User.withUsername("guest")
                .password("{noop}guest-pass")
                .roles("GUEST").build());
    }
}
~~~

**Vì sao những status kỳ vọng tương ứng?**

- Anonymous POST không thỏa **hasAnyRole**; httpBasic authentication entry point đưa về **401 Unauthorized**.
- Guest đã xác thực nhưng chỉ có ROLE_GUEST, không thuộc allowlist, nên truy cập **403 Forbidden**.
- Reader và admin có quyền vào **đường HTTP**, không có nghĩa đọc được mọi field GraphQL.
- **anyRequest().denyAll()** chặn các URL ngoài POST /graphql; tránh vô tình phơi bày endpoint khác trong bài mẫu.
- **csrf.ignoringRequestMatchers("/graphql")** chỉ bỏ qua CSRF trên một URL dùng Basic Auth trong demo, không tự tắt CSRF cho toàn ứng dụng.

**Lưu ý bảo mật:** password dạng **{noop}** chỉ dành cho bài học, không hash secret, không phù hợp production. Ứng dụng thật phải dùng PasswordEncoder mạnh và secrets từ nguồn an toàn, HTTPS, rate limiting, credentials/role quản lý đúng cách. Basic Auth qua plain HTTP như localhost trong test không phù hợp để truyền credentials qua mạng công khai.

### 5.4. Resolver và method security

**src/main/java/com/example/graphqlsecure/SecretService.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SecretService {
    @PreAuthorize("hasRole('ADMIN')")
    public String readSecret() {
        return "secret-for-admin";
    }
}
~~~

**src/main/java/com/example/graphqlsecure/GreetingGraphQlController.java**

~~~java
package com.example.graphqlsecure;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingGraphQlController {
    private final SecretService service;

    public GreetingGraphQlController(SecretService service) {
        this.service = service;
    }

    @QueryMapping
    public String greeting(@Argument String name) {
        return "Hello, " + name;
    }

    @QueryMapping
    public String secret() {
        return service.readSecret();
    }
}
~~~

Spring GraphQL map method **greeting** và **secret** với các field trong type Query, không phải HTTP REST @GetMapping. **@Argument String name** trích biến name từ GraphQL input sau document validation. Với **secret**, controller gọi sang **Spring-managed SecretService**, bảo đảm @PreAuthorize đi qua proxy AOP. Nếu dùng **this.readSecret()** tự gọi nội bộ trong cùng bean, lời gọi có thể không qua proxy method security.

Khi reader gọi secret, bộ lọc HTTP đã cho reader vào /graphql nhưng @PreAuthorize ở service từ chối. Spring GraphQL chuyển exception data fetcher thành **GraphQL errors**. Thông điệp lỗi công khai có thể được framework làm mờ; test nên kiểm tra có error và path, **không phụ thuộc vào text nội bộ** của AccessDeniedException.

## 6. Test HTTP thật với HttpGraphQlTester và WebTestClient

**src/test/java/com/example/graphqlsecure/GraphQlHttpTransportTest.java**

~~~java
package com.example.graphqlsecure;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class GraphQlHttpTransportTest {
    @LocalServerPort
    private int port;

    private WebTestClient rawHttp;
    private HttpGraphQlTester baseTester;
    private HttpGraphQlTester readerTester;
    private HttpGraphQlTester adminTester;

    @BeforeEach
    void configureClients() {
        String root = "http://127.0.0.1:" + port;

        rawHttp = WebTestClient.bindToServer()
                .baseUrl(root)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        WebTestClient gqlHttp = WebTestClient.bindToServer()
                .baseUrl(root + "/graphql")
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        baseTester = HttpGraphQlTester.create(gqlHttp);

        readerTester = baseTester.mutate()
                .headers(headers ->
                    headers.setBasicAuth("reader", "reader-pass"))
                .build();

        adminTester = baseTester.mutate()
                .headers(headers ->
                    headers.setBasicAuth("admin", "admin-pass"))
                .build();
    }

    @Test
    void runtimePortIsAssignedByRealServer() {
        assertTrue(port > 0);
    }

    @Test
    void unauthenticatedGraphQlPostIsHttp401() {
        rawHttp.post().uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query",
                        "{ greeting(name: \"Lan\") }"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicCredentialsAreHttp401() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("reader", "wrong-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query",
                        "{ greeting(name: \"Lan\") }"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedButWrongRoleIsHttp403() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("guest", "guest-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query",
                        "{ greeting(name: \"Lan\") }"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerUsesHttpHeaderAndGraphQlVariables() {
        readerTester.document("""
                query Greet($name: String!) {
                  greeting(name: $name)
                }
                """)
                .variable("name", "Lan")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Hello, Lan");
    }

    @Test
    void adminCanReadProtectedGraphQlField() {
        adminTester.document("{ secret }")
                .execute()
                .path("secret")
                .entity(String.class)
                .isEqualTo("secret-for-admin");
    }

    @Test
    void readerGetsGraphQlErrorForProtectedField() {
        readerTester.document("{ secret }")
                .execute()
                .errors()
                .satisfy(errors -> assertFalse(errors.isEmpty()));
    }

    @Test
    void fieldAuthorizationErrorCanStillBeHttp200() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("reader", "reader-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query", "{ secret }"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.errors[0].path[0]")
                    .isEqualTo("secret");
    }

    @Test
    void rawHttpAlsoChecksSuccessContract() {
        rawHttp.post().uri("/graphql")
                .headers(h ->
                        h.setBasicAuth("reader", "reader-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "query", "query Greet($name: String!) "
                                + "{ greeting(name: $name) }",
                        "operationName", "Greet",
                        "variables", Map.of("name", "Mai")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.data.greeting")
                    .isEqualTo("Hello, Mai");
    }
}
~~~

**Phần này dùng hai công cụ để chứng minh hai lớp khác nhau:**

1. **HttpGraphQlTester** cho query thành công và GraphQL-level expected errors. Nó trích data path bằng **path(...).entity(...)**, đồng thời quản lý request document/variables. **mutate().headers(...)** xây các tester độc lập cho reader/admin, không cần sửa header của một tester dùng chung giữa các test.
2. **WebTestClient thô** cho status **401/403** của security filter, không giả vờ GraphQL server đã execute query khi request bị chặn trước đó. Nó cũng kiểm tra raw HTTP response 200 kèm **errors** khi reader bị từ chối ở **field-level authorization**.
3. **@LocalServerPort** cung cấp port ngẫu nhiên thực tế; **bindToServer** tạo request HTTP qua loopback, không phải mock servlet. **responseTimeout(5s)** giới hạn thời gian chờ client thực; đây không phải ứng dụng khai báo SLA bắt buộc là 5s.
4. **Basic Authorization** được set qua headers, khác với GraphQL variables. Không đặt credentials trong GraphQL document hoặc query string, nơi chúng có thể bị log/cache.
5. Trong test reader bị chặn ở field, **không assert một thông điệp exception cụ thể** vì Spring GraphQL có thể che nội dung lỗi bảo mật; assertion status=200 cùng errors.path là bằng chứng về pha **GraphQL execution**.

**Nhận xét về code:** imports assertNotEquals là import dư không gây lỗi compile; có thể bỏ nếu IDE yêu cầu không dùng. Không có thao tác stateful DB và không cần thread sleep, nên test dễ cô lập. Mỗi test tạo WebTestClient/tester mới trong @BeforeEach nhưng Spring ApplicationContext và embedded server có thể được **TestContext cache** dùng lại giữa các methods. Port lấy sau server startup, không hard-code.

### Vì sao không dùng HttpGraphQlTester cho 401/403?

HttpGraphQlTester tiện khi GraphQL transport trả **response hợp lệ cho GraphQL tester**, thường HTTP 200 với JSON data/errors. Khi server trả **HTTP 401/403**, tester có thể thất bại ở bước transport trước khi bạn truy cập .errors(), vì response đó không phải GraphQL execution result dự kiến. Muốn kiểm tra trực tiếp mã trạng thái, **WebTestClient.expectStatus()** nêu rõ hợp đồng hơn.

Nếu test dùng **GraphQlTester.errors().satisfy(...)** cho mọi lỗi, nó có thể bỏ sót việc request đã bị HTTP filter chặn trước khi đến GraphQL engine. Ngược lại, chỉ assert raw HTTP 200 không chứng minh operation đã trả data đúng.

## 7. Đọc kết quả: bốn ca bảo mật riêng biệt

| Kịch bản | Authorization header | Tầng quyết định | HTTP status kỳ vọng | GraphQL data/errors |
| --- | --- | --- | --- | --- |
| Không đăng nhập | Không có | HTTP Basic/Spring Security | **401** | Không yêu cầu GraphQL envelope |
| Credentials sai | Basic với password sai | Authentication provider | **401** | Không yêu cầu GraphQL envelope |
| Guest đăng nhập nhưng thiếu role | Basic guest/GUEST | URL SecurityFilterChain | **403** | Không yêu cầu GraphQL envelope |
| Reader gọi greeting | Basic reader/READER | HTTP allow + resolver | **200** | data.greeting, không error |
| Admin gọi secret | Basic admin/ADMIN | HTTP allow + method @PreAuthorize | **200** | data.secret, không error |
| Reader gọi secret | Basic reader/READER | HTTP allow, method security từ chối | **200** trong demo | errors[0].path có secret, data.secret có thể null |

Bảng này là **contract của project demo**, không phải bảng HTTP status bắt buộc cho tất cả GraphQL servers. Security customization có thể thay status/error body. GraphQL-over-HTTP media type **application/graphql-response+json** có thể ảnh hưởng cách xử lý lỗi request/validation trước execution; hãy kiểm tra Accept/Content-Type mà client thực tế gửi.

### Đường đi của một request thành công

~~~text
POST /graphql + Basic reader + GraphQL query greeting
 -> HttpSecurity: authenticated + ROLE_READER => ALLOW
 -> Spring GraphQL: parse/validate document
 -> GreetingGraphQlController.greeting("Lan")
 -> "Hello, Lan"
 -> HTTP 200 + {"data":{"greeting":"Hello, Lan"}}
~~~

### Đường đi của request guest không đủ role

~~~text
POST /graphql + Basic guest + query greeting
 -> Authentication thành công (guest hợp lệ)
 -> hasAnyRole(READER, ADMIN) => DENY
 -> HTTP 403
 -> GraphQL controller không cần được gọi
~~~

### Đường đi của reader đọc field nhạy cảm

~~~text
POST /graphql + Basic reader + query secret
 -> HTTP security ALLOW /graphql
 -> GraphQL parse/validate thành công
 -> GreetingGraphQlController.secret()
 -> SecretService.readSecret() qua Spring AOP proxy
 -> @PreAuthorize hasRole('ADMIN') => DENY
 -> GraphQL data-fetching error
 -> HTTP 200 + errors, không phải một kết quả secret hợp lệ
~~~

**Không dùng HTTP URL filter để thay thế field-level permissions** khi một GraphQL endpoint cho phép nhiều operations. Một tài khoản có quyền gọi /graphql **không được suy ra** có quyền đọc mọi field hay mọi object. Với dữ liệu nhiều tenant, cần kiểm tra ownership, resource-level security, field-level security và việc propagating principal vào asynchronous DataFetchers.

## 8. Cách chạy dự án và kiểm tra bằng HTTP thủ công

Với Gradle Wrapper tương thích Java 17 và Boot 3.4.x, chạy:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.graphqlsecure.GraphQlHttpTransportTest
./gradlew bootRun
~~~

Trên Windows, dùng **gradlew.bat** thay ./gradlew. Các JUnit tests trong phần 6 **được thiết kế để PASS** khi source/dependency/configuration đúng như bài. Đây là kết quả **dự kiến từ logic mã nguồn**, không phải stdout build đã chạy thực tế; port RANDOM_PORT mỗi lần có thể khác nhau.

Sau khi bootRun, mặc định servlet HTTP server của Spring Boot thường dùng 8080 trừ khi có environment/config override, có thể thử:

~~~bash
curl -i -X POST "http://127.0.0.1:8080/graphql" \
  -H "Content-Type: application/json" \
  -u "reader:reader-pass" \
  --data '{"query":"{ greeting(name: \"Lan\") }"}'

curl -i -X POST "http://127.0.0.1:8080/graphql" \
  -H "Content-Type: application/json" \
  -u "guest:guest-pass" \
  --data '{"query":"{ greeting(name: \"Lan\") }"}'

curl -i -X POST "http://127.0.0.1:8080/graphql" \
  -H "Content-Type: application/json" \
  -u "admin:admin-pass" \
  --data '{"query":"{ secret }"}'
~~~

Các dòng dùng dấu **\\** để xuống dòng trong Unix shell, không phải Windows PowerShell. Trên Windows có thể dùng một dòng curl.exe tương ứng. Không chạy các lệnh với credentials thật từ shell history trong production.

**Kết quả kỳ vọng:** reader greeting nhận data.greeting = "Hello, Lan"; guest nhận HTTP 403; admin secret trả "secret-for-admin". Với reader gọi secret, response có errors từ field-level method security (message có thể bị generic hóa), không được trả giá trị secret.

## 9. Kiểm chứng HTTP headers và biến GraphQL đúng cách

### Query document, operationName và variables

Một POST GraphQL JSON có thể chứa:

~~~json
{
  "query": "query Greet($name: String!) { greeting(name: $name) }",
  "operationName": "Greet",
  "variables": { "name": "Lan" }
}
~~~

**query** là document; **operationName** chọn operation khi document có nhiều operation; **variables** cung cấp giá trị. Với HttpGraphQlTester, không cần tự serialize JSON của request:

~~~java
readerTester
        .document("""
            query Greet($name: String!) {
              greeting(name: $name)
            }
            """)
        .variable("name", "Lan")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, Lan");
~~~

Đây là trích đoạn rút từ test runnable. **Đừng nối trực tiếp input người dùng vào query string** nếu có thể dùng variables; variables giúp bảo vệ phân tách data/document, giảm lỗi escaping và dễ kiểm tra schema type.

### HTTP authentication header

HttpGraphQlTester hỗ trợ cấu hình headers trên builder, ví dụ:

~~~java
HttpGraphQlTester asAdmin = readerTester.mutate()
        .headers(headers ->
                headers.setBasicAuth("admin", "admin-pass"))
        .build();
~~~

Đây là **trích đoạn**. Việc **mutate()** tạo một tester mới, không nên đổi global mutable credentials trên một tester dùng chung để test chạy parallel. Nếu không muốn kế thừa header Basic cũ theo behavior của mutate, tạo admin tester trực tiếp từ **baseTester** như project ở phần 6; như vậy nguồn header rõ ràng hơn.

Với Bearer token trong dự án thật:

~~~java
HttpGraphQlTester bearerTester = baseTester.mutate()
        .headers(headers ->
                headers.setBearerAuth(accessToken))
        .build();
~~~

**Trích đoạn:** accessToken cần được tạo bởi test identity provider hoặc fixture hợp lệ; không hard-code token production trong source. Khi test JWT, cần kiểm tra signature, issuer, audience, expiry, scope và authorization ở HTTP/field layer theo policy, không chỉ “có một chuỗi token”.

### Để khẳng định header thực sự đến server, phải test behavior

Chỉ gọi **headers.setBasicAuth** không tự chứng minh filter đã xác thực đúng; bài test phải quan sát:
- Reader request có credentials đúng => HTTP được cho qua, GraphQL greeting trả data.
- Guest credentials đúng nhưng role sai => HTTP 403.
- Sai password => HTTP 401.
- Admin credentials đúng => field security cho phép secret.
- Reader credentials đúng => GraphQL field security từ chối secret.

Năm bằng chứng này giúp phân biệt **header có mặt**, **authentication hợp lệ**, **URL authorization**, **field authorization** và **business response**.

## 10. Nếu muốn kiểm tra HTTP lỗi do JSON hoặc content negotiation

Lỗi HTTP input là một nhóm khác với GraphQL execution errors. Ví dụ tùy version/framework:

- **POST** thiếu hoặc sai Content-Type có thể bị **415 Unsupported Media Type**.
- JSON body hỏng có thể bị **400 Bad Request** trước GraphQL validation.
- GraphQL document không hợp lệ về cú pháp hoặc schema có thể tạo GraphQL request error, status khác nhau theo server và Accept negotiation.
- Request vượt kích thước cho phép có thể bị 413 từ servlet/proxy.
- Rate limiter hoặc API gateway có thể trả 429 trước khi GraphQL resolver chạy.

Đừng bắt các status này bằng **GraphQlTester.errors()** nếu layer HTTP trả non-200 response. Dùng WebTestClient và assert **HTTP status + response body/header phù hợp policy**, đồng thời xác định request có đi qua security filter trước đó hay không.

Ví dụ kiểm tra request header mà không giả định status cố định ngoài cấu hình hiện có:

~~~java
rawHttp.post()
        .uri("/graphql")
        .headers(h -> h.setBasicAuth("reader", "reader-pass"))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting(name: \"Lan\") }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.data.greeting").isEqualTo("Hello, Lan");
~~~

Ở đây ta cố định Content-Type theo hợp đồng test và assert kết quả thành công. Các ca Content-Type sai nếu quan trọng cho API cần thêm test riêng với status thực tế do framework/version trả.

## 11. GraphQL errors: message, path, extensions và phân quyền

Một GraphQL error thường có **message**, **locations**, **path** và có thể có **extensions**. Việc kiểm chứng nên ưu tiên các thuộc tính **ổn định do ứng dụng định nghĩa**, không dựa vào message nội bộ, trace hoặc stack data framework có thể ẩn nhằm tránh lộ thông tin.

Trong demo, GraphQL schema có nullable field **secret**, nên nếu method security từ chối, response sau execution thường có:
- **data.secret = null**
- **errors** không rỗng
- error path trỏ tới **secret**

Nếu một field được khai báo non-null và fetcher trả lỗi, GraphQL null bubbling có thể khiến **data parent hoặc toàn bộ data = null**, vì vậy đừng assert một shape partial data cố định khi schema khác. Khi ứng dụng tự đăng ký **DataFetcherExceptionResolver**, error classification/code có thể khác, và có thể mapping AccessDeniedException thành một **FORBIDDEN** extension do đội ngũ quy định; lúc đó hãy assert extension code contract thay vì đoán framework default.

**Không phơi bày stacktrace/exception message nhạy cảm** trong response cho client chỉ để test dễ assert. Kết hợp **errors.path**, **extensions.code** do ứng dụng kiểm soát và behavior deny/allow sẽ an toàn hơn.

### Khi một query có cả field được phép và bị cấm

GraphQL cho phép query nhiều field trong cùng operation. Nếu một field bị cấm, những field khác có thể vẫn có data, tùy schema nullability và execution semantics. Test nên kiểm tra:
1. Trường được phép đúng dữ liệu.
2. Trường bị cấm không tiết lộ secret.
3. Error path/code tương ứng.
4. Không bị bỏ qua authorization khi sử dụng alias, fragments hoặc nested resolver.

URL security chỉ nhìn thấy path **/graphql**, không phân biệt query fields; muốn test multi-field authorization đầy đủ, viết integration test với nhiều roles/tenants và data fetchers thật.

## 12. So sánh test slice và full integration test

Một số lựa chọn test:

**@GraphQlTest(GreetingGraphQlController.class)** giới hạn GraphQL infrastructure và controller, thường không mở HTTP socket. Nếu controller cần SecretService, có thể dùng **@MockitoBean** hoặc @Import phù hợp. Nó hữu ích cho schema/datafetcher mapping, nhưng không phải bằng chứng transport authentication.

**@SpringBootTest(webEnvironment = MOCK)** + WebGraphQlTester có thể kiểm tra handler trong memory, không chắc kiểm thử Servlet filter hay TCP socket.

**@SpringBootTest(webEnvironment = RANDOM_PORT)** + HttpGraphQlTester dùng WebTestClient.bindToServer tạo real HTTP request, kiểm tra GraphQL endpoint qua servlet HTTP pipeline và Spring Security.

**HttpGraphQlTester + MockMvcWebTestClient.bindToApplicationContext(...)** có thể kiểm tra mock servlet transport/filter behavior trong Spring MVC mà không dựng server thật. API tester như nhau, nhưng kết luận về **network transport** phải khác nhau.

| Mục tiêu | Công cụ/thiết lập khuyến nghị |
| --- | --- |
| Test @QueryMapping trả đúng data không cần HTTP | @GraphQlTest + GraphQlTester |
| Test schema validation và resolver wiring | GraphQlTester hoặc ExecutionGraphQlServiceTester |
| Test WebGraphQlInterceptor/headers ở handler | WebGraphQlTester |
| Test MVC mock HTTP handler/filter | HttpGraphQlTester qua MockMvcWebTestClient |
| Test HTTP URL, Basic/Bearer, 401/403 và data thực | **RANDOM_PORT + HttpGraphQlTester + WebTestClient** |
| Test WebSocket subscription auth | WebSocketGraphQlTester, không dùng HTTP tester thay thế |
| Test SOAP envelope/SOAPAction/WS-Security | SOAP test client riêng, không dùng HttpGraphQlTester |

**SOAP là nhánh khác của module "GraphQL và SOAP"**: SOAP transport sử dụng XML Envelope, XML Schema, SOAPAction và có cơ chế SOAP Fault/WS-Security khác. Trong bài này chỉ so sánh để tránh dùng nhầm tester; nội dung chính vẫn là HttpGraphQlTester.

## 13. Các lỗi phổ biến khi test authentication và transport

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| IDE không tìm thấy HttpGraphQlTester | Thiếu **spring-graphql-test** ở testImplementation | Thêm đúng dependency theo Spring Boot BOM |
| Không tìm thấy WebTestClient | Thiếu Spring WebFlux test client/connector | Thêm starter-webflux chỉ ở testImplementation khi app MVC |
| Test với HttpGraphQlTester chạy nhưng không có HTTP server | WebTestClient bindToApplicationContext hoặc MockMvcWebTestClient | Dùng bindToServer + RANDOM_PORT |
| GET/POST GraphQL bị 404 | Sai spring.graphql.path hoặc URL trong tester | Xác nhận /graphql, context path và actual port |
| GraphQL test 401 dù user đúng | Authorization header không được gửi, path khác hoặc sai password | Kiểm tra Basic header và server security |
| GraphQL test 403 cho POST | CSRF chặn hoặc role không đủ | Phân biệt CSRF và Authorization, kiểm tra token/security config |
| Guest được phép gửi query | Matcher không bảo vệ /graphql hoặc custom SecurityFilterChain không hiệu lực | Assert 403 với user đã authenticated thiếu role |
| Reader gọi secret lại được data | @EnableMethodSecurity thiếu, @PreAuthorize self-invocation hoặc service không qua proxy | Đặt method security trên bean được gọi qua proxy; assert deny |
| Reader gọi secret trả error nhưng test mong HTTP 403 | Lỗi xảy ra ở data fetcher, sau HTTP allow | Assert HTTP 200+GraphQL errors theo contract |
| Test gọi .errors() nhưng HTTP response là 401 | GraphQlTester không được thiết kế làm status tester cho mọi non-200 | Dùng WebTestClient.expectStatus() |
| Test xanh nhưng field secret bị lộ trong multi-field query | Không test alias/fragments/nested data fetcher | Viết permission tests theo operation và object |
| GraphQL errors có message thay đổi theo framework | Dùng string nội bộ của exception | Assert stable error path/code từ resolver |
| MockMvc test xanh nhưng production transport lỗi | Không test TCP/TLS/network/proxy | Thêm RANDOM_PORT hoặc deploy-level integration tests |
| Wrong Content-Type bị 415 | Không gửi application/json hoặc sai Accept | Cấu hình request đúng; test 415 có chủ đích |
| JSON response có data và errors | Partial success theo GraphQL semantics | Kiểm tra cả hai chứ không chỉ HTTP status |
| Tests rò credentials giữa các vai trò | Dùng mutable tester/header share toàn suite | Tạo tester mới bằng mutate từ base, giữ identities độc lập |
| Test với RANDOM_PORT gọi 8080 | Hard-code port thay vì local.server.port | @LocalServerPort và root URL thực |
| Test role xanh riêng, fail khi chạy suite | Context cache/security config/profile khác, shared state | Isolate fixture, explicit configuration, tránh global mutation |

## 14. Security và dữ liệu test: những giới hạn cần nhớ

**Credentials:** password {noop} trong ví dụ chỉ để minh họa. Trong production phải mã hóa mật khẩu, dùng HTTPS, quản lý secrets qua vault/env và tránh log Authorization headers. Test không nên sao chép token thật từ người dùng vào repository.

**CSRF:** khi dùng browser session/cookies, bỏ qua CSRF cho /graphql có thể không phù hợp. Phải đánh giá attack surface thực tế; nếu cần CSRF, test một request thiếu token => 403 và request có token => success bằng HTTP client hỗ trợ cookie/session.

**GraphQL depth/complexity:** URL đã authenticated không có nghĩa operation tùy ý an toàn. Giới hạn query depth, complexity, field authorization, pagination, introspection policy và batch abuse nếu cần.

**Multi-tenant/ownership:** hasRole('ADMIN') là ví dụ đơn giản; với dữ liệu thật, query phải kiểm tra caller có quyền trên **object cụ thể**, không chỉ role ở URL. Test phải bao gồm “đúng token, sai tenant/resource”.

**Error masking:** authorization/validation failure không được vô tình lộ secret/stacktrace. Server logs có thể giữ correlation ID và diagnostic; HTTP GraphQL errors trả nội dung an toàn.

**Timeout/concurrency:** WebTestClient responseTimeout là giới hạn test; không chứng minh SLA, server timeout, connection pooling và retry production. Cần integration/load tests riêng khi đó là hợp đồng.

**Context cache:** @SpringBootTest có thể tái sử dụng ApplicationContext giữa methods. Mọi tests trong demo không mutate server-side state. Với mutation GraphQL ghi DB, real HTTP client và server thường chạy ở thread/transaction riêng; @Transactional trên JUnit method không tự rollback DB transaction của HTTP server. Phải cleanup dữ liệu bằng chiến lược rõ.

## 15. Bài tập tự kiểm tra

**A.** HttpGraphQlTester trả greeting đúng khi dùng MockMvcWebTestClient. Có chứng minh TCP port /graphql chạy thật chưa? **Chưa**. Cần bindToServer và real server test.

**B.** Anonymous request /graphql trả HTTP 401. Có nên cố gọi GraphQlTester.errors() để chứng minh xác thực? **Không cần và dễ sai**; dùng WebTestClient.expectStatus().isUnauthorized().

**C.** Guest đăng nhập hợp lệ nhưng role GUEST, HTTP 403. Điều gì đã được kiểm tra? **URL authorization** từ chối identity không có quyền, khác với password sai.

**D.** Reader query greeting thành công, nhưng query secret trả HTTP 200 với errors. Có phải lỗi của security? **Không nhất thiết**. Đây là field-level authorization ở execution layer; response GraphQL error là hợp đồng phù hợp.

**E.** Thêm URL SecurityFilterChain chỉ cho ROLE_READER vào /graphql. Reader có thể đọc tất cả GraphQL fields an toàn không? **Không**; phải có field/service/resource-level authorization.

**F.** Vì sao test phải dùng @LocalServerPort? **RANDOM_PORT** cấp port thực tế khác nhau, không thể giả định là 8080.

**G.** Vì sao @PreAuthorize cần ở SecretService được controller gọi? Vì **method security dùng proxy**, self-invocation có thể bỏ qua advice.

**H.** Muốn xác minh Content-Type sai nhận 415 hoặc HTTP error, dùng tester nào? **WebTestClient thô**, assert status/body theo framework/version.

**I.** Có thể dùng HttpGraphQlTester để kiểm thử SOAP XML body không? **Không**. SOAP cần test client và assertions tương ứng envelope/WS-Security.

### Checklist review trước khi chốt

- Đã phân biệt GraphQlTester, HttpGraphQlTester và WebTestClient?
- WebTestClient đang **bindToServer** hay mock context? Kết luận về transport có tương ứng không?
- RANDOM_PORT test dùng **@LocalServerPort** thay vì 8080 cố định?
- Endpoint path, POST, Content-Type, variables và operationName có được kiểm tra?
- HTTP 401 khi anonymous/wrong credentials, HTTP 403 khi authenticated wrong role có test không?
- GraphQL 200 + errors sau field-level authorization có được phân biệt với HTTP 403?
- HTTP security và @EnableMethodSecurity/@PreAuthorize có được kích hoạt đúng cách?
- Tester với từng identity có được tạo độc lập, không rò header sang test khác?
- Errors/assertions có tránh phụ thuộc message nội bộ hoặc lộ secrets?
- Schema nullability, partial data, extensions và error path có được diễn giải đúng?
- CSRF, HTTPS, resource/tenant authorization và query complexity có được tính khi đưa vào production?
- Có test phù hợp cho transport khác (WebSocket, SOAP), không lạm dụng HTTP tester?
- Có kiểm tra security configuration thực tế, không vô tình tắt filter để test xanh?

**Kết luận:** **HttpGraphQlTester** cho phép gửi GraphQL documents/variables và assert data/errors qua HTTP, nhưng bằng chứng về transport phụ thuộc việc WebTestClient **có bind vào server thật hay không**. Với kiểm thử **transport và authentication**, dùng **@SpringBootTest(RANDOM_PORT)** + **WebTestClient.bindToServer** để gọi port thật, **HttpGraphQlTester** cho query hợp lệ và GraphQL errors, **WebTestClient thô** cho HTTP 401/403, headers và status không phải GraphQL. URL security chỉ bảo vệ /graphql; field-level authorization phải được kiểm tra riêng để không coi mọi user có quyền gọi endpoint là được phép đọc toàn bộ dữ liệu.

## Tài liệu chính thức

- Spring for GraphQL 1.3 — Testing (HTTP tester, builders, errors): https://docs.spring.io/spring-graphql/docs/1.3.x/reference/html/#testing
- Spring GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- Spring GraphQL — Security: https://docs.spring.io/spring-graphql/reference/security.html
- Spring GraphQL 1.3 — HttpGraphQlTester API: https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/HttpGraphQlTester.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Security — Servlet Authorization và Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
