# Tạo điểm truy cập công khai và điểm truy cập yêu cầu đăng nhập trong Spring Security Reactive

> **Chủ đề:** Spring Security - reactive · **Nhóm:** Khởi tạo ứng dụng  
> **Kết quả thực hành:** một ứng dụng Spring Boot WebFlux có \`GET /api/public\` truy cập được khi chưa đăng nhập và \`GET /api/private\` chỉ trả dữ liệu khi người gọi đã xác thực. Có mã nguồn, lệnh chạy, lệnh thử HTTP và kiểm thử tự động.

## 1. Yêu cầu và hành vi cần đạt

Trong một ứng dụng thực tế, không phải mọi đường dẫn đều cần đăng nhập. Trang giới thiệu, thông tin công khai hoặc health endpoint thường được truy cập ẩn danh; trang hồ sơ, đơn hàng hoặc thao tác người dùng phải có danh tính đã được xác thực. **Mục tiêu của bài này là thiết lập ranh giới đó ngay khi khởi tạo ứng dụng WebFlux**.

Ta sẽ tạo hai điểm truy cập:

| Điểm truy cập | Chính sách | Kết quả khi chưa đăng nhập | Kết quả khi đăng nhập hợp lệ |
| --- | --- | --- | --- |
| \`GET /api/public\` | \`permitAll()\` | **200 OK**, \`{"message":"Public endpoint"}\` | **200 OK**, cùng nội dung |
| \`GET /api/private\` | \`authenticated()\` | **401 Unauthorized**, yêu cầu thông tin xác thực | **200 OK**, \`{"username":"student"}\` với tài khoản demo |

Cả hai endpoint đều dùng HTTP **GET** và không thay đổi dữ liệu. Những đường dẫn ngoài danh sách được cấu hình \`denyAll()\` để tránh vô tình công khai endpoint mới. Ví dụ dùng **HTTP Basic** vì dễ quan sát vòng đời xác thực; đây là phương án **dành cho môi trường học cục bộ**, không có chức năng tạo tài khoản, đăng ký người dùng hay cấp JWT.

### Phân biệt ba khái niệm trước khi viết code

- **Endpoint công khai:** yêu cầu không cần danh tính để được cấp quyền truy cập đường dẫn. \`permitAll()\` không có nghĩa bỏ toàn bộ security filter hoặc bảo đảm request mang credentials sai vẫn được bỏ qua.
- **Endpoint yêu cầu đăng nhập:** yêu cầu có \`Authentication\` hợp lệ, không ở trạng thái anonymous; \`authenticated()\` chưa kiểm tra role, scope hay quyền trên dữ liệu cụ thể.
- **Xác thực khác phân quyền:** HTTP Basic + kho user dùng để xác định ai đang gọi; \`authorizeExchange\` quyết định URL nào được phép; với dữ liệu nghiệp vụ nhạy cảm cần bổ sung kiểm tra role, owner, tenant ở tầng phù hợp.

## 2. Luồng request trong WebFlux Security

~~~mermaid
flowchart TD
    A["HTTP GET request"] --> B["WebFlux: SecurityWebFilterChain"]
    B --> C{"GET /api/public?"}
    C -->|"Có"| D["permitAll → controller"]
    C -->|"Không"| E{"GET /api/private?"}
    E -->|"Không"| F["denyAll → từ chối truy cập"]
    E -->|"Có"| G{"Có Authentication hợp lệ?"}
    G -->|"Không"| H["HTTP Basic challenge → 401"]
    G -->|"Có"| I["authenticated → controller"]
    I --> J["Lấy username từ Reactor SecurityContext"]
    J --> K["200 + JSON username"]
    D --> L["200 + JSON công khai"]
~~~

Trong WebFlux, \`SecurityWebFilterChain\` xử lý yêu cầu qua các \`WebFilter\`; controller chỉ chạy khi các quy tắc trước đó cho phép. \`ServerHttpSecurity\` là API cấu hình security của **Reactive WebFlux**, khác \`HttpSecurity\` dành cho Servlet MVC. Thông tin \`SecurityContext\` trong luồng reactive được truyền qua **Reactor Context**, vì vậy không lấy bằng cách giả định một \`ThreadLocal\` gắn cố định với một request.

**Lưu ý về sơ đồ:** ứng dụng thực tế còn có các filter khác, kiểm tra credentials có thể diễn ra trước bước quyết định quyền URL, và lỗi 401/403 còn chịu ảnh hưởng bởi loại cơ chế đăng nhập và exception handling. Đây là sơ đồ giúp hiểu các ranh giới chính của bài học.

## 3. Tạo dự án mẫu có thể chạy

Yêu cầu: **JDK 17+**, Maven, cổng **8080** chưa bị sử dụng. Ví dụ dưới đây dùng Spring Boot **3.3.13** để minh họa dòng Spring Boot 3.3; dòng 3.3 đã kết thúc hỗ trợ mã nguồn mở, nên dự án sản phẩm mới cần chọn **bản Spring Boot đang được hỗ trợ** và đối chiếu API theo phiên bản tương ứng. Các API Java trong bài thuộc mô hình Spring Security 6 / WebFlux.

Cấu trúc dự án:

~~~text
reactive-public-private/
├── pom.xml
├── src/
│   ├── main/java/example/reactive/
│   │   ├── ReactiveSecurityApplication.java
│   │   ├── SecurityConfig.java
│   │   └── ApiController.java
│   └── test/java/example/reactive/
│       └── ApiSecurityTest.java
~~~

### 3.1. \`pom.xml\`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>reactive-public-private</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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
~~~

**Vai trò dependency:** \`starter-webflux\` cung cấp reactive web server, controller và Reactor; \`starter-security\` cung cấp Spring Security WebFlux, xác thực và rule HTTP; \`starter-test\` cung cấp JUnit, Spring Test và WebTestClient để kiểm thử HTTP. Trong bài này **không thêm \`spring-boot-starter-web\`**, tránh vô tình chạy theo mô hình Servlet MVC trong cùng ứng dụng mẫu.

### 3.2. Điểm khởi động Spring Boot

File \`src/main/java/example/reactive/ReactiveSecurityApplication.java\`:

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
~~~

\`@SpringBootApplication\` bật cấu hình tự động và component scanning trong package \`example.reactive\`, do đó \`SecurityConfig\` và \`ApiController\` cùng package sẽ được tìm thấy.

## 4. Viết hai endpoint trong controller

File \`src/main/java/example/reactive/ApiController.java\`:

~~~java
package example.reactive;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "Public endpoint"));
    }

    @GetMapping("/api/private")
    public Mono<Map<String, String>> privateEndpoint() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "username", context.getAuthentication().getName()
            ));
    }
}
~~~

**Giải thích chi tiết:**

1. \`@RestController\` giúp trả JSON trực tiếp; \`@GetMapping\` ràng buộc phương thức HTTP GET với đúng đường dẫn. Hai method đều trả \`Mono<...>\`, phù hợp với WebFlux.
2. Endpoint công khai trả dữ liệu cố định, không cần đọc danh tính và không kích hoạt thủ công một lần đăng nhập.
3. Endpoint riêng tư lấy \`SecurityContext\` bằng \`ReactiveSecurityContextHolder.getContext()\`, sau đó trả tên principal từ \`Authentication\`. Với tài khoản demo, \`getName()\` là \`student\`.
4. Controller **không** tự giải mã header Basic, kiểm tra password, hay so sánh role. Những việc này thuộc về Spring Security và tầng authorization.
5. Không gọi \`block()\` để lấy người dùng: method vẫn trả một publisher. Khi có yêu cầu đã xác thực, Spring Security cung cấp ngữ cảnh bảo mật trong reactive pipeline.

**Điều kiện quan trọng:** \`privateEndpoint()\` được thiết kế để chỉ chạy qua chain đã kiểm tra \`authenticated()\`. Nếu gọi method trực tiếp như một method Java bình thường, không qua HTTP security, có thể không có \`ReactiveSecurityContext\` và kết quả \`Mono\` rỗng. Không xem điều đó là một phương thức tự bảo vệ khi gọi từ mọi nơi; việc hạn chế hành vi nghiệp vụ qua service vẫn cần kiểm soát riêng.

## 5. Khai báo chính sách công khai và yêu cầu đăng nhập

File \`src/main/java/example/reactive/SecurityConfig.java\`:

~~~java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/private").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder passwordEncoder) {
        UserDetails student = User.withUsername("student")
            .password(passwordEncoder.encode("demo-pass"))
            .roles("STUDENT")
            .build();

        return new MapReactiveUserDetailsService(student);
    }
}
~~~

### 5.1. Cấu hình này hoạt động như thế nào?

- \`@EnableWebFluxSecurity\` kích hoạt cấu hình bảo mật reactive. Bean \`SecurityWebFilterChain\` được dùng để đưa các quy tắc vào request pipeline.
- \`.pathMatchers(HttpMethod.GET, "/api/public").permitAll()\` mở **chính xác GET** đến \`/api/public\`. Không suy ra POST hoặc mọi đường dẫn bắt đầu bằng \`/api/public\` cũng được mở.
- \`.pathMatchers(HttpMethod.GET, "/api/private").authenticated()\` yêu cầu một \`Authentication\` đã xác thực. Role \`STUDENT\` được gán cho user demo nhưng **không phải điều kiện phân quyền** của endpoint này.
- \`.anyExchange().denyAll()\` từ chối mọi request không khớp các rule trên. Việc endpoint không tồn tại sẽ cho 404 hay bị security chặn trước tùy request, authentication và cấu hình, nên không ép một status duy nhất cho mọi đường dẫn khác.
- \`.httpBasic(Customizer.withDefaults())\` bật xác thực Basic: client gửi header \`Authorization: Basic <base64(username:password)>\`. Base64 **không mã hóa bí mật**, vì thế HTTPS là bắt buộc ngoài local test.
- \`.formLogin(...disable)\` tắt luồng form login trong ví dụ API để phản hồi cho request chưa xác thực là **401 Basic challenge** thay vì điều hướng tới trang đăng nhập HTML.
- \`PasswordEncoderFactories.createDelegatingPasswordEncoder()\` tạo bộ mã hóa mật khẩu có định danh thuật toán, thường dùng bcrypt. Mật khẩu demo được lưu ở dạng đã mã hóa trong memory, không lưu plain text trong \`UserDetails\`. Tuy nhiên chuỗi \`demo-pass\` trong source **chỉ chấp nhận cho học cục bộ**, không đưa vào production.
- \`MapReactiveUserDetailsService\` cung cấp tài khoản mẫu cho cơ chế xác thực reactive. Ở hệ thống thật, thay bằng user store/identity provider đáng tin cậy và chính sách quản lý thông tin xác thực tương ứng.

### 5.2. Vì sao phải đặt \`permitAll()\` trước rule tổng quát?

Các rule authorization được xét theo thứ tự khớp. Với cấu hình:

~~~java
.authorizeExchange(exchanges -> exchanges
    .anyExchange().authenticated()
    .pathMatchers("/api/public").permitAll()
)
~~~

\`anyExchange()\` đặt trước có thể khiến rule công khai không bao giờ được áp dụng, hoặc cấu hình bị từ chối vì matcher tổng quát đã kết thúc chuỗi. Hãy khai báo rule cụ thể trước, rule dự phòng cuối cùng:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/private").authenticated()
    .anyExchange().denyAll()
)
~~~

Ví dụ chỉ dùng **một** \`SecurityWebFilterChain\`. Nếu dự án có nhiều chain, Spring Security lựa chọn chain theo \`securityMatcher\` và \`@Order\`; \`pathMatchers\` bên trong một chain không tự thay thế quy tắc chọn chain.

### 5.3. Điểm khác biệt với Servlet MVC

| Nội dung | WebFlux / Reactive (bài này) | Servlet MVC |
| --- | --- | --- |
| Cấu hình HTTP | \`ServerHttpSecurity\` | \`HttpSecurity\` |
| Security filter | \`SecurityWebFilterChain\` / \`WebFilter\` | \`SecurityFilterChain\` / servlet filter |
| User details | \`ReactiveUserDetailsService\` | \`UserDetailsService\` |
| Lấy security context trong pipeline | \`ReactiveSecurityContextHolder\` | Thường \`SecurityContextHolder\` |
| Giá trị trả về endpoint | \`Mono<T>\`, \`Flux<T>\` | Giá trị trực tiếp, \`ResponseEntity<T>\`, v.v. |

Không trộn \`HttpSecurity\` với ví dụ WebFlux hoặc đặt \`SecurityContextHolder.getContext()\` trong luồng reactive rồi kỳ vọng thông tin luôn đúng khi đổi thread.

## 6. Khởi chạy và thử yêu cầu HTTP

Ở thư mục chứa \`pom.xml\`, chạy:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Dùng một cửa sổ terminal khác để kiểm tra. Các lệnh dưới đây dùng \`curl\`; trên Windows PowerShell 5.1, dùng \`curl.exe\` nếu \`curl\` bị ánh xạ thành \`Invoke-WebRequest\`.

### 6.1. Endpoint công khai, không truyền credentials

~~~bash
curl -i http://localhost:8080/api/public
~~~

Phần thân JSON kỳ vọng:

~~~json
{"message":"Public endpoint"}
~~~

HTTP status kỳ vọng: **200 OK**. Request không có \`Authorization\`, nhưng rule \`permitAll()\` cho phép đi tới controller.

### 6.2. Endpoint riêng tư, không đăng nhập

~~~bash
curl -i http://localhost:8080/api/private
~~~

HTTP status kỳ vọng: **401 Unauthorized**. Với HTTP Basic, phản hồi thường có header \`WWW-Authenticate\` để client biết cách gửi thông tin xác thực. Body lỗi và các header phụ thuộc cấu hình, không cố định JSON nào trong bài.

### 6.3. Endpoint riêng tư, thông tin đăng nhập đúng

~~~bash
curl -i -u student http://localhost:8080/api/private
~~~

\`curl\` sẽ yêu cầu nhập mật khẩu. Nhập \`demo-pass\` từ terminal. HTTP status kỳ vọng: **200 OK**; JSON:

~~~json
{"username":"student"}
~~~

Không khuyến khích đưa mật khẩu thật vào lệnh dạng \`-u student:password\` trong shell history hoặc tài liệu chia sẻ. Cú pháp prompt \`-u student\` ở trên phù hợp cho bài thử cục bộ.

### 6.4. Endpoint riêng tư, password sai

~~~bash
curl -i -u student http://localhost:8080/api/private
~~~

Ở lần này nhập một mật khẩu **khác** \`demo-pass\`. HTTP status kỳ vọng: **401 Unauthorized**, vì server không xác thực được cặp credentials. Nếu tài khoản không tồn tại, kết quả cũng thuộc nhánh xác thực thất bại; ứng dụng không nên tiết lộ user nào tồn tại qua thông báo lỗi.

### 6.5. Bảng quan sát và giải thích

| Request | Header Authorization | Rule áp dụng | Status dự kiến |
| --- | --- | --- | --- |
| GET /api/public | Không | \`permitAll()\` | 200 |
| GET /api/private | Không | \`authenticated()\` | 401 |
| GET /api/private | Basic hợp lệ | \`authenticated()\` | 200 |
| GET /api/private | Basic sai | Xác thực thất bại | 401 |
| GET /api/public | Basic hợp lệ | \`permitAll()\` | 200 |
| POST /api/public | Không | Không có rule mở GET; security/CSRF có thể từ chối | Không mong đợi 200 |

**Bẫy nhỏ:** một request có header \`Authorization\` **không đồng nghĩa đã đăng nhập**. Header có thể sai, hết hạn (đối với token) hoặc không được cơ chế xác thực hiện hành hỗ trợ. \`authenticated()\` chỉ pass khi Spring Security tạo được \`Authentication\` hợp lệ.

## 7. Kiểm thử tự động với WebTestClient

Không nên xác nhận bằng cách xem riêng một lần 200. Test cần chứng minh **cả hai nhánh** công khai và bảo vệ.

File \`src/test/java/example/reactive/ApiSecurityTest.java\`:

~~~java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ApiSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointDoesNotRequireLogin() {
        client.get()
            .uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("Public endpoint");
    }

    @Test
    void privateEndpointRejectsAnonymousRequest() {
        client.get()
            .uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void privateEndpointAcceptsCorrectCredentials() {
        client.get()
            .uri("/api/private")
            .headers(headers ->
                headers.setBasicAuth("student", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("student");
    }

    @Test
    void privateEndpointRejectsWrongPassword() {
        client.get()
            .uri("/api/private")
            .headers(headers ->
                headers.setBasicAuth("student", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Chạy kiểm thử:

~~~bash
mvn test
~~~

**Bốn nhánh ở đây chứng minh được:**

1. \`permitAll()\` thực sự cho phép anonymous truy cập URL cụ thể.
2. \`authenticated()\` chặn anonymous.
3. Cơ chế HTTP Basic + user store thật trong ngữ cảnh test kiểm tra password chính xác và tạo principal.
4. Password sai không được chấp nhận.

Test \`RANDOM_PORT\` khởi động ứng dụng để gửi HTTP thật đến cổng test ngẫu nhiên. Khác với cách chỉ gọi method controller bằng \`new\`, test này đi qua WebFlux + security filter chain.

Vì đây là ứng dụng mẫu, password và username được cố định trong code test. Khi mở rộng, dùng fixture hoặc identity provider chuyên dụng cho test, không dùng credential production.

## 8. Xác thực và phân quyền: cần hiểu trước khi mở rộng

**HTTP 401** là tình huống thông tin xác thực còn thiếu hoặc không hợp lệ đối với tài nguyên cần danh tính. **HTTP 403** thường biểu thị người gọi đã xác thực nhưng không được phép thực hiện thao tác. Hai trường hợp khác nhau:

~~~text
GET /api/private
    ├── không xác thực được     → 401
    └── đã xác thực             → 200

GET /api/admin (nếu bổ sung policy hasRole("ADMIN"))
    ├── chưa xác thực           → 401
    ├── đã xác thực, không ADMIN → 403
    └── đã xác thực, có ADMIN    → được tiếp tục
~~~

Trong code của bài, \`student\` có role \`STUDENT\`, tương ứng authority \`ROLE_STUDENT\`, nhưng \`/api/private\` **không yêu cầu role này**. Nếu đổi rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/private")
    .hasRole("STUDENT")
~~~

thì endpoint chuyển sang yêu cầu quyền role cụ thể. Cấu hình role trên đây là **biến thể minh họa**, không được sử dụng cùng cấu hình ban đầu nếu đang đối chiếu expected status trong test. \`hasRole("STUDENT")\` kiểm tra authority \`ROLE_STUDENT\`; không viết \`hasRole("ROLE_STUDENT")\` trong trường hợp prefix ROLE_ mặc định.

Nếu dữ liệu trong endpoint là đơn hàng/hồ sơ của nhiều người, việc đã đăng nhập hoặc có \`ROLE_STUDENT\` vẫn **chưa** chứng minh được quyền xem bản ghi. Tầng service/repository phải kiểm tra owner, tenant, trạng thái hoặc quy tắc nghiệp vụ. Bài này chỉ tạo ranh giới public/private ban đầu.

## 9. Chọn cơ chế đăng nhập phù hợp ngữ cảnh

Bài mẫu dùng **HTTP Basic + In-memory users** để làm rõ sự khác nhau giữa request ẩn danh và đã xác thực. Khi thiết kế ứng dụng thực tế, cơ chế có thể thay đổi:

| Cơ chế | Cách gửi danh tính | Khi nào cân nhắc | Lưu ý |
| --- | --- | --- | --- |
| HTTP Basic | \`Authorization: Basic ...\` trên request | Demo, công cụ nội bộ có TLS, trường hợp đơn giản | Credentials được gửi lại trên mỗi request; cần HTTPS và quản lý bí mật |
| Form login + session | Trình duyệt gửi cookie session | Website có phiên người dùng | Phân tích CSRF, cookie flags, session lifecycle |
| OAuth2 Resource Server / Bearer JWT | \`Authorization: Bearer ...\` | API được bảo vệ bởi issuer/authorization server | Xác minh chữ ký, issuer, expiry, audience và claim mapping |
| OIDC login | Authorization Code flow và ID token cho việc đăng nhập | Website muốn đăng nhập qua identity provider | Phân biệt ID token với access token dùng gọi API |

**Không** thay HTTP Basic bằng cách tự tạo header \`X-Username\` hoặc tin query \`?user=...\`: đó không phải cơ chế xác thực. Nếu chuyển sang JWT, chỉ thay cấu hình authentication phù hợp và test theo token, còn ý tưởng \`permitAll()\`, \`authenticated()\` và bảo vệ data-level vẫn có giá trị.

## 10. Bảo mật cần giữ ngay cả trong ví dụ nhỏ

### 10.1. HTTPS và credential

HTTP Basic mã hóa dữ liệu bằng Base64, **không phải encryption**. \`http://localhost:8080\` chỉ dùng trong môi trường thực hành. Với mạng thật cần HTTPS, tránh ghi header Authorization vào log và dùng kho bí mật/identity provider thay tài khoản cố định trong source.

### 10.2. CSRF

Ví dụ **không tắt CSRF**: Spring Security bảo vệ các yêu cầu có khả năng thay đổi trạng thái theo cấu hình mặc định; hai endpoint GET chỉ đọc nên không cần token CSRF cho thao tác bình thường. Nếu thêm POST/PUT/DELETE, một yêu cầu có xác thực đúng vẫn có thể gặp **403** vì thiếu CSRF token. Đừng sửa bằng cách tắt CSRF vô điều kiện. Với API dùng Bearer token do client chủ động gắn và không có cookie tự động xác thực, có thể cân nhắc tắt CSRF sau khi đánh giá threat model. Với đăng nhập cookie/session, thường cần bảo vệ CSRF.

### 10.3. CORS khác authentication

CORS quyết định browser có được đọc phản hồi từ một origin khác hay không; nó **không** cấp quyền truy cập tài nguyên và không thay thế \`authenticated()\`. Không thêm \`Access-Control-Allow-Origin: *\` để “sửa” lỗi 401/403. Nếu frontend khác origin, xác định rõ origin, methods, headers và credential policy.

### 10.4. \`permitAll\` không bỏ qua mọi kiểm tra

Rule \`permitAll()\` chỉ nói request khớp rule không cần quyền truy cập. Nếu client cố ý gửi header Basic sai, authentication filter vẫn có thể phát hiện và trả 401. Bởi vậy test đúng nghĩa endpoint công khai phải dùng request **không có credentials**. Ngược lại, client được xác thực vẫn có thể bị \`denyAll()\` ở đường dẫn không cho phép.

### 10.5. Không lạm dụng đường dẫn public

Công khai chỉ những route cần thiết, giới hạn dữ liệu trả về (không lộ email, secret, tài nguyên nội bộ), cân nhắc rate limiting và caching riêng cho nội dung công khai. Không thêm rule \`/api/**.permitAll()\` chỉ để mọi endpoint “chạy được” trong lúc phát triển.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| \`/api/public\` trả 401 | Rule bị che bởi \`anyExchange\`, nhầm path/method, hoặc client tự gửi Basic sai | Kiểm tra thứ tự matcher; thử curl không có Authorization |
| \`/api/private\` trả 200 khi chưa đăng nhập | Vô tình mở public quá rộng hoặc chưa kích hoạt security chain | Kiểm tra \`@EnableWebFluxSecurity\`, chain được chọn, URL match và negative test |
| Tài khoản đúng nhưng 401 | Mật khẩu mã hóa sai/không đúng password encoder, nhầm username, header Basic sai | Xem \`MapReactiveUserDetailsService\` và prefix mật khẩu; không log password |
| GET public 200 nhưng POST bị 403 | Rule chỉ mở GET, hoặc thiếu token CSRF | Phân biệt method, route authorization và CSRF |
| Request nhận redirect tới \`/login\` thay vì 401 | Form login vẫn được bật cho request/chain đó | Tắt form login cho API hoặc dùng chain/cơ chế phù hợp |
| Không lấy được principal trong pipeline | Đọc context sai mô hình reactive hoặc gọi controller trực tiếp | Dùng \`ReactiveSecurityContextHolder\` bên trong publisher và test qua HTTP |
| Config không biên dịch | Dùng \`HttpSecurity\`/Servlet API trong dự án WebFlux hoặc sai version | Đối chiếu import \`ServerHttpSecurity\`, \`SecurityWebFilterChain\`, dependency |
| Request ngoài hai route trả status khác dự đoán | Security từ chối trước routing hoặc entry point khác | Kiểm tra rule \`denyAll\`, trạng thái xác thực và HTTP response; không giả định luôn 404 |

Để chẩn đoán, đọc theo thứ tự: **method + URL → SecurityWebFilterChain → credentials → Authentication → matcher → controller**. Với bài này không cần viết custom filter, custom JWT parser hoặc tự thao tác \`SecurityContext\`.

## 12. Bài tập vận dụng

**Bài A — thêm public endpoint:** tạo \`GET /api/version\` trả \`{"version":"1.0"}\`, chỉ mở đúng GET ở cấu hình security. Chứng minh truy cập được không cần đăng nhập và những method khác không tự được mở.

**Bài B — bảo vệ quyền theo role:** thêm user \`viewer\` có \`ROLE_VIEWER\` và \`GET /api/admin\` chỉ cho \`ROLE_ADMIN\`. Viết test phân biệt: không đăng nhập (401), đăng nhập viewer (403) và đăng nhập admin (200). Đừng dùng test này để thay đổi hành vi của \`/api/private\` nếu chưa chủ ý.

**Bài C — tích hợp UI:** dùng WebTestClient hoặc một frontend khác origin để quan sát vấn đề CORS. Giải thích tại sao browser bị CORS không đồng nghĩa request không được xác thực, và tại sao thêm rule CORS không cấp quyền truy cập endpoint private.

**Bài D — chuyển sang Bearer token:** giữ nguyên hai endpoint/nhóm rule, thay cách xác thực bằng OAuth2 Resource Server có issuer hợp lệ trong môi trường test. Kiểm tra 401 khi token thiếu/sai, 200 khi token hợp lệ, và bổ sung một ví dụ 403 khi thiếu authority. Đây là bước mở rộng, cần cấu hình identity provider và test riêng.

### Checklist tự đánh giá

- [ ] Ứng dụng khởi động với WebFlux và Spring Security, không trộn với Spring MVC.
- [ ] \`GET /api/public\` trả 200 và JSON đúng khi **không** gửi header Authorization.
- [ ] \`GET /api/private\` trả 401 khi anonymous hoặc password sai.
- [ ] \`GET /api/private\` trả 200 và username khi Basic credentials hợp lệ.
- [ ] \`anyExchange().denyAll()\` đứng cuối và không vô tình mở đường dẫn khác.
- [ ] Kiểm thử \`mvn test\` xác minh bốn tình huống trên.
- [ ] Giải thích được khác biệt \`permitAll()\`, \`authenticated()\`, \`hasRole()\` và 401/403.
- [ ] Không dùng Basic qua HTTP trên môi trường thật; không tắt CSRF bừa bãi; không lưu credential production trong source.

## 13. Câu hỏi tự kiểm tra

1. Vì sao controller \`/api/private\` không cần tự phân tích header \`Authorization\`?
2. Vì sao \`permitAll()\` nên đặt trước \`anyExchange().denyAll()\`?
3. \`GET /api/private\` với password sai trả gì và vì sao khác trường hợp user có password đúng nhưng thiếu role ADMIN?
4. Nếu chuyển controller sang trả \`Mono<UserDto>\` từ service reactive, có nên gọi \`block()\` để lấy principal trước không?
5. Nếu frontend báo CORS error khi gọi \`/api/private\`, có thể kết luận user chưa đăng nhập không?
6. Khi thêm POST /api/orders trong ứng dụng dùng cookie/session, vì sao cần suy xét CSRF dù route đã \`authenticated()\`?
7. Nếu user đã đăng nhập có thể gọi \`/api/orders/42\`, lớp nào bảo đảm đơn 42 thật sự thuộc user hoặc tenant của họ?

Nếu trả lời được các câu này và hoàn thành ma trận kiểm thử, người học đã có nền tảng để mở rộng từ **xác thực HTTP** sang **quyền route, method và nghiệp vụ**.

## 14. Tài liệu chính thức

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cấu hình \`ServerHttpSecurity\`, \`SecurityWebFilterChain\`, reactive user store.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): matcher và rule authorization ở HTTP.
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html): xác thực Basic trong Reactive.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): ngữ cảnh cần CSRF và cách cấu hình.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): \`@RestController\`, reactive return type và request mapping.
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html): cấu trúc \`spring-boot-starter-parent\` và cách dùng Maven.

**Kết quả cốt lõi:** hai endpoint có thể nằm trong cùng controller, nhưng **chính sách truy cập** nằm ở \`SecurityWebFilterChain\`: một đường dẫn cho anonymous vào bằng \`permitAll()\`, một đường dẫn chỉ cho \`Authentication\` hợp lệ vào bằng \`authenticated()\`. Hãy chứng minh hai hành vi bằng HTTP request và test âm tính trước khi bổ sung các điều kiện quyền nghiệp vụ.