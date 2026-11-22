# Chuyển đổi tên đăng nhập và mật khẩu thành Authentication trong HTTP Basic

**Chủ đề:** Spring Security – Reactive (WebFlux)  
**Phần:** HTTP Basic  
**Mục tiêu:** Hiểu chính xác từ header `Authorization: Basic ...` đến `Authentication`, phân biệt token *chưa được xác thực* và kết quả *đã được xác thực*, cấu hình WebFlux an toàn, và kiểm chứng được bằng Java 17+, `curl`, `WebTestClient` và `StepVerifier`.

HTTP Basic là cơ chế mà HTTP client gửi username/password trong header của mỗi request. Spring Security không lấy username từ URL hoặc biến global để cho phép truy cập: nó cần **đọc header, chuyển credential thành một yêu cầu xác thực, đối chiếu với nguồn người dùng, rồi mới tạo danh tính đáng tin cậy**.

> **Điểm then chốt:** “Chuyển đổi username/password thành Authentication” không đồng nghĩa “người dùng đã đăng nhập thành công”. `ServerHttpBasicAuthenticationConverter` tạo một `Authentication` dùng làm **đề nghị xác thực**; `ReactiveAuthenticationManager` mới là thành phần kiểm tra và trả `Authentication` được xác thực. Không được tin quyền hay username do client tự khai chỉ vì chúng đã được giải mã Base64.

## 1. Nhìn toàn bộ đường đi trước khi lập trình

Với client HTTP Basic, request ví dụ (chuỗi trong dấu ngoặc nhọn dưới đây chỉ diễn giải, không phải header hợp lệ để copy nguyên văn):

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic <Base64-cua-chuoi-alice:alice123>
```

`Basic` chỉ tên authentication scheme. Phần theo sau là Base64 của byte biểu diễn `username:password`; Base64 **không phải mã hóa bảo mật**, ai đọc được header đều có thể khôi phục credential. Vì vậy phải dùng HTTPS ngoài localhost và tuyệt đối không log/header-dump credential thật.

Sơ đồ **WebFlux**, không phải luồng Servlet:

```text
HTTP request
   |
   v
SecurityWebFilterChain có HTTP Basic
   |
   v
AuthenticationWebFilter
   |
   +--> ServerHttpBasicAuthenticationConverter
   |      đọc Authorization; kiểm tra scheme Basic;
   |      giải mã credentials và tách username/password
   |      |
   |      +--> Không có Basic phù hợp -> Mono.empty()
   |      |                          (không gọi manager cho request này)
   |      |
   |      +--> Tạo Authentication chưa xác thực:
   |              UsernamePasswordAuthenticationToken
   |              principal = "alice"
   |              credentials = raw password tạm thời
   |              authenticated = false
   |              authorities = []
   |
   v
ReactiveAuthenticationManager.authenticate(requestToken)
   |
   +--> ReactiveUserDetailsService.findByUsername("alice")
   |      -> UserDetails: username, hash mật khẩu, quyền, trạng thái
   |
   +--> PasswordEncoder.matches(raw, storedHash)
   |      + kiểm tra tài khoản enabled/locked/... theo policy
   |
   +--> Sai: Mono lỗi AuthenticationException
   |         -> handler / entry point, thường HTTP 401
   |
   +--> Đúng: Mono<Authentication> đã xác thực
   |             authenticated = true
   |             authorities = quyền từ nguồn tin cậy
   |
   v
ReactiveSecurityContextHolder (Reactor Context theo request)
   |
   v
authorizeExchange(...) kiểm tra vai trò/quyền
   |
   +--> Được phép -> WebFlux controller -> Mono/Flux -> HTTP response
   |
   +--> Thiếu quyền -> thường HTTP 403
```

Spring Security cung cấp sẵn bộ lọc và converter cho HTTP Basic khi gọi `ServerHttpSecurity.httpBasic(...)`. **Đa số ứng dụng không cần viết parser Base64 hoặc filter xác thực của riêng mình**.

### 1.1. “Authentication” có hai trạng thái

Cùng một interface `org.springframework.security.core.Authentication` được dùng để mô tả cả **yêu cầu** lẫn **kết quả** xác thực. Một số thuộc tính quan trọng:

| Thuộc tính | Ngay sau Basic converter | Sau manager thành công |
| --- | --- | --- |
| `getPrincipal()` | Thường là chuỗi username client khai, ví dụ `"alice"` | Thường là `UserDetails` hoặc principal tin cậy do manager tạo |
| `getCredentials()` | Password client gửi; **nhạy cảm** | Có thể được xóa/giảm thời gian tồn tại tùy implementation; không dựa vào nó sau login |
| `isAuthenticated()` | **`false`** | **`true`** |
| `getAuthorities()` | Rỗng/chưa đáng tin | Quyền như `ROLE_USER` được tải từ user store/policy |
| `getName()` | Tên client đề nghị, **chưa xác minh** | Tên principal đã qua kiểm tra |

`UsernamePasswordAuthenticationToken.unauthenticated(username, password)` là cách biểu đạt tường minh một request token. API `UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)` có thể tạo token đã xác thực trong **mã tin cậy**, nhưng **không bao giờ được dùng nó để tin trực tiếp username/role từ HTTP header**. Xác thực phải thông qua manager hoặc một trust boundary được thiết kế an toàn.

### 1.2. Không có Basic header là trường hợp khác với mật khẩu sai

- Request **không có `Authorization`**: converter không tạo token; filter không xác thực bằng Basic. Sau đó, nếu endpoint yêu cầu `authenticated()`, Spring Security sẽ từ chối và phát HTTP Basic challenge.
- Header có scheme khác, ví dụ `Bearer`: Basic converter không biến credential đó thành username/password. Nếu ứng dụng cần Bearer token, cấu hình OAuth2 Resource Server/manager **khác**, không ép token vào parser Basic.
- Header Basic có username hợp lệ nhưng **password sai**: converter vẫn có thể tạo request token, nhưng manager từ chối sau khi thử `PasswordEncoder.matches(...)`.
- Header Basic **bị hỏng** (Base64 không hợp lệ/không có dấu phân cách): cần được xử lý như request không hợp lệ/không thể xác thực. Chính xác status/exception phụ thuộc phiên bản và cấu hình handler; không giả định mọi chuỗi hỏng đều đi đến `findByUsername`.

Đối với endpoint public, client gửi một header Basic **sai** vẫn có thể bị filter Basic từ chối trước controller, dù URL có `permitAll()`. `permitAll()` cho phép request **không cần xác thực**, không có nghĩa Spring bắt buộc bỏ qua mọi credential sai do client chủ động gửi.

## 2. Base64, dấu hai chấm và charset

HTTP Basic biểu diễn credential bằng một chuỗi `username:password` được mã hóa thành bytes rồi Base64:

```text
username   = alice
password   = alice123
raw        = alice:alice123
scheme     = Basic
header     = Authorization: Basic <base64(raw-bytes)>
```

**Dấu hai chấm đầu tiên** phân cách username và password. Username theo cú pháp Basic không được chứa `:`; password **có thể** chứa dấu `:` phía sau, nên parser phải tách theo dấu `:` *đầu tiên*, không cắt mỗi dấu hai chấm rồi chỉ lấy phần thứ hai. Ví dụ `alice:p:a:ss` nghĩa là username `alice`, password `p:a:ss`.

### 2.1. Chương trình Java 17 độc lập: nhìn rõ bước giải mã

Đây là **mô phỏng cơ chế wire format để học**, không phải mã parser nên đưa vào production. Chương trình dùng credential giả hoàn toàn trên máy cục bộ, không kết nối mạng và không in password gốc.

Lưu thành `BasicHeaderAnatomy.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderAnatomy {
    public static void main(String[] args) {
        String original = "alice:p:a:ss"; // Chỉ dùng giá trị demo

        String base64 = Base64.getEncoder().encodeToString(
            original.getBytes(StandardCharsets.UTF_8));
        String header = "Basic " + base64;

        byte[] decoded = Base64.getDecoder().decode(header.substring(6));
        String pair = new String(decoded, StandardCharsets.UTF_8);
        int firstColon = pair.indexOf(':');

        String username = pair.substring(0, firstColon);
        String password = pair.substring(firstColon + 1);

        System.out.println("scheme=Basic");
        System.out.println("username=" + username);
        System.out.println("password-has-colon=" + password.contains(":"));
        System.out.println("password-length=" + password.length());
    }
}
```

Chạy:

```bash
javac BasicHeaderAnatomy.java
java BasicHeaderAnatomy
```

Stdout chính xác:

```text
scheme=Basic
username=alice
password-has-colon=true
password-length=6
```

Lưu ý: demo chỉ cho thấy cách phân tách, **không kiểm tra người dùng có tồn tại hay mật khẩu có đúng**. Nó cũng chưa có bước validate header/hạn chế kích thước/exception handling, nên **không sử dụng thay cho converter của Spring Security**. Trong ứng dụng thực, bạn thường không cần tự decode header.

### 2.2. Encoding của username/password không phải chi tiết tùy ý

Base64 xử lý **bytes**, không trực tiếp xử lý chuỗi Unicode. Với ký tự ASCII như `alice:alice123`, UTF-8 và ISO-8859-1 tạo cùng bytes; với tên/mật khẩu có dấu tiếng Việt, hai charset có thể khác và dẫn tới 401 dù người dùng nghĩ đúng mật khẩu. HTTP Basic có quy tắc tương tác charset và Spring Security cung cấp cấu hình liên quan converter. Hãy xác định chính sách client/server thống nhất và test bằng dữ liệu thực tế; không tự sửa password bằng `trim()`, lowercase hoặc thay đổi Unicode normalization trong lúc login nếu không có quy tắc đăng ký tương ứng.

Trong mã client Spring, `HttpHeaders.setBasicAuth(username, password)` có overload nhận `Charset`. Nếu hệ thống dùng credential Unicode, cần chọn cách encode phù hợp với server, xem đầy đủ challenge `WWW-Authenticate` và cách converter giải mã; đừng mặc định mọi browser/curl có cùng hành vi không phụ thuộc phiên bản.

## 3. Bốn thành phần Spring Security phải phân biệt

### 3.1. ServerAuthenticationConverter

Interface `org.springframework.security.web.server.authentication.ServerAuthenticationConverter` nhận `ServerWebExchange` và trả `Mono<Authentication>`. Với HTTP Basic, Spring cung cấp `ServerHttpBasicAuthenticationConverter` (package `org.springframework.security.web.server.authentication`).

Converter chịu trách nhiệm **diễn giải HTTP credential và tạo request token**. Nó **không**:

- truy vấn database;
- xác minh hash mật khẩu;
- cấp role/authority đáng tin;
- tự thiết lập principal vào Reactor Context;
- tự quyết định client có quyền với `/api/admin` hay không.

Khi converter phát `Mono.empty()`, điều đó nghĩa là **không có kết quả chuyển đổi** cho filter này, không phải “đã xác thực vô danh thành công”.

### 3.2. AuthenticationWebFilter

`AuthenticationWebFilter` là WebFilter nằm trong chuỗi Spring Security WebFlux. Nó nhận converter, gọi manager để xác thực token, xử lý thành công/thất bại và nối kết quả vào ngữ cảnh bảo mật reactive. Những điểm quan trọng:

1. Kiểm tra request có thuộc phạm vi filter yêu cầu xác thực không.
2. Gọi `ServerAuthenticationConverter.convert(exchange)`.
3. Nếu `Mono.empty()`, không gọi manager cho filter này; tiếp tục pipeline.
4. Nếu có request token, gọi `ReactiveAuthenticationManager.authenticate(token)`.
5. Nếu thành công, xử lý thành công và cung cấp `Authentication` trong `ReactiveSecurityContextHolder`.
6. Nếu thất bại, dùng failure handler/entry point phù hợp; không để request token chưa xác thực trở thành danh tính tin cậy.

Đừng nhầm `AuthenticationWebFilter` của **WebFlux** với `BasicAuthenticationFilter` của **Servlet**. Tương tự, `SecurityFilterChain` + `HttpSecurity` là Servlet; ứng dụng này phải dùng `SecurityWebFilterChain` + `ServerHttpSecurity`.

### 3.3. ReactiveAuthenticationManager

`ReactiveAuthenticationManager` nhận `Authentication` chưa xác thực và trả một `Mono<Authentication>` kết quả. Với username/password lưu trong user store, `UserDetailsRepositoryReactiveAuthenticationManager` dùng `ReactiveUserDetailsService` để tìm user và `PasswordEncoder` để so raw credential với password hash.

Manager xác minh **danh tính**, còn Spring Security authorization kiểm tra **quyền truy cập endpoint** sau khi danh tính đã đáng tin. Kể cả người dùng đăng nhập đúng vẫn có thể bị `403 Forbidden` khi thiếu role.

### 3.4. ReactiveSecurityContextHolder

Sau xác thực, `Authentication` đã xác thực được đưa vào `SecurityContext` theo đường Reactor Context của subscriber. Code service/controller đọc qua `ReactiveSecurityContextHolder.getContext()`, không dựa trên `ThreadLocal` giữ user từ request trước. Trong WebFlux, các request có thể đan xen trên cùng event-loop thread hoặc chuyển scheduler; đọc principal trong pipeline là cách đáng tin cậy hơn lưu ở biến singleton.

## 4. Ứng dụng Spring Boot WebFlux Java 17+ chạy được

Ứng dụng mẫu minh họa luồng thật: converter mặc định của HTTP Basic → `ReactiveAuthenticationManager` → user store có hash → kết quả xác thực trong Reactor Context → controller/authorization.

Endpoints:

| Method + path | Quy tắc | Kết quả quan trọng |
| --- | --- | --- |
| `GET /public/ping` | `permitAll()` | Anonymous nhận `200`, `pong` |
| `GET /api/me` | `authenticated()` | Anonymous nhận `401`; Alice hợp lệ nhận `200`, `hello:alice` |
| `GET /api/admin` | `hasRole("ADMIN")` | Alice hợp lệ nhận `403`; admin hợp lệ nhận `200`, `admin-ok` |
| Mọi đường/method khác | `denyAll()` | Không vô tình mở route mới |

Tài khoản mẫu: `alice / alice123` có `ROLE_USER` và `admin / admin123` có `ROLE_ADMIN`. **Chúng chỉ được dùng trong môi trường học tập localhost.** Mật khẩu được hash bằng `DelegatingPasswordEncoder` (BCrypt theo policy mặc định) trước khi đưa vào `MapReactiveUserDetailsService`.

### 4.1. Cấu trúc

```text
basic-auth-conversion/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/basic/
    │   │   ├── BasicAuthApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── AuthController.java
    │   └── resources/application.properties
    └── test/java/demo/basic/
        └── BasicAuthConversionTests.java
```

Dùng **Spring Boot 3.5.7** làm mốc dependency tái hiện và JDK 17+. Đây là phiên bản ví dụ, không phải lời khuyên giữ phiên bản cũ ở production. Khi triển khai thật, chọn bản vá còn được hỗ trợ và theo chính sách bảo mật của dự án.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>basic-auth-conversion</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

**Vì sao không thêm `spring-boot-starter-web`?** Bài đang dùng WebFlux. Khi cả MVC và WebFlux starter có mặt, Spring Boot có thể ưu tiên Servlet MVC, làm filter chain và kiểu ứng dụng khác dự kiến. Không cần database, Docker hay WebClient tùy biến cho bài thực hành này.

`src/main/resources/application.properties`:

```properties
spring.application.name=basic-auth-conversion
server.port=8080
```

### 4.2. Entry point

`src/main/java/demo/basic/BasicAuthApplication.java`:

```java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicAuthApplication.class, args);
    }
}
```

Các Java class khác được đặt trong package `demo.basic` để `@SpringBootApplication` component-scan tìm thấy chúng.

### 4.3. Cấu hình SecurityWebFilterChain, user store và manager

`src/main/java/demo/basic/SecurityConfig.java`:

```java
package demo.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
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
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
            .authenticationManager(authenticationManager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Từng phần đang giải quyết vấn đề gì?**

1. `@EnableWebFluxSecurity` kích hoạt tích hợp Spring Security với WebFlux.
2. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` dùng chính sách mã hóa/kiểm tra hash thống nhất. Hash demo thường có dạng `{bcrypt}...`; hai lần encode cùng password có thể sinh hash khác nhau nhờ salt.
3. `users(...)` giữ `UserDetails` có password **đã encode**, authorities và trạng thái user. Một hệ thống thực dùng `ReactiveUserDetailsService` đọc hash từ R2DBC/nguồn dữ liệu phù hợp, không lưu raw password.
4. `authenticationManager(...)` là nơi **xác minh** request token mà Basic converter tạo. Nó truy xuất username và gọi `PasswordEncoder.matches(raw, encoded)`; chỉ sau khi pass mới trả kết quả đã xác thực.
5. `http.authenticationManager(...)` kết nối manager này vào những cơ chế authentication do chain hỗ trợ. `httpBasic(Customizer.withDefaults())` cài sẵn filter/converter Basic thay vì tự giải mã Base64 bằng controller.
6. `formLogin(...disable())` bỏ login form cho mẫu API, giúp quan sát 401/403 qua HTTP Basic. Không mặc định “mọi ứng dụng có HTTP Basic đều không có session”: những cấu hình khác có thể thêm form login/session.
7. `anyExchange().denyAll()` ngăn mở các method/path chưa xác định.

**Quan trọng:** Mã trên không tạo bean `ServerHttpBasicAuthenticationConverter` và không viết `AuthenticationWebFilter` riêng, **vì Spring Security đã làm việc đó**. Tạo thêm một filter tự chế mà không hiểu matcher, order và success/failure handler có thể tạo hai cơ chế authentication mâu thuẫn hoặc bỏ sót security context.

### 4.4. Controller đọc đúng Authentication đã xác thực

`src/main/java/demo/basic/AuthController.java`:

```java
package demo.basic;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AuthController {

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "hello:" + name);
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

`/api/me` không đọc username từ URL, query parameter hay header `X-User`. Nó lấy principal **sau khi Spring Security đã xác thực** từ Reactor Context của chính request. Khi trả `Mono` cho framework, WebFlux subscribe và xử lý context đúng theo pipeline. Không gọi `subscribe()` thủ công trong controller và không dùng trường `static currentUser` để lưu người vừa đăng nhập.

## 5. Chạy thực tế bằng curl và hiểu kết quả

Ở thư mục `basic-auth-conversion`:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Khi log cho biết server Reactor Netty lắng nghe cổng 8080, mở terminal khác. Nếu cổng bị chiếm, sửa `server.port` và mọi URL tương ứng. Trên Windows PowerShell cũ, `curl` đôi khi là alias của `Invoke-WebRequest`, hãy gọi `curl.exe` để có đúng lệnh.

### 5.1. Anonymous, credential đúng, credential sai và role sai

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/me
curl -i --user alice:wrong http://localhost:8080/api/me
curl -i --user unknown:whatever http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
curl -i -H "Authorization: Bearer not-a-basic-credential" \
  http://localhost:8080/api/me
```

Ma trận theo thứ tự lệnh:

| Request | HTTP status kỳ vọng | Giải thích |
| --- | --- | --- |
| Public, không credential | `200`, body `pong` | Không cần converter hoặc manager để truy cập public |
| `/api/me`, không Basic | `401` và thường có `WWW-Authenticate: Basic ...` | Basic converter không có token; authorization yêu cầu login |
| `/api/me`, Alice đúng | `200`, body `hello:alice` | Converter tạo request token; manager xác minh; controller đọc principal |
| `/api/me`, Alice sai mật khẩu | `401` | Token đã được chuyển đổi nhưng `matches` không đúng |
| `/api/me`, username không tồn tại | `401` | Không có tài khoản tin cậy để xác thực |
| `/api/admin`, Alice đúng | `403` | **Authentication thành công, authorization thất bại** |
| `/api/admin`, admin đúng | `200`, body `admin-ok` | Danh tính và quyền đều phù hợp |
| `/api/me`, scheme Bearer nhưng app chỉ bật Basic | `401` | Basic converter không hiểu Bearer thành username/password |

Chính xác các body/header lỗi có thể thay đổi theo Spring Security version và custom handler, nhưng bảng này biểu thị behavior kỳ vọng với cấu hình mẫu. Để tìm nguyên nhân lỗi, xem **method + path + Authorization scheme + status + WWW-Authenticate**; không dựa vào trang lỗi HTML của trình duyệt.

`curl --user username:password` tự tạo header Basic; **không cần tự Base64 và dán header trong file cấu hình**. Nếu muốn tránh password trong command history/process list, có thể chỉ định `--user alice` rồi nhập mật khẩu ở prompt (cách hỗ trợ phụ thuộc client). Tuyệt đối không chạy demo qua HTTP mở ra Internet.

### 5.2. Thử request có header giả mạo tên người dùng

```bash
curl -i --user alice:alice123 \
  -H "X-Authenticated-User: admin" \
  -H "X-Role: ADMIN" \
  http://localhost:8080/api/me
```

Vẫn phải trả `hello:alice`, không phải `hello:admin`. Cả hai header `X-...` trên do client tự gửi, **không phải bằng chứng xác thực**. Nếu ứng dụng nằm sau reverse proxy, chỉ được tin header danh tính khi proxy/gateway đã xác thực, gỡ header do client cung cấp và có hợp đồng trust boundary cụ thể.

### 5.3. HTTP Basic gửi credential mỗi request

Basic không “đổi” username/password thành một token phiên tự động ở client. Một request mới thường phải gửi `Authorization: Basic ...` lần nữa. Trình duyệt có thể cache Basic credential và tự gửi lại; quan sát DevTools Network, không suy ra tính stateless tuyệt đối chỉ từ cơ chế Basic. Nếu ứng dụng có thêm session/cookie hoặc chuỗi xác thực khác, toàn hệ thống có thể có state riêng.

## 6. Kiểm thử trực tiếp converter: trước khi có xác thực

`WebTestClient` qua server thật cho thấy kết quả cuối, nhưng để nhìn rõ **giai đoạn chuyển đổi** cần test trực tiếp `ServerHttpBasicAuthenticationConverter` với `MockServerWebExchange`.

Chúng ta muốn chứng minh:

1. Header `Basic` hợp lệ tạo một `UsernamePasswordAuthenticationToken` **chưa xác thực**.
2. Token có `principal` là username từ header, `credentials` là password tạm thời, **không có role** được cấp từ converter.
3. Không có Basic header thì converter phát `Mono.empty()`, không tự sinh “anonymous user” đã xác thực.
4. Password chứa dấu `:` vẫn được giữ sau dấu hai chấm đầu tiên.

Đây là các kiểm thử **chuyển đổi HTTP → token**, chưa kiểm tra hash/password. Chính bước manager và integration test sẽ làm việc đó.

## 7. Kiểm thử manager và HTTP bằng StepVerifier + WebTestClient

Tạo `src/test/java/demo/basic/BasicAuthConversionTests.java`. Test này dùng cùng context Spring Boot, chạy server thật trên **cổng ngẫu nhiên** với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và inject `WebTestClient`. Các test converter dùng mock exchange thuần; các test manager gọi trực tiếp `authenticate`; các test HTTP đi qua Spring Security WebFilter toàn bộ.

```java
package demo.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.security.web.server.authentication.ServerHttpBasicAuthenticationConverter;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BasicAuthConversionTests {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveAuthenticationManager manager;

    private final ServerHttpBasicAuthenticationConverter converter =
        new ServerHttpBasicAuthenticationConverter();

    @Test
    void basicHeaderBecomesAnUnauthenticatedToken() {
        var request = MockServerHttpRequest.get("/api/me")
            .headers(headers -> headers.setBasicAuth("alice", "alice123"));

        var exchange = MockServerWebExchange.from(request);
        StepVerifier.create(converter.convert(exchange))
            .assertNext(auth -> {
                assertInstanceOf(UsernamePasswordAuthenticationToken.class, auth);
                assertEquals("alice", auth.getPrincipal());
                assertEquals("alice123", auth.getCredentials());
                assertFalse(auth.isAuthenticated());
                assertTrue(auth.getAuthorities().isEmpty());
            })
            .verifyComplete();
    }

    @Test
    void noAuthorizationHeaderCreatesNoBasicRequestToken() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/me"));

        StepVerifier.create(converter.convert(exchange))
            .verifyComplete();
    }

    @Test
    void theFirstColonSeparatesUsernameFromPassword() {
        var request = MockServerHttpRequest.get("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "alice", "pass:with:colons"));

        StepVerifier.create(
                converter.convert(MockServerWebExchange.from(request)))
            .assertNext(auth -> {
                assertEquals("alice", auth.getPrincipal());
                assertEquals("pass:with:colons", auth.getCredentials());
                assertFalse(auth.isAuthenticated());
            })
            .verifyComplete();
    }

    @Test
    void managerTurnsCorrectCredentialsIntoVerifiedAuthentication() {
        Authentication proposed =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice123");

        StepVerifier.create(manager.authenticate(proposed))
            .assertNext(verified -> {
                assertTrue(verified.isAuthenticated());
                assertEquals("alice", verified.getName());
                assertTrue(verified.getAuthorities().stream()
                    .anyMatch(role -> "ROLE_USER".equals(
                        role.getAuthority())));
            })
            .verifyComplete();
    }

    @Test
    void managerRejectsIncorrectPassword() {
        Authentication proposed =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "incorrect");

        StepVerifier.create(manager.authenticate(proposed))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void publicEndpointAcceptsAnonymous() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedEndpointChallengesMissingCredentials() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void httpBasicProducesTheExpectedPrincipal() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "alice", "alice123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello:alice");
    }

    @Test
    void wrongPasswordFailsAuthentication() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameDoesNotAuthenticate() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "unknown", "whatever"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validNonAdminCredentialsFailAuthorization() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "alice", "alice123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validAdminCredentialsCanAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Chạy:

```bash
mvn test
```

Với đúng class test trên, kỳ vọng **12 bài test pass** khi code/dependency đúng và server khởi động được. Không viết cứng stdout Maven vì log, thứ tự test, thời gian tải dependency và chi tiết response header có thể khác. Nếu test fail, hãy xem *expected/actual* ở assertion, stack trace và cấu hình bean. Bài chỉ đưa **mã và kết quả kỳ vọng để chạy**, không tuyên bố đã chạy bộ test trong môi trường của người đọc.

### 7.1. Đọc từng nhóm kiểm thử

- **Converter**: ba test đầu cho thấy Basic header được chuyển thành request `Authentication` chưa tin cậy, không có header thì không có token, và dấu hai chấm trong password không làm sai phần password.
- **Manager**: hai test sau chứng minh `PasswordEncoder`/user store/manager biến username-password thành principal có role đáng tin, hoặc báo lỗi khi sai credential.
- **HTTP**: các test còn lại chứng minh converter và manager đã được WebFilter nối vào request thật; authorization nhìn thấy kết quả, trả 200/401/403 theo quyền.
- **Body chính xác**: status 200 chưa đủ. `hello:alice` chứng minh controller nhìn thấy đúng principal sau xác thực.
- **Không tin credential từ test mock khi kiểm tra HTTP**: các request `WebTestClient` dùng `headers.setBasicAuth(...)`, giống một HTTP client thật. Test direct converter/manager không thay thế được integration test qua WebFilter.

### 7.2. Tách bạch “converter đã hoạt động” và “hệ thống đã an toàn”

Một test converter có thể pass dù source user store bị lỗi, vì converter không gọi database. Một test manager có thể pass dù HTTP Basic filter chưa được gắn vào chain. Một test endpoint `200` có thể pass dù URL vô tình public nếu không có các **test âm** `401` và `403`. Vì vậy ba lớp kiểm thử bổ sung cho nhau và nên được chạy cùng nhau khi thay cơ chế đăng nhập.

## 8. Vì sao Reactor Context quan trọng ngay sau Authentication?

Sau khi manager xác thực thành công, Spring Security Reactive giúp truyền `Authentication` qua `ReactiveSecurityContextHolder` trên đường subscription của request. Điều này quan trọng vì một WebFlux event-loop thread có thể phục vụ nhiều yêu cầu xen kẽ; `SecurityContextHolder` theo ThreadLocal của mô hình Servlet không phải nguồn chân lý phù hợp cho reactive.

Fragment được khuyến nghị ở service:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đây chỉ là **một method fragment**, không phải file Java độc lập; trong ví dụ runnable, controller đã có đầy đủ import và class bao quanh.

Một request khác gửi header Basic cho `bob` không được đọc lại username từ request `alice` trước đó. Tránh các lỗi:

- Lưu `Authentication` hoặc username vào trường mutable của singleton service rồi đọc khi `Mono.delay` hoàn tất.
- Gọi `subscribe()` thủ công để tiếp tục xác thực/ghi audit ngoài pipeline.
- Cache `Mono<Authentication>` theo key toàn cục mà không phân vùng user/tenant.
- Đọc `ThreadLocal currentUser` khi đổi scheduler và cho rằng nó luôn gắn với request.

Một số công việc bất đồng bộ được tách hẳn khỏi Reactor pipeline có thể **không còn security context của request**; hãy truyền identity đã xác minh bằng hợp đồng tin cậy và kiểm tra quyền khi thực thi, không tự sử dụng tên user do client khai.

## 9. Tùy biến việc chuyển đổi: khi nào mới cần?

Thông thường chỉ cần:

```java
return http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .httpBasic(Customizer.withDefaults())
    .build();
```

Đây là **fragment** trong một bean `SecurityWebFilterChain`, không phải chương trình đầy đủ. Spring Security tự cấu hình converter HTTP Basic. Đừng tạo một parser Base64 tự chế để đưa user đã xác thực trực tiếp vào SecurityContext.

Nếu có yêu cầu thực sự cần một cấu trúc header khác hoặc chính sách charset đặc biệt, Spring Security cho phép tùy biến `ServerAuthenticationConverter` trên `AuthenticationWebFilter`. Về mặt API, cơ chế (fragment) là:

```java
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(reactiveAuthenticationManager);
filter.setServerAuthenticationConverter(customConverter);
```

Đoạn trên là **minh họa API**, không phải cấu hình hoàn chỉnh: cần xác định `reactiveAuthenticationManager`, `customConverter`, matcher, vị trí WebFilter trong `SecurityWebFilterChain`, success/failure handler, context repository và behavior của HTTP Basic challenge. Nếu chỉ muốn dùng Basic chuẩn, hãy giữ DSL `httpBasic` thay vì tự thêm filter, bởi việc thêm nhầm filter có thể gây bypass hoặc xử lý credential hai lần.

Một custom converter an toàn phải:

1. Chỉ chấp nhận đúng scheme/format đã định nghĩa; không tin header tùy ý như `X-User` chỉ vì nó có username.
2. Validate kích thước header, Base64 hợp lệ, dấu phân cách, username và charset; không cho phép fallback “đăng nhập mặc định” khi lỗi.
3. Trả `Authentication` với `authenticated=false`, chưa có authorities tự khai.
4. Để manager xử lý xác thực và lấy role từ nguồn đáng tin.
5. Không log/password echo và không cất password lâu dài.
6. Có test âm cho request thiếu header, sai scheme, malformed Base64, user không tồn tại, mật khẩu sai, header trùng lặp và khác biệt charset.

**Nếu cần Bearer token/OAuth2/JWT**, cấu hình `oauth2ResourceServer(...)` với các thành phần xác minh token phù hợp. Đừng lấy phần sau chữ `Bearer` rồi biến thành username/password hoặc giao cho password manager: hai phương thức xác thực có trust model khác nhau.

## 10. Phân biệt Authentication với Authorization và với HTTP status

| Kết quả | Ý nghĩa thường gặp trong demo | Nên kiểm tra gì? |
| --- | --- | --- |
| `200 OK` trên `/api/me` | Header Basic hợp lệ, manager xác thực, endpoint cho phép | Body đúng principal, không lẫn user |
| `401 Unauthorized` không credential | Converter không tạo request token; endpoint yêu cầu authenticated | `WWW-Authenticate`, có đúng Basic challenge không |
| `401` sai password | Converter đã tạo request token nhưng manager từ chối | Hash, user store, account status, client password |
| `401` user không tồn tại | Không tìm được principal đáng tin | Không tiết lộ user tồn tại thông qua lỗi |
| `403 Forbidden` với Alice ở `/api/admin` | Authentication thành công, role không đủ | `hasRole("ADMIN")`, authority nguồn tin cậy |
| `302 Found` | Có thể có form login hoặc redirect khác | `Location`, config login/session/HTTPS, không suy ra Basic đã xác thực |
| `404 Not Found` | Có thể mapping endpoint không tồn tại | Mapping/controller; một fallback deny-all có thể chặn sớm bằng 401/403 |
| `403` với POST/PUT | Có thể CSRF token thiếu, không chỉ quyền | Method, CSRF policy và token; đừng tắt CSRF mù quáng |

Các status trên phụ thuộc cấu hình và HTTP challenge; chúng **không chứng minh toàn bộ kiến trúc bảo mật**. Chỉ đo một mã 200 mà không kiểm tra body/authorization không phát hiện được lỗi lộ dữ liệu theo người dùng.

### 10.1. Hai trường hợp 401 khác nhau phải điều tra ở tầng khác nhau

1. **Không gửi `Authorization`:** converter trả empty, bước manager có thể không chạy. Điều tra client, proxy loại header, cấu hình filter và matcher.
2. **Gửi header Basic hợp lệ nhưng password không đúng:** converter tạo token, manager từ chối. Điều tra `ReactiveUserDetailsService`, `PasswordEncoder.matches`, prefix `{bcrypt}` và trạng thái user.

Tương tự, một header bị sai charset có thể khiến username/password được diễn giải khác so với những gì người dùng nhập. Không khắc phục bằng cách bypass manager hoặc bật `permitAll()`; hãy xác định giao thức client/server và nâng chất lượng test.

## 11. Những lỗi phổ biến và cách sửa

### 11.1. Cho token đã xác thực ngay tại converter

**Sai (fragment cố ý nguy hiểm):**

```java
return Mono.just(
    UsernamePasswordAuthenticationToken.authenticated(
        usernameFromHeader, null, adminAuthoritiesFromHeader));
```

Mã này tin `usernameFromHeader` và quyền tự khai là đã xác thực, bỏ qua kiểm tra mật khẩu. Chỉ tạo **unauthenticated token** rồi để manager xác minh; authorities phải xuất phát từ user store hoặc hệ thống danh tính đã được tin cậy.

### 11.2. Lưu password plaintext hoặc tự hash lại trước khi matches

`PasswordEncoder.matches(rawPassword, storedHash)` là phép kiểm đúng. Không so `encoder.encode(raw).equals(storedHash)` vì hash có salt khác nhau. Không lưu raw password trong database, log hoặc response. Dùng hash chuyên dụng như BCrypt/Argon2 theo chính sách và giới hạn tài nguyên.

### 11.3. Dùng Base64 như mã hóa bảo mật

`Authorization: Basic ...` có thể được giải mã bởi bất kỳ ai đọc được traffic hoặc log. Không gửi qua HTTP công khai; dùng HTTPS end-to-end thích hợp, không đưa raw header lên log/error telemetry hoặc ticket. Proxy/ingress phải xử lý header có kiểm soát.

### 11.4. Tự lấy username bằng cách cắt header

`String[] parts = decoded.split(":")` có thể làm mất phần password sau dấu hai chấm đầu tiên. Tự parser cũng dễ bỏ qua base64 malformed, charset, whitespace và header trùng lặp. Dùng converter chuẩn của Spring, chỉ tùy biến khi thực sự cần và có negative tests.

### 11.5. Đọc getPrincipal() trước khi authenticate như danh tính đáng tin

Ở request token, principal đơn thuần là text do client gửi. Chỉ kết quả manager xác thực thành công mới đáng tin. Một `Authentication.isAuthenticated()` bị lập trình viên tự set true không phải bằng chứng mật khẩu đã được kiểm tra.

### 11.6. Nhầm WebFlux với Servlet

`BasicAuthenticationFilter`, `HttpSecurity` và `SecurityContextHolder` ThreadLocal thường xuất hiện trong bài Servlet. Ở WebFlux, chúng ta dùng `AuthenticationWebFilter`, `ServerHttpBasicAuthenticationConverter`, `ServerHttpSecurity` và `ReactiveSecurityContextHolder`. Không copy trực tiếp Java configuration từ Servlet sang Reactor.

### 11.7. Chuyển lỗi 401 thành cho phép

Đổi `anyExchange().permitAll()` chỉ để tránh 401 có thể làm endpoint bị công khai. Nếu sai credential thì sửa credential/hash/manager. Nếu sai matcher thì sửa chain/filter. Nếu role thiếu thì sửa authorization policy và quyền đúng của tài khoản; không tự cấp ADMIN cho mọi người.

### 11.8. Đánh đồng `{noop}` với hashing mạnh

`User.withUsername(...).password("{noop}secret")` chỉ thích hợp demo rất giới hạn; `noop` chấp nhận mật khẩu lưu plaintext. Ví dụ đầy đủ ở trên dùng `DelegatingPasswordEncoder` và hash BCrypt để tránh thói quen xấu này.

### 11.9. Tưởng Basic tự lưu session và có logout

Basic là phương thức gửi credential qua header request. HTTP client/browser có thể cache thông tin xác thực, nhưng không có lệnh logout thần kỳ chỉ bằng xóa một biến trên server. Trong hệ thống có login form/session đi kèm, cookie/session có vòng đời riêng. Với API stateless, cân nhắc token nếu bài toán và mô hình nguy cơ phù hợp, không lạm dụng Basic ở nơi khó bảo vệ mật khẩu người dùng.

## 12. Checklist triển khai thực tế

1. **Chọn cơ chế xác thực rõ ràng:** API chỉ Basic hay còn Form Login/Bearer? Chain nào nhận route nào, theo `securityMatcher`/`@Order`?
2. **Tạo user store đáng tin:** `ReactiveUserDetailsService` trả đúng user, hash còn nguyên, roles từ database/nguồn nội bộ. Nếu user không tồn tại, không tạo user “guest” có quyền.
3. **Cấu hình encoder nhất quán:** cùng policy để `encode` khi lưu và `matches` khi login; lưu prefix hash nếu dùng Delegating. Chỉ nâng cấp password hash theo luồng tin cậy.
4. **Wiring filter/manager:** `httpBasic` tạo luồng Basic; `ReactiveAuthenticationManager` xác thực; không tự gắn `Authentication` đã authenticated theo dữ liệu HTTP client.
5. **Chính sách quyền cuối:** phân biệt `authenticated()` và `hasRole(...)`, nên có default deny cho các đường chưa cấp phép.
6. **Bảo vệ bí mật:** HTTPS, không in raw password/Authorization header, giới hạn kích thước request, quản lý secrets và log redaction.
7. **Chống brute force:** rate limit, giám sát đăng nhập thất bại, credential stuffing và lockout/captcha/risk-based policy hợp lý; hash chậm không thay thế chống thử online.
8. **Không block event-loop:** truy xuất user bằng reactive repository/driver khi phù hợp, dùng scheduler cho việc CPU-intensive như password hashing theo chính sách/benchmark, không gọi `block()` trong handler.
9. **Test cả ba tầng:** converter output còn unauthenticated; manager cho đúng/sai credentials; HTTP trả 401/403/200 đúng role và body.
10. **Kiểm thử dữ liệu có chủ sở hữu:** sau khi xác thực, endpoint còn cần kiểm tra resource ownership/tenant để tránh “Alice xem được báo cáo Bob”.
11. **Trước production:** bỏ tài khoản mật khẩu hard-code, dùng quản lý account thực tế, đánh giá lifecycle, rotation/reset/MFA phù hợp, và cập nhật Spring Boot/Security còn được hỗ trợ.

## 13. Câu hỏi tự đánh giá

**Câu 1.** Khi nhận `Authorization: Basic ...`, Spring có biết mật khẩu đúng chỉ từ Base64 không?  
**Không.** Base64 chỉ biểu diễn bytes. Converter tạo request token chưa xác thực; manager mới kiểm tra user/hash/trạng thái.

**Câu 2.** Có thể tin `UsernamePasswordAuthenticationToken.getAuthorities()` từ một token mà converter tự tạo không?  
**Không.** Request token chưa được xác thực phải không có authorities đáng tin. Quyền chỉ được cấp bởi manager và nguồn tin cậy.

**Câu 3.** Khi không có Basic header, tại sao endpoint protected có thể trả 401 dù manager không chạy?  
Vì converter không tạo token, nhưng authorization vẫn yêu cầu danh tính; entry point gửi Basic challenge cho client.

**Câu 4.** Đăng nhập Alice thành công nhưng gọi `/api/admin` nhận 403: có phải converter sai?  
**Không nhất thiết.** Authentication đã thành công; authorization nhận thấy Alice thiếu `ROLE_ADMIN`.

**Câu 5.** Nếu password là `p:a:ss`, có thể dùng `decoded.split(":")[1]` không?  
**Không.** Cần giữ toàn bộ phần sau dấu `:` đầu tiên; hãy dùng converter chuẩn để tránh sai parser.

**Câu 6.** Vì sao không dùng `ThreadLocal` lưu username ở controller WebFlux?  
Vì các request có thể đan xen trên cùng thread và một pipeline có thể đổi scheduler. Dùng Reactor Context của request thông qua `ReactiveSecurityContextHolder`.

**Câu 7.** Tại sao chỉ có unit test converter là chưa đủ?  
Vì converter không kiểm mật khẩu, không nối security filter với web chain và không cấp quyền. Cần manager tests và HTTP integration tests.

**Câu 8.** HTTP Basic có an toàn khi gửi trên HTTP không mã hóa không?  
**Không.** Base64 có thể đảo ngược dễ dàng; dùng HTTPS, bảo vệ credentials và tránh log header.

**Câu 9.** Nếu ứng dụng dùng Bearer JWT, có nên tái sử dụng Basic converter để lấy “username” trong token?  
**Không.** JWT/Bearer phải được xác minh chữ ký/issuer/audience/claims theo resource server, không phải giải mã username/password bằng Basic.

**Câu 10.** Có phải mọi response 401 đều có nguyên nhân sai password?  
**Không.** Có thể không có header, dùng sai scheme, charset không khớp, user không tồn tại, mật khẩu sai hoặc config entry point; phải điều tra đúng tầng.

### Tài liệu tham khảo chính thức

- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security API, `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security API, `ServerHttpBasicAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerHttpBasicAuthenticationConverter.html
- Spring Security API, `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security, `Authentication` interface: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html
- Spring Security, *Password Storage*: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- IETF RFC 7617, *The 'Basic' HTTP Authentication Scheme*: https://www.rfc-editor.org/rfc/rfc7617

**Tóm ý quan trọng:** `Authorization: Basic ...` chỉ mang **credential do client khai**. `ServerHttpBasicAuthenticationConverter` tạo `UsernamePasswordAuthenticationToken` **chưa xác thực**; `ReactiveAuthenticationManager` đối chiếu user và password hash để trả `Authentication` **đã xác thực**, sau đó Spring Security đưa nó vào `ReactiveSecurityContextHolder` và kiểm tra quyền endpoint. Giữ hai trạng thái này tách biệt là nguyên tắc cốt lõi tránh giả mạo danh tính khi triển khai HTTP Basic trong WebFlux.